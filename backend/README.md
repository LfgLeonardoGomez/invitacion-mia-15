# API de la invitación de Mia

Backend independiente con FastAPI + SQLite (`sqlite3`, sin ORM). Una instancia, un evento y una invitación por familia. API v0.4 preparada para la tarjeta y el panel: invitaciones, RSVP, deseos privados, configuración de secciones, sesión administrativa persistente y enlaces recuperables cifrados. La conexión real requiere configurar el origen de esta API en el frontend; la vista sin enlace puede seguir siendo una preview, no una confirmación real.

## Preparación local (PowerShell)

Requiere Python 3.12 o posterior. Desde la raíz del proyecto:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Generar una clave privada y copiarla a MIA_ADMIN_API_KEY en .env:
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
# Generar OTRA clave privada y copiarla a MIA_LINK_ENCRYPTION_KEY:
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Sin `MIA_ADMIN_API_KEY`, todas las operaciones administrativas devuelven **503**. Una clave configurada debe tener entre 32 y 256 caracteres ASCII imprimibles sin espacios; una clave inválida impide arrancar. No existe clave ni familia de prueba por defecto. `.env` no se carga por importar Python: el comando siguiente lo carga explícitamente.

`MIA_LINK_ENCRYPTION_KEY` es una clave Fernet separada (32bytes codificados en base64url,44caracteres), no una contraseña humana ni la clave administrativa. Sin ella, la API puede iniciar y servir enlaces ya emitidos, confirmaciones, deseos y sesiones, pero **crear, regenerar o recuperar un enlace devuelve503 sin modificar nada**. Una clave malformada impide arrancar. Respaldarla de forma privada, separada de SQLite y fuera del repositorio/directorio público; no imprimirla en logs ni copiarla al frontend.

```powershell
# Ejecutar desde backend/. Sin access logs: las URLs contienen tokens privados.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --env-file .env --no-access-log --no-proxy-headers
```

El entrypoint para la CLI FastAPI también está declarado en `pyproject.toml`. Las docs están deshabilitadas; solo habilitarlas localmente con `MIA_ENABLE_DOCS=true` (`/api/docs`). `MIA_ALLOWED_ORIGINS` admite orígenes explícitos separados por comas; vacío significa sin CORS entre orígenes. No acepta `*`; permite credenciales únicamente con esos orígenes para la cookie privada del panel. La tarjeta invitada sigue omitiendo cookies.

## Contrato

JSON camelCase. Se rechazan campos extra y conversiones de tipos peligrosas (por ejemplo `"4"`, `true` o `4.5` no son una cantidad válida).

| Método y ruta | Acceso | Resultado |
| --- | --- | --- |
| `GET /api/health` | Público | `{ "status": "ok" }`; liveness, no prueba de disponibilidad de disco |
| `GET /api/invitations/{token}` | Link secreto | Evento, familia/cupo, RSVP, secciones y último deseo de esa familia únicamente |
| `PUT /api/invitations/{token}/rsvp` | Link secreto | Guarda `{ "attending": true, "guestCount": 3 }` y devuelve RSVP |
| `POST /api/invitations/{token}/wishes` | Link secreto | Crea un deseo privado con autor, mensaje y UUID de idempotencia |
| `POST /api/admin/session` | Solo clave Bearer original | Abre sesión; cookie HttpOnly y `{ authenticated: true, csrfToken, expiresAt }` |
| `GET /api/admin/session` | Cookie | Restaura sesión vigente y token CSRF; 401 si no existe o venció |
| `DELETE /api/admin/session` | Cookie + Origin + CSRF | Revoca sesión y elimina cookie; `{ authenticated: false }` |
| `GET /api/admin/event` | Admin | Datos globales del evento |
| `PUT /api/admin/event` | Admin | Reemplaza datos completos del evento |
| `POST /api/admin/invitations` | Admin + cifrado configurado | Crea `{ "familyName": "Familia Pérez", "seats": 4 }` y persiste su token cifrado |
| `GET /api/admin/invitations?limit=50&offset=0&status=all&q=` | Admin | Lista paginada con RSVP, sin tokens ni hashes; máximo 200 por página |
| `PATCH /api/admin/invitations/{id}` | Admin | Modifica `familyName`, `seats` y/o `active` |
| `POST /api/admin/invitations/{id}/rotate-token` | Admin + cifrado configurado | Invalida token anterior y cifra el nuevo; sin body |
| `GET /api/admin/invitations/{id}/link` | Admin + cifrado configurado | Recupera `{ id, token, invitationPath }` para copiar; no-store, nunca en listados |
| `GET /api/admin/summary` | Admin | Totales de familias, cupos, asistentes confirmados y deseos |
| `GET /api/admin/wishes?limit=50&offset=0&q=` | Admin | Deseos privados con autor, mensaje, fecha y familia; máximo 200 por página |
| `DELETE /api/admin/wishes/{id}` | Admin | Elimina el contenido de un deseo; sigue contando para el límite de la invitación |
| `GET /api/admin/sections` | Admin | Zona horaria, contacto y datos bancarios |
| `PUT /api/admin/sections` | Admin | Reemplaza toda la configuración de secciones |

Admin acepta `Authorization: Bearer <MIA_ADMIN_API_KEY>` para herramientas privadas; el panel la usa solo al hacer `POST /api/admin/session`. **Nunca incorporar esa clave en los archivos públicos, configuración del frontend, enlaces o almacenamiento del navegador.** El panel la descarta tras iniciar sesión y usa una cookie opaca `mia_admin_session`, HttpOnly, SameSite=Strict, sin Domain, limitada a la ruta `/api/admin` (más el prefijo del proxy si existe). Vence a las **12 horas desde el inicio**, sin renovarse por actividad. SQLite guarda solo su hash, CSRF, vencimiento y fingerprint de la clave. Reiniciar la API o recargar el navegador conserva la sesión; cerrar sesión la revoca. Cambiar la clave administrativa invalida todas las sesiones anteriores; sin clave, administración queda deshabilitada. Máximo20 sesiones activas, con poda de vencidas/antiguas al iniciar otra.

Las peticiones del panel usan `credentials: include`; las mutaciones con cookie necesitan `Origin` permitido y `X-CSRF-Token`, obtenido al abrir/restaurar sesión y guardado únicamente en memoria. Un GET sin Origin solo se acepta con `Sec-Fetch-Site: same-origin`; el navegador envía Origin al consultar la API desde otro origen. El bootstrap Bearer permite omitir Origin para herramientas privadas; si se envía Origin, también debe ser permitido. Una cabecera Authorization malformada nunca cae de vuelta a una cookie válida.

La cookie usa Secure en producción. La única excepción es HTTP local con host API, IP de conexión y Origin permitidos de loopback. **Usar `127.0.0.1` para frontend y API**, no mezclarlo con `localhost`: SameSite=Strict requiere que el panel y la API sean del mismo sitio. En producción alojarlos en el mismo origen o sitio HTTPS y configurar CORS explícitamente; no depender de cookies de terceros desde un dominio de Pages hacia una API de otro sitio. No hay usuarios individuales, MFA ni biometría en esta etapa.

La respuesta pública tiene esta forma:

```json
{
  "event": {
    "name": "Mia",
    "date": "2026-12-26",
    "arrivalTime": "20:30",
    "entranceTime": "21:30",
    "venueName": "Jardín Secreto",
    "venueAddress": "Teodoro Fels 7423, Trujui",
    "dressCode": "Elegante Sport"
  },
  "invitation": { "id": "UUID", "familyName": "Familia Pérez", "seats": 4 },
  "rsvp": null,
  "sections": {
    "eventUtcOffset": "-03:00",
    "contact": { "whatsappNumber": "5491141675124" },
    "bankTransfer": null
  },
  "wish": null
}
```

Un RSVP guardado es `{ "attending": true, "guestCount": 3, "updatedAt": "ISO-8601 UTC" }`. Asistencia positiva exige entre 1 y el cupo real; negativa exige 0. La misma respuesta repetida conserva su timestamp. El backend consulta y escribe bajo una única transacción: el cupo del cliente nunca es autoridad. Bajar cupo por debajo de una confirmación existente devuelve **409**; primero hay que resolver esa confirmación. Cupos permitidos: 1–50. No se almacena una lista de nombres de asistentes.

Tokens inexistentes, malformados, revocados o de invitaciones inactivas devuelven el mismo **404**, también para enviar deseos. Reabrir una invitación con `active: true` vuelve a habilitar su token vigente; rotarlo lo reemplaza definitivamente, sin borrar el RSVP ni los deseos. La creación y rotación devuelven `invitationPath: "/?invitation=..."`; al construir el enlace público, conservar el prefijo del sitio si está alojado en una subruta como GitHub Pages.

## Copiar enlaces después de cargar familias

SQLite conserva el hash SHA256 usado en la búsqueda pública y un **sobre Fernet cifrado y autenticado** con el identificador de familia y su token. Al recuperar se validan familia, formato y hash para impedir sustituciones entre filas. Se usa [PyCA cryptography/Fernet](https://cryptography.io/en/stable/fernet/), no criptografía casera. El token sin cifrar y la clave de cifrado no se guardan en SQLite, respuestas de listados ni payloads públicos.

Solo el endpoint administrativo de una familia entrega el token descifrado, con headers no-store. El navegador necesariamente recibe el enlace temporalmente para copiarlo al portapapeles; no mostrar la URL en pantalla no la vuelve invisible para las herramientas del navegador ni para quien acceda al portapapeles. No persistirla en localStorage/sessionStorage, DOM oculto o logs. Los campos `token`/`invitationPath` de las respuestas de creación y rotación se conservan por compatibilidad con herramientas privadas, pero el panel puede ignorarlos y copiar luego desde la tarjeta.

La migración v4 agrega una columna nullable, **sin regenerar ni invalidar enlaces existentes**. Las familias antiguas con solo hash siguen funcionando con su URL original; intentar recuperarla devuelve409. Si ya no se conserva esa URL, debe regenerarse explícitamente, con advertencia de que la anterior dejará de funcionar. Esto no elimina confirmaciones ni deseos.

Una clave equivocada, un sobre corrupto o intercambiado no produce un enlace nuevo ni revela detalles: recuperación devuelve503. Perder la clave impide recuperar enlaces cifrados; los enlaces originales conservados siguen abriendo por su hash. No cambiar la clave sin un proceso de recifrado/migración y backup verificado; ese proceso operativo de rotación de clave de cifrado no está automatizado aquí.

### Deseos privados

`POST /api/invitations/{token}/wishes` recibe `{ "author": "Ana", "message": "¡Feliz cumple!", "clientRequestId": "UUID" }`. Autor: 1–80 caracteres; mensaje: 1–600; se recortan espacios extremos y se rechazan caracteres nulos. El texto se conserva como texto, no como HTML confiable. Devuelve **201** con `{ "id", "author", "message", "createdAt", "updatedAt" }`; ambas fechas son iguales porque no hay edición de deseos. La tarjeta recibe solo el último deseo de su propia familia; únicamente administración puede listar todos.

Reintentar con la misma UUID y contenido devuelve el mismo deseo sin duplicarlo; usar esa UUID con contenido distinto devuelve **409**. La UUID se limita a esa familia y no se expone en listados. Se admiten hasta **10 deseos por invitación** para que distintos miembros escriban sin sobrescribirse; una nueva solicitud al llegar al límite devuelve **409** con `code: wish_limit_reached` y `maxWishes: 10`, pero una repetición idempotente sigue funcionando. No se borran mensajes históricos que excedan el nuevo límite. Rotar el enlace no reinicia ese límite. El límite adicional de10envíos/minuto por IP es independiente. No hay muro público, envío automático de WhatsApp ni email.

### Resumen, filtros y secciones

- `status` admite `all`, `active`, `inactive`, `confirmed`, `declined`, `pending`. El valor predeterminado de la API sigue siendo `all`, que incluye inactivas para compatibilidad; `active` e `inactive` filtran por activaci?n, y los tres estados RSVP solo incluyen familias activas. El panel solicita `active` inicialmente y ofrece una pesta?a `inactive`. `q` busca literalmente en el nombre familiar (máximo 120 caracteres), no interpreta `%`, `_` ni SQL. Los deseos buscan además por autor y mensaje. SQLite LIKE ignora mayúsculas ASCII, no garantiza búsqueda sin acentos.
- Resumen: `totalInvitations` incluye todas; `activeInvitations`, `confirmedInvitations`, `declinedInvitations`, `pendingInvitations`, `confirmedGuests` y `reservedSeats` cuentan solo activas. `confirmedGuests` es cantidad de personas, no familias. `totalWishes` incluye los deseos de activas e inactivas.
- `eventUtcOffset` es `-03:00` para este evento. `contact.whatsappNumber` admite dígitos internacionales ASCII sin `+`, o cadena vacía para ocultar el contacto. `bankTransfer` puede ser `null`, o un objeto `{ holder, bank, alias, accountNumber, illustrative }`; alias o cuenta debe estar presente. `accountNumber` es vacío o 22 dígitos ASCII. No se valida titularidad bancaria ni se realizan transferencias.
- El valor inicial es el banco **ilustrativo** de la tarjeta (`illustrative: true`), no datos reales. Solo reemplazarlo después de verificar los datos con el organizador. `PUT` sustituye el objeto completo, no hace merge parcial.

## Persistencia y despliegue

- La base se crea al iniciar el lifespan, con el evento real si aún no existe. Reiniciar no pisa cambios ni crea invitados demo.
- `MIA_DATABASE_PATH` vacío usa `backend/data/invitations.sqlite3`. En producción usar ruta persistente privada, disco local y permisos exclusivos del usuario de servicio. Proteger también archivos `-wal`/`-shm` y backups; en Windows configurar ACL del directorio. Nunca exponer esa carpeta al servidor web.
- Todas las consultas usan parámetros SQL; conexiones por operación y transacciones `BEGIN IMMEDIATE` para mutaciones. No se comparten conexiones entre hilos.
- Ejecutar **un solo worker/proceso** detrás de HTTPS: el rate limit vive en memoria y SQLite no se plantea como base distribuida. Escalar requiere revisar almacenamiento y límites compartidos.
- Ejemplo de proceso detrás de un proxy HTTPS configurado: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --env-file .env --no-access-log --no-proxy-headers`. Si el proxy necesita IP real, configurar confianza explícita, no aceptar cabeceras de cualquier cliente.
- Desactivar o redactar logs del proxy/CDN/hosting que incluyan **paths o query strings** con tokens (`/api/invitations/...` y `/?invitation=...`). El token permite leer/modificar la respuesta de esa familia: compartirlo solo con ella. Rotarlo si se filtra.
- La telemetría nativa de FastAPI queda deshabilitada explícitamente (trazas, métricas, logs y autoconfiguración de exporters). No instrumentar externamente esta API sin una política de redacción de secretos y datos personales.
- Servir únicamente los archivos públicos de la tarjeta mediante una allowlist o directorio público separado. **No usar `http.server` sobre la raíz del repositorio**: podría publicar `.env`, SQLite o código privado. Esta API no monta archivos estáticos.
- Para backup consistente usar la API de backup de SQLite o detener la API antes de copiar base y sus auxiliares; no copiar solo el archivo principal mientras hay escrituras WAL.
- Migraciones aditivas y transaccionales en `schema_migrations`: versión1 adopta tablas originales; versión2 agrega secciones y deseos; versión3 sesiones; versión4 `token_ciphertext` nullable para enlaces recuperables. No reescribe datos del evento, familias ni RSVP existentes ni regenera enlaces antiguos. Una base con versión posterior a la soportada impide iniciar; hacer backup consistente antes de actualizar. Cambiar defaults en código solo afecta a bases nuevas, no corrige automáticamente una configuración existente.
- No hay historial de auditoría administrativa ni borrado/moderación de deseos todavía. Revisar [SECURITY.md](SECURITY.md) para límites de amenazas y operación.

## Pruebas (sin build)

Desde la raíz:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
```

Cada prueba usa una base temporal independiente. Se cubren aislamiento entre familias, persistencia, validación estricta, idempotencia y concurrencia de cupos/deseos, rotación/revocación, filtros/totales, migración de una base anterior y protección administrativa, además del middleware de seguridad. No se crea ni modifica una base real en estas pruebas.
