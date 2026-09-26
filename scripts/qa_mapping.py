"""Quality checks over the full mapping (output/mapping/final).

  python3 scripts/qa_mapping.py auto               structural checks on all questions -> output/mapping/qa/auto.json + .md
  python3 scripts/qa_mapping.py sample             stratified manual-review sample    -> output/mapping/qa/sample.json
  python3 scripts/qa_mapping.py show QID [QID...]   print a question with its citations/topics and the cited text
  python3 scripts/qa_mapping.py report             merge auto checks + manual judgments -> output/mapping/qa/质量核对报告.md
"""
from pathlib import Path
from collections import Counter, defaultdict
import json
import math
import random
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import HTML_TAG, save, jsonsave  # noqa: E402
import map_questions as mq  # noqa: E402

FINAL = mq.OUT / 'final'
QA = mq.OUT / 'qa'
OUT_OF_SCOPE = ('GS2/6', 'GS2/8/8.3', 'GS2/9', 'GS2/10')  # 数二 exclusions used for the card scope
SEED = 20260925


def load():
    qs = {q['question_id']: q for q in json.loads(mq.QINDEX.read_text(encoding='utf-8'))['questions']}
    res = {f.stem: json.loads(f.read_text(encoding='utf-8')) for f in FINAL.glob('math2-*.json')}
    return qs, res


def block_meta():
    con = sqlite3.connect(mq.DB)
    return {uid: (zone, sec, label, text, num) for uid, zone, sec, label, text, num in con.execute(
        'select uid, zone, coalesce(subsection, section, node), label, text, num_label from blocks')}


def wilson(k, n, z=1.96):
    if not n:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


# ---------- automatic checks ----------

def cmd_auto():
    qs, res = load()
    meta = block_meta()
    rows, order = mq.load_blocks()
    cards = mq.load_cards()
    issues = defaultdict(list)
    stats = defaultdict(Counter)
    for qid, r in sorted(res.items()):
        eng = r.get('engine', 'codex')
        st = stats[eng]
        st['questions'] += 1
        st['citations'] += len(r['citations'])
        steps = {s['n'] for s in r['steps']}
        if not r['citations']:
            issues['no_citations'].append(qid)
        if not any(t['relation'] == 'primary' for t in r['topics']):
            issues['no_primary_topic'].append(qid)
        if not any(c['role'] == 'core' for c in r['citations']) and r['citations']:
            issues['no_core_citation'].append(qid)
        for t in r['topics']:
            if not t.get('valid'):
                issues['invalid_topic_card'].append((qid, t['card_id']))
        book = 'LA' if r.get('subject') == 'LA' else 'GS'
        for c in r['citations']:
            st['role_' + c['role']] += 1
            st['conf_' + c['confidence']] += 1
            if c['verify'] not in ('ok', 'repaired', 'quote_fixed'):
                issues['quote_mismatch'].append((qid, c['start_uid'], c['end_uid'], c['quote'][:80]))
                continue
            s, e = sorted((order[c['start_uid']], order[c['end_uid']]))
            if e - s + 1 > 8:
                issues['long_span'].append((qid, c['start_uid'], c['end_uid'], e - s + 1))
            zones = {meta[rows[i][0]][0] for i in range(s, e + 1)}
            if zones - {'body', 'practice'}:
                issues['cites_non_body'].append((qid, c['start_uid'], sorted(zones), c['knowledge'][:40]))
            if 'practice' in zones:
                st['cites_practice'] += 1
            sec = c['section'] or ''
            if sec.startswith(OUT_OF_SCOPE):
                issues['out_of_scope_section'].append((qid, sec, c['knowledge'][:40], c['role']))
            if c['start_uid'].split('-')[0] not in (('LA', 'LALU') if book == 'LA' else ('GS1', 'GS2')):
                issues['wrong_book'].append((qid, c['start_uid'], c['knowledge'][:40]))
            if book == 'LA' and c['start_uid'].startswith('LALU') and '王宽程未见' not in c['why']:
                issues['lalu_without_reason'].append((qid, c['start_uid'], c['knowledge'][:40]))
            if not c.get('card_id'):
                issues['no_card'].append((qid, sec, c['knowledge'][:40]))
            bad_steps = set(c['steps']) - steps
            if bad_steps:
                issues['unknown_step'].append((qid, sorted(bad_steps)))
            if meta[c['start_uid']][2] in ('example', 'exercise_item') or re.match(r'^\s*例', meta[c['start_uid']][3] or ''):
                st['cites_example'] += 1
        for n in r['not_in_textbook']:
            issues['not_in_textbook'].append((qid, n['knowledge'][:80]))
    # source-flagged questions (answer/solution may itself be doubtful)
    for qid, q in qs.items():
        if q['review']['verdict'] in ('reference_issue', 'unresolved') or q['status'] != 'solved' or \
                q.get('repo_review', {}).get('verdict') in ('source_conflict', 'repository_issue'):
            issues['source_flagged'].append(qid)
    missing = sorted(set(qs) - set(res))
    out = {'questions': len(res), 'missing': missing, 'stats': {k: dict(v) for k, v in stats.items()},
           'issues': {k: v for k, v in issues.items()}}
    jsonsave(QA / 'auto.json', out)
    lines = ['# 自动检查结果\n', f'映射结果 {len(res)} 题，缺失 {len(missing)} 题。\n', '| 检查项 | 数量 |\n|---|---|']
    for k, v in sorted(issues.items(), key=lambda x: -len(x[1])):
        lines.append(f'| {k} | {len(v)} |')
    lines.append('\n## 两种引擎对比\n\n| 指标 | ' + ' | '.join(stats) + ' |\n|---|' + '---|' * len(stats))
    keys = sorted({k for v in stats.values() for k in v})
    for k in keys:
        vals = []
        for eng, v in stats.items():
            x = v.get(k, 0)
            vals.append(f'{x}' if k in ('questions', 'citations') else f'{x / max(v["questions"], 1):.2f}/题')
        lines.append(f'| {k} | ' + ' | '.join(vals) + ' |')
    save(QA / 'auto.md', '\n'.join(lines) + '\n')
    print('\n'.join(lines))


# ---------- manual review sample ----------

def era(y):
    return '1987-1996' if y <= 1996 else '1997-2009' if y <= 2009 else '2010-2026'


def cmd_sample():
    qs, res = load()
    auto = json.loads((QA / 'auto.json').read_text(encoding='utf-8'))
    rng = random.Random(SEED)
    strata = defaultdict(list)
    for qid, r in res.items():
        q = qs[qid]
        kind = '解答' if '解答' in q['section'] or q['section'] in ('计算题', '证明题') else '选择填空'
        strata[(r.get('subject', 'GS'), era(q['year']), kind)].append(qid)
    per = {('GS', e, k): 3 for e in ('1987-1996', '1997-2009', '2010-2026') for k in ('选择填空', '解答')}
    per.update({('LA', e, k): 2 for e in ('1997-2009', '2010-2026') for k in ('选择填空', '解答')})
    picked = []
    for key, n in sorted(per.items()):
        pool = sorted(strata.get(key, []))
        picked += [(qid, 'stratified:' + '/'.join(key)) for qid in rng.sample(pool, min(n, len(pool)))]
    flagged = sorted(set(auto['issues'].get('source_flagged', [])) & set(res))
    picked += [(qid, 'source_flagged') for qid in rng.sample(flagged, min(4, len(flagged)))
               if qid not in {p for p, _ in picked}]
    for key in ('no_citations', 'no_core_citation'):
        for qid in auto['issues'].get(key, [])[:3]:
            if qid not in {p for p, _ in picked}:
                picked.append((qid, key))
    jsonsave(QA / 'sample.json', {'seed': SEED, 'questions': [{'question_id': q, 'why': w} for q, w in picked]})
    print(len(picked), 'questions:', ' '.join(q for q, _ in picked))


# ---------- display for manual review ----------

def clip(t, n):
    t = re.sub(r'\s+', ' ', HTML_TAG.sub('', t or '')).strip()
    return t if len(t) <= n else t[:n] + '…'


def cmd_show(ids, width=260):
    qs, res = load()
    meta = block_meta()
    rows, order = mq.load_blocks()
    cards = mq.load_cards()
    for qid in ids:
        q, r = qs[qid], res[qid]
        print(f'\n######## {qid}  [{q["section"]}] engine={r.get("engine", "codex")} review={q["review"]["verdict"]}')
        print('题干:', clip(q['stem'], 500))
        print('答案:', clip(q['answer'], 200))
        print('解析:', clip(q['solution'], 700))
        for s in r['steps']:
            print(f'  step{s["n"]}: {clip(s["description"], 160)}')
        for i, c in enumerate(r['citations'], 1):
            s, e = sorted((order.get(c['start_uid'], 0), order.get(c['end_uid'], 0)))
            text = ' ‖ '.join(clip(rows[j][2], width) for j in range(s, min(e + 1, s + 3)))
            num = meta.get(c['start_uid'], (None,) * 5)[4]
            print(f'  C{i} [{c["role"]}/{c["confidence"]}] steps{c["steps"]} {c["knowledge"]}  '
                  f'{c["start_uid"]}..{c["end_uid"]} {c["section"]} {num or ""} verify={c["verify"]}\n      » {text}')
        for t in r['topics']:
            cd = cards.get(t['card_id'], {})
            print(f'  T[{t["relation"]}] {cd.get("label", "")} {cd.get("title", "?")} ({t["card_id"].split("#")[0]}) '
                  f'— {clip(t["reason"], 120)}')
        for n in r['not_in_textbook']:
            print('  NOT-IN-BOOK:', clip(n['knowledge'], 120))
        if r.get('topic_note'):
            print('  topic_note:', clip(r['topic_note'], 200))


# ---------- report ----------

def cmd_report():
    auto = json.loads((QA / 'auto.json').read_text(encoding='utf-8'))
    judg = json.loads((QA / 'judgments.json').read_text(encoding='utf-8'))
    qs, res = load()
    cit = Counter()
    q_ok = Counter()
    miss = 0
    topic = Counter()
    by_stratum = defaultdict(Counter)
    for qid, j in judg['questions'].items():
        for v in j['citations'].values():
            cit[v] += 1
        miss += len(j.get('missing_core', []))
        q_ok[j['overall']] += 1
        topic[j['topic']] += 1
        by_stratum[j.get('why', '')]['q'] += 1
    n = sum(cit.values())
    lines = ['# 映射质量核对报告\n', f'核对日期：2026-09-25。对象：`output/mapping/final/` 全部 {auto["questions"]} 题。\n',
             '## 一、全量自动检查\n', '| 检查项 | 数量 | 处理 |\n|---|---|---|']
    notes = judg.get('auto_notes', {})
    for k, v in sorted(auto['issues'].items(), key=lambda x: -len(x[1])):
        lines.append(f'| {k} | {len(v)} | {notes.get(k, "")} |')
    lines.append('\n## 二、分层人工抽查\n')
    lines.append(f'抽查 {len(judg["questions"])} 题、{n} 条引用（抽样方法见 `sample.json`，随机种子 {SEED}）。\n')
    lines.append('| 判定 | 条数 | 比例（95% CI） |\n|---|---|---|')
    for k in ('correct', 'imprecise', 'wrong'):
        p, lo, hi = wilson(cit[k], n)
        lines.append(f'| {k} | {cit[k]} | {p:.1%}（{lo:.1%}–{hi:.1%}） |')
    lines.append(f'\n漏掉的核心依据：{miss} 处。整题判定：' + '，'.join(f'{k} {v}' for k, v in q_ok.items())
                 + '。考查主题：' + '，'.join(f'{k} {v}' for k, v in topic.items()) + '。\n')
    lines.append('判定口径：correct = 区间直接陈述所述依据；imprecise = 知识点对，但区间偏移、过宽或选了次优段落（如例题而非定理）；'
                 'wrong = 所引段落不支持该步骤。\n')
    lines.append('## 三、逐题记录\n')
    for qid, j in judg['questions'].items():
        imp = '；'.join(f'{k} 不够精确：{v}' for k, v in j.get('imprecise_notes', {}).items())
        lines.append(f'- `{qid}`（{j.get("why", "")}）：{j["overall"]}，{len(j["citations"])} 条引用。'
                     f'{j.get("note", "")}{imp}')
    for sec in judg.get('sections', []):
        lines.append(f'\n## {sec["title"]}\n\n{sec["body"]}')
    save(QA / '质量核对报告.md', '\n'.join(lines) + '\n')
    print('\n'.join(lines[:30]))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'auto':
        cmd_auto()
    elif cmd == 'sample':
        cmd_sample()
    elif cmd == 'show':
        cmd_show(sys.argv[2:])
    elif cmd == 'report':
        cmd_report()
    else:
        print(__doc__)
