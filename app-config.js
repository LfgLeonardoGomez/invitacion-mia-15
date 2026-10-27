/* Configuración PÚBLICA: nunca poner claves ni tokens acá.
   null = API sin configurar (solo vista previa sin enlace privado).
   Producción: URL HTTPS del backend, sin /api al final.
   '' = mismo origen explícito cuando un proxy sirve frontend y API juntos.
   El servidor local genera este archivo sin modificarlo en disco. */
window.MIA_CONFIG = Object.freeze({
  apiBaseUrl: null,
  invitationBaseUrl: null,
});
