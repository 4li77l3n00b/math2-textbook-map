"""Map bank questions to textbook passages (pilot condition A) plus a solution-independent topic layer.

  python3 scripts/map_questions.py run [GS|LA] [QUESTION_ID ...]   run missing jobs of a subject / given ids
  python3 scripts/map_questions.py post                    verify / repair spans, attach card ids, summary

Citations: astra reads the book like a student (toc/read/blocks/search) and cites contiguous block spans with a
verbatim quote. Topics: what the question is designed to test, chosen from knowledge cards regardless of the
reference solution's route. Cards are also attached to citations afterwards by block overlap.
Calculus questions use GS1/GS2 (OCR); linear-algebra questions use 王宽程 LA (OCR, main book) and the LaTeX notes
LALU only for what LA lacks.
"""
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
import re
import sqlite3
from difflib import SequenceMatcher
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import HTML_TAG, save, jsonsave  # noqa: E402
from build_cards import SCOPE, SKIP  # noqa: E402
from codex_run import run_codex  # noqa: E402

DB = ROOT / 'output/textbook/textbook_index.sqlite'
CARDS = ROOT / 'output/textbook/cards'
QINDEX = ROOT / 'output/astra/question_index.json'
SUBJECTS = ROOT / 'output/question_subjects.json'
OUT = ROOT / 'output/mapping'
WORKERS = 4

CITATION = {
    'type': 'object', 'additionalProperties': False,
    'required': ['steps', 'knowledge', 'role', 'start_uid', 'end_uid', 'quote', 'why', 'confidence'],
    'properties': {
        'steps': {'type': 'array', 'items': {'type': 'integer'}},
        'knowledge': {'type': 'string'},
        'role': {'type': 'string', 'enum': ['core', 'auxiliary', 'prerequisite']},
        'start_uid': {'type': 'string'}, 'end_uid': {'type': 'string'},
        'quote': {'type': 'string'}, 'why': {'type': 'string'},
        'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']}}}
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['steps', 'citations', 'not_in_textbook', 'topics', 'topic_note', 'notes'],
    'properties': {
        'steps': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['n', 'description'],
            'properties': {'n': {'type': 'integer'}, 'description': {'type': 'string'}}}},
        'citations': {'type': 'array', 'items': CITATION},
        'not_in_textbook': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['steps', 'knowledge', 'searched'],
            'properties': {'steps': {'type': 'array', 'items': {'type': 'integer'}},
                           'knowledge': {'type': 'string'}, 'searched': {'type': 'string'}}}},
        'topics': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['card_id', 'relation', 'reason'],
            'properties': {'card_id': {'type': 'string'},
                           'relation': {'type': 'string', 'enum': ['primary', 'secondary']},
                           'reason': {'type': 'string'}}}},
        'topic_note': {'type': 'string'},
        'notes': {'type': 'string'}},
}

PROMPT = '''你是一名做完考研数学二真题的学生，现在要“翻教材”：(一) 把这道题解答中用到的每一条知识依据落实到教材原文；(二) 判断这道题在教材知识体系里考查的是哪一部分。

## 题目 {qid}
{stem}

## 参考答案
{answer}

## 参考解析
{solution}

## 教材
{books}目录（节点 id 与标题）：
{toc}

## 查询工具（只读）
在工作目录运行 `python3 scripts/textbook_cli.py <子命令>`：
- `read NODE_ID [--from UID] [--limit N]`：按阅读顺序读某节正文块
- `blocks UID [UID_END] [--context K]`：读指定块/区间（可带上下文）
- `search 关键词 [--book {book_ids}]`：全文检索（空格分隔的多个词表示同时包含）
- `cards NODE_ID`：列出某节的知识卡片（按书整理的知识点索引：书中编号、名称、概要、原文区间）；`card CARD_ID`：查看一张卡片及原文
{block_note}

## 第一部分：解题依据 → 教材原文
1. 把参考解析拆成若干步骤（steps），每步写清用了什么数学依据；解析省略的隐含依据也要补出（如“闭区间连续函数可取到最值”）。
2. 像人翻书一样：根据目录定位章节，用 read 或 search 找到具体段落，读原文确认后再引用。解题用到其他章节的工具时（如求极限用泰勒公式）要去对应章节找。
3. 每条依据一个引用：start_uid..end_uid 是直接陈述该依据的**连续**块区间，尽量小（通常 1–5 块，即定理/定义/公式本身）；优先引用定义、定理、公式、书中明确讲的方法，只有书中没有一般性陈述时才引用例题。quote 从区间内原文**逐字**摘一句（10–80 字，照抄工具显示的原文，含其中的 LaTeX）。knowledge 用书中的叫法；role：core / auxiliary / prerequisite。
4. 粒度：只引用大学{course}课程层面的知识。中学层面的代数与初等函数运算（对数/指数运算律、不等式同乘除正数、解代数方程、三角恒等式、配方等）不必引用，也不列入 not_in_textbook，除非它恰是考查重点。同一知识多步使用只引用一次（steps 列出所有步号）。
5. 教材里确实找不到的课程层面依据放入 not_in_textbook，写明查过哪里；不要勉强凑不相干的段落。

## 第二部分：考查主题（与解析路线无关）
6. 暂时忘掉参考解析用的方法，从命题意图看：这道题考的是教材哪部分知识、属于书中哪类题型？{topic_example}用 `cards` 查看候选小节的卡片，选 1–3 张 primary（最直接的考查对象）和若干 secondary（常用解法或关联知识），card_id 必须是 cards 输出中真实存在的；reason 说明理由。若主题与解析路线不同，在 topic_note 中说明。

## 要求
- 查找要高效：通常 10–20 条命令内完成，读节时先看开头定位，不必通读整节。
- 只使用上述工具命令，不要读取或修改项目中的其他文件。最后直接输出 JSON。
'''


SUBJECT = {
    'GS': {'books': 'GS1 = 高等数学上册，GS2 = 高等数学下册（数二范围内的章节）。', 'prefixes': ('GS1', 'GS2'),
           'book_ids': 'GS1|GS2', 'course': '高等数学',
           'block_note': '每个块形如 `GS1-p144-b23 文本`；OCR 文本可能有少量识别错误。',
           'topic_example': '例如“证明 f\'\'≥0 与某积分不等式等价”考的是凹凸性，即使参考解析用中值定理和泰勒公式完成。'},
    'LA': {'books': 'LA = 王宽程《线性代数》（主教材，数二范围的第 1–5 章），LALU = 线性代数讲义《线性代数：未竟之美》（补充）。先在 LA 中查找并引用；只有 LA 中没有该结论的一般性陈述时（如秩的不等式、伴随矩阵的秩与行列式、代数重数与几何重数、范德蒙德行列式等），才引用 LALU，并在 why 中写明“王宽程未见”。LALU 以线性空间、线性映射（算子）的抽象语言叙述，书中只有抽象版本时引用抽象版本，并在 why 中说明对应关系（如“σ 的特征值”对应“矩阵 A 的特征值”）。',
           'prefixes': ('LA/', 'LALU'), 'book_ids': 'LA|LALU', 'course': '线性代数',
           'block_note': ('LA 的块形如 `LA-p070-b12 文本`，是 OCR 文本，可能有少量识别错误；LALU 的块形如 '
                          '`LALU-c14-b0050 [theorem 定理14.3] 文本`，是讲义的 LaTeX 源码，类型中带书中编号。'
                          'knowledge 请写出书中编号（如“定理 2.2”“定理14.3”）。'),
           'topic_example': '例如“已知 A 相似于对角阵求参数”考的是可对角化的判定，即使参考解析主要在解线性方程组。'},
}


def toc_text(subject):
    con = sqlite3.connect(DB)
    rows = con.execute("select id, kind, num, title from sections where kind in ('chapter','section','subsection') "
                       "order by book, pdf_first, id").fetchall()
    out = []
    for sid, kind, num, title in rows:
        if not sid.startswith(SUBJECT[subject]['prefixes']):
            continue
        if not any(sid == s or sid.startswith(s + '/') or s.startswith(sid + '/') for s in SCOPE):
            continue
        if any(sid == s or sid.startswith(s + '/') for s in SKIP):
            continue
        ind = {'chapter': '', 'section': '  ', 'subsection': '    '}[kind]
        name = f'第{num}章 {title}' if kind == 'chapter' else f'{num} {title}'
        out.append(f'{ind}{sid}  {name}')
    return '\n'.join(out)


def questions(subject=None):
    subj = json.loads(SUBJECTS.read_text(encoding='utf-8'))
    qs = json.loads(QINDEX.read_text(encoding='utf-8'))['questions']
    for q in qs:
        q['_subject'] = subj[q['question_id']]['subject']
    return [q for q in qs if subject is None or q['_subject'] == subject]


def run_one(q, tocs):
    qid, sub = q['question_id'], q['_subject']
    out = OUT / 'raw' / f'{qid}.json'
    if out.exists():
        return qid, 'skip'
    cfg = SUBJECT[sub]
    prompt = PROMPT.format(qid=qid, stem=q['stem'], answer=q['answer'], solution=q['solution'], toc=tocs[sub],
                           books=cfg['books'], book_ids=cfg['book_ids'], block_note=cfg['block_note'],
                           course=cfg['course'], topic_example=cfg['topic_example'])
    r = run_codex(prompt, OUT / 'schema.json', OUT / 'runs' / f'{qid}.json')
    if not r['ok']:
        save(OUT / 'raw' / f'{qid}.err.txt', r['error'] or '')
        return qid, f'failed: {(r["error"] or "")[:150]}'
    jsonsave(out, {'question_id': qid, 'subject': sub, 'year': q['year'], 'label': q['label'], 'usage': r['usage'],
                   'seconds': r['seconds'], 'commands': r['commands'], **r['result']})
    return qid, f'{len(r["result"]["citations"])} citations, {len(r["result"]["topics"])} topics, {r["seconds"]}s'


def cmd_run(args):
    subjects = [a for a in args if a in SUBJECT]
    ids = {a for a in args if a.startswith('math2-')}
    qs = [q for q in questions() if (q['_subject'] in subjects) or (q['question_id'] in ids)]
    jsonsave(OUT / 'schema.json', SCHEMA)
    tocs = {k: toc_text(k) for k in SUBJECT}
    with ThreadPoolExecutor(WORKERS) as ex:
        for qid, status in ex.map(lambda q: run_one(q, tocs), qs):
            print(qid, status, flush=True)


# ---------- post-processing ----------

FULLWIDTH = str.maketrans('。，：；（）！？', '.,:;()!?')


def squash(t):
    t = HTML_TAG.sub('', t).translate(FULLWIDTH)
    t = re.sub(r'\\math(?:bb|bf|rm)\b', '', t)  # \mathbb{R} vs \mathbf{R}: same symbol for our purpose
    return re.sub(r'[\s$\\\u200b-\u200f\ufeff]', '', t)


# LaTeX inside a JSON string: `\ldots`, `\times`, `\frac` may come back as newline/tab/form-feed + letters
UNESCAPE = str.maketrans({'\n': '\\n', '\t': '\\t', '\r': '\\r', '\f': '\\f', '\b': '\\b'})


def quote_variants(q):
    return {squash(q), squash(q.translate(UNESCAPE))} - {''}


def load_blocks():
    con = sqlite3.connect(DB)
    rows = con.execute("select uid, book, text, coalesce(subsection, section, node) from blocks "
                       "where trim(text) != '' order by book, pdf_page, block_id").fetchall()
    return rows, {r[0]: i for i, r in enumerate(rows)}


def load_cards():
    cards = {}
    for f in sorted(CARDS.glob('*_*.json')):
        for c in json.loads(f.read_text(encoding='utf-8'))['cards']:
            cards[c['card_id']] = c
    return cards


def repair(c, rows, order):
    """Verify the quote; if it sits one block outside the span, widen the span by that block."""
    s, e = order.get(c['start_uid']), order.get(c['end_uid'])
    if s is None or e is None:
        return 'unknown_uid'
    s, e = min(s, e), max(s, e)
    if rows[s][1] != rows[e][1]:
        return 'cross_book'
    qs = quote_variants(c['quote'])

    def has(i, j):
        text = squash(''.join(r[2] for r in rows[i:j + 1]))
        return any(q in text for q in qs)
    if has(s, e):
        return 'ok'
    for i, j in ((s - 1, e), (s, e + 1), (s - 1, e + 1)):
        if 0 <= i and j < len(rows) and rows[i][1] == rows[s][1] and has(i, j):
            c['start_uid'], c['end_uid'] = rows[i][0], rows[j][0]
            return 'repaired'
    # the span is usually right and only the quote was paraphrased: substitute the most similar sentence of
    # the span, keeping the model's wording for the audit trail
    best = best_sentence(c['quote'], ''.join(r[2] + '\n' for r in rows[s:e + 1]))
    if best:
        c['quote_original'], c['quote'] = c['quote'], best
        return 'quote_fixed'
    return 'quote_mismatch'


def best_sentence(quote, text):
    # sentence ends: Chinese punctuation, or a full stop not between digits ("定理 2.1.1" stays whole)
    parts = [p.strip() for p in re.split(r'(?<=[。．；;！？!?])\s*|(?<=\D\.)\s*|\n+', HTML_TAG.sub('', text))
             if len(squash(p)) >= 10]  # skip fragments like "因此有"
    if not parts:
        return None
    target = squash(quote)
    if len(target) < 6:  # the model's quote carries no information: take the span's first real sentence
        return parts[0][:200]

    def coverage(p):  # share of the quote found in the sentence; shorter sentences win ties
        m = SequenceMatcher(None, target, squash(p), autojunk=False)
        return sum(b.size for b in m.get_matching_blocks()) / len(target), -len(p)
    score, sentence = max((coverage(p), p) for p in parts)
    return sentence[:200] if score[0] >= 0.6 else None


NEAREST_MAX = 5  # blocks


def attach_cards(c, cards_by_book, order, section_of):
    """(card_id, how): card whose statement blocks overlap the citation ('core'), else whose span contains or
    overlaps it ('span'), else the nearest card of the same section within NEAREST_MAX blocks ('nearest')."""
    s, e = sorted((order[c['start_uid']], order[c['end_uid']]))
    span = set(range(s, e + 1))
    best, near = None, None
    for cid, cd, core, full in cards_by_book.get(c['start_uid'].split('-')[0], []):
        if span & core:
            score = (3, len(span & core))
        elif span <= full:
            score = (2, -len(full))
        elif span & full:
            score = (1, len(span & full))
        else:
            if cd['unit'] == section_of(c['start_uid']):
                d = min(abs(i - j) for i in (s, e) for j in (min(full), max(full)))
                if d <= NEAREST_MAX and (near is None or d < near[0]):
                    near = (d, cid)
            continue
        if not best or score > best[0]:
            best = (score, cid)
    if best:
        return best[1], ('core' if best[0][0] == 3 else 'span')
    return (near[1], 'nearest') if near else (None, None)


def cmd_post():
    rows, order = load_blocks()
    cards = load_cards()
    by_book = defaultdict(list)
    for cid, cd in cards.items():
        if cd['start_uid'] in order and cd['end_uid'] in order:
            s, e = sorted((order[cd['start_uid']], order[cd['end_uid']]))
            core = {order[u] for u in cd['statement_uids'] if u in order}
            by_book[cid.split('/')[0]].append((cid, cd, core, set(range(s, e + 1))))
    st = defaultdict(Counter)
    manual = json.loads((OUT / 'manual_review.json').read_text(encoding='utf-8'))['questions'] \
        if (OUT / 'manual_review.json').exists() else {}
    canon = defaultdict(dict)  # question -> citation index -> decision (scripts/canonicalize.py)
    if (OUT / 'canonical/decisions.json').exists():
        for d in json.loads((OUT / 'canonical/decisions.json').read_text(encoding='utf-8'))['decisions'].values():
            if d['choice'] != 0 and d['confidence'] != 'low':
                canon[d['question_id']][d['index']] = d
    # knowledge points (scripts/build_kps.py): citation wording -> knowledge points; card -> knowledge point
    kp_of_cite, kp_of_card = {}, {}
    kp_path = ROOT / 'output/knowledge/knowledge_points.json'
    if kp_path.exists():
        kpd = json.loads(kp_path.read_text(encoding='utf-8'))
        kp_of_cite = {(x['card_id'], x['knowledge']): x['kps'] for x in kpd['citations']}
        rank = {'restatement': 1, 'derivation': 2}
        for k in kpd['kps']:
            kp_of_card[k['canonical']] = (0, k['id'])
            for m in k['members']:
                kp_of_card[m['card']] = min(kp_of_card.get(m['card'], (9, None)), (rank[m['relation']], k['id']))
    for f in sorted((OUT / 'raw').glob('math2-*.json')):
        r = json.loads(f.read_text(encoding='utf-8'))
        mr = manual.get(r['question_id'], {})
        # QA overlay: reviewed "not in textbook" items, and citations added by manual review
        for n in r['not_in_textbook']:
            hit = next((v for k, v in mr.get('not_in_textbook', {}).items() if k in n['knowledge']), None)
            if hit:
                n['review'] = hit
                st['not_in_textbook_review'][hit['verdict']] += 1
        for c in mr.get('add_citations', []):
            if not any(x['start_uid'] == c['start_uid'] for x in r['citations']):
                r['citations'].append({**c, 'source': 'manual_qa'})
        for i, c in enumerate(r['citations']):
            d = canon[r['question_id']].get(i)
            if d and [c['start_uid'], c['end_uid']] == d['from']:  # stale decisions (question re-run) are ignored
                a, b = sorted((order[d['to'][0]], order[d['to'][1]]))
                c['original_span'] = [c['start_uid'], c['end_uid']]
                c['start_uid'], c['end_uid'] = rows[a][0], rows[b][0]
                c['canonical'] = {'reason': d['reason'], 'confidence': d['confidence'], 'from_kind': d['to_kind']}
                c['quote_original'] = c.get('quote_original', c['quote'])
                c['quote'] = best_sentence(c['knowledge'] + c['quote'], ''.join(x[2] + '\n' for x in rows[a:b + 1])) \
                    or best_sentence('', ''.join(x[2] + '\n' for x in rows[a:b + 1])) or c['quote']
                st['canonicalized'][d['to_kind']] += 1
            c['verify'] = repair(c, rows, order)
            st['verify'][c['verify']] += 1
            c['section'] = rows[order[c['start_uid']]][3] if c['start_uid'] in order else None
            if c['verify'] in ('ok', 'repaired', 'quote_fixed'):
                c['card_id'], c['card_match'] = attach_cards(c, by_book, order, lambda u: rows[order[u]][3])
            else:
                c['card_id'], c['card_match'] = None, None
            st['card_match'][c['card_match'] or 'none'] += 1
            st['citation_card']['with_card' if c['card_id'] else 'no_card'] += 1
            if kp_of_cite:
                c['kps'] = kp_of_cite.get((c['card_id'], c['knowledge'].strip())) or \
                    ([kp_of_card[c['card_id']][1]] if c['card_id'] in kp_of_card else [])  # wording not assigned yet
                st['citation_kp']['with_kp' if c['kps'] else 'no_kp'] += 1
        for t in r['topics']:
            t['valid'] = t['card_id'] in cards
            st['topics']['valid' if t['valid'] else 'unknown_card'] += 1
            if kp_of_card:
                t['kp'] = kp_of_card.get(t['card_id'], (None, None))[1]
                st['topic_kp']['with_kp' if t['kp'] else 'no_kp'] += 1
        u = r['usage']
        for k in ('input_tokens', 'cached_input_tokens', 'output_tokens'):
            st['usage'][k] += u.get(k, 0)
        st['usage']['seconds'] += r['seconds']
        st['usage']['questions'] += 1
        jsonsave(OUT / 'final' / f.name, r)
    jsonsave(OUT / 'summary.json', {k: dict(v) for k, v in st.items()})
    print(json.dumps({k: dict(v) for k, v in st.items()}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    if sys.argv[1:2] == ['run']:
        cmd_run(sys.argv[2:])
    elif sys.argv[1:2] == ['post']:
        cmd_post()
    else:
        print(__doc__)
