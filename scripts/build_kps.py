"""Knowledge points (plan A): merge cards that state the same conclusion, give each conclusion one canonical
source, a standard name and a one-sentence statement, and assign every question citation to the knowledge point it
actually uses.

Why citations and not just cards: one example card may derive two formulas (例2.1.6: 反三角函数 and 指数函数的导数),
so a card can belong to several knowledge points; what a citation used is decided by its knowledge wording.

  python3 scripts/build_kps.py select [CHAPTER ...]   payloads + token estimate (no API)
  python3 scripts/build_kps.py run [CHAPTER ...]      one astra call per chapter -> output/knowledge/raw/<chapter>.json
  python3 scripts/build_kps.py cross                  cross-chapter duplicates: candidates by text similarity, astra
                                                      judges them in batches -> output/knowledge/cross.json
  python3 scripts/build_kps.py post                   validate, merge -> output/knowledge/knowledge_points.json
Chapters are e.g. GS1/2 or LALU/14; without arguments, all chapters with in-scope cards. Runs resume (finished
chapters are skipped); like every API script here it takes the global single-process lock (≤4 requests).
"""
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
import re
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import HTML_TAG, jsonsave  # noqa: E402
from build_viz import in_scope  # noqa: E402
import map_questions as mq  # noqa: E402
import map_direct as md  # noqa: E402

OUT = ROOT / 'output/knowledge'
WORKERS = 4
SUMMARY_CHARS = 150
KINDS = ['definition', 'theorem', 'formula', 'property', 'method', 'concept', 'example']
RELATIONS = ['restatement', 'derivation']
CROSS_MIN = 0.3    # candidate pair threshold (mean of name and statement bigram Jaccard)
CROSS_BATCH = 12

SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['kps', 'citations', 'notes'],
    'properties': {
        'kps': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['id', 'kind', 'name', 'statement', 'canonical', 'members'],
            'properties': {
                'id': {'type': 'string'}, 'kind': {'type': 'string', 'enum': KINDS},
                'name': {'type': 'string'}, 'statement': {'type': 'string'}, 'canonical': {'type': 'string'},
                'members': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False, 'required': ['card', 'relation'],
                    'properties': {'card': {'type': 'string'},
                                   'relation': {'type': 'string', 'enum': RELATIONS}}}}}}},
        'citations': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['k', 'kp'],
            'properties': {'k': {'type': 'string'}, 'kp': {'type': 'string'}}}},
        'notes': {'type': 'string'}}}

PROMPT = '''你在整理一本教材某一章的知识点，供考研数学二复习使用。下面给出本章全部知识卡片（按书序），以及历年真题解答引用本章卡片时使用的知识表述。请把本章内容整理成“知识点”，并把每条真题引用归到它实际用到的知识点。

规则：
1. 知识点 = 一条可以单独引用的定义、定理/性质、公式、方法或概念。粒度与一张正式卡片相当；汇总表中的各类公式（如指数函数、三角函数的导数公式）按卡片划分分别成为知识点。
2. 同一结论出现在多张卡片上（首次正式陈述、公式汇总、推导或证明它的例题、复述它的注、本章回顾、后面小节的重述）时，只建一个知识点：canonical 取首次正式陈述它的卡片（定义、定理、公式、性质优先于例题和注），其余卡片列入 members，relation 为 restatement（复述、汇总、回顾、换一种写法）或 derivation（推导或证明出这条结论的例题、证明）。
3. 应用某结论解题的例题不是该结论的 member。例题若示范了有独立价值的方法或题型，单独成为知识点（kind 为 example 或 method，canonical 为该例题）；纯练习性质的例题可以不建知识点。
4. 一张卡片可以是多个知识点的 member（如一道例题同时推导了两个公式），但最多是一个知识点的 canonical。
5. 除例题外，每张卡片（定义、定理、公式、性质、方法、概念、注）都要出现在某个知识点里，作为 canonical 或 member。
6. name：规范、简洁的知识点名称，不超过 20 字，用教材术语，不带编号，如“指数函数的导数公式”“等价无穷小替换定理”。statement：用一句话写出结论本身，准确完整，可以直接拿来复习；公式用 LaTeX，写在 $…$ 中。
7. id：小写英文、数字和下划线组成的短标识，在本章内唯一。canonical 和 members 里写卡片编号（如 c12）。
8. 真题引用：每条 k 是某道真题的解答引用某张卡片时的一种知识表述（括号里是所引卡片和出现次数）。把每条 k 归到它实际使用的知识点。通常就是所引卡片所属的知识点；若所引卡片是汇总表或例题，而该表述只用到其中一条结论，就归到那条结论的知识点。每条 k 都要归类，kp 写知识点的 id。
9. 只用本章卡片。卡片文本来自 OCR 或 LaTeX 源码，可能有少量识别错误。只输出 JSON。

## {book}　{chapter}
### 知识卡片
{cards}

### 真题引用中的知识表述
{cites}
'''


def clip(t, n):
    t = re.sub(r'\s+', ' ', HTML_TAG.sub('', t or '')).strip()
    return t if len(t) <= n else t[:n] + '…'


def chapter_of(card_id):
    return '/'.join(card_id.split('/')[:2])


def load():
    rows, order = mq.load_blocks()
    cards = {cid: c for cid, c in mq.load_cards().items() if in_scope(c['unit'])}
    finals = [json.loads(f.read_text(encoding='utf-8')) for f in sorted((mq.OUT / 'final').glob('math2-*.json'))]
    return rows, order, cards, finals


def payloads(chapters=None):
    rows, order, cards, finals = load()
    toc = {n['id']: n for n in json.loads((ROOT / 'output/textbook/toc.json').read_text(encoding='utf-8'))['nodes']}
    by_ch = defaultdict(list)
    for cid, c in cards.items():
        by_ch[chapter_of(cid)].append(cid)
    uses = defaultdict(Counter)  # chapter -> (card, knowledge) -> count
    for r in finals:
        for c in r['citations']:
            if c.get('card_id') in cards:
                uses[chapter_of(c['card_id'])][c['card_id'], c['knowledge'].strip()] += 1
    out = {}
    for ch in sorted(by_ch):
        if chapters and ch not in chapters:
            continue
        ids = sorted(by_ch[ch], key=lambda x: (order.get(cards[x]['start_uid'], 0), x))
        local = {cid: f'c{i + 1}' for i, cid in enumerate(ids)}
        lines = []
        for cid in ids:
            c = cards[cid]
            unit = toc.get(c['unit'], {})
            lab = f'{c["label"]} ' if c['label'] else ''
            lines.append(f'[{local[cid]}] {lab}{c["title"]}｜{c["kind"]}｜{unit.get("num") or c["unit"]}｜'
                         f'{clip(c["summary"], SUMMARY_CHARS)}')
        ks = sorted(uses[ch].items(), key=lambda kv: (order.get(cards[kv[0][0]]['start_uid'], 0), -kv[1]))
        kmap = {f'k{i + 1}': {'card_id': cid, 'knowledge': k, 'count': n} for i, ((cid, k), n) in enumerate(ks)}
        klines = [f'[{kid}] {v["knowledge"]}（{local[v["card_id"]]} ×{v["count"]}）' for kid, v in kmap.items()]
        book = {'GS1': '高等数学（上册）', 'GS2': '高等数学（下册）', 'LA': '线性代数（王宽程）',
                'LALU': '线性代数（LALU 讲义）'}[ch.split('/')[0]]
        chap = toc.get(ch, {})
        prompt = PROMPT.format(book=book, chapter=f'第{chap.get("num", ch)}章 {chap.get("title", "")}',
                               cards='\n'.join(lines), cites='\n'.join(klines) or '（无）')
        out[ch] = {'chapter': ch, 'prompt': prompt, 'cards': {v: k for k, v in local.items()}, 'ks': kmap}
    return out


def cmd_select(args):
    ps = payloads(set(args) or None)
    tot = 0
    for ch, p in ps.items():
        n = len(p['prompt']) // 1.35
        tot += n
        print(f'{ch}: {len(p["cards"])} cards, {len(p["ks"])} citation wordings, ~{n:.0f} input tokens')
    print(f'{len(ps)} chapters, ~{tot:.0f} input tokens')


_workers = {}
_workers_lock = threading.Lock()


def worker_index():
    with _workers_lock:
        return _workers.setdefault(threading.get_ident(), len(_workers)) % WORKERS


def call(prompt, schema, name, key, per_worker=True, prefix=None):
    """per_worker: batches that share a long static prefix use one cache key per worker (the relay rejects
    concurrent use of a key); a one-off prompt (a chapter) uses its own key, so a retry of it hits the cache.
    prefix: the shared static part, sent as its own developer message — the relay only caches whole messages."""
    body = {'model': md.MODEL, 'store': False, 'reasoning': {'effort': md.EFFORT},
            'prompt_cache_key': f'{key}-w{worker_index()}' if per_worker else key,
            'text': {'format': {'type': 'json_schema', 'name': name, 'schema': schema, 'strict': True}},
            'input': ([md.msg('developer', prefix)] if prefix else []) + [md.msg('user', prompt)]}
    items, usage = md.post(body)
    text = ''.join(c.get('text', '') for i in items if i.get('type') == 'message'
                   for c in i.get('content', []) if c.get('type') == 'output_text')
    return json.loads(text), usage


def cmd_run(args):
    _lock = md.single_api_process()  # noqa: F841 - never run next to another API process
    ps = payloads(set(args) or None)
    todo = [p for ch, p in ps.items() if not (OUT / 'raw' / f'{ch.replace("/", "_")}.json').exists()]
    todo.sort(key=lambda p: -len(p['prompt']))  # longest first
    md.log(f'{len(todo)} chapters to do')

    def one(p):
        try:
            res, usage = call(p['prompt'], SCHEMA, 'knowledge_points', f'math2-kp-v1-{p["chapter"]}', per_worker=False)
        except Exception as e:  # noqa: BLE001 - keep the others; a rerun picks it up
            md.log(f'{p["chapter"]} failed: {e}')
            return
        jsonsave(OUT / 'raw' / f'{p["chapter"].replace("/", "_")}.json',
                 {'chapter': p['chapter'], 'cards': p['cards'], 'ks': p['ks'], 'usage': usage, 'result': res})
        md.log(f'{p["chapter"]}: {len(res["kps"])} kps, {len(res["citations"])}/{len(p["ks"])} citations, '
               f'in {usage.get("input_tokens")} out {usage.get("output_tokens")}')
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))


# ---------- cross-chapter duplicates ----------

CROSS_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['judgements'],
                'properties': {'judgements': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False, 'required': ['pair', 'same', 'keep'],
                    'properties': {'pair': {'type': 'string'}, 'same': {'type': 'boolean'},
                                   'keep': {'type': 'string', 'enum': ['A', 'B']}}}}}}

# static prefix (> 1024 tokens with the examples) so every batch reuses the cached part
CROSS_PROMPT = """你在检查一本教材不同章节的知识点里，有没有“同一条结论”被重复建成了两个知识点。每一对给出知识点 A 和 B（所在章节、名称、陈述、规范出处卡片）。

判断规则：
1. same=true 只在两者说的是同一条数学结论/定义/公式/方法时成立：同一结论在后文复述、在总结或回顾中重列、换一种记号或写法、作为特例推导后又单独陈述。
2. 以下都不算同一条（same=false）：一元与多元的对应结论（如一元函数的极值必要条件与二元函数的极值必要条件）；不定积分与定积分的对应方法（如不定积分换元法与定积分换元法）；一般结论与它的特殊情形，除非两处陈述的就是同一个特殊情形；只是用到同一个工具的两个不同结论；方向相反的结论（定理与其逆命题）。
3. keep：same=true 时保留哪一个作为规范出处，选首次正式陈述它的那个（通常在前面章节、以定义/定理/公式形式出现的一方）；same=false 时 keep 随意填 A。
4. 拿不准时 same=false。只输出 JSON。

示例（仅说明判断标准）：
- A「等价无穷小替换定理」（第1章，定理）与 B「用等价无穷小替换求极限」（第3章，回顾中重列的同一定理）→ same=true，keep=A。
- A「一元函数极值的必要条件（费马引理）」与 B「二元函数极值的必要条件」→ same=false。
- A「不定积分的换元法」与 B「定积分的换元法」→ same=false。
- A「矩阵的秩等于其行秩等于列秩」（第8章）与 B「行秩等于列秩」（第10章复述）→ same=true，keep=A。
- A「牛顿-莱布尼茨公式」与 B「变上限积分的导数」→ same=false（后者是推出前者的工具，不是同一结论）。
- A「特征值之积等于行列式」（第14章，定理）与 B「特征值之和等于迹、之积等于行列式」（第15章，性质汇总）→ same=true，keep=A；若 B 另外包含更多结论，仍按主要结论相同判断。
- A「可导必连续」与 B「可微必连续」（多元函数）→ same=false。
- A「矩阵」（第1讲，预备知识中的定义）与 B「矩阵」（第7讲，正式定义并引入记号）→ same=true，keep 取较早正式给出定义的一方；若较早一处只是非正式提及，则 keep 取正式定义处。
- A「泊松积分 ∫e^{-x²}dx=√π」（上册反常积分）与 B「泊松积分」（下册用二重积分重新推导）→ same=true，keep=A（首次陈述结论处），B 作为另一种推导并入。
- A「定积分的线性性质」与 B「二重积分的线性性质」→ same=false（积分对象不同）。
- A「函数的零点」（第1章定义）与 B「函数的零点」（第2章复述）→ same=true，keep=A。
- A「伴随矩阵的秩」（第10讲）与 B「伴随矩阵的秩」（第11讲作为秩的例题重述）→ same=true，keep 取先给出完整结论的一方。
- A「分部积分法」（不定积分）与 B「定积分分部积分法」→ same=false。
- A「导数的定义」与 B「偏导数的定义」→ same=false。
- A「幂等矩阵」（定义）与 B「幂等矩阵」（后文在相似标准形中再次定义并讨论）→ same=true，keep 取首次正式定义处。

## 待判断的知识点对
"""


def grams(t):
    t = re.sub(r'[\s$\\{}()（）,，.。:：、;；=+\-^_]', '', t or '')
    return {t[i:i + 2] for i in range(len(t) - 1)}


def cmd_cross(args):
    kps, _, _, cards = load_chapters()
    by_subj = defaultdict(list)
    for k in kps.values():
        by_subj['LA' if k['chapter'].split('/')[0] in ('LA', 'LALU') else 'GS'].append(k)
    wording = load_wording()
    name = {k['id']: (wording.get(k['id']) or [k['draft_name']])[0] for k in kps.values()}
    g = {k['id']: (grams(name[k['id']]), grams(re.sub(r'\\[a-zA-Z]+', '', k['draft_statement'])))
         for k in kps.values()}

    def sim(a, b):  # both the names and the statements must look alike
        (na, sa), (nb, sb) = g[a], g[b]
        jn = len(na & nb) / max(1, len(na | nb))
        js = len(sa & sb) / max(1, len(sa | sb))
        return 0.5 * jn + 0.5 * js
    pairs = {}
    for ks in by_subj.values():
        for a in ks:
            best = sorted(((sim(a['id'], b['id']), b['id']) for b in ks if b['chapter'] != a['chapter']), reverse=True)
            for s, b in best[:2]:
                if s >= CROSS_MIN:
                    pairs[tuple(sorted((a['id'], b)))] = s
    items = sorted(pairs, key=lambda p: (kps[p[0]]['chapter'], p))
    print(len(items), 'candidate pairs')
    if args and args[0] == 'dry':
        for a, b in items:
            print(f'{pairs[a, b]:.2f}  {name[a]}  ⇄  {name[b]}   ({a} / {b})')
        return
    _lock = md.single_api_process()  # noqa: F841
    path = OUT / 'cross.json'
    done = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'judgements': {}, 'merges': [], 'usage': {}}

    def show(k):
        c = cards[k['canonical']]
        return (f'{k["chapter"]}｜{k["kind"]}｜{k["draft_name"]}｜{clip(k["draft_statement"], 160)}｜出处：'
                f'{c["label"]} {c["title"]}')
    todo = [p for p in items if f'{p[0]}|{p[1]}' not in done['judgements']]
    batches = [todo[i:i + CROSS_BATCH] for i in range(0, len(todo), CROSS_BATCH)]
    usage = Counter(done['usage'])

    def one(batch):
        text = '\n'.join(f'### pair {i}\nA：{show(kps[a])}\nB：{show(kps[b])}' for i, (a, b) in enumerate(batch))
        try:
            return batch, call(text, CROSS_SCHEMA, 'cross', 'math2-kpcross-v2', prefix=CROSS_PROMPT)
        except Exception as e:  # noqa: BLE001
            md.log(f'cross batch failed: {e}')
            return batch, None
    with ThreadPoolExecutor(WORKERS) as ex:
        for batch, out in ex.map(one, batches):
            if not out:
                continue
            res, u = out
            usage['input_tokens'] += u.get('input_tokens', 0)
            usage['cached_input_tokens'] += (u.get('input_tokens_details') or {}).get('cached_tokens', 0)
            usage['output_tokens'] += u.get('output_tokens', 0)
            for j in res['judgements']:
                if not j['pair'].isdigit() or int(j['pair']) >= len(batch):
                    continue
                a, b = batch[int(j['pair'])]
                done['judgements'][f'{a}|{b}'] = j
            done['usage'] = dict(usage)
            jsonsave(path, done)
    merges = []
    for key, j in done['judgements'].items():
        if j['same']:
            a, b = key.split('|')
            keep, drop = (a, b) if j['keep'] == 'A' else (b, a)
            if {keep.split('/')[0], drop.split('/')[0]} == {'LA', 'LALU'} and keep.startswith('LALU'):
                keep, drop = drop, keep  # 王宽程 is the main linear-algebra book: its statement is the canonical one
            merges.append({'keep': keep, 'drop': drop})
    done['merges'] = merges
    jsonsave(path, done)
    print(f'{len(done["judgements"])} judged, {len(merges)} merges, usage {dict(usage)}')


# ---------- validation and assembly ----------

def load_chapters():
    """Per-chapter results with global ids, validated; problems are fixed conservatively and reported."""
    cards = {cid: c for cid, c in mq.load_cards().items() if in_scope(c['unit'])}
    kps, cite_kps, problems = {}, {}, Counter()
    for f in sorted((OUT / 'raw').glob('*.json')):
        d = json.loads(f.read_text(encoding='utf-8'))
        ch, local, res = d['chapter'], d['cards'], d['result']
        gid = lambda s: f'{ch}#{s}'  # noqa: E731
        canon_of = {}
        for kp in res['kps']:
            if kp['canonical'] not in local:
                problems['bad canonical'] += 1
                continue
            cid = local[kp['canonical']]
            if cid in canon_of:  # a card is canonical of one knowledge point only: keep the first
                problems['card canonical twice'] += 1
                continue
            if gid(kp['id']) in kps:
                problems['duplicate id'] += 1
                continue
            canon_of[cid] = gid(kp['id'])
            members = [{'card': local[m['card']], 'relation': m['relation']} for m in kp['members']
                       if m['card'] in local and local[m['card']] != cid]
            problems['bad member'] += sum(1 for m in kp['members'] if m['card'] not in local)
            kps[gid(kp['id'])] = {'id': gid(kp['id']), 'chapter': ch, 'kind': kp['kind'], 'draft_name': kp['name'],
                                  'draft_statement': kp['statement'], 'canonical': cid, 'members': members}
        covered = set(canon_of) | {m['card'] for k in kps.values() if k['chapter'] == ch for m in k['members']}
        for cid in local.values():  # every non-example card must belong somewhere: own knowledge point
            if cid not in covered and cards[cid]['kind'] != 'example':
                problems['uncovered card -> own kp'] += 1
                k = f'{ch}#card_{cid.split("#")[1]}'
                kps[k] = {'id': k, 'chapter': ch, 'kind': cards[cid]['kind'] if cards[cid]['kind'] in KINDS else
                          'concept', 'draft_name': cards[cid]['title'], 'draft_statement': cards[cid]['summary'],
                          'canonical': cid, 'members': [], 'auto': True}
                canon_of[cid] = k
        home = {}  # card -> knowledge point for citation fallback: canonical first, then first membership
        for k in kps.values():
            if k['chapter'] == ch:
                for m in k['members']:
                    home.setdefault(m['card'], k['id'])
        home.update(canon_of)
        assigned = defaultdict(list)
        for x in res['citations']:
            if x['k'] in d['ks'] and gid(x['kp']) in kps and gid(x['kp']) not in assigned[x['k']]:
                assigned[x['k']].append(gid(x['kp']))
        for kid, v in d['ks'].items():
            if not assigned.get(kid):
                problems['citation wording unassigned -> card home'] += 1
                assigned[kid] = [home[v['card_id']]] if v['card_id'] in home else []
            cite_kps[v['card_id'], v['knowledge']] = assigned[kid]
    return kps, cite_kps, problems, cards


def load_wording():
    w = {}
    for f in sorted((OUT / 'wording').glob('*.json')):
        w.update(json.loads(f.read_text(encoding='utf-8')))
    return w


def cmd_sheet(args):
    """Print the drafts of a chapter for rewording (names / statements are written by hand into wording/)."""
    kps, cite_kps, _, cards = load_chapters()
    wording = load_wording()
    uses = defaultdict(Counter)
    for (cid, k), ids in cite_kps.items():
        for i in ids:
            uses[i][k] += 1
    for k in kps.values():
        if args and k['chapter'] not in args:
            continue
        c = cards[k['canonical']]
        done = '✓' if k['id'] in wording else ' '
        print(f'{done} {k["id"]} [{k["kind"]}] {k["draft_name"]}')
        print(f'    草稿：{k["draft_statement"]}')
        print(f'    出处：{c["label"]} {c["title"]}：{clip(c["summary"], 220)}')
        for m in k['members']:
            print(f'    {m["relation"]}：{cards[m["card"]]["label"]} {cards[m["card"]]["title"]}')
        if uses[k['id']]:
            print('    引用：' + '；'.join(list(uses[k['id']])[:6]))


def cmd_post(args):
    kps, cite_kps, problems, cards = load_chapters()
    merges = json.loads((OUT / 'cross.json').read_text(encoding='utf-8'))['merges'] if (OUT / 'cross.json').exists() else []
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x
    review = json.loads((OUT / 'cross_review.json').read_text(encoding='utf-8')) if (OUT / 'cross_review.json').exists() \
        else {'reject': []}
    rejected = {(r[0], r[1]) for r in review['reject']}
    for m in merges:  # keep -> absorbs drop; a point is absorbed at most once (no chains through a dropped point)
        if (m['keep'], m['drop']) in rejected or m['drop'] in parent or m['keep'] in parent:
            continue
        a, b = find(m['keep']), m['drop']
        if a != b and a in kps and b in kps:
            parent[b] = a
    for k in list(kps):
        r = find(k)
        if r != k:
            kps[r]['members'] += [{'card': kps[k]['canonical'], 'relation': 'restatement'}] + kps[k]['members']
            kps[r].setdefault('merged', []).append(k)
            del kps[k]
    cite_kps = {key: list(dict.fromkeys(find(i) for i in ids)) for key, ids in cite_kps.items()}
    wording = load_wording()
    missing = 0
    for k in kps.values():
        w = wording.get(k['id'])
        if w:
            k['name'], k['statement'] = w
        else:
            missing += 1
            k['name'], k['statement'] = k['draft_name'], k['draft_statement']
        k['worded'] = bool(w)
        seen, ms = set(), []
        for m in k['members']:
            if m['card'] != k['canonical'] and m['card'] not in seen:
                seen.add(m['card'])
                ms.append(m)
        k['members'] = ms
    n_cite = Counter(i for ids in cite_kps.values() for i in ids)
    for k in kps.values():
        k['cited_wordings'] = n_cite[k['id']]
    jsonsave(OUT / 'knowledge_points.json', {
        'kps': sorted(kps.values(), key=lambda k: k['id']),
        'citations': [{'card_id': c, 'knowledge': k, 'kps': ids} for (c, k), ids in sorted(cite_kps.items())]})
    print(f'{len(kps)} knowledge points ({missing} without hand wording), {len(cite_kps)} citation wordings, '
          f'{len(parent)} of {len(merges)} cross-chapter merges applied; problems: {dict(problems)}')


if __name__ == '__main__':
    cmds = {'select': cmd_select, 'run': cmd_run, 'cross': cmd_cross, 'sheet': cmd_sheet, 'post': cmd_post}
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd in cmds:
        cmds[cmd](sys.argv[2:])
    else:
        print(__doc__)
