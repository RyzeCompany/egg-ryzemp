#!/usr/bin/env python3
"""Updater contract tests: selection, integrity, preservation and interrupted commits."""
import hashlib
import importlib.util
import io
import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

spec = importlib.util.spec_from_file_location('updater', pathlib.Path(__file__).parents[1] / 'installer/update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def checksum(value):
    return hashlib.sha256(value).hexdigest()


def native_zip(extra=None):
    files = {'ryzertc.so': b'native-v2', 'lib/libdatachannel.so.0.24.6': b'sctp-library',
        'php-abi.json': json.dumps({'php': '8.4', 'php_api': 20240924, 'zts': True, 'architecture': 'x86_64'}).encode()}
    files.update(extra or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr('SHA256SUMS.txt', ''.join(f'{checksum(value)}  {name}\n' for name, value in files.items()))
    return output.getvalue()


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.root = self.base / 'server'
        self.root.mkdir()
        self.php = self.base / 'php7'
        (self.php / 'bin').mkdir(parents=True)
        (self.php / 'bin/php').write_text('new-php')
        self.start = self.base / 'start.sh'
        self.start.write_text('#!/bin/bash\nnew-start\n')
        self.downloads = {}
        self.releases = []
        self.release('old', 10)
        self.release('new', 20)
        self.calls = []
        self.transport = mock.patch.object(updater, 'download', side_effect=self.download)
        self.transport.start()
        self.addCleanup(self.transport.stop)
        self.preflight = mock.patch.object(updater, 'validate')
        self.validate = self.preflight.start()
        self.addCleanup(self.preflight.stop)
        self.go_preflight = mock.patch.object(updater, 'validate_go_binary')
        self.validate_go = self.go_preflight.start()
        self.addCleanup(self.go_preflight.stop)
        self.seed()

    def seed(self):
        for target, value in [('bin/php7/bin/php', b'original-php'), ('.ryzertc-runtime/ryzertc.so', b'original-native'),
                ('RyzeMP.phar', b'original-phar'), ('start-ryzemp.sh', b'original-start'),
                ('worlds/world/level.dat', b'world'), ('plugins/test/config.yml', b'plugin'),
                ('server.properties', b'server-ip=127.0.0.1\nserver-port=19132\n'),
                ('nethernet/operator-key.pem', b'private-key')]:
            path = self.root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        (self.root / 'nethernet/operator-key.pem').chmod(0o600)

    def release(self, tag, identifier, channel='pruebas', **changes):
        phar, native = b'PHAR-' + tag.encode(), native_zip()
        go_bytes = b'synthetic-vanillagen-' + tag.encode()
        if changes.get('schema') == 2 and 'vanillagen' not in changes:
            changes['vanillagen'] = {'asset': updater.GO_FILENAME,
                'sha256': checksum(go_bytes), 'protocol': 7, 'algorithm': 4, 'stage': 'full'}
        manifest = {'schema': 1, 'channel': channel, 'release': tag, 'platform': updater.PLATFORM,
            'phar': {'asset': 'RyzeMP.phar', 'sha256': checksum(phar)},
            'ryzertc': {'tag': 'v0.1.0-dev.3', 'asset': 'runtime.zip', 'sha256': checksum(native), 'api': 2, 'version': '0.1.0-dev.3'}}
        manifest.update(changes)
        body = json.dumps(manifest).encode()
        release = {'id': identifier, 'tag_name': tag, 'draft': False, 'prerelease': channel == 'pruebas',
            'published_at': f'2026-10-{identifier:02d}T00:00:00Z', 'assets': [
                {'name': updater.MANIFEST, 'state': 'uploaded', 'digest': 'sha256:' + checksum(body),
                 'browser_download_url': updater.asset_url(updater.MP, tag, updater.MANIFEST)},
                {'name': 'RyzeMP.phar', 'state': 'uploaded', 'digest': 'sha256:' + checksum(phar)}]}
        if manifest['schema'] == 2 and isinstance(manifest.get('vanillagen'), dict):
            release['assets'].append({'name': updater.GO_FILENAME, 'state': 'uploaded',
                                      'digest': 'sha256:' + checksum(go_bytes)})
            self.downloads[updater.asset_url(updater.MP, tag, updater.GO_FILENAME)] = go_bytes
        self.releases.append(release)
        self.downloads[updater.asset_url(updater.MP, tag, updater.MANIFEST)] = body
        self.downloads[updater.asset_url(updater.MP, tag, 'RyzeMP.phar')] = phar
        self.downloads[updater.asset_url(updater.RTC, 'v0.1.0-dev.3', 'runtime.zip')] = native
        return release

    def download(self, url, destination, limit):
        self.calls.append(url)
        if url == f'https://api.github.com/repos/{updater.MP}/releases?per_page=100&page=1':
            value = json.dumps(self.releases).encode()
        else:
            value = self.downloads[url]
        if isinstance(value, Exception):
            raise value
        self.assertLessEqual(len(value), limit)
        destination.write_bytes(value)

    def install(self, channel='pruebas'):
        return updater.update(self.root, self.php, self.start, channel)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*')
            if p.is_file() and p.name != '.ryzemp-update.lock'}

    def test_upgrade_preserves_data_and_full_previous_installation(self):
        before = self.snapshot()
        state = self.install()
        self.assertEqual(state['release'], 'new')
        self.assertEqual((self.root / 'RyzeMP.phar').read_bytes(), b'PHAR-new')
        self.assertEqual((self.root / 'bin/php7/bin/php').read_text(), 'new-php')
        self.assertEqual((self.root / '.ryzemp-backups/previous/RyzeMP.phar').read_bytes(), b'original-phar')
        self.assertEqual((self.root / '.ryzemp-backups/previous/php7/bin/php').read_bytes(), b'original-php')
        for name in ('worlds/world/level.dat', 'plugins/test/config.yml', 'server.properties', 'nethernet/operator-key.pem'):
            self.assertEqual((self.root / name).read_bytes(), before[name])
        self.assertEqual((self.root / 'nethernet/operator-key.pem').stat().st_mode & 0o777, 0o600)
        self.validate.assert_called_once()

    def test_schema2_installs_verified_go_outside_phar_preserving_player_data(self):
        self.release('go', 29, schema=2)
        before = self.snapshot()
        state = self.install()
        self.assertEqual(state['release'], 'go')
        binary = self.root / '.ryzemp-vanillagen' / updater.GO_FILENAME
        self.assertEqual(binary.read_bytes(), b'synthetic-vanillagen-go')
        self.assertEqual(binary.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / '.ryzemp-vanillagen/SHA256SUMS').read_text(),
                         checksum(binary.read_bytes()) + '  ' + updater.GO_FILENAME + '\n')
        self.assertEqual(state['vanillagen']['protocol'], 7)
        self.validate_go.assert_called_once()
        for name in ('worlds/world/level.dat', 'plugins/test/config.yml',
                     'server.properties', 'nethernet/operator-key.pem'):
            self.assertEqual((self.root / name).read_bytes(), before[name])

    def test_schema1_update_disables_go_but_preserves_previous_binary(self):
        self.release('go', 29, schema=2)
        self.install()
        self.release('later', 30, schema=1)
        state = self.install()
        self.assertIsNone(state['vanillagen'])
        self.assertFalse((self.root / '.ryzemp-vanillagen' / updater.GO_FILENAME).exists())
        self.assertEqual((self.root / '.ryzemp-backups/previous/vanillagen' /
                          updater.GO_FILENAME).read_bytes(), b'synthetic-vanillagen-go')

    def test_schema2_bad_go_checksum_keeps_all_old_files(self):
        self.release('go', 29, schema=2)
        self.downloads[updater.asset_url(updater.MP, 'go', updater.GO_FILENAME)] = b'altered'
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, 'SHA-256 del ejecutable Go'):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_schema2_rejects_bad_go_protocol_or_stage(self):
        for bad in ({'protocol': 8}, {'algorithm': 5}, {'stage': 'terrain'}):
            with self.subTest(bad=bad):
                self.releases = [r for r in self.releases if r['tag_name'] != 'bad']
                self.release('bad', 29, schema=2)
                url = updater.asset_url(updater.MP, 'bad', updater.MANIFEST)
                manifest = json.loads(self.downloads[url])
                manifest['vanillagen'].update(bad)
                body = json.dumps(manifest).encode()
                self.downloads[url] = body
                self.releases[-1]['assets'][0]['digest'] = 'sha256:' + checksum(body)
                before = self.snapshot()
                with self.assertRaisesRegex(updater.UpdateError, 'protocolo/algoritmo'):
                    self.install()
                self.assertEqual(self.snapshot(), before)

    def test_schema2_version_preflight_failure_keeps_original_files(self):
        self.release('go', 29, schema=2)
        self.validate_go.side_effect = updater.UpdateError('incompatible Go version')
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, 'incompatible Go'):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_failed_commit_after_replacing_go_rolls_back_everything(self):
        self.release('go', 29, schema=2)
        self.install()
        self.release('go2', 30, schema=2)
        before = self.snapshot()
        original = updater.os.replace
        def replace(source, destination):
            if pathlib.Path(destination) == self.root / '.ryzemp-install.json' and '.ryzemp-stage.' in str(source):
                raise OSError('Go transaction failure')
            return original(source, destination)
        with mock.patch.object(updater.os, 'replace', side_effect=replace):
            with self.assertRaisesRegex(OSError, 'Go transaction failure'):
                self.install()
        self.assertEqual(self.snapshot(), before)

    def test_legacy_journal_recovers_when_upgrading_egg(self):
        before = self.snapshot()
        transaction = self.root / '.ryzemp-update-transaction'
        (transaction / 'old').mkdir(parents=True)
        entries = [{'target': target, 'had_old': (self.root / target).exists()}
                   for target in updater.LEGACY_TARGETS]
        updater.write_json(transaction / 'journal.json', entries)
        for i in (0, 1, 2):
            destination = self.root / updater.LEGACY_TARGETS[i]
            destination.rename(transaction / 'old' / updater.LEGACY_BACKUPS[i])
        updater.recover(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_identical_reinstall_keeps_last_useful_backup(self):
        self.install()
        before = self.snapshot()
        self.install()
        self.assertEqual(self.snapshot(), before)

    def test_default_channel_never_selects_stable_drafts_or_incomplete_releases(self):
        self.release('stable', 29, 'estable')
        self.release('draft', 30)['draft'] = True
        self.release('incomplete', 31)['assets'] = []
        self.assertEqual(self.install()['release'], 'new')

    def test_explicit_stable_channel(self):
        self.release('stable', 29, 'estable')
        self.assertEqual(self.install('estable')['release'], 'stable')

    def test_no_stable_release_keeps_installed_files(self):
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, 'No hay una release'):
            self.install('estable')
        self.assertEqual(self.snapshot(), before)

    def test_newest_invalid_manifest_never_falls_back_to_older_release(self):
        self.release('broken', 29, schema=3)
        with self.assertRaisesRegex(updater.UpdateError, 'actualiza el egg'):
            self.install()
        self.assertFalse(any('/old/RyzeMP.phar' in url for url in self.calls))

    def test_wrong_platform_keeps_installation(self):
        self.release('wrong', 29, platform={**updater.PLATFORM, 'php': '8.5'})
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, 'otro PHP'):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_bad_phar_checksum_keeps_every_original_file(self):
        self.downloads[updater.asset_url(updater.MP, 'new', 'RyzeMP.phar')] = b'corrupt'
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, 'SHA-256 del PHAR'):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_bad_native_checksum_keeps_every_original_file(self):
        self.downloads[updater.asset_url(updater.RTC, 'v0.1.0-dev.3', 'runtime.zip')] = b'corrupt'
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, 'SHA-256 de RyzeRTC'):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_download_error_keeps_every_original_file(self):
        self.downloads[updater.asset_url(updater.MP, 'new', 'RyzeMP.phar')] = updater.UpdateError('HTTP 503')
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, '503'):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_native_loading_failure_keeps_every_original_file(self):
        self.validate.side_effect = updater.UpdateError('ABI native mismatch')
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, 'ABI'):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_failed_file_replacement_rolls_back_all_components_and_keeps_prior_backup(self):
        self.install()
        self.release('newer', 29)
        before = self.snapshot()
        original = updater.os.replace
        def replace(source, destination):
            if pathlib.Path(destination) == self.root / 'RyzeMP.phar' and '.ryzemp-stage.' in str(source):
                raise OSError('injected disk failure')
            return original(source, destination)
        with mock.patch.object(updater.os, 'replace', side_effect=replace):
            with self.assertRaisesRegex(OSError, 'disk failure'):
                self.install()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / '.ryzemp-update-transaction').exists())

    def test_recovery_after_process_interruption_between_rename_operations(self):
        before = self.snapshot()
        transaction = self.root / '.ryzemp-update-transaction'
        (transaction / 'old').mkdir(parents=True)
        entries = [{'target': target, 'had_old': (self.root / target).exists()} for target in updater.TARGETS]
        updater.write_json(transaction / 'journal.json', entries)
        for index in range(3):
            destination = self.root / updater.TARGETS[index]
            destination.rename(transaction / 'old' / updater.BACKUPS[index])
            if index < 2:
                destination.mkdir()
                (destination / 'partially-installed').write_text('new')
        updater.recover(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_automatic_downgrade_is_rejected(self):
        self.install()
        self.releases = [r for r in self.releases if r['tag_name'] != 'new']
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, 'bajada automatica'):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_mutated_release_is_rejected(self):
        self.install()
        self.release('new', 21)
        # Alter a non-hash-bearing field of the new manifest.
        url = updater.asset_url(updater.MP, 'new', updater.MANIFEST)
        value = json.loads(self.downloads[url])
        value['note'] = 'edited'
        self.downloads[url] = json.dumps(value).encode()
        self.releases[-1]['assets'][0]['digest'] = 'sha256:' + checksum(self.downloads[url])
        with self.assertRaisesRegex(updater.UpdateError, 'fue modificada'):
            self.install()

    def test_managed_symlink_is_rejected_before_download(self):
        shutil.rmtree(self.root / 'bin')
        (self.root / 'bin').symlink_to(self.php)
        with self.assertRaisesRegex(updater.UpdateError, 'enlace simbolico'):
            self.install()
        self.assertEqual(self.calls, [])

    def test_zip_path_traversal_is_rejected(self):
        path = self.base / 'bad.zip'
        path.write_bytes(native_zip({'../escape': b'bad'}))
        with self.assertRaisesRegex(updater.UpdateError, 'Ruta insegura'):
            updater.unpack_runtime(path, self.base / 'extracted')
        self.assertFalse((self.base / 'escape').exists())

    def test_manifest_digest_mismatch_preserves_installation(self):
        self.downloads[updater.asset_url(updater.MP, 'new', updater.MANIFEST)] += b'\n'
        before = self.snapshot()
        with self.assertRaisesRegex(updater.UpdateError, 'SHA-256 del manifiesto'):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_recovery_finishes_backup_after_committed_update(self):
        transaction = self.root / '.ryzemp-update-transaction'
        (transaction / 'old').mkdir(parents=True)
        entries = [{'target': target, 'had_old': (self.root / target).exists()} for target in updater.TARGETS]
        updater.write_json(transaction / 'journal.json', entries)
        (transaction / 'old/RyzeMP.phar').write_bytes(b'previous-version')
        (self.root / 'RyzeMP.phar').write_bytes(b'committed-new-version')
        updater.write_json(transaction / 'COMMITTED', True)
        updater.recover(self.root)
        self.assertEqual((self.root / 'RyzeMP.phar').read_bytes(), b'committed-new-version')
        self.assertEqual((self.root / '.ryzemp-backups/previous/RyzeMP.phar').read_bytes(), b'previous-version')
        self.assertFalse(transaction.exists())

    def test_recovery_discards_uncommitted_journal_temporary_file(self):
        before = self.snapshot()
        transaction = self.root / '.ryzemp-update-transaction'
        transaction.mkdir()
        (transaction / 'journal.json.tmp').write_bytes(b'[{"partial')
        updater.recover(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_old_launcher_is_guarded_before_replacing_any_binary(self):
        self.start.write_text((pathlib.Path(__file__).parents[1] / 'installer/start.sh').read_text())
        original = updater.os.replace
        inspected = []
        def replace(source, destination):
            if pathlib.Path(destination) == self.root / 'bin/php7' and '.ryzemp-stage.' in str(source):
                self.assertIn('.ryzemp-update-transaction', (self.root / 'start-ryzemp.sh').read_text())
                self.assertTrue((self.root / '.ryzemp-update-transaction').is_dir())
                inspected.append(True)
                raise OSError('interrupted before PHP activation')
            return original(source, destination)
        before = self.snapshot()
        with mock.patch.object(updater.os, 'replace', side_effect=replace):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                self.install()
        self.assertEqual(inspected, [True])
        self.assertEqual(self.snapshot(), before)

    def test_insufficient_server_disk_preserves_active_files_and_previous_backup(self):
        self.install()
        self.release('newer', 29)
        before = self.snapshot()
        with mock.patch.object(updater.shutil, 'disk_usage', return_value=mock.Mock(free=0)):
            with self.assertRaisesRegex(updater.UpdateError, 'Espacio insuficiente para preparar PHP'):
                self.install()
        self.assertEqual(self.snapshot(), before)


class GoPreflightTests(unittest.TestCase):
    def test_go_version_is_checked_before_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / updater.GO_FILENAME
            path.write_bytes(b'elf-placeholder')
            path.chmod(0o700)
            for stdout, valid in [('vanillagen dev protocol 7 algorithm 4\n', True),
                                  ('vanillagen dev protocol 7 algorithm 5\n', False),
                                  ('invalid', False)]:
                with self.subTest(stdout=stdout), mock.patch.object(
                        updater.subprocess, 'run',
                        return_value=mock.Mock(returncode=0, stdout=stdout, stderr='')):
                    if valid:
                        updater.validate_go_binary(path)
                    else:
                        with self.assertRaisesRegex(updater.UpdateError, 'Version'):
                            updater.validate_go_binary(path)


class PHPTempTests(unittest.TestCase):
    def check(self, effect=None):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            observed = []
            def execute(command, **kwargs):
                cache = pathlib.Path(kwargs['env']['TMPDIR'])
                self.assertEqual(cache.parent, root)
                self.assertTrue(cache.is_dir())
                self.assertIn(f'sys_temp_dir={cache}', command)
                observed.append(cache)
                (cache / 'partial-cache.tar').write_bytes(b'partial')
                if isinstance(effect, Exception):
                    raise effect
                return effect or mock.Mock(returncode=0, stdout='OK', stderr='')
            with mock.patch.object(updater.subprocess, 'run', side_effect=execute):
                try:
                    return updater.run_php(pathlib.Path('/fake/php'), ['--version'], temp_root=root)
                finally:
                    self.assertEqual(len(observed), 1)
                    self.assertFalse(observed[0].exists())
                    self.assertEqual(list(root.iterdir()), [])

    def test_private_server_volume_cache_is_removed_after_success(self):
        self.assertEqual(self.check(), 'OK')

    def test_partial_cache_is_removed_after_php_disk_failure(self):
        with self.assertRaisesRegex(updater.UpdateError, 'Espacio insuficiente al validar el PHAR'):
            self.check(mock.Mock(returncode=255, stdout='', stderr='errno=28 No space left on device'))

    def test_partial_cache_is_removed_after_timeout(self):
        with self.assertRaisesRegex(updater.UpdateError, 'No se pudo ejecutar'):
            self.check(updater.subprocess.TimeoutExpired('php', 30))


class DownloadAuthTests(unittest.TestCase):
    def download_request(self, url):
        class Response(io.BytesIO):
            def geturl(self):
                return url
        opener = mock.Mock()
        opener.open.return_value = Response(b'{}')
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.dict(updater.os.environ, {'RYZEMP_GITHUB_TOKEN': 'synthetic-ci-test'}), \
                mock.patch.object(updater.urllib.request, 'build_opener', return_value=opener):
            updater.download(url, pathlib.Path(directory) / 'response', 100)
        return opener.open.call_args.args[0]

    def test_optional_ci_token_is_only_sent_to_api_and_never_redirected(self):
        request = self.download_request(f'https://api.github.com/repos/{updater.MP}/releases')
        self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-ci-test')
        redirect = updater.HTTPSRedirects().redirect_request(request, None, 302, 'Found', {},
                                                           'https://downloads.example.test/file')
        self.assertFalse(redirect.has_header('Authorization'))

    def test_release_download_never_receives_ci_token(self):
        request = self.download_request(updater.asset_url(updater.MP, 'test', 'RyzeMP.phar'))
        self.assertFalse(request.has_header('Authorization'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
