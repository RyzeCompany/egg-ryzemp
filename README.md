# RyzeMP · Egg de Pterodactyl con RyzeRTC y Go nativo

**Reinstalar actualiza RyzeMP desde las releases oficiales**, verifica los archivos y conserva mundos, plugins, configuración y la identidad NetherNet. PHP y RyzeRTC se preparan antes de sustituir la instalación. El módulo nativo y sus bibliotecas permanecen fuera de `RyzeMP.phar`.

## PHP 8.4 JIT activo por defecto (reversible)

El Egg ahora inicia el **proceso PHP del servidor** con OPcache CLI y **JIT tracing (64 MiB)** activos de forma predeterminada. No cambia el PHAR, no descarga extensiones nuevas y no requiere puertos adicionales. En la pestaña **Startup** aparece la variable **PHP JIT (tracing, 64 MiB)**:

| `RYZEMP_PHP_JIT` | Comportamiento |
|---|---|
| `true` (valor predeterminado) | Se intenta activar OPcache CLI y JIT `tracing` con buffer de 64 MiB. |
| `false` | Se inicia PHP sin JIT; basta reiniciar el servidor. |

En el arranque aparece `[RyzeMP] PHP JIT activo (tracing, 64M)` cuando la comprobación del PHP real confirma su activación. Si JIT no está disponible o no se inicializa, el lanzador **avisa y continúa sin JIT**; nunca afirma que esté activo si no lo está. Utiliza `/version runtime` en un PHAR que incluya el PR #65 para consultar el estado desde dentro del proceso.

Para aplicarlo a un servidor existente, importa el nuevo `egg-ryze-m-p.json` en el Egg del panel. Como el script `start-ryzemp.sh` forma parte de la instalación, después ejecuta **Reinstalar** una sola vez; el actualizador transaccional conserva mundos, plugins, `server.properties` e identidad NetherNet. **No realiza una nueva publicación de RyzeMP** ni convierte automáticamente un PR fusionado en una release: seguirá seleccionando la release oficial preparada del canal.

JIT puede mejorar algunos bucles PHP intensivos, pero no acelera directamente RyzeVanillaGen en Go, LevelDB ni RyzeRTC nativo. Consume RAM adicional y debe medirse bajo carga real (TPS, tick p95 y memoria); si observas errores o regresiones, cambia `RYZEMP_PHP_JIT=false` en Startup y reinicia, sin reinstalar.

Referencia: https://www.php.net/manual/en/opcache.configuration.php

## Instalacion limpia: una sola carpeta de componentes

El nuevo Egg mantiene `RyzeMP.phar` y `start-ryzemp.sh` en la raiz, pero agrupa los componentes internos en `bin/ryzemp/`: `ryzertc/`, `vanillagen/` (siempre desde RyzeVanillaGen), `backups/previous/` y `install.json`. PHP sigue en `bin/php7/`; la clave de confianza `nethernet/operator-key.pem` no se mueve.

La nueva instalacion descarga exclusivamente RyzeRTC como motor NetherNet; no instala `pm-nethernet`. `vanillagen` se instala **siempre** desde [RyzeVanillaGen v0.1.0](https://github.com/RyzeCompany/RyzeVanillaGen/releases/tag/v0.1.0), con SHA-256 fijado, protocolo 7 y algoritmo 4. Ya no depende del manifiesto ni de los PR de RyzeMP. La beta.5 puede ignorar Go porque su PHAR es anterior a la integración.

Tras una instalacion correcta, el Egg traslada los antiguos directorios ocultos `.ryzertc-runtime`, `.ryzemp-vanillagen`, `.ryzemp-backups` y el viejo registro hacia `bin/ryzemp/legacy/` para conservar su contenido sin saturar la raiz. Las carpetas antiguas vacias se eliminan; si hubiera una copia anterior con el mismo nombre, se conserva sin sobrescribir. **No elimina mundos, plugins, archivos de usuario ni las claves de identidad.** No borres manualmente `bin/ryzemp/legacy/` sin revisar sus respaldos.

La compilacion del PR #63 de RyzeMP elimina el puente pm-nethernet y mantiene RyzeRTC y Go fuera del PHAR. Instalar esa nueva version mediante el Egg necesita una **release oficial con manifiesto y assets SHA-256**, no un ZIP temporal de GitHub Actions.

## Actualizar el egg del panel una vez

1. Descarga [egg-ryze-m-p.json](https://raw.githubusercontent.com/RyzeCompany/egg-ryzemp/main/egg-ryze-m-p.json).
2. En el panel de administración, abre **Nests → tu Nest → RyzeMP**. En **Egg File**, selecciona el JSON y pulsa **Update Egg**. No necesitas crear otro servidor.
3. Conserva la imagen `ghcr.io/ptero-eggs/yolks:debian`, la asignación habitual y los valores de `server-ip` y `server-port`.
4. Deja **Canal de actualizaciones** (`RYZEMP_CHANNEL`) en `pruebas`.
5. Pulsa **Reinstalar** en el servidor. Esta vez reemplazará el PHAR anterior por la última prerelease preparada y cargará el RyzeRTC que esa versión necesita.
6. Inicia el servidor y comprueba la versión instalada y `NetherNet READY`.

La ultima prerelease preparada al incorporar Go al Egg es [RyzeMP v1.0.0-beta.5](https://github.com/RyzeCompany/RyzeMP/releases/tag/v1.0.0-beta.5), con RyzeRTC API 2 y generacion PHP. SHA-256 del PHAR: `c67173111ab59e3b6baf8c1ed51a89d7eabe9c6b3a1578104670f4a8b5938c44`. El Egg obtiene Go de RyzeVanillaGen independientemente de la release de RyzeMP; el canal solo selecciona el PHAR oficial.

Las siguientes actualizaciones solo requieren publicar una release preparada y pulsar **Reinstalar**. Un reinicio normal conserva la versión instalada. Composer no interviene en este proceso.

## Generacion Vanilla automatica (beta)

En **Startup → Generacion Vanilla automatica (beta)** cambia `RYZEMP_VANILLA_WORLDGEN` a `true` para solicitar la creacion de un **mundo nuevo, separado**, con el generador `vanilla`. En las versiones de RyzeMP compatibles con esta funcionalidad, si el servidor ya tiene un mundo principal existente, se crea `world_vanilla_auto` en `worlds/`: **no se reemplaza ni se cambia el mundo principal**, ni se modifica `server.properties` o `pocketmine.yml`. En un servidor nuevo cuyo generador predeterminado ya es `vanilla`, no se crea un mundo duplicado.

Los datos de worldgen Java se preparan automaticamente por el propio RyzeMP al cargar o crear el mundo Vanilla, mediante `VanillaDataManager`; si faltan los datos, se descargan desde las fuentes oficiales verificadas. Los chunks se generan conforme se necesitan, no se precalcula todo el mapa. El ejecutable Go de RyzeVanillaGen se instala por separado y se usa como acelerador cuando corresponde.

**Compatibilidad con beta.6:** la beta.6 ya incluye el generador Vanilla y el descargador de datos, pero **no implementa la creacion automatica del mundo adicional por variable de entorno**. El Egg ya no exige la clase inexistente `VanillaWorldgenSetup.php` ni ejecuta el comando antiguo de preparacion. Con el Egg corregido, activar `RYZEMP_VANILLA_WORLDGEN=true` en beta.6 muestra una advertencia y permite arrancar el servidor; para la creacion automatica adicional, sera necesaria una version de RyzeMP posterior a beta.6 que incorpore el cambio.

Si una descarga falla, se informa del error y el mundo nuevo no se sustituye silenciosamente por terreno PocketMine. Los mundos existentes no se alteran; en el siguiente arranque se reintenta la preparacion. Para servidores en produccion, haz respaldo antes de activar funciones beta.

## Perfilador opcional de chunks y generación (beta)

En **Startup → Perfil de rendimiento de chunks (beta)** cambia \`RYZEMP_WORLDGEN_PROFILE\` de \`false\` a \`true\` y reinicia con un PHAR actualizado del [PR #60](https://github.com/RyzeCompany/RyzeMP/pull/60). No requiere ejecutar comandos Linux ni cambiar puertos.

El perfilador agrupa 16 tareas de población y muestra una línea \`[Worldgen perf]\` con tiempos medios y p95 de **espera en cola**, **ejecución del worker**, **validación SHA-256**, **terreno Go/PHP**, **escritura bloques/biomas** y **decoración**. En la entrada inicial muestra los tiempos de solicitud/población y preparación de paquetes antes de avisar al cliente. Son medidas desde el servidor: no confundir la puesta en cola del paquete con la recepción final por el móvil. No se registran nombres, coordenadas ni semillas. El modo se desactiva por defecto para evitar coste de perfilado y más mensajes en consola.

No cambies los mundos ni borres \`vanillamine-cache/\` para activar el perfil. El perfilador ayuda a detectar cuellos de botella antes de ajustar el número de async-workers.

## Aceleracion nativa Go (worldgen core-v6)

El Egg descarga `vanillagen-linux-amd64` desde **RyzeCompany/RyzeVanillaGen v0.1.0**, nunca desde RyzeMP. Fija el SHA-256 `3cddcb4be9bd17eaa3225be5d167fb63328566c252a8c4fe7b1e3b9e7d716dc7`, ejecuta `-version` y verifica exactamente `vanillagen v0.1.0 protocol 7 algorithm 4` antes de sustituir el servidor. Los manifiestos schema 1 y 2 siguen siendo compatibles; el binario Go se instala aunque RyzeMP aún use generación PHP.

En el arranque, el Egg vuelve a verificar el hash y configura `RYZEMP_VANILLAGEN_BINARY`, `RYZEMP_VANILLAGEN_SHA256` y `RYZEMP_VANILLAGEN_STAGE=full` automaticamente. Usa un puerto local efimero en 127.0.0.1 y **ninguna asignacion TCP/UDP publica adicional**. El nuevo directorio `bin/ryzemp/vanillagen/` se actualiza junto con los otros binarios, admite copia anterior en `bin/ryzemp/backups/previous/` y recupera transacciones interrumpidas. Tambien se pueden recuperar los diarios antiguos.

**El Egg no descarga datos propietarios ni cambia mundos existentes**. Para generar mundos nuevos en `core-v6`, primero prepara un caché Java 26.3 externo e inmutable segun la [guia de RyzeMP](https://github.com/RyzeCompany/RyzeMP/blob/integration/vanillamine-worldgen/docs/WORLDGEN_GO_VPS.md).

La integración PHP del generador se desarrolla en [RyzeMP PR #63](https://github.com/RyzeCompany/RyzeMP/pull/63). La instalación del **ejecutable** ya es independiente del PR; para que el PHAR oficial lo aproveche en mundos nuevos, RyzeMP aún necesita publicar una versión compatible tras las pruebas. La beta.5 puede seguir usando el fallback PHP.

## NetherNet solo con RyzeRTC

El Egg instala `ryzertc.so` desde la release oficial independiente de RyzeRTC. Ya no descarga ni ejecuta el puente `pm-nethernet`. Al reinstalar, un ejecutable antiguo que estuviera en `bin/ryzemp/nethernet/` se retira transaccionalmente y se conserva en `bin/ryzemp/backups/previous/nethernet/`; nunca se elimina la identidad `nethernet/operator-key.pem`.

El PR #63 de RyzeMP habilita HTTP y HTTPS en el mismo puerto TCP `server-port`, y comparte UDP con RakLib sin puertos adicionales. Si quieres HTTPS, proporciona certificados PEM válidos en `network.nethernet.https.certificate` y `private-key`. Para emitir/renovar certificados públicos se necesita un servicio externo de hosting o ACME: RyzeRTC todavía no administra las validaciones ACME. Sin certificados, Windows/Android pueden recurrir a HTTP; iOS requiere HTTPS válido.

**Importante:** la última prerelease de RyzeMP sigue siendo beta.5. Importar este Egg no instala automáticamente el código sin puente del PR #63: hace falta una nueva release oficial verificada de RyzeMP para desplegarlo. El Egg no usa artefactos temporales de PR.

## Canales

| Valor | Selección |
|---|---|
| `pruebas` — predeterminado | Última prerelease publicada con manifiesto de actualización. Es el canal actual de Bedrock 1.26.60. |
| `estable` | Última release no marcada como prerelease con manifiesto. Todavía no hay una preparada; seleccionarlo detiene la instalación con un mensaje útil. |

No se instalan borradores ni releases sin `ryzemp-update.json`. Si la última release preparada está dañada o es incompatible, el instalador informa del fallo y conserva la instalación; no elige silenciosamente otra versión. Dentro del mismo canal se rechazan bajadas automáticas y cambios del manifiesto de una versión ya instalada. Cambiar de canal es una selección explícita del administrador.

## Integridad y versiones compatibles

El manifiesto de cada release declara el SHA-256 del PHAR y la versión, API y SHA-256 exactos de RyzeRTC. El Egg utiliza únicamente releases de `RyzeCompany/RyzeMP`, `RyzeCompany/RyzeRTC` y `RyzeCompany/RyzeVanillaGen` por HTTPS; también verifica el digest del manifiesto publicado por GitHub. No ejecuta scripts descargados: el instalador completo está dentro del JSON importado.

El host público no necesita credenciales. Actions proporciona su token automático a los contenedores de instalación para evitar el límite de consultas anónimas de las IP compartidas. El actualizador solo lo usa para la API oficial; no lo envía a assets ni redirecciones ni lo guarda en el servidor. Si GitHub limita una consulta del host, la instalación se detiene sin sustituir los componentes actuales.

Antes de reemplazar archivos comprueba:

- SHA-256 del PHAR y del ZIP nativo, archivos internos y rutas del ZIP.
- PHP 8.4 ZTS Linux x86_64, OPCache y ABI nativa 20240924; compatible con Debian 12 / glibc 2.36.
- Carga real de la API y versión de RyzeRTC requeridas.
- PHAR válido y ejecución real de `RyzeMP.phar --version`.

La primera release preparada es [ryzemp-2225-ryzertc-integration.2](https://github.com/RyzeCompany/RyzeMP/releases/tag/ryzemp-2225-ryzertc-integration.2), con PHAR `a974c34acc36fdf2178cd09424a8c45053cd05872f4f1fac186da8efd2a07b55` y [RyzeRTC v0.1.0-dev.3 / API 2](https://github.com/RyzeCompany/RyzeRTC/releases/tag/v0.1.0-dev.3), ZIP `9ecea6cc9d239b8c583d042c91df0448432321ceaf128850fe5b27bcde234602`. Las siguientes versiones se resuelven desde su manifiesto; no hace falta volver a importar el egg para cada release compatible.

Un nuevo formato de manifiesto o cambio de ABI de PHP requiere actualizar el egg del panel. PHP se obtiene del proveedor oficial PocketMine con SHA-256 fijado; si el proveedor cambia el archivo sin conservar el hash, la instalación se detiene antes de sustituir archivos.

## Temporales y espacio de instalación

Wings limita `/tmp` mediante un tmpfs independiente (100 MiB por defecto). Aunque el PHAR ocupa unos 7 MiB comprimido, su caché descomprimida y los archivos temporales de conversión necesitan mucho más espacio. La validación de `--version` también ejecuta esa conversión.

El instalador ahora usa una caché privada dentro de su directorio de preparación en `/mnt/server`, fija tanto `TMPDIR` como `sys_temp_dir` y la elimina después de cada comprobación, incluso al fallar o agotar el tiempo. El lanzador fija también `sys_temp_dir` al `tmp/` del servidor. No es necesario aumentar el tmpfs de Wings para esta validación.

Antes de copiar PHP y expandir el PHAR se comprueba el espacio disponible en el volumen. Si ese volumen está lleno, se informa de los MiB necesarios y disponibles y se conserva la instalación anterior. Las cuotas del nodo todavía pueden impedir escribir aunque el sistema informe de espacio libre.

Si la reinstalación anterior terminó con `Phar::convertToData(): No space left on device`, actualiza el egg existente con el JSON nuevo y repite **Reinstalar**. Se utiliza el mismo PHAR oficial beta.4 y RyzeRTC; mundos, plugins, configuración e identidad permanecen en su sitio.

## Copia anterior y recuperación

La instalación guarda PHP, RyzeRTC, PHAR, lanzador y registro de versión anteriores en `bin/ryzemp/backups/previous/` con los nombres `php7`, `ryzertc`, `RyzeMP.phar`, `start-ryzemp.sh` e `install.json`. Una reinstalación idéntica conserva esa copia útil. Este respaldo cubre los componentes del software; los datos del servidor permanecen en su sitio.

Un error al sustituir un componente restaura el conjunto anterior. Si el proceso se interrumpe, `start-ryzemp.sh` impide arrancar una instalación incompleta y la siguiente reinstalación recupera el diario `.ryzemp-update-transaction`. No borres ese directorio mientras haya una recuperación pendiente.

El instalador conserva `server.properties`, mundos, plugins y `nethernet/operator-key.pem`. Esa clave P-384 mantiene sus permisos 0600 y la confianza del cliente. La reinstalación no la genera ni la sustituye.

## Una sola asignación pública

La señalización HTTP usa **TCP** y RakNet/WebRTC usan **UDP**, ambos en el mismo `server-port`, por ejemplo 19132. No se agrega un puerto público ni configuración adicional de NetherNet. El mux privado de ICE se administra automáticamente en loopback.

Wings publica cada asignación para [TCP y UDP](https://github.com/pterodactyl/wings/blob/747bc4393daf5d95fdf61d76382f5e23749cffe9/environment/allocations.go#L53). En el nodo, `docker inspect ID_DEL_CONTENEDOR` debe mostrar ambos mapeos con la misma asignación. El firewall del nodo debe permitir los dos protocolos.

Desde una red externa, `http://IP_O_DOMINIO:PUERTO/v1/join` debe devolver HTTP 200 y protocolo 2225. Una oferta sin identidad válida se rechaza con HTTP 401. La autenticación oficial permanece activa.

## Desarrollo y pruebas

Modifica `installer/install.sh.in`, `installer/update.py` o `installer/start.sh` y regenera el JSON con:

```sh
python3 tools/build-egg.py
python3 tools/build-egg.py --check
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

El [workflow](.github/workflows/validate-ryzertc-egg.yml) comprueba selección de canales, errores, corrupción, conservación de datos, recuperación y reinstalación sin cambios. Además limita `/tmp` a 64 MiB en las imágenes de instalación y ejecución, reproduce el fallo original con el PHAR real, verifica dos validaciones sin fugas de caché e instala las releases en imágenes reales de Pterodactyl, prueba el PHAR y módulo nativo reales, rechaza una API/PHAR inválidos, actualiza un PHAR oficial anterior, conserva datos y copia anterior, rechaza un paquete PHP corrupto y vuelve a comprobar HTTP/RakNet sobre la misma asignación TCP/UDP.

[Publicación de releases preparadas](https://github.com/RyzeCompany/RyzeMP/blob/main/docs/EGG_UPDATES.md): el workflow de RyzeMP publica PHAR y checksum primero y `ryzemp-update.json` al final. Cada nueva versión debe llevar un tag nuevo.

El operador ya confirmó entrada real al mundo con integración.2. La actualización mediante **Reinstalar** todavía debe repetirse en su panel real. Quedan las pruebas completas de movimiento, interacción, inventario, paquetes de recursos, desconexión/reconexión y coexistencia RakNet. RyzeMP PR #63 y Egg PR #3 permanecen como borradores hasta validar clientes reales. La release oficial del servidor sigue siendo beta. Sin Amber; HardCoreFactions no se modifica.
