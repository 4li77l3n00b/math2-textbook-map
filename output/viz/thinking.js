/* Thinking layer (scripts/thinking.py): per question the stages of the solution, the decision points (situation, the
   question to ask yourself, candidate moves with why they work / fail / are clumsier), the breakthrough idea and traps.
   Two uses: a "思路" section on the questions page, and the 思路训练 page — read the stem, then at each decision point
   pick the next move before seeing the reasons. Loaded after app.js and methods.js. */
const ST = D.strategies || [];
const STAGE = ['审题定型', '转化化归', '执行计算', '收尾检验'];
const VD = [['chosen', '✓ 参考解答的做法'], ['fails', '✗ 走不通'], ['worse', '△ 更繁']];
const tx = s => esc(s).replace(/\n/g, '<br>');  // $…$ is rendered by math() on the container
const stChip = i => ST[i] ? `<span class="chip st" title="${esc(ST[i].w)}">${esc(ST[i].n)}</span>` : '';
const thMethod = mi => mi >= 0 && D.methods[mi] ? ` <a class="mtag" data-method="${D.methods[mi].id}">${esc(D.methods[mi].n)}</a>` : '';
const breakHtml = th => `<div class="th-break"><span class="lbl">突破口</span><div><div>${tx(th.b[0])}</div>
  <div class="muted small">怎么想到：${tx(th.b[1])}</div><div>${th.b[2].map(stChip).join('')}</div></div></div>`;
const trapsHtml = th => th.t.length ? `<div class="th-traps"><span class="lbl">易错</span><ul>${th.t.map(([s, t]) => `<li>${s ? `<span class="muted small">步骤 ${s}</span> ` : ''}${tx(t)}</li>`).join('')}</ul></div>` : '';
const stagesHtml = th => `<div class="th-stages">${th.st.map(([i, steps, goal]) => `<div class="th-stage s${i}" style="flex:${Math.max(steps.length, 1)}" title="${esc(goal)}">
  <b>${STAGE[i]}</b> <span class="muted small">步骤 ${steps.join('、')}</span><div class="small">${tx(goal)}</div></div>`).join('')}</div>`;
// one decision point; pick = the option the user chose (index into d.o), or null while undecided; order = display order
function decisionHtml(d, k, pick, order, done) {
  const open = done || pick != null;
  const opts = order.map((oi, n) => {
    const [label, mi, v, reason] = d.o[oi];
    const cls = open ? ` v-${VD[v][0]}${oi === pick ? ' picked' : ''}` : '';
    return `<div class="th-opt${cls}" ${open ? '' : `data-pick="${oi}"`}><div class="th-ol"><span class="key">${n + 1}</span><span>${tx(label)}</span>
      ${open ? `<span class="th-v">${VD[v][1]}${oi === pick ? ' · 你的选择' : ''}</span>` : ''}</div>
      ${open ? `<div class="th-reason">${tx(reason)}${thMethod(mi)}</div>` : ''}</div>`;
  }).join('');
  return `<div class="th-dec${open ? ' open' : ''}">
    <div class="th-dh"><span class="badge muted">决策 ${k + 1}</span> <span class="muted small">从步骤 ${d.s} 开始</span></div>
    <div class="th-sit"><span class="lbl">局面</span>${tx(d.si)}</div>
    <div class="th-ask">${tx(d.a)}</div>
    <div class="th-opts">${opts}</div>
    ${open ? `<div class="th-sig"><span class="lbl">信号</span>${tx(d.sg)} ${d.g.map(stChip).join('')}</div>` : ''}</div>`;
}
// questions page / pop-up: the whole trace, everything shown
window.thinkHtml = function (q) {
  const th = q.th;
  if (!th) return '';
  return `${stagesHtml(th)}${th.d.map((d, k) => decisionHtml(d, k, null, d.o.map((_, i) => i), true)).join('')}${breakHtml(th)}${trapsHtml(th)}
    <p class="muted small">思路由模型根据参考解答还原；"走不通 / 更繁"的理由是推断，可能有误。<a data-train="${q.id}">在思路训练中练这道题</a></p>`;
};

/* ---------- 思路训练 ---------- */
const TR = { sub: '', sort: 'new', cur: null, list: [], step: 0, picks: [], orders: [], nolist: false };
let TRAIN = {};  // qid -> {r: [1 right | 0 wrong per decision], t: time}; this browser only
try { TRAIN = JSON.parse(localStorage.getItem('math2viz.train') || '{}'); TR.nolist = localStorage.getItem('math2viz.tNoList') === '1'; } catch (e) { /* defaults */ }
const saveTrain = () => { try { localStorage.setItem('math2viz.train', JSON.stringify(TRAIN)); } catch (e) { /* storage unavailable */ } };
const trState = id => { const r = TRAIN[id]; return !r ? '' : r.r.every(Boolean) ? 'ok' : 'bad'; };
const shuffle = a => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

function trainPool() {
  const qs = F.filter(q => q.th && q.th.d.length && (!TR.sub || q.sub === TR.sub));
  const rank = { '': 0, bad: 1, ok: 2 };
  return qs.sort((a, b) => TR.sort === 'todo' ? rank[trState(a.id)] - rank[trState(b.id)] || b.y - a.y
    : TR.sort === 'wrong' ? (trState(b.id) === 'bad') - (trState(a.id) === 'bad') || b.y - a.y
    : b.y - a.y || a.id.localeCompare(b.id, 'en', { numeric: true }));
}
function renderTrainList() {
  const el = $('#tList');
  if (!el.dataset.init) {
    el.dataset.init = 1;
    el.innerHTML = `<div class="ctl"><select id="tsub"><option value="">高数＋线代</option><option value="GS">高数</option><option value="LA">线代</option></select>
      <select id="tsort"><option value="new">新 → 旧</option><option value="todo">先练没做过的</option><option value="wrong">先练做错的</option></select>
      <button class="small" id="trand" title="随机一道（R）">随机一题</button></div>
      <div class="lst"><div id="tn" class="muted small" style="padding:6px 12px"></div><div id="trows"></div></div>`;
    const upd = () => { TR.sub = $('#tsub').value; TR.sort = $('#tsort').value; renderTrainList(); };
    ['#tsub', '#tsort'].forEach(x => $(x).addEventListener('input', upd));
    $('#trand').addEventListener('click', trainRandom);
  }
  const qs = trainPool();
  TR.list = qs.map(q => q.id);
  const done = qs.filter(q => TRAIN[q.id]);
  const nd = done.reduce((s, q) => s + TRAIN[q.id].r.length, 0), nr = done.reduce((s, q) => s + TRAIN[q.id].r.filter(Boolean).length, 0);
  $('#tn').textContent = `${qs.length} 题可练 · 已练 ${done.length}${nd ? ` · 决策选对 ${nr}/${nd}` : ''}` +
    (D.questions.filter(q => q.th).length < N_Q ? '（目前只有试标的题）' : '');
  let year = null;
  $('#trows').innerHTML = qs.map(q => {
    const h = q.y !== year ? `<div class="qyr">${(year = q.y)} 年</div>` : '';
    const s = trState(q.id);
    return `${h}<div class="qrow${q.id === TR.cur ? ' cur' : ''}" data-tsel="${q.id}"><div class="h"><b>${esc(q.lb)}</b><span class="badge muted">${TYPE[q.ty]}</span>
      <span class="muted small">${q.th.d.length} 个决策</span>${s ? `<span class="tr-${s}" title="${s === 'ok' ? '全部选对' : '有选错的'}">${s === 'ok' ? '✓' : '✗'}</span>` : ''}</div>
      <div class="stem tex">${stemHtml(q)}</div></div>`;
  }).join('') || '<p class="muted small" style="padding:6px 12px">当前筛选下没有带思路的题。</p>';
}
function trainStart(id) {
  const q = qById[id];
  TR.cur = id; TR.step = 0; TR.picks = []; TR.orders = q.th.d.map(d => shuffle(d.o.map((_, i) => i)));
}
function renderTrainMain() {
  const el = $('#tMain');
  const q = qById[TR.cur];
  if (!q || !q.th) { el.innerHTML = `<p class="muted" style="text-align:center;margin-top:60px">${TR.list.length ? '从左侧选一道题开始。' : '还没有思路数据（运行 scripts/thinking.py 后重建 data.js）。'}</p>`; return; }
  const th = q.th, n = th.d.length, finished = TR.picks.length === n;
  const pos = TR.list.indexOf(q.id);
  const shown = th.d.slice(0, Math.min(TR.step + 1, n));
  let next = '';
  if (TR.picks.length > TR.step) next = TR.step + 1 < n
    ? `<button class="primary" data-tnext>下一个决策 →</button> <span class="muted small">Enter</span>`
    : '';
  const res = finished ? TR.picks.map((p, k) => th.d[k].o[p][2] === 0) : null;
  const x = finished ? qSections(q) : null;
  el.innerHTML = `<div class="kpd train">
    <div class="kpd-top"><button class="icon" data-tlist title="收起或展开左侧列表（L）">${TR.nolist ? '☰ 列表' : '⇤ 收起列表'}</button>
      <span class="crumb muted small">思路训练 · ${q.sub === 'LA' ? '线性代数' : '高等数学'} · ${TYPE[q.ty]}题</span>
      <button class="small" data-qopen="${q.id}" title="在真题页打开">在真题页打开</button>
      ${pos >= 0 ? `<span class="kp-nav"><button class="icon" data-tstep="-1" ${pos > 0 ? '' : 'disabled'} title="上一题（K）">↑</button><span class="muted small">${pos + 1} / ${TR.list.length}</span><button class="icon" data-tstep="1" ${pos < TR.list.length - 1 ? '' : 'disabled'} title="下一题（J）">↓</button></span>` : ''}</div>
    <h1 class="kp-title">${q.y} 年 第 ${esc(q.lb)} 题</h1>
    ${stemBlock(q)}
    <p class="muted small th-hint">先自己想：每到一个决策点，读局面和问题，选你会走的下一步（数字键 1–${Math.max(...th.d.map(d => d.o.length))}），再看各个做法的理由。</p>
    ${shown.map((d, k) => decisionHtml(d, k, TR.picks[k] ?? null, TR.orders[k], false)).join('')}
    ${next}
    ${finished ? `<div class="th-done"><b>${res.filter(Boolean).length} / ${n}</b> 个决策与参考解答一致
        ${res.every(Boolean) ? '' : '<span class="muted small">——选了别的做法不一定错，看看理由里说它卡在哪</span>'}</div>
      ${breakHtml(th)}${trapsHtml(th)}
      <h3>阶段</h3>${stagesHtml(th)}
      <details class="th-full"><summary>完整解答（答案、方法与步骤）</summary>${x.ans}${x.methods}${x.steps}</details>
      <p>${pos < TR.list.length - 1 ? '<button class="primary" data-tstep="1">下一题 →</button> <span class="muted small">Enter</span>' : ''}
        <button class="small" data-tagain>重做这道</button></p>` : ''}
  </div>`;
  math(el);
  const cur = el.querySelectorAll('.th-dec')[TR.step];
  if (cur && TR.step > 0) cur.scrollIntoView({ block: 'start', behavior: 'smooth' });
  $$('#trows .qrow.cur').forEach(r => r.classList.remove('cur'));
  const row = $(`#trows .qrow[data-tsel="${q.id}"]`);
  if (row) { row.classList.add('cur'); row.scrollIntoView({ block: 'nearest' }); }
}
function trainPick(oi) {
  const q = qById[TR.cur];
  if (!q || TR.picks.length > TR.step) return;
  TR.picks.push(oi);
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
  if (TR.picks.length > TR.step) { TR.step++; renderTrainMain(); }
}
function trainStep(d) {
  const i = TR.list.indexOf(TR.cur) + d;
  if (i >= 0 && i < TR.list.length) go('train', TR.list[i]);
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
  const op = e.target.closest('[data-qopen]'); if (op) go('questions', op.dataset.qopen);
});
document.addEventListener('click', e => { const a = e.target.closest && e.target.closest('[data-train]'); if (a) { closeModal(); go('train', a.dataset.train); } });
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
});
if (VIEW === 'train') route();
