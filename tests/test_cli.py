import pytest
from src.cli import EXIT_OK, EXIT_PREFLIGHT, build_parser, main

SECTION_24_OPTIONS = [
    "--input", "--output", "--config", "--prompt", "--prompt-file", "--scope", "--include",
    "--collection-name", "--collection-output", "--mode", "--recursive", "--retry-failed",
    "--force", "--plan-only", "--model-vision", "--model-text", "--dpi", "--cpu-workers",
    "--log-level",
]

def test_positional_and_option_input_rejected(isolated_cwd):
    with pytest.raises(SystemExit):
        main(["papers", "--input", "other"])

def test_include_is_repeatable():
    args = build_parser().parse_args(["--include", "a.pdf", "--include", "b.pdf"])
    assert args.include == ["a.pdf", "b.pdf"]

def test_help_lists_all_section_24_options():
    help_text = build_parser().format_help()
    for option in SECTION_24_OPTIONS:
        assert option in help_text, option

def test_missing_input_returns_preflight_exit(isolated_cwd, capsys):
    assert main([]) == EXIT_PREFLIGHT
    assert "Giriş yolu verilmedi" in capsys.readouterr().err

def test_input_from_config_file_is_accepted(isolated_cwd):
    (isolated_cwd / "papers").mkdir()
    (isolated_cwd / "config.yaml").write_text("input_dir: papers\n", encoding="utf-8")
    assert main([]) == EXIT_OK

def test_invalid_config_returns_preflight_exit(isolated_cwd, capsys):
    (isolated_cwd / "config.yaml").write_text("mode: turbo\n", encoding="utf-8")
    assert main(["papers"]) == EXIT_PREFLIGHT
    assert "mode" in capsys.readouterr().err

def test_plan_only_does_not_create_output_dir(isolated_cwd):
    (isolated_cwd / "papers").mkdir()
    output = isolated_cwd / "out"
    assert main(["papers", "--output", str(output), "--plan-only"]) == EXIT_OK
    assert not output.exists()

def test_prompt_and_prompt_file_warning_prefers_prompt(isolated_cwd, capsys):
    (isolated_cwd / "papers").mkdir()
    # Boş --prompt kazanır (b.md hiç okunmaz) ve varsayılan dönüşüme düşer
    assert main(["papers", "--prompt", " ", "--prompt-file", "b.md"]) == EXIT_OK
    assert "--prompt önceliklidir" in capsys.readouterr().err
