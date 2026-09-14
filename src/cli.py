import argparse
import signal
import sys
import threading
from datetime import datetime

from tqdm import tqdm

from .atomic_io import cleanup_temp_files
from .batch_processor import BatchEvents, BatchProcessor, Cancelled, CancelToken
from .cache_manager import CacheManager
from .config import load_config, merge_cli
from .default_prompt import resolve_prompt
from .errors import FatalBatchError, PreflightError
from .logger import add_file_handler, new_run_id, setup_logging, unique_run_id
from .paths import default_output_dir, normalize
from .pdf_discovery import discover, sync_with_state
from .llm_client import TextClient
from .model_clients import ModelUnavailable
from .ollama_backend import OllamaBackend
from .prompt_planner import (PlanContext, compute_plan_hash, create_plan, describe_plan, filter_targets,
                             summary_signature)
from .preflight import check_gpu, check_models, check_ocr, check_xlsx, raise_on_errors, run_preflight
from .vision_client import VisionClient
from .schemas import RunSummary
from .state_manager import OutputLock, StateManager

EXIT_OK, EXIT_DOC_FAILED, EXIT_PREFLIGHT = 0, 1, 2
EXIT_CANCELLED = 130  # §24 dışı: Ctrl+C ile güvenli iptal (kabuk geleneği 128 + SIGINT)

def build_parser():
    p = argparse.ArgumentParser(
        prog="process_papers.py",
        description="Yerel akademik PDF işleme, Markdown dönüştürme ve bilgi çıkarım sistemi")
    p.add_argument("input_positional", nargs="?", metavar="INPUT", help="Klasör veya tek PDF (--input ile aynı)")
    p.add_argument("--input", dest="input_dir", help="Klasör veya tek PDF")
    p.add_argument("--output", dest="output_dir", help="Çıktı klasörü (varsayılan: <giriş>_output)")
    p.add_argument("--config", help="Yapılandırma dosyası (varsayılan: ./config.yaml varsa)")
    p.add_argument("--prompt", help="Prompt metni")
    p.add_argument("--prompt-file", help="Prompt dosyası")
    p.add_argument("--scope", choices=["auto", "document", "collection"], help="İşlem kapsamı (varsayılan: auto)")
    p.add_argument("--include", action="append", metavar="GLOB", help="Glob filtresi, tekrarlanabilir")
    p.add_argument("--collection-name", help="Koleksiyon çıktı adı")
    p.add_argument("--collection-output", help="Koleksiyon çıktı tam yolu")
    p.add_argument("--mode", choices=["fast", "balanced", "full"], help="Çalışma modu (varsayılan: balanced)")
    p.add_argument("--recursive", action="store_true", default=None, help="Alt klasörleri tara")
    p.add_argument("--retry-failed", action="store_true", default=None, help="Başarısız belgeleri yeniden dene")
    p.add_argument("--force", action="store_true", help="Önbelleği ve atlama kuralını yok say")
    p.add_argument("--plan-only", action="store_true", help="Planı göster, işleme yapma")
    p.add_argument("--model-vision", help="Görsel model adı (varsayılan: minicpm-v4.5:8b)")
    p.add_argument("--model-text", help="Metin model adı (varsayılan: gemma4:latest)")
    p.add_argument("--dpi", type=int, help="Render DPI, 150-400 (varsayılan: 250)")
    p.add_argument("--cpu-workers", type=int, help="PDF ayrıştırma worker sayısı (varsayılan: 4)")
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Log seviyesi (varsayılan: INFO)")
    return p

def _configure_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

def _print_error(exc):
    print(f"Hata: {exc}", file=sys.stderr)

def _log_checks(logger, results):
    for result in results:
        if result.ok:
            logger.info("Kontrol [%s]: %s", result.name, result.message)
        elif result.severity == "warning":
            hint = f" Öneri: {result.hint}" if result.hint else ""
            logger.warning("Kontrol [%s]: %s.%s", result.name, result.message, hint)

class ConsoleEvents(BatchEvents):
    """Konsolda tqdm ilerleme çubuğu. Konsol TTY değilse (ör. yönlendirilmiş çıktı) çubuk gizlenir."""

    def __init__(self):
        self.bar = None

    def on_run_start(self, total):
        self.bar = tqdm(total=total, unit="pdf", file=sys.stderr, disable=None, dynamic_ncols=True, leave=False)

    def on_document_start(self, relative_path, index, total):
        if self.bar:
            self.bar.set_postfix_str(relative_path[-40:], refresh=True)

    def on_stage(self, relative_path, stage):
        if self.bar:
            self.bar.set_description_str(stage, refresh=True)

    def on_document_end(self, relative_path, status, warnings, output_path, error=None):
        if self.bar:
            self.bar.update(1)

    def on_run_end(self, summary):
        if self.bar:
            self.bar.close()


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


def run_plan_only(prompt, config, input_path, output_dir, backend, models, logger, force):
    """§10.2: plan yazdırılır, PDF açılmaz; kilit alınmaz, çıktı klasörü oluşturulmaz, plan önbelleğe yazılmaz."""
    result = discover(input_path, config.recursive, config.include)
    context = _plan_context(config, input_path, len(result.documents))
    try:
        plan_result, plan_hash, _, _ = make_plan(prompt, context, config, backend, models, logger,
                                              cache_root=output_dir / "_cache", write_cache=False, force=force)
    except ModelUnavailable as exc:
        _print_error(exc)
        return EXIT_PREFLIGHT
    _log_plan(logger, plan_result, plan_hash)
    documents = filter_targets(result.documents, plan_result.plan, context)
    for line in describe_plan(plan_result, plan_hash, documents):
        print(line)
    print("PDF işlenmedi (--plan-only).")
    return EXIT_OK


def _install_interrupt_handler(token, logger):
    """İlk Ctrl+C (veya Windows Ctrl+Break) güvenli iptal ister (belge yarım bırakılmaz), ikincisi hemen keser.
    Kilit `atexit` ve `finally` ile bırakılır."""
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


def main(argv=None, events=None, cancel_token=None):
    _configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input_positional and args.input_dir:
        parser.error("Giriş konumsal argümanla veya --input ile verilebilir, ikisi birlikte kullanılamaz")
    if args.input_positional:
        args.input_dir = args.input_positional
    run_id = new_run_id()
    started_at = datetime.now().isoformat(timespec="seconds")
    # Kilit alınana kadar yalnızca konsola log yazılır; çıktı klasörüne dokunulmaz.
    logger = setup_logging(level="INFO", run_id=run_id)
    try:
        config = merge_cli(load_config(args.config), args)
        if not config.input_dir:
            raise PreflightError("Giriş yolu verilmedi",
                                 "process_papers.py <klasör|pdf> veya --input ya da config.yaml içinde input_dir kullanın")
        logger = setup_logging(level=config.logging.level, run_id=run_id)
        if args.prompt is not None and args.prompt_file is not None:
            logger.warning("--prompt ve --prompt-file birlikte verildi; --prompt önceliklidir (§10.1).")
        prompt = resolve_prompt(args, config)
        input_path = normalize(config.input_dir)
        output_dir = normalize(config.output_dir) if config.output_dir else default_output_dir(input_path)
        checks = run_preflight(config, input_path, output_dir)
        ocr_check, ocr_settings = check_ocr(config)
        checks.append(ocr_check)
        backend = create_model_backend(config, logger)
        model_checks, models = check_models(config, backend)
        checks.extend(model_checks)
        checks.append(check_gpu())
        xlsx_check = check_xlsx(config)
        if xlsx_check is not None:
            checks.append(xlsx_check)
        _log_checks(logger, checks)
        raise_on_errors(checks)
    except PreflightError as exc:
        _print_error(exc)
        return EXIT_PREFLIGHT

    if args.plan_only:
        return run_plan_only(prompt, config, input_path, output_dir, backend, models, logger, args.force)

    output_dir.mkdir(parents=True, exist_ok=True)
    lock = OutputLock(output_dir, run_id)
    try:
        lock.acquire()
    except PreflightError as exc:
        _print_error(exc)
        return EXIT_PREFLIGHT
    token = cancel_token or CancelToken()
    previous_handler = _install_interrupt_handler(token, logger)
    try:
        state = StateManager(output_dir)
        state.load()
        run_id = unique_run_id(run_id, output_dir, state.state.runs)
        log_path = add_file_handler(output_dir, run_id, config.logging.level)
        logger.info("Çalıştırma %s başladı. Giriş: %s, çıktı: %s", run_id, input_path, output_dir)
        prompt_label = ("boş prompt, varsayılan kullanıldı" if prompt.empty_prompt else
                        "varsayılan (tam dönüşüm)" if prompt.is_default else "kullanıcı promptu")
        logger.info("Prompt: %s (kaynak: %s, sha256: %s)", prompt_label, prompt.source, prompt.sha256[:12])
        logger.debug("Etkin yapılandırma: %s", config.model_dump_json())
        for result in checks:
            logger.debug("Kontrol [%s] %s: %s", result.name, "ok" if result.ok else result.severity, result.message)
        if lock.stale_info:
            logger.warning("Önceki çalıştırma kilidi temizlemeden sonlanmış (pid %s, run %s); kilit devralındı.",
                           lock.stale_info.get("pid"), lock.stale_info.get("run_id"))
        removed = cleanup_temp_files(output_dir)
        if removed:
            logger.warning("Önceki kesintiden kalan %d geçici dosya silindi.", len(removed))

        recovered = state.recover_interrupted()
        if recovered:
            logger.warning("Yarıda kalmış %d belge yeniden pending yapıldı.", len(recovered))

        result = discover(input_path, config.recursive, config.include)
        summary = RunSummary(run_id=run_id, started_at=started_at, input_path=str(input_path),
                             output_path=str(output_dir), recovered_interrupted=len(recovered))
        sync_with_state(result, state, summary, logger)
        if not result.documents:
            logger.warning("İşlenecek PDF bulunamadı: %s", input_path)
        discovery_message = (f"Keşif: {summary.discovered} PDF (yeni {summary.new}, değişen {summary.changed}, "
                             f"değişmeyen {summary.unchanged}, okunamayan {summary.discovery_failed}), "
                             f"filtre dışı {summary.excluded_by_filter}.")
        logger.info(discovery_message)
        print(discovery_message)

        for role, info in models.items():
            if info is not None:
                logger.info("Model (%s): %s", role, info.reference)
        context = _plan_context(config, input_path, len(result.documents))
        try:
            plan_result, plan_hash, text_client, content_hash = make_plan(prompt, context, config, backend, models,
                                                                          logger,
                                                            cache_root=output_dir / "_cache", force=args.force)
        except ModelUnavailable as exc:
            raise PreflightError(f"Plan oluşturulamadı: {exc}") from exc
        _log_plan(logger, plan_result, plan_hash)
        if plan_result.plan.scope == "collection":
            raise PreflightError("Koleksiyon kapsamı henüz desteklenmiyor (Faz 12).",
                                 "Her PDF için ayrı cevap üretmek üzere --scope document ile çalıştırın")
        summary.plan_hash = plan_hash
        targeted = filter_targets(result.documents, plan_result.plan, context)
        if len(targeted) != len(result.documents):
            logger.info("Plan hedef filtresi (%s): %d/%d PDF", ", ".join(plan_result.plan.targets.include),
                        len(targeted), len(result.documents))
            result.documents = targeted
        if text_client is not None:
            summary.text_llm_calls = text_client.calls
        vision = None
        if models.get("vision") is not None:
            vision = VisionSetup(VisionClient(backend, models["vision"].name, config.models.max_output_tokens, logger,
                                              log_content=config.logging.log_model_content), models["vision"])
        processor = BatchProcessor(config, state, CacheManager(output_dir), output_dir, run_id, logger, prompt,
                                   force=args.force, events=events or ConsoleEvents(), cancel_token=token,
                                   ocr_settings=ocr_settings, vision=vision, plan=plan_result.plan, plan_hash=plan_hash,
                                   content_hash=content_hash,
                                   text=TextSetup(text_client, models["text"]) if text_client is not None else None)
        cancelled = False
        stopped = None
        try:
            processor.run(result, summary)
        except Cancelled:
            cancelled = True
        except FatalBatchError as exc:
            # §28: sistem geneli hata (model servisi kapandı); durum kaydedildi, yeniden çalıştırınca devam edilir.
            stopped = exc
            logger.error("Batch durduruldu [%s]: %s", exc.stage.value, exc.message)
        summary.failed += summary.discovery_failed
        summary.finished_at = datetime.now().isoformat(timespec="seconds")
        state.record_run(summary)
        processor.write_summary()  # §22.1: çalıştırma sonunda da (keşif hataları ve atlanan belgeler dahil)
        for line in summary_lines(summary, cancelled):
            logger.info(line)
            print(line)
        if stopped is not None:
            print(f"Batch durduruldu: {stopped.message}. Sorunu giderip yeniden çalıştırınca kaldığı yerden devam edilir.",
                  file=sys.stderr)
        print(f"Çıktı: {output_dir}")
        print(f"Log: {log_path}")
        if cancelled:
            return EXIT_CANCELLED
        if stopped is not None:
            return EXIT_DOC_FAILED
        return EXIT_DOC_FAILED if summary.failed else EXIT_OK
    except PreflightError as exc:
        logger.error(str(exc))
        _print_error(exc)
        return EXIT_PREFLIGHT
    finally:
        for signum, handler in (previous_handler or {}).items():
            signal.signal(signum, handler)
        lock.release()


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
