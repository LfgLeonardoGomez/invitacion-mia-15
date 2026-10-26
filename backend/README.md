# API de la invitación de Mia

Backend independiente con FastAPI + SQLite (`sqlite3`, sin ORM). Una instancia, un evento y una invitación por familia. El frontend **todavía usa datos mock**: no consulta esta API ni envía confirmaciones reales.

## Preparación local (PowerShell)

Requiere Python 3.12 o posterior. Desde la raíz del proyecto:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Generar una clave privada y copiarla a MIA_ADMIN_API_KEY en .env:
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Sin `MIA_ADMIN_API_KEY`, todas las operaciones administrativas devuelven **503**. Una clave configurada debe tener entre 32 y 256 caracteres ASCII imprimibles sin espacios; una clave inválida impide arrancar. No existe clave ni familia de prueba por defecto. `.env` no se carga por importar Python: el comando siguiente lo carga explícitamente.

```powershell
# Ejecutar desde backend/. Sin access logs: las URLs contienen tokens privados.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --env-file .env --no-access-log --no-proxy-headers
```

El entrypoint para la CLI FastAPI también está declarado en `pyproject.toml`. Las docs están deshabilitadas; solo habilitarlas localmente con `MIA_ENABLE_DOCS=true` (`/api/docs`). `MIA_ALLOWED_ORIGINS` admite orígenes explícitos separados por comas; vacío significa sin CORS entre orígenes. No acepta `*` ni envía credenciales/cookies.

## Contrato

JSON camelCase. Se rechazan campos extra y conversiones de tipos peligrosas (por ejemplo `"4"`, `true` o `4.5` no son una cantidad válida).

| Método y ruta | Acceso | Resultado |
| --- | --- | --- |
| `GET /api/health` | Público | `{ "status": "ok" }`; liveness, no prueba de disponibilidad de disco |
| `GET /api/invitations/{token}` | Link secreto | Evento, familia/cupo y RSVP de esa familia únicamente |
| `PUT /api/invitations/{token}/rsvp` | Link secreto | Guarda `{ "attending": true, "guestCount": 3 }` y devuelve RSVP |
| `GET /api/admin/event` | Admin | Datos globales del evento |
| `PUT /api/admin/event` | Admin | Reemplaza datos completos del evento |
| `POST /api/admin/invitations` | Admin | Crea `{ "familyName": "Familia Pérez", "seats": 4 }`; devuelve token una sola vez |
| `GET /api/admin/invitations?limit=50&offset=0` | Admin | Lista paginada con RSVP, sin tokens ni hashes; máximo 200 por página |
| `PATCH /api/admin/invitations/{id}` | Admin | Modifica `familyName`, `seats` y/o `active` |
| `POST /api/admin/invitations/{id}/rotate-token` | Admin | Invalida token anterior; devuelve nuevo token una sola vez; sin body |

Admin requiere `Authorization: Bearer <MIA_ADMIN_API_KEY>`. Guardar esa clave solo en herramientas privadas del organizador: **nunca en el frontend**. No hay panel administrativo, registro de usuarios ni roles múltiples.

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
    "dressCode": "Elegante sport"
  },
  "invitation": { "id": "UUID", "familyName": "Familia Pérez", "seats": 4 },
  "rsvp": null
}
```

Un RSVP guardado es `{ "attending": true, "guestCount": 3, "updatedAt": "ISO-8601 UTC" }`. Asistencia positiva exige entre 1 y el cupo real; negativa exige 0. La misma respuesta repetida conserva su timestamp. El backend consulta y escribe bajo una única transacción: el cupo del cliente nunca es autoridad. Bajar cupo por debajo de una confirmación existente devuelve **409**; primero hay que resolver esa confirmación. Cupos permitidos: 1–50. No se almacena una lista de nombres de asistentes.

Tokens inexistentes, malformados, revocados o de invitaciones inactivas devuelven el mismo **404**. Reabrir una invitación con `active: true` vuelve a habilitar su token vigente; rotarlo lo reemplaza definitivamente, sin borrar el RSVP. La creación y rotación devuelven `invitationPath: "/?invitation=..."` para construir el link del frontend cuando se integre. **Ese link todavía no está conectado a la tarjeta.**

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
- No hay migraciones versionadas ni auditoría administrativa todavía; planificarlas antes de cambiar esquema o ampliar alcance. Revisar [SECURITY.md](SECURITY.md) para límites de amenazas y operación.

## Pruebas (sin build)

Desde la raíz:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
```

Cada prueba usa una base temporal independiente. Se cubren aislamiento entre familias, persistencia, validación estricta, idempotencia, concurrencia de cupos, rotación/revocación y protección administrativa, además del middleware de seguridad. No se crea ni modifica una base real en estas pruebas.
