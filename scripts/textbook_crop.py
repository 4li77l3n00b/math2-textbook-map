"""Crop textbook blocks (crop box includes empty blocks whose text was merged into them) from the scanned PDF by `block_uid`, for OCR checks and review pages.

Usage: python3 scripts/textbook_crop.py OUT_DIR UID [UID ...]
Bboxes are in the CropBox at 2 px/pt after rotation, so pages are rendered with
`pdftoppm -cropbox -r 144` (see build_textbook_index.page_sizes).
"""
from pathlib import Path
import json
import sqlite3
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import BOOKS, SRC  # noqa: E402

DB = ROOT / 'output/textbook/textbook_index.sqlite'


def render(book, page, cache):
    k = (book, page)
    if k not in cache:
        tmp = Path(tempfile.mkdtemp())
        subprocess.run(['pdftoppm', '-cropbox', '-r', '144', '-f', str(page), '-l', str(page), '-png',
                        str(SRC / BOOKS[book][1]), str(tmp / 'p')], check=True)
        cache[k] = Image.open(next(tmp.glob('p-*.png')))
    return cache[k]


def crop(uids, out_dir, pad=6):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    cache, paths = {}, []
    for uid in uids:
        row = con.execute('select book, pdf_page, cx0, cy0, cx1, cy1 from blocks where uid=?', (uid,)).fetchone()
        if not row:
            print('unknown block', uid, file=sys.stderr)
            continue
        book, page, x0, y0, x1, y1 = row
        im = render(book, page, cache)
        box = (max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad))
        path = out_dir / f'{uid}.png'
        im.crop(box).save(path)
        paths.append(path)
    return paths


if __name__ == '__main__':
    for p in crop(sys.argv[2:], sys.argv[1]):
        print(p)
