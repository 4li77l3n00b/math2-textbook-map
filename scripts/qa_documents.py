import concurrent.futures,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output'
D=json.loads((OUT/'documents.json').read_text())
def check(d):
 p=OUT/'pdf'/str(d['year'])/(d['id']+'.pdf')
 if not p.exists():return {'id':d['id'],'error':'missing PDF'}
 r=subprocess.run(['pdftotext','-bbox',str(p),'-'],capture_output=True,text=True)
 pages=re.findall(r'<page width="([0-9.]+)" height="([0-9.]+)"[^>]*>(.*?)</page>',r.stdout,re.S)
 outside=[];margins=[]
 for n,(w,h,page) in enumerate(pages,1):
  for m in re.finditer(r'<word xMin="([0-9.-]+)" yMin="([0-9.-]+)" xMax="([0-9.-]+)" yMax="([0-9.-]+)"[^>]*>(.*?)</word>',page):
   x,y,x2,y2=map(float,m.group(1,2,3,4))
   if x<5 or x2>float(w)-5 or y<5 or y2>float(h)-5:outside.append({'page':n,'text':m[5][:35],'bbox':[x,y,x2,y2]})
   elif x<40 or x2>float(w)-40:margins.append({'page':n,'text':m[5][:35],'bbox':[x,y,x2,y2]})
 log=(OUT/'tex'/str(d['year'])/(d['id']+'.build.log')).read_text()
 return {'id':d['id'],'pages':len(pages),'page_edge_violations':outside,'margin_warnings':margins,'missing_glyphs':re.findall(r'Missing character:[^\n]*',log),'overfull_boxes':re.findall(r'Overfull[^\n]*',log),'text_extraction_ok':r.returncode==0}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(check,D))
sols=[d['id'] for d in D if d['kind']=='解析'];refs=[d.get('corresponding_solution') for d in D if d['kind']=='答案速查']
report={'document_count':len(D),'years':sorted(set(d['year'] for d in D)),'all_solutions_have_answers':set(sols)==set(refs),'missing_year_types':[(y,k) for y in range(1987,2027) for k in ['试卷','解析','答案速查'] if not any(d['year']==y and d['kind']==k for d in D)],'checks':results,'visual_review':'Representative rendered pages reviewed separately; no claim of full mathematical proofreading.'}
(OUT/'quality-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
for r in results:
 if r.get('error') or r.get('page_edge_violations') or r.get('margin_warnings') or r.get('missing_glyphs'):print(r['id'],str(r)[:1100])
print('QA',len(results),'PDFs',sum(r.get('pages',0) for r in results),'pages; matched answers:',report['all_solutions_have_answers'])
