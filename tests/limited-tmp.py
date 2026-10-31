#!/usr/bin/env python3
"""Reproduce the retail installer error on small tmpfs, then validate the real fix."""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('updater', pathlib.Path(__file__).parents[1] / 'installer/update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)
parser = argparse.ArgumentParser()
parser.add_argument('--root', type=pathlib.Path, required=True)
parser.add_argument('--system-tmp', type=pathlib.Path, default=pathlib.Path('/tmp'))
args = parser.parse_args()
root = args.root.resolve()
system_tmp = args.system_tmp.resolve()
capacity = shutil.disk_usage(system_tmp).total
assert capacity <= 100 * 1024 * 1024, 'Run inside a dedicated limited tmpfs, not the host /tmp'
phar = root / 'RyzeMP.phar'
digest_before = updater.sha(phar)
native = root / '.ryzertc-runtime'
php = root / 'bin/php7/bin/php'
environment = os.environ.copy()
environment['LD_LIBRARY_PATH'] = str(native / 'lib')
with tempfile.TemporaryDirectory(prefix='old-phar-check.', dir=system_tmp) as previous_temp:
    environment['TMPDIR'] = previous_temp
    old = subprocess.run([str(php), '-n', '-d', f'sys_temp_dir={previous_temp}',
        '-d', f'extension={native}/ryzertc.so', str(phar), '--version'],
        env=environment, capture_output=True, text=True, timeout=40)
    evidence = old.stdout + old.stderr
    assert old.returncode != 0 and 'No space left on device' in evidence, evidence
    (root / 'limited-tmp-regression.log').write_text('EXPECTED PREVIOUS FAILURE\n' + evidence)
    print(f'REPRODUCED: real released PHAR preflight fails with ENOSPC on {capacity // 1048576} MiB tmpfs')

with tempfile.TemporaryDirectory(prefix='.ci-private-cache.', dir=root) as directory:
    stage = pathlib.Path(directory)
    shutil.copytree(root / 'bin/php7', stage / 'php7', symlinks=True)
    shutil.copytree(native, stage / 'runtime', symlinks=True)
    shutil.copyfile(phar, stage / 'RyzeMP.phar')
    rtc = json.loads((root / '.ryzemp-install.json').read_text())['ryzertc']
    previous_environment = os.environ.get('TMPDIR')
    os.environ['TMPDIR'] = str(system_tmp)
    try:
        for attempt in range(2):
            updater.validate(stage / 'php7', stage / 'RyzeMP.phar', stage / 'runtime', rtc)
            assert not list(stage.glob('.ryzemp-php-check.*')), 'Validation leaked decompressed archives'
            print(f'PASS: fixed real PHP/native/PHAR validation {attempt + 1}; private volume cache removed')
    finally:
        if previous_environment is None:
            os.environ.pop('TMPDIR', None)
        else:
            os.environ['TMPDIR'] = previous_environment
assert updater.sha(phar) == digest_before
with (root / 'limited-tmp-regression.log').open('a') as log:
    log.write('\nPASS: fixed real preflight twice with small system tmpfs; no cache leak; installed PHAR unchanged\n')
print('PASS: small system /tmp no longer prevents reinstall; no change to release bytes or installed PHAR')
