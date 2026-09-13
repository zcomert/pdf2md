"""PyMuPDF ile metin, blok ve sayfa bilgisinin çıkarımı (§11.1) ve `DocumentModel` üretimi.

`parse_pdf` saf bir fonksiyondur: global durum tutmaz, açık dosya nesnesi döndürmez. Faz 10'da
süreç havuzunda paralel çalıştırılacaktır. OCR ve görsel model çağırmaz (Faz 06–07).
"""
import hashlib
import json
import re

import fitz

from . import PARSER_VERSION
from .document_model import (Block, BlockType, DocumentModel, DocumentSource, DocumentStats, DocumentWarning,
                             Line, Page, PageClass, Section)
from .errors import DocumentError, ErrorStage
from .layout_analyzer import (NUMBERING_RE, RawBlock, RawLine, classify_blocks, detect_gutter, document_gutter,
                              gutter_fits, mark_header_footer, normalize_heading_text, order_page, split_by_style)
from .page_classifier import DRAWING_COUNT_CHAR_LIMIT, classify_page, image_area_ratio

# Ligatürler açılır (ﬁ → fi), boşluklar korunur, sayfa dışı metin atılır. Görseller `dict` çıktısına
# gömülmez (bellek); görsel konumları `get_image_info` ile alınır.
TEXT_FLAGS = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP
INVISIBLE_CHARS = re.compile("[​‌‍⁠﻿]")
BOLD_FONT_RE = re.compile(r"bold|black|heavy|semibold|demibold|[-,]bd\b", re.I)
ITALIC_FONT_RE = re.compile(r"italic|oblique|[-,]it\b", re.I)
GARBLED_RATIO = 0.05


def parse_config_hash(pdf_config):
    relevant = {key: getattr(pdf_config, key) for key in ("min_text_chars", "mixed_image_ratio", "scanned_image_ratio")}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:16]


def open_pdf(path):
    """PDF'i salt okunur açar (§32.2). Şifreliyse boş parola denenir (§28)."""
    try:
        doc = fitz.open(path, filetype="pdf")
    except Exception as exc:
        # MuPDF mesajı dosyanın mutlak yolunu içerir; kayıtta dosya zaten belli olduğundan çıkarılır.
        detail = str(exc).replace(f"'{path}'", "").replace(str(path), "").strip()
        raise DocumentError(ErrorStage.parse, f"PDF açılamadı ({type(exc).__name__}): {detail}") from exc
    if doc.needs_pass and not doc.authenticate(""):
        doc.close()
        raise DocumentError(ErrorStage.parse, "PDF şifreli ve boş parola ile açılamıyor")
    if doc.page_count == 0:
        doc.close()
        raise DocumentError(ErrorStage.parse, "PDF'te okunabilir sayfa yok (bozuk olabilir)")
    return doc


def parse_pdf(path, relative_path, sha256, pdf_config):
    doc = open_pdf(path)
    try:
        return _parse_document(doc, relative_path, sha256, pdf_config)
    finally:
        doc.close()


def _parse_document(doc, relative_path, sha256, pdf_config):
    warnings = []
    if getattr(doc, "is_repaired", False):
        warnings.append(DocumentWarning(code="pdf_repaired", message="PDF yapısı onarılarak açıldı"))

    raw_pages = []
    for page in doc:
        number = page.number + 1
        info = {"number": number, "width": page.rect.width, "height": page.rect.height, "blocks": [],
                "error": None, "image_ratio": 0.0, "drawing_count": None, "garbled": False}
        try:
            blocks, char_count, garbled = _extract_blocks(page, number)
            images = [tuple(image["bbox"]) for image in page.get_image_info()]
            blocks.extend(RawBlock(number, image_bbox, is_image=True) for image_bbox in images
                          if image_bbox[2] > image_bbox[0] and image_bbox[3] > image_bbox[1])
            info.update(blocks=blocks, char_count=char_count, garbled=garbled,
                        image_ratio=image_area_ratio(images, page.rect.width, page.rect.height))
            if char_count < DRAWING_COUNT_CHAR_LIMIT:
                info["drawing_count"] = len(page.get_cdrawings())
        except Exception as exc:  # tek sayfa hatası belgeyi durdurmaz (§28)
            info.update(error=f"{type(exc).__name__}: {exc}", char_count=0)
            warnings.append(DocumentWarning(code="page_parse_error", page=number, message=str(exc)))
        raw_pages.append(info)

    mark_header_footer([(p["number"], p["width"], p["height"], p["blocks"]) for p in raw_pages])

    page_gutters = [detect_gutter(info["blocks"], info["width"]) for info in raw_pages]
    shared_gutter = document_gutter(page_gutters, raw_pages[0]["width"])
    pages, ordered_pages = [], []
    for info, gutter in zip(raw_pages, page_gutters):
        if gutter is None and shared_gutter is not None and gutter_fits(info["blocks"], info["width"], shared_gutter):
            gutter = shared_gutter
        ordered, columns, gutter, uncertain = order_page(info["blocks"], info["width"], info["height"], gutter)
        body_chars = sum(b.chars for b in ordered if b.type != BlockType.header_footer and not b.is_image)
        page_class, codes = (PageClass.text, []) if info["error"] else classify_page(
            body_chars, info["image_ratio"], info["drawing_count"], pdf_config)
        warnings.extend(DocumentWarning(code=code, page=info["number"]) for code in codes)
        if info["garbled"]:
            warnings.append(DocumentWarning(code="garbled_text", page=info["number"]))
        pages.append(Page(number=info["number"], width=info["width"], height=info["height"], page_class=page_class,
                          char_count=info["char_count"], body_char_count=body_chars,
                          text_block_count=sum(1 for b in ordered if not b.is_image),
                          image_area_ratio=info["image_ratio"], drawing_count=info["drawing_count"],
                          columns=columns, gutter_x=gutter, reading_order_uncertain=uncertain,
                          vector_text_suspected="vector_text_suspected" in codes, parse_error=info["error"]))
        ordered_pages.append((info["number"], ordered))

    metadata = {key: value.strip() for key, value in (doc.metadata or {}).items() if isinstance(value, str) and value.strip()}
    title = classify_blocks(ordered_pages, raw_pages[0]["height"], metadata)
    blocks = _to_blocks(ordered_pages)
    stats = DocumentStats(pages=len(pages),
                          text_pages=sum(p.page_class == PageClass.text for p in pages),
                          mixed_pages=sum(p.page_class == PageClass.mixed for p in pages),
                          scanned_pages=sum(p.page_class == PageClass.scanned for p in pages))
    return DocumentModel(parser_version=PARSER_VERSION, parse_config_hash=parse_config_hash(pdf_config),
                         source=DocumentSource(relative_path=relative_path, sha256=sha256, page_count=doc.page_count),
                         pdf_metadata=metadata, title=title, pages=pages, blocks=blocks,
                         sections=build_sections(blocks), warnings=warnings, stats=stats)


def _extract_blocks(page, number):
    data = page.get_text("dict", flags=TEXT_FLAGS)
    blocks, char_count, replacement_chars = [], 0, 0
    for raw in data["blocks"]:
        if raw.get("type") != 0:
            continue
        lines = []
        for raw_line in raw["lines"]:
            spans = [s for s in raw_line["spans"] if s["text"]]
            if not spans:
                continue
            text = INVISIBLE_CHARS.sub("", "".join(s["text"] for s in spans))
            if not text.strip():
                continue
            chars = bold_chars = italic_chars = 0
            sizes, fonts = {}, {}
            for span in spans:
                span_chars = len(INVISIBLE_CHARS.sub("", span["text"]).strip()) or 0
                font = span["font"].split("+", 1)[-1]
                bold = bool(span["flags"] & 16) or bool(BOLD_FONT_RE.search(font))
                italic = bool(span["flags"] & 2) or bool(ITALIC_FONT_RE.search(font))
                chars += span_chars
                bold_chars += span_chars if bold else 0
                italic_chars += span_chars if italic else 0
                sizes[round(span["size"], 1)] = sizes.get(round(span["size"], 1), 0) + span_chars + 0.001
                fonts[font] = fonts.get(font, 0) + span_chars + 0.001
            direction = raw_line.get("dir", (1, 0))
            lines.append(RawLine(text=text, bbox=tuple(raw_line["bbox"]), font=max(fonts, key=fonts.get),
                                 size=max(sizes, key=sizes.get), bold=chars > 0 and bold_chars / chars >= 0.8,
                                 italic=chars > 0 and italic_chars / chars >= 0.8, chars=chars,
                                 bold_chars=bold_chars, vertical=abs(direction[0]) < 0.5))
            char_count += len(re.sub(r"\s", "", text))
            replacement_chars += text.count("�")
        if lines:
            block = RawBlock(number, tuple(raw["bbox"]), lines)
            blocks.extend(split_by_style(block))
    garbled = char_count > 0 and replacement_chars / char_count > GARBLED_RATIO
    return blocks, char_count, garbled


def _to_blocks(ordered_pages):
    blocks, order = [], 0
    for number, raw_blocks in ordered_pages:
        for index, raw in enumerate(raw_blocks, start=1):
            text = raw.text if not raw.is_image else ""
            blocks.append(Block(
                id=f"p{number}-b{index}", type=raw.type, page=number, bbox=_round_bbox(raw.bbox), text=text,
                lines=[Line(text=l.text, bbox=_round_bbox(l.bbox), font=l.font, size=l.size, bold=l.bold, italic=l.italic)
                       for l in raw.lines],
                font=raw.font, size=raw.size, bold=raw.bold if raw.lines else False,
                italic=raw.italic if raw.lines else False,
                heading_level=raw.heading_level if raw.type == BlockType.heading else None,
                order=order, column=raw.column))
            order += 1
    return blocks


def _round_bbox(bbox):
    return tuple(round(value, 2) for value in bbox)


def build_sections(blocks):
    """Başlık bloklarından bölüm ağacı: her bölüm, aynı veya daha üst seviyedeki bir sonraki başlığa kadar sürer."""
    headings = [b for b in blocks if b.type == BlockType.heading]
    last_order = blocks[-1].order if blocks else 0
    sections, stack = [], []
    for index, heading in enumerate(headings, start=1):
        level = heading.heading_level or 1
        end = last_order
        for later in headings[index:]:
            if (later.heading_level or 1) <= level:
                end = later.order - 1
                break
        while stack and stack[-1].level >= level:
            stack.pop()
        text = normalize_heading_text(heading.text)
        match = NUMBERING_RE.match(text)
        section = Section(id=f"s{index}", title=text, level=level,
                          number=match.group("num").rstrip(".") if match and match.group("num")[0].isdigit() else None,
                          heading_block_id=heading.id, start_order=heading.order, end_order=end,
                          parent_id=stack[-1].id if stack else None)
        sections.append(section)
        stack.append(section)
    return sections
