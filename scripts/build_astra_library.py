"""Build the local, question-indexed Astra answer library without changing drafts."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/astra'
VERDICTS = {'agree': '一致', 'equivalent': '等价', 'corrected': '独立稿已修正',
            'reference_issue': '来源问题', 'unresolved': '待确认'}
REPO_VERDICTS = {'agree': '答案与推导一致', 'equivalent': '答案等价',
                 'corrected': '本轮已修正', 'repository_issue': '仓库存在问题',
                 'source_conflict': '来源或条件疑点', 'stem_only': '题干一致（无解析）'}


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.md':
        text = re.sub(r'(?m)(\|[^\n]*\|)\n\n(?=\|)', r'\1\n', text)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def jsonsave(path, data):
    save(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def images(text, source, destination):
    def replace(m):
        target = m[2]
        if target.startswith(('https://', 'http://', 'data:')):
            return m[0]
        p = Path(target)
        if not p.is_absolute():
            p = (ROOT / p) if target.startswith(('output/', 'source/')) else source.parent / p
        return f'![{m[1]}]({os.path.relpath(p.resolve(), destination)})'
    return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace, text)


def main():
    manifest = json.loads((OUT / 'input_manifest.json').read_text())
    expected = [e['year'] for e in manifest['exams']]
    all_questions, years, errors = [], [], []
    seen = set()
    for year in expected:
        path = OUT / 'final' / f'{year}.json'
        if not path.exists():
            continue
        doc = json.loads(path.read_text())
        draftpath = OUT / 'drafts' / f'{year}.json'
        draft = json.loads(draftpath.read_text())
        if doc['year'] != year or doc.get('model') != 'gpt-6-astra':
            errors.append(f'{year}: invalid year/model')
        questions = doc['questions']
        if [q['question_id'] for q in questions] != [q['question_id'] for q in draft['questions']]:
            errors.append(f'{year}: final question IDs/order differ from draft')
        source = ROOT / f'output/markdown/{year}/{year}-exam.md'
        md = [f'# {year} 年数学二 · Astra 独立解答（校对版）',
              '先独立解答，锁定初稿后再对照现有参考资料。来源疑点和未决项在各题列明。',
              '[返回逐题索引](../index.html)', '## 题目目录']
        ans = [f'# {year} 年数学二 · Astra 仅答案（校对版）',
               '证明题仅列结论，完整推导及校对记录见对应解答。']
        for q in questions:
            md.append(f'- [{q["label"]}](#{q["question_id"]})')
        for ordinal, q in enumerate(questions, 1):
            qid = q['question_id']
            if qid in seen or not re.fullmatch(r'math2-\d{4}-[A-Za-z0-9_-]+', qid):
                errors.append(f'{qid}: duplicate/invalid ID')
            seen.add(qid)
            for field in ['label', 'section', 'stem', 'answer', 'solution']:
                if not isinstance(q.get(field), str) or not q[field].strip():
                    errors.append(f'{qid}: empty {field}')
            review = q.get('review', {})
            repo_review = q.get('repo_review')
            repo_block = []
            if repo_review:
                repo_block = ['**GitHub 仓库复核：'+REPO_VERDICTS.get(repo_review['verdict'], repo_review['verdict'])+'**',
                              repo_review['explanation']]
                if not repo_review.get('solution_reference'):
                    repo_block += ['此年仓库未提供答案，本轮仅核对题干。']
                repo_block += [f'[固定仓库版本]({repo_review["repository"]}/tree/{repo_review["commit"]})']
            if review.get('verdict') not in VERDICTS or not review.get('references') or not review.get('explanation'):
                errors.append(f'{qid}: incomplete review')
            for ref in review.get('references', []):
                if not (ROOT / ref.split('#',1)[0]).is_file():
                    errors.append(f'{qid}: missing reference {ref}')
            if q.get('status') not in ['solved', 'uncertain', 'blocked_by_source']:
                errors.append(f'{qid}: invalid status')
            text = '\n'.join(q.get(k, '') for k in ['stem', 'answer', 'solution'])
            if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text):
                errors.append(f'{qid}: control character in math/text')
            entry = dict(q, year=year, ordinal=ordinal)
            entry['draft_answer'] = draft['questions'][ordinal - 1]['answer']
            for field in ['stem', 'answer', 'solution']:
                entry[field] = images(entry[field], source, OUT)
            all_questions.append(entry)
            block = [f'<a id="{qid}"></a>', f'## {q["label"]} · {q["section"]}',
                     images(q['stem'], source, OUT/'markdown'), '**答案**', q['answer'],
                     '**推导**', images(q['solution'], source, OUT/'markdown'),
                     f'**校对：{VERDICTS.get(review.get("verdict"), "缺失")}**', review.get('explanation', '')]
            if q.get('notes'):
                block += ['**说明**'] + [f'- {n}' for n in q['notes']]
            block += repo_block
            block += ['**对照材料**'] + [f'- [{Path(r).name}]({os.path.relpath(ROOT/r, OUT/"markdown")})' for r in review.get('references', [])]
            md.extend(block)
            ans += [f'## {q["label"]}', q['answer']]
            if review.get('verdict') in ['corrected', 'reference_issue', 'unresolved'] or q.get('status') != 'solved':
                ans += [f'校对：{VERDICTS.get(review.get("verdict"))}。{review.get("explanation", "")}']
            if repo_review and repo_review['verdict'] in ['corrected','repository_issue','source_conflict']:
                ans += repo_block
            individual = [f'# {year} 年 · {q["label"]}', f'稳定编号：`{qid}`',
                          f'[在索引中查看](../index.html#{qid})',
                          images(q['stem'], source, OUT/'questions'), '**答案**', q['answer'],
                          '**推导**', images(q['solution'], source, OUT/'questions'),
                          '**校对记录**', review.get('explanation', '')]
            if q.get('notes'):
                individual += ['**说明**'] + [f'- {n}' for n in q['notes']]
            individual += repo_block
            save(OUT/'questions'/f'{qid}.md', '\n\n'.join(individual)+'\n')
        save(OUT/'markdown'/f'{year}.md', '\n\n'.join(md)+'\n')
        save(OUT/'answers'/f'{year}.md', '\n\n'.join(ans)+'\n')
        years.append({'year': year, 'questions': len(questions),
                      'verdicts': dict(Counter(q['review']['verdict'] for q in questions)),
                      'draft_sha256': hashlib.sha256(draftpath.read_bytes()).hexdigest(),
                      'final_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    data = {'updated': datetime.now(timezone.utc).isoformat(), 'model': 'gpt-6-astra',
            'expected_years': expected, 'years': years, 'questions': all_questions,
            'missing_years': [y for y in expected if y not in [r['year'] for r in years]],
            'verdict_labels': VERDICTS, 'repo_verdict_labels': REPO_VERDICTS}
    jsonsave(OUT/'question_index.json', data)
    save(OUT/'assets/data.js', 'window.ASTRA_LIBRARY='+json.dumps(data, ensure_ascii=False).replace('</', '<\\/')+';\n')
    # Keep an already-open browser from mixing old data with new review controls.
    index_path=OUT/'index.html'
    html=index_path.read_text()
    for asset in ['data.js','library.js','library.css']:
        digest=hashlib.sha256((OUT/'assets'/asset).read_bytes()).hexdigest()[:12]
        html=re.sub(r'(assets/'+re.escape(asset)+r')(?:\?v=[a-f0-9]+)?',
                    lambda m:m[1]+'?v='+digest,html)
    save(index_path,html)
    with (OUT/'question_index.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['稳定编号','年份','题号','题型','答案','校对状态','校对说明','单题文件','仓库复核范围','仓库复核结论','仓库复核说明'])
        for q in all_questions:
            rr=q.get('repo_review',{})
            writer.writerow([q['question_id'],q['year'],q['label'],q['section'],q['answer'],
                             VERDICTS[q['review']['verdict']],q['review']['explanation'],f'questions/{q["question_id"]}.md',
                             ('题干、答案与推导' if rr.get('solution_reference') else '仅题干') if rr else '',
                             REPO_VERDICTS.get(rr.get('verdict'),''),rr.get('explanation','')])
    dbpath=OUT/'question_index.sqlite.tmp'
    dbpath.unlink(missing_ok=True)
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE questions (question_id TEXT PRIMARY KEY, year INTEGER, ordinal INTEGER, label TEXT, section TEXT, stem TEXT, answer TEXT, solution TEXT, verdict TEXT, status TEXT, record_json TEXT)')
        db.executemany('INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            [(q['question_id'],q['year'],q['ordinal'],q['label'],q['section'],q['stem'],q['answer'],q['solution'],q['review']['verdict'],q['status'],json.dumps(q,ensure_ascii=False)) for q in all_questions])
        db.execute('CREATE INDEX year_question ON questions(year, ordinal)')
    dbpath.replace(OUT/'question_index.sqlite')
    jsonsave(OUT/'validation.json', {'checked_at':data['updated'],'completed_years':len(years),
             'question_count':len(all_questions),'errors':errors,'missing_years':data['missing_years']})
    summary=Counter(q['review']['verdict'] for q in all_questions)
    readme=['# 数学二 · Astra 独立解答与校对库',
            '[打开逐题索引](index.html)',
            f'模型：gpt-6-astra。解题工作任务并发上限：3。已完成 {len(years)}/40 年，共 {len(all_questions)} 个题目条目。',
            '先只读题干独立作答，完成批次初稿并记录 SHA-256 后，才读取参考资料校对。独立初稿永久保留；校对后的答案不代表初次作答全部正确。',
            '## 使用方式',
            '- 网页支持年份、题型、校对状态及关键词筛选；每题有稳定链接，可展开推导和校对依据。公式与字体随库附带，可离线阅读。',
            '- `markdown/YYYY.md`：年度完整解答；`answers/YYYY.md`：年度仅答案；`questions/题目编号.md`：单题文稿。',
            '- `question_index.json` / `.sqlite`：结构化题库；`.csv`：表格索引。',
            '- `drafts/`：独立稿；`final/`：校对稿；`reports/`：年度校对报告；`audit/`：独立稿锁定和完成记录。',
            '## 编号与质量说明',
            '保留原卷题号；早年的大题和小题联合编号。含关联子问的解答题可能共用一个主条目，因此条目数不等于所有最小子问数。',
            '来源为用户项目的 OCR 试卷和已有参考解析，并非官方评分。题干缺损、来源冲突及无法确定的问题会标为来源问题或待确认，不强行补成一致。',
            '## 当前校对计数']
    readme += [f'- {VERDICTS[k]}：{v}' for k,v in summary.items()]
    repo_count=sum(bool(q.get('repo_review')) for q in all_questions)
    if repo_count:
        readme += ['## GitHub 仓库补充复核',
                   f'已记录 {repo_count} 题的仓库核对。1987–1999 年仅有题干可核对，2000–2026 年另有个人答案与解析。仓库自述尚未与官方核对，不视为官方答案，也不假定其与已有资料独立。',
                   '[仓库复核汇总与逐年记录](仓库复核汇总.md)。原校对稿备份在 `audit/pre-github-review/`，本轮逐题记录在 `repo-review/`，固定版本资料与散列在 `external/`。']
    if data['missing_years']:readme += ['尚未完成：'+ '、'.join(map(str,data['missing_years']))+'。']
    save(OUT/'README.md','\n\n'.join(readme)+'\n')
    review_md=['# Astra 批量作答 · 校对汇总',
               f'已校对 {len(years)}/40 年、{len(all_questions)} 个题目条目。逐题结论包含题干修复、参考错误、解答修正和未决情况，不据此计算考试正确率。',
               '| 年份 | 条目 | 一致/等价 | 独立稿修正 | 来源问题 | 待确认 |',
               '|---|---:|---:|---:|---:|---:|']
    for row in years:
        v=row['verdicts'];y=row['year']
        review_md.append(f'| [{y}](reports/{y}.md) | {row["questions"]} | {v.get("agree",0)+v.get("equivalent",0)} | {v.get("corrected",0)} | {v.get("reference_issue",0)} | {v.get("unresolved",0)} |')
    if repo_count:
        review_md += ['', '[本轮 GitHub 仓库复核汇总](仓库复核汇总.md)。本轮结论与原独立稿校对分别记录；仓库早年没有答案，不能将全部条目都计作答案复核。']
    review_md += ['', '## 需要留意的题目', '“独立稿修正”也包括转义、排版和论证补充，具体原因以每题记录为准。']
    for q in all_questions:
        v=q['review']['verdict']
        if v not in ['agree','equivalent'] or q['status']!='solved':
            review_md += [f'### [{q["year"]} 年 {q["label"]}](index.html#{q["question_id"]}) · {VERDICTS[v]}',
                          q['review']['explanation']]
    save(OUT/'校对汇总.md','\n\n'.join(review_md)+'\n')
    print(json.dumps({'years':len(years),'questions':len(all_questions),'verdicts':dict(summary),'errors':errors},ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__=='__main__': main()
