"""Index the LaTeX lecture notes 《线性代数：未竟之美》(LALU) at paragraph/environment granularity.

Source: source/LALU (git clone of github.com/yhwu-is/Linear-Algebra-Left-Undone, branch `new`, commit pinned below).
Only the 25 main-line chapters (讲义/专题/*.tex) are indexed; 未竟专题 are compiled (for correct page numbers) but not
indexed.

Blocks: every theorem-like environment is a block (long proofs/solutions/examples are split at their own
paragraph breaks), every top-level paragraph is a block, every exercise item is a block, and headings are
blocks. To recover the book's numbering (定理14.3) and pages, a scratch copy of the sources gets an invisible
`\\LALUB{uid}` marker at each block, is compiled once with xelatex, and the .aux is read back. The marker also
records, at shipout, the PDF page and the position of the block's start (`tex_pos`: x, y in TeX pt from the page's
bottom-left; a marker that opens a paragraph gives that line's baseline), used by the offline visualisation.

  python3 scripts/build_lalu_index.py        -> output/textbook/lalu/{blocks.jsonl,toc.json,LALU.pdf,构建报告.md}
"""
from pathlib import Path
from collections import Counter
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import save, jsonsave, jsonl, norm_text  # noqa: E402

SRC = ROOT / 'source/LALU'
OUT = ROOT / 'output/textbook/lalu'
BUILD = OUT / 'build'
MAIN = '线性代数荣誉课辅学讲义.tex'
COMMIT = '3bfd91c05a77411e132c2bfcce04a8042a74a84e'
BOOK = 'LALU'

NUMBERED = {'definition': '定义', 'example': '例', 'lemma': '引理', 'theorem': '定理', 'corollary': '推论',
            'axiom': '公理'}
UNNUMBERED = {'proof': '证明', 'solution': '解', 'summary': '内容总结'}
THEOREMLIKE = set(NUMBERED) | set(UNNUMBERED)
SPLITTABLE = {'proof', 'solution', 'example', 'summary'}  # long ones are split at their paragraph breaks
SPLIT_MIN_LINES = 12
HEADING_START = re.compile(r'^\s*\\(chapter|section|subsection|subsubsection)(\*?)\s*(?:\[[^\]]*\])?\s*\{')


def match_heading(line):
    """(level, star, title) for a sectioning line; the title is the brace-balanced first argument."""
    m = HEADING_START.match(line)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(line) and depth:
        depth += {'{': 1, '}': -1}.get(line[i], 0) if line[i - 1] != '\\' else 0
        i += 1
    if depth:
        return None
    title = re.sub(r'\\quad|~', ' ', line[m.end():i - 1]).strip()
    return None, m[1], m[2], title  # indexed like a regex match: [1] level, [2] star, [3] title
ENV = re.compile(r'\\(begin|end)\{([a-zA-Z*]+)\}')


def strip_comment(line):
    out, i = [], 0
    while i < len(line):
        ch = line[i]
        if ch == '\\' and i + 1 < len(line):
            out.append(line[i:i + 2])
            i += 2
            continue
        if ch == '%':
            break
        out.append(ch)
        i += 1
    return ''.join(out).rstrip()


def chapter_files():
    files = []
    for f in (SRC / '讲义/专题').glob('*.tex'):
        m = re.match(r'(\d+) (.+)\.tex$', f.name)
        files.append((int(m[1]), m[2], f))
    return sorted(files)


class Parser:
    """Split one chapter file into blocks and remember where to inject markers."""

    def __init__(self, chap, path):
        self.chap, self.path = chap, path
        self.raw = path.read_text(encoding='utf-8').split('\n')
        self.blocks, self.inject = [], {}  # inject: line index -> [(where, marker)]
        self.cur = None
        self.pending = None  # (env, part) of a split environment waiting for its next paragraph

    def uid(self):
        return f'{BOOK}-c{self.chap:02d}-b{len(self.blocks):04d}'

    def start(self, i, kind, zone, env=None, part=1):
        self.cur = {'uid': self.uid(), 'kind': kind, 'env': env, 'part': part, 'zone': zone,
                    'line_start': i + 1, 'lines': []}
        self.blocks.append(self.cur)
        return self.cur['uid']

    def mark(self, i, where, uid):
        self.inject.setdefault(i, []).append((where, uid))

    def close(self, i):
        if self.cur:
            self.cur['line_end'] = i
            self.cur = None

    def parse(self):
        stack = []
        zone = 'body'
        for i, raw in enumerate(self.raw):
            line = strip_comment(raw)
            top = stack[-1] if stack else None
            h = match_heading(line)
            if h and not stack:
                self.close(i)
                uid = self.start(i, 'heading', zone)
                self.cur.update(level=h[1], starred=bool(h[2]), title=h[3])
                self.cur['lines'].append(line)
                if not h[2]:
                    self.mark(i, 'after', uid)
                self.close(i + 1)
                continue
            events = ENV.findall(line)
            if not line.strip():
                if not stack:
                    self.close(i)
                elif (len(stack) == 1 and top in SPLITTABLE and self.cur
                      and len(self.cur['lines']) >= SPLIT_MIN_LINES):
                    part = self.cur['part'] + 1
                    self.close(i)
                    self.pending = (top, part)
                elif self.cur:
                    self.cur['lines'].append(line)
                continue
            begins = [e for b, e in events if b == 'begin']
            # new block?
            if not stack:
                if begins and begins[0] in THEOREMLIKE:
                    self.close(i)
                    uid = self.start(i, begins[0], zone, env=begins[0])
                    self.mark(i, 'after_numbered' if begins[0] in NUMBERED else 'after', uid)
                elif begins and begins[0] == 'exercise':
                    self.close(i)
                    zone = 'exercises'
                elif self.cur is None:
                    uid = self.start(i, 'paragraph', zone)
                    self.mark(i, 'before', uid)
            elif len(stack) == 1 and self.cur is None and self.pending:
                env, part = self.pending
                uid = self.start(i, env, zone, env=env, part=part)
                self.mark(i, 'before', uid)
                self.pending = None
            elif top == 'exgroup' and re.match(r'^\s*\\item\b', line):
                self.close(i)
                uid = self.start(i, 'exercise_item', 'exercises')
                self.mark(i, 'item', uid)
            if self.cur is not None:
                self.cur['lines'].append(line)
            for b, e in events:
                if b == 'begin':
                    stack.append(e)
                elif stack and stack[-1] == e:
                    stack.pop()
                    if e == 'exercise':
                        zone = 'body'
                        self.close(i + 1)
                    elif e == 'exgroup':
                        self.close(i + 1)
            if not stack and self.cur and self.cur['kind'] in THEOREMLIKE:
                self.close(i + 1)  # the environment (or its last part) ended on this line
        self.close(len(self.raw))
        for b in self.blocks:
            b['text'] = '\n'.join(b.pop('lines')).strip()
        self.blocks = [b for b in self.blocks if b['text'] or b['kind'] == 'heading']
        return self

    def injected(self):
        out = []
        for i, raw in enumerate(self.raw):
            marks = self.inject.get(i, [])
            for where, uid in marks:
                if where == 'before':
                    out.append(f'\\LALUB{{{uid}}}%')
            line = raw
            for where, uid in marks:
                if where == 'item':
                    m = re.match(r'^(\s*\\item\s*(?:\[[^\]]*\])?)', line)
                    line = line[:m.end()] + f'\\LALUB{{{uid}}}' + line[m.end():]
            out.append(line)
            for where, uid in marks:
                if where == 'after':
                    out.append(f'\\LALUB{{{uid}}}%')
                elif where == 'after_numbered':
                    out.append(f'\\LALUBT{{{uid}}}%')
        return '\n'.join(out)


PREAMBLE = r'''
\makeatletter
\newcommand\lalupdfpage[2]{}
\newcommand\lalunum[2]{}
\newcommand\lalupos[3]{}
% absolute PDF page and position of the marker, both taken when the page ships out. \protected@write expands its
% text right away (at typesetting time, when the page may not be decided yet), so these must be \noexpand'ed.
% At shipout \ReadonlyShipoutCounter already counts the page being shipped.
\newcommand\LALUB[1]{\label{LALUB:#1}\pdfsavepos\protected@write\@auxout{}{\string\lalupdfpage{#1}{\noexpand\the\ReadonlyShipoutCounter}\string\lalupos{#1}{\noexpand\the\pdflastxpos}{\noexpand\the\pdflastypos}}}
% inside a numbered tcolorbox theorem the box number is \thetcbcounter (\label would see the section)
\newcommand\LALUBT[1]{\edef\lalu@n{\thetcbcounter}\protected@write\@auxout{}{\string\lalunum{#1}{\lalu@n}}\LALUB{#1}}
\makeatother
'''


def compile_marked(parsers):
    if BUILD.exists():
        shutil.rmtree(BUILD)
    shutil.copytree(SRC, BUILD, ignore=shutil.ignore_patterns('.git'))
    for p in parsers:
        (BUILD / '讲义/专题' / p.path.name).write_text(p.injected(), encoding='utf-8')
    main = (BUILD / '讲义' / MAIN).read_text(encoding='utf-8')
    main = main.replace('\\begin{document}', PREAMBLE + '\\begin{document}', 1)
    (BUILD / '讲义/LALU.tex').write_text(main, encoding='utf-8')
    r = subprocess.run(['latexmk', '-xelatex', '-shell-escape', '-interaction=nonstopmode', '-file-line-error',
                        'LALU.tex'], cwd=BUILD / '讲义', capture_output=True, text=True, timeout=3000)
    aux = (BUILD / '讲义/LALU.aux').read_text(encoding='utf-8')
    errors = re.findall(r'^\S+:\d+: .*$', (BUILD / '讲义/LALU.log').read_text(encoding='utf-8', errors='replace'),
                        re.M)
    return r.returncode, aux, errors


def read_aux(aux):
    num, page, pdf, pos = {}, {}, {}, {}
    for m in re.finditer(r'\\newlabel\{LALUB:([^}]+)\}\{\{([^}]*)\}\{([^}]*)\}', aux):
        num[m[1]], page[m[1]] = m[2], m[3]
    for m in re.finditer(r'\\lalupdfpage\{([^}]+)\}\{(\d+)\}', aux):
        pdf[m[1]] = int(m[2])
    for m in re.finditer(r'\\lalunum\{([^}]+)\}\{([^}]*)\}', aux):
        num[m[1]] = m[2]  # box counter overrides the section number \label saw
    for m in re.finditer(r'\\lalupos\{([^}]+)\}\{(-?\d+)\}\{(-?\d+)\}', aux):
        pos[m[1]] = [round(int(m[2]) / 65536, 2), round(int(m[3]) / 65536, 2)]  # TeX pt from the page's bottom-left
    return num, page, pdf, pos


def main():
    parsers = [Parser(n, f).parse() for n, _, f in chapter_files()]
    rc, aux, errors = compile_marked(parsers)
    num, page, pdf, pos = read_aux(aux)
    shutil.copy(BUILD / '讲义/LALU.pdf', OUT / 'LALU.pdf')

    blocks, nodes, missing = [], [], []
    for p in parsers:
        chap_title = next((b['title'] for b in p.blocks if b['kind'] == 'heading' and b['level'] == 'chapter'),
                          p.path.stem)
        chap_id = f'{BOOK}/{p.chap}'
        sec_id = sub_id = None
        heading = [None, None]
        for b in p.blocks:
            uid = b['uid']
            n = num.get(uid)
            if uid not in pdf:
                missing.append(uid)
            if b['kind'] == 'heading' and not b['starred'] and b['level'] in ('chapter', 'section', 'subsection'):
                lvl = b['level']
                if lvl == 'chapter':
                    nodes.append({'id': chap_id, 'kind': 'chapter', 'num': str(p.chap), 'title': chap_title,
                                  'raw': f'第{p.chap}章 {chap_title}', 'anchor': uid})
                    sec_id = sub_id = None
                elif lvl == 'section':
                    sec_id, sub_id = f'{chap_id}/{n}', None
                    nodes.append({'id': sec_id, 'kind': 'section', 'num': n, 'title': b['title'],
                                  'raw': f'{n} {b["title"]}', 'anchor': uid})
                else:
                    sub_id = f'{sec_id}/{n}'
                    nodes.append({'id': sub_id, 'kind': 'subsection', 'num': n, 'title': b['title'],
                                  'raw': f'{n} {b["title"]}', 'anchor': uid})
                heading = [None, None]
            elif b['kind'] == 'heading':
                heading = [b['title'], None] if b['level'] != 'subsubsection' else [heading[0], b['title']]
            label = 'paragraph_title' if b['kind'] == 'heading' else b['kind']
            if b['env'] in NUMBERED:
                num_label = f'{NUMBERED[b["env"]]}{n}' if n else NUMBERED[b['env']]
            elif b['env'] in UNNUMBERED:
                num_label = UNNUMBERED[b['env']]
            elif b['kind'] == 'exercise_item':
                num_label = f'习题{n}' if n else '习题'
            else:
                num_label = None
            title = re.match(r'\\begin\{\w+\}\s*(?:\[([^\]]*)\])?', b['text'])
            blocks.append({
                'uid': uid, 'book': BOOK, 'pdf_page': pdf.get(uid), 'printed_page': page.get(uid),
                'block_id': int(uid.rsplit('b', 1)[1]), 'label': label, 'bbox': [0, 0, 0, 0],
                'crop_bbox': [0, 0, 0, 0], 'text': b['text'], 'norm': norm_text(b['text']),
                'chapter': chap_id, 'section': sec_id, 'subsection': sub_id,
                'node': sub_id or sec_id or chap_id, 'zone': b['zone'],
                'local_heading': ' / '.join(x for x in heading if x) or None,
                'src': f'讲义/专题/{p.path.name}:{b["line_start"]}-{b["line_end"]}',
                'num_label': num_label + (f'（续{b["part"] - 1}）' if b['part'] > 1 else '') if num_label else None,
                'env_title': title[1] if title and title[1] else None,
                'tex_pos': pos.get(uid) if pos.get(uid, [0, 0])[1] > 0 else None,
            })
    # starred headings carry no marker: they sit on the page of the block that follows them
    for i in range(len(blocks) - 2, -1, -1):
        if blocks[i]['pdf_page'] is None and blocks[i + 1]['book'] == BOOK:
            blocks[i]['pdf_page'], blocks[i]['printed_page'] = blocks[i + 1]['pdf_page'], blocks[i + 1]['printed_page']
    counts = Counter()
    for b in blocks:
        for nid in {b['chapter'], b['section'], b['subsection']} - {None}:
            counts[nid] += 1
    by_node = {}
    for b in blocks:
        for nid in {b['chapter'], b['section'], b['subsection']} - {None}:
            if b['pdf_page']:
                lo, hi = by_node.get(nid, (b['pdf_page'], b['pdf_page']))
                by_node[nid] = (min(lo, b['pdf_page']), max(hi, b['pdf_page']))
    for n in nodes:
        n['block_count'] = counts[n['id']]
        n['pdf_page_range'] = list(by_node.get(n['id'], (None, None)))
        n['pdf_page'] = n['pdf_page_range'][0]
        n['printed_page'] = None
        n['anchor_method'] = 'latex_heading'
        n['chapter'] = n['id'].split('/')[1]
    OUT.mkdir(parents=True, exist_ok=True)
    jsonl(OUT / 'blocks.jsonl', blocks)
    jsonsave(OUT / 'toc.json', {'book': BOOK, 'commit': COMMIT, 'nodes': nodes})
    kinds = Counter(b['label'] for b in blocks)
    zones = Counter(b['zone'] for b in blocks)
    unnumbered = [b['uid'] for b in blocks if b['label'] in NUMBERED and not re.search(r'\d', b['num_label'] or '')]
    lines = [f'# 《线性代数：未竟之美》索引构建报告\n',
             f'源：`source/LALU`，提交 `{COMMIT}`。编译返回码 {rc}，LaTeX 错误 {len(errors)} 条。\n',
             f'- 块 {len(blocks)}：' + '，'.join(f'{k} {v}' for k, v in kinds.most_common()),
             f'- 分区：' + '，'.join(f'{k} {v}' for k, v in zones.items()),
             f'- 未取到页码的块：{len(missing)}' + (f'（{", ".join(missing[:10])}）' if missing else ''),
             f'- 编号环境未取到编号：{len(unnumbered)}' + (f'（{", ".join(unnumbered[:10])}）' if unnumbered else ''),
             f'- 章节节点：{len(nodes)}\n']
    if errors:
        lines.append('LaTeX 错误（前 20 条）：\n\n```\n' + '\n'.join(errors[:20]) + '\n```\n')
    lines.append('## 目录\n')
    for n in nodes:
        ind = {'chapter': '', 'section': '  ', 'subsection': '    '}[n['kind']]
        lines.append(f'{ind}- `{n["id"]}` {n["raw"]}（{n["block_count"]} 块，PDF p{n["pdf_page_range"][0]}–'
                     f'{n["pdf_page_range"][1]}）')
    save(OUT / '构建报告.md', '\n'.join(lines) + '\n')
    print(f'rc={rc} errors={len(errors)} blocks={len(blocks)} nodes={len(nodes)} missing_pages={len(missing)} '
          f'unnumbered={len(unnumbered)}')
    print(dict(kinds))


if __name__ == '__main__':
    main()
