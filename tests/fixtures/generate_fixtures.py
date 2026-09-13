"""Sentetik test PDF'lerini deterministik olarak üretir.

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe -m tests.fixtures.generate_fixtures [--out KLASÖR]

Aynı PyMuPDF/Pillow sürümüyle her çalıştırma bayt bayt aynı dosyaları üretir.
Beklenen içerik `EXPECTED` sözlüğündedir; sonraki fazların testleri buradan okur.
"""
import argparse
import io
import random
import shutil
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

FIXTURES_DIR = Path(__file__).resolve().parent
A4 = fitz.paper_rect("a4")
MARGIN = 56
CONTENT_WIDTH = A4.width - 2 * MARGIN
FIXED_DATE = "D:20240101000000Z"
USER_PASSWORD = "user-secret"
OWNER_PASSWORD = "owner-secret"

SINGLE_COLUMN_TITLE = "Synthetic Study of Fatigue Detection"
SUBDIR_TITLE = "Different Study With The Same File Name"
TWO_COLUMN_TITLE = "Two Column Layout Example"
TABLE_EQUATION_TITLE = "Tables Equations and Figures"
LIST_ITEMS = ["Signal filtering", "Feature extraction", "Model training"]
LOREM = ("The proposed approach processes physiological signals collected from participants. "
         "Each recording is segmented into fixed windows and normalized before analysis. "
         "Results are reported on a held out test split to avoid optimistic estimates.")

TABLE_CAPTION = "Table 1. Classification results"
TABLE_ROWS = [
    ["Model", "Accuracy", "F1"],
    ["Bi-LSTM", "0.99", "0.98"],
    ["Bi-GRU", "0.96", "0.95"],
    ["SVM", "0.91", "0.90"],
]
EQUATIONS = [
    {"number": "1", "text": "z = (x - mu) / s"},
    {"number": "2", "text": "SPL = 20 log(p / p_ref)"},
]
FIGURE_CAPTION = "Figure 1. Proposed pipeline"
HEADER_TEXT = "Journal of Synthetic Studies"
HEADER_FOOTER_PAGES = 4
SCANNED_LINES = [
    "Scanned Document Sample",
    "This page was rendered to an image",
    "and contains no text layer at all.",
    "Optical character recognition should",
    "recover these sentences reliably.",
]

EXPECTED = {
    "synthetic_single_column.pdf": {
        "pages": 1,
        "title": SINGLE_COLUMN_TITLE,
        # Başlık seviye 1; bölüm başlıkları buna göre bir seviye aşağı kaydırılır (Faz 03)
        "headings": [
            {"text": SINGLE_COLUMN_TITLE, "level": 1},
            {"text": "Abstract", "level": 2},
            {"text": "1. Introduction", "level": 2},
            {"text": "2. Method", "level": 2},
            {"text": "2.1 Dataset", "level": 3},
            {"text": "3. Conclusion", "level": 2},
        ],
        "list_items": LIST_ITEMS,
    },
    "synthetic_two_column.pdf": {
        "pages": 1,
        "title": TWO_COLUMN_TITLE,
        # Okuma sırası: başlık, üst sol, üst sağ, tam genişlik tablo, alt sol, alt sağ
        "reading_order_markers": [TWO_COLUMN_TITLE, "LEFT-TOP", "RIGHT-TOP", TABLE_CAPTION,
                                  "LEFT-BOTTOM", "RIGHT-BOTTOM"],
        "table": TABLE_ROWS,
    },
    "synthetic_table_equation.pdf": {
        "pages": 1,
        "title": TABLE_EQUATION_TITLE,
        "table_caption": TABLE_CAPTION,
        "table": TABLE_ROWS,
        "equations": EQUATIONS,
        "figure_caption": FIGURE_CAPTION,
        "embedded_images": 1,
    },
    "synthetic_header_footer.pdf": {
        "pages": HEADER_FOOTER_PAGES,
        "header": HEADER_TEXT,
        "footer_pattern": "Page {n} of %d" % HEADER_FOOTER_PAGES,
    },
    "synthetic_scanned.pdf": {
        "pages": 1,
        "text_layer_chars": 0,
        "ocr_lines": SCANNED_LINES,
    },
    "synthetic_encrypted.pdf": {"opens_with_empty_password": False, "user_password": USER_PASSWORD},
    "synthetic_encrypted_empty_pw.pdf": {"opens_with_empty_password": True},
    "corrupt.pdf": {"valid": False},
    "not_a_pdf.PDF": {"valid": False},
    "subdir/synthetic_single_column.pdf": {"pages": 1, "title": SUBDIR_TITLE},
    "duplicate_copy.pdf": {"same_content_as": "synthetic_single_column.pdf"},
}

# Şifreleme rastgele değer kullandığından bu dosyaların hash'i üretimden üretime değişir.
NONDETERMINISTIC = {"synthetic_encrypted.pdf", "synthetic_encrypted_empty_pw.pdf"}


def new_document(title):
    doc = fitz.open()
    doc.set_metadata({
        "title": title,
        "author": "Fixture Author; Second Author",
        "subject": "pdf2md test fixture",
        "creator": "pdf2md generate_fixtures.py",
        "producer": "PyMuPDF",
        "creationDate": FIXED_DATE,
        "modDate": FIXED_DATE,
    })
    return doc


def new_page(doc):
    return doc.new_page(width=A4.width, height=A4.height)


def save(doc, path, **options):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path, garbage=4, deflate=True, no_new_id=True, **options)
    doc.close()


def text(page, x0, y, text_value, width=CONTENT_WIDTH, fontsize=10, fontname="helv",
         align=fitz.TEXT_ALIGN_LEFT):
    """Metni (x0, y) noktasından başlayan, sayfa sonuna uzanan kutuya yazar; metnin alt y'sini döndürür."""
    rect = fitz.Rect(x0, y, x0 + width, A4.height - 8)
    spare = page.insert_textbox(rect, text_value, fontsize=fontsize, fontname=fontname, align=align)
    if spare < 0:
        raise ValueError(f"Metin sayfaya sığmadı: {text_value[:40]!r}")
    return rect.y1 - spare


def draw_table(page, top, rows, left=MARGIN, width=CONTENT_WIDTH, row_height=20, fontsize=10):
    col_width = width / len(rows[0])
    bottom = top + row_height * len(rows)
    for i in range(len(rows) + 1):
        y = top + i * row_height
        page.draw_line((left, y), (left + width, y), width=0.8)
    for j in range(len(rows[0]) + 1):
        x = left + j * col_width
        page.draw_line((x, top), (x, bottom), width=0.8)
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            page.insert_text((left + j * col_width + 6, top + i * row_height + 14), cell,
                             fontsize=fontsize, fontname="hebo" if i == 0 else "helv")
    return bottom


def figure_png():
    image = Image.new("RGB", (480, 240), "white")
    draw = ImageDraw.Draw(image)
    for i, bar_height in enumerate([60, 120, 90, 180]):
        x0 = 40 + i * 110
        draw.rectangle([x0, 220 - bar_height, x0 + 70, 220], fill=(40, 90, 160))
    draw.line([20, 220, 460, 220], fill="black", width=2)
    draw.line([20, 20, 20, 220], fill="black", width=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def single_column_doc(title=SINGLE_COLUMN_TITLE):
    doc = new_document(title)
    page = new_page(doc)
    y = text(page, MARGIN, MARGIN, title, fontsize=20, fontname="hebo", align=fitz.TEXT_ALIGN_CENTER) + 16

    def heading(value):
        nonlocal y
        y = text(page, MARGIN, y, value, fontsize=13, fontname="hebo") + 6

    def paragraph(value):
        nonlocal y
        y = text(page, MARGIN, y, value) + 10

    heading("Abstract")
    paragraph(LOREM)
    heading("1. Introduction")
    paragraph(LOREM)
    heading("2. Method")
    paragraph("The method consists of the following steps:")
    for item in LIST_ITEMS:
        y = text(page, MARGIN + 16, y, f"- {item}", width=CONTENT_WIDTH - 16) + 2
    y += 8
    heading("2.1 Dataset")
    paragraph(LOREM)
    heading("3. Conclusion")
    paragraph(LOREM)
    return doc


def two_column_doc():
    doc = new_document(TWO_COLUMN_TITLE)
    page = new_page(doc)
    gap = 20
    col = (CONTENT_WIDTH - gap) / 2
    left_x, right_x = MARGIN, MARGIN + col + gap
    top = text(page, MARGIN, MARGIN, TWO_COLUMN_TITLE, fontsize=20, fontname="hebo",
               align=fitz.TEXT_ALIGN_CENTER) + 20
    column_text = " ".join([LOREM] * 2)
    bottom = max(text(page, left_x, top, f"LEFT-TOP {column_text}", width=col, fontsize=9),
                 text(page, right_x, top, f"RIGHT-TOP {column_text}", width=col, fontsize=9))
    y = text(page, MARGIN, bottom + 20, TABLE_CAPTION, fontname="hebo", align=fitz.TEXT_ALIGN_CENTER) + 6
    y = draw_table(page, y, TABLE_ROWS) + 24
    text(page, left_x, y, f"LEFT-BOTTOM {column_text}", width=col, fontsize=9)
    text(page, right_x, y, f"RIGHT-BOTTOM {column_text}", width=col, fontsize=9)
    return doc


def table_equation_doc():
    doc = new_document(TABLE_EQUATION_TITLE)
    page = new_page(doc)
    y = text(page, MARGIN, MARGIN, TABLE_EQUATION_TITLE, fontsize=18, fontname="hebo") + 10
    y = text(page, MARGIN, y, "Table 1 summarizes the results. The normalization in Eq. 1 is applied first.") + 14
    y = text(page, MARGIN, y, TABLE_CAPTION, fontname="hebo") + 6
    y = draw_table(page, y, TABLE_ROWS) + 30
    for equation in EQUATIONS:
        page.insert_text((A4.width / 2 - 70, y), equation["text"], fontsize=11, fontname="tiit")
        page.insert_text((A4.width - MARGIN - 20, y), f"({equation['number']})", fontsize=11, fontname="tiro")
        y += 30
    y = text(page, MARGIN, y, "where mu is the mean and s is the standard deviation.") + 20
    image_rect = fitz.Rect(MARGIN + 60, y, A4.width - MARGIN - 60, y + 200)
    page.insert_image(image_rect, stream=figure_png())
    text(page, MARGIN, image_rect.y1 + 8, FIGURE_CAPTION, align=fitz.TEXT_ALIGN_CENTER)
    return doc


def header_footer_doc():
    doc = new_document("Header Footer Example")
    for n in range(1, HEADER_FOOTER_PAGES + 1):
        page = new_page(doc)
        text(page, MARGIN, 24, HEADER_TEXT, fontsize=8, align=fitz.TEXT_ALIGN_CENTER)
        y = text(page, MARGIN, 80, f"Section {n}", fontsize=13, fontname="hebo") + 8
        text(page, MARGIN, y, " ".join([LOREM] * 2))
        text(page, MARGIN, A4.height - 40, f"Page {n} of {HEADER_FOOTER_PAGES}", fontsize=8,
             align=fitz.TEXT_ALIGN_CENTER)
    return doc


def scanned_doc(dpi=200):
    source = fitz.open()
    page = new_page(source)
    y = 120
    for i, line in enumerate(SCANNED_LINES):
        page.insert_text((MARGIN + 20, y), line, fontsize=22 if i == 0 else 16,
                         fontname="hebo" if i == 0 else "helv")
        y += 40
    png = page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")
    source.close()
    doc = new_document("Scanned Document Sample")
    scanned = new_page(doc)
    scanned.insert_image(scanned.rect, stream=png)
    return doc


def save_encrypted(path, user_password, overwrite):
    # MuPDF şifrelemede rastgele değer kullanır; bayt düzeyinde deterministik olamaz.
    # Git'te gereksiz fark oluşmasın diye mevcut dosya varsayılan olarak korunur.
    if path.exists() and not overwrite:
        return
    save(single_column_doc(title="Encrypted Document"), path, encryption=fitz.PDF_ENCRYPT_AES_256,
         owner_pw=OWNER_PASSWORD, user_pw=user_password, permissions=fitz.PDF_PERM_ACCESSIBILITY)


def write_corrupt(path, valid_source):
    # Yalnızca PDF başlığı + rastgele bayt: MuPDF onararak açamaz. Daha uzun bir önek
    # bırakılırsa MuPDF xref'i yeniden kurup sayfaları kısmen okuyabiliyor.
    rng = random.Random(1234)
    path.write_bytes(valid_source.read_bytes()[:16] + bytes(rng.randrange(256) for _ in range(4096)))


def generate(out_dir=FIXTURES_DIR, overwrite_encrypted=False):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    save(single_column_doc(), out / "synthetic_single_column.pdf")
    save(two_column_doc(), out / "synthetic_two_column.pdf")
    save(table_equation_doc(), out / "synthetic_table_equation.pdf")
    save(header_footer_doc(), out / "synthetic_header_footer.pdf")
    save(scanned_doc(), out / "synthetic_scanned.pdf")
    save_encrypted(out / "synthetic_encrypted.pdf", USER_PASSWORD, overwrite_encrypted)
    save_encrypted(out / "synthetic_encrypted_empty_pw.pdf", "", overwrite_encrypted)
    write_corrupt(out / "corrupt.pdf", out / "synthetic_single_column.pdf")
    (out / "not_a_pdf.PDF").write_bytes(b"This is plain text, not a PDF document.\n")
    save(single_column_doc(title=SUBDIR_TITLE), out / "subdir" / "synthetic_single_column.pdf")
    shutil.copyfile(out / "synthetic_single_column.pdf", out / "duplicate_copy.pdf")
    return sorted(EXPECTED)


def main():
    parser = argparse.ArgumentParser(description="Sentetik test PDF'lerini üretir")
    parser.add_argument("--out", default=str(FIXTURES_DIR), help="Çıktı klasörü")
    parser.add_argument("--overwrite-encrypted", action="store_true",
                        help="Mevcut şifreli PDF'leri de yeniden üret (hash'leri değişir)")
    args = parser.parse_args()
    for name in generate(args.out, args.overwrite_encrypted):
        print(name)


if __name__ == "__main__":
    main()
