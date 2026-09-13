"""İş akışı orkestrasyonu (Faz 04: varsayılan prompt ile tam dönüşüm).

GUI (Faz 13) aynı çekirdeği kullanabilsin diye ilerleme `BatchEvents` ile bildirilir, iptal ve duraklatma
`CancelToken` ile işbirlikçi olarak yapılır: belge ve aşama sınırlarında kontrol edilir.
"""
import threading
import time
from datetime import datetime

from .atomic_io import atomic_write_text
from .document_model import DocumentWarning
from .errors import DocumentError, ErrorStage, FatalBatchError
from .model_clients import ModelUnavailable
from .vision_enrichment import apply_vision_results, run_vision_jobs
from .vision_triggers import select_vision_jobs
from .assets import sync_assets
from .figure_extractor import materialize_assets
from .markdown_builder import RenderContext, render_full_conversion, unreadable_pages
from .paths import ensure_under_output, resolve_output_paths
from .pdf_parser import parse_config_hash, parse_pdf
from .schemas import DocumentStatus, HistoryEntry, ModelRef

COMPLETED_STATUSES = {DocumentStatus.completed, DocumentStatus.completed_with_warnings}


class Cancelled(Exception):
    """Kullanıcı iptal etti; belge yarım bırakılmadan çalışma durduruldu."""


class CancelToken:
    def __init__(self):
        self._cancelled = threading.Event()
        self._running = threading.Event()
        self._running.set()

    def cancel(self):
        self._cancelled.set()
        self._running.set()

    def pause(self):
        self._running.clear()

    def resume(self):
        self._running.set()

    @property
    def cancelled(self):
        return self._cancelled.is_set()

    @property
    def paused(self):
        return not self._running.is_set()

    def checkpoint(self):
        """Duraklatılmışsa devam edilene kadar bekler; iptal edilmişse `Cancelled` fırlatır."""
        while not self._running.wait(timeout=0.2):
            pass
        if self._cancelled.is_set():
            raise Cancelled()


class BatchEvents:
    """İlerleme bildirimleri. Varsayılan gerçekleme hiçbir şey yapmaz; CLI ve GUI alt sınıf yazar."""

    def on_run_start(self, total):
        pass

    def on_document_start(self, relative_path, index, total):
        pass

    def on_stage(self, relative_path, stage):
        pass

    def on_document_end(self, relative_path, status, warnings, output_path, error=None):
        pass

    def on_run_end(self, summary):
        pass


def decide(record, prompt_sha256, output_file, retry_failed, force):
    """Döner: `process`, `skip` veya `not_selected`.

    Atlama (§9.3, Faz 04 hali): durum tamamlanmış, prompt hash'i aynı ve çıktı dosyası mevcut ve boş değil.
    SHA-256 değişimi keşif aşamasında belgeyi zaten `pending` yapar. Plan hash'i (mod, modeller, ayrıştırıcı
    sürümü) Faz 08–10'da eklenecek.
    """
    if force:
        return "process"
    if record.status in COMPLETED_STATUSES:
        if record.prompt_sha256 == prompt_sha256 and output_file is not None and _non_empty(output_file):
            return "skip"
        return "process"
    if record.status == DocumentStatus.failed and not retry_failed:
        return "not_selected"
    return "process"


def _non_empty(path):
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


class BatchProcessor:
    def __init__(self, config, state, cache, output_dir, run_id, logger, prompt, force=False,
                 events=None, cancel_token=None, now=None, ocr_settings=None, vision=None):
        self.config = config
        self.state = state
        self.cache = cache
        self.output_dir = output_dir
        self.run_id = run_id
        self.logger = logger
        self.prompt = prompt
        self.force = force
        self.events = events or BatchEvents()
        self.cancel_token = cancel_token or CancelToken()
        self._now = now or (lambda: datetime.now().isoformat(timespec="seconds"))
        self._config_hash = parse_config_hash(config.pdf)
        self.ocr_settings = ocr_settings
        self.vision = vision  # VisionSetup (istemci + model bilgisi) veya None

    def run(self, discovery, summary):
        """Belgeleri sırayla işler ve `summary` sayaçlarını doldurur. İptalde `Cancelled` yayılır;
        o ana kadarki durum state'e yazılmış olur."""
        started = time.monotonic()
        documents = [(pdf, self.state.get(pdf.relative_path)) for pdf in discovery.documents]
        documents = [(pdf, record) for pdf, record in documents if record is not None and record.sha256]
        existing = {rel: record.output_path for rel, record in self.state.state.documents.items() if record.output_path}
        planned = resolve_output_paths([(pdf.relative_path, record.sha256) for pdf, record in documents], existing)

        self.events.on_run_start(len(documents))
        try:
            for index, (pdf, record) in enumerate(documents, start=1):
                self.cancel_token.checkpoint()
                output_file = self.output_dir / record.output_path if record.output_path else None
                decision = decide(record, self.prompt.sha256, output_file, self.config.processing.retry_failed, self.force)
                if decision == "skip":
                    summary.skipped += 1
                    self.logger.info("Atlandı (değişmedi): %s", pdf.relative_path)
                    self.events.on_document_end(pdf.relative_path, DocumentStatus.skipped, record.warnings, record.output_path)
                    continue
                if decision == "not_selected":
                    summary.not_retried += 1
                    self.logger.info("Denenmedi (önceki çalıştırmada başarısız; --retry-failed): %s", pdf.relative_path)
                    continue
                self.events.on_document_start(pdf.relative_path, index, len(documents))
                self._process(pdf, record, planned[pdf.relative_path], summary)
        finally:
            summary.total_time_sec = round(time.monotonic() - started, 2)
            self.events.on_run_end(summary)
        return summary

    def _process(self, pdf, record, output_rel, summary):
        rel = pdf.relative_path
        self.state.update(rel, status=DocumentStatus.processing, attempts=record.attempts + 1, last_run_id=self.run_id)
        started = time.monotonic()
        stage = ErrorStage.parse
        try:
            self.events.on_stage(rel, "parse")
            document = self._load_or_parse(pdf, record, summary)
            self.cancel_token.checkpoint()

            stage = ErrorStage.vision
            self.events.on_stage(rel, "vision")
            document, vision_warnings, vision_model = self._enrich_with_vision(pdf, record, document, summary)
            self.cancel_token.checkpoint()

            self.events.on_stage(rel, "assets")
            doc_cache_dir = self.cache.doc_dir(record.sha256)
            assets = materialize_assets(pdf.absolute_path, document, doc_cache_dir, self.config.pdf.render_dpi,
                                        self.config.pdf.crop_padding_pt, overwrite=self.force)
            for item_id, page_number, error in assets.failed:
                self.logger.warning("Görsel çıkarılamadı [%s, s.%d]: %s — %s", item_id, page_number, rel, error)
            self.cancel_token.checkpoint()

            stage = ErrorStage.write
            self.events.on_stage(rel, "write")
            warnings = [str(w) for w in document.warnings] + vision_warnings + list(self.prompt.run_warnings)
            warnings += sorted({f"asset_extraction_failed: page {page_number}" for _, page_number, _ in assets.failed})
            warnings += [f"unreadable_page: page {n}" for n in unreadable_pages(document)
                         if f"unreadable_page: page {n}" not in warnings]
            status = DocumentStatus.completed_with_warnings if warnings else DocumentStatus.completed
            models = {"vision": vision_model.reference} if vision_model else {}
            markdown, referenced = render_full_conversion(document, self._context(rel, record.sha256, status,
                                                                                   frozenset(assets.available), models))
            target = ensure_under_output(self.output_dir / output_rel, self.output_dir)
            self.cancel_token.checkpoint()
            # Görseller Markdown'dan önce yazılır: Markdown hiçbir zaman olmayan bir görsele referans vermez.
            sync_assets(target.parent, doc_cache_dir, referenced)
            atomic_write_text(target, markdown)
        except (Cancelled, FatalBatchError):
            # Belgenin kendisinde sorun yok (iptal veya model servisi kapandı): sonraki çalıştırmada işlenir.
            self.state.update(rel, status=DocumentStatus.pending)
            raise
        except DocumentError as exc:
            return self._fail(rel, exc.stage, exc.message, summary)
        except OSError as exc:
            return self._fail(rel, ErrorStage.write, f"Yazılamadı: {exc}", summary)
        except Exception as exc:  # beklenmeyen hata tek bir PDF yüzünden batch'i durdurmamalı
            self.logger.exception("Beklenmeyen hata [%s]: %s", stage.value, rel)
            return self._fail(rel, stage, f"{type(exc).__name__}: {exc}", summary)

        history = list(record.history)
        if record.status in COMPLETED_STATUSES and record.prompt_sha256 and record.prompt_sha256 != self.prompt.sha256:
            history.append(HistoryEntry(prompt_sha256=record.prompt_sha256, plan_hash=record.plan_hash,
                                        output_path=record.output_path, status=record.status,
                                        processed_at=record.processed_at, run_id=record.last_run_id))
        elapsed = round(time.monotonic() - started, 2)
        self.state.update(rel, status=status, warnings=warnings, output_path=output_rel,
                          prompt_sha256=self.prompt.sha256, processed_at=self._now(), processing_time_sec=elapsed,
                          error_stage=None, error=None, history=history,
                          models={"vision": ModelRef(name=vision_model.name, digest=vision_model.digest)} if vision_model else {})
        if status == DocumentStatus.completed:
            summary.completed += 1
        else:
            summary.completed_with_warnings += 1
        self.logger.info("Tamamlandı [%s]: %s → %s (%.1f sn, %d uyarı)", status.value, rel, output_rel, elapsed, len(warnings))
        self.events.on_document_end(rel, status, warnings, output_rel)

    def _load_or_parse(self, pdf, record, summary):
        signature = self.ocr_settings.signature if self.ocr_settings else None
        document = self.cache.load_document(record.sha256, self._config_hash, force=self.force, ocr_signature=signature)
        if document is not None:
            summary.parsed_from_cache += 1
            return document
        document = parse_pdf(pdf.absolute_path, pdf.relative_path, record.sha256, self.config.pdf, self.ocr_settings)
        self.cache.save_document(document)
        summary.parsed += 1
        classes = ", ".join(f"{name}={count}" for name, count in (("text", document.stats.text_pages),
                            ("mixed", document.stats.mixed_pages), ("scanned", document.stats.scanned_pages)) if count)
        ocr = f", OCR {document.stats.ocr_pages} sayfa" if document.stats.ocr_pages else ""
        self.logger.info("Ayrıştırıldı: %s (%d sayfa: %s%s)", pdf.relative_path, document.stats.pages, classes, ocr)
        return document

    def _enrich_with_vision(self, pdf, record, document, summary):
        """§12.3 tetikleyicilerine göre görsel model işleri. Döner: (belge, uyarı metinleri, kullanılan model veya None).
        Model servisi kapanırsa `FatalBatchError` (§28: batch durur)."""
        failed_ocr = {w.page for w in document.warnings if w.code in ("ocr_failed", "ocr_empty")}
        jobs = select_vision_jobs(document, self.config.mode, None, failed_ocr)
        if not jobs:
            return document, [], None
        if self.vision is None:
            warning = DocumentWarning(code="vision_unavailable", message=f"{len(jobs)} görsel iş çalıştırılamadı")
            return document, [str(warning)], None
        sha = record.sha256
        cache_path = self.cache.doc_dir(sha) / "vision" / f"{self.vision.info.digest[:12]}.json"
        try:
            run = run_vision_jobs(pdf.absolute_path, jobs, self.vision.client, cache_path, self.cache.model_raw_dir(sha),
                                  self.cache.errors_dir(sha), self.config.pdf.render_dpi, self.config.pdf.crop_padding_pt,
                                  force=self.force, checkpoint=self.cancel_token.checkpoint)
        except ModelUnavailable as exc:
            raise FatalBatchError(ErrorStage.vision, str(exc)) from exc
        summary.vision_calls += run.calls
        document, warnings, applied = apply_vision_results(document, jobs, run)
        if run.unavailable:
            warnings.append(DocumentWarning(code="vision_unavailable", message="görsel model bulunamadı"))
        self.logger.info("Görsel model: %s — %d iş, %d önbellekten, %d çağrı, %d başarısız", pdf.relative_path,
                         len(jobs), run.from_cache, run.calls, len(run.failures))
        return document, [str(w) for w in warnings], (self.vision.info if applied else None)

    def _context(self, relative_path, sha256, status, available_assets=frozenset(), models=None):
        return RenderContext(source_path=relative_path, sha256=sha256, generated=self._now(), mode=self.config.mode,
                             status=status.value, prompt_sha256=self.prompt.sha256, models=models or {},
                             front_matter=self.config.output.front_matter, page_markers=self.config.output.page_markers,
                             available_assets=available_assets)

    def _fail(self, relative_path, stage, message, summary):
        self.state.update(relative_path, status=DocumentStatus.failed, error_stage=stage, error=message)
        summary.failed += 1
        self.logger.error("Başarısız [%s]: %s — %s", stage.value, relative_path, message)
        self.events.on_document_end(relative_path, DocumentStatus.failed, [], None, error=message)
