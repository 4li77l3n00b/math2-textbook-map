#!/usr/bin/env python3
"""Solving-method layer: which question-type methods (output/methods/taxonomy.txt) each exam question uses.

  python3 scripts/methods.py probe                one tiny request: is the model reachable
  python3 scripts/methods.py pilot [N]            label a stratified sample of N questions (default 20)
  python3 scripts/methods.py run [--workers K]    label all questions into output/methods/raw/ (skips done ones)
  python3 scripts/methods.py redo [ID ...]        relabel the given questions, or by default the gaps: no method,
                                                  a new-method suggestion, or not labelled yet
  python3 scripts/methods.py report [raw|pilot]   summarize the labels

The taxonomy (written by Claude) goes in a developer message of its own so the relay caches it; the question
(stem, answer, reference solution, numbered steps) is the user message. Output is strict JSON per question.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections import Counter
import json
import random
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import jsonsave  # noqa: E402

OUT = ROOT / 'output/methods'
MODEL = 'gpt-6.1-sol'    # user decision 2026-10-29 (the mapping used gpt-6-astra)
EFFORT = 'medium'
WORKERS = 2              # Codex desktop may share the relay; the hard cap across everything is 4
CACHE_KEY = 'math2-methods-v3'  # v3: + 11 methods from the full run's gaps (der-basic, int-basic, ode-exact, ...)


def taxonomy():
    groups, items = [], []
    for raw in (OUT / 'taxonomy.txt').read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('# '):
            continue
        if line.startswith('## '):
            groups.append(line[3:])
            continue
        mid, name, signal = [s.strip() for s in line.split(' | ')]
        items.append({'id': mid, 'name': name, 'signal': signal, 'group': groups[-1]})
    return items


def questions():
    s = (ROOT / 'output/viz/data.js').read_text(encoding='utf-8')
    d = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    return d['questions']


PREFIX = '''你在为考研数学二真题标注"解题方法"。方法是题型级的：看到题目的某种特征，就该想到的一套做法。
下面是方法体系（id | 方法名 | 识别信号），按章节分组：

{table}

对给你的每道题：
1. methods：列出这道题的解法实际用到的方法（只从上表选 id）。
   - steps：用到该方法的步骤号（来自"解题步骤"，可多个）。
   - role：core = 解题的关键方法（拿掉它就做不出来，一般 1–2 个）；aux = 过程中顺带用到的常规方法。
   - cue：题干中让人想到这个方法的具体特征（引用或概括题干里的式子、条件、问法；不要照抄"识别信号"）。
   - why：一句话说明这一步怎样用到该方法。
   只标真正用到的；纯计算（如四则运算、代入数值）不算方法。
2. new_methods：如果某个关键做法在表中没有合适的 id，在这里提出（name 题型级命名，signal 识别信号，
   steps 步骤号，why 说明）。表中已有合适的就不要提。没有就给空数组。
3. comment：对方法体系本身的意见（某个方法太粗或太细、边界不清、名字不准），没有就给空字符串。
用中文回答。'''

SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['methods', 'new_methods', 'comment'], 'properties': {
    'methods': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                'required': ['id', 'steps', 'role', 'cue', 'why'], 'properties': {
                    'id': {'type': 'string'}, 'steps': {'type': 'array', 'items': {'type': 'integer'}},
                    'role': {'type': 'string', 'enum': ['core', 'aux']}, 'cue': {'type': 'string'}, 'why': {'type': 'string'}}}},
    'new_methods': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                    'required': ['name', 'signal', 'steps', 'why'], 'properties': {
                        'name': {'type': 'string'}, 'signal': {'type': 'string'},
                        'steps': {'type': 'array', 'items': {'type': 'integer'}}, 'why': {'type': 'string'}}}},
    'comment': {'type': 'string'}}}


def prefix(items):
    table, g = [], None
    for it in items:
        if it['group'] != g:
            g = it['group']
            table.append(f'【{g}】')
        table.append(f"{it['id']} | {it['name']} | {it['signal']}")
    return PREFIX.format(table='\n'.join(table))


def prompt(q):
    steps = '\n'.join(f'{n}. {tex or desc}' for n, desc, tex in q['steps'])
    return f'''## 题目 {q['id']}（{q['y']} 年 {q['lb']}）
{q['stem']}

## 答案
{q.get('ans') or ''}

## 参考解析
{q.get('sol') or ''}

## 解题步骤
{steps}'''


def _md():
    import map_direct  # reads the API key at import: only the API commands need it
    return map_direct


_workers, _wl = {}, threading.Lock()


def call(pre, user):
    md = _md()
    with _wl:
        w = _workers.setdefault(threading.get_ident(), len(_workers)) % WORKERS
    body = {'model': MODEL, 'store': False, 'reasoning': {'effort': EFFORT}, 'prompt_cache_key': f'{CACHE_KEY}-w{w}',
            'text': {'format': {'type': 'json_schema', 'name': 'methods', 'schema': SCHEMA, 'strict': True}},
            'input': [md.msg('developer', pre), md.msg('user', user)]}
    items, usage = md.post(body)
    text = ''.join(c.get('text', '') for i in items if i.get('type') == 'message'
                   for c in i.get('content', []) if c.get('type') == 'output_text')
    return json.loads(text), usage


def sample(qs, n):
    """Spread over subject (GS / LA roughly 2:1), question type and decade; fixed seed."""
    rnd = random.Random(20261029)
    by = {}
    for q in qs:
        by.setdefault((q['sub'], q['ty'], q['y'] // 10), []).append(q)
    cells = sorted(by)
    rnd.shuffle(cells)
    gs = [c for c in cells if c[0] == 'GS']
    la = [c for c in cells if c[0] == 'LA']
    order = []
    while gs or la:  # two GS cells for each LA cell
        for src in (gs, gs, la):
            if src:
                order.append(src.pop())
    picked = []
    while len(picked) < n:
        for c in order:
            pool = [q for q in by[c] if q not in picked]
            if pool and len(picked) < n:
                picked.append(rnd.choice(pool))
    return picked


def cmd_probe():
    md = _md()
    _lock = md.single_api_process()  # noqa: F841
    items, usage = md.post({'model': MODEL, 'store': False, 'reasoning': {'effort': 'low'},
                            'input': [md.msg('user', '只回答 OK')]})
    text = ''.join(c.get('text', '') for i in items if i.get('type') == 'message' for c in i.get('content', []))
    print(MODEL, '->', text.strip(), usage)


def label(qs, out_dir, redo=False):
    """Label the questions not yet in out_dir (all of qs with redo); failures are logged and left for a rerun."""
    md = _md()
    _lock = md.single_api_process()  # noqa: F841 - never next to another API process
    items = taxonomy()
    ids = {it['id'] for it in items}
    pre = prefix(items)
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [q for q in qs if redo or not (out_dir / f"{q['id']}.json").exists()]
    md.log(f'{len(todo)}/{len(qs)} questions to label with {MODEL}, {WORKERS} workers')
    done = [0]

    def one(q):
        try:
            res, usage = call(pre, prompt(q))
        except Exception as e:  # noqa: BLE001 - keep the others; a rerun picks it up
            md.log(f"{q['id']} failed: {e}")
            return
        bad = [m['id'] for m in res['methods'] if m['id'] not in ids]
        jsonsave(out_dir / f"{q['id']}.json", {'id': q['id'], 'model': MODEL, 'cache_key': CACHE_KEY, 'usage': usage,
                                                'unknown_ids': bad, 'result': res})
        done[0] += 1
        md.log(f"[{done[0]}/{len(todo)}] {q['id']}: {len(res['methods'])} methods, {len(res['new_methods'])} new"
               f"{', UNKNOWN ' + ','.join(bad) if bad else ''}, in {usage.get('input_tokens')} "
               f"(cached {usage.get('input_tokens_details', {}).get('cached_tokens')}) out {usage.get('output_tokens')}")
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))


def cmd_pilot(n):
    picked = sample(questions(), n)
    (OUT / 'pilot').mkdir(parents=True, exist_ok=True)
    jsonsave(OUT / 'pilot' / 'sample.json', [q['id'] for q in picked])
    label(picked, OUT / 'pilot')


def cmd_run():
    label(questions(), OUT / 'raw')


def gaps():
    """Questions the current labels leave open: not labelled, no method, or a suggested new method."""
    out = []
    for q in questions():
        f = OUT / 'raw' / f"{q['id']}.json"
        if not f.exists():
            out.append(q['id'])
            continue
        res = json.loads(f.read_text(encoding='utf-8'))['result']
        if not res['methods'] or res['new_methods']:
            out.append(q['id'])
    return out


def cmd_redo(ids):
    ids = set(ids or gaps())
    label([q for q in questions() if q['id'] in ids], OUT / 'raw', redo=True)


def cards():
    """output/methods/cards.txt (written by Claude): per method id, standard steps and pitfalls."""
    out, cur = {}, None
    for raw in (OUT / 'cards.txt').read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('# '):
            continue
        if line.startswith('@ '):
            cur = out.setdefault(line[2:].strip(), {'st': [], 'pf': []})
        elif line.startswith('!'):
            cur['pf'].append(line[1:].strip())
        else:
            cur['st'].append(line.split('. ', 1)[1] if line[0].isdigit() else line)
    return out


def export(qids):
    """For build_viz.py: the method list (with its card) and, per question id,
    [[method index, 1 core | 0 aux, steps, cue, why]]."""
    items = taxonomy()
    idx = {it['id']: i for i, it in enumerate(items)}
    cd = cards()
    methods = [{'id': it['id'], 'n': it['name'], 'g': it['group'], 's': it['signal'], **cd.get(it['id'], {})}
               for it in items]
    per_q = {}
    for qid in qids:
        f = OUT / 'raw' / f'{qid}.json'
        if not f.exists():
            continue
        res = json.loads(f.read_text(encoding='utf-8'))['result']
        per_q[qid] = [[idx[m['id']], int(m['role'] == 'core'), m['steps'], m['cue'], m['why']]
                      for m in sorted(res['methods'], key=lambda m: m['role'] != 'core') if m['id'] in idx]
    return methods, per_q


def cmd_report(sub='raw'):
    items = {it['id']: it for it in taxonomy()}
    files = sorted((OUT / sub).glob('math2-*.json'))
    tin = tout = tcached = 0
    used, new = Counter(), []
    for f in files:
        d = json.loads(f.read_text(encoding='utf-8'))
        u = d['usage']
        tin += u.get('input_tokens', 0)
        tout += u.get('output_tokens', 0)
        tcached += u.get('input_tokens_details', {}).get('cached_tokens', 0)
        for m in d['result']['methods']:
            used[m['id']] += 1
        new += [(d['id'], m['name']) for m in d['result']['new_methods']]
    print(f'{len(files)} questions; tokens in {tin} (cached {tcached}) out {tout}; '
          f'per question in {tin // max(len(files), 1)} out {tout // max(len(files), 1)}')
    print(f'{len(used)} of {len(items)} methods used:', ', '.join(f'{k}×{v}' for k, v in used.most_common()))
    print('new:', new)


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--workers' in args:  # at most 4: the relay's limit for everything running together
        i = args.index('--workers')
        WORKERS = min(int(args[i + 1]), 4)
        del args[i:i + 2]
    cmd, *rest = args or ['report']
    {'probe': cmd_probe, 'pilot': lambda: cmd_pilot(int(rest[0]) if rest else 20), 'run': cmd_run,
     'redo': lambda: cmd_redo(rest), 'report': lambda: cmd_report(*rest)}[cmd]()
