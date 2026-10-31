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
        self.release('broken', 29, schema=2)
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
