# Invitación de Mia

Invitación móvil de quince años con panel administrativo y backend FastAPI + SQLite. La portada, música, fondo y revelado aprobados se mantienen independientes de la carga de datos.

Repositorio: [LfgLeonardoGomez/invitacion-mia-15-anios](https://github.com/LfgLeonardoGomez/invitacion-mia-15-anios), rama principal `main`. Vista previa en [GitHub Pages](https://lfgleonardogomez.github.io/invitacion-mia-15-anios/), disponible cuando finalice correctamente el workflow `Publicar invitación`.

## Vista previa y datos

Sin enlace privado, `index.html` conserva la vista previa local de `invitation-data.js`. Con `?invitation=TOKEN`, el adaptador exige una API configurada en `app-config.js` y carga los grupos `event`, `invitation`, `rsvp`, `sections` y `wish` del backend. **Un enlace inválido o un servidor caído nunca se convierte en una invitación simulada.** El ingreso queda bloqueado con un aviso y reintento hasta cargar datos válidos.

- Los datos del evento son los confirmados para Mia.
- **Familia Gomez / 3 lugares es el ejemplo de vista previa** solicitado, no una invitación real cargada en el backend. El saludo dice «En mi noche especial…» y «Reservamos 3 lugares para compartir este momento juntos».
- Asistentes se eligen con botones de selección única generados de **1 al cupo** recibido. Son radios nativos accesibles con teclado; no hay cantidad libre ni selección automática. El servidor sigue siendo quien valida el cupo real.
- **Dos modos separados:** sin token, formularios solo en memoria y sin peticiones HTTP; con token y API configurada, RSVP y deseos se guardan en SQLite y reaparecen al recargar. La confirmación de guardado real solo se muestra tras una respuesta válida del servidor. Los errores conservan lo escrito/seleccionado.
- Al guardar, una lámpara dorada asciende desde la base del viewport con un agradecimiento visible, sin bloquear la página ni cambiar el foco. Entrada y salida duran1s cada una, con curvas suaves por segmento y3,2s de lectura; el easing global es lineal para no comprimir el ingreso. Con movimiento reducido se usan fades de360ms sin desplazamiento. Solo celebra guardados reales; si la familia no asiste, agradece el aviso sin decir «te esperamos». Vista previa y errores muestran avisos distintos, sin afirmar entrega. Mantiene un resultado visible junto al formulario. Al enviar un deseo correctamente limpia nombre, mensaje y contador, conservando el último deseo enviado como recuerdo.
- Cuenta regresiva hasta la recepción: **26/12/2026 20:30, UTC−03:00**, independiente de la zona horaria del invitado. Se detiene en cero y muestra «¡Llegó el gran día!».
- Regalos/transferencias: botón «Ver datos bancarios» que abre un **modal de cristal violeta casi transparente**, con filete dorado, texto opaco/legible y blur12px. Usa un [`dialog` nativo](https://html.spec.whatwg.org/multipage/interactive-elements.html#the-dialog-element) fuera de las secciones animadas. Cierra con cruz/Escape o un toque que empieza fuera; no se cierra al arrastrar desde dentro. Mantiene inerte el fondo, bloquea su scroll y restaura el foco al botón. En pantallas bajas el contenido del modal tiene scroll propio.
- Datos de transferencia suministrados por el usuario: titular Mia Aylen Torres, Mercado Pago, alias `mia.aylen.torres67`, sin CBU/CVU visible. Con `bankTransfer: null` se oculta el botón y vuelve el estado pendiente. Las secciones ya guardadas en la base de datos se administran por separado y no cambian al modificar los valores iniciales. No realiza pagos ni guarda información bancaria del invitado.
- El panel administrativo permite consultar, editar o desactivar los datos de transferencia. Al guardar obtiene las secciones vigentes y conserva contacto y zona horaria; la API reemplaza el objeto completo, por lo que dos ediciones simultáneas todavía pueden sobrescribirse. Verificar los datos en una invitación personalizada después de guardar.
- Deseos: nombre de hasta80 caracteres y mensaje de hasta600. En modo API se agregan deseos privados por invitación (máximo10); cada envío usa UUID para no duplicarse al reintentar una respuesta incierta. El servidor valida el total aunque se rote el enlace. Al llegar al límite muestra un aviso y conserva lo escrito; no borra mensajes históricos si había más de10 bajo el límite anterior. Un reintento idempotente ya aceptado sigue siendo válido. El invitado ve el último deseo de su familia; el panel puede leer todos. No hay muro público ni mensajes de otras familias en el payload del invitado.
- `invitation-sections.js` maneja contador, datos de regalo y formulario de deseos sin modificar la intro aprobada ni realizar peticiones HTTP.
- Contacto: `sections.contact.whatsappNumber` configura el número internacional de la mamá, solo dígitos. Se usa un [enlace directo oficial de WhatsApp](https://faq.whatsapp.com/5913398998672934) con mensaje genérico, sin datos familiares ni token de invitación. El chat se abre al tocar el enlace; no se envía un mensaje automáticamente.
- Pie: usa **solo el castillo y parte de la colina de `assets/Reino de Linternas sobre el Lago.png`**, mediante un recorte visual CSS de425×480px desde(125,360), máscara SVG suavizada y fundido lateral/inferior. Se quitaron140px de la base anterior (620px), sin comprimir ni cortar las torres. El bote, el lago y los faroles grandes quedan fuera. Oscurecimiento `brightness(.68)`, saturación `.78` y opacidad `.92` conservan las ventanas cálidas. Ancho máximo380px, también acotado por la altura de pantalla: «¡Te espero!», Mia/fecha y castillo forman un único cierre que entra completo en el último viewport desde320×568, incluso en la prueba horizontal844×390. La imagen de entrada queda intacta; la silueta negra anterior se conserva sin uso.
- Farolitos locales ascienden desde detrás de las terrazas del nuevo encuadre, se pausan fuera de pantalla y quedan estáticos con movimiento reducido. Al entrar el castillo en pantalla se desvanece la capa de farolitos lejanos para evitar un origen visual desconectado.
- La tarjeta no contiene claves administrativas. El panel usa la clave únicamente para crear una sesión opaca de12horas en una cookie HttpOnly/SameSiteStrict, Secure fuera del entorno local; no guarda la clave en URL ni storage. Recargar restaura la sesión desde el servidor; salir la revoca. Las escrituras con cookie requieren CSRF y origen permitido. El único dato en sessionStorage es una marca booleana de cierre pendiente si falló la red, nunca una credencial. El enlace familiar sí es una credencial: no compartirlo públicamente.
- No publicar referencias de Instagram, tests, `.env`, bases de datos ni todo el repositorio como sitio estático. Evitar `python -m http.server` desde la raíz: también expondría archivos del backend. Publicar solo archivos/recursos públicos seleccionados o un directorio de salida dedicado.

## Panel y prueba local conectada

`admin.html` presenta cada familia en una tarjeta violeta arqueada con doble borde dorado. Su frente muestra nombre, cupo, estado y personas confirmadas; al tocarlo, una segunda cara muestra Editar, Activar/Desactivar, Copiar enlace y Regenerar enlace **dentro de la misma altura de320px**, sin desplazar otras tarjetas ni la página. Giro tridimensional suave de420ms; teclado y movimiento reducido cambian de cara sin giro. Los nombres usan inicial may?scula por palabra solo en presentaci?n, sin modificar la base; los datos est?n centrados y cada cara contiene sus propios bordes y espacio interior. Cerrar o Escape devuelven el foco sin scroll. Los avisos largos tienen scroll interno. Grilla de2columnas en escritorio y1en móvil, con20familias por página. El resumen de familias activas muestra también las **personas invitadas/lugares reservados**, separado de quienes confirmaron. El total general también incluye familias desactivadas.

La vista inicial muestra **Activas**; la pesta?a **Desactivadas** permite consultar y reactivar familias sin borrar sus confirmaciones ni deseos. Permite buscar mientras se escribe y paginar. Ambas búsquedas esperan una pausa breve de280ms para no enviar una petición por cada tecla; ignoran respuestas obsoletas y conservan Enter/botón como acceso alternativo. Muestra los deseos privados. No hay envío automático por WhatsApp ni nómina individual de asistentes.

Los tokens nuevos se conservan **cifrados con Fernet** y una clave privada independiente, además del hash para validar las visitas públicas. El botón «Copiar enlace» recupera únicamente el de esa familia, con autenticación administrativa, y lo copia sin agregarlo a inputs, texto, atributos ni almacenamiento del navegador. El navegador recibe el enlace descifrado transitoriamente para escribirlo en el portapapeles: no es invisible a las herramientas de desarrollo ni al historial del portapapeles del sistema. Si no se permite copiar, se muestra un error y reintento, nunca un fallback que exponga la URL.

Crear y regenerar ya no abren un modal con el enlace. Se pueden cargar todas las familias y después abrir cada tarjeta para copiar. **Regenerar** sigue siendo una acción distinta con advertencia: invalida el enlace anterior, sin borrar confirmación ni deseos. Las invitaciones antiguas que solo guardaban hash siguen funcionando con su URL original, pero no pueden recuperarse: el panel ofrece regenerarlas individualmente, nunca lo hace automáticamente. No se puede reducir el cupo por debajo de una confirmación existente.

1. Preparar el entorno siguiendo [backend/README.md](backend/README.md), crear `backend/.env` con clave administrativa aleatoria y una **clave de cifrado distinta** (`MIA_LINK_ENCRYPTION_KEY`, generada con `Fernet.generate_key()`), y configurar `MIA_ALLOWED_ORIGINS=http://127.0.0.1:5173`. Respaldar la clave de cifrado por un canal privado separado de la base; no regenerarla en cada arranque. Sin ella no se crean, rotan ni recuperan enlaces. Perderla impide recuperarlos, aunque una URL original conservada sigue validándose por su hash. Ver [documentación de Fernet](https://cryptography.io/en/stable/fernet/).
2. En una terminal desde la raíz:

   ```powershell
   .\backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --env-file backend/.env --no-access-log --no-proxy-headers
   ```

3. En otra terminal:

   ```powershell
   python scripts/serve_frontend.py --port 5173 --api-base-url http://127.0.0.1:8000
   ```

4. Abrir `http://127.0.0.1:5173/admin.html`, ingresar la clave configurada y crear una familia. El enlace generado abre la invitación real. Recargar conserva la sesión mientras esté vigente (12horas); «Cerrar sesión» la revoca. Usar127.0.0.1 tanto en frontend como en API: mezclar localhost y127.0.0.1 impide el funcionamiento de una cookie Strict.

El servidor local sirve **solo una allowlist pública**, no el repositorio, y genera `app-config.js` en la respuesta sin modificarlo en disco. No registra URLs con tokens. Es solo para desarrollo: [`http.server` no es un servidor de producción](https://docs.python.org/3/library/http.server.html).

### Configuración pública y despliegue pendiente

`app-config.js` no debe contener secretos. `apiBaseUrl: null` deshabilita la API; una URL HTTPS indica el backend, sin `/api` al final; `''` habilita explícitamente `/api` del mismo origen. HTTP solo se acepta con frontend y API en loopback local. `invitationBaseUrl` permite indicar la URL pública de la tarjeta; `null` conserva la carpeta de `admin.html`, incluida la subruta de GitHub Pages. La configuración no se toma de parámetros de URL.

**Esta etapa no despliega el backend.** Pages sigue publicando solo archivos estáticos; antes de repartir enlaces reales falta elegir/configurar hosting HTTPS, disco persistente privado y backups, clave administrativa, CORS del origen exacto y logs sin tokens. Ver [backend/SECURITY.md](backend/SECURITY.md). La autenticación actual es una clave compartida del organizador y una sesión administrativa, no cuentas individuales ni MFA. El HTML del panel puede ser público; los datos y operaciones están protegidos por la API.

Panel y API deben alojarse en el mismo sitio (preferentemente mismo origen) para la cookie SameSiteStrict: no alcanza con habilitar CORS si el panel está en Pages y la API en otro dominio independiente. No se implementan cookies de terceros ni un fallback que persista la clave en el navegador. Referencia: [atributos de Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

### Acceso biométrico — solo propuesta

El usuario pidió evaluar, **no implementar**, passkeys/WebAuthn: primer ingreso con clave y posterior registro opcional de una credencial del dispositivo. El sistema operativo puede autorizar con huella, rostro o PIN; los datos biométricos no se entregan al backend. Antes de implementarlo se debe definir dominio HTTPS estable, registro/autenticación con desafíos de servidor y una recuperación de acceso si se pierde el dispositivo. No hay rutas, SDK ni claves de passkeys agregadas en esta etapa. Referencia: [WebAuthn y privacidad biométrica](https://www.w3.org/TR/webauthn-3/#sctn-biometric-authenticator-privacy).

### Pruebas sin build

```powershell
node --test tests/test_invitation_data.cjs tests/test_api_adapter.cjs tests/test_music_player.cjs tests/test_admin_panel.cjs
python -m unittest discover -s tests -p "test_*.py"
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
python tests/check_intro.py
python tests/check_admin_panel.py
python tests/check_connected.py --api-python .\backend\.venv\Scripts\python.exe
```

Las comprobaciones Playwright requieren Chromium instalado. `check_connected.py` inicia API/servidor local con base y credenciales temporales, prueba panel→enlace→confirmación→deseo→panel y detiene ambos al terminar. No toca una base real ni hace un despliegue.

## Música

Playlist local de tres canciones en `music-playlist.js`, en este orden:

1. [Piano de apertura](https://www.youtube.com/watch?v=e8jN1-HC-Vc): conserva el recorte inicial aprobado (~4:23,59).
2. [My One And Only Love](https://www.youtube.com/watch?v=lcoqOPaBe9M): ~3:02.
3. [UNDERSTAND](https://www.youtube.com/watch?v=6DcUnqZqTvI): ~2:30.

El reproductor queda **al pie del hero**, separado de la identidad principal y sin disco dorado lleno/glow protagonista. Título/posición quedan a un lado y los tres controles juntos en el orden **atrás · play/pausa · adelante**, cada uno con objetivo táctil44px. Está en flujo normal, no fijo ni superpuesto: en pantallas bajas el hero crece para evitar solapamientos.

Los controles usan `-webkit-tap-highlight-color: transparent` para evitar el rectángulo azul nativo al tocar en mobile ([referencia Safari](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/AdjustingtheTextSize/AdjustingtheTextSize.html)). El feedback táctil es cálido y tenue, con pulsación corta; se conserva el foco dorado de2px para teclado y no se deshabilita la selección de texto. Listeners pasivos de Pointer Events mantienen el estado de presión donde `:active` no es fiable, sin bloquear scroll ni clics: se limpia al soltar, cancelar, perder foco o ocultar página. Las pruebas incluyen emulación táctil (`is_mobile`/`has_touch`), pulsación sostenida/cancelación y navegación con Tab/Enter; no sustituyen revisar un teléfono físico.

`music-player.js` usa un único `<audio preload="none">`: no reproduce ni descarga música antes de tocar Ingresar; carga solo la pista seleccionada. Al terminar avanza, y la tercera vuelve a la primera. Anterior/siguiente conservan la pausa si la música estaba pausada. Los cambios rápidos cancelan fades anteriores e ignoran promesas obsoletas. Si falla una canción, muestra error y permite reintentar o elegir otra sin saltos automáticos infinitos.

Las pistas nuevas son MP3 a192kb/s y se ajustaron en dos pasadas a−17LUFS, tomando como referencia el piano original, con pico objetivo−1,5dBTP. El piano no fue modificado. La lista completa suma casi diez minutos/~14,3MB, pero no se precargan las tres pistas juntas. Los enlaces de origen no incluyen playlist/radio.

## Publicación sin build

En Settings → Pages, Source debe ser **GitHub Actions**. `.github/workflows/pages.yml` publica al pushear `main` o al ejecutarlo manualmente desde Actions. Solo corre sobre `main`, con permisos de lectura del código y escritura de Pages/OIDC; las acciones oficiales están fijadas a SHAs verificados.

`scripts/prepare_pages.py` copia una allowlist de14archivos (tarjeta, panel, configuración pública, scripts, dos imágenes y tres MP3) más `.nojekyll` a un directorio temporal nuevo. No compila, instala dependencias ni sirve el repositorio completo. **Backend, tests, docs, referencias, secretos y bases de datos no forman parte del artefacto web.** Las pruebas del empaquetado fallan si falta un recurso, si sale del proyecto o si se intenta reutilizar un destino existente; nunca eliminan contenido.

Antes de compartir, comprobar en Actions que el despliegue terminó correctamente, abrir la URL y probar música, botones y formularios. Para volver a una versión anterior: revertir el commit del cambio con `git revert <sha>` y pushear a `main`; el mismo workflow republica esa versión. Esto no despliega ni conecta la API.

## Backend

Ver `backend/README.md` y `backend/SECURITY.md` para API, configuración y límites de despliegue. Se ejecuta separado del frontend. La tarjeta puede conectarse mediante `app-config.js` y un enlace privado; la vista previa sin token sigue siendo local.

Las instrucciones de prueba completas están en «Pruebas sin build» más arriba. Las capturas se guardan en los directorios temporales `mia-intro-review`, `mia-admin-review` y `mia-connected-review`, fuera de `assets`.

Datos y decisiones vigentes: `EVENTO.md`. No se ejecuta build después de cambios, por instrucción del proyecto.
