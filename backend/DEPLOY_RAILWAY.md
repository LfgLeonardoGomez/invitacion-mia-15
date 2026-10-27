# Producción: Railway + frontend Vercel

## Estado y alcance

La configuración del repositorio está preparada; eso NO implica que exista un despliegue.
Primero validar con familias ficticias y recién después entregar enlaces reales.
No migrar automáticamente la base local ni sus credenciales a producción.

## Servicio Railway

1. Crear un servicio desde este repositorio, rama `main`.
2. Configurar Root Directory `/backend` y Config File `/backend/railway.json`.
   El archivo de configuración se indica desde la raíz del repositorio.
3. Agregar un volumen al servicio, montado en `/data`, antes del primer uso.
4. Configurar una sola réplica en una sola región. No activar suspensión/serverless.
5. Variables privadas del servicio:

   | Variable | Valor |
   | --- | --- |
   | `MIA_DATABASE_PATH` | `/data/invitations.sqlite3` |
   | `MIA_ADMIN_API_KEY` | Clave nueva aleatoria, mínimo32 caracteres |
   | `MIA_LINK_ENCRYPTION_KEY` | Clave Fernet nueva, distinta de la administrativa |
   | `MIA_ENABLE_DOCS` | `false` |
   | `MIA_ALLOWED_ORIGINS` | Origen HTTPS definitivo de Vercel, sin ruta ni barra final |

   Railway inyecta `PORT` y `RAILWAY_VOLUME_MOUNT_PATH`; no reemplazar esta última.
   Generar y respaldar las claves por un canal privado; nunca pegarlas en el chat,
   frontend, commits o capturas. La clave Fernet debe conservarse entre despliegues.
   Durante el primer despliegue puede omitirse `MIA_ALLOWED_ORIGINS`: el panel
   entre orígenes no estará habilitado hasta configurar su dominio definitivo.
6. Sin comandos de pre-deploy para migraciones: el volumen no está montado allí.
   El lifespan de la API realiza las migraciones al arrancar, sobre el volumen.
7. Railway instala dependencias y ejecuta `python railway_start.py`.
   El launcher rechaza una ruta SQLite fuera del volumen o secretos faltantes.
   Inicia un worker, sin access logs ni confianza en cabeceras proxy arbitrarias.
8. Generar dominio HTTPS del servicio. Verificar `GET /api/health`.
   Este healthcheck es liveness, no una prueba de restauración ni de espacio libre.

No se ejecutan builds locales. El despliegue remoto necesita la instalación/empaquetado
normal del proveedor. No importar assets, referencias ni datos locales al servicio.

## Frontend Vercel (siguiente etapa)

Publicar únicamente los archivos seleccionados por `scripts/prepare_pages.py`.
Nunca servir la raíz del repositorio: contiene código y documentación privados.
Crear una rewrite `/api/:path*` hacia `https://DOMINIO-RAILWAY/api/:path*`.
Configurar `apiBaseUrl: ''` y `invitationBaseUrl` con la URL pública definitiva.
La clave administrativa NO forma parte de ninguna variable pública del frontend.

Validar en el dominio final que el proxy conserva cookies, Origin y CSRF:
login, recarga, logout y rechazo de solicitudes sin CSRF. No debilitar SameSite
para compensar un proxy mal configurado. No cachear respuestas `/api/*`.
Revisar logs/analytics de ambos proveedores para no registrar tokens en rutas
o query strings; los enlaces privados permiten operar sobre la familia.

## Prueba de aceptación y entrega

- Crear familias ficticias identificadas como prueba, con cupos distintos.
- Copiar enlaces después de recargar el panel; abrirlos desde otro navegador.
- Confirmar asistencia, no asistencia, límites de cupo y envío de deseos.
- Revisar filtros, contadores, edición, desactivación y reactivación.
- Reiniciar/redeployar y verificar persistencia de datos y recuperación de enlaces.
- Comprobar separación entre familias y rechazo de enlaces revocados.
- Realizar un backup consistente con `sqlite3.Connection.backup()` y probar
  restauración sobre una copia aislada. Backups del volumen son complemento;
  no asumir consistencia SQLite de una copia del archivo principal con WAL activo.

### Limpieza posterior: operación separada, NO ejecutada al desplegar

Una vez aprobadas las pruebas, detener escrituras y respaldar consistentemente.
Eliminar las familias de prueba, sus confirmaciones y deseos, y revocar sesiones
administrativas, conservando evento, secciones y esquema/migraciones.
No borrar el volumen ni todo el archivo SQLite como atajo: eso también perdería
configuración real. Verificar integridad y contadores en cero; comprobar que los
enlaces de prueba devuelven404. El procedimiento destructivo se prepara y ejecuta
contra el servicio identificado al finalizar las pruebas, no automáticamente.
No cargar invitados reales hasta completar esta limpieza.

## Backups y rollback

Programar backups y definir retención fuera del servicio. Respaldar la clave Fernet
por separado; una DB sin su clave no permite recuperar enlaces cifrados.
Ante fallo de despliegue, detener escrituras y tomar backup antes de retroceder.
No ejecutar código antiguo contra un esquema más nuevo: restaurar una copia
compatible, documentando cualquier dato posterior al backup que se perdería.

Referencias: [Railway config](https://docs.railway.com/config-as-code/reference),
[volúmenes](https://docs.railway.com/volumes),
[backups](https://docs.railway.com/volumes/backups),
[rewrites Vercel](https://vercel.com/docs/routing/rewrites).
