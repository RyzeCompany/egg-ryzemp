# RyzeMP · Pterodactyl Egg

Egg oficial para **RyzeMP**, con PHP 8.4 ZTS y la extension nativa propia **RyzeRTC** en Linux x86_64 con compatibilidad base Debian 12 / glibc 2.36. El modulo se distribuye por separado y **no forma parte de `RyzeMP.phar`**.

## Descargar e importar

1. Descarga [`egg-ryze-m-p.json`](./egg-ryze-m-p.json) desde el repositorio (rama de prueba hasta aprobar el PR).
2. Importalo en la pagina **Nests → Import Egg** del panel Pterodactyl.
3. Asigna al servidor la imagen `ghcr.io/ptero-eggs/yolks:debian` y el puerto habitual de Minecraft.
4. En el servidor instala/reinstala el Egg. La instalacion descarga el PHP oficial y `RyzeRTC v0.1.0-dev.2` desde GitHub de RyzeCompany, verifica hashes y guarda el runtime en `.ryzertc-runtime/`.
5. Sube `RyzeMP.phar` a la raiz de archivos y ejecuta el servidor; el script `start-ryzemp.sh` comprueba PHP, OPCache y la carga de `ryzertc.so`.

**Actualizacion de Egg existente:** importar una nueva version del JSON no actualiza automaticamente el `start-ryzemp.sh` ya generado; debes reinstalar el Egg para generar el script y obtener la extension. Una reinstalacion preserva `RyzeMP.phar`, `server.properties`, `plugins/` y `worlds/`.

## Seguridad y distribucion

- PHP proviene del artefacto oficial PocketMine PHP 8.4 ZTS fijado por SHA-256.
- RyzeRTC proviene de una **prerelease oficial versionada** de [RyzeCompany/RyzeRTC](https://github.com/RyzeCompany/RyzeRTC/releases/tag/v0.1.0-dev.2), no de Amber ni de una descarga efimera de GitHub Actions.
- La descarga de RyzeRTC requiere SHA-256 fijo `f5fa7e5babc456a9e33a4c8c6c864c1b510841c79eef868fad1e78787d1daa5f`; tambien se verifica `SHA256SUMS.txt` dentro del ZIP y la compatibilidad con PHP 8.4 ZTS.
- La extension se instala en `.ryzertc-runtime/ryzertc.so`; las bibliotecas compartidas quedan en `.ryzertc-runtime/lib`. El PHAR y los plugins no se modifican.
- El arranque exporta `LD_LIBRARY_PATH`, configura `PHPRC` y usa `php.ini` para cargar RyzeRTC en PHP y los procesos secundarios.
- No se crean los parametros `nethernet-enabled` ni `nethernet-ice-port`: se mantienen `server-ip` y `server-port` del servidor, sin introducir un nuevo puerto publico.
- Si RyzeRTC falla al instalarse o cargarse, el proceso muestra un error explicito en lugar de arrancar silenciosamente sin extension.

## Estado de Minecraft 1.26.60

**La prueba de carga del `.so` no equivale a solucionar Terracota ni a garantizar entrada de clientes Minecraft 1.26.60.** La release de RyzeRTC ya supero pruebas de ICE/DTLS/SCTP de extremos a extremo; sigue pendiente conectar en [RyzeMP PR #48](https://github.com/RyzeCompany/RyzeMP/pull/48) la senalizacion autenticada, la gestion de sesiones y el multiplexor UDP compartido con RakNet. Esta prerelease es solo para pruebas; no sustituye a un lanzamiento estable validado con jugadores reales.

## Pruebas de Egg

El workflow [validate-ryzertc-egg.yml](.github/workflows/validate-ryzertc-egg.yml) verifica sintaxis JSON PTDL_v2 y Bash, descarga/verifica la release en el contenedor real de instalacion Pterodactyl y prueba el arranque en su contenedor Debian. Repite la instalacion y comprueba la conservacion de mundos, plugins y PHAR.

**Compatibilidad:** el modulo de la prerelease se ha compilado para Linux x86_64, PHP 8.4 ZTS y el ABI previsto; los entornos diferentes requieren su propio binario probado.
