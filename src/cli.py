import argparse
import sys
from datetime import datetime
from .config import load_config, merge_cli
from .logger import setup_logging

EXIT_OK, EXIT_DOC_FAILED, EXIT_PREFLIGHT = 0, 1, 2

def build_parser():
    p = argparse.ArgumentParser(description="Yerel akademik PDF işleme sistemi")
    p.add_argument("input_positional", nargs="?")
    p.add_argument("--input", dest="input_dir")
    p.add_argument("--output", dest="output_dir")
    p.add_argument("--config")
    p.add_argument("--mode", choices=["fast", "balanced", "full"])
    p.add_argument("--scope", choices=["auto", "document", "collection"])
    p.add_argument("--recursive", action="store_true", default=None)
    p.add_argument("--retry-failed", action="store_true", default=None)
    p.add_argument("--force", action="store_true", default=None)
    p.add_argument("--prompt")
    p.add_argument("--prompt-file")
    p.add_argument("--include", action="append")
    p.add_argument("--model-vision")
    p.add_argument("--model-text")
    p.add_argument("--dpi", type=int)
    p.add_argument("--workers", type=int)
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    p.add_argument("--plan-only", action="store_true")
    return p

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input_positional and args.input_dir:
        parser.error("Giriş konumsal argümanla veya --input ile verilebilir, ikisi birlikte kullanılamaz")
    try:
        if args.input_positional: args.input_dir = args.input_positional
        config = merge_cli(load_config(args.config), args)
        logger = setup_logging(config.output_dir, config.logging.level,
                               datetime.now().strftime("%Y%m%d-%H%M%S"))
        logger.debug("Etkin yapılandırma: %s", config.model_dump_json())
        if args.prompt and args.prompt_file:
            logger.warning("--prompt ve --prompt-file birlikte verildi; prompt dosyası önceliklidir.")
        if args.plan_only: print(config.model_dump_json(indent=2))
        return EXIT_OK
    except Exception as exc:
        print(f"Yapılandırma hatası: {exc}", file=sys.stderr)
        return EXIT_PREFLIGHT

