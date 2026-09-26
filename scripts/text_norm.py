"""One spelling for names shown to people: knowledge-card labels/titles and textbook TOC titles.

  python3 scripts/text_norm.py cards      rewrite output/textbook/cards/*.json in place (idempotent; the first
                                          rewrite keeps the originals as label_raw / title_raw)
  python3 scripts/text_norm.py show       list what would change, without writing

Rules
- Titles are plain Unicode text (no TeX), so they read the same in HTML, the terminal and canvas labels:
  $…$ / \\(…\\) are unwrapped, common commands become symbols, simple ^x / _x become super/subscripts.
- A space separates CJK from Latin letters, digits and formulas (the majority style of the cards).
- Half-width brackets around formulas, full-width （…） around Chinese text.
- Labels: equation numbers read 式(1.2.3); full-width brackets and ASCII primes are normalised.
"""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / 'output/textbook/cards'

CJK = r'\u4e00-\u9fff'
SYMBOLS = {
    r'\pi': 'π', r'\varphi': 'φ', r'\phi': 'φ', r'\lambda': 'λ', r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ',
    r'\mu': 'μ', r'\sigma': 'σ', r'\theta': 'θ', r'\xi': 'ξ', r'\eta': 'η', r'\delta': 'δ', r'\varepsilon': 'ε',
    r'\epsilon': 'ε', r'\omega': 'ω', r'\Delta': 'Δ', r'\pm': '±', r'\mp': '∓', r'\times': '×', r'\cdot': '·',
    r'\infty': '∞', r'\to': '→', r'\le': '≤', r'\leq': '≤', r'\ge': '≥', r'\geq': '≥', r'\ne': '≠', r'\neq': '≠',
    r'\in': '∈', r'\subset': '⊂', r'\cap': '∩', r'\cup': '∪', r'\int': '∫', r'\sum': '∑', r'\sqrt': '√',
    r'\ldots': '…', r'\cdots': '⋯', r'\prime': '′',
}
FONTS = {'R': 'ℝ', 'C': 'ℂ', 'Q': 'ℚ', 'Z': 'ℤ', 'N': 'ℕ'}  # \mathbf / \mathbb number sets
SCRIPT = {'L': 'ℒ'}
SUP = dict(zip('0123456789+-=()nijkmrtxyTabcdeghlopsuvw', '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱʲᵏᵐʳᵗˣʸᵀᵃᵇᶜᵈᵉᵍʰˡᵒᵖˢᵘᵛʷ'))
SUB = dict(zip('0123456789+-=()aeijklmnoprstuvx', '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ'))


def _script(s, table):
    return ''.join(table[c] for c in s) if s and all(c in table for c in s) else None


def tex_to_plain(s):
    """Unwrap TeX math in a short title and render it as Unicode."""
    s = re.sub(r'\\\((.*?)\\\)', r'\1', s)
    s = re.sub(r'\$\s*(.*?)\s*\$', r'\1', s)
    for _ in range(3):  # nested \frac
        s = re.sub(r'\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}',
                   lambda m: '/'.join(x if re.fullmatch(r'\w+', x) else f'({x})' for x in (m[1], m[2])), s)
    s = re.sub(r'\\(?:mathbf|mathbb|boldsymbol)\{([A-Z])\}', lambda m: FONTS.get(m[1], m[1]), s)
    s = re.sub(r'\\mathcal\{([A-Z])\}', lambda m: SCRIPT.get(m[1], m[1]), s)
    s = re.sub(r'\\(?:mathrm|operatorname|text|mathbf|mathit)\s*\{([^{}]*)\}', r'\1', s)
    s = re.sub(r'\\mathrm\s*(\w)', r'\1', s)
    s = re.sub(r'(\\[a-zA-Z]+) ?', lambda m: SYMBOLS.get(m[1], m[0]), s)  # a command eats the space after it
    s = re.sub(r'\\([,;!: ])', ' ', s)
    s = s.replace(r'\{', '{').replace(r'\}', '}')

    # ^{…} always; a bare ^x only when it is a whole exponent (not the 3 of 1.03^3.98)
    s = re.sub(r'\^\{([^{}]*)\}|\^([A-Za-z0-9])(?![A-Za-z0-9.])', lambda m: _script(m[1] or m[2], SUP) or
               ('^(' + m[1] + ')' if m[1] and len(m[1]) > 1 else '^' + (m[1] or m[2])), s)
    s = re.sub(r'_\{([^{}]*)\}|_([A-Za-z0-9])(?![A-Za-z0-9.])', lambda m: _script(m[1] or m[2], SUB) or
               ('_' + (m[1] or m[2])), s)
    return s


LATINISH = r'A-Za-z0-9α-ωΑ-Ωℝℂℚℤℕℒ∞′″¹²³⁰-⁹ⁿⁱʲᵏᵐʳᵗˣʸᵀᵃᵇᶜᵈᵉᵍʰˡᵒᵖˢᵘᵛʷ₀-₉ₐₑᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ'


def spacing(s):
    """Chinese text in full-width brackets, one space between CJK and Latin/formula runs."""
    s = re.sub(rf'\(([{CJK}][^()]*)\)', r'（\1）', s)
    s = re.sub(rf'([{CJK}])([{LATINISH}(\[|√∫∑])', r'\1 \2', s)
    s = re.sub(rf'([{CJK}])([+\-−](?=[{LATINISH}]))', r'\1 \2', s)
    s = re.sub(rf"([{LATINISH})\]|!'])([{CJK}])", r'\1 \2', s)
    s = re.sub(r'(定理|定义|例|命题|推论|引理|公式|习题|思考题|性质|反例|问题|第) (?=\d)', r'\1', s)  # 例5.1, not 例 5.1
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def title(s):
    return spacing(tex_to_plain(s or ''))


def label(s):
    s = (s or '').strip()
    s = s.replace('（', '(').replace('）', ')')
    s = re.sub(r"(\d)''|(\d)\"", lambda m: (m[1] or m[2]) + '″', s)
    s = re.sub(r"(\d)'", r'\1′', s)
    s = re.sub(r'^公式\s*(?=\()', '', s)
    if re.fullmatch(r'\(\d+(?:\.\d+)+\)(?:、\(\d+(?:\.\d+)+\))*', s):
        s = '式' + s  # equation numbers: 式(1.2.3)、(1.2.4)
    return s


def card_name(card):
    return f'{card["label"]} {card["title"]}' if card.get('label') else card['title']


def normalize_card(c):
    """In place; returns True if the card changed. Originals are kept once as label_raw / title_raw."""
    lab, tit = label(c.get('label_raw', c['label'])), title(c.get('title_raw', c['title']))
    if (lab, tit) == (c['label'], c['title']):
        return False
    c.setdefault('label_raw', c['label'])
    c.setdefault('title_raw', c['title'])
    c['label'], c['title'] = lab, tit
    return True


def cmd_cards(write):
    changed = files = 0
    for f in sorted(CARDS.glob('*_*.json')):
        d = json.loads(f.read_text(encoding='utf-8'))
        hits = []
        for c in d['cards']:
            before = card_name(c)
            if normalize_card(c):
                hits.append((before, card_name(c)))
        if hits:
            files += 1
            changed += len(hits)
            if write:
                f.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')  # = jsonsave
            else:
                for a, b in hits:
                    print(f'{a}\n  → {b}')
    print(f'{"rewrote" if write else "would change"} {changed} cards in {files} files')


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg in ('cards', 'show'):
        cmd_cards(write=arg == 'cards')
    else:
        print(__doc__)
