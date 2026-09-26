"""Explicit repairs of malformed OCR; raw evidence remains under output/ocr."""
import re

def repair(doc,s):
 if doc=='1997-exam':
  s=s.replace(r'(C）\left(x_{0},f\left(x_{0}\right)\right)',r'(C）$\left(x_{0},f\left(x_{0}\right)\right)$')
 if doc=='2007-solutions':
  s=s.replace('与 BX=b_{2} $','与 $ BX=b_{2} $')
 if doc=='2017-solutions':
  s='\n'.join(r'$$\int_0^1\tan x\,dx=-\ln(\cos1).$$'+'\n\n整理校注：第 13 题 OCR 产生了重复字符循环，此行按前一步积分及来源答案恢复。' if len(line)>4000 and line.count(r'\lim')>15 else line for line in s.splitlines())
 if doc=='2021-exam':
  s=s.replace("y'' - y = 0", "y''' - y = 0")
  s=s.replace(r'17. 求极限  $ \lim_{x \to \infty}',r'17. 求极限  $ \lim_{x \to 0}')
  s+='\n整理校注：第 15 题按原图恢复三阶导数；第 17 题来源把极限点印为无穷，按对应解析及表达式改为 0。\n'
 if doc=='2010-solutions':
  s=re.sub(r'\$\$\s*\\begin\{aligned\}\\lim_\{t\\to1.*?\$\$',lambda m:r'$$\lim_{x\to1^-}\sqrt{1-x}\,\frac{|\ln(1-x)|^{2/m}}{x^{1/n}}=\lim_{t\to0^+}t^{1/2}|\ln t|^{2/m}=0.$$'+'\n\n整理校注：此处 OCR 的分式层级损坏，按原式的等价极限重排。',s,flags=re.S)
 if doc=='2024-solutions-full':
  s=re.sub(r'\$\$\s*k=\\frac\{\\left\|y.*?\$\$',lambda m:r'$$\kappa=2,\quad R=\frac12,\quad (x-\tfrac12)^2+y^2=\frac14.$$'+'\n\n整理校注：利用曲线 $x=y^2$ 在原点的曲率，重排原稿损坏的曲率计算行。',s,flags=re.S)
  s=re.sub(r'11\.【答案】[^\n]*','11.【答案】$(x-1/2)^2+y^2=1/4$。',s)
 if doc=='2025-solutions':
  s=re.sub(r'(?m)^D=([^\n]*?)\\\)[，,]',lambda m:'$D='+m[1]+'$，',s)
  # Correct OCR of the printed options, using the downloaded page images.
  a=s.index('4.设函数');b=s.index('5. 设函数',a)
  s=s[:a]+s[a:b].replace('O(', 'o(')+s[b:]
  a=s.index('5. 设函数');b=s.index('【答案】',a)
  q=s[a:b].replace(r'A.  $ \int_{0}^{4} \left[ \int_{-2}^{\sqrt{4-y}}',r'A.  $ \int_{0}^{4} \left[ \int_{-2}^{-\sqrt{4-y}}').replace(r'C.  $ \int_{0}^{4} \left[ \int_{-2}^{\sqrt{4-y}}',r'C.  $ \int_{0}^{4} \left[ \int_{-2}^{-\sqrt{4-y}}')
  s=s[:a]+q+s[b:]
  a=s.index('7. 设函数');b=s.index('8. 设矩阵',a)
  q=s[a:b].replace('7.【答案】B','7.【答案】D（整理校正，四个条件均充分；原解析 B 有误）')
  s=s[:a]+q+s[b:]
  a=s.index('8. 设矩阵');b=s.index('【答案】',a)
  s=s[:a]+r'''8. 设矩阵 $\begin{pmatrix}1&2&0\\2&a&0\\0&0&b\end{pmatrix}$ 有一个正特征值和两个负特征值，则（ ）。

A. $a>4,b>0$。　B. $a<4,b>0$。

C. $a>4,b<0$。　D. $a<4,b<0$。

'''+s[b:]
  a=s.index('9. 下列矩阵');b=s.index('9.【答案】',a)
  s=s[:a]+r'''9. 下列矩阵中，可以经过若干初等行变换得到矩阵 $\begin{pmatrix}1&1&0&1\\0&0&1&2\\0&0&0&0\end{pmatrix}$ 的是（ ）。

A. $\begin{pmatrix}1&1&0&1\\1&2&1&3\\2&3&1&4\end{pmatrix}$。

B. $\begin{pmatrix}1&1&0&1\\1&1&2&5\\1&1&1&3\end{pmatrix}$。

C. $\begin{pmatrix}1&0&0&1\\0&1&0&3\\0&1&0&0\end{pmatrix}$。

D. $\begin{pmatrix}1&1&2&3\\1&2&2&3\\2&3&4&6\end{pmatrix}$。

'''+s[b:]
  s=re.sub(r'(12\. 曲线[^\n]*渐近线方程为)[^\n]*',r'\1 ___。',s)
  s=s.replace('![原文插图](image-007.jpg)','')
  s=re.sub(r'再单位化得：[^\n]*',lambda m:r'再单位化得：$Q=\begin{pmatrix}1/\sqrt3&-1/\sqrt2&1/\sqrt6\\1/\sqrt3&0&-2/\sqrt6\\1/\sqrt3&1/\sqrt2&1/\sqrt6\end{pmatrix}$。',s)
  a=s.index('6. 设单位质点');b=s.index('7. 设函数',a)
  q=s[a:b].replace('【答案】A','【答案】B（整理校正：按本题选项顺序）')
  s=s[:a]+q+s[b:]

 if doc=='2009-solutions':
  s=re.sub(r'\$\s*\(A \\vdots \\xi_1\).*?\$',lambda m:r'$(A\mid\xi_1)=\left(\begin{array}{ccc|c}1&-1&-1&-1\\-1&1&1&1\\0&-4&-2&-2\end{array}\right)\longrightarrow\left(\begin{array}{ccc|c}1&0&-1/2&-1/2\\0&1&1/2&1/2\\0&0&0&0\end{array}\right)$',s,flags=re.S)
  s=re.sub(r'\$\s*\(\\mathbf\{A\}\^2 \\vdots \\xi_1\).*?\$',lambda m:r'$(A^2\mid\xi_1)=\left(\begin{array}{ccc|c}2&2&0&-1\\-2&-2&0&1\\4&4&0&-2\end{array}\right)\longrightarrow\left(\begin{array}{ccc|c}1&1&0&-1/2\\0&0&0&0\\0&0&0&0\end{array}\right)$',s,flags=re.S)
 return s
