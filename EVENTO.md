# Referencia del evento

Registro de información suministrada por el usuario. No implica implementación ni aprobación de las ideas indicadas como propuestas.

## Datos confirmados

| Dato | Información |
|------|-------------|
| Celebración | Cumpleaños de 15 |
| Nombre de la cumpleañera | Mia |
| Temática | Rapunzel |
| Fecha | 26 de diciembre de 2026 |
| Llegada de invitados | 20:30 hs |
| Entrada de la cumpleañera al salón | 21:30 hs |
| Puntualidad | Pedir explícitamente a los invitados que sean puntuales |
| Salón | Jardin Secreto |
| Dirección | Teodoro Fels 7423, Trujui |
| Vestimenta | Elegante Sport |
| Transferencias | [Datos bancarios pendientes de informar] |

Solicitudes previas confirmadas: enlaces de invitación personalizados por familia, cupos por familia, confirmación de asistencia (RSVP) y visibilidad de esa información desde administración.

**Texto sugerido de puntualidad (borrador, no aprobado):**

> Te esperamos a las 20:30 hs. La entrada de la cumpleañera al salón será a las 21:30 hs. Por favor, sé puntual para compartir ese momento.

## Recursos visuales verificados

Archivos existentes en `assets/`, inspeccionados visualmente:

| Recurso | Contenido y uso solicitado |
|---------|---------------------------|
| `assets/Reino de Linternas sobre el Lago.png` | Escena general luminosa con lago, castillo y bote vacío. Imagen inicial intacta; el pie reutiliza solo el sector del castillo mediante recorte visual CSS/SVG. |
| `assets/Linternas doradas sobre un reino de ensueño.png` | Alternativa de primer plano; no se utiliza en la transición actual aprobada. |
| `assets/2026-10-26 14-07-25.mp4` | Referencia extendida de 61,87 s con secciones e interacciones; reemplaza el video anterior eliminado por el usuario. |

La transición actual aprobada por el usuario usa solo la imagen general con acercamiento y brillo cálido continuo. La imagen cercana queda como alternativa si hiciera falta más detalle. Son imágenes distintas, no recortes de cámara exactamente coincidentes.

## Referencia visual aprobada por la cumpleañera

El usuario confirma que a la cumpleañera le gustaron especialmente el tono violeta, los dorados y los contenedores de la referencia de `assets/capturas video/`. Tomar estos rasgos como guía visual y adaptarlos al contenido de este evento; no copiar textos ni elementos propios de la invitación de Rapunzel de la referencia.

- **Fondo animado:** farolitos encendidos que ascienden lentamente por detrás del contenido. Esta descripción del movimiento fue confirmada por el usuario; las capturas por sí solas son estáticas.
- **Paleta aproximada extraída de las capturas comprimidas** (valores de referencia, no colores originales garantizados): fondo violeta noche `#170F2E` (RGB 23, 15, 46); superficie de contenedor `#291647` (RGB 41, 22, 71); violeta luminoso de bordes/detalles `#3C2377` (RGB 60, 35, 119); dorado medio `#C59C68` (RGB 197, 156, 104); brillo dorado `#F4A844` (RGB 244, 168, 68).
- **Contenedores:** tarjetas verticales apiladas, redondeadas, en violeta más claro que el fondo, con filetes/bordes finos dobles en violeta y dorado.
- **Detalles:** divisores pequeños con destello/rombo; botones en forma de cápsula; partículas luminosas discretas; texto principal dorado con buena jerarquía.
- **Referencia de estructura visual:** portada, mensaje/cita, fecha y horario, ubicación con acción de Maps, accesos de calendario y cuenta regresiva. Esto describe la referencia, no confirma que todas esas secciones estén definidas para nuestro contenido.

La captura es de baja resolución; los HEX son estimaciones tomadas de los píxeles visibles y deben ajustarse visualmente al implementarlos.

### Referencia extendida, no requisitos aprobados

El video nuevo se revisó por fotogramas y muestra: galería ampliable, calendario, cuenta regresiva, itinerario, vestimenta, álbum/playlist, formulario RSVP con acompañantes/restricciones alimentarias, deseos y copiar alias. Registrar como referencia para conversar más adelante; no importar contenido/horarios/alias/colores reservados de esa fiesta ni implementar automáticamente esas secciones para Mia.

## Revisión del primer prototipo visual de Stitch

El HTML compartido por el usuario es una referencia generada por Stitch, no código aprobado para implementar. El usuario lo ve como un acercamiento útil, pero pide más delicadeza y más contraste de luces/sombras; la tipografía y las imágenes decorativas deben revisarse.

- **Profundidad e iluminación:** aunque el prototipo ya usa gradientes, sombras y brillos, repite casi el mismo tratamiento violeta/dorado en todas las tarjetas, diamantes y textos. Para la próxima propuesta, variar jerarquía y luminosidad: halo cálido localizado alrededor de los farolitos, contenedores con planos/bordes menos uniformes, sombras profundas y dorado reservado para puntos focales.
- **Tarjetas:** conservar el lenguaje de contenedores redondeados con filetes dobles, pero evitar que todas tengan idéntica silueta arqueada e intensidad; diferenciar portada, datos clave y secciones secundarias con sutileza.
- **Tipografía:** el prototipo mezcla Great Vibes, Playfair Display, Cinzel y Montserrat. No hay elección final; comparar pocas combinaciones contra las capturas y revisar legibilidad con el nombre real cuando se informe.
- **Recursos gráficos:** la tiara actual es un SVG geométrico inline y la flor también es un SVG; evaluar imágenes/ilustraciones más delicadas y coherentes con la iluminación, preferentemente con fondo transparente y sin aspecto de sticker pegado. Buscar recursos propios inspirados en farolitos/sol/tiara, no copiar personajes ni logos.
- **Entrada/audio observados en el HTML:** el botón actual solo oculta la portada y muestra el contenido; no ejecuta el zoom acordado ni inicia audio. El reproductor solo cambia su apariencia, no incluye una fuente de audio. Son elementos de mockup, no funcionalidad implementada.
- **Contenido que no debe heredarse del prototipo:** “Francesca” aparece hardcodeado en enlaces/textos de calendario y archivo ICS, pero la cumpleañera se llama Mia. El horario de finalización usado en esos ejemplos tampoco está confirmado. No copiar esos valores al contenido final.
- El fondo principal del HTML apunta a una URL remota; al preparar el diseño propio debe usarse la imagen aprobada del repositorio como referencia visual.
- **Segunda propuesta de Stitch:** suma comparación tipográfica y una tiara más detallada, pero sigue tratando las secciones con una tarjeta casi idéntica y mantiene iluminación/glow muy repartidos. El estado de transición usa otra imagen remota con zoom, no el mismo recurso inicial; el audio sigue siendo solo una representación visual y el storyboard necesita clics manuales entre estados. No equivale a la animación/sonido real acordados.
- **Recomendación para el flujo de trabajo:** no pedir más iteraciones de prompt a Stitch por ahora. Usar sus propuestas como referencia de estructura y trabajar nosotros la dirección visual; comparar fuentes y recursos gráficos aparte. La implementación queda para cuando el usuario la habilite.

## Dirección visual propia — v1 aprobada para probar y ajustar

- **Iluminación:** mantener el violeta noche como campo dominante. Usar viñeta/sombras violetas en bordes y base; iluminar el centro con gradiente violeta más claro; reservar la luz ámbar intensa para los farolitos y un brillo final de entrada. Evitar glow uniforme en cada texto, borde y control.
- **Profundidad de tarjetas:** después de revisar el video completo por fotogramas y las capturas, usar arcos superiores amplios, radios inferiores pequeños, filetes dobles tenues y rellenos violetas semitransparentes (no paneles opacos). Los farolitos deben iluminar el fondo y percibirse suavemente detrás de las tarjetas. Los rombos superiores llevan halo difuso tenue y relleno dorado suave.
- **Hero sin contenedor:** la tiara, Mia y los datos iniciales van directamente sobre el fondo. Tras ~200ms de fondo vacío, tiara en fade-in de1100ms, nombre y datos escalonados. Mantener tamaño de tiara; Mia usa `clamp(94px, 27vw, 124px)` sin deformar letras y corrección óptica hacia izquierda de `.055em` (~5–7px). Fecha con separadores: **26 · Diciembre · 2026**. MisXV y fecha más atenuados para jerarquía secundaria; fecha peso400. **Reproductor al pie del hero**, por pedido posterior del usuario para no ser protagonista: identidad centrada en espacio disponible y grupo inferior con música/Deslizá, separados al menos52px, padding inferior24px y flujo normal. Cápsula dehasta300px con filete tenue, sin glow ni disco dorado sólido, controles44px. Esta ubicación reemplaza la separación anterior de38px bajo fecha. En pantallas bajas el hero crece, no superpone controles.
- **Revelado por scroll:** las secciones permanecen en flujo normal y aparecen una sola vez al entrar al viewport con `IntersectionObserver`, no por temporizador global ni fijadas a pantalla. Aparición más suave de1200ms (antes720), subida de8px y nitidez gradual con blur de1.4px a0 solo en textos/contenido pequeño, no en fondos/bordes de tarjetas. Con movimiento reducido o sin soporte del observador, se muestran sin desplazamiento ni demoras adicionales.
- **Tipografía candidata:** probar **Pinyon Script** solo para “Mia”; **Cormorant Garamond** para títulos, fecha y texto emotivo; **Montserrat** para etiquetas y controles. Sacar Cinzel de la jerarquía principal para reducir el efecto rígido/medieval y no acumular cuatro familias. Es una dirección tipográfica recomendada, pendiente de validación visual con la cumpleañera.
- **Farolitos:** que la imagen aprobada sea el foco del movimiento. Si se agregan farolitos flotantes, usar siluetas reconocibles, tamaños y desenfoques variados, brillo local suave y movimiento lento; evitar bloques cuadrados luminosos genéricos y no duplicar visualmente los farolitos de la foto.
- **Luz según tamaño:** los farolitos grandes del fondo tienen halo más amplio e intenso, papel/llama más luminosos; los pequeños quedan más tenues para profundidad. Derivado automáticamente de `--size` en CSS, sin alterar velocidades ni la intro aprobada: halo de104px/alpha.08 para8px de ancho a195px/alpha.234 para15px.
- **Tiara/ornamento:** imagen elegida por el usuario: `assets/Tiara Real de Oro y Gemas Facetadas.png` (1448 × 1086 px, RGBA, transparencia confirmada). Integrarla sobre “Mia” con escala contenida y luz/sombra acorde con la escena; no tratarla como sticker.

## Pendientes

- Datos bancarios reales: se suministrarán más adelante. Para revisión visual, el usuario pidió desplegable con datos ilustrativos; no habilitar transferencias ni copiarlos hasta reemplazarlos por datos verificados.
- Aprobar o ajustar el borrador de puntualidad y los ajustes finos de hero/secciones.
- **Portada inicial corregida por el usuario:** solo fondo y texto **“Ingresar”** directo sobre la imagen, con filigranas arriba/abajo y sin caja/fondo/borde de botón. Sigue siendo un botón semántico accesible con área táctil generosa. `assets/adornos.png` es una lámina con marcas de agua: se usó como referencia para una filigrana SVG propia, no se quitaron marcas. Sin nombre, tiara, frases, etiquetas ni instrucciones adicionales.
- **Transición aprobada:** acercamiento continuo sobre la misma imagen hacia los dos farolitos principales y brillo que los sigue. Conservar Ingresar con filigranas y la transición suave que el usuario aprobó.
- **Implementación de la intro:** el usuario aprobó el zoom/brillo continuo. Imagen y dos halos comparten coordenadas y transformación; cámara calculada según recorte de pantalla, sin desplazamientos rígidos en vw/vh. Una única línea de tiempo de **3,5 s**, zoom final **1,9×**, brillo creciente y revelado solapado del fondo vacío mientras la cámara aún se mueve; después aparecen los componentes del hero.
- **Música elegida:** playlist de3canciones aprobada por el usuario. Primera: piano `https://www.youtube.com/watch?v=e8jN1-HC-Vc`, `assets/mia-soundtrack.mp3` (192kb/s), conserva **9,462875s de silencio inicial recortados**, duración~4:23,59. Segunda: **My One And Only Love**, `https://www.youtube.com/watch?v=lcoqOPaBe9M`, `assets/mia-my-one-and-only-love.mp3` (~3:02). Tercera: **UNDERSTAND**, `https://www.youtube.com/watch?v=6DcUnqZqTvI`, `assets/mia-understand.mp3` (~2:30). Solo videos individuales, sin radio/list. Fuentes nuevas convertidas aMP3 192kb/s y loudnorm dos pasadas a−17LUFS/TP−1,5/LRA14 para aproximar sonoridad al piano original sin modificarlo. Total casi10min/~14,3MB.
- **Reproducción:** empieza únicamente al pulsar Ingresar con volumen gradual. Reproductor discreto al pie del hero, título/posición1de3, anterior/siguiente y play/pausa. Un solo audio, preloadnone y solo pista seleccionada; autoavance al terminar y retorno3→1. Navegar en pausa mantiene pausa. Controlador protege fades/promesas frente a clics rápidos; error recuperable sin bucle automático. Config `music-playlist.js` y lógica `music-player.js`. La URL antigua `Cz_ZY6WCGKE` sigue descartada.
- **Evaluación de calidad de la imagen inicial:** ambas imágenes son verticales de `941 × 1672 px` (aprox. 9:16). La imagen amplia tiene los dos farolitos principales bien definidos y puede servir para un zoom en celular. Manteniendo la proporción, el zoom no los deforma geométricamente; lo que puede perderse al ampliar es nitidez/detalle. Como prueba inicial, limitar el acercamiento a aprox. `1,8–2×` y culminar con el brillo cálido podría hacer innecesaria la segunda imagen. La imagen cercana queda como alternativa si se busca más detalle de los farolitos, con el costo de que el cambio de composición puede sentirse como un salto. Recomendación por validar en un celular real; no es una decisión cerrada.
- **Cambio posterior solicitado:** mostrar el botón de datos bancarios con valores ilustrativos durante la revisión visual. Dentro del desplegable se aclara que no se deben realizar transferencias.

El usuario aprobó la base visual y la intro actuales. Continuar incrementalmente con los ajustes solicitados de hero/reproductor/revelado por scroll; no agregar automáticamente secciones del video nuevo. Prototipo local `index.html`, comprobaciones `tests/check_intro.py`; no ejecutar build.

## Secciones reales y datos de vista previa — primera implementación

Por pedido del usuario se continúa con datos hardcodeados que representan la futura respuesta de la API. `invitation-data.js` concentra el contrato `event`, `invitation` y `rsvp`; no realiza solicitudes HTTP. Los datos de Mia son los confirmados arriba. **Familia Gomez / 3 lugares es el ejemplo de vista previa** solicitado, no una invitación cargada en el backend.

Composición actual, conservando intro y hero aprobados:

1. Hero sin contenedor: tiara, Mia, fecha y reproductor.
2. Saludo familiar y cupos directamente sobre el fondo: «En mi noche especial…», «Familia Gomez», «Reservamos 3 lugares para compartir este momento juntos». Nombre/cupo siguen viniendo del payload, no quedan incrustados en la lógica.
3. Cuenta regresiva libre, sin cuatro tarjetas repetidas, hasta el **26 de diciembre de 2026 a las 20:30 hs, UTC−03:00**. Usa la hora del evento, no la del dispositivo. Al llegar a cero muestra «¡Llegó el gran día!» sin números negativos.
4. Una tarjeta de celebración que reúne salón, dirección, recepción, entrada de Mia, puntualidad y ubicación.
5. Vestimenta sin tarjeta, acompañada por una ilustración vectorial propia y discreta.
6. Tarjeta RSVP con respuesta sí/no y botones de cantidad **1..cupo** generados desde el payload (ejemplo:4reservas→1,2,3,4). Radios nativos accesibles, sin input numérico libre; al asistir exige elegir cantidad y al no asistir guarda0. Restaura la última respuesta válida. Esto reduce errores de interfaz, pero no sustituye la validación de cupo en servidor.
7. Regalos/transferencias libre con botón «Ver datos bancarios». **Por pedido posterior del usuario, abre modal casi transparente en vez de desplegar contenido en la página.** `dialog` nativo fuera de reveal-item, cristal violeta con alfa.18–.28, blur12px, bordeoro tenue y texto legible sin bajar opacidad. Entrada200ms opacidad/8px, respeta reducedmotion; cierrecruz/Escape/toqueafuera, no al arrastrar desde dentro; foco restituido y scroll de fondo bloqueado mientras abre. Tiene scroll interno para pantallas bajas. Mantiene `illustrative: true`, titular «Mia · XV años», banco ilustrativo, alias «ALIAS A CONFIRMAR» y22ceros. Aviso «Datos ilustrativos. No realizar transferencias» y copiar deshabilitado hasta tener datos reales; no se ejecutan pagos. Con datos reales sin ese flag, copiar/fallback manual; con `null`, cierra modal/oculta botón y muestra estado pendiente.
8. Deseos libre, nombre (hasta80caracteres), mensaje (hasta600) y vista del último deseo, siempre texto seguro. Como el RSVP, sigue **solo en memoria**, sin envío ni muro público y se pierde al recargar. Por pedido del usuario, se retiraron los rótulos «de prueba»: botones «Confirmar asistencia» / «Enviar mi deseo», agradecimiento y selección sin afirmar entrega al servidor.
9. Contacto libre para escribir por WhatsApp a la mamá de Mia. Subtítulo «Comunicate con mi mamá» y botón «Escribir por Whatsapp». Número suministrado por el usuario, normalizado en `sections.contact.whatsappNumber`; mensaje genérico sin datos familiares/token, sin envío automático ni verificación de que el número tenga cuenta activa.
10. Cierre «¡Te espero!», Mia/fecha y **castillo de la portada al pie**, agrupados como una sola composición. El usuario aprobó la foto pero pidió recortar la base porque el último viewport mostraba solo el castillo. Recurso original `assets/Reino de Linternas sobre el Lago.png` (941×1672), intacto: ventana de(125,360) a(550,840), **425×480px**; se retiraron140px de la villa/colina inferior respecto de los620px anteriores, sin aplastar torres. La máscara conserva el contorno original con factor vertical620/480 y un nuevo fundido inferior, además del lateral. Sin bote, lago ni faroles grandes. Oscurecimiento `brightness(.68)`, `saturate(.78)` y opacidad `.92` se mantienen.
11. `invitation-closing` agrupa texto/fecha/escena en flujo normal. Separación del texto a fecha14px, escena12px y cielo vacío32px (antes80). Ancho máximo380px, además limitado por altura de viewport reservando180px para el cierre: comprobado que los tres elementos quedan juntos al final en320×568,360×640,390×844,430×932,844×390 y1440×900. No se modifica la portada/transición ni la imagen original.
12. Ocho farolitos locales nacen detrás de las mismas terrazas (posición recalculada a18% de la nueva altura desde la base; antes36%), con ascenso lento, deriva y halo según tamaño. Capa ambiente lejana se desvanece al entrar el castillo en pantalla para no percibir un segundo punto de lanzamiento. Animación local pausada fuera de pantalla; composición estática con movimiento reducido. `assets/Ciudadela fantástica en la colina.png` (silueta negra anterior) se conserva sin uso; tampoco se usa `assets/castillo.jpg` (imagen diurna).

El formulario permite revisar los estados, pero **solo guarda en memoria de esa página y pierde la respuesta al recargar**. Los rótulos de prueba se retiraron para la revisión visual; esto no conecta la API ni vuelve reales las confirmaciones. La respuesta local describe la selección («Elegiste asistir…») sin decir que fue enviada. No compartir como sistema definitivo para invitados hasta integrar backend.

El usuario aprobó agregar **cuenta regresiva, regalos/transferencias y deseos**. `sections` y `wish` amplían únicamente el mock de `invitation-data.js`; `invitation-sections.js` implementa su interacción. Backend v1 aún no soporta configurar esos campos ni guardar deseos. No confundir esta aprobación con habilitar todos los extras del video.

### Reproductor y publicación para revisión

Los tres controles se agrupan contiguos en el orden atrás · play/pausa · adelante (`music-transport`), con título/estado/posición separados a un lado y targets44px. Se conserva ubicación discreta al pie del hero.

Se elimina el resaltado táctil azul nativo con `-webkit-tap-highlight-color: transparent` en botones, enlaces, summary, labels y campos. Causa verificada en Chromium móvil: color por defecto `rgba(51,181,229,.4)` sin `:focus-visible`. Música/cierre de modal responden con ámbar tenue al presionar y RSVP con escala mínima, en160ms y respetando movimiento reducido. Listeners Pointer Events pasivos agregan `is-touch-pressed` solo para touch/pen y lo limpian en up/cancel/blur/hidden, sin preventDefault ni bloqueo de scroll; evita depender solo de `:active`, que no se activó durante el hold táctil emulado al quitar el overlay nativo. **No** se elimina `outline` globalmente: permanece foco dorado de2px para teclado, y los campos conservan selección/edición normal. Verificación emulada, no garantía de prueba en dispositivo físico.

El usuario habilitó Pages con Source GitHub Actions. `.github/workflows/pages.yml` usa una sola tarea sin build: prueba y ejecuta `scripts/prepare_pages.py`, copia únicamente la allowlist pública más `.nojekyll` a un directorio temporal nuevo y despliega ese artefacto, nunca la raíz del repo. Incluye la tarjeta, configuración pública y el HTML/CSS/JS del panel; ningún secreto ni dato familiar se incorpora al artefacto. Solo `main` puede publicar. Backend, bases/env, docs, tests y referencias no se sirven. Pages por sí solo no despliega la API.

## Backend y panel — integración local con sesión persistente

El usuario autorizó trabajar en paralelo con dos agentes para armar un backend simple y seguro. Se eligió **FastAPI + SQLite mediante `sqlite3`**, para un único evento y un único proceso API; evitar complejidad de cuentas, ORM y servicios distribuidos por ahora. Escalar a múltiples instancias requerirá revisar almacenamiento y rate limiting compartido.

- API de evento, invitaciones familiares, cupos y RSVP persistentes; contrato JSON camelCase con `sections` y `wish`. Configuración de contacto/banco/zona horaria guardada en SQLite por GET/PUT admin de secciones.
- Panel `admin.html`, responsive violeta/dorado, para cargar/editar familias/cupos, ver estados, buscar/paginar, activar/desactivar y copiar o regenerar enlaces. Familias y deseos se buscan automáticamente tras una pausa de280ms, con cancelación/versionado de respuestas obsoletas. La clave administrativa se usa una sola vez para crear sesión opaca HttpOnly/SameSiteStrict de12horas (Secure fuera del loopback local), restaurable al recargar; no se guarda la clave en storage. Las escrituras con cookie exigen origen permitido y CSRF. Logout revoca sesión y limpia DOM; si falla la red se guarda solo una marca booleana de cierre pendiente, sin credenciales, para no restaurar silenciosamente. No hay cuentas individuales ni MFA.
- Links familiares con tokens aleatorios: hash para acceso público y, desde esquema4, token cifrado Fernet en envelope ligado a la familia para recuperación administrativa. Clave independiente `MIA_LINK_ENCRYPTION_KEY`, privada y respaldada fuera de SQLite; sin clave no crear/rotar/recuperar. El usuario aprobó recuperar y copiar sin mostrar URL: cardabierta «Copiar enlace» hace GETadmin/id/link y escribe portapapeles desde variable efímera, nunca DOM/storage; si copiar falla, error sin fallback visible. Crear/rotar no muestran modal de URL. «Regenerar enlace» requiere advertencia e invalida el anterior sin borrar RSVP/deseos. Legacyhash-only devuelve409, conserva su URL vieja y no se regenera automáticamente. Poseer un link permite acceder a esa familia: no verifica identidad personal. No prometer invisibilidad ante herramientas de red/portapapeles OS.
- Cupos validados bajo transacción en el servidor, consultas parametrizadas, tipos/campos estrictos, respuestas públicas acotadas, CORS explícito, límite de cuerpo y rate limiting básico en memoria.
- Documentación interactiva desactivada por defecto. Telemetría automática desactivada y arranque documentado sin access logs para no registrar tokens; el proxy/hosting también necesita redacción.
- Las pruebas automáticas utilizan bases temporales. Por pedido posterior del usuario se dejó API8000/panel5173 funcionando localmente con `backend/.env` y SQLite privados/ignorados por Git; la base manual puede contener sus pruebas y se preserva al reiniciar. Antes de migrarla se hace backup consistente con SQLite, fuera del directorio público.
- Antes de publicar: configurar clave privada, HTTPS, permisos/backups de base y proxy; nunca servir la raíz completa del repositorio como sitio estático. Ver `backend/README.md` y `backend/SECURITY.md`.

- Deseos privados: varios mensajes por familia, autor80/mensaje600, máximo10porinvitación por pedido posterior del usuario y10envíos/minuto por IP como protección independiente; UUID de solicitud evita duplicados al reintentar una respuesta incierta. La 11ª solicitud nueva devuelve409concodewish_limit_reached ycap10; errorvisibleconservadraft, nocelebraéxito. Históricosmayoresa10noseborran, reintentoUUIDyaaceptadosigueválido, rotaciónlinknoreiniciacupo. El invitado recibe solo su último deseo; administración ve el historial con búsqueda/paginación. No hay muro público ni envío automático por WhatsApp.
- El límite inicial50se redujo a10por pedido explícito posterior. Tras guardar se limpian autor/mensaje/contador, no ante error. Confirmación y deseo tienen una lámpara dorada grande que asciende con aviso destacado durante5,2s, solo tras éxito real. Asistencia sí: «Gracias por confirmar, te esperamos»; no: «Gracias por avisarnos 💛»; deseo: «Mia ya recibió tu mensaje 💕». Vista previa no afirma envío; errores no celebran. Resultado inline persistente, único anuncio accesible, sin bloqueo/foco/sonido y sin ascenso con movimiento reducido.
- Resumen: familias confirmadas/no asisten/pendientes, personas confirmadas y lugares reservados cuentan invitaciones activas; totales generales incluyen inactivas. Una sola respuesta RSVP editable por familia, sin nómina individual. La baja de cupo incompatible devuelve409 y no modifica datos.
- Listado de familias son cards arqueadas/doble filete/rombo suave, doscolumnas desktop y una móvil. Tras reporte de reflow brusco se reemplazó details expansivo por article con dos caras en la misma huella estable de320px: frente nombre/cupo/estado, detrás acciones2x2+Cerrar/avisos internos. Giro3D420ms, sin mover grid ni scroll; teclado/reducedmotion sin giro. Nombres con iniciales may?sculas solo en presentaci?n, datos centrados y reverso con padding dentro de sus bordes. Vista inicial Activas y pesta?a Desactivadas para consultar/reactivar sin borrar RSVP ni deseos. Botón aria-expanded/control, panel inactivo inert/aria-hidden, una cara abierta, Escape/afuera/Cerrar restauran foco sin scroll; cerrar invalida copias pendientes y abrir diálogos cierra cara sin perder retorno de foco. Se conservan búsqueda/filtros/paginación20 y sesión. La tarjeta «Familias activas» agrega personas invitadas desde reservedSeats, separadas de confirmedGuests.
- Por devolución del usuario se suavizó el popup: easing global lineal y curva suave por tramo; entrada1000ms/lectura3200/salida1000(total5200), sin compresión global del ingreso. Reducedmotion fade360ms por extremo sin ascenso. No modificar intro/hero/música.
- Migración aditiva versionada para preservar bases existentes, evento y confirmaciones. Nuevas bases usan Elegante Sport; bases anteriores requieren actualización explícita del evento, sin pisar cambios administrativos.
- Esquema3 agrega sesiones administrativas hashadas y acotadas, expiración fija12h y revocación por cierre/rotación de clave. Consultas admin120/min, escrituras/login/restore30/min; mantiene Bearer para herramientas privadas y bootstrap. No confundir cookie de sesión con guardar la clave maestra.
- `app-config.js` solo contiene direcciones públicas: `apiBaseUrl:null` sin API, URL HTTPS o `''` para mismo origen explícito; HTTP solamente loopback local. Enlaces privados obligan modo API sin fallback a Familia Gomez. Sin token continúa la vista previa local; con API configurada muestra un aviso discreto de vista previa sin envíos.
- Token en URL conservado para recargar/compartir, con referrer-policy no-referrer, sin guardarlo en storage ni registrarlo. El panel construye enlaces conservando subruta de Pages, no concatenando la ruta devuelta por API con el origin.
- `scripts/serve_frontend.py` sirve solo la allowlist en127.0.0.1, genera configuración local y no registra URLs; no es hosting productivo. Pruebas conectadas usan servicios/base/credenciales temporales, no familias reales.

La conexión y el panel están implementados para configuración/prueba local. Siguen pendientes elegir y desplegar hosting API con HTTPS/disco privado/backups, configurar URL pública y CORS, entregar la clave de administración por canal privado y cargar familias reales. Panel y API necesitan mismo sitio para cookieStrict (preferentemente mismo origen; en local ambos127.0.0.1, no mezclar localhost). Los datos bancarios siguen siendo ilustrativos. Los párrafos anteriores sobre formularios solo en memoria describen la etapa visual y siguen aplicando exclusivamente al modo vista previa sin token. No se aprobó soporte multievento, SaaS ni constructor arbitrario de páginas. No hay integración bancaria. Calendario, galerías y demás extras del video no solicitados siguen siendo referencias, no requisitos aprobados; la playlist de3pistas no implica un formulario de canciones sugeridas.

**Biometría: solo consulta, NO implementar todavía.** Es viable ofrecer registro opcional de passkey/WebAuthn después del primer acceso con clave; el dispositivo autoriza con huella/rostro/PIN según capacidades y el servidor no recibe biometría. Requiere dominio HTTPS estable, desafíos verificados en backend y recuperación de acceso. Queda para una etapa posterior explícitamente autorizada.
