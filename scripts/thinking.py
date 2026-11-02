#!/usr/bin/env python3
"""Thinking layer: for each exam question, the solving process as stages, decision points and the breakthrough idea.

  python3 scripts/thinking.py pilot [N] [ID ...]   label the methods pilot sample (N questions, default 20) plus IDs
  python3 scripts/thinking.py run [--workers K]    label all questions into output/thinking/raw/ (skips done ones)
  python3 scripts/thinking.py redo [all|ID ...]    relabel all or the given questions
  python3 scripts/thinking.py report [raw|pilot]   summarize the labels
  python3 scripts/thinking.py show ID [raw|pilot]  print one question's trace

Builds on the method layer (scripts/methods.py): the method table and the strategy list (output/thinking/strategies.txt,
written by Claude) go in one developer message so the relay caches them; the question, its reference solution, numbered
steps and its method labels are the user message. Output is strict JSON per question.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections import Counter
import json
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import jsonsave  # noqa: E402
import methods as mt  # noqa: E402

OUT = ROOT / 'output/thinking'
MODEL = mt.MODEL
EFFORT = 'medium'
WORKERS = 2              # the hard cap across everything is 4
CACHE_KEY = 'math2-thinking-v2'  # v2: ask must not hint at the chosen move; st-reduce only for real reductions
STAGES = ['审题定型', '转化化归', '执行计算', '收尾检验']


def strategies():
    items = []
    for raw in (OUT / 'strategies.txt').read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        sid, name, when = [s.strip() for s in line.split(' | ')]
        items.append({'id': sid, 'name': name, 'when': when})
    return items


PREFIX = '''你在为考研数学二真题写"解题思路轨迹"，用来训练学生面对陌生题目时的判断：此刻处于什么局面、看到了什么信号、
有哪几种可能的做法、为什么选这个、别的为什么不行。参考解答只给出了成品路线，你要还原出它背后的思考过程。

方法体系（id | 方法名 | 识别信号）：
{methods}

思想策略（id | 名称 | 什么时候想到它）：
{strategies}

对给你的题目输出：
1. stages：把解答步骤分到阶段（{stages}）。只列实际出现的阶段，按顺序；steps 是步骤号，goal 是这一阶段要达成的目标。
   简单题可以只有一两个阶段。
2. decisions：解题中真正需要做选择的地方，1–3 个，按先后顺序；纯计算、没有别的合理选择的步骤不算。每个决策：
   - step：开始实施这个选择的步骤号。
   - situation：此刻的局面——已知什么、已经得到什么、要达成什么。写给正在做题的学生看，不要透露选了哪种做法。
   - ask：自测时问学生的问题，只问"接下来从哪入手、怎么处理"，如"右端含 ξ、η，接下来怎么处理？"。
     不得出现所选做法的关键词或暗示（例如不能问"怎样构造辅助函数……""怎样把它们统一成同一个函数的导数"），
     否则学生不用思考就能选对。
   - signals：让人做出这个选择的具体信号（引用题目或当前式子的特征）。
   - options：3–4 个候选做法，恰好一个 verdict=chosen（参考解答实际采用的），其余是学生真会想到的做法：
     fails = 走不通，worse = 能做但明显更繁或易错。label 是一句话的做法（不超过 30 字，可含 $…$ 公式）；
     method 是对应的方法 id（没有合适的给空串）；reason 说明为什么选它，或为什么走不通、更繁——要具体，
     走不通的最好指出会卡在哪一步、得到什么。不要编造明显荒谬的选项凑数。
   - strategies：这个选择体现的思想策略 id（0–2 个）。st-reduce 只用于确实把非标准形式变形成已知题型的情形；
     直接认出标准题型、套用对应方法的，不标 st-reduce（没有合适的策略就给空数组）。
3. breakthrough：全题的突破口。idea 一句话写出关键想法；origin 说明怎样能想到它（从哪个信号、用什么思路）；
   strategies 为对应的策略 id。
4. traps：学生在这道题上常见的卡点或错误（0–3 条），step 为相关步骤号（无则 0），trap 写具体错在哪里。
5. comment：对方法体系或策略列表的意见，没有就给空字符串。
数学式写在 $…$ 里（LaTeX）。用中文回答。'''

SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['stages', 'decisions', 'breakthrough', 'traps', 'comment'], 'properties': {
    'stages': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
               'required': ['stage', 'steps', 'goal'], 'properties': {
                   'stage': {'type': 'string', 'enum': STAGES}, 'steps': {'type': 'array', 'items': {'type': 'integer'}},
                   'goal': {'type': 'string'}}}},
    'decisions': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                  'required': ['step', 'situation', 'ask', 'signals', 'options', 'strategies'], 'properties': {
                      'step': {'type': 'integer'}, 'situation': {'type': 'string'}, 'ask': {'type': 'string'},
                      'signals': {'type': 'string'},
                      'options': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                                  'required': ['label', 'method', 'verdict', 'reason'], 'properties': {
                                      'label': {'type': 'string'}, 'method': {'type': 'string'},
                                      'verdict': {'type': 'string', 'enum': ['chosen', 'fails', 'worse']},
                                      'reason': {'type': 'string'}}}},
                      'strategies': {'type': 'array', 'items': {'type': 'string'}}}}},
    'breakthrough': {'type': 'object', 'additionalProperties': False, 'required': ['idea', 'origin', 'strategies'],
                     'properties': {'idea': {'type': 'string'}, 'origin': {'type': 'string'},
                                    'strategies': {'type': 'array', 'items': {'type': 'string'}}}},
    'traps': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['step', 'trap'],
              'properties': {'step': {'type': 'integer'}, 'trap': {'type': 'string'}}}},
    'comment': {'type': 'string'}}}


def prefix():
    table, g = [], None
    for it in mt.taxonomy():
        if it['group'] != g:
            g = it['group']
            table.append(f'【{g}】')
        table.append(f"{it['id']} | {it['name']} | {it['signal']}")
    sts = '\n'.join(f"{s['id']} | {s['name']} | {s['when']}" for s in strategies())
    return PREFIX.format(methods='\n'.join(table), strategies=sts, stages='、'.join(STAGES))


def prompt(q):
    labels = mt.OUT / 'raw' / f"{q['id']}.json"
    me = json.loads(labels.read_text(encoding='utf-8'))['result']['methods'] if labels.exists() else []
    used = '\n'.join(f"- {m['id']}（{'关键' if m['role'] == 'core' else '顺带'}，步骤 {m['steps']}）：{m['why']}"
                     for m in me) or '（无）'
    return f'''{mt.prompt(q)}

## 已标注的方法
{used}'''


def check(res, q, mids, sids):
    """Problems the schema cannot catch: unknown ids, step numbers out of range, not exactly one chosen option."""
    n = len(q['steps'])
    bad = []
    for d in res['decisions']:
        if sum(o['verdict'] == 'chosen' for o in d['options']) != 1:
            bad.append(f"step {d['step']}: chosen != 1")
        bad += [f"method {o['method']}" for o in d['options'] if o['method'] and o['method'] not in mids]
        bad += [f'strategy {s}' for s in d['strategies'] if s not in sids]
        if not 1 <= d['step'] <= n:
            bad.append(f"step {d['step']} out of range")
    bad += [f'strategy {s}' for s in res['breakthrough']['strategies'] if s not in sids]
    bad += [f'stage step {s}' for st in res['stages'] for s in st['steps'] if not 1 <= s <= n]
    return bad


_workers, _wl = {}, threading.Lock()


def call(pre, user):
    md = mt._md()
    with _wl:
        w = _workers.setdefault(threading.get_ident(), len(_workers)) % WORKERS
    body = {'model': MODEL, 'store': False, 'reasoning': {'effort': EFFORT}, 'prompt_cache_key': f'{CACHE_KEY}-w{w}',
            'text': {'format': {'type': 'json_schema', 'name': 'thinking', 'schema': SCHEMA, 'strict': True}},
            'input': [md.msg('developer', pre), md.msg('user', user)]}
    items, usage = md.post(body)
    text = ''.join(c.get('text', '') for i in items if i.get('type') == 'message'
                   for c in i.get('content', []) if c.get('type') == 'output_text')
    return json.loads(text), usage


def label(qs, out_dir, redo=False):
    """Label the questions not yet in out_dir (all of qs with redo); failures are logged and left for a rerun."""
    md = mt._md()
    _lock = md.single_api_process()  # noqa: F841 - never next to another API process
    pre = prefix()
    mids = {it['id'] for it in mt.taxonomy()}
    sids = {s['id'] for s in strategies()}
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [q for q in qs if redo or not (out_dir / f"{q['id']}.json").exists()]
    md.log(f'{len(todo)}/{len(qs)} questions to trace with {MODEL} ({EFFORT}), {WORKERS} workers')
    done = [0]

    def one(q):
        try:
            res, usage = call(pre, prompt(q))
        except Exception as e:  # noqa: BLE001 - keep the others; a rerun picks it up
            md.log(f"{q['id']} failed: {e}")
            return
        bad = check(res, q, mids, sids)
        jsonsave(out_dir / f"{q['id']}.json", {'id': q['id'], 'model': MODEL, 'effort': EFFORT, 'cache_key': CACHE_KEY,
                                                'usage': usage, 'problems': bad, 'result': res})
        done[0] += 1
        md.log(f"[{done[0]}/{len(todo)}] {q['id']}: {len(res['decisions'])} decisions"
               f"{', PROBLEMS ' + '; '.join(bad) if bad else ''}, in {usage.get('input_tokens')} "
               f"(cached {usage.get('input_tokens_details', {}).get('cached_tokens')}) out {usage.get('output_tokens')}")
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))


def cmd_pilot(n, extra=()):
    qs = mt.questions()
    picked = mt.sample(qs, n)
    picked += [q for q in qs if q['id'] in extra and q not in picked]
    (OUT / 'pilot').mkdir(parents=True, exist_ok=True)
    jsonsave(OUT / 'pilot' / 'sample.json', [q['id'] for q in picked])
    label(picked, OUT / 'pilot')


def cmd_redo(ids):
    qs = mt.questions()
    ids = {q['id'] for q in qs} if ids == ['all'] else set(ids)
    label([q for q in qs if q['id'] in ids], OUT / 'raw', redo=True)


VERDICT = {'chosen': 0, 'fails': 1, 'worse': 2}


def export(qids):
    """For build_viz.py: the strategy list and, per question id with a trace (output/thinking/raw, else the pilot),
    {st: [[stage index, steps, goal]], d: [{s step, si situation, a ask, sg signals,
    o: [[label, method index or -1, 0 chosen | 1 fails | 2 worse, reason]], g: [strategy index]}],
    b: [idea, origin, [strategy index]], t: [[step, trap]]}."""
    sts = strategies()
    sidx = {s['id']: i for i, s in enumerate(sts)}
    midx = {it['id']: i for i, it in enumerate(mt.taxonomy())}
    per_q = {}
    for qid in qids:
        f = next((d / f'{qid}.json' for d in (OUT / 'raw', OUT / 'pilot') if (d / f'{qid}.json').exists()), None)
        if not f:
            continue
        r = json.loads(f.read_text(encoding='utf-8'))['result']
        per_q[qid] = {
            'st': [[STAGES.index(s['stage']), s['steps'], s['goal']] for s in r['stages']],
            'd': [{'s': d['step'], 'si': d['situation'], 'a': d['ask'], 'sg': d['signals'],
                   'o': [[o['label'], midx.get(o['method'], -1), VERDICT[o['verdict']], o['reason']] for o in d['options']],
                   'g': [sidx[g] for g in d['strategies'] if g in sidx]} for d in r['decisions']],
            'b': [r['breakthrough']['idea'], r['breakthrough']['origin'],
                  [sidx[g] for g in r['breakthrough']['strategies'] if g in sidx]],
            't': [[t['step'], t['trap']] for t in r['traps']]}
    return [{'id': s['id'], 'n': s['name'], 'w': s['when']} for s in sts], per_q


def cmd_report(sub='raw'):
    files = sorted((OUT / sub).glob('math2-*.json'))
    tin = tout = tcached = 0
    nd, verdicts, strat, stages, probs = Counter(), Counter(), Counter(), Counter(), []
    for f in files:
        d = json.loads(f.read_text(encoding='utf-8'))
        u, r = d['usage'], d['result']
        tin += u.get('input_tokens', 0)
        tout += u.get('output_tokens', 0)
        tcached += u.get('input_tokens_details', {}).get('cached_tokens', 0)
        nd[len(r['decisions'])] += 1
        for dec in r['decisions']:
            verdicts.update(o['verdict'] for o in dec['options'])
            strat.update(dec['strategies'])
        strat.update(r['breakthrough']['strategies'])
        stages.update(s['stage'] for s in r['stages'])
        if d['problems']:
            probs.append((d['id'], d['problems']))
    k = max(len(files), 1)
    print(f'{len(files)} questions; tokens in {tin} (cached {tcached}) out {tout}; per question in {tin // k} out {tout // k}')
    print('decisions per question:', sorted(nd.items()), '| options:', dict(verdicts))
    print('stages:', dict(stages))
    print('strategies:', ', '.join(f'{s}×{c}' for s, c in strat.most_common()))
    print('problems:', probs)


def cmd_show(qid, sub='raw'):
    r = json.loads((OUT / sub / f'{qid}.json').read_text(encoding='utf-8'))['result']
    print('阶段:', ' → '.join(f"{s['stage']}{s['steps']}（{s['goal']}）" for s in r['stages']))
    for d in r['decisions']:
        print(f"\n◆ 步骤 {d['step']}  {d['ask']}\n  局面：{d['situation']}\n  信号：{d['signals']}  {d['strategies']}")
        for o in d['options']:
            print(f"  [{o['verdict']}] {o['label']} ({o['method']})\n      {o['reason']}")
    b = r['breakthrough']
    print(f"\n突破口：{b['idea']}\n  怎么想到：{b['origin']}  {b['strategies']}")
    for t in r['traps']:
        print(f"卡点（步骤 {t['step']}）：{t['trap']}")
    if r['comment']:
        print('意见：', r['comment'])


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--workers' in args:  # at most 4: the relay's limit for everything running together
        i = args.index('--workers')
        WORKERS = min(int(args[i + 1]), 4)
        del args[i:i + 2]
    if '--effort' in args:
        i = args.index('--effort')
        EFFORT = args[i + 1]
        del args[i:i + 2]
    cmd, *rest = args or ['report']
    {'pilot': lambda: cmd_pilot(int(rest[0]) if rest else 20, rest[1:]), 'run': lambda: label(mt.questions(), OUT / 'raw'),
     'redo': lambda: cmd_redo(rest), 'report': lambda: cmd_report(*rest), 'show': lambda: cmd_show(*rest)}[cmd]()
