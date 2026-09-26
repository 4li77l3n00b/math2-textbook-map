"""Pilot: map exam questions to textbook passages, A = navigate the book only, B = knowledge cards + book.

  python3 scripts/pilot_map.py run [A|B] [QUESTION_ID ...]   run (skips finished jobs)
  python3 scripts/pilot_map.py check                         verify spans/quotes, write summary
"""
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import HTML_TAG, save, jsonsave  # noqa: E402
from codex_run import run_codex  # noqa: E402

DB = ROOT / 'output/textbook/textbook_index.sqlite'
QINDEX = ROOT / 'output/astra/question_index.json'
OUT = ROOT / 'output/pilot'
WORKERS = 3
QUESTIONS = [
    # 高数上册第3章：中值定理、泰勒、洛必达、单调/极值/凹凸/曲率
    'math2-2020-q6', 'math2-2015-q21', 'math2-2023-q21', 'math2-2022-q21', 'math2-2019-q6',
    'math2-2021-q4', 'math2-2018-q12', 'math2-1989-II-03', 'math2-1996-III-04', 'math2-2003-X',
    # 线性代数第4章：特征值、相似、对角化、实对称（2015-q8 为二次型，测跨章）
    'math2-2007-q24', 'math2-2012-q8', 'math2-2016-q7', 'math2-2017-q8', 'math2-2018-q7',
    'math2-2020-q8', 'math2-2004-q23', 'math2-2009-q14', 'math2-2015-q8',
]

SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['steps', 'citations', 'not_in_textbook', 'notes'],
    'properties': {
        'steps': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['n', 'description'],
            'properties': {'n': {'type': 'integer'}, 'description': {'type': 'string'}}}},
        'citations': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['steps', 'knowledge', 'role', 'card_id', 'start_uid', 'end_uid', 'quote', 'why',
                         'confidence'],
            'properties': {
                'steps': {'type': 'array', 'items': {'type': 'integer'}},
                'knowledge': {'type': 'string'},
                'role': {'type': 'string', 'enum': ['core', 'auxiliary', 'prerequisite']},
                'card_id': {'type': 'string'},
                'start_uid': {'type': 'string'}, 'end_uid': {'type': 'string'},
                'quote': {'type': 'string'}, 'why': {'type': 'string'},
                'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']}}}},
        'not_in_textbook': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['steps', 'knowledge', 'searched'],
            'properties': {'steps': {'type': 'array', 'items': {'type': 'integer'}},
                           'knowledge': {'type': 'string'}, 'searched': {'type': 'string'}}}},
        'notes': {'type': 'string'}},
}

COMMON = '''你是一名做完考研数学二真题的学生，现在要“翻教材”，把这道题解答中用到的每一条知识依据落实到教材原文的具体段落。

## 题目 {qid}
{stem}

## 参考答案
{answer}

## 参考解析
{solution}

## 教材查询工具（只读）
在工作目录运行 `python3 scripts/textbook_cli.py <子命令>`：
- `toc [LA|GS1|GS2] [--depth N]`：目录与节点 id（LA 线性代数，GS1 高等数学上册，GS2 高等数学下册）
- `read NODE_ID [--from UID] [--limit N]`：按阅读顺序读某节正文块
- `blocks UID [UID_END] [--context K]`：读指定块/区间（可带上下文）
- `search 关键词 [--book B]`：全文检索（多个词用空格分隔，表示同时包含）
{card_tools}
每个块形如 `GS1-p144-b23 文本`，uid 是引用的依据。OCR 文本可能有少量识别错误。

## 做法
1. 把参考解析拆成若干步骤（steps），每步写清用了什么数学依据；解析省略的隐含依据也要补出（如“闭区间连续函数可取到最值”）。
2. 像人翻书一样查找：{strategy}读原文确认后再引用。解题用到其他章节的工具时（如求极限用泰勒公式），要去对应章节找，不要只停留在题目“所属”的章节。
3. 为每条依据给出一个引用：
   - start_uid..end_uid：教材中直接陈述该依据的**连续**块区间，尽量小（通常 1–5 块，定理/定义/公式本身，而非整节）；优先引用定义、定理、公式、书中明确讲的方法；只有书中没有一般性陈述、只在例题里出现时才引用例题。
   - quote：从区间内原文**逐字**摘出的一句（10–80 字，照抄 OCR 文本，包括其中的 LaTeX），用于核验；
   - knowledge 用书中的叫法；role：core（本题考查的核心）/ auxiliary（辅助工具）/ prerequisite（前置概念）；
   - card_id：{card_field}
4. 粒度：只引用大学高等数学/线性代数课程层面的知识（概念、定理、公式、法则、书中讲的方法）。中学层面的代数与初等函数运算（对数/指数运算律、不等式同乘除正数、解代数方程、三角恒等式、配方等）不必引用，也不要列入 not_in_textbook，除非它恰是本题考查的重点。同一知识在多步使用时只引用一次（steps 里列出所有步号）。
5. 教材里确实找不到的课程层面依据放入 not_in_textbook，写明查过哪些地方；不要勉强凑一个不相干的段落。
6. 查找要高效：通常 10–20 条命令内完成，读节时先看开头定位，不必通读整节。
7. 只使用上述工具命令，不要读取或修改项目中的其他文件。最后直接输出 JSON。
'''

A_TOOLS = ''
A_STRATEGY = '先看目录定位可能的章节，再用 read 或 search 找到具体段落，'
A_CARD = '本次不可用，一律填空串。'
B_TOOLS = ('- `cards [NODE_ID]`：列出某节（或全部）的知识卡片（卡片是按书整理的索引，含书中编号、概要和原文块区间）\n'
           '- `card CARD_ID`：查看一张卡片及其原文\n'
           '知识卡片目前只覆盖 GS1 第3章与 LA 第4章；其他章节请直接读原文。\n')
B_STRATEGY = '先看目录，对有卡片的章节先用 cards 找到对应卡片，再用 card/blocks 读原文；没有卡片的章节用 read 或 search，'
B_CARD = '引用与某张卡片对应时填其 card_id（引用区间应落在该卡片区间内或与其核心块重合），否则填空串。'


def question(qid):
    for q in json.loads(QINDEX.read_text(encoding='utf-8'))['questions']:
        if q['question_id'] == qid:
            return q
    raise KeyError(qid)


def run_one(cond, qid):
    out = OUT / cond / f'{qid}.json'
    if out.exists():
        return cond, qid, 'skip'
    q = question(qid)
    prompt = COMMON.format(qid=qid, stem=q['stem'], answer=q['answer'], solution=q['solution'],
                           card_tools=B_TOOLS if cond == 'B' else A_TOOLS,
                           strategy=B_STRATEGY if cond == 'B' else A_STRATEGY,
                           card_field=B_CARD if cond == 'B' else A_CARD)
    config = ['shell_environment_policy.set.TEXTBOOK_NO_CARDS="1"'] if cond == 'A' else []
    r = run_codex(prompt, OUT / 'schema.json', OUT / cond / 'runs' / f'{qid}.json', config=config)
    if not r['ok']:
        save(OUT / cond / f'{qid}.err.txt', r['error'] or '')
        return cond, qid, f'failed: {(r["error"] or "")[:150]}'
    jsonsave(out, {'question_id': qid, 'condition': cond, 'usage': r['usage'], 'seconds': r['seconds'],
                   'commands': r['commands'], **r['result']})
    return cond, qid, f'{len(r["result"]["citations"])} citations, {r["seconds"]}s'


def cmd_run(args):
    conds = [a for a in args if a in ('A', 'B')] or ['A', 'B']
    qids = [a for a in args if a.startswith('math2-')] or QUESTIONS
    jsonsave(OUT / 'schema.json', SCHEMA)
    jobs = [(c, q) for q in qids for c in conds]
    with ThreadPoolExecutor(WORKERS) as ex:
        for cond, qid, status in ex.map(lambda j: run_one(*j), jobs):
            print(cond, qid, status, flush=True)


# ---------- verification ----------

def squash(t):
    t = HTML_TAG.sub('', t)
    return re.sub(r'[\s$\u200b-\u200f\ufeff]', '', t)


def load_blocks():
    con = sqlite3.connect(DB)
    rows = con.execute("select uid, book, text, coalesce(subsection, section, node), zone from blocks "
                       "where trim(text) != '' order by book, pdf_page, block_id").fetchall()
    order = {}
    for i, (uid, book, *_rest) in enumerate(rows):
        order[uid] = i
    return rows, order


def verify(c, rows, order):
    s, e = order.get(c['start_uid']), order.get(c['end_uid'])
    if s is None or e is None:
        return 'unknown_uid', None
    if s > e:
        s, e = e, s
    if rows[s][1] != rows[e][1]:
        return 'cross_book', None
    if e - s > 12:
        return 'span_too_long', rows[s][3]
    text = squash(''.join(r[2] for r in rows[s:e + 1]))
    return ('ok' if squash(c['quote']) and squash(c['quote']) in text else 'quote_mismatch'), rows[s][3]


def cmd_check():
    rows, order = load_blocks()
    cards = {}
    for f in (ROOT / 'output/textbook/cards').glob('*_*.json'):
        for c in json.loads(f.read_text(encoding='utf-8'))['cards']:
            cards[c['card_id']] = c
    summary = {'A': defaultdict(Counter), 'B': defaultdict(Counter)}
    table = []
    for cond in ('A', 'B'):
        for f in sorted((OUT / cond).glob('math2-*.json')):
            r = json.loads(f.read_text(encoding='utf-8'))
            st = summary[cond]
            u = r['usage']
            st['usage']['input'] += u.get('input_tokens', 0)
            st['usage']['cached'] += u.get('cached_input_tokens', 0)
            st['usage']['output'] += u.get('output_tokens', 0)
            st['usage']['seconds'] += r['seconds']
            st['usage']['questions'] += 1
            st['usage']['commands'] += len(r['commands'])
            if cond == 'A' and any(' card' in x['command'] for x in r['commands']):
                st['leak']['card_command_in_A'] += 1
            for c in r['citations']:
                v, sec = verify(c, rows, order)
                c['_verify'], c['_section'] = v, sec
                st['verify'][v] += 1
                st['role'][c['role']] += 1
                if cond == 'B':
                    st['card'][('with_card' if c['card_id'] else 'no_card')] += 1
                    if c['card_id'] and c['card_id'] not in cards:
                        st['card']['unknown_card'] += 1
                    elif c['card_id']:
                        cd = cards[c['card_id']]
                        inside = order.get(cd['start_uid'], -1) <= order.get(c['start_uid'], -2) <= \
                            order.get(c['end_uid'], -3) <= order.get(cd['end_uid'], -4)
                        st['card']['span_inside_card' if inside else 'span_outside_card'] += 1
            st['count']['citations'] += len(r['citations'])
            st['count']['not_in_textbook'] += len(r['not_in_textbook'])
            jsonsave(OUT / cond / 'checked' / f.name, r)
            table.append((r['question_id'], cond, len(r['citations']), len(r['not_in_textbook']),
                          sum(c['_verify'] == 'ok' for c in r['citations']), u.get('input_tokens', 0),
                          u.get('output_tokens', 0), r['seconds'], len(r['commands'])))
    out = {c: {k: dict(v) for k, v in s.items()} for c, s in summary.items()}
    jsonsave(OUT / 'check_summary.json', {'summary': out, 'per_question': table})
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    if sys.argv[1:2] == ['run']:
        cmd_run(sys.argv[2:])
    elif sys.argv[1:2] == ['check']:
        cmd_check()
    else:
        print(__doc__)
