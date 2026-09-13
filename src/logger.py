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
    stamp = datetime.strptime(run_id, "%Y%m%d-%H%M%S")
    return f"process_{stamp:%Y-%m-%d_%H%M%S}.log"

def setup_logging(output_dir=None, level="INFO", run_id=None):
    """Konsol loglamasını kurar. `output_dir` verilirse dosya handler'ı da eklenir;
    çıktı klasörüne kilit alındıktan sonra yazılması için normalde `add_file_handler` ayrıca çağrılır."""
    logger = logging.getLogger(LOGGER_NAME)
    close_logging()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    console = TqdmHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(console)
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
