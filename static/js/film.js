/* =====================================================================
   Évenza · film « Un soir en Méditerranée » (30 s, Ken Burns)
   Une séquence légère de 6 plans (photos des catégories), sans fichier vidéo :
   zoom/pan CSS, étalonnage (filtre + courbe en S), grain, vignette et des
   transitions variées (balayage, fondu croisé, zoom-through, rideau).
   - Muette par défaut : l'ambiance ne joue que si le fichier audio existe.
   - Lue à la demande : « ?film=1 » ou un lien « Revoir le film » ([data-film]).
   - « réduire les animations » : un seul plan statique, sans Ken Burns.
   ===================================================================== */
(() => {
  const box = document.getElementById('film');
  if (!box) return;
  const html = document.documentElement;
  const main = document.getElementById('contenu');
  const reduit = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const DUREE = 5000; // durée d'un plan (6 × 5 s = 30 s)
  const imgs = (box.dataset.img || '').split('|').filter(Boolean);
  const audioSrc = box.dataset.audio || '';

  // Un plan par photo : chaque transition a son effet ; le concert est désaturé.
  const PLANS = [
    { src: imgs[0], mod: 'balaye' },
    { src: imgs[1], mod: 'fondu' },
    { src: imgs[2], mod: 'zoom' },
    { src: imgs[3], mod: 'rideau', concert: true },
    { src: imgs[4], mod: 'balaye-rev' },
    { src: imgs[5] || imgs[0], mod: 'fondu' }
  ].filter(p => p.src);
  if (!PLANS.length) return;

  let actif = false, dom = null, plan = 0, timer = 0, son = { stop() {} };

  // ---------- construction du plateau (une seule fois par lecture) ----------
  function construire() {
    const stage = document.createElement('div');
    stage.className = 'film-stage';
    PLANS.forEach((p, i) => {
      const fig = document.createElement('figure');
      fig.className = 'film-plan film-plan--' + p.mod + (p.concert ? ' plan-concert' : '');
      const img = document.createElement('img');
      img.src = p.src; img.alt = ''; img.decoding = 'async';
      if (i > 0) img.loading = 'lazy';
      fig.appendChild(img); stage.appendChild(fig);
    });
    box.appendChild(stage);

    // étalonnage : courbe en S appliquée au plateau via feComponentTransfer
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'film-svg');
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = '<filter id="film-scurve"><feComponentTransfer>' +
      '<feFuncR type="table" tableValues="0 .06 .24 .56 .88 1"/>' +
      '<feFuncG type="table" tableValues="0 .05 .21 .53 .86 1"/>' +
      '<feFuncB type="table" tableValues="0 .04 .19 .50 .84 1"/>' +
      '</feComponentTransfer></filter>';
    box.appendChild(svg);

    const grain = document.createElement('div');
    grain.className = 'film-grain'; grain.setAttribute('aria-hidden', 'true');
    const vig = document.createElement('div');
    vig.className = 'film-vignette'; vig.setAttribute('aria-hidden', 'true');
    box.appendChild(grain); box.appendChild(vig);

    const titre = document.createElement('p');
    titre.className = 'film-title'; titre.textContent = 'Un soir en Méditerranée';
    box.appendChild(titre);

    const sonBtn = document.createElement('button');
    sonBtn.type = 'button'; sonBtn.className = 'film-sound';
    sonBtn.setAttribute('aria-pressed', 'false'); sonBtn.hidden = true; sonBtn.textContent = 'Son';
    box.appendChild(sonBtn);

    const ferme = document.createElement('button');
    ferme.type = 'button'; ferme.className = 'film-skip';
    ferme.innerHTML = 'Fermer <span aria-hidden="true">✕</span>';
    box.appendChild(ferme);

    const audio = document.createElement('audio');
    audio.preload = 'none'; audio.loop = true; audio.setAttribute('aria-hidden', 'true');
    audio.volume = 0.5; audio.muted = true;
    if (audioSrc) audio.src = audioSrc;
    box.appendChild(audio);

    return { plans: [].slice.call(stage.children), sonBtn, ferme, audio };
  }

  // ---------- son : muet par défaut, silence si le fichier est absent ----------
  function brancherSon(audio, btn) {
    if (!audioSrc) { btn.hidden = true; return { stop() {} }; }
    audio.addEventListener('error', () => { btn.hidden = true; if (audio.parentNode) audio.remove(); }, { once: true });
    audio.addEventListener('canplaythrough', () => { btn.hidden = false; }, { once: true });
    audio.load();
    btn.addEventListener('click', () => {
      audio.muted = !audio.muted;
      if (!audio.muted) audio.play().catch(() => {});
      btn.textContent = audio.muted ? 'Son' : 'Muet';
      btn.setAttribute('aria-pressed', String(!audio.muted));
    });
    audio.play().catch(() => {});
    return { stop() { audio.pause(); } };
  }

  // ---------- ouverture / fermeture ----------
  function ouvrir() {
    if (actif) return;
    actif = true; plan = 0;
    dom = construire();
    son = brancherSon(dom.audio, dom.sonBtn);
    box.hidden = false;
    html.classList.add('film-on');
    if (main) main.inert = true;
    dom.ferme.addEventListener('click', fermer);
    addEventListener('keydown', clavier);
    requestAnimationFrame(() => {
      box.classList.add('on');
      montrer(0);
      dom.ferme.focus({ preventScroll: true });
    });
    // un seul plan statique si « réduire les animations »
    if (!reduit && dom.plans.length > 1) timer = setInterval(suivant, DUREE);
  }
  function suivant() {
    plan += 1;
    if (plan >= PLANS.length) { fermer(); return; }
    montrer(plan);
  }
  function montrer(i) { const p = dom && dom.plans[i]; if (p) p.classList.add('on'); }
  function clavier(e) { if (e.key === 'Escape') fermer(); }
  function fermer() {
    if (!actif) return;
    if (timer) { clearInterval(timer); timer = 0; }
    removeEventListener('keydown', clavier);
    son.stop();
    box.classList.remove('on'); box.classList.add('fin');
    if (main) main.inert = false;
    const fin = () => {
      html.classList.remove('film-on');
      box.hidden = true; box.innerHTML = '';
      box.classList.remove('fin');
      dom = null; plan = 0; actif = false;
      if (location.search.indexOf('film=') !== -1) {
        try { history.replaceState(null, '', location.pathname + location.hash); } catch (e) {}
        const t = document.getElementById('mx-titre');
        if (t) { t.setAttribute('tabindex', '-1'); t.focus({ preventScroll: true }); }
      }
    };
    setTimeout(fin, reduit ? 20 : 620);
  }

  // ---------- déclencheurs : « ?film=1 » ou lien « Revoir le film » ----------
  if (new URLSearchParams(location.search).get('film') === '1') ouvrir();
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-film]');
    if (!a) return;
    e.preventDefault();
    ouvrir();
  });
})();
