/* Un único elemento audio: sin reproducción simultánea ni descargas anticipadas. */
(() => {
  function createPlayer(audio, entries, onChange = () => {}) {
    if (!Array.isArray(entries) || !entries.length || entries.some((track) => !track.src || !track.title)) {
      throw new Error('La playlist necesita al menos una pista válida.');
    }
    const tracks = entries.map((track) => Object.freeze({ ...track }));
    let index = 0;
    let generation = 0;
    let wantsPlayback = false;
    let loading = false;
    let error = null;
    let fade;

    audio.loop = false;
    audio.preload = 'none';
    audio.src = tracks[0].src;

    function state() {
      return Object.freeze({
        index, total: tracks.length, track: tracks[index],
        playing: !audio.paused && !audio.ended && !error,
        pending: wantsPlayback && loading,
        error,
      });
    }
    const notify = () => onChange(state());
    const stopFade = () => { clearInterval(fade); fade = undefined; };

    async function play() {
      const attempt = ++generation;
      stopFade();
      wantsPlayback = true;
      loading = true;
      error = null;
      if (audio.error) audio.load();
      audio.volume = 0;
      notify();
      try {
        // Must be reached directly from Ingresar / a playback control's click.
        await audio.play();
        if (attempt !== generation || !wantsPlayback) return false;
        loading = false;
        let step = 0;
        fade = setInterval(() => {
          if (attempt !== generation || audio.paused) { stopFade(); return; }
          audio.volume = Math.min(.55, .55 * (++step / 18));
          if (step >= 18) stopFade();
        }, 80);
        notify();
        return true;
      } catch {
        if (attempt !== generation) return false; // Superseded play/load, not a user-facing failure.
        wantsPlayback = false;
        loading = false;
        error = 'No pudimos reproducir esta canción. Podés reintentar o elegir otra.';
        stopFade();
        notify();
        return false;
      }
    }

    function pause() {
      generation += 1;
      wantsPlayback = false;
      loading = false;
      stopFade();
      audio.pause();
      notify();
    }

    function move(delta, autoplay = wantsPlayback && (loading || !audio.paused || audio.ended)) {
      generation += 1;
      wantsPlayback = false;
      loading = false;
      stopFade();
      audio.pause();
      index = (index + delta + tracks.length) % tracks.length;
      error = null;
      audio.src = tracks[index].src;
      audio.load();
      notify();
      return autoplay ? play() : Promise.resolve(false);
    }

    audio.addEventListener('play', notify);
    audio.addEventListener('pause', notify);
    audio.addEventListener('ended', () => { if (wantsPlayback) void move(1, true); });
    audio.addEventListener('error', () => {
      generation += 1;
      wantsPlayback = false;
      loading = false;
      error = 'No pudimos cargar esta canción. Podés reintentar o elegir otra.';
      stopFade();
      notify();
    });

    return Object.freeze({
      state, play, pause,
      next: () => move(1),
      previous: () => move(-1),
    });
  }
  window.InvitationAudio = Object.freeze({ createPlayer });
})();
