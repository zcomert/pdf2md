import errno
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.cli import EXIT_DOC_FAILED, EXIT_OK, main
from src.error_policy import CANCEL, FAIL, STOP, WriteErrorTracker, classify
from src.errors import DocumentError, ErrorStage, FatalBatchError, PreflightError
from src.model_clients import ModelUnavailable
from src.batch_processor import Cancelled

ROOT = Path(__file__).resolve().parents[1]
THREE = ("--include", "synthetic_single_column.pdf", "--include", "synthetic_two_column.pdf",
         "--include", "synthetic_table_equation.pdf")


def load_state(output):
    return json.loads((output / "processing_state.json").read_text(encoding="utf-8"))


def run(tmp_input_copy, tmp_output, *extra):
    return main([str(tmp_input_copy), "--output", str(tmp_output), *extra])


def markdown_contents(output):
    """Çıktı Markdown'ları; üretim zamanı satırı hariç."""
    return {path.relative_to(output).as_posix(): "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                                                          if not line.startswith("generated:"))
            for path in sorted(output.rglob("*.md"))}


# --- §28 tablosu --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("exc, stage, action, error_stage, error_type", [
    (DocumentError(ErrorStage.parse, "bozuk", "corrupt_pdf"), ErrorStage.parse, FAIL, ErrorStage.parse, "corrupt_pdf"),
    (DocumentError(ErrorStage.llm, "yavaş", "model_timeout"), ErrorStage.llm, FAIL, ErrorStage.llm, "model_timeout"),
    (DocumentError(ErrorStage.validation, "json", "invalid_model_response"), ErrorStage.llm, FAIL,
     ErrorStage.validation, "invalid_model_response"),
    (ModelUnavailable("kapalı"), ErrorStage.vision, STOP, ErrorStage.vision, "model_unavailable"),
    (ModelUnavailable("kapalı"), ErrorStage.write, STOP, ErrorStage.llm, "model_unavailable"),
    (FatalBatchError(ErrorStage.write, "dolu", "insufficient_disk"), ErrorStage.parse, STOP, ErrorStage.write,
     "insufficient_disk"),
    (PermissionError("erişim"), ErrorStage.write, FAIL, ErrorStage.write, "write_error"),
    (OSError(errno.ENOSPC, "No space left"), ErrorStage.write, STOP, ErrorStage.write, "disk_full"),
    (Cancelled(), ErrorStage.vision, CANCEL, ErrorStage.vision, "cancelled"),
    (KeyError("x"), ErrorStage.vision, FAIL, ErrorStage.vision, "unexpected_error"),
])
def test_error_policy_table(exc, stage, action, error_stage, error_type):
    outcome = classify(exc, stage, Cancelled)
    assert (outcome.action, outcome.stage, outcome.error_type) == (action, error_stage, error_type)
    assert outcome.document_status.value == ("failed" if action == FAIL else "pending")


def test_write_error_tracker_resets_on_success():
    tracker = WriteErrorTracker()
    write = classify(PermissionError("x"), ErrorStage.write)
    parse = classify(DocumentError(ErrorStage.parse, "x"), ErrorStage.parse)
    assert tracker.record(write) is False
    tracker.success()
    assert tracker.record(write) is False
    assert tracker.record(parse) is False  # başka bir hata art arda sayımını bozar
    assert tracker.record(write) is False and tracker.record(write) is True


def test_pipeline_errors_survive_pickling():
    # Paralel ayrıştırmada worker'dan gelen hata ana süreçte aynı aşama ve türle yeniden fırlatılır.
    for error in (DocumentError(ErrorStage.parse, "bozuk", "corrupt_pdf"), FatalBatchError("write", "dolu"),
                  PreflightError("mesaj", "öneri")):
        copy = pickle.loads(pickle.dumps(error))
        assert type(copy) is type(error) and str(copy) == str(error)
    assert pickle.loads(pickle.dumps(DocumentError("parse", "x", "corrupt_pdf"))).error_type == "corrupt_pdf"


# --- Yazma ve disk hataları ---------------------------------------------------------------------------------------

def test_repeated_write_error_stops_batch(tmp_input_copy, tmp_output, no_ocr_config, monkeypatch, capsys):
    import src.batch_processor as module

    def failing(path, text, **kwargs):
        raise PermissionError(13, "Erişim engellendi", str(path))

    monkeypatch.setattr(module, "atomic_write_text", failing)
    code = run(tmp_input_copy, tmp_output, "--config", str(no_ocr_config), "--cpu-workers", "1", *THREE)
    assert code == EXIT_DOC_FAILED
    documents = load_state(tmp_output)["documents"]
    statuses = [documents[name]["status"] for name in ("synthetic_single_column.pdf", "synthetic_table_equation.pdf",
                                                        "synthetic_two_column.pdf")]
    assert statuses == ["failed", "failed", "pending"]  # ikinci ardışık hatada durur, üçüncüye dokunulmaz
    record = documents["synthetic_single_column.pdf"]
    assert (record["error_stage"], record["error_type"], record["attempts"]) == ("write", "write_error", 1)
    err = capsys.readouterr().err
    assert "Yazma hatası art arda tekrarlandı" in err and "kaldığı yerden devam" in err
    log = next((tmp_output / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert "Başarısız [write/write_error]: synthetic_single_column.pdf (deneme 1)" in log


def test_disk_full_stops_immediately_and_keeps_document_pending(tmp_input_copy, tmp_output, no_ocr_config, monkeypatch):
    import src.batch_processor as module

    def full(path, text, **kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(module, "atomic_write_text", full)
    assert run(tmp_input_copy, tmp_output, "--config", str(no_ocr_config), "--cpu-workers", "1", *THREE) == EXIT_DOC_FAILED
    documents = load_state(tmp_output)["documents"]
    assert {record["status"] for record in documents.values()} == {"pending"}


def test_low_disk_space_checked_before_each_document(tmp_input_copy, tmp_output, no_ocr_config, monkeypatch, capsys):
    import src.batch_processor as module
    real = module.BatchProcessor._check_disk
    checks = []

    def check(self):
        checks.append(1)
        if len(checks) == 2:
            self._disk_usage = lambda path: SimpleNamespace(free=10 * 1024 * 1024)
        return real(self)

    monkeypatch.setattr(module.BatchProcessor, "_check_disk", check)
    assert run(tmp_input_copy, tmp_output, "--config", str(no_ocr_config), "--cpu-workers", "1", *THREE) == EXIT_DOC_FAILED
    documents = load_state(tmp_output)["documents"]
    assert sorted(record["status"] for record in documents.values()) == ["completed", "pending", "pending"]
    assert "Yetersiz disk alanı: 10 MB boş" in capsys.readouterr().err
    # Yer açılınca kaldığı yerden devam
    monkeypatch.setattr(module.BatchProcessor, "_check_disk", real)
    assert run(tmp_input_copy, tmp_output, "--config", str(no_ocr_config), *THREE) == EXIT_OK
    assert "skipped 1" in capsys.readouterr().out


# --- §38 kriter 12, 15; paralellik; günlükleme -------------------------------------------------------------------

def test_second_run_makes_no_model_calls(tmp_input_copy, tmp_output, no_ocr_config, fake_model_backend, capsys):
    args = ("--config", str(no_ocr_config), "--recursive", "--mode", "full")
    run(tmp_input_copy, tmp_output, *args)
    first_calls = len(fake_model_backend.calls)
    assert first_calls > 0  # taranmış sayfa ve adaylar görsel modele gitti
    capsys.readouterr()
    run(tmp_input_copy, tmp_output, *args)
    output = capsys.readouterr().out
    assert "completed 0, completed_with_warnings 0" in output and len(fake_model_backend.calls) == first_calls


def test_parallel_parsing_matches_sequential(tmp_input_copy, tmp_path, no_ocr_config, capsys):
    sequential, parallel = tmp_path / "seq", tmp_path / "par"
    assert run(tmp_input_copy, sequential, "--config", str(no_ocr_config), "--recursive", "--cpu-workers", "1") == EXIT_DOC_FAILED
    assert run(tmp_input_copy, parallel, "--config", str(no_ocr_config), "--recursive", "--cpu-workers", "3") == EXIT_DOC_FAILED
    assert markdown_contents(sequential) == markdown_contents(parallel)
    seq_state, par_state = load_state(sequential), load_state(parallel)
    for name, record in seq_state["documents"].items():
        other = par_state["documents"][name]
        assert (record["status"], record.get("error_type"), record["warnings"]) == \
               (other["status"], other.get("error_type"), other["warnings"])
    assert par_state["documents"]["corrupt.pdf"]["error_type"] == "corrupt_pdf"  # worker hatası taşındı
    runs = [next(iter(state["runs"].values())) for state in (seq_state, par_state)]
    # Aynı içerikli kopya (duplicate_copy.pdf) bir kez ayrıştırılır
    assert (runs[0]["parsed"], runs[0]["parsed_from_cache"]) == (runs[1]["parsed"], runs[1]["parsed_from_cache"])
    assert runs[1]["parsed_from_cache"] >= 1


def test_document_summary_logged_without_pdf_content(tmp_input_copy, tmp_output, no_ocr_config, fake_model_backend):
    fake_model_backend.responses["LlmExtraction"] = [{"fields": {
        "dataset.name": {"status": "found", "value": "GizliVeriSeti", "evidence": [{"block_id": "p1-b12", "page": 1}]}}}]
    fake_model_backend.responses["ProcessingPlan"] = [{
        "scope_reason": "tek tek", "scope": "document", "requested_fields": ["dataset.name"],
        "output_language": "tr", "output_outline": ["Veri Seti"]}]
    assert run(tmp_input_copy, tmp_output, "--config", str(no_ocr_config), "--include", "synthetic_single_column.pdf",
               "--prompt", "Veri setini çıkar.") == EXIT_OK
    log = next((tmp_output / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert "Başladı: synthetic_single_column.pdf (1/1)" in log
    assert "Belge özeti: synthetic_single_column.pdf — " in log and "1 sayfa (text=1), OCR 0 sayfa, görsel çağrı 0, metin çağrı 2" in log
    # §29: PDF içeriği ve model yanıtı loglanmaz (log_model_content: false)
    assert "physiological signals" not in log and "GizliVeriSeti" not in log


def test_killed_run_leaves_no_partial_files_and_resumes(tmp_input_copy, tmp_path, no_ocr_config):
    """§38 kriter 15: süreç yazım ortasında zorla sonlandırılır; yeniden başlatınca yarım dosya yok ve devam edilir."""
    output = tmp_path / "killed"
    marker = tmp_path / "marker.txt"
    args = [str(tmp_input_copy), "--output", str(output), "--config", str(no_ocr_config), "--cpu-workers", "1", *THREE]
    process = subprocess.Popen([sys.executable, str(ROOT / "tests" / "kill_target.py"), str(marker), "2", *args],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 90
        while not marker.exists():
            assert process.poll() is None, "alt süreç işaret yazmadan bitti"
            assert time.monotonic() < deadline, "işaret beklenirken zaman aşımı"
            time.sleep(0.2)
        temp_file = Path(marker.read_text(encoding="utf-8"))
        assert temp_file.exists()  # geçici dosya yazıldı ama yerine konmadı
    finally:
        process.kill()
        process.wait(timeout=30)

    state = load_state(output)
    assert sorted(r["status"] for r in state["documents"].values()) == ["completed", "pending", "processing"]
    interrupted = next(name for name, r in state["documents"].items() if r["status"] == "processing")
    assert state["documents"][interrupted]["output_path"] is None  # yarım belge çıktı kaydı almadı

    assert main(args) == EXIT_OK
    assert not list(output.rglob("*.pdf2md.tmp"))
    state = load_state(output)
    assert {r["status"] for r in state["documents"].values()} == {"completed"}
    assert state["documents"][interrupted]["attempts"] == 2
    assert next(iter(state["runs"].values()))["recovered_interrupted"] == 1
    log = "".join(path.read_text(encoding="utf-8") for path in (output / "logs").glob("*.log"))
    assert "kilidi temizlemeden sonlanmış" in log and "geçici dosya silindi" in log

    clean = tmp_path / "clean"
    assert main([str(tmp_input_copy), "--output", str(clean), "--config", str(no_ocr_config), *THREE]) == EXIT_OK
    assert markdown_contents(output) == markdown_contents(clean)
