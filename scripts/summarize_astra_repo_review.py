"""Validate the frozen GitHub evidence and publish the supplemental review ledger."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/astra'
EXT=OUT/'external/wangziyu1234-Mathematics-II'
LABELS={'agree':'答案与推导一致','equivalent':'答案等价','corrected':'本轮已修正',
        'repository_issue':'仓库存在问题','source_conflict':'来源或条件疑点','stem_only':'题干一致（无解析）'}
FIELDS=['stem','answer','solution','status','notes']

def write_json(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

def main():
    manifest=json.loads((EXT/'manifest.json').read_text())
    errors=[];rows=[];years=[];changes=[]
    for f in manifest['files']:
        p=EXT/f['path']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']:
            errors.append('Snapshot changed or missing: '+f['path'])
    for y in range(1987,2027):
        doc=json.loads((OUT/'final'/f'{y}.json').read_text())
        old=json.loads((OUT/'audit/pre-github-review'/f'{y}.json').read_text())
        oldq={q['question_id']:q for q in old['questions']}
        records=[]
        for q in doc['questions']:
            qid=q['question_id'];r=q.get('repo_review')
            if not r:
                errors.append(qid+': missing supplemental review');continue
            if r.get('commit')!=manifest['commit'] or r.get('repository')!=manifest['repository']:
                errors.append(qid+': wrong evidence version')
            if r.get('verdict') not in LABELS or not r.get('explanation'):
                errors.append(qid+': invalid verdict/explanation')
            scope='stem_only' if y<2000 else 'stem_answer_solution'
            if (y>=2000)!=bool(r.get('solution_reference')):
                errors.append(qid+': incorrect coverage claim')
            for key in ['exam_reference','solution_reference']:
                if r.get(key):
                    p=(ROOT/r[key]).resolve()
                    if not p.is_relative_to(EXT) or not p.is_file():errors.append(qid+': reference missing/outside snapshot '+key)
            diff={f:{'before':oldq[qid].get(f),'after':q.get(f)} for f in FIELDS if oldq[qid].get(f)!=q.get(f)}
            row={'question_id':qid,'year':y,'label':q['label'],'scope':scope,'verdict':r['verdict'],
                 'explanation':r['explanation'],'exam_reference':r['exam_reference'],
                 'solution_reference':r.get('solution_reference'),'changed_fields':list(diff),
                 'needs_confirmation':q['status']!='solved' or q['review']['verdict']=='unresolved'}
            rows.append(row);records.append(row)
            if diff:changes.append(dict(question_id=qid,year=y,label=q['label'],fields=diff))
        counts=Counter(r['verdict'] for r in records)
        years.append({'year':y,'questions':len(doc['questions']),'reviewed':len(records),
                      'scope':'仅题干' if y<2000 else '题干、答案与推导','verdicts':dict(counts)})
        md=[f'# {y} 年 · GitHub 仓库补充核对',
            f'核对范围：{years[-1]["scope"]}。固定提交 `{manifest["commit"]}`。',
            '仓库答案注明“我的解答，未与官方核对”。本轮不以仓库结论替代数学验证；原独立稿与前轮校对稿均保留。',
            '[返回仓库复核汇总](../仓库复核汇总.md)']
        for r in records:
            md += [f'<a id="{r["question_id"]}"></a>', f'## [{r["label"]}](../index.html#{r["question_id"]}) · {LABELS[r["verdict"]]}',r['explanation']]
            if r['changed_fields']:md += ['本轮变更字段：'+ '、'.join(r['changed_fields'])+'。具体前后内容保存在 audit/github-review-changes.json。']
            for k in ['exam_reference','solution_reference']:
                if r[k]:
                    rel=Path(r[k]).relative_to(EXT.relative_to(ROOT)).as_posix()
                    md += [f'[仓库{"题干" if k=="exam_reference" else "解析"}（固定版本）]({manifest["repository"]}/blob/{manifest["commit"]}/{quote(rel)})']
        (OUT/'repo-review'/f'{y}.md').write_text('\n\n'.join(md)+'\n')
    if len(rows)!=872:errors.append(f'Expected 872 reviews, found {len(rows)}')
    now=datetime.now(timezone.utc).isoformat();counts=Counter(r['verdict'] for r in rows)
    record={'reviewed_at':now,'repository':manifest['repository'],'commit':manifest['commit'],
            'snapshot_files':len(manifest['files']),'question_count':len(rows),
            'scope_counts':dict(Counter(r['scope'] for r in rows)), 'verdicts':dict(counts),
            'changed_questions':len(changes),'changed_field_counts':dict(Counter(f for r in changes for f in r['fields'])),
            'needs_confirmation':sum(r['needs_confirmation'] for r in rows),'years':years,'questions':rows,'errors':errors}
    write_json(OUT/'repo-review/summary.json',record)
    write_json(OUT/'audit/github-review-changes.json',{'reviewed_at':now,'commit':manifest['commit'],
         'baseline':'output/astra/audit/pre-github-review','note':'相对前轮校对稿的变化，不是独立初稿错误计数。','changes':changes})
    md=['# GitHub 仓库补充复核汇总',
        f'本轮使用 [wangziyu1234/Mathematics-II-]({manifest["repository"]}/tree/{manifest["commit"]})，固定提交 `{manifest["commit"]}`。',
        f'逐题记录 {len(rows)} 条：1987–1999 年 265 条仅核对题干；2000–2026 年 607 条核对题干、答案和关键推导。',
        '仓库声明答案为个人解答且尚未与官方核对。早年仓库没有答案，不能将题干一致计成答案复核通过；不同资料也可能来自共同题源，不假定统计独立。',
        f'本轮后仍有 {record["needs_confirmation"]} 道题因来源或条件解释疑点保留标记。新增记录可在网页“仓库复核”筛选中按题查看。',
        '[打开逐题索引](index.html) · [原独立稿校对汇总](校对汇总.md)',
        '## 本轮核对结论']
    md += [f'- {LABELS[k]}：{v}' for k,v in counts.items()]
    md += ['## 本轮内容变化',
           '以下比较对象是上一轮校对稿。题干排版、等价表达和条件说明变更均单列，不能把所有变化都算作数学错题。']
    lookup={r['question_id']:r for r in rows}
    for c in changes:
        r=lookup[c['question_id']]
        md += [f'### [{c["year"]} 年 {c["label"]}](index.html#{c["question_id"]})',
               '变更字段：'+ '、'.join(c['fields'])+'。',r['explanation']]
    md += ['## 仓库问题与其他版本差异',
           '下列题目已有明确的本地解答；仍保留仓库转录、论证或版本差异，避免仅凭结果相同忽略条件。']
    for r in rows:
        if r['verdict']=='repository_issue' or (r['verdict']=='source_conflict' and not r['needs_confirmation']):
            md += [f'### [{r["year"]} 年 {r["label"]}](index.html#{r["question_id"]})',r['explanation']]
    md += ['## 仍需确认的题目']
    for r in rows:
        if r['needs_confirmation']:
            md += [f'### [{r["year"]} 年 {r["label"]}](index.html#{r["question_id"]})',r['explanation']]
    md += ['## 逐年记录','| 年份 | 条目 | 核对范围 | 本轮结论 |','|---|---:|---|---|']
    for y in years:
        summary='；'.join(f'{LABELS[k]} {v}' for k,v in y['verdicts'].items())
        md += [f'| [{y["year"]}](repo-review/{y["year"]}.md) | {y["reviewed"]}/{y["questions"]} | {y["scope"]} | {summary} |']
    md += ['## 证据与保留记录',
           '- `external/wangziyu1234-Mathematics-II/manifest.json`：获取时间、固定提交、86 个资料文件的 SHA-256。',
           '- `repo-review/summary.json`：872 个稳定题号的复核范围、结论与说明；各年 JSON 含工作记录。',
           '- `audit/pre-github-review/`：本轮前40份校对稿；`audit/github-review-changes.json`：本轮字段级前后差异。',
           '- 独立稿 `drafts/` 与试题输入 `input/` 均不修改，仍以盲锁散列验证。']
    (OUT/'仓库复核汇总.md').write_text(re.sub(r'(?m)(\|[^\n]*\|)\n\n(?=\|)',r'\1\n','\n\n'.join(md))+'\n')
    print(json.dumps({k:record[k] for k in ['question_count','scope_counts','verdicts','changed_questions','changed_field_counts','needs_confirmation','errors']},ensure_ascii=False))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
