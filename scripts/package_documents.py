"""Validate, index and package annual OCR editions with source evidence."""
import collections,hashlib,html,json,re,shutil,zipfile
from pathlib import Path
from pypdf import PdfReader,PdfWriter
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output'
D=json.loads((OUT/'documents.json').read_text())
status={x['id']:x['success'] for x in json.loads((OUT/'build-status.json').read_text())}
assert all(status.get(d['id']) for d in D),'Every edition must compile successfully before packaging.'
for d in D:
 p=OUT/'pdf'/str(d['year'])/(d['id']+'.pdf'); r=PdfReader(p)
 assert len(r.pages)>0
 d['pages']=len(r.pages);d['pdf']=str(p.relative_to(OUT));d['markdown']=f'markdown/{d["year"]}/{d["id"]}.md'
 d['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 for ext in ('.aux','.out','.log'):p.with_suffix(ext).unlink(missing_ok=True)
 # Store a portable source copy once per input.
 target=OUT/'sources'/(d['source_id']+'.pdf');target.parent.mkdir(exist_ok=True)
 if not target.exists():shutil.copy2(ROOT/d['source_path'],target)
 d['source_pdf']=str(target.relative_to(OUT))
# Remove stale, superseded editions from final PDF and Markdown folders.
valid={str(OUT/d['pdf']) for d in D};valid_md={str(OUT/d['markdown']) for d in D}
for p in (OUT/'pdf').glob('[12][0-9][0-9][0-9]/*.pdf'):
 if str(p) not in valid:p.unlink()
for p in (OUT/'markdown').glob('[12][0-9][0-9][0-9]/*.md'):
 if str(p) not in valid_md:p.unlink()
volumes=[];vdir=OUT/'pdf/汇总';vdir.mkdir(exist_ok=True)
for kind,label in [('试卷','历年试卷'),('解析','历年解析'),('答案速查','历年仅答案')]:
 writer=PdfWriter();selected=[d for d in D if d['kind']==kind]
 for d in selected:writer.append(str(OUT/d['pdf']),outline_item=d['title'],import_outline=False)
 writer.add_metadata({'/Title':f'数学二 1987–2026 {label}','/Author':'PaddleOCR-VL-1.6 OCR 整理','/Subject':'按年份书签导航；来源与校注见配套总目录'})
 path=vdir/f'数学二_1987-2026_{label}.pdf';writer.write(path)
 volumes.append({'label':label,'path':str(path.relative_to(OUT)),'pages':len(writer.pages),'documents':len(selected)})
 writer.close()
(OUT/'catalog.json').write_text(json.dumps({'documents':D,'volumes':volumes},ensure_ascii=False,indent=2))
summary='覆盖 1987–2026 共 40 年。试卷、解析、仅答案分别成册；保留独立解析版本及对应答案。'
notes='这些文稿由 PaddleOCR-VL-1.6 MCP 识别后重排，已检查文件覆盖、编译和代表页版式，尚未逐题校订全部公式。原始扫描与 OCR 输出保留，疑义请对照来源；已确认的修正见校注。'
rows=[];mdrows=[]
for y in range(1987,2027):
 group=[d for d in D if d['year']==y];cells=[];mdcells=[]
 for kind in ['试卷','解析','答案速查']:
  items=[d for d in group if d['kind']==kind];links=[];ml=[]
  for d in items:
   name={'试卷':'试卷','解析':'解析','答案速查':'仅答案'}[kind]+(' · 另一版' if d['id'].endswith('-2') else '')
   links.append(f'<div><a href="{d["pdf"]}">{name} PDF</a> <span>{d["pages"]} 页</span><br><a class="small" href="{d["markdown"]}">Markdown</a> · <a class="small" href="{d["source_pdf"]}">来源 PDF</a></div>')
   ml.append(f'[{name}]({d["pdf"]}) / [MD]({d["markdown"]})')
  cells.append('<td>'+''.join(links)+'</td>');mdcells.append('；'.join(ml))
 rows.append(f'<tr data-year="{y}"><th>{y}</th>'+''.join(cells)+'</tr>')
 mdrows.append('| '+str(y)+' | '+' | '.join(mdcells)+' |')
links=''.join(f'<a class="volume" href="{v["path"]}"><b>{v["label"]}</b><span>{v["documents"]} 份 · {v["pages"]} 页</span></a>' for v in volumes)
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>数学二历年真题文库</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#20364a;font:16px/1.7 system-ui,"Noto Sans CJK SC",sans-serif}main{max-width:1080px;margin:50px auto;padding:32px;background:white;border-radius:16px}h1{font-size:36px;line-height:1.3;margin-bottom:8px}.eyebrow{letter-spacing:3px;font-size:12px;color:#657b8c}p{max-width:900px}.muted,span{color:#657b8c;font-size:14px}a{color:#176582;text-decoration:none}a:hover{text-decoration:underline}.volumes{display:flex;gap:16px;margin:30px 0}.volume{flex:1;background:#edf4f7;border:1px solid #d4e3eb;padding:18px;border-radius:10px}.volume span{display:block}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:15px;border-bottom:1px solid #e4eaee;vertical-align:top}thead{background:#edf4f7}td div+div{margin-top:12px}.small{font-size:13px}input{padding:10px;border:1px solid #ccd9e0;border-radius:6px;font:inherit;margin-bottom:18px}aside{background:#fff8e8;padding:15px 20px;border-left:3px solid #e2bd6c;border-radius:4px;margin:25px 0}@media(max-width:650px){main{margin:0;padding:18px}.volumes{display:block}.volume{display:block;margin:10px 0}td,th{padding:8px}h1{font-size:28px}}
</style><main><div class="eyebrow">PADDLEOCR-VL-1.6 · 1987–2026</div><h1>数学二历年真题文库</h1><p>SUMMARY</p><div class="volumes">VOLUMES</div><aside>NOTES<br><a href="校注与质量说明.md">校注与质量说明</a> · <a href="来源清单.md">来源清单</a></aside><input id="year" placeholder="筛选年份，例如 2025" aria-label="筛选年份"><table><thead><tr><th>年份</th><th>试卷</th><th>解析</th><th>仅答案</th></tr></thead><tbody>ROWS</tbody></table><p class="muted">仅答案版按对应试卷的题号及选项顺序整理；证明题只保留结论或标注证明过程见解析。</p></main><script>document.querySelector('#year').addEventListener('input',e=>document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.dataset.year.includes(e.target.value.trim())))</script></html>'''
page=page.replace('SUMMARY',summary).replace('VOLUMES',links).replace('NOTES',notes).replace('ROWS',''.join(rows));(OUT/'总目录.html').write_text(page)
(OUT/'README.md').write_text('# 数学二历年试卷、解析与仅答案\n\n'+summary+'\n\n'+notes+'\n\n请先打开 [总目录](总目录.html)。\n\n## 合订本\n\n'+'\n'.join(f'- [{v["label"]}]({v["path"]})：{v["pages"]} 页。' for v in volumes)+'\n\n## 年度文稿\n\n| 年份 | 试卷 | 解析 | 仅答案 |\n|---|---|---|---|\n'+'\n'.join(mdrows)+'\n')
# Include portable Markdown image paths, OCR evidence, and originals; exclude credentials and temporary builds.
zip_path=OUT/'数学二_1987-2026_OCR整理文库.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for directory in ['pdf','markdown','sources']:
  for p in (OUT/directory).rglob('*'):
   if p.is_file() and p.suffix in ('.pdf','.md'):z.write(p,str(p.relative_to(OUT)))
 for p in (OUT/'ocr').glob('*/*'):
  if p.is_file() and p.suffix in ('.md','.jpg','.png'):z.write(p,str(p.relative_to(OUT)))
 for name in ['README.md','总目录.html','catalog.json','documents.json','来源清单.md','校注与质量说明.md','quality-report.json']:
  p=OUT/name
  if p.exists():z.write(p,name)
print(json.dumps({'documents':len(D),'volumes':volumes,'zip_mib':round(zip_path.stat().st_size/1024**2,1)},ensure_ascii=False))
