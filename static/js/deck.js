/* Évenza · deck de cartes : glisser à la souris ou au doigt, flèches, points, clavier. */
(() => {
  const deck = document.getElementById('deck'); if (!deck) return;
  const cards = [...deck.querySelectorAll('.dcard')], dotsBox = document.getElementById('deckDots');
  const n = cards.length; let cur = 0, drag = 0, x0 = 0, moved = false, down = false;
  dotsBox.innerHTML = cards.map((_, i) => `<button type="button" aria-label="Carte ${i + 1}"></button>`).join('');
  const dots = [...dotsBox.children];

  function layout() {
    const w = cards[0].offsetWidth || 360, pos = cur - drag / (w * .9);
    cards.forEach((c, i) => {
      const d = i - pos, a = Math.abs(d);
      const x = d * w * (innerWidth < 700 ? .78 : .62), z = -a * 120, r = -d * 14, s = 1 - Math.min(a, 3) * .07;
      c.style.transform = `translateX(${x}px) translateZ(${z}px) rotateY(${r}deg) scale(${s})`;
      c.style.opacity = a > 2.6 ? 0 : 1 - a * .18;
      c.style.filter = `brightness(${1 - Math.min(a, 2) * .25})`;
      c.style.zIndex = 100 - Math.round(a * 10);
      c.setAttribute('aria-hidden', Math.round(a) !== 0);
    });
    const k = Math.round(Math.min(n - 1, Math.max(0, pos)));
    dots.forEach((d, i) => d.classList.toggle('on', i === k));
  }
  const go = i => { cur = Math.min(n - 1, Math.max(0, i)); drag = 0; layout(); };

  deck.addEventListener('pointerdown', e => { down = true; moved = false; x0 = e.clientX; deck.classList.add('dragging'); deck.setPointerCapture(e.pointerId); });
  deck.addEventListener('pointermove', e => { if (!down) return; drag = e.clientX - x0; if (Math.abs(drag) > 6) moved = true; layout(); });
  const up = e => {
    if (!down) return; down = false; deck.classList.remove('dragging');
    const w = cards[0].offsetWidth;
    if (moved) { go(Math.round(cur - drag / (w * .9))); return; }
    // simple clic : carte du centre -> page de l'événement ; carte de côté -> on la ramène au centre
    const c = document.elementsFromPoint(e.clientX, e.clientY).find(el => el.classList && el.classList.contains('dcard'));
    const i = cards.indexOf(c); drag = 0;
    if (i === cur) { const btn = document.elementsFromPoint(e.clientX, e.clientY).find(el => el.tagName === 'A'); location.href = btn ? btn.href : c.dataset.href; }
    else if (i >= 0) go(i); else layout();
  };
  deck.addEventListener('pointerup', up); deck.addEventListener('pointercancel', up);
  deck.querySelectorAll('a').forEach(a => a.addEventListener('click', e => e.preventDefault()));   // la navigation est gérée au relâchement
  deck.addEventListener('keydown', e => { if (e.key === 'ArrowRight') go(cur + 1); if (e.key === 'ArrowLeft') go(cur - 1); if (e.key === 'Enter') location.href = cards[cur].dataset.href; });
  document.getElementById('deckPrev').onclick = () => go(cur - 1);
  document.getElementById('deckNext').onclick = () => go(cur + 1);
  dots.forEach((d, i) => d.onclick = () => go(i));
  addEventListener('resize', layout);
  go(Math.min(1, n - 1));
})();
