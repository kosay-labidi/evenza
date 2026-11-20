/* =====================================================================
   Évenza · mouvement (sans dépendance)
   - titres qui montent mot par mot ([data-split] + grands titres)
   - images qui se dévoilent en rideau (.reveal-img)
   - parallaxe discrète ([data-parallax] img), seulement à l'écran
   - barre de progression de lecture
   Rien ne bouge si le visiteur a demandé « réduire les animations » ;
   sans JavaScript, tout reste visible.
   ===================================================================== */
(() => {
  const reduit = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---------- titres découpés en mots ----------
  function decouper(el) {
    if (el.dataset.decoupe) return; el.dataset.decoupe = '1';
    const texte = el.textContent.replace(/\s+/g, ' ').trim();
    let i = 0;
    const marcher = n => [...n.childNodes].forEach(c => {
      if (c.nodeType === 3) {
        const frag = document.createDocumentFragment();
        c.textContent.split(/(\s+)/).forEach(m => {
          if (!m) return;
          if (/^\s+$/.test(m)) { frag.appendChild(document.createTextNode(m)); return; }
          const o = document.createElement('span'); o.className = 'mot'; o.setAttribute('aria-hidden', 'true');
          const s = document.createElement('span'); s.textContent = m; s.style.setProperty('--i', i++);
          o.appendChild(s); frag.appendChild(o);
        });
        c.replaceWith(frag);
      } else if (c.nodeType === 1 && c.tagName !== 'BR') marcher(c);
    });
    marcher(el);
    // le texte complet reste lisible par les lecteurs d'écran
    const sr = document.createElement('span'); sr.className = 'sr-only'; sr.textContent = texte; el.appendChild(sr);
  }
  const titres = document.querySelectorAll('.page-banner h1, .detail-head-in h1, [data-split]');
  titres.forEach(t => { t.setAttribute('data-split', ''); if (!reduit) decouper(t); });
  window.evenzaDecouper = el => { el.setAttribute('data-split', ''); if (!reduit) { decouper(el); requestAnimationFrame(() => el.classList.add('vu')); } };

  // ---------- apparition au défilement ----------
  const cibles = document.querySelectorAll('[data-split], .reveal-img');
  if (reduit || !('IntersectionObserver' in window)) cibles.forEach(c => c.classList.add('vu'));
  else {
    // une image « rideau » est découpée (clip-path) : on observe son parent, lui visible
    const lien = new Map();
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (!e.isIntersecting) return;
      (lien.get(e.target) || []).forEach(c => c.classList.add('vu')); io.unobserve(e.target);
    }), { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
    cibles.forEach(c => {
      const t = c.classList.contains('reveal-img') ? c.parentElement : c;
      if (!lien.has(t)) { lien.set(t, []); io.observe(t); }
      lien.get(t).push(c);
    });
  }
  if (reduit) return;

  // ---------- parallaxe discrète + barre de progression ----------
  const para = [...document.querySelectorAll('[data-parallax] > img, .detail-head > img')];
  const visibles = new Set();
  if ('IntersectionObserver' in window) {
    const vo = new IntersectionObserver(es => es.forEach(e => e.isIntersecting ? visibles.add(e.target) : visibles.delete(e.target)), { rootMargin: '120px 0px' });
    para.forEach(i => { i.style.willChange = 'transform'; vo.observe(i.parentElement); i.parentElement._img = i; });
  }
  const barre = document.createElement('div'); barre.className = 'progress'; barre.setAttribute('aria-hidden', 'true'); document.body.appendChild(barre);
  let attente = false;
  const maj = () => {
    attente = false;
    const h = document.documentElement.scrollHeight - innerHeight;
    barre.style.transform = `scaleX(${h > 0 ? scrollY / h : 0})`;
    visibles.forEach(box => {
      const r = box.getBoundingClientRect(), k = (r.top + r.height / 2 - innerHeight / 2) / innerHeight; // -1 … 1
      const force = +(box.dataset.parallax || 6);
      box._img.style.transform = `translate3d(0, ${(-k * force).toFixed(2)}%, 0) scale(1.12)`;
    });
  };
  addEventListener('scroll', () => { if (!attente) { attente = true; requestAnimationFrame(maj); } }, { passive: true });
  addEventListener('resize', maj); maj();
})();
