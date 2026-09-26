"""Render pilot results per question (A vs B) with the cited textbook text, for manual review."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import HTML_TAG, save  # noqa: E402
from pilot_map import OUT, QUESTIONS, question, load_blocks, verify  # noqa: E402


def clip(t, n=160):
    t = HTML_TAG.sub('', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t if len(t) <= n else t[:n] + '…'


def render(qid, rows, order):
    q = question(qid)
    out = [f'# {qid}\n', f'**题干**：{clip(q["stem"], 400)}\n', f'**解析**：{clip(q["solution"], 600)}\n']
    for cond in ('A', 'B'):
        f = OUT / cond / f'{qid}.json'
        if not f.exists():
            out.append(f'\n## {cond}：未完成\n')
            continue
        r = json.loads(f.read_text(encoding='utf-8'))
        u = r['usage']
        out.append(f'\n## {cond}（{len(r["commands"])} 条命令，输入 {u.get("input_tokens", 0):,}，'
                   f'输出 {u.get("output_tokens", 0):,}，{r["seconds"]}s）\n')
        for s in r['steps']:
            out.append(f'{s["n"]}. {clip(s["description"], 200)}')
        out.append('')
        for i, c in enumerate(r['citations'], 1):
            v, sec = verify(c, rows, order)
            s, e = sorted((order.get(c['start_uid'], 0), order.get(c['end_uid'], 0)))
            text = ' ‖ '.join(clip(x[2], 120) for x in rows[s:e + 1][:4]) if v != 'unknown_uid' else ''
            card = f' 卡片 `{c["card_id"]}`' if c['card_id'] else ''
            out.append(f'- **{cond}{i}** [{c["role"]}/{c["confidence"]}] 步骤{c["steps"]} **{c["knowledge"]}** '
                       f'`{c["start_uid"]}..{c["end_uid"]}` {sec} 校验:{v}{card}\n  > {text}')
        for n in r['not_in_textbook']:
            out.append(f'- 教材无对应：{n["knowledge"]}（查过：{clip(n["searched"], 120)}）')
        if r['notes']:
            out.append(f'\n备注：{clip(r["notes"], 300)}')
    return '\n'.join(out) + '\n'


def main():
    rows, order = load_blocks()
    qids = sys.argv[1:] or QUESTIONS
    text = '\n\n---\n\n'.join(render(q, rows, order) for q in qids)
    save(OUT / 'review.md', text)
    if sys.argv[1:]:
        print(text)


if __name__ == '__main__':
    main()
