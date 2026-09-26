// Hand-typeset LaTeX for solution steps (written by Claude): output/mapping/steps_tex/*.txt, blocks of
//   @<question_id> <step n>
//   <the step, wording unchanged, math as $…$ LaTeX>
// Steps not listed there are shown through the automatic converter (output/viz/plain2tex.js).
//   node scripts/steps_tex.cjs todo [--all]    candidate steps (fractions, integrals, limits, matrices, …; --all: every step with any math) -> todo.json
//   node scripts/steps_tex.cjs show N [SIZE]   print batch N of the candidates not written yet (default 60 steps)
//   node scripts/steps_tex.cjs check           parse every written step with KaTeX, list errors / unknown ids
//   node scripts/steps_tex.cjs build           merge -> output/mapping/steps_tex.json {qid: {n: tex}}
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const DIR = path.join(root, 'output/mapping/steps_tex');
globalThis.katex = require(path.join(root, 'output/viz/vendor/katex/katex.min.js'));
const plain2tex = require(path.join(root, 'output/viz/plain2tex.js'));
const FINAL = path.join(root, 'output/mapping/final');

function steps() {
  const out = [];
  for (const f of fs.readdirSync(FINAL).filter(f => f.startsWith('math2-')).sort()) {
    const r = JSON.parse(fs.readFileSync(path.join(FINAL, f), 'utf8'));
    for (const s of r.steps) out.push({ id: `${r.question_id} ${s.n}`, q: r.question_id, n: s.n, d: s.description });
  }
  return out;
}
function written() {
  const map = {};
  for (const f of fs.readdirSync(DIR).filter(f => f.endsWith('.txt')).sort()) {
    const lines = fs.readFileSync(path.join(DIR, f), 'utf8').split('\n');
    let cur = null;
    for (const line of lines) {
      const m = /^@(math2-\S+) (\d+)\s*$/.exec(line);
      if (m) { cur = `${m[1]} ${m[2]}`; map[cur] = { file: f, tex: '' }; continue; }
      if (cur && line.trim()) map[cur].tex += (map[cur].tex ? ' ' : '') + line.trim();
    }
  }
  return map;
}
const cmd = process.argv[2];
if (cmd === 'todo') {
  const todo = [];
  for (const s of steps()) {
    const parts = plain2tex(s.d), math = parts.filter(x => x.t === 'math').map(x => x.v).join(' ');
    if (process.argv.includes('--all') ? parts.some(x => x.t === 'math') :
        /[A-Za-z0-9)\]}]\s*\/\s*[A-Za-z0-9(\\]/.test(math) || /\\lim|\\sum|\\prod|\\int/.test(math) ||
        /\[\[|\\operatorname\{diag\}|\]\s*,\s*\[/.test(math) || /(?<![A-Za-z\\])[A-Za-z]\d{2,}/.test(math) || parts.some(x => x.failed))
      todo.push(s.id);
  }
  fs.writeFileSync(path.join(DIR, 'todo.json'), JSON.stringify(todo));
  console.log(todo.length, 'candidate steps');
} else if (cmd === 'show') {
  const todo = JSON.parse(fs.readFileSync(path.join(DIR, 'todo.json'), 'utf8')), done = written();
  const all = Object.fromEntries(steps().map(s => [s.id, s.d]));
  const left = todo.filter(id => !done[id]);
  const size = +(process.argv[4] || 60), n = +(process.argv[3] || 0);
  // whole questions only: extend the batch to the end of its last question
  let batch = left.slice(n * size, (n + 1) * size);
  console.log(`# ${left.length} left; batch ${n}: ${batch.length} steps`);
  for (const id of batch) console.log(`@${id}\n${all[id]}`);
} else if (cmd === 'check') {
  const done = written(), all = Object.fromEntries(steps().map(s => [s.id, s.d]));
  let bad = 0;
  for (const [id, { file, tex }] of Object.entries(done)) {
    if (!(id in all)) { console.log('unknown step', id, file); bad++; continue; }
    const dollars = (tex.match(/(?<!\\)\$/g) || []).length;
    if (dollars % 2) { console.log('✗', id, 'odd number of $'); bad++; continue; }
    for (const m of tex.matchAll(/(?<!\\)\$(.+?)(?<!\\)\$/g)) {
      try { katex.renderToString(m[1], { throwOnError: true, strict: 'ignore' }); } catch (e) { console.log('✗', id, '|', m[1], '|', e.message.slice(0, 90)); bad++; }
    }
    const strip = t => t.replace(/\$[^$]*\$/g, '').replace(/[\s，。；：、]/g, '');
    const cjkA = strip(all[id]).replace(/[^一-鿿]/g, ''), cjkB = strip(tex).replace(/[^一-鿿]/g, '');
    if (cjkA !== cjkB && Math.abs(cjkA.length - cjkB.length) > 2) console.log('  ≠ wording changed?', id, cjkA.length, cjkB.length);
  }
  const todo = JSON.parse(fs.readFileSync(path.join(DIR, 'todo.json'), 'utf8'));
  console.log(`${Object.keys(done).length} written (${todo.filter(id => done[id]).length}/${todo.length} candidates), ${bad} problems`);
} else if (cmd === 'build') {
  const out = {};
  for (const [id, { tex }] of Object.entries(written())) {
    const [q, n] = id.split(' ');
    (out[q] ||= {})[n] = tex;
  }
  fs.writeFileSync(path.join(root, 'output/mapping/steps_tex.json'), JSON.stringify(out, null, 0));
  console.log(Object.values(out).reduce((a, x) => a + Object.keys(x).length, 0), 'steps in output/mapping/steps_tex.json');
} else console.log(fs.readFileSync(__filename, 'utf8').split('\n').slice(0, 8).join('\n'));
