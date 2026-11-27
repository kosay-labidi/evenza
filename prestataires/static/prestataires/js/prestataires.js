/* =====================================================================
   Gestion des prestataires · interactions (sans bibliothèque)
   - L4 inclinaison + reflet des cartes (souris uniquement)
   - D2 anneau « taux de confirmation » qui se dessine
   - F2 aperçu en direct de la carte · F5 dépôt de photo avec aperçu
   - K1 Kanban : glisser-déposer + boutons ✓ / ✕, envoi sans rechargement
   Rien ne bouge si « réduire les animations » est activé ; sans JS, tout marche (formulaires classiques).
   ===================================================================== */
(() => {
  const reduit = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduit) document.documentElement.classList.add("pr-motion");

  /* ---------- L4 · inclinaison + reflet doré ---------- */
  if (!reduit && matchMedia("(hover: hover) and (pointer: fine)").matches) {
    document.querySelectorAll("[data-pr-tilt]").forEach(carte => {
      let rafId = 0;
      carte.addEventListener("pointermove", e => {
        cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(() => {
          const r = carte.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
          carte.style.setProperty("--mx", `${x * 100}%`);
          carte.style.setProperty("--my", `${y * 100}%`);
          carte.style.transform = `perspective(900px) rotateX(${((0.5 - y) * 5).toFixed(2)}deg) rotateY(${((x - 0.5) * 5).toFixed(2)}deg) translateY(-4px)`;
        });
      });
      carte.addEventListener("pointerleave", () => { cancelAnimationFrame(rafId); carte.style.transform = ""; });
    });
  }

  /* ---------- D2 · anneau qui se dessine quand il devient visible ---------- */
  const anneaux = document.querySelectorAll(".pr-anneau");
  if (reduit || !("IntersectionObserver" in window)) anneaux.forEach(a => a.classList.add("vu"));
  else {
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting) { e.target.classList.add("vu"); io.unobserve(e.target); }
    }), { threshold: 0.4 });
    anneaux.forEach(a => io.observe(a));
  }

  /* ---------- F3 · téléphone tunisien : mise en forme « 22 123 456 » + message clair ----------
     Mêmes règles que prestataires/telephone.py (le serveur vérifie toujours, ce script n'aide qu'à la saisie). */
  const telChiffres = v => {
    const b = (v || "").replace(/[\s.\-]/g, "");
    for (const ind of ["+216", "00216"]) if (b.startsWith(ind)) return b.slice(ind.length);
    return b;
  };
  const telFormat = n => [n.slice(0, 2), n.slice(2, 5), n.slice(5, 8)].filter(Boolean).join(" ");
  const telErreur = v => {
    const n = telChiffres(v);
    if (!/^\d{8}$/.test(n)) return "Le numéro doit contenir 8 chiffres.";
    if (!"234579".includes(n[0])) return "Ce numéro n'est pas un numéro tunisien valide.";
    return "";
  };
  const telAffiche = v => (v.trim() && !telErreur(v) ? telFormat(telChiffres(v)) : v.trim());
  document.querySelectorAll("[data-pr-tel]").forEach(champ => {
    const bloc = champ.closest(".pr-field");
    const afficher = texte => {
      let msg = bloc && bloc.querySelector("[data-pr-tel-err]");
      if (bloc) bloc.querySelectorAll(".pr-err:not([data-pr-tel-err])").forEach(e => e.remove());   // ancien message serveur
      if (texte && bloc && !msg) {
        msg = document.createElement("small"); msg.className = "pr-err"; msg.setAttribute("role", "alert");
        msg.dataset.prTelErr = ""; bloc.appendChild(msg);
      }
      if (msg) { msg.textContent = texte; msg.hidden = !texte; }
      if (bloc) bloc.classList.toggle("has-error", !!texte);
      champ.setAttribute("aria-invalid", texte ? "true" : "false");
    };
    champ.addEventListener("input", () => {
      const v = champ.value;
      if (/^\s*(\+|0{2})/.test(v)) return;            // indicatif en cours de saisie : mis en forme à la sortie du champ
      const pos = champ.selectionStart ?? v.length;
      const avant = v.slice(0, pos).replace(/\D/g, "").length;   // chiffres avant le curseur
      const f = telFormat(v.replace(/\D/g, "").slice(0, 8));
      if (f !== v) {
        champ.value = f;
        let p = 0, vus = 0;
        while (p < f.length && vus < avant) { if (/\d/.test(f[p])) vus++; p++; }
        champ.setSelectionRange(p, p);
      }
      if (!telErreur(champ.value)) afficher("");
    });
    champ.addEventListener("blur", () => {
      const v = champ.value.trim();
      if (!v) return;
      const err = telErreur(v);
      if (!err) champ.value = telFormat(telChiffres(v));
      afficher(err);
      champ.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });

  /* ---------- F2 · aperçu en direct ---------- */
  const form = document.querySelector("[data-pr-form]");
  const apercu = document.querySelector("[data-pr-apercu]");
  const initiales = nom => nom.split(/\s+/).filter(m => /^[\p{L}\p{N}]/u.test(m)).slice(0, 2)
    .map(m => m[0]).join("").toUpperCase() || "?";
  if (form && apercu) {
    const $ = s => apercu.querySelector(s);
    const nom = form.querySelector("[name=nom]"), tel = form.querySelector("[name=telephone]");
    const cover = $("[data-pr-apercu-cover]"), chip = $("[data-pr-apercu-chip]"), tags = $("[data-pr-apercu-tags]");
    const ini = $("[data-pr-apercu-initiales]"), photo = $("[data-pr-apercu-photo]");
    const majTexte = () => {
      const n = nom.value.trim();
      $("[data-pr-apercu-nom]").textContent = n || "Nom du prestataire";
      ini.textContent = initiales(n);
      $("[data-pr-apercu-tel]").textContent = (tel && telAffiche(tel.value)) || "Téléphone non renseigné";
    };
    const majServices = () => {
      const coches = [...form.querySelectorAll("[name=services]:checked")].map(i => i.closest("[data-type]"));
      tags.replaceChildren(...[...new Set(coches.map(l => l.dataset.type))].map(t => {
        const li = document.createElement("li"); li.className = "pr-tag"; li.textContent = t; return li;
      }));
      chip.hidden = !coches.length; chip.textContent = coches.length ? coches[0].dataset.type : "";
      const src = coches.length ? coches[0].dataset.cover : cover.dataset.defaut;
      if (src && !cover.src.endsWith(src)) {
        cover.src = src;
        if (!reduit) cover.animate([{ opacity: 0.2, transform: "scale(1.06)" }, { opacity: 1, transform: "none" }], { duration: 450, easing: "ease-out" });
      }
    };
    nom.addEventListener("input", majTexte); tel && tel.addEventListener("input", majTexte);
    form.addEventListener("change", e => { if (e.target.name === "services") majServices(); });
    window.prApercuPhoto = url => { photo.hidden = !url; ini.hidden = !!url; if (url) photo.src = url; };
  }

  /* ---------- F5 · dépôt de photo : surbrillance + aperçu ---------- */
  document.querySelectorAll("[data-pr-depot]").forEach(zone => {
    const input = zone.querySelector("input[type=file]"), img = zone.querySelector("[data-pr-depot-img]");
    const libelle = zone.querySelector("[data-pr-depot-nom]"), urlInitiale = img.getAttribute("src");
    let url = null;
    ["dragenter", "dragover"].forEach(t => zone.addEventListener(t, () => zone.classList.add("survol")));
    ["dragleave", "drop"].forEach(t => zone.addEventListener(t, () => zone.classList.remove("survol")));
    input.addEventListener("change", () => {
      if (url) URL.revokeObjectURL(url);
      const f = input.files[0];
      url = f && f.type.startsWith("image/") ? URL.createObjectURL(f) : null;
      img.hidden = !(url || urlInitiale); img.src = url || urlInitiale || "";
      zone.classList.toggle("a-photo", !img.hidden);
      libelle.textContent = f ? f.name : (urlInitiale ? "Remplacer la photo" : "Glisse une image ici");
      if (url && !reduit) img.animate([{ transform: "scale(.6)", opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 350, easing: "cubic-bezier(.34,1.56,.64,1)" });
      window.prApercuPhoto && window.prApercuPhoto(url || urlInitiale);
    });
  });

  /* ---------- K1 · Kanban ---------- */
  if (!document.querySelector("[data-pr-kanban]")) return;
  let glisse = null;

  // Envoi d'un changement de statut sans rechargement : on remplace le tableau et les messages par ceux
  // de la page renvoyée, puis la carte « vole » de son ancienne place à la nouvelle (technique FLIP).
  document.addEventListener("submit", async e => {
    const f = e.target.closest("[data-pr-kanban] form[data-pr-statut]");
    if (!f || e.defaultPrevented) return;      // annulation refusée dans confirm() : rien à faire
    e.preventDefault();
    const carte = f.closest(".pr-kcarte"), id = carte.dataset.id, avant = carte.getBoundingClientRect();
    carte.classList.add("envoi");
    try {
      const rep = await fetch(f.action, { method: "POST", body: new FormData(f), credentials: "same-origin" });
      if (!rep.ok) throw new Error(rep.status);
      const doc = new DOMParser().parseFromString(await rep.text(), "text/html");
      const neuf = doc.querySelector("[data-pr-kanban]");
      if (!neuf) throw new Error("kanban");
      document.querySelector("[data-pr-kanban]").replaceWith(neuf);
      const contenu = document.querySelector(".app-content"), anciens = contenu && contenu.querySelector(":scope > .messages");
      const msgs = doc.querySelector(".app-content > .messages");
      if (anciens) anciens.remove();
      if (msgs && contenu) { msgs.setAttribute("role", "status"); contenu.prepend(msgs); }
      const arrivee = neuf.querySelector(`.pr-kcarte[data-id="${id}"]`);
      if (arrivee) {
        arrivee.focus({ preventScroll: true });
        if (!reduit) {
          const apres = arrivee.getBoundingClientRect();
          arrivee.animate([
            { transform: `translate(${avant.left - apres.left}px, ${avant.top - apres.top}px) scale(1.04)`, boxShadow: "0 24px 50px rgba(0,0,0,.35)" },
            { transform: "none", boxShadow: "none" }], { duration: 550, easing: "cubic-bezier(.16,1,.3,1)" });
          neuf.querySelector(".pr-kanban-total b").animate([{ transform: "scale(1.15)" }, { transform: "none" }], { duration: 400, easing: "ease-out" });
        }
      }
    } catch (err) {
      f.submit();                                // repli : envoi classique, la page se recharge
    }
  });

  // Glisser-déposer (souris) ; au clavier et au doigt, les boutons ✓ / ✕ font la même chose.
  const peutAller = (carte, statut) => carte && carte.dataset.vers.split(" ").includes(statut);
  document.addEventListener("dragstart", e => {
    const c = e.target.closest && e.target.closest("[data-pr-kanban] .pr-kcarte[draggable=true]");
    if (!c) return;
    glisse = c; c.classList.add("glisse");
    e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", c.dataset.id);
    document.querySelectorAll("[data-pr-kanban] .pr-kcol").forEach(col =>
      col.classList.add(peutAller(c, col.dataset.statut) ? "possible" : (col.contains(c) ? "origine" : "interdit")));
  });
  document.addEventListener("dragend", () => {
    if (glisse) glisse.classList.remove("glisse");
    glisse = null;
    document.querySelectorAll("[data-pr-kanban] .pr-kcol").forEach(col => col.classList.remove("possible", "interdit", "origine", "cible"));
  });
  document.addEventListener("dragover", e => {
    const col = e.target.closest && e.target.closest("[data-pr-kanban] .pr-kcol");
    if (!col || !peutAller(glisse, col.dataset.statut)) return;
    e.preventDefault(); e.dataTransfer.dropEffect = "move";
    document.querySelectorAll("[data-pr-kanban] .pr-kcol.cible").forEach(c => c !== col && c.classList.remove("cible"));
    col.classList.add("cible");
  });
  document.addEventListener("drop", e => {
    const col = e.target.closest && e.target.closest("[data-pr-kanban] .pr-kcol");
    if (!col || !peutAller(glisse, col.dataset.statut)) return;
    e.preventDefault();
    const f = glisse.querySelector(`form[data-pr-statut="${col.dataset.statut}"]`);
    if (f) f.requestSubmit();                    // déclenche aussi le confirm() de l'annulation
  });
})();
