from pathlib import Path
import logging
from datetime import datetime

def setup_logging(output_dir, level="INFO", run_id=None):
    logger = logging.getLogger("pdf2md")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper()))
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(formatter)
    logger.addHandler(console)
    if output_dir:
        folder = Path(output_dir) / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        handler = logging.FileHandler(folder / f"process_{stamp}.log", encoding="utf-8")
        handler.setLevel(getattr(logging, level.upper()))
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

