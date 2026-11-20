/* =====================================================================
   Évenza · intro vidéo facultative
   Une vraie vidéo plein écran (paysage sur ordinateur, portrait sur mobile),
   avec le nom Évenza et le slogan qui apparaissent par-dessus.
   - « Passer l'intro » ou Échap à tout moment
   - durée plafonnée par data-max (en secondes) sur la balise .intro
   - si la vidéo ne peut pas être lue, le site s'affiche directement
   - la page d'accueil est déjà chargée dessous : rien ne dépend de cette intro
   ===================================================================== */
(() => {
  const ctx = window.__evenzaIntro; if (!ctx) return;
  const { el } = ctx;
  const html = document.documentElement, main = document.getElementById('contenu');
  const video = el.querySelector('.intro-video');
  const btnGo = el.querySelector('[data-intro-go]'), btnSkip = el.querySelector('[data-intro-skip]');
  const btnSound = el.querySelector('[data-intro-sound]'), audio = el.querySelector('[data-intro-audio]');
  const MAX = parseFloat(el.dataset.max) || 14;
  const timers = [];
  let fini = false;

  // ---------- son d'ambiance (facultatif : static/audio/ambiance.mp3) ----------
  const son = (() => {
    if (!audio || !btnSound) return { stop() {} };
    audio.volume = 0.18; audio.muted = true;
    audio.addEventListener('error', () => { btnSound.hidden = true; }, { once: true });
    audio.addEventListener('canplaythrough', () => { btnSound.hidden = false; }, { once: true });
    audio.load();
    btnSound.addEventListener('click', () => {
      audio.muted = !audio.muted;
      if (!audio.muted) audio.play().catch(() => {});
      btnSound.textContent = audio.muted ? 'Son' : 'Muet';
      btnSound.setAttribute('aria-pressed', String(!audio.muted));
    });
    audio.play().catch(() => {});
    return { stop() { audio.pause(); } };
  })();

  // ---------- fin de l'intro : retour au site ----------
  function fin(rapide) {
    if (fini) return; fini = true;
    try { sessionStorage.setItem('evenza-intro', 'vue'); } catch (e) {}
    timers.forEach(clearTimeout);
    removeEventListener('keydown', clavier);
    const d = rapide ? 450 : 900;
    el.style.transition = `opacity ${d}ms ease`; el.style.opacity = '0'; el.classList.add('fin');
    html.classList.add('intro-revele');
    setTimeout(() => {
      video.pause(); video.removeAttribute('src'); video.load();   // libère la mémoire
      son.stop();
      el.remove(); html.classList.remove('intro-on');
      if (main) main.inert = false;
      const t = document.getElementById('mx-titre');
      if (t) { t.setAttribute('tabindex', '-1'); t.focus({ preventScroll: true }); }
    }, d + 10);
  }
  window.__evenzaIntroFin = () => fin(true);
  btnSkip.addEventListener('click', () => fin(true));
  btnGo.addEventListener('click', () => fin(false));

  function clavier(e) {
    if (e.key === 'Escape') fin(true);
    if (e.key === 'Tab') { // la focalisation reste dans l'intro
      const b = [btnGo, btnSkip, btnSound].filter(x => x && !x.hidden && x.offsetParent !== null && getComputedStyle(x).visibility !== 'hidden');
      if (!b.length) return;
      const i = b.indexOf(document.activeElement);
      e.preventDefault(); b[(i + (e.shiftKey ? -1 : 1) + b.length) % b.length].focus();
    }
  }
  addEventListener('keydown', clavier);
  btnSkip.focus({ preventScroll: true });

  // ---------- la vidéo ----------
  const portrait = matchMedia('(max-aspect-ratio: 4/5)').matches;
  video.poster = portrait ? video.dataset.posterPortrait : video.dataset.posterPaysage;
  const webm = video.canPlayType('video/webm; codecs="vp9"') !== '' && (portrait ? video.dataset.portraitWebm : video.dataset.paysageWebm);
  video.src = webm || (portrait ? video.dataset.portrait : video.dataset.paysage);
  video.preload = 'auto';
  video.addEventListener('error', () => fin(true), { once: true });

  video.addEventListener('playing', () => {
    if (el.classList.contains('pret')) return;
    el.classList.add('pret');
    // apparitions du texte, calées sur la durée de l'intro
    const duree = Math.min(MAX, isFinite(video.duration) && video.duration > 0 ? video.duration : MAX);
    const a = (cls, s) => timers.push(setTimeout(() => el.classList.add(cls), s * 1000));
    a('t-brand', 0.8);
    a('t-line', 1.8);
    a('t-go', Math.max(2.6, duree - 3.5));
    timers.push(setTimeout(() => { if (document.activeElement === btnSkip) btnGo.focus({ preventScroll: true }); }, Math.max(2.6, duree - 3.5) * 1000 + 50));
    // fin automatique : à la fin de la vidéo ou à data-max secondes (suit le temps réel de la vidéo)
    video.addEventListener('timeupdate', () => { if (video.currentTime >= duree - 0.3) fin(false); });
  });
  video.addEventListener('ended', () => fin(false), { once: true });

  // onglet masqué : on met en pause pour ne pas « rater » l'intro
  document.addEventListener('visibilitychange', () => {
    if (fini) return;
    if (document.hidden) video.pause(); else video.play().catch(() => {});
  });

  const p = video.play();
  if (p && p.catch) p.catch(() => fin(true));   // lecture automatique refusée : on montre le site
})();
