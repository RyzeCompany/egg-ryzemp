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
egg['description'] = ('RyzeMP con PHP 8.4 ZTS, RyzeRTC y aceleracion Go nativa fuera del PHAR. '
    'Go se activa solo en releases compatibles; reinstalar verifica SHA-256 '
    'y conserva mundos, plugins, configuraciones y copia anterior.')
egg['scripts']['installation']['script'] = script
egg['variables'] = [{
    'name': 'Canal de actualizaciones',
    'description': 'pruebas: ultima prerelease preparada; estable: ultima release estable preparada. Se aplica al reinstalar.',
    'env_variable': 'RYZEMP_CHANNEL', 'default_value': 'pruebas',
    'user_viewable': True, 'user_editable': True,
    'rules': 'required|string|in:pruebas,estable', 'field_type': 'text',
}, {
    'name': 'Generacion Vanilla automatica (beta)',
    'description': 'true: al iniciar prepara datos Java 26.3, SHA y mundos NUEVOS core-v6. Conserva todos los mundos y cache; primera preparacion requiere red, RAM y espacio.',
    'env_variable': 'RYZEMP_VANILLA_WORLDGEN', 'default_value': 'false',
    'user_viewable': True, 'user_editable': True,
    'rules': 'required|string|in:true,false', 'field_type': 'text',
}, {
    'name': 'Perfil de rendimiento de chunks (beta)',
    'description': 'true: registra resúmenes de colas, generación, validación y envío inicial de chunks. No registra nombres ni coordenadas. Desactivado por defecto.',
    'env_variable': 'RYZEMP_WORLDGEN_PROFILE', 'default_value': 'false',
    'user_viewable': True, 'user_editable': True,
    'rules': 'required|string|in:true,false', 'field_type': 'text',
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
