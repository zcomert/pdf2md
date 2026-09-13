"""Görsel model işlerinin çalıştırılması ve sonuçların belgeye uygulanması.

`document.json` yalnızca metin katmanı ayrıştırmasını tutar. Görsel sonuçlar `_cache/<sha>/vision/<digest12>.json`
dosyasında iş anahtarına göre saklanır ve her çalıştırmada belgenin bir kopyasına uygulanır. Böylece mod değişince
PDF yeniden ayrıştırılmaz, yalnızca yeni gereken işler çalışır; görsel model değişince (digest) sonuçlar yenilenir.
"""
import json
import re
from dataclasses import dataclass, field

from .atomic_io import atomic_write_json
from .document_model import Block, BlockType, DocumentWarning, SourceMethod
from .evidence_verifier import validate_latex
from .pdf_parser import build_sections, open_pdf
from .render import render_page_png, render_region_png
from .table_extractor import assess_cells, clean_cell, to_markdown
from .vision_client import UNCLEAR
from .vision_triggers import PAGE_DPI_LIMIT

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
TABLE_PADDING_PT = 2.0
PAGE_BLOCK_TYPES = {"heading": BlockType.heading, "paragraph": BlockType.paragraph, "list": BlockType.list,
                    "caption": BlockType.caption, "table": BlockType.table, "equation": BlockType.equation,
                    "footnote": BlockType.footnote}
REPLACEABLE_TYPES = {BlockType.heading, BlockType.paragraph, BlockType.list, BlockType.caption, BlockType.footnote,
                     BlockType.reference}


@dataclass
class VisionRun:
    results: dict = field(default_factory=dict)    # iş anahtarı → sonuç
    failures: dict = field(default_factory=dict)   # iş anahtarı → hata
    calls: int = 0
    from_cache: int = 0
    unavailable: bool = False


def load_vision_cache(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("results", {}) if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def run_vision_jobs(pdf_path, jobs, client, cache_path, raw_dir, errors_dir, render_dpi, padding_pt,
                    force=False, checkpoint=None):
    """Önbellekte olmayan işleri çalıştırır; her başarılı sonuç hemen önbelleğe yazılır (kesintide kaybolmaz).
    `ModelUnavailable` yayılır (§28: batch durur)."""
    run = VisionRun()
    cached = {} if force else load_vision_cache(cache_path)
    pending = [job for job in jobs if job.key not in cached]
    run.results.update({job.key: cached[job.key] for job in jobs if job.key in cached})
    run.from_cache = len(run.results)
    if not pending:
        return run
    doc = open_pdf(pdf_path)
    try:
        for job in pending:
            if checkpoint:
                checkpoint()
            page = doc[job.page - 1]
            if job.bbox is None:
                dpi = min(render_dpi, PAGE_DPI_LIMIT)
                png = render_page_png(page, dpi)
                size = (round(page.rect.width * dpi / 72), round(page.rect.height * dpi / 72))
            else:
                padding = TABLE_PADDING_PT if job.task == "table" else padding_pt
                png = render_region_png(page, job.bbox, render_dpi, padding)
                size = (round((job.bbox[2] - job.bbox[0] + 2 * padding) * render_dpi / 72),
                        round((job.bbox[3] - job.bbox[1] + 2 * padding) * render_dpi / 72))
            outcome = client.run(job, png, raw_dir=raw_dir, errors_dir=errors_dir, image_size=size)
            run.calls += outcome.calls
            if outcome.result is not None:
                run.results[job.key] = outcome.result
                cached[job.key] = outcome.result
                atomic_write_json(cache_path, {"model": client.model, "results": cached})
            else:
                run.failures[job.key] = outcome.error
                if outcome.unavailable:
                    run.unavailable = True
                    break
    finally:
        doc.close()
    return run


def apply_vision_results(document, jobs, run):
    """Sonuçları belgenin kopyasına uygular. Döner: (belge, uyarılar, uygulanan sonuç sayısı)."""
    document = document.model_copy(deep=True)
    tables = {t.id: t for t in document.tables}
    equations = {e.id: e for e in document.equations}
    figures = {f.id: f for f in document.figures}
    pages = {p.number: p for p in document.pages}
    warnings, applied, page_changes = [], 0, False
    for job in jobs:
        result = run.results.get(job.key)
        if result is None:
            if job.key in run.failures:
                warnings.append(DocumentWarning(code="vision_failed", page=job.page,
                                                message=f"{job.task}: {run.failures[job.key]}"))
            continue
        applied += 1
        if job.task == "table" and job.ref_id in tables:
            mismatches = _apply_table(tables[job.ref_id], result)
            if mismatches is None:
                warnings.append(DocumentWarning(code="vision_table_inconsistent", page=job.page))
            elif mismatches:
                warnings.append(DocumentWarning(code="table_value_mismatch", page=job.page,
                                                message=f"{mismatches} hücre metin katmanıyla uyuşmadı"))
        elif job.task == "equation" and job.ref_id in equations:
            equation = equations[job.ref_id]
            equation.latex = result["latex"].strip()
            equation.latex_valid = validate_latex(equation.latex)[0]
            equation.source_method = SourceMethod.vision
        elif job.task == "figure" and job.ref_id in figures:
            figure = figures[job.ref_id]
            figure.figure_type = result["figure_type"]
            if not figure.caption and result.get("caption"):
                figure.caption = " ".join(result["caption"].split())
            figure.source_method = SourceMethod.vision
        elif job.task == "page_text" and job.page in pages:
            _replace_page_text(document, pages[job.page], result["blocks"])
            page_changes = True
        elif job.task == "page_layout" and job.page in pages:
            page_changes |= _apply_layout(document, pages[job.page], result["columns"])
    if page_changes:
        for order, block in enumerate(document.blocks):
            block.order = order
        document.sections = build_sections(document.blocks)
    document.stats.vision_calls = applied
    return document, warnings, applied


def _numbers(text):
    return {token.replace(",", ".") for token in NUMBER_RE.findall(text or "")}


def _apply_table(table, result):
    """§13: görselden gelen sayısal hücreler aynı bölgenin metin katmanında aranır; bulunmayan değer tahmin edilmez,
    `[unclear]` yapılır. Metin katmanı yoksa (görsel/çizim olarak gömülü tablo) değerler görselden alınır.
    Döner: uyuşmayan hücre sayısı, tutarsız sonuçta None."""
    rows = [[clean_cell(cell) or "" for cell in result["header"]]] + \
           [[clean_cell(cell) or "" for cell in row] for row in result["rows"]]
    if not assess_cells(rows):
        return None
    text_numbers = _numbers(table.raw_text)
    mismatches = 0
    if text_numbers:
        for row in rows:
            for index, cell in enumerate(row):
                values = _numbers(cell)
                if values and not values <= text_numbers:
                    row[index] = UNCLEAR
                    mismatches += 1
    table.cells = rows
    table.markdown = to_markdown(rows)
    table.consistent = True
    table.source_method = SourceMethod.vision
    if not table.caption and result.get("caption"):
        table.caption = " ".join(result["caption"].split())
    return mismatches


def _replace_page_text(document, page, blocks):
    """Sayfanın akış metni bloklarını (başlık, paragraf, liste, başlık, dipnot, kaynakça) görsel modelin okumasıyla
    değiştirir; tablo/formül/şekil ve üst/alt bilgi blokları korunur."""
    kept = [b for b in document.blocks if b.page == page.number and b.type not in REPLACEABLE_TYPES]
    top = [b for b in kept if b.type == BlockType.header_footer and b.bbox[1] < page.height / 2]
    rest = [b for b in kept if b not in top]
    new = [Block(id=f"p{page.number}-v{index}", type=PAGE_BLOCK_TYPES[item["type"]], page=page.number,
                 bbox=(0.0, 0.0, page.width, page.height), text=item["text"].strip(), source_method=SourceMethod.vision,
                 heading_level=(item.get("heading_level") or 2) if item["type"] == "heading" else None, order=0)
           for index, item in enumerate(blocks, start=1) if item["text"].strip()]
    _replace_page_blocks(document, page.number, top + new + rest)
    page.vision_applied = True


def _apply_layout(document, page, columns):
    """Okuma sırası belirsiz sayfada model tek sütun diyorsa bloklar yukarıdan aşağı sıralanır; iki sütun diyorsa
    mevcut sütun sırası doğrulanmış sayılır."""
    page.reading_order_uncertain = False
    if columns != 1 or page.columns == 1:
        return False
    blocks = [b for b in document.blocks if b.page == page.number]
    top = [b for b in blocks if b.type == BlockType.header_footer and b.bbox[1] < page.height / 2]
    bottom = [b for b in blocks if b.type == BlockType.header_footer and b not in top]
    body = sorted((b for b in blocks if b.type != BlockType.header_footer), key=lambda b: (round(b.bbox[1] / 3), b.bbox[0]))
    for block in body:
        block.column = 0
    page.columns = 1
    _replace_page_blocks(document, page.number, top + body + bottom)
    return True


def _replace_page_blocks(document, page_number, page_blocks):
    before = [b for b in document.blocks if b.page < page_number]
    after = [b for b in document.blocks if b.page > page_number]
    document.blocks = before + page_blocks + after
