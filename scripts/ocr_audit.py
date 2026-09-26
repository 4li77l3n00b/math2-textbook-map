"""Stratified OCR error-rate audit of textbook blocks, judged by Astra (via `codex exec`) against page crops.

  python3 scripts/ocr_audit.py sample   # draw the stratified sample, crop images, write batches
  python3 scripts/ocr_audit.py run      # judge batches with Astra (skips batches already done)
  python3 scripts/ocr_audit.py report   # aggregate into rates with Wilson intervals

The OCR text is never modified; Astra's corrected text is stored beside it for later use.
"""
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import random
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import save, jsonsave  # noqa: E402
from textbook_crop import crop  # noqa: E402

DB = ROOT / 'output/textbook/textbook_index.sqlite'
OUT = ROOT / 'output/textbook/ocr_audit'
MODEL = 'gpt-6-astra'
SEED = 20260923
ZONES = ('body', 'practice')
# per book: stratum -> (labels, sample size)
STRATA = {
    'text': (('text',), 16),
    'display_formula': (('display_formula',), 12),
    'title_inline': (('paragraph_title', 'inline_formula'), 4),
}
BATCH = 8
WORKERS = 3

SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['blocks'],
    'properties': {'blocks': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False,
        'required': ['uid', 'verdict', 'errors', 'corrected_text', 'confidence', 'note'],
        'properties': {
            'uid': {'type': 'string'},
            'verdict': {'type': 'string', 'enum': ['exact', 'equivalent', 'cosmetic_error', 'meaning_error',
                                                   'crop_problem']},
            'errors': {'type': 'array', 'items': {
                'type': 'object', 'additionalProperties': False,
                'required': ['type', 'severity', 'ocr', 'correct'],
                'properties': {
                    'type': {'type': 'string', 'enum': ['chinese_char', 'latin_or_digit', 'math_symbol',
                                                        'formula_structure', 'missing_content', 'extra_content',
                                                        'punctuation', 'layout_merge', 'handwritten_annotation', 'other']},
                    'severity': {'type': 'string', 'enum': ['meaning', 'cosmetic']},
                    'ocr': {'type': 'string'}, 'correct': {'type': 'string'}}}},
            'corrected_text': {'type': 'string'},
            'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']},
            'note': {'type': 'string'}}}}},
}

PROMPT = '''你在核对一本扫描教材的 OCR 结果。附带的 {n} 张图片依次对应下面 {n} 个块（顺序一致）；每张图是按 OCR 版面框从原书页面裁出的区域（四周留有少量空白，可能带进相邻行的边缘，那不属于本块）。

对每个块，逐字、逐符号比对图片与 OCR 文本，给出：
- verdict：
  - exact：完全一致；
  - equivalent：只有 LaTeX 写法差异，渲染后与原书相同（如 \\left/\\right、多余花括号、空格、\\mathrm{{d}} 与 d、全半角标点的等价写法）——不算错误；
  - cosmetic_error：有错但不改变数学或文字含义（如标点错、个别无关紧要的字形、排版标记）；
  - meaning_error：至少一处会改变含义或让读者误解的错误（错字改变词义、符号/上下标/指数/分式/积分限/矩阵元素错误、漏行、多出内容、把旁注混入正文等）；
  - crop_problem：图片与该块明显不对应或无法辨认，此时说明原因。
- errors：逐条列出错误（equivalent 的写法差异不要列）。type 取最贴切的一类；severity 为 meaning 或 cosmetic；ocr 为 OCR 中的错误片段，correct 为原书应为的内容（缺失内容时 ocr 为空串）。
- corrected_text：按原书内容修正后的完整块文本，保持 OCR 的 Markdown/LaTeX 风格（$...$、$$...$$）；exact/equivalent 时原样返回 OCR 文本。
- confidence：你对判断的把握；图片模糊或难辨时如实给 medium/low。
- note：简短说明（可空）。

注意：扫描书页上可能有读者的手写批注或划线（非印刷体，常为彩色笔迹）。它们不属于原书内容：若被 OCR 识别进文本，按 handwritten_annotation 记错（混入正文或替换了印刷内容为 meaning，仅多出孤立无关字符为 cosmetic），corrected_text 中去掉；若只是图上有笔迹而 OCR 未受影响，则不算错误，可在 note 提及。

要求：只根据图片判断，不要凭数学常识“猜”原书应该怎么写；看不清就降低 confidence 并在 note 说明。不要运行任何命令或读写文件，直接输出 JSON。

{blocks}
'''


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def population(con):
    rows = con.execute(f'''select uid, book, label, text from blocks
                           where zone in {ZONES} and trim(text) != '' order by uid''').fetchall()
    pop = defaultdict(list)
    for uid, book, label, text in rows:
        for name, (labels, _) in STRATA.items():
            if label in labels:
                pop[(book, name)].append((uid, text))
    return pop


def cmd_sample():
    con = sqlite3.connect(DB)
    pop = population(con)
    rng = random.Random(SEED)
    sample = []
    for (book, name), items in sorted(pop.items()):
        k = STRATA[name][1]
        for uid, text in rng.sample(items, min(k, len(items))):
            sample.append({'uid': uid, 'book': book, 'stratum': name, 'text': text})
    rng.shuffle(sample)
    crop([s['uid'] for s in sample], OUT / 'crops', pad=8)
    for s in sample:
        s['image'] = f'crops/{s["uid"]}.png'
    batches = [sample[i:i + BATCH] for i in range(0, len(sample), BATCH)]
    jsonsave(OUT / 'sample.json', {
        'seed': SEED, 'zones': ZONES, 'strata': {k: {'labels': v[0], 'per_book': v[1]} for k, v in STRATA.items()},
        'population': {f'{b}/{n}': len(v) for (b, n), v in sorted(pop.items())},
        'batches': [[s['uid'] for s in b] for b in batches], 'blocks': sample})
    jsonsave(OUT / 'schema.json', SCHEMA)
    print(len(sample), 'blocks in', len(batches), 'batches')


def run_batch(i, uids, by_uid):
    out = OUT / 'results' / f'batch-{i:02d}.json'
    if out.exists():
        return i, 'skip'
    blocks = '\n\n'.join(f'### 块 {j + 1}：uid = {u}\nOCR 文本：\n```\n{by_uid[u]["text"]}\n```'
                         for j, u in enumerate(uids))
    prompt = PROMPT.format(n=len(uids), blocks=blocks)
    raw = OUT / 'results' / f'batch-{i:02d}.raw.json'
    cmd = ['codex', 'exec', '-m', MODEL, '-s', 'read-only', '--ephemeral', '--skip-git-repo-check',
           '-C', str(OUT), '--output-schema', str(OUT / 'schema.json'), '-o', str(raw)]
    for u in uids:
        cmd += ['-i', str(OUT / by_uid[u]['image'])]
    cmd += ['--', prompt]
    started = datetime.now(timezone.utc).isoformat()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL)
    if p.returncode or not raw.exists():
        save(OUT / 'results' / f'batch-{i:02d}.err.txt', p.stdout[-4000:] + '\n---\n' + p.stderr[-4000:])
        return i, f'failed rc={p.returncode}'
    data = json.loads(raw.read_text(encoding='utf-8'))
    got = [b['uid'] for b in data['blocks']]
    if got != uids:
        save(OUT / 'results' / f'batch-{i:02d}.err.txt', f'uid mismatch: {got} vs {uids}')
        return i, 'uid mismatch'
    jsonsave(out, {'model': MODEL, 'started': started, 'finished': datetime.now(timezone.utc).isoformat(),
                   'uids': uids, 'blocks': data['blocks']})
    raw.unlink()
    return i, 'ok'


def cmd_run(only=None):
    s = json.loads((OUT / 'sample.json').read_text(encoding='utf-8'))
    by_uid = {b['uid']: b for b in s['blocks']}
    (OUT / 'results').mkdir(parents=True, exist_ok=True)
    jobs = [(i, u) for i, u in enumerate(s['batches']) if only is None or i in only]
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, status in ex.map(lambda a: run_batch(*a, by_uid), jobs):
            print(f'batch {i:02d}: {status}', flush=True)


def cmd_report():
    s = json.loads((OUT / 'sample.json').read_text(encoding='utf-8'))
    meta = {b['uid']: b for b in s['blocks']}
    res = {}
    for f in sorted((OUT / 'results').glob('batch-[0-9][0-9].json')):
        for b in json.loads(f.read_text(encoding='utf-8'))['blocks']:
            res[b['uid']] = b
    judged = [u for u in meta if u in res and res[u]['verdict'] != 'crop_problem']
    lines = [f'# 教材 OCR 错误率抽样报告\n',
             f'模型：{MODEL}（codex exec，只读、无工具）。抽样：正文与练习分区，按 书 × 块类型 分层，随机种子 {s["seed"]}。'
             f'共抽 {len(meta)} 块，已判定 {len(res)} 块，其中裁图问题 {len(res) - len(judged)} 块不计入比率。\n',
             '判定口径：`equivalent`（仅 LaTeX 写法不同、渲染一致）不算错误；`cosmetic_error` 不影响含义；'
             '`meaning_error` 至少一处改变数学或文字含义。\n']

    def rate_rows(keyf, title):
        lines.append(f'\n## {title}\n')
        lines.append('| 分组 | 判定数 | 完全一致 | 写法等价 | 仅外观错误 | 含义错误 | 含义错误率（95% CI） |\n|---|---|---|---|---|---|---|')
        groups = defaultdict(list)
        for u in judged:
            groups[keyf(meta[u])].append(res[u]['verdict'])
        for g, vs in sorted(groups.items()):
            c = Counter(vs)
            p, lo, hi = wilson(c['meaning_error'], len(vs))
            lines.append(f'| {g} | {len(vs)} | {c["exact"]} | {c["equivalent"]} | {c["cosmetic_error"]} | '
                         f'{c["meaning_error"]} | {p:.0%}（{lo:.0%}–{hi:.0%}） |')

    rate_rows(lambda m: m['stratum'], '按块类型')
    rate_rows(lambda m: m['book'], '按书')
    rate_rows(lambda m: f'{m["book"]} / {m["stratum"]}', '按层')

    # population-weighted estimate over the sampled strata
    pop = s['population']
    tot = sum(pop.values())
    est = 0.0
    for key_, n in pop.items():
        book, name = key_.split('/')
        vs = [res[u]['verdict'] for u in judged if meta[u]['book'] == book and meta[u]['stratum'] == name]
        if vs:
            est += n / tot * sum(v == 'meaning_error' for v in vs) / len(vs)
    lines.append(f'\n按各层总体块数加权的含义错误率估计：**{est:.1%}**（总体 {tot} 块；分层样本小，仅作量级参考）。\n')

    et = Counter((e['type'], e['severity']) for u in judged for e in res[u]['errors'])
    lines.append('\n## 错误类型\n\n| 类型 | 含义 | 外观 |\n|---|---|---|')
    for t in sorted({t for t, _ in et}):
        lines.append(f'| {t} | {et[(t, "meaning")]} | {et[(t, "cosmetic")]} |')
    conf = Counter(res[u]['confidence'] for u in res)
    lines.append(f'\n模型自评把握：' + '，'.join(f'{k} {v}' for k, v in conf.items()) + '\n')

    lines.append('\n## 含义错误明细\n')
    for u in sorted(judged):
        r = res[u]
        if r['verdict'] != 'meaning_error':
            continue
        lines.append(f'### `{u}`（{meta[u]["stratum"]}，把握 {r["confidence"]}）\n')
        lines.append(f'![](crops/{u}.png)\n')
        for e in r['errors']:
            lines.append(f'- [{e["type"]}/{e["severity"]}] `{e["ocr"]}` → `{e["correct"]}`')
        if r['note']:
            lines.append(f'- 说明：{r["note"]}')
        lines.append('')
    adj_path = OUT / 'adjudication.json'
    if adj_path.exists():
        adj = json.loads(adj_path.read_text(encoding='utf-8'))
        cats = Counter(v['category'] for v in adj['blocks'].values())
        n = len(judged)
        lines.append(f'\n## 复核后（{adj["reviewer"]}）\n')
        lines.append('astra 判为含义错误的块逐一复核后的归类：\n')
        lines.append('| 归类 | 块数 | 占样本（95% CI） | 说明 |\n|---|---|---|---|')
        for c, desc in adj['categories'].items():
            p, lo, hi = wilson(cats[c], n)
            lines.append(f'| {c} | {cats[c]} | {p:.1%}（{lo:.1%}–{hi:.1%}） | {desc} |')
        lines.append('')
        for u, v in sorted(adj['blocks'].items()):
            lines.append(f'- `{u}`：**{v["category"]}**，{v["note"]}')
        if adj.get('calibration'):
            lines.append('\n独立抽查（先于查看 astra 结论判读）：' + '；'.join(f'`{k}` {v}' for k, v in adj['calibration'].items()))
    probs = [u for u in res if res[u]['verdict'] == 'crop_problem']
    if probs:
        lines.append('\n## 裁图问题\n')
        lines += [f'- `{u}`：{res[u]["note"]}' for u in probs]
    missing = [u for u in meta if u not in res]
    if missing:
        lines.append(f'\n未完成判定：{len(missing)} 块。')
    save(OUT / '抽样报告.md', '\n'.join(lines) + '\n')
    print('\n'.join(lines[:40]))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'sample':
        cmd_sample()
    elif cmd == 'run':
        cmd_run({int(x) for x in sys.argv[2:]} or None)
    elif cmd == 'report':
        cmd_report()
    else:
        print(__doc__)
