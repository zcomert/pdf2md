import json
import subprocess
import sys
from pathlib import Path

from src.cli import EXIT_DOC_FAILED, EXIT_OK, EXIT_PREFLIGHT, main
from tests.fixtures.generate_fixtures import EXPECTED
from tests.helpers import input_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Açılamayan fixture'lar ayrıştırmada failed olur; bu yüzden ilk çalıştırmanın çıkış kodu 1'dir.
UNOPENABLE = {"corrupt.pdf", "not_a_pdf.PDF", "synthetic_encrypted.pdf"}


def load_state(output):
    return json.loads((output / "processing_state.json").read_text(encoding="utf-8"))


def test_end_to_end_discovery_registers_all_pdfs(tmp_input_copy, tmp_output, capsys):
    before = input_snapshot(tmp_input_copy)
    assert main([str(tmp_input_copy), "--output", str(tmp_output), "--recursive"]) == EXIT_DOC_FAILED
    state = load_state(tmp_output)
    assert set(state["documents"]) == set(EXPECTED)
    assert all(len(doc["sha256"]) == 64 for doc in state["documents"].values())
    assert {rel for rel, doc in state["documents"].items() if doc["status"] == "failed"} == UNOPENABLE
    assert len(state["runs"]) == 1
    assert not (tmp_output / ".lock").exists()
    assert list((tmp_output / "logs").glob("process_*.log"))
    assert "Keşif: 11 PDF (yeni 11" in capsys.readouterr().out
    # §38 kriter 17: giriş klasörü değişmez, içine dosya yazılmaz
    assert input_snapshot(tmp_input_copy) == before


def test_second_run_marks_documents_unchanged(tmp_input_copy, tmp_output, capsys):
    args = [str(tmp_input_copy), "--output", str(tmp_output), "--recursive"]
    assert main(args) == EXIT_DOC_FAILED
    capsys.readouterr()
    assert main(args) == EXIT_OK  # başarısız belgeler --retry-failed olmadan yeniden denenmez
    output = capsys.readouterr().out
    assert "değişen 0, değişmeyen 11" in output
    assert "skipped 8, önceki hata nedeniyle denenmeyen 3" in output
    assert len(load_state(tmp_output)["runs"]) == 2


def test_default_output_dir_is_sibling_of_input(tmp_input_copy):
    assert main([str(tmp_input_copy)]) == EXIT_DOC_FAILED
    assert (tmp_input_copy.parent / "input_output" / "processing_state.json").exists()


def test_output_inside_input_rejected_without_writing(tmp_input_copy):
    before = input_snapshot(tmp_input_copy)
    assert main([str(tmp_input_copy), "--output", str(tmp_input_copy / "out")]) == EXIT_PREFLIGHT
    assert input_snapshot(tmp_input_copy) == before


def test_leftover_temp_files_are_cleaned(tmp_input_copy, tmp_output):
    leftover = tmp_output / "doc" / ".x.md.123.pdf2md.tmp"
    leftover.parent.mkdir(parents=True)
    leftover.write_text("yarım", encoding="utf-8")
    assert main([str(tmp_input_copy), "--output", str(tmp_output)]) == EXIT_DOC_FAILED
    assert not leftover.exists()


def test_interrupted_processing_records_recovered(tmp_input_copy, tmp_output, no_ocr_config):
    args = [str(tmp_input_copy), "--output", str(tmp_output), "--config", str(no_ocr_config)]
    assert main(args) == EXIT_DOC_FAILED
    state = load_state(tmp_output)
    state["documents"]["synthetic_scanned.pdf"].update(status="processing", attempts=1)
    (tmp_output / "processing_state.json").write_text(json.dumps(state), encoding="utf-8")
    assert main(args) == EXIT_OK
    # yarıda kalan kayıt pending'e alınır, bu çalıştırmada yeniden işlenir; deneme sayısı korunup artar
    record = load_state(tmp_output)["documents"]["synthetic_scanned.pdf"]
    assert (record["status"], record["attempts"]) == ("completed_with_warnings", 2)
    assert next(reversed(load_state(tmp_output)["runs"].values()))["recovered_interrupted"] == 1


HOLD_LOCK = """
import sys
from src.state_manager import OutputLock
OutputLock(sys.argv[1], "holder").acquire()
print("ready", flush=True)
sys.stdin.readline()
"""


def test_concurrent_run_rejected_with_exit_code_2(tmp_input_copy, tmp_output, capsys):
    # §38 kriter 16
    tmp_output.mkdir()
    holder = subprocess.Popen([sys.executable, "-c", HOLD_LOCK, str(tmp_output)], cwd=PROJECT_ROOT,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ready"
        assert main([str(tmp_input_copy), "--output", str(tmp_output)]) == EXIT_PREFLIGHT
        assert "kullanılıyor" in capsys.readouterr().err
        assert not (tmp_output / "processing_state.json").exists()
    finally:
        holder.stdin.close()
        holder.wait(timeout=10)


def test_process_papers_entry_reports_missing_dependency(tmp_path):
    # §38 kriter 19: eksik paket, üçüncü taraf içe aktarımlardan önce bildirilir
    script = (
        "import importlib.util, runpy, sys\n"
        "real = importlib.util.find_spec\n"
        "importlib.util.find_spec = lambda name, *a: None if name == 'pydantic' else real(name, *a)\n"
        f"sys.argv = ['process_papers.py', {str(tmp_path)!r}]\n"
        "runpy.run_path('process_papers.py', run_name='__main__')\n"
    )
    completed = subprocess.run([sys.executable, "-c", script], cwd=PROJECT_ROOT, capture_output=True,
                               text=True, encoding="utf-8")
    assert completed.returncode == 2
    assert "pydantic" in completed.stderr and "pip install -r requirements.txt" in completed.stderr
