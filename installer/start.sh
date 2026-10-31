#!/usr/bin/env bash
set -euo pipefail
cd /home/container

if [[ -d .ryzemp-update-transaction ]]; then
  echo '[RyzeMP] La actualizacion fue interrumpida. Reinstala para recuperar la instalacion anterior.' >&2
  exit 1
fi

if [[ ! -x ./bin/php7/bin/php ]]; then
  echo '[RyzeMP] Falta el PHP de PocketMine. Reinstala este Egg.' >&2
  exit 1
fi
if [[ ! -s ./RyzeMP.phar ]]; then
  echo '[RyzeMP] Falta RyzeMP.phar.' >&2
  echo '[RyzeMP] Reinstala el Egg para descargar automaticamente el PHAR oficial o sube uno existente.' >&2
  exit 1
fi

# Arreglar tambien instalaciones existentes que recibieron el php.ini con una
# extension_dir absoluta del entorno de compilacion (GitHub Actions).
php_ini='./bin/php7/bin/php.ini'
if [[ ! -f "$php_ini" ]]; then
  echo '[RyzeMP] No se encontro el php.ini de PocketMine PHP.' >&2
  exit 1
fi
opcache_file="$(find ./bin/php7 -type f -name opcache.so -print -quit)"
if [[ -z "$opcache_file" ]]; then
  echo '[RyzeMP] No existe opcache.so en la distribucion PHP. Reinstala el Egg.' >&2
  exit 1
fi
ext_dir="$(cd "$(dirname "$opcache_file")" && pwd -P)"
if ! grep -Fxq "extension_dir=\"$ext_dir\"" "$php_ini"; then
  sed -i '/^[[:space:]]*extension_dir[[:space:]]*=/d' "$php_ini"
  printf '\nextension_dir="%s"\n' "$ext_dir" >> "$php_ini"
fi

# Cargar la biblioteca nativa desde su directorio separado del PHAR.
if [[ ! -s ./.ryzertc-runtime/ryzertc.so || ! -s ./.ryzertc-runtime/lib/libdatachannel.so.0.24 ]]; then
  echo '[RyzeMP] Falta RyzeRTC. Reinstala el Egg para descargar la release oficial.' >&2
  exit 1
fi
export LD_LIBRARY_PATH="/home/container/.ryzertc-runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# El mismo php.ini sera utilizado por los procesos hijos, incluido ConsoleReader.
export PHPRC=/home/container/bin/php7/bin
mkdir -p ./tmp
export TMPDIR=/home/container/tmp

# Comprobar la carga real de OPCache en el contenedor de ejecucion.
if ! ./bin/php7/bin/php -r 'if(!extension_loaded("Zend OPcache")){fwrite(STDERR, "[RyzeMP] Zend OPcache no se cargo. Comprueba php.ini y opcache.so.\n"); exit(1);}' ; then
  echo '[RyzeMP] PHP no puede cargar OPCache. Revisa bin/php7/bin/php.ini.' >&2
  exit 1
fi

# Verificar carga real del modulo bajo el mismo php.ini y las mismas librerias.
if ! ./bin/php7/bin/php -r '
  if (!extension_loaded("ryzertc") || !class_exists("RyzeRTC\\Runtime") || RyzeRTC\Runtime::apiVersion() < 2) {
    fwrite(STDERR, "[RyzeMP] No se pudo cargar ryzertc.so. Comprueba php.ini, ABI y librerias.\n");
    exit(1);
  }
  echo "[RyzeMP] RyzeRTC ", RyzeRTC\Runtime::version(), " cargado.\n";
'; then
  echo '[RyzeMP] Arranque detenido: RyzeRTC no esta disponible.' >&2
  exit 1
fi
echo '[RyzeMP] Red: publica TCP y UDP en la misma asignacion server-port. El Egg no abre el firewall de Wings.'
exec ./bin/php7/bin/php ./RyzeMP.phar --no-wizard --enable-ansi --settings.enable-dev-builds=1
