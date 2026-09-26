"""Compare codex-exec mapping (output/mapping/raw) with direct-API mapping (output/mapping/direct_test).

  python3 scripts/compare_engines.py [DIRECT_DIR] QUESTION_ID ...   (DIRECT_DIR under output/mapping, default direct_test)
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import map_questions as mq  # noqa: E402

A_DIR = mq.OUT / 'raw'


def main(args):
    B_DIR = mq.OUT / (args.pop(0) if args and not args[0].startswith('math2-') else 'direct_test')
    ids = args
    rows, order = mq.load_blocks()

    def span(c):
        s, e = sorted((order.get(c['start_uid'], -1), order.get(c['end_uid'], -1)))
        return set(range(s, e + 1))

    tot = {k: 0 for k in ('a_in', 'a_cached', 'a_out', 'b_in', 'b_cached', 'b_out', 'a_cit', 'b_cit', 'a_match',
                          'b_match', 'a_core', 'a_core_in_b', 'verify_b', 'prim_overlap', 'q')}
    print(f'{"question":18s} {"codex in/cached/out":>24s} {"direct in/cached/out":>24s}  cites A→B  B→A  core  topics')
    for qid in ids:
        a = json.loads((A_DIR / f'{qid}.json').read_text(encoding='utf-8'))
        fb = B_DIR / f'{qid}.json'
        if not fb.exists():
            print(qid, 'direct missing')
            continue
        b = json.loads(fb.read_text(encoding='utf-8'))
        ua, ub = a['usage'], b['usage']
        am = sum(any(span(x) & span(y) for y in b['citations']) for x in a['citations'])
        bm = sum(any(span(y) & span(x) for x in a['citations']) for y in b['citations'])
        core = [x for x in a['citations'] if x['role'] == 'core']
        cm = sum(any(span(x) & span(y) for y in b['citations']) for x in core)
        vb = sum(mq.repair(dict(c), rows, order) in ('ok', 'repaired') for c in b['citations'])
        pa = {t['card_id'] for t in a['topics'] if t['relation'] == 'primary'}
        pb = {t['card_id'] for t in b['topics'] if t['relation'] == 'primary'}
        po = len(pa & pb) / max(1, len(pa | pb))
        print(f'{qid:18s} {ua["input_tokens"]:>8,}/{ua["cached_input_tokens"]:>7,}/{ua["output_tokens"]:>5,} '
              f'{ub["input_tokens"]:>8,}/{ub["cached_input_tokens"]:>7,}/{ub["output_tokens"]:>5,}  '
              f'{am:>2}/{len(a["citations"]):<2}  {bm:>2}/{len(b["citations"]):<2}  {cm}/{len(core)}  '
              f'{len(pa & pb)}/{len(pa | pb)}  verify {vb}/{len(b["citations"])}')
        for k, v in (('a_in', ua['input_tokens']), ('a_cached', ua['cached_input_tokens']),
                     ('a_out', ua['output_tokens']), ('b_in', ub['input_tokens']),
                     ('b_cached', ub['cached_input_tokens']), ('b_out', ub['output_tokens']),
                     ('a_cit', len(a['citations'])), ('b_cit', len(b['citations'])), ('a_match', am),
                     ('b_match', bm), ('a_core', len(core)), ('a_core_in_b', cm), ('verify_b', vb),
                     ('prim_overlap', po), ('q', 1)):
            tot[k] += v
    n = tot['q']
    print(f'\nper question  codex: in {tot["a_in"] / n:,.0f} (uncached {(tot["a_in"] - tot["a_cached"]) / n:,.0f}), '
          f'out {tot["a_out"] / n:,.0f}   direct: in {tot["b_in"] / n:,.0f} '
          f'(uncached {(tot["b_in"] - tot["b_cached"]) / n:,.0f}), out {tot["b_out"] / n:,.0f}')
    print(f'citations codex {tot["a_cit"]} (found by direct {tot["a_match"]}), direct {tot["b_cit"]} '
          f'(found by codex {tot["b_match"]}); codex core found by direct {tot["a_core_in_b"]}/{tot["a_core"]}; '
          f'direct quotes verified {tot["verify_b"]}/{tot["b_cit"]}; mean primary-topic Jaccard '
          f'{tot["prim_overlap"] / n:.2f}')


if __name__ == '__main__':
    main(sys.argv[1:])
