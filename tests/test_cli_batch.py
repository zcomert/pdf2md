import json

from src.batch_processor import BatchEvents, CancelToken
from src.cli import EXIT_CANCELLED, EXIT_DOC_FAILED, EXIT_OK, EXIT_PREFLIGHT, main
from src.document_model import DocumentModel
from tests.helpers import input_snapshot

UNOPENABLE = {"corrupt.pdf", "not_a_pdf.PDF", "synthetic_encrypted.pdf"}


def load_state(output):
    return json.loads((output / "processing_state.json").read_text(encoding="utf-8"))


def run(tmp_input_copy, tmp_output, *extra, **kwargs):
    return main([str(tmp_input_copy), "--output", str(tmp_output), *extra], **kwargs)


def test_full_conversion_end_to_end(tmp_input_copy, tmp_output, capsys):
    before = input_snapshot(tmp_input_copy)
    assert run(tmp_input_copy, tmp_output, "--recursive") == EXIT_DOC_FAILED
    state = load_state(tmp_output)
    for rel, record in state["documents"].items():
        if rel in UNOPENABLE:
            assert (record["status"], record["error_stage"]) == ("failed", "parse")
            continue
        assert record["status"] in ("completed", "completed_with_warnings")
        markdown = tmp_output / record["output_path"]
        assert markdown.read_text(encoding="utf-8").startswith("---\n")
        # §38 kriter 2: belge klasöründe .md dışında içerik dosyası yok (assets henüz yok)
        assert [p.name for p in markdown.parent.iterdir()] == [markdown.name]
        DocumentModel.model_validate_json((tmp_output / "_cache" / record["sha256"] / "document.json").read_text(encoding="utf-8"))
    # §38 kriter 3: aynı adlı iki PDF çakışmaz
    assert (tmp_output / "synthetic_single_column" / "synthetic_single_column.md").is_file()
    assert (tmp_output / "subdir" / "synthetic_single_column" / "synthetic_single_column.md").is_file()
    # taranmış sayfa içeriği henüz çıkarılamıyor: işaretli ve uyarılı
    scanned = state["documents"]["synthetic_scanned.pdf"]
    assert scanned["status"] == "completed_with_warnings" and "unreadable_page: page 1" in scanned["warnings"]
    output = capsys.readouterr().out
    assert "completed 7, completed_with_warnings 1, failed 3, skipped 0" in output
    assert "Ayrıştırma: 7 ayrıştırıldı, 1 önbellekten." in output
    run_record = next(iter(state["runs"].values()))
    assert (run_record["completed"], run_record["failed"]) == (7, 3)
    assert input_snapshot(tmp_input_copy) == before  # §38 kriter 17


def test_no_text_llm_in_full_conversion(tmp_input_copy, tmp_output):
    # §38 kriter 4: varsayılan prompt metin LLM'i çağırmaz; kullanılan model kaydı boştur
    run(tmp_input_copy, tmp_output, "--include", "synthetic_single_column.pdf")
    record = load_state(tmp_output)["documents"]["synthetic_single_column.pdf"]
    assert record["models"] == {}
    assert "models: {}" in (tmp_output / record["output_path"]).read_text(encoding="utf-8")


def test_second_run_skips_and_exits_ok(tmp_input_copy, tmp_output, capsys):
    run(tmp_input_copy, tmp_output)
    capsys.readouterr()
    assert run(tmp_input_copy, tmp_output) == EXIT_OK
    output = capsys.readouterr().out
    assert "completed 0, completed_with_warnings 0, failed 0, skipped 7, önceki hata nedeniyle denenmeyen 3" in output
    assert "0 ayrıştırıldı, 0 önbellekten" in output


def test_empty_prompt_completes_with_warnings(tmp_input_copy, tmp_output):
    # §38 kriter 6
    assert run(tmp_input_copy, tmp_output, "--prompt", "  ", "--include", "synthetic_single_column.pdf") == EXIT_OK
    record = load_state(tmp_output)["documents"]["synthetic_single_column.pdf"]
    assert record["status"] == "completed_with_warnings"
    assert any(w.startswith("empty_prompt") for w in record["warnings"])


def test_custom_prompt_not_supported_yet(tmp_input_copy, tmp_output, capsys):
    assert run(tmp_input_copy, tmp_output, "--prompt", "Veri setlerini çıkar") == EXIT_PREFLIGHT
    assert "henüz desteklenmiyor" in capsys.readouterr().err
    assert not tmp_output.exists()


def test_force_regenerates_everything(tmp_input_copy, tmp_output, capsys):
    args = ("--include", "synthetic_s*.pdf")
    run(tmp_input_copy, tmp_output, *args)
    capsys.readouterr()
    assert run(tmp_input_copy, tmp_output, *args, "--force") == EXIT_OK
    assert "skipped 0" in capsys.readouterr().out
    record = load_state(tmp_output)["documents"]["synthetic_scanned.pdf"]
    assert record["attempts"] == 2


def test_retry_failed(tmp_input_copy, tmp_output, capsys):
    run(tmp_input_copy, tmp_output)
    capsys.readouterr()
    assert run(tmp_input_copy, tmp_output, "--retry-failed") == EXIT_DOC_FAILED
    assert "failed 3, skipped 7" in capsys.readouterr().out
    assert load_state(tmp_output)["documents"]["corrupt.pdf"]["attempts"] == 2


def test_changed_pdf_is_regenerated(tmp_input_copy, tmp_output, capsys, synthetic_pdf):
    args = ("--include", "synthetic_two_column.pdf")
    run(tmp_input_copy, tmp_output, *args)
    capsys.readouterr()
    (tmp_input_copy / "synthetic_two_column.pdf").write_bytes(synthetic_pdf("synthetic_table_equation.pdf").read_bytes())
    assert run(tmp_input_copy, tmp_output, *args) == EXIT_OK
    output = capsys.readouterr().out
    assert "değişen 1" in output and "1 ayrıştırıldı" in output
    markdown = (tmp_output / "synthetic_two_column" / "synthetic_two_column.md").read_text(encoding="utf-8")
    assert "Tables Equations and Figures" in markdown


class CancelAfterFirst(BatchEvents):
    def __init__(self, token):
        self.token = token

    def on_document_end(self, relative_path, status, warnings, output_path, error=None):
        self.token.cancel()


def test_cancellation_exit_code_and_resume(tmp_input_copy, tmp_output, capsys):
    token = CancelToken()
    args = ("--include", "synthetic_s*.pdf")
    assert run(tmp_input_copy, tmp_output, *args, events=CancelAfterFirst(token), cancel_token=token) == EXIT_CANCELLED
    output = capsys.readouterr().out
    assert "İptal edildi: 1 belge işlenmeden kaldı" in output
    statuses = {rel: r["status"] for rel, r in load_state(tmp_output)["documents"].items()}
    assert sorted(statuses.values()) == ["completed_with_warnings", "pending"]
    assert not (tmp_output / ".lock").exists()
    assert run(tmp_input_copy, tmp_output, *args) == EXIT_OK
    assert "skipped 1" in capsys.readouterr().out
