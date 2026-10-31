# RyzeMP · Egg de Pterodactyl con RyzeRTC

**Reinstalar actualiza RyzeMP desde las releases oficiales**, verifica los archivos y conserva mundos, plugins, configuración y la identidad NetherNet. PHP y RyzeRTC se preparan antes de sustituir la instalación. El módulo nativo y sus bibliotecas permanecen fuera de `RyzeMP.phar`.

## Actualizar el egg del panel una vez

1. Descarga [egg-ryze-m-p.json](https://raw.githubusercontent.com/RyzeCompany/egg-ryzemp/main/egg-ryze-m-p.json).
2. En el panel de administración, abre **Nests → tu Nest → RyzeMP**. En **Egg File**, selecciona el JSON y pulsa **Update Egg**. No necesitas crear otro servidor.
3. Conserva la imagen `ghcr.io/ptero-eggs/yolks:debian`, la asignación habitual y los valores de `server-ip` y `server-port`.
4. Deja **Canal de actualizaciones** (`RYZEMP_CHANNEL`) en `pruebas`.
5. Pulsa **Reinstalar** en el servidor. Esta vez reemplazará el PHAR anterior por la última prerelease preparada y cargará el RyzeRTC que esa versión necesita.
6. Inicia el servidor y comprueba la versión instalada y `NetherNet READY`.

La release normal actual es [RyzeMP v1.0.0-beta.4](https://github.com/RyzeCompany/RyzeMP/releases/tag/v1.0.0-beta.4), con dependencias públicas beta.2 y RyzeRTC API 2. SHA-256 del PHAR: `b62e43fcbb3cfa25b82d74dd761283c06235ab04ef756666cde6641c957f0d89`. El canal selecciona su manifiesto automáticamente.

Las siguientes actualizaciones solo requieren publicar una release preparada y pulsar **Reinstalar**. Un reinicio normal conserva la versión instalada. Composer no interviene en este proceso.

## Canales

| Valor | Selección |
|---|---|
| `pruebas` — predeterminado | Última prerelease publicada con manifiesto de actualización. Es el canal actual de Bedrock 1.26.60. |
| `estable` | Última release no marcada como prerelease con manifiesto. Todavía no hay una preparada; seleccionarlo detiene la instalación con un mensaje útil. |

No se instalan borradores ni releases sin `ryzemp-update.json`. Si la última release preparada está dañada o es incompatible, el instalador informa del fallo y conserva la instalación; no elige silenciosamente otra versión. Dentro del mismo canal se rechazan bajadas automáticas y cambios del manifiesto de una versión ya instalada. Cambiar de canal es una selección explícita del administrador.

## Integridad y versiones compatibles

El manifiesto de cada release declara el SHA-256 del PHAR y la versión, API y SHA-256 exactos de RyzeRTC. El egg usa únicamente las releases de `RyzeCompany/RyzeMP` y `RyzeCompany/RyzeRTC` por HTTPS; también verifica el digest del manifiesto publicado por GitHub. No ejecuta scripts descargados: el instalador completo está dentro del JSON importado.

El host público no necesita credenciales. Actions proporciona su token automático a los contenedores de instalación para evitar el límite de consultas anónimas de las IP compartidas. El actualizador solo lo usa para la API oficial; no lo envía a assets ni redirecciones ni lo guarda en el servidor. Si GitHub limita una consulta del host, la instalación se detiene sin sustituir los componentes actuales.

Antes de reemplazar archivos comprueba:

- SHA-256 del PHAR y del ZIP nativo, archivos internos y rutas del ZIP.
- PHP 8.4 ZTS Linux x86_64, OPCache y ABI nativa 20240924; compatible con Debian 12 / glibc 2.36.
- Carga real de la API y versión de RyzeRTC requeridas.
- PHAR válido y ejecución real de `RyzeMP.phar --version`.

La primera release preparada es [ryzemp-2225-ryzertc-integration.2](https://github.com/RyzeCompany/RyzeMP/releases/tag/ryzemp-2225-ryzertc-integration.2), con PHAR `a974c34acc36fdf2178cd09424a8c45053cd05872f4f1fac186da8efd2a07b55` y [RyzeRTC v0.1.0-dev.3 / API 2](https://github.com/RyzeCompany/RyzeRTC/releases/tag/v0.1.0-dev.3), ZIP `9ecea6cc9d239b8c583d042c91df0448432321ceaf128850fe5b27bcde234602`. Las siguientes versiones se resuelven desde su manifiesto; no hace falta volver a importar el egg para cada release compatible.

Un nuevo formato de manifiesto o cambio de ABI de PHP requiere actualizar el egg del panel. PHP se obtiene del proveedor oficial PocketMine con SHA-256 fijado; si el proveedor cambia el archivo sin conservar el hash, la instalación se detiene antes de sustituir archivos.

## Copia anterior y recuperación

La instalación guarda PHP, RyzeRTC, PHAR, lanzador y registro de versión anteriores en `.ryzemp-backups/previous/` con los nombres `php7`, `ryzertc-runtime`, `RyzeMP.phar`, `start-ryzemp.sh` e `install.json`. Una reinstalación idéntica conserva esa copia útil. Este respaldo cubre los componentes del software; los datos del servidor permanecen en su sitio.

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

El [workflow](.github/workflows/validate-ryzertc-egg.yml) comprueba selección de canales, errores, corrupción, conservación de datos, recuperación y reinstalación sin cambios. Además instala las releases en imágenes reales de Pterodactyl, prueba el PHAR y módulo nativo reales, rechaza una API/PHAR inválidos, actualiza un PHAR oficial anterior, conserva datos y copia anterior, rechaza un paquete PHP corrupto y vuelve a comprobar HTTP/RakNet sobre la misma asignación TCP/UDP.

[Publicación de releases preparadas](https://github.com/RyzeCompany/RyzeMP/blob/main/docs/EGG_UPDATES.md): el workflow de RyzeMP publica PHAR y checksum primero y `ryzemp-update.json` al final. Cada nueva versión debe llevar un tag nuevo.

El operador ya confirmó entrada real al mundo con integración.2. La actualización mediante **Reinstalar** todavía debe repetirse en su panel real. Quedan las pruebas completas de movimiento, interacción, inventario, paquetes de recursos, desconexión/reconexión y coexistencia RakNet. Las PR de esta integración ya están fusionadas a main; la release sigue siendo beta. Sin Amber; HardCoreFactions no se modifica.
