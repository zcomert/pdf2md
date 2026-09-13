"""Sayfa ve bölge render'ı (§12.4). Görsel model (Faz 07) ve bölge görüntüleri için ortak."""
import fitz


def padded_clip(page, bbox, padding_pt):
    rect = fitz.Rect(bbox[0] - padding_pt, bbox[1] - padding_pt, bbox[2] + padding_pt, bbox[3] + padding_pt)
    return rect & page.rect


def render_region_png(page, bbox, dpi, padding_pt=0.0):
    """Bölgeyi PNG baytı olarak render eder; bölge sayfa sınırına kırpılır."""
    clip = padded_clip(page, bbox, padding_pt)
    if clip.is_empty:
        raise ValueError(f"Boş render bölgesi: {bbox}")
    return page.get_pixmap(dpi=dpi, clip=clip, alpha=False).tobytes("png")


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
