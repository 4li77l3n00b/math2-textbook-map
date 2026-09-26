// Run the step-text converter (output/viz/plain2tex.js) over every step and note text in the mapping, with KaTeX
// loaded: counts math spans, spans KaTeX rejected (they fall back to plain text), and prints samples.
//   node scripts/check_plain2tex.cjs [N_SAMPLES] [--failed]
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
globalThis.katex = require(path.join(root, 'output/viz/vendor/katex/katex.min.js'));
const plain2tex = require(path.join(root, 'output/viz/plain2tex.js'));
const dir = path.join(root, 'output/mapping/final');
const texts = [];
for (const f of fs.readdirSync(dir).filter(f => f.startsWith('math2-'))) {
  const r = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
  r.steps.forEach(s => texts.push([r.question_id + ' ' + s.n, s.description]));
  r.topics.forEach(t => texts.push([r.question_id + ' reason', t.reason]));
  if (r.notes) texts.push([r.question_id + ' notes', r.notes]);
  if (r.topic_note) texts.push([r.question_id + ' tn', r.topic_note]);
}
let spans = 0, failed = 0, words = 0;
const bad = [];
for (const [id, t] of texts) {
  for (const p of plain2tex(t)) {
    if (p.t === 'math') spans++;
    else if (p.failed) { failed++; bad.push([id, p.v]); }
  }
}
console.log(`${texts.length} texts, ${spans} math spans, ${failed} rejected by KaTeX (kept as text)`);
const n = +(process.argv[2] || 12);
if (process.argv.includes('--failed')) bad.slice(0, n).forEach(([id, v]) => console.log('  ✗', id, '|', v));
else {
  const pick = texts.filter((_, i) => i % Math.max(1, Math.floor(texts.length / n)) === 0).slice(0, n);
  for (const [id, t] of pick) {
    console.log('\n' + id + '\n  ' + t.slice(0, 200));
    console.log('  → ' + plain2tex(t).map(p => p.t === 'math' ? `$${p.v}$` : p.v).join('').slice(0, 260));
  }
}
