"""Tablo hücrelerinin tutarlılık değerlendirmesi ve Markdown/HTML gösterimi (§13)."""
import html
import re

from .document_model import TableCellSpan

NUMERIC_RE = re.compile(r"^[\s(\[]*[-−+±]?\s*\d[\d.,]*\s*%?\s*(?:[±]\s*\d[\d.,]*)?[)\]*†‡a-z]*\s*$")
MIN_FILLED_RATIO = 0.5


def clean_cell(value):
    if value is None:
        return None
    return " ".join(str(value).split())


def assess_cells(rows):
    """§12.3: "metin çıkarımı tablo hücrelerini korumuyor" kararı. Tutarlı sayılması için en az 2×2 olmalı,
    birleştirilmemiş hücrelerin en az yarısı dolu olmalı, tamamen boş satır/sütun bulunmamalıdır.
    `None` birleştirilmiş hücreyi (PyMuPDF), boş metin boş hücreyi gösterir."""
    if len(rows) < 2 or max((len(row) for row in rows), default=0) < 2:
        return False
    width = max(len(row) for row in rows)
    grid = [list(row) + [None] * (width - len(row)) for row in rows]
    real = [cell for row in grid for cell in row if cell is not None]
    filled = [cell for cell in real if cell.strip()]
    if not real or len(filled) < MIN_FILLED_RATIO * len(real):
        return False
    if any(all(cell is None or not cell.strip() for cell in row) for row in grid):
        return False
    for column in range(width):
        if all(grid[r][column] is None or not grid[r][column].strip() for r in range(len(grid))):
            return False
    return True


def merged_cells_from_bboxes(row_cells):
    """PyMuPDF `table.rows[i].cells` (hücre bbox'ı veya birleşik hücrede None) listesinden rowspan/colspan."""
    boxes = [cell for row in row_cells for cell in row if cell is not None]
    if not boxes:
        return []
    col_edges = sorted({round(box[0], 1) for box in boxes})
    row_edges = sorted({round(box[1], 1) for box in boxes})
    spans = []
    for r, row in enumerate(row_cells):
        for c, box in enumerate(row):
            if box is None:
                continue
            colspan = sum(1 for edge in col_edges if box[0] - 0.5 <= edge < box[2] - 0.5)
            rowspan = sum(1 for edge in row_edges if box[1] - 0.5 <= edge < box[3] - 0.5)
            if colspan > 1 or rowspan > 1:
                spans.append(TableCellSpan(row=r, col=c, rowspan=max(rowspan, 1), colspan=max(colspan, 1)))
    return spans


def to_markdown(rows):
    """İlk satır başlık. Sayısal sütunlar sağa hizalanır. Hücre içindeki `|` kaçırılır."""
    width = max(len(row) for row in rows)
    grid = [[_markdown_cell(row[c] if c < len(row) else None) for c in range(width)] for row in rows]
    alignments = []
    for c in range(width):
        body = [rows[r][c] for r in range(1, len(rows)) if c < len(rows[r]) and rows[r][c] and rows[r][c].strip()]
        numeric = body and sum(bool(NUMERIC_RE.match(value)) for value in body) >= 0.8 * len(body)
        alignments.append("---:" if numeric else "---")
    lines = ["| " + " | ".join(grid[0]) + " |", "|" + "|".join(alignments) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in grid[1:])
    return "\n".join(lines)


def to_html(rows, merged):
    """Birleşik hücreli tablolar için HTML (§13). Birleşik hücrenin kapsadığı konumlar atlanır."""
    spans = {(span.row, span.col): span for span in merged}
    covered = set()
    for span in merged:
        for r in range(span.row, span.row + span.rowspan):
            for c in range(span.col, span.col + span.colspan):
                if (r, c) != (span.row, span.col):
                    covered.add((r, c))
    out = ["<table>"]
    for r, row in enumerate(rows):
        tag = "th" if r == 0 else "td"
        cells = []
        for c, value in enumerate(row):
            if (r, c) in covered or (value is None and (r, c) not in spans):
                continue
            span = spans.get((r, c))
            attributes = ""
            if span and span.rowspan > 1:
                attributes += f' rowspan="{span.rowspan}"'
            if span and span.colspan > 1:
                attributes += f' colspan="{span.colspan}"'
            cells.append(f"<{tag}{attributes}>{html.escape(value or '')}</{tag}>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def _markdown_cell(value):
    return (value or "").replace("|", "\\|").replace("\n", " ")


def rows_from_words(words, row_tolerance=3.0, column_gap=8.0):
    """Hücreleri güvenilir çıkarılamayan tablo bölgesinin metni: kelimeler satırlara gruplanır, geniş yatay
    boşluklar iki boşlukla gösterilir. PyMuPDF `get_text("words")` biçiminde (x0, y0, x1, y1, metin, ...)."""
    rows = []
    for word in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        center = (word[1] + word[3]) / 2
        if rows and abs(rows[-1]["center"] - center) <= row_tolerance:
            rows[-1]["words"].append(word)
        else:
            rows.append({"center": center, "words": [word]})
    lines = []
    for row in rows:
        ordered = sorted(row["words"], key=lambda w: w[0])
        text = ordered[0][4]
        for previous, word in zip(ordered, ordered[1:]):
            text += ("  " if word[0] - previous[2] > column_gap else " ") + word[4]
        lines.append(text)
    return "\n".join(lines)
