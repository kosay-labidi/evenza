/* =====================================================================
   Évenza · accueil « film »
   Une vraie vidéo plein écran qui avance ou recule avec la molette.
   - La vidéo est chargée entièrement en mémoire (blob) pour un défilement fluide.
   - Le temps de la vidéo suit le scroll avec un amortissement (mouvement doux).
   - Chaque plan du film = un chapitre qui présente une fonction d'Évenza.
   ===================================================================== */
(() => {
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const video = $('#film'), track = $('.scroll-track'), intro = $('.intro'), player = $('.player'), nav = $('.nav');
  const chaps = $$('.chap'), ticks = $$('.ticks button'), tc = $('#tc'), loader = $('#loader');
  const CH = JSON.parse($('#chapitres-data').textContent);           // [{debut, fin}, …] en secondes
  const DUREE = CH[CH.length - 1].fin;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const portrait = matchMedia('(max-aspect-ratio: 4/5)').matches;
  const src = portrait ? video.dataset.portrait : video.dataset.paysage;
  if (portrait) video.poster = video.dataset.posterPortrait;
  const fmt = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const sm = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  const fin = () => { loader.style.opacity = 0; setTimeout(() => loader.remove(), 900); };

  /* --- mode sans animation : simple vidéo en boucle, chapitres en liste --- */
  if (reduce) {
    document.body.classList.add('static');
    video.src = src; video.loop = true; video.play().catch(() => { });
    chaps.forEach(c => c.classList.add('on')); fin(); return;
  }

  /* --- chargement complet de la vidéo, avec barre de progression --- */
  const bar = $('#loader .bar i'), pct = $('#loader small');
  async function charger() {
    try {
      const r = await fetch(src); const total = +r.headers.get('content-length') || 0;
      const rd = r.body.getReader(); const parts = []; let n = 0;
      for (; ;) { const { done, value } = await rd.read(); if (done) break; parts.push(value); n += value.length;
        if (total) { bar.style.width = (n / total * 100) + '%'; pct.textContent = Math.round(n / total * 100) + ' %'; } }
      video.src = URL.createObjectURL(new Blob(parts, { type: 'video/mp4' }));
    } catch (e) { video.src = src; }                                     // repli : lecture directe
    video.load();
    await new Promise(ok => video.readyState >= 1 ? ok() : video.addEventListener('loadedmetadata', ok, { once: true }));
    video.pause(); video.currentTime = 0;
    fin();
  }
  charger();

  /* --- hauteur de défilement : ~120 vh par chapitre --- */
  track.style.setProperty('--track', (CH.length * 120 + 60) + 'vh');
  // largeur des repères proportionnelle à la durée de chaque plan
  ticks.forEach((b, i) => { b.style.setProperty('--w', CH[i].fin - CH[i].debut);
    b.addEventListener('click', () => { const y = track.offsetTop + (CH[i].debut + .05) / DUREE * (track.offsetHeight - innerHeight); scrollTo({ top: y, behavior: 'smooth' }); }); });

  let cible = 0, temps = 0, actif = -1;

  /* « Passer l'intro » : saut direct au contenu ; « Revoir le film » : retour au début */
  const apres = document.getElementById('apres'), skip = document.getElementById('skip');
  skip.addEventListener('click', () => { temps = DUREE; scrollTo({ top: apres.offsetTop - 40, behavior: 'instant' }); });
  document.getElementById('replay').addEventListener('click', () => { temps = 0; scrollTo({ top: 0, behavior: 'instant' }); });
  addEventListener('keydown', e => { if (e.key === 'Escape' && scrollY < apres.offsetTop - innerHeight) skip.click(); });
  const lire = () => { const max = track.offsetHeight - innerHeight; cible = Math.min(1, Math.max(0, (scrollY - track.offsetTop) / Math.max(1, max))); };
  addEventListener('scroll', lire, { passive: true }); addEventListener('resize', lire); lire();

  function boucle() {
    // amortissement : la vidéo rattrape le scroll en douceur
    const t = cible * DUREE;
    temps += (t - temps) * .085;
    if (Math.abs(temps - t) < .002) temps = t;
    if (video.readyState >= 2 && !video.seeking && Math.abs(video.currentTime - temps) > 1 / 60) video.currentTime = temps;

    const p = temps / DUREE, fondu = sm(.985, 1, cible) * sm(0, 1, (scrollY - (track.offsetTop + track.offsetHeight - innerHeight)) / (innerHeight * .6));
    // intro : le titre grossit et s'efface ; les bandes cinéma s'ouvrent
    const i0 = sm(0, .045, p);
    intro.style.opacity = 1 - i0; intro.style.transform = `scale(${1 + i0 * .35})`; intro.style.filter = `blur(${i0 * 8}px)`;
    document.documentElement.style.setProperty('--bar', (12 - 8 * sm(0, .05, p)) + 'vh');
    // léger travelling avant pendant tout le film, puis flou derrière le contenu
    video.style.setProperty('--zoom', (1.06 + .05 * Math.sin(p * Math.PI * CH.length)).toFixed(4));
    video.style.setProperty('--bright', (.8 - fondu * .35).toFixed(3));
    video.style.setProperty('--blur', (fondu * 6).toFixed(2) + 'px');
    player.style.opacity = (i0 * (1 - fondu)).toFixed(3);
    skip.style.opacity = (1 - fondu).toFixed(3); skip.style.pointerEvents = fondu > .5 ? 'none' : 'auto';
    $('.chapters').style.opacity = (1 - fondu).toFixed(3);

    // chapitre actif
    let k = CH.findIndex(c => temps >= c.debut && temps < c.fin); if (k < 0) k = temps >= DUREE - .01 ? CH.length - 1 : 0;
    const visible = p > .03;
    if (k !== actif || (visible !== !!chaps[k].classList.contains('on'))) { actif = k; chaps.forEach((c, j) => c.classList.toggle('on', visible && j === k)); }
    ticks.forEach((b, j) => b.firstElementChild.style.width = (Math.min(1, Math.max(0, (temps - CH[j].debut) / (CH[j].fin - CH[j].debut))) * 100) + '%');
    tc.textContent = `${fmt(temps)} / ${fmt(DUREE)}`;
    requestAnimationFrame(boucle);
  }
  requestAnimationFrame(boucle);
})();
