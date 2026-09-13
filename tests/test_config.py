import pytest
from pydantic import ValidationError
from src.cli import build_parser
from src.config import AppConfig, load_config, merge_cli
from src.errors import PreflightError

def write_config(path, text):
    path.write_text(text, encoding="utf-8")
    return path

def test_default_config_is_valid(valid_config):
    assert valid_config.mode == "balanced"
    assert valid_config.pdf.render_dpi == 250

def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"unknown": True})

def test_dpi_range_rejected():
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"pdf": {"render_dpi": 500}})

def test_cli_overrides_config_file(tmp_path):
    cfg = write_config(tmp_path / "c.yaml", "mode: full\npdf:\n  render_dpi: 300\n")
    args = build_parser().parse_args(["papers", "--mode", "fast"])
    config = merge_cli(load_config(cfg), args)
    assert config.mode == "fast"
    assert config.pdf.render_dpi == 300

def test_cli_overrides_nested_fields():
    args = build_parser().parse_args([
        "--dpi", "200", "--model-text", "qwen3:8b", "--model-vision", "v:1",
        "--log-level", "DEBUG", "--cpu-workers", "2", "--retry-failed", "--recursive",
        "--include", "a/*.pdf"])
    config = merge_cli(AppConfig(), args)
    assert config.pdf.render_dpi == 200
    assert config.models.text == "qwen3:8b"
    assert config.models.vision == "v:1"
    assert config.logging.level == "DEBUG"
    assert config.processing.cpu_workers == 2
    assert config.processing.retry_failed is True
    assert config.recursive is True
    assert config.include == ["a/*.pdf"]

def test_unset_cli_flags_keep_config_values(tmp_path):
    cfg = write_config(tmp_path / "c.yaml", "recursive: true\nprocessing:\n  retry_failed: true\n")
    config = merge_cli(load_config(cfg), build_parser().parse_args(["papers"]))
    assert config.recursive is True
    assert config.processing.retry_failed is True

def test_invalid_cli_value_is_validated():
    args = build_parser().parse_args(["--dpi", "999"])
    with pytest.raises(PreflightError, match="pdf.render_dpi"):
        merge_cli(AppConfig(), args)

def test_explicit_missing_config_rejected(tmp_path):
    with pytest.raises(PreflightError, match="bulunamadı"):
        load_config(tmp_path / "nope.yaml")

def test_default_config_file_is_optional(isolated_cwd):
    assert load_config() == AppConfig()

def test_default_config_file_is_used(isolated_cwd):
    write_config(isolated_cwd / "config.yaml", "mode: full\n")
    assert load_config().mode == "full"

@pytest.mark.parametrize("text", ["- a\n- b\n", "mode: [unclosed\n", "pdf:\n  unknown: 1\n"])
def test_invalid_config_file_rejected(tmp_path, text):
    with pytest.raises(PreflightError):
        load_config(write_config(tmp_path / "c.yaml", text))

def test_example_config_is_valid():
    from pathlib import Path
    example = Path(__file__).resolve().parents[1] / "config.example.yaml"
    assert isinstance(load_config(example), AppConfig)
