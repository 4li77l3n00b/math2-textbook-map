"""Compile independent annual PDFs with bounded local parallelism."""
import concurrent.futures,json
from pathlib import Path
from build_documents import ROOT,OUT,build
D=json.loads((OUT/'documents.json').read_text())
def run(d):
 try:
  ok=build(d['id'],d['title'],d.get('subtitle','PaddleOCR-VL-1.6 识别整理 | OCR 整理稿，非逐题校订版'),(ROOT/d['markdown_source']).read_text(),ROOT/d['image_folder'])
  return {'id':d['id'],'success':ok}
 except Exception as e:return {'id':d['id'],'success':False,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,D))
(OUT/'build-status.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print('BUILD',sum(x['success'] for x in results),'/',len(results),flush=True)
