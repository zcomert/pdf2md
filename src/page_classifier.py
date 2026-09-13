from .document_model import PageClass

# Metni vektör yol olarak çizilmiş sayfa ("Print To PDF" çıktıları): gövde metni neredeyse yok ama çizim
# sayısı yüksek. Gerçek setteki bu tür sayfalarda 635–5972 çizim, normal grafik sayfalarında ise
# yüzlerce çizimle birlikte binlerce karakter vardır (tests/fixtures/real/SOURCES.md).
VECTOR_TEXT_MIN_DRAWINGS = 200
# Sayfaya özgü bir damga satırı gövde metnini `min_text_chars` üstüne çıkarabilir (Shilaskar s.1: 115 karakter,
# 5289 çizim). Çok yoğun çizimde bu yüzden daha yüksek bir karakter sınırı uygulanır. Logo/grafik yoğun normal
# ilk sayfalarda (Vekkot s.1: 3867 çizim) binlerce karakter metin bulunur.
DENSE_VECTOR_MIN_DRAWINGS = 1000
DENSE_VECTOR_MAX_CHARS = 500
# Çizim sayımı pahalı olabildiğinden yalnızca bu sınırın altında metni olan sayfalarda yapılır.
DRAWING_COUNT_CHAR_LIMIT = 1000


def union_area(rects, clip):
    """Dikdörtgenlerin `clip` içinde kalan birleşik alanı (örtüşmeler iki kez sayılmaz)."""
    x0c, y0c, x1c, y1c = clip
    clipped = []
    for x0, y0, x1, y1 in rects:
        x0, y0, x1, y1 = max(x0, x0c), max(y0, y0c), min(x1, x1c), min(y1, y1c)
        if x1 > x0 and y1 > y0:
            clipped.append((x0, y0, x1, y1))
    if not clipped:
        return 0.0
    xs = sorted({x for r in clipped for x in (r[0], r[2])})
    ys = sorted({y for r in clipped for y in (r[1], r[3])})
    area = 0.0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in clipped):
                area += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
    return area


def image_area_ratio(image_rects, width, height):
    page_area = width * height
    if page_area <= 0:
        return 0.0
    return min(1.0, union_area(image_rects, (0, 0, width, height)) / page_area)


def classify_page(body_chars, image_ratio, drawing_count, pdf_config):
    """§11.2 sınıflandırması. Döner: (sınıf, uyarı kodları).

    Karakter sayısı olarak üst/alt bilgi ve kenar damgaları hariç gövde metni kullanılır; aksi halde her
    sayfada tekrarlanan bir indirme damgası taranmış sayfayı `text` gösterebilir. Tablonun kapsamadığı
    "az metin + düşük görsel oranı" durumu `text` + `low_text_page`, vektör çizilmiş metin şüphesi ise
    `scanned` + `vector_text_suspected` olarak ele alınır (fazlar/README.md karar tablosu).
    """
    if (drawing_count is not None and drawing_count >= DENSE_VECTOR_MIN_DRAWINGS
            and body_chars < DENSE_VECTOR_MAX_CHARS and image_ratio < pdf_config.scanned_image_ratio):
        return PageClass.scanned, ["vector_text_suspected"]
    if body_chars >= pdf_config.min_text_chars:
        if image_ratio >= pdf_config.mixed_image_ratio:
            return PageClass.mixed, []
        return PageClass.text, []
    if image_ratio >= pdf_config.scanned_image_ratio:
        return PageClass.scanned, []
    if drawing_count is not None and drawing_count >= VECTOR_TEXT_MIN_DRAWINGS:
        return PageClass.scanned, ["vector_text_suspected"]
    return PageClass.text, ["low_text_page"]
