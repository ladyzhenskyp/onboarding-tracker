/* Onboarding Tracker — small behaviours. No framework: HTMX fetches fragments,
   this file only opens/closes things and adds motion.

   1. entrance motion plays once per page load, then is switched off
   2. tile numbers count up
   3. search palette ("/" opens it, arrows + Enter, Esc closes)
   4. client peek panel (rows marked data-peek load /clients/<id>/peek via HTMX)
   5. click-to-sort tables
   6. dropdowns drawn in the app's own style (the real <select> stays underneath)
   7. a toast whenever a save fails, so nothing fails silently
   8. edit (reveal a row's form) and delete (confirm in place) on the client page
   9. shared demo: a countdown before the scheduled reset, and a clear message after it
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
  function toast(msg, ms) {
    const t = $('#toast'); if (!t) return;
    t.textContent = msg; t.classList.add('on');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('on'), ms || 2400);
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

  // 6 ---- dropdowns: the browser draws an open <select> in the operating system's
  // style, which can't be themed. So each <select> keeps working underneath (forms and
  // HTMX still read its value) while a button + list in the app's own style sits on top.
  const chevron = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';
  let openSel = null;
  function closeSel() { if (openSel) { openSel.classList.remove('open'); $('.sel-btn', openSel).setAttribute('aria-expanded', 'false'); openSel = null; } }
  function enhanceSelect(sel) {
    if (sel.dataset.enhanced || sel.multiple) return;
    sel.dataset.enhanced = '1';
    const wrap = document.createElement('div');
    // the wrapper is what the page lays out now, so it takes over the select's sizing
    // classes (w-auto, sm:w-44, flex-1 ...); otherwise it would default to full width
    const layout = Array.from(sel.classList).filter(c => c !== 'input');
    wrap.className = ['sel', sel.classList.contains('w-auto') ? 'sel-auto' : '', ...layout].join(' ').trim();
    sel.parentNode.insertBefore(wrap, sel);
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'sel-btn'; btn.setAttribute('aria-haspopup', 'listbox'); btn.setAttribute('aria-expanded', 'false');
    const menu = document.createElement('ul'); menu.className = 'sel-menu'; menu.setAttribute('role', 'listbox'); menu.tabIndex = -1;
    // built once: replacing the label while it is being clicked would detach the clicked
    // element, and the "click outside closes" check below would then shut the list again
    btn.innerHTML = '<span></span>' + chevron;
    const label = btn.firstChild;
    wrap.append(btn, menu, sel);
    sel.classList.add('sel-native'); sel.tabIndex = -1;
    let act = -1;
    const opts = () => $$('.sel-opt', menu);
    function render() {
      const cur = sel.options[sel.selectedIndex];
      label.textContent = cur ? cur.textContent : '';
      btn.classList.toggle('placeholder', !cur || cur.value === '');
      menu.innerHTML = '';
      Array.from(sel.options).forEach((o, i) => {
        if (o.disabled) return;  // e.g. the "Move to…" prompt
        const li = document.createElement('li');
        li.className = 'sel-opt'; li.setAttribute('role', 'option'); li.dataset.i = i;
        li.setAttribute('aria-selected', i === sel.selectedIndex ? 'true' : 'false');
        li.textContent = o.textContent;
        menu.appendChild(li);
      });
    }
    function paintAct() { opts().forEach((li, i) => li.classList.toggle('act', i === act)); const a = opts()[act]; if (a) a.scrollIntoView({ block: 'nearest' }); }
    function open() {
      closeSel(); render();
      const r = btn.getBoundingClientRect();
      wrap.classList.toggle('up', r.bottom + 280 > innerHeight && r.top > 280);
      wrap.classList.add('open'); btn.setAttribute('aria-expanded', 'true'); openSel = wrap;
      act = Math.max(opts().findIndex(li => li.getAttribute('aria-selected') === 'true'), 0); paintAct();
    }
    function choose(li) {
      sel.selectedIndex = Number(li.dataset.i);
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      render(); closeSel(); btn.focus({ preventScroll: true });
    }
    btn.addEventListener('click', () => (wrap.classList.contains('open') ? closeSel() : open()));
    menu.addEventListener('click', e => {
      // inside a <label>, the browser would pass this click on to the button and reopen the list
      e.preventDefault();
      const li = e.target.closest('.sel-opt'); if (li) choose(li);
    });
    menu.addEventListener('mousemove', e => { const li = e.target.closest('.sel-opt'); if (li) { act = opts().indexOf(li); paintAct(); } });
    wrap.addEventListener('keydown', e => {
      const isOpen = wrap.classList.contains('open');
      if (!isOpen && ['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) { e.preventDefault(); open(); return; }
      if (!isOpen) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); act = Math.min(act + 1, opts().length - 1); paintAct(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); act = Math.max(act - 1, 0); paintAct(); }
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (opts()[act]) choose(opts()[act]); }
      else if (e.key === 'Escape' || e.key === 'Tab') { e.stopPropagation(); closeSel(); }
      else if (e.key.length === 1) {  // type a letter to jump
        e.stopPropagation();
        const k = e.key.toLowerCase(), i = opts().findIndex(li => li.textContent.trim().toLowerCase().startsWith(k));
        if (i >= 0) { act = i; paintAct(); }
      }
    });
    // A required dropdown left empty: the browser would point its "fill out this field"
    // bubble at the hidden native select (a 1px dot in a corner). Show it on the button instead.
    sel.addEventListener('invalid', e => {
      e.preventDefault();
      wrap.classList.add('sel-error'); btn.focus({ preventScroll: true });
      toast('Choose an option from "' + label.textContent.trim() + '" first');
    });
    sel.addEventListener('change', () => wrap.classList.remove('sel-error'));
    sel.addEventListener('change', render);
    if (sel.form) sel.form.addEventListener('reset', () => setTimeout(render));
    render();
  }
  // filter bars marked data-autosubmit apply as soon as a value changes (no Apply click needed)
  document.addEventListener('change', e => {
    const form = e.target.closest && e.target.closest('form[data-autosubmit]');
    if (form) form.requestSubmit ? form.requestSubmit() : form.submit();
  });
  // keep shared URLs short: untouched filters are left out of the address
  document.addEventListener('submit', e => {
    if (!e.target.matches('form[data-autosubmit]')) return;
    Array.from(e.target.elements).forEach(el => { if (el.name && el.value === '') el.disabled = true; });
  });

  function enhanceAll(root) { $$('select', root).forEach(enhanceSelect); }
  enhanceAll(document);
  document.addEventListener('click', e => { if (openSel && !e.composedPath().includes(openSel)) closeSel(); });
  document.body.addEventListener('htmx:afterSwap', e => enhanceAll(e.target));

  // 9 ---- shared demo: warn before the scheduled data reset, and say so afterwards
  const resetNote = $('#reset-note');
  const resetAt = resetNote ? Date.parse(resetNote.dataset.resetAt) : NaN;
  const WARN_MINUTES = 5;
  function paintReset() {
    if (isNaN(resetAt)) return;
    const left = resetAt - Date.now();
    if (left > WARN_MINUTES * 60000) { resetNote.hidden = true; return; }
    resetNote.hidden = false;
    if (left > 0) {
      const mins = Math.ceil(left / 60000);
      resetNote.textContent = 'Demo data resets in ' + (mins <= 1 ? 'under a minute' : mins + ' min');
      resetNote.title = 'This is a shared demo. Anything added or changed is put back to the starting point every hour.';
    } else {
      resetNote.classList.add('done');
      resetNote.innerHTML = 'Demo data was just reset. <a href="">Refresh</a>';
    }
  }
  if (resetNote) { paintReset(); setInterval(paintReset, 15000); }
  const resetJustHappened = () => !isNaN(resetAt) && Date.now() > resetAt;

  // 7 ---- never fail silently: if the server rejects or can't be reached, say so
  document.body.addEventListener('htmx:responseError', e => {
    const code = e.detail.xhr ? e.detail.xhr.status : 0;
    if (code === 404) {  // the row is gone: deleted by someone else, or removed by the demo reset
      toast(resetNote && resetJustHappened()
        ? 'The demo data just reset, so that item is gone. Refresh to continue.'
        : 'That item no longer exists' + (resetNote ? ' (the demo data resets every hour)' : '') + '. Refresh to continue.', 6000);
      return;
    }
    toast(code === 422 ? "That couldn't be saved. Check the fields and try again." : "Something went wrong saving that (error " + code + ").");
  });
  document.body.addEventListener('htmx:sendError', () => toast("Couldn't reach the server. Check your connection and try again."));

  // 8 ---- edit + delete on rows
  // Edit: a pencil with data-edit="<id>" reveals that (hidden) form; Cancel hides it again.
  // Delete: a button marked data-confirm asks once more, in place, before it submits.
  document.addEventListener('click', e => {
    const ed = e.target.closest('[data-edit]');
    if (ed) {
      const target = document.getElementById(ed.dataset.edit); if (!target) return;
      const show = target.hidden;
      $$('.edit-row').forEach(r => { r.hidden = true; });  // one at a time
      $$('tr.editing').forEach(r => r.classList.remove('editing'));
      target.hidden = !show;
      if (show) {
        const row = ed.closest('tr'); if (row) row.classList.add('editing');
        const first = target.querySelector('input:not([type=hidden]), textarea');
        if (first) { first.focus({ preventScroll: true }); if (first.select) first.select(); }
      }
      return;
    }
    const tog = e.target.closest('[data-toggle]');
    if (tog) {  // e.g. the "Add client" button shows or hides its form
      const box = document.getElementById(tog.dataset.toggle); if (!box) return;
      box.hidden = !box.hidden;
      if (!box.hidden) { const f = box.querySelector('input, textarea'); if (f) f.focus({ preventScroll: true }); }
      return;
    }
    const cancel = e.target.closest('[data-edit-cancel]');
    if (cancel) {
      const box = cancel.closest('.edit-row'); box.hidden = true;
      const f = box.matches('form') ? box : box.querySelector('form');
      if (f) { f.reset(); $$('select', f).forEach(x => x.dispatchEvent(new Event('change'))); }
      $$('tr.editing').forEach(r => r.classList.remove('editing'));
      return;
    }
    const del = e.target.closest('[data-confirm]');
    if (del && !del.classList.contains('armed')) {
      e.preventDefault();
      const original = del.innerHTML;
      del.classList.add('armed'); del.textContent = 'Delete?';
      const disarm = () => { del.classList.remove('armed'); del.innerHTML = original; };
      const timer = setTimeout(disarm, 3500);
      del.addEventListener('blur', () => { clearTimeout(timer); disarm(); }, { once: true });
    }
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
          // remember each row's edit form so it stays directly under its row after sorting
          const partner = new Map(rows.map(r => [r, r.nextElementSibling && r.nextElementSibling.classList.contains('edit-row') ? r.nextElementSibling : null]));
          rows.sort((a, b) => {
            const ka = key(a.cells[i]), kb = key(b.cells[i]);
            const c = typeof ka === 'number' && typeof kb === 'number' ? ka - kb : String(ka).localeCompare(String(kb));
            return dir === 'ascending' ? c : -c;
          });
          rows.forEach(r => { tbody.appendChild(r); if (partner.get(r)) tbody.appendChild(partner.get(r)); });
        });
      });
    });
  }
  bind(document);
  document.body.addEventListener('htmx:afterSwap', e => bind(e.target));
})();
