/* Thinking layer (scripts/thinking.py): per question the stages of the solution, the decision points (situation, the
   question to ask yourself, candidate moves with why they work / fail / are clumsier), the breakthrough idea and traps.
   Two uses: a "思路" section on the questions page, and the 思路训练 page — read the stem, then at each decision point
   pick the next move before seeing the reasons. Loaded after app.js and methods.js. */
const ST = D.strategies || [];
// question-type decision trees (trees.js draws them): a question belongs to a tree when one of its key methods is in scope
const TREES = D.trees || [];
const inScope = (mi, sc) => { const id = D.methods[mi] && D.methods[mi].id; return !!id && sc.some(s => id === s || (s.endsWith('*') && id.startsWith(s.slice(0, -1)))); };
const inTree = (q, t) => (q.me || []).some(m => m[1] && inScope(m[0], t.sc));
const qTrees = q => TREES.filter(t => inTree(q, t));
const treeLinks = q => { const ts = qTrees(q); return ts.length ? `<span class="dt-links">决策树：${ts.map(t => `<a data-tree="${t.id}">${esc(t.n)}</a>`).join('、')}</span>` : ''; };
const STAGE = ['审题定型', '转化化归', '执行计算', '收尾检验'];
const VD = [['chosen', '✓', '参考做法'], ['fails', '✗', '走不通'], ['worse', '△', '更繁']];
const tx = s => esc(s).replace(/\n/g, '<br>');  // $…$ is rendered by math() on the container
const stNames = ids => ids.filter(i => ST[i]).map(i => `<span class="th-st" title="${esc(ST[i].w)}">${esc(ST[i].n)}</span>`).join('、');
const thMethod = mi => mi >= 0 && D.methods[mi] ? `<a class="th-m" data-method="${D.methods[mi].id}" title="打开方法页">${esc(D.methods[mi].n)} ›</a>` : '';
const breakHtml = th => `<div class="th-break"><div class="th-k">突破口</div><div class="th-idea">${tx(th.b[0])}</div>
  <div class="th-origin">${tx(th.b[1])}${th.b[2].length ? ` <span class="th-sts">· ${stNames(th.b[2])}</span>` : ''}</div></div>`;
const trapsHtml = (th, open) => th.t.length ? `<details class="th-fold"${open ? ' open' : ''}><summary>易错 <span class="n">${th.t.length}</span></summary>
  <ul class="th-traps">${th.t.map(([s, t]) => `<li>${tx(t)}${s ? ` <span class="th-step">步骤 ${s}</span>` : ''}</li>`).join('')}</ul></details>` : '';
const stagesHtml = th => `<div class="th-flow">${th.st.map(([i, steps, goal]) => `<span class="th-sg s${i}" title="${esc(goal)}">${STAGE[i]}<small>${steps.join('·')}</small></span>`).join('<i>→</i>')}</div>`;
// one decision point. pick = the option the user chose (index into d.o) or null while undecided, order = display order,
// review = show it answered without a pick (questions page). Answered: the reference move and the pick show their reason,
// the others show theirs on click — the page stays light enough to read.
function decisionHtml(d, k, n, pick, order, review) {
  const open = review || pick != null;
  const opts = order.map((oi, j) => {
    const [label, mi, v, reason] = d.o[oi];
    if (!open) return `<button class="th-opt" data-pick="${oi}"><span class="key">${j + 1}</span><span class="th-l">${tx(label)}</span></button>`;
    const show = v === 0 || oi === pick;
    return `<div class="th-opt v${v}${oi === pick ? ' picked' : ''}${show ? ' show' : ''}" ${show ? '' : 'data-rshow'}>
      <div class="th-ol"><span class="th-ic">${VD[v][1]}</span><span class="th-l">${tx(label)}</span>
        <span class="th-v">${oi === pick ? '你的选择 · ' : ''}${VD[v][2]}</span></div>
      <div class="th-reason">${tx(reason)}${v === 0 ? ' ' + thMethod(mi) : ''}</div></div>`;
  }).join('');
  return `<div class="th-dec${open ? ' open' : ''}">
    <div class="th-dh">决策 ${k + 1}${n > 1 ? ` / ${n}` : ''}</div>
    <div class="th-sit">${tx(d.si)}</div>
    <div class="th-ask">${tx(d.a)}</div>
    <div class="th-opts">${opts}</div>
    ${open ? `<div class="th-sig"><b>信号</b> ${tx(d.sg)}${d.g.length ? ` <span class="th-sts">· ${stNames(d.g)}</span>` : ''}</div>` : ''}</div>`;
}
// a finished decision in the training flow: one line, expands on click
function pastHtml(d, k, pick, expanded, order) {
  if (expanded) return `<div class="th-pastwrap" data-texp="${k}" title="收起">${decisionHtml(d, k, 0, pick, order, false)}</div>`;
  const ref = d.o.find(o => o[2] === 0), my = d.o[pick];
  return `<div class="th-past" data-texp="${k}" title="展开"><span class="th-dh">决策 ${k + 1}</span>
    <span class="th-ic v${my[2]}">${VD[my[2]][1]}</span><span class="th-pl">${tx(my[0])}</span>
    ${my[2] ? `<span class="th-pr">参考：${tx(ref[0])}</span>` : ''}<span class="th-more">›</span></div>`;
}
// questions page / pop-up: the whole trace, answered
window.thinkHtml = function (q) {
  const th = q.th;
  if (!th) return '';
  return `<div class="th-read">${stagesHtml(th)}${breakHtml(th)}
    ${th.d.map((d, k) => decisionHtml(d, k, th.d.length, null, d.o.map((_, i) => i), true)).join('')}${trapsHtml(th, true)}
    <p class="th-note">思路由模型依据参考解答还原，"走不通 / 更繁"是推断，可能有误。<a data-train="${q.id}">到思路训练里练这道题 ›</a> ${treeLinks(q)}</p></div>`;
};
document.addEventListener('click', e => {
  const r = e.target.closest && e.target.closest('[data-rshow]');
  if (r && !e.target.closest('a')) r.classList.toggle('show');
});

/* ---------- 思路训练 ---------- */
// a branch's questions: the tree's questions with one of its methods as a key method, newest first (trees.js shows the same)
const branchQs = (t, br, pool = F) => pool.filter(q => inTree(q, t) && (q.me || []).some(m => m[1] && br.m.includes(m[0])))
  .sort((a, b) => b.y - a.y || a.id.localeCompare(b.id, 'en', { numeric: true }));
// the tree in reading order as a practice sequence: each question once, under the branch matching most of its key methods
// (first such branch on ties); questions no branch names go last. Branch: {p path, w situation, m methods, crumbs}
function treeSeq(t) {
  const brs = [];
  const walk = (nodes, path, crumbs, ask) => nodes.forEach((x, i) => {
    const p = path + '.' + i;
    if (x.q != null) return walk(x.b, p, crumbs, x.q);
    if (x.m.length) brs.push({ p, w: x.w, m: x.m, no: x.no, crumbs, ask });
    walk(x.s, p, [...crumbs, x.w], ask);
  });
  walk(t.r, 'r', [], '');
  const pool = F.filter(q => q.th && q.th.d.length && inTree(q, t));
  const home = new Map();
  for (const q of pool) {
    const core = (q.me || []).filter(m => m[1]).map(m => m[0]);
    // ties go to the branch naming the move the reference solution makes first, then any move it makes
    const chosen = q.th.d.map(d => (d.o.find(o => o[2] === 0) || [])[1]);
    let best = null, bn = 0;
    brs.forEach(br => {
      const hit = br.m.filter(mi => core.includes(mi)).length;
      if (!hit) return;
      const n = hit * 10 + (br.m.includes(chosen[0]) ? 5 : 0) + (chosen.some(c => br.m.includes(c)) ? 1 : 0);
      if (n > bn) { bn = n; best = br; }
    });
    home.set(q.id, best);
  }
  const seq = [];
  for (const br of brs) for (const q of branchQs(t, br, pool)) if (home.get(q.id) === br) seq.push({ id: q.id, br });
  const other = { p: null, w: '其他（树中没有单独列出的方法）', m: [], crumbs: [] };
  for (const q of pool) if (!home.get(q.id)) seq.push({ id: q.id, br: other });
  return seq;
}
const TR = { sub: '', sort: 'new', cur: null, list: [], seq: null, step: 0, picks: [], orders: [], exp: new Set(), scroll: false, nolist: false, hint: false, skip: false };
let TRAIN = {};  // qid -> {r: [1 right | 0 wrong per decision], t: time}; this browser only
try {
  TRAIN = JSON.parse(localStorage.getItem('math2viz.train') || '{}');
  TR.nolist = localStorage.getItem('math2viz.tNoList') === '1';
  Object.assign(TR, JSON.parse(localStorage.getItem('math2viz.tOpts') || '{}'));
} catch (e) { /* defaults */ }
const saveTrain = () => { try { localStorage.setItem('math2viz.train', JSON.stringify(TRAIN)); } catch (e) { /* storage unavailable */ } };
const saveOpts = () => { try { localStorage.setItem('math2viz.tOpts', JSON.stringify({ sub: TR.sub, sort: TR.sort, hint: TR.hint, skip: TR.skip })); } catch (e) { /* ignore */ } };
const trState = id => { const r = TRAIN[id]; return !r ? '' : r.r.every(Boolean) ? 'ok' : 'bad'; };
const shuffle = a => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const curTree = () => TR.sub.startsWith('tree:') ? TREES.find(t => 'tree:' + t.id === TR.sub) || null : null;
// progress over a list of question ids: practiced, all right, decisions right / total
function progress(ids) {
  let done = 0, ok = 0, dr = 0, dn = 0;
  for (const id of ids) { const r = TRAIN[id]; if (!r) continue; done++; if (r.r.every(Boolean)) ok++; dr += r.r.filter(Boolean).length; dn += r.r.length; }
  return { n: ids.length, done, ok, bad: done - ok, dr, dn };
}
window.treeProgress = (t, br) => progress((br ? branchQs(t, br) : F.filter(q => inTree(q, t))).filter(q => q.th).map(q => q.id));
const progBar = pr => `<span class="tr-bar" title="已练 ${pr.done} / ${pr.n}，全对 ${pr.ok}"><i class="ok" style="width:${pr.n ? pr.ok / pr.n * 100 : 0}%"></i><i class="bad" style="width:${pr.n ? pr.bad / pr.n * 100 : 0}%"></i></span>`;

function trainPool() {
  const tree = curTree();
  if (tree && TR.sort === 'tree') { TR.seq = treeSeq(tree); return TR.seq.map(x => qById[x.id]); }
  TR.seq = null;
  const qs = F.filter(q => q.th && q.th.d.length && (tree ? inTree(q, tree) : !TR.sub || q.sub === TR.sub));
  const rank = { '': 0, bad: 1, ok: 2 };
  return qs.sort((a, b) => TR.sort === 'todo' ? rank[trState(a.id)] - rank[trState(b.id)] || b.y - a.y
    : TR.sort === 'wrong' ? (trState(b.id) === 'bad') - (trState(a.id) === 'bad') || b.y - a.y
    : b.y - a.y || a.id.localeCompare(b.id, 'en', { numeric: true }));
}
const seqOf = id => TR.seq && TR.seq.find(x => x.id === id);
// a branch out of its tree: a bare answer ("能", "是") gets the question it answers; a nested branch gets its parent
const brWhen = br => /^(能|不能|是|否|有|没有|不是)$/.test(br.w.trim()) && br.ask ? `${br.ask.replace(/[？?]\s*$/, '')}：${br.w}` : br.w;
const brLabel = br => br.crumbs.length ? `${br.crumbs[br.crumbs.length - 1]} › ${brWhen(br)}` : brWhen(br);
const methodNames = m => m.map(mi => D.methods[mi] ? D.methods[mi].n : '').join('、');
function renderTrainList() {
  const el = $('#tList');
  if (!el.dataset.init) {
    el.dataset.init = 1;
    el.innerHTML = `<div class="ctl"><select id="tsub"><option value="">高数＋线代</option><option value="GS">高数</option><option value="LA">线代</option>
      ${TREES.length ? `<optgroup label="按题型（决策树）">${TREES.map(t => `<option value="tree:${t.id}">${esc(t.n)}</option>`).join('')}</optgroup>` : ''}</select>
      <select id="tsort"><option value="tree">按决策树的顺序</option><option value="new">新 → 旧</option><option value="todo">先练没做过的</option><option value="wrong">先练做错的</option></select>
      <button class="small" id="trand" title="随机一道（R）">随机一题</button>
      <label class="small" title="下一题时跳过已经全部选对的题"><input type="checkbox" id="tskip">跳过做对的</label>
      <label class="small" id="thintl" title="做题时就显示这道题在决策树中的分支（会提示方法）"><input type="checkbox" id="thint">提示分支</label></div>
      <div class="lst"><div id="tn" class="muted small" style="padding:6px 12px"></div><div id="trows"></div></div>`;
    const upd = () => {
      const was = curTree();
      TR.sub = $('#tsub').value; TR.sort = $('#tsort').value;
      if (curTree() && !was) TR.sort = 'tree';  // entering a tree: its own order by default
      saveOpts(); renderTrainList(); renderTrainMain();
    };
    ['#tsub', '#tsort'].forEach(x => $(x).addEventListener('input', upd));
    $('#trand').addEventListener('click', trainRandom);
    $('#tskip').addEventListener('change', e => { TR.skip = e.target.checked; saveOpts(); });
    $('#thint').addEventListener('change', e => { TR.hint = e.target.checked; saveOpts(); renderTrainList(); renderTrainMain(); });
  }
  const tree = curTree();
  if (!tree && TR.sort === 'tree') TR.sort = 'new';
  $('#tsub').value = TR.sub; $('#tsort').value = TR.sort;
  $('#tsort option[value="tree"]').hidden = !tree;
  $('#tskip').checked = TR.skip; $('#thint').checked = TR.hint;
  $('#thintl').hidden = !(tree && TR.sort === 'tree');
  const qs = trainPool();
  TR.list = qs.map(q => q.id);
  const pr = progress(TR.list);
  $('#tn').innerHTML = `${qs.length} 题 · 已练 ${pr.done}${pr.dn ? ` · 决策选对 ${pr.dr}/${pr.dn}` : ''} ${progBar(pr)}`;
  const row = q => {
    const s = trState(q.id);
    return `<div class="qrow${q.id === TR.cur ? ' cur' : ''}" data-tsel="${q.id}"><div class="h"><b>${q.y}·${esc(q.lb)}</b><span class="badge muted">${TYPE[q.ty]}</span>
      <span class="muted small">${q.th.d.length} 个决策</span>${s ? `<span class="tr-${s}" title="${s === 'ok' ? '全部选对' : '有选错的'}">${s === 'ok' ? '✓' : '✗'}</span>` : ''}</div>
      <div class="stem tex">${stemHtml(q)}</div></div>`;
  };
  let html = '';
  if (TR.seq) {  // grouped by branch, in tree order
    let br = null, k = 0;
    for (const x of TR.seq) {
      if (x.br !== br) {
        br = x.br; k++;
        const ids = TR.seq.filter(y => y.br === br).map(y => y.id), bp = progress(ids);
        html += `<div class="qyr tr-br"><span class="tr-bn">${k}</span><span class="tr-bw">${tx(brLabel(br))}${TR.hint && br.m.length ? ` <span class="muted small">· ${esc(methodNames(br.m))}</span>` : ''}</span>
          <span class="muted small">${bp.done}/${bp.n}</span></div>`;
      }
      html += row(qById[x.id]);
    }
  } else {
    let year = null;
    for (const q of qs) { if (q.y !== year) html += `<div class="qyr">${(year = q.y)} 年</div>`; html += row(q); }
  }
  $('#trows').innerHTML = html || '<p class="muted small" style="padding:6px 12px">当前筛选下没有带思路的题。</p>';
  if (TR.seq) math($('#trows'));
}
function trainStart(id) {
  const q = qById[id];
  TR.cur = id; TR.step = 0; TR.picks = []; TR.exp = new Set(); TR.orders = q.th.d.map(d => shuffle(d.o.map((_, i) => i)));
}
// where this question sits in the tree; shown after answering (or throughout with 提示分支)
function branchBox(x, tree, open) {
  if (!x || !x.br.p) return '';
  const path = [...x.br.crumbs, brWhen(x.br)].map(tx).join(' <i>›</i> ');
  return `<div class="tr-where${open ? '' : ' closed'}"><span class="th-k">在决策树中</span>
    <div class="tr-path">${esc(tree.n)} <i>›</i> ${path}</div>
    ${open ? `<div>${x.br.m.map(mi => `<a class="mtag core" data-method="${D.methods[mi].id}">${esc(D.methods[mi].n)}</a>`).join('')}
      ${x.br.no ? `<span class="muted small">${tx(x.br.no)}</span>` : ''}</div>` : ''}</div>`;
}
// the next question for "下一题": the next in the list, skipping all-right ones when asked
function nextIndex(d) {
  let i = TR.list.indexOf(TR.cur) + d;
  if (TR.skip && d > 0) while (i < TR.list.length && trState(TR.list[i]) === 'ok') i++;
  return i >= 0 && i < TR.list.length ? i : -1;
}
function renderTrainMain() {
  const el = $('#tMain');
  const q = qById[TR.cur];
  if (!q || !q.th) { el.innerHTML = `<p class="muted" style="text-align:center;margin-top:60px">${TR.list.length ? '从左侧选一道题开始。' : '还没有思路数据（运行 scripts/thinking.py 后重建 data.js）。'}</p>`; return; }
  const th = q.th, n = th.d.length, finished = TR.picks.length === n;
  const pos = TR.list.indexOf(q.id);
  const cur = Math.min(TR.step, n - 1);
  const answered = TR.picks.length > cur;
  const past = th.d.slice(0, cur).map((d, k) => pastHtml(d, k, TR.picks[k], TR.exp.has(k), TR.orders[k])).join('');
  const now = decisionHtml(th.d[cur], cur, n, TR.picks[cur] ?? null, TR.orders[cur], false);
  const right = finished ? TR.picks.filter((p, k) => th.d[k].o[p][2] === 0).length : 0;
  const x = finished ? qSections(q) : null;
  const tree = curTree(), sx = seqOf(q.id);
  const ni = nextIndex(1), nx = ni >= 0 ? seqOf(TR.list[ni]) : null;
  // session bar while practising a tree in its order
  let bar = '';
  if (tree && TR.seq) {
    const pr = progress(TR.list);
    bar = `<div class="tr-sess"><b>${esc(tree.n)}</b><span class="muted small">第 ${pos + 1} / ${TR.list.length} 题 · 已练 ${pr.done}${pr.dn ? ` · 选对 ${Math.round(pr.dr / pr.dn * 100)}%` : ''}</span>
      ${progBar(pr)}<a class="small" data-tback title="回到决策树中这道题所在的分支">回到决策树 ›</a></div>`;
  }
  // finishing the last question of a branch: a small summary of the branch
  let brEnd = '';
  if (finished && sx && (!nx || nx.br !== sx.br)) {
    const bp = progress(TR.seq.filter(y => y.br === sx.br).map(y => y.id));
    brEnd = `<div class="tr-brend">这一分支练完了：${bp.done}/${bp.n} 题，全对 ${bp.ok} 题${bp.dn ? `，决策选对 ${bp.dr}/${bp.dn}` : ''}</div>`;
  }
  const nextLabel = nx && sx && nx.br !== sx.br ? `下一分支：${tx(clip(brLabel(nx.br), 60))}` : '';
  el.innerHTML = `<div class="kpd train">
    <div class="kpd-top"><button class="icon" data-tlist title="收起或展开左侧列表（L）">${TR.nolist ? '☰ 列表' : '⇤ 收起列表'}</button>
      <span class="crumb muted small">思路训练 · ${q.sub === 'LA' ? '线性代数' : '高等数学'} · ${TYPE[q.ty]}题</span>
      <button class="small" data-qopen="${q.id}" title="在真题页打开">真题页</button>
      ${pos >= 0 ? `<span class="kp-nav"><button class="icon" data-tstep="-1" ${pos > 0 ? '' : 'disabled'} title="上一题（K）">↑</button><span class="muted small">${pos + 1} / ${TR.list.length}</span><button class="icon" data-tstep="1" ${ni >= 0 ? '' : 'disabled'} title="下一题（J）">↓</button></span>` : ''}</div>
    <div class="th-col">
      ${bar}
      <div class="th-qh">${q.y} 年 第 ${esc(q.lb)} 题${TRAIN[q.id] && !finished ? ` <span class="tr-${trState(q.id)}">${trState(q.id) === 'ok' ? '✓ 上次全对' : '✗ 上次有错'}</span>` : ''}</div>
      ${tree && TR.hint && !finished ? branchBox(sx, tree, true) : ''}
      <div class="th-stem">${stemBlock(q)}</div>
      ${past}${now}
      ${answered && !finished ? `<div class="th-go"><button class="primary" data-tnext>下一个决策 →</button><span class="muted small">Enter</span></div>` : ''}
      ${!answered && cur === 0 && !TRAIN[q.id] ? '<p class="th-note">先自己想下一步，再按 1–4 选择。</p>' : ''}
      ${finished ? `<div class="th-end">
        <div class="th-score"><b>${right}</b> / ${n}<span>${right === n ? '和参考解答的思路一致' : '选了别的做法不一定错，看理由里说它卡在哪'}</span></div>
        ${tree ? branchBox(sx, tree, true) : ''}
        ${breakHtml(th)}${stagesHtml(th)}${trapsHtml(th, false)}
        ${!tree && qTrees(q).length ? `<p class="th-note">${treeLinks(q)}</p>` : ''}
        <details class="th-fold"><summary>完整解答</summary>${x.ans}${x.steps}</details>
        ${brEnd}
        <div class="th-go">${ni >= 0 ? `<button class="primary" data-tstep="1">下一题 →</button><span class="muted small">Enter</span>${nextLabel ? `<span class="tr-next">${nextLabel}</span>` : ''}`
          : `<span class="muted">${tree ? '这一类练完了。' : '列表已到底。'}</span>${tree ? ' <a data-tback>回到决策树 ›</a>' : ''}`}
          <button class="small" data-tagain>重做</button></div></div>` : ''}
    </div></div>`;
  math(el);
  if (TR.scroll) { TR.scroll = false; const t = finished ? el.querySelector('.th-end') : [...el.querySelectorAll('.th-dec')].pop(); if (t) t.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
  else el.scrollTop = 0;
  $$('#trows .qrow.cur').forEach(r => r.classList.remove('cur'));
  const row = $(`#trows .qrow[data-tsel="${q.id}"]`);
  if (row) { row.classList.add('cur'); row.scrollIntoView({ block: 'nearest' }); }
}
function trainPick(oi) {
  const q = qById[TR.cur];
  if (!q || TR.picks.length > TR.step) return;
  TR.picks.push(oi);
  TR.scroll = true;
  if (TR.picks.length === q.th.d.length) {  // finished: record the result of this attempt
    TRAIN[q.id] = { r: TR.picks.map((p, k) => +(q.th.d[k].o[p][2] === 0)), t: Date.now() };
    saveTrain();
    renderTrainList();
  }
  renderTrainMain();
}
function trainNext() {
  const q = qById[TR.cur];
  if (!q) return;
  if (TR.picks.length === q.th.d.length) return trainStep(1);
  if (TR.picks.length > TR.step) { TR.step++; TR.scroll = true; renderTrainMain(); }
}
function trainStep(d) {
  const i = nextIndex(d);
  if (i >= 0) go('train', TR.list[i]);
}
function trainRandom() {
  const todo = TR.list.filter(id => !TRAIN[id] && id !== TR.cur);
  const pool = todo.length ? todo : TR.list.filter(id => id !== TR.cur);
  if (pool.length) go('train', pool[Math.floor(Math.random() * pool.length)]);
}
function trainListToggle(show) {
  TR.nolist = !show;
  try { localStorage.setItem('math2viz.tNoList', TR.nolist ? '1' : '0'); } catch (e) { /* ignore */ }
  $('#v-train').classList.toggle('nolist', TR.nolist);
  const b = $('#tMain [data-tlist]'); if (b) b.textContent = TR.nolist ? '☰ 列表' : '⇤ 收起列表';
}
// from a decision tree: practise that kind of question in the tree's order, starting at qid, or where it was left off
window.trainTree = function (tid, qid) {
  TR.sub = 'tree:' + tid; TR.sort = 'tree'; saveOpts();
  if (!qid) {
    const seq = treeSeq(TREES.find(t => t.id === tid));
    const todo = seq.find(x => !TRAIN[x.id]) || seq.find(x => trState(x.id) === 'bad') || seq[0];
    qid = todo && todo.id;
  }
  TR.cur = null;
  if (location.hash === '#train/' + qid) renderTrain(qid); else go('train', qid || '');
};
window.trainScope = id => trainTree(id);
window.renderTrain = function (arg) {
  renderTrainList();
  const id = arg && qById[arg] && qById[arg].th ? arg : TR.cur && TR.list.includes(TR.cur) ? TR.cur : TR.list[0];
  if (id && id !== TR.cur) trainStart(id);
  if (!id) TR.cur = null;
  renderTrainMain();
};
$('#tList').addEventListener('click', e => { const r = e.target.closest('[data-tsel]'); if (r) go('train', r.dataset.tsel); });
$('#tMain').addEventListener('click', e => {
  const p = e.target.closest('[data-pick]'); if (p) return trainPick(+p.dataset.pick);
  if (e.target.closest('[data-tnext]')) return trainNext();
  const st = e.target.closest('[data-tstep]'); if (st) return trainStep(+st.dataset.tstep);
  if (e.target.closest('[data-tlist]')) return trainListToggle(TR.nolist);
  if (e.target.closest('[data-tagain]')) { trainStart(TR.cur); renderTrainMain(); return; }
  if (e.target.closest('[data-tback]')) { const t = curTree(), x = seqOf(TR.cur); if (t && window.treeFocus) treeFocus(t.id, x && x.br.p, TR.cur); return; }
  const ex = e.target.closest('[data-texp]');
  if (ex && !e.target.closest('a, [data-rshow]')) {
    const k = +ex.dataset.texp;
    if (TR.exp.has(k)) TR.exp.delete(k); else TR.exp.add(k);
    return renderTrainMain();
  }
  const op = e.target.closest('[data-qopen]'); if (op) go('questions', op.dataset.qopen);
});
document.addEventListener('click', e => {
  const a = e.target.closest && e.target.closest('[data-train]');
  if (!a) return;
  closeModal();
  const [tid, qid] = a.dataset.train.includes('|') ? a.dataset.train.split('|') : [null, a.dataset.train];
  if (tid) trainTree(tid, qid); else go('train', qid);
});
$('#v-train').classList.toggle('nolist', TR.nolist);
addEventListener('keydown', e => {
  if (VIEW !== 'train' || e.ctrlKey || e.metaKey || e.altKey || !$('#modal').hidden) return;
  if (e.target.closest && e.target.closest('input, select, textarea, [contenteditable]')) return;
  const q = qById[TR.cur], k = e.key.toLowerCase();
  if (/^[1-9]$/.test(e.key) && q && TR.picks.length === TR.step && TR.step < q.th.d.length) {
    const oi = TR.orders[TR.step][+e.key - 1];
    if (oi != null) { e.preventDefault(); trainPick(oi); }
  } else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); trainNext(); }
  else if (k === 'j' || e.key === 'ArrowDown') { e.preventDefault(); trainStep(1); }
  else if (k === 'k' || e.key === 'ArrowUp') { e.preventDefault(); trainStep(-1); }
  else if (k === 'r') trainRandom();
  else if (k === 'l') trainListToggle(TR.nolist);
  else if (k === 't' && curTree()) { const x = seqOf(TR.cur); if (window.treeFocus) treeFocus(curTree().id, x && x.br.p, TR.cur); }
});
if (VIEW === 'train') route();
