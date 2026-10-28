/* ---------- solving methods (#methods) ----------
   Question-type methods: the taxonomy and its recognition signals are written by Claude (output/methods/taxonomy.txt),
   the exam questions are labelled with the methods they use, at which steps, and what in the stem points to it
   (methods.py). Left: the methods grouped like the taxonomy; right: signal, years, knowledge points it leans on,
   methods it comes with, and the questions (key method first). Counts follow the year / question-type filter. */
const MT = D.methods || [];
const MV = { q: '', sort: 'book', core: false, cur: null, order: [], nolist: false, role: 'all', all: false };
try { MV.nolist = localStorage.getItem('math2viz.mNoList') === '1'; } catch (e) { /* defaults */ }
MT.forEach((m, i) => { m.i = i; m.uses = []; });
D.questions.forEach(q => (q.me || []).forEach(([mi, core, steps, cue, why]) => {
  if (MT[mi]) MT[mi].uses.push({ q, core, steps, cue, why });
}));
MT.forEach(m => { m.search = [m.n, m.s, m.g, m.id, ...m.uses.map(u => u.cue)].join(' ').toLowerCase(); });

function mCounts() {  // per method: [key, incidental] uses among the filtered questions
  const inF = new Set(F);
  return MT.map(m => m.uses.reduce((a, u) => { if (inF.has(u.q)) a[u.core ? 0 : 1]++; return a; }, [0, 0]));
}
function renderMethodList(force) {
  const box = $('#mList');
  if (!box.dataset.init) {
    box.dataset.init = 1;
    box.innerHTML = `<div class="ctl"><input type="search" id="mq" placeholder="搜索方法名、识别信号、题干特征…">
      <select id="msort"><option value="book">按体系顺序</option><option value="core">按作关键方法的题数</option><option value="all">按用到的题数</option></select>
      <label class="small" title="只列出在当前筛选下至少作为一道题的关键方法出现的方法"><input type="checkbox" id="mcore">只看作关键方法的</label></div><div class="lst"></div>`;
    const upd = () => { MV.q = $('#mq').value.trim(); MV.sort = $('#msort').value; MV.core = $('#mcore').checked; renderMethodList(); };
    ['#mq', '#msort', '#mcore'].forEach(s => $(s, box).addEventListener('input', upd));
  }
  const cnt = mCounts();
  const words = MV.q.toLowerCase().split(/\s+/).filter(Boolean);
  const ms = MT.filter(m => (!MV.core || cnt[m.i][0]) && (!words.length || words.every(w => m.search.includes(w))));
  const key = { book: m => m.i, core: m => -cnt[m.i][0] * 1e4 - cnt[m.i][1], all: m => -(cnt[m.i][0] + cnt[m.i][1]) * 1e4 - cnt[m.i][0] }[MV.sort];
  ms.sort((a, b) => key(a) - key(b) || a.i - b.i);
  MV.order = ms.map(m => m.i);
  const lst = $('.lst', box), sig = MV.sort + '|' + MV.order.join(',') + '|' + F.length;
  if (!force && lst.dataset.sig === sig) {  // only the selection moved
    $$('.ci.cur', lst).forEach(e => e.classList.remove('cur'));
    const c = $(`.ci[data-msel="${MV.cur}"]`, lst); if (c) c.classList.add('cur');
    return;
  }
  lst.dataset.sig = sig;
  const max = Math.max(1, ...cnt.map(c => c[0] + c[1]));
  const book = MV.sort === 'book', rows = [];
  let g = null;
  for (const m of ms) {
    if (book && m.g !== g) {
      g = m.g;
      rows.push(`<div class="kch">${esc(g)} <span class="muted small">${ms.filter(x => x.g === g).length} 个</span></div>`);
    }
    const [c, a] = cnt[m.i];
    rows.push(`<div class="ci${MV.cur === m.i ? ' cur' : ''}" data-msel="${m.i}"><div><div class="nm">${esc(m.n)}</div>
      <div class="s">${book ? '' : esc(m.g) + ' · '}关键 ${c} · 顺带 ${a}</div></div>
      <div class="bars"><div class="hb mb"><i class="core" style="width:${100 * c / max}%"></i><i style="width:${100 * a / max}%"></i></div></div></div>`);
  }
  lst.innerHTML = `<div class="muted small" style="padding:6px 12px">${ms.length} 个方法 · ${F.length} 道题在筛选范围内</div>` + rows.join('');
}
$('#mList').addEventListener('click', e => { const c = e.target.closest('[data-msel]'); if (c) go('methods', MT[+c.dataset.msel].id); });

function mYearChart(core, aux) {  // stacked: key uses dark, incidental uses light
  const n = Y_MAX - Y_MIN + 1, bw = 14, H2 = 46;
  const mx = Math.max(1, ...Object.keys({ ...core, ...aux }).map(y => (core[y] || 0) + (aux[y] || 0)));
  const vw = n * bw + 30, vh = H2 + 22;
  let s = `<svg class="yearbars" viewBox="0 0 ${vw} ${vh}" style="width:${Math.round(vw * 1.15)}px;max-width:100%">`;
  for (let y = Y_MIN; y <= Y_MAX; y++) {
    const x = (y - Y_MIN) * bw + 26, op = y >= S.y0 && y <= S.y1 ? 1 : 0.3, c = core[y] || 0, a = aux[y] || 0;
    const hc = H2 * c / mx, ha = H2 * a / mx;
    if (c + a) s += `<g opacity="${op}"><title>${y} 年：关键方法 ${c} 题，顺带用到 ${a} 题</title>
      <rect x="${x}" y="${H2 - hc}" width="${bw - 3}" height="${hc}" fill="var(--accent)"/>
      <rect x="${x}" y="${H2 - hc - ha}" width="${bw - 3}" height="${ha}" fill="var(--accent)" opacity=".35"/></g>`;
    if (y % 5 === 0) s += `<text x="${x + bw / 2 - 1}" y="${H2 + 16}" font-size="10" text-anchor="middle" fill="currentColor" opacity=".6">${y}</text>`;
  }
  return s + `<line x1="24" x2="${n * bw + 28}" y1="${H2 + 0.5}" y2="${H2 + 0.5}" stroke="currentColor" opacity=".25"/></svg>`;
}
function mItem(u) {
  const st = u.steps.length ? `步骤 ${u.steps.join('、')}` : '';
  return `<div class="qi mqi" data-q="${u.q.id}"><div class="h">${qHead(u.q)}<span class="badge ${u.core ? 'r-c' : 'r-a'}">${u.core ? '关键' : '顺带'}</span><span class="muted small">${st}</span></div>
    <div class="stem tex">${stemHtml(u.q)}</div>
    <div class="d"><span class="lbl">信号</span>${fmtStep(u.cue)}</div>
    <div class="d"><span class="lbl">用法</span>${fmtStep(u.why)}</div></div>`;
}
const M_FIRST = 30;
function renderMethodDetail() {
  const el = $('#mDetail');
  if (MV.cur == null && MV.order.length) MV.cur = MV.order[0];
  const m = MT[MV.cur];
  if (!m) { el.innerHTML = `<p class="muted" style="text-align:center;margin-top:60px">${MT.length ? '从左侧选择一个方法。' : '还没有方法数据（运行 scripts/methods.py 后重建 data.js）。'}</p>`; return; }
  const inF = new Set(F);
  const uses = m.uses.filter(u => inF.has(u.q) && typeOk(u.q));
  const coreY = {}, auxY = {};
  m.uses.forEach(u => { if (!typeOk(u.q)) return; const t = u.core ? coreY : auxY; t[u.q.y] = (t[u.q.y] || 0) + 1; });
  // knowledge points cited at the steps where the method is used
  const kp = new Map(), co = new Map();
  uses.forEach(u => {
    u.q.ci.forEach(c => { if (c.s.some(n => u.steps.includes(n))) c.kp.forEach(k => kp.set(k, (kp.get(k) || 0) + 1)); });
    (u.q.me || []).forEach(([o]) => { if (o !== m.i) co.set(o, (co.get(o) || 0) + 1); });
  });
  const kps = [...kp].sort((a, b) => b[1] - a[1]).slice(0, 18);
  const partners = [...co].sort((a, b) => b[1] - a[1]).slice(0, 10);
  const nc = uses.filter(u => u.core).length;
  const shown = uses.filter(u => MV.role === 'all' || (MV.role === 'core') === !!u.core)
    .sort((a, b) => b.core - a.core || b.q.y - a.q.y || a.q.id.localeCompare(b.q.id, 'en', { numeric: true }));
  const pos = MV.order.indexOf(m.i), rng = S.y0 === S.y1 ? `${S.y0} 年` : `${S.y0}–${S.y1}`;
  const list = MV.all ? shown : shown.slice(0, M_FIRST);
  el.innerHTML = `<div class="kpd mdet">
    <div class="kpd-top"><button class="icon" data-mlist title="收起或展开左侧列表（L）">${MV.nolist ? '☰ 列表' : '⇤ 收起列表'}</button>
      <span class="crumb muted small">方法 › ${esc(m.g)}</span>
      ${pos >= 0 ? `<span class="kp-nav"><button class="icon" data-mstep="-1" ${pos > 0 ? '' : 'disabled'} title="上一个（↑ / ←）">↑</button><span class="muted small">${pos + 1} / ${MV.order.length}</span><button class="icon" data-mstep="1" ${pos < MV.order.length - 1 ? '' : 'disabled'} title="下一个（↓ / →）">↓</button></span>` : ''}</div>
    <h1 class="kp-title">${esc(m.n)}</h1>
    <div class="kp-stmt msig"><span class="lbl">识别信号</span>${fmtStep(m.s)}</div>
    ${m.st && m.st.length ? `<div class="mcard">
      <div><h4>标准步骤</h4><ol>${m.st.map(t => `<li>${esc(t)}</li>`).join('')}</ol></div>
      ${m.pf && m.pf.length ? `<div class="pf"><h4>易错点</h4><ul>${m.pf.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>` : ''}
    </div>` : ''}
    <div class="kp-meta"><span class="stat">作关键方法 <b>${nc}</b> 题</span><span class="stat">顺带用到 <b>${uses.length - nc}</b> 题</span><span class="muted small">${rng}</span></div>
    <h3>历年出现 <span class="muted small">深色为关键方法，浅色为顺带用到；淡色为筛选范围外的年份</span></h3>${mYearChart(coreY, auxY)}
    ${kps.length ? `<h3>常用知识点 <span class="muted small">用到这个方法的步骤所引用的知识点，数字为题数</span></h3>
      ${kps.map(([k, n]) => `<span class="chip" data-kp="${k}">${esc(K[k].n)} <b>${n}</b></span>`).join('')}` : ''}
    ${partners.length ? `<h3>常一起用的方法</h3>${partners.map(([o, n]) => `<span class="chip" data-method="${MT[o].id}">${esc(MT[o].n)} <b>${n}</b></span>`).join('')}` : ''}
    <h3 class="mq-h">真题（${uses.length}）
      <span class="seg">${[['all', '全部'], ['core', '关键'], ['aux', '顺带']].map(([k, l]) => `<button class="small${MV.role === k ? ' on' : ''}" data-mrole="${k}">${l}</button>`).join('')}</span></h3>
    ${list.map(mItem).join('') || '<p class="muted small">当前筛选下没有</p>'}
    ${shown.length > list.length ? `<button class="more-btn" data-mall>显示其余 ${shown.length - list.length} 题</button>` : ''}
  </div>`;
  el.scrollTop = 0;
  math(el);
}
function renderMethods(arg, force) {
  if (arg) { const m = MT.find(x => x.id === arg); if (m && m.i !== MV.cur) { MV.cur = m.i; MV.all = false; } }
  renderMethodList(force);
  renderMethodDetail();
  const cur = $('#mList .ci.cur'); if (cur) cur.scrollIntoView({ block: 'nearest' });
}
function mList(show) {
  MV.nolist = !show;
  try { localStorage.setItem('math2viz.mNoList', MV.nolist ? '1' : '0'); } catch (e) { /* ignore */ }
  $('#v-methods').classList.toggle('nolist', MV.nolist);
  const b = $('#mDetail [data-mlist]'); if (b) b.textContent = MV.nolist ? '☰ 列表' : '⇤ 收起列表';
}
function mStep(d) {
  const i = MV.order.indexOf(MV.cur) + d;
  if (i >= 0 && i < MV.order.length) go('methods', MT[MV.order[i]].id);
}
$('#v-methods').classList.toggle('nolist', MV.nolist);
$('#mDetail').addEventListener('click', e => {
  if (e.target.closest('[data-mlist]')) return mList(MV.nolist);
  const st = e.target.closest('[data-mstep]'); if (st) return mStep(+st.dataset.mstep);
  const r = e.target.closest('[data-mrole]'); if (r) { MV.role = r.dataset.mrole; MV.all = false; return renderMethodDetail(); }
  if (e.target.closest('[data-mall]')) { MV.all = true; const sc = $('#mDetail').scrollTop; renderMethodDetail(); $('#mDetail').scrollTop = sc; }
});
// method tags anywhere (question steps, pop-up, chips) open the method page
document.addEventListener('click', e => {
  const a = e.target.closest('[data-method]');
  if (!a) return;
  e.preventDefault();
  closeModal();
  go('methods', a.dataset.method);
});
addEventListener('keydown', e => {
  if (VIEW !== 'methods' || e.ctrlKey || e.metaKey || e.altKey || !$('#modal').hidden) return;
  if (e.target.closest && e.target.closest('input, select, textarea, [contenteditable]')) return;
  const k = e.key.toLowerCase();
  const d = e.key === 'ArrowDown' || e.key === 'ArrowRight' || k === 'j' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' || k === 'k' ? -1 : 0;
  if (d) { e.preventDefault(); mStep(d); } else if (k === 'l') mList(MV.nolist);
});
if (VIEW === 'methods') route();  // the page was opened on #methods before this file loaded
