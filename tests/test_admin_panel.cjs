const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { resolveConfig, invitationUrl, invitationState } = require('../admin.js');

test('panel fails closed without explicit backend configuration', () => {
  for (const config of [undefined, {}, { apiBaseUrl: null }, { apiBaseUrl: 42 }]) {
    assert.throws(() => resolveConfig(config, 'https://example.com/mia/admin.html'), /servidor configurado/);
  }
});

test('backend permits secure hosts and loopback-only local HTTP', () => {
  const result = resolveConfig({ apiBaseUrl: 'https://api.example.com/base/' }, 'https://example.com/mia/admin.html');
  assert.equal(result.apiBaseUrl, 'https://api.example.com/base');
  assert.equal(result.invitationBaseUrl, 'https://example.com/mia/');
  assert.equal(resolveConfig({ apiBaseUrl: '' }, 'https://example.com/mia/admin.html').apiBaseUrl, 'https://example.com');
  assert.equal(resolveConfig({ apiBaseUrl: 'http://127.0.0.1:8000' }, 'http://localhost:5173/admin.html').apiBaseUrl, 'http://127.0.0.1:8000');
  for (const page of ['http://panel.example.com/admin.html', 'file:///tmp/admin.html']) {
    assert.throws(() => resolveConfig({ apiBaseUrl: 'https://api.example.com', invitationBaseUrl: 'https://front.example.com/' }, page), /página HTTPS/);
  }
  for (const apiBaseUrl of ['javascript:alert(1)', 'http://api.example.com', 'https://user:password@example.com', 'https://api.example.com?key=secret', 'https://api.example.com#secret', 'http://127.0.0.1:8000', ' https://example.com', 'https://example.com\n', 'https://example.com\\path']) {
    assert.throws(() => resolveConfig({ apiBaseUrl }, 'https://example.com/mia/admin.html'));
  }
});

test('private links preserve the frontend project subpath, not API invitationPath', () => {
  const config = resolveConfig({ apiBaseUrl: 'https://api.example.com', invitationBaseUrl: 'https://example.com/invitacion-mia/index.html' }, 'https://example.com/invitacion-mia/admin.html');
  const token = 'a'.repeat(43);
  assert.equal(invitationUrl(token, config.invitationBaseUrl, 'https://example.com/invitacion-mia/admin.html'), `https://example.com/invitacion-mia/?invitation=${token}`);
  for (const bad of ['', '../foo', '<script>', 'a'.repeat(42), null]) assert.throws(() => invitationUrl(bad, config.invitationBaseUrl, 'https://example.com/'));
});

test('states distinguish inactive, pending, declined and confirmed including 0', () => {
  assert.equal(invitationState({ active: false, rsvp: { attending: true, guestCount: 2 } }).key, 'inactive');
  assert.equal(invitationState({ active: true, rsvp: null }).key, 'pending');
  assert.equal(invitationState({ active: true, rsvp: { attending: false, guestCount: 0 } }).key, 'declined');
  assert.equal(invitationState({ active: true, rsvp: { attending: true, guestCount: 1 } }).key, 'confirmed');
});

test('panel has no browser credential storage, HTML injection, auto-retry or URL-supplied API', () => {
  const source = fs.readFileSync(path.join(__dirname, '../admin.js'), 'utf8');
  for (const forbidden of ['localStorage', 'document.cookie', 'innerHTML', 'insertAdjacentHTML', 'location.search', 'console.log']) assert.equal(source.includes(forbidden), false, forbidden);
  assert.ok(source.includes("credentials: 'include'"));
  assert.ok(source.includes("'X-CSRF-Token'"));
  assert.ok(source.includes("'mia.admin.logoutPending'"));
  assert.equal((source.match(/sessionStorage\.setItem\(/g) || []).length, 1);
  assert.ok(source.includes("sessionStorage.setItem(LOGOUT_PENDING, '1')"));
  assert.ok(source.includes("redirect: 'error'"));
  assert.ok(source.includes("referrerPolicy: 'no-referrer'"));
});

test('family links can only be copied, never rendered or stored in form fields', () => {
  const source = fs.readFileSync(path.join(__dirname, '../admin.js'), 'utf8');
  const html = fs.readFileSync(path.join(__dirname, '../admin.html'), 'utf8');
  assert.equal(html.includes('id="link-dialog"'), false);
  assert.equal(html.includes('id="invitation-link"'), false);
  assert.equal(source.includes('showLink('), false);
  assert.ok(source.includes('navigator.clipboard.writeText(value)'));
  assert.ok(source.includes('card.isConnected'));
  assert.ok(source.includes('currentCopy === copyEpoch'));
});
