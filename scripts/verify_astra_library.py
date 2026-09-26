"""Check coverage, immutable drafts, export consistency and local image links."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/astra'

def main():
    errors=[]; coverage=[]; lockmap={}; lock_checks=[]; inputs_checked=0
    manifest=json.loads((OUT/'input_manifest.json').read_text())
    for exam in manifest['exams']:
        for key in ['exam','source']:
            p=ROOT/exam[key]
            if hashlib.sha256(p.read_bytes()).hexdigest()!=exam['sha256']:
                errors.append(f'{exam["year"]}: original/input exam changed ({key})')
        inputs_checked+=1
    for p in (OUT/'audit').glob('*-blind-lock.json'):
        d=json.loads(p.read_text())
        records=d.get('drafts',[])
        if isinstance(records,dict):
            records=[dict(v,year=int(k)) if isinstance(v,dict) else {'year':int(k),'sha256':v} for k,v in records.items()]
        for r in records:
            year=int(r['year']); path=ROOT/r.get('path',f'output/astra/drafts/{year}.json')
            actual=hashlib.sha256(path.read_bytes()).hexdigest()
            expected=r.get('sha256') or r.get('draft_sha256')
            ok=actual==expected
            lock_checks.append({'year':year,'lock':str(p.relative_to(ROOT)),'sha256_unchanged':ok})
            if not ok: errors.append(f'{year}: draft SHA-256 changed')
            lockmap[year]=r
    index=json.loads((OUT/'question_index.json').read_text())
    for row in index['years']:
        year=row['year'];doc=json.loads((OUT/'final'/f'{year}.json').read_text())
        src=(OUT/'input'/f'{year}-exam.md').read_text()
        labels=[q['label'] for q in doc['questions']]
        if len(labels)!=len(set(labels)):errors.append(f'{year}: duplicate display labels')
        if year not in lockmap:errors.append(f'{year}: no independent draft lock')
        if year>=2004:
            nums=[int(m[1] or m[2]) for m in re.finditer(r'^(?:#{1,6}\s*)?(?:[（(](\d{1,2})[）)]|(\d{1,2})\s*[.、．])',src,re.M)]
            # A section's declared range also covers a question whose OCR heading is lost.
            nums += [int(m[2]) for m in re.finditer(r'(\d{1,2})\s*[～~—至-]\s*(\d{1,2})\s*小题',src)]
            expected=set(range(1,max(nums)+1)) if nums else set()
            actual={int(re.search(r'\d+',s)[0]) for s in labels if re.search(r'\d+',s)}
            missing=sorted(expected-actual);extra=sorted(actual-expected)
            if missing or extra:errors.append(f'{year}: coverage missing={missing}, extra={extra}')
            coverage.append({'year':year,'source_question_numbers':sorted(expected),'indexed_question_numbers':sorted(actual),'missing':missing,'extra':extra})
        else:
            heads=re.findall(r'^#{1,6}\s*([一二三四五六七八九十]+)[、．.]',src,re.M)
            missing=[h for h in heads if not any(l==h or l.startswith(h+'（') or l.startswith(h+'(') for l in labels)]
            if missing:errors.append(f'{year}: missing original sections {missing}')
            coverage.append({'year':year,'source_sections':heads,'indexed_labels':labels,'missing_sections':missing})
        for q in doc['questions']:
            qp=OUT/'questions'/f'{q["question_id"]}.md'
            if not qp.is_file():errors.append(f'{q["question_id"]}: individual export missing')
    images=0
    for p in (OUT/'markdown').glob('*.md'):
        for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',p.read_text()):
            if target.startswith(('http://','https://','data:')):continue
            images+=1
            if not (p.parent/target).is_file():errors.append(f'{p.name}: missing image {target}')
    with sqlite3.connect(OUT/'question_index.sqlite') as db:
        count=db.execute('SELECT count(*) FROM questions').fetchone()[0]
        if count!=len(index['questions']):errors.append('SQLite/JSON question count mismatch')
        integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity!='ok':errors.append('SQLite integrity: '+integrity)
    report={'verified_at':datetime.now(timezone.utc).isoformat(),'completed_years':len(index['years']),
            'questions':len(index['questions']),'missing_years':index['missing_years'],'draft_locks':lock_checks,
            'coverage':coverage,'input_exams_checked':inputs_checked,'local_images_checked':images,'errors':errors}
    (OUT/'integrity-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'completed_years':report['completed_years'],'questions':report['questions'],'lock_checks':len(lock_checks),'images_checked':images,'errors':errors},ensure_ascii=False))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
