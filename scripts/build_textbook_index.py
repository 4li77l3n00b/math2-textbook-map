"""Build a block-level textbook index and a TOC-anchored section tree from PaddleOCR JSON.

The OCR text itself is never edited here: blocks keep their raw content, and every derived
field (printed page, section path, zone, local heading) is recorded with how it was decided,
so later stages can cite `block_uid` + bbox and verify against the scanned page.
"""
from pathlib import Path
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from datetime import datetime, timezone
import json
import re
import sqlite3
import subprocess

import text_norm

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'source'
OUT = ROOT / 'output/textbook'
# Linear algebra: 王宽程 (LA, OCR) is the main book; the LaTeX notes LALU (scripts/build_lalu_index.py, merged in
# main()) supplement what LA lacks (rank inequalities, adjugate rank, multiplicities, Vandermonde, …)
def source_pdf(prefix):
    """The textbook PDF in source/ whose file name starts with `prefix` (downloaded names carry extra suffixes)."""
    hits = sorted(p.name for p in SRC.glob(prefix + '*.pdf'))
    return hits[0] if hits else prefix + '.pdf'


BOOKS = {
    'GS1': ('高等数学 上册（严亚强）', source_pdf('高等数学 上册 严亚强编')),
    'GS2': ('高等数学 第二版 下册（严亚强）', source_pdf('高等数学 第二版 下册')),
    'LA': ('线性代数（王宽程）', source_pdf('线性代数 (王宽程)')),
}
DROP = {'header', 'number', 'header_image', 'footer', 'footer_image'}
TITLE_LABELS = {'paragraph_title', 'doc_title', 'text', 'content'}
CN_NUM = '一二三四五六七八九十'
# only real markup: math like `0<x` … `f(x)>0` must survive
HTML_TAG = re.compile(r'</?(?:div|img|span|br|p|table|tr|td|th|sup|sub|center)\b[^>]*>', re.I)
ANCHOR_OK = {'title_match', 'title_match_header', 'chapter_page_start'}


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def jsonsave(path, data):
    save(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def jsonl(path, rows):
    save(path, ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))


# ---------- text normalisation (for matching/search only; raw text is kept) ----------

def norm_text(s):
    s = HTML_TAG.sub(' ', s)
    s = re.sub(r'(?m)^\s*#+\s*', '', s)
    s = re.sub(r'\{\{\{([^{}]*)\}\}\}', r'{\1}', s)
    s = re.sub(r'\\(left|right|big|Big|bigg|Bigg)(?![a-zA-Z])', '', s)
    s = s.replace('\\mathrm', '').replace('\\quad', ' ').replace('\\,', ' ')
    s = s.replace('$$', '$')
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def key(s):
    """Aggressive key for fuzzy title matching: no markup, spaces or punctuation."""
    s = norm_text(s)
    s = re.sub(r'[\s$#§\\{}（）()、，,.．:：—\-–…·]', '', s)
    return s


def sim(a, b):
    a, b = key(a), key(b)
    if not a or not b:
        return 0.0
    if b in a and len(a) <= len(b) * 1.6 + 4:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# ---------- TOC ----------

TOC_LINE = re.compile(r'^(?P<title>.*?\S)\s*(?:\.{2,}|…+|\s)\s*(?P<page>\d{1,3})\s*$')
SEC_NUM = re.compile(r'^(?:[§$S5]\s*)?(?P<num>\d{1,2}(?:\.\d{1,2}){1,2})\s*(?P<title>\S.*)$')


def classify(title):
    t = re.sub(r'\s+', ' ', title).strip()
    t = re.sub(r'^\s*\$\s*([^$]*?)\s*\$', r'\1', t) if t.startswith('$') else t
    if m := re.match(r'^第\s*(\d+)\s*章\s*(.*)$', t):
        n, rest = m[1], m[2].strip()
        if rest.startswith(('复习题', '自测题', '思考题')):
            return 'chapter_review', n, t
        return 'chapter', n, rest
    if m := re.match(r'^总习题\s*(\d+)$', t):
        return 'chapter_review', m[1], t
    if m := re.match(r'^习题\s*(\d+)\s*[.\-－]\s*(\d+)$', t):
        return 'exercises', f'{m[1]}.{m[2]}', t
    # OCR merged "习题6.2 平面..." where the original reads "§6.2 平面..."
    if m := re.match(r'^习题\s*(\d+\.\d+)\s+(\S.*)$', t):
        return 'section', m[1], m[2]
    if m := SEC_NUM.match(t):
        num = m['num']
        return ('subsection' if num.count('.') == 2 else 'section'), num, m['title'].strip()
    return 'backmatter', None, t


def parse_toc(pages, bid):
    lines = []
    for i, p in enumerate(pages[:14]):
        blocks = p['prunedResult']['parsing_res_list']
        text = '\n'.join(b['block_content'] for b in blocks if b['block_label'] in ('content', 'text'))
        if len(re.findall(r'(?m)(?:\.{3,}|…{2,}|\s)\s*\d{1,3}\s*$', text)) < 5:
            continue
        for ln in text.split('\n'):
            ln = ln.strip()
            if not ln or ln.startswith('#'):
                continue
            # split merged "习题6.1 习题6.2 xxx 18" into its two entries
            if m := re.match(r'^(习题\s*\d+[.\-]\d+)\s+(习题.*)$', ln):
                lines.append((i + 1, m[1], None))
                ln = m[2]
            if m := TOC_LINE.match(ln):
                lines.append((i + 1, m['title'], int(m['page'])))
            else:
                lines.append((i + 1, ln, None))
    nodes = []
    for toc_page, title, page in lines:
        kind, num, name = classify(title)
        nodes.append({'kind': kind, 'num': num, 'title': name, 'raw': title,
                      'printed_page': page, 'toc_pdf_page': toc_page})
    # exercises without a page: inherit the following entry's page (it starts on or before it)
    for i, n in enumerate(nodes):
        if n['printed_page'] is None:
            nxt = next((m['printed_page'] for m in nodes[i + 1:] if m['printed_page']), None)
            n['printed_page'] = nxt
            n['page_inferred'] = True
    # parent/ids
    chapter = None
    for n in nodes:
        if n['kind'] == 'chapter':
            chapter = n['num']
        if n['kind'] in ('section', 'subsection', 'exercises') and n['num']:
            chapter = n['num'].split('.')[0]
        ch = chapter if n['kind'] != 'backmatter' else None
        if n['kind'] == 'chapter':
            n['id'] = f'{bid}/{n["num"]}'
        elif n['kind'] == 'chapter_review':
            n['id'] = f'{bid}/{n["num"]}/review:{key(n["title"])}'
        elif n['kind'] == 'section':
            n['id'] = f'{bid}/{n["num"].split(".")[0]}/{n["num"]}'
        elif n['kind'] == 'subsection':
            a, b, _ = n['num'].split('.')
            n['id'] = f'{bid}/{a}/{a}.{b}/{n["num"]}'
        elif n['kind'] == 'exercises':
            a = n['num'].split('.')[0]
            n['id'] = f'{bid}/{a}/{n["num"]}/exercises'
        else:
            n['id'] = f'{bid}/back:{key(n["title"])}'
        n['chapter'] = ch
    return nodes


def tidy_titles(nodes):
    """Display titles, set after anchoring (ids and `raw` keep the OCR text): no TeX, one spelling for 习题x.y /
    第n章… headings, （续）, CJK–Latin spacing, and the space between a section's two topics that OCR sometimes
    drops (§2.3 函数的微分 导数的概念（续）)."""
    subs = defaultdict(list)
    for n in nodes:
        if n['kind'] == 'subsection':
            subs[n['id'].rsplit('/', 1)[0]].append(text_norm.title(n['title']))
    for n in nodes:
        t = text_norm.title(n['title'])
        t = re.sub(r'^第\s*(\d+)\s*章\s*', r'第\1章', t)
        parts = subs.get(n['id'], [])
        if n['kind'] == 'section' and len(parts) > 1 and ' ' not in t and key(t) == key(''.join(parts)):
            t = ' '.join(parts)
        n['title'] = t


# ---------- pages & printed page numbers ----------

def page_offsets(pages):
    """PDF page (1-based) minus printed page, voted over pages that print a number."""
    obs = {}
    for i, p in enumerate(pages):
        nums = [b['block_content'].strip() for b in p['prunedResult']['parsing_res_list']
                if b['block_label'] == 'number']
        if nums and nums[0].isdigit():
            obs[i + 1] = (i + 1) - int(nums[0])
    offsets, misread = {}, []
    keys = sorted(obs)
    for pdf in range(1, len(pages) + 1):
        near = sorted(keys, key=lambda k: abs(k - pdf))[:9]
        if not near:
            continue
        off, cnt = Counter(obs[k] for k in near).most_common(1)[0]
        offsets[pdf] = off
    for k in keys:
        if obs[k] != offsets[k]:
            misread.append({'pdf_page': k, 'printed_ocr': k - obs[k], 'printed_voted': k - offsets[k]})
    return obs, offsets, misread


OCR_SCALE = 2.0  # px per pt


def page_sizes(pdf, n):
    """Size of each page's bbox coordinate space.

    Verified against the OCR service's input images and by cropping: bboxes live in the CropBox,
    after applying /Rotate, at 2 px/pt, i.e. `pdftoppm -cropbox -r 144` (LA's stored input images
    were downscaled to 2000 px, but its bboxes still use the 2 px/pt space).
    """
    out = subprocess.run(['pdfinfo', '-f', '1', '-l', str(n), str(pdf)], capture_output=True, text=True).stdout
    size = {int(m[1]): (float(m[2]), float(m[3]))
            for m in re.finditer(r'Page\s+(\d+) size:\s+([\d.]+) x ([\d.]+) pts', out)}
    rot = {int(m[1]): int(m[2]) for m in re.finditer(r'Page\s+(\d+) rot:\s+(\d+)', out)}
    sizes = {}
    for pg, (w, h) in size.items():
        if rot.get(pg, 0) % 180:
            w, h = h, w
        sizes[pg] = (w, h, rot.get(pg, 0), round(w * OCR_SCALE), round(h * OCR_SCALE))
    return sizes


# ---------- anchoring TOC nodes to blocks ----------

TITLE_LABELS_EXTRA = TITLE_LABELS | {'inline_formula'}
# nodes whose headings may sit at the page top and be labelled `header` by the layout model
HEADER_OK = {'exercises', 'chapter_review', 'backmatter'}


def title_candidates(by_page, pdf_lo, pdf_hi, with_headers):
    for pg in range(pdf_lo, pdf_hi + 1):
        for b in by_page.get(pg, []):
            if b['label'] == 'header' and not with_headers:
                continue
            if (b['label'] in TITLE_LABELS_EXTRA or b['label'] == 'header') and len(b['text']) < 200:
                yield b


def strip_latex(t):
    return re.sub(r'\\[a-zA-Z]+|begin|end|aligned|array|&|\^|\*', '', t)


def score(node, b):
    t = key(b['text'])
    num = node['num']
    if node['kind'] == 'chapter':
        want = f'第{num}章'
        s = 1.0 if t.startswith(want) or t == key(node['title']) else 0.0
        return s + (0.3 if b['label'] in ('paragraph_title', 'doc_title') else 0)
    if node['kind'] == 'exercises':
        a, c = num.split('.')
        # "习题1.4 $...$" (heading glued to first item) and "习题43" (dot dropped) both count
        ok = re.match(rf'^习题{a}[.\-－]?{c}(?!\d)', strip_latex(t))
        exact = ok and len(strip_latex(t)) <= len(f'习题{a}{c}') + 1
        return (1.0 if ok else 0.0) + (0.3 if exact else 0) + (0.1 if b['label'] == 'paragraph_title' else 0)
    if node['kind'] in ('section', 'subsection'):
        compact = num.replace('.', '')
        head = strip_latex(norm_text(b['text'])).lstrip('#$§ {}').replace(' ', '')
        m = re.match(r'^[§S5]?(\d+(?:\.\d+)*)', head)
        got = m[1] if m else ''
        # tolerate a leading '§' misread as '5'
        num_ok = got == num or (got.startswith('5') and got[1:] == num)
        # OCR sometimes drops a digit ("1.3" for "1.1.3"): partial credit for a proper suffix
        num_part = not num_ok and got.count('.') >= 1 and num.endswith('.' + got.split('.', 1)[1]) \
            and num.startswith(got.split('.')[0])
        # compare the title against the start of the block only (headings may be glued to body text)
        rest = key(strip_latex(b['text']))
        rest = re.sub(r'^[S5]?[\d]+', '', rest)[:len(key(node['title'])) + 2]
        s = (0.6 if num_ok else 0.4 if num_part else 0.0) + 0.6 * max(
            sim(strip_latex(b['text']).replace(num, ''), node['title']), sim(rest, node['title']))
        if not (num_ok or num_part) and compact not in t:
            s *= 0.5
        return s + (0.2 if b['label'] == 'paragraph_title' else 0)
    return sim(b['text'], node['title']) + (0.2 if b['label'] == 'paragraph_title' else 0)


def anchor_nodes(nodes, blocks, offsets, headers):
    main_off = Counter(offsets.values()).most_common(1)[0][0]
    by_uid = {b['uid']: i for i, b in enumerate(blocks)}
    by_page = defaultdict(list)
    for b in sorted(blocks + headers, key=lambda b: (b['pdf_page'], b['block_id'])):
        by_page[b['pdf_page']].append(b)
    prev_pdf, prev_pos = 1, (0, -1)
    for n in nodes:
        n['anchor'] = None
        if not n['printed_page']:
            n['anchor_method'] = 'no_page'
            continue
        guess = n['printed_page'] + main_off
        pdf = n['printed_page'] + offsets.get(guess, main_off)
        n['pdf_page'] = pdf
        # a page inferred from the next TOC entry is an upper bound: search back to the previous entry
        lo = max(prev_pdf, pdf - 4) if n.get('page_inferred') else pdf - 1
        with_headers = n['kind'] in HEADER_OK
        threshold = 0.9 if n['kind'] in ('chapter', 'exercises') else 0.85
        scored = [(score(n, b) - 0.05 * max(0, abs(b['pdf_page'] - pdf) - (1 if n.get('page_inferred') else 0)), b)
                  for b in title_candidates(by_page, lo, pdf + 1, with_headers)]
        good = [(s, b) for s, b in scored if s >= threshold]
        best_s, best = max(scored, key=lambda x: x[0], default=(0.0, None))
        # prefer matches after the previous TOC entry's anchor, and real headings over running headers
        # (a running header names what the page is about, not where it starts)
        after = [(s, b) for s, b in good if (b['pdf_page'], b['block_id']) >= prev_pos]
        body = [(s, b) for s, b in (after or good) if b['label'] != 'header']
        heads = [(s, b) for s, b in after if b['label'] == 'header']
        good = body or heads
        if good:
            s, b = max(good, key=lambda x: x[0]) if body else min(good, key=lambda x: (x[1]['pdf_page'], x[1]['block_id']))
            method = 'title_match'
            if b['label'] == 'header':
                method = 'title_match_header'
                b = next((k for k in by_page[b['pdf_page']] if k['label'] != 'header' and k['block_id'] > b['block_id']),
                         next((k for k in by_page.get(b['pdf_page'] + 1, []) if k['label'] != 'header'), None))
            if b:
                n['anchor'], n['anchor_score'], n['anchor_method'] = b['uid'], round(s, 3), method
                prev_pos = (b['pdf_page'], b['block_id'])
        if not n['anchor']:
            n['anchor_score'] = round(best_s, 3)
            n['best_candidate'] = best['text'][:80] if best else None
            # never let a fallback anchor jump before the previous entry: that would reorder sections
            first = next((b for b in by_page.get(pdf, []) if b['label'] != 'header'), None)
            if first and (first['pdf_page'], first['block_id']) > prev_pos:
                n['anchor'], n['anchor_method'] = first['uid'], 'page_start_fallback'
                prev_pos = (first['pdf_page'], first['block_id'])
            else:
                n['anchor_method'] = 'unresolved'
        prev_pdf = n.get('pdf_page', prev_pdf)
    # chapter headings in these books are often artwork: a chapter starting on the page of its first
    # section is anchored at that page start (or at the section, whichever comes first)
    for i, n in enumerate(nodes):
        if n['kind'] == 'chapter' and n.get('anchor_method') == 'page_start_fallback':
            nxt = next((m for m in nodes[i + 1:] if m['kind'] == 'section' and m.get('anchor')), None)
            if nxt and n.get('anchor'):
                if by_uid[nxt['anchor']] < by_uid[n['anchor']]:
                    n['anchor'] = nxt['anchor']
                if blocks[by_uid[nxt['anchor']]]['pdf_page'] in (n['pdf_page'], n['pdf_page'] + 1):
                    n['anchor_method'] = 'chapter_page_start'
    return by_uid


def numkey(num):
    return tuple(int(x) for x in num.split('.'))


# ---------- main per-book build ----------

def build_book(bid):
    name, pdfname = BOOKS[bid]
    pdf = SRC / pdfname
    pages = json.loads((SRC / f'{pdfname}_by_PaddleOCR-VL-1.6.json').read_text(encoding='utf-8'))
    obs, offsets, misread = page_offsets(pages)
    sizes = page_sizes(pdf, len(pages))
    main_off = Counter(offsets.values()).most_common(1)[0][0]

    page_rows, blocks, dropped, headers_kept = [], [], Counter(), []
    for i, p in enumerate(pages):
        pdfp = i + 1
        res = p['prunedResult']['parsing_res_list']
        headers = [b['block_content'].strip() for b in res if b['block_label'] == 'header']
        printed = pdfp - offsets[pdfp] if pdfp in offsets else None
        w, h, rot, ow, oh = sizes.get(pdfp, (None,) * 5)
        page_rows.append({'book': bid, 'pdf_page': pdfp, 'printed_page': printed if printed and printed > 0 else None,
                          'printed_page_ocr': (pdfp - obs[pdfp]) if pdfp in obs else None,
                          'headers': headers, 'page_w_pt': w, 'page_h_pt': h, 'rotate': rot, 'ocr_scale': OCR_SCALE,
                          'ocr_w': ow, 'ocr_h': oh,
                          'input_image': p.get('inputImage')})
        for order, b in enumerate(sorted(res, key=lambda b: b['block_id'])):
            if b['block_label'] in DROP:
                dropped[b['block_label']] += 1
                if b['block_label'] == 'header':
                    headers_kept.append({'uid': f'{bid}-p{pdfp:03d}-h{b["block_id"]:02d}', 'pdf_page': pdfp,
                                         'block_id': b['block_id'], 'label': 'header', 'text': b['block_content'].strip()})
                continue
            text = b['block_content']
            blocks.append({'uid': f'{bid}-p{pdfp:03d}-b{b["block_id"]:02d}', 'book': bid, 'pdf_page': pdfp,
                           'printed_page': page_rows[-1]['printed_page'], 'block_id': b['block_id'],
                           'label': b['block_label'], 'bbox': b['block_bbox'],
                           'text': text.strip(), 'norm': norm_text(text)})

    # PaddleOCR's block merging sometimes moves a block's text into the preceding block and leaves
    # an empty `text` block behind; widen the preceding block's crop box so its image shows all its text
    for i, b in enumerate(blocks):
        b['crop_bbox'] = list(b['bbox'])
        if b['label'] == 'text' and not b['text'] and i:
            j = i - 1
            while j >= 0 and blocks[j]['label'] == 'text' and not blocks[j]['text']:
                j -= 1
            prev = blocks[j]
            if j >= 0 and prev['pdf_page'] == b['pdf_page'] and prev['label'] == 'text' and prev['text']:
                x0, y0, x1, y1 = prev['crop_bbox']
                prev['crop_bbox'] = [min(x0, b['bbox'][0]), min(y0, b['bbox'][1]),
                                     max(x1, b['bbox'][2]), max(y1, b['bbox'][3])]
                prev['absorbed'] = prev.get('absorbed', []) + [b['uid']]

    nodes = parse_toc(pages, bid)
    toc_pdf_pages = {n['toc_pdf_page'] for n in nodes}
    by_uid = anchor_nodes(nodes, blocks, offsets, headers_kept)

    # walk blocks in order, applying anchors
    anchors = defaultdict(list)
    for n in nodes:
        if n.get('anchor'):
            anchors[n['anchor']].append(n)
    kind_rank = {'chapter': 0, 'section': 1, 'chapter_review': 1, 'backmatter': 0, 'subsection': 2, 'exercises': 2}
    state = {'chapter': None, 'section': None, 'subsection': None, 'node': None, 'zone': 'front'}
    heading = [None, None]
    first_body = min((by_uid[n['anchor']] for n in nodes if n['kind'] == 'chapter' and n.get('anchor')), default=0)
    for idx, b in enumerate(blocks):
        for n in sorted(anchors.get(b['uid'], []), key=lambda n: kind_rank[n['kind']]):
            k = n['kind']
            if k == 'chapter':
                state.update(chapter=n['id'], section=None, subsection=None, node=n['id'], zone='body')
            elif k == 'section':
                ch = f'{bid}/{n["num"].split(".")[0]}'
                state.update(chapter=ch, section=n['id'], subsection=None, node=n['id'], zone='body')
            elif k == 'subsection':
                a, c, _ = n['num'].split('.')
                state.update(chapter=f'{bid}/{a}', section=f'{bid}/{a}/{a}.{c}', subsection=n['id'], node=n['id'], zone='body')
            elif k == 'exercises':
                state.update(subsection=None, node=n['id'], zone='exercises')
            elif k == 'chapter_review':
                state.update(chapter=f'{bid}/{n["num"]}', section=None, subsection=None, node=n['id'], zone='chapter_review')
            else:
                state.update(chapter=None, section=None, subsection=None, node=n['id'], zone='backmatter')
            heading = [None, None]
        if b['pdf_page'] in toc_pdf_pages and idx < first_body:
            zone = 'toc'
        else:
            zone = state['zone']
        # soft, in-section markers: 练习 blocks and local headings (not used for boundaries)
        t = key(b['text'])
        is_practice = re.match(r'^练习\d+(\.\d+)+$', norm_text(b['text']).replace(' ', '')) is not None
        # soft markers only inside the running text; answer keys at the back reuse the same headings
        in_text = state['zone'] in ('body', 'practice', 'exercises')
        if (b['label'] == 'paragraph_title' or is_practice) and not anchors.get(b['uid']) and in_text:
            if is_practice or re.match(r'^习题\d', t):
                state['zone'] = zone = 'practice' if t.startswith('练习') else 'exercises'
                heading = [None, None]
            elif re.match(rf'^[{CN_NUM}]+、', norm_text(b['text']).lstrip('#$ ')):
                heading = [norm_text(b['text'])[:60], None]
            else:
                heading[1] = norm_text(b['text'])[:60]
        b.update(chapter=state['chapter'], section=state['section'], subsection=state['subsection'],
                 node=state['node'], zone=zone, local_heading=' / '.join(h for h in heading if h) or None)

    # node spans
    span = defaultdict(lambda: {'blocks': 0, 'pages': set()})
    for b in blocks:
        for nid in {b['chapter'], b['section'], b['subsection'], b['node']} - {None}:
            span[nid]['blocks'] += 1
            span[nid]['pages'].add(b['pdf_page'])
    for n in nodes:
        s = span.get(n['id'])
        n['block_count'] = s['blocks'] if s else 0
        n['pdf_page_range'] = [min(s['pages']), max(s['pages'])] if s else None

    checks = run_checks(bid, nodes, blocks, page_rows, by_uid, misread, main_off)
    meta = {'book': bid, 'name': name, 'pdf': pdfname, 'pages': len(pages), 'blocks': len(blocks),
            'dropped_labels': dict(dropped), 'main_offset': main_off,
            'labels': dict(Counter(b['label'] for b in blocks)),
            'zones': dict(Counter(b['zone'] for b in blocks))}
    tidy_titles(nodes)
    return meta, nodes, blocks, page_rows, checks


# ---------- checks ----------

def header_claims(text, known_sections):
    """Chapter / section numbers a running header asserts (tolerating §→5/$ misreads)."""
    t = norm_text(text).replace(' ', '')
    ch = re.match(r'^第(\d+)章', t)
    if ch:
        return ('chapter', ch[1])
    m = re.match(r'^[§$S]?(\d+\.\d+)', t)
    if m:
        num = m[1]
        if num not in known_sections and num.startswith('5') and num[1:] in known_sections:
            num = num[1:]
        if num in known_sections:
            return ('section', num)
    return None


def run_checks(bid, nodes, blocks, page_rows, by_uid, misread, main_off):
    known_sections = {n['num'] for n in nodes if n['kind'] == 'section'}
    page_sections = defaultdict(set)
    page_chapters = defaultdict(set)
    for b in blocks:
        if b['section']:
            page_sections[b['pdf_page']].add(b['section'].rsplit('/', 1)[1])
        if b['chapter']:
            page_chapters[b['pdf_page']].add(b['chapter'].rsplit('/', 1)[1])
    header_ok = header_bad = 0
    header_conflicts = []
    for p in page_rows:
        for h in p['headers']:
            c = header_claims(h, known_sections)
            if not c or p['pdf_page'] not in page_chapters:
                continue
            kind, num = c
            ok = num in (page_chapters if kind == 'chapter' else page_sections)[p['pdf_page']]
            if ok:
                header_ok += 1
            else:
                header_bad += 1
                header_conflicts.append({'pdf_page': p['pdf_page'], 'header': h, 'claims': f'{kind} {num}',
                                         'assigned': sorted(page_sections[p['pdf_page']] or page_chapters[p['pdf_page']])})
    # anchor ordering must follow numbering among numbered nodes
    order_issues = []
    numbered = [n for n in nodes if n['kind'] in ('section', 'subsection') and n.get('anchor')]
    for a, b in zip(numbered, numbered[1:]):
        if numkey(a['num']) < numkey(b['num']) and by_uid[a['anchor']] > by_uid[b['anchor']]:
            order_issues.append(f'{a["num"]} anchored after {b["num"]}')
    unanchored = [{'id': n['id'], 'raw': n['raw'], 'method': n.get('anchor_method'),
                   'score': n.get('anchor_score'), 'best_candidate': n.get('best_candidate')}
                  for n in nodes if n.get('anchor_method') not in ANCHOR_OK]
    empty = [n['id'] for n in nodes if n['kind'] in ('section', 'subsection') and not n['block_count']]
    # numbered items (例/定理/定义/推论) per chapter: gaps hint at OCR losses or merged blocks
    seen = defaultdict(set)
    for b in blocks:
        if b['zone'] != 'body':
            continue
        for kind, num in re.findall(r'(?:^|[\s>#*}$])(例|定理|定义|推论)\s*(\d+(?:\.\d+){1,2})(?=[\s（(，,:：]|$)',
                                    norm_text(b['text'])[:40]):
            seen[kind].add(num)
    gaps = []
    for kind, nums in seen.items():
        groups = defaultdict(set)
        for num in nums:
            *pre, last = num.split('.')
            groups['.'.join(pre)].add(int(last))
        for pre, vals in sorted(groups.items(), key=lambda x: numkey(x[0])):
            miss = sorted(set(range(1, max(vals) + 1)) - vals)
            if miss:
                gaps.append(f'{kind} {pre}.' + ','.join(map(str, miss)))
    unassigned = sum(1 for b in blocks if b['zone'] == 'body' and not b['chapter'])
    dims = {p['pdf_page']: (p['ocr_w'], p['ocr_h']) for p in page_rows}
    out_of_page = [b['uid'] for b in blocks
                   if dims.get(b['pdf_page'], (None,))[0] and (b['bbox'][2] > dims[b['pdf_page']][0] + 3
                                                            or b['bbox'][3] > dims[b['pdf_page']][1] + 3)]
    return {'header_agree': header_ok, 'header_conflict': header_bad, 'header_conflicts': header_conflicts,
            'order_issues': order_issues, 'not_title_anchored': unanchored, 'empty_nodes': empty,
            'page_number_misreads': misread, 'numbering_gaps': gaps,
            'numbered_items': {k: len(v) for k, v in seen.items()}, 'body_blocks_without_chapter': unassigned,
            'bbox_out_of_page': out_of_page}


# ---------- outputs ----------

def write_sqlite(path, all_blocks, all_nodes, all_pages):
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.executescript('''
    create table pages(book text, pdf_page int, printed_page int, printed_page_ocr int, headers text,
                       page_w_pt real, page_h_pt real, rotate int, ocr_scale real, ocr_w int, ocr_h int, input_image text,
                       primary key(book, pdf_page));
    create table sections(id text primary key, book text, kind text, num text, title text, raw text,
                          printed_page int, pdf_page int, anchor text, anchor_method text, anchor_score real,
                          block_count int, pdf_first int, pdf_last int);
    create table blocks(uid text primary key, book text, pdf_page int, printed_page int, block_id int,
                        label text, x0 int, y0 int, x1 int, y1 int, cx0 int, cy0 int, cx1 int, cy1 int,
                        absorbed text, src text, num_label text, chapter text, section text,
                        subsection text, node text, zone text, local_heading text, text text, norm text);
    create virtual table blocks_fts using fts5(uid unindexed, norm, tokenize='trigram');
    ''')
    con.executemany('insert into pages values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    [(p['book'], p['pdf_page'], p['printed_page'], p['printed_page_ocr'],
                      json.dumps(p['headers'], ensure_ascii=False), p['page_w_pt'], p['page_h_pt'], p['rotate'],
                      p['ocr_scale'], p['ocr_w'], p['ocr_h'], p['input_image'])
                     for p in all_pages])
    con.executemany('insert or replace into sections values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    [(n['id'], n['id'].split('/')[0], n['kind'], n['num'], n['title'], n['raw'], n['printed_page'],
                      n.get('pdf_page'), n.get('anchor'), n.get('anchor_method'), n.get('anchor_score'),
                      n['block_count'], *(n['pdf_page_range'] or (None, None))) for n in all_nodes])
    con.executemany('insert into blocks values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    [(b['uid'], b['book'], b['pdf_page'], b['printed_page'], b['block_id'], b['label'], *b['bbox'],
                      *b['crop_bbox'], json.dumps(b.get('absorbed')) if b.get('absorbed') else None,
                      b.get('src'), b.get('num_label'),
                      b['chapter'], b['section'], b['subsection'], b['node'], b['zone'], b['local_heading'],
                      b['text'], b['norm']) for b in all_blocks])
    con.executemany('insert into blocks_fts values (?,?)', [(b['uid'], b['norm']) for b in all_blocks])
    con.commit()
    con.close()


def report(metas, nodes_by_book, checks_by_book):
    now = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')
    out = [f'# 教材块级索引构建报告\n\n生成时间：{now}。来源：`source/*_by_PaddleOCR-VL-1.6.json`，OCR 原文未修改。\n']
    out.append('| 书 | PDF 页 | 保留块 | 页码偏移（PDF−印刷） | 目录条目 | 可靠锚定 | 回退锚定 | 页眉一致 / 冲突 |\n|---|---|---|---|---|---|---|---|')
    for m in metas:
        ns, c = nodes_by_book[m['book']], checks_by_book[m['book']]
        tm = sum(1 for n in ns if n.get('anchor_method') in ANCHOR_OK)
        out.append(f'| {m["name"]} | {m["pages"]} | {m["blocks"]} | {m["main_offset"]} | {len(ns)} | {tm} | '
                   f'{len(ns) - tm} | {c["header_agree"]} / {c["header_conflict"]} |')
    for m in metas:
        c, ns = checks_by_book[m['book']], nodes_by_book[m['book']]
        out.append(f'\n## {m["name"]}（{m["book"]}）\n')
        out.append(f'- 块类型：' + '，'.join(f'{k} {v}' for k, v in sorted(m['labels'].items(), key=lambda x: -x[1])))
        out.append(f'- 分区：' + '，'.join(f'{k} {v}' for k, v in sorted(m['zones'].items(), key=lambda x: -x[1])))
        out.append(f'- 已丢弃（页眉、页码等）：' + '，'.join(f'{k} {v}' for k, v in m['dropped_labels'].items()))
        out.append(f'- 页码识别错误（按邻近页投票纠正）：{len(c["page_number_misreads"])} 处' +
                   ('：' + '；'.join(f'PDF {x["pdf_page"]} 识别为 {x["printed_ocr"]}，应为 {x["printed_voted"]}'
                                   for x in c['page_number_misreads']) if c['page_number_misreads'] else ''))
        out.append(f'- 正文块缺少章归属：{c["body_blocks_without_chapter"]}；bbox 超出页面：{len(c["bbox_out_of_page"])}'
                   + (f'（{", ".join(c["bbox_out_of_page"][:8])}）' if c['bbox_out_of_page'] else ''))
        out.append(f'- 正文中识别到的编号条目：' + '，'.join(f'{k} {v}' for k, v in c['numbered_items'].items()))
        if c['numbering_gaps']:
            out.append(f'- 编号缺口（可能是 OCR 漏识别、标题粘连，或教材本身跳号）共 {len(c["numbering_gaps"])} 组：'
                       + '；'.join(c['numbering_gaps']))
        if c['order_issues']:
            out.append(f'- **锚点顺序与编号不符**：' + '；'.join(c['order_issues']))
        if c['empty_nodes']:
            out.append(f'- **无块的节点**：' + '，'.join(c['empty_nodes']))
        if c['not_title_anchored']:
            out.append('\n未能按标题锚定（回退到页首或缺页码），需人工看一眼：\n')
            out.append('| 节点 | 目录原文 | 方式 | 最佳候选（得分） |\n|---|---|---|---|')
            for x in c['not_title_anchored']:
                out.append(f'| `{x["id"]}` | {x["raw"]} | {x["method"]} | {x["best_candidate"] or "—"} ({x["score"]}) |')
        if c['header_conflicts']:
            out.append(f'\n页眉与章节归属冲突（共 {len(c["header_conflicts"])} 页，列前 30）：\n')
            out.append('| PDF 页 | 页眉 | 页眉声称 | 本页实际归属 |\n|---|---|---|---|')
            for x in c['header_conflicts'][:30]:
                out.append(f'| {x["pdf_page"]} | {x["header"]} | {x["claims"]} | {", ".join(x["assigned"])} |')
        out.append('\n章节树（块数，PDF 页范围）：\n')
        for n in ns:
            ind = {'chapter': 0, 'backmatter': 0, 'section': 1, 'chapter_review': 1}.get(n['kind'], 2)
            flag = '' if n.get('anchor_method') in ANCHOR_OK else f' ⚠ {n.get("anchor_method")}'
            rng = f'p{n["pdf_page_range"][0]}–{n["pdf_page_range"][1]}' if n['pdf_page_range'] else '—'
            label = {'section': f'§{n["num"]} {n["title"]}', 'subsection': f'{n["num"]} {n["title"]}'}.get(n['kind'], n['raw'])
            if label != n['raw'] and n['kind'] == 'section' and not n['raw'].lstrip('§$5 ').startswith(n['num']):
                label += f'（目录 OCR：{n["raw"]}）'
            out.append(f'{"  " * ind}- {label}（{n["block_count"]} 块，{rng}）{flag}')
    return '\n'.join(out) + '\n'


def main():
    metas, all_nodes, all_blocks, all_pages = [], [], [], []
    nodes_by_book, checks_by_book = {}, {}
    for bid in BOOKS:
        meta, nodes, blocks, pages, checks = build_book(bid)
        metas.append(meta)
        nodes_by_book[bid], checks_by_book[bid] = nodes, checks
        all_nodes += nodes
        all_blocks += blocks
        all_pages += pages
    lalu = OUT / 'lalu'
    if (lalu / 'blocks.jsonl').exists():
        lb = [json.loads(x) for x in (lalu / 'blocks.jsonl').read_text(encoding='utf-8').splitlines()]
        ln = json.loads((lalu / 'toc.json').read_text(encoding='utf-8'))['nodes']
        all_blocks += lb
        all_nodes += ln
        print('LALU', len(lb), 'blocks;', len(ln), 'toc nodes (LaTeX source, see lalu/构建报告.md)')
    jsonl(OUT / 'blocks.jsonl', all_blocks)
    jsonl(OUT / 'pages.jsonl', all_pages)
    jsonsave(OUT / 'toc.json', {'books': metas, 'nodes': all_nodes})
    jsonsave(OUT / 'checks.json', checks_by_book)
    write_sqlite(OUT / 'textbook_index.sqlite', all_blocks, all_nodes, all_pages)
    save(OUT / '构建报告.md', report(metas, nodes_by_book, checks_by_book))
    for m in metas:
        c = checks_by_book[m['book']]
        ns = nodes_by_book[m['book']]
        print(m['book'], m['blocks'], 'blocks;', len(ns), 'toc nodes;',
              sum(1 for n in ns if n.get('anchor_method') in ANCHOR_OK), 'anchored ok;',
              f'header {c["header_agree"]}/{c["header_conflict"]};', 'order issues', len(c['order_issues']))


if __name__ == '__main__':
    main()
