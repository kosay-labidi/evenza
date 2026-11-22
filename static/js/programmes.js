(() => {
  const root = document.querySelector('[data-programme]');
  if (!root) return;
  const box = root.querySelector('[data-programme-markers]');
  const empty = root.querySelector('[data-programme-empty]');
  const error = root.querySelector('[data-programme-filter-error]');
  const status = root.querySelector('[data-programme-status]');
  const fd = root.querySelector('[data-programme-from-date]');
  const ft = root.querySelector('[data-programme-from-time]');
  const td = root.querySelector('[data-programme-to-date]');
  const tt = root.querySelector('[data-programme-to-time]');
  const modal = document.querySelector('[data-programme-modal]');
  const form = modal?.querySelector('[data-seance-form]');
  const deleteButton = modal?.querySelector('[data-programme-delete]');
  const eventStart = new Date(root.dataset.eventStart);
  const eventEnd = new Date(root.dataset.eventEnd);
  const canEdit = root.dataset.canEdit === 'true';
  const initialFilters = {fromDate: fd.value, fromTime: ft.value, toDate: td.value, toTime: tt.value};
  let active = null;
  let dirty = false;
  const pad = n => String(n).padStart(2, '0');
  const label = v => new Intl.DateTimeFormat('fr-FR', {dateStyle: 'full', timeStyle: 'short'}).format(new Date(v));
  const shortLabel = v => new Intl.DateTimeFormat('fr-FR', {day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'}).format(new Date(v));
  const localValue = v => { const d = new Date(v); if (d.getSeconds() || d.getMilliseconds()) d.setMinutes(d.getMinutes() + 1); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; };
  const bound = (date, time, end) => date.value ? new Date(`${date.value}T${time.value || (end ? '23:59:59' : '00:00')}`) : null;
  const message = (text, bad = false) => { status.textContent = text; status.classList.toggle('is-error', bad); };
  function attach(marker) { marker.addEventListener('click', () => open(marker)); }
  function create(seance) {
    const marker = document.createElement('button'); marker.type = 'button'; marker.className = 'programme-marker';
    Object.assign(marker.dataset, {seanceId: seance.id, seanceTitle: seance.titre, seanceDescription: seance.description || '', seanceDate: seance.date});
    marker.setAttribute('aria-label', `Voir les détails de ${seance.titre}`);
    marker.innerHTML = '<span class="programme-marker-title"></span><span class="programme-marker-tick" aria-hidden="true"></span><span class="programme-marker-date"></span><span class="programme-marker-hint">Voir détails</span>';
    marker.querySelector('.programme-marker-title').textContent = seance.titre;
    marker.querySelector('.programme-marker-date').textContent = shortLabel(seance.date);
    attach(marker); box.appendChild(marker); return marker;
  }
  function render() {
    error.hidden = true;
    const start = bound(fd, ft); const end = bound(td, tt, true);
    if ((ft.value && !fd.value) || (tt.value && !td.value)) { error.textContent = 'Sélectionnez une date pour chaque heure.'; error.hidden = false; empty.hidden = true; return; }
    if (start && end && start > end) { error.textContent = 'Le début du filtre doit précéder sa fin.'; error.hidden = false; empty.hidden = true; return; }
    const visible = [];
    box.querySelectorAll('.programme-marker').forEach(marker => { const date = new Date(marker.dataset.seanceDate); const matches = (!start || date >= start) && (!end || date <= end); marker.hidden = !matches; if (matches) visible.push(marker); });
    visible.sort((left, right) => new Date(left.dataset.seanceDate) - new Date(right.dataset.seanceDate));
    const track = root.querySelector('[data-programme-track]');
    const endLabel = track.querySelector('.programme-axis-end');
    const fixedSpacing = 230;
    track.style.width = `${Math.max(680, (visible.length + 1) * fixedSpacing)}px`;
    visible.forEach((marker, index) => {
      const position = ((index + 1) / (visible.length + 1)) * 60;
      marker.style.left = `${position}%`;
      marker.style.setProperty('--lane', index % 3);
    });
    if (visible.length) {
      const lastPosition = (visible.length / (visible.length + 1)) * 100;
      endLabel.style.left = `calc(${lastPosition}% + 34px)`;
      endLabel.style.right = 'auto';
    } else {
      endLabel.style.left = '';
      endLabel.style.right = '';
    }
    empty.hidden = visible.length !== 0;
    const url = new URL(root.dataset.pdfUrl, location.origin);
    [['from_date', fd], ['from_time', ft], ['to_date', td], ['to_time', tt]].forEach(([key, input]) => input.value ? url.searchParams.set(key, input.value) : url.searchParams.delete(key));
    root.querySelector('[data-programme-pdf]').href = url;
  }
  function open(marker = null) {
    active = marker; dirty = false; const creating = !marker;
    modal.querySelector('[data-programme-modal-eyebrow]').textContent = creating ? 'Nouvelle séance' : (canEdit ? 'Modifier le programme' : 'Consultation');
    modal.querySelector('[data-programme-modal-title]').textContent = creating ? 'Ajouter une séance' : marker.dataset.seanceTitle;
    const view = modal.querySelector('[data-programme-modal-view]'); view.hidden = creating || canEdit;
    if (!creating && !canEdit) { modal.querySelector('[data-programme-modal-date]').textContent = label(marker.dataset.seanceDate); modal.querySelector('[data-programme-modal-description]').textContent = marker.dataset.seanceDescription || 'Aucune description.'; }
    if (form) { form.hidden = !canEdit; form.reset(); if (creating) form.elements.date.value = localValue(root.dataset.eventStart); else { form.elements.titre.value = marker.dataset.seanceTitle; form.elements.date.value = localValue(marker.dataset.seanceDate); form.elements.description.value = marker.dataset.seanceDescription; } }
    if (deleteButton) deleteButton.hidden = creating; if (!modal.open) modal.showModal();
  }
  function close(force = false) { if (!modal || !modal.open) return; if (!force && dirty && !confirm('Les modifications non enregistrées seront perdues. Fermer ?')) return; modal.close(); dirty = false; }
  async function submit(event) { event.preventDefault(); const creating = !active; const action = creating ? root.dataset.createUrl : root.dataset.updateUrlTemplate.replace('/0/', `/${active.dataset.seanceId}/`); try { const response = await fetch(action, {method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}}); const data = await response.json(); if (!response.ok) { modal.querySelector('[data-programme-form-errors]').textContent = Object.values(data.errors || {}).flatMap(items => items.map(item => item.message)).join('\n') || 'Le formulaire contient une erreur.'; return; } if (creating) active = create(data.seance); else { Object.assign(active.dataset, {seanceTitle: data.seance.titre, seanceDescription: data.seance.description || '', seanceDate: data.seance.date}); active.querySelector('.programme-marker-title').textContent = data.seance.titre; active.querySelector('.programme-marker-date').textContent = shortLabel(data.seance.date); } render(); message(data.message); close(true); } catch (_) { modal.querySelector('[data-programme-form-errors]').textContent = 'Le serveur est momentanément indisponible.'; } }
  async function remove() { if (!active || !confirm('Supprimer définitivement cette séance ?')) return; try { const action = root.dataset.deleteUrlTemplate.replace('/0/', `/${active.dataset.seanceId}/`); const response = await fetch(action, {method: 'POST', body: new FormData(form), credentials: 'same-origin'}); const data = await response.json(); if (!response.ok) throw Error(data.detail || 'Suppression impossible'); active.remove(); active = null; render(); message(data.message); close(true); } catch (exception) { message(exception.message, true); } }
  box.querySelectorAll('.programme-marker').forEach(attach); [fd, ft, td, tt].forEach(input => input.addEventListener('input', render));
  root.querySelector('[data-programme-reset]').addEventListener('click', () => { fd.value = initialFilters.fromDate; ft.value = initialFilters.fromTime; td.value = initialFilters.toDate; tt.value = initialFilters.toTime; render(); }); root.querySelector('[data-programme-add]')?.addEventListener('click', () => open());
  modal?.querySelector('[data-programme-close]').addEventListener('click', () => close()); modal?.querySelector('[data-programme-cancel]')?.addEventListener('click', () => close());
  modal?.querySelector('[data-programme-clear]')?.addEventListener('click', () => { form?.querySelectorAll('input:not([type="hidden"]), textarea').forEach(field => { field.value = ''; }); dirty = true; });
  deleteButton?.addEventListener('click', remove); form?.addEventListener('input', () => dirty = true); form?.addEventListener('submit', submit); render();
})();
