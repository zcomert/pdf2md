import os
from pathlib import Path

import pytest
import yaml

from src.config import PdfConfig
from src.document_model import (Block, BlockType, DocumentModel, DocumentSource, Equation, Figure, Page, PageClass,
                                 Table, TableCellSpan)
from src.markdown_builder import RenderContext, build_full_conversion, reflow, render_full_conversion, unreadable_pages
from src.pdf_parser import parse_pdf
from tests.helpers import sha256_file

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
SHA = "a" * 64


def context(**overrides):
    values = dict(source_path="papers/a.pdf", sha256=SHA, generated="2026-09-13T12:00:00", mode="balanced",
                  status="completed", prompt_sha256="b" * 64)
    values.update(overrides)
    return RenderContext(**values)


def make_block(index, block_type, text, page=1, level=None):
    return Block(id=f"p{page}-b{index}", type=block_type, page=page, bbox=(0, index * 10, 100, index * 10 + 9),
                 text=text, heading_level=level, order=index)


def make_document(blocks, pages=None):
    pages = pages or [Page(number=1, width=595, height=842)]
    return DocumentModel(parser_version="t", parse_config_hash="t",
                         source=DocumentSource(relative_path="a.pdf", sha256=SHA, page_count=len(pages)),
                         pages=pages, blocks=blocks)


def test_golden_single_column(synthetic_pdf):
    """Beklenen çıktı `tests/golden/` altındadır. Bilinçli bir değişiklikten sonra güncellemek için:
    UPDATE_GOLDEN=1 pytest tests/test_markdown_builder.py"""
    path = synthetic_pdf("synthetic_single_column.pdf")
    document = parse_pdf(path, path.name, sha256_file(path), PdfConfig())
    markdown = build_full_conversion(document, context(source_path=path.name, sha256=document.source.sha256))
    golden = GOLDEN_DIR / "synthetic_single_column.md"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(exist_ok=True)
        golden.write_text(markdown, encoding="utf-8", newline="\n")
    assert markdown == golden.read_text(encoding="utf-8")


def test_output_is_deterministic(synthetic_pdf):
    path = synthetic_pdf("synthetic_header_footer.pdf")
    first = parse_pdf(path, path.name, sha256_file(path), PdfConfig())
    second = parse_pdf(path, path.name, sha256_file(path), PdfConfig())
    assert build_full_conversion(first, context()) == build_full_conversion(second, context())


def test_front_matter_fields_and_toggle():
    document = make_document([make_block(0, BlockType.paragraph, "Metin")])
    markdown = build_full_conversion(document, context(models={"vision": "m@sha256:1"}, status="completed_with_warnings"))
    header = yaml.safe_load(markdown.split("---")[1])
    assert header == {"source": "papers/a.pdf", "sha256": SHA, "generated": "2026-09-13T12:00:00", "mode": "balanced",
                      "prompt_sha256": "b" * 64, "models": {"vision": "m@sha256:1"}, "status": "completed_with_warnings"}
    assert not build_full_conversion(document, context(front_matter=False)).startswith("---")


def test_page_markers_toggle_and_parse_error():
    pages = [Page(number=1, width=1, height=1), Page(number=2, width=1, height=1, parse_error="x")]
    document = make_document([make_block(0, BlockType.paragraph, "Bir"), make_block(1, BlockType.paragraph, "İki", page=2)], pages)
    markdown = build_full_conversion(document, context(front_matter=False))
    assert markdown == "<!-- page: 1 -->\n\nBir\n\n<!-- page: 2 [parse_error] -->\n\nİki\n"
    assert build_full_conversion(document, context(front_matter=False, page_markers=False)) == "Bir\n\nİki\n"


def test_unreadable_scanned_page_is_marked_even_without_markers():
    pages = [Page(number=1, width=1, height=1, page_class=PageClass.scanned)]
    document = make_document([], pages)
    assert unreadable_pages(document) == [1]
    assert build_full_conversion(document, context(front_matter=False, page_markers=False)) == "[unreadable_page]\n"
    pages[0].ocr_applied = True
    assert unreadable_pages(document) == []


def test_block_types_rendering():
    blocks = [
        make_block(0, BlockType.header_footer, "Journal 2024"),
        make_block(1, BlockType.heading, "Title", level=1),
        make_block(2, BlockType.heading, "A B S T R A C T", level=2),
        make_block(3, BlockType.paragraph, "First line of a para-\ngraph continues\nhere."),
        make_block(4, BlockType.list, "• first item\nwraps here"),
        make_block(5, BlockType.list, "(ii) second item"),
        make_block(6, BlockType.list, "3) third item"),
        make_block(7, BlockType.figure, ""),
        make_block(8, BlockType.caption, "Figure 1. Caption"),
        make_block(9, BlockType.algorithm, "for i in x:\n    y()"),
        make_block(10, BlockType.reference, "[1] A. Author, Title."),
        make_block(11, BlockType.heading, "Deep", level=6),
    ]
    markdown = build_full_conversion(make_document(blocks), context(front_matter=False, page_markers=False))
    assert markdown == (
        "# Title\n\n## ABSTRACT\n\nFirst line of a paragraph continues here.\n\n"
        "- first item wraps here\n- (ii) second item\n3. third item\n\n"
        "Figure 1. Caption\n\n```text\nfor i in x:\n    y()\n```\n\n[1] A. Author, Title.\n\n###### Deep\n"
    )


@pytest.mark.parametrize("text, expected", [
    ("# not a heading", "\\# not a heading"),
    ("> quote", "\\> quote"),
    ("- dash sentence", "\\- dash sentence"),
    ("1. numbered sentence", "1\\. numbered sentence"),
    ("---", "\\---"),
    ("p<0.05 and a<b", "p<0.05 and a&lt;b"),
    ("<script>alert(1)</script>", "&lt;script>alert(1)&lt;/script>"),
    ("Normal text", "Normal text"),
])
def test_paragraph_escaping(text, expected):
    markdown = build_full_conversion(make_document([make_block(0, BlockType.paragraph, text)]),
                                     context(front_matter=False, page_markers=False))
    assert markdown == expected + "\n"


@pytest.mark.parametrize("text, vocabulary, expected", [
    ("classifi-\ncation", set(), "classification"),
    ("pre-\ntrained", {"pre-trained"}, "pre-trained"),
    ("Speaker-\nDependent", set(), "Speaker-Dependent"),
    ("range 1990-\n2000", set(), "range 1990-2000"),
    ("word –\nnext", set(), "word – next"),
    ("soft\u00ad\nhyphen", set(), "softhyphen"),
    ("a  b\n\n  c", set(), "a b c"),
])
def test_reflow(text, vocabulary, expected):
    assert reflow(text, frozenset(vocabulary)) == expected


def test_hyphenated_vocabulary_comes_from_document():
    blocks = [make_block(0, BlockType.paragraph, "We use a pre-trained model."),
              make_block(1, BlockType.paragraph, "The pre-\ntrained weights and classifi-\ncation.")]
    markdown = build_full_conversion(make_document(blocks), context(front_matter=False, page_markers=False))
    assert "The pre-trained weights and classification." in markdown


# --- tablo, formül, şekil (Faz 05) ---

def visual_document(tables=(), equations=(), figures=(), blocks=()):
    document = make_document(list(blocks))
    return document.model_copy(update={"tables": list(tables), "equations": list(equations), "figures": list(figures)})


def ref_block(index, block_type, ref_id, text=""):
    block = make_block(index, block_type, text)
    block.ref_id = ref_id
    return block


def plain(**overrides):
    return context(front_matter=False, page_markers=False, **overrides)


def test_consistent_table_renders_markdown_or_html():
    table = Table(id="table-1", page=1, bbox=(0, 0, 1, 1), markdown="| a | b |\n|---|---|\n| 1 | 2 |", consistent=True)
    html_table = Table(id="table-2", page=1, bbox=(0, 0, 1, 1), html="<table></table>", consistent=True,
                       merged_cells=[TableCellSpan(row=0, col=0, colspan=2)])
    document = visual_document(tables=[table, html_table], blocks=[ref_block(0, BlockType.table, "table-1", "a b 1 2"),
                                                                     ref_block(1, BlockType.table, "table-2", "x")])
    assert build_full_conversion(document, plain()) == "| a | b |\n|---|---|\n| 1 | 2 |\n\n<table></table>\n"


def test_unstructured_table_renders_image_raw_text_and_marker():
    table = Table(id="table-1", number="6", caption="Table 6 Signals", page=1, bbox=(0, 0, 1, 1),
                  raw_text="Rate  Channels\n128  14", cache_path="tables/table_06.png", consistent=False)
    document = visual_document(tables=[table], blocks=[ref_block(0, BlockType.table, "table-1")])
    markdown, assets = render_full_conversion(document, plain(available_assets=frozenset({"table-1"})))
    assert markdown == ("![Table 6 Signals](assets/tables/table_06.png)\n\n```text\nRate  Channels\n128  14\n```\n\n"
                        "[table_structure_unavailable]\n")
    assert assets == ["tables/table_06.png"]
    markdown, assets = render_full_conversion(document, plain())
    assert "![" not in markdown and assets == []


def test_equation_rendering():
    raw = Equation(id="eq-1", number="1", raw_text="z = (x - mu) / s  (1)", page=1, bbox=(0, 0, 1, 1))
    latex = Equation(id="eq-2", number="2", latex=r"z = \frac{x-\mu}{s}", latex_valid=False, page=1, bbox=(0, 0, 1, 1))
    document = visual_document(equations=[raw, latex], blocks=[ref_block(0, BlockType.equation, "eq-1"),
                                                                ref_block(1, BlockType.equation, "eq-2")])
    assert build_full_conversion(document, plain()) == (
        r"```text" + "\nz = (x - mu) / s  (1)\n" + r"```" + "\n\n[latex_unavailable]\n\n$$\n" + r"z = \frac{x-\mu}{s}" + "\n$$ [latex_unverified]\n")


def test_figure_rendering_and_unavailable_marker():
    figure = Figure(id="fig-1", number="3", caption="Fig. 3. A [draft] pipeline", page=1, bbox=(0, 0, 1, 1),
                    cache_path="figures/figure_03.png")
    document = visual_document(figures=[figure], blocks=[ref_block(0, BlockType.figure, "fig-1"),
                                                         make_block(1, BlockType.figure, "")])
    markdown, assets = render_full_conversion(document, plain(available_assets=frozenset({"fig-1"})))
    assert markdown == "![Fig. 3. A (draft) pipeline](assets/figures/figure_03.png)\n"
    assert assets == ["figures/figure_03.png"]
    assert build_full_conversion(document, plain()) == "[figure_unavailable]\n"


def test_fence_longer_than_backticks_in_content():
    table = Table(id="table-1", page=1, bbox=(0, 0, 1, 1), raw_text="a ``` b", consistent=False)
    document = visual_document(tables=[table], blocks=[ref_block(0, BlockType.table, "table-1")])
    assert build_full_conversion(document, plain()).startswith("````text\na ``` b\n````")
