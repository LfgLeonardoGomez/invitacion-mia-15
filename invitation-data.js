/* Enlaces privados usan la API. Sin enlace, la vista previa no envía datos. */
(() => {
  const payload = {
    event: {
      name: 'Mia',
      date: '2026-12-26',
      arrivalTime: '20:30',
      entranceTime: '21:30',
      venueName: 'Jardín Secreto',
      venueAddress: 'Teodoro Fels 7423, Trujui',
      dressCode: 'Elegante Sport',
    },
    // Datos de una familia ficticia para diseñar los estados de la invitación.
    invitation: { id: 'preview-family', familyName: 'Familia Gomez', seats: 3 },
    rsvp: null,
    sections: {
      eventUtcOffset: '-03:00',
      // Solo para revisar el diseño: sustituir y retirar illustrative al tener datos reales.
      bankTransfer: {
        holder: 'Mia · XV años',
        bank: 'Banco ilustrativo',
        alias: 'ALIAS A CONFIRMAR',
        accountNumber: '0000000000000000000000',
        illustrative: true,
      },
      contact: { whatsappNumber: '5491141675124' },
    },
    wish: null,
  };

  const location = window.location;
  const params = location?.href ? new URL(location.href).searchParams : null;
  const privateLink = params?.has('invitation') === true;
  const token = privateLink ? params.get('invitation') : null;
  const mode = privateLink ? 'api' : 'mock';
  let currentPayload;
  let pendingWish;
  let wishInFlight = false;

  class InvitationError extends Error {
    constructor(message, status = 0) {
      super(message);
      this.name = 'InvitationError';
      this.status = status;
    }
  }

  const text = (value, max) => typeof value === 'string' && value.trim().length > 0 && value.length <= max;
  const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
  const badResponse = () => new InvitationError('La invitación recibida no es válida. Intentá nuevamente.');
  const timestamp = (value) => typeof value === 'string' && value.length <= 64 && Number.isFinite(Date.parse(value));
  function validRsvp(value, seats) {
    return object(value) && typeof value.attending === 'boolean' && Number.isInteger(value.guestCount)
      && value.guestCount >= (value.attending ? 1 : 0) && value.guestCount <= seats
      && (value.attending || value.guestCount === 0) && timestamp(value.updatedAt);
  }
  function validWish(value) {
    return object(value) && text(value.id, 80) && text(value.author, 80) && text(value.message, 600)
      && timestamp(value.createdAt) && timestamp(value.updatedAt);
  }
  function validatePayload(data) {
    if (!object(data) || !object(data.event) || !object(data.invitation) || !object(data.sections)) throw badResponse();
    const { event, invitation: family, sections } = data;
    const lengths = { name: 80, venueName: 160, venueAddress: 300, dressCode: 100 };
    if (Object.entries(lengths).some(([key, max]) => !text(event[key], max))) throw badResponse();
    if (typeof event.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(event.date)
      || !Number.isFinite(Date.parse(`${event.date}T00:00:00Z`))
      || new Date(`${event.date}T00:00:00Z`).toISOString().slice(0, 10) !== event.date) throw badResponse();
    if (['arrivalTime', 'entranceTime'].some((key) => typeof event[key] !== 'string' || !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(event[key]))
      || event.entranceTime < event.arrivalTime) throw badResponse();
    if (!text(family.id, 80) || !text(family.familyName, 120) || !Number.isInteger(family.seats) || family.seats < 1 || family.seats > 50) throw badResponse();
    if (data.rsvp !== null && !validRsvp(data.rsvp, family.seats)) throw badResponse();
    if (typeof sections.eventUtcOffset !== 'string' || !/^[+-](?:0\d|1[0-4]):[0-5]\d$/.test(sections.eventUtcOffset)
      || !Number.isFinite(Date.parse(`${event.date}T${event.arrivalTime}:00${sections.eventUtcOffset}`))) throw badResponse();
    if (sections.contact !== null && (!object(sections.contact) || typeof sections.contact.whatsappNumber !== 'string'
      || (sections.contact.whatsappNumber !== '' && !/^[1-9]\d{7,14}$/.test(sections.contact.whatsappNumber)))) throw badResponse();
    const bank = sections.bankTransfer;
    if (bank !== null && (!object(bank) || typeof bank.illustrative !== 'boolean'
      || ['holder', 'bank', 'alias', 'accountNumber'].some((key) => typeof bank[key] !== 'string' || bank[key].length > 200)
      || (!bank.alias.trim() && !bank.accountNumber.trim()))) throw badResponse();
    if (data.wish !== null && !validWish(data.wish)) throw badResponse();
    return data;
  }

  function apiBase() {
    const configured = window.MIA_CONFIG?.apiBaseUrl;
    if (typeof configured !== 'string') throw new InvitationError('Esta invitación todavía no está disponible. Consultá con la familia de Mia.');
    const loopback = (hostname) => ['localhost', '127.0.0.1', '[::1]'].includes(hostname);
    const localPage = location.protocol === 'http:' && loopback(location.hostname);
    if (!(location.protocol === 'https:' || localPage) || /[\s\u0000-\u001f\u007f\\]/.test(configured)) {
      throw new InvitationError('La conexión con la invitación no está configurada de forma segura.');
    }
    let url;
    try { url = new URL(configured || location.origin, location.href); } catch { throw new InvitationError('No se pudo conectar con la invitación. Consultá con la familia de Mia.'); }
    if (url.username || url.password || url.search || url.hash || (configured !== '' && !/^https?:\/\//i.test(configured))
      || !(url.protocol === 'https:' || (url.protocol === 'http:' && loopback(url.hostname) && localPage))) {
      throw new InvitationError('La conexión con la invitación no está configurada de forma segura.');
    }
    return url.href.replace(/\/+$/, '');
  }

  function errorForStatus(status) {
    const messages = {
      404: 'El enlace no está disponible o fue reemplazado. Pedile un nuevo enlace a la familia de Mia.',
      409: 'No pudimos guardar este cambio. Revisá los datos e intentá nuevamente.',
      422: 'Revisá tu selección: la cantidad debe estar dentro de los lugares reservados.',
      429: 'Hubo varios intentos seguidos. Esperá un minuto antes de volver a intentar.',
      503: 'El servicio no está disponible por un momento. Intentá nuevamente más tarde.',
    };
    return new InvitationError(messages[status] || 'No pudimos completar la solicitud. Intentá nuevamente más tarde.', status);
  }

  async function request(suffix = '', body, method = 'GET') {
    if (!/^[A-Za-z0-9_-]{43}$/.test(token || '') || params.getAll('invitation').length !== 1) {
      throw new InvitationError('El enlace de invitación no es válido. Pedile uno nuevo a la familia de Mia.', 404);
    }
    const url = `${apiBase()}/api/invitations/${encodeURIComponent(token)}${suffix}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(url, {
        method, signal: controller.signal, credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer', redirect: 'error',
        headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      if (!response.ok || !(response.headers.get('content-type') || '').toLowerCase().includes('application/json')) {
        // Only this allow-listed error code is interpreted; never reflect server detail text.
        if (response.status === 409 && suffix === '/wishes'
          && (response.headers.get('content-type') || '').toLowerCase().includes('application/json')) {
          let issue;
          try { issue = await response.json(); } catch { /* Keep the generic safe error. */ }
          if (issue?.code === 'wish_limit_reached' && Number.isInteger(issue.maxWishes) && issue.maxWishes > 0 && issue.maxWishes <= 100) {
            throw new InvitationError(`Esta invitación ya envió sus ${issue.maxWishes} mensajes para Mia. ¡Gracias por todos tus deseos!`, 409);
          }
        }
        // We deliberately do not render server error bodies. Release their streams anyway.
        try { await response.body?.cancel(); } catch { /* Preserve the original safe error. */ }
        if (!response.ok) throw errorForStatus(response.status);
        throw badResponse();
      }
      return await response.json();
    } catch (error) {
      if (error instanceof InvitationError) throw error;
      throw new InvitationError(controller.signal.aborted
        ? 'La conexión tardó demasiado. Podés volver a intentar sin perder tus datos.'
        : 'No pudimos conectar. Revisá tu conexión e intentá nuevamente.');
    } finally { clearTimeout(timeout); }
  }

  function validateAnswer(answer, seats) {
    if (!answer || Object.keys(answer).some((key) => !['attending', 'guestCount'].includes(key))) throw new Error('La respuesta contiene campos que no corresponden.');
    const { attending, guestCount } = answer;
    if (typeof attending !== 'boolean' || !Number.isInteger(guestCount)) throw new Error('Elegí una respuesta y una cantidad válida.');
    if ((attending && (guestCount < 1 || guestCount > seats)) || (!attending && guestCount !== 0)) throw new Error(`Podés confirmar hasta ${seats} personas para esta invitación.`);
  }
  function validateWishAnswer(answer) {
    if (!answer || Object.keys(answer).some((key) => !['author', 'message'].includes(key))) throw new Error('El deseo contiene campos que no corresponden.');
    if (typeof answer.author !== 'string' || typeof answer.message !== 'string') throw new Error('Completá tu nombre y un mensaje.');
    const author = answer.author.trim();
    const message = answer.message.trim();
    if (!author || author.length > 80 || !message || message.length > 600) throw new Error('Usá hasta 80 caracteres para tu nombre y 600 para tu deseo.');
    return { author, message };
  }

  window.InvitationData = Object.freeze({
    mode,
    previewNotice: mode === 'mock' && typeof window.MIA_CONFIG?.apiBaseUrl === 'string',
    resetWishAttempt() { if (!wishInFlight) pendingWish = null; },
    async load() {
      if (mode === 'api') {
        currentPayload = validatePayload(await request());
        return structuredClone(currentPayload);
      }
      return structuredClone(payload);
    },
    async saveRsvp(answer) {
      if (mode === 'api') {
        if (!currentPayload) throw new InvitationError('Primero necesitamos cargar tu invitación.');
        validateAnswer(answer, currentPayload.invitation.seats);
        const response = await request('/rsvp', answer, 'PUT');
        if (!validRsvp(response, currentPayload.invitation.seats)) throw badResponse();
        currentPayload.rsvp = response;
        return structuredClone(response);
      }
      if (!answer || Object.keys(answer).some((key) => !['attending', 'guestCount'].includes(key))) {
        throw new Error('La respuesta contiene campos que no corresponden.');
      }
      const { attending, guestCount } = answer;
      if (typeof attending !== 'boolean' || !Number.isInteger(guestCount)) {
        throw new Error('Elegí una respuesta y una cantidad válida.');
      }
      if ((attending && (guestCount < 1 || guestCount > payload.invitation.seats)) || (!attending && guestCount !== 0)) {
        throw new Error(`Podés confirmar hasta ${payload.invitation.seats} personas para esta invitación.`);
      }
      payload.rsvp = { attending, guestCount, updatedAt: new Date().toISOString() };
      return structuredClone(payload.rsvp);
    },
    async saveWish(answer) {
      if (mode === 'api') {
        if (!currentPayload) throw new InvitationError('Primero necesitamos cargar tu invitación.');
        if (wishInFlight) throw new InvitationError('Tu deseo se está enviando. Esperá un momento.');
        const content = validateWishAnswer(answer);
        if (!pendingWish || pendingWish.author !== content.author || pendingWish.message !== content.message) {
          if (typeof window.crypto?.randomUUID !== 'function') throw new InvitationError('Abrí la invitación desde una conexión segura para enviar tu deseo.');
          pendingWish = { ...content, clientRequestId: window.crypto.randomUUID() };
        }
        wishInFlight = true;
        try {
          const response = await request('/wishes', pendingWish, 'POST');
          if (!validWish(response)) throw badResponse();
          currentPayload.wish = response;
          pendingWish = null;
          return structuredClone(response);
        } finally { wishInFlight = false; }
      }
      if (!answer || Object.keys(answer).some((key) => !['author', 'message'].includes(key))) {
        throw new Error('El deseo contiene campos que no corresponden.');
      }
      if (typeof answer.author !== 'string' || typeof answer.message !== 'string') {
        throw new Error('Completá tu nombre y un mensaje.');
      }
      const author = answer.author.trim();
      const message = answer.message.trim();
      if (!author || author.length > 80 || !message || message.length > 600) {
        throw new Error('Usá hasta 80 caracteres para tu nombre y 600 para tu deseo.');
      }
      payload.wish = { author, message, updatedAt: new Date().toISOString() };
      return structuredClone(payload.wish);
    },
  });
})();
