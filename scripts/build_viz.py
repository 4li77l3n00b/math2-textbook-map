"""Offline visualisation of the question -> textbook mapping (no API calls).

  python3 scripts/build_viz.py pages     render the in-scope textbook pages -> output/viz/pages/<book>/<page>.webp
  python3 scripts/build_viz.py data      aggregate mapping + cards + blocks  -> output/viz/data.js
Open output/viz/index.html in a browser (works from file://, everything is local).

Page images: GS1/GS2 are rendered like textbook_crop.py (`pdftoppm -cropbox -r 144`), so OCR bbox pixels
(2 px/pt) are image pixels. LALU blocks have no bbox; build_lalu_index.py records each marker's shipout position
(`tex_pos`), and a block covers the band from its marker down to the next marker.
"""
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import io
import json
import re
import subprocess
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import HTML_TAG, BOOKS as TB_BOOKS  # noqa: E402
from build_cards import SCOPE, SKIP  # noqa: E402
import map_questions as mq  # noqa: E402

OUT = ROOT / 'output/viz'
# hand-typeset LaTeX versions of solution steps (scripts/steps_tex.cjs build): {qid: {n: text with $…$}}
STEPS_TEX_FILE = ROOT / 'output/mapping/steps_tex.json'
STEPS_TEX = json.loads(STEPS_TEX_FILE.read_text()) if STEPS_TEX_FILE.exists() else {}
TB = ROOT / 'output/textbook'
PDF = {**{b: ROOT / "source" / f for b, (_, f) in TB_BOOKS.items()},
       'LALU': TB / 'lalu/LALU.pdf'}
BOOK_NAME = {'GS1': '高等数学 上册', 'GS2': '高等数学 下册', 'LA': '线性代数（王宽程）', 'LALU': '线性代数讲义（LALU，补充）'}
DPI = 144
SCALE = DPI / 72  # image px per PDF point
LALU_PAGE = (524.41, 737.01)  # pt
TEX_PT = 72 / 72.27  # PDF points per TeX point
QUALITY = 62
BASELINE_LIFT = 17  # px (8.5 pt)


def in_scope(node):
    node = node or ''
    hit = lambda lst: any(node == s or node.startswith(s + '/') for s in lst)  # noqa: E731
    return hit(SCOPE) and not hit(SKIP)


def load_blocks_jsonl():
    return [json.loads(line) for line in (TB / 'blocks.jsonl').open(encoding='utf-8')]


def scope_pages(blocks):
    lalu = lalu_rects(lalu_positions(blocks))
    pages = defaultdict(set)
    for b in blocks:
        if in_scope(b['node']) and b['pdf_page']:
            pages[b['book']].update([r[0] for r in lalu.get(b['uid'], [])] if b['book'] == 'LALU' else [b['pdf_page']])
    return pages


def render(book, page):
    dst = OUT / 'pages' / book / f'{page:04d}.webp'
    if dst.exists():
        return
    args = ['pdftoppm', '-cropbox', '-r', str(DPI), '-f', str(page), '-l', str(page), '-png']
    if book != 'LALU':
        args.append('-gray')  # scans: grey keeps the heat colours readable and the files small
    png = subprocess.run(args + [str(PDF[book])], capture_output=True, check=True).stdout
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(png)).save(dst, 'WEBP', quality=QUALITY, method=4)


def cmd_pages():
    pages = scope_pages(load_blocks_jsonl())
    jobs = [(bk, p) for bk in sorted(pages) for p in sorted(pages[bk])]
    print(len(jobs), 'pages', {k: len(v) for k, v in pages.items()})
    with ThreadPoolExecutor(12) as ex:
        for i, _ in enumerate(ex.map(lambda j: render(*j), jobs), 1):
            if i % 100 == 0:
                print(i, flush=True)


def lalu_positions(blocks=None):
    """uid -> (pdf_page, y from page top in px), from the shipout-time marker positions in the LALU index."""
    pos = {}
    for b in blocks or load_blocks_jsonl():
        if b['book'] == 'LALU' and b.get('tex_pos'):
            # a marker that opens a paragraph records that line's baseline: lift to the top of the line
            pos[b['uid']] = (b['pdf_page'], (LALU_PAGE[1] - b['tex_pos'][1] * TEX_PT) * SCALE - BASELINE_LIFT)
    return pos


def lalu_rects(pos):
    """A block spans from its marker to the next marker (possibly on a later page) -> uid -> [[page, x0, y0, x1, y1]]."""
    x0, x1 = 50 * SCALE, (LALU_PAGE[0] - 50) * SCALE
    ys = [y for _, y in pos.values()]
    top, bottom = min(ys) - 4, (LALU_PAGE[1] - 50) * SCALE
    seq = sorted(pos.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    rects = {}
    for i, (uid, (p, y)) in enumerate(seq):
        np_, ny = seq[i + 1][1] if i + 1 < len(seq) else (p, bottom)
        if np_ == p:
            r = [[p, y, max(ny, y + 8)]]
        elif np_ - p > 2:  # next marker is far away (unindexed chapter / page break): stop at this page
            r = [[p, y, bottom]]
        else:
            r = [[p, y, bottom]] + [[q, top, bottom] for q in range(p + 1, np_)] + ([[np_, top, ny]] if ny > top + 6 else [])
        rects[uid] = [[q, round(x0), round(a), round(x1), round(b)] for q, a, b in r if b - a > 2]
    return rects


def clean(t, n=None):
    t = HTML_TAG.sub('', t or '').strip()
    return t if n is None or len(t) <= n else t[:n] + '…'


QTYPE = {'选择题': 'x', '填空题': 't', '解答题': 'j'}
ROLE = {'core': 'c', 'auxiliary': 'a', 'prerequisite': 'p'}


def cmd_data():
    raw = {b['uid']: b for b in load_blocks_jsonl()}
    rows, order = mq.load_blocks()
    cards = mq.load_cards()
    finals = {f.stem: json.loads(f.read_text(encoding='utf-8')) for f in sorted((mq.OUT / 'final').glob('math2-*.json'))}

    # blocks: everything in scope plus anything a citation / card / review points at
    wanted = {i for i, r in enumerate(rows) if in_scope(raw[r[0]]['node'])}

    def span(s, e):
        a, b = sorted((order[s], order[e]))
        return list(range(a, b + 1))
    cite_spans = {}
    for qid, r in finals.items():
        for j, c in enumerate(r['citations']):
            if c['start_uid'] in order and c['end_uid'] in order:
                cite_spans[qid, j] = span(c['start_uid'], c['end_uid'])
                wanted.update(cite_spans[qid, j])
    card_blocks = {}
    for cid, cd in cards.items():
        st = [order[u] for u in cd['statement_uids'] if u in order] or span(cd['start_uid'], cd['end_uid'])
        card_blocks[cid] = (sorted(st), span(cd['start_uid'], cd['end_uid']))
        wanted.update(card_blocks[cid][1])
    wanted = sorted(wanted)
    bidx = {i: k for k, i in enumerate(wanted)}

    rects = lalu_rects(lalu_positions())
    blocks = []
    for i in wanted:
        b = raw[rows[i][0]]
        if b['book'] == 'LALU':
            rr = rects.get(b['uid'], [])
        else:
            x0, y0, x1, y1 = b['crop_bbox']
            rr = [[b['pdf_page'], x0, y0, x1, y1]]
        blocks.append({'u': b['uid'], 'bk': b['book'], 'n': b['node'], 'l': b['label'], 'nl': b.get('num_label'),
                       'r': rr, 'pg': b['printed_page'], 't': clean(b['text'], 1500)})

    # nodes: in-scope toc nodes and their ancestors, in book order
    toc = json.loads((TB / 'toc.json').read_text(encoding='utf-8'))['nodes']
    ids = {n['id'] for n in toc}
    keep = set()
    for n in toc:
        if in_scope(n['id']) or any(in_scope(c['id']) and c['id'].startswith(n['id'] + '/') for c in toc):
            keep.add(n['id'])
    nodes = []
    for n in toc:
        if n['id'] not in keep:
            continue
        parent = n['id'].rsplit('/', 1)[0] if '/' in n['id'] else None
        anchor = raw.get(n.get('anchor') or '')
        nodes.append({'id': n['id'], 'p': parent if parent in ids else None, 'k': n['kind'], 'num': n['num'],
                      'ti': n['title'], 'bk': n['id'].split('/')[0], 'pdf': n.get('pdf_page') or (anchor or {}).get('pdf_page'),
                      'in': in_scope(n['id']), 'ab': bidx.get(order.get(n.get('anchor') or ''))})

    # book order: position of the card's unit in the chapter tree, then of its first block
    # (sorting the ids as text would put GS2/11 before GS2/7 and LALU/10 before LALU/2)
    npos = {n['id']: i for i, n in enumerate(nodes)}

    def book_pos(cid):
        blocks = [bidx[u] for u in card_blocks[cid][0] + card_blocks[cid][1] if u in bidx]
        return (npos.get(cards[cid]['unit'], len(npos)), min(blocks, default=0), cid)
    card_list = sorted(cards, key=book_pos)
    cidx = {c: k for k, c in enumerate(card_list)}
    card_out = []
    for cid in card_list:
        cd = cards[cid]
        st, sp = card_blocks[cid]
        card_out.append({'id': cid, 'bk': cid.split('/')[0], 'n': cd['unit'], 'k': cd['kind'], 'lb': cd['label'],
                         'ti': cd['title'], 'su': cd['summary'], 'kw': cd['keywords'],
                         'st': [bidx[i] for i in st if i in bidx], 'sp': [bidx[i] for i in sp if i in bidx],
                         'in': in_scope(cd['unit'])})

    # knowledge points (build_kps.py); cards that questions use but no knowledge point covers get their own
    kp_path = ROOT / 'output/knowledge/knowledge_points.json'
    kpd = json.loads(kp_path.read_text(encoding='utf-8')) if kp_path.exists() else {'kps': [], 'citations': []}
    kp_list, kidx = [], {}

    def add_kp(k):
        kidx[k['id']] = len(kp_list)
        kp_list.append(k)
        return kidx[k['id']]
    for k in kpd['kps']:
        add_kp({'id': k['id'], 'n': k['name'], 's': k['statement'], 'k': k['kind'], 'c': cidx.get(k['canonical'], -1),
                'm': [[cidx[m['card']], m['relation'][0]] for m in k['members'] if m['card'] in cidx],
                'w': k.get('worded', False)})
    home = {}
    for i, k in enumerate(kp_list):
        for c, _ in k['m']:
            home.setdefault(c, i)
    for i, k in enumerate(kp_list):
        home[k['c']] = i

    def kp_for_card(cid):
        c = cidx.get(cid)
        if c is None:
            return None
        if c not in home:  # a used card no knowledge point covers: its own item
            cd = cards[cid]
            home[c] = add_kp({'id': f'card:{cid}', 'n': cd['title'], 's': cd['summary'], 'k': cd['kind'], 'c': c,
                              'm': [], 'w': False, 'card': True})
        return home[c]

    qs = []
    for q in mq.questions():
        r = finals[q['question_id']]
        cites = []
        for j, c in enumerate(r['citations']):
            cites.append({'b': [bidx[i] for i in cite_spans.get((q['question_id'], j), []) if i in bidx],
                          'r': ROLE[c['role']], 'k': c['knowledge'], 'q': c['quote'], 's': c['steps'], 'w': c['why'],
                          'c': cidx.get(c.get('card_id'), -1), 'm': c.get('source') == 'manual_qa',
                          'kp': [kidx[x] for x in c.get('kps', []) if x in kidx] or
                          ([kp_for_card(c['card_id'])] if c.get('card_id') in cidx else [])})
        topics = [{'c': cidx[t['card_id']], 'p': 1 if t['relation'] == 'primary' else 0, 'r': t['reason'],
                   'kp': kidx[t['kp']] if t.get('kp') in kidx else kp_for_card(t['card_id'])}
                  for t in r['topics'] if t['card_id'] in cidx]
        nit = []
        for x in r['not_in_textbook']:
            rv = x.get('review') or {}
            rel = rv.get('related_span')
            nit.append({'k': x['knowledge'], 's': x['steps'], 'se': x['searched'], 'v': rv.get('verdict', ''),
                        'no': rv.get('note', ''),
                        'rb': [bidx[i] for i in span(*rel) if i in bidx] if rel and rel[0] in order and rel[1] in order else []})
        qs.append({'id': q['question_id'], 'y': q['year'], 'lb': q['label'], 'ty': QTYPE.get(q['section'], 'j'),
                   'sub': q['_subject'], 'stem': q['stem'], 'ans': q['answer'], 'sol': q['solution'],
                   'steps': [[s['n'], s['description']] + ([tex] if (tex := STEPS_TEX.get(q['question_id'], {}).get(str(s['n']))) else [])
                             for s in r['steps']], 'ci': cites, 'to': topics,
                   'tn': r['topic_note'], 'no': r['notes'], 'nit': nit, 'cx': r.get('engine') is None})
    qs.sort(key=lambda x: (x['y'], x['id']))

    books = {}
    pages_json = [json.loads(line) for line in (TB / 'pages.jsonl').open(encoding='utf-8')]
    for bk in ('GS1', 'GS2', 'LA', 'LALU'):
        have = sorted(int(p.stem) for p in (OUT / 'pages' / bk).glob('*.webp'))
        if bk == 'LALU':
            size = {p: [round(LALU_PAGE[0] * SCALE), round(LALU_PAGE[1] * SCALE)] for p in have}
            printed = {r[0]: b['printed_page'] for b in raw.values() if b['book'] == bk for r in rects.get(b['uid'], [])[:1]}
        else:
            pj = {x['pdf_page']: x for x in pages_json if x['book'] == bk}
            size = {p: [pj[p]['ocr_w'], pj[p]['ocr_h']] for p in have}
            printed = {p: pj[p]['printed_page'] for p in have}
        books[bk] = {'name': BOOK_NAME[bk], 'pages': [[p, *size[p], printed.get(p)] for p in have]}

    # derivation sources (build_deps.py): d = [[kp it depends on, 0 concept | 1 proof, 1 book | 2 astra | 3 both]]
    dp_path = ROOT / 'output/knowledge/deps.json'
    for e in json.loads(dp_path.read_text(encoding='utf-8'))['edges'] if dp_path.exists() else []:
        if e['from'] in kidx and e['to'] in kidx:
            src = ('book' in e['source']) + 2 * ('astra' in e['source'])
            kp_list[kidx[e['from']]].setdefault('d', []).append([kidx[e['to']], int(e['type'] == 'proof'), src])
    for i, k in enumerate(kp_list):  # card -> knowledge points it belongs to (canonical first)
        for c in [k['c']] + [m for m, _ in k['m']]:
            if c >= 0:
                card_out[c].setdefault('kp', []).append(i)
    data = {'books': books, 'nodes': nodes, 'blocks': blocks, 'cards': card_out, 'questions': qs, 'kps': kp_list,
            'built': __import__('datetime').date.today().isoformat()}
    OUT.mkdir(parents=True, exist_ok=True)
    js = 'window.DATA=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    (OUT / 'data.js').write_text(js, encoding='utf-8')
    print(f'knowledge points {len(kp_list)} ({sum(1 for k in kp_list if k.get("card"))} single-card, '
          f'{sum(1 for k in kp_list if k["w"])} hand-worded)')
    print(f'blocks {len(blocks)} nodes {len(nodes)} cards {len(card_out)} questions {len(qs)} '
          f'size {len(js.encode()) / 1e6:.1f} MB; lalu blocks without rect '
          f'{sum(1 for b in blocks if b["bk"] == "LALU" and not b["r"])}')


if __name__ == '__main__':
    cmds = {'pages': cmd_pages, 'data': lambda: cmd_data()}
    cmds.get(sys.argv[1] if len(sys.argv) > 1 else '', lambda: print(__doc__))()
