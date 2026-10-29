"""Önceki fazlarda doğrudan testi olmayan kabul kriterleri (§38: 21–23, 26–28)."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.bibliographic import Bibliographic
from src.cli import EXIT_OK, main
from src.document_model import DocumentModel
from src.schemas import Extraction, ProcessingPlan
from src.state_manager import StateManager
from tests.reference_schema import REFERENCE_DIR, load_reference

ROOT = Path(__file__).resolve().parents[2]


def load_evaluator():
    spec = importlib.util.spec_from_file_location("evaluate", ROOT / "tools" / "evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Kriter 21–22: doğruluk ölçüm aracı ---------------------------------------------------------------------------

def test_evaluator_detects_verified_value_from_wrong_cell():
    """Faz 09'da gerçek sette görülen durum: Recall sütunundaki 92, F skoru sanılarak verified raporlandı."""
    evaluate = load_evaluator()
    reference = load_reference(REFERENCE_DIR / "vekkot_continuous.yaml")
    wrong = {"model": "MFCC+Stat-Bi-LSTM", "metric": "F score Ambiguous", "value": 92, "claim": ""}
    right = {"model": "MFCC+Stat-Bi-LSTM", "metric": "F score Ambiguous", "value": 91, "claim": ""}
    sibling_row = {"model": "MFCC-Bi-LSTM", "metric": "F score Ambiguous", "value": 94, "claim": ""}
    assert evaluate.table_cell_verdict(reference, wrong) is False
    assert evaluate.table_cell_verdict(reference, right) is True
    assert evaluate.table_cell_verdict(reference, sibling_row) is True  # MFCC+Stat satırıyla karışmaz
    # Model adı birden çok satıra uyuyor (MFCC-Bi-LSTM, Stat-Bi-LSTM, MFCC+Stat-Bi-LSTM; F skoru: 94, 66, 91)
    ambiguous_wrong = {"model": "Bi-LSTM", "metric": "F1-Score (Ambiguous)", "value": 92, "claim": ""}
    ambiguous_possible = {"model": "Bi-LSTM", "metric": "F1-Score (Ambiguous)", "value": 91, "claim": ""}
    assert evaluate.table_cell_verdict(reference, ambiguous_wrong) is False
    assert evaluate.table_cell_verdict(reference, ambiguous_possible) is None


def test_evaluator_scores_synthetic_reference(tmp_input_copy, tmp_output, no_ocr_config):
    evaluate = load_evaluator()
    reference = load_reference(REFERENCE_DIR / "synthetic_table_equation.yaml")
    assert main([str(tmp_input_copy), "--output", str(tmp_output), "--config", str(no_ocr_config), "--include",
                 reference.source, "--mode", "balanced"]) == EXIT_OK
    state = json.loads((tmp_output / "processing_state.json").read_text(encoding="utf-8"))
    record = state["documents"][reference.source]
    markdown = (tmp_output / record["output_path"]).read_text(encoding="utf-8")
    tables = evaluate.score_tables(reference, markdown)
    assert tables[0]["cell_accuracy"] == 1.0
    equations, valid_rate = evaluate.score_equations(reference, markdown)
    assert equations[0]["exact"] and valid_rate == 1.0  # formül 1 metin katmanından birebir LaTeX'e çevrilir
    assert evaluate.score_bibliographic(reference, record)["title"] is True
    summary = evaluate.summarize([{"bibliographic": evaluate.score_bibliographic(reference, record), "tables": tables,
                                   "equations": equations, "latex_valid_rate": valid_rate,
                                   "results": evaluate.score_results(reference, None)}])
    assert summary["table_cells"] == 1.0 and summary["contradicting_verified"] == 0
    assert "| Tablo hücreleri (yapılandırılmış tabloda) | 1.0 |" in evaluate.render_markdown(
        {"generated": "2026-09-14T00:00:00", "prompt": "x",
         "modes": {"balanced": {"summary": summary, "papers": []}}})


# --- Kriter 23: tüm JSON ara dosyaları şemadan geçer --------------------------------------------------------------

def test_all_output_json_files_validate(tmp_input_copy, tmp_output, no_ocr_config, fake_model_backend):
    fake_model_backend.responses["ProcessingPlan"] = [{
        "scope_reason": "tek tek", "scope": "document", "requested_fields": ["results.best", "dataset.name"],
        "output_language": "tr", "output_outline": ["Sonuçlar", "Veri Seti"]}]
    args = [str(tmp_input_copy), "--output", str(tmp_output), "--config", str(no_ocr_config), "--recursive"]
    main(args)  # tam dönüşüm (bozuk PDF'ler nedeniyle çıkış 1)
    main(args + ["--prompt", "En iyi sonuçları ve veri setini çıkar."])
    validated = {"document": 0, "extraction": 0, "plan": 0, "bibliographic": 0}
    for path in (tmp_output / "_cache").rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        if path.name == "document.json":
            DocumentModel.model_validate_json(text)
            validated["document"] += 1
        elif path.parent.name == "extractions":
            Extraction.model_validate_json(text)
            validated["extraction"] += 1
        elif path.parent.name == "plans":
            ProcessingPlan.model_validate_json(text)
            validated["plan"] += 1
        elif path.name.startswith("bibliographic_"):
            Bibliographic.model_validate_json(text)
            validated["bibliographic"] += 1
    assert all(count > 0 for count in validated.values()), validated
    StateManager(tmp_output).load()  # geçersizse PreflightError


# --- Kriter 26: sonuç sayıları konsolda ve log'da -----------------------------------------------------------------

def test_run_summary_on_console_and_in_log(tmp_input_copy, tmp_output, no_ocr_config, capsys):
    main([str(tmp_input_copy), "--output", str(tmp_output), "--config", str(no_ocr_config), "--recursive"])
    console = capsys.readouterr().out
    line = next(line for line in console.splitlines() if line.startswith("Sonuç: toplam"))
    for word in ("completed", "completed_with_warnings", "failed", "skipped", "süre"):
        assert word in line
    log = next((tmp_output / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert line in log
    state = json.loads((tmp_output / "processing_state.json").read_text(encoding="utf-8"))
    run = next(iter(state["runs"].values()))
    assert {"completed", "completed_with_warnings", "failed", "skipped", "total_time_sec"} <= set(run)


# --- Kriter 27–28: sanal ortam ve sürüm kontrolü ------------------------------------------------------------------

def test_virtualenv_does_not_use_global_site_packages():
    if sys.prefix == sys.base_prefix:
        pytest.skip("Testler sanal ortam dışında çalıştırılıyor")
    config = Path(sys.prefix) / "pyvenv.cfg"
    settings = dict(line.split("=", 1) for line in config.read_text(encoding="utf-8").splitlines() if "=" in line)
    assert settings[next(key for key in settings if key.strip() == "include-system-site-packages")].strip() == "false"
    import site
    assert all(Path(path).resolve().is_relative_to(Path(sys.prefix).resolve()) for path in site.getsitepackages())
    import fitz
    assert Path(fitz.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())


def test_venv_and_caches_not_in_output_or_git(tmp_input_copy, tmp_output, no_ocr_config):
    main([str(tmp_input_copy), "--output", str(tmp_output), "--config", str(no_ocr_config), "--include",
          "synthetic_single_column.pdf"])
    forbidden = [p for p in tmp_output.rglob("*") if p.name in (".venv", "__pycache__") or p.suffix == ".pyc"]
    assert not forbidden
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {".venv/", "__pycache__/", "*.pyc", "*_output/"} <= set(ignored)
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("git yok")
    tracked = subprocess.run([git, "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    assert not [path for path in tracked if path.startswith(".venv/") or "__pycache__" in path or path.endswith(".pyc")]
    checked = subprocess.run([git, "check-ignore", ".venv/pyvenv.cfg", "src/__pycache__/x.pyc", "papers_output/a.md"],
                             cwd=ROOT, capture_output=True, text=True)
    assert len(checked.stdout.splitlines()) == 3
