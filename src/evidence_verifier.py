"""Kanıt ve doğrulama (§19). Faz 07: LaTeX doğrulaması (§19.3). Sayısal değer doğrulaması Faz 09'da eklenir."""
import re

from pylatexenc.latexwalker import LatexWalker, LatexWalkerError

BEGIN_END_RE = re.compile(r"\\(begin|end)\s*\{([^}]*)\}")


def validate_latex(latex):
    """Döner: (geçerli mi, sorunlar). Kontroller: süslü parantez dengesi (kaçışlı `\\{`, `\\}` hariç),
    `\\left`/`\\right` eşleşmesi, `\\begin`/`\\end` yığını ve pylatexenc ile ayrıştırılabilirlik."""
    problems = []
    if not latex or not latex.strip():
        return False, ["boş"]
    depth = 0
    unescaped = re.sub(r"\\[{}]", "", latex)
    for char in unescaped:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                break
    if depth != 0:
        problems.append("süslü parantezler dengesiz")
    lefts = len(re.findall(r"\\left(?![a-zA-Z])", latex))
    rights = len(re.findall(r"\\right(?![a-zA-Z])", latex))
    if lefts != rights:
        problems.append(f"\\left ({lefts}) ve \\right ({rights}) sayısı farklı")
    stack = []
    for kind, name in BEGIN_END_RE.findall(latex):
        if kind == "begin":
            stack.append(name)
        elif not stack or stack.pop() != name:
            problems.append(f"\\end{{{name}}} eşleşmiyor")
            break
    if stack:
        problems.append(f"\\begin{{{stack[-1]}}} kapanmamış")
    try:
        LatexWalker(latex, tolerant_parsing=False).get_latex_nodes()
    except (LatexWalkerError, Exception) as exc:
        problems.append(f"pylatexenc: {type(exc).__name__}")
    return not problems, problems
