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
GO_REPO = 'RyzeCompany/RyzeVanillaGen'
GO_TAG = 'v0.1.0'
# First independent release: immutable checksum from GitHub's published asset.
GO_SHA256 = '3cddcb4be9bd17eaa3225be5d167fb63328566c252a8c4fe7b1e3b9e7d716dc7'
MANIFEST = 'ryzemp-update.json'
PLATFORM = {'os': 'linux', 'arch': 'x86_64', 'php': '8.4', 'php_api': 20240924, 'zts': True}
# Install the guarded launcher first, including when upgrading from an older egg.
# Recover transactions left by the previous RyzeRTC-only Egg as well.
LEGACY_TARGETS = ('start-ryzemp.sh', 'bin/php7', '.ryzertc-runtime', 'RyzeMP.phar', '.ryzemp-install.json')
LEGACY_BACKUPS = ('start-ryzemp.sh', 'php7', 'ryzertc-runtime', 'RyzeMP.phar', 'install.json')
PREVIOUS_TARGETS = ('start-ryzemp.sh', 'bin/php7', '.ryzertc-runtime', 'RyzeMP.phar',
                    '.ryzemp-vanillagen', '.ryzemp-install.json')
PREVIOUS_BACKUPS = ('start-ryzemp.sh', 'php7', 'ryzertc-runtime', 'RyzeMP.phar',
                    'vanillagen', 'install.json')
# Keep all software inside bin/; ordinary world, player and plugin data stay at server root.
RUNTIME_ROOT = pathlib.Path('bin/ryzemp')
STATE_FILE = RUNTIME_ROOT / 'install.json'
BACKUP_ROOT = RUNTIME_ROOT / 'backups/previous'
TRANSACTION_ROOT = RUNTIME_ROOT / 'update-transaction'
TARGETS = ('start-ryzemp.sh', 'bin/php7', 'bin/ryzemp/ryzertc', 'RyzeMP.phar',
           'bin/ryzemp/vanillagen', 'bin/ryzemp/nethernet', 'bin/ryzemp/install.json')
BACKUPS = ('start-ryzemp.sh', 'php7', 'ryzertc', 'RyzeMP.phar',
           'vanillagen', 'nethernet', 'install.json')
GO_FILENAME = 'vanillagen-linux-amd64'
# bin/ryzemp/nethernet remains in TARGETS solely to remove obsolete bridges
# transactionally and retain them in the rollback backup. Never download one.
GO_PROTOCOL = 7
GO_ALGORITHM = 4


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
                            'https://github.com/RyzeCompany/')),
            'Origen de descarga no permitido.')
    request = urllib.request.Request(url, headers={
        'User-Agent': 'RyzeMP-Pterodactyl-Updater/1', 'Accept': 'application/vnd.github+json'
        if url.startswith('https://api.github.com/') else 'application/octet-stream'})
    # Optional in CI; public hosts do not need a token. Never forward it to assets
    # or redirects, including GitHub's external signed download hosts.
    api_token = os.environ.get('RYZEMP_GITHUB_TOKEN', '')
    if api_token and url.startswith('https://api.github.com/repos/RyzeCompany/'):
        request.add_unredirected_header('Authorization', 'Bearer ' + api_token)
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
    require(type(manifest.get('schema')) is int and manifest['schema'] in (1, 2),
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
    if manifest['schema'] == 1:
        require('vanillagen' not in manifest, 'El manifiesto antiguo no admite Go.')
    else:
        go = manifest.get('vanillagen')
        require(isinstance(go, dict), 'La release de worldgen Go necesita vanillagen.')
        require(go.get('asset') == GO_FILENAME, 'Nombre del ejecutable Go invalido.')
        digest(go.get('sha256'))
        require(type(go.get('protocol')) is int and go['protocol'] == GO_PROTOCOL
                and type(go.get('algorithm')) is int and go['algorithm'] == GO_ALGORITHM
                and go.get('stage') == 'full',
                'La version del protocolo/algoritmo Go no coincide con RyzeMP.')
        # Legacy schema-2 Go metadata is accepted and checked for compatibility,
        # but the binary itself comes ONLY from RyzeVanillaGen's independent release.
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


def require_space(directory, needed, operation):
    free = shutil.disk_usage(directory).free
    require(free >= needed,
            f'Espacio insuficiente para {operation} en {directory}: '
            f'se necesitan {(needed + 1048575) // 1048576} MiB libres y hay {free // 1048576} MiB. '
            'Se conserva la instalacion actual.')


def run_php(php, arguments, runtime=None, *, temp_root):
    environment = os.environ.copy()
    if runtime:
        environment['LD_LIBRARY_PATH'] = str(runtime / 'lib')
    try:
        # Wings mounts a small tmpfs at /tmp, even in installer containers.
        # The PHAR stub expands before --version, so every probe needs disk-backed
        # private temporary storage and cleanup on success, failure and timeout.
        with tempfile.TemporaryDirectory(prefix='.ryzemp-php-check.', dir=temp_root) as temporary:
            environment['TMPDIR'] = temporary
            result = subprocess.run([str(php), '-n', '-d', f'sys_temp_dir={temporary}', *arguments],
                                    env=environment, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        if result.returncode != 0 and any(value in output.lower() for value in
                ('no space left on device', 'errno=28', 'disk quota exceeded')):
            raise UpdateError(f'Espacio insuficiente al validar el PHAR en {temp_root}. '
                              'Libera espacio del volumen del servidor; se conserva la instalacion actual.')
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
    '''], runtime, temp_root=phar.parent)
    require(json.loads(output) == {'api': rtc['api'], 'version': rtc['version']}, 'Version/API RyzeRTC incompatible.')
    archive_info = run_php(php, ['-r', '''
        try {
            $p = new Phar($argv[1]);
            if($p->count() === 0 || !str_contains($p->getStub(), "<?php") ||
               !isset($p["src/PocketMine.php"]) || !isset($p["vendor/autoload.php"])) exit(1);
            $tarBytes = 8192;
            foreach(new RecursiveIteratorIterator($p) as $file){
                if($file->isFile()) $tarBytes += (int)(ceil($file->getSize() / 512) * 512) + 2048;
            }
            echo json_encode(["tar_bytes" => $tarBytes]);
        } catch(Throwable $e) { exit(1); }
    ''', str(phar)], temp_root=phar.parent)
    # Phar conversion can hold both a temporary stream and its output archive.
    needed = 2 * json.loads(archive_info)['tar_bytes'] + phar.stat().st_size + 8 * 1024 * 1024
    require_space(phar.parent, needed, 'descomprimir y comprobar el PHAR')
    output = run_php(php, [*options, str(phar), '--version'], runtime, temp_root=phar.parent)
    require('RyzeMP ' in output, 'El PHAR no identifica RyzeMP.')
    ini = php_dir / 'bin/php.ini'
    require(ini.is_file(), 'Falta php.ini en el PHP preparado.')
    lines = [line for line in ini.read_text().splitlines()
        if not re.match(r'\s*extension_dir\s*=', line) and not re.match(r'\s*extension\s*=.*ryzertc', line)]
    extension_dir = '/home/container/bin/php7/' + str(opcache[0].parent.relative_to(php_dir))
    ini.write_text('\n'.join(lines) + f'\nextension_dir="{extension_dir}"\n'
        'extension="/home/container/bin/ryzemp/ryzertc/ryzertc.so"\n')



def validate_go_binary(path):
    """Reject wrong Go protocol/algorithm before replacing any installed software."""
    require(path.is_file() and not path.is_symlink() and os.access(path, os.X_OK),
            'vanillagen no es un ejecutable valido.')
    try:
        result = subprocess.run([str(path), '-version'], capture_output=True, text=True,
                                timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UpdateError(f'vanillagen no pudo verificarse: {error}.') from error
    require(result.returncode == 0 and
            result.stdout.strip() == f'vanillagen {GO_TAG} protocol {GO_PROTOCOL} algorithm {GO_ALGORITHM}',
            'Version del ejecutable Go incompatible; se conserva la instalacion anterior.')


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
    for relative in (*TARGETS, str(BACKUP_ROOT), str(TRANSACTION_ROOT),
                     '.ryzemp-backups/previous', '.ryzemp-update-transaction',
                     '.ryzemp-vanillagen', '.ryzertc-runtime'):
        current = root
        for part in pathlib.PurePosixPath(relative).parts:
            current /= part
            require(not current.is_symlink(), f'Ruta administrada con enlace simbolico: {current}.')


def recover(root):
    # Support interrupted installs produced by both earlier Egg layouts.
    for relative in ('.ryzemp-update-transaction', str(TRANSACTION_ROOT)):
        transaction = root / relative
        if not transaction.exists():
            continue
        journal = transaction / 'journal.json'
        if not journal.exists():
            require(all(p.name == 'journal.json.tmp' for p in transaction.iterdir()),
                    'Diario de actualizacion ausente; revisa el directorio de transaccion.')
            shutil.rmtree(transaction)
            continue
        entries = json.loads(journal.read_text())
        names = [e.get('target') for e in entries]
        if names == list(TARGETS):
            backups, previous = BACKUPS, root / BACKUP_ROOT
        elif names == list(PREVIOUS_TARGETS):
            backups, previous = PREVIOUS_BACKUPS, root / '.ryzemp-backups/previous'
        elif names == list(LEGACY_TARGETS):
            backups, previous = LEGACY_BACKUPS, root / '.ryzemp-backups/previous'
        else:
            raise UpdateError('Diario de recuperacion invalido.')
        if (transaction / 'COMMITTED').exists():
            if (transaction / 'old').exists():
                previous.parent.mkdir(parents=True, exist_ok=True)
                remove(previous)
                os.replace(transaction / 'old', previous)
        else:
            for index, entry in reversed(list(enumerate(entries))):
                destination, backup = root / entry['target'], transaction / 'old' / backups[index]
                if backup.exists():
                    remove(destination)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(backup, destination)
                elif entry['had_old'] is False:
                    remove(destination)
            print('[RyzeMP] Instalacion anterior recuperada.', flush=True)
        shutil.rmtree(transaction)


def migrate_legacy_layout(root):
    """Hide obsolete installer folders without deleting any nonempty user data."""
    legacy = root / RUNTIME_ROOT / 'legacy'
    for old, new in (('.ryzertc-runtime', 'ryzertc'),
                     ('.ryzemp-vanillagen', 'vanillagen'),
                     ('.ryzemp-backups', 'backups'),
                     ('.ryzemp-install.json', 'install.json')):
        path = root / old
        if not path.exists() or path.is_symlink():
            continue
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
            continue
        legacy.mkdir(parents=True, exist_ok=True)
        destination = legacy / new
        if not destination.exists():
            os.replace(path, destination)
        else:
            print(f'[RyzeMP] Se conservo {old}: ya hay una copia anterior.', flush=True)


def signature(path):
    if not path.exists():
        return None
    if path.is_file():
        return (sha(path), stat.S_IMODE(path.stat().st_mode))
    return [(str(p.relative_to(path)), ('link', os.readlink(p)) if p.is_symlink()
             else (sha(p), stat.S_IMODE(p.stat().st_mode)))
            for p in sorted(path.rglob('*')) if p.is_file() or p.is_symlink()]


def commit(root, prepared):
    # A release without Go has no Go directory. None removes a previous binary transactionally.
    if all(signature(root / target) == (signature(source) if source is not None else None)
           for target, source in zip(TARGETS, prepared)):
        print('[RyzeMP] La ultima release ya esta instalada y verificada.', flush=True)
        return False
    transaction = root / TRANSACTION_ROOT
    transaction.mkdir(parents=True, mode=0o700)
    entries = [{'target': target, 'had_old': (root / target).exists()} for target in TARGETS]
    write_json(transaction / 'journal.json', entries)
    (transaction / 'old').mkdir()
    try:
        for index, (target, source) in enumerate(zip(TARGETS, prepared)):
            destination = root / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            if entries[index]['had_old']:
                os.replace(destination, transaction / 'old' / BACKUPS[index])
            if source is not None:
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
    (root / RUNTIME_ROOT).mkdir(parents=True, exist_ok=True)
    descriptor = os.open(root / RUNTIME_ROOT / 'update.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recover(root)
        with tempfile.TemporaryDirectory(prefix='.ryzemp-stage.', dir=root) as temp:
            stage = pathlib.Path(temp)
            manifest, state = select_release(channel, stage)
            old = root / STATE_FILE
            if not old.exists():
                old = root / '.ryzemp-install.json'
            if old.exists():
                installed = json.loads(old.read_text())
                if installed.get('channel') == channel:
                    require((state['published_at'], state['release_id']) >=
                        (installed['published_at'], installed['release_id']), 'Se rechazo una bajada automatica de version.')
                    if installed.get('release') == state['release']:
                        require(installed['manifest_sha256'] == state['manifest_sha256'],
                                'La release instalada fue modificada; publica una nueva release.')
            print(f"[RyzeMP] Canal {channel}: {state['release']} + RyzeRTC {manifest['ryzertc']['tag']}"
                  f" + RyzeVanillaGen {GO_TAG} (release independiente)", flush=True)
            phar, rtc = stage / 'RyzeMP.phar', stage / 'runtime.zip'
            download(asset_url(MP, state['release'], manifest['phar']['asset']), phar, 100 * 1024 * 1024)
            require(sha(phar) == manifest['phar']['sha256'], 'SHA-256 del PHAR incorrecto; se conserva la instalacion.')
            native = manifest['ryzertc']
            download(asset_url(RTC, native['tag'], native['asset']), rtc, 100 * 1024 * 1024)
            require(sha(rtc) == native['sha256'], 'SHA-256 de RyzeRTC incorrecto; se conserva la instalacion.')
            runtime = stage / 'runtime'
            unpack_runtime(rtc, runtime)
            php = stage / 'php7'
            php_bytes = sum(p.stat().st_size for p in php_dir.rglob('*') if p.is_file())
            require_space(stage, php_bytes + 8 * 1024 * 1024, 'preparar PHP')
            shutil.copytree(php_dir, php, symlinks=True)
            validate(php, phar, runtime, native)
            # Always provision Go independently of the PHAR release manifest.
            # Even schema-1 RyzeMP releases receive the verified native binary;
            # older PHARs can simply ignore the environment variable.
            go = {'repo': GO_REPO, 'tag': GO_TAG, 'asset': GO_FILENAME,
                  'sha256': GO_SHA256, 'protocol': GO_PROTOCOL,
                  'algorithm': GO_ALGORITHM, 'stage': 'full'}
            go_dir = stage / 'vanillagen'
            go_dir.mkdir(mode=0o700)
            binary = go_dir / GO_FILENAME
            download(asset_url(GO_REPO, GO_TAG, GO_FILENAME), binary, 64 * 1024 * 1024)
            require(sha(binary) == GO_SHA256,
                    'SHA-256 de la release oficial RyzeVanillaGen incorrecto; se conserva la instalacion.')
            binary.chmod(0o700)
            validate_go_binary(binary)
            (go_dir / 'SHA256SUMS').write_text(GO_SHA256 + '  ' + GO_FILENAME + '\n')
            (go_dir / 'SHA256SUMS').chmod(0o600)
            # Native RyzeRTC is the sole NetherNet transport. On upgrade any
            # existing Go bridge is moved into the previous-version backup.
            start = stage / 'start-ryzemp.sh'
            shutil.copyfile(startup, start)
            start.chmod(0o755)
            phar.chmod(0o644)
            state['schema'] = 1
            state['phar'] = manifest['phar']
            state['ryzertc'] = native
            state['vanillagen'] = go
            state_file = stage / 'state.json'
            write_json(state_file, state)
            changed = commit(root, (start, php, runtime, phar, go_dir, None, state_file))
            migrate_legacy_layout(root)
            if changed:
                print('[RyzeMP] Actualizacion verificada. Copia anterior: bin/ryzemp/backups/previous/', flush=True)
            print(f'[RyzeMP] RyzeVanillaGen {GO_TAG} instalado externamente y verificado; no depende de un PR.', flush=True)
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
