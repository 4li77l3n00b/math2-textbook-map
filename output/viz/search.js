/* Global search (Ctrl+K or /): one box over questions, knowledge points, methods, formulas and textbook sections.
   Results are grouped; ↑↓ to move, Enter to open, Esc to close. Loaded last (needs app.js, methods.js, formulas.js). */
(() => {
  // inline formulas of a short text rendered once (display $$ shown inline)
  const inl = s => String(s || '').replace(/\$\$([\s\S]*?)\$\$/g, (m, f) => `$${f.trim()}$`).replace(/\s*\n\s*/g, ' ')
    .split(/(\$[^$]+\$)/).map(p => p.length > 2 && p[0] === '$' && p.at(-1) === '$' && window.katex
      ? katex.renderToString(p.slice(1, -1), { throwOnError: false, strict: 'ignore' }) : esc(p)).join('');
  // \xi in the sources matches a typed ξ (and the other way round)
  const GREEK = { alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', varepsilon: 'ε', epsilon: 'ε', zeta: 'ζ', eta: 'η', theta: 'θ',
    lambda: 'λ', mu: 'μ', xi: 'ξ', pi: 'π', rho: 'ρ', sigma: 'σ', tau: 'τ', varphi: 'φ', phi: 'φ', psi: 'ψ', omega: 'ω' };
  const norm = s => String(s || '').toLowerCase().replace(/\\(varepsilon|varphi|[a-z]+)(?![a-z])/g, (m, w) => GREEK[w] || m);
  const GROUPS = [['q', '真题'], ['kp', '知识点'], ['m', '方法'], ['fx', '公式'], ['sec', '教材章节']];
  let IDX = null;
  // each entry: g group, t title text (scored higher), b body text, open(), html()
  function build() {
    const out = [];
    const tname = t => (t.kp != null ? K[t.kp].n : D.cards[t.c].ti);
    for (const q of D.questions) {
      const me = (q.me || []).map(m => D.methods[m[0]] && D.methods[m[0]].n).join(' ');
      out.push({ g: 'q', y: String(q.y), lb: norm(q.lb), t: norm(`${q.y}年 ${q.y} 第${q.lb}题`), b: norm(q.stem + ' ' + q.to.map(tname).join(' ') + ' ' + me),
        html: () => `<div class="gs-t">${q.y} 年 第 ${esc(q.lb)} 题 <span class="badge muted">${TYPE[q.ty]}</span></div><div class="gs-s">${stemHtml(q)}</div>`,
        open: () => openQuestion(q.id) });
    }
    for (const k of K) out.push({ g: 'kp', t: norm(k.n), b: norm(k.s),
      html: () => `<div class="gs-t">${inl(k.n)} ${kindBadge(k.k)}</div><div class="gs-s">${inl(clip(k.s, 110))}</div>`,
      open: () => go('cards', k.id) });
    for (const m of D.methods || []) out.push({ g: 'm', t: norm(m.n), b: norm(m.s + ' ' + (m.st || []).join(' ') + ' ' + m.g),
      html: () => `<div class="gs-t">${esc(m.n)} <span class="muted small">${esc(m.g)}</span></div><div class="gs-s">${inl(clip(m.s, 110))}</div>`,
      open: () => go('methods', m.id) });
    if (typeof FX !== 'undefined') FX.forEach(gr => gr.items.forEach(it => out.push({ g: 'fx', t: norm(it.name), b: norm(gr.name + ' ' + it.tex + ' ' + it.note),
      html: () => `<div class="gs-t">${esc(it.name)} <span class="muted small">${esc(gr.name)}</span></div><div class="gs-s">${inl('$' + it.tex.split(/,\\q?quad/)[0] + '$')}</div>`,
      open: () => window.fxSearch && fxSearch(it.name) })));
    for (const n of D.nodes) {
      if (!n.ti || n.k === 'book') continue;
      const path = nodePath(n.id);
      out.push({ g: 'sec', t: norm(`${n.num || ''} ${n.ti}`), b: norm(path),
        html: () => `<div class="gs-t">${n.num ? `<span class="muted">${esc(n.num)}</span> ` : ''}${inl(n.ti)} <span class="badge muted">${BOOK_SHORT[n.bk] || n.bk}</span></div><div class="gs-s">${inl(path)}</div>`,
        open: () => goNode(n.id) });
    }
    return out;
  }
  // every word must occur; title hits, exact year / question number and earlier positions rank first
  function score(e, words) {
    let s = 0;
    for (const w of words) {
      const it = e.t.indexOf(w);
      if (e.g === 'q' && (w === e.y || w === e.lb)) s += 60;
      else if (it >= 0) s += 30 - Math.min(it, 20);
      else if (e.b.includes(w)) s += 5;
      else return -1;
    }
    return s + (e.t === words.join(' ') ? 50 : 0);
  }
  const PER = 5, MORE = 40;
  const UI = { sel: 0, items: [], open: new Set() };
  const box = document.createElement('div');
  box.id = 'gs';
  box.hidden = true;
  box.innerHTML = `<div class="gs-box"><div class="gs-in"><span class="gs-ic">⌕</span><input type="search" id="gsq" placeholder="搜索真题、知识点、方法、公式、章节… 例如：2010 21、泰勒、伴随矩阵、华里士" autocomplete="off">
    <kbd>Esc</kbd></div><div class="gs-res"></div><div class="gs-ft muted small">↑↓ 选择 · Enter 打开 · Ctrl+K 或 / 随时呼出</div></div>`;
  document.body.appendChild(box);
  const q = $('#gsq', box), res = $('.gs-res', box);

  function render() {
    const words = norm(q.value).split(/\s+/).filter(Boolean);
    UI.items = [];
    if (!words.length) { res.innerHTML = '<p class="gs-empty muted small">输入关键词。多个词用空格分开，全部出现才算匹配；年份加题号可直接找题。</p>'; return; }
    if (!IDX) IDX = build();
    const hits = {};
    for (const e of IDX) { const s = score(e, words); if (s >= 0) (hits[e.g] = hits[e.g] || []).push([s, e]); }
    // newest question first among equal scores; the group with the best hit comes first (a concept word puts
    // knowledge points and methods above the questions that merely mention it; "2010 21" puts the question first)
    const sorted = GROUPS.map(([g, name], i) => [g, name, i, (hits[g] || []).sort((a, b) => b[0] - a[0] || (b[1].y || 0) - (a[1].y || 0))])
      .filter(x => x[3].length).sort((a, b) => b[3][0][0] - a[3][0][0] || a[2] - b[2]);
    let html = '';
    for (const [g, name, , h] of sorted) {
      const lim = UI.open.has(g) ? MORE : PER;
      html += `<div class="gs-g">${name} <span class="muted small">${h.length}</span></div>`;
      for (const [, e] of h.slice(0, lim)) { html += `<div class="gs-r" data-gi="${UI.items.length}">${e.html()}</div>`; UI.items.push(e); }
      if (h.length > lim) html += `<button class="gs-more" data-gmore="${g}">${UI.open.has(g) ? `前 ${MORE} 条，换个更具体的词` : `显示更多（共 ${h.length}）`}</button>`;
    }
    res.innerHTML = html || '<p class="gs-empty muted small">没有找到。</p>';
    UI.sel = Math.min(UI.sel, Math.max(UI.items.length - 1, 0));
    mark();
  }
  function mark() {
    $$('.gs-r', res).forEach(r => r.classList.toggle('on', +r.dataset.gi === UI.sel));
    const r = $(`.gs-r[data-gi="${UI.sel}"]`, res);
    if (r) r.scrollIntoView({ block: 'nearest' });
  }
  function pick(i) {
    const e = UI.items[i];
    if (!e) return;
    close();
    closeModal();
    e.open();
  }
  function open() {
    box.hidden = false;
    $('#gsBtn').classList.add('on');
    q.focus();
    q.select();
    render();
  }
  function close() { box.hidden = true; $('#gsBtn').classList.remove('on'); }
  let t = 0;
  q.addEventListener('input', () => { UI.sel = 0; UI.open.clear(); clearTimeout(t); t = setTimeout(render, IDX ? 60 : 0); });
  q.addEventListener('keydown', e => {
    e.stopPropagation();  // keep the page shortcuts (j/k, digits …) out of the box
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      UI.sel = Math.max(0, Math.min(UI.items.length - 1, UI.sel + (e.key === 'ArrowDown' ? 1 : -1)));
      mark();
    } else if (e.key === 'Enter') { e.preventDefault(); pick(UI.sel); }
    else if (e.key === 'Escape') { e.preventDefault(); close(); }
  });
  box.addEventListener('click', e => {
    if (e.target === box) return close();
    const m = e.target.closest('[data-gmore]');
    if (m) { UI.open.add(m.dataset.gmore); render(); q.focus(); return; }
    const r = e.target.closest('[data-gi]');
    if (r) pick(+r.dataset.gi);
  });
  box.addEventListener('mousemove', e => {
    const r = e.target.closest('[data-gi]');
    if (r && +r.dataset.gi !== UI.sel) { UI.sel = +r.dataset.gi; mark(); }
  });
  $('#gsBtn').addEventListener('click', () => (box.hidden ? open() : close()));
  addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') { e.preventDefault(); box.hidden ? open() : close(); return; }
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && box.hidden &&
        !(e.target.closest && e.target.closest('input, select, textarea, [contenteditable]'))) { e.preventDefault(); open(); }
  }, true);
})();
