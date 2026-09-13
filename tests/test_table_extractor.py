import pytest

from src.document_model import TableCellSpan
from src.table_extractor import assess_cells, merged_cells_from_bboxes, rows_from_words, to_html, to_markdown


@pytest.mark.parametrize("rows, expected", [
    ([["Model", "Acc"], ["A", "0.9"]], True),
    ([["Model", "Acc", None], ["A", "0.9", "0.8"]], True),          # None = birleşik hücre
    ([["Model"], ["A"]], False),                                     # tek sütun
    ([["Model", "Acc"]], False),                                     # tek satır
    ([["Model", "Acc"], ["", ""], ["A", "0.9"]], False),             # boş satır
    ([["Model", ""], ["A", ""], ["B", ""]], False),                  # boş sütun
    ([["a", "", "", ""], ["", "", "", "b"], ["c", "", "", "d"]], False),  # dolu oranı < %50
])
def test_assess_cells(rows, expected):
    assert assess_cells(rows) is expected


def test_merged_cells_from_bboxes():
    # 2 sütunluk başlık hücresi + 2x2 gövde
    rows = [
        [(0, 0, 100, 10), None],
        [(0, 10, 50, 20), (50, 10, 100, 20)],
    ]
    assert merged_cells_from_bboxes(rows) == [TableCellSpan(row=0, col=0, rowspan=1, colspan=2)]
    assert merged_cells_from_bboxes([[(0, 0, 50, 20), (50, 0, 100, 10)], [None, (50, 10, 100, 20)]]) == [
        TableCellSpan(row=0, col=0, rowspan=2, colspan=1)]


def test_to_markdown_alignment_and_escaping():
    markdown = to_markdown([["Model", "Accuracy", "Note"], ["A|B", "0.99", "iyi"], ["C", "95.2 ± 1.3", "orta\nsatır"]])
    assert markdown.splitlines() == [
        "| Model | Accuracy | Note |",
        "|---|---:|---|",
        "| A\\|B | 0.99 | iyi |",
        "| C | 95.2 ± 1.3 | orta satır |",
    ]


def test_to_html_with_spans_and_escaping():
    html = to_html([["Grup", None], ["<a>", "1"]], [TableCellSpan(row=0, col=0, colspan=2)])
    assert html == '<table>\n<tr><th colspan="2">Grup</th></tr>\n<tr><td>&lt;a&gt;</td><td>1</td></tr>\n</table>'


def test_rows_from_words_groups_lines_and_marks_gaps():
    words = [(10, 0, 30, 8, "Model"), (60, 0, 90, 8, "Acc"), (10, 12, 25, 20, "Bi"), (27, 12, 40, 20, "LSTM"),
             (60, 13, 80, 21, "0.99")]
    assert rows_from_words(words) == "Model  Acc\nBi LSTM  0.99"
