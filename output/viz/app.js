'use strict';
/* 数二考点地图: everything is computed in the browser from data.js (built by scripts/build_viz.py). */
const D = window.DATA;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const texHtml = s => esc(s).replace(/\n/g, '<br>');
const fmt = v => v >= 100 ? Math.round(v) : v >= 10 ? v.toFixed(1).replace(/\.0$/, '') : v.toFixed(1).replace(/\.0$/, '');

const RW = { c: 3, a: 1.5, p: 0.5 };
const TYPE = { x: '选择', t: '填空', j: '解答' };
const ROLE = { c: '核心', a: '辅助', p: '前置' };
const KIND = { definition: '定义', theorem: '定理', formula: '公式', property: '性质', corollary: '推论', lemma: '引理',
  method: '方法', concept: '概念', example: '例题', remark: '注' };
const FORMAL = new Set(['definition', 'theorem', 'formula', 'property', 'corollary', 'lemma', 'method', 'concept']);
const VERDICT = { absent: '书中未见', related: '书中有相近表述', present: '书中有（已补引用）', '': '未复核' };
const YEARS = [...new Set(D.questions.map(q => q.y))].sort((a, b) => a - b);
const Y_MIN = YEARS[0], Y_MAX = YEARS[YEARS.length - 1];
const BOOKS = ['GS1', 'GS2', 'LA', 'LALU'];
const BOOK_SHORT = { GS1: '高数上', GS2: '高数下', LA: '线代', LALU: '线代讲义' };
const isLA = bk => bk === 'LA' || bk === 'LALU';
const MODE_RGB = { topic: 'var(--topic)', tool: 'var(--tool)' };

/* ---------- static indexes ---------- */
const nodeById = {};
D.nodes.forEach((n, i) => { n.i = i; n.kids = []; n.cards = []; nodeById[n.id] = n; });
D.nodes.forEach(n => { if (n.p && nodeById[n.p]) nodeById[n.p].kids.push(n); });
D.cards.forEach((c, i) => { c.i = i; (nodeById[c.n] || { cards: [] }).cards.push(i); });
const qById = {};
D.questions.forEach(q => { qById[q.id] = q; });

const ancCache = {};
function ancestors(id) {
  if (!id) return [];
  if (ancCache[id]) return ancCache[id];
  const parts = id.split('/'), out = [];
  for (let k = 2; k <= parts.length; k++) { const a = parts.slice(0, k).join('/'); if (nodeById[a]) out.push(a); }
  return (ancCache[id] = out);
}
const chapterOf = id => (id || '').split('/').slice(0, 2).join('/');
function nodeName(n, short) {
  if (!n) return '';
  if (n.k === 'chapter') return short ? `第${n.num}章` : `第${n.num}章 ${n.ti}`;
  return short ? n.num : `${n.num} ${n.ti}`;
}
function nodePath(id) { return ancestors(id).map(a => nodeName(nodeById[a])).join(' › '); }
const cardName = c => (c.lb ? c.lb + ' ' : '') + c.ti;
const kpLink = k => `<a data-kp="${k}">${esc(K[k].n)}</a>`;

// which cards contain a block (statement first)
const blockCards = D.blocks.map(() => null);
D.cards.forEach(c => {
  c.st.forEach(b => { (blockCards[b] ||= []).push([c.i, 1]); });
  c.sp.forEach(b => { if (!c.st.includes(b)) (blockCards[b] ||= []).push([c.i, 0]); });
});
// page -> [block, rect]
const pageRects = {};
D.blocks.forEach((b, i) => b.r.forEach((r, k) => { ((pageRects[b.bk] ||= {})[r[0]] ||= []).push([i, k]); }));
const pageInfo = {};
BOOKS.forEach(bk => { pageInfo[bk] = {}; D.books[bk].pages.forEach((p, k) => { pageInfo[bk][p[0]] = { k, w: p[1], h: p[2], pp: p[3] }; }); });

// knowledge points: the unit of aggregation (a card may state several; restatements roll up to one)
const K = D.kps;
D.nodes.forEach(n => { n.kps = []; });
K.forEach((k, i) => {
  const c = D.cards[k.c];
  k.i = i; k.node = c ? c.n : null; k.bk = c ? c.bk : ''; k.ch = chapterOf(k.node); k.in = !!(c && c.in);
  if (nodeById[k.node]) nodeById[k.node].kps.push(i);
});
const cardHome = D.cards.map(c => (c.kp || []).find(i => K[i].c === c.i) ?? (c.kp || [])[0] ?? null);
const kpStBlocks = k => { const c = D.cards[k.c]; return c ? (c.st.length ? c.st : c.sp) : []; };
const KREL = { r: '复述', d: '推导' };
const KP_FORMAL = k => k.k !== 'example';
// derivation sources (build_deps.py): k.d = what it rests on [[kp, 0 concept | 1 proof, 1 book | 2 astra | 3 both]]; k.u = reverse
K.forEach(k => { k.d = k.d || []; k.u = []; });
K.forEach(k => k.d.forEach(([t, ty, src]) => K[t].u.push([k.i, ty, src])));

// "too common" tools: down-weight by how many questions (all years) use the knowledge point
const N_Q = D.questions.length;
const DF = new Uint16Array(K.length);
D.questions.forEach(q => new Set(q.ci.flatMap(c => c.kp)).forEach(k => DF[k]++));
const IDF = Array.from(DF, df => df <= 10 ? 1 : Math.max(0.15, Math.log(N_Q / df) / Math.log(N_Q / 10)));

// per question weight maps, fixed once. merge=1: a restatement's heat goes to the canonical statement
function maxSet(m, k, w) { if (!(m.get(k) >= w)) m.set(k, w); }
const topicBlocks = (t, merge) => merge && t.kp != null ? kpStBlocks(K[t.kp]) : D.cards[t.c].st;
const topicNode = (t, merge) => merge && t.kp != null ? K[t.kp].node : D.cards[t.c].n;
const citeBlocks = (ci, merge) => merge && ci.kp.length ? ci.kp.flatMap(k => kpStBlocks(K[k])) : ci.b;
const citeNodes = (ci, merge) => merge && ci.kp.length ? ci.kp.map(k => K[k].node)
  : [ci.c >= 0 ? D.cards[ci.c].n : (ci.b.length ? D.blocks[ci.b[0]].n : null)];
D.questions.forEach(q => {
  q.tk = new Map(); q.tbm = [new Map(), new Map()]; q.tnm = [new Map(), new Map()];
  q.to.forEach(t => {
    const w = t.p ? 1 : 0.5;
    if (t.kp != null) maxSet(q.tk, t.kp, w);
    for (const m of [0, 1]) {
      topicBlocks(t, m).forEach(b => maxSet(q.tbm[m], b, w));
      ancestors(topicNode(t, m)).forEach(a => maxSet(q.tnm[m], a, w));
    }
  });
  q.okm = [new Map(), new Map()]; q.obm = [[new Map(), new Map()], [new Map(), new Map()]]; q.onm = [[new Map(), new Map()], [new Map(), new Map()]];
  for (const idf of [0, 1]) {
    q.ci.forEach(ci => {
      const base = RW[ci.r];
      ci.kp.forEach(k => maxSet(q.okm[idf], k, base * (idf ? IDF[k] : 1)));
      const w = base * (idf && ci.kp.length ? Math.max(...ci.kp.map(k => IDF[k])) : 1);
      for (const m of [0, 1]) {
        citeBlocks(ci, m).forEach(b => maxSet(q.obm[idf][m], b, w));
        citeNodes(ci, m).forEach(n => ancestors(n).forEach(a => maxSet(q.onm[idf][m], a, w)));
      }
    });
  }
});

// inherited heat: a question that uses a knowledge point also exercises what it rests on — INH per level, two levels,
// never for a point the question already uses directly
const INH = 0.3;
function inherit(m) {
  const out = new Map();
  m.forEach((w, k) => K[k].d.forEach(([a]) => {
    if (!m.has(a)) maxSet(out, a, w * INH);
    K[a].d.forEach(([b]) => { if (!m.has(b) && b !== k) maxSet(out, b, w * INH * INH); });
  }));
  return out;
}
D.questions.forEach(q => { q.itk = inherit(q.tk); q.iok = [inherit(q.okm[0]), inherit(q.okm[1])]; });
function spread(ik, bm, nm, bh, nh) { // inherited weights -> canonical blocks / sections, only above the direct weight
  const b = new Map(), n = new Map();
  ik.forEach((w, k) => { kpStBlocks(K[k]).forEach(x => maxSet(b, x, w)); ancestors(K[k].node).forEach(x => maxSet(n, x, w)); });
  b.forEach((w, x) => { const d = bm.get(x) || 0; if (w > d) bh[x] += w - d; });
  n.forEach((w, x) => { const d = nm.get(x) || 0; if (w > d) nh[x] = (nh[x] || 0) + w - d; });
}

/* ---------- filter state ---------- */
const S = { y0: Y_MIN, y1: Y_MAX, types: new Set(['x', 't', 'j']), mode: 'topic', idf: true, merge: true, inh: false };
try {
  const saved = JSON.parse(localStorage.getItem('math2viz') || '{}');
  if (saved.y0) Object.assign(S, { y0: saved.y0, y1: saved.y1, mode: saved.mode || 'topic', idf: saved.idf !== false,
    merge: saved.merge !== false, inh: saved.inh === true, types: new Set(saved.types || ['x', 't', 'j']) });
} catch (e) { /* storage unavailable: defaults */ }
function saveState() {
  try { localStorage.setItem('math2viz', JSON.stringify({ y0: S.y0, y1: S.y1, mode: S.mode, idf: S.idf, merge: S.merge, inh: S.inh, types: [...S.types] })); } catch (e) { /* ignore */ }
}
const M = () => (S.merge ? 1 : 0), I = () => (S.idf ? 1 : 0);
const qTB = q => q.tbm[M()];
const qTN = q => q.tnm[M()];
const qOK = q => q.okm[I()];
const qOB = q => q.obm[I()][M()];
const qON = q => q.onm[I()][M()];
const typeOk = q => S.types.has(q.ty);
const inRange = q => q.y >= S.y0 && q.y <= S.y1;

/* ---------- aggregates for the current filter ---------- */
let F = [], H = null;
function compute() {
  F = D.questions.filter(q => inRange(q) && typeOk(q));
  const nb = D.blocks.length, nk = K.length;
  H = { bt: new Float32Array(nb), bo: new Float32Array(nb), btn: new Uint16Array(nb), bon: new Uint16Array(nb),
    kt: new Float32Array(nk), ko: new Float32Array(nk), ktn: new Uint16Array(nk), kon: new Uint16Array(nk),
    kti: new Float32Array(nk), koi: new Float32Array(nk),
    nt: {}, no: {}, ntn: {}, non: {} };
  const add = (o, on, k, w) => { o[k] = (o[k] || 0) + w; on[k] = (on[k] || 0) + 1; };
  for (const q of F) {
    qTB(q).forEach((w, b) => { H.bt[b] += w; H.btn[b]++; });
    q.tk.forEach((w, k) => { H.kt[k] += w; H.ktn[k]++; });
    qTN(q).forEach((w, n) => add(H.nt, H.ntn, n, w));
    qOB(q).forEach((w, b) => { H.bo[b] += w; H.bon[b]++; });
    qOK(q).forEach((w, k) => { H.ko[k] += w; H.kon[k]++; });
    qON(q).forEach((w, n) => add(H.no, H.non, n, w));
    const itk = q.itk, iok = q.iok[I()];
    itk.forEach((w, k) => { H.kti[k] += w; });
    iok.forEach((w, k) => { H.koi[k] += w; });
    if (S.inh) {
      itk.forEach((w, k) => { H.kt[k] += w; });
      iok.forEach((w, k) => { H.ko[k] += w; });
      spread(itk, qTB(q), qTN(q), H.bt, H.nt);
      spread(iok, qOB(q), qON(q), H.bo, H.no);
    }
  }
  H.bmax = {}; H.kmax = { topic: 0, tool: 0 };
  BOOKS.forEach(bk => { H.bmax[bk] = { topic: 1e-9, tool: 1e-9 }; });
  D.blocks.forEach((b, i) => { const m = H.bmax[b.bk]; if (H.bt[i] > m.topic) m.topic = H.bt[i]; if (H.bo[i] > m.tool) m.tool = H.bo[i]; });
  for (let k = 0; k < nk; k++) { H.kmax.topic = Math.max(H.kmax.topic, H.kt[k]); H.kmax.tool = Math.max(H.kmax.tool, H.ko[k]); }
}
const bHeat = (i, mode = S.mode) => mode === 'topic' ? H.bt[i] : H.bo[i];
const kHeat = (k, mode = S.mode) => mode === 'topic' ? H.kt[k] : H.ko[k];
const kHit = k => H.ktn[k] + H.kon[k] > 0;
const nHeat = (id, mode = S.mode) => (mode === 'topic' ? H.nt[id] : H.no[id]) || 0;
const nCount = (id, mode = S.mode) => (mode === 'topic' ? H.ntn[id] : H.non[id]) || 0;
function level(v, max) { return v > 0 ? Math.log1p(v) / Math.log1p(Math.max(max, v)) : 0; }
function heatColor(v, max, mode = S.mode, lo = 0.1, span = 0.55) {
  return v > 0 ? `rgba(${MODE_RGB[mode]}, ${(lo + span * level(v, max)).toFixed(3)})` : 'transparent';
}
function bar(v, max, mode = S.mode) {
  const w = v > 0 ? Math.max(3, 100 * level(v, max)) : 0;
  return `<div class="hb"><i style="width:${w}%;background:rgb(${MODE_RGB[mode]})"></i></div>`;
}

/* ---------- math ---------- */
function math(el) {
  if (!window.renderMathInElement) return;
  try {
    window.renderMathInElement(el, { throwOnError: false, strict: 'ignore', delimiters: [
      { left: '$$', right: '$$', display: true }, { left: '\\[', right: '\\]', display: true },
      { left: '$', right: '$', display: false }, { left: '\\(', right: '\\)', display: false }] });
  } catch (e) { /* leave source */ }
}

/* ---------- tooltip ---------- */
const tip = $('#tip');
function showTip(e, html) { tip.innerHTML = html; tip.hidden = false; moveTip(e); }
function moveTip(e) {
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(e.clientX + 14, innerWidth - w - 8) + 'px';
  tip.style.top = (e.clientY + 16 + h > innerHeight ? e.clientY - h - 10 : e.clientY + 16) + 'px';
}
const hideTip = () => { tip.hidden = true; };

/* ---------- shared renderers ---------- */
function qHead(q) {
  return `<b>${q.y}·${esc(q.lb)}</b><span class="badge muted">${TYPE[q.ty]}</span>`;
}
// solution steps, notes and reasons are plain text with bare math ("∫₀ˣe^{t²}dt=xe^{ξ²}，ξ在0与x之间"):
// plain2tex.js cuts out the math spans and turns them into LaTeX (spans KaTeX rejects stay text); rendered once, cached
const stepCache = new Map();
function fmtStep(t) {
  t = String(t ?? '');
  const hit = stepCache.get(t);
  if (hit != null) return hit;
  const text = v => esc(v).replace(/\n/g, '<br>');
  const html = window.plain2tex && window.katex
    ? plain2tex(t).map(p => p.t === 'math' ? katex.renderToString(p.v, { throwOnError: false, strict: 'ignore' }) : text(p.v)).join('')
    : text(t);
  if (stepCache.size > 5000) stepCache.clear();
  stepCache.set(t, html);
  return html;
}
// hand-typeset steps (output/mapping/steps_tex.json, q.steps[i][2]) already carry $…$ LaTeX: render those spans directly.
// For reading (not in one-line briefs): tall or long formulas (matrices, determinants, long equation chains) get a line of
// their own in display style, taking the punctuation that follows them; a lead-in label ("充分性第一步：", "排除A：") is bold.
const texLen = s => s.replace(/\\(left|right|mathrm|operatorname|limits|displaystyle|[,;!])/g, '')
  .replace(/\\[a-zA-Z]+/g, 'x').replace(/[{}\s^_]/g, '').length;
const texBlock = s => /\\begin\{[pv]matrix\}/.test(s) || texLen(s) >= 48 || (/\\dfrac|\\limits/.test(s) && texLen(s) >= 28);
function fmtTex(t, inline) {
  const key = (inline ? '\u0001' : '\u0000') + t;
  const hit = stepCache.get(key);
  if (hit != null) return hit;
  if (!window.katex) return esc(t);
  const kx = (v, disp) => katex.renderToString(disp ? '\\displaystyle ' + v : v, { throwOnError: false, strict: 'ignore' });
  const parts = t.split(/(\$[^$]+\$)/);
  let out = '';
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (!(p.length > 2 && p[0] === '$' && p.at(-1) === '$')) {
      let h = esc(p);
      if (i === 0 && !inline) {
        const m = /^(（[ⅠⅡⅢⅣ]+）|[^，。；：:（(]{1,14}[：:])/.exec(p);
        if (m) h = `<b class="slab">${esc(m[1])}</b>` + esc(p.slice(m[1].length));
      }
      out += h;
      continue;
    }
    const v = p.slice(1, -1);
    if (inline || !texBlock(v)) { out += kx(v); continue; }
    // display line: the punctuation right after the formula stays with it
    const next = parts[i + 1] || '', pm = /^\s*([，。；：、,.;]?)/.exec(next);
    parts[i + 1] = next.slice(pm[0].length);
    out = out.replace(/\s+$/, '') + `<span class="eqb">${kx(v, true)}${pm[1] ? `<span class="eqp">${pm[1]}</span>` : ''}</span>`;
  }
  stepCache.set(key, out);
  return out;
}
const stepHtml = ([, d, tex], n = Infinity) => tex ? fmtTex(clip(tex, n), n !== Infinity) : fmtStep(clip(d, n));
// the cited steps of a question, rendered, within a budget of about n characters
function stepsBrief(q, steps, n) {
  const m = new Map(q.steps.map(s => [s[0], s]));
  const out = [];
  for (const k of steps) {
    const s = m.get(k);
    if (!s || n <= 0) continue;
    out.push(stepHtml(s, n));
    n -= (s[2] || s[1]).length;
  }
  return out.join(' / ');
}
function clip(s, n) {
  // never cut inside inline math: drop an unclosed $…$ or \(…\) at the end of the cut
  s = String(s || '');
  if (s.length <= n) return s;
  let c = s.slice(0, n);
  if (((c.match(/\$\$/g) || []).length) % 2) c = c.slice(0, c.lastIndexOf('$$'));
  const dollars = (c.match(/(?<!\\)\$/g) || []).length;
  if (dollars % 2) c = c.slice(0, c.search(/(?<!\\)\$(?=[^$]*$)/));
  if (c.lastIndexOf('\\(') > c.lastIndexOf('\\)')) c = c.slice(0, c.lastIndexOf('\\('));
  return c.trimEnd() + ' …';
}
// a statement for reading: top-level "；" clauses become a list, very long inline formulas get a line of their own
function splitTop(s, sep) {
  const out = [];
  let cur = '', inMath = false;
  for (const ch of s) {
    if (ch === '$') inMath = !inMath;
    if (ch === sep && !inMath) { out.push(cur); cur = ''; } else cur += ch;
  }
  out.push(cur);
  return out.map(x => x.trim()).filter(Boolean);
}
function stmtHtml(s) {
  const long = t => t.replace(/\$([^$]{70,})\$[：:，,；]?\s*/g, (m, f) => '$$' + f + '$$');  // own line; drop the dangling "：
  const parts = splitTop(s, '；');
  if (parts.length >= 2 && s.replace(/\$[^$]*\$/g, 'x').length > 36)
    return `<ul>${parts.map(p => `<li>${texHtml(long(p.replace(/[。；]$/, '')))}</li>`).join('')}</ul>`;
  return texHtml(long(s));
}
function snippet(bi, maxW = 640, maxS = 0.62) {
  const b = D.blocks[bi];
  return b.r.map(([p, x0, y0, x1, y1]) => {
    const pi = pageInfo[b.bk][p];
    if (!pi) return '';
    const pad = 6; x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad); x1 = Math.min(pi.w, x1 + pad); y1 = Math.min(pi.h, y1 + pad);
    const s = Math.min(maxS, maxW / (x1 - x0));
    return `<div class="snip" title="${esc(b.bk)} p.${esc(pi.pp ?? p)}" style="width:${((x1 - x0) * s).toFixed(0)}px;height:${((y1 - y0) * s).toFixed(0)}px;` +
      `background-image:url(pages/${b.bk}/${String(p).padStart(4, '0')}.webp);background-size:${(pi.w * s).toFixed(1)}px ${(pi.h * s).toFixed(1)}px;` +
      `background-position:${(-x0 * s).toFixed(1)}px ${(-y0 * s).toFixed(1)}px"></div>`;
  }).join('');
}
// one-line glance of the year chart: tiny bars, topic up / tool down, out-of-range years faded
function sparkChart(topicByYear, toolByYear) {
  const n = Y_MAX - Y_MIN + 1, bw = 5, h = 12;
  const mt = Math.max(1, ...Object.values(topicByYear)), mo = Math.max(1, ...Object.values(toolByYear));
  let s = `<svg class="spark" viewBox="0 0 ${n * bw} ${2 * h + 1}" width="${n * bw}" height="${2 * h + 1}"><line x1="0" x2="${n * bw}" y1="${h + .5}" y2="${h + .5}" stroke="currentColor" opacity=".18"/>`;
  for (let y = Y_MIN; y <= Y_MAX; y++) {
    const x = (y - Y_MIN) * bw, op = y >= S.y0 && y <= S.y1 ? 1 : 0.28, t = topicByYear[y] || 0, o = toolByYear[y] || 0;
    if (t) s += `<rect x="${x}" y="${h - Math.max(2, h * t / mt)}" width="${bw - 1}" height="${Math.max(2, h * t / mt)}" fill="rgb(${MODE_RGB.topic})" opacity="${op}"/>`;
    if (o) s += `<rect x="${x}" y="${h + 1}" width="${bw - 1}" height="${Math.max(2, h * o / mo)}" fill="rgb(${MODE_RGB.tool})" opacity="${op}"/>`;
  }
  return s + '</svg>';
}
function yearChart(topicByYear, toolByYear) {
  const n = Y_MAX - Y_MIN + 1, bw = 14, H2 = 34;
  const mt = Math.max(1, ...Object.values(topicByYear)), mo = Math.max(1, ...Object.values(toolByYear));
  const vw = n * bw + 30, vh = H2 * 2 + 22;
  let s = `<svg class="yearbars" viewBox="0 0 ${vw} ${vh}" style="width:${Math.round(vw * 1.15)}px;max-width:100%">`;
  for (let y = Y_MIN; y <= Y_MAX; y++) {
    const x = (y - Y_MIN) * bw + 26, inr = y >= S.y0 && y <= S.y1 ? 1 : 0.3;
    const t = topicByYear[y] || 0, o = toolByYear[y] || 0;
    if (t) s += `<rect x="${x}" y="${H2 - H2 * t / mt}" width="${bw - 3}" height="${H2 * t / mt}" fill="rgb(${MODE_RGB.topic})" opacity="${inr}"><title>${y} 考点 ${t} 题</title></rect>`;
    if (o) s += `<rect x="${x}" y="${H2 + 1}" width="${bw - 3}" height="${H2 * o / mo}" fill="rgb(${MODE_RGB.tool})" opacity="${inr}"><title>${y} 工具 ${o} 题</title></rect>`;
    if (y % 5 === 0) s += `<text x="${x + bw / 2 - 1}" y="${H2 * 2 + 18}" font-size="10" text-anchor="middle" fill="currentColor" opacity=".6">${y}</text>`;
  }
  s += `<line x1="24" x2="${n * bw + 28}" y1="${H2 + 0.5}" y2="${H2 + 0.5}" stroke="currentColor" opacity=".25"/>`;
  s += `<text x="0" y="14" font-size="10" fill="rgb(${MODE_RGB.topic})">考点</text><text x="0" y="${H2 + 14}" font-size="10" fill="rgb(${MODE_RGB.tool})">工具</text></svg>`;
  return s;
}

/* ---------- question modal ---------- */
let QNAV = { ids: [], fb: null };
// how citations show under the steps: 'hide' (steps only), 'chip' (collapsed chips), 'open' (unfolded)
let CITE_MODE = 'chip';
try { CITE_MODE = localStorage.getItem('math2viz.citeMode') || (localStorage.getItem('math2viz.citeOpen') === '1' ? 'open' : 'chip'); } catch (e) { /* default */ }
const CITE_MODES = [['hide', '隐藏'], ['chip', '标签'], ['open', '展开']];
// the leading "1." / "(3)" of a stem repeats the title; choice options are typeset as a list (two columns when short)
const STEM_NO = /^\s*(?:\(\d+\)|\d+\s*[.．、])\s*/;
function stemBlock(q) {
  const body = q.stem.replace(STEM_NO, '');
  const m = /\n\s*\(A[)）]/.exec(body);
  const parts = m ? body.slice(m.index).split(/(?<=^|\s)(?=\([A-D][)）])/).map(x => x.trim()).filter(Boolean) : [];
  if (parts.length !== 4 || parts.map(x => x[1]).join('') !== 'ABCD') return `<div class="tex q-stem">${texHtml(body)}</div>`;
  const opts = parts.map(x => ({ l: x[1], t: x.replace(/^\([A-D][)）]\s*/, '') }));
  const short = opts.every(o => o.t.replace(/\\[a-zA-Z]+|[{}$\s]/g, '').length <= 22);
  return `<div class="tex q-stem">${texHtml(body.slice(0, m.index).trim())}</div>
    <div class="q-opts${short ? ' two' : ''}">${opts.map(o => `<div class="opt"><span class="ol">${o.l}</span><span class="tex">${texHtml(o.t)}</span></div>`).join('')}</div>`;
}
// the parts of a question shown both in the pop-up (from other pages) and on the questions page
function qSections(q, focusBlock) {
  const cites = q.ci.map((c, i) => ({ ...c, i }));
  const used = new Set();
  // a citation is a chip under the step it supports; its wording, quote and book link unfold on click.
  // a citation used by several steps is shown under each of them (repeats are marked "见步骤 n")
  const firstStep = {};
  const citeHtml = (c, n) => {
    const card = c.c >= 0 ? D.cards[c.c] : null;
    const hit = focusBlock != null && (c.b.includes(focusBlock) || citeBlocks(c, 1).includes(focusBlock));
    const again = firstStep[c.i] != null && firstStep[c.i] !== n;
    if (firstStep[c.i] == null) firstStep[c.i] = n;
    used.add(c.i);
    const name = c.kp.length ? c.kp.map(k => esc(K[k].n)).join('、') : esc(c.k);
    return `<details class="cite ${c.r}${hit ? ' hit' : ''}" ${hit || (CITE_MODE === 'open' && !again) ? 'open' : ''}><summary><span class="badge r-${c.r}">${ROLE[c.r]}</span> ${name}${card && card.lb ? ` <span class="lb">${esc(card.lb)}</span>` : ''}${again ? ` <span class="muted small">见步骤 ${firstStep[c.i]}</span>` : ''}${c.m ? ' <span class="badge muted">人工补入</span>' : ''}</summary>
      <div class="cdet">${c.kp.length ? `<div>知识点：${c.kp.map(kpLink).join('、')}</div>` : ''}
      <div class="muted small">解答原话：${esc(c.k)}${card ? ` · 引自 ${esc(cardName(card))}` : ''}${c.b.length ? ` · <a data-read="${c.b.join(',')}">在书中查看</a>` : ''}</div>
      <div class="qt tex">“${texHtml(clip(c.q, 240))}”</div></div></details>`;
  };
  let steps = q.steps.map(st => {
    const n = st[0], cs = cites.filter(c => c.s.includes(n));
    return `<div class="step"><div class="n"><span>${n}</span></div><div class="body"><div class="stxt">${stepHtml(st)}</div>
      ${cs.length ? `<div class="cites">${cs.map(c => citeHtml(c, n)).join('')}</div>` : ''}</div></div>`;
  }).join('');
  const rest = cites.filter(c => !used.has(c.i));
  if (rest.length) steps += `<div class="step orphan"><div class="n"><span>·</span></div><div class="body"><div class="stxt muted small">未对应到具体步骤的依据</div><div class="cites">${rest.map(c => citeHtml(c, 0)).join('')}</div></div></div>`;
  return {
    badges: `<span class="badge muted">${TYPE[q.ty]}</span> <span class="badge muted">${q.sub === 'LA' ? '线代' : '高数'}</span>${q.cx ? ' <span class="badge muted" title="早期 codex 版映射，前置引用偏多">早期版</span>' : ''}`,
    stem: stemBlock(q),
    selftest: `<label class="small" title="先隐藏答案、解析和考查主题，自己做完再看"><input type="checkbox" data-selftest ${SELFTEST ? 'checked' : ''}> 自测模式</label>`,
    reveal: SELFTEST ? '<button class="reveal-btn" data-reveal>显示答案、解析与考查主题</button>' : '',
    ans: `<div class="q-ans"><span class="lbl">答案</span><div class="tex">${texHtml(q.ans)}</div></div>
      <details class="q-sol"><summary class="muted">参考解析</summary><div class="tex">${texHtml(q.sol)}</div></details>`,
    topics: q.to.map(t => `<div class="q-topic"><span class="badge ${t.p ? 'r-P' : 'r-S'}">${t.p ? '主' : '次'}</span>
      ${t.kp != null ? kpLink(t.kp) : `<a data-card="${t.c}">${esc(cardName(D.cards[t.c]))}</a>`} <span class="muted small">${esc(nodePath(D.cards[t.c].n))}</span>
      <div class="muted small">${fmtStep(t.r)}</div></div>`).join('') + (q.tn ? `<div class="box-note">${fmtStep(q.tn)}</div>` : ''),
    stepsHead: `<span class="muted small">${q.steps.length} 步 · ${q.ci.length} 条依据</span>
      <span class="seg" title="依据的显示方式">依据${CITE_MODES.map(([k, l]) => `<button class="small${k === CITE_MODE ? ' on' : ''}" data-citemode="${k}">${l}</button>`).join('')}</span>`,
    steps: `<div class="steps${CITE_MODE === 'hide' && focusBlock == null ? ' no-cites' : ''}">${steps}</div>`,
    notes: (q.nit.length ? `<h3>书中未找到</h3>${q.nit.map(x => `<div class="box-note"><b>${fmtStep(x.k)}</b> <span class="badge muted">${VERDICT[x.v] || x.v}</span>
      ${x.rb.length ? ` · <a data-read="${x.rb.join(',')}">最接近的原文</a>` : ''}<div class="muted small">${fmtStep(x.no || x.se)}</div></div>`).join('')}` : '')
      + (q.no ? `<h3>备注</h3><div class="muted q-note">${fmtStep(q.no)}</div>` : ''),
    nNotes: q.nit.length + (q.no ? 1 : 0),
  };
}
function markSeen(id) {
  SEEN.add(id); store.put('seen', SEEN);
  $$(`.qrow[data-qsel="${id}"]`).forEach(r => {
    r.classList.add('seen');
    const h = r.querySelector('.h');
    if (h && !h.querySelector('.seen-dot')) h.insertAdjacentHTML('beforeend', '<span class="seen-dot" title="看过">✓</span>');
  });
  qCount();
}
// pop-up version, opened from the other pages (textbook, knowledge points, blind spots …)
function openQuestion(id, focusBlock, ids) {
  const q = qById[id];
  if (ids) QNAV = { ids, fb: focusBlock };
  if (!QNAV.ids.includes(id)) QNAV = { ids: [id], fb: focusBlock };
  markSeen(id);
  const pos = QNAV.ids.indexOf(id), n = QNAV.ids.length;
  const x = qSections(q, focusBlock);
  const html = `<div class="qnav"><button data-qnav="-1" ${pos > 0 ? '' : 'disabled'} title="上一题（←）">← 上一题</button>
      <span class="muted small">${n > 1 ? `${pos + 1} / ${n}` : ''}</span><button data-qnav="1" ${pos < n - 1 ? '' : 'disabled'} title="下一题（→）">下一题 →</button>
      <span style="flex:1"></span><button class="small" data-qopen="${id}" title="在真题页中打开">在真题页打开</button>${starBtn(id, ' 标记')}${x.selftest}
      <button class="close" title="关闭（Esc）">×</button></div>
    <h2>${q.y} 年 第 ${esc(q.lb)} 题 ${x.badges}</h2>
    ${x.stem}${x.reveal}
    <div class="q-reveal" ${SELFTEST ? 'hidden' : ''}>${x.ans}
    <h3>考查主题</h3>${x.topics}
    <h3 class="steps-h">解题步骤与教材依据 ${x.stepsHead}</h3>${x.steps}${x.notes}</div>`;
  const box = $('#modal .content');
  box.innerHTML = html;
  $('#modal').dataset.cur = id;
  $('#modal').hidden = false;
  $('#modal').scrollTop = 0;
  math(box);
}
function closeModal() { $('#modal').hidden = true; }
$('#modal').addEventListener('click', e => {
  if (e.target.id === 'modal' || e.target.classList.contains('close')) return closeModal();
  const nav = e.target.closest('[data-qnav]');
  if (nav) stepQuestion(+nav.dataset.qnav);
  const op = e.target.closest('[data-qopen]');
  if (op) { closeModal(); go('questions', op.dataset.qopen); }
});
// controls shared by the pop-up and the questions page: self-test reveal, citation display mode
document.addEventListener('click', e => {
  const root = e.target.closest && e.target.closest('.qbox');
  if (!root) return;
  if (e.target.closest('[data-reveal]')) { root.querySelector('.q-reveal').hidden = false; e.target.closest('[data-reveal]').remove(); }
  const cm = e.target.closest('[data-citemode]');
  if (cm) {
    CITE_MODE = cm.dataset.citemode;
    try { localStorage.setItem('math2viz.citeMode', CITE_MODE); } catch (err) { /* ignore */ }
    root.querySelectorAll('[data-citemode]').forEach(b => b.classList.toggle('on', b === cm));
    root.querySelector('.steps').classList.toggle('no-cites', CITE_MODE === 'hide');
    if (CITE_MODE !== 'hide') root.querySelectorAll('details.cite').forEach(d => { d.open = CITE_MODE === 'open' && !d.querySelector('summary .muted.small'); });
  }
});
document.addEventListener('change', e => {
  if (!e.target.matches || !e.target.matches('[data-selftest]')) return;
  SELFTEST = e.target.checked;
  try { localStorage.setItem('math2viz.selftest', SELFTEST ? '1' : '0'); } catch (err) { /* ignore */ }
  $$('[data-selftest]').forEach(c => { c.checked = SELFTEST; });
  if (!SELFTEST) $$('.qbox').forEach(r => { const v = r.querySelector('.q-reveal'); if (v) v.hidden = false; r.querySelectorAll('[data-reveal]').forEach(b => b.remove()); });
});
function stepQuestion(d) {
  const i = QNAV.ids.indexOf($('#modal').dataset.cur) + d;
  if (i >= 0 && i < QNAV.ids.length) openQuestion(QNAV.ids[i], QNAV.fb);
}
addEventListener('keydown', e => {
  if ($('#modal').hidden) return;
  if (e.key === 'Escape') closeModal();
  else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !e.target.closest?.('input, select, textarea')) { e.preventDefault(); stepQuestion(e.key === 'ArrowLeft' ? -1 : 1); }
});
// ★ toggles never open the row they sit in
document.addEventListener('click', e => { const b = e.target.closest('[data-star]'); if (b) { e.stopPropagation(); toggleMark(b.dataset.star); } }, true);
// copy a statement (LaTeX source)
document.addEventListener('click', e => {
  const b = e.target.closest('[data-copy]');
  if (!b) return;
  e.stopPropagation();
  const k = K[+b.dataset.copy], text = `${k.n}：${k.s}`;
  const done = () => { b.textContent = '已复制'; setTimeout(() => { b.textContent = '复制'; }, 1200); };
  try { navigator.clipboard.writeText(text).then(done, () => { b.textContent = '复制失败'; }); } catch (err) { b.textContent = '复制失败'; }
}, true);
// hover any knowledge-point reference: its statement, rendered
let tipKp = null;
document.addEventListener('mouseover', e => {
  const a = e.target.closest && e.target.closest('[data-kp],[data-kpsel]');
  const id = a ? +(a.dataset.kp ?? a.dataset.kpsel) : null;
  if (!a || a.dataset.kp === '' || !K[id] || (a.dataset.kpsel != null && id === CV.cur)) { if (tipKp != null) { tipKp = null; hideTip(); } return; }
  if (id === tipKp) return;
  tipKp = id;
  const k = K[id];
  showTip(e, `<div class="tip-kp"><b>${esc(k.n)}</b> <span class="tip-meta">${KIND[k.k] || k.k} · ${BOOK_SHORT[k.bk] || ''} ${esc(nodeName(nodeById[k.node], true))}</span>` +
    `<div class="tex">${stmtHtml(k.s)}</div>${a.dataset.kpnote ? `<div class="tip-meta">${esc(a.dataset.kpnote)}</div>` : ''}</div>`);
  math(tip);
});
document.addEventListener('mousemove', e => { if (tipKp != null) moveTip(e); });
// global link delegation
document.addEventListener('click', e => {
  const a = e.target.closest('[data-kp],[data-card],[data-read],[data-q],[data-node]');
  if (!a) return;
  if (a.dataset.q) {
    const scope = a.closest('#modal') ? null : a.closest('#cardDetail, #side, #graphSide, #v-blind, .view');
    const ids = scope ? [...new Set([...scope.querySelectorAll('[data-q]')].map(x => x.dataset.q))] : null;
    openQuestion(a.dataset.q, a.dataset.fb != null ? +a.dataset.fb : null, ids);
    return;
  }
  closeModal();
  if (a.dataset.kp != null && a.dataset.kp !== '') go('cards', K[+a.dataset.kp].id);
  else if (a.dataset.card != null && a.dataset.card !== '') {
    const c = +a.dataset.card;
    if (cardHome[c] != null) go('cards', K[cardHome[c]].id); else goRead(D.cards[c].st.length ? D.cards[c].st : D.cards[c].sp);
  }
  else if (a.dataset.read) goRead(a.dataset.read.split(',').map(Number));
  else if (a.dataset.node) goNode(a.dataset.node);
});

/* ---------- reader ---------- */
const R = { bk: null, rects: {}, sel: new Set(), built: {}, curNode: null };
function buildReader(bk) {
  if (R.bk === bk) return;
  R.bk = bk; R.rects = {};
  $$('#bookTabs button').forEach(b => b.classList.toggle('on', b.dataset.bk === bk));
  const pages = D.books[bk].pages;
  const html = pages.map(([p, w, h, pp]) => {
    const rs = (pageRects[bk][p] || []).map(([i, k]) => {
      const [, x0, y0, x1, y1] = D.blocks[i].r[k];
      return `<rect data-b="${i}" x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" rx="5"/>`;
    }).join('');
    return `<div class="page" data-p="${p}" style="aspect-ratio:${w}/${h}"><img loading="lazy" decoding="async" alt="" src="pages/${bk}/${String(p).padStart(4, '0')}.webp">` +
      `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${rs}</svg><span class="pno">${pp ?? ''}</span></div>`;
  }).join('');
  $('#pages').innerHTML = html;
  $$('#pages rect').forEach(el => { (R.rects[el.dataset.b] ||= []).push(el); });
  R.pageEls = $$('#pages .page');
  R.nodes = D.nodes.filter(n => n.bk === bk);
  R.curNode = null;
  tocCtl();
  renderToc();
  paintReader();
  sidePanel();
}
function paintReader() {
  if (!R.bk) return;
  const max = H.bmax[R.bk][S.mode];
  for (const i in R.rects) {
    const f = heatColor(bHeat(+i), max);
    R.rects[i].forEach(el => { el.setAttribute('fill', f); el.classList.toggle('sel', R.sel.has(+i)); });
  }
  // minimap: heat per page
  const pages = D.books[R.bk].pages, n = pages.length;
  const ph = pages.map(([p]) => (pageRects[R.bk][p] || []).reduce((s, [i]) => s + bHeat(i), 0));
  const pmax = Math.max(1e-9, ...ph);
  $('#minimap').innerHTML = ph.map((v, k) => v > 0 ? `<i style="top:${(100 * k / n).toFixed(3)}%;height:${Math.max(100 / n, 0.25).toFixed(3)}%;background:${heatColor(v, pmax, S.mode, 0.15, 0.85)}"></i>` : '').join('') + '<div class="vp"></div>';
  updateViewport();
  renderToc();
  updateJumpbar();
}
// TOC: chapters fold; exercises / chapter reviews are hidden unless asked for
const TOC = { open: new Set(), showEx: false };
try { TOC.showEx = localStorage.getItem('math2viz.showEx') === '1'; } catch (e) { /* default */ }
const EXTRA = new Set(['exercises', 'chapter_review']);
function tocName(n) {
  if (n.k === 'exercises') return n.ti;                      // 习题1.1
  if (n.k === 'chapter_review') return n.ti.replace(/^第\d+章/, ''); // 复习题 / 自测题 / 思考题解答
  return nodeName(n);
}
const tocVisible = n => n.k === 'chapter' || (TOC.open.has(chapterOf(n.id)) && (TOC.showEx || !EXTRA.has(n.k)));
function renderToc() {
  if (!R.bk) return;
  const maxBy = {};
  R.nodes.forEach(n => { maxBy[n.k] = Math.max(maxBy[n.k] || 0, nHeat(n.id)); });
  $('#tocTree').innerHTML = R.nodes.filter(tocVisible).map(n => `<div class="tn k-${n.k}${n.in ? '' : ' out'}${R.curNode === n.id ? ' cur' : ''}" data-nid="${esc(n.id)}"
      title="${esc(nodeName(n))}${n.in ? '' : '（数二范围外）'}\n考点 ${nCount(n.id, 'topic')} 题 · 工具 ${nCount(n.id, 'tool')} 题">
      <span class="t">${n.k === 'chapter' ? `<span class="tw" data-fold="${esc(n.id)}">${TOC.open.has(n.id) ? '▾' : '▸'}</span>` : ''}${esc(tocName(n))}</span>${bar(nHeat(n.id), maxBy[n.k])}</div>`).join('');
}
function tocCtl() {
  $('#tocCtl').innerHTML = `<label class="small"><input type="checkbox" id="tocEx" ${TOC.showEx ? 'checked' : ''}> 显示习题与复习</label>
    <span><a class="small" data-tocall="1">全部展开</a> · <a class="small" data-tocall="0">收起</a></span>`;
}
$('#tocCtl').addEventListener('change', e => {
  if (e.target.id !== 'tocEx') return;
  TOC.showEx = e.target.checked;
  try { localStorage.setItem('math2viz.showEx', TOC.showEx ? '1' : '0'); } catch (err) { /* ignore */ }
  renderToc();
});
$('#tocCtl').addEventListener('click', e => {
  const a = e.target.closest('[data-tocall]');
  if (!a) return;
  TOC.open = a.dataset.tocall === '1' ? new Set(R.nodes.filter(n => n.k === 'chapter').map(n => n.id)) : new Set();
  renderToc();
});
$('#tocTree').addEventListener('click', e => {
  const f = e.target.closest('[data-fold]');
  if (f) { const id = f.dataset.fold; TOC.open.has(id) ? TOC.open.delete(id) : TOC.open.add(id); renderToc(); return; }
  const el = e.target.closest('.tn');
  if (el) { TOC.open.add(chapterOf(el.dataset.nid)); goNode(el.dataset.nid); }
});
function scrollToPage(p, frac = 0, smooth = false, margin = 60) {
  const pages = D.books[R.bk].pages;
  let k = pages.findIndex(x => x[0] >= p);
  if (k < 0) k = pages.length - 1;
  const el = R.pageEls[k], wrap = $('#pagesWrap');
  wrap.scrollTo({ top: el.offsetTop + frac * el.offsetHeight - margin, behavior: smooth ? 'smooth' : 'auto' });
}
function goNode(id) {
  const n = nodeById[id];
  if (!n) return;
  if (location.hash.split('/')[0] !== '#read') { pending = () => goNode(id); location.hash = '#read/' + n.bk; return; }
  buildReader(n.bk);
  TOC.open.add(chapterOf(id));
  const ab = n.ab != null ? D.blocks[n.ab] : null, r = ab && ab.r[0];
  if (r) scrollToPage(r[0], r[2] / pageInfo[n.bk][r[0]].h, false, 90);
  else scrollToPage(n.pdf || (D.books[n.bk].pages[0] || [0])[0]);
  R.sel = new Set(); R.selNode = id; paintReader(); sidePanel();
}
let pending = null;
function goRead(blocks, keepHash) {
  const b0 = D.blocks[blocks[0]];
  if (!b0) return;
  if (!keepHash && location.hash.split('/')[0] !== '#read') { pending = () => goRead(blocks, true); location.hash = '#read/' + b0.bk; return; }
  buildReader(b0.bk);
  TOC.open.add(chapterOf(b0.n));
  R.sel = new Set(blocks); R.selNode = null;
  paintReader();
  const r = b0.r[0];
  if (r) {
    const pi = pageInfo[b0.bk][r[0]];
    scrollToPage(r[0], r[2] / pi.h, false, 140);
    (R.rects[blocks[0]] || []).forEach(el => { el.classList.remove('pulse'); void el.getBoundingClientRect(); el.classList.add('pulse'); });
  }
  sidePanel(blocks[0]);
}
$('#pages').addEventListener('click', e => {
  const r = e.target.closest('rect');
  if (!r) return;
  const i = +r.dataset.b;
  R.sel = new Set([i]); R.selNode = null;
  R.rects[i]?.forEach(el => el.classList.add('sel'));
  paintReader(); sidePanel(i);
});
$('#pages').addEventListener('mousemove', e => {
  const r = e.target.closest('rect');
  if (!r) return hideTip();
  const i = +r.dataset.b, b = D.blocks[i];
  const ks = blockKps(i).map(([k]) => K[k].n);
  showTip(e, `${esc(b.nl || '')} ${ks.length ? esc(clip(ks.join('；'), 80)) : ''}<br>考点 ${fmt(H.bt[i])}（${H.btn[i]} 题）· 工具 ${fmt(H.bo[i])}（${H.bon[i]} 题）`);
});
$('#pages').addEventListener('mouseleave', hideTip);
// jump between cited passages: consecutive blocks with the same heat and question counts (one theorem, one
// cited span) form one stop; order = book order; "hot" scopes keep the stops above a heat quantile
const JUMP = { scope: 'all' };
try { JUMP.scope = localStorage.getItem('math2viz.jump') || 'all'; } catch (e) { /* default */ }
function jumpStops() {
  const out = [];
  let prev = null;
  D.blocks.forEach((b, i) => {
    if (b.bk !== R.bk || !b.r.length) return;
    const h = bHeat(i);
    if (!(h > 0)) { prev = null; return; }
    const sig = `${H.bt[i]}|${H.bo[i]}|${H.btn[i]}|${H.bon[i]}`;
    if (prev && prev.sig === sig) prev.blocks.push(i);
    else { prev = { sig, h, blocks: [i] }; out.push(prev); }
  });
  if (JUMP.scope !== 'all' && out.length) {
    const hs = out.map(s => s.h).sort((a, b) => b - a), cut = hs[Math.max(0, Math.ceil(hs.length * +JUMP.scope) - 1)];
    return out.filter(s => s.h >= cut);
  }
  return out;
}
function stopY(s) { // scroll offset of a stop's first block inside #pagesWrap
  const r = D.blocks[s.blocks[0]].r[0], k = D.books[R.bk].pages.findIndex(x => x[0] === r[0]), el = R.pageEls[k];
  return el ? el.offsetTop + el.offsetHeight * r[2] / pageInfo[R.bk][r[0]].h : 0;
}
function jumpIndex(stops) { // the stop the current selection is in, else -1
  const b = [...R.sel][0];
  return b == null ? -1 : stops.findIndex(s => s.blocks.includes(b));
}
function jump(dir) {
  if (VIEW !== 'read' || !R.bk) return;
  const stops = jumpStops();
  if (!stops.length) { updateJumpbar(stops); return; }
  let k = jumpIndex(stops);
  if (k >= 0) k += dir;
  else { // from the reading position: goRead puts a stop 140 px below the top
    const y = $('#pagesWrap').scrollTop + 140;
    k = dir > 0 ? stops.findIndex(s => stopY(s) > y + 2) : stops.findLastIndex(s => stopY(s) < y - 2);
  }
  if (k < 0 || k >= stops.length) return;
  goRead(stops[k].blocks, true);
  updateJumpbar(stops);
}
function updateJumpbar(stops = jumpStops()) {
  const k = jumpIndex(stops);
  $('#jpos').textContent = stops.length ? `${k >= 0 ? `第 ${k + 1}` : '—'} / ${stops.length} 处` : '没有引用';
  $('#jscope').value = JUMP.scope;
}
$('#jprev').addEventListener('click', () => jump(-1));
$('#jnext').addEventListener('click', () => jump(1));
$('#jscope').addEventListener('change', e => {
  JUMP.scope = e.target.value;
  try { localStorage.setItem('math2viz.jump', JUMP.scope); } catch (err) { /* ignore */ }
  updateJumpbar();
});
addEventListener('keydown', e => {
  if (VIEW !== 'read' || e.ctrlKey || e.metaKey || e.altKey || !$('#modal').hidden) return;
  if (e.target.closest && e.target.closest('input, select, textarea, [contenteditable]')) return;
  const k = e.key.toLowerCase();
  const d = e.key === 'ArrowDown' || e.key === 'ArrowRight' || k === 'j' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' || k === 'k' ? -1 : 0;
  if (d) { e.preventDefault(); jump(d); }
});
function currentPage() {
  const wrap = $('#pagesWrap'), y = wrap.scrollTop + 80;
  let lo = 0, hi = R.pageEls.length - 1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (R.pageEls[m].offsetTop <= y) lo = m; else hi = m - 1; }
  return D.books[R.bk].pages[lo][0];
}
function updateViewport() {
  const wrap = $('#pagesWrap'), vp = $('#minimap .vp');
  if (!vp || !wrap.scrollHeight) return;
  vp.style.top = (100 * wrap.scrollTop / wrap.scrollHeight) + '%';
  vp.style.height = Math.max(0.5, 100 * wrap.clientHeight / wrap.scrollHeight) + '%';
}
let scrollRaf = 0;
$('#pagesWrap').addEventListener('scroll', () => {
  if (scrollRaf) return;
  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = 0;
    updateViewport();
    if (!R.pageEls?.length) return;
    const p = currentPage();
    let cur = null;
    for (const n of R.nodes) if (n.pdf && n.pdf <= p && (TOC.showEx || !EXTRA.has(n.k))) cur = n.id;
    if (cur !== R.curNode) {
      R.curNode = cur;
      if (cur && !TOC.open.has(chapterOf(cur))) { TOC.open.add(chapterOf(cur)); renderToc(); }
      $$('#tocTree .tn.cur').forEach(el => el.classList.remove('cur'));
      const el = $(`#tocTree .tn[data-nid="${CSS.escape(cur || '')}"]`);
      if (el) { el.classList.add('cur'); el.scrollIntoView({ block: 'nearest' }); }
      if (!R.sel.size && !R.selNode) sidePanel();
    }
  });
});
$('#minimap').addEventListener('click', e => {
  const m = $('#minimap').getBoundingClientRect(), wrap = $('#pagesWrap');
  wrap.scrollTop = (e.clientY - m.top) / m.height * wrap.scrollHeight - wrap.clientHeight / 2;
});

// knowledge points a block belongs to: [kp, is the canonical statement]
function blockKps(i) {
  const out = new Map();
  (blockCards[i] || []).forEach(([c, st]) => (D.cards[c].kp || []).forEach(k => {
    const canon = K[k].c === c && st;
    if (!out.has(k) || canon) out.set(k, canon);
  }));
  return [...out].sort((a, b) => b[1] - a[1]);
}
function qItemsForBlock(i) {
  const topic = [], tool = [];
  for (const q of F) {
    if (qTB(q).has(i)) q.to.filter(t => topicBlocks(t, M()).includes(i)).forEach(t => topic.push({ q, t }));
    if (qOB(q).has(i)) q.ci.filter(c => citeBlocks(c, M()).includes(i)).forEach(c => tool.push({ q, c }));
  }
  const byYear = (a, b) => b.q.y - a.q.y || a.q.id.localeCompare(b.q.id);
  return { topic: topic.sort(byYear), tool: tool.sort(byYear) };
}
function topicItem({ q, t }, fb) {
  return `<div class="qi" data-q="${q.id}" ${fb != null ? `data-fb="${fb}"` : ''}><div class="h">${qHead(q)}<span class="badge ${t.p ? 'r-P' : 'r-S'}">${t.p ? '主考点' : '次考点'}</span></div>
    <div class="d">${fmtStep(clip(t.r, 110))}</div></div>`;
}
function toolItem({ q, c }, fb) {
  return `<div class="qi" data-q="${q.id}" ${fb != null ? `data-fb="${fb}"` : ''}><div class="h">${qHead(q)}<span class="badge r-${c.r}">${ROLE[c.r]}</span></div>
    <div class="d"><span class="tex">${esc(c.kp.length ? c.kp.map(k => K[k].n).join('、') : c.k)}</span> — <span>${stepsBrief(q, c.s, 90)}</span></div></div>`;
}
function kpRow(k, max, cls = 'ci', attr = 'data-kp') {
  return `<div class="${cls}" ${attr}="${k.i}"><div><div>${esc(k.n)}</div><div class="s">${BOOK_SHORT[k.bk] || ''} ${esc(nodeName(nodeById[k.node], true))} · ${KIND[k.k] || k.k}${k.m.length ? ` · 另见 ${k.m.length} 处` : ''} · 考点 ${H.ktn[k.i]} · 工具 ${H.kon[k.i]}</div></div><div class="bars">${bar(kHeat(k.i), max)}</div></div>`;
}
function statsHtml(topicHeat, topicN, toolHeat, toolN) {
  return `<div class="kv"><span class="stat topic">考点 <b>${topicN}</b> 题 <span class="muted small">热度 ${fmt(topicHeat)}</span></span>
    <span class="stat tool">工具 <b>${toolN}</b> 题 <span class="muted small">热度 ${fmt(toolHeat)}</span></span></div>`;
}
function sidePanel(bi) {
  const side = $('#side');
  if (bi == null) {
    const id = R.selNode || R.curNode;
    const n = nodeById[id];
    if (!n) { side.innerHTML = `<h2>${esc(D.books[R.bk].name)}</h2><p class="muted">点击页面上的色块查看相关真题；左侧目录的色条表示各节热度。</p>`; return; }
    const ids = new Set([id, ...D.nodes.filter(x => x.id.startsWith(id + '/')).map(x => x.id)]);
    const ks = K.filter(k => ids.has(k.node)).sort((a, b) => kHeat(b.i) - kHeat(a.i));
    const max = Math.max(1e-9, ...ks.map(k => kHeat(k.i)));
    side.innerHTML = `<div class="muted small">${esc(nodePath(n.p || ''))}</div><h2>${esc(nodeName(n))}</h2>
      ${statsHtml(nHeat(id, 'topic'), nCount(id, 'topic'), nHeat(id, 'tool'), nCount(id, 'tool'))}
      <h3>本节知识点（按${S.mode === 'topic' ? '考点' : '工具'}热度）</h3>
      ${ks.slice(0, 40).map(k => kpRow(k, max)).join('')}
      ${ks.length > 40 ? `<p class="muted small">另有 ${ks.length - 40} 个知识点</p>` : ''}
      <p class="muted small" style="margin-top:14px">提示：点击页面上的色块查看该段落关联的真题。</p>`;
    math(side);
    return;
  }
  const b = D.blocks[bi], n = nodeById[b.n];
  const { topic, tool } = qItemsForBlock(bi);
  const cards = (blockCards[bi] || []).sort((x, y) => y[1] - x[1]);
  const kps = blockKps(bi);
  const topicHtml = `<h3>作为考点（${topic.length}）</h3>${topic.map(x => topicItem(x, bi)).join('') || '<p class="muted small">当前筛选下没有</p>'}`;
  const toolHtml = `<h3>作为解题工具（${tool.length}）</h3>${tool.map(x => toolItem(x, bi)).join('') || '<p class="muted small">当前筛选下没有</p>'}`;
  side.innerHTML = `<div class="muted small">${esc(nodePath(b.n))}</div>
    <h2>${esc(b.nl || (cards.find(x => x[1]) ? cardName(D.cards[cards.find(x => x[1])[0]]) : ''))} <span class="muted small">${esc(D.books[b.bk].name)} · 第 ${esc(b.pg ?? '?')} 页</span></h2>
    ${statsHtml(H.bt[bi], H.btn[bi], H.bo[bi], H.bon[bi])}
    ${kps.length ? `<div>${kps.map(([k, canon]) => `<span class="chip" data-kp="${k}" title="${canon ? '本段是该知识点的规范出处' : '本段复述、推导或属于该知识点'}">${canon ? '★ ' : ''}${esc(K[k].n)}</span>`).join('')}</div>` : ''}
    <details><summary class="muted small" style="cursor:pointer;margin-top:6px">识别文本</summary><div class="tex small">${texHtml(b.t)}</div></details>
    ${S.mode === 'topic' ? topicHtml + toolHtml : toolHtml + topicHtml}
    ${n ? `<p style="margin-top:16px"><a data-node="${esc(n.id)}">← 本节概况</a></p>` : ''}`;
  math(side);
}
$('#bookTabs').innerHTML = BOOKS.map(bk => `<button data-bk="${bk}">${BOOK_SHORT[bk]}</button>`).join('');
$('#bookTabs').addEventListener('click', e => { const b = e.target.closest('button'); if (b) location.hash = '#read/' + b.dataset.bk; });

/* ---------- overview ---------- */
const OV = { open: new Set(), openTree: new Set(D.nodes.filter(n => n.k === 'chapter').map(n => n.id)), sort: 'book' };
function chapterYear(ids) {
  // distinct questions per node per year (type filter only; the year filter only dims columns)
  const m = {};
  ids.forEach(id => { m[id] = {}; });
  D.questions.forEach(q => {
    if (!typeOk(q)) return;
    const nm = S.mode === 'topic' ? qTN(q) : qON(q);
    ids.forEach(id => { if (nm.has(id)) m[id][q.y] = (m[id][q.y] || 0) + 1; });
  });
  return m;
}
function renderOverview() {
  const el = $('#v-overview');
  const chapters = D.nodes.filter(n => n.k === 'chapter' && (n.in || n.kids.some(k => k.in)));
  const rows = [];
  chapters.forEach(c => { rows.push(c); if (OV.open.has(c.id)) c.kids.filter(k => k.in).forEach(k => rows.push(k)); });
  const cy = chapterYear(rows.map(r => r.id));
  const max = Math.max(1, ...rows.filter(r => r.k === 'chapter').flatMap(r => Object.values(cy[r.id])));
  let lastBk = null;
  let hm = `<table class="hm"><tr><th></th>${YEARS.map(y => `<th class="yr${y >= S.y0 && y <= S.y1 ? ' in' : ''}" data-year="${y}" title="只看 ${y} 年">${y}</th>`).join('')}<th></th></tr>`;
  rows.forEach(r => {
    if (r.bk !== lastBk) { lastBk = r.bk; hm += `<tr><td class="name muted" colspan="${YEARS.length + 2}" style="padding-top:8px">${esc(D.books[r.bk].name)}</td></tr>`; }
    const tot = YEARS.filter(y => y >= S.y0 && y <= S.y1).reduce((s, y) => s + (cy[r.id][y] || 0), 0);
    hm += `<tr class="${r.k === 'chapter' ? '' : 'sub'}"><td class="name" data-ov="${esc(r.id)}" title="${esc(nodeName(r))}">${r.k === 'chapter' ? (OV.open.has(r.id) ? '▾ ' : '▸ ') : ''}${esc(nodeName(r))}</td>` +
      YEARS.map(y => { const v = cy[r.id][y] || 0; return `<td class="c${y >= S.y0 && y <= S.y1 ? '' : ' out'}" style="background:${v ? heatColor(v, max, S.mode, 0.15, 0.85) : 'var(--hover)'}" title="${y} · ${esc(nodeName(r, true))} · ${v} 题">${v || ''}</td>`; }).join('') +
      `<td class="tot">${tot}</td></tr>`;
  });
  hm += '</table>';

  const tree = renderTree();
  el.innerHTML = `<h2>各章历年出题分布 <span class="muted small">格内数字 = 当年涉及该章的题数（${S.mode === 'topic' ? '按考查主题' : '按解题所用工具'}；题型筛选生效，点年份只看该年，点章名展开各节）</span></h2>
    <div style="overflow:auto">${hm}</div>
    <h2 style="margin-top:28px">章 → 节 → 知识点热度 <span class="muted small">${S.y0}–${S.y1}，${F.length} 题；数字为涉及题数，色条为加权热度（对数刻度）</span>
      <select id="ovSort"><option value="book">按书序</option><option value="heat">按当前热度</option></select></h2>
    <div class="tree">${tree}</div>`;
  $('#ovSort').value = OV.sort;
  math(el);
}
function renderTree() {
  const maxAt = { topic: {}, tool: {} };
  D.nodes.forEach(n => ['topic', 'tool'].forEach(m => { maxAt[m][n.k] = Math.max(maxAt[m][n.k] || 0, nHeat(n.id, m)); }));
  const cmax = { topic: H.kmax.topic, tool: H.kmax.tool };
  const lv = { chapter: 1, section: 2, subsection: 3 };
  let out = `<div class="row head"><span>章节 / 知识点</span><span class="num">考点题数</span><span>考点热度</span><span class="num">工具题数</span><span>工具热度</span></div>`;
  const sortN = arr => OV.sort === 'heat' ? [...arr].sort((a, b) => nHeat(b.id) - nHeat(a.id)) : arr;
  const walk = n => {
    if (!n.in && !n.kids.some(k => k.in || k.kids.some(kk => kk.in))) return;
    const open = OV.openTree.has(n.id), hasKids = n.kids.length || n.kps.length;
    out += `<div class="row lv${lv[n.k] || 3}"><span class="nm" data-tree="${esc(n.id)}"><span class="tw">${hasKids ? (open ? '▾' : '▸') : ''}</span>${esc(nodeName(n))}</span>
      <span class="num">${nCount(n.id, 'topic') || ''}</span>${bar(nHeat(n.id, 'topic'), maxAt.topic[n.k], 'topic')}
      <span class="num">${nCount(n.id, 'tool') || ''}</span>${bar(nHeat(n.id, 'tool'), maxAt.tool[n.k], 'tool')}</div>`;
    if (!open) return;
    sortN(n.kids).forEach(walk);
    const ks = [...n.kps].sort((a, b) => OV.sort === 'heat' ? kHeat(b) - kHeat(a) : 0).filter(k => K[k].in);
    ks.forEach(k => {
      const kp = K[k];
      out += `<div class="row lv4"><span class="nm" data-kp="${k}"><span class="tw"></span><span class="badge muted">${KIND[kp.k] || kp.k}</span> ${esc(kp.n)}</span>
        <span class="num">${H.ktn[k] || ''}</span>${bar(H.kt[k], cmax.topic, 'topic')}<span class="num">${H.kon[k] || ''}</span>${bar(H.ko[k], cmax.tool, 'tool')}</div>`;
    });
  };
  sortN(D.nodes.filter(n => n.k === 'chapter')).forEach(walk);
  return out;
}
$('#v-overview').addEventListener('click', e => {
  const y = e.target.closest('[data-year]');
  if (y) { setYears(+y.dataset.year, +y.dataset.year); return; }
  const r = e.target.closest('[data-ov]');
  if (r) { const id = r.dataset.ov; if (nodeById[id].k === 'chapter') { OV.open.has(id) ? OV.open.delete(id) : OV.open.add(id); renderOverview(); } else goNode(id); return; }
  const t = e.target.closest('[data-tree]');
  if (t) { const id = t.dataset.tree; OV.openTree.has(id) ? OV.openTree.delete(id) : OV.openTree.add(id); const sc = $('#v-overview').scrollTop; renderOverview(); $('#v-overview').scrollTop = sc; }
});
$('#v-overview').addEventListener('change', e => { if (e.target.id === 'ovSort') { OV.sort = e.target.value; renderOverview(); } });

/* ---------- knowledge points ---------- */
const CV = { q: '', bk: '', kind: 'formal', sort: 'heat', hit: false, cur: null, order: [], tab: 'src', nolist: false };
try { CV.tab = localStorage.getItem('math2viz.kpTab') || 'src'; CV.nolist = localStorage.getItem('math2viz.kpNoList') === '1'; } catch (e) { /* defaults */ }
function kpSet(q, basis) {
  const s = new Set();
  if (basis !== 'tool') q.tk.forEach((w, k) => s.add(k));
  if (basis !== 'topic') qOK(q).forEach((w, k) => s.add(k));
  return s;
}
// what question solutions actually said when they used a knowledge point (for search and the detail page)
const kpWords = K.map(() => new Map());
D.questions.forEach(q => q.ci.forEach(c => c.kp.forEach(k => kpWords[k].set(c.k, (kpWords[k].get(c.k) || 0) + 1))));
K.forEach(k => {
  const cs = [k.c, ...k.m.map(m => m[0])].filter(c => c >= 0).map(c => cardName(D.cards[c]));
  k.search = [k.n, k.s, ...cs, ...kpWords[k.i].keys(), k.node || ''].join(' ').toLowerCase();
});
function renderCardList() {
  const box = $('#cardList');
  if (!box.dataset.init) {
    box.dataset.init = 1;
    box.innerHTML = `<div class="ctl"><input type="search" id="cq" placeholder="搜索知识点、公式、教材编号、真题里的说法…">
      <select id="cbk"><option value="">全部教材</option>${BOOKS.map(b => `<option value="${b}">${BOOK_SHORT[b]}</option>`).join('')}</select>
      <select id="ckind"><option value="formal">不含例题</option><option value="">全部类型</option>${['definition', 'theorem', 'formula', 'property', 'method', 'concept', 'example'].map(k => `<option value="${k}">${KIND[k]}</option>`).join('')}</select>
      <select id="csort"><option value="heat">按当前热度</option><option value="topic">按考点热度</option><option value="tool">按工具热度</option><option value="book">按书序</option></select>
      <label class="small"><input type="checkbox" id="chit">只看考过的</label></div><div class="lst"></div>`;
    const upd = () => { CV.q = $('#cq').value.trim(); CV.bk = $('#cbk').value; CV.kind = $('#ckind').value; CV.sort = $('#csort').value; CV.hit = $('#chit').checked; renderCardList(); };
    ['#cq', '#cbk', '#ckind', '#csort', '#chit'].forEach(s => $(s, box).addEventListener('input', upd));
    $('#ckind').value = CV.kind;
  }
  const words = CV.q.toLowerCase().split(/\s+/).filter(Boolean);
  const ks = K.filter(k => k.in && (!CV.bk || k.bk === CV.bk) && (!CV.kind || (CV.kind === 'formal' ? KP_FORMAL(k) : k.k === CV.kind)) &&
    (!CV.hit || kHit(k.i)) && (!words.length || words.every(w => k.search.includes(w))));
  const key = { heat: k => -kHeat(k.i), topic: k => -H.kt[k.i], tool: k => -H.ko[k.i], book: k => k.c }[CV.sort];
  ks.sort((a, b) => key(a) - key(b) || a.c - b.c);
  CV.order = ks.map(k => k.i);
  const shown = ks.slice(0, 600);
  $('.lst', box).innerHTML = `<div class="muted small" style="padding:6px 12px">${ks.length} 个知识点${ks.length > 600 ? '（显示前 600）' : ''}</div>` +
    shown.map(k => `<div class="ci${CV.cur === k.i ? ' cur' : ''}" data-kpsel="${k.i}"><div><div>${esc(k.n)}</div>
      <div class="s">${BOOK_SHORT[k.bk]} ${esc(nodeName(nodeById[k.node], true))} · ${KIND[k.k] || k.k}${k.m.length ? ` · 另见 ${k.m.length} 处` : ''} · 考点 ${H.ktn[k.i]} · 工具 ${H.kon[k.i]}</div></div>
      <div class="bars">${bar(H.kt[k.i], H.kmax.topic, 'topic')}${bar(H.ko[k.i], H.kmax.tool, 'tool')}</div></div>`).join('');
}
$('#cardList').addEventListener('click', e => { const c = e.target.closest('[data-kpsel]'); if (c) go('cards', K[+c.dataset.kpsel].id); });
function kpTab(t) {
  CV.tab = t;
  try { localStorage.setItem('math2viz.kpTab', t); } catch (e) { /* ignore */ }
  const d = $('#cardDetail .kpd');
  if (!d) return;
  d.dataset.tab = t;
  $$('#cardDetail .kp-tabs [data-kptab]').forEach(b => b.classList.toggle('cur', b.dataset.kptab === t));
  const nav = $('#cardDetail .kp-tabs'), box = $('#cardDetail');
  if (nav.getBoundingClientRect().top < box.getBoundingClientRect().top + 1) box.scrollTop = nav.offsetTop - box.offsetTop;
}
function kpList(show) {
  CV.nolist = !show;
  try { localStorage.setItem('math2viz.kpNoList', CV.nolist ? '1' : '0'); } catch (e) { /* ignore */ }
  $('#v-cards').classList.toggle('nolist', CV.nolist);
  const b = $('#cardDetail [data-kplist]'); if (b) b.textContent = CV.nolist ? '☰ 列表' : '⇤ 收起列表';
}
function kpStep(d) {
  const i = CV.order.indexOf(CV.cur) + d;
  if (i >= 0 && i < CV.order.length) go('cards', K[CV.order[i]].id);
}
$('#cardDetail').addEventListener('click', e => {
  const t = e.target.closest('[data-kptab]'); if (t) return kpTab(t.dataset.kptab);
  if (e.target.closest('[data-kplist]')) return kpList(CV.nolist);
  const st = e.target.closest('[data-kpstep]'); if (st) kpStep(+st.dataset.kpstep);
});
$('#v-cards').classList.toggle('nolist', CV.nolist);
addEventListener('keydown', e => {
  if (VIEW !== 'cards' || e.ctrlKey || e.metaKey || e.altKey || !$('#modal').hidden) return;
  if (e.target.closest && e.target.closest('input, select, textarea, [contenteditable]')) return;
  const k = e.key.toLowerCase();
  const d = e.key === 'ArrowDown' || e.key === 'ArrowRight' || k === 'j' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' || k === 'k' ? -1 : 0;
  if (d) { e.preventDefault(); kpStep(d); }
  else if (k === 'l') kpList(CV.nolist);
  else if (k === '1' || k === '2' || k === '3') kpTab(['src', 'dep', 'exam'][+k - 1]);
});
// textbook excerpts in the knowledge-point page: up to the reading column's width, a bit above print size
const SNIP_W = 700, SNIP_S = 0.7;
function renderCardDetail() {
  const el = $('#cardDetail');
  const k = K[CV.cur];
  if (!k) { el.innerHTML = '<p class="muted">从左侧选择一个知识点。</p>'; return; }
  const c = D.cards[k.c];
  const topicY = {}, toolY = {};
  D.questions.forEach(q => { if (!typeOk(q)) return; if (q.tk.has(k.i)) topicY[q.y] = (topicY[q.y] || 0) + 1; if (qOK(q).has(k.i)) toolY[q.y] = (toolY[q.y] || 0) + 1; });
  const topic = [], tool = [];
  F.forEach(q => {
    q.to.filter(t => t.kp === k.i).forEach(t => topic.push({ q, t }));
    q.ci.filter(x => x.kp.includes(k.i)).forEach(x => tool.push({ q, c: x }));
  });
  topic.sort((a, b) => b.q.y - a.q.y); tool.sort((a, b) => b.q.y - a.q.y);
  const co = new Map(); let nq = 0;
  F.forEach(q => { const s = kpSet(q, 'both'); if (!s.has(k.i)) return; nq++; s.forEach(o => { if (o !== k.i) co.set(o, (co.get(o) || 0) + 1); }); });
  const partners = [...co].sort((a, b) => b[1] - a[1]).slice(0, 16);
  const st = kpStBlocks(k);
  const words = [...kpWords[k.i]].sort((a, b) => b[1] - a[1]);
  const pos = CV.order.indexOf(k.i), rng = S.y0 === S.y1 ? `${S.y0} 年` : `${S.y0}–${S.y1}`;
  const nDep = k.d.length + k.u.length, nExam = topic.length + tool.length;
  const tabs = [['src', '原文', st.length ? `${st.length} 段` : ''], ['dep', '推导', nDep || ''], ['exam', '真题', nExam || '']];
  // reading-first: title, statement and a one-line summary; everything else sits behind three tabs
  el.innerHTML = `<div class="kpd" data-tab="${CV.tab}">
    <div class="kpd-top"><button class="icon" data-kplist title="收起或展开左侧列表（L）">${CV.nolist ? '☰ 列表' : '⇤ 收起列表'}</button>
      <span class="crumb muted small" title="${esc(D.books[k.bk]?.name || '')} › ${esc(nodePath(k.node))}">${esc(BOOK_SHORT[k.bk] || '')} › ${esc(nodePath(k.node))}</span>
      ${pos >= 0 ? `<span class="kp-nav"><button class="icon" data-kpstep="-1" ${pos > 0 ? '' : 'disabled'} title="上一个（↑ / ←）">↑</button><span class="muted small">${pos + 1} / ${CV.order.length}</span><button class="icon" data-kpstep="1" ${pos < CV.order.length - 1 ? '' : 'disabled'} title="下一个（↓ / →）">↓</button></span>` : ''}</div>
    <h1 class="kp-title">${esc(k.n)} <span class="badge muted">${KIND[k.k] || k.k}</span></h1>
    <div class="kp-stmt tex">${stmtHtml(k.s)}<button class="copy" data-copy="${k.i}" title="复制这条表述（公式为 LaTeX 源码）">复制</button></div>
    <div class="kp-meta" data-kptab="exam" title="查看真题（3）">
      <span class="stat topic">考点 <b>${H.ktn[k.i]}</b> 题</span><span class="stat tool">工具 <b>${H.kon[k.i]}</b> 题</span>
      <span class="muted small">${rng}</span>${sparkChart(topicY, toolY)}</div>
    <nav class="kp-tabs">${tabs.map(([t, l, n], x) => `<button data-kptab="${t}" class="${t === CV.tab ? 'cur' : ''}" title="${l}（${x + 1}）">${l}${n !== '' ? ` <span class="n">${n}</span>` : ''}</button>`).join('')}</nav>
    <section data-pane="src">
      <h3>规范出处：${c ? esc(cardName(c)) : ''} <a class="small" data-read="${st.join(',')}">在书中查看</a></h3>
      ${st.slice(0, 8).map(b => snippet(b, SNIP_W, SNIP_S)).join('')}${st.length > 8 ? `<p class="muted small">…共 ${st.length} 段</p>` : ''}
      ${k.m.length ? `<h3>书中其他讲到它的地方（${k.m.length}）</h3>` + k.m.map(([mc, rel]) => {
        const card = D.cards[mc], bl = card.st.length ? card.st : card.sp;
        return `<details class="member"><summary><span class="badge muted">${KREL[rel] || rel}</span> ${esc(cardName(card))} <span class="muted small">${card.bk !== k.bk ? BOOK_SHORT[card.bk] + ' ' : ''}${esc(nodeName(nodeById[card.n], true))}</span> · <a class="small" data-read="${bl.join(',')}">在书中查看</a></summary>${bl.slice(0, 4).map(b => snippet(b, SNIP_W, SNIP_S)).join('')}</details>`;
      }).join('') : ''}
    </section>
    <section data-pane="dep">${depsHtml(k)}</section>
    <section data-pane="exam">
      <div class="kp-heat muted small">${rng}热度：考点 ${fmt(H.kt[k.i])} · 工具 ${fmt(H.ko[k.i])}；全部年份共 ${DF[k.i]} 题用它作工具${IDF[k.i] < 1 ? `（普遍工具，降权系数 ${IDF[k.i].toFixed(2)}）` : ''}${H.kti[k.i] + H.koi[k.i] > 0 ? `；作为其他知识点的依据，间接热度考点 ${fmt(H.kti[k.i])} · 工具 ${fmt(H.koi[k.i])}${S.inh ? '（已计入）' : '（勾选“依据继承热度”可计入）'}` : ''}</div>
      <h3>历年出现 <span class="muted small">淡色为筛选范围外的年份</span></h3>${yearChart(topicY, toolY)}
      <h3>作为考点（${topic.length}）</h3>${topic.map(x => topicItem(x)).join('') || '<p class="muted small">当前筛选下没有</p>'}
      <h3>作为解题工具（${tool.length}）</h3>${tool.map(x => toolItem(x)).join('') || '<p class="muted small">当前筛选下没有</p>'}
      <h3>常一起出现 <span class="muted small">与它同题出现的知识点（${nq} 题）</span></h3>
      ${partners.slice(0, 10).map(([o, n]) => `<span class="chip" data-kp="${o}">${esc(K[o].n)} <b>${n}</b></span>`).join('') || '<p class="muted small">无</p>'}
      ${words.length ? `<details class="words"><summary class="muted small">真题解答里的原话（${words.length} 种说法）</summary>
        <div class="small">${words.map(([w, n]) => `<div>${esc(w)} <span class="muted">×${n}</span></div>`).join('')}</div></details>` : ''}
    </section></div>`;
  el.scrollTop = 0;
  math(el);
}

const DTY = ['概念', '证明'];
function depRow([o, ty, src]) {
  const h = kHeat(o);
  return `<span class="chip" data-kp="${o}" data-kpnote="${DTY[ty]}${ty ? '中用到' : '上的依据'} · ${src & 1 ? '书中明确引用' : '据原文判断'}"><span class="badge muted">${DTY[ty]}</span> ${esc(K[o].n)}${src & 1 ? ' <span class="muted">§</span>' : ''}${h > 0 ? ` <b>${fmt(h)}</b>` : ''}</span>`;
}
function depsHtml(k) {
  const up = [...k.u].sort((a, b) => kHeat(b[0]) - kHeat(a[0]));
  return `<h3>推导依据（${k.d.length}） <span class="muted small">它建立在这些知识点之上；§ = 书中明确引用，数字 = 当前热度</span></h3>
    ${k.d.map(depRow).join('') || '<p class="muted small">无（定义、记号或直接给出的结论）</p>'}
    <h3>以它为依据（${k.u.length}） <span class="muted small">按当前热度排序</span></h3>
    ${up.slice(0, 40).map(depRow).join('')}${up.length > 40 ? ` <span class="muted small">…共 ${up.length} 个</span>` : ''}${up.length ? '' : '<p class="muted small">无</p>'}`;
}

/* ---------- graph ---------- */
const G = { n: 120, minCo: 2, basis: 'both', ec: 'co', group: true, bk: '', nodes: [], edges: [], tx: 0, ty: 0, k: 1, hover: null, sel: null, drag: null, alpha: 0, raf: 0 };
const chapterIds = D.nodes.filter(n => n.k === 'chapter').map(n => n.id);
const chapterColor = {};
chapterIds.forEach((id, i) => { chapterColor[id] = `hsl(${(i * 137.508 + 20) % 360}, 58%, ${isLA(id.split('/')[0]) ? 42 : 50}%)`; });
function initGraphCtl() {
  const c = $('#graphCtl');
  c.innerHTML = `<div class="row">节点 <input type="range" id="gn" min="30" max="400" step="10" value="${G.n}"><span id="gnv">${G.n}</span></div>
    <div class="row">最少共现 <input type="range" id="gm" min="1" max="12" value="${G.minCo}"><span id="gmv">${G.minCo}</span></div>
    <div class="row"><select id="gb"><option value="both">考点+工具共现</option><option value="topic">仅考点共现</option><option value="tool">仅工具共现</option></select>
      <select id="gbk"><option value="">全部</option><option value="GS">高数</option><option value="LA">线代</option></select></div>
    <div class="row"><select id="ge"><option value="co">边：共现</option><option value="dep">边：推导依据</option><option value="both">边：共现＋推导依据</option></select></div>
    <label class="row"><input type="checkbox" id="gg" ${G.group ? 'checked' : ''}>按章聚拢</label>
    <div class="muted small">节点大小 = 当前热度；灰边 = 同一题中共同出现的题数；橙色箭头 = 推导依据（依据 → 由它推出的知识点，实线为证明中用到，虚线为概念上的依据）。拖动画布平移，滚轮缩放，点节点看详情。</div>
    <div class="legend" id="glegend"></div>`;
  const upd = () => { G.n = +$('#gn').value; G.minCo = +$('#gm').value; G.basis = $('#gb').value; G.bk = $('#gbk').value; G.ec = $('#ge').value; G.group = $('#gg').checked;
    $('#gnv').textContent = G.n; $('#gmv').textContent = G.minCo; buildGraph(); };
  ['#gn', '#gm', '#gb', '#gbk', '#ge', '#gg'].forEach(s => $(s).addEventListener('input', upd));
}
function buildGraph() {
  const keep = K.filter(k => k.in && kHeat(k.i) > 0 && (!G.bk || (G.bk === 'GS' ? !isLA(k.bk) : isLA(k.bk))))
    .sort((a, b) => kHeat(b.i) - kHeat(a.i)).slice(0, G.n);
  const idx = new Map(keep.map((c, k) => [c.i, k]));
  const old = new Map(G.nodes.map(n => [n.c, n]));
  const chs = [...new Set(keep.map(k => k.ch))];
  const R0 = 260 + 4 * Math.sqrt(keep.length) * 10;
  const center = {};
  chs.forEach((ch, k) => { const a = 2 * Math.PI * k / chs.length; center[ch] = [Math.cos(a) * R0 * 0.55, Math.sin(a) * R0 * 0.55]; });
  const maxH = Math.max(1e-9, ...keep.map(k => kHeat(k.i)));
  G.nodes = keep.map(k => {
    const o = old.get(k.i), ch = k.ch, cc = center[ch];
    return { c: k.i, ch, cx: cc[0], cy: cc[1], x: o ? o.x : cc[0] + (Math.random() - 0.5) * 120, y: o ? o.y : cc[1] + (Math.random() - 0.5) * 120,
      vx: 0, vy: 0, r: 3.5 + 13 * Math.sqrt(kHeat(k.i) / maxH), h: kHeat(k.i) };
  });
  const pair = new Map();
  if (G.ec !== 'dep') F.forEach(q => {
    const s = [...kpSet(q, G.basis)].filter(c => idx.has(c)).map(c => idx.get(c)).sort((a, b) => a - b);
    for (let i = 0; i < s.length; i++) for (let j = i + 1; j < s.length; j++) { const k = s[i] * 4096 + s[j]; pair.set(k, (pair.get(k) || 0) + 1); }
  });
  G.edges = [...pair].filter(([, w]) => w >= G.minCo).map(([k, w]) => ({ a: Math.floor(k / 4096), b: k % 4096, w }));
  G.maxW = Math.max(1, ...G.edges.map(e => e.w));
  G.adj = G.nodes.map(() => []);
  G.edges.forEach(e => { G.adj[e.a].push([e.b, e.w]); G.adj[e.b].push([e.a, e.w]); });
  G.dedges = [];
  if (G.ec !== 'co') keep.forEach((k, a) => k.d.forEach(([t, ty]) => { if (idx.has(t)) G.dedges.push({ a, b: idx.get(t), ty }); }));
  G.dadj = G.nodes.map(() => []);
  G.dedges.forEach(e => { G.dadj[e.a].push(e.b); G.dadj[e.b].push(e.a); });
  $('#glegend').innerHTML = chs.map(ch => `<span><i style="background:${chapterColor[ch]}"></i>${esc(nodeName(nodeById[ch], true))}${isLA(ch.split('/')[0]) ? '(线)' : ''}</span>`).join('');
  G.alpha = 1; G.touched = false;
  if (!G.raf) G.raf = requestAnimationFrame(tick);
  graphSide();
}
function tick() {
  G.raf = 0;
  const N = G.nodes, a = G.alpha;
  if (a > 0.005) {
    for (let s = 0; s < 2; s++) {
      for (let i = 0; i < N.length; i++) {
        const p = N[i];
        for (let j = i + 1; j < N.length; j++) {
          const q = N[j]; let dx = p.x - q.x, dy = p.y - q.y; let d2 = dx * dx + dy * dy + 0.01;
          if (d2 > 250000) continue;
          const f = 2200 * a / d2, d = Math.sqrt(d2);
          const mind = p.r + q.r + 4;
          const g = d < mind ? (mind - d) * 0.5 : 0;
          dx /= d; dy /= d;
          p.vx += dx * (f + g); p.vy += dy * (f + g); q.vx -= dx * (f + g); q.vy -= dy * (f + g);
        }
      }
      G.edges.forEach(e => {
        const p = N[e.a], q = N[e.b]; const dx = q.x - p.x, dy = q.y - p.y; const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
        const k = 0.02 * a * Math.min(1, 0.3 + e.w / G.maxW) * (d - 50) / d;
        p.vx += dx * k; p.vy += dy * k; q.vx -= dx * k; q.vy -= dy * k;
      });
      G.dedges.forEach(e => {
        const p = N[e.a], q = N[e.b]; const dx = q.x - p.x, dy = q.y - p.y; const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
        const k = 0.012 * a * (d - 60) / d;
        p.vx += dx * k; p.vy += dy * k; q.vx -= dx * k; q.vy -= dy * k;
      });
      N.forEach(p => {
        const gx = G.group ? p.cx : 0, gy = G.group ? p.cy : 0;
        p.vx += (gx - p.x) * 0.012 * a; p.vy += (gy - p.y) * 0.012 * a;
        if (p === G.drag) { p.vx = p.vy = 0; return; }
        p.vx *= 0.6; p.vy *= 0.6; p.x += p.vx; p.y += p.vy;
      });
    }
    G.alpha *= 0.985;
    if (!G.touched) fitGraph();
    G.raf = requestAnimationFrame(tick);
  }
  drawGraph();
}
function fitGraph() {
  const cv = $('#graph'), W = cv.clientWidth - 360, Hh = cv.clientHeight;
  if (!G.nodes.length || W <= 0) return;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  G.nodes.forEach(p => { x0 = Math.min(x0, p.x - p.r); x1 = Math.max(x1, p.x + p.r); y0 = Math.min(y0, p.y - p.r); y1 = Math.max(y1, p.y + p.r); });
  G.k = Math.min(3, W / (x1 - x0 + 60), Hh / (y1 - y0 + 60));
  G.tx = -G.k * (x0 + x1) / 2; G.ty = -G.k * (y0 + y1) / 2;
}
function drawGraph() {
  const cv = $('#graph'), dpr = devicePixelRatio || 1;
  const W = cv.clientWidth, Hh = cv.clientHeight;
  if (!W) return;
  if (cv.width !== W * dpr || cv.height !== Hh * dpr) { cv.width = W * dpr; cv.height = Hh * dpr; }
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, Hh);
  ctx.translate((W - 360) / 2 + G.tx, Hh / 2 + G.ty);
  ctx.scale(G.k, G.k);
  const focus = G.hover ?? G.sel;
  const nb = focus != null ? new Set([focus, ...G.adj[focus].map(x => x[0]), ...G.dadj[focus]]) : null;
  const ink = getComputedStyle(document.body).color;
  G.edges.forEach(e => {
    const p = G.nodes[e.a], q = G.nodes[e.b];
    const on = nb && (e.a === focus || e.b === focus);
    ctx.globalAlpha = nb ? (on ? 0.8 : 0.04) : 0.12 + 0.5 * e.w / G.maxW;
    ctx.strokeStyle = on ? ink : '#888';
    ctx.lineWidth = (0.6 + 3.5 * e.w / G.maxW) / Math.sqrt(G.k);
    ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
  });
  const dcol = '#d0782c';
  G.dedges.forEach(e => { // arrow from the basis (b) to the point derived from it (a)
    const p = G.nodes[e.b], q = G.nodes[e.a];
    const on = nb && (e.a === focus || e.b === focus);
    ctx.globalAlpha = nb ? (on ? 0.9 : 0.04) : 0.4;
    ctx.strokeStyle = dcol; ctx.fillStyle = dcol;
    ctx.lineWidth = (on ? 1.8 : 1.1) / Math.sqrt(G.k);
    ctx.setLineDash(e.ty ? [] : [4 / G.k, 3 / G.k]);
    const dx = q.x - p.x, dy = q.y - p.y, d = Math.hypot(dx, dy) || 1, ux = dx / d, uy = dy / d;
    const ex = q.x - ux * (q.r + 1), ey = q.y - uy * (q.r + 1), s = 7 / Math.sqrt(G.k);
    ctx.beginPath(); ctx.moveTo(p.x + ux * p.r, p.y + uy * p.r); ctx.lineTo(ex, ey); ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex - ux * s - uy * s * 0.45, ey - uy * s + ux * s * 0.45);
    ctx.lineTo(ex - ux * s + uy * s * 0.45, ey - uy * s - ux * s * 0.45); ctx.closePath(); ctx.fill();
  });
  const lab = [...G.nodes].sort((a, b) => b.h - a.h).slice(0, Math.round(18 * Math.max(1, G.k * G.k)));
  const labSet = new Set(lab);
  G.nodes.forEach((p, i) => {
    ctx.globalAlpha = nb && !nb.has(i) ? 0.15 : 1;
    ctx.fillStyle = chapterColor[p.ch] || '#888';
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 7); ctx.fill();
    if (i === G.sel) { ctx.lineWidth = 3 / G.k; ctx.strokeStyle = ink; ctx.stroke(); }
  });
  ctx.font = `${12 / G.k}px sans-serif`;
  ctx.textAlign = 'center';
  G.nodes.forEach((p, i) => {
    if (!(labSet.has(p) || (nb && nb.has(i)))) return;
    if (nb && !nb.has(i)) return;
    ctx.globalAlpha = 1;
    const t = clip(K[p.c].n, 14);
    ctx.lineWidth = 3 / G.k; ctx.strokeStyle = getComputedStyle(document.body).backgroundColor; ctx.strokeText(t, p.x, p.y - p.r - 3 / G.k);
    ctx.fillStyle = ink; ctx.fillText(t, p.x, p.y - p.r - 3 / G.k);
  });
  ctx.globalAlpha = 1;
}
function graphPos(e) {
  const cv = $('#graph'), b = cv.getBoundingClientRect();
  return [((e.clientX - b.left) - (cv.clientWidth - 360) / 2 - G.tx) / G.k, ((e.clientY - b.top) - cv.clientHeight / 2 - G.ty) / G.k];
}
function nodeAt(e) {
  const [x, y] = graphPos(e);
  let best = null, bd = Infinity;
  G.nodes.forEach((p, i) => { const d = Math.hypot(p.x - x, p.y - y); if (d < p.r + 4 / G.k && d < bd) { bd = d; best = i; } });
  return best;
}
(() => {
  const cv = $('#graph');
  let pan = null, moved = false;
  cv.addEventListener('mousedown', e => { moved = false; const i = nodeAt(e); if (i != null) { G.drag = G.nodes[i]; } else pan = [e.clientX - G.tx, e.clientY - G.ty]; });
  addEventListener('mousemove', e => {
    if (!$('#v-graph').classList.contains('on')) return;
    if (G.drag) { moved = true; const [x, y] = graphPos(e); G.drag.x = x; G.drag.y = y; G.alpha = Math.max(G.alpha, 0.2); if (!G.raf) G.raf = requestAnimationFrame(tick); return; }
    if (pan) { moved = true; G.touched = true; G.tx = e.clientX - pan[0]; G.ty = e.clientY - pan[1]; drawGraph(); return; }
    if (e.target !== cv) return;
    const i = nodeAt(e);
    if (i !== G.hover) { G.hover = i; drawGraph(); }
    if (i != null) { const k = K[G.nodes[i].c]; showTip(e, `${esc(k.n)}<br>${esc(nodePath(k.node))}<br>考点 ${H.ktn[k.i]} 题 · 工具 ${H.kon[k.i]} 题 · 共现边 ${G.adj[i].length} · 依据边 ${G.dadj[i].length}`); } else hideTip();
  });
  addEventListener('mouseup', e => {
    if (G.drag && !moved) { G.sel = G.nodes.indexOf(G.drag); graphSide(); drawGraph(); }
    else if (pan && !moved && e.target === cv) { G.sel = null; graphSide(); drawGraph(); }
    G.drag = null; pan = null;
  });
  cv.addEventListener('mouseleave', () => { G.hover = null; hideTip(); drawGraph(); });
  cv.addEventListener('wheel', e => {
    e.preventDefault();
    const f = Math.exp(-e.deltaY * 0.0015), cvb = cv.getBoundingClientRect();
    const mx = e.clientX - cvb.left - (cv.clientWidth - 360) / 2, my = e.clientY - cvb.top - cv.clientHeight / 2;
    G.touched = true; G.tx = mx - (mx - G.tx) * f; G.ty = my - (my - G.ty) * f; G.k *= f; drawGraph();
  }, { passive: false });
  addEventListener('resize', () => { if ($('#v-graph').classList.contains('on')) drawGraph(); });
})();
function graphSide() {
  const el = $('#graphSide');
  if (G.sel == null || !G.nodes[G.sel]) {
    el.innerHTML = `<h2>知识关联图</h2><p class="muted">${G.nodes.length} 个知识点、${G.edges.length} 条共现边、${G.dedges.length} 条推导依据边（${S.y0}–${S.y1}，${F.length} 题）。</p>
      <h3>最强的共现</h3>${[...G.edges].sort((a, b) => b.w - a.w).slice(0, 25).map(e => `<div class="qi" data-gsel="${e.a}"><div class="h"><b>${e.w}</b> 题</div>
      <div class="d">${esc(K[G.nodes[e.a].c].n)} ＋ ${esc(K[G.nodes[e.b].c].n)}</div></div>`).join('')}`;
    return;
  }
  const p = G.nodes[G.sel], k = K[p.c];
  el.innerHTML = `<div class="muted small">${esc(nodePath(k.node))}</div><h2>${esc(k.n)}</h2>
    ${statsHtml(H.kt[k.i], H.ktn[k.i], H.ko[k.i], H.kon[k.i])}
    <div class="kp-stmt tex compact">${stmtHtml(k.s)}</div>
    <p><a data-kp="${k.i}">打开知识点</a> · <a data-read="${kpStBlocks(k).join(',')}">在书中查看</a> · <a data-gsel="">返回</a></p>
    <h3>共现邻居（${G.adj[G.sel].length}）</h3>
    ${[...G.adj[G.sel]].sort((a, b) => b[1] - a[1]).map(([j, w]) => `<div class="qi" data-gsel="${j}"><div class="h"><b>${w}</b> 题 <span>${esc(K[G.nodes[j].c].n)}</span></div>
      <div class="d">${esc(nodePath(K[G.nodes[j].c].node))}</div></div>`).join('')}
    ${depsHtml(k)}`;
  math(el);
}
$('#graphSide').addEventListener('click', e => { const g = e.target.closest('[data-gsel]'); if (g) { G.sel = g.dataset.gsel === '' ? null : +g.dataset.gsel; graphSide(); drawGraph(); } });

/* ---------- blind spots ---------- */
const BV = { years: 10, formalOnly: true, foundResults: true };
const RESULT_KIND = k => !['definition', 'concept', 'example'].includes(K[k].k);
function renderBlind() {
  const el = $('#v-blind');
  const hit = kHit;
  const kindOk = k => !BV.formalOnly || KP_FORMAL(K[k]);
  // coverage per section
  const secs = D.nodes.filter(n => n.in && (n.k === 'section' || (n.k === 'chapter' && !n.kids.length)));
  const secRows = secs.map(n => {
    const ids = K.filter(k => k.in && k.node && (k.node === n.id || k.node.startsWith(n.id + '/')) && kindOk(k.i)).map(k => k.i);
    const h = ids.filter(hit).length;
    return { n, ids, h, miss: ids.filter(c => !hit(c)) };
  }).filter(r => r.ids.length);
  // long unseen: examined before the window, not inside the last N years of the window
  const cut = S.y1 - BV.years + 1;
  const hist = new Map();
  D.questions.forEach(q => {
    if (!typeOk(q) || q.y > S.y1) return;
    kpSet(q, 'both').forEach(c => { const h = hist.get(c) || { n: 0, last: 0 }; h.n++; h.last = Math.max(h.last, q.y); hist.set(c, h); });
  });
  const cold = [...hist].filter(([c, h]) => h.last < cut && h.n >= 2 && K[c].in && kindOk(c)).sort((a, b) => b[1].n - a[1].n);
  // foundations: rarely asked directly, but what rests on them is
  const found = K.filter(k => k.in && kindOk(k.i) && (!BV.foundResults || RESULT_KIND(k.i)) && H.ktn[k.i] + H.kon[k.i] <= 1 && H.kti[k.i] + H.koi[k.i] > 0)
    .sort((a, b) => (H.kti[b.i] + H.koi[b.i]) - (H.kti[a.i] + H.koi[a.i])).slice(0, 40);
  const direct = o => H.kt[o] + H.ko[o] - (S.inh ? H.kti[o] + H.koi[o] : 0);
  // not found in book
  const nit = [];
  F.forEach(q => q.nit.forEach(x => nit.push({ q, x })));
  const byV = {};
  nit.forEach(o => (byV[o.x.v] ||= []).push(o));
  el.innerHTML = `<h2>盲区与冷门</h2>
    <p class="muted">筛选：${S.y0}–${S.y1}，${F.length} 题。<label><input type="checkbox" id="bformal" ${BV.formalOnly ? 'checked' : ''}> 不统计例题型知识点</label>；同一结论在书中多处出现只算一个知识点。</p>
    <h3>各节覆盖率 <span class="small">（被考点或工具命中过的知识点占比；展开可看未命中的）</span></h3>
    <table class="t"><tr><th>节</th><th style="width:90px">命中/总数</th><th style="width:160px">覆盖率</th><th>未命中的知识点</th></tr>
    ${secRows.map(r => `<tr><td><a data-node="${esc(r.n.id)}">${esc(nodeName(r.n))}</a><div class="muted small">${esc(nodePath(r.n.p || ''))}</div></td>
      <td>${r.h}/${r.ids.length}</td><td><div style="display:flex;gap:8px;align-items:center"><div class="hb" style="flex:1"><i style="width:${(100 * r.h / r.ids.length).toFixed(0)}%;background:rgb(var(--topic))"></i></div>${(100 * r.h / r.ids.length).toFixed(0)}%</div></td>
      <td><details><summary class="small muted" style="cursor:pointer">${r.miss.length} 个</summary>${r.miss.map(c => `<span class="chip" data-kp="${c}">${esc(K[c].n)}</span>`).join('')}</details></td></tr>`).join('')}</table>
    <h3>幕后基础 <span class="small">很少直接出现在解答里（≤1 题），但以它为依据的知识点常考；按间接热度排序</span>
      <label class="small" style="font-weight:normal;margin-left:8px"><input type="checkbox" id="bfound" ${BV.foundResults ? 'checked' : ''}> 只看定理 / 公式 / 方法（收起定义与概念）</label></h3>
    ${found.length ? `<table class="t"><tr><th>知识点</th><th>位置</th><th style="width:70px">直接题数</th><th style="width:70px">间接热度</th><th>以它为依据的常考知识点</th></tr>
      ${found.map(k => `<tr><td>${kpLink(k.i)}</td><td class="muted small">${esc(nodePath(k.node))}</td><td>${H.ktn[k.i] + H.kon[k.i]}</td><td>${fmt(H.kti[k.i] + H.koi[k.i])}</td>
        <td class="small">${[...k.u].sort((a, b) => direct(b[0]) - direct(a[0])).slice(0, 3).filter(([o]) => direct(o) > 0).map(([o]) => kpLink(o)).join('、')}</td></tr>`).join('')}</table>` : '<p class="muted">没有</p>'}
    <h3>久未出现 <span class="small">截至 ${S.y1} 年，最近 <select id="byears">${[5, 10, 15, 20].map(y => `<option ${y === BV.years ? 'selected' : ''}>${y}</option>`).join('')}</select> 年没考、但此前至少出现过 2 次（按出现次数排序）</span></h3>
    ${cold.length ? `<table class="t"><tr><th>知识点</th><th>位置</th><th style="width:80px">此前次数</th><th style="width:80px">最近一次</th></tr>
      ${cold.slice(0, 120).map(([c, h]) => `<tr><td>${kpLink(c)}</td><td class="muted small">${esc(nodePath(K[c].node))}</td><td>${h.n}</td><td>${h.last}</td></tr>`).join('')}</table>` : '<p class="muted">没有</p>'}
    <h3>考到了、但书中未找到的知识（${nit.length}）</h3>
    ${['absent', 'related', 'present', ''].filter(v => byV[v]).map(v => `<h3 style="color:var(--ink)">${VERDICT[v]}（${byV[v].length}）</h3>` +
      byV[v].map(({ q, x }) => `<div class="qi" data-q="${q.id}"><div class="h">${qHead(q)}<span>${esc(x.k)}</span></div>
        <div class="d">${esc(x.no || clip(x.se, 160))}${x.rb.length ? ` · <a data-read="${x.rb.join(',')}">最接近的原文</a>` : ''}</div></div>`).join('')).join('')}`;
  math(el);
}
$('#v-blind').addEventListener('change', e => {
  if (e.target.id === 'bformal') { BV.formalOnly = e.target.checked; renderBlind(); }
  if (e.target.id === 'bfound') { const sc = e.currentTarget.scrollTop; BV.foundResults = e.target.checked; renderBlind(); e.currentTarget.scrollTop = sc; }
  if (e.target.id === 'byears') { BV.years = +e.target.value; renderBlind(); }
});

/* ---------- questions ---------- */
// per-viewer study marks (this browser only): ★ marked questions, questions already opened
const store = {
  get(k) { try { return new Set(JSON.parse(localStorage.getItem('math2viz.' + k) || '[]')); } catch (e) { return new Set(); } },
  put(k, set) { try { localStorage.setItem('math2viz.' + k, JSON.stringify([...set])); } catch (e) { /* storage unavailable */ } },
};
const MARK = store.get('marks'), SEEN = store.get('seen');
let SELFTEST = false;
try { SELFTEST = localStorage.getItem('math2viz.selftest') === '1'; } catch (e) { /* default */ }
function toggleMark(id) {
  if (MARK.has(id)) MARK.delete(id); else MARK.add(id);
  store.put('marks', MARK);
  $$(`[data-star="${id}"]`).forEach(b => b.classList.toggle('on', MARK.has(id)));
  qCount();
  if (QV.marked && VIEW === 'questions') renderQuestions();
}
const QV = { q: '', sub: '', sort: 'desc', marked: false, unseen: false, list: [], cur: null, tab: 'steps', nolist: false };
try { QV.tab = localStorage.getItem('math2viz.qTab') || 'steps'; QV.nolist = localStorage.getItem('math2viz.qNoList') === '1'; } catch (e) { /* defaults */ }
function qCount() {
  const n = $('#qn');
  if (n) n.textContent = `${QV.list.length} 题 · 已看 ${QV.list.filter(id => SEEN.has(id)).length} · 标记 ${QV.list.filter(id => MARK.has(id)).length}`;
}
const stemPreview = q => clip(q.stem.replace(STEM_NO, '').split(/\n\s*\(A\)/)[0].replace(/\$\$([\s\S]*?)\$\$/g, (m, f) => `$${f.trim()}$`).replace(/\s*\n\s*/g, ' '), 170);
// the list shows ~2000 preview formulas: render each stem once to an HTML string (KaTeX renderToString, cached) instead of
// letting auto-render walk the whole table on every visit — noticeably slow in the desktop app's WebKitGTK
const STEM_HTML = new Map();
function stemHtml(q) {
  let h = STEM_HTML.get(q.id);
  if (h == null) {
    const t = stemPreview(q);
    h = window.katex ? t.split(/(\$[^$]+\$)/).map(p => p.length > 2 && p[0] === '$' && p.at(-1) === '$'
      ? katex.renderToString(p.slice(1, -1), { throwOnError: false, strict: 'ignore' }) : esc(p)).join('') : texHtml(t);
    STEM_HTML.set(q.id, h);
  }
  return h;
}
const starBtn = (id, label = '') => `<button class="star${MARK.has(id) ? ' on' : ''}" data-star="${id}" title="标记这道题（只保存在本浏览器）">★${label}</button>`;
// questions page: filterable list on the left, the selected question in a centred reading column on the right
function renderQuestions() {
  const el = $('#qList');
  if (!el.dataset.init) {
    el.dataset.init = 1;
    el.innerHTML = `<div class="ctl"><input type="search" id="qq" placeholder="搜索题干、考点、年份、题号…">
      <select id="qsub"><option value="">高数＋线代</option><option value="GS">高数</option><option value="LA">线代</option></select>
      <select id="qsort"><option value="desc">新 → 旧</option><option value="asc">旧 → 新</option></select>
      <label class="small"><input type="checkbox" id="qmark">只看标记</label><label class="small"><input type="checkbox" id="qunseen">只看未看过</label></div>
      <div class="lst"><div id="qn" class="muted small" style="padding:6px 12px"></div><div id="qrows"></div></div>`;
    const upd = () => { QV.q = $('#qq').value.trim(); QV.sub = $('#qsub').value; QV.sort = $('#qsort').value; QV.marked = $('#qmark').checked; QV.unseen = $('#qunseen').checked; renderQuestions(); };
    ['#qq', '#qsub', '#qsort', '#qmark', '#qunseen'].forEach(x => $(x).addEventListener('input', upd));
  }
  const words = QV.q.toLowerCase().split(/\s+/).filter(Boolean);
  const tname = t => (t.kp != null ? K[t.kp].n : D.cards[t.c].ti);
  const qs = F.filter(q => (!QV.sub || q.sub === QV.sub) && (!QV.marked || MARK.has(q.id)) && (!QV.unseen || !SEEN.has(q.id)) &&
      (!words.length || words.every(w => (q.stem + ' ' + q.to.map(tname).join(' ') + ' ' + q.y + ' ' + q.lb).toLowerCase().includes(w))))
    .sort((a, b) => (QV.sort === 'asc' ? a.y - b.y : b.y - a.y) || a.id.localeCompare(b.id, 'en', { numeric: true }));
  QV.list = qs.map(q => q.id);
  qCount();
  // same list as last time (e.g. just switching back to this tab): keep the rendered rows
  const sig = QV.list.join(',');
  if (el.dataset.sig !== sig || !$('#qrows').childElementCount) {
    el.dataset.sig = sig;
    const rows = [];
    let year = null;
    for (const q of qs) {
      if (q.y !== year) {
        year = q.y;
        rows.push(`<div class="qyr">${year} 年 <span class="muted small">${qs.filter(x => x.y === year).length} 题</span></div>`);
      }
      const main = q.to.filter(t => t.p).map(tname).join('；');
      rows.push(() => `<div class="qrow${SEEN.has(q.id) ? ' seen' : ''}${q.id === QV.cur ? ' cur' : ''}" data-qsel="${q.id}">
        <div class="h">${starBtn(q.id)}<b>${esc(q.lb)}</b><span class="badge muted">${TYPE[q.ty]}</span>${SEEN.has(q.id) ? '<span class="seen-dot" title="看过">✓</span>' : ''}</div>
        <div class="stem tex">${stemHtml(q)}</div>${main ? `<div class="s">${esc(main)}</div>` : ''}</div>`);
    }
    const row = r => (typeof r === 'function' ? r() : r);
    // first screenful at once, the rest in slices so switching to this tab never blocks for long
    const FIRST = 40, SLICE = 120, token = QV.token = {};
    const box = $('#qrows');
    box.innerHTML = rows.slice(0, FIRST).map(row).join('') + (qs.length ? '' : '<p class="muted small" style="padding:6px 12px">没有符合条件的题目。</p>');
    let at = FIRST;
    const more = () => {
      if (QV.token !== token || at >= rows.length) return;
      box.insertAdjacentHTML('beforeend', rows.slice(at, at + SLICE).map(row).join(''));
      at += SLICE;
      setTimeout(more, 0);
    };
    setTimeout(more, 0);
  }
  if (QV.cur == null || !qById[QV.cur]) QV.cur = QV.list[0] || null;
  // coming back to the same question with the same list: keep the rendered detail (formulas are slow in WebKitGTK)
  const key = QV.cur + '|' + sig;
  if ($('#qDetail').dataset.key !== key) { $('#qDetail').dataset.key = key; renderQDetail(); }
}
function renderQDetail() {
  const el = $('#qDetail');
  $$('#qrows .qrow.cur').forEach(r => r.classList.remove('cur'));
  const q = qById[QV.cur];
  if (!q) { el.innerHTML = '<p class="muted" style="text-align:center;margin-top:60px">从左侧选择一道题。</p>'; return; }
  const row = $(`#qrows .qrow[data-qsel="${q.id}"]`);
  if (row) { row.classList.add('cur'); row.scrollIntoView({ block: 'nearest' }); }
  markSeen(q.id);
  const x = qSections(q, null);
  const pos = QV.list.indexOf(q.id);
  const tabs = [['steps', '解题', `${q.steps.length} 步`], ['topics', '考点', q.to.length || ''], ['notes', '备注', x.nNotes || '']].filter(t => t[0] !== 'notes' || x.nNotes);
  const tab = tabs.some(t => t[0] === QV.tab) ? QV.tab : 'steps';
  el.innerHTML = `<div class="kpd qbox" data-tab="${tab}">
    <div class="kpd-top"><button class="icon" data-qlist title="收起或展开左侧列表（L）">${QV.nolist ? '☰ 列表' : '⇤ 收起列表'}</button>
      <span class="crumb muted small">${q.sub === 'LA' ? '线性代数' : '高等数学'} · ${TYPE[q.ty]}题</span>
      ${starBtn(q.id, ' 标记')}${x.selftest}
      ${pos >= 0 ? `<span class="kp-nav"><button class="icon" data-qstep="-1" ${pos > 0 ? '' : 'disabled'} title="上一题（↑ / ←）">↑</button><span class="muted small">${pos + 1} / ${QV.list.length}</span><button class="icon" data-qstep="1" ${pos < QV.list.length - 1 ? '' : 'disabled'} title="下一题（↓ / →）">↓</button></span>` : ''}</div>
    <h1 class="kp-title">${q.y} 年 第 ${esc(q.lb)} 题 ${x.badges}</h1>
    ${x.stem}${x.reveal}
    <div class="q-reveal" ${SELFTEST ? 'hidden' : ''}>${x.ans}
      <nav class="kp-tabs">${tabs.map(([t, l, n], i) => `<button data-qtab="${t}" class="${t === tab ? 'cur' : ''}" title="${l}（${i + 1}）">${l}${n !== '' ? ` <span class="n">${n}</span>` : ''}</button>`).join('')}</nav>
      <section data-pane="steps"><div class="steps-h q-steps-h">${x.stepsHead}</div>${x.steps}</section>
      <section data-pane="topics">${x.topics}</section>
      <section data-pane="notes">${x.notes}</section>
    </div></div>`;
  el.scrollTop = 0;
  math(el);
}
function qTab(t) {
  const d = $('#qDetail .qbox');
  if (!d || !d.querySelector(`[data-qtab="${t}"]`)) return;
  QV.tab = t;
  try { localStorage.setItem('math2viz.qTab', t); } catch (e) { /* ignore */ }
  d.dataset.tab = t;
  $$('#qDetail [data-qtab]').forEach(b => b.classList.toggle('cur', b.dataset.qtab === t));
  const nav = $('#qDetail .kp-tabs'), box = $('#qDetail');
  if (nav && nav.getBoundingClientRect().top < box.getBoundingClientRect().top + 1) box.scrollTop = nav.offsetTop - box.offsetTop;
}
function qList(show) {
  QV.nolist = !show;
  try { localStorage.setItem('math2viz.qNoList', QV.nolist ? '1' : '0'); } catch (e) { /* ignore */ }
  $('#v-questions').classList.toggle('nolist', QV.nolist);
  const b = $('#qDetail [data-qlist]'); if (b) b.textContent = QV.nolist ? '☰ 列表' : '⇤ 收起列表';
}
function qStep(d) {
  const i = QV.list.indexOf(QV.cur) + d;
  if (i >= 0 && i < QV.list.length) go('questions', QV.list[i]);
}
$('#qList').addEventListener('click', e => { const r = e.target.closest('[data-qsel]'); if (r) go('questions', r.dataset.qsel); });
$('#qDetail').addEventListener('click', e => {
  const t = e.target.closest('[data-qtab]'); if (t) return qTab(t.dataset.qtab);
  if (e.target.closest('[data-qlist]')) return qList(QV.nolist);
  const st = e.target.closest('[data-qstep]'); if (st) qStep(+st.dataset.qstep);
});
$('#v-questions').classList.toggle('nolist', QV.nolist);
addEventListener('keydown', e => {
  if (VIEW !== 'questions' || e.ctrlKey || e.metaKey || e.altKey || !$('#modal').hidden) return;
  if (e.target.closest && e.target.closest('input, select, textarea, [contenteditable]')) return;
  const k = e.key.toLowerCase();
  const d = e.key === 'ArrowDown' || e.key === 'ArrowRight' || k === 'j' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' || k === 'k' ? -1 : 0;
  if (d) { e.preventDefault(); qStep(d); }
  else if (k === 'l') qList(QV.nolist);
  else if (k === '1' || k === '2' || k === '3') qTab(['steps', 'topics', 'notes'][+k - 1]);
});

/* ---------- filters & routing ---------- */
function setYears(a, b) {
  S.y0 = Math.max(Y_MIN, Math.min(a, b)); S.y1 = Math.min(Y_MAX, Math.max(a, b));
  refresh();
}
function syncFilterUi() {
  $('#y0').value = S.y0; $('#y1').value = S.y1;
  $$('#types input').forEach(i => { i.checked = S.types.has(i.value); });
  $$('#mode button').forEach(b => b.classList.toggle('on', b.dataset.mode === S.mode));
  $('#idf').checked = S.idf;
  $('#merge').checked = S.merge;
  $('#inh').checked = S.inh;
  $('#idfwrap').style.opacity = S.mode === 'tool' ? 1 : 0.5;
  $$('.presets button').forEach(b => {
    const p = b.dataset.preset;
    b.classList.toggle('on', p === 'all' ? S.y0 === Y_MIN && S.y1 === Y_MAX : S.y1 === Y_MAX && S.y0 === Y_MAX - +p + 1);
  });
  $('#qcount').textContent = `${F.length} 题`;
}
['#y0', '#y1'].forEach(s => { $(s).innerHTML = YEARS.map(y => `<option>${y}</option>`).join(''); });
$('#y0').addEventListener('change', () => setYears(+$('#y0').value, S.y1));
$('#y1').addEventListener('change', () => setYears(S.y0, +$('#y1').value));
$('#yprev').addEventListener('click', () => { if (S.y0 > Y_MIN) setYears(S.y0 - 1, S.y1 - 1); });
$('#ynext').addEventListener('click', () => { if (S.y1 < Y_MAX) setYears(S.y0 + 1, S.y1 + 1); });
$$('.presets button').forEach(b => b.addEventListener('click', () => {
  const p = b.dataset.preset;
  setYears(p === 'all' ? Y_MIN : Y_MAX - +p + 1, Y_MAX);
}));
$('#types').addEventListener('change', () => { S.types = new Set($$('#types input').filter(i => i.checked).map(i => i.value)); refresh(); });
$('#mode').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { S.mode = b.dataset.mode; refresh(); } });
$('#idf').addEventListener('change', () => { S.idf = $('#idf').checked; refresh(); });
$('#merge').addEventListener('change', () => { S.merge = $('#merge').checked; refresh(); });
$('#inh').addEventListener('change', () => { S.inh = $('#inh').checked; refresh(); });

let VIEW = null;
function refresh() {
  compute(); saveState(); syncFilterUi(); renderView();
}
function renderView() {
  if (VIEW === 'read') { paintReader(); sidePanel([...R.sel][0]); }
  else if (VIEW === 'overview') { const sc = $('#v-overview').scrollTop; renderOverview(); $('#v-overview').scrollTop = sc; }
  else if (VIEW === 'cards') { renderCardList(); renderCardDetail(); }
  else if (VIEW === 'graph') buildGraph();
  else if (VIEW === 'blind') renderBlind();
  else if (VIEW === 'questions') renderQuestions();
}
function go(view, arg) { location.hash = '#' + view + (arg ? '/' + encodeURIComponent(arg) : ''); }
function route() {
  const [v, ...rest] = location.hash.slice(1).split('/');
  const arg = decodeURIComponent(rest.join('/'));
  VIEW = ['read', 'overview', 'cards', 'graph', 'blind', 'questions'].includes(v) ? v : 'read';
  $$('.view').forEach(el => el.classList.toggle('on', el.id === 'v-' + VIEW));
  $$('#tabs a').forEach(a => a.classList.toggle('on', a.dataset.view === VIEW));
  hideTip();
  if (VIEW === 'read') {
    const bk = BOOKS.includes(arg) ? arg : (R.bk || 'GS1');
    const fresh = R.bk !== bk;
    buildReader(bk);
    if (!pending && fresh) { R.sel = new Set(); paintReader(); sidePanel(); }
  } else if (VIEW === 'cards') {
    const k = K.find(x => x.id === arg);
    CV.cur = k ? k.i : CV.cur;
    renderCardList(); renderCardDetail();
    const cur = $('#cardList .ci.cur'); if (cur) cur.scrollIntoView({ block: 'nearest' });
  } else if (VIEW === 'questions') {
    if (arg && qById[arg]) QV.cur = arg;
    renderQuestions();
  } else if (VIEW === 'graph') {
    if (!$('#graphCtl').innerHTML) initGraphCtl();
    buildGraph();
  } else renderView();
  if (pending) { const p = pending; pending = null; p(); }
}
$('#tabs').addEventListener('click', e => { const a = e.target.closest('a'); if (a) go(a.dataset.view, a.dataset.view === 'read' ? R.bk : (a.dataset.view === 'cards' && CV.cur != null ? K[CV.cur].id : '')); });
addEventListener('hashchange', route);

compute(); syncFilterUi(); route();

// warm up in the background once the page is up: WebKit (the desktop app) keeps formula text invisible until a KaTeX
// font has arrived and only starts fetching a font on first use, so fetch the common faces now; then pre-render the
// question-list formulas in small idle slices so the first visit to that tab is quick
const idle = window.requestIdleCallback ? f => requestIdleCallback(f, { timeout: 1000 }) : f => setTimeout(f, 50);
idle(() => {
  if (document.fonts) ['1em KaTeX_Main', 'bold 1em KaTeX_Main', 'italic 1em KaTeX_Main', 'italic 1em KaTeX_Math', '1em KaTeX_AMS',
    '1em KaTeX_Size1', '1em KaTeX_Size2', '1em KaTeX_Size3', '1em KaTeX_Size4'].forEach(f => document.fonts.load(f).catch(() => {}));
  let i = 0;
  const warm = () => {
    const end = performance.now() + 12;
    while (i < D.questions.length && performance.now() < end) stemHtml(D.questions[i++]);
    if (i < D.questions.length) idle(warm);
  };
  idle(warm);
});
