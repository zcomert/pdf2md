"""Çalıştırma çekirdeği: CLI ve GUI aynı iş akışını kullanır (§41 "iş mantığı tekrar yazılmaz").

`run(options, events, cancel_token, console)` argparse'a bağlı değildir. Kullanıcıya gösterilecek kısa satırlar
`console(metin, hata_mi)` geri çağrısına gider (CLI: stdout/stderr, GUI: arayüz paneli); ayrıntılar log dosyasındadır.
"""
import signal
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime

from .atomic_io import cleanup_temp_files
from .batch_processor import BatchEvents, BatchProcessor, Cancelled, CancelToken
from .cache_manager import CacheManager
from .config import load_config, merge_cli
from .default_prompt import resolve_prompt
from .errors import DocumentError, ErrorStage, FatalBatchError, PreflightError
from .llm_client import TextClient
from .logger import add_file_handler, new_run_id, setup_logging, unique_run_id
from .model_clients import ModelUnavailable
from .ollama_backend import OllamaBackend
from .paths import default_output_dir, normalize
from .pdf_discovery import discover, sync_with_state
from .preflight import (check_collection_output, check_gpu, check_models, check_ocr, check_xlsx, raise_on_errors,
                        run_preflight)
from .prompt_planner import (PlanContext, compute_plan_hash, create_plan, describe_plan, filter_targets,
                             summary_signature)
from .schemas import RunSummary
from .state_manager import OutputLock, StateManager
from .vision_client import VisionClient

EXIT_OK, EXIT_DOC_FAILED, EXIT_PREFLIGHT = 0, 1, 2
EXIT_CANCELLED = 130  # §24 dışı: Ctrl+C ile güvenli iptal (kabuk geleneği 128 + SIGINT)


@dataclass
class RunOptions:
    """CLI argümanlarının karşılığı (§24). Alan adları `merge_cli` ve `resolve_prompt` ile uyumludur."""
    input_dir: str | None = None
    output_dir: str | None = None
    config: str | None = None
    prompt: str | None = None
    prompt_file: str | None = None
    scope: str | None = None
    include: list | None = None
    collection_name: str | None = None
    collection_output: str | None = None
    mode: str | None = None
    recursive: bool | None = None
    retry_failed: bool | None = None
    force: bool = False
    plan_only: bool = False
    model_vision: str | None = None
    model_text: str | None = None
    dpi: int | None = None
    cpu_workers: int | None = None
    log_level: str | None = None
    console_logging: bool = True  # GUI'de konsol yoktur (pythonw)


@dataclass
class DocumentResult:
    relative_path: str
    status: str
    output_path: str | None
    error_stage: str | None = None
    error: str | None = None
    warnings_count: int = 0


@dataclass
class RunResult:
    exit_code: int
    output_dir: object = None
    log_path: str | None = None
    summary: RunSummary | None = None
    checks: list = field(default_factory=list)
    error: str | None = None
    hint: str | None = None
    cancelled: bool = False
    stopped: str | None = None
    collection_path: object = None
    collection_unchanged: bool = False
    collection_error: str | None = None
    documents: list = field(default_factory=list)
    plan_lines: list = field(default_factory=list)


def print_console(text, error=False):
    print(text, file=sys.stderr if error else sys.stdout)


class TextSetup:
    def __init__(self, client, info):
        self.client = client
        self.info = info


class VisionSetup:
    def __init__(self, client, info):
        self.client = client
        self.info = info


def create_model_backend(config, logger):
    """Model arka ucu; testler bu fonksiyonu sahte arka uçla değiştirir."""
    return OllamaBackend(config.ollama, logger, workers=config.processing.llm_workers)


def _log_checks(logger, results):
    for result in results:
        if result.ok:
            logger.info("Kontrol [%s]: %s", result.name, result.message)
        elif result.severity == "warning":
            hint = f" Öneri: {result.hint}" if result.hint else ""
            logger.warning("Kontrol [%s]: %s.%s", result.name, result.message, hint)


def _plan_context(config, input_path, pdf_count):
    """`--scope auto` dışı ve `--include` (CLI veya config) planı geçersiz kılar (§10.2)."""
    return PlanContext(input_is_file=input_path.is_file(), pdf_count=pdf_count,
                       cli_scope=None if config.scope == "auto" else config.scope, cli_include=tuple(config.include))


def make_plan(prompt, context, config, backend, models, logger, cache_root=None, write_cache=True, force=False):
    """İşleme planı ve hash'leri. Varsayılan prompt metin modelini çağırmaz. Döner: (PlanResult, plan_hash (atlama
    kuralı, envanter ayarları dahil), TextClient|None, içerik hash'i (çıkarım önbelleği))."""
    text_model = models.get("text")
    text_client = None
    if text_model is not None:
        text_client = TextClient(backend, text_model.name, config.models.text_num_ctx,
                                 config.models.max_output_tokens, logger, log_content=config.logging.log_model_content)
    cache_dir = cache_root / "plans" if cache_root is not None else None
    result = create_plan(prompt, context, text_client, text_model, cache_dir=cache_dir, write_cache=write_cache,
                         force=force, errors_dir=cache_dir / "errors" if cache_dir and write_cache else None,
                         logger=logger)
    hash_args = dict(text_model=text_model, vision_model=models.get("vision"), uses_text_model=result.uses_text_model)
    content_hash = compute_plan_hash(result.plan, prompt.sha256, config.mode, **hash_args)
    plan_hash = compute_plan_hash(result.plan, prompt.sha256, config.mode, **hash_args,
                                  summary=summary_signature(config.summary, text_model))
    return result, plan_hash, text_client, content_hash


def _log_plan(logger, result, plan_hash):
    plan = result.plan
    logger.info("Plan (%s): kapsam=%s, alanlar=%s, needs=%s, dil=%s, plan_hash=%s", result.source, plan.scope,
                ",".join(plan.requested_fields), ",".join(k for k, v in plan.needs.model_dump().items() if v) or "-",
                plan.output_language, plan_hash)
    logger.info("Kapsam gerekçesi: %s", plan.scope_reason or "-")
    for warning in result.warnings:
        logger.warning("Plan uyarısı: %s", warning)
    logger.debug("Plan: %s", plan.model_dump_json())


def _install_interrupt_handler(token, logger):
    """İlk Ctrl+C (veya Windows Ctrl+Break) güvenli iptal ister (belge yarım bırakılmaz), ikincisi hemen keser.
    Kilit `atexit` ve `finally` ile bırakılır. Ana iş parçacığı dışında (GUI) kurulmaz."""
    if threading.current_thread() is not threading.main_thread():
        return None
    signals = [signal.SIGINT] + ([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])
    previous = {signum: signal.getsignal(signum) for signum in signals}

    def handler(signum, frame):
        if token.cancelled:
            raise KeyboardInterrupt
        token.cancel()
        logger.warning("İptal istendi; güvenli bir noktada durulacak. Hemen çıkmak için tekrar Ctrl+C.")

    for signum in signals:
        signal.signal(signum, handler)
    return previous


def summary_lines(summary, cancelled=False):
    """Çalıştırma sonu özeti (§29): durum sayıları ve toplam süre."""
    handled = (summary.completed + summary.completed_with_warnings + summary.failed + summary.skipped
               + summary.not_retried)
    retried = f", önceki hata nedeniyle denenmeyen {summary.not_retried}" if summary.not_retried else ""
    lines = [f"Sonuç: toplam {summary.discovered}, completed {summary.completed}, "
             f"completed_with_warnings {summary.completed_with_warnings}, failed {summary.failed}, "
             f"skipped {summary.skipped}{retried}, süre {summary.total_time_sec or 0:.1f} sn.",
             f"Ayrıştırma: {summary.parsed} ayrıştırıldı, {summary.parsed_from_cache} önbellekten."]
    if cancelled:
        lines.append(f"İptal edildi: {max(0, summary.discovered - handled)} belge işlenmeden kaldı; "
                     "yeniden çalıştırınca kaldığı yerden devam edilir.")
    return lines


def _preflight_error(result, exc, console):
    console(f"Hata: {exc}", True)
    result.exit_code, result.error, result.hint = EXIT_PREFLIGHT, exc.message, exc.hint
    return result


def run(options, events=None, cancel_token=None, console=print_console):
    """Tek çalıştırma. Döner: `RunResult` (çıkış kodu §24)."""
    events = events or BatchEvents()
    run_id = new_run_id()
    started_at = datetime.now().isoformat(timespec="seconds")
    result = RunResult(exit_code=EXIT_OK)
    # Kilit alınana kadar yalnızca konsola log yazılır; çıktı klasörüne dokunulmaz.
    logger = setup_logging(level="INFO", run_id=run_id, console=options.console_logging)
    try:
        config = merge_cli(load_config(options.config), options)
        if not config.input_dir:
            raise PreflightError("Giriş yolu verilmedi",
                                 "process_papers.py <klasör|pdf> veya --input ya da config.yaml içinde input_dir kullanın")
        logger = setup_logging(level=config.logging.level, run_id=run_id, console=options.console_logging)
        if options.prompt is not None and options.prompt_file is not None:
            logger.warning("--prompt ve --prompt-file birlikte verildi; --prompt önceliklidir (§10.1).")
        prompt = resolve_prompt(options, config)
        input_path = normalize(config.input_dir)
        output_dir = normalize(config.output_dir) if config.output_dir else default_output_dir(input_path)
        result.output_dir = output_dir
        checks = run_preflight(config, input_path, output_dir)
        ocr_check, ocr_settings = check_ocr(config)
        checks.append(ocr_check)
        backend = create_model_backend(config, logger)
        model_checks, models = check_models(config, backend)
        checks.extend(model_checks)
        checks.append(check_gpu())
        for optional_check in (check_xlsx(config), check_collection_output(options.collection_output, input_path)):
            if optional_check is not None:
                checks.append(optional_check)
        result.checks = checks
        events.on_checks(checks)
        _log_checks(logger, checks)
        raise_on_errors(checks)
    except PreflightError as exc:
        return _preflight_error(result, exc, console)

    if options.plan_only:
        return _run_plan_only(result, prompt, config, input_path, output_dir, backend, models, logger, options.force,
                              console)

    output_dir.mkdir(parents=True, exist_ok=True)
    lock = OutputLock(output_dir, run_id)
    try:
        lock.acquire()
    except PreflightError as exc:
        return _preflight_error(result, exc, console)
    token = cancel_token or CancelToken()
    previous_handler = _install_interrupt_handler(token, logger)
    try:
        state = StateManager(output_dir)
        state.load()
        run_id = unique_run_id(run_id, output_dir, state.state.runs)
        log_path = add_file_handler(output_dir, run_id, config.logging.level)
        result.log_path = log_path
        logger.info("Çalıştırma %s başladı. Giriş: %s, çıktı: %s", run_id, input_path, output_dir)
        prompt_label = ("boş prompt, varsayılan kullanıldı" if prompt.empty_prompt else
                        "varsayılan (tam dönüşüm)" if prompt.is_default else "kullanıcı promptu")
        logger.info("Prompt: %s (kaynak: %s, sha256: %s)", prompt_label, prompt.source, prompt.sha256[:12])
        logger.debug("Etkin yapılandırma: %s", config.model_dump_json())
        for check in checks:
            logger.debug("Kontrol [%s] %s: %s", check.name, "ok" if check.ok else check.severity, check.message)
        if lock.stale_info:
            logger.warning("Önceki çalıştırma kilidi temizlemeden sonlanmış (pid %s, run %s); kilit devralındı.",
                           lock.stale_info.get("pid"), lock.stale_info.get("run_id"))
        removed = cleanup_temp_files(output_dir)
        if removed:
            logger.warning("Önceki kesintiden kalan %d geçici dosya silindi.", len(removed))

        recovered = state.recover_interrupted()
        if recovered:
            logger.warning("Yarıda kalmış %d belge yeniden pending yapıldı.", len(recovered))

        discovery = discover(input_path, config.recursive, config.include)
        summary = RunSummary(run_id=run_id, started_at=started_at, input_path=str(input_path),
                             output_path=str(output_dir), recovered_interrupted=len(recovered))
        result.summary = summary
        sync_with_state(discovery, state, summary, logger)
        if not discovery.documents:
            logger.warning("İşlenecek PDF bulunamadı: %s", input_path)
        discovery_message = (f"Keşif: {summary.discovered} PDF (yeni {summary.new}, değişen {summary.changed}, "
                             f"değişmeyen {summary.unchanged}, okunamayan {summary.discovery_failed}), "
                             f"filtre dışı {summary.excluded_by_filter}.")
        logger.info(discovery_message)
        console(discovery_message, False)

        for role, info in models.items():
            if info is not None:
                logger.info("Model (%s): %s", role, info.reference)
        context = _plan_context(config, input_path, len(discovery.documents))
        try:
            plan_result, plan_hash, text_client, content_hash = make_plan(
                prompt, context, config, backend, models, logger, cache_root=output_dir / "_cache", force=options.force)
        except ModelUnavailable as exc:
            raise PreflightError(f"Plan oluşturulamadı: {exc}") from exc
        _log_plan(logger, plan_result, plan_hash)
        if plan_result.plan.scope == "collection" and prompt.is_default:
            raise PreflightError("Koleksiyon kapsamı bir prompt gerektirir (varsayılan prompt tam dönüşümdür).",
                                 "--prompt ile karşılaştırma isteğini verin veya --scope document kullanın")
        summary.plan_hash = plan_hash
        targeted = filter_targets(discovery.documents, plan_result.plan, context)
        if len(targeted) != len(discovery.documents):
            logger.info("Plan hedef filtresi (%s): %d/%d PDF", ", ".join(plan_result.plan.targets.include),
                        len(targeted), len(discovery.documents))
            discovery.documents = targeted
        if text_client is not None:
            summary.text_llm_calls = text_client.calls
        vision = None
        if models.get("vision") is not None:
            vision = VisionSetup(VisionClient(backend, models["vision"].name, config.models.max_output_tokens, logger,
                                              log_content=config.logging.log_model_content), models["vision"])
        processor = BatchProcessor(config, state, CacheManager(output_dir), output_dir, run_id, logger, prompt,
                                   force=options.force, events=events, cancel_token=token,
                                   ocr_settings=ocr_settings, vision=vision, plan=plan_result.plan, plan_hash=plan_hash,
                                   content_hash=content_hash,
                                   text=TextSetup(text_client, models["text"]) if text_client is not None else None)
        stopped = None
        try:
            processor.run(discovery, summary)
        except Cancelled:
            result.cancelled = True
        except FatalBatchError as exc:
            # §28: sistem geneli hata (model servisi kapandı); durum kaydedildi, yeniden çalıştırınca devam edilir.
            stopped = exc
            logger.error("Batch durduruldu [%s]: %s", exc.stage.value, exc.message)
        if processor.collection and not result.cancelled and stopped is None:
            try:
                result.collection_path, result.collection_unchanged = processor.synthesize_collection(
                    discovery, summary, name=options.collection_name, output_path=options.collection_output,
                    prompt_text=prompt.text)
                if result.collection_path is None:
                    result.collection_error = "başarıyla çıkarılmış belge yok"
            except ModelUnavailable as exc:
                stopped = FatalBatchError(ErrorStage.llm, str(exc), "model_unavailable")
                logger.error("Batch durduruldu [llm]: %s", exc)
            except DocumentError as exc:
                result.collection_error = exc.message
            except OSError as exc:
                result.collection_error = f"Koleksiyon yazılamadı: {exc}"
            if result.collection_error:
                logger.error("Koleksiyon çıktısı üretilemedi: %s", result.collection_error)
            if result.collection_path is not None:
                events.on_collection_output(result.collection_path)
        summary.failed += summary.discovery_failed
        summary.finished_at = datetime.now().isoformat(timespec="seconds")
        state.record_run(summary)
        processor.write_summary()  # §22.1: çalıştırma sonunda da (keşif hataları ve atlanan belgeler dahil)
        result.documents = _document_results(state, discovery)
        for line in summary_lines(summary, result.cancelled):
            logger.info(line)
            console(line, False)
        if stopped is not None:
            result.stopped = stopped.message
            console(f"Batch durduruldu: {stopped.message}. Sorunu giderip yeniden çalıştırınca kaldığı yerden devam "
                    "edilir.", True)
        if result.collection_path is not None:
            note = " (değişmedi, sentez atlandı)" if result.collection_unchanged else ""
            console(f"Koleksiyon: {result.collection_path}{note}", False)
        if result.collection_error:
            console(f"Koleksiyon çıktısı üretilemedi: {result.collection_error}", True)
        console(f"Çıktı: {output_dir}", False)
        console(f"Log: {log_path}", False)
        if result.cancelled:
            result.exit_code = EXIT_CANCELLED
        elif stopped is not None or summary.failed or result.collection_error:
            result.exit_code = EXIT_DOC_FAILED
        return result
    except PreflightError as exc:
        logger.error(str(exc))
        return _preflight_error(result, exc, console)
    finally:
        for signum, handler in (previous_handler or {}).items():
            signal.signal(signum, handler)
        lock.release()


def _document_results(state, discovery):
    documents = []
    for pdf in discovery.documents:
        record = state.get(pdf.relative_path)
        if record is None:
            continue
        documents.append(DocumentResult(pdf.relative_path, record.status.value, record.output_path,
                                        record.error_stage.value if record.error_stage else None, record.error,
                                        len(record.warnings)))
    return documents


def _run_plan_only(result, prompt, config, input_path, output_dir, backend, models, logger, force, console):
    """§10.2: plan yazdırılır, PDF açılmaz; kilit alınmaz, çıktı klasörü oluşturulmaz, plan önbelleğe yazılmaz."""
    discovery = discover(input_path, config.recursive, config.include)
    context = _plan_context(config, input_path, len(discovery.documents))
    try:
        plan_result, plan_hash, _, _ = make_plan(prompt, context, config, backend, models, logger,
                                                 cache_root=output_dir / "_cache", write_cache=False, force=force)
    except ModelUnavailable as exc:
        console(f"Hata: {exc}", True)
        result.exit_code, result.error = EXIT_PREFLIGHT, str(exc)
        return result
    _log_plan(logger, plan_result, plan_hash)
    documents = filter_targets(discovery.documents, plan_result.plan, context)
    result.plan_lines = describe_plan(plan_result, plan_hash, documents) + ["PDF işlenmedi (--plan-only)."]
    for line in result.plan_lines:
        console(line, False)
    return result
