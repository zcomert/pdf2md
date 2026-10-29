import fitz
import pytest

from src.equation_latex import (_Glyph, clean_latex, equation_glyphs, fraction_rules, page_lines, strip_number,
                                text_layer_latex)


def g(char, x, base, size=10.0, font="CMMI10", width=None, flags=0):
    """Karakter: kutu fontun ascender/descender değerlerine benzer biçimde taban çizgisinin üstüne/altına taşar."""
    width = width if width is not None else 0.5 * size
    return _Glyph(char, font, size, flags, (x, base - 0.8 * size, x + width, base + 0.25 * size), (x, base))


def text(string, x, base, size=10.0, font="CMMI10", step=None):
    step = step if step is not None else 0.5 * size
    return [g(char, x + index * step, base, size, font) for index, char in enumerate(string) if char != " "]


# --- metin katmanından LaTeX -------------------------------------------------------------------------------------

def test_fraction_with_numerator_and_denominator():
    glyphs = [g("z", 100, 300), g("=", 108, 300, font="CMR10"), *text("x−u", 122, 293), g("s", 128, 307)]
    rules = [(120, 296.5, 138)]
    assert text_layer_latex(glyphs, rules) == r"z = \frac{x - u}{s}"


def test_sum_limits_scripts_and_nested_subscript():
    glyphs = [g("∑", 100, 300, font="CMEX10", width=10), *text("i=1", 101, 309, size=7, step=3),
              g("N", 103, 290, size=7), g("x", 112, 300), g("i", 117, 302, size=7), g("2", 117, 296, size=7),
              g("=", 124, 300, font="CMR10"), g("y", 134, 300), g("N", 139, 302, size=7), g("F", 143, 303.5, size=5)]
    assert text_layer_latex(glyphs, []) == r"\sum_{i = 1}^{N}x_{i}^{2} = y_{N_{F}}"


def test_cmex_letter_is_big_operator():
    glyphs = [g("P", 100, 300, font="CMEX10", width=10), g("j", 112, 302, size=7), g("x", 118, 300)]
    assert text_layer_latex(glyphs, []) == r"\sum_{j}x"


def test_accent_and_math_alphanumerics():
    glyphs = [g("\u0302", 100, 298, font="STIXMath-Italic"), g("𝐢", 100, 300, font="STIXMath-Bold"),
              g("∈", 108, 300, font="STIXMath-Regular"), g("ℝ", 116, 300, font="STIXMath-Regular"),
              g("𝑁", 122, 296, size=7, font="STIXMath-Italic"), g("𝛼", 130, 300, font="STIXMath-Italic")]
    assert text_layer_latex(glyphs, []) == r"\hat{\mathbf{i}} \in \mathbb{R}^{N}\alpha"


def test_text_words_and_operator_names():
    glyphs = [*text("F1 score", 100, 300, font="CharisSIL"), g("=", 150, 300, font="CMR10"),
              *text("2595", 160, 300, font="CMR10"), *text("log", 184, 300, font="LMRoman10-Regular"),
              g("p", 202, 300)]
    assert text_layer_latex(glyphs, []) == r"\text{F1 score} = 2595\log p"


def test_arg_max_with_limit_below():
    glyphs = [g("y", 100, 300), g("=", 108, 300, font="CMR10"), *text("arg max", 118, 300, font="LMRoman10-Regular"),
              g("c", 140, 306, size=7), g("P", 156, 300)]
    assert text_layer_latex(glyphs, []) == r"y = \arg\max_{c}P"


def test_italic_text_font_words():
    glyphs = [*text("SPL", 100, 300, font="TimesLTStd-Italic"), g("=", 120, 300, font="MTSYN"),
              *text("Window index", 130, 300, font="TimesLTStd-Italic")]
    assert text_layer_latex(glyphs, []) == r"SPL = \textit{Window index}"


@pytest.mark.parametrize("glyphs", [
    [g("x", 100, 300), g("\uf8f1", 108, 300, font="LMMathExtension10")],      # büyük parantez parçası
    [g("x", 100, 300), g("�", 108, 300)],                                  # eşlenmemiş glif
    [g("x", 100, 300), g("=", 108, 300), g("y", 100, 316)],                     # ikinci satır (cases/matris)
    [g("√", 100, 300, font="CMSY10"), g("x", 108, 300)],                        # üst çizgisiz kök
])
def test_unsupported_structures_return_none(glyphs):
    assert text_layer_latex(glyphs, []) is None


def test_radical_with_overline():
    glyphs = [g("√", 100, 300, font="CMSY10", width=8), g("x", 110, 300)]
    assert text_layer_latex(glyphs, [(108, 291, 118)]) == r"\sqrt{x}"


def test_strip_number_only_when_detached():
    glyphs = [g("x", 100, 300), *text("(3)", 200, 300, font="Times")]
    assert [x.char for x in strip_number(glyphs, "3")] == ["x"]
    attached = [g("f", 100, 300), *text("(3)", 105, 300, font="Times")]
    assert len(strip_number(attached, "3")) == 4
    assert len(strip_number(glyphs, "4")) == 4


@pytest.mark.parametrize("raw, cleaned", [
    (r"x = 1 \tag{3}", "x = 1"),
    (r"x = 1 \qquad (3)", "x = 1"),
    (r"\Delta y = f_d(x) \qquad (1) \nonumber", r"\Delta y = f_d(x)"),
    (r"$$a+b$$", "a+b"),
    (r"\begin{equation} a = b, \end{equation}", "a = b"),
    (r"I = \{i_1, \dots, i_N\}.", r"I = \{i_1, \dots, i_N\}"),
    (r"f(x)", "f(x)"),
])
def test_clean_latex(raw, cleaned):
    assert clean_latex(raw) == cleaned


def test_pdf_fraction_from_drawn_rule():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 300), "z =", fontsize=11, fontname="tiit")
    page.insert_text((128, 292), "x", fontsize=11, fontname="tiit")
    page.insert_text((128, 309), "s", fontsize=11, fontname="tiit")
    page.draw_line((127, 296), (134, 296), width=0.5)
    page.insert_text((300, 300), "(1)", fontsize=11, fontname="tiro")
    lines = page_lines(page)
    glyphs = strip_number(equation_glyphs(lines, [tuple(line["bbox"]) for line in lines]), "1")
    region = (min(x.bbox[0] for x in glyphs), min(x.bbox[1] for x in glyphs),
              max(x.bbox[2] for x in glyphs), max(x.bbox[3] for x in glyphs))
    assert text_layer_latex(glyphs, fraction_rules(page.get_drawings(), region)) == r"z = \frac{x}{s}"
