import logging
from datetime import datetime
from src.logger import TqdmHandler, add_file_handler, log_file_name, new_run_id, setup_logging

def test_run_id_format():
    assert new_run_id(datetime(2026, 9, 13, 14, 30, 12)) == "20260913-143012"

def test_log_file_name_matches_run_id():
    assert log_file_name("20260913-143012") == "process_2026-09-13_143012.log"

def test_console_only_setup_writes_no_files(tmp_path):
    logger = setup_logging(level="DEBUG")
    assert [type(h) for h in logger.handlers] == [TqdmHandler]
    assert logger.propagate is False
    assert list(tmp_path.iterdir()) == []

def test_repeated_setup_does_not_duplicate_handlers():
    setup_logging()
    logger = setup_logging()
    assert len(logger.handlers) == 1

def test_file_handler_writes_utf8(tmp_path):
    logger = setup_logging(level="DEBUG")
    path = add_file_handler(tmp_path, "20260913-143012", "DEBUG")
    logger.debug("Türkçe karakterler: ığüşöçİĞÜŞÖÇ")
    for handler in logger.handlers:
        handler.flush()
    assert path.endswith("process_2026-09-13_143012.log")
    assert "ığüşöçİĞÜŞÖÇ" in (tmp_path / "logs" / "process_2026-09-13_143012.log").read_text(encoding="utf-8")

def test_file_handler_respects_level(tmp_path):
    logger = setup_logging()
    add_file_handler(tmp_path, "20260913-143012", "WARNING")
    file_handler = [h for h in logger.handlers if isinstance(h, logging.FileHandler)][0]
    assert file_handler.level == logging.WARNING
