// ===== Évenza · scripts communs (sans dépendance) =====
(() => {
  const html = document.documentElement;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- panneaux à ouvrir (menu mobile, barre latérale) : [data-toggle="id"] ----------
  const fermer = (btn, panel) => {
    panel.classList.remove("open"); btn.setAttribute("aria-expanded", "false");
    if (btn.dataset.labelOpen) btn.setAttribute("aria-label", btn.dataset.labelOpen);
    html.classList.remove("menu-open");
  };
  document.querySelectorAll("[data-toggle]").forEach(btn => {
    const panel = document.getElementById(btn.dataset.toggle); if (!panel) return;
    btn.dataset.labelOpen = btn.getAttribute("aria-label") || "";
    btn.addEventListener("click", () => {
      const open = panel.classList.toggle("open");
      btn.setAttribute("aria-expanded", open);
      btn.setAttribute("aria-label", open ? "Fermer le menu" : btn.dataset.labelOpen);
      html.classList.toggle("menu-open", open);
      if (open) { const f = panel.querySelector("a, button"); if (f) setTimeout(() => f.focus({ preventScroll: true }), 250); }
    });
    // un lien cliqué ferme le panneau
    panel.addEventListener("click", e => { if (e.target.closest("a")) fermer(btn, panel); });
    document.addEventListener("keydown", e => { if (e.key === "Escape" && panel.classList.contains("open")) { fermer(btn, panel); btn.focus(); } });
  });
  document.querySelectorAll("[data-close]").forEach(el => el.addEventListener("click", () => {
    const btn = document.querySelector(`[data-toggle="${el.dataset.close}"]`), panel = document.getElementById(el.dataset.close);
    if (btn && panel) fermer(btn, panel);
  }));

  // ---------- menu du compte : fermer en cliquant ailleurs ou avec Échap ----------
  document.addEventListener("click", e => {
    document.querySelectorAll(".user-menu[open]").forEach(d => { if (!d.contains(e.target)) d.removeAttribute("open"); });
  });
  document.addEventListener("keydown", e => {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".user-menu[open]").forEach(d => { d.removeAttribute("open"); d.querySelector("summary").focus(); });
  });

  // ---------- menu : fond crème après 60 px, se cache en descendant, revient en remontant ----------
  const nav = document.getElementById("nav");
  if (nav) {
    let y0 = scrollY, attente = false;
    const maj = () => {
      attente = false;
      const y = scrollY, ouvert = document.querySelector(".nav-links.open, .user-menu[open]");
      nav.classList.toggle("scrolled", y > 60);
      if (!ouvert && y > 480 && y > y0 + 6) nav.classList.add("hide");
      if (y < y0 - 6 || y < 480) nav.classList.remove("hide");
      y0 = y;
    };
    addEventListener("scroll", () => { if (!attente) { attente = true; requestAnimationFrame(maj); } }, { passive: true });
    maj();
  }

  // ---------- apparitions au défilement (.reveal, .stagger) + compteurs (data-count) ----------
  const compter = el => {
    const fin = +el.dataset.count;
    if (reduce || !fin) { el.textContent = el.dataset.count; return; }
    const t0 = performance.now(), d = 1600;
    const pas = t => { const k = Math.min(1, (t - t0) / d), e = 1 - Math.pow(1 - k, 4); el.textContent = Math.round(fin * e); if (k < 1) requestAnimationFrame(pas); };
    requestAnimationFrame(pas);
  };
  const els = document.querySelectorAll(".reveal, .stagger");
  if (reduce || !("IntersectionObserver" in window)) {
    els.forEach(e => e.classList.add("in"));
    document.querySelectorAll("[data-count]").forEach(compter);
  } else {
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (!e.isIntersecting) return;
      e.target.classList.add("in");
      e.target.querySelectorAll("[data-count]").forEach(compter);
      io.unobserve(e.target);
    }), { threshold: .12, rootMargin: "0px 0px -40px 0px" });
    els.forEach(e => io.observe(e));
    // compteurs hors .reveal
    document.querySelectorAll("[data-count]").forEach(c => { if (!c.closest(".reveal, .stagger")) { c.closest("section") ? io.observe(c.closest("section")) : compter(c); } });
  }

  // ---------- accordéon accessible : [data-accordion] > .acc-item > .acc-btn + .acc-panel ----------
  document.querySelectorAll("[data-accordion]").forEach(acc => {
    const btns = () => [...acc.querySelectorAll(".acc-btn")].filter(b => !b.closest(".acc-item").hidden);
    acc.addEventListener("click", e => {
      const b = e.target.closest(".acc-btn"); if (!b) return;
      const item = b.closest(".acc-item"), open = !item.classList.contains("open");
      if (acc.dataset.accordion === "single") acc.querySelectorAll(".acc-item.open").forEach(i => { if (i !== item) { i.classList.remove("open"); i.querySelector(".acc-btn").setAttribute("aria-expanded", "false"); } });
      item.classList.toggle("open", open); b.setAttribute("aria-expanded", open);
    });
    acc.addEventListener("keydown", e => {
      const b = e.target.closest(".acc-btn"); if (!b) return;
      const l = btns(), i = l.indexOf(b);
      const cible = { ArrowDown: l[(i + 1) % l.length], ArrowUp: l[(i - 1 + l.length) % l.length], Home: l[0], End: l[l.length - 1] }[e.key];
      if (cible) { e.preventDefault(); cible.focus(); }
    });
  });

  // ---------- filtres de galerie : [data-filtres] boutons [data-f] → éléments [data-cat] ----------
  document.querySelectorAll("[data-filtres]").forEach(bar => {
    const cible = document.getElementById(bar.dataset.filtres); if (!cible) return;
    bar.addEventListener("click", e => {
      const b = e.target.closest("[data-f]"); if (!b) return;
      bar.querySelectorAll("[data-f]").forEach(x => x.setAttribute("aria-pressed", x === b));
      const f = b.dataset.f;
      cible.querySelectorAll("[data-cat]").forEach(it => {
        const ok = f === "*" || it.dataset.cat === f;
        it.classList.toggle("off", !ok);
        it.setAttribute("aria-hidden", !ok);
        it.querySelectorAll("a").forEach(a => ok ? a.removeAttribute("tabindex") : a.setAttribute("tabindex", "-1"));
      });
    });
  });

  // ---------- les messages de succès disparaissent après 6 secondes ----------
  setTimeout(() => document.querySelectorAll(".msg.success").forEach(m => {
    m.style.transition = "opacity .5s, transform .5s"; m.style.opacity = 0; m.style.transform = "translateY(-6px)";
    setTimeout(() => m.remove(), 500);
  }), 6000);
})();
