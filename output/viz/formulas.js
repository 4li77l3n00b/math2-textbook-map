/* Formula quick reference: a floating panel on every page (top-bar button or Alt+F).
   Draggable by its title bar, resizable from the corner; position, size and options are remembered.
   Content: one entry per line, "# group" starts a group, otherwise "name | TeX | note" (note may hold $…$). */
const FX_SRC = String.raw`
# 极限
重要极限 | \lim_{x\to0}\frac{\sin x}{x}=1
重要极限 | \lim_{x\to0}(1+x)^{\frac1x}=\lim_{x\to\infty}\Big(1+\frac1x\Big)^x=e
1^∞ 型 | \lim u^{v}=e^{\lim v(u-1)} | $u\to1,\ v\to\infty$
等价无穷小 | \sin x\sim\tan x\sim\arcsin x\sim\arctan x\sim x | $x\to0$
等价无穷小 | \ln(1+x)\sim e^x-1\sim x,\quad a^x-1\sim x\ln a | $x\to0$
等价无穷小 | 1-\cos x\sim\frac12x^2,\quad (1+x)^\alpha-1\sim\alpha x | $x\to0$
差的等价 | x-\sin x\sim\frac16x^3,\quad \arcsin x-x\sim\frac16x^3 | $x\to0$
差的等价 | \tan x-x\sim\frac13x^3,\quad x-\arctan x\sim\frac13x^3 | $x\to0$
差的等价 | \tan x-\sin x\sim\frac12x^3 | $x\to0$
差的等价 | x-\ln(1+x)\sim\frac12x^2,\quad e^x-1-x\sim\frac12x^2 | $x\to0$
增长速度 | \ln x\ll x^\alpha\ll a^x\ll x^x | $x\to+\infty$，$\alpha>0,\ a>1$
常用极限 | \lim_{n\to\infty}\sqrt[n]{n}=1,\quad \lim_{n\to\infty}\sqrt[n]{a}=1 | $a>0$
常用极限 | \lim_{x\to0^+}x^\alpha\ln x=0,\quad \lim_{x\to0^+}x^x=1 | $\alpha>0$
定积分定义 | \lim_{n\to\infty}\frac1n\sum_{i=1}^nf\Big(\frac in\Big)=\int_0^1f(x)\,dx

# 导数
幂函数 | (x^\mu)'=\mu x^{\mu-1}
指数函数 | (a^x)'=a^x\ln a,\quad (e^x)'=e^x
对数函数 | (\log_ax)'=\frac1{x\ln a},\quad (\ln|x|)'=\frac1x
三角函数 | (\sin x)'=\cos x,\quad (\cos x)'=-\sin x
三角函数 | (\tan x)'=\sec^2x,\quad (\cot x)'=-\csc^2x
三角函数 | (\sec x)'=\sec x\tan x,\quad (\csc x)'=-\csc x\cot x
反三角函数 | (\arcsin x)'=\frac1{\sqrt{1-x^2}},\quad (\arccos x)'=-\frac1{\sqrt{1-x^2}}
反三角函数 | (\arctan x)'=\frac1{1+x^2},\quad (\operatorname{arccot}x)'=-\frac1{1+x^2}
对数型 | \big[\ln(x+\sqrt{x^2\pm a^2})\big]'=\frac1{\sqrt{x^2\pm a^2}}
幂指函数 | \big(u^v\big)'=u^v\Big(v'\ln u+\frac{vu'}{u}\Big) | 或写成 $e^{v\ln u}$ 再求导
反函数 | \frac{dx}{dy}=\frac1{y'},\quad \frac{d^2x}{dy^2}=-\frac{y''}{(y')^3}
参数方程 | \frac{dy}{dx}=\frac{y'(t)}{x'(t)},\quad \frac{d^2y}{dx^2}=\frac{y''(t)x'(t)-y'(t)x''(t)}{[x'(t)]^3}
变限积分 | \frac{d}{dx}\int_{\psi(x)}^{\varphi(x)}f(t)\,dt=f(\varphi(x))\varphi'(x)-f(\psi(x))\psi'(x)
微分 | dy=f'(x)\,dx

# 高阶导数
指数 | (e^{ax})^{(n)}=a^ne^{ax},\quad (a^x)^{(n)}=a^x(\ln a)^n
正弦余弦 | (\sin kx)^{(n)}=k^n\sin\Big(kx+\frac{n\pi}2\Big),\quad (\cos kx)^{(n)}=k^n\cos\Big(kx+\frac{n\pi}2\Big)
分式 | \Big(\frac1{x+a}\Big)^{(n)}=\frac{(-1)^nn!}{(x+a)^{n+1}}
对数 | [\ln(1+x)]^{(n)}=\frac{(-1)^{n-1}(n-1)!}{(1+x)^n}
幂函数 | (x^\mu)^{(n)}=\mu(\mu-1)\cdots(\mu-n+1)\,x^{\mu-n}
莱布尼茨公式 | (uv)^{(n)}=\sum_{k=0}^n\mathrm C_n^k\,u^{(k)}v^{(n-k)}
由展开式求 | f(x)=\sum a_nx^n\ \Rightarrow\ f^{(n)}(0)=n!\,a_n

# 泰勒展开
泰勒公式 | f(x)=\sum_{k=0}^n\frac{f^{(k)}(x_0)}{k!}(x-x_0)^k+R_n(x)
拉格朗日余项 | R_n(x)=\frac{f^{(n+1)}(\xi)}{(n+1)!}(x-x_0)^{n+1} | $\xi$ 介于 $x_0$ 与 $x$ 之间；皮亚诺余项 $R_n=o((x-x_0)^n)$
e^x | e^x=1+x+\frac{x^2}{2!}+\frac{x^3}{3!}+\cdots+\frac{x^n}{n!}+o(x^n)
sin x | \sin x=x-\frac{x^3}{3!}+\frac{x^5}{5!}-\cdots+\frac{(-1)^nx^{2n+1}}{(2n+1)!}+o(x^{2n+1})
cos x | \cos x=1-\frac{x^2}{2!}+\frac{x^4}{4!}-\cdots+\frac{(-1)^nx^{2n}}{(2n)!}+o(x^{2n})
ln(1+x) | \ln(1+x)=x-\frac{x^2}2+\frac{x^3}3-\cdots+\frac{(-1)^{n-1}x^n}n+o(x^n)
(1+x)^α | (1+x)^\alpha=1+\alpha x+\frac{\alpha(\alpha-1)}{2!}x^2+\cdots+\frac{\alpha(\alpha-1)\cdots(\alpha-n+1)}{n!}x^n+o(x^n)
1/(1−x) | \frac1{1-x}=1+x+x^2+\cdots+x^n+o(x^n)
1/(1+x) | \frac1{1+x}=1-x+x^2-\cdots+(-1)^nx^n+o(x^n)
√(1+x) | \sqrt{1+x}=1+\frac x2-\frac{x^2}8+o(x^2)
tan x | \tan x=x+\frac{x^3}3+\frac{2x^5}{15}+o(x^5)
arcsin x | \arcsin x=x+\frac{x^3}6+\frac{3x^5}{40}+o(x^5)
arctan x | \arctan x=x-\frac{x^3}3+\frac{x^5}5-\cdots+\frac{(-1)^nx^{2n+1}}{2n+1}+o(x^{2n+1})

# 不定积分
幂函数 | \int x^\mu\,dx=\frac{x^{\mu+1}}{\mu+1}+C,\quad \int\frac{dx}x=\ln|x|+C | $\mu\neq-1$
指数函数 | \int a^x\,dx=\frac{a^x}{\ln a}+C,\quad \int e^x\,dx=e^x+C
三角函数 | \int\sin x\,dx=-\cos x+C,\quad \int\cos x\,dx=\sin x+C
三角函数 | \int\tan x\,dx=-\ln|\cos x|+C,\quad \int\cot x\,dx=\ln|\sin x|+C
三角函数 | \int\sec x\,dx=\ln|\sec x+\tan x|+C,\quad \int\csc x\,dx=\ln|\csc x-\cot x|+C
三角函数 | \int\sec^2x\,dx=\tan x+C,\quad \int\csc^2x\,dx=-\cot x+C
三角函数 | \int\sec x\tan x\,dx=\sec x+C,\quad \int\csc x\cot x\,dx=-\csc x+C
平方 | \int\sin^2x\,dx=\frac x2-\frac{\sin2x}4+C,\quad \int\cos^2x\,dx=\frac x2+\frac{\sin2x}4+C
平方 | \int\tan^2x\,dx=\tan x-x+C
有理式 | \int\frac{dx}{a^2+x^2}=\frac1a\arctan\frac xa+C
有理式 | \int\frac{dx}{x^2-a^2}=\frac1{2a}\ln\Big|\frac{x-a}{x+a}\Big|+C,\quad \int\frac{dx}{a^2-x^2}=\frac1{2a}\ln\Big|\frac{a+x}{a-x}\Big|+C
根式 | \int\frac{dx}{\sqrt{a^2-x^2}}=\arcsin\frac xa+C | $a>0$
根式 | \int\frac{dx}{\sqrt{x^2\pm a^2}}=\ln\big|x+\sqrt{x^2\pm a^2}\big|+C
根式 | \int\sqrt{a^2-x^2}\,dx=\frac x2\sqrt{a^2-x^2}+\frac{a^2}2\arcsin\frac xa+C | $a>0$
根式 | \int\sqrt{x^2\pm a^2}\,dx=\frac x2\sqrt{x^2\pm a^2}\pm\frac{a^2}2\ln\big|x+\sqrt{x^2\pm a^2}\big|+C
对数 | \int\ln x\,dx=x\ln x-x+C
指数×三角 | \int e^{ax}\sin bx\,dx=\frac{e^{ax}(a\sin bx-b\cos bx)}{a^2+b^2}+C
指数×三角 | \int e^{ax}\cos bx\,dx=\frac{e^{ax}(a\cos bx+b\sin bx)}{a^2+b^2}+C
分部积分 | \int u\,dv=uv-\int v\,du | 选 $u$ 的顺序：反三角、对数、幂、指数、三角
万能代换 | t=\tan\frac x2:\ \sin x=\frac{2t}{1+t^2},\ \cos x=\frac{1-t^2}{1+t^2},\ dx=\frac{2\,dt}{1+t^2}
三角代换 | \sqrt{a^2-x^2}:\ x=a\sin t;\quad \sqrt{a^2+x^2}:\ x=a\tan t;\quad \sqrt{x^2-a^2}:\ x=a\sec t

# 定积分
牛顿–莱布尼茨 | \int_a^bf(x)\,dx=F(b)-F(a) | $F'=f$
奇偶性 | \int_{-a}^af(x)\,dx=\int_0^a[f(x)+f(-x)]\,dx | 奇函数为 $0$，偶函数为 $2\int_0^af$
周期性 | \int_a^{a+T}f(x)\,dx=\int_0^Tf(x)\,dx | $T$ 为周期
区间再现 | \int_a^bf(x)\,dx=\int_a^bf(a+b-x)\,dx
正余弦互换 | \int_0^{\frac\pi2}f(\sin x)\,dx=\int_0^{\frac\pi2}f(\cos x)\,dx
x f(sin x) | \int_0^\pi xf(\sin x)\,dx=\frac\pi2\int_0^\pi f(\sin x)\,dx
半周期 | \int_0^\pi f(\sin x)\,dx=2\int_0^{\frac\pi2}f(\sin x)\,dx
华里士公式 | \int_0^{\frac\pi2}\sin^nx\,dx=\int_0^{\frac\pi2}\cos^nx\,dx=\begin{cases}\dfrac{(n-1)!!}{n!!}\cdot\dfrac\pi2,&n\text{ 为正偶数}\\[2mm]\dfrac{(n-1)!!}{n!!},&n\text{ 为大于 1 的奇数}\end{cases}
半圆面积 | \int_0^a\sqrt{a^2-x^2}\,dx=\frac{\pi a^2}4,\quad \int_{-a}^a\sqrt{a^2-x^2}\,dx=\frac{\pi a^2}2
泊松积分 | \int_0^{+\infty}e^{-x^2}\,dx=\frac{\sqrt\pi}2
Γ 函数 | \int_0^{+\infty}x^ne^{-x}\,dx=n!
p 积分 | \int_1^{+\infty}\frac{dx}{x^p}\ \text{收敛}\iff p>1;\qquad \int_0^1\frac{dx}{x^p}\ \text{收敛}\iff p<1
积分中值定理 | \int_a^bf(x)\,dx=f(\xi)(b-a) | $f$ 连续，$\xi\in[a,b]$
平均值 | \bar f=\frac1{b-a}\int_a^bf(x)\,dx

# 积分应用
面积（直角） | A=\int_a^b|f(x)-g(x)|\,dx
面积（极坐标） | A=\frac12\int_\alpha^\beta r^2(\theta)\,d\theta
旋转体（绕 x 轴） | V=\pi\int_a^bf^2(x)\,dx
旋转体（绕 y 轴） | V=2\pi\int_a^bx\,|f(x)|\,dx | 柱壳法，$0\le a<b$
弧长（直角） | s=\int_a^b\sqrt{1+y'^2}\,dx
弧长（参数） | s=\int_\alpha^\beta\sqrt{x'^2(t)+y'^2(t)}\,dt
弧长（极坐标） | s=\int_\alpha^\beta\sqrt{r^2(\theta)+r'^2(\theta)}\,d\theta
旋转曲面面积 | S=2\pi\int_a^b|f(x)|\sqrt{1+f'^2(x)}\,dx | 绕 $x$ 轴
曲率 | K=\frac{|y''|}{(1+y'^2)^{3/2}},\quad R=\frac1K
曲率（参数） | K=\frac{|x'y''-x''y'|}{(x'^2+y'^2)^{3/2}}
形心（曲边梯形） | \bar x=\frac{\int_a^bxf(x)\,dx}{\int_a^bf(x)\,dx},\quad \bar y=\frac{\frac12\int_a^bf^2(x)\,dx}{\int_a^bf(x)\,dx} | $f\ge0$
形心（平面区域） | \bar x=\frac{\iint_Dx\,d\sigma}{\iint_Dd\sigma},\quad \bar y=\frac{\iint_Dy\,d\sigma}{\iint_Dd\sigma}

# 多元微积分
全微分 | dz=\frac{\partial z}{\partial x}dx+\frac{\partial z}{\partial y}dy
隐函数（一元） | F(x,y)=0:\ \frac{dy}{dx}=-\frac{F_x}{F_y}
隐函数（二元） | F(x,y,z)=0:\ \frac{\partial z}{\partial x}=-\frac{F_x}{F_z},\quad \frac{\partial z}{\partial y}=-\frac{F_y}{F_z}
链式法则 | z=f(u,v),\ u=u(x,y),\ v=v(x,y):\ \frac{\partial z}{\partial x}=f_u\frac{\partial u}{\partial x}+f_v\frac{\partial v}{\partial x}
极值判别 | A=f_{xx},\ B=f_{xy},\ C=f_{yy}:\ AC-B^2>0\ \text{有极值（}A>0\text{ 极小，}A<0\text{ 极大）} | $AC-B^2<0$ 无极值，$=0$ 需另行判断
条件极值 | L(x,y,\lambda)=f(x,y)+\lambda\varphi(x,y),\quad L_x=L_y=L_\lambda=0
极坐标 | \iint_Df(x,y)\,d\sigma=\iint_Df(r\cos\theta,r\sin\theta)\,r\,dr\,d\theta
对称性 | D\ \text{关于 }y\text{ 轴对称}:\ \iint_Df\,d\sigma=\begin{cases}0,&f\text{ 关于 }x\text{ 为奇}\\2\iint_{D_{x\ge0}}f\,d\sigma,&f\text{ 关于 }x\text{ 为偶}\end{cases}
轮换对称 | D\ \text{关于 }y=x\text{ 对称}:\ \iint_Df(x,y)\,d\sigma=\iint_Df(y,x)\,d\sigma

# 微分方程
一阶线性 | y'+P(x)y=Q(x):\ y=e^{-\int P\,dx}\Big(\int Q\,e^{\int P\,dx}\,dx+C\Big)
齐次方程 | y'=\varphi\Big(\frac yx\Big):\ \text{令 }u=\frac yx,\ y'=u+xu'
伯努利方程 | y'+P(x)y=Q(x)y^n:\ \text{令 }z=y^{1-n} | $n\neq0,1$
可降阶 | y''=f(x,y'):\ \text{令 }p=y';\qquad y''=f(y,y'):\ \text{令 }p=y',\ y''=p\frac{dp}{dy}
二阶常系数齐次 | y''+py'+qy=0,\ \text{特征方程 } r^2+pr+q=0
两相异实根 | y=C_1e^{r_1x}+C_2e^{r_2x}
二重根 | y=(C_1+C_2x)e^{rx}
共轭复根 r=α±βi | y=e^{\alpha x}(C_1\cos\beta x+C_2\sin\beta x)
特解 Pₘ(x)e^{λx} | y^*=x^kQ_m(x)e^{\lambda x} | $k=0,1,2$：$\lambda$ 不是特征根、是单根、是二重根
特解 e^{λx}(cos, sin) | f=e^{\lambda x}[P_l(x)\cos\omega x+P_n(x)\sin\omega x]:\ y^*=x^ke^{\lambda x}[R_m^{(1)}(x)\cos\omega x+R_m^{(2)}(x)\sin\omega x] | $m=\max(l,n)$；$k=0,1$：$\lambda+i\omega$ 不是、是特征根
解的结构 | y=\bar y+y^* | 齐次通解 + 非齐次特解；两特解之差是齐次的解

# 三角与代数
平方关系 | \sin^2x+\cos^2x=1,\quad 1+\tan^2x=\sec^2x,\quad 1+\cot^2x=\csc^2x
二倍角 | \sin2x=2\sin x\cos x,\quad \cos2x=\cos^2x-\sin^2x=2\cos^2x-1=1-2\sin^2x
降幂 | \sin^2x=\frac{1-\cos2x}2,\quad \cos^2x=\frac{1+\cos2x}2
二倍角（正切） | \tan2x=\frac{2\tan x}{1-\tan^2x}
和角 | \sin(\alpha\pm\beta)=\sin\alpha\cos\beta\pm\cos\alpha\sin\beta,\quad \cos(\alpha\pm\beta)=\cos\alpha\cos\beta\mp\sin\alpha\sin\beta
积化和差 | \sin\alpha\cos\beta=\frac12[\sin(\alpha+\beta)+\sin(\alpha-\beta)]
积化和差 | \cos\alpha\cos\beta=\frac12[\cos(\alpha+\beta)+\cos(\alpha-\beta)],\quad \sin\alpha\sin\beta=-\frac12[\cos(\alpha+\beta)-\cos(\alpha-\beta)]
和差化积 | \sin\alpha+\sin\beta=2\sin\frac{\alpha+\beta}2\cos\frac{\alpha-\beta}2,\quad \sin\alpha-\sin\beta=2\cos\frac{\alpha+\beta}2\sin\frac{\alpha-\beta}2
和差化积 | \cos\alpha+\cos\beta=2\cos\frac{\alpha+\beta}2\cos\frac{\alpha-\beta}2,\quad \cos\alpha-\cos\beta=-2\sin\frac{\alpha+\beta}2\sin\frac{\alpha-\beta}2
求和 | \sum_{k=1}^nk=\frac{n(n+1)}2,\quad \sum_{k=1}^nk^2=\frac{n(n+1)(2n+1)}6,\quad \sum_{k=1}^nk^3=\Big[\frac{n(n+1)}2\Big]^2
等比求和 | \sum_{k=0}^{n-1}q^k=\frac{1-q^n}{1-q} | $q\neq1$
立方和差 | a^3\pm b^3=(a\pm b)(a^2\mp ab+b^2)
常用不等式 | \frac x{1+x}<\ln(1+x)<x | $x>0$
常用不等式 | \sin x<x<\tan x | $0<x<\frac\pi2$
常用不等式 | e^x\ge1+x,\quad \ln x\le x-1 | 等号仅在 $x=0$（$x=1$）时成立

# 线性代数
行列式 | |A^{\mathrm T}|=|A|,\quad |kA|=k^n|A|,\quad |AB|=|A||B|,\quad |A^{-1}|=|A|^{-1} | $A$ 为 $n$ 阶
伴随矩阵 | AA^*=A^*A=|A|E,\quad A^{-1}=\frac{A^*}{|A|}
伴随矩阵 | |A^*|=|A|^{n-1},\quad (A^*)^*=|A|^{n-2}A,\quad (kA)^*=k^{n-1}A^* | $n\ge2$
伴随的秩 | r(A^*)=\begin{cases}n,&r(A)=n\\1,&r(A)=n-1\\0,&r(A)<n-1\end{cases}
二阶逆 | \begin{pmatrix}a&b\\c&d\end{pmatrix}^{-1}=\frac1{ad-bc}\begin{pmatrix}d&-b\\-c&a\end{pmatrix}
分块逆 | \begin{pmatrix}A&O\\O&B\end{pmatrix}^{-1}=\begin{pmatrix}A^{-1}&O\\O&B^{-1}\end{pmatrix},\quad \begin{pmatrix}O&A\\B&O\end{pmatrix}^{-1}=\begin{pmatrix}O&B^{-1}\\A^{-1}&O\end{pmatrix}
范德蒙行列式 | \begin{vmatrix}1&1&\cdots&1\\x_1&x_2&\cdots&x_n\\\vdots&\vdots&&\vdots\\x_1^{n-1}&x_2^{n-1}&\cdots&x_n^{n-1}\end{vmatrix}=\prod_{1\le j<i\le n}(x_i-x_j)
秩不等式 | r(A+B)\le r(A)+r(B),\quad r(AB)\le\min\{r(A),r(B)\}
秩不等式 | A_{m\times n}B_{n\times s}=O\ \Rightarrow\ r(A)+r(B)\le n
秩不等式 | r(A)+r(B)-n\le r(AB),\quad r(A^{\mathrm T}A)=r(A)
齐次方程组 | Ax=0\ \text{的基础解系含 }n-r(A)\text{ 个向量}
非齐次有解 | Ax=b\ \text{有解}\iff r(A)=r(A\,|\,b) | 唯一解 $\iff r(A)=r(A|b)=n$
特征值 | \sum\lambda_i=\operatorname{tr}A,\quad \prod\lambda_i=|A|
特征值 | A\ \text{的特征值 }\lambda:\ f(A)\to f(\lambda),\ A^{-1}\to\frac1\lambda,\ A^*\to\frac{|A|}\lambda | 特征向量不变
相似 | P^{-1}AP=B\ \Rightarrow\ |\lambda E-A|=|\lambda E-B|,\ \operatorname{tr}A=\operatorname{tr}B,\ |A|=|B|,\ r(A)=r(B)
施密特正交化 | \beta_2=\alpha_2-\frac{(\alpha_2,\beta_1)}{(\beta_1,\beta_1)}\beta_1,\quad \beta_3=\alpha_3-\frac{(\alpha_3,\beta_1)}{(\beta_1,\beta_1)}\beta_1-\frac{(\alpha_3,\beta_2)}{(\beta_2,\beta_2)}\beta_2
正定 | A\ \text{正定}\iff\text{特征值全正}\iff\text{顺序主子式全正}\iff A=C^{\mathrm T}C\ (C\text{ 可逆})
`;

const FX = (() => {
  const groups = [];
  for (const raw of FX_SRC.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('# ')) { groups.push({ name: line.slice(2), items: [] }); continue; }
    const [name, tex, note = ''] = line.split(' | ');
    groups[groups.length - 1].items.push({ name, tex, note, search: (name + ' ' + tex + ' ' + note).toLowerCase() });
  }
  return groups;
})();

(() => {
  const ST = { x: null, y: null, w: 560, h: 0, open: false, hide: false };
  try { Object.assign(ST, JSON.parse(localStorage.getItem('math2viz.fx') || '{}')); } catch (e) { /* defaults */ }
  const save = () => { try { localStorage.setItem('math2viz.fx', JSON.stringify(ST)); } catch (e) { /* ignore */ } };
  const tex = (s, big = true) => {
    try { return katex.renderToString((big ? '\\displaystyle ' : '') + s, { throwOnError: false, strict: 'ignore' }); } catch (e) { return esc(s); }
  };
  // "a,\quad b" entries wrap between the pieces, never inside one
  const pieces = s => {
    const ps = s.split(/([,;])\\q?quad\s*/);
    const out = [];
    for (let i = 0; i < ps.length; i += 2) out.push(`<span class="fx-p">${tex(ps[i] + (ps[i + 1] || ''))}</span>`);
    return `<div class="fx-ps">${out.join('')}</div>`;
  };
  const note = s => s.split(/\$([^$]+)\$/).map((p, i) => (i % 2 ? tex(p, false) : esc(p))).join('');
  const html = it => it.html || (it.html = `<div class="fx-it"><div class="fx-nm">${esc(it.name)}</div>
    <div class="fx-f">${pieces(it.tex)}${it.note ? `<div class="fx-note">${note(it.note)}</div>` : ''}</div></div>`);

  const box = document.createElement('div');
  box.id = 'fx';
  box.hidden = true;
  box.innerHTML = `<div class="fx-hd" title="拖动移动窗口"><b>公式速查</b>
      <input type="search" id="fxq" placeholder="搜索：泰勒、华里士、arctan、伴随…">
      <label class="small" title="遮住公式，点一下显示，用来背诵"><input type="checkbox" id="fxhide">背诵</label>
      <button class="icon" id="fxclose" title="关闭（Esc / Alt+F）">×</button></div>
    <div class="fx-chips">${FX.map((g, i) => `<button data-fxg="${i}">${esc(g.name)}</button>`).join('')}</div>
    <div class="fx-body"></div>`;
  document.body.appendChild(box);
  const body = $('.fx-body', box), q = $('#fxq', box);

  function render() {
    const words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    let out = '', n = 0;
    FX.forEach((g, i) => {
      const its = words.length ? g.items.filter(it => words.every(w => it.search.includes(w) || g.name.includes(w))) : g.items;
      if (!its.length) return;
      n += its.length;
      out += `<div class="fx-g" data-fxsec="${i}">${esc(g.name)}</div>` + its.map(html).join('');
    });
    body.innerHTML = out || '<p class="muted small" style="padding:10px 14px">没有找到匹配的公式。</p>';
    box.classList.toggle('hide', ST.hide);
    $$('.fx-chips [data-fxg]', box).forEach(b => { b.disabled = !body.querySelector(`[data-fxsec="${b.dataset.fxg}"]`); });
    return n;
  }
  function place() {  // keep the window on screen (after a resize of the app window too)
    const W = innerWidth, H = innerHeight;
    ST.w = Math.min(Math.max(ST.w || 560, 320), W - 16);
    ST.h = Math.min(Math.max(ST.h || Math.round(H * 0.7), 220), H - 16);
    if (ST.x == null) { ST.x = W - ST.w - 24; ST.y = 100; }
    ST.x = Math.min(Math.max(ST.x, 8), W - ST.w - 8);
    ST.y = Math.min(Math.max(ST.y, 8), H - 60);
    Object.assign(box.style, { left: ST.x + 'px', top: ST.y + 'px', width: ST.w + 'px', height: ST.h + 'px' });
  }
  function toggle(open = box.hidden) {
    ST.open = open;
    save();
    $('#fxBtn').classList.toggle('on', open);
    if (!open) { box.hidden = true; return; }
    if (!body.childElementCount) render();
    box.hidden = false;
    place();
    q.focus();
    q.select();
  }

  // drag by the title bar
  $('.fx-hd', box).addEventListener('pointerdown', e => {
    if (e.button !== 0 || e.target.closest('input, button, label')) return;
    const dx = e.clientX - ST.x, dy = e.clientY - ST.y, hd = e.currentTarget;
    hd.setPointerCapture(e.pointerId);
    const move = ev => { ST.x = ev.clientX - dx; ST.y = ev.clientY - dy; place(); };
    const up = () => { hd.removeEventListener('pointermove', move); hd.removeEventListener('pointerup', up); save(); };
    hd.addEventListener('pointermove', move);
    hd.addEventListener('pointerup', up);
    e.preventDefault();
  });
  // resized from the corner (CSS resize): remember the size
  new ResizeObserver(() => {
    if (box.hidden) return;
    ST.w = box.offsetWidth; ST.h = box.offsetHeight;
    clearTimeout(box.saveT); box.saveT = setTimeout(save, 300);
  }).observe(box);
  addEventListener('resize', () => { if (!box.hidden) place(); });

  q.addEventListener('input', render);
  $('#fxhide', box).checked = ST.hide;
  $('#fxhide', box).addEventListener('change', e => { ST.hide = e.target.checked; save(); box.classList.toggle('hide', ST.hide); $$('.fx-it.show', box).forEach(x => x.classList.remove('show')); });
  $('#fxclose', box).addEventListener('click', () => toggle(false));
  box.addEventListener('click', e => {
    const c = e.target.closest('[data-fxg]');
    if (c) { const s = body.querySelector(`[data-fxsec="${c.dataset.fxg}"]`); if (s) body.scrollTop = s.offsetTop - body.offsetTop; return; }
    const it = e.target.closest('.fx-it');
    if (it && ST.hide) it.classList.toggle('show');
  });
  box.addEventListener('keydown', e => {
    e.stopPropagation();  // typing in the search box must not trigger page shortcuts
    if (e.key === 'Escape' || (e.altKey && e.code === 'KeyF')) { e.preventDefault(); toggle(false); }
  });
  $('#fxBtn').addEventListener('click', () => toggle());
  addEventListener('keydown', e => {
    if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === 'KeyF') { e.preventDefault(); toggle(); }
  });
  if (ST.open) toggle(true);
})();
