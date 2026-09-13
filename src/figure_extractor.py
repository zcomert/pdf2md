"""Şekil ve tablo bölgesi görsellerinin önbelleğe yazılması (§15). `parse_pdf` saf kaldığı için bu adım
ayrı çalışır ve PDF'i yeniden (salt okunur) açar. Mevcut görseller yeniden üretilmez."""
from dataclasses import dataclass, field

from .atomic_io import atomic_write_bytes
from .pdf_parser import open_pdf
from .render import embedded_image_png, render_region_png

TABLE_PADDING_PT = 2.0


@dataclass
class AssetResult:
    available: set = field(default_factory=set)  # görseli mevcut şekil/tablo kimlikleri
    failed: list = field(default_factory=list)   # (kimlik, sayfa, hata)
    written: int = 0


def materialize_assets(pdf_path, document, doc_cache_dir, dpi, padding_pt, overwrite=False):
    """`document.figures` ve görselli `document.tables` için `_cache/<sha>/` altına PNG yazar."""
    result = AssetResult()
    items = [(f.id, f.page, f.bbox, f.cache_path, f.image_xref, padding_pt) for f in document.figures if f.cache_path]
    # Tablo bölgeleri başlığın hemen altından/çizgilerden sıkı belirlenir; geniş pay başlık satırını görüntüye katar.
    items += [(t.id, t.page, t.bbox, t.cache_path, None, min(padding_pt, TABLE_PADDING_PT))
              for t in document.tables if t.cache_path and not t.consistent]  # görselden yapılandırılan tablo görsel istemez
    missing = [item for item in items if overwrite or not (doc_cache_dir / item[3]).is_file()]
    result.available.update(item[0] for item in items if item not in missing)
    if not missing:
        return result
    doc = open_pdf(pdf_path)
    try:
        for item_id, page_number, bbox, cache_path, xref, padding in missing:
            try:
                data = embedded_image_png(doc, xref) if xref else None
                if data is None:
                    data = render_region_png(doc[page_number - 1], bbox, dpi, padding)
                atomic_write_bytes(doc_cache_dir / cache_path, data)
                result.available.add(item_id)
                result.written += 1
            except Exception as exc:
                result.failed.append((item_id, page_number, f"{type(exc).__name__}: {exc}"))
    finally:
        doc.close()
    return result
