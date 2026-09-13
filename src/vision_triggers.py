"""Görsel model çağırma kuralları (§12.3, §23). Tablo tek bir veri yapısıdır; mod × tetikleyici kararı buradan okunur."""
from dataclasses import dataclass

from .document_model import CandidateKind, PageClass

FAST, BALANCED, FULL = "fast", "balanced", "full"

# tetikleyici → hangi modlarda görsel model çağrılır
TRIGGER_MODES = {
    "scanned_no_ocr": {FAST, BALANCED, FULL},        # taranmış sayfa, OCR yok
    "scanned_ocr_failed": {FAST, BALANCED, FULL},    # taranmış sayfa, OCR başarısız/boş
    "table_inconsistent": {BALANCED, FULL},          # metin katmanı hücreleri korumuyor
    "equation_requested": {BALANCED, FULL},          # formül adayı ve plan formül istiyor
    "figure_requested": {BALANCED, FULL},            # şekil adayı ve plan şekil istiyor
    "reading_order_uncertain": {BALANCED, FULL},
    "garbled_text": {BALANCED, FULL},                # §12.1: metin katmanında bozulmuş içerik
    "candidate_full": {FULL},                        # tüm tablo/formül/şekil adayları (plan istemese de)
    "page_full_analysis": {FULL},                    # mixed ve scanned tüm sayfalar
}

PAGE_DPI_LIMIT = 150  # tam sayfa görüntüleri modele büyük geldiğinde küçültülür; bölge kırpmaları render_dpi ile


@dataclass(frozen=True)
class VisionJob:
    task: str            # table | equation | figure | page_text | page_layout
    trigger: str
    page: int
    bbox: tuple | None   # None: tam sayfa
    ref_id: str | None = None

    @property
    def key(self):
        """Sonuç önbelleği anahtarı: görev, sayfa ve bölge (mod ve tetikleyiciden bağımsız)."""
        box = "page" if self.bbox is None else "_".join(str(int(round(v))) for v in self.bbox)
        return f"{self.task}:p{self.page}:{box}"


def enabled(trigger, mode):
    return mode in TRIGGER_MODES[trigger]


def select_vision_jobs(document, mode, needs=None, ocr_failed_pages=()):
    """Belge ve moda göre görsel model işleri. `needs`: plan ihtiyaçları (tables, equations, figures; varsayılan plan
    hepsini ister). Aynı bölge için tek iş üretilir; ilk eşleşen tetikleyici kaydedilir.

    Karar (şekiller): BALANCED modda yalnızca başlıksız şekiller gönderilir. Başlıklı şekilde modelin katacağı tek
    bilgi şekil türüdür ve tam dönüşüm bunu kullanmaz (§10.2: gereksiz model çağrısı önlenir). FULL modda tüm
    şekiller gönderilir."""
    needs = {"tables": True, "equations": True, "figures": True, **(needs or {})}
    jobs, seen = [], set()

    def add(job):
        if job.key not in seen and enabled(job.trigger, mode):
            seen.add(job.key)
            jobs.append(job)

    figures = {figure.id: figure for figure in document.figures}
    for page in document.pages:
        if page.page_class == PageClass.scanned and not page.ocr_applied:
            trigger = "scanned_ocr_failed" if page.number in ocr_failed_pages else "scanned_no_ocr"
            add(VisionJob("page_text", trigger, page.number, None))
        elif page.page_class == PageClass.scanned and mode == FULL:
            add(VisionJob("page_text", "page_full_analysis", page.number, None))
    garbled = {w.page for w in document.warnings if w.code == "garbled_text"}
    for number in sorted(garbled):
        add(VisionJob("page_text", "garbled_text", number, None))

    for candidate in document.candidates:
        bbox = tuple(candidate.bbox)
        if candidate.kind == CandidateKind.table:
            # Metin katmanından tutarlı çıkarılmış tablo görsel modele gönderilmez (FULL dahil): §13'e göre
            # uyuşmazlıkta metin katmanı değeri kullanılacağı için çağrının sonucu çıktıyı değiştiremez.
            if candidate.needs_vision:
                if needs["tables"]:
                    add(VisionJob("table", "table_inconsistent", candidate.page, bbox, candidate.ref_id))
                add(VisionJob("table", "candidate_full", candidate.page, bbox, candidate.ref_id))
        elif candidate.kind == CandidateKind.equation:
            if needs["equations"]:
                add(VisionJob("equation", "equation_requested", candidate.page, bbox, candidate.ref_id))
            add(VisionJob("equation", "candidate_full", candidate.page, bbox, candidate.ref_id))
        elif candidate.kind == CandidateKind.figure:
            figure = figures.get(candidate.ref_id)
            if needs["figures"] and figure is not None and not figure.caption:
                add(VisionJob("figure", "figure_requested", candidate.page, bbox, candidate.ref_id))
            add(VisionJob("figure", "candidate_full", candidate.page, bbox, candidate.ref_id))

    for page in document.pages:
        if page.reading_order_uncertain:
            add(VisionJob("page_layout", "reading_order_uncertain", page.number, None))
        elif page.page_class == PageClass.mixed:
            add(VisionJob("page_layout", "page_full_analysis", page.number, None))
    return jobs
