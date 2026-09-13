import pytest
from pydantic import ValidationError
from src.config import AppConfig

def test_default_config_is_valid(valid_config):
    assert valid_config.mode == "balanced"
    assert valid_config.pdf.render_dpi == 250

def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"unknown": True})

def test_dpi_range_rejected():
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"pdf": {"render_dpi": 500}})

