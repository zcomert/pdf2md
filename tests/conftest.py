import pytest

@pytest.fixture
def valid_config():
    from src.config import AppConfig
    return AppConfig()

@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    """Depo kökündeki olası config.yaml testleri etkilemesin."""
    monkeypatch.chdir(tmp_path)
    return tmp_path

@pytest.fixture(autouse=True)
def _close_log_handlers():
    yield
    from src.logger import close_logging
    close_logging()
