#!/usr/bin/env python3
"""Question-type decision trees: material for writing them, and the parser the viz uses.

  python3 scripts/trees.py scopes             how many questions each tree covers (core method in its scope)
  python3 scripts/trees.py dump TREE [N]      the decisions of the questions in a tree, compact, for reading
  python3 scripts/trees.py check              parse output/thinking/trees.txt, report unknown method / question ids

The trees themselves are written by Claude in output/thinking/trees.txt:
  @ id | 名称 | 方法 id 或前缀（空格分隔，前缀以 * 结尾）
  一行说明
  ? 判断的问题                      — a decision node; its branches follow, indented two more spaces
    - 情形 => 方法id 方法id | 说明     — a branch: when, which methods, a short note; a branch may hold a nested "?"
  ! 常见误入：……                   — a pitfall line for the whole tree
Indentation is two spaces per level.
"""
from collections import Counter
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import methods as mt  # noqa: E402

OUT = ROOT / 'output/thinking'


def parse(path=OUT / 'trees.txt'):
    trees, stack = [], []
    for n, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not raw.strip() or raw.startswith('# '):
            continue
        line = raw.strip()
        ind = (len(raw) - len(raw.lstrip(' '))) // 2
        if line.startswith('@ '):
            tid, name, scope = [s.strip() for s in line[2:].split(' | ')]
            trees.append({'id': tid, 'n': name, 'scope': scope.split(), 'about': '', 'root': [], 'pit': []})
            stack = [(-1, trees[-1]['root'])]
            continue
        t = trees[-1]
        if line.startswith('! '):
            t['pit'].append(line[2:])
            continue
        if not line.startswith(('? ', '- ')):
            t['about'] += line
            continue
        while stack and stack[-1][0] >= ind:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith('? '):
            node = {'q': line[2:], 'br': []}
            parent.append(node)
            stack.append((ind, node['br']))
        else:
            when, _, rest = line[2:].partition('=>')
            ms, _, note = rest.partition('|')
            br = {'w': when.strip(), 'm': ms.split(), 'note': note.strip(), 'sub': [], 'line': n}
            parent.append(br)
            stack.append((ind, br['sub']))
    return trees


def in_scope(mid, scope):
    return any(mid == s or (s.endswith('*') and mid.startswith(s[:-1])) for s in scope)


def traces():
    out = {}
    for f in sorted((OUT / 'raw').glob('math2-*.json')):
        out[f.stem] = json.loads(f.read_text(encoding='utf-8'))['result']
    return out


def labels():
    out = {}
    for f in sorted((mt.OUT / 'raw').glob('math2-*.json')):
        out[f.stem] = json.loads(f.read_text(encoding='utf-8'))['result']['methods']
    return out


def members(tree, lab):
    return [q for q, ms in lab.items() if any(m['role'] == 'core' and in_scope(m['id'], tree['scope']) for m in ms)]


def cmd_scopes():
    lab = labels()
    covered = set()
    for t in parse():
        m = members(t, lab)
        covered |= set(m)
        print(f"{t['id']:12} {t['n']:16} {len(m):4}")
    print('questions in no tree:', len(set(lab) - covered))


def cmd_dump(tid, limit=0):
    t = next(x for x in parse() if x['id'] == tid)
    lab, tr = labels(), traces()
    qs = members(t, lab)
    qs = [q for q in qs if q in tr][: int(limit) or None]
    first, fails, pairs = Counter(), Counter(), Counter()
    for q in qs:
        r = tr[q]
        print(f"\n## {q}  core: {' '.join(m['id'] for m in lab[q] if m['role'] == 'core')}")
        for k, d in enumerate(r['decisions']):
            ch = next(o for o in d['options'] if o['verdict'] == 'chosen')
            if k == 0:
                first[ch['method'] or '-'] += 1
            print(f"  ? {d['ask']}\n    信号 {d['signals'][:160]}\n    ✓ {ch['label']} [{ch['method']}]")
            for o in d['options']:
                if o['verdict'] != 'chosen':
                    fails[o['method'] or '-'] += 1
                    pairs[(ch['method'] or '-', o['method'] or '-', o['verdict'])] += 1
                    print(f"    {'✗' if o['verdict'] == 'fails' else '△'} {o['label']} [{o['method']}] — {o['reason'][:120]}")
        print(f"  突破口 {r['breakthrough']['idea'][:160]}")
    print(f'\n# {len(qs)} questions; first chosen:', first.most_common(15))
    print('# rejected methods:', fails.most_common(15))
    print('# chosen vs rejected:', pairs.most_common(20))


def cmd_check():
    mids = {it['id'] for it in mt.taxonomy()}
    for t in parse():
        def walk(nodes):
            for x in nodes:
                if 'q' in x:
                    walk(x['br'])
                else:
                    bad = [m for m in x['m'] if m not in mids]
                    if bad:
                        print(f"{t['id']} line {x['line']}: unknown {bad}")
                    walk(x['sub'])
        walk(t['root'])
    print('checked', len(parse()), 'trees')


def export():
    """For build_viz.py: the trees with method ids turned into indices."""
    path = OUT / 'trees.txt'
    if not path.exists():
        return []
    idx = {it['id']: i for i, it in enumerate(mt.taxonomy())}

    def conv(nodes):
        out = []
        for x in nodes:
            if 'q' in x:
                out.append({'q': x['q'], 'b': conv(x['br'])})
            else:
                out.append({'w': x['w'], 'm': [idx[m] for m in x['m'] if m in idx], 'no': x['note'], 's': conv(x['sub'])})
        return out
    return [{'id': t['id'], 'n': t['n'], 'sc': t['scope'], 'ab': t['about'], 'r': conv(t['root']), 'pit': t['pit']}
            for t in parse()]


if __name__ == '__main__':
    cmd, *rest = sys.argv[1:] or ['scopes']
    {'scopes': cmd_scopes, 'dump': lambda: cmd_dump(*rest), 'check': cmd_check}[cmd]()
