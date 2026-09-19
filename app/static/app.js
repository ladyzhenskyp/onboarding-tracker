/* Onboarding Tracker — small behaviours. No framework: HTMX fetches fragments,
   this file only opens/closes things and adds motion.

   1. entrance motion plays once per page load, then is switched off
   2. tile numbers count up
   3. search palette ("/" opens it, arrows + Enter, Esc closes)
   4. client peek panel (rows marked data-peek load /clients/<id>/peek via HTMX)
   5. click-to-sort tables
*/
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // 1 ---- one-shot entrance: after it has played, nothing can replay it (opening
  // the peek panel, HTMX swaps, focus changes) until the next real page load.
  setTimeout(() => document.documentElement.classList.add('settled'), 1800);

  // 2 ---- count-up for KPI tiles
  if (!reduced) {
    $$('[data-count]').forEach(el => {
      const to = Number(el.dataset.count), t0 = performance.now(), dur = 700;
      if (!to) return;
      (function frame(t) {
        const k = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - k, 3);
        el.textContent = Math.round(to * e);
        if (k < 1) requestAnimationFrame(frame);
      })(t0);
    });
  }

  // toast (also shown after a redirect if the previous page left a message)
  let toastTimer;
  function toast(msg) {
    const t = $('#toast'); if (!t) return;
    t.textContent = msg; t.classList.add('on');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('on'), 2400);
  }
  window.toast = toast;

  // 3 ---- search palette
  const pal = $('#pal'), palScrim = $('#pal-scrim'), palInput = $('#search'), palList = $('#search-results');
  let sel = 0;
  const items = () => $$('a.pal-i', palList);
  const paint = () => items().forEach((a, i) => a.classList.toggle('sel', i === sel));
  function openPal() {
    if (!pal) return;
    pal.classList.add('on'); palScrim.classList.add('on');
    setTimeout(() => { palInput.focus({ preventScroll: true }); palInput.select(); }, 30);
  }
  function closePal() { if (pal) { pal.classList.remove('on'); palScrim.classList.remove('on'); } }
  if (pal) {
    $('#search-open').addEventListener('click', openPal);
    palScrim.addEventListener('click', closePal);
    palList.addEventListener('htmx:afterSwap', () => { sel = 0; paint(); });
    palList.addEventListener('mousemove', e => {
      const a = e.target.closest('a.pal-i'); if (!a) return;
      const i = items().indexOf(a); if (i !== sel) { sel = i; paint(); }
    });
  }

  // 4 ---- client peek panel
  const drawer = $('#drawer'), scrim = $('#scrim');
  function openDrawer() {
    drawer.classList.add('on'); scrim.classList.add('on');
    const x = $('.x', drawer); if (x) x.focus({ preventScroll: true });
    // draw the stage line up to the current stage
    const prog = $('.prog', drawer);
    if (prog) requestAnimationFrame(() => requestAnimationFrame(() => { prog.style.width = prog.dataset.w; }));
  }
  function closeDrawer() { if (drawer) { drawer.classList.remove('on'); scrim.classList.remove('on'); } }
  if (drawer) {
    drawer.addEventListener('htmx:afterSwap', openDrawer);
    scrim.addEventListener('click', closeDrawer);
    drawer.addEventListener('click', e => { if (e.target.closest('.x')) closeDrawer(); });
    // a row marked data-peek opens the panel; its inner link still works as a
    // normal link when opened in a new tab or when JavaScript is off
    document.addEventListener('click', e => {
      const a = e.target.closest('[data-peek] a'); if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
      e.preventDefault();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Enter' && e.target.matches && e.target.matches('tr[data-peek]')) e.target.click();
    });
  }

  document.addEventListener('keydown', e => {
    const typing = /input|textarea|select/i.test(document.activeElement.tagName);
    if (e.key === '/' && !typing) { e.preventDefault(); openPal(); return; }
    if (e.key === 'Escape') { if (pal && pal.classList.contains('on')) closePal(); else closeDrawer(); return; }
    if (!pal || !pal.classList.contains('on')) return;
    const list = items();
    if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, list.length - 1); paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); paint(); }
    else if (e.key === 'Enter') { const t = list[sel] || list[0]; if (t) { e.preventDefault(); location.href = t.href; } }
  });

  // 5 ---- click-to-sort for <table class="sortable">
  const rank = { 'badge-red': 0, 'badge-amber': 1, 'badge-green': 2, 'chip-critical': 0, 'chip-high': 1, 'chip-medium': 2, 'chip-low': 3 };
  function key(td) {
    if (td.dataset.value !== undefined) return isNaN(td.dataset.value) ? td.dataset.value : Number(td.dataset.value);
    const b = td.querySelector('.badge, .chip');
    if (b) for (const c of b.classList) if (c in rank) return rank[c];
    const t = td.textContent.trim();
    const n = t.replace(/[$,]/g, '').match(/^-?\d+(\.\d+)?/);
    if (n && /^[-$\d]/.test(t)) return Number(n[0]);
    const d = Date.parse(t);
    if (!isNaN(d) && /\d{4}/.test(t)) return d;
    return t.toLowerCase();
  }
  function bind(root) {
    $$('table.sortable:not([data-bound])', root).forEach(table => {
      table.dataset.bound = '1';
      const ths = $$('thead th', table);
      ths.forEach((th, i) => {
        if (!th.textContent.trim()) return;
        th.addEventListener('click', () => {
          const dir = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
          ths.forEach(o => o.removeAttribute('aria-sort'));
          th.setAttribute('aria-sort', dir);
          const tbody = table.tBodies[0];
          const rows = Array.from(tbody.rows).filter(r => r.cells.length > 1);
          rows.sort((a, b) => {
            const ka = key(a.cells[i]), kb = key(b.cells[i]);
            const c = typeof ka === 'number' && typeof kb === 'number' ? ka - kb : String(ka).localeCompare(String(kb));
            return dir === 'ascending' ? c : -c;
          });
          rows.forEach(r => tbody.appendChild(r));
        });
      });
    });
  }
  bind(document);
  document.body.addEventListener('htmx:afterSwap', e => bind(e.target));
})();
