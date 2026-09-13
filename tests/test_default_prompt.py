import hashlib
from types import SimpleNamespace

import pytest

from src.config import AppConfig
from src.default_prompt import DEFAULT_PROMPT, resolve_prompt
from src.errors import PreflightError


def args(prompt=None, prompt_file=None):
    return SimpleNamespace(prompt=prompt, prompt_file=prompt_file)


def test_no_prompt_uses_default_without_warning():
    resolved = resolve_prompt(args(), AppConfig())
    assert resolved.is_default and resolved.source == "default" and resolved.run_warnings == []
    assert resolved.sha256 == hashlib.sha256(DEFAULT_PROMPT.encode()).hexdigest()


@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_empty_prompt_falls_back_with_warning(value):
    resolved = resolve_prompt(args(prompt=value), AppConfig())
    assert resolved.is_default and resolved.empty_prompt
    assert resolved.run_warnings and resolved.run_warnings[0].startswith("empty_prompt")
    assert resolved.sha256 != resolve_prompt(args(), AppConfig()).sha256


def test_priority_order(tmp_path):
    cli_file = tmp_path / "cli.md"
    cli_file.write_text("dosyadan", encoding="utf-8")
    config_file = tmp_path / "config.md"
    config_file.write_text("config dosyası", encoding="utf-8")
    config = AppConfig(prompt="config prompt", prompt_file=str(config_file))
    assert resolve_prompt(args(prompt="cli", prompt_file=str(cli_file)), config).text == "cli"
    assert resolve_prompt(args(prompt_file=str(cli_file)), config).text == "dosyadan"
    assert resolve_prompt(args(), config).source == "config"
    assert resolve_prompt(args(), AppConfig(prompt_file=str(config_file))).text == "config dosyası"


def test_custom_prompt_is_not_default():
    resolved = resolve_prompt(args(prompt="Veri setlerini çıkar"), AppConfig())
    assert not resolved.is_default and not resolved.empty_prompt


def test_missing_prompt_file_is_preflight_error(tmp_path):
    with pytest.raises(PreflightError, match="okunamadı"):
        resolve_prompt(args(prompt_file=str(tmp_path / "yok.md")), AppConfig())
