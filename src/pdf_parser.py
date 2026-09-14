"""PyMuPDF ile metin, blok ve sayfa bilgisinin çıkarımı (§11.1) ve `DocumentModel` üretimi.

`parse_pdf` saf bir fonksiyondur: global durum tutmaz, açık dosya nesnesi döndürmez. Faz 10'da
süreç havuzunda paralel çalıştırılacaktır. OCR ve görsel model çağırmaz (Faz 06–07).
"""
import hashlib
import json
import re

import fitz

from . import PARSER_VERSION
from .document_model import (Block, BlockType, Candidate, CandidateKind, DocumentModel, DocumentSource,
                             DocumentStats, DocumentWarning, Equation, Figure, Line, Page, PageClass, Section,
                             SourceMethod, Table)
from .errors import DocumentError, ErrorStage
from .layout_analyzer import (NUMBERING_RE, RawBlock, RawLine, body_font_size, classify_blocks, detect_gutter,
                              document_gutter, gutter_fits, mark_header_footer, normalize_heading_text, order_page,
                              split_by_style)
from .paths import safe_filename
from .table_extractor import to_html, to_markdown
from .visual_detector import detect_page_visuals
from .ocr import OCR_UNAVAILABLE_SIGNATURE, build_ocr_blocks, merge_ocr_blocks, ocr_page, text_line_boxes
from .page_classifier import DRAWING_COUNT_CHAR_LIMIT, classify_page, image_area_ratio

# Ligatürler açılır (ﬁ → fi), boşluklar korunur, sayfa dışı metin atılır. Görseller `dict` çıktısına
# gömülmez (bellek); görsel konumları `get_image_info` ile alınır.
TEXT_FLAGS = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP
INVISIBLE_CHARS = re.compile("[​‌‍⁠﻿]")
BOLD_FONT_RE = re.compile(r"bold|black|heavy|semibold|demibold|[-,]bd\b", re.I)
ITALIC_FONT_RE = re.compile(r"italic|oblique|[-,]it\b", re.I)
# Matematik fontları (§12.2): TeX (CMMI, CMSY, CMEX, MSBM), Cambria Math, STIX, MathType, Symbol
MATH_FONT_RE = re.compile(r"^(?:CM(?:MI|SY|EX|BSY)|MSBM|MSAM|EUFM|RSFS|CambriaMath|Cambria-Math|STIX|MT(?:MI|SY|EX)|Symbol|"
                          r"TimesNewRoman.*Italic.*Math|.*Math)", re.I)
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
        raise DocumentError(ErrorStage.parse, f"PDF açılamadı ({type(exc).__name__}): {detail}",
                            error_type="corrupt_pdf") from exc
    if doc.needs_pass and not doc.authenticate(""):
        doc.close()
        raise DocumentError(ErrorStage.parse, "PDF şifreli ve boş parola ile açılamıyor", error_type="encrypted_pdf")
    if doc.page_count == 0:
        doc.close()
        raise DocumentError(ErrorStage.parse, "PDF'te okunabilir sayfa yok (bozuk olabilir)", error_type="corrupt_pdf")
    return doc


def parse_pdf(path, relative_path, sha256, pdf_config, ocr_settings=None):
    """`ocr_settings` (`OcrSettings`) verilmezse taranmış sayfalar OCR'lanmaz ve `ocr_unavailable` uyarısı alır."""
    doc = open_pdf(path)
    try:
        return _parse_document(doc, relative_path, sha256, pdf_config, ocr_settings)
    finally:
        doc.close()


def _parse_document(doc, relative_path, sha256, pdf_config, ocr_settings=None):
    warnings = []
    if getattr(doc, "is_repaired", False):
        warnings.append(DocumentWarning(code="pdf_repaired", message="PDF yapısı onarılarak açıldı"))

    raw_pages = []
    for page in doc:
        number = page.number + 1
        info = {"number": number, "width": page.rect.width, "height": page.rect.height, "blocks": [],
                "error": None, "image_ratio": 0.0, "drawing_count": None, "garbled": False, "images": [],
                "ocr_applied": False}
        try:
            blocks, char_count, garbled = _extract_blocks(page, number)
            images = page.get_image_info(xrefs=True)
            boxes = [tuple(image["bbox"]) for image in images]
            blocks.extend(RawBlock(number, box, is_image=True) for box in boxes if box[2] > box[0] and box[3] > box[1])
            info.update(blocks=blocks, char_count=char_count, garbled=garbled, images=images,
                        image_ratio=image_area_ratio(boxes, page.rect.width, page.rect.height))
            if char_count < DRAWING_COUNT_CHAR_LIMIT:
                info["drawing_count"] = len(page.get_cdrawings())
        except Exception as exc:  # tek sayfa hatası belgeyi durdurmaz (§28)
            info.update(error=f"{type(exc).__name__}: {exc}", char_count=0)
            warnings.append(DocumentWarning(code="page_parse_error", page=number, message=str(exc)))
        raw_pages.append(info)

    mark_header_footer([(p["number"], p["width"], p["height"], p["blocks"]) for p in raw_pages])
    body_size = body_font_size([b for p in raw_pages for b in p["blocks"]])

    for info in raw_pages:
        body_chars = sum(b.chars for b in info["blocks"] if b.type != BlockType.header_footer and not b.is_image)
        info["body_chars"] = body_chars
        info["class"], info["codes"] = (PageClass.text, []) if info["error"] else classify_page(
            body_chars, info["image_ratio"], info["drawing_count"], pdf_config)
        if info["class"] == PageClass.scanned and not info["error"]:
            warnings.extend(_apply_ocr(doc[info["number"] - 1], info, ocr_settings))
    if any(info["ocr_applied"] for info in raw_pages):
        # OCR bloklarındaki tekrarlanan üst/alt bilgiler de işaretlensin
        mark_header_footer([(p["number"], p["width"], p["height"], p["blocks"]) for p in raw_pages])

    # Taranmış sayfalarda görsel tespit yapılmaz; tablo/şekil içerikleri görsel modelin konusudur (Faz 07).
    page_visuals = {}
    for info in raw_pages:
        if info["error"] or info["class"] == PageClass.scanned:
            continue
        try:
            page = doc[info["number"] - 1]
            gutter = detect_gutter(info["blocks"], info["width"])
            info["blocks"], page_visuals[info["number"]] = detect_page_visuals(
                page, info["number"], info["blocks"], body_size, gutter, images=info["images"])
        except Exception as exc:  # görsel tespit hatası sayfanın metnini kaybettirmemeli
            warnings.append(DocumentWarning(code="visual_detection_error", page=info["number"], message=str(exc)))

    page_gutters = [detect_gutter(info["blocks"], info["width"]) for info in raw_pages]
    shared_gutter = document_gutter(page_gutters, raw_pages[0]["width"])
    pages, ordered_pages = [], []
    for info, gutter in zip(raw_pages, page_gutters):
        if gutter is None and shared_gutter is not None and gutter_fits(info["blocks"], info["width"], shared_gutter):
            gutter = shared_gutter
        ordered, columns, gutter, uncertain = order_page(info["blocks"], info["width"], info["height"], gutter)
        codes = info["codes"]
        # OCR başarıyla uygulandıysa içerik kaybı yoktur; vektör metin şüphesi sayfa bayrağında kalır, uyarı olmaz.
        warnings.extend(DocumentWarning(code=code, page=info["number"]) for code in codes
                        if not (info["ocr_applied"] and code == "vector_text_suspected"))
        if info["garbled"]:
            warnings.append(DocumentWarning(code="garbled_text", page=info["number"]))
        pages.append(Page(number=info["number"], width=info["width"], height=info["height"], page_class=info["class"],
                          char_count=info["char_count"], body_char_count=info["body_chars"],
                          text_block_count=sum(1 for b in ordered if not b.is_image),
                          image_area_ratio=info["image_ratio"], drawing_count=info["drawing_count"],
                          columns=columns, gutter_x=gutter, reading_order_uncertain=uncertain,
                          vector_text_suspected="vector_text_suspected" in codes, parse_error=info["error"],
                          ocr_applied=info["ocr_applied"]))
        ordered_pages.append((info["number"], ordered))

    metadata = {key: value.strip() for key, value in (doc.metadata or {}).items() if isinstance(value, str) and value.strip()}
    title = classify_blocks(ordered_pages, raw_pages[0]["height"], metadata)
    blocks, block_ids = _to_blocks(ordered_pages)
    sections = build_sections(blocks)
    tables, equations, figures, candidates = _visual_models(page_visuals, block_ids, blocks, sections)
    stats = DocumentStats(pages=len(pages),
                          text_pages=sum(p.page_class == PageClass.text for p in pages),
                          mixed_pages=sum(p.page_class == PageClass.mixed for p in pages),
                          scanned_pages=sum(p.page_class == PageClass.scanned for p in pages),
                          ocr_pages=sum(p.ocr_applied for p in pages))
    ocr_signature = None
    if stats.scanned_pages:
        ocr_signature = ocr_settings.signature if ocr_settings else OCR_UNAVAILABLE_SIGNATURE
    return DocumentModel(parser_version=PARSER_VERSION, parse_config_hash=parse_config_hash(pdf_config),
                         source=DocumentSource(relative_path=relative_path, sha256=sha256, page_count=doc.page_count),
                         pdf_metadata=metadata, title=title, pages=pages, blocks=blocks, sections=sections,
                         tables=tables, equations=equations, figures=figures, candidates=candidates,
                         warnings=warnings, stats=stats, ocr_signature=ocr_signature)


def _apply_ocr(page, info, settings):
    """Taranmış sayfayı OCR'lar ve metin katmanıyla birleştirir (§11.4). Döner: uyarılar. OCR yoksa veya
    başarısızsa sayfa görsel model adayı olarak kalır (Faz 07); ikisi de yoksa `[unreadable_page]`."""
    number = info["number"]
    if settings is None:
        return [DocumentWarning(code="ocr_unavailable", page=number)]
    try:
        words, line_sizes = ocr_page(page, settings, TEXT_FLAGS)
        ocr_blocks = build_ocr_blocks(number, words, line_sizes, info["width"], text_line_boxes(info["blocks"]))
    except Exception as exc:
        return [DocumentWarning(code="ocr_failed", page=number, message=f"{type(exc).__name__}: {exc}")]
    info["blocks"], added = merge_ocr_blocks(info["blocks"], ocr_blocks)
    info["ocr_applied"] = True
    return [] if added else [DocumentWarning(code="ocr_empty", page=number)]


def _visual_models(page_visuals, block_ids, blocks, sections):
    """Tespit edilen öğeleri şema modellerine çevirir; blokların `ref_id` alanlarını bağlar."""
    by_id = {block.id: block for block in blocks}
    tables, equations, figures, candidates = [], [], [], []
    figure_names, table_names = set(), set()
    for number in sorted(page_visuals):
        visuals = page_visuals[number]
        for element in visuals.tables:
            table_id = f"table-{len(tables) + 1}"
            block_id = block_ids.get(id(element.block))
            caption_id = block_ids.get(id(element.caption)) if element.caption else None
            cache_path = None
            if not element.consistent:
                cache_path = "tables/" + _unique_name("table", element.number, number, len(tables) + 1, table_names) + ".png"
            markdown = html = None
            if element.consistent:
                if element.merged:
                    html = to_html(element.rows, element.merged)
                else:
                    markdown = to_markdown(element.rows)
            tables.append(Table(id=table_id, number=element.number, caption=_caption_text(by_id, caption_id),
                                caption_block_id=caption_id, page=number, bbox=_round_bbox(element.bbox),
                                cells=element.rows if element.consistent else [], merged_cells=element.merged,
                                markdown=markdown, html=html, raw_text=element.raw_text, cache_path=cache_path,
                                consistent=element.consistent))
            _link(by_id, block_id, table_id)
            candidates.append(Candidate(id=f"cand-{len(candidates) + 1}", kind=CandidateKind.table, page=number,
                                        bbox=_round_bbox(element.bbox), reasons=element.reasons, number=element.number,
                                        caption_block_id=caption_id, ref_id=table_id, needs_vision=not element.consistent,
                                        vision_trigger=None if element.consistent else "table_inconsistent"))
        for element in visuals.equations:
            equation_id = f"eq-{len(equations) + 1}"
            block_id = block_ids.get(id(element.block))
            block = by_id.get(block_id)
            equations.append(Equation(id=equation_id, number=element.number, raw_text=element.raw_text, page=number,
                                      section=_section_title(sections, block.order) if block else None,
                                      bbox=_round_bbox(element.bbox)))
            _link(by_id, block_id, equation_id)
            candidates.append(Candidate(id=f"cand-{len(candidates) + 1}", kind=CandidateKind.equation, page=number,
                                        bbox=_round_bbox(element.bbox), reasons=element.reasons, number=element.number,
                                        ref_id=equation_id, needs_vision=True, vision_trigger="equation_requested"))
        for element in visuals.figures:
            figure_id = f"fig-{len(figures) + 1}"
            block_id = block_ids.get(id(element.block))
            caption_id = block_ids.get(id(element.caption)) if element.caption else None
            name = _unique_name("figure", element.number, number, len(figures) + 1, figure_names)
            figures.append(Figure(id=figure_id, number=element.number, caption=_caption_text(by_id, caption_id),
                                  caption_block_id=caption_id, page=number, bbox=_round_bbox(element.bbox),
                                  cache_path=f"figures/{name}.png", image_xref=element.xref,
                                  referenced_by=figure_references(blocks, element.number)))
            _link(by_id, block_id, figure_id)
            candidates.append(Candidate(id=f"cand-{len(candidates) + 1}", kind=CandidateKind.figure, page=number,
                                        bbox=_round_bbox(element.bbox), reasons=element.reasons, number=element.number,
                                        caption_block_id=caption_id, ref_id=figure_id, needs_vision=False,
                                        vision_trigger="figure_requested"))
    return tables, equations, figures, candidates


def _link(by_id, block_id, ref_id):
    if block_id in by_id:
        by_id[block_id].ref_id = ref_id


def _caption_text(by_id, caption_id):
    block = by_id.get(caption_id)
    return " ".join(block.text.split()) if block else None


def _unique_name(prefix, number, page, index, used):
    if number and number.isdigit():
        base = f"{prefix}_{int(number):02d}"
    elif number:
        base = f"{prefix}_{safe_filename(number)}"
    else:
        base = f"{prefix}_p{page}_{index}"
    name, suffix = base, 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


def _section_title(sections, order):
    containing = [s for s in sections if s.start_order <= order <= s.end_order]
    return max(containing, key=lambda s: s.level).title if containing else None


FIGURE_REFERENCE_RE = re.compile(r"\b(?:Fig(?:ure)?s?\.?|FIGURES?|FIGS?\.|Şekil(?:ler)?)\s*((?:\d+[a-z]?(?:\s*(?:,|and|ve|&|–|-)\s*)?)+)")


def figure_references(blocks, number):
    """Metinde şekle atıf yapan paragraf/liste bloklarının kimlikleri ("Fig. 3", "Figs. 2 and 3", "Figures 2–4")."""
    if not number or not number[:1].isdigit():
        return []
    target = int(re.match(r"\d+", number).group())
    result = []
    for block in blocks:
        if block.type not in (BlockType.paragraph, BlockType.list):
            continue
        for match in FIGURE_REFERENCE_RE.finditer(block.text.replace("\n", " ")):
            if target in _expand_numbers(match.group(1)):
                result.append(block.id)
                break
    return result


def _expand_numbers(text):
    numbers = set()
    for start, end in re.findall(r"(\d+)(?:\s*[–-]\s*(\d+))?", text):
        low = int(start)
        high = int(end) if end else low
        if high >= low and high - low <= 50:
            numbers.update(range(low, high + 1))
    return numbers


def _extract_blocks(page, number, data=None):
    """`data` verilirse (ör. OCR metin sayfasının `dict` çıktısı) sayfa yeniden okunmaz."""
    data = data if data is not None else page.get_text("dict", flags=TEXT_FLAGS)
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
            chars = bold_chars = italic_chars = math_chars = 0
            sizes, fonts = {}, {}
            for span in spans:
                span_chars = len(INVISIBLE_CHARS.sub("", span["text"]).strip()) or 0
                font = span["font"].split("+", 1)[-1]
                bold = bool(span["flags"] & 16) or bool(BOLD_FONT_RE.search(font))
                italic = bool(span["flags"] & 2) or bool(ITALIC_FONT_RE.search(font))
                chars += span_chars
                bold_chars += span_chars if bold else 0
                italic_chars += span_chars if italic else 0
                math_chars += span_chars if MATH_FONT_RE.match(font) else 0
                sizes[round(span["size"], 1)] = sizes.get(round(span["size"], 1), 0) + span_chars + 0.001
                fonts[font] = fonts.get(font, 0) + span_chars + 0.001
            direction = raw_line.get("dir", (1, 0))
            lines.append(RawLine(text=text, bbox=tuple(raw_line["bbox"]), font=max(fonts, key=fonts.get),
                                 size=max(sizes, key=sizes.get), bold=chars > 0 and bold_chars / chars >= 0.8,
                                 italic=chars > 0 and italic_chars / chars >= 0.8, chars=chars,
                                 bold_chars=bold_chars, vertical=abs(direction[0]) < 0.5, math_chars=math_chars))
            char_count += len(re.sub(r"\s", "", text))
            replacement_chars += text.count("�")
        if lines:
            block = RawBlock(number, tuple(raw["bbox"]), lines)
            blocks.extend(split_by_style(block))
    garbled = char_count > 0 and replacement_chars / char_count > GARBLED_RATIO
    return blocks, char_count, garbled


def _to_blocks(ordered_pages):
    """Döner: (bloklar, ham blok nesne kimliği → blok kimliği)."""
    blocks, block_ids, order = [], {}, 0
    for number, raw_blocks in ordered_pages:
        for index, raw in enumerate(raw_blocks, start=1):
            text = raw.text if not raw.is_image else ""
            blocks.append(Block(
                id=f"p{number}-b{index}", type=raw.type, page=number, bbox=_round_bbox(raw.bbox), text=text,
                source_method=SourceMethod(raw.source),
                lines=[Line(text=l.text, bbox=_round_bbox(l.bbox), font=l.font, size=l.size, bold=l.bold, italic=l.italic)
                       for l in raw.lines],
                font=raw.font, size=raw.size, bold=raw.bold if raw.lines else False,
                italic=raw.italic if raw.lines else False,
                heading_level=raw.heading_level if raw.type == BlockType.heading else None,
                order=order, column=raw.column))
            block_ids[id(raw)] = blocks[-1].id
            order += 1
    return blocks, block_ids


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
