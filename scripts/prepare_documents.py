"""Produce year-specific, traceable editions without changing raw MCP responses."""
import json,re
from pathlib import Path
from build_documents import normalize
from editorial_repairs import repair
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output'
D=json.loads((OUT/'ocr/manifest.json').read_text()); source={d['id']:d for d in D}
corrections=[]; docs=[]
def raw(i):return (OUT/'ocr'/i/'raw.md').read_text()
def clean(s):
 s=s.replace(r'\right]$$，$',r'\right]$，$')
 s=s.replace(r'\left\{\begin{array}{l}|A|=|B| $',r'|A|=|B|,\quad\operatorname{tr}A=\operatorname{tr}B $')
 s=normalize(s)
 s=re.sub(r'^#{0,6}\s*(?:聚创考研网|聚创教育|考研辅导班|启航教育|海文考研)[^\n$]*$', '', s, flags=re.M)
 s=re.sub(r'^2004\s*$','',s,flags=re.M)
 return s

def fix(i,s):
 if i=='2016-solutions':
  s=s.replace(r'\begin{cases}2&-1&-2\\-1&1&\frac{1}{2}\\0&0&\frac{1}{2}\end{cases}',r'\begin{pmatrix}2&-1&-2\\-1&1&\frac{1}{2}\\0&0&\frac{1}{2}\end{pmatrix}')
 if i=='2018-solutions':
  s=re.sub(r'\$\$[^$]*\\left\(\\boldsymbol\{A\}\\mid\\boldsymbol\{B\}[^$]*\$\$',lambda m:r'$$ (A\mid B)=\left(\begin{array}{ccc|ccc}1&2&2&1&2&2\\1&3&0&0&1&1\\2&7&-2&-1&1&1\end{array}\right)\longrightarrow\left(\begin{array}{ccc|ccc}1&0&6&3&4&4\\0&1&-2&-1&-1&-1\\0&0&0&0&0&0\end{array}\right). $$',s)
 if i=='2023-solutions-2':
  s=s.replace(r'\ $ x+1)',r'\\ (x+1)')
  s=s.replace(r'\  x+1)',r'\\ (x+1)')
  # The source contains a duplicate incorrect answer label; its derivation and alternative agree on B.
  s=s.replace('【答案】（D）\n\n【答案】(B)','【答案】(B)',1)
 if i=='2026-solutions':
  s=s.split('## 注：本文档')[0]
 if i=='2025-solutions':
  s=s.replace(r'\begin{pmatrix} 2 & a & 0 \\ 0 & 0 & b \end{pmatrix}',r'\begin{pmatrix}1&2&0\\2&a&0\\0&0&b\end{pmatrix}')
  s=s.replace(r'\frac{3}{0}\ln2',r'\frac{3}{10}\ln2')
  # Retain a visible correction note alongside the source's published solution.
  marker='### 20. （本题满分12分）'
  if marker in s and '整理校注：本题来源' not in s:s=s.replace(marker,marker+'\n\n整理校注：本题来源解析的积分区域与结果有误。按题面两圆盘的交集，正确结果为 $12\\pi-\\frac{112}{3}$。其计算为 $2\\int_0^{\\pi/4}\\int_0^{4\\sin\\theta}r^3(\\cos\\theta-\\sin\\theta)^2\\,dr\\,d\\theta$。以下保留来源解析供对照。')
 return repair(i,s)

def put(i,kind,s,src,relation=None,title=None):
 folder=OUT/'editorial'/i;folder.mkdir(parents=True,exist_ok=True)
 s=clean(s) if kind=='答案速查' or (kind=='试卷' and int(i[:4])>=2024) else fix(src,clean(s));(folder/'content.md').write_text(s)
 d={'id':i,'year':int(i[:4]),'kind':kind,'source_id':src,'source_path':source[src]['path'],'image_folder':f'output/ocr/{src}','markdown_source':str((folder/'content.md').relative_to(ROOT)),'title':title or f'{i[:4]} 年数学二 · '+{'试卷':'试卷','解析':'解析','答案速查':'仅答案'}[kind]+('（另一版本）' if i.endswith('-2') else '')}
 if relation:d['corresponding_solution']=relation
 if kind=='答案速查':d['subtitle']='仅列最终结论；证明题省略证明过程 | 对应 '+i[:4]+' 年解析'+('（另一版本）' if i.endswith('-2') else '')
 docs.append(d)

# Existing standalone editions, with known mislabeled compilations split by their actual headings.
for d in D:
 i=d['id'];p=OUT/'ocr'/i/'raw.md'
 if not p.exists() or d['year']>=2023:continue
 s=raw(i)
 if i=='2003-answers':s=re.search(r'^# 2003 年真题参考答案\n(.*?)(?=^# 2004)',s,re.S|re.M)[0]
 if i=='2005-exam' and len(s)>15000:
  s=re.search(r'^#+ 2005\s*年[^\n]*\n(.*?)(?=^#+ 2006)',s,re.S|re.M)[0]
 if i=='2007-answers':s=s.split('# 2008 年真题参考答案')[0]
 if i=='2020-exam':
  a,b=s.split('# 数学（二）参考答案',1);s=a
  put('2020-solutions-2','解析',b,i)
 if i=='2022-solutions':s=s.split('# 2022年全国硕士研究生招生考试数学（二）答案速查')[0]
 if d['kind']=='答案速查':
  # Remove proof hints, retaining final results and the source's question numbers.
  s=re.sub(r'证明略[.。]?[ \t]*[（(][^\n]*','证明题：结论成立，证明过程见解析。',s)
  if i=='2002-answers':s=s.replace('八、证明题：结论成立，证明过程见解析。','八、极限存在，$\\lim_{n\\to\\infty}x_n=\\frac32$。')
  if i=='1996-answers':s=s.split('（2）简要证明：')[0]+'（2）$|y(x)|\\leq\\frac{k}{a}(1-e^{-ax})$，$x\\geq0$。\n'
 put(i,d['kind'],s,i,i.replace('answers','solutions') if d['kind']=='答案速查' else None)

# 2023: separate front exam and back solutions. Preserve the independent alternative.
s=raw('2023-solutions');a,b=s.split('## 2023 年答案及解析（数学二）',1)
put('2023-exam','试卷',a,'2023-solutions');put('2023-solutions','解析',b,'2023-solutions')
put('2023-solutions-2','解析',raw('2023-solutions-2'),'2023-solutions-2')

# Interleaved recent sources: sequential major question starts, followed by explicit answer/solution boundary.
def split_questions(s):
 s=re.sub(r'^#{1,6}\s*','',s,flags=re.M)
 s=s.replace(r'\.', '.')
 starts=[];offset=0
 for n in range(1,23):
  pat=rf'^\s*{n}\s*[.、．]\s*(?!【答案】|【解】|解[：:]|证明[：:])'
  m=re.search(pat,s[offset:],re.M)
  if not m:raise ValueError(f'Missing question {n}')
  start=offset+m.start();starts.append(start);offset=offset+m.end()
 out=[]
 for idx,start in enumerate(starts):
  q=s[start:starts[idx+1] if idx<21 else len(s)]
  n=idx+1
  boundary=re.search(rf'(?:^\s*(?:{n}\s*[.、．]?\s*)?(?:【答案】|【解析】|【解】|解[：:]|证明[：:]))',q,re.M)
  if n==17 and not boundary:boundary=re.search(r'\$\$\s*\\begin\{aligned\}17',q)
  # Q22 in 2025 has no solution label.
  if n==22 and not boundary:boundary=re.search(r'^\(1\) A 与 B 合同',q,re.M)
  if not boundary:raise ValueError(f'Missing solution boundary {n}')
  if n in (1,11,17):out.append({1:'## 一、选择题',11:'## 二、填空题',17:'## 三、解答题'}[n])
  out.append(q[:boundary.start()].strip())
 return '\n\n'.join(out)
for y,src in [(2024,'2024-solutions-full'),(2025,'2025-solutions-full'),(2026,'2026-solutions')]:
 s=clean(raw(src))
 put(f'{y}-solutions','解析',s,src)
 exam=split_questions(fix(src,s))
 exam=exam.replace('试卷及解析','试卷')
 exam=re.sub(r'整理校注：[^\n]*\n', '', exam)
 put(f'{y}-exam','试卷',exam,src)
put('2025-solutions-2','解析',raw('2025-solutions'),'2025-solutions',title='2025 年数学二 · 解析（另一版本，含校注）')

# Explicitly reviewed final-result transcriptions and existing answer appendix.
for y in range(2020,2027):
 p=OUT/'editorial/answers'/f'{y}.md'
 if p.exists():s=p.read_text()
 elif y==2022:s=raw('2022-solutions').split('# 2022年全国硕士研究生招生考试数学（二）答案速查')[1]
 else:continue
 put(f'{y}-answers','答案速查',s,(f'{y}-solutions-full' if y in (2024,2025) else f'{y}-solutions'),f'{y}-solutions')
 if y==2025:put('2025-answers-2','答案速查',s,'2025-solutions','2025-solutions-2')
 if y in (2020,2023):put(f'{y}-answers-2','答案速查',s,('2020-exam' if y==2020 else '2023-solutions-2'),f'{y}-solutions-2')
(OUT/'documents.json').write_text(json.dumps(sorted(docs,key=lambda d:d['id']),ensure_ascii=False,indent=2))
print('Prepared',len(docs),'documents')
