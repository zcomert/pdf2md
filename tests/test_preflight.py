import io

import pytest

from src.config import AppConfig
from src.dependencies import bootstrap_check, missing_packages
from src.errors import PreflightError
from src.preflight import (check_dependencies, check_disk, check_input, check_output, check_python,
                           check_virtualenv, raise_on_errors, run_preflight)


def test_python_version_check():
    assert check_python((3, 11, 0)).ok
    assert not check_python((3, 10, 9)).ok


def test_virtualenv_warning_has_command():
    result = check_virtualenv(prefix="/usr", base_prefix="/usr")
    assert result.severity == "warning" and "process_papers.py" in result.hint
    assert check_virtualenv(prefix="/p/.venv", base_prefix="/usr").ok


def test_missing_packages_reported_with_install_command():
    fake_find_spec = lambda module: None if module in {"yaml", "PIL"} else object()
    assert missing_packages(fake_find_spec) == ["pyyaml", "pillow"]
    result = check_dependencies(fake_find_spec)
    assert not result.ok and "pip install -r requirements.txt" in result.hint


def test_bootstrap_check_messages():
    stream = io.StringIO()
    assert bootstrap_check(stream, find_spec=lambda module: None if module == "pymupdf" else object()) == 2
    assert "pymupdf" in stream.getvalue() and "pip install" in stream.getvalue()
    stream = io.StringIO()
    assert bootstrap_check(stream, version_info=(3, 9, 1)) == 2
    assert "3.11" in stream.getvalue()
    assert bootstrap_check(io.StringIO(), find_spec=lambda module: object()) is None


def test_input_checks(tmp_path):
    assert not check_input(tmp_path / "missing").ok
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert not check_input(tmp_path / "notes.txt").ok
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    assert check_input(tmp_path / "a.pdf").ok
    assert check_input(tmp_path).ok


def test_output_same_as_or_inside_input_rejected(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    assert not check_output(papers, papers).ok
    assert not check_output(papers, papers / "out").ok
    assert check_output(papers, tmp_path / "papers_output").ok


def test_single_pdf_output_inside_its_folder_rejected(tmp_path):
    pdf = tmp_path / "papers" / "a.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF")
    assert not check_output(pdf, tmp_path / "papers" / "out").ok


def test_output_is_file_rejected(tmp_path):
    (tmp_path / "papers").mkdir()
    (tmp_path / "out").write_text("x", encoding="utf-8")
    assert not check_output(tmp_path / "papers", tmp_path / "out").ok


def test_disk_check_uses_existing_parent(tmp_path):
    assert check_disk(tmp_path / "not" / "yet", 0).ok
    assert not check_disk(tmp_path, 10 ** 12).ok


def test_run_preflight_and_raise(tmp_path):
    (tmp_path / "papers").mkdir()
    results = run_preflight(AppConfig(), tmp_path / "papers", tmp_path / "papers")
    with pytest.raises(PreflightError, match="giriş klasörüyle aynı"):
        raise_on_errors(results)
    raise_on_errors(run_preflight(AppConfig(), tmp_path / "papers", tmp_path / "out"))
