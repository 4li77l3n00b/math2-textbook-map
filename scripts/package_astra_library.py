"""Package the complete library and its explicitly referenced local evidence."""
import json
import re
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/astra'

def main():
    index=json.loads((OUT/'question_index.json').read_text())
    assert not index['missing_years'], 'Do not package an incomplete library'
    for name in ['validation.json','integrity-report.json','math-validation.json']:
        assert not json.loads((OUT/name).read_text())['errors'], f'Unresolved validation failures: {name}'
    supplemental=OUT/'repo-review/summary.json'
    if supplemental.exists():
        supplemental_data=json.loads(supplemental.read_text())
        assert not supplemental_data['errors'], 'Incomplete or invalid supplemental review'
        assert supplemental_data['question_count']==len(index['questions'])
        assert all(q.get('repo_review') for q in index['questions'])
    files={p.resolve() for p in OUT.rglob('*') if p.is_file() and p.suffix not in ['.tmp','.pyc'] and p.name!='package-report.json'}
    for q in index['questions']:
        for ref in q['review']['references']:
            files.add((ROOT/ref.split('#',1)[0]).resolve())
    for row in index['years']:
        files.add((ROOT/f'output/markdown/{row["year"]}/{row["year"]}-exam.md').resolve())
    # Local image links in exported and reference Markdown retain their original layout.
    for p in list(files):
        if p.suffix.lower()!='.md':continue
        for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',p.read_text()):
            if target.startswith(('http://','https://','data:')):continue
            candidate=(p.parent/target).resolve()
            if candidate.is_file() and candidate.is_relative_to(ROOT):files.add(candidate)
    assert all(p.is_file() and p.is_relative_to(ROOT) for p in files)
    path=ROOT/'output/数学二_1987-2026_Astra独立解答.zip'
    tmp=path.with_suffix('.zip.tmp')
    pending=[q for q in index['questions'] if q['status']!='solved' or q['review']['verdict']=='unresolved']
    readme='数学二 1987–2026 · Astra 独立解答与校对库\n\n解压后打开 output/astra/index.html；无需启动服务，公式和字体可离线显示。\n\n'
    readme+=f'40 年，共 {len(index["questions"])} 个题目条目，{len(pending)} 道仍有题源/条件疑点。\n'
    readme+='完整解答：output/astra/markdown/\n仅答案：output/astra/answers/\n逐题 JSON/CSV/SQLite：output/astra/question_index.*\n初稿和校对审计：output/astra/drafts/、audit/\n校对汇总：output/astra/校对汇总.md\n\n参考材料仅为核对所用的项目资料，并非官方评分依据。\n'
    if supplemental.exists():
        readme+='\n已补充 GitHub 仓库复核：2000–2026 年607题核对题干、答案与推导；1987–1999 年265题仅核对题干（仓库无此段答案）。\n详见 output/astra/仓库复核汇总.md；固定提交与资料散列在 external/ 目录。\n'
    with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('开始阅读.txt',readme)
        for p in sorted(files):z.write(p,p.relative_to(ROOT).as_posix())
    tmp.replace(path)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
    report={'archive':str(path.relative_to(ROOT)),'files':len(files)+1,'bytes':path.stat().st_size,
            'years':40,'questions':len(index['questions']),'needs_confirmation':len(pending)}
    (OUT/'package-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
