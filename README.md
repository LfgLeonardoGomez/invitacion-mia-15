# Invitación de Mia

Prototipo visual móvil de una invitación de quince años. La portada, música, fondo y revelado por scroll siguen siendo independientes del backend.

Repositorio: [LfgLeonardoGomez/invitacion-mia-15-anios](https://github.com/LfgLeonardoGomez/invitacion-mia-15-anios), rama principal `main`. Vista previa en [GitHub Pages](https://lfgleonardogomez.github.io/invitacion-mia-15-anios/), disponible cuando finalice correctamente el workflow `Publicar invitación`.

## Vista previa y datos

Abrir `index.html` en el navegador. Los datos se editan por ahora en `invitation-data.js`, no en una API real. El objeto conserva los grupos `event`, `invitation` y `rsvp` del backend v1. `sections` y `wish` son extensiones de la vista previa: **todavía no tienen soporte en esa API**.

- Los datos del evento son los confirmados para Mia.
- **Familia Gomez / 3 lugares es el ejemplo de vista previa** solicitado, no una invitación real cargada en el backend. El saludo dice «En mi noche especial…» y «Reservamos 3 lugares para compartir este momento juntos».
- Asistentes se eligen con botones de selección única generados de **1 al cupo** recibido. Son radios nativos accesibles con teclado; no hay cantidad libre ni selección automática. El servidor sigue siendo quien valida el cupo real.
- **Los formularios siguen siendo locales:** guardan la selección/deseo únicamente en memoria de esa página; al recargar se pierden y **no se envían al organizador ni al backend**. Por pedido del usuario, los botones y mensajes ya no llevan rótulos «de prueba»: «Confirmar asistencia» y «Enviar mi deseo». Los agradecimientos no afirman entrega al servidor. Es una revisión visual, no un sistema de confirmaciones listo para invitados reales.
- Cuenta regresiva hasta la recepción: **26/12/2026 20:30, UTC−03:00**, independiente de la zona horaria del invitado. Se detiene en cero y muestra «¡Llegó el gran día!».
- Regalos/transferencias: botón «Ver datos bancarios» que abre un **modal de cristal violeta casi transparente**, con filete dorado, texto opaco/legible y blur12px. Usa un [`dialog` nativo](https://html.spec.whatwg.org/multipage/interactive-elements.html#the-dialog-element) fuera de las secciones animadas. Cierra con cruz/Escape o un toque que empieza fuera; no se cierra al arrastrar desde dentro. Mantiene inerte el fondo, bloquea su scroll y restaura el foco al botón. En pantallas bajas el contenido del modal tiene scroll propio.
- Los datos siguen siendo **ilustrativos**, alias «ALIAS A CONFIRMAR» y22ceros en CBU/CVU; `illustrative: true` muestra «No realizar transferencias» y deshabilita copiar. Reemplazar todos los valores por datos verificados y quitar ese flag al usar una cuenta real. Con `bankTransfer: null` se oculta el botón y vuelve el estado pendiente. No realiza pagos ni guarda información bancaria del invitado.
- Deseos: formulario de nombre (80 caracteres) y mensaje (600), con vista previa de texto segura. Se conserva solo el último deseo **de prueba en memoria**, sin muro público, envío ni persistencia real.
- `invitation-sections.js` maneja contador, datos de regalo y formulario de deseos sin modificar la intro aprobada ni realizar peticiones HTTP.
- Contacto: `sections.contact.whatsappNumber` configura el número internacional de la mamá, solo dígitos. Se usa un [enlace directo oficial de WhatsApp](https://faq.whatsapp.com/5913398998672934) con mensaje genérico, sin datos familiares ni token de invitación. El chat se abre al tocar el enlace; no se envía un mensaje automáticamente.
- Pie: usa **solo el castillo y parte de la colina de `assets/Reino de Linternas sobre el Lago.png`**, mediante un recorte visual CSS de425×480px desde(125,360), máscara SVG suavizada y fundido lateral/inferior. Se quitaron140px de la base anterior (620px), sin comprimir ni cortar las torres. El bote, el lago y los faroles grandes quedan fuera. Oscurecimiento `brightness(.68)`, saturación `.78` y opacidad `.92` conservan las ventanas cálidas. Ancho máximo380px, también acotado por la altura de pantalla: «¡Te espero!», Mia/fecha y castillo forman un único cierre que entra completo en el último viewport desde320×568, incluso en la prueba horizontal844×390. La imagen de entrada queda intacta; la silueta negra anterior se conserva sin uso.
- Farolitos locales ascienden desde detrás de las terrazas del nuevo encuadre, se pausan fuera de pantalla y quedan estáticos con movimiento reducido. Al entrar el castillo en pantalla se desvanece la capa de farolitos lejanos para evitar un origen visual desconectado.
- No hay claves administrativas en el frontend. La integración real con la API es un paso posterior: reemplazar el adaptador, no el diseño.
- No publicar referencias de Instagram, tests, `.env`, bases de datos ni todo el repositorio como sitio estático. Evitar `python -m http.server` desde la raíz: también expondría archivos del backend. Publicar solo archivos/recursos públicos seleccionados o un directorio de salida dedicado.

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

`scripts/prepare_pages.py` copia una allowlist de10archivos (HTML, cuatro JS, dos imágenes y tres MP3) más `.nojekyll` a un directorio temporal nuevo. No compila, instala dependencias ni sirve el repositorio completo. **Backend, tests, docs, referencias, secretos y bases de datos no forman parte del artefacto web.** Las pruebas del empaquetado fallan si falta un recurso, si sale del proyecto o si se intenta reutilizar un destino existente; nunca eliminan contenido.

Antes de compartir, comprobar en Actions que el despliegue terminó correctamente, abrir la URL y probar música, botones y formularios. Para volver a una versión anterior: revertir el commit del cambio con `git revert <sha>` y pushear a `main`; el mismo workflow republica esa versión. Esto no despliega ni conecta la API.

## Backend

Ver `backend/README.md` y `backend/SECURITY.md` para API, configuración y límites de despliegue. Se ejecuta separado del frontend; no está conectado a la tarjeta de vista previa todavía.

## Pruebas (sin build)

```powershell
node --test tests/test_invitation_data.cjs tests/test_music_player.cjs
python tests/check_intro.py
python -m unittest discover -s tests -p test_prepare_pages.py
python -m pytest backend/tests
```

El navegador de prueba requiere Python Playwright con Chromium instalado. Las capturas se guardan en el directorio temporal `mia-intro-review`, fuera de `assets`.

Datos y decisiones vigentes: `EVENTO.md`. No se ejecuta build después de cambios, por instrucción del proyecto.
