"""Metin katmanından formül LaTeX'i ve LaTeX temizliği (§19.3).

Formül bölgesindeki karakterlerin konum, boyut ve fontlarından LaTeX kurulur: kesir çizgileri (yatay çizimler) pay ve
paydayı, büyük operatörlerin (∑, ∏, ∫) altındaki/üstündeki küçük satırlar sınırları, taban çizgisinden kayan küçük
karakterler üs/alt simgeleri, aksanlar (ˆ, ˜, ¯ ve birleşen biçimleri) `\\hat`/`\\tilde`/`\\bar` komutlarını verir.
Matematik alfasayısal karakterleri (𝐢, 𝑁, ℝ) stillerine (`\\mathbf`, `\\mathbb`, `\\mathcal`) çevrilir; metin fontundaki
sözcükler `\\text{}` ya da operatör adı (`\\log`, `\\max`) olur.

Çıktı tahmin değildir: tanınmayan bir glif (özel kullanım alanı, `�`, büyük parantez parçaları), birden çok satır
(cases, matris, hizalı denklemler), kök işareti ya da sahipsiz kalan bir karakter varsa sonuç `None` olur ve formül
görsel modele bırakılır.
"""
import re
import statistics
import unicodedata
from dataclasses import dataclass, field

import fitz

from .evidence_verifier import validate_latex

TEXT_FLAGS = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP
MATH_FONT_RE = re.compile(r"^(?:CM(?:MI|SY|EX|BSY)|MSBM|MSAM|EUFM|EUSM|RSFS|CambriaMath|Cambria-Math|STIX|MT(?:MI|SY|EX)|"
                          r"Symbol|.*Math)", re.I)
CMEX_FONT_RE = re.compile(r"^(?:CMEX|.*MathExtension|.*Extensions?-)", re.I)
ITALIC_FONT_RE = re.compile(r"italic|oblique|[-,]it\b|^CMMI|^LMMathItalic", re.I)
BOLD_FONT_RE = re.compile(r"bold|black|heavy|^CMBX|^CMBSY", re.I)

# Yükseklik oranları: karakter kutusu fontun ascender/descender değerinden geldiği için dikey kararlarda taban çizgisi
# ve punto kullanılır.
GLYPH_TOP = 0.72
GLYPH_BOTTOM = 0.22
LEVEL_SIZE_RATIO = 0.85     # bu oranın altındaki punto üs/alt simge ya da sınır adayıdır
LEVEL_BASE_TOLERANCE = 0.2  # taban çizgisi sapması (punto oranı)
ROW_BASE_LIMIT = 0.5        # tam puntolu karakter bu kadar kayarsa ikinci satır vardır (cases/matris)
WORD_GAP = 0.6              # metin sözcüklerini birleştiren en büyük boşluk (punto oranı)
SPACE_GAP = 0.12            # sözcük içinde boşluk sayılan aralık

OPERATOR_NAMES = {"log", "ln", "exp", "max", "min", "arg", "sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh",
                  "tanh", "lim", "sup", "inf", "det", "dim", "ker", "deg", "gcd", "Pr", "lg", "argmax", "argmin"}
BIG_OPERATORS = {"∑": r"\sum", "∏": r"\prod", "∐": r"\coprod", "∫": r"\int", "∬": r"\iint", "∭": r"\iiint",
                 "∮": r"\oint", "⋃": r"\bigcup", "⋂": r"\bigcap", "⨁": r"\bigoplus", "⨂": r"\bigotimes",
                 "⋁": r"\bigvee", "⋀": r"\bigwedge"}
# CMEX (TeX büyük semboller fontu): metin katmanında Latin harfi olarak görünen büyük operatörler ve parantezler
CMEX_OPERATORS = {"P": r"\sum", "X": r"\sum", "Q": r"\prod", "Y": r"\prod", "R": r"\int", "Z": r"\int",
                  "S": r"\bigcup", "T": r"\bigcap", "H": r"\oint", "I": r"\oint"}
CMEX_DELIMITERS = {"\x00": "(", "\x10": "(", "\x12": "(", "\x20": "(", "\x01": ")", "\x11": ")", "\x13": ")",
                   "\x21": ")", "\x02": "[", "\x14": "[", "\x22": "[", "\x03": "]", "\x15": "]", "\x23": "]",
                   "(": "(", ")": ")", "[": "[", "]": "]", "|": "|", "/": "/"}
ACCENTS = {"\u0302": "hat", "\u02c6": "hat", "\u0303": "tilde", "\u02dc": "tilde", "\u0304": "bar", "\u0305": "bar",
           "\u00af": "bar", "\u02c9": "bar", "\u0307": "dot", "\u02d9": "dot", "\u0308": "ddot", "\u00a8": "ddot",
           "\u20d7": "vec", "\u030c": "check", "\u02c7": "check", "\u0306": "breve", "\u02d8": "breve"}
WIDE_ACCENTS = {"hat": "widehat", "tilde": "widetilde", "bar": "overline"}
SYMBOLS = {
    "−": "-", "–": "-", "∗": "*", "⋅": r"\cdot", "·": r"\cdot", "×": r"\times", "÷": r"\div", "±": r"\pm",
    "∓": r"\mp", "∘": r"\circ", "•": r"\bullet", "⊙": r"\odot", "⊕": r"\oplus", "⊗": r"\otimes", "∖": r"\setminus",
    "≤": r"\le", "≥": r"\ge", "⩽": r"\le", "⩾": r"\ge", "≪": r"\ll", "≫": r"\gg", "≠": r"\neq", "≈": r"\approx",
    "≃": r"\simeq", "≅": r"\cong", "≡": r"\equiv", "∼": r"\sim", "∝": r"\propto", "∈": r"\in", "∉": r"\notin",
    "∋": r"\ni", "⊂": r"\subset", "⊃": r"\supset", "⊆": r"\subseteq", "⊇": r"\supseteq", "→": r"\to",
    "←": r"\leftarrow", "↔": r"\leftrightarrow", "⇒": r"\Rightarrow", "⇐": r"\Leftarrow", "⇔": r"\Leftrightarrow",
    "↦": r"\mapsto", "⟶": r"\longrightarrow", "∶": ":", "≔": ":=", "≜": r"\triangleq", "⊥": r"\perp",
    "∥": r"\parallel", "∣": "|", "‖": r"\|", "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla", "∆": r"\Delta",
    "∀": r"\forall", "∃": r"\exists", "∅": r"\emptyset", "¬": r"\neg", "∧": r"\wedge", "∨": r"\vee", "∪": r"\cup",
    "∩": r"\cap", "…": r"\ldots", "⋯": r"\cdots", "⋮": r"\vdots", "⋱": r"\ddots", "′": "'", "″": "''",
    "°": r"^{\circ}", "⟨": r"\langle", "⟩": r"\rangle", "⌊": r"\lfloor", "⌋": r"\rfloor", "⌈": r"\lceil",
    "⌉": r"\rceil", "{": r"\{", "}": r"\}", "#": r"\#", "%": r"\%", "&": r"\&", "$": r"\$", "_": r"\_",
    "\\": r"\backslash", "ℓ": r"\ell", "ı": r"\imath", "ȷ": r"\jmath", "ℏ": r"\hbar", "†": r"\dagger",
    "⋆": r"\star", "’": "'", "ϵ": r"\epsilon", "ε": r"\epsilon", "ϕ": r"\phi", "φ": r"\phi", "ϑ": r"\vartheta",
    "ϖ": r"\varpi", "ϱ": r"\varrho", "ς": r"\varsigma", "ℎ": "h",
}
LETTERLIKE = {"ℝ": r"\mathbb{R}", "ℕ": r"\mathbb{N}", "ℤ": r"\mathbb{Z}", "ℚ": r"\mathbb{Q}", "ℂ": r"\mathbb{C}",
              "ℒ": r"\mathcal{L}", "ℋ": r"\mathcal{H}", "ℱ": r"\mathcal{F}", "ℰ": r"\mathcal{E}",
              "ℳ": r"\mathcal{M}", "ℬ": r"\mathcal{B}", "ℐ": r"\mathcal{I}", "ℛ": r"\mathcal{R}"}
GREEK_CAPITALS = {"Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega"}
MATH_STYLES = (("DOUBLE-STRUCK", "mathbb"), ("FRAKTUR", "mathfrak"), ("SCRIPT", "mathcal"), ("MONOSPACE", "mathtt"),
               ("SANS-SERIF", "mathsf"), ("BOLD", "mathbf"))
PLAIN = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+=()[],.;:!?/|<>'*-@")
RELATIONS = {"=", "<", ">", r"\le", r"\ge", r"\ll", r"\gg", r"\neq", r"\approx", r"\simeq", r"\cong", r"\equiv",
             r"\sim", r"\propto", r"\in", r"\notin", r"\ni", r"\subset", r"\supset", r"\subseteq", r"\supseteq",
             r"\to", r"\leftarrow", r"\leftrightarrow", r"\Rightarrow", r"\Leftarrow", r"\Leftrightarrow",
             r"\mapsto", r"\longrightarrow", ":=", r"\triangleq", ":"}
BINARIES = {"+", "-", "*", r"\cdot", r"\times", r"\div", r"\pm", r"\mp", r"\circ", r"\bullet", r"\odot", r"\oplus",
            r"\otimes", r"\setminus", r"\cup", r"\cap", r"\wedge", r"\vee"}


class Unsupported(Exception):
    """Metin katmanından güvenilir biçimde kurulamayan yapı."""


@dataclass
class Atom:
    latex: str
    x0: float
    x1: float
    top: float
    bottom: float
    base: float
    size: float
    kind: str = "ord"          # ord | op | frac | accent | prime
    word: str | None = None    # metin fontundaki harf/rakam (sözcük birleştirme için)
    italic: bool = False
    scripts: list = field(default_factory=list)

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.top + self.bottom) / 2


# --- giriş ----------------------------------------------------------------------------------------

def page_lines(page):
    """Sayfanın `rawdict` satırları (karakter düzeyinde). Formül satırları bunlardan kutu eşleşmesiyle seçilir."""
    data = page.get_text("rawdict", flags=TEXT_FLAGS)
    return [line for block in data.get("blocks", []) for line in block.get("lines", [])]


def equation_glyphs(lines, line_bboxes):
    """Formül satırlarının karakterleri. Satırlar, ayrıştırıcının satır kutularıyla eşleşen `rawdict` satırlarıdır;
    böylece formül kutusuna taşan komşu düzyazının karakterleri (ör. üs simgesi) alınmaz."""
    glyphs = []
    for line in lines:
        if not any(all(abs(a - b) <= 0.6 for a, b in zip(line["bbox"], box)) for box in line_bboxes):
            continue
        for span in line.get("spans", []):
            font = span["font"].split("+", 1)[-1]
            math_font = bool(MATH_FONT_RE.match(font))
            for char in span.get("chars", []):
                c = char["c"]
                # Metin fontlarındaki kontrol karakterleri görünmez kutulardır (ör. "\x08 (1)"); matematik fontlarında
                # ise eşlenmemiş sembollerdir (CMSY'de eksi, CMEX'te büyük parantez) ve atlanmaz.
                if not c.strip() or (unicodedata.category(c) == "Cc" and not math_font):
                    continue
                glyphs.append(_Glyph(c, font, span["size"], span["flags"], tuple(char["bbox"]), char["origin"]))
    return glyphs


@dataclass
class _Glyph:
    char: str
    font: str
    size: float
    flags: int
    bbox: tuple
    origin: tuple


def strip_number(glyphs, number):
    """Sağdaki "(n)" numara karakterlerini atar (yalnızca numara bilinen değerle eşleşir ve gövdeden ayrıksa)."""
    if not number or not glyphs:
        return glyphs
    ordered = sorted(glyphs, key=lambda g: g.bbox[0])
    tail = f"({number})"
    if "".join(g.char for g in ordered[-len(tail):]) != tail:
        return glyphs
    rest = ordered[:-len(tail)]
    if rest and ordered[-len(tail)].bbox[0] - max(g.bbox[2] for g in rest) < 3:
        return glyphs
    return rest


def glyph_region(glyphs):
    """Karakterlerin font kutularının birleşimi (görsel model kırpımı için)."""
    return (min(g.bbox[0] for g in glyphs), min(g.bbox[1] for g in glyphs),
            max(g.bbox[2] for g in glyphs), max(g.bbox[3] for g in glyphs))


def text_layer_latex(glyphs, rules):
    """Karakterlerden ve yatay çizgilerden (x0, y, x1) LaTeX. Kurulamazsa None."""
    if not glyphs:
        return None
    try:
        atoms = _to_atoms(glyphs)
        atoms = _attach_accents(atoms)
        atoms = _collapse_radicals(atoms, rules)
        atoms = _collapse_fractions(atoms, rules)
        latex = _layout(atoms)
    except Unsupported:
        return None
    latex = clean_latex(latex.replace("...", r"\ldots"))
    return latex if latex and validate_latex(latex)[0] else None


def fraction_rules(drawings, region, tolerance=4.0):
    """Bölgedeki ince yatay çizgiler (kesir çizgisi, kök üst çizgisi): (x0, y, x1). Kesir çizgisi içeriğinden bir iki
    punto taşabildiği için yatay pay bırakılır."""
    rules = []
    x0, y0, x1, y1 = region
    for drawing in drawings:
        rect = drawing["rect"]
        if rect.x1 < x0 - tolerance or rect.x0 > x1 + tolerance or rect.y1 < y0 - 2 or rect.y0 > y1 + 2:
            continue
        for item in drawing.get("items", []):
            if item[0] == "l" and abs(item[1].y - item[2].y) < 0.5:
                left, right, y = min(item[1].x, item[2].x), max(item[1].x, item[2].x), item[1].y
            elif item[0] == "re" and item[1].height <= 1.5:
                left, right, y = item[1].x0, item[1].x1, (item[1].y0 + item[1].y1) / 2
            else:
                continue
            if right - left >= 2 and x0 - tolerance <= left and right <= x1 + tolerance and y0 - 2 <= y <= y1 + 2:
                rules.append((left, y, right))
    return rules


# --- karakter → atom ------------------------------------------------------------------------------

def _to_atoms(glyphs):
    atoms = []
    for g in glyphs:
        x0, _, x1, _ = g.bbox
        base = g.origin[1]
        top, bottom = base - GLYPH_TOP * g.size, base + GLYPH_BOTTOM * g.size
        kind, word = "ord", None
        if g.char in ACCENTS:
            latex, kind = ACCENTS[g.char], "accent"
        elif CMEX_FONT_RE.match(g.font) and g.char in CMEX_OPERATORS:
            latex, kind = CMEX_OPERATORS[g.char], "op"
            top, bottom = g.bbox[1], g.bbox[3]
        elif CMEX_FONT_RE.match(g.font) and g.char in CMEX_DELIMITERS:
            # Büyük parantezin taban çizgisi formülünkiyle aynı değildir; satır düzeninde her zaman tabanda sayılır.
            latex, kind = CMEX_DELIMITERS[g.char], "delim"
            top, bottom = g.bbox[1], g.bbox[3]
        elif g.char in BIG_OPERATORS:
            latex, kind = BIG_OPERATORS[g.char], "op"
            top, bottom = g.bbox[1], g.bbox[3]
        elif g.char == "√":
            latex, kind = r"\sqrt", "radical"
            top, bottom = g.bbox[1], g.bbox[3]
        else:
            latex = _char_latex(g)
            if g.char in "′″":
                kind = "prime"
            elif g.char.isalnum() and not MATH_FONT_RE.match(g.font) and latex == g.char:
                word = g.char
        atoms.append(Atom(latex, x0, x1, top, bottom, base, g.size, kind, word, italic=_italic(g)))
    return atoms


def _italic(glyph):
    return bool(glyph.flags & 2) or bool(ITALIC_FONT_RE.search(glyph.font))


def _char_latex(glyph):
    c = glyph.char
    if c in LETTERLIKE:
        return LETTERLIKE[c]
    if c in SYMBOLS:
        return SYMBOLS[c]
    if 0x1D400 <= ord(c) <= 0x1D7FF:
        return _math_alphanumeric(c)
    if "GREEK" in unicodedata.name(c, ""):
        return _greek(c)
    if c in PLAIN:
        if c.isalpha() and BOLD_FONT_RE.search(glyph.font) and not MATH_FONT_RE.match(glyph.font):
            return rf"\mathbf{{{c}}}"
        return c
    raise Unsupported(f"tanınmayan karakter U+{ord(c):04X}")


def _math_alphanumeric(c):
    name = unicodedata.name(c, "")
    base = unicodedata.normalize("NFKC", c)
    if not base or base == c:
        raise Unsupported(f"tanınmayan matematik karakteri U+{ord(c):04X}")
    letter = _greek(base) if "GREEK" in unicodedata.name(base, "") or base in "ϵϕϑϖϱ" else base
    for marker, command in MATH_STYLES:
        if marker in name:
            if command == "mathbf" and letter.startswith("\\"):
                command = "boldsymbol"
            return rf"\{command}{{{letter}}}"
    return letter


def _greek(c):
    if c in SYMBOLS:
        return SYMBOLS[c]
    name = unicodedata.name(c, "")
    match = re.match(r"GREEK (CAPITAL|SMALL) LETTER ([A-Z]+)$", name)
    if not match:
        raise Unsupported(f"tanınmayan Yunan karakteri U+{ord(c):04X}")
    word = match.group(2).capitalize()
    if match.group(1) == "SMALL":
        return "\\" + ("omicron" if word == "Omicron" else word.lower())
    return "\\" + word if word in GREEK_CAPITALS else unicodedata.normalize("NFKD", c).upper().translate(_GREEK_LATIN)


_GREEK_LATIN = str.maketrans("ΑΒΕΖΗΙΚΜΝΟΡΤΧ", "ABEZHIKMNOPTX")


# --- yapılar ---------------------------------------------------------------------------------------

def _attach_accents(atoms):
    """Aksan karakterini altındaki karaktere bağlar; birden çok karakterin üstündeki aksan geniş aksan olur."""
    accents = [a for a in atoms if a.kind == "accent"]
    rest = [a for a in atoms if a.kind != "accent"]
    for accent in accents:
        covered = [a for a in rest if a.base >= accent.base - 1 and a.x0 - 1 <= accent.cx <= a.x1 + 1]
        if not covered:
            raise Unsupported("aksanın altında karakter yok")
        target = max(covered, key=lambda a: min(a.x1, accent.x1) - max(a.x0, accent.x0))
        if target.kind != "ord" or target.scripts:
            raise Unsupported("aksan karmaşık bir yapının üstünde")
        target.latex = rf"\{accent.latex}{{{target.latex}}}"
        target.word = None
    return rest


def _collapse_radicals(atoms, rules):
    """√ karakteri ve hemen sağından başlayan üst çizgi: çizginin altındaki karakterler kökün içidir."""
    radicals = [a for a in atoms if a.kind == "radical"]
    if not radicals:
        return atoms
    for radical in radicals:
        rule = next((r for r in rules if abs(r[0] - radical.x1) <= 3 and radical.top - 2 <= r[1] <= radical.cy), None)
        if rule is None:
            raise Unsupported("kök üst çizgisi bulunamadı")
        inside = [a for a in atoms if a is not radical and a.kind != "radical" and rule[0] - 0.5 <= a.cx <= rule[2] + 0.5
                  and rule[1] < a.cy <= radical.bottom + 1]
        if not inside:
            raise Unsupported("boş kök")
        atoms = [a for a in atoms if a is not radical and all(a is not b for b in inside)]
        size = max(a.size for a in inside)
        base = statistics.median(a.base for a in inside if a.size >= LEVEL_SIZE_RATIO * size)
        atoms.append(Atom(rf"\sqrt{{{_layout(inside)}}}", radical.x0, rule[2], rule[1], max(a.bottom for a in inside),
                          base, size, "frac"))
        rules = [r for r in rules if r is not rule]
    return atoms


def _collapse_fractions(atoms, rules):
    """Kesir çizgileri kısadan uzuna işlenir; iç içe kesirde iç kesir dış kesrin payında/paydasında tek atom olur."""
    for x0, y, x1 in sorted(rules, key=lambda r: r[2] - r[0]):
        within = [a for a in atoms if x0 - 0.5 <= a.cx <= x1 + 0.5]
        numerator = _stack(within, y, above=True)
        denominator = _stack(within, y, above=False)
        if not numerator or not denominator:
            continue
        used = {id(a) for a in numerator + denominator}
        atoms = [a for a in atoms if id(a) not in used]
        size = max(a.size for a in numerator + denominator)
        latex = rf"\frac{{{_layout(numerator)}}}{{{_layout(denominator)}}}"
        # Kesrin matematik ekseni çizgidir; taban çizgisi eksenin yaklaşık 0,25 em altındadır.
        atoms.append(Atom(latex, x0, x1, min(a.top for a in numerator), max(a.bottom for a in denominator),
                          y + 0.25 * size, size, "frac"))
    return atoms


def _stack(atoms, y, above):
    """Çizgiye bitişik karakterlerden başlayıp dikeyde birbirine değen karakterlerle büyüyen pay/payda kümesi."""
    side = [a for a in atoms if (a.cy < y if above else a.cy > y)]
    group = [a for a in side if (y - a.bottom <= 0.9 * a.size if above else a.top - y <= 0.9 * a.size)]
    changed = bool(group)
    while changed:
        changed = False
        top, bottom = min(a.top for a in group), max(a.bottom for a in group)
        for a in side:
            if a not in group and a.bottom >= top - 1 and a.top <= bottom + 1:
                group.append(a)
                changed = True
    return group


# --- satır düzeni ----------------------------------------------------------------------------------

def _layout(atoms):
    """Tek satırlık ifadeyi soldan sağa yazar; küçük ve kaymış karakterler sol komşularının üs/alt simgesi,
    büyük operatörün üstünde/altında duranlar sınırları olur."""
    if not atoms:
        return ""
    sized = [a for a in atoms if a.kind in ("ord", "prime")] or atoms
    main_size = max(a.size for a in sized)
    anchors = [a for a in sized if a.size >= LEVEL_SIZE_RATIO * main_size] or sized
    main_base = statistics.median(a.base for a in anchors)

    level, minor = [], []
    for atom in atoms:
        large = atom.size >= LEVEL_SIZE_RATIO * main_size
        if atom.kind in ("op", "frac", "delim") and large:
            level.append(atom)
        elif large and abs(atom.base - main_base) <= LEVEL_BASE_TOLERANCE * main_size:
            level.append(atom)
        elif large and abs(atom.base - main_base) > ROW_BASE_LIMIT * main_size:
            raise Unsupported("birden çok satır")
        else:
            minor.append(atom)
    if not level:
        raise Unsupported("taban satırı yok")
    level = _merge_words(sorted(level, key=lambda a: a.x0))

    ops = [a for a in level if a.kind == "op"]
    for op in ops:
        others = [o for o in ops if o is not op]
        lower = _limit_row(op, others, minor, lambda a: a.cy > main_base + 0.3 * main_size)
        minor = [a for a in minor if all(a is not b for b in lower)]
        upper = _limit_row(op, others, minor, lambda a: a.cy < main_base - 0.45 * main_size)
        minor = [a for a in minor if all(a is not b for b in upper)]
        if lower:
            op.latex += f"_{{{_layout(lower)}}}"
        if upper:
            op.latex += f"^{{{_layout(upper)}}}"

    for atom in sorted(minor, key=lambda a: a.x0):
        owners = [a for a in level if a.x0 <= atom.x0 + 0.5]
        if not owners:
            raise Unsupported("solunda taban karakteri olmayan üs/alt simge")
        owners[-1].scripts.append(atom)

    tokens = []
    for atom in level:
        latex = atom.latex
        if atom.scripts:
            sub = [s for s in atom.scripts if s.base > main_base]
            sup = [s for s in atom.scripts if s.base <= main_base]
            if sub:
                latex += f"_{{{_layout(sub)}}}"
            if sup:
                latex += f"^{{{_layout(sup)}}}"
        tokens.append(latex)
    return _join(tokens)


def _limit_row(op, others, minor, on_side):
    """Operatörün yatay aralığında başlayan ve aynı bantta yatay olarak bitişik küçük karakterler. Yan yana iki
    operatörün (∑∑) sınırları birbirine karışmasın diye başka bir operatörün aralığındaki karakter alınmaz."""
    side = [a for a in minor if on_side(a) and not any(o.x0 - 1 <= a.cx <= o.x1 + 1 for o in others)]
    row = [a for a in side if op.x0 - 1 <= a.cx <= op.x1 + 1]
    changed = bool(row)
    while changed:
        changed = False
        x0, x1 = min(a.x0 for a in row), max(a.x1 for a in row)
        for a in side:
            if a not in row and a.x0 <= x1 + 0.25 * a.size and a.x1 >= x0 - 0.25 * a.size:
                row.append(a)
                changed = True
    return row


def _merge_words(level):
    """Metin fontundaki bitişik harf/rakamlar sözcük olur: operatör adları `\log`, `\arg\max`; diğer sözcükler
    (komşularıyla birlikte) `\text{}`. Sayılar ve tek harfler olduğu gibi kalır. İtalik metin fontundaki tek sözcük
    değişken gibi bırakılır ("SPL"); boşluk içeren italik ifade `\textit{}` olur."""
    result, run = [], []

    def merged(atoms, latex):
        return Atom(latex, atoms[0].x0, atoms[-1].x1, min(a.top for a in atoms), max(a.bottom for a in atoms),
                    atoms[0].base, atoms[0].size)

    def flush():
        if not run:
            return
        words = [[run[0]]]
        for previous, atom in zip(run, run[1:]):
            if atom.x0 - previous.x1 > SPACE_GAP * atom.size:
                words.append([atom])
            else:
                words[-1].append(atom)
        pending = []

        def emit_text():
            if not pending:
                return
            atoms = [a for word in pending for a in word]
            text = " ".join("".join(a.word for a in word) for word in pending)
            if atoms[0].italic and len(pending) == 1:
                result.extend(atoms)
            else:
                result.append(merged(atoms, rf"\textit{{{text}}}" if atoms[0].italic else rf"\text{{{text}}}"))
            pending.clear()

        for word in words:
            text = "".join(a.word for a in word)
            if text in OPERATOR_NAMES:
                emit_text()
                result.append(merged(word, "\\" + text))
            elif len(text) < 2 or not text[0].isalpha():
                emit_text()
                result.extend(word)
            else:
                pending.append(word)
        emit_text()
        run.clear()

    for atom in level:
        if atom.word and run and (atom.x0 - run[-1].x1 > WORD_GAP * atom.size or run[-1].italic != atom.italic):
            flush()
        if atom.word:
            run.append(atom)
        else:
            flush()
            result.append(atom)
    flush()
    return result


OPENERS = {"(", "[", r"\{", r"\langle", "|", r"\|", r"\lfloor", r"\lceil"}


def _join(tokens):
    """Bağıntı ve ikili işlemlerin çevresine boşluk koyar (tekli eksi hariç); komut ile harf arasına zorunlu boşluk."""
    parts, unary = [], set()
    for index, token in enumerate(tokens):
        previous = tokens[index - 1] if index else None
        if token in BINARIES and (previous is None or previous in RELATIONS | BINARIES | OPENERS or previous == ","):
            unary.add(index)
        if previous is not None:
            spaced = (token in RELATIONS or (token in BINARIES and index not in unary) or previous in RELATIONS
                      or (previous in BINARIES and index - 1 not in unary) or previous == ",")
            if spaced or (re.search(r"\\[A-Za-z]+$", previous) and token[:1].isalpha()):
                parts.append(" ")
        parts.append(token)
    return "".join(parts)


# --- temizlik --------------------------------------------------------------------------------------

WRAPPERS = (r"^\$\$(.*)\$\$$", r"^\$(.*)\$$", r"^\\\[(.*)\\\]$", r"^\\\((.*)\\\)$",
            r"^\\begin\{(?:equation|displaymath|align)\*?\}(.*)\\end\{(?:equation|displaymath|align)\*?\}$")


def clean_latex(latex):
    """Matematik ortamı sarmalayıcılarını, formül numarasını (`\\tag{3}`, `\\qquad (3)`, sondaki `(3)`), `\\label`,
    `\\nonumber` ve sondaki cümle noktalamasını atar."""
    text = (latex or "").strip()
    for pattern in WRAPPERS:
        match = re.match(pattern, text, flags=re.S)
        if match:
            text = match.group(1).strip()
    text = re.sub(r"\\(?:tag\*?|label)\{[^{}]*\}", "", text)
    text = re.sub(r"\\(?:nonumber|notag)\b", "", text)
    text = re.sub(r"(?:\\q?quad|\\,|\\;|~|\s)*\(\d{1,3}(?:\.\d{1,2})?[a-z]?\)\s*$", "", text)
    text = re.sub(r"(?:\s|\\[,;!]|\\q?quad)*[.,;]\s*$", "", text)
    return text.strip()
