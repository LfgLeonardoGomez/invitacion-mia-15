/* Panel privado: credencial inicial efímera, cookie HttpOnly y CSRF solo en memoria. */
(() => {
  'use strict';

  const loopback = (hostname) => ['localhost', '127.0.0.1', '[::1]', '::1'].includes(hostname);
  function safeHttpUrl(value, pageHref) {
    if (typeof value !== 'string' || /[\s\u0000-\u001f\u007f\\]/.test(value)) throw new Error('La dirección configurada contiene caracteres no permitidos.');
    const page = new URL(pageHref);
    if (!(page.protocol === 'https:' || (page.protocol === 'http:' && loopback(page.hostname)))) {
      throw new Error('Abrí el panel desde una página HTTPS o desde el entorno local.');
    }
    const url = new URL(value, page);
    const localHttp = url.protocol === 'http:' && loopback(url.hostname) && page.protocol === 'http:' && loopback(page.hostname);
    if (!(url.protocol === 'https:' || localHttp) || url.username || url.password || url.search || url.hash) {
      throw new Error('La dirección configurada debe usar HTTPS, sin credenciales ni parámetros.');
    }
    return url;
  }
  function resolveConfig(config, pageHref) {
    if (!config || typeof config.apiBaseUrl !== 'string') throw new Error('El panel todavía no tiene un servidor configurado. Consultá con quien administra el sitio para habilitarlo.');
    const api = safeHttpUrl(config.apiBaseUrl || '/', pageHref);
    api.pathname = api.pathname.replace(/\/+$/, '');
    const invitation = safeHttpUrl(config.invitationBaseUrl == null ? './' : config.invitationBaseUrl, pageHref);
    if (invitation.pathname.endsWith('/index.html')) invitation.pathname = invitation.pathname.slice(0, -10);
    return { apiBaseUrl: api.href.replace(/\/$/, ''), invitationBaseUrl: invitation.href };
  }
  function invitationUrl(token, base, pageHref) {
    if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(token)) throw new Error('El servidor no devolvió un enlace válido.');
    const url = safeHttpUrl(base, pageHref);
    url.searchParams.set('invitation', token);
    return url.href;
  }
  function invitationState(item) {
    if (!item.active) return { key: 'inactive', label: 'Desactivada' };
    if (!item.rsvp) return { key: 'pending', label: 'Pendiente' };
    return item.rsvp.attending ? { key: 'confirmed', label: 'Confirmaron' } : { key: 'declined', label: 'No asisten' };
  }
  const utils = Object.freeze({ resolveConfig, invitationUrl, invitationState });
  if (typeof module !== 'undefined' && module.exports) module.exports = utils;
  if (typeof document === 'undefined') return;

  const $ = (id) => document.getElementById(id);
  const PAGE_SIZE = 20;
  let config;
  let csrfToken = '';
  let authPending = false;
  let session = 0;
  let guestVersion = 0;
  let wishVersion = 0;
  let summaryVersion = 0;
  let copyEpoch = 0;
  let activeCard = null;
  let cardSequence = 0;
  const dialogReturnFocus = new Map();
  let guestOffset = 0;
  let wishOffset = 0;
  let guestFilter = 'active';
  let guestSearch = '';
  let wishSearch = '';
  let editing = null;
  let pendingConfirmation = null;
  let modalOverflow = null;
  let mutationPending = false;
  let guestSearchTimer;
  let wishSearchTimer;
  let bankLoaded = false;
  let bankPending = false;
  const LOGOUT_PENDING = 'mia.admin.logoutPending';
  const controllers = new Set();
  const queryControllers = new Map();

  // This flag is NOT an authentication token; it only prevents silently reopening
  // a session when a network failure made the previous logout uncertain.
  function logoutPending() {
    try { return sessionStorage.getItem(LOGOUT_PENDING) === '1'; }
    catch { return false; }
  }
  function markLogoutPending(pending) {
    try {
      if (pending) sessionStorage.setItem(LOGOUT_PENDING, '1');
      else sessionStorage.removeItem(LOGOUT_PENDING);
    } catch { /* The in-memory warning still protects this page when storage is unavailable. */ }
  }

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text != null) element.textContent = String(text);
    return element;
  }
  function status(id, message = '', error = false) {
    const element = $(id);
    element.textContent = message;
    element.classList.toggle('status-error', error);
  }
  function resetSession(message = '') {
    session += 1;
    csrfToken = '';
    clearTimeout(guestSearchTimer);
    clearTimeout(wishSearchTimer);
    guestVersion += 1;
    wishVersion += 1;
    summaryVersion += 1;
    copyEpoch += 1;
    activeCard = null;
    dialogReturnFocus.clear();
    for (const controller of controllers) controller.abort();
    controllers.clear();
    queryControllers.clear();
    for (const dialog of document.querySelectorAll('dialog[open]')) dialog.close();
    if (pendingConfirmation) pendingConfirmation(false);
    pendingConfirmation = null;
    $('confirm-title').textContent = '';
    $('confirm-copy').textContent = '';
    editing = null;
    mutationPending = false;
    $('create-submit').disabled = false;
    $('edit-submit').disabled = false;
    $('edit-form').reset();
    $('create-form').reset();
    $('guest-search-form').reset();
    $('wish-search-form').reset();
    $('bank-form').reset();
    $('bank-fields').disabled = true;
    $('bank-enabled').disabled = true;
    $('bank-submit').disabled = true;
    bankLoaded = false;
    bankPending = false;
    $('guests-list').replaceChildren();
    $('wishes-list').replaceChildren();
    $('admin-key').value = '';
    document.querySelectorAll('[data-summary]').forEach((element) => { element.textContent = '—'; });
    ['dashboard-status', 'guests-status', 'wishes-status', 'create-status', 'edit-status', 'bank-status'].forEach((id) => status(id));
    guestOffset = 0;
    wishOffset = 0;
    guestFilter = 'active';
    guestSearch = '';
    wishSearch = '';
    document.querySelectorAll('[data-filter]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.filter === 'active')));
    $('dashboard').hidden = true;
    $('logout').hidden = true;
    $('login-panel').hidden = false;
    $('logout-retry').hidden = !logoutPending();
    $('main').removeAttribute('aria-busy');
    status('login-status', message, Boolean(message));
  }

  class ApiError extends Error {
    constructor(message, code = 0) { super(message); this.code = code; }
  }
  async function request(path, { method = 'GET', body, bootstrapKey, allowAnonymous = false, silent401 = false, csrfOverride, channel } = {}) {
    if (!config || (!csrfToken && !allowAnonymous)) throw new ApiError('Ingresá al panel para continuar.');
    const currentSession = session;
    const controller = new AbortController();
    if (channel) {
      queryControllers.get(channel)?.abort();
      queryControllers.set(channel, controller);
    }
    controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`${config.apiBaseUrl}/api/admin${path}`, {
        method,
        headers: {
          ...(bootstrapKey ? { Authorization: `Bearer ${bootstrapKey}` } : {}),
          ...(method !== 'GET' && (csrfOverride || csrfToken) ? { 'X-CSRF-Token': csrfOverride || csrfToken } : {}),
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: controller.signal,
        cache: 'no-store',
        credentials: 'include',
        redirect: 'error',
        referrerPolicy: 'no-referrer',
      });
      if (session !== currentSession) throw new ApiError('Sesión cerrada.', -1);
      if (!response.ok) {
        // Do not render private server errors, but release the unread response stream.
        try { await response.body?.cancel(); } catch { /* Keep the safe status message. */ }
        if (session !== currentSession) throw new ApiError('Sesión cerrada.', -1);
      }
      if (response.status === 401) {
        if (!silent401) resetSession('La sesión terminó o la clave no es válida. Volvé a ingresar.');
        throw new ApiError('La sesión terminó o la clave no es válida. Volvé a ingresar.', 401);
      }
      if (!response.ok) {
        const messages = {
          403: 'No tenés permiso para realizar esta acción.',
          404: 'Esta invitación ya no está disponible. Actualizá la lista.',
          409: 'No se puede reducir el cupo por debajo de la cantidad confirmada.',
          422: 'Revisá los datos: el nombre es obligatorio y el cupo debe ser un entero entre 1 y 50.',
          429: 'Hiciste varias consultas seguidas. Esperá un minuto antes de continuar.',
          503: 'La administración no está disponible en este momento. Intentá más tarde.',
        };
        const message = response.status === 422 && path === '/sections' ? 'Revisá los datos de transferencia e intentá nuevamente.' : messages[response.status];
        throw new ApiError(message || 'El servidor no pudo completar la operación. Intentá más tarde.', response.status);
      }
      const data = await response.json();
      if (session !== currentSession) throw new ApiError('Sesión cerrada.', -1);
      return data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (session !== currentSession) throw new ApiError('Sesión cerrada.', -1);
      throw new ApiError(method === 'GET'
        ? 'No pudimos conectar con el servidor. Revisá tu conexión e intentá nuevamente.'
        : 'No pudimos verificar si se guardó el cambio. Actualizá la lista antes de repetirlo.');
    } finally {
      clearTimeout(timeout);
      controllers.delete(controller);
      if (channel && queryControllers.get(channel) === controller) queryControllers.delete(channel);
    }
  }
  function showError(id, error, expectedSession) {
    if (session === expectedSession && csrfToken && error.code !== -1) status(id, error.message, true);
  }
  function emptyState(container, title, copy) {
    const block = textElement('div', 'empty-state');
    block.append(textElement('strong', '', title), textElement('p', '', copy));
    container.replaceChildren(block);
  }
  function rowButton(text, handler, label = text) {
    const button = textElement('button', 'button button-quiet', text);
    button.type = 'button';
    button.setAttribute('aria-label', label);
    button.addEventListener('click', handler);
    return button;
  }
  function formatDate(value) {
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('es-AR', { dateStyle: 'medium', timeStyle: 'short' }).format(date) : '';
  }
  function setCardOpen(card, open, { restoreFocus = false, instant = false } = {}) {
    if (!card?.isConnected) return;
    if (open && activeCard && activeCard !== card) setCardOpen(activeCard, false);
    const trigger = card.querySelector('.guest-summary');
    const front = card.querySelector('.guest-front');
    const actions = card.querySelector('.guest-actions');
    card.dataset.instant = String(instant);
    card.classList.toggle('is-open', open);
    trigger.setAttribute('aria-expanded', String(open));
    front.inert = open;
    front.setAttribute('aria-hidden', String(open));
    actions.inert = !open;
    actions.setAttribute('aria-hidden', String(!open));
    if (open) {
      activeCard = card;
      card.querySelector('.guest-close').focus({ preventScroll: true });
    } else {
      copyEpoch += 1;
      if (activeCard === card) activeCard = null;
      if (restoreFocus) trigger.focus({ preventScroll: true });
    }
  }
  function prepareCardDialog(card) {
    const trigger = card?.querySelector('.guest-summary');
    if (card) setCardOpen(card, false);
    return trigger;
  }
  function renderGuests(items) {
    copyEpoch += 1;
    activeCard = null;
    const container = $('guests-list');
    container.replaceChildren();
    if (!items.length) {
      const filtered = Boolean(guestSearch) || !['active', 'inactive'].includes(guestFilter);
      emptyState(container, filtered ? 'No encontramos coincidencias' : guestFilter === 'inactive' ? 'No hay familias desactivadas' : 'La lista empieza con vos', filtered ? 'Probá con otro nombre o filtro.' : guestFilter === 'inactive' ? 'Las invitaciones que desactives aparecerán acá. Podés reactivarlas sin perder sus respuestas.' : 'Creá la primera invitación para empezar.');
      return;
    }
    for (const item of items) {
      const state = invitationState(item);
      const row = textElement('article', 'guest-row guest-card');
      row.dataset.familyId = item.id;
      const rotator = textElement('div', 'guest-rotator');
      const front = textElement('div', 'guest-front');
      const summary = textElement('button', 'guest-summary');
      summary.type = 'button';
      summary.setAttribute('aria-expanded', 'false');
      const details = textElement('span', 'guest-details');
      details.append(textElement('span', 'guest-name', item.familyName));
      const meta = textElement('span', 'guest-meta');
      meta.append(textElement('span', '', `${item.seats} ${item.seats === 1 ? 'lugar reservado' : 'lugares reservados'}`));
      const badge = textElement('span', 'guest-state', state.label);
      badge.dataset.state = state.key;
      meta.append(badge);
      if (item.rsvp?.attending) meta.append(textElement('span', '', `${item.rsvp.guestCount} ${item.rsvp.guestCount === 1 ? 'persona confirmada' : 'personas confirmadas'}`));
      details.append(meta);
      const toggle = textElement('span', 'guest-toggle');
      toggle.append(textElement('span', '', 'Ver opciones'));
      const chevron = textElement('span', 'guest-chevron');
      chevron.setAttribute('aria-hidden', 'true');
      toggle.append(chevron);
      summary.append(details, toggle);
      front.append(summary);
      const actions = textElement('div', 'guest-actions');
      actions.id = `family-actions-${++cardSequence}`;
      actions.setAttribute('role', 'group');
      actions.setAttribute('aria-label', `Opciones de ${item.familyName}`);
      actions.setAttribute('aria-hidden', 'true');
      actions.inert = true;
      summary.setAttribute('aria-controls', actions.id);
      const heading = textElement('div', 'guest-actions__header');
      const close = rowButton('Volver', (event) => setCardOpen(row, false, { restoreFocus: true, instant: event.detail === 0 }), `Cerrar opciones de ${item.familyName}`);
      close.classList.add('guest-close');
      const backIdentity = textElement('span', 'guest-back-identity');
      const backState = textElement('span', 'guest-back-state', state.label);
      backState.dataset.state = state.key;
      backIdentity.append(textElement('span', 'guest-back-name', item.familyName), backState);
      heading.append(backIdentity);
      const buttons = textElement('div', 'guest-action-buttons');
      const copyStatus = textElement('p', 'guest-copy-status status');
      copyStatus.setAttribute('role', 'status');
      copyStatus.setAttribute('aria-live', 'polite');
      copyStatus.tabIndex = 0;
      const copy = rowButton('Copiar enlace', () => copyLink(item, row, copy, copyStatus), `Copiar enlace de ${item.familyName}`);
      copy.classList.add('guest-copy');
      buttons.append(
        copy,
        rowButton('Editar', () => openEditor(item, row), `Editar ${item.familyName}`),
        rowButton(item.active ? 'Desactivar' : 'Activar', () => changeActive(item, row), `${item.active ? 'Desactivar' : 'Activar'} ${item.familyName}`),
        rowButton('Regenerar enlace', () => rotateLink(item, copyStatus, row), `Regenerar enlace de ${item.familyName}`),
      );
      actions.append(heading, buttons, copyStatus, close);
      summary.addEventListener('click', (event) => setCardOpen(row, true, { instant: event.detail === 0 }));
      rotator.append(front, actions);
      row.append(rotator);
      container.append(row);
    }
  }
  function renderWishes(items) {
    const container = $('wishes-list');
    container.replaceChildren();
    if (!items.length) {
      emptyState(container, wishSearch ? 'No encontramos coincidencias' : 'Las palabras lindas van a llegar', wishSearch ? 'Probá buscando otro nombre o mensaje.' : 'Cuando tus invitados te dejen un deseo, lo vas a encontrar acá.');
      return;
    }
    for (const item of items) {
      const article = textElement('article', 'wish-card');
      article.append(
        textElement('p', 'wish-copy', item.message),
        textElement('p', 'wish-signature', item.author),
        textElement('p', 'wish-family', item.familyName),
        textElement('p', 'wish-date', formatDate(item.createdAt || item.updatedAt)),
      );
      article.append(rowButton('Eliminar deseo', (event) => deleteWish(item, event.currentTarget), `Eliminar deseo de ${item.author}`));
      container.append(article);
    }
  }
  async function loadSummary() {
    const version = ++summaryVersion;
    const currentSession = session;
    try {
      const summary = await request('/summary');
      if (version !== summaryVersion || session !== currentSession) return;
      document.querySelectorAll('[data-summary]').forEach((element) => {
        const value = summary[element.dataset.summary];
        element.textContent = Number.isSafeInteger(value) && value >= 0 ? String(value) : '—';
      });
    } catch (error) { showError('dashboard-status', error, currentSession); }
  }
  async function loadGuests() {
    const version = ++guestVersion;
    const currentSession = session;
    const requestedOffset = guestOffset;
    const container = $('guests-list');
    container.setAttribute('aria-busy', 'true');
    $('guests-prev').disabled = true;
    $('guests-next').disabled = true;
    status('guests-status', 'Cargando familias…');
    try {
      const query = new URLSearchParams({ status: guestFilter, q: guestSearch, limit: String(PAGE_SIZE), offset: String(requestedOffset) });
      const items = await request(`/invitations?${query}`, { channel: 'guests' });
      if (version !== guestVersion || session !== currentSession) return;
      if (!Array.isArray(items)) throw new ApiError('El servidor devolvió una lista inválida.');
      renderGuests(items);
      $('guests-prev').disabled = requestedOffset === 0;
      $('guests-next').disabled = items.length < PAGE_SIZE;
      $('guests-page').textContent = `Página ${Math.floor(requestedOffset / PAGE_SIZE) + 1}`;
      status('guests-status', items.length ? `${items.length} ${items.length === 1 ? 'familia en esta página' : 'familias en esta página'}.` : '');
    } catch (error) {
      if (version === guestVersion) {
        showError('guests-status', error, currentSession);
        if (session === currentSession && csrfToken) container.replaceChildren();
      }
    } finally { if (version === guestVersion) container.setAttribute('aria-busy', 'false'); }
  }
  async function loadWishes() {
    const version = ++wishVersion;
    const currentSession = session;
    const requestedOffset = wishOffset;
    const container = $('wishes-list');
    container.setAttribute('aria-busy', 'true');
    $('wishes-prev').disabled = true;
    $('wishes-next').disabled = true;
    status('wishes-status', 'Buscando los deseos…');
    try {
      const query = new URLSearchParams({ q: wishSearch, limit: String(PAGE_SIZE), offset: String(requestedOffset) });
      const items = await request(`/wishes?${query}`, { channel: 'wishes' });
      if (version !== wishVersion || session !== currentSession) return;
      if (!Array.isArray(items)) throw new ApiError('El servidor devolvió una lista inválida.');
      renderWishes(items);
      $('wishes-prev').disabled = requestedOffset === 0;
      $('wishes-next').disabled = items.length < PAGE_SIZE;
      $('wishes-page').textContent = `Página ${Math.floor(requestedOffset / PAGE_SIZE) + 1}`;
      status('wishes-status', items.length ? `${items.length} ${items.length === 1 ? 'deseo en esta página' : 'deseos en esta página'}.` : '');
    } catch (error) {
      if (version === wishVersion) {
        showError('wishes-status', error, currentSession);
        if (session === currentSession && csrfToken) container.replaceChildren();
      }
    } finally { if (version === wishVersion) container.setAttribute('aria-busy', 'false'); }
  }
  async function refresh() {
    clearTimeout(guestSearchTimer);
    clearTimeout(wishSearchTimer);
    const currentSession = session;
    $('refresh').disabled = true;
    status('dashboard-status');
    try { await Promise.all([loadSummary(), loadGuests(), loadWishes(), ...(bankLoaded ? [] : [loadBank()])]); }
    finally { if (session === currentSession) $('refresh').disabled = false; }
  }
  async function loadBank() {
    if (bankPending) return;
    const currentSession = session;
    bankLoaded = false;
    $('bank-submit').disabled = true;
    $('bank-enabled').disabled = true;
    $('bank-fields').disabled = true;
    status('bank-status', 'Cargando datos…');
    try {
      const sections = await request('/sections', { channel: 'bank' });
      if (session !== currentSession) return;
      const bank = sections?.bankTransfer;
      if (bank !== null && (!bank || ['holder', 'bank', 'alias', 'accountNumber'].some((key) => typeof bank[key] !== 'string') || typeof bank.illustrative !== 'boolean')) throw new ApiError('No pudimos verificar los datos recibidos.');
      $('bank-enabled').checked = bank !== null;
      $('bank-fields').disabled = bank === null;
      $('bank-enabled').disabled = false;
      $('bank-holder').value = bank?.holder || '';
      $('bank-name').value = bank?.bank || '';
      $('bank-alias').value = bank?.alias || '';
      $('bank-account').value = bank?.accountNumber || '';
      bankLoaded = true;
      $('bank-submit').disabled = false;
      status('bank-status', bank?.illustrative ? 'Los datos actuales son ilustrativos y no permiten copiar. Revisalos antes de guardar.' : '');
    } catch (error) { showError('bank-status', error, currentSession); }
  }
  function openDialog(dialog, returnFocus) {
    if (dialog.open) return;
    if (!document.querySelector('dialog[open]')) {
      modalOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    if (returnFocus) dialogReturnFocus.set(dialog.id, { target: returnFocus, familyId: returnFocus.closest('.guest-card')?.dataset.familyId });
    dialog.showModal();
  }
  async function copyLink(item, card, button, notice) {
    if (!csrfToken || button.disabled || mutationPending || !card.classList.contains('is-open')) return;
    const currentSession = session;
    const currentCopy = copyEpoch;
    const active = () => session === currentSession && currentCopy === copyEpoch && csrfToken && card.isConnected && card.classList.contains('is-open');
    button.disabled = true;
    notice.textContent = 'Preparando el enlace…';
    notice.classList.remove('status-error');
    let result;
    let value = '';
    try {
      if (!navigator.clipboard?.writeText) throw new ApiError('Este navegador no permitió copiar. Habilitá el portapapeles y volvé a intentarlo.', -2);
      result = await request(`/invitations/${encodeURIComponent(item.id)}/link`);
      if (!active()) return;
      if (result?.id !== item.id) throw new ApiError('El servidor no devolvió el enlace de esta familia. Intentá nuevamente.');
      value = invitationUrl(result.token, config.invitationBaseUrl, location.href);
      if (!active()) return;
      try { await navigator.clipboard.writeText(value); }
      catch { throw new ApiError('No pudimos copiar. Permití el acceso al portapapeles y volvé a tocar «Copiar enlace».', -2); }
      if (active()) notice.textContent = item.active
        ? 'Enlace copiado. Ya podés compartirlo con esta familia.'
        : 'Enlace copiado. La invitación está desactivada; activala antes de compartirlo.';
    } catch (error) {
      if (!active()) return;
      notice.classList.add('status-error');
      notice.textContent = error.code === 409
        ? 'Este enlace anterior no se puede recuperar. Usá «Regenerar enlace» para reemplazarlo; el anterior dejará de funcionar.'
        : error.code === 503
          ? 'No pudimos recuperar el enlace. La configuración del servidor necesita revisión; intentá más tarde.'
          : error.message;
    } finally {
      // The private URL is intentionally never inserted into the DOM or storage.
      value = '';
      result = null;
      if (session === currentSession && card.isConnected) {
        button.disabled = false;
        if (currentCopy !== copyEpoch && notice.textContent === 'Preparando el enlace…') notice.textContent = 'Volvé a tocar «Copiar enlace» para obtener el enlace vigente.';
      }
    }
  }
  function confirmAction(title, copy, accept, returnFocus) {
    if (pendingConfirmation) pendingConfirmation(false);
    $('confirm-title').textContent = title;
    $('confirm-copy').textContent = copy;
    $('confirm-accept').textContent = accept;
    openDialog($('confirm-dialog'), returnFocus);
    return new Promise((resolve) => { pendingConfirmation = resolve; });
  }
  async function deleteWish(item, button) {
    if (!csrfToken || mutationPending || typeof item.id !== 'string') return;
    const currentSession = session;
    const accepted = await confirmAction('¿Eliminar este deseo?', 'El mensaje se eliminará y no se podrá recuperar desde el panel. Seguirá contando para el límite de esta invitación.', 'Eliminar deseo', button);
    if (!accepted || session !== currentSession || !csrfToken || mutationPending) return;
    mutationPending = true;
    button.disabled = true;
    status('wishes-status', 'Eliminando deseo…');
    try {
      await request(`/wishes/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
      if (session !== currentSession) return;
      if (wishOffset > 0 && $('wishes-list').children.length === 1) wishOffset = Math.max(0, wishOffset - PAGE_SIZE);
      await Promise.all([loadWishes(), loadSummary()]);
      if (session === currentSession) status('wishes-status', 'Deseo eliminado.');
    } catch (error) { showError('wishes-status', error, currentSession); }
    finally { if (session === currentSession) { mutationPending = false; if (button.isConnected) button.disabled = false; } }
  }
  function openEditor(item, card) {
    if (!csrfToken) return;
    editing = item;
    $('edit-name').value = item.familyName;
    $('edit-seats').value = item.seats;
    status('edit-status');
    openDialog($('edit-dialog'), prepareCardDialog(card));
  }
  async function changeActive(item, card) {
    if (mutationPending || !csrfToken) return;
    const currentSession = session;
    const accepted = await confirmAction(item.active ? '¿Desactivar esta invitación?' : '¿Activar esta invitación?', `${item.familyName}. ${item.active ? 'Su enlace dejará de funcionar y no contará entre las familias activas. La respuesta se conserva.' : 'Su enlace vigente volverá a funcionar y la respuesta anterior se conserva.'}`, item.active ? 'Desactivar' : 'Activar', prepareCardDialog(card));
    if (!accepted || session !== currentSession || !csrfToken || mutationPending) return;
    mutationPending = true;
    try {
      await request(`/invitations/${encodeURIComponent(item.id)}`, { method: 'PATCH', body: { active: !item.active } });
      if (session !== currentSession) return;
      status('dashboard-status', `Invitación ${item.active ? 'desactivada' : 'activada'}.`);
      await Promise.all([loadGuests(), loadSummary()]);
    } catch (error) { showError('dashboard-status', error, currentSession); }
    finally { if (session === currentSession) mutationPending = false; }
  }
  async function rotateLink(item, notice, card) {
    if (mutationPending || !csrfToken) return;
    const currentSession = session;
    const accepted = await confirmAction('¿Regenerar el enlace?', `El enlace anterior de ${item.familyName} dejará de funcionar. Su confirmación y sus deseos no se borran. Después copiá y compartí el enlace regenerado.`, 'Regenerar enlace', prepareCardDialog(card));
    if (!accepted || session !== currentSession || !csrfToken || mutationPending) return;
    mutationPending = true;
    copyEpoch += 1;
    if (notice?.isConnected) { notice.textContent = ''; notice.classList.remove('status-error'); }
    try {
      await request(`/invitations/${encodeURIComponent(item.id)}/rotate-token`, { method: 'POST' });
      if (session !== currentSession) return;
      status('dashboard-status', item.active ? 'Enlace regenerado. Ya podés copiarlo. El anterior dejó de funcionar.' : 'Enlace regenerado. Ya podés copiarlo. La invitación sigue desactivada: activala para que se pueda abrir.');
      if (notice?.isConnected) notice.textContent = 'Enlace regenerado. Tocá «Copiar enlace» para compartirlo.';
    } catch (error) { showError('dashboard-status', error, currentSession); }
    finally { if (session === currentSession) mutationPending = false; }
  }

  function sessionData(data) {
    if (!data || data.authenticated !== true || typeof data.csrfToken !== 'string'
      || !/^[A-Za-z0-9_-]{32,256}$/.test(data.csrfToken) || !Number.isFinite(Date.parse(data.expiresAt))) {
      throw new ApiError('No pudimos verificar la sesión. Volvé a ingresar.');
    }
    return data;
  }
  async function showDashboard(data) {
    csrfToken = sessionData(data).csrfToken;
    markLogoutPending(false);
    $('login-panel').hidden = true;
    $('dashboard').hidden = false;
    $('logout').hidden = false;
    $('logout-retry').hidden = true;
    $('refresh').disabled = false;
    status('login-status');
    await refresh();
  }
  async function restoreSession() {
    if (!config || authPending) return;
    if (logoutPending()) {
      resetSession('El último cierre de sesión no pudo verificarse. Reintentá cerrarla antes de dejar este dispositivo.');
      return;
    }
    resetSession();
    const currentSession = session;
    authPending = true;
    $('login-submit').disabled = true;
    status('login-status', 'Comprobando tu sesión…');
    try {
      const data = await request('/session', { allowAnonymous: true, silent401: true });
      if (session === currentSession) await showDashboard(data);
    } catch (error) {
      if (session === currentSession) {
        resetSession(error.code === 401 ? '' : error.message);
      }
    } finally { authPending = false; $('login-submit').disabled = !config; }
  }
  async function closeSession() {
    if (!config || authPending) return;
    let token = csrfToken;
    markLogoutPending(true);
    resetSession('Cerrando la sesión…');
    const currentSession = session;
    authPending = true;
    $('login-submit').disabled = true;
    $('logout-retry').disabled = true;
    try {
      if (!token) {
        const data = await request('/session', { allowAnonymous: true, silent401: true });
        token = sessionData(data).csrfToken;
      }
      const result = await request('/session', { method: 'DELETE', allowAnonymous: true, silent401: true, csrfOverride: token });
      if (result?.authenticated !== false) throw new ApiError('No pudimos verificar el cierre de sesión.');
      if (session === currentSession) { markLogoutPending(false); resetSession(); }
    } catch (error) {
      if (session === currentSession) {
        if (error.code === 401) { markLogoutPending(false); resetSession(); }
        else resetSession('Ocultamos tus datos, pero no pudimos verificar el cierre en el servidor. Reintentá cerrar la sesión antes de dejar este dispositivo.');
      }
    } finally {
      token = '';
      authPending = false;
      $('logout-retry').disabled = false;
      $('login-submit').disabled = !config;
      $('admin-key').focus();
    }
  }

  $('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!config || authPending || !event.currentTarget.reportValidity()) return;
    let value = $('admin-key').value;
    if (!/^[\x21-\x7e]{32,256}$/.test(value)) {
      status('login-status', 'La clave debe tener entre 32 y 256 caracteres, sin espacios.', true);
      return;
    }
    resetSession();
    authPending = true;
    const currentSession = session;
    $('login-submit').disabled = true;
    status('login-status', 'Verificando acceso…');
    try {
      const data = await request('/session', { method: 'POST', allowAnonymous: true, bootstrapKey: value });
      value = '';
      if (session !== currentSession) return;
      await showDashboard(data);
    } catch (error) {
      if (session === currentSession) resetSession(error.message);
    } finally { value = ''; authPending = false; $('login-submit').disabled = !config; }
  });
  $('logout').addEventListener('click', closeSession);
  $('logout-retry').addEventListener('click', closeSession);
  $('refresh').addEventListener('click', refresh);
  $('bank-enabled').addEventListener('change', () => { $('bank-fields').disabled = !$('bank-enabled').checked; });
  $('bank-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!csrfToken || !bankLoaded || bankPending || !event.currentTarget.reportValidity()) return;
    const enabled = $('bank-enabled').checked;
    const bank = enabled ? { holder: $('bank-holder').value.trim(), bank: $('bank-name').value.trim(), alias: $('bank-alias').value.trim(), accountNumber: $('bank-account').value.trim(), illustrative: false } : null;
    if (bank && (!bank.holder || !bank.bank || (!bank.alias && !bank.accountNumber) || (bank.accountNumber && !/^[0-9]{22}$/.test(bank.accountNumber)))) {
      status('bank-status', 'Completá titular, banco y un alias o CBU/CVU válido de 22 dígitos.', true);
      return;
    }
    const currentSession = session;
    bankPending = true;
    $('bank-submit').disabled = true;
    $('bank-enabled').disabled = true;
    $('bank-fields').disabled = true;
    status('bank-status', 'Guardando datos…');
    try {
      const sections = await request('/sections');
      if (!sections || typeof sections !== 'object' || !sections.contact || typeof sections.eventUtcOffset !== 'string') throw new ApiError('No pudimos verificar la configuración actual. No se guardaron cambios.');
      await request('/sections', { method: 'PUT', body: { ...sections, bankTransfer: bank } });
      if (session === currentSession) status('bank-status', enabled ? 'Datos guardados. Verificalos en una invitación personalizada.' : 'Datos de transferencia ocultos en las invitaciones.');
    } catch (error) { showError('bank-status', error, currentSession); }
    finally { if (session === currentSession) { bankPending = false; $('bank-submit').disabled = false; $('bank-enabled').disabled = false; $('bank-fields').disabled = !$('bank-enabled').checked; } }
  });
  $('create-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!csrfToken || mutationPending || !event.currentTarget.reportValidity()) return;
    const familyName = $('family-name').value.trim();
    const seats = Number($('family-seats').value);
    if (!familyName || !Number.isInteger(seats) || seats < 1 || seats > 50) {
      status('create-status', 'Completá el nombre y un cupo entero entre 1 y 50.', true);
      return;
    }
    const currentSession = session;
    mutationPending = true;
    $('create-submit').disabled = true;
    status('create-status', 'Creando invitación…');
    try {
      await request('/invitations', { method: 'POST', body: { familyName, seats } });
      if (session !== currentSession) return;
      $('create-form').reset();
      status('create-status', 'Invitación creada. Podés copiar su enlace desde la tarjeta de la familia.');
      guestOffset = 0;
      await Promise.all([loadSummary(), loadGuests()]);
    } catch (error) { showError('create-status', error, currentSession); }
    finally { if (session === currentSession) { mutationPending = false; $('create-submit').disabled = false; } }
  });
  $('edit-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!csrfToken || !editing || mutationPending || !event.currentTarget.reportValidity()) return;
    const familyName = $('edit-name').value.trim();
    const seats = Number($('edit-seats').value);
    if (!familyName || !Number.isInteger(seats) || seats < 1 || seats > 50) {
      status('edit-status', 'Completá el nombre y un cupo entero entre 1 y 50.', true);
      return;
    }
    const currentSession = session;
    const identifier = editing.id;
    mutationPending = true;
    $('edit-submit').disabled = true;
    status('edit-status', 'Guardando…');
    try {
      await request(`/invitations/${encodeURIComponent(identifier)}`, { method: 'PATCH', body: { familyName, seats } });
      if (session !== currentSession) return;
      if (editing?.id === identifier) $('edit-dialog').close();
      status('dashboard-status', 'Los datos de la familia se actualizaron.');
      await Promise.all([loadSummary(), loadGuests(), loadWishes()]);
    } catch (error) { showError('edit-status', error, currentSession); }
    finally { if (session === currentSession) { mutationPending = false; $('edit-submit').disabled = false; } }
  });
  function searchNow(kind) {
    if (!csrfToken) return;
    if (kind === 'guests') {
      clearTimeout(guestSearchTimer);
      guestSearch = $('guest-search').value.trim(); guestOffset = 0;
      void loadGuests();
    } else {
      clearTimeout(wishSearchTimer);
      wishSearch = $('wish-search').value.trim(); wishOffset = 0;
      void loadWishes();
    }
  }
  function queueSearch(kind) {
    if (!csrfToken) return;
    if (kind === 'guests') {
      clearTimeout(guestSearchTimer);
      guestSearch = $('guest-search').value.trim(); guestOffset = 0;
      guestVersion += 1;
      $('guests-prev').disabled = true; $('guests-next').disabled = true;
      guestSearchTimer = setTimeout(() => searchNow(kind), 280);
    } else {
      clearTimeout(wishSearchTimer);
      wishSearch = $('wish-search').value.trim(); wishOffset = 0;
      wishVersion += 1;
      $('wishes-prev').disabled = true; $('wishes-next').disabled = true;
      wishSearchTimer = setTimeout(() => searchNow(kind), 280);
    }
    queryControllers.get(kind)?.abort();
  }
  $('guest-search').addEventListener('input', () => queueSearch('guests'));
  $('wish-search').addEventListener('input', () => queueSearch('wishes'));
  $('guest-search-form').addEventListener('submit', (event) => { event.preventDefault(); searchNow('guests'); });
  $('wish-search-form').addEventListener('submit', (event) => { event.preventDefault(); searchNow('wishes'); });
  document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', () => {
    clearTimeout(guestSearchTimer);
    guestFilter = button.dataset.filter;
    guestOffset = 0;
    document.querySelectorAll('[data-filter]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
    void loadGuests();
  }));
  $('guests-prev').addEventListener('click', () => { guestOffset = Math.max(0, guestOffset - PAGE_SIZE); void loadGuests(); });
  $('guests-next').addEventListener('click', () => { guestOffset += PAGE_SIZE; void loadGuests(); });
  $('wishes-prev').addEventListener('click', () => { wishOffset = Math.max(0, wishOffset - PAGE_SIZE); void loadWishes(); });
  $('wishes-next').addEventListener('click', () => { wishOffset += PAGE_SIZE; void loadWishes(); });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && activeCard && !document.querySelector('dialog[open]')) {
      event.preventDefault();
      setCardOpen(activeCard, false, { restoreFocus: true, instant: true });
    }
  });
  document.addEventListener('pointerdown', (event) => {
    if (activeCard && !activeCard.contains(event.target) && !document.querySelector('dialog[open]')) setCardOpen(activeCard, false);
  });
  document.querySelectorAll('[data-close]').forEach((button) => button.addEventListener('click', () => $(button.dataset.close).close()));
  for (const dialog of document.querySelectorAll('dialog')) {
    dialog.addEventListener('close', () => {
      if (!document.querySelector('dialog[open]') && modalOverflow !== null) {
        document.body.style.overflow = modalOverflow;
        modalOverflow = null;
      }
      if (dialog.id === 'edit-dialog' && !dialog.open) { editing = null; $('edit-form').reset(); status('edit-status'); }
      if (dialog.id === 'confirm-dialog' && !dialog.open && pendingConfirmation) { pendingConfirmation(false); pendingConfirmation = null; }
      const returnFocus = dialogReturnFocus.get(dialog.id);
      dialogReturnFocus.delete(dialog.id);
      if (returnFocus && csrfToken && !document.querySelector('dialog[open]')) {
        const target = returnFocus.target.isConnected ? returnFocus.target : [...document.querySelectorAll('.guest-card')].find((card) => card.dataset.familyId === returnFocus.familyId)?.querySelector('.guest-summary');
        target?.focus({ preventScroll: true });
      }
    });
  }
  $('confirm-cancel').addEventListener('click', () => $('confirm-dialog').close());
  $('confirm-accept').addEventListener('click', () => {
    const resolve = pendingConfirmation;
    pendingConfirmation = null;
    $('confirm-dialog').close();
    if (resolve) resolve(true);
  });
  window.addEventListener('pagehide', () => resetSession());
  window.addEventListener('pageshow', (event) => { if (event.persisted) void restoreSession(); });

  try { config = resolveConfig(window.MIA_CONFIG, location.href); }
  catch (error) {
    $('config-notice').textContent = error.message;
    $('config-notice').hidden = false;
    $('admin-key').disabled = true;
    $('login-submit').disabled = true;
  }
  if (config) void restoreSession();
})();
