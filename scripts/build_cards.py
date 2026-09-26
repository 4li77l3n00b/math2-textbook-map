"""Build textbook knowledge cards (one Astra call per leaf unit).

  python3 scripts/build_cards.py [UNIT_ID ...]      build missing cards in SCOPE (or just the given units)

Scope (数二): every chapter of GS1; GS2 ch.7, 8.1-8.2 + 8.4, ch.11. Excluded GS2 ch.6, 8.3, 9, 10: none of
the 872 bank questions touches series, triple/line/surface integrals or space analytic geometry (checked by
keyword search; the "space geometry" hits were plane-curve tangents). Borderline units (7.4 gradient, 11.1.4,
11.3) are kept because cards are cheap and bank solutions occasionally borrow such tools.
Linear algebra: 王宽程 (LA) is the main book — ch.1–5; excluded ch.6 (linear spaces, change of basis: no bank
question uses them; the bank's "线性变换" is the substitution x = Py of quadratic forms) and the MATLAB sections.
The LaTeX notes LALU supplement it; excluded there: dual spaces, history, polynomials, Jordan/rational forms, normal
operators/SVD, geometry, tensors, calculus, optimisation, quotient and product spaces.
Engine: LA cards call the relay's Responses API directly (no codex overhead; global single-process lock ≤4 requests);
the earlier GS / LALU cards were made through `codex exec`.

Cards are derived from the book only: names and numbering follow the book, and each card points at a
contiguous block span (start_uid..end_uid) plus the blocks that state it. Output: output/textbook/cards/.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import HTML_TAG, save, jsonsave  # noqa: E402
import text_norm  # noqa: E402
from codex_run import run_codex  # noqa: E402

DB = ROOT / 'output/textbook/textbook_index.sqlite'
OUT = ROOT / 'output/textbook/cards'
SCOPE = ['GS1/1', 'GS1/2', 'GS1/3', 'GS1/4', 'GS1/5', 'GS2/7', 'GS2/8', 'GS2/11',
         'LA/1', 'LA/2', 'LA/3', 'LA/4', 'LA/5',  # 王宽程: main linear-algebra book
         # LALU (LaTeX notes): computational linear algebra of 数二, framed abstractly in this book
         'LALU/1/1.4', 'LALU/2', 'LALU/3', 'LALU/4', 'LALU/5', 'LALU/7', 'LALU/8', 'LALU/9', 'LALU/10',
         'LALU/11', 'LALU/14', 'LALU/15', 'LALU/17/17.1', 'LALU/19', 'LALU/20/20.1', 'LALU/20/20.2', 'LALU/22',
         'LALU/16/16.1']  # Jordan form: not in 数二, but bank solutions use it (e.g. 2018-q7)
SKIP = {'GS2/8/8.3', 'LA/2/2.7', 'LA/3/3.6', 'LA/4/4.5', 'LA/5/5.5',  # triple integrals (not in 数二); MATLAB
        'LALU/4/4.5', 'LALU/5/5.7'}  # quotient spaces, products of spaces
WORKERS = 4

SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['cards'],
    'properties': {'cards': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False,
        'required': ['local_id', 'kind', 'label', 'title', 'summary', 'start_uid', 'end_uid',
                     'statement_uids', 'keywords', 'related'],
        'properties': {
            'local_id': {'type': 'string', 'description': 'ascii slug, unique within the unit'},
            'kind': {'type': 'string', 'enum': ['definition', 'theorem', 'lemma', 'corollary', 'formula',
                                                'property', 'method', 'example', 'remark', 'concept']},
            'label': {'type': 'string'}, 'title': {'type': 'string'}, 'summary': {'type': 'string'},
            'start_uid': {'type': 'string'}, 'end_uid': {'type': 'string'},
            'statement_uids': {'type': 'array', 'items': {'type': 'string'}},
            'keywords': {'type': 'array', 'items': {'type': 'string'}},
            'related': {'type': 'array', 'items': {'type': 'string'}}}}}},
}

PROMPT = '''你在为一本教材的一个小节建立“知识卡片”，供之后把考研真题映射回教材时使用。卡片必须完全来自这本书：名称、编号、表述都以书为准，不要引入书里没有的知识点。

小节：{unit}（{title}），书：{book}
下面是该小节正文的全部块，每行格式为 `uid [类型] 文本`。{source_note}

要求：
1. 覆盖本节所有实质知识：每个定义、定理/引理/推论、重要公式与性质、书中明确讲解的方法（如“构造辅助函数”“用单调性证不等式”）、重要的“注”。例题：只为展示了独立方法或典型题型的例题建卡（kind=example），同类例题可合并为一张卡。
2. 每张卡对应书中一段**连续**的块：start_uid..end_uid（按给出顺序，含两端），应涵盖该知识的完整陈述（及紧随的证明/推导，如有）；statement_uids 列出直接陈述该知识的核心块（定理条件和结论所在块、定义句所在块、公式块等），它们必须在区间内。
3. label 用书中编号（如“定理3.1.2”“定义4.3”“例3.1.10”“推论”），没有编号则为空串；title 用书中的名称或最贴近书的简短名称；summary 用一两句话按书的表述概括内容（公式可用 LaTeX）。
4. keywords 给 3–8 个检索用词（书中术语、常见别称）；related 填本节内相关卡片的 local_id（如方法卡关联其依据的定理卡）。
5. local_id 用简短 ASCII（如 lagrange_mvt、ex_3_1_10）。只使用下面出现的 uid，不要编造。
6. 不要运行任何命令或读文件，直接输出 JSON。

{blocks}
'''


def units(con):
    out = []
    for ch in SCOPE:
        rows = con.execute("select id, kind, title from sections where (id = ? or id like ?) "
                           "and kind in ('section','subsection') order by pdf_first, id", (ch, ch + '/%')).fetchall()
        subs = {r[0] for r in rows if r[1] == 'subsection'}
        for sid, kind, title in rows:
            if sid in SKIP or any(sid.startswith(s + '/') for s in SKIP):
                continue
            if kind == 'subsection':
                q = "select uid,label||coalesce(' '||num_label,''),text from blocks where subsection=? and zone='body'"
            elif any(s.startswith(sid + '/') for s in subs):
                q = "select uid,label||coalesce(' '||num_label,''),text from blocks where section=? and subsection is null and zone='body'"
            else:
                q = "select uid,label||coalesce(' '||num_label,''),text from blocks where section=? and zone='body'"
            blocks = con.execute(q + " and trim(text)!='' and label not in ('image','chart') "
                                 "order by pdf_page, block_id", (sid,)).fetchall()
            if any(lab.split()[0] != 'paragraph_title' for _, lab, _ in blocks):  # any content beyond headings
                out.append({'unit': sid, 'title': title, 'blocks': blocks})
    return out


def validate(unit, cards):
    order = {b[0]: i for i, b in enumerate(unit['blocks'])}
    problems, seen = [], set()
    for c in cards:
        cid = c['local_id']
        if cid in seen:
            problems.append(f'duplicate local_id {cid}')
        seen.add(cid)
        s, e = order.get(c['start_uid']), order.get(c['end_uid'])
        if s is None or e is None or s > e:
            problems.append(f'{cid}: bad span {c["start_uid"]}..{c["end_uid"]}')
            continue
        bad = [u for u in c['statement_uids'] if not (s <= order.get(u, -1) <= e)]
        if bad:
            problems.append(f'{cid}: statement_uids outside span {bad}')
    return problems


def run_direct(prompt, slug):
    """Same result shape as run_codex, through the Responses API (one-off prompt: its own cache key, so a retry hits)."""
    import time
    import map_direct as md
    t = time.time()
    body = {'model': md.MODEL, 'store': False, 'reasoning': {'effort': md.EFFORT}, 'prompt_cache_key': f'math2-cards-{slug}',
            'text': {'format': {'type': 'json_schema', 'name': 'cards', 'schema': SCHEMA, 'strict': True}},
            'input': [md.msg('user', prompt)]}
    try:
        items, u = md.post(body)
        text = ''.join(c.get('text', '') for i in items if i.get('type') == 'message'
                       for c in i.get('content', []) if c.get('type') == 'output_text')
        result = json.loads(text)
    except Exception as e:  # noqa: BLE001 - reported per unit; a rerun picks it up
        return {'ok': False, 'error': str(e)}
    usage = {'input_tokens': u.get('input_tokens', 0),
             'cached_input_tokens': (u.get('input_tokens_details') or {}).get('cached_tokens', 0),
             'output_tokens': u.get('output_tokens', 0),
             'reasoning_output_tokens': (u.get('output_tokens_details') or {}).get('reasoning_tokens', 0)}
    return {'ok': True, 'result': result, 'usage': usage, 'seconds': round(time.time() - t, 1)}


def build(unit):
    slug = unit['unit'].replace('/', '_')
    out = OUT / f'{slug}.json'
    if out.exists():
        return unit['unit'], 'skip'
    book = {'LA': '线性代数（王宽程）', 'GS1': '高等数学上册（严亚强）',
            'GS2': '高等数学第二版下册（严亚强）', 'LALU': '线性代数：未竟之美（LaTeX 讲义）'}[unit['unit'].split('/')[0]]
    blocks = '\n'.join(f'{u} [{l}] {HTML_TAG.sub("", t).strip()}' for u, l, t in unit['blocks'])
    note = ('文本是讲义的 LaTeX 源码（每块是一个段落或一个定理类环境，类型中带书中编号，如 theorem 定理14.3）；'
            'label 请用书中编号。' if unit['unit'].startswith('LALU') else
            'OCR 文本可能有少量识别错误；个别块混有侧栏人物简介等旁注，那不是知识内容。')
    prompt = PROMPT.format(unit=unit['unit'], title=unit['title'], book=book, blocks=blocks, source_note=note)
    if unit['unit'].startswith('LA/'):
        r = run_direct(prompt, slug)
    else:
        r = run_codex(prompt, OUT / 'runs' / 'schema.json', OUT / 'runs' / f'{slug}.json')
    if not r['ok']:
        return unit['unit'], f'failed: {r["error"][:200]}'
    cards = r['result']['cards']
    problems = validate(unit, cards)
    for c in cards:
        c['card_id'] = f'{unit["unit"]}#{c["local_id"]}'
        c['unit'] = unit['unit']
        c['related'] = [f'{unit["unit"]}#{x}' for x in c['related']]
        text_norm.normalize_card(c)  # one spelling for labels / titles (originals kept as label_raw / title_raw)
    jsonsave(out, {'unit': unit['unit'], 'title': unit['title'], 'model': 'gpt-6-astra', 'usage': r['usage'],
                   'seconds': r['seconds'], 'block_count': len(unit['blocks']), 'problems': problems,
                   'cards': cards})
    return unit['unit'], f'{len(cards)} cards, {len(problems)} problems, {r["seconds"]}s'


def main():
    import map_direct as md
    _lock = md.single_api_process()  # noqa: F841 - never run next to another API process (≤4 requests in total)
    con = sqlite3.connect(DB)
    us = units(con)
    OUT.mkdir(parents=True, exist_ok=True)
    jsonsave(OUT / 'runs' / 'schema.json', SCHEMA)
    only = set(sys.argv[1:])
    us = [u for u in us if not only or u['unit'] in only]
    print('units:', [(u['unit'], len(u['blocks'])) for u in us], flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        for unit, status in ex.map(build, us):
            print(unit, status, flush=True)


if __name__ == '__main__':
    main()
