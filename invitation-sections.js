/* Secciones adicionales de la tarjeta: no realizan solicitudes a la API. */
(() => {
  function countdown(target, now = Date.now()) {
    if (!Number.isFinite(target) || !Number.isFinite(now)) return null;
    const total = Math.max(0, Math.ceil((target - now) / 1000));
    return {
      days: Math.floor(total / 86400),
      hours: Math.floor(total / 3600) % 24,
      minutes: Math.floor(total / 60) % 60,
      seconds: total % 60,
      expired: total === 0,
    };
  }

  let timer;
  let deadline = NaN;
  let bound = false;

  function whatsappLink(number, name) {
    if (typeof number !== 'string' || !/^[1-9]\d{7,14}$/.test(number)) return null;
    const link = new URL(`https://wa.me/${number}`);
    link.searchParams.set('text', `Hola, tengo una consulta sobre los XV de ${name}.`);
    return link.href;
  }

  function updateClock() {
    const parts = countdown(deadline);
    const clock = document.getElementById('countdown-clock');
    clock.hidden = !parts;
    if (!parts) {
      document.getElementById('countdown-heading').textContent = 'Una noche para recordar';
      return;
    }
    for (const unit of ['days', 'hours', 'minutes', 'seconds']) {
      const element = document.querySelector(`[data-countdown="${unit}"]`);
      const value = String(parts[unit]).padStart(2, '0');
      if (element.textContent !== value) element.textContent = value;
    }
    document.getElementById('countdown-heading').textContent = parts.expired ? '¡Llegó el gran día!' : 'Falta cada vez menos';
    if (parts.expired) clearInterval(timer);
  }

  function restartClock() {
    clearInterval(timer);
    updateClock();
    if (!document.hidden && countdown(deadline)?.expired === false) timer = setInterval(updateClock, 1000);
  }

  function renderWish(wish) {
    const preview = document.getElementById('wish-preview');
    preview.hidden = !wish;
    document.getElementById('wish-preview-message').textContent = wish?.message || '';
    document.getElementById('wish-preview-author').textContent = wish?.author || '';
  }

  function renderTransfer(transfer) {
    const button = document.getElementById('transfer-open');
    const dialog = document.getElementById('transfer-dialog');
    const rows = document.getElementById('transfer-fields');
    const valid = transfer && ['alias', 'accountNumber'].some((key) => typeof transfer[key] === 'string' && transfer[key].trim());
    button.hidden = !valid;
    if (dialog.open) dialog.close();
    rows.replaceChildren();
    document.getElementById('transfer-pending').hidden = Boolean(valid);
    document.getElementById('transfer-status').textContent = '';
    const disclaimer = document.getElementById('transfer-disclaimer');
    disclaimer.hidden = !valid || !transfer.illustrative;
    dialog.setAttribute('aria-describedby', valid && transfer.illustrative ? 'transfer-disclaimer' : 'transfer-dialog-note');
    if (!valid) return;

    for (const [key, label] of [['holder', 'Titular'], ['bank', 'Banco / billetera'], ['alias', 'Alias'], ['accountNumber', 'CBU / CVU']]) {
      if (typeof transfer[key] !== 'string' || !transfer[key].trim()) continue;
      const row = document.createElement('div');
      row.className = 'transfer-field';
      const title = document.createElement('label');
      title.htmlFor = `transfer-${key}`;
      title.textContent = label;
      const value = document.createElement('input');
      value.id = title.htmlFor;
      value.value = transfer[key].trim();
      value.readOnly = true;
      row.append(title, value);
      if (key === 'alias' || key === 'accountNumber') {
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'transfer-copy';
        copy.textContent = 'Copiar';
        copy.setAttribute('aria-label', `Copiar ${label}`);
        copy.disabled = Boolean(transfer.illustrative);
        if (transfer.illustrative) copy.title = 'Disponible cuando se carguen los datos reales.';
        copy.addEventListener('click', async () => {
          const status = document.getElementById('transfer-status');
          try {
            if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
            await navigator.clipboard.writeText(value.value);
            status.textContent = `${label} copiado.`;
          } catch {
            value.focus();
            value.select();
            status.textContent = 'No se pudo copiar automáticamente. Seleccionamos el dato para que lo copies manualmente.';
          }
        });
        row.append(copy);
      }
      rows.append(row);
    }
  }

  function bind() {
    if (bound) return;
    bound = true;
    const transferButton = document.getElementById('transfer-open');
    const transferDialog = document.getElementById('transfer-dialog');
    let previousOverflow;
    let scrollLocked = false;
    let startedOnBackdrop = false;
    const outsideDialog = (event) => {
      const rect = transferDialog.getBoundingClientRect();
      return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
    };
    transferButton.addEventListener('click', () => {
      if (transferButton.hidden || transferDialog.open) return;
      transferDialog.showModal();
      if (!scrollLocked) previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      scrollLocked = true;
    });
    document.getElementById('transfer-close').addEventListener('click', () => transferDialog.close());
    transferDialog.addEventListener('pointerdown', (event) => {
      startedOnBackdrop = event.target === transferDialog && outsideDialog(event);
    }, { passive: true });
    transferDialog.addEventListener('pointercancel', () => { startedOnBackdrop = false; }, { passive: true });
    transferDialog.addEventListener('click', (event) => {
      if (startedOnBackdrop && event.target === transferDialog && outsideDialog(event)) transferDialog.close();
      startedOnBackdrop = false;
    });
    transferDialog.addEventListener('close', () => {
      if (transferDialog.open) return;
      if (scrollLocked) document.body.style.overflow = previousOverflow;
      scrollLocked = false;
      if (!transferButton.hidden) transferButton.focus({ preventScroll: true });
    });
    const scene = document.getElementById('castle-scene');
    const invitation = document.getElementById('invitation');
    const activateCastle = (visible) => {
      scene.classList.toggle('is-active', visible);
      invitation.dataset.castleVisible = String(visible);
    };
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(([entry]) => activateCastle(entry.isIntersecting), { threshold: .01 });
      observer.observe(scene);
    } else {
      // Local launch remains usable without the visibility optimization.
      scene.classList.add('is-active');
    }
    document.addEventListener('visibilitychange', restartClock);
    window.addEventListener('pagehide', () => clearInterval(timer));
    window.addEventListener('pageshow', restartClock);
    const form = document.getElementById('wish-form');
    const author = document.getElementById('wish-author');
    const message = document.getElementById('wish-message');
    const status = document.getElementById('wish-status');
    form.addEventListener('input', () => {
      author.setCustomValidity('');
      message.setCustomValidity('');
      document.getElementById('wish-length').textContent = `${message.value.length} / 600`;
      status.textContent = '';
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      author.setCustomValidity(author.value.trim() ? '' : 'Completá tu nombre.');
      message.setCustomValidity(message.value.trim() ? '' : 'Escribí tu deseo.');
      if (!form.reportValidity()) return;
      const submit = document.getElementById('wish-submit');
      submit.disabled = true;
      try {
        const wish = await window.InvitationData.saveWish({ author: author.value, message: message.value });
        renderWish(wish);
        status.textContent = '¡Gracias por tu deseo!';
      } catch (error) {
        status.textContent = error instanceof Error ? error.message : 'No pudimos guardar tu deseo. Intentá nuevamente.';
      } finally {
        submit.disabled = false;
      }
    });
  }

  function render(payload) {
    bind();
    // Offset del evento, nunca la zona del dispositivo del invitado.
    const offset = payload.sections?.eventUtcOffset;
    deadline = typeof offset === 'string' && /^[+-]\d{2}:\d{2}$/.test(offset)
      ? Date.parse(`${payload.event.date}T${payload.event.arrivalTime}:00${offset}`) : NaN;
    restartClock();
    const date = new Date(`${payload.event.date}T12:00:00Z`);
    const dateLabel = new Intl.DateTimeFormat('es-AR', { day: 'numeric', month: 'long', timeZone: 'UTC' }).format(date);
    document.getElementById('countdown-caption').textContent = `${dateLabel} · ${payload.event.arrivalTime} hs · Hora de Argentina`;
    renderTransfer(payload.sections?.bankTransfer);
    renderWish(payload.wish);
    const contactLink = whatsappLink(payload.sections?.contact?.whatsappNumber, payload.event.name);
    const contact = document.getElementById('contact-whatsapp');
    document.getElementById('contact-section').hidden = !contactLink;
    contact.removeAttribute('href');
    if (contactLink) contact.href = contactLink;
    contact.setAttribute('aria-label', `Contactar a la mamá de ${payload.event.name} por WhatsApp`);
    document.getElementById('wish-submit').textContent = 'Enviar mi deseo';
  }

  window.InvitationSections = Object.freeze({ countdown, whatsappLink, render });
})();
