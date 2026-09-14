"""Kanıt ve doğrulama (§19): sayısal değer doğrulaması (§19.1), kural tabanlı güven (§19.2), LaTeX (§19.3)."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from pylatexenc.latexwalker import LatexWalker, LatexWalkerError

BEGIN_END_RE = re.compile(r"\\(begin|end)\s*\{([^}]*)\}")

# Sayı: isteğe bağlı işaret, rakam grupları (nokta/virgül ayırıcılı) veya ".99", bilimsel gösterim, yüzde işareti
# önde (%99, Türkçe) veya sonda (99%, 99 %).
NUMBER_RE = re.compile(
    r"(?P<pre>%\s?)?(?<![\w.,])(?P<sign>[-−–](?=[.,]?\d))?(?P<num>\d+(?:[.,]\d+)*|[.,]\d+)"
    r"(?P<exp>[eE][-+−]?\d+)?(?P<post>\s?%)?")


def _interpretations(num):
    """Ayırıcı yorumları. Hem nokta hem virgül varsa sondaki ondalıktır. Tek ayırıcı ve ardından tam 3 rakam
    (1,234 / 1.234) belirsizdir: binlik ve ondalık yorumların ikisi de eklenir."""
    if num[0] in ".,":
        return ["0." + num[1:]]
    has_dot, has_comma = "." in num, "," in num
    if has_dot and has_comma:
        decimal_sep = "." if num.rfind(".") > num.rfind(",") else ","
        thousands = "," if decimal_sep == "." else "."
        return [num.replace(thousands, "").replace(decimal_sep, ".")]
    sep = "." if has_dot else "," if has_comma else None
    if sep is None:
        return [num]
    parts = num.split(sep)
    if len(parts) > 2:
        return ["".join(parts)] if all(len(part) == 3 for part in parts[1:]) else [num.replace(sep, ".", 1)]
    if len(parts[1]) == 3 and parts[0] != "0" and len(parts[0]) <= 3:
        return ["".join(parts), f"{parts[0]}.{parts[1]}"]
    return [f"{parts[0]}.{parts[1]}"]


def number_tokens(text):
    """Metindeki sayılar; her biri olası değerlerinin kümesi. `0.99` ↔ `99%` eşdeğerliği için yüzde değerler
    hem kendisi hem /100 olarak eklenir. Yuvarlama yapılmaz (0.987 ≠ 0.99)."""
    tokens = []
    for match in NUMBER_RE.finditer(text or ""):
        values = set()
        for candidate in _interpretations(match.group("num")):
            try:
                value = Decimal(candidate + (match.group("exp") or "").replace("−", "-"))
            except InvalidOperation:
                continue
            if match.group("sign"):
                value = -value
            values.add(value.normalize())
            if match.group("pre") or match.group("post"):
                values.add((value / 100).normalize())
        if values:
            tokens.append(frozenset(values))
    return tokens


def normalize_numbers(text):
    """Metindeki tüm sayıların olası değerleri (kaynak tarafı)."""
    values = set()
    for token in number_tokens(text):
        values |= token
    # İşaretsiz karşılık: "−0.5" kaynağında "0.5" iddiası da aranabilir; işaret uyuşmazlığı ayrıca yakalanmaz.
    values |= {abs(value) for value in values}
    return values


def numbers_in_source(claim_text, source_text):
    """İddia metnindeki her sayı kaynakta var mı. Döner: (sayı içeriyor mu, hepsi bulundu mu)."""
    claim = number_tokens(claim_text)
    if not claim:
        return False, True
    source = normalize_numbers(source_text)
    return True, all(token & source or {abs(v) for v in token} & source for token in claim)


def normalize_text(text):
    """Metin karşılaştırması için: Unicode NFKC, satır sonu tirelemesi, küçük harf, tek boşluk."""
    text = unicodedata.normalize("NFKC", text or "").replace("İ", "i").replace("ı", "i")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).casefold().strip()


WORD_RE = re.compile(r"\w{4,}", re.UNICODE)


def text_supported(value, source_text, min_overlap=0.6):
    """Sayısal olmayan değer kanıtta geçiyor mu: birebir (normalize) veya uzun kelimelerin en az %60'ı."""
    source = normalize_text(source_text)
    items = value if isinstance(value, list) else [value]
    for item in items:
        needle = normalize_text(str(item))
        if not needle or needle in source:
            continue
        words = WORD_RE.findall(needle)
        if not words or sum(1 for word in words if word in source) / len(words) < min_overlap:
            return False
    return True


def confidence_for(verification, methods, conflicted=False, supported=True):
    """§19.2: güven modelin beyanına göre değil kurala göre belirlenir."""
    if conflicted or verification in ("unverified", "source_not_found") or not supported:
        return "low"
    if not methods:
        return "low"
    return "high" if set(methods) <= {"text"} else "medium"


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
