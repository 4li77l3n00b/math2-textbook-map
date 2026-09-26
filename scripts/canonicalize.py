"""Canonical-source review of doubtful citations (one astra call per batch of citations, no tool use).

A citation is doubtful when it does not touch the core blocks of the card it maps to, when it deviates from
the span most questions use for the same card, or when it cites an example/remark card. For each one astra
chooses, among the current span and a few candidate statements (the card's core, the most common span for
that card, and the most similar theorem/definition/formula cards of the same book), the passage that states
the knowledge used most directly — preferring the first formal statement over restatements, examples, remarks.

  python3 scripts/canonicalize.py select      list doubtful citations + candidates -> output/mapping/canonical/candidates.json
  python3 scripts/canonicalize.py run         judge them in batches            -> output/mapping/canonical/decisions.json
Decisions are applied as an overlay by `map_questions.py post` (raw results stay untouched).
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
from build_textbook_index import HTML_TAG, save, jsonsave  # noqa: E402
import map_questions as mq  # noqa: E402
import map_direct as md  # noqa: E402

OUT = mq.OUT / 'canonical'
BATCH = 8
WORKERS = 4
SIMILAR = 3
FORMAL = {'theorem', 'definition', 'formula', 'property', 'corollary', 'lemma', 'method', 'concept'}


def clip(t, n):
    t = re.sub(r'\s+', ' ', HTML_TAG.sub('', t or '')).strip()
    return t if len(t) <= n else t[:n] + '…'


def grams(t):
    t = re.sub(r'[\s$\\{}()（）,，.。:：、;；]', '', t or '')
    return {t[i:i + 2] for i in range(len(t) - 1)}


def sim(a, b):
    return len(a & b) / max(1, min(len(a), len(b)))


def card_span(cd, order, rows):
    idx = sorted(order[u] for u in cd['statement_uids'] if u in order) or \
        sorted((order[cd['start_uid']], order[cd['end_uid']]))
    return rows[idx[0]][0], rows[idx[-1]][0]


def span_text(s_uid, e_uid, order, rows, n=600):
    s, e = sorted((order[s_uid], order[e_uid]))
    return clip(' ‖ '.join(r[2] for r in rows[s:e + 1]), n)


def cmd_select():
    rows, order = mq.load_blocks()
    cards = mq.load_cards()
    card_grams = {cid: grams(' '.join([cd['label'], cd['title'], cd['summary'], ' '.join(cd['keywords'])]))
                  for cid, cd in cards.items()}
    res = [json.loads(f.read_text(encoding='utf-8')) for f in sorted((mq.OUT / 'final').glob('math2-*.json'))]

    def spanset(s, e):
        a, b = sorted((order[s], order[e]))
        return set(range(a, b + 1))
    usage = defaultdict(Counter)
    for r in res:
        for c in r['citations']:
            if c.get('card_id'):
                usage[c['card_id']][(c['start_uid'], c['end_uid'])] += 1
    items, why = [], Counter()
    for r in res:
        steps = {s['n']: s['description'] for s in r['steps']}
        for i, c in enumerate(r['citations']):
            cid = c.get('card_id')
            if not cid or c.get('source') == 'manual_qa':
                continue
            cd = cards[cid]
            reasons = []
            if c.get('card_match') in ('span', 'nearest'):
                reasons.append('off_card_core')
            if cd['kind'] in ('example', 'remark'):
                reasons.append('example_or_remark')
            if sum(usage[cid].values()) >= 3:
                modal = usage[cid].most_common(1)[0][0]
                cur = spanset(c['start_uid'], c['end_uid'])
                mset = spanset(*modal)
                if not (cur <= mset or mset <= cur):
                    reasons.append('deviates_from_common_span')
            if not reasons:
                continue
            for x in reasons:
                why[x] += 1
            # candidate passages
            opts = [('current', cid, c['start_uid'], c['end_uid'])]
            seen = {(c['start_uid'], c['end_uid'])}

            def add(kind, card_id, s, e):
                if (s, e) not in seen:
                    seen.add((s, e))
                    opts.append((kind, card_id, s, e))
            add('card_core', cid, *card_span(cd, order, rows))
            if sum(usage[cid].values()) >= 3:
                add('common_span', cid, *usage[cid].most_common(1)[0][0])
            g = grams(c['knowledge'] + ' ' + c['why'])
            book = c['start_uid'].split('-')[0]
            ranked = sorted(((sim(g, card_grams[k]), k) for k, v in cards.items()
                             if k.split('/')[0] == book and v['kind'] in FORMAL and k != cid), reverse=True)
            for _, k in ranked[:SIMILAR]:
                add('similar_card', k, *card_span(cards[k], order, rows))
            if len(opts) == 1:
                continue
            items.append({
                'id': f'{r["question_id"]}#{i}', 'question_id': r['question_id'], 'index': i, 'reasons': reasons,
                'knowledge': c['knowledge'], 'role': c['role'], 'why': c['why'],
                'step': ' / '.join(steps.get(n, '') for n in c['steps'])[:400],
                'options': [{'n': j, 'kind': k, 'card_id': cc, 'label': cards[cc]['label'],
                             'title': cards[cc]['title'], 'card_kind': cards[cc]['kind'],
                             'start_uid': s, 'end_uid': e, 'section': rows[order[s]][3],
                             'text': span_text(s, e, order, rows)}
                            for j, (k, cc, s, e) in enumerate(opts)]})
    OUT.mkdir(parents=True, exist_ok=True)
    jsonsave(OUT / 'candidates.json', {'reasons': dict(why), 'items': items})
    print(len(items), 'doubtful citations', dict(why), 'options/item',
          round(sum(len(x['options']) for x in items) / max(1, len(items)), 1))


SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['decisions'],
          'properties': {'decisions': {'type': 'array', 'items': {
              'type': 'object', 'additionalProperties': False,
              'required': ['id', 'choice', 'confidence', 'reason'],
              'properties': {'id': {'type': 'string'}, 'choice': {'type': 'integer'},
                             'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                             'reason': {'type': 'string'}}}}}}

PROMPT = '''你在核对“考研真题解题步骤 → 教材原文”的引用出处。每条引用给出：解题步骤、所用知识、当前引用的原文（选项 0），以及若干候选原文（选项 1 起）。请为每条引用选出**最直接、最规范地陈述该知识**的一段原文。

规则：
1. 选的原文必须陈述步骤实际用到的那条知识；候选若说的是别的知识，不能选。
2. 同一结论在书中多处出现时（公式汇总表、推导它的例题、注释、后文或另一册的复述、章末回顾），选首次正式陈述它的定理/定义/公式/命题。
3. 书中若只在例题或注中讲到这条知识（没有一般性陈述），就保留例题或注。
4. 二级结论本身被使用时（如常见函数的麦克劳林公式、等价无穷小表），引用该二级结论，不要换成推出它的更基础的定理。
5. 当前引用已经是最佳出处时选 0。拿不准时选 0。
6. 教材是 OCR 文本或 LaTeX 源码，可能有少量识别错误。只输出 JSON。

{items}
'''


def render(item):
    lines = [f'### 引用 {item["id"]}', f'解题步骤：{item["step"]}', f'所用知识：{item["knowledge"]}（{item["role"]}）',
             f'引用理由：{clip(item["why"], 200)}']
    for o in item['options']:
        lab = f'{o["label"]} ' if o['label'] else ''
        lines.append(f'- 选项 {o["n"]}（{o["kind"]}，卡片[{o["card_kind"]}] {lab}{o["title"]}，{o["section"]}）：{o["text"]}')
    return '\n'.join(lines)


_workers = {}
_workers_lock = threading.Lock()


def worker_index():
    with _workers_lock:
        return _workers.setdefault(threading.get_ident(), len(_workers)) % WORKERS


def judge(batch):
    body = {'model': md.MODEL, 'store': False, 'reasoning': {'effort': md.EFFORT},
            'prompt_cache_key': f'math2-canonical-v1-w{worker_index()}',  # one key per worker: the relay
                                                                          # rejects concurrent use of a key
            'text': {'format': {'type': 'json_schema', 'name': 'canonical', 'schema': SCHEMA, 'strict': True}},
            'input': [md.msg('user', PROMPT.format(items='\n\n'.join(render(x) for x in batch)))]}
    items, usage = md.post(body)
    text = ''.join(c.get('text', '') for i in items if i.get('type') == 'message'
                   for c in i.get('content', []) if c.get('type') == 'output_text')
    return json.loads(text)['decisions'], usage


def cmd_run():
    _lock = md.single_api_process()  # noqa: F841 - never run next to another API process
    data = json.loads((OUT / 'candidates.json').read_text(encoding='utf-8'))
    done_path = OUT / 'decisions.json'
    done = json.loads(done_path.read_text(encoding='utf-8')) if done_path.exists() else {'decisions': {}, 'usage': {}}
    todo = [x for x in data['items'] if x['id'] not in done['decisions']]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    by_id = {x['id']: x for x in data['items']}
    usage = Counter(done['usage'])

    def one(b):
        try:
            return b, judge(b)
        except Exception as e:  # noqa: BLE001 - keep the others; rerun picks the batch up again
            md.log(f'batch failed: {e}')
            return b, None
    with ThreadPoolExecutor(WORKERS) as ex:
        for b, out in ex.map(one, batches):
            if not out:
                continue
            decisions, u = out
            usage['input_tokens'] += u.get('input_tokens', 0)
            usage['cached_input_tokens'] += (u.get('input_tokens_details') or {}).get('cached_tokens', 0)
            usage['output_tokens'] += u.get('output_tokens', 0)
            for d in decisions:
                item = by_id.get(d['id'])
                if not item or not 0 <= d['choice'] < len(item['options']):
                    continue
                o = item['options'][d['choice']]
                done['decisions'][d['id']] = {**d, 'question_id': item['question_id'], 'index': item['index'],
                                              'from': [item['options'][0]['start_uid'], item['options'][0]['end_uid']],
                                              'to': [o['start_uid'], o['end_uid']], 'to_card': o['card_id'],
                                              'to_kind': o['kind']}
            done['usage'] = dict(usage)
            jsonsave(done_path, done)
            md.log(f'{len(done["decisions"])}/{len(data["items"])} judged')
    changed = Counter(d['to_kind'] for d in done['decisions'].values())
    print('decisions', len(done['decisions']), dict(changed), 'usage', dict(usage))


if __name__ == '__main__':
    {'select': cmd_select, 'run': cmd_run}.get(sys.argv[1] if len(sys.argv) > 1 else '', lambda: print(__doc__))()
