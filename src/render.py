"""Sayfa ve bölge render'ı (§12.4). Görsel model (Faz 07) ve bölge görüntüleri için ortak."""
import fitz


def padded_clip(page, bbox, padding_pt):
    rect = fitz.Rect(bbox[0] - padding_pt, bbox[1] - padding_pt, bbox[2] + padding_pt, bbox[3] + padding_pt)
    return rect & page.rect


def render_region_png(page, bbox, dpi, padding_pt=0.0, mask_outside=False):
    """Bölgeyi PNG baytı olarak render eder; bölge sayfa sınırına kırpılır. `mask_outside`: dolgu payına düşen ve
    merkezi `bbox` dışında kalan karakterler (komşu düzyazı, formül numarası) beyazla örtülür."""
    clip = padded_clip(page, bbox, padding_pt)
    if clip.is_empty:
        raise ValueError(f"Boş render bölgesi: {bbox}")
    pixmap = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
    if mask_outside:
        _mask_foreign_text(page, pixmap, clip, fitz.Rect(bbox), dpi)
    return pixmap.tobytes("png")


def _mask_foreign_text(page, pixmap, clip, region, dpi):
    scale = fitz.Matrix(dpi / 72, dpi / 72)
    data = page.get_text("rawdict", clip=clip)
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for char in span.get("chars", []):
                    rect = fitz.Rect(char["bbox"])
                    cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
                    if not char["c"].strip() or (region.x0 - 0.5 <= cx <= region.x1 + 0.5
                                                 and region.y0 - 0.5 <= cy <= region.y1 + 0.5):
                        continue
                    # Karakter kutusu font yüksekliğinden gelir ve formül karakterlerine taşabilir; örtü bölge dışında
                    # kalan kısımla sınırlanır.
                    if cy < region.y0:
                        rect.y1 = min(rect.y1, region.y0)
                    elif cy > region.y1:
                        rect.y0 = max(rect.y0, region.y1)
                    elif cx < region.x0:
                        rect.x1 = min(rect.x1, region.x0)
                    else:
                        rect.x0 = max(rect.x0, region.x1)
                    box = (rect * scale).irect & pixmap.irect
                    if not box.is_empty:
                        pixmap.set_rect(box, (255, 255, 255))


def render_page_png(page, dpi):
    return page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")


def region_cache_name(page_number, bbox, dpi):
    """Render önbelleği dosya adı: sayfa, yuvarlanmış bölge ve DPI."""
    x0, y0, x1, y1 = (int(round(v)) for v in bbox)
    return f"p{page_number}_{x0}_{y0}_{x1}_{y1}_{dpi}.png"


def embedded_image_png(doc, xref):
    """Gömülü görseli PNG'ye çevirir. Maske (saydamlık) uygulanır, CMYK/gri tonlama RGB'ye dönüştürülür.
    Çevrilemezse None döner; çağıran bölgeyi render eder."""
    try:
        pixmap = fitz.Pixmap(doc, xref)
        smask = doc.xref_get_key(xref, "SMask")
        if smask[0] == "xref":
            mask = fitz.Pixmap(doc, int(smask[1].split()[0]))
            pixmap = fitz.Pixmap(pixmap, mask)
        if pixmap.colorspace and pixmap.colorspace.n not in (1, 3):
            pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
        return pixmap.tobytes("png")
    except Exception:
        return None
