# Seguridad y alcance del backend

Esta primera versión es para **un evento y un proceso de API**. Los controles reducen riesgos concretos; no equivalen a una auditoría de producción ni reemplazan una configuración de despliegue segura.

## Controles de aplicación

- Administración con `Authorization: Bearer <ADMIN_API_KEY>`. La clave debe configurarse fuera del código, con al menos 32 caracteres y suficiente aleatoriedad. Si falta, las operaciones administrativas quedan deshabilitadas con `503`; no hay clave de demostración activa por defecto.
- Comparación de credenciales con `secrets.compare_digest` sobre bytes, respuesta `401` genérica para credenciales incorrectas/malformadas/duplicadas y sin reflejar la clave. La [documentación de Python](https://docs.python.org/3/library/secrets.html#secrets.compare_digest) describe esta comparación de tiempo constante y generación de tokens seguros.
- El enlace de una familia es una **credencial de acceso por posesión**: quien tenga el token podrá acceder a esa invitación y responder. No compartirlo públicamente; rotarlo o desactivarlo si se expone. Esto no verifica identidad personal de cada invitado.
- Límite de cuerpo API de **16 KiB**, verificado antes de ejecutar la ruta, también sin `Content-Length` y con cuerpo por chunks. Solicitudes excesivas reciben `413` y no alcanzan la lógica de modificación.
- Escrituras con cuerpo solo aceptan `application/json` (puede incluir charset). No se aceptan formularios, `text/plain` ni compresión de cuerpos. Un POST sin cuerpo, como rotar un token, no exige un header ficticio.
- Límites de solicitudes por IP de conexión y categoría, en ventana de 60 segundos: 120 públicas, 20 actualizaciones RSVP y 30 administrativas. `OPTIONS` no consume cuotas. Respuestas `429` incluyen `Retry-After`.
- El almacén de límites está acotado a 4096 entradas, protegido para concurrencia y con vencimiento. **No guarda tokens, rutas, cuerpos ni cabeceras**; no confía en `X-Forwarded-For` enviado por el cliente.
- Respuestas API con `Cache-Control: no-store`, `Pragma: no-cache`, `X-Content-Type-Options: nosniff` y `Referrer-Policy: no-referrer`. Los errores inesperados previos a la respuesta devuelven un `500` genérico; los logs propios solo registran la clase del error, no su mensaje/datos.
- CORS se configura con orígenes explícitos, no como autenticación. No debe incluir comodines ni credenciales de navegador. `CORSMiddleware` debe envolver el middleware de seguridad para que también las respuestas de rechazo incluyan los headers CORS; véase el patrón de [middlewares de FastAPI](https://fastapi.tiangolo.com/advanced/middleware/).

## Condiciones necesarias antes de publicar

1. **HTTPS obligatorio.** El servidor local puede hablar HTTP únicamente en loopback detrás de un proxy TLS correctamente configurado. Un enlace privado y un bearer administrativo no deben circular por HTTP público. [FastAPI: HTTPS](https://fastapi.tiangolo.com/deployment/https/).
2. Usar un secreto administrativo generado de forma segura; no guardarlo en el frontend, enlaces, repositorio, capturas o registros. No usar una contraseña humana reutilizada. Esta versión no tiene usuarios, roles, MFA ni una sesión administrativa de navegador; el bearer concede administración completa.
3. **Deshabilitar o redactar los access logs de servidor y proxy.** Tanto la ruta `/api/invitations/{token}` como el enlace frontend `/?invitation={token}` contienen la credencial. No registrar URL completa, query, Authorization ni cuerpo. En Uvicorn se puede desactivar el access log con `--no-access-log`; revisar también el proxy, CDN, APM y analítica. [Uvicorn: logging](https://www.uvicorn.org/settings/#logging).
4. No servir la raíz del repositorio con un servidor estático genérico: puede exponer `.env`, base SQLite, backups o código. Publicar solo archivos front permitidos y `assets/` desde un directorio de salida separado. La API no debe montar el repo como archivos estáticos.
5. Restringir acceso/red, permisos del archivo SQLite y sus backups. Backups fuera del directorio público; proteger su contenido, probar restauración y definir una retención razonable de nombres y confirmaciones.
6. Aplicar límites de tamaño de request, headers, conexiones y tiempo de lectura en el proxy. El límite ASGI no protege contra slowloris ni agota todas las formas de abuso de red.
7. Ejecutar **un solo worker/instancia** con este limitador en memoria. Sus contadores se reinician al reiniciar el proceso; un atacante con muchas IP o instancias distribuidas requiere protección compartida/edge. Una ventana fija permite ráfagas cerca de su cambio. No es una garantía de protección DDoS.
8. Configurar el origen permitido exacto del frontend. Si se coloca un proxy, confiar en headers de forwarding **solo** desde proxies conocidos. Por defecto, los límites usan el peer real de `scope.client`; detrás de un proxy sin configuración apropiada pueden compartir cuota todos los usuarios. [Uvicorn: proxy settings](https://www.uvicorn.org/settings/#http).
9. La futura página con token en URL debe usar `Referrer-Policy: no-referrer` y evitar analítica o recursos externos que reciban la URL. No incluir datos de otras familias en el payload del cliente ni tratar los cupos mostrados en HTML como fuente de verdad.

## Verificación local, no certificación

`backend/tests/test_security.py` comprueba auth correcta/incorrecta, clave ausente, Unicode/duplicados, cuerpo con/sin longitud y por chunks, rechazo antes de mutar, JSON, headers, límites/expiración/concurrencia/caché acotada, CORS preflight y errores genéricos. La suite de core valida las reglas de datos, permisos y persistencia. Ninguna prueba local reemplaza revisar el entorno real antes de exponerlo.

No se hicieron builds ni despliegues como parte de esta implementación.
