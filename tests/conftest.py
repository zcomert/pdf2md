import pytest

@pytest.fixture
def valid_config():
    from src.config import AppConfig
    return AppConfig()

