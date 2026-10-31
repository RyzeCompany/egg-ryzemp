#!/usr/bin/env python3
"""Release-driven, transactional updater embedded in the Pterodactyl egg."""
import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

MP = 'RyzeCompany/RyzeMP'
RTC = 'RyzeCompany/RyzeRTC'
MANIFEST = 'ryzemp-update.json'
PLATFORM = {'os': 'linux', 'arch': 'x86_64', 'php': '8.4', 'php_api': 20240924, 'zts': True}
TARGETS = ('bin/php7', '.ryzertc-runtime', 'RyzeMP.phar', 'start-ryzemp.sh', '.ryzemp-install.json')
BACKUPS = ('php7', 'ryzertc-runtime', 'RyzeMP.phar', 'start-ryzemp.sh', 'install.json')


class UpdateError(Exception):
    pass


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        require(url.startswith('https://'), 'GitHub intento redirigir sin HTTPS.')
        return super().redirect_request(request, response, code, message, headers, url)


def require(condition, message):
    if not condition:
        raise UpdateError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def token(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}', value),
            'Nombre de release o archivo invalido.')
    return value


def digest(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value), 'SHA-256 invalido.')
    return value


def asset_url(repo, tag, name):
    return f'https://github.com/{repo}/releases/download/{token(tag)}/{token(name)}'


def download(url, destination, limit):
    require(url.startswith(('https://api.github.com/repos/RyzeCompany/',
                            'https://github.com/RyzeCompany/')), 'Origen de descarga no permitido.')
    request = urllib.request.Request(url, headers={
        'User-Agent': 'RyzeMP-Pterodactyl-Updater/1', 'Accept': 'application/vnd.github+json'
        if url.startswith('https://api.github.com/') else 'application/octet-stream'})
    try:
        opener = urllib.request.build_opener(HTTPSRedirects())
        with opener.open(request, timeout=60) as response, destination.open('wb') as output:
            require(response.geturl().startswith('https://'), 'Redireccion sin HTTPS.')
            total = 0
            while block := response.read(128 * 1024):
                total += len(block)
                require(total <= limit, 'Descarga demasiado grande.')
                output.write(block)
    except (OSError, urllib.error.URLError) as error:
        raise UpdateError(f'Fallo al descargar desde GitHub: {error}. No se sustituyo la instalacion.') from error


def fetch_json(url, directory, limit=4 * 1024 * 1024):
    path = directory / 'response.json'
    download(url, path, limit)
    try:
        return json.loads(path.read_text())
    except (ValueError, UnicodeError) as error:
        raise UpdateError('GitHub devolvio JSON invalido.') from error


def select_release(channel, directory):
    require(channel in ('pruebas', 'estable'), 'Canal invalido: usa pruebas o estable.')
    releases = []
    for page in range(1, 6):
        batch = fetch_json(f'https://api.github.com/repos/{MP}/releases?per_page=100&page={page}', directory)
        require(isinstance(batch, list), 'Respuesta de releases invalida o limite de GitHub alcanzado.')
        releases.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise UpdateError('Demasiadas releases para seleccionar con seguridad; actualiza el egg.')
    candidates = []
    for release in releases:
        if release.get('draft') is not False or release.get('prerelease') is not (channel == 'pruebas'):
            continue
        assets = [a for a in release.get('assets', []) if a.get('name') == MANIFEST and a.get('state') == 'uploaded']
        if assets:
            require(len(assets) == 1, 'Manifiesto duplicado en la release.')
            candidates.append((release, assets[0]))
    require(candidates, f'No hay una release preparada para el canal {channel}. Se conserva la instalacion actual.')
    release, asset = max(candidates, key=lambda item: (item[0]['published_at'], item[0]['id']))
    url = asset_url(MP, release['tag_name'], MANIFEST)
    require(asset.get('browser_download_url') == url, 'Origen del manifiesto invalido.')
    expected = asset.get('digest', '')
    require(expected.startswith('sha256:'), 'GitHub no proporciona el SHA-256 del manifiesto.')
    manifest = fetch_json(url, directory, 64 * 1024)
    require(sha(directory / 'response.json') == digest(expected[7:]), 'SHA-256 del manifiesto incorrecto.')
    require(isinstance(manifest, dict), 'Manifiesto de actualizacion invalido.')
    require(type(manifest.get('schema')) is int and manifest['schema'] == 1,
            'Formato nuevo de actualizaciones: actualiza el egg del panel.')
    require(manifest.get('channel') == channel and manifest.get('release') == release['tag_name'],
            'El manifiesto no corresponde al canal/release seleccionado.')
    require(manifest.get('platform') == PLATFORM, 'La release requiere otro PHP o arquitectura; actualiza el egg.')
    phar, rtc = manifest['phar'], manifest['ryzertc']
    require(isinstance(phar, dict) and isinstance(rtc, dict), 'Requisitos del manifiesto invalidos.')
    token(phar['asset'])
    require(phar['asset'].endswith('.phar'), 'La release no contiene un PHAR.')
    digest(phar['sha256'])
    token(rtc['tag'])
    token(rtc['asset'])
    digest(rtc['sha256'])
    require(rtc['asset'].endswith('.zip') and type(rtc['api']) is int and rtc['api'] >= 2,
            'Requisito de RyzeRTC invalido.')
    token(rtc['version'])
    phar_assets = [a for a in release['assets'] if a.get('name') == phar['asset'] and a.get('state') == 'uploaded']
    require(len(phar_assets) == 1 and phar_assets[0].get('digest') == 'sha256:' + phar['sha256'],
            'PHAR ausente, incompleto o con SHA-256 distinto en GitHub.')
    return manifest, {'channel': channel, 'release': release['tag_name'],
        'published_at': release['published_at'], 'release_id': release['id'], 'manifest_sha256': expected[7:]}


def unpack_runtime(archive, destination):
    destination.mkdir()
    links, seen, total = [], set(), 0
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            name = pathlib.PurePosixPath(entry.filename)
            require(not name.is_absolute() and '..' not in name.parts and '\\' not in entry.filename,
                    'Ruta insegura en el ZIP nativo.')
            require(name.parts and name not in seen, 'Entrada duplicada en el ZIP nativo.')
            seen.add(name)
            total += entry.file_size
            require(total <= 160 * 1024 * 1024, 'ZIP nativo demasiado grande.')
            path = destination.joinpath(*name.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            if entry.is_dir():
                path.mkdir(exist_ok=True)
            elif stat.S_ISLNK(entry.external_attr >> 16):
                target = package.read(entry).decode('utf-8')
                require(re.fullmatch(r'[A-Za-z0-9._-]+', target) and target not in ('.', '..'),
                        'Enlace inseguro en el ZIP nativo.')
                links.append((path, target))
            else:
                with package.open(entry) as source, path.open('wb') as output:
                    shutil.copyfileobj(source, output)
                path.chmod(0o644)
    for path, target in links:
        path.symlink_to(target)
        require(path.is_file() and path.resolve().is_relative_to(destination.resolve()), 'Enlace nativo roto.')
    sums = destination / 'SHA256SUMS.txt'
    require(sums.is_file() and not sums.is_symlink(), 'Falta el manifiesto SHA-256 nativo.')
    verified, verified_hashes = set(), set()
    for line in sums.read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64}) [ *](.+)', line)
        require(match, 'Manifiesto SHA-256 nativo invalido.')
        name = pathlib.PurePosixPath(match[2])
        require(not name.is_absolute() and '..' not in name.parts, 'Ruta SHA-256 insegura.')
        path = destination.joinpath(*name.parts)
        require(path.is_file() and sha(path) == match[1], f'Archivo nativo corrupto: {name}.')
        verified.add(path.resolve())
        verified_hashes.add(match[1])
    for path in destination.rglob('*'):
        if path.is_file() and path != sums:
            # The published dev.3 ZIP dereferences libdatachannel's two soname links.
            alias = path.parent == destination / 'lib' and re.fullmatch(r'libdatachannel\.so(?:\.[0-9]+)*', path.name)
            require(path.resolve() in verified or (alias and sha(path) in verified_hashes),
                    f'Archivo nativo sin SHA-256: {path.name}.')


def run_php(php, arguments, runtime=None):
    environment = os.environ.copy()
    if runtime:
        environment['LD_LIBRARY_PATH'] = str(runtime / 'lib')
    try:
        result = subprocess.run([str(php), '-n', *arguments], env=environment,
                                capture_output=True, text=True, timeout=30)
        require(result.returncode == 0, 'PHP rechazo el PHAR o RyzeRTC: ' + (result.stdout + result.stderr)[-2000:])
        return result.stdout
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UpdateError(f'No se pudo ejecutar el PHP preparado: {error}.') from error


def validate(php_dir, phar, runtime, rtc):
    php = php_dir / 'bin/php'
    require(php.is_file() and os.access(php, os.X_OK), 'PHP preparado no ejecutable.')
    abi = json.loads((runtime / 'php-abi.json').read_text())
    require(all(abi.get(k) == v for k, v in {'php': '8.4', 'php_api': 20240924,
        'zts': True, 'architecture': 'x86_64'}.items()), 'ABI nativa incompatible.')
    opcache = list(php_dir.rglob('opcache.so'))
    require(len(opcache) == 1, 'No se encuentra OPCache en el PHP preparado.')
    options = ['-d', f'zend_extension={opcache[0]}', '-d', f'extension={runtime}/ryzertc.so']
    output = run_php(php, [*options, '-r', '''
        if(PHP_VERSION_ID < 80400 || PHP_VERSION_ID >= 80500 || !PHP_ZTS || PHP_INT_SIZE !== 8 ||
           !extension_loaded("Zend OPcache") || !extension_loaded("ryzertc")) exit(1);
        echo json_encode(["api" => RyzeRTC\\Runtime::apiVersion(), "version" => RyzeRTC\\Runtime::version()]);
    '''], runtime)
    require(json.loads(output) == {'api': rtc['api'], 'version': rtc['version']}, 'Version/API RyzeRTC incompatible.')
    run_php(php, ['-r', '''
        try {
            $p = new Phar($argv[1]);
            if($p->count() === 0 || !str_contains($p->getStub(), "<?php") ||
               !isset($p["src/PocketMine.php"]) || !isset($p["vendor/autoload.php"])) exit(1);
        } catch(Throwable $e) { exit(1); }
    ''', str(phar)])
    output = run_php(php, [*options, str(phar), '--version'], runtime)
    require('RyzeMP ' in output, 'El PHAR no identifica RyzeMP.')
    ini = php_dir / 'bin/php.ini'
    require(ini.is_file(), 'Falta php.ini en el PHP preparado.')
    lines = [line for line in ini.read_text().splitlines()
        if not re.match(r'\s*extension_dir\s*=', line) and not re.match(r'\s*extension\s*=.*ryzertc', line)]
    extension_dir = '/home/container/bin/php7/' + str(opcache[0].parent.relative_to(php_dir))
    ini.write_text('\n'.join(lines) + f'\nextension_dir="{extension_dir}"\n'
        'extension="/home/container/.ryzertc-runtime/ryzertc.so"\n')


def remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def write_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def safe_targets(root):
    for relative in (*TARGETS, '.ryzemp-backups/previous', '.ryzemp-update-transaction'):
        current = root
        for part in pathlib.PurePosixPath(relative).parts:
            current /= part
            require(not current.is_symlink(), f'Ruta administrada con enlace simbolico: {current}.')


def recover(root):
    transaction = root / '.ryzemp-update-transaction'
    if not transaction.exists():
        return
    journal = transaction / 'journal.json'
    if not journal.exists():
        require(all(p.name == 'journal.json.tmp' for p in transaction.iterdir()),
                'Diario de actualizacion ausente; revisa .ryzemp-update-transaction.')
        shutil.rmtree(transaction)
        return
    entries = json.loads(journal.read_text())
    require([e['target'] for e in entries] == list(TARGETS), 'Diario de recuperacion invalido.')
    if (transaction / 'COMMITTED').exists():
        previous = root / '.ryzemp-backups/previous'
        if (transaction / 'old').exists():
            previous.parent.mkdir(exist_ok=True, mode=0o700)
            remove(previous)
            os.replace(transaction / 'old', previous)
    else:
        for index, entry in reversed(list(enumerate(entries))):
            destination, backup = root / entry['target'], transaction / 'old' / BACKUPS[index]
            if backup.exists():
                remove(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup, destination)
            elif entry['had_old'] is False:
                remove(destination)
        print('[RyzeMP] Instalacion anterior recuperada.', flush=True)
    shutil.rmtree(transaction)


def signature(path):
    if not path.exists():
        return None
    if path.is_file():
        return (sha(path), stat.S_IMODE(path.stat().st_mode))
    return [(str(p.relative_to(path)), ('link', os.readlink(p)) if p.is_symlink() else sha(p))
            for p in sorted(path.rglob('*')) if p.is_file() or p.is_symlink()]


def commit(root, prepared):
    # Identical reinstalls must retain the last useful backup.
    if all(signature(root / target) == signature(source) for target, source in zip(TARGETS, prepared)):
        print('[RyzeMP] La ultima release ya esta instalada y verificada.', flush=True)
        return False
    transaction = root / '.ryzemp-update-transaction'
    transaction.mkdir(mode=0o700)
    entries = [{'target': target, 'had_old': (root / target).exists()} for target in TARGETS]
    write_json(transaction / 'journal.json', entries)
    (transaction / 'old').mkdir()
    try:
        for index, (target, source) in enumerate(zip(TARGETS, prepared)):
            destination = root / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            if entries[index]['had_old']:
                os.replace(destination, transaction / 'old' / BACKUPS[index])
            os.replace(source, destination)
        write_json(transaction / 'COMMITTED', True)
    except BaseException:
        recover(root)
        raise
    recover(root)
    return True


def update(root, php_dir, startup, channel):
    root = root.resolve()
    safe_targets(root)
    descriptor = os.open(root / '.ryzemp-update.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recover(root)
        with tempfile.TemporaryDirectory(prefix='.ryzemp-stage.', dir=root) as temp:
            stage = pathlib.Path(temp)
            manifest, state = select_release(channel, stage)
            old = root / '.ryzemp-install.json'
            if old.exists():
                installed = json.loads(old.read_text())
                if installed.get('channel') == channel:
                    require((state['published_at'], state['release_id']) >=
                        (installed['published_at'], installed['release_id']), 'Se rechazo una bajada automatica de version.')
                    if installed.get('release') == state['release']:
                        require(installed['manifest_sha256'] == state['manifest_sha256'],
                                'La release instalada fue modificada; publica una nueva release.')
            print(f"[RyzeMP] Canal {channel}: {state['release']} + RyzeRTC {manifest['ryzertc']['tag']}", flush=True)
            phar, rtc = stage / 'RyzeMP.phar', stage / 'runtime.zip'
            download(asset_url(MP, state['release'], manifest['phar']['asset']), phar, 100 * 1024 * 1024)
            require(sha(phar) == manifest['phar']['sha256'], 'SHA-256 del PHAR incorrecto; se conserva la instalacion.')
            native = manifest['ryzertc']
            download(asset_url(RTC, native['tag'], native['asset']), rtc, 100 * 1024 * 1024)
            require(sha(rtc) == native['sha256'], 'SHA-256 de RyzeRTC incorrecto; se conserva la instalacion.')
            runtime = stage / 'runtime'
            unpack_runtime(rtc, runtime)
            php = stage / 'php7'
            shutil.copytree(php_dir, php, symlinks=True)
            validate(php, phar, runtime, native)
            start = stage / 'start-ryzemp.sh'
            shutil.copyfile(startup, start)
            start.chmod(0o755)
            phar.chmod(0o644)
            state['schema'] = 1
            state['phar'] = manifest['phar']
            state['ryzertc'] = native
            state_file = stage / 'state.json'
            write_json(state_file, state)
            changed = commit(root, (php, runtime, phar, start, state_file))
            if changed:
                print('[RyzeMP] Actualizacion verificada. Copia anterior: .ryzemp-backups/previous/', flush=True)
            return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=pathlib.Path, required=True)
    parser.add_argument('--php-dir', type=pathlib.Path, required=True)
    parser.add_argument('--startup', type=pathlib.Path, required=True)
    parser.add_argument('--channel', default='pruebas', choices=('pruebas', 'estable'))
    args = parser.parse_args()
    try:
        update(args.root, args.php_dir, args.startup, args.channel)
    except (UpdateError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(f'[RyzeMP] Actualizacion detenida: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
