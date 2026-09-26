"""Read-only textbook lookup tool for agents mapping exam questions to the textbooks.

  python3 scripts/textbook_cli.py toc [BOOK] [--depth N]      table of contents with node ids
  python3 scripts/textbook_cli.py read NODE_ID [--from UID] [--limit N] [--all-zones]
                                                             blocks of a section, in reading order
  python3 scripts/textbook_cli.py blocks UID [UID_END] [--context K]
                                                             one block, a range, or a block with neighbours
  python3 scripts/textbook_cli.py search QUERY [--book B] [--limit N] [--all-zones]
                                                             full-text search (body/practice by default)
  python3 scripts/textbook_cli.py cards [NODE_ID]            knowledge cards (if built) for a section / all
  python3 scripts/textbook_cli.py card CARD_ID               one card with its source blocks

Books: GS1 高等数学上册, GS2 高等数学下册, LA 线性代数（王宽程）, LALU 线性代数讲义. Block uids look like GS1-p144-b23 /
LA-p070-b12 / LALU-c14-b0050.
"""
from pathlib import Path
import argparse
import json
import os
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'output/textbook/textbook_index.sqlite'
CARDS = ROOT / 'output/textbook/cards'
BOOK_NAMES = {'LALU': '线性代数：未竟之美（LaTeX 讲义）', 'GS1': '高等数学上册', 'GS2': '高等数学下册', 'LA': '线性代数（王宽程）'}
LABEL = "label || coalesce(' ' || num_label, '')"  # e.g. `theorem 定理14.3`
TEXT_ZONES = ('body', 'practice')
HTML_TAG = re.compile(r'</?(?:div|img|span|br|p|table|tr|td|th|sup|sub|center)\b[^>]*>', re.I)


def db():
    return sqlite3.connect(f'file:{DB}?mode=ro', uri=True)


def clip(t, n):
    t = HTML_TAG.sub('', t).strip()
    return t if len(t) <= n else t[:n] + '…'


def fmt(row, width=600):
    uid, label, zone, text = row
    tag = '' if label in ('text', 'paragraph') else f'[{label}]'
    z = '' if zone == 'body' else f'{{{zone}}}'
    return f'{uid} {tag}{z} {clip(text, width)}'.rstrip()


def cmd_toc(a):
    con = db()
    q = 'select id, kind, num, title, raw, pdf_first, pdf_last, block_count from sections'
    rows = con.execute(q + (' where book=?' if a.book else ''), (a.book,) if a.book else ()).fetchall()
    depth = {'chapter': 0, 'backmatter': 0, 'section': 1, 'chapter_review': 1, 'subsection': 2, 'exercises': 2}
    for sid, kind, num, title, raw, p0, p1, n in rows:
        d = depth[kind]
        if d > a.depth or kind in ('backmatter',):
            continue
        name = f'§{num} {title}' if kind == 'section' else f'{num} {title}' if kind == 'subsection' else raw
        print(f'{"  " * d}{sid}  {name}  ({n} blocks, pdf p{p0}-{p1})')


def section_rows(con, node, all_zones):
    col = 'subsection' if node.count('/') == 3 else 'section' if node.count('/') == 2 else 'chapter'
    if node.endswith('/exercises') or '/review:' in node:
        col = 'node'
    q = f'select uid, {LABEL}, zone, text from blocks where {col}=?'
    if not all_zones:
        q += f" and zone in {TEXT_ZONES + ('exercises', 'chapter_review') if col == 'node' else TEXT_ZONES}"
    q += " and trim(text) != '' and label not in ('image', 'chart') order by pdf_page, block_id"
    return con.execute(q, (node,)).fetchall()


def cmd_read(a):
    con = db()
    rows = section_rows(con, a.node, a.all_zones)
    if not rows:
        sys.exit(f'no blocks for {a.node}; use `toc` to see node ids')
    start = 0
    if a.from_uid:
        start = next((i for i, r in enumerate(rows) if r[0] == a.from_uid), 0)
    chunk = rows[start:start + a.limit]
    print(f'# {a.node}: blocks {start + 1}-{start + len(chunk)} of {len(rows)}')
    for r in chunk:
        print(fmt(r, a.width))
    if start + len(chunk) < len(rows):
        print(f'# … more: read {a.node} --from {rows[start + len(chunk)][0]}')


def order_key(uid):
    m = re.match(r'(\w+)-p(\d+)-b(\d+)', uid)
    return m[1], int(m[2]), int(m[3])


def cmd_blocks(a):
    con = db()
    book = a.uid.split('-')[0]
    rows = con.execute(f"select uid, {LABEL}, zone, text from blocks where book=? and trim(text) != '' "
                       "order by pdf_page, block_id", (book,)).fetchall()
    idx = {r[0]: i for i, r in enumerate(rows)}
    if a.uid not in idx:
        sys.exit(f'unknown or empty block {a.uid}')
    i = idx[a.uid]
    j = idx.get(a.uid_end, i) if a.uid_end else i
    lo, hi = max(0, min(i, j) - a.context), min(len(rows), max(i, j) + a.context + 1)
    sec = con.execute('select coalesce(subsection, section, node) from blocks where uid=?', (a.uid,)).fetchone()[0]
    print(f'# {sec}')
    for r in rows[lo:hi]:
        print(fmt(r, 2000))


def cmd_search(a):
    con = db()
    q = a.query.strip()
    zones = '' if a.all_zones else f' and b.zone in {TEXT_ZONES}'
    book = ' and b.book=?' if a.book else ''
    args = [a.book] if a.book else []
    terms = [t for t in re.split(r'\s+', q) if t]
    if all(len(t) >= 3 for t in terms):
        match = ' AND '.join('"' + t.replace('"', '""') + '"' for t in terms)
        sql = (f'select b.uid, b.label || coalesce(\' \' || b.num_label, \'\'), b.zone, b.text, '
               f'coalesce(b.subsection, b.section, b.node) from blocks_fts f '
               f'join blocks b on b.uid=f.uid where f.norm match ?{zones}{book} order by rank limit ?')
        rows = con.execute(sql, [match] + args + [a.limit]).fetchall()
    else:  # trigram index needs >= 3 chars per term
        like = ' and '.join('b.norm like ?' for _ in terms)
        sql = (f'select b.uid, b.label || coalesce(\' \' || b.num_label, \'\'), b.zone, b.text, '
               f'coalesce(b.subsection, b.section, b.node) from blocks b '
               f'where {like}{zones}{book} order by b.book, b.pdf_page, b.block_id limit ?')
        rows = con.execute(sql, [f'%{t}%' for t in terms] + args + [a.limit]).fetchall()
    for uid, label, zone, text, sec in rows:
        print(f'{sec} | {fmt((uid, label, zone, text), 220)}')
    if not rows:
        print('(no hits)')


def load_cards():
    if os.environ.get('TEXTBOOK_NO_CARDS'):
        sys.exit('cards are disabled in this run')
    cards = {}
    for f in sorted(CARDS.glob('*_*.json')):
        for c in json.loads(f.read_text(encoding='utf-8'))['cards']:
            cards[c['card_id']] = c
    return cards


def cmd_cards(a):
    cards = load_cards()
    if not cards:
        sys.exit('no cards built')
    for cid, c in cards.items():
        if a.node and not cid.startswith(a.node + '#'):
            continue
        lab = f'{c["label"]} ' if c.get('label') else ''
        if a.brief:
            print(f'{cid}  [{c["kind"]}] {lab}{c["title"]}')
        else:
            print(f'{cid}  [{c["kind"]}] {lab}{c["title"]} :: {clip(c["summary"], 160)}  '
                  f'<{c["start_uid"]}..{c["end_uid"]}>')


def cmd_card(a):
    c = load_cards().get(a.card_id)
    if not c:
        sys.exit(f'unknown card {a.card_id}')
    print(json.dumps({k: v for k, v in c.items()}, ensure_ascii=False, indent=1))
    ns = argparse.Namespace(uid=c['start_uid'], uid_end=c['end_uid'], context=0)
    cmd_blocks(ns)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('toc'); s.add_argument('book', nargs='?'); s.add_argument('--depth', type=int, default=2)
    s = sp.add_parser('read'); s.add_argument('node'); s.add_argument('--from', dest='from_uid')
    s.add_argument('--limit', type=int, default=60); s.add_argument('--all-zones', action='store_true')
    s.add_argument('--width', type=int, default=600, help='characters shown per block')
    s = sp.add_parser('blocks'); s.add_argument('uid'); s.add_argument('uid_end', nargs='?')
    s.add_argument('--context', type=int, default=0)
    s = sp.add_parser('search'); s.add_argument('query'); s.add_argument('--book')
    s.add_argument('--limit', type=int, default=15); s.add_argument('--all-zones', action='store_true')
    s = sp.add_parser('cards'); s.add_argument('node', nargs='?')
    s.add_argument('--brief', action='store_true', help='ids, numbers and titles only')
    s = sp.add_parser('card'); s.add_argument('card_id')
    a = p.parse_args(argv)
    {'toc': cmd_toc, 'read': cmd_read, 'blocks': cmd_blocks, 'search': cmd_search,
     'cards': cmd_cards, 'card': cmd_card}[a.cmd](a)


if __name__ == '__main__':
    main()
