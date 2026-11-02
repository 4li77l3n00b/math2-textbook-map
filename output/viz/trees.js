/* Question-type decision trees (output/thinking/trees.txt, written by Claude from all the thinking traces): for a kind
   of question, what to look at first and which method each situation calls for. A question belongs to a tree when one of
   its key methods is in the tree's scope. Each branch lists its methods and opens the questions that use them as a key
   method. Loaded after app.js, methods.js and thinking.js. */
const TV = { cur: null, open: new Set(), nolist: false };
try { TV.nolist = localStorage.getItem('math2viz.dtNoList') === '1'; } catch (e) { /* default */ }
const treeQs = (t, pool = F) => pool.filter(q => inTree(q, t));
// subject of a tree: the method group of its first scope entry
const treeGroup = t => { const m = (D.methods || []).find((x, i) => inScope(i, t.sc)); return m ? m.g : ''; };

function renderTreeList() {
  const el = $('#trList');
  let g = null, html = '';
  for (const t of TREES) {
    const gr = treeGroup(t);
    if (gr !== g) { g = gr; html += `<div class="qyr">${esc(gr)}</div>`; }
    const n = treeQs(t).length;
    html += `<div class="qrow dt-row${t.id === TV.cur ? ' cur' : ''}" data-tsel="${t.id}"><div class="h"><b>${esc(t.n)}</b>
      <span class="muted small">${n} 题</span>${t.r.length ? '' : '<span class="badge muted">待写</span>'}</div></div>`;
  }
  el.innerHTML = `<div class="lst">${html || '<p class="muted small" style="padding:6px 12px">还没有决策树。</p>'}</div>`;
}
// questions of the tree that use one of the branch's methods as a key method, newest first
const branchQs = (t, br) => treeQs(t).filter(q => (q.me || []).some(m => m[1] && br.m.includes(m[0])))
  .sort((a, b) => b.y - a.y || a.id.localeCompare(b.id, 'en', { numeric: true }));
function nodesHtml(t, nodes, path) {
  return nodes.map((x, i) => {
    const p = path + '.' + i;
    if (x.q != null) return `<div class="dt-node"><div class="dt-q">${tx(x.q)}</div><div class="dt-brs">${nodesHtml(t, x.b, p)}</div></div>`;
    const qs = x.m.length ? branchQs(t, x) : [];
    const open = TV.open.has(p);
    return `<div class="dt-br${x.s.length ? ' has-sub' : ''}">
      <div class="dt-bh"${qs.length ? ` data-bopen="${p}" title="${open ? '收起' : '看真题'}"` : ''}>
        <span class="dt-w">${tx(x.w)}</span>
        ${x.m.map(mi => `<a class="mtag core" data-method="${D.methods[mi].id}">${esc(D.methods[mi].n)}</a>`).join('')}
        ${qs.length ? `<span class="dt-n${open ? ' on' : ''}">${qs.length} 题 ${open ? '▴' : '▾'}</span>` : ''}</div>
      ${x.no ? `<div class="dt-no">${tx(x.no)}</div>` : ''}
      ${open ? `<div class="dt-qs">${qs.slice(0, 12).map(q => `<div class="dt-qi" data-q="${q.id}"><span class="dt-qh">${q.y}·${esc(q.lb)}</span><span class="stem">${stemHtml(q)}</span>
        ${q.th ? `<a class="dt-tr" data-train="${q.id}" title="在思路训练中练">练 ›</a>` : ''}</div>`).join('')}
        ${qs.length > 12 ? `<div class="muted small">还有 ${qs.length - 12} 题，可在方法页查看</div>` : ''}</div>` : ''}
      ${x.s.length ? `<div class="dt-sub">${nodesHtml(t, x.s, p)}</div>` : ''}</div>`;
  }).join('');
}
function renderTreeMain() {
  const el = $('#trMain');
  const t = TREES.find(x => x.id === TV.cur);
  if (!t) { el.innerHTML = '<p class="muted" style="text-align:center;margin-top:60px">从左侧选一类题。</p>'; return; }
  const qs = treeQs(t), pos = TREES.indexOf(t);
  el.innerHTML = `<div class="kpd dtree">
    <div class="kpd-top"><button class="icon" data-dtlist title="收起或展开左侧列表（L）">${TV.nolist ? '☰ 列表' : '⇤ 收起列表'}</button>
      <span class="crumb muted small">决策树 · ${esc(treeGroup(t))}</span>
      <span class="kp-nav"><button class="icon" data-dtstep="-1" ${pos > 0 ? '' : 'disabled'} title="上一类（K）">↑</button><span class="muted small">${pos + 1} / ${TREES.length}</span><button class="icon" data-dtstep="1" ${pos < TREES.length - 1 ? '' : 'disabled'} title="下一类（J）">↓</button></span></div>
    <div class="th-col">
      <h1 class="kp-title">${esc(t.n)} <span class="muted small">${qs.length} 题</span></h1>
      ${t.ab ? `<p class="dt-ab">${tx(t.ab)}</p>` : ''}
      ${t.r.length ? `<div class="dt-tree">${nodesHtml(t, t.r, 'r')}</div>` : '<p class="muted">这棵树还没写。</p>'}
      ${t.pit.length ? `<details class="th-fold" open><summary>常见误入 <span class="n">${t.pit.length}</span></summary><ul class="th-traps">${t.pit.map(p => `<li>${tx(p)}</li>`).join('')}</ul></details>` : ''}
      ${qs.some(q => q.th) ? `<p class="th-note"><a data-dtrain="${t.id}">在思路训练里只练这一类 ›</a></p>` : ''}
    </div></div>`;
  math(el);
  $$('#trList .qrow.cur').forEach(r => r.classList.remove('cur'));
  const row = $(`#trList .qrow[data-tsel="${t.id}"]`);
  if (row) { row.classList.add('cur'); row.scrollIntoView({ block: 'nearest' }); }
}
window.renderTrees = function (arg) {
  if (arg && TREES.some(t => t.id === arg) && arg !== TV.cur) { TV.cur = arg; TV.open.clear(); }
  if (!TV.cur && TREES.length) TV.cur = TREES[0].id;
  renderTreeList();
  renderTreeMain();
};
function treeStep(d) {
  const i = TREES.findIndex(t => t.id === TV.cur) + d;
  if (i >= 0 && i < TREES.length) go('trees', TREES[i].id);
}
function treeListToggle(show) {
  TV.nolist = !show;
  try { localStorage.setItem('math2viz.dtNoList', TV.nolist ? '1' : '0'); } catch (e) { /* ignore */ }
  $('#v-trees').classList.toggle('nolist', TV.nolist);
  const b = $('#trMain [data-dtlist]'); if (b) b.textContent = TV.nolist ? '☰ 列表' : '⇤ 收起列表';
}
$('#trList').addEventListener('click', e => { const r = e.target.closest('[data-tsel]'); if (r) go('trees', r.dataset.tsel); });
$('#trMain').addEventListener('click', e => {
  if (e.target.closest('a, [data-q]')) {
    const tr = e.target.closest('[data-dtrain]');
    if (tr && window.trainScope) trainScope(tr.dataset.dtrain);
    return;
  }
  const b = e.target.closest('[data-bopen]');
  if (b) { const p = b.dataset.bopen; if (TV.open.has(p)) TV.open.delete(p); else TV.open.add(p); const sc = $('#trMain').scrollTop; renderTreeMain(); $('#trMain').scrollTop = sc; return; }
  const st = e.target.closest('[data-dtstep]'); if (st) return treeStep(+st.dataset.dtstep);
  if (e.target.closest('[data-dtlist]')) treeListToggle(TV.nolist);
});
document.addEventListener('click', e => { const a = e.target.closest && e.target.closest('[data-tree]'); if (a) { closeModal(); go('trees', a.dataset.tree); } });
$('#v-trees').classList.toggle('nolist', TV.nolist);
addEventListener('keydown', e => {
  if (VIEW !== 'trees' || e.ctrlKey || e.metaKey || e.altKey || !$('#modal').hidden) return;
  if (e.target.closest && e.target.closest('input, select, textarea, [contenteditable]')) return;
  const k = e.key.toLowerCase();
  if (k === 'j' || e.key === 'ArrowDown') { e.preventDefault(); treeStep(1); }
  else if (k === 'k' || e.key === 'ArrowUp') { e.preventDefault(); treeStep(-1); }
  else if (k === 'l') treeListToggle(TV.nolist);
});
if (VIEW === 'trees') route();
