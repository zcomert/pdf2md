import fitz
import pytest

from src.document_model import BlockType
from src.layout_analyzer import RawBlock, RawLine
from src.pdf_parser import _expand_numbers, figure_references
from src.visual_detector import (PageVisuals, _detect_equations, _detect_figures, _merge_collinear, is_prose,
                                 merge_caption_labels, ruled_table_clip)

W, H = 595.0, 842.0


def line(text, x0, y0, x1=None, size=9.0, math_chars=0, bold=False):
    x1 = x1 if x1 is not None else x0 + 5 * len(text)
    chars = len(text.replace(" ", ""))
    return RawLine(text, (x0, y0, x1, y0 + size + 2), "Times", size, bold, False, chars, chars if bold else 0,
                   math_chars=math_chars)


def block(*lines):
    return RawBlock(1, (min(l.bbox[0] for l in lines), min(l.bbox[1] for l in lines),
                        max(l.bbox[2] for l in lines), max(l.bbox[3] for l in lines)), list(lines))


# --- başlık ve düzyazı ---

def test_caption_label_merges_with_following_text():
    label = block(line("Table 1", 307, 52, bold=True))
    text = block(line("Dataset overview in terms of gender", 307, 61))
    other = block(line("Body paragraph far below", 307, 200))
    merged = merge_caption_labels([label, text, other])
    assert len(merged) == 2 and merged[0].text == "Table 1\nDataset overview in terms of gender"


def test_long_caption_is_not_merged():
    caption = block(line("Table 1. A long caption that already has its text", 50, 50))
    following = block(line("Model Acc F1", 50, 63))
    assert len(merge_caption_labels([caption, following])) == 2


def test_is_prose():
    prose = block(*[line("This sentence describes the experimental protocol used in the study " * 1, 50, 100 + i * 11, 290)
                    for i in range(3)])
    table_rows = block(line("Bi-LSTM 0.99 0.98", 50, 100, 290), line("Bi-GRU 0.96 0.95", 50, 111, 290))
    assert is_prose(prose, 240)
    assert not is_prose(table_rows, 240)


# --- çizgili tablo ön kontrolü ---

def drawing_lines(segments):
    return [{"rect": fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
             "items": [("l", fitz.Point(x0, y0), fitz.Point(x1, y1))]} for x0, y0, x1, y1 in segments]


def test_ruled_table_clip_requires_grid():
    grid = drawing_lines([(50, 100, 300, 100), (50, 120, 300, 120)] + [(x, 100, x, 120) for x in (50, 150, 300)])
    clip = ruled_table_clip(grid)
    assert clip == pytest.approx((50, 100, 300, 120))
    frame = drawing_lines([(50, 100, 300, 100), (50, 200, 300, 200), (50, 100, 50, 200), (300, 100, 300, 200)])
    assert ruled_table_clip(frame) is None
    booktabs = drawing_lines([(50, y, 300, y) for y in (100, 115, 200)])
    assert ruled_table_clip(booktabs) is None


def test_row_rules_drawn_per_cell_are_merged():
    assert _merge_collinear([(49.5, 375.7, 134.4), (134.4, 375.7, 554.3), (49.5, 390, 100)]) == [
        (49.5, 375.7, 554.3), (49.5, 390, 100)]
    per_cell = drawing_lines([(50, 100, 150, 100), (150, 100, 300, 100)] + [(x, 95, x, 110) for x in (50, 150, 300)])
    assert ruled_table_clip(per_cell) is not None


# --- formüller ---

def test_standalone_equation_number_with_math_body():
    equation = block(line("z = (x − μ) / s", 120, 300, 220, math_chars=4))
    number = block(line("(1)", 270, 300, 282))
    prose = block(line("where μ is the mean of the population and s the standard deviation", 50, 330, 290))
    visuals = PageVisuals()
    result = _detect_equations(1, [equation, number, prose], 298.0, W, visuals)
    assert len(visuals.equations) == 1
    assert visuals.equations[0].number == "1" and visuals.equations[0].raw_text == "z = (x − μ) / s  (1)"
    types = sorted(b.type.value for b in result)
    assert types == ["equation", "paragraph"]


def test_reference_numbers_without_math_are_not_equations():
    reference = block(line("[15] D. Chaffin,", 50, 500, 120), line("Localized", 50, 511, 100))
    number = block(line("(4)", 130, 500, 142))
    visuals = PageVisuals()
    _detect_equations(1, [reference, number], None, W, visuals)
    assert visuals.equations == []


def test_equation_body_stays_in_number_column():
    left_number = block(line("(1)", 278, 637, 289))
    left_body = block(line("F1 = 2 · p · r", 150, 637, 250, math_chars=3))
    right_body = block(line("I(M) = {i ∈ I}", 400, 637, 500, math_chars=4))
    right_number = block(line("(5)", 547, 637, 558))
    visuals = PageVisuals()
    _detect_equations(1, [left_body, left_number, right_body, right_number], 298.0, W, visuals)
    raw = {e.number: e.raw_text for e in visuals.equations}
    assert raw == {"1": "F1 = 2 · p · r  (1)", "5": "I(M) = {i ∈ I}  (5)"}


def test_inline_numbered_equation():
    visuals = PageVisuals()
    _detect_equations(1, [block(line("SPL = 20 log(p / p_ref)   (2)", 150, 400, 540))], None, W, visuals)
    assert [(e.number, e.raw_text) for e in visuals.equations] == [("2", "SPL = 20 log(p / p_ref)  (2)")]


# --- şekiller ---

def test_figure_panels_grouped_under_caption_and_labels_absorbed():
    images = [{"bbox": (36, 66, 287, 187), "xref": 10, "transform": (1, 0, 0, 1, 0, 0)},
              {"bbox": (287, 70, 538, 187), "xref": 11, "transform": (1, 0, 0, 1, 0, 0)},
              {"bbox": (162, 210, 413, 328), "xref": 12, "transform": (1, 0, 0, 1, 0, 0)}]
    caption = block(line("FIGURE 7. Model validation performance", 60, 340, 500))
    label = block(line("(a) Using GRU model", 100, 190, 180))
    other_caption = block(line("FIGURE 8. Another figure far below", 60, 700, 500))
    visuals = PageVisuals()
    result = _detect_figures(1, [caption, label, other_caption], None, W, H, images, [], visuals)
    assert len(visuals.figures) == 1
    figure = visuals.figures[0]
    assert figure.number == "7" and figure.bbox == (36, 66, 538, 328) and figure.xref is None
    assert label not in result and caption in result


def test_single_embedded_image_keeps_xref_and_small_images_ignored():
    images = [{"bbox": (100, 100, 400, 300), "xref": 5, "transform": (300, 0, 0, 200, 100, 100)},
              {"bbox": (500, 800, 520, 820), "xref": 6, "transform": (1, 0, 0, 1, 0, 0)}]
    caption = block(line("Fig. 2. Pipeline overview", 100, 310, 300))
    visuals = PageVisuals()
    _detect_figures(1, [caption], None, W, H, images, [], visuals)
    assert [(f.number, f.xref) for f in visuals.figures] == [("2", 5)]


def test_figure_caption_between_blocks_grouping():
    images = [{"bbox": (50, 50, 300, 200), "xref": 1, "transform": (1, 0, 0, 1, 0, 0)},
              {"bbox": (50, 240, 300, 400), "xref": 2, "transform": (1, 0, 0, 1, 0, 0)}]
    first = block(line("Fig. 1. First", 50, 205, 200))
    second = block(line("Fig. 2. Second", 50, 405, 200))
    visuals = PageVisuals()
    _detect_figures(1, [first, second], None, W, H, images, [], visuals)
    assert sorted((f.number, f.xref) for f in visuals.figures) == [("1", 1), ("2", 2)]


# --- şekil atıfları ---

@pytest.mark.parametrize("text, numbers", [("3", {3}), ("2 and 3", {2, 3}), ("2–4", {2, 3, 4}), ("1, 5", {1, 5})])
def test_expand_numbers(text, numbers):
    assert _expand_numbers(text) == numbers


def test_figure_references():
    from src.document_model import Block

    def paragraph(i, text):
        return Block(id=f"p1-b{i}", type=BlockType.paragraph, page=1, bbox=(0, 0, 1, 1), text=text, order=i)
    blocks = [paragraph(0, "As shown in Fig. 3, the model"), paragraph(1, "see Figs. 2–4 for details"),
              paragraph(2, "Figure 30 is unrelated"), paragraph(3, "Şekil 3'te görüldüğü gibi")]
    assert figure_references(blocks, "3") == ["p1-b0", "p1-b1", "p1-b3"]
    assert figure_references(blocks, None) == []
