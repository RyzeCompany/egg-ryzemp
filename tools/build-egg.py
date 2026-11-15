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
egg['description'] = ('RyzeMP con PHP 8.4 ZTS y JIT tracing activado por defecto (opcional), RyzeRTC exclusivo para NetherNet y RyzeVanillaGen v0.1.0 externo con SHA-256 fijo. Unica carpeta bin/ryzemp, sin binarios dentro del PHAR; conserva mundos, plugins y respaldos.')
egg['scripts']['installation']['script'] = script

egg['variables'] = [{
    'name': 'Canal de actualizaciones',
    'description': 'pruebas: ultima prerelease preparada; estable: ultima release estable preparada. Se aplica al reinstalar.',
    'env_variable': 'RYZEMP_CHANNEL', 'default_value': 'pruebas',
    'user_viewable': True, 'user_editable': True,
    'rules': 'required|string|in:pruebas,estable', 'field_type': 'text',
}, {
    'name': 'Generacion Vanilla automatica (beta)',
    'description': 'true: una version compatible crea un mundo Vanilla adicional sin reemplazar el actual; el descargador integrado prepara los datos Java al cargarlo. En beta.6 no causa crash ni genera mundo extra. Requiere red, RAM y espacio.',
    'env_variable': 'RYZEMP_VANILLA_WORLDGEN', 'default_value': 'false',
    'user_viewable': True, 'user_editable': True,
    'rules': 'required|string|in:true,false', 'field_type': 'text',
}, {
    'name': 'Perfil de rendimiento de chunks (beta)',
    'description': 'true: registra resúmenes de colas, generación, validación y envío inicial de chunks. No registra nombres ni coordenadas. Desactivado por defecto.',
    'env_variable': 'RYZEMP_WORLDGEN_PROFILE', 'default_value': 'false',
    'user_viewable': True, 'user_editable': True,
    'rules': 'required|string|in:true,false', 'field_type': 'text',
}, {
    'name': 'PHP JIT (tracing, 64 MiB)',
    'description': 'true (predeterminado): activa PHP 8.4 CLI JIT tracing con buffer de 64 MiB. false: desactiva JIT sin reinstalar. Si no se puede iniciar, el lanzador continua sin JIT para evitar caidas.',
    'env_variable': 'RYZEMP_PHP_JIT', 'default_value': 'true',
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
