/* Adaptador temporal sin HTTP. sections/wish son extensiones de vista previa;
   todavía no forman parte del contrato implementado por el backend v1. */
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

  window.InvitationData = Object.freeze({
    mode: 'mock',
    async load() {
      return structuredClone(payload);
    },
    async saveRsvp(answer) {
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
