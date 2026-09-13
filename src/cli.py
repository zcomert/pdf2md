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
from .errors import PreflightError
from .logger import add_file_handler, new_run_id, setup_logging, unique_run_id
from .paths import default_output_dir, normalize
from .pdf_discovery import discover, sync_with_state
from .preflight import raise_on_errors, run_preflight
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


def _install_interrupt_handler(token, logger):
    """İlk Ctrl+C güvenli iptal ister (belge yarım bırakılmaz), ikincisi hemen keser."""
    if threading.current_thread() is not threading.main_thread():
        return None
    previous = signal.getsignal(signal.SIGINT)

    def handler(signum, frame):
        if token.cancelled:
            raise KeyboardInterrupt
        token.cancel()
        logger.warning("İptal istendi; güvenli bir noktada durulacak. Hemen çıkmak için tekrar Ctrl+C.")

    signal.signal(signal.SIGINT, handler)
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
        if not prompt.is_default:
            raise PreflightError("Prompt tabanlı çıkarım henüz desteklenmiyor (Faz 08–09).",
                                 "Tam Markdown dönüşümü için prompt vermeden çalıştırın")
        input_path = normalize(config.input_dir)
        output_dir = normalize(config.output_dir) if config.output_dir else default_output_dir(input_path)
        checks = run_preflight(config, input_path, output_dir)
        _log_checks(logger, checks)
        raise_on_errors(checks)
    except PreflightError as exc:
        _print_error(exc)
        return EXIT_PREFLIGHT

    if args.plan_only:
        print(config.model_dump_json(indent=2))
        return EXIT_OK

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
        prompt_label = "boş prompt, varsayılan kullanıldı" if prompt.empty_prompt else "varsayılan (tam dönüşüm)"
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

        processor = BatchProcessor(config, state, CacheManager(output_dir), output_dir, run_id, logger, prompt,
                                   force=args.force, events=events or ConsoleEvents(), cancel_token=token)
        cancelled = False
        try:
            processor.run(result, summary)
        except Cancelled:
            cancelled = True
        summary.failed += summary.discovery_failed
        summary.finished_at = datetime.now().isoformat(timespec="seconds")
        state.record_run(summary)
        for line in summary_lines(summary, cancelled):
            logger.info(line)
            print(line)
        print(f"Çıktı: {output_dir}")
        print(f"Log: {log_path}")
        if cancelled:
            return EXIT_CANCELLED
        return EXIT_DOC_FAILED if summary.failed else EXIT_OK
    except PreflightError as exc:
        logger.error(str(exc))
        _print_error(exc)
        return EXIT_PREFLIGHT
    finally:
        if previous_handler is not None:
            signal.signal(signal.SIGINT, previous_handler)
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
