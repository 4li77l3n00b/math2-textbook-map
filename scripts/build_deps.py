"""Derivation sources (plan B): which knowledge points a knowledge point is built on — the concepts its statement
uses and the results its proof / derivation uses. Edges point from a knowledge point to what it depends on.

  python3 scripts/build_deps.py explicit     references written in the book ("由定理 3.2.4", \\autoref{thm:…}),
                                             no API -> output/knowledge/deps/explicit.json
  python3 scripts/build_deps.py select       batches + token estimate (no API)
  python3 scripts/build_deps.py run [N]      astra reads each knowledge point (statement + proof / derivation text)
                                             against the catalogue of its subject -> deps/astra.json; N = only the
                                             first N batches (pilot). Resumes; global single-process lock (≤4).
  python3 scripts/build_deps.py post         validate + union -> output/knowledge/deps.json

Cache: every request of a subject starts with the same developer message (instructions + catalogue, ≈ 15k
tokens; the relay caches whole messages only, so it must not be glued to the batch), and each worker
thread keeps its own prompt_cache_key per subject, so after a worker's first batch the prefix is served from cache.
"""
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import jsonsave  # noqa: E402
import map_questions as mq  # noqa: E402
import map_direct as md  # noqa: E402
from build_kps import OUT as KOUT, clip, call, WORKERS  # noqa: E402

OUT = KOUT / 'deps'
LALU_SRC = ROOT / 'source/LALU'
LALU_ENV = {'definition': 'def', 'example': 'ex', 'lemma': 'lem', 'theorem': 'thm', 'corollary': 'cor', 'axiom': 'axm'}
MAX_DEPS = 8
BATCH = 16
TEXT_CHARS = 900       # canonical card span (statement + proof)
DERIV_CHARS = 450      # one derivation member (the example / proof that derives it)
TYPES = ['concept', 'proof']


def subject(kp_id):
    return 'LA' if kp_id.split('/')[0] in ('LA', 'LALU') else 'GS'


class Book:
    """Blocks, cards and knowledge points with the lookups both steps need."""

    def __init__(self):
        self.rows, self.order = mq.load_blocks()
        self.cards = mq.load_cards()
        kp = json.loads((KOUT / 'knowledge_points.json').read_text(encoding='utf-8'))
        self.kps = {k['id']: k for k in kp['kps']}
        self.home = {}  # card -> knowledge point: canonical first, then first membership
        for k in self.kps.values():
            for m in k['members']:
                self.home.setdefault(m['card'], k['id'])
        self.home.update({k['canonical']: k['id'] for k in self.kps.values()})
        self.toc = {n['id']: n for n in json.loads((ROOT / 'output/textbook/toc.json').read_text(encoding='utf-8'))['nodes']}
        spans = []
        for cid, c in self.cards.items():
            s, e = self.order.get(c['start_uid']), self.order.get(c['end_uid'])
            if s is not None and e is not None and cid in self.home:
                spans.append((s, e, cid))
        self.cover = defaultdict(list)  # block index -> cards whose span contains it (smallest first)
        for s, e, cid in spans:
            for i in range(s, e + 1):
                self.cover[i].append((e - s, cid))
        for v in self.cover.values():
            v.sort()

    def pos(self, kp_id):
        return self.order.get(self.cards[self.kps[kp_id]['canonical']]['start_uid'], 0)

    def text(self, card_id, n):
        c = self.cards[card_id]
        s, e = self.order[c['start_uid']], self.order[c['end_uid']]
        return clip(' '.join(r[2] for r in self.rows[s:e + 1]), n)

    def num(self, kp_id):
        unit = self.cards[self.kps[kp_id]['canonical']]['unit']
        return (self.toc.get(unit) or {}).get('num') or unit


# ---------- explicit references ----------

GS_REF = re.compile(r'(定理|命题|定义|推论|性质|引理|例)\s*(\d+(?:\.\d+){2})')
LA_REF = re.compile(r'(定理|定义|推论|性质|引理)\s*(\d+\.\d+)(?![\d.])')  # 王宽程: 定理 2.2 (examples restart per section)
GS_EQ = re.compile(r'[(（]\s*(\d+\.\d+\.\d+)\s*[)）]')
TEX_REF = re.compile(r'\\(?:auto|c|C|eq|name)?ref\*?\{([^}]+)\}')


def lalu_labels():
    """author label (def:群, thm:HC, an equation \\label) -> block uid, from each block's source lines"""
    lines = {}
    out = {}
    for line in (ROOT / 'output/textbook/lalu/blocks.jsonl').open(encoding='utf-8'):
        b = json.loads(line)
        m = re.fullmatch(r'(.+):(\d+)-(\d+)', b.get('src') or '')
        if not m:
            continue
        f = m[1]
        if f not in lines:
            lines[f] = (LALU_SRC / f).read_text(encoding='utf-8').split('\n')
        src = '\n'.join(lines[f][int(m[2]) - 1:int(m[3])])
        for e in re.finditer(r'\\begin\{(\w+)\}\{[^}]*\}\{([^}]+)\}', src):
            if e[1] in LALU_ENV:
                out.setdefault(f'{LALU_ENV[e[1]]}:{e[2].strip()}', b['uid'])
        for e in re.finditer(r'\\label\{([^}]+)\}', src):
            out.setdefault(e[1].strip(), b['uid'])
    return out


def cmd_explicit(args):
    bk = Book()
    by_label = {}  # OCR books: (book, card label) e.g. (GS1, 定理3.2.4), (GS2, 式3.2.4), (LA, 定理2.2) -> card
    for cid, c in sorted(bk.cards.items(), key=lambda kv: bk.order.get(kv[1]['start_uid'], 0)):
        book = cid.split('/')[0]
        if book != 'LALU' and cid in bk.home:
            for lab in re.split(r'[、,，]', re.sub(r'\s', '', c['label'] or '')):
                m = re.match(r'(定理|命题|定义|推论|性质|引理|例)(\d+(?:\.\d+){2})' if book != 'LA' else
                             r'(定理|定义|推论|性质|引理)(\d+\.\d+)(?![\d.])', lab)
                if m:
                    by_label.setdefault((book, m[1] + m[2]), cid)
                for q in re.findall(r'\((\d+\.\d+\.\d+)\)', lab):
                    by_label.setdefault((book, f'式{q}'), cid)
    other = {'GS1': 'GS2', 'GS2': 'GS1'}
    gs_label = lambda key: by_label.get((r[1], key)) or by_label.get((other[r[1]], key))  # noqa: E731 - 下册 cites 上册
    labels = lalu_labels()
    eq_owner = {}  # GS equation number -> first block index showing it (its display)
    for i, r in enumerate(bk.rows):
        if r[1] in ('GS1', 'GS2'):
            for q in GS_EQ.findall(r[2]):
                eq_owner.setdefault(q, i)
    edges = defaultdict(list)  # (from kp, to kp) -> evidence
    unresolved = Counter()
    for i, r in enumerate(bk.rows):
        if not bk.cover.get(i):
            continue
        src_card = bk.cover[i][0][1]
        targets = []
        if r[1] == 'LALU':
            for m in TEX_REF.finditer(r[2]):
                for lab in m[1].split(','):
                    uid = labels.get(lab.strip())
                    if uid is None:
                        unresolved['lalu label'] += 1
                        continue
                    targets.append((bk.order.get(uid), lab.strip()))
        elif r[1] == 'LA':
            for m in LA_REF.finditer(r[2]):
                cid = by_label.get(('LA', m[1] + m[2]))
                if cid:
                    targets.append((bk.order[bk.cards[cid]['start_uid']], m[0]))
                else:
                    unresolved['la label'] += 1
        else:
            for m in GS_REF.finditer(r[2]):
                cid = gs_label(m[1] + m[2])
                if cid:
                    targets.append((bk.order[bk.cards[cid]['start_uid']], m[0]))
                else:
                    unresolved['gs label'] += 1
            for m in GS_EQ.finditer(r[2]):
                cid = gs_label(f'式{m[1]}')
                j = bk.order[bk.cards[cid]['start_uid']] if cid else eq_owner.get(m[1])
                if j is not None and j != i:
                    targets.append((j, m[0]))
        for j, what in targets:
            if j is None or not bk.cover.get(j):
                unresolved['target outside cards'] += 1
                continue
            a, b = bk.home[src_card], bk.home[bk.cover[j][0][1]]
            if a == b or src_card in [c for _, c in bk.cover[j]]:
                continue  # inside the same knowledge point / the reference is the label itself
            if subject(a) != subject(b):
                continue
            ev = edges[a, b]
            if len(ev) < 3:
                ev.append({'uid': r[0], 'ref': what})
    out = [{'from': a, 'to': b, 'evidence': ev} for (a, b), ev in sorted(edges.items())]
    jsonsave(OUT / 'explicit.json', {'edges': out, 'unresolved': dict(unresolved)})
    print(f'{len(out)} explicit edges ({Counter(subject(e["from"]) for e in out)}), unresolved {dict(unresolved)}')


# ---------- astra ----------

SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['items'],
          'properties': {'items': {'type': 'array', 'items': {
              'type': 'object', 'additionalProperties': False, 'required': ['kp', 'deps'],
              'properties': {'kp': {'type': 'string'}, 'deps': {'type': 'array', 'items': {
                  'type': 'object', 'additionalProperties': False, 'required': ['kp', 'type'],
                  'properties': {'kp': {'type': 'string'}, 'type': {'type': 'string', 'enum': TYPES}}}}}}}}}

PROMPT = '''你在为一本教材（{book}）的知识点标注“推导依据”，供考研数学二复习使用：复习一个知识点时，要知道它建立在哪些知识点之上。下面先给出全书知识点目录（编号、所在小节、名称），然后是一批待标注的知识点，每个给出名称、一句话陈述和教材原文（陈述及其证明、推导；原文来自 OCR 或 LaTeX 源码，可能截断或有识别错误）。

对每个待标注的知识点，从目录中列出它直接依据的知识点：
- type=concept：它的陈述或定义本身用到的概念（如“导数的定义”依据“函数极限的定义”；“特征多项式”依据“行列式”）。
- type=proof：它的证明、推导或解题过程中直接使用的定理、公式、性质或方法（如“洛必达法则”的证明用到“柯西中值定理”）。

规则：
1. 只列直接依据，不列依据的依据；按重要性排序，最多 {max_deps} 条。
2. 只能用目录中的编号，不列它自身。原文中明确引用的（如“由定理 3.2.4”“根据\\autoref{{thm:…}}”）只要在目录中找得到就应列入。
3. 中学数学常识（四则运算、初等代数恒等式、基本不等式等）和“实数”“集合”“函数”这类贯穿全书的最基础概念不列，除非原文专门用到它们的某个具体结论。
4. 原文没有证明或推导（如直接给出的定义、记号、公式表）时，只列陈述中用到的概念，可以为空。
5. 例题类知识点：列出解题过程用到的知识点（type=proof）以及题目涉及的概念（type=concept）。
6. 依据一般在书中更靠前，但也可以在后面（如证明留到后文的定理，或用后文结论证明的例题）。
7. 每个待标注的知识点都要输出一项（kp 写它的编号），只输出 JSON。

## 知识点目录
{catalog}

## 待标注的知识点
'''


def catalogue(bk):
    """per subject: code <-> knowledge point, prompt prefix"""
    out = {}
    for subj, book in [('GS', '严亚强《高等数学》上下册'), ('LA', '线性代数讲义 LALU')]:
        ids = sorted((k for k in bk.kps if subject(k) == subj), key=lambda k: (bk.pos(k), k))
        code = {k: f'{subj[0].lower()}{i + 1}' for i, k in enumerate(ids)}
        lines = [f'[{code[k]}] {bk.num(k)} {bk.kps[k]["name"]}' for k in ids]
        out[subj] = {'ids': ids, 'code': code, 'kp': {v: k for k, v in code.items()},
                     'prefix': PROMPT.format(book=book, max_deps=MAX_DEPS, catalog='\n'.join(lines))}
    return out


def kp_block(bk, cat, k, hints):
    kp = bk.kps[k]
    c = bk.cards[kp['canonical']]
    lab = f'{c["label"]} ' if c['label'] else ''
    s = [f'### [{cat["code"][k]}] {kp["name"]}（{kp["kind"]}，{bk.num(k)}）',
         f'陈述：{kp["statement"]}', f'原文（{lab}{c["title"]}）：{bk.text(kp["canonical"], TEXT_CHARS)}']
    der = [m['card'] for m in kp['members'] if m['relation'] == 'derivation']
    if der:
        d = bk.cards[der[0]]
        s.append(f'推导（{d["label"] or d["title"]}）：{bk.text(der[0], DERIV_CHARS)}')
    h = [cat['code'][t] for t in hints.get(k, []) if t in cat['code']]
    if h:
        s.append('原文明确引用：' + '、'.join(h))
    return '\n'.join(s)


def batches(bk):
    cat = catalogue(bk)
    hints = defaultdict(list)
    ex = OUT / 'explicit.json'
    if ex.exists():
        for e in json.loads(ex.read_text(encoding='utf-8'))['edges']:
            hints[e['from']].append(e['to'])
    out = []
    for subj, c in cat.items():
        for i in range(0, len(c['ids']), BATCH):
            ids = c['ids'][i:i + BATCH]
            out.append({'subj': subj, 'ids': ids, 'body': '\n\n'.join(kp_block(bk, c, k, hints) for k in ids)})
    return cat, out


def cmd_select(args):
    bk = Book()
    cat, bs = batches(bk)
    for subj, c in cat.items():
        b = [x for x in bs if x['subj'] == subj]
        pre = len(c['prefix']) / 1.35
        body = sum(len(x['body']) for x in b) / 1.35
        print(f'{subj}: {len(c["ids"])} kps, {len(b)} batches, prefix ~{pre:.0f} tok, bodies ~{body:.0f} tok, '
              f'input ~{pre * len(b) + body:.0f} (uncached if the prefix hits: ~{pre * WORKERS + body:.0f})')
    if args:
        print(cat[bs[0]['subj']]['prefix'][:3000], '\n…\n', bs[0]['body'][:4000])


def cmd_run(args):
    _lock = md.single_api_process()  # noqa: F841 - never run next to another API process
    bk = Book()
    cat, bs = batches(bk)
    path = OUT / 'astra.json'
    done = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'kps': {}, 'usage': {}}
    todo = [b for b in bs if any(k not in done['kps'] for k in b['ids'])]
    if args:
        todo = todo[:int(args[0])]
    md.log(f'deps: {len(todo)} batches to do')
    usage = Counter(done['usage'])

    def one(b):
        c = cat[b['subj']]
        try:
            return b, call(b['body'], SCHEMA, 'deps', f'math2-deps-v2-{b["subj"]}', prefix=c['prefix'])
        except Exception as e:  # noqa: BLE001 - a rerun picks it up
            md.log(f'deps batch {b["ids"][0]} failed: {e}')
            return b, None
    with ThreadPoolExecutor(WORKERS) as ex:
        for b, out in ex.map(one, todo):
            if not out:
                continue
            res, u = out
            cached = (u.get('input_tokens_details') or {}).get('cached_tokens', 0)
            usage['input_tokens'] += u.get('input_tokens', 0)
            usage['cached_input_tokens'] += cached
            usage['output_tokens'] += u.get('output_tokens', 0)
            usage['batches'] += 1
            c = cat[b['subj']]
            got = {}
            for it in res['items']:
                k = c['kp'].get(it['kp'])
                if k in b['ids']:
                    got[k] = [[c['kp'][d['kp']], d['type']] for d in it['deps'] if d['kp'] in c['kp']]
            for k in b['ids']:
                done['kps'][k] = got.get(k, [])
            done['usage'] = dict(usage)
            jsonsave(path, done)
            md.log(f'deps {b["ids"][0]}…: {len(got)}/{len(b["ids"])} kps, in {u.get("input_tokens")} '
                   f'cached {cached} out {u.get("output_tokens")}')
    print(f'{len(done["kps"])} kps done, usage {dict(usage)}')


# ---------- assembly ----------

def cmd_post(args):
    bk = Book()
    alias = {m: k['id'] for k in bk.kps.values() for m in k.get('merged', [])}
    fix = lambda k: alias.get(k, k)  # noqa: E731
    edges = {}
    ex = OUT / 'explicit.json'
    for e in json.loads(ex.read_text(encoding='utf-8'))['edges'] if ex.exists() else []:
        a, b = fix(e['from']), fix(e['to'])
        if a != b and a in bk.kps and b in bk.kps:
            edges[a, b] = {'from': a, 'to': b, 'type': 'proof', 'source': ['book'], 'evidence': e['evidence']}
    ast = OUT / 'astra.json'
    problems = Counter()
    for k, deps in (json.loads(ast.read_text(encoding='utf-8'))['kps'] if ast.exists() else {}).items():
        a = fix(k)
        for d, t in deps[:MAX_DEPS]:
            b = fix(d)
            if a == b or a not in bk.kps or b not in bk.kps:
                problems['self or unknown'] += 1
                continue
            e = edges.get((a, b))
            if e:
                if 'astra' not in e['source']:  # merged points can propose the same edge twice
                    e['source'].append('astra')
                    e['type'] = t
            else:
                edges[a, b] = {'from': a, 'to': b, 'type': t, 'source': ['astra']}
    # a book reference no reader confirmed and that points forward ("技巧见例 4.2.5") is a pointer, not a basis
    for (a, b), e in list(edges.items()):
        if e['source'] == ['book'] and bk.pos(b) > bk.pos(a):
            problems['unconfirmed forward reference dropped'] += 1
            del edges[a, b]
    # cycles of length 2 (A needs B and B needs A) keep the backwards edge: the later point rests on the earlier
    for (a, b) in list(edges):
        if (b, a) in edges and (a, b) in edges and bk.pos(a) < bk.pos(b):
            problems['2-cycle dropped'] += 1
            del edges[a, b]
    out = sorted(edges.values(), key=lambda e: (e['from'], e['to']))
    jsonsave(KOUT / 'deps.json', {'edges': out})
    src = Counter('+'.join(e['source']) for e in out)
    print(f'{len(out)} dependency edges {dict(src)}, types {dict(Counter(e["type"] for e in out))}, '
          f'problems {dict(problems)}')


if __name__ == '__main__':
    cmds = {'explicit': cmd_explicit, 'select': cmd_select, 'run': cmd_run, 'post': cmd_post}
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd in cmds:
        cmds[cmd](sys.argv[2:])
    else:
        print(__doc__)
