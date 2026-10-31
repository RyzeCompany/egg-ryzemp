#!/usr/bin/env python3
"""Run actual PHP/native/PHAR validation, including failures, without replacing a server."""
import argparse
import importlib.util
import json
import pathlib
import shutil
import tempfile

spec = importlib.util.spec_from_file_location('updater', pathlib.Path(__file__).parents[1] / 'installer/update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)
parser = argparse.ArgumentParser()
parser.add_argument('--root', type=pathlib.Path, required=True)
args = parser.parse_args()
root = args.root.resolve()
with tempfile.TemporaryDirectory() as temp:
    stage = pathlib.Path(temp)
    shutil.copytree(root / 'bin/php7', stage / 'php7', symlinks=True)
    shutil.copytree(root / '.ryzertc-runtime', stage / 'runtime', symlinks=True)
    shutil.copyfile(root / 'RyzeMP.phar', stage / 'RyzeMP.phar')
    rtc = json.loads((root / '.ryzemp-install.json').read_text())['ryzertc']
    updater.validate(stage / 'php7', stage / 'RyzeMP.phar', stage / 'runtime', rtc)
    for mode in ('api', 'phar'):
        if mode == 'phar':
            (stage / 'RyzeMP.phar').write_bytes(b'corrupt PHAR')
        try:
            updater.validate(stage / 'php7', stage / 'RyzeMP.phar', stage / 'runtime',
                             {**rtc, 'api': 999} if mode == 'api' else rtc)
        except updater.UpdateError:
            print(f'PASS: actual PHP rejected invalid {mode} before replacement')
        else:
            raise RuntimeError(f'Invalid {mode} was accepted')
print('PASS: real PHP 8.4 ZTS, OPCache, RyzeRTC API/version and PHAR preflight')
