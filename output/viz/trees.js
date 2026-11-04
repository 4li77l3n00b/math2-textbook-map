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
    const n = treeQs(t).length, pr = treeProgress(t);
    html += `<div class="qrow dt-row${t.id === TV.cur ? ' cur' : ''}" data-tsel="${t.id}"><div class="h"><b>${esc(t.n)}</b>
      <span class="muted small">${pr.done ? `${pr.done}/` : ''}${n} 题</span>${t.r.length ? '' : '<span class="badge muted">待写</span>'}</div>
      ${pr.done ? progBar(pr) : ''}</div>`;
  }
  el.innerHTML = `<div class="lst">${html || '<p class="muted small" style="padding:6px 12px">还没有决策树。</p>'}</div>`;
}
// branchQs (thinking.js): the tree's questions using one of the branch's methods as a key method, newest first
const trMark = id => { const s = trState(id); return s ? `<span class="tr-${s}">${s === 'ok' ? '✓' : '✗'}</span>` : ''; };
const prText = pr => pr.done ? `<span class="dt-pr" title="已练 ${pr.done} / ${pr.n}，全对 ${pr.ok}">${pr.done}/${pr.n}${pr.bad ? ` <i class="tr-bad">✗${pr.bad}</i>` : ''}</span>` : '';
function nodesHtml(t, nodes, path) {
  return nodes.map((x, i) => {
    const p = path + '.' + i;
    if (x.q != null) return `<div class="dt-node"><div class="dt-q">${tx(x.q)}</div><div class="dt-brs">${nodesHtml(t, x.b, p)}</div></div>`;
    const qs = x.m.length ? branchQs(t, x) : [];
    const open = TV.open.has(p), pr = qs.length ? treeProgress(t, x) : null;
    return `<div class="dt-br${x.s.length ? ' has-sub' : ''}">
      <div class="dt-bh"${qs.length ? ` data-bopen="${p}" title="${open ? '收起' : '看真题'}"` : ''}>
        <span class="dt-w">${tx(x.w)}</span>
        ${x.m.map(mi => `<a class="mtag core" data-method="${D.methods[mi].id}">${esc(D.methods[mi].n)}</a>`).join('')}
        ${qs.length ? `<span class="dt-n${open ? ' on' : ''}">${qs.length} 题 ${open ? '▴' : '▾'}</span>${prText(pr)}` : ''}</div>
      ${x.no ? `<div class="dt-no">${tx(x.no)}</div>` : ''}
      ${open ? `<div class="dt-qs">${qs.map(q => `<div class="dt-qi${q.id === TV.hl ? ' hl' : ''}" data-q="${q.id}"><span class="dt-qh">${q.y}·${esc(q.lb)}</span><span class="stem">${stemHtml(q)}</span>
        ${trMark(q.id)}${q.th ? `<a class="dt-tr" data-train="${t.id}|${q.id}" title="按这棵树的顺序，从这道题开始练">练 ›</a>` : ''}</div>`).join('')}</div>` : ''}
      ${x.s.length ? `<div class="dt-sub">${nodesHtml(t, x.s, p)}</div>` : ''}</div>`;
  }).join('');
}
function renderTreeMain() {
  const el = $('#trMain');
  const t = TREES.find(x => x.id === TV.cur);
  if (!t) { el.innerHTML = '<p class="muted" style="text-align:center;margin-top:60px">从左侧选一类题。</p>'; return; }
  const qs = treeQs(t), pos = TREES.indexOf(t), pr = treeProgress(t);
  const resume = pr.done && pr.done < pr.n;
  el.innerHTML = `<div class="kpd dtree">
    <div class="kpd-top"><button class="icon" data-dtlist title="收起或展开左侧列表（L）">${TV.nolist ? '☰ 列表' : '⇤ 收起列表'}</button>
      <span class="crumb muted small">决策树 · ${esc(treeGroup(t))}</span>
      <span class="kp-nav"><button class="icon" data-dtstep="-1" ${pos > 0 ? '' : 'disabled'} title="上一类（K）">↑</button><span class="muted small">${pos + 1} / ${TREES.length}</span><button class="icon" data-dtstep="1" ${pos < TREES.length - 1 ? '' : 'disabled'} title="下一类（J）">↓</button></span></div>
    <div class="th-col">
      <h1 class="kp-title">${esc(t.n)} <span class="muted small">${qs.length} 题</span></h1>
      ${t.ab ? `<p class="dt-ab">${tx(t.ab)}</p>` : ''}
      ${qs.some(q => q.th) ? `<div class="dt-go"><button class="primary" data-dttrain="${t.id}" title="按树的顺序${resume ? '，从第一道没练过的题' : ''}开始">${resume ? '继续练' : pr.done ? '再练一遍' : '按树的顺序练'} →</button>
        ${resume ? `<button class="small" data-dttrain0="${t.id}">从头练</button>` : ''}
        ${pr.done ? `<span class="muted small">已练 ${pr.done} / ${pr.n}，全对 ${pr.ok}${pr.dn ? `，决策选对 ${Math.round(pr.dr / pr.dn * 100)}%` : ''}</span>${progBar(pr)}` : '<span class="muted small">从第一个分支的第一道题开始，逐题往下练</span>'}</div>` : ''}
      ${t.r.length ? `<div class="dt-tree">${nodesHtml(t, t.r, 'r')}</div>` : '<p class="muted">这棵树还没写。</p>'}
      ${t.pit.length ? `<details class="th-fold" open><summary>常见误入 <span class="n">${t.pit.length}</span></summary><ul class="th-traps">${t.pit.map(p => `<li>${tx(p)}</li>`).join('')}</ul></details>` : ''}
    </div></div>`;
  math(el);
  $$('#trList .qrow.cur').forEach(r => r.classList.remove('cur'));
  const row = $(`#trList .qrow[data-tsel="${t.id}"]`);
  if (row) { row.classList.add('cur'); row.scrollIntoView({ block: 'nearest' }); }
}
window.renderTrees = function (arg) {
  if (arg && TREES.some(t => t.id === arg) && arg !== TV.cur) { TV.cur = arg; TV.open.clear(); TV.hl = null; }
  if (!TV.cur && TREES.length) TV.cur = TREES[0].id;
  renderTreeList();
  renderTreeMain();
};
// from the training page: show the tree with the question's branch open and the question highlighted
window.treeFocus = function (tid, path, qid) {
  TV.cur = tid; TV.open.clear(); TV.hl = qid;
  if (path) TV.open.add(path);
  if (location.hash === '#trees/' + tid) renderTrees(tid); else go('trees', tid);
  setTimeout(() => { const r = $('#trMain .dt-qi.hl') || (path && $(`#trMain [data-bopen="${path}"]`)); if (r) r.scrollIntoView({ block: 'center' }); }, 30);
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
  const tr = e.target.closest('[data-dttrain], [data-dttrain0]');
  if (tr) {
    const tid = tr.dataset.dttrain || tr.dataset.dttrain0;
    if (tr.dataset.dttrain0) { const seq = treeSeq(TREES.find(t => t.id === tid)); return trainTree(tid, seq[0] && seq[0].id); }
    return trainTree(tid);
  }
  if (e.target.closest('a, [data-q]')) return;
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
