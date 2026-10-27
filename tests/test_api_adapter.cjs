const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../invitation-data.js'), 'utf8');
const token = 'A'.repeat(43);
const stamp = '2026-10-26T19:00:00Z';
const uuid = '12345678-1234-4234-8234-123456789abc';
const apiUrl = 'https://api.example.test';

function payload() {
  return {
    event: { name: 'Mia', date: '2026-12-26', arrivalTime: '20:30', entranceTime: '21:30', venueName: 'Jardín Secreto', venueAddress: 'Trujui', dressCode: 'Elegante Sport' },
    invitation: { id: 'family-id', familyName: 'Familia Real', seats: 4 },
    rsvp: null, sections: { eventUtcOffset: '-03:00', contact: { whatsappNumber: '5491141675124' }, bankTransfer: null }, wish: null,
  };
}
const wish = () => ({ id: 'wish-id', author: 'Ana', message: 'Un hermoso festejo', createdAt: stamp, updatedAt: stamp });
const response = (body, status = 200, contentType = 'application/json') => ({ ok: status >= 200 && status < 300, status, headers: { get: () => contentType }, json: async () => structuredClone(body) });

function adapter({ href = `https://front.example.test/mia/?invitation=${token}`, config = { apiBaseUrl: apiUrl }, fetcher = async () => response(payload()), timers = {}, crypto } = {}) {
  const calls = [];
  let uuidCalls = 0;
  const window = { location: new URL(href), MIA_CONFIG: config, crypto: crypto || { randomUUID: () => { uuidCalls += 1; return `${uuid.slice(0, -1)}${uuidCalls}`; } } };
  vm.runInNewContext(source, {
    window, URL, structuredClone, Date, AbortController,
    setTimeout: timers.setTimeout || setTimeout, clearTimeout: timers.clearTimeout || clearTimeout,
    fetch: async (...args) => { calls.push(args); return fetcher(...args); },
  });
  return { data: window.InvitationData, calls, uuidCalls: () => uuidCalls };
}

test('no-token preview stays offline, explicitly flagged when API is configured', async () => {
  const { data, calls } = adapter({ href: 'https://front.example.test/mia/' });
  assert.equal(data.mode, 'mock');
  assert.equal(data.previewNotice, true);
  assert.equal((await data.load()).invitation.familyName, 'Familia Gomez');
  await data.saveRsvp({ attending: true, guestCount: 2 });
  assert.equal(calls.length, 0);
});

test('private links never fall back to a fake family when unconfigured or malformed', async () => {
  for (const config of [{}, { apiBaseUrl: null }]) {
    const { data, calls } = adapter({ config });
    assert.equal(data.mode, 'api');
    await assert.rejects(data.load(), /todavía no está disponible/);
    assert.equal(calls.length, 0);
  }
  for (const query of ['invitation=', 'invitation=short', `invitation=${token}&invitation=${token}`, 'invitation=%3Cscript%3E']) {
    const { data, calls } = adapter({ href: `https://front.example.test/?${query}` });
    assert.equal(data.mode, 'api');
    await assert.rejects(data.load(), /no es válido/);
    assert.equal(calls.length, 0);
  }
});

test('API URL rejects unsafe transport, credentials, query overrides and redirects', async () => {
  for (const base of ['http://api.example.test', 'http://127.0.0.1:8000', '//api.example.test', '/api', 'https://user:pass@api.example.test', 'https://api.example.test?key=x', 'https://api.example.test/#secret', 'javascript:alert(1)', 'https://api.example.test/ ', 'https://api.example.test/\n', 'https://api.example.test/\u007f', 'https://api.example.test/\\other']) {
    const { data, calls } = adapter({ config: { apiBaseUrl: base } });
    await assert.rejects(data.load(), /segura/);
    assert.equal(calls.length, 0);
  }
  for (const href of [`http://front.example.test/?invitation=${token}`, `file:///local/index.html?invitation=${token}`]) {
    const { data, calls } = adapter({ href });
    await assert.rejects(data.load(), /segura/);
    assert.equal(calls.length, 0);
  }
  const mixedLocal = adapter({ href: `https://localhost/?invitation=${token}`, config: { apiBaseUrl: 'http://localhost:8000' } });
  await assert.rejects(mixedLocal.data.load(), /segura/);
  assert.equal(mixedLocal.calls.length, 0);
  const remote = adapter({ href: `https://front.example.test/?invitation=${token}&apiBaseUrl=https://evil.example.test`, config: { apiBaseUrl: apiUrl } });
  await remote.data.load();
  assert.equal(remote.calls[0][0], `${apiUrl}/api/invitations/${token}`);
  assert.equal(remote.calls[0][1].redirect, 'error');
});

test('same-origin explicit configuration and local-only HTTP preserve API base paths', async () => {
  for (const [href, base, expected] of [
    [`https://front.example.test/mia/?invitation=${token}`, '', 'https://front.example.test'],
    [`https://front.example.test/mia/?invitation=${token}`, 'https://api.example.test/service///', 'https://api.example.test/service'],
    [`http://127.0.0.1:5173/?invitation=${token}`, 'http://127.0.0.1:8000/service/', 'http://127.0.0.1:8000/service'],
  ]) {
    const { data, calls } = adapter({ href, config: { apiBaseUrl: base } });
    await data.load();
    assert.equal(calls[0][0], `${expected}/api/invitations/${token}`);
  }
});

test('load uses private fetch options, validates response and returns independent data', async () => {
  const { data, calls } = adapter();
  const first = await data.load();
  first.invitation.seats = 999;
  assert.equal((await data.load()).invitation.seats, 4);
  const options = calls[0][1];
  assert.equal(options.credentials, 'omit');
  assert.equal(options.cache, 'no-store');
  assert.equal(options.referrerPolicy, 'no-referrer');
  assert.equal(options.headers.Authorization, undefined);
  assert.equal(options.method, 'GET');
  assert.equal(options.body, undefined);
});

test('payload validation rejects invalid family data, dates, sections and injected URLs', async () => {
  const mutations = [
    (p) => { p.invitation.seats = 51; }, (p) => { p.invitation.seats = '4'; },
    (p) => { p.event.date = '2026-02-30'; }, (p) => { p.event.arrivalTime = '25:00'; },
    (p) => { delete p.sections; }, (p) => { p.sections.eventUtcOffset = 'bad'; },
    (p) => { p.sections.contact.whatsappNumber = 'javascript:alert(1)'; },
    (p) => { p.sections.bankTransfer = { alias: 'alias' }; },
    (p) => { p.rsvp = { attending: false, guestCount: 1, updatedAt: stamp }; },
    (p) => { p.wish = { author: 'other', message: 'text' }; },
  ];
  for (const mutate of mutations) {
    const invalid = payload(); mutate(invalid);
    const { data } = adapter({ fetcher: async () => response(invalid) });
    await assert.rejects(data.load(), /no es válida/);
  }
  const hiddenContact = payload(); hiddenContact.sections.contact.whatsappNumber = '';
  await adapter({ fetcher: async () => response(hiddenContact) }).data.load();
});

test('API errors use safe messages instead of reflecting server details or token', async () => {
  for (const status of [404, 409, 422, 429, 500, 503]) {
    const { data } = adapter({ fetcher: async () => response({ detail: `database password ${token}` }, status) });
    await assert.rejects(data.load(), (error) => error.status === status && !error.message.includes(token) && !error.message.includes('password'));
  }
  const { data } = adapter({ fetcher: async () => response('<html>not JSON</html>', 200, 'text/html') });
  await assert.rejects(data.load(), /no es válida/);
});

test('wish quota errors show the validated cap without exposing server details', async () => {
  const { data } = adapter({ fetcher: async (url, options) => options.method === 'POST'
    ? response({ code: 'wish_limit_reached', maxWishes: 10, detail: `secret ${token}` }, 409) : response(payload()) });
  await data.load();
  await assert.rejects(data.saveWish({ author: 'Ana', message: 'Un deseo' }), (error) =>
    error.status === 409 && error.message.includes('10 mensajes') && !error.message.includes(token));
  for (const maxWishes of ['10', '<script>', -1, 10000]) {
    const current = adapter({ fetcher: async (url, options) => options.method === 'POST'
      ? response({ code: 'wish_limit_reached', maxWishes, detail: `secret ${token}` }, 409) : response(payload()) });
    await current.data.load();
    await assert.rejects(current.data.saveWish({ author: 'Ana', message: 'Un deseo' }), (error) =>
      error.status === 409 && !error.message.includes('secret') && !error.message.includes('script'));
  }
});

test('ignored error and non-JSON bodies are cancelled instead of leaving fetch streams open', async () => {
  for (const [status, type] of [[404, 'application/json'], [200, 'text/html']]) {
    let cancelled = 0;
    const reply = response({ detail: 'private server details' }, status, type);
    reply.body = { cancel: async () => { cancelled += 1; } };
    const { data } = adapter({ fetcher: async () => reply });
    await assert.rejects(data.load());
    assert.equal(cancelled, 1);
  }
  const reply = response({}, 429);
  reply.body = { cancel: async () => { throw new Error('stream already closed'); } };
  const { data } = adapter({ fetcher: async () => reply });
  await assert.rejects(data.load(), (error) => error.status === 429);
});

test('API RSVP requires loaded data, sends only answer and never accepts fake success', async () => {
  const { data, calls } = adapter({ fetcher: async (url, options) => options.method === 'PUT'
    ? response({ attending: true, guestCount: 3, updatedAt: stamp }) : response(payload()) });
  await assert.rejects(data.saveRsvp({ attending: true, guestCount: 1 }), /cargar/);
  await data.load();
  await assert.rejects(data.saveRsvp({ attending: true, guestCount: 5 }), /hasta 4/);
  const saved = await data.saveRsvp({ attending: true, guestCount: 3 });
  assert.equal(saved.guestCount, 3);
  assert.equal(calls[1][0], `${apiUrl}/api/invitations/${token}/rsvp`);
  assert.equal(calls[1][1].body, JSON.stringify({ attending: true, guestCount: 3 }));
  const broken = adapter({ fetcher: async (url, options) => response(options.method === 'PUT' ? { attending: true, guestCount: 99, updatedAt: stamp } : payload()) });
  await broken.data.load();
  await assert.rejects(broken.data.saveRsvp({ attending: true, guestCount: 1 }), /no es válida/);
});

test('wish retries reuse request ID after uncertain failure; successful or edited drafts get a new ID', async () => {
  let fail = true;
  const { data, calls, uuidCalls } = adapter({ fetcher: async (url, options) => {
    if (options.method !== 'POST') return response(payload());
    if (fail) { fail = false; throw new Error('network failure with secrets'); }
    return response(wish(), 201);
  } });
  await data.load();
  const answer = { author: ' Ana ', message: ' Un hermoso festejo ' };
  await assert.rejects(data.saveWish(answer), /No pudimos conectar/);
  await data.saveWish(answer);
  const first = JSON.parse(calls[1][1].body), retried = JSON.parse(calls[2][1].body);
  assert.equal(first.clientRequestId, retried.clientRequestId);
  assert.equal(first.author, 'Ana');
  assert.equal(first.message, 'Un hermoso festejo');
  await data.saveWish(answer);
  assert.notEqual(JSON.parse(calls[3][1].body).clientRequestId, first.clientRequestId);
  fail = true;
  await assert.rejects(data.saveWish(answer));
  data.resetWishAttempt();
  await data.saveWish(answer);
  assert.notEqual(JSON.parse(calls[4][1].body).clientRequestId, JSON.parse(calls[5][1].body).clientRequestId);
  assert.equal(uuidCalls(), 4);
});

test('wish concurrent submit is rejected without creating a second write', async () => {
  let finish;
  const { data, calls } = adapter({ fetcher: async (url, options) => options.method === 'POST'
    ? new Promise((resolve) => { finish = () => resolve(response(wish(), 201)); }) : response(payload()) });
  await data.load();
  const pending = data.saveWish({ author: 'Ana', message: 'Un hermoso festejo' });
  await assert.rejects(data.saveWish({ author: 'Ana', message: 'Un hermoso festejo' }), /se está enviando/);
  finish(); await pending;
  assert.equal(calls.filter(([, options]) => options.method === 'POST').length, 1);
});

test('aborted request offers retry and does not return a preview family', async () => {
  const { data } = adapter({ timers: { setTimeout: (callback) => { callback(); return 0; }, clearTimeout: () => {} }, fetcher: async () => { throw new Error('aborted'); } });
  await assert.rejects(data.load(), /tardó demasiado/);
});

