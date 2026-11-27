/* Gestion des utilisateurs : sélection groupée et aperçu du rôle. Amélioration progressive :
   sans JavaScript, les formulaires fonctionnent (le serveur revérifie tout). */
(() => {
  // ---------- Sélection pour les actions groupées ----------
  const barre = document.querySelector("[data-u-groupe]");
  if (barre) {
    const cases = [...document.querySelectorAll("[data-u-select]")];
    const tout = document.querySelector("[data-u-select-tout]");
    const compteur = barre.querySelector("[data-u-compte]");
    const boutons = barre.querySelectorAll("button[name=action]");
    const maj = () => {
      const n = cases.filter(c => c.checked).length;
      compteur.textContent = n;
      barre.hidden = n === 0;
      boutons.forEach(b => { b.disabled = n === 0; });
      if (tout) { tout.checked = n > 0 && n === cases.length; tout.indeterminate = n > 0 && n < cases.length; }
    };
    cases.forEach(c => c.addEventListener("change", maj));
    if (tout) tout.addEventListener("change", () => { cases.forEach(c => { c.checked = tout.checked; }); maj(); });
    barre.querySelector("[data-u-vider]")?.addEventListener("click", () => {
      cases.forEach(c => { c.checked = false; }); maj(); tout?.focus();
    });
    maj();
  }

  // ---------- Aperçu dynamique des autorisations du rôle ----------
  const donnees = document.getElementById("catalogue-roles");
  const select = document.querySelector("select[name=role]");
  const apercu = document.querySelector("[data-role-apercu]");
  if (donnees && select && apercu) {
    const catalogue = JSON.parse(donnees.textContent);
    const remplir = (sel, items, vide) => {
      const ul = apercu.querySelector(sel);
      ul.replaceChildren(...(items.length ? items : [vide]).map(t => {
        const li = document.createElement("li"); li.textContent = t; return li;
      }));
    };
    const maj = () => {
      const r = catalogue[select.value];
      if (!r) return;
      apercu.querySelector("[data-role-libelle]").textContent = r.libelle;
      apercu.querySelector("[data-role-description]").textContent = r.description;
      apercu.querySelector("[data-role-niveau]").textContent = r.niveau;
      remplir("[data-role-modules]", r.modules, "Aucun module de gestion");
      remplir("[data-role-espace]", [...r.espace_personnel, ...r.espaces_dedies], "—");
      remplir("[data-role-fonctions]", r.fonctions, "—");
      remplir("[data-role-restrictions]", r.restrictions, "—");
      const prep = apercu.querySelector("[data-role-preparees]");
      prep.hidden = !r.preparees.length;
      remplir("[data-role-preparees] ul", r.preparees, "—");
    };
    select.addEventListener("change", maj);
    maj();
  }
})();
