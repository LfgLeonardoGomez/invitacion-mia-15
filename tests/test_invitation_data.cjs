const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function adapter() {
  const window = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../invitation-data.js'), 'utf8'), { window, structuredClone, Date });
  return window.InvitationData;
}

test('mock preserves the API payload and returns independent data', async () => {
  const data = adapter();
  const original = await data.load();
  assert.equal(data.mode, 'mock');
  assert.equal(original.event.name, 'Mia');
  assert.equal(original.event.date, '2026-12-26');
  assert.equal(original.invitation.seats, 3);
  assert.equal(original.invitation.familyName, 'Familia Gomez');
  original.invitation.seats = 999;
  original.event.name = '<script>not HTML</script>';
  assert.equal((await data.load()).invitation.seats, 3);
  assert.equal((await data.load()).event.name, 'Mia');
});

test('preview accepts only valid counts and has no server persistence', async () => {
  const data = adapter();
  await assert.rejects(data.saveRsvp({ attending: true, guestCount: 4 }), /hasta 3/);
  await assert.rejects(data.saveRsvp({ attending: false, guestCount: 1 }), /hasta 3/);
  await assert.rejects(data.saveRsvp({ attending: true, guestCount: 1.5 }), /válida/);
  await assert.rejects(data.saveRsvp({ attending: 'true', guestCount: 1 }), /válida/);
  await assert.rejects(data.saveRsvp({ attending: true, guestCount: 1, seats: 999 }), /campos/);
  const saved = await data.saveRsvp({ attending: true, guestCount: 3 });
  assert.equal(saved.guestCount, 3);
  assert.equal((await data.load()).rsvp.attending, true);
  assert.equal((await adapter().load()).rsvp, null);
  await data.saveRsvp({ attending: false, guestCount: 0 });
  assert.equal((await data.load()).rsvp.guestCount, 0);
});

test('bank details remain pending and mock sections are cloned', async () => {
  const data = adapter();
  const payload = await data.load();
  assert.equal(payload.sections.bankTransfer, null);
  assert.equal(payload.sections.eventUtcOffset, '-03:00');
  payload.sections.bankTransfer = { alias: 'should-not-persist' };
  assert.equal((await data.load()).sections.bankTransfer, null);
});

test('wish preview validates, trims, clones and resets on reload', async () => {
  const data = adapter();
  for (const answer of [null, {}, { author: 123, message: 'Hola' }, { author: '  ', message: 'Hola' },
    { author: 'Ana', message: '   ' }, { author: 'a'.repeat(81), message: 'Hola' },
    { author: 'Ana', message: 'a'.repeat(601) }, { author: 'Ana', message: 'Hola', familyId: 'other' }]) {
    await assert.rejects(data.saveWish(answer));
  }
  const saved = await data.saveWish({ author: '  Ana  ', message: '  Que seas muy feliz.  ' });
  assert.equal(saved.author, 'Ana');
  assert.equal(saved.message, 'Que seas muy feliz.');
  saved.message = 'altered';
  assert.equal((await data.load()).wish.message, 'Que seas muy feliz.');
  await data.saveWish({ author: 'A'.repeat(80), message: 'x'.repeat(600) });
  assert.equal((await data.load()).wish.message.length, 600);
  assert.equal((await adapter().load()).wish, null);
});

const sectionWindow = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../invitation-sections.js'), 'utf8'), { window: sectionWindow, Date, URL, setInterval, clearInterval });
const countdown = sectionWindow.InvitationSections.countdown;

test('countdown uses the event offset, handles carry and never turns negative', () => {
  const target = Date.parse('2026-12-26T20:30:00-03:00');
  assert.equal(target, Date.parse('2026-12-26T23:30:00Z'));
  const parts = countdown(target, target - (86400 + 2 * 3600 + 3 * 60 + 4) * 1000);
  assert.equal(parts.days, 1);
  assert.equal(parts.hours, 2);
  assert.equal(parts.minutes, 3);
  assert.equal(parts.seconds, 4);
  assert.equal(parts.expired, false);
  assert.equal(countdown(target, target - 1).seconds, 1);
  assert.equal(countdown(target, target).expired, true);
  assert.equal(countdown(target, target + 86400000).days, 0);
  assert.equal(countdown(target, target + 86400000).seconds, 0);
  assert.equal(countdown(NaN), null);
  assert.equal(countdown(target, Infinity), null);
});

test('WhatsApp URL uses only the configured number and a generic message', async () => {
  const { whatsappLink } = sectionWindow.InvitationSections;
  const payload = await adapter().load();
  const link = new URL(whatsappLink(payload.sections.contact.whatsappNumber, payload.event.name));
  assert.equal(link.origin, 'https://wa.me');
  assert.equal(link.pathname, '/5491141675124');
  assert.equal(link.searchParams.get('text'), 'Hola, tengo una consulta sobre los XV de Mia.');
  assert.equal(link.href.includes(payload.invitation.familyName), false);
  for (const value of [null, undefined, '', '+54 9 11', 'javascript:alert(1)', '123/../../other', '0'.repeat(13), '1'.repeat(16)]) {
    assert.equal(whatsappLink(value, 'Mia'), null);
  }
  const unusual = new URL(whatsappLink(payload.sections.contact.whatsappNumber, 'Mia & familia?'));
  assert.equal(unusual.searchParams.get('text'), 'Hola, tengo una consulta sobre los XV de Mia & familia?.');
  assert.equal([...unusual.searchParams].length, 1);
});
