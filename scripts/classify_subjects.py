"""Tag each bank question as calculus (GS) or linear algebra (LA), so LA mapping can wait for the new textbook.

Keyword rule on the stem, checked against the paper structure (no LA before 1997; five LA items a year since
2004 at fixed positions) plus explicit overrides for stems that use α as an ordinary variable.
Output: output/question_subjects.json
"""
from pathlib import Path
from collections import Counter
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import jsonsave  # noqa: E402

LA = (r'矩阵|行列式|向量组|线性相关|线性无关|线性表示|特征值|特征向量|二次型|线性方程组|方程组.{0,6}(解|通解)|'
      r'基础解系|秩|相似|合同|正交变换|正定|伴随|可逆矩阵|\\begin\{(p|b|v)matrix\}')
GS = r'\\int|\\lim|导数|极限|微分方程|积分|f\s*\(x\)|f\'|连续|可导|偏导|曲线|dx|\\frac\{d'
OVERRIDES = {
    'math2-2016-q1': ('GS', 'α_i 是无穷小量的名字'),
    'math2-2023-q6': ('GS', 'α 是反常积分中的参数'),
    # found in QA (2026-09-25): no matrix keywords in the stem, but linear-algebra questions
    'math2-2003-XII': ('LA', '三条直线共点 ⇔ 线性方程组有解，用行列式判定'),
    'math2-2022-q10': ('LA', '含参数向量组的等价'),
}


def main():
    qs = json.loads((ROOT / 'output/astra/question_index.json').read_text(encoding='utf-8'))['questions']
    out = {}
    for q in qs:
        qid, t = q['question_id'], q['stem']
        la, gs = len(re.findall(LA, t)), len(re.findall(GS, t))
        subject = 'LA' if la and la >= gs else 'GS'
        how = 'keywords'
        if qid in OVERRIDES:
            subject, how = OVERRIDES[qid][0], 'override: ' + OVERRIDES[qid][1]
        out[qid] = {'subject': subject, 'year': q['year'], 'label': q['label'], 'method': how}
    jsonsave(ROOT / 'output/question_subjects.json', out)
    print(Counter(v['subject'] for v in out.values()))


if __name__ == '__main__':
    main()
