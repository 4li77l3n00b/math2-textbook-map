/* Plain-text math (as in the solution steps: "∫₀ˣe^{t²}dt=xe^{ξ²}，ξ在0与x之间") -> text with $…$ LaTeX spans.
   Math spans are the stretches between CJK text / CJK punctuation. Each span is converted (Unicode symbols, scripts,
   function names) and, when KaTeX is available, parsed once: a span KaTeX rejects stays plain text.
   Used by app.js (window.plain2tex) and by the node check in scripts/check_plain2tex.cjs (module.exports). */
(function (root) {
  const TEXT = /[　-〿㐀-鿿豈-﫿！-／：-＠［-｀｛-･‘’“”…—]/;
  const SUP = { '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', '⁺': '+', '⁻': '-',
    '⁼': '=', '⁽': '(', '⁾': ')', 'ⁿ': 'n', 'ⁱ': 'i', 'ˣ': 'x', 'ʸ': 'y', 'ᵀ': 'T', 'ᵏ': 'k', 'ᵐ': 'm', 'ᵗ': 't', 'ᵃ': 'a', 'ᵇ': 'b', 'ᶜ': 'c',
    'ᵈ': 'd', 'ᵉ': 'e', 'ᶠ': 'f', 'ᵍ': 'g', 'ʰ': 'h', 'ʲ': 'j', 'ˡ': 'l', 'ᵒ': 'o', 'ᵖ': 'p', 'ʳ': 'r', 'ˢ': 's', 'ᵘ': 'u', 'ᵛ': 'v', 'ʷ': 'w', 'ᶻ': 'z',
    'ᴬ': 'A', 'ᴮ': 'B', 'ᴰ': 'D', 'ᴱ': 'E', 'ᴳ': 'G', 'ᴴ': 'H', 'ᴵ': 'I', 'ᴶ': 'J', 'ᴷ': 'K', 'ᴸ': 'L', 'ᴹ': 'M', 'ᴺ': 'N', 'ᴼ': 'O', 'ᴾ': 'P', 'ᴿ': 'R', 'ᵁ': 'U', 'ⱽ': 'V', 'ᵂ': 'W' };
  const SUB = { '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4', '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9', '₊': '+', '₋': '-',
    '₌': '=', '₍': '(', '₎': ')', 'ₐ': 'a', 'ₑ': 'e', 'ₒ': 'o', 'ₓ': 'x', 'ₕ': 'h', 'ᵢ': 'i', 'ⱼ': 'j', 'ₖ': 'k', 'ₗ': 'l', 'ₘ': 'm', 'ₙ': 'n',
    'ₚ': 'p', 'ᵣ': 'r', 'ₛ': 's', 'ₜ': 't', 'ᵤ': 'u', 'ᵥ': 'v' };
  const SYM = { '∫': '\\int ', '∬': '\\iint ', '∭': '\\iiint ', '∮': '\\oint ', '∑': '\\sum ', 'Σ': '\\sum ', '∏': '\\prod ', 'Π': '\\prod ',
    '∞': '\\infty ', '→': '\\to ', '⟶': '\\to ', '←': '\\leftarrow ', '⇒': '\\Rightarrow ', '⟹': '\\Rightarrow ', '⇐': '\\Leftarrow ',
    '⇔': '\\iff ', '⟺': '\\iff ', '↔': '\\leftrightarrow ', '↑': '\\uparrow ', '↓': '\\downarrow ', '≤': '\\le ', '⩽': '\\le ',
    '≥': '\\ge ', '⩾': '\\ge ', '≠': '\\ne ', '≈': '\\approx ', '≡': '\\equiv ', '∼': '\\sim ', '~': '\\sim ', '≅': '\\cong ', '±': '\\pm ',
    '∓': '\\mp ', '×': '\\times ', '·': '\\cdot ', '⋅': '\\cdot ', '∙': '\\cdot ', '÷': '\\div ', '∂': '\\partial ', '∇': '\\nabla ',
    '∈': '\\in ', '∉': '\\notin ', '⊂': '\\subset ', '⊆': '\\subseteq ', '⊃': '\\supset ', '∪': '\\cup ', '∩': '\\cap ', '∀': '\\forall ',
    '∃': '\\exists ', '∅': '\\varnothing ', '⊥': '\\perp ', '∥': '\\parallel ', '∠': '\\angle ', '°': '^\\circ ', '′': "'", '″': "''",
    '−': '-', '–': '-', '⁄': '/', '…': '\\cdots ', '⋯': '\\cdots ', '⋮': '\\vdots ', '⋱': '\\ddots ', '∘': '\\circ ', '⊕': '\\oplus ',
    '⌈': '\\lceil ', '⌉': '\\rceil ', '⌊': '\\lfloor ', '⌋': '\\rfloor ', '‖': '\\|', '∣': '|', '√': '\\sqrt ', '∛': '\\sqrt[3] ',
    '∜': '\\sqrt[4] ', '%': '\\%', '#': '\\#', '&': '\\&', '½': '\\tfrac12 ', '⅓': '\\tfrac13 ', '¼': '\\tfrac14 ', '¾': '\\tfrac34 ',
    'Ⅰ': '\\mathrm{I}', 'Ⅱ': '\\mathrm{II}', 'Ⅲ': '\\mathrm{III}', 'Ⅳ': '\\mathrm{IV}', '‴': "'''", 'ᐟ': '/' };
  const FN = 'arcsin|arccos|arctan|sinh|cosh|tanh|sin|cos|tan|cot|sec|csc|ln|lg|log|exp|lim|max|min|sup|inf|det|dim|deg|ker';
  const OPN = 'arccot|diag|rank|tr|sgn|sign|grad|Var|Cov';
  const WORD = new RegExp(`^(?:${FN}|${OPN}|dx|dy|dz|dt|du|dv|ds|d)$`);

  function scripts(s) { // runs of Unicode super/subscript characters -> ^{…} / _{…}
    let out = '';
    for (let i = 0; i < s.length;) {
      const map = SUP[s[i]] != null ? SUP : SUB[s[i]] != null ? SUB : null;
      if (!map) { out += s[i++]; continue; }
      let g = '';
      while (i < s.length && map[s[i]] != null) g += map[s[i++]];
      out += (map === SUP ? '^' : '_') + (g.length > 1 ? `{${g}}` : g);
    }
    return out;
  }
  function braces(s) { // "{" right after ^ _ \cmd{ is grouping; any other { } are set braces -> \{ \}
    let out = '';
    const stack = [];
    for (let i = 0; i < s.length; i++) {
      const c = s[i];
      const escaped = out.endsWith('\\') && !out.endsWith('\\\\');  // already \{ \} in the source
      if (c === '{') {
        if (escaped) { stack.push(false); out += c; continue; }
        const group = /[\^_]$/.test(out) || /\\[a-zA-Z]+(\[\d\])?$/.test(out) || /\}$/.test(out) && stack.includes(true);
        stack.push(group);
        out += group ? '{' : '\\{';
      } else if (c === '}') {
        if (escaped) { stack.pop(); out += c; continue; }
        out += stack.length && stack.pop() ? '}' : '\\}';  // a closer whose opener sits in another span is a set brace
      } else out += c;
    }
    return out;
  }
  function paren(s, i) { // index of the ")" / "]" matching s[i] === "(" / "["
    const [o, c] = s[i] === '[' ? ['[', ']'] : ['(', ')'];
    for (let d = 0; i < s.length; i++) { if (s[i] === o) d++; else if (s[i] === c && --d === 0) return i; }
    return -1;
  }
  function roots(s) { // \sqrt(…) / \sqrt x / sqrt(…) -> \sqrt{…}
    s = s.replace(/(?<![\\A-Za-z])sqrt(?=\()/g, '\\sqrt');
    let out = '';
    for (let i = 0; i < s.length; i++) {
      const head = /^\\sqrt(\[\d\])?( ?)/.exec(s.slice(i));
      if (head && (head[2] || !/^[a-zA-Z{]/.test(s.slice(i + head[0].length)))) {  // "\sqrt " (from √) or \sqrt(
        const root = `\\sqrt${head[1] || ''}`;
        let j = i + head[0].length;
        while (s[j] === ' ') j++;
        if (s[j] === '(' || s[j] === '[') {
          const k = paren(s, j);
          if (k > 0) { out += `${root}{${s.slice(j + 1, k)}}`; i = k; continue; }
        }
        const m = /^(\\[a-zA-Z]+ ?\([^()]*\)|\d+(?:\.\d+)?|[A-Za-zͰ-Ͽ](?:_\{?\w+\}?)?|\\[a-zA-Z]+)/.exec(s.slice(j));
        if (m) { out += `${root}{${m[0]}}`; i = j + m[0].length - 1; continue; }
      }
      out += s[i];
    }
    return out;
  }
  function convert(span) {
    let s = span.replace(/\s+/g, ' ').trim();
    if (!s) return null;
    s = scripts(s);
    s = s.replace(/[\s\S]/g, c => SYM[c] ?? c);
    s = s.replace(/<=/g, '\\le ').replace(/>=/g, '\\ge ').replace(/!=/g, '\\ne ').replace(/(?<![<=])=>/g, '\\Rightarrow ').replace(/->/g, '\\to ');
    s = roots(s);
    s = s.replace(new RegExp(`(?<![A-Za-z\\\\])(${FN})(?![a-z]{2,}\\b)`, 'g'), '\\$1 ');
    s = s.replace(new RegExp(`(?<![A-Za-z\\\\])(${OPN})(?![A-Za-z])`, 'g'), '\\operatorname{$1}');
    s = s.replace(/([\^_])\(([^()]{1,40})\)/g, '$1{$2}');           // e^(x+1) -> e^{x+1}
    s = s.replace(/([\^_])(\\(?:operatorname\{\w+\}|[a-zA-Z]+)) ?/g, '$1{$2}');  // y_\max -> y_{\max}
    s = s.replace(/([\^_])-(\d+(?:\.\d+)?|[A-Za-z])/g, '$1{-$2}');  // e^-x -> e^{-x}
    s = s.replace(/([A-Za-z])\\\{/g, '$1\\setminus\\{');               // R\{0} -> R \setminus \{0\}
    s = braces(s);
    // groups added here, after braces(): they must not be taken for set braces
    s = s.replace(/([A-Za-z)])\*(?![A-Za-z0-9(])|([A-Za-z])\*(?=[A-Za-z(|])/g, (m, a, b) => `{${a || b}^*}`); // A* (adjugate), y*'
    s = s.replace(/([A-Za-zͰ-Ͽ}])('+)(?=[\^_])/g, '{$1$2}');   // y'^2 -> {y'}^2 (no double superscript)
    s = s.replace(/\\ +([_^}),.])/g, '$1').replace(/ {2,}/g, ' ').trim();
    return s;
  }
  function isMath(span) {
    const t = span.trim();
    if (!t) return false;
    if (/^(GS1|GS2|LA|LALU)(\/(GS1|GS2|LA|LALU))*$/.test(t)) return false;  // book ids
    if (/^[A-Za-z][A-Za-z'\- ]*$/.test(t)) { // plain words (Taylor, Cauchy-Schwarz, "RHS") stay text
      const words = t.split(/[\s\-]+/).filter(Boolean);
      return words.every(w => w.length <= 3 || WORD.test(w));
    }
    return /[A-Za-z0-9Ͱ-Ͽ⁰-₟←-⋿ᴀ-ᶿ=<>+*/^_|\\√′]/.test(t);
  }
  function ok(tex) {
    if (!root.katex) return true;
    try { root.katex.renderToString(tex, { throwOnError: true, strict: 'ignore' }); return true; } catch (e) { return false; }
  }
  // text -> [{t: 'text', v}, {t: 'math', v: tex}] (math spans that fail to parse become text)
  function plain2tex(text) {
    const parts = [];
    let buf = '', inText = null;
    const flush = () => {
      if (!buf) return;
      if (inText) parts.push({ t: 'text', v: buf });
      else {
        const lead = buf.match(/^\s*/)[0], trail = buf.match(/\s*$/)[0], core = buf.trim();
        if (lead) parts.push({ t: 'text', v: lead });
        const tex = isMath(core) ? convert(core) : null;
        parts.push(tex && ok(tex) ? { t: 'math', v: tex, src: core } : { t: 'text', v: core, failed: !!tex });
        if (trail) parts.push({ t: 'text', v: trail });
      }
      buf = '';
    };
    for (const c of String(text || '')) {
      const isText = TEXT.test(c) || c === '\n';
      if (inText !== null && isText !== inText) flush();
      inText = isText;
      buf += c;
    }
    flush();
    return parts;
  }
  root.plain2tex = plain2tex;
  if (typeof module !== 'undefined') module.exports = plain2tex;
})(typeof window !== 'undefined' ? window : globalThis);
