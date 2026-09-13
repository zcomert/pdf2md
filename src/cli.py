import argparse
import sys
from .config import load_config, merge_cli
from .errors import PreflightError
from .logger import new_run_id, setup_logging

EXIT_OK, EXIT_DOC_FAILED, EXIT_PREFLIGHT = 0, 1, 2

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

def main(argv=None):
    _configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input_positional and args.input_dir:
        parser.error("Giriş konumsal argümanla veya --input ile verilebilir, ikisi birlikte kullanılamaz")
    if args.input_positional:
        args.input_dir = args.input_positional
    run_id = new_run_id()
    # Dosya log'u çıktı klasörüne kilit alındıktan sonra eklenir (Faz 02).
    logger = setup_logging(level="INFO", run_id=run_id)
    try:
        config = merge_cli(load_config(args.config), args)
        if not config.input_dir:
            raise PreflightError("Giriş yolu verilmedi",
                                 "process_papers.py <klasör|pdf> veya --input ya da config.yaml içinde input_dir kullanın")
    except PreflightError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return EXIT_PREFLIGHT
    logger = setup_logging(level=config.logging.level, run_id=run_id)
    logger.debug("Etkin yapılandırma: %s", config.model_dump_json())
    if args.prompt is not None and args.prompt_file is not None:
        logger.warning("--prompt ve --prompt-file birlikte verildi; --prompt önceliklidir (§10.1).")
    if args.plan_only:
        print(config.model_dump_json(indent=2))
    return EXIT_OK
