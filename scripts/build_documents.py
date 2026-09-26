"""Normalize PaddleOCR Markdown and create readable XeLaTeX documents."""
import argparse
import html
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'

def escape(s):
    mapping={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    return ''.join(mapping.get(c,c) for c in s)

def normalize(s):
    s=re.sub(r'^Pages: \d+\s*$', '', s, flags=re.M)
    s=re.sub(r'^.*(?:更多笔记资料公众号|关注淘宝店铺|更多考研精品资料|考研666).*$', '', s, flags=re.M)
    s=s.replace('\u00a0',' ').replace('\u200b','')
    s=re.sub(r'</?div[^>]*>', '', s, flags=re.I)
    # Keep each display environment intact when splitting prose paragraphs.
    s=re.sub(r'\$\$(.*?)\$\$',lambda m:'$$'+re.sub(r'\n\s*\n','\n',m[1])+'$$',s,flags=re.S)
    s=re.sub(r'(\\begin\{(?:cases|aligned|array|pmatrix|bmatrix|matrix|vmatrix)\})(.*?)(\\end\{(?:cases|aligned|array|pmatrix|bmatrix|matrix|vmatrix)\})',lambda m:m[1]+m[2].replace('$','')+m[3],s,flags=re.S)
    s=re.sub(r'\n{3,}','\n\n',s)
    return s.strip()+'\n'

def math(s):
    s=s.strip()
    s=s.rstrip('\\').rstrip()
    s=re.sub(r'[\u4e00-\u9fff\u3001-\u303f\uff01-\uff60]+',lambda m:r'\text{'+m[0]+'}',s)
    s=s.replace(r'\begin{align*}',r'\begin{aligned}').replace(r'\end{align*}',r'\end{aligned}')
    s=s.replace(r'\begin{align}',r'\begin{aligned}').replace(r'\end{align}',r'\end{aligned}')
    s=re.sub(r'(\\begin\{aligned\})\s*&',r'\1{}&',s)
    s=s.replace(r'\tag*',r'\tag')
    s=re.sub(r'\\tag\{[^{}]*\}', '', s)
    s=s.replace(r'\boldsymbol',r'\boldsymbol')
    # Some OCR runs mistakenly emit an extra dollar in the middle of cases.
    s=s.replace('$','')
    balanced=[]; depth=0
    for i,c in enumerate(s):
        escaped=(len(s[:i])-len(s[:i].rstrip('\\'))) % 2 == 1
        if c=='{' and not escaped:depth+=1
        if c=='}' and not escaped:
            if depth==0:continue
            depth-=1
        balanced.append(c)
    s=''.join(balanced)+'}'*depth
    stack=[]
    for match in re.finditer(r'\\(begin|end)\{([^}]+)\}',s):
        if match[1]=='begin':stack.append(match[2])
        elif stack and stack[-1]==match[2]:stack.pop()
    s+=''.join(r'\end{'+env+'}' for env in reversed(stack))
    # Top-level line breaks need an outer gathered even if an inner matrix exists.
    level=0; top_break=False
    for token in re.finditer(r'\\begin\{[^}]+\}|\\end\{[^}]+\}|\\\\',s):
        if token[0].startswith(r'\begin'):level+=1
        elif token[0].startswith(r'\end'):level-=1
        elif level==0:top_break=True
    if top_break:s=r'\begin{gathered}'+s+r'\end{gathered}'
    # Keep document output incapable of interpreting file/system commands.
    s=re.sub(r'\\(?:input|include|write|openout|read|catcode|usepackage|documentclass)\b',r'\\mathrm',s)
    return s

TOKEN=re.compile(r'\$\$(.*?)\$\$|(?<!\\)\$(.*?)(?<!\\)\$|!\[([^\]]*)\]\(([^)]+)\)',re.S)
def inline(s,folder):
    out=[];pos=0
    for m in TOKEN.finditer(s):
        out.append(escape(html.unescape(s[pos:m.start()])))
        if m[1] is not None:
            out.append('\n\\begin{center}\\fitmath{\\displaystyle '+math(m[1])+'}\\end{center}\n')
        elif m[2] is not None:
            formula=math(m[2])
            if len(formula)>100 or r'\begin{' in formula:
                out.append('\n\\begin{center}\\fitmath{\\displaystyle '+formula+'}\\end{center}\n')
            else:
                out.append(' $'+formula+'$ ')
        else:
            p=(folder/m[4]).resolve()
            if p.exists():out.append('\n\\begin{center}\\adjustimage{max width=.78\\linewidth,max height=.42\\textheight}{'+str(p)+'}\\end{center}\n')
            else:out.append(escape('〔原文插图见来源文件〕'))
        pos=m.end()
    out.append(escape(html.unescape(s[pos:])))
    return ''.join(out)

def body(md,folder):
    md=normalize(md)
    # Remove only Markdown heading markers, preserving all heading content.
    md=re.sub(r'^#{1,6}\s*','',md,flags=re.M)
    md=re.sub(r'<br\s*/?>','\n',md,flags=re.I)
    # Convert HTML table rows to readable independent lines; retain cell values.
    md=re.sub(r'<tr[^>]*>', '\n\n',md,flags=re.I)
    md=re.sub(r'</t[dh]>\s*<t[dh][^>]*>', '　|　',md,flags=re.I)
    md=re.sub(r'</?(?:table|thead|tbody|tr|td|th)[^>]*>', '',md,flags=re.I)
    pieces=re.split(r'\n\s*\n',md)
    result=[]
    for p in pieces:
        p=p.strip()
        if not p:continue
        content=inline(p,folder)
        if re.match(r'^[一二三四五六七八九十]+[、．.]\s*(选择|填空|解答|计算|证明)',p):
            result.append(r'\needspace{4\baselineskip}\subsection*{'+content+'}')
        elif re.match(r'^(?:\d{4}\s*年.*(?:试题|真题|答案|解析)|[（(]试卷[ⅠⅡⅢIV一二三]+[)）])$',p):
            result.append(r'{\centering\large\bfseries '+content+r'\par}\medskip')
        elif re.match(r'^(?:[（(]\d{1,2}[)）]|\d{1,2}[.、．])',p):
            result.append(r'\needspace{3\baselineskip}\noindent '+content+r'\par\smallskip')
        else:result.append(r'\noindent '+content+r'\par\smallskip')
    return '\n'.join(result)

PREAMBLE=r'''\documentclass[UTF8,fontset=none,a4paper,11pt]{ctexart}
\usepackage[left=21mm,right=21mm,top=23mm,bottom=23mm]{geometry}
\setCJKmainfont{Noto Serif CJK SC}
\setCJKsansfont{Noto Sans CJK SC}
\setmainfont{Liberation Serif}
\usepackage{amsmath,amssymb,mathtools,bm,extarrows}
\usepackage{graphicx,adjustbox,xcolor,fancyhdr,needspace,hyperref}
\usepackage{newunicodechar}
\newsavebox{\formulabox}
\newcommand{\fitmath}[1]{\sbox{\formulabox}{$#1$}\ifdim\wd\formulabox>.96\linewidth\resizebox{.96\linewidth}{!}{\usebox{\formulabox}}\else\usebox{\formulabox}\fi}
\newunicodechar{①}{\ifmmode\text{1}\else(1)\fi}
\newunicodechar{②}{\ifmmode\text{2}\else(2)\fi}
\newunicodechar{③}{\ifmmode\text{3}\else(3)\fi}
\newunicodechar{④}{\ifmmode\text{4}\else(4)\fi}
\newunicodechar{⑤}{\ifmmode\text{5}\else(5)\fi}
\newunicodechar{⑥}{\ifmmode\text{6}\else(6)\fi}
\newunicodechar{⑦}{\ifmmode\text{7}\else(7)\fi}
\newunicodechar{⑧}{\ifmmode\text{8}\else(8)\fi}
\newunicodechar{⑨}{\ifmmode\text{9}\else(9)\fi}
\newunicodechar{⑩}{\ifmmode\text{10}\else(10)\fi}
\newunicodechar{∪}{\ensuremath{\cup}}
\newunicodechar{⋯}{\ensuremath{\cdots}}
\newunicodechar{❹}{(4)}
\newunicodechar{Ⅰ}{I}\newunicodechar{Ⅱ}{II}\newunicodechar{Ⅲ}{III}
\newunicodechar{Ⅳ}{IV}\newunicodechar{Ⅴ}{V}
\newunicodechar{∞}{\ensuremath{\infty}}\newunicodechar{α}{\ensuremath{\alpha}}
\newunicodechar{β}{\ensuremath{\beta}}\newunicodechar{γ}{\ensuremath{\gamma}}
\newunicodechar{π}{\ensuremath{\pi}}\newunicodechar{θ}{\ensuremath{\theta}}
\newunicodechar{λ}{\ensuremath{\lambda}}\newunicodechar{μ}{\ensuremath{\mu}}
\newunicodechar{ξ}{\ensuremath{\xi}}\newunicodechar{ε}{\ensuremath{\varepsilon}}
\newunicodechar{δ}{\ensuremath{\delta}}\newunicodechar{φ}{\ensuremath{\varphi}}
\newunicodechar{→}{\ensuremath{\to}}\newunicodechar{≤}{\ensuremath{\leq}}
\newunicodechar{≥}{\ensuremath{\geq}}\newunicodechar{≠}{\ensuremath{\ne}}
\newunicodechar{∈}{\ensuremath{\in}}\newunicodechar{∑}{\ensuremath{\sum}}
\newunicodechar{∫}{\ensuremath{\int}}\newunicodechar{√}{\ensuremath{\sqrt{\vphantom{x}}}}
\newunicodechar{−}{\ensuremath{-}}\newunicodechar{′}{\ensuremath{'}}
\newunicodechar{″}{\ensuremath{''}}\newunicodechar{·}{\ensuremath{\cdot}}
\newunicodechar{∠}{\ensuremath{\angle}}\newunicodechar{△}{\ensuremath{\triangle}}
\newunicodechar{∂}{\ensuremath{\partial}}\newunicodechar{∃}{\ensuremath{\exists}}
\newunicodechar{∀}{\ensuremath{\forall}}\newunicodechar{⩾}{\ensuremath{\geqslant}}
\newunicodechar{⩽}{\ensuremath{\leqslant}}\newunicodechar{∘}{\ensuremath{\circ}}
\providecommand{\d}{\mathrm{d}}
\providecommand{\R}{\mathbb{R}}\providecommand{\rank}{\operatorname{rank}}
\providecommand{\arccot}{\operatorname{arccot}}\providecommand{\sgn}{\operatorname{sgn}}
\providecommand{\arsinh}{\operatorname{arsinh}}
\definecolor{ink}{HTML}{17364D}
\hypersetup{unicode=true,colorlinks=true,linkcolor=ink,urlcolor=ink}
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\small\sffamily 考研数学二}\fancyhead[R]{\small\sffamily DOCTITLE}
\fancyfoot[C]{\small\thepage}\setlength{\headheight}{16pt}
\setlength{\parindent}{0pt}\setlength{\parskip}{3pt}
\linespread{1.18}\allowdisplaybreaks\emergencystretch=3em
\setcounter{secnumdepth}{0}
\begin{document}
{\sffamily\color{ink}\LARGE\bfseries DOCTITLE\par}
\vspace{3mm}{\small SUBTITLE\par}\vspace{4mm}\hrule\vspace{5mm}
'''

def build(doc_id,title,subtitle,md,folder,force=False):
    year=doc_id[:4]
    dest=OUT/'pdf'/year;dest.mkdir(parents=True,exist_ok=True)
    texdir=OUT/'tex'/year;texdir.mkdir(parents=True,exist_ok=True)
    mdpath=OUT/'markdown'/year/(doc_id+'.md');mdpath.parent.mkdir(exist_ok=True,parents=True)
    # Image links in delivered Markdown are relative to its own location.
    normalized=normalize(md)
    normalized=re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',lambda m:f'![{m[1]}]({Path(__import__("os").path.relpath(folder/m[2],mdpath.parent))})',normalized)
    mdpath.write_text('# '+title+'\n\n'+subtitle+'\n\n'+normalized)
    tex=texdir/(doc_id+'.tex')
    content=PREAMBLE.replace('DOCTITLE',escape(title)).replace('SUBTITLE',escape(subtitle))+body(md,folder)+'\n\\end{document}\n'
    unchanged=tex.exists() and tex.read_text()==content
    tex.write_text(content)
    logpath=texdir/(doc_id+'.build.log')
    if unchanged and (dest/(doc_id+'.pdf')).exists() and logpath.exists() and 'Output written on' in logpath.read_text() and '!' not in logpath.read_text() and not force:return True
    r=subprocess.run(['xelatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-file-line-error','-output-directory',str(dest),str(tex)],capture_output=True,text=True,timeout=120)
    (texdir/(doc_id+'.build.log')).write_text(r.stdout+r.stderr)
    if r.returncode:
        (dest/(doc_id+'.pdf')).unlink(missing_ok=True)
        errors=[l for l in r.stdout.splitlines() if 'Error' in l or 'Undefined' in l or l.startswith('l.') or '.tex:' in l]
        print('FAIL',doc_id,' | '.join(errors[-5:]),flush=True)
        return False
    print('PDF',doc_id,flush=True)
    return True

def main():
    p=argparse.ArgumentParser();p.add_argument('--ids',nargs='*');p.add_argument('--force',action='store_true');p.add_argument('--curated',action='store_true');args=p.parse_args()
    docs=json.loads((OUT/('documents.json' if args.curated else 'ocr/manifest.json')).read_text())
    results=[]
    for d in docs:
        if args.ids and d['id'] not in args.ids:continue
        folder=ROOT/d.get('image_folder',str(Path('output/ocr')/d['id']));raw=ROOT/d['markdown_source'] if args.curated else folder/'raw.md'
        if not raw.exists():continue
        kind={'试卷':'试卷','解析':'完整解析','答案速查':'仅答案'}[d['kind']]
        extra='（另一版本）' if d['id'].endswith('-2') else ''
        title=d.get('title',f"{d['year']} 年数学二 · {kind}{extra}")
        subtitle=d.get('subtitle','PaddleOCR-VL-1.6 识别整理 | OCR 整理稿，非逐题校订版')
        ok=build(d['id'],title,subtitle,raw.read_text(),folder,args.force)
        results.append({'id':d['id'],'success':ok})
    (OUT/'build-status.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
