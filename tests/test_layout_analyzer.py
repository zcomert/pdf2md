import pytest

from src.document_model import BlockType
from src.layout_analyzer import (CAPTION_RE, LIST_RE, RawBlock, RawLine, classify_blocks, detect_gutter, document_gutter,
                                 heading_score, mark_header_footer, merge_indented_first_lines, order_page, section_name,
                                 split_by_style)

W, H = 595.0, 842.0


def line(text, x0, y0, x1=None, size=9.0, bold=False, italic=False, vertical=False):
    x1 = x1 if x1 is not None else x0 + 6 * len(text)
    chars = len(text.replace(" ", ""))
    return RawLine(text, (x0, y0, x1, y0 + size + 2), "Times", size, bold, italic, chars, chars if bold else 0, vertical)


def block(page, *lines):
    return RawBlock(page, (min(l.bbox[0] for l in lines), min(l.bbox[1] for l in lines),
                           max(l.bbox[2] for l in lines), max(l.bbox[3] for l in lines)), list(lines))


def column_block(page, x0, y0, n_lines, width=240, prefix="text"):
    return block(page, *[line(f"{prefix} line {i} with some words", x0, y0 + i * 12, x0 + width) for i in range(n_lines)])


# --- sütun tespiti ve okuma sırası ---

def test_detects_gutter_between_two_columns():
    blocks = [column_block(1, 50, 100, 10), column_block(1, 310, 100, 10)]
    gutter = detect_gutter(blocks, W)
    assert gutter is not None and 290 <= gutter <= 310


def test_single_column_has_no_gutter():
    blocks = [column_block(1, 50, 100, 20, width=495)]
    assert detect_gutter(blocks, W) is None


def test_ragged_last_lines_and_table_cells_do_not_create_columns():
    # Tek sütun (x 156–556) + paragraf son satırları + kısa tablo hücreleri (Berardi düzeni)
    lines = [line("full width paragraph line " * 3, 156, 100 + i * 12, 556) for i in range(10)]
    lines += [line("short last line of para", 156, 300 + i * 30, 156 + 180 + i * 20) for i in range(5)]
    lines += [line("0.99", 341 + (i % 3) * 60, 500 + i * 10, 370 + (i % 3) * 60) for i in range(12)]
    blocks = [RawBlock(1, l.bbox, [l]) for l in lines]
    assert detect_gutter(blocks, W) is None


def test_two_column_reading_order_with_full_width_separator():
    title = block(1, line("Full width title spanning columns", 60, 40, 540, size=16))
    left_top = column_block(1, 50, 100, 5, prefix="LT")
    right_top = column_block(1, 310, 100, 5, prefix="RT")
    table = block(1, line("Table spanning both columns wide", 50, 200, 545))
    left_bottom = column_block(1, 50, 260, 5, prefix="LB")
    right_bottom = column_block(1, 310, 260, 5, prefix="RB")
    blocks = [right_bottom, table, left_top, title, right_top, left_bottom]
    ordered, columns, gutter, uncertain = order_page(blocks, W, H, detect_gutter(blocks, W))
    assert columns == 2 and not uncertain
    assert [b.lines[0].text[:2] for b in ordered] == ["Fu", "LT", "RT", "Ta", "LB", "RB"]
    assert [b.column for b in ordered] == [None, 0, 1, None, 0, 1]


def test_centered_single_line_caption_is_not_uncertain_but_multiline_narrow_block_is():
    base = [column_block(1, 50, 100, 10), column_block(1, 310, 100, 10)]
    gutter = detect_gutter(base, W)
    caption = block(1, line("Figure 1. Caption", 240, 300, 360))
    assert order_page(base + [caption], W, H, gutter)[3] is False
    narrow = block(1, line("narrow multi", 240, 300, 380), line("line block", 240, 312, 380))
    assert order_page(base + [narrow], W, H, gutter)[3] is True


def test_document_gutter_requires_majority_and_agreement():
    assert document_gutter([300, 301, None, 299], W) == 300
    assert document_gutter([300, None, None, None], W) is None
    assert document_gutter([250, 350, 300], W) is None


def test_merge_indented_first_line():
    first = block(1, line("Indented first line of paragraph", 62, 100, 289))
    rest = block(1, line("rest of the paragraph continues", 50, 111, 289), line("and ends here", 50, 122, 200))
    other = block(1, line("Next paragraph starts", 62, 140, 289))
    for b in (first, rest, other):
        b.column = 0
    merged = merge_indented_first_lines([first, rest, other])
    assert len(merged) == 2 and len(merged[0].lines) == 3


def test_split_by_style_separates_bold_heading_from_paragraph():
    raw = block(1, line("2. Method", 50, 100, bold=True), line("Body text follows", 50, 112), line("more body", 50, 124))
    parts = split_by_style(raw)
    assert [len(p.lines) for p in parts] == [1, 2]


# --- üst/alt bilgi ---

def test_repeated_margin_text_marked_with_page_numbers_normalized():
    pages = []
    for n in range(1, 6):
        header = block(n, line("Journal of Tests", 200, 20, size=7))
        footer = block(n, line(f"Page {n}", 280, 815, size=7))
        body = column_block(n, 50, 300, 3)
        unique_top = block(n, line(f"Unique top {n * 'x'}", 50, 20, size=7))
        pages.append((n, W, H, [header, footer, body, unique_top]))
    mark_header_footer(pages)
    for _, _, _, blocks in pages:
        assert [b.type for b in blocks] == [BlockType.header_footer, BlockType.header_footer,
                                            BlockType.paragraph, BlockType.paragraph]


def test_header_footer_skipped_for_short_documents():
    pages = [(n, W, H, [block(n, line("Journal", 200, 20))]) for n in (1, 2)]
    mark_header_footer(pages)
    assert all(b.type == BlockType.paragraph for _, _, _, blocks in pages for b in blocks)


# --- başlıklar ve blok türleri ---

@pytest.mark.parametrize("text, expected", [
    ("Table 1. Results", True), ("TABLE II: Results", True), ("Table 1 Characteristics of studies", True),
    ("Fig. 3 Pipeline", True), ("Şekil 2. Akış", True), ("Table 1 summarizes the results", False),
    ("Figure 10", True), ("Tables are shown", False),
])
def test_caption_regex(text, expected):
    assert bool(CAPTION_RE.match(text)) is expected


@pytest.mark.parametrize("text, expected", [
    ("- item", True), ("• item", True), ("(a) item", True), ("(ii) item", True), ("1) item", True),
    ("2. Method", True), ("Plain text", False),
])
def test_list_regex(text, expected):
    assert bool(LIST_RE.match(text)) is expected


@pytest.mark.parametrize("text, kwargs, is_heading, number", [
    ("1. Introduction", {"bold": True}, True, "1"),
    ("2.1. Data collection", {"italic": True}, True, "2.1"),
    ("A. Dataset", {"italic": True}, True, "A"),
    ("A. EARLY STUDIES", {}, True, "A"),
    ("B. LEARNING-BASED APPROACHES", {}, True, "B"),
    ("II. BACKGROUND", {"bold": True}, True, "II"),
    ("Abstract", {}, True, None),
    ("A B S T R A C T", {}, True, None),
    ("Results and Discussion", {"size": 12.0}, True, None),
    ("OPEN ACCESS", {"bold": True, "size": 12.0}, False, None),
    ("Research article", {"bold": True, "size": 12.0}, False, None),
    ("This is a normal sentence that ends with a period.", {"bold": True}, False, None),
    ("A. Smith and B. Jones", {}, False, None),
    ("0.99 0.98 0.97", {"bold": True}, False, None),
])
def test_heading_score(text, kwargs, is_heading, number):
    raw = block(1, line(text, 50, 100, **kwargs))
    score, detected = heading_score(raw, 9.0)
    assert (score >= 3) is is_heading
    if is_heading:
        assert detected == number


def test_section_name_normalization():
    assert section_name("2. Materials and Methods:") == "materials and methods"
    assert section_name("A B S T R A C T") == "abstract"


def _classify(page_blocks, metadata=None):
    title = classify_blocks([(1, page_blocks)], H, metadata)
    return title, [(b.type, b.heading_level) for b in page_blocks]


def test_title_levels_and_front_matter():
    blocks = [
        block(1, line("ORIGINAL MANUSCRIPT", 50, 40, size=9.5, bold=True)),
        block(1, line("A Study of Something Important", 50, 80, size=18, bold=True)),
        block(1, line("Author One, Author Two & Author Three", 50, 120, size=10, bold=True)),
        block(1, line("Abstract", 50, 160, size=10, bold=True)),
        column_block(1, 50, 180, 3),
        block(1, line("1. Introduction", 50, 240, bold=True, size=11)),
        column_block(1, 50, 260, 3),
        block(1, line("1.1. Background", 50, 320, italic=True)),
        column_block(1, 50, 340, 3),
        block(1, line("References", 50, 400, bold=True, size=11)),
        block(1, line("[1] A. Author, Title, Journal, 2020.", 50, 420)),
    ]
    title, types = _classify(blocks)
    assert title == "A Study of Something Important"
    assert types[0] == (BlockType.paragraph, None)
    assert types[1] == (BlockType.heading, 1)
    assert types[2] == (BlockType.paragraph, None)
    assert types[3] == (BlockType.heading, 2)
    assert types[5] == (BlockType.heading, 2)
    assert types[7] == (BlockType.heading, 3)
    assert types[9] == (BlockType.heading, 2)
    assert types[10] == (BlockType.reference, None)


def test_title_prefers_metadata_and_skips_journal_name():
    blocks = [
        block(1, line("Journal of Safety Research 90 (2024) 100-114", 50, 30, size=7)),
        block(1, line("Journal of Safety Research", 150, 80, size=13.95)),
        block(1, line("Designing a practical fatigue detection", 50, 160, size=13.45),
              line("system: a review", 50, 176, size=13.45)),
        column_block(1, 50, 300, 10),
    ]
    title, _ = _classify(blocks, {"title": "Designing a practical fatigue detection system: A review"})
    assert title.startswith("Designing")
    for b in blocks:
        b.type = BlockType.paragraph
    title, _ = _classify(blocks, {})
    assert title.startswith("Designing")


def test_unnumbered_levels_follow_font_sizes():
    blocks = [
        block(1, line("Voice fatigue subtyping", 50, 40, size=26, bold=True)),
        block(1, line("Methods", 50, 100, size=11, bold=True)),
        block(1, line("Participants", 50, 140, size=10, bold=True)),
        block(1, line("Data availibility", 50, 180, size=11, bold=True)),
        column_block(1, 50, 200, 5),
    ]
    _, types = _classify(blocks)
    assert [t[1] for t in types[:4]] == [1, 2, 3, 2]


def test_section_heading_is_never_document_title():
    blocks = [
        block(1, line("1. Introduction", 50, 100, size=14, bold=True)),
        column_block(1, 50, 130, 5),
        block(1, line("Background", 50, 250, size=12, bold=True)),
        column_block(1, 50, 280, 5),
    ]
    title, types = _classify(blocks)
    assert title is None
    assert types[0] == (BlockType.heading, 1)
