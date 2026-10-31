#!/usr/bin/env python3
"""Generate the self-contained Panel import; no remote scripts run at install time."""
import argparse
import json
import pathlib

root = pathlib.Path(__file__).resolve().parents[1]
path = root / 'egg-ryze-m-p.json'
egg = json.loads(path.read_text())
script = (root / 'installer/install.sh.in').read_text()
for token, name in [('@@UPDATER@@', 'update.py'), ('@@START@@', 'start.sh')]:
    assert script.count(token) == 1
    script = script.replace(token, (root / 'installer' / name).read_text().rstrip())
egg['description'] = ('RyzeMP con PHP 8.4 ZTS y RyzeRTC nativo fuera del PHAR. '
    'Reinstalar actualiza desde el canal oficial seleccionado, verifica SHA-256 '
    'y conserva datos y una copia de la instalacion anterior.')
egg['scripts']['installation']['script'] = script
egg['variables'] = [{
    'name': 'Canal de actualizaciones',
    'description': 'pruebas: ultima prerelease preparada; estable: ultima release estable preparada. Se aplica al reinstalar.',
    'env_variable': 'RYZEMP_CHANNEL', 'default_value': 'pruebas',
    'user_viewable': True, 'user_editable': True,
    'rules': 'required|string|in:pruebas,estable', 'field_type': 'text',
}]
result = json.dumps(egg, ensure_ascii=False, indent=4) + '\n'
parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
if args.check:
    if result != path.read_text():
        raise SystemExit('Regenerate egg-ryze-m-p.json: python3 tools/build-egg.py')
else:
    path.write_text(result)
