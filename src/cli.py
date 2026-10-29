"""Komut satırı arayüzü (§24): argümanları `RunOptions`'a çevirir ve `runner.run` çağırır."""
import argparse
import sys

from tqdm import tqdm

from .batch_processor import BatchEvents
from .runner import (EXIT_CANCELLED, EXIT_DOC_FAILED, EXIT_OK, EXIT_PREFLIGHT, RunOptions, TextSetup,  # noqa: F401
                     VisionSetup, create_model_backend, run, summary_lines)


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


def options_from_args(args):
    values = {name: getattr(args, name) for name in RunOptions.__dataclass_fields__ if hasattr(args, name)}
    return RunOptions(**values)


def main(argv=None, events=None, cancel_token=None):
    _configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input_positional and args.input_dir:
        parser.error("Giriş konumsal argümanla veya --input ile verilebilir, ikisi birlikte kullanılamaz")
    if args.input_positional:
        args.input_dir = args.input_positional
    return run(options_from_args(args), events=events or ConsoleEvents(), cancel_token=cancel_token).exit_code


def cli_entry():
    """`pdf2md` konsol betiği ve `process_papers.py` için ortak giriş noktası (§24, §38 kriter 19)."""
    import signal

    from .dependencies import bootstrap_check

    exit_code = bootstrap_check()
    if exit_code is not None:
        return exit_code
    if hasattr(signal, "SIGBREAK"):
        # Windows Ctrl+Break varsayılan olarak süreci anında sonlandırır; finally blokları (kilit, state) çalışsın.
        def _interrupt(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGBREAK, _interrupt)
    try:
        return main()
    except KeyboardInterrupt:
        print("İptal edildi.", file=sys.stderr)
        return 130
