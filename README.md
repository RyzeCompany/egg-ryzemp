# RyzeMP · Egg de Pterodactyl con RyzeRTC

Instala PHP 8.4 ZTS y RyzeRTC API 2 en Linux x86_64, compatible con Debian 12 / glibc 2.36. El módulo nativo y sus bibliotecas quedan en `.ryzertc-runtime/`, **fuera de `RyzeMP.phar`**.

## Instalar o actualizar

1. Importa [egg-ryze-m-p.json de la rama de pruebas](https://raw.githubusercontent.com/RyzeCompany/egg-ryzemp/feature/ryzertc-native-egg/egg-ryze-m-p.json) en **Nests → Import Egg**.
2. Conserva la imagen `ghcr.io/ptero-eggs/yolks:debian`, la asignación habitual y los valores existentes de `server-ip` y `server-port`.
3. Respalda el servidor y reinstala el egg para obtener RyzeRTC y regenerar `start-ryzemp.sh`. La reinstalación conserva `server.properties`, mundos, plugins, identidad del operador y cualquier PHAR existente.
4. Si ya existe `RyzeMP.phar`, **reemplázalo manualmente por el PHAR nuevo** de la [release de integración autenticada](https://github.com/RyzeCompany/RyzeMP/releases/tag/ryzemp-2225-ryzertc-integration.1). El instalador descarga ese PHAR únicamente cuando falta.
5. Inicia y espera `NetherNet READY`. El arranque verifica PHP, OPCache, bibliotecas, carga del módulo y API 2; RyzeMP obtiene las claves oficiales de Minecraft en segundo plano.

## Una sola asignación pública

La señalización HTTP usa **TCP** y RakNet/WebRTC usan **UDP**, ambos en el mismo `server-port`, por ejemplo 19132. No se agregan `nethernet-enabled`, `nethernet-ice-port` ni otro puerto público. El mux privado de ICE se administra automáticamente en loopback.

Wings debe publicar la asignación para **TCP y UDP**. En el host del nodo, inspecciona `docker inspect ID_DEL_CONTENEDOR`: `NetworkSettings.Ports` debe incluir `19132/tcp` y `19132/udp` con la misma asignación. Permite ambos protocolos en el firewall. El JSON del egg no puede modificar los mapeos Docker ni el firewall del host.

Desde una red externa, `http://IP_O_DOMINIO:PUERTO/v1/join` debe devolver HTTP 200 y `protocol: 2225`. Esa respuesta verifica acceso TCP; todavía hay que probar UDP y el ingreso real del cliente.

## Versiones e integridad

| Componente | Release | SHA-256 del archivo descargado |
|---|---|---|
| RyzeRTC API 2 | [v0.1.0-dev.3](https://github.com/RyzeCompany/RyzeRTC/releases/tag/v0.1.0-dev.3) | `9ecea6cc9d239b8c583d042c91df0448432321ceaf128850fe5b27bcde234602` |
| RyzeMP 2225 | [ryzemp-2225-ryzertc-integration.1](https://github.com/RyzeCompany/RyzeMP/releases/tag/ryzemp-2225-ryzertc-integration.1) | `6856b9f88965ceed0ce1052e0b59142ad880c69181c9258ef3c2558931151eba` |

El instalador verifica el SHA-256 del ZIP nativo y su manifiesto interno, PHP 8.4 ZTS x86_64 y la carga real de la API. El PHAR se verifica por hash y con PHP `Phar`. Las descargas proceden de releases oficiales propias, no de artefactos temporales. No se utiliza Amber ni se modifica HardCoreFactions.

El operador conserva su clave P-384 en `nethernet/operator-key.pem` con permisos 0600. Incluye ese archivo en tus respaldos: cambiarlo restablece la confianza TOFU del cliente. El instalador no lo borra ni lo reemplaza.

## Integración y pruebas

RyzeMP sustituye el receptor de diagnóstico por metadata GET, validación de JWT oficial y huellas DTLS, respuestas SDP firmadas, ICE/DTLS/SCTP y sesiones Minecraft mediante DataChannels. La autenticación está activa: una oferta sin identidad válida se rechaza con HTTP 401.

El [workflow del egg](.github/workflows/validate-ryzertc-egg.yml) instala las releases en imágenes reales de instalación y ejecución de Pterodactyl, arranca el PHAR, publica y prueba TCP y UDP con el mismo número, verifica metadata y rechazo de ofertas sin firma, recibe un pong RakNet y comprueba cierre y preservación de PHAR, plugins, mundos y clave del operador al reinstalar.

Los [tests de RyzeMP](https://github.com/RyzeCompany/RyzeMP/actions/workflows/ci-2225-phar-preview.yml) también realizan negociación nativa autenticada con identidades sintéticas, transmisión binaria, fragmentación, concurrencia y reconexiones. Consulta el [detalle técnico](https://github.com/RyzeCompany/RyzeMP/blob/feature/bedrock-1.26.60-nethernet/docs/BEDROCK_1_26_60_NETHERNET.md).

**Pendiente obligatorio:** probar en el host Wings real con Minecraft Bedrock 1.26.60: login, mundo, movimiento, interacción, inventario, paquetes de recursos, desconexión, reconexión y coexistencia con un cliente RakNet. No se declara Terracotta solucionado hasta completar esa prueba. Las PR permanecen abiertas, sin fusionar a main.
