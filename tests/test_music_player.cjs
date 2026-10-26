const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeAudio extends EventTarget {
  paused = true;
  ended = false;
  error = null;
  currentTime = 0;
  volume = 1;
  playCalls = 0;
  loadCalls = 0;
  playBehavior = null;
  play() {
    this.playCalls += 1;
    this.paused = false;
    this.dispatchEvent(new Event('play'));
    return this.playBehavior ? this.playBehavior() : Promise.resolve();
  }
  pause() { this.paused = true; this.dispatchEvent(new Event('pause')); }
  load() { this.loadCalls += 1; this.paused = true; this.ended = false; this.error = null; this.currentTime = 0; }
  finish() { this.ended = true; this.paused = true; this.dispatchEvent(new Event('ended')); }
}

function setup() {
  const window = {};
  const timers = new Map();
  let id = 0;
  const context = { window, setInterval: (fn) => { timers.set(++id, fn); return id; }, clearInterval: (key) => timers.delete(key) };
  for (const file of ['music-playlist.js', 'music-player.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), context);
  }
  const audio = new FakeAudio();
  const snapshots = [];
  const player = window.InvitationAudio.createPlayer(audio, window.InvitationPlaylist, (state) => snapshots.push(state));
  return { window, audio, player, snapshots, timers, tick: () => [...timers.values()].forEach(fn => fn()) };
}

test('three specific tracks preserve the approved opener, with no autoplay or preload', () => {
  const { window, audio, player } = setup();
  assert.equal(window.InvitationPlaylist.length, 3);
  assert.equal(audio.src, './assets/mia-soundtrack.mp3?v=trim9');
  assert.equal(audio.preload, 'none');
  assert.equal(audio.loop, false);
  assert.equal(audio.loadCalls, 0);
  assert.equal(audio.playCalls, 0);
  assert.equal(player.state().index, 0);
  assert.equal(player.state().total, 3);
  assert.ok(window.InvitationPlaylist.every(track => !track.source.includes('list=') && fs.existsSync(path.join(__dirname, '..', track.src.split('?')[0]))));
  assert.throws(() => window.InvitationAudio.createPlayer(audio, []), /playlist/);
});

test('play fades gently, pause stops the fade, resume keeps position', async () => {
  const { audio, player, tick, timers } = setup();
  assert.equal(await player.play(), true);
  assert.equal(audio.volume, 0);
  for (let step = 0; step < 18; step += 1) tick();
  assert.equal(audio.volume, .55);
  assert.equal(timers.size, 0);
  audio.currentTime = 42;
  player.pause();
  assert.equal(audio.paused, true);
  await player.play();
  assert.equal(audio.currentTime, 42);
  assert.equal(audio.loadCalls, 0);
  player.pause();
  assert.equal(timers.size, 0);
});

test('next and previous wrap the playlist and keep playing', async () => {
  const { audio, player, timers } = setup();
  await player.play();
  await player.next();
  assert.equal(player.state().index, 1);
  assert.ok(audio.src.endsWith('mia-my-one-and-only-love.mp3'));
  await player.next();
  assert.equal(player.state().track.title, 'UNDERSTAND');
  await player.next();
  assert.equal(player.state().index, 0);
  await player.previous();
  assert.equal(player.state().index, 2);
  assert.equal(audio.paused, false);
  assert.equal(timers.size, 1, 'Only the latest fade can run');
});

test('navigation while paused changes the track without starting audio', async () => {
  const { audio, player } = setup();
  await player.next();
  assert.equal(player.state().index, 1);
  assert.equal(audio.playCalls, 0);
  assert.equal(audio.paused, true);
  await player.previous();
  await player.previous();
  assert.equal(player.state().index, 2);
  assert.equal(audio.playCalls, 0);
});

test('ended advances automatically, including third back to first', async () => {
  const { audio, player } = setup();
  await player.play();
  audio.finish();
  await Promise.resolve();
  assert.equal(player.state().index, 1);
  assert.equal(audio.paused, false);
  await player.next();
  audio.finish();
  await Promise.resolve();
  assert.equal(player.state().index, 0);
});

test('rapid skip ignores an obsolete play rejection and leaves one fade', async () => {
  const { audio, player, timers } = setup();
  let reject;
  audio.playBehavior = () => new Promise((_, fail) => { reject = fail; });
  const old = player.play();
  audio.playBehavior = null;
  await player.next();
  await player.next();
  reject(new Error('The old play was interrupted by load'));
  assert.equal(await old, false);
  assert.equal(player.state().index, 2);
  assert.equal(player.state().error, null);
  assert.equal(player.state().playing, true);
  assert.equal(timers.size, 1);
});

test('pause during pending play prevents a late fade or restart', async () => {
  const { audio, player, timers } = setup();
  let resolve;
  audio.playBehavior = () => new Promise(done => { resolve = done; });
  const pending = player.play();
  player.pause();
  resolve();
  assert.equal(await pending, false);
  assert.equal(player.state().pending, false);
  assert.equal(player.state().playing, false);
  assert.equal(timers.size, 0);
});

test('play failure is recoverable and never auto-skips in an error loop', async () => {
  const { audio, player, timers } = setup();
  audio.playBehavior = () => Promise.reject(new Error('NotAllowedError'));
  assert.equal(await player.play(), false);
  assert.ok(player.state().error);
  assert.equal(player.state().index, 0);
  assert.equal(timers.size, 0);
  audio.playBehavior = null;
  assert.equal(await player.play(), true);
  audio.error = { code: 4 };
  audio.dispatchEvent(new Event('error'));
  assert.ok(player.state().error);
  assert.equal(player.state().index, 0);
  assert.equal(timers.size, 0);
  await player.next();
  assert.equal(player.state().error, null);
  assert.equal(player.state().index, 1);
  assert.equal(audio.paused, true);
});
