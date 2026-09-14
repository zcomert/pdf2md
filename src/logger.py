import logging
import sys
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

LOGGER_NAME = "pdf2md"
_FORMAT = "%(asctime)s %(levelname)s %(message)s"

class TqdmHandler(logging.Handler):
    """Konsol mesajlarını ilerleme çubuğunu bozmadan yazar."""
    def emit(self, record):
        try:
            tqdm.write(self.format(record), file=sys.stderr)
        except Exception:
            self.handleError(record)

def new_run_id(now=None):
    return (now or datetime.now()).strftime("%Y%m%d-%H%M%S")

def log_file_name(run_id):
    """`20260913-143012` → `process_2026-09-13_143012.log`; çakışma eki korunur (`-2` → `..._143012-2.log`)."""
    base, suffix = run_id[:15], run_id[15:]
    stamp = datetime.strptime(base, "%Y%m%d-%H%M%S")
    return f"process_{stamp:%Y-%m-%d_%H%M%S}{suffix}.log"


def unique_run_id(base_run_id, output_dir, existing_run_ids=()):
    """Aynı saniyede başlayan çalıştırmaların log dosyası ve state kaydı birbirini ezmesin."""
    logs = Path(output_dir) / "logs"
    candidate, counter = base_run_id, 1
    while candidate in existing_run_ids or (logs / log_file_name(candidate)).exists():
        counter += 1
        candidate = f"{base_run_id}-{counter}"
    return candidate

def setup_logging(output_dir=None, level="INFO", run_id=None, console=True):
    """Konsol loglamasını kurar. `output_dir` verilirse dosya handler'ı da eklenir;
    çıktı klasörüne kilit alındıktan sonra yazılması için normalde `add_file_handler` ayrıca çağrılır."""
    logger = logging.getLogger(LOGGER_NAME)
    close_logging()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if console and sys.stderr is not None:  # GUI (pythonw) altında konsol akışı yoktur
        handler = TqdmHandler()
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
    if output_dir is not None:
        add_file_handler(output_dir, run_id or new_run_id(), level)
    return logger

def add_file_handler(output_dir, run_id, level="INFO"):
    logger = logging.getLogger(LOGGER_NAME)
    folder = Path(output_dir) / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(folder / log_file_name(run_id), encoding="utf-8")
    handler.setLevel(getattr(logging, level.upper()))
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
    return handler.baseFilename

def close_logging():
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
