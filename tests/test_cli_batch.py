import json

import pytest

from src.batch_processor import BatchEvents, CancelToken
from src.cli import EXIT_CANCELLED, EXIT_DOC_FAILED, EXIT_OK, EXIT_PREFLIGHT, main
from src.document_model import DocumentModel
from tests.fakes import FAKE_LATEX, FAKE_PAGE_TEXT
from tests.helpers import input_snapshot

UNOPENABLE = {"corrupt.pdf", "not_a_pdf.PDF", "synthetic_encrypted.pdf"}


def load_state(output):
    return json.loads((output / "processing_state.json").read_text(encoding="utf-8"))


def run(tmp_input_copy, tmp_output, *extra, **kwargs):
    return main([str(tmp_input_copy), "--output", str(tmp_output), *extra], **kwargs)


def test_full_conversion_end_to_end(tmp_input_copy, tmp_output, capsys, no_ocr_config):
    before = input_snapshot(tmp_input_copy)
    assert run(tmp_input_copy, tmp_output, "--recursive", "--config", str(no_ocr_config)) == EXIT_DOC_FAILED
    state = load_state(tmp_output)
    for rel, record in state["documents"].items():
        if rel in UNOPENABLE:
            assert (record["status"], record["error_stage"]) == ("failed", "parse")
            continue
        assert record["status"] in ("completed", "completed_with_warnings")
        markdown = tmp_output / record["output_path"]
        assert markdown.read_text(encoding="utf-8").startswith("---\n")
        # §38 kriter 2: belge klasöründe .md dışında içerik dosyası yok (assets/ görselleri hariç)
        assert {p.name for p in markdown.parent.iterdir()} <= {markdown.name, "assets"}
        text = markdown.read_text(encoding="utf-8")
        assets_dir = markdown.parent / "assets"
        if assets_dir.exists():
            files = [p.relative_to(markdown.parent).as_posix() for p in assets_dir.rglob("*") if p.is_file()]
            assert files and all(f"]({name})" in text for name in files)  # yalnızca referans verilen görseller
        DocumentModel.model_validate_json((tmp_output / "_cache" / record["sha256"] / "document.json").read_text(encoding="utf-8"))
    # §38 kriter 3: aynı adlı iki PDF çakışmaz
    assert (tmp_output / "synthetic_single_column" / "synthetic_single_column.md").is_file()
    assert (tmp_output / "subdir" / "synthetic_single_column" / "synthetic_single_column.md").is_file()
    # OCR kapalıyken taranmış sayfa görsel modelle okunur (§11.4, §12.3 scanned_no_ocr); OCR eksikliği uyarı olarak kalır
    scanned = state["documents"]["synthetic_scanned.pdf"]
    assert scanned["status"] == "completed_with_warnings" and scanned["warnings"] == ["ocr_unavailable: page 1"]
    scanned_markdown = (tmp_output / scanned["output_path"]).read_text(encoding="utf-8")
    assert FAKE_PAGE_TEXT in scanned_markdown and "[unreadable_page]" not in scanned_markdown
    assert scanned["models"]["vision"]["name"] == "minicpm-v4.5:8b"
    output = capsys.readouterr().out
    assert "completed 7, completed_with_warnings 1, failed 3, skipped 0" in output
    assert "Ayrıştırma: 7 ayrıştırıldı, 1 önbellekten." in output
    run_record = next(iter(state["runs"].values()))
    assert (run_record["completed"], run_record["failed"]) == (7, 3)
    assert input_snapshot(tmp_input_copy) == before  # §38 kriter 17


def test_tables_equations_and_figures_in_markdown(tmp_input_copy, tmp_output):
    assert run(tmp_input_copy, tmp_output, "--include", "synthetic_table_equation.pdf", "--include", "synthetic_single_column.pdf") == EXIT_OK
    folder = tmp_output / "synthetic_table_equation"
    markdown = (folder / "synthetic_table_equation.md").read_text(encoding="utf-8")
    assert "| Model | Accuracy | F1 |\n|---|---:|---:|\n| Bi-LSTM | 0.99 | 0.98 |" in markdown
    # BALANCED: formüller görsel modelle LaTeX'e çevrilir (§12.3 equation_requested)
    assert f"$$\n{FAKE_LATEX}\n$$" in markdown and "[latex_unavailable]" not in markdown
    assert "minicpm-v4.5:8b@sha256:" in markdown.split("---")[1]  # front matter'da görsel model ve digest'i
    assert "![Figure 1. Proposed pipeline](assets/figures/figure_01.png)" in markdown
    assert (folder / "assets" / "figures" / "figure_01.png").read_bytes().startswith(b"\x89PNG")
    assert markdown.count("Bi-GRU") == 1  # tablo hücreleri paragraf olarak tekrar yazılmaz
    # görsel referansı olmayan belgede assets/ oluşmaz (§6.2)
    assert not (tmp_output / "synthetic_single_column" / "assets").exists()


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


def test_cancellation_exit_code_and_resume(tmp_input_copy, tmp_output, capsys, no_ocr_config):
    token = CancelToken()
    args = ("--include", "synthetic_s*.pdf", "--config", str(no_ocr_config))
    assert run(tmp_input_copy, tmp_output, *args, events=CancelAfterFirst(token), cancel_token=token) == EXIT_CANCELLED
    output = capsys.readouterr().out
    assert "İptal edildi: 1 belge işlenmeden kaldı" in output
    statuses = {rel: r["status"] for rel, r in load_state(tmp_output)["documents"].items()}
    assert sorted(statuses.values()) == ["completed_with_warnings", "pending"]
    assert not (tmp_output / ".lock").exists()
    assert run(tmp_input_copy, tmp_output, *args) == EXIT_OK
    assert "skipped 1" in capsys.readouterr().out


# --- Faz 06: OCR ---

@pytest.mark.requires_tesseract
def test_scanned_pdf_is_ocr_converted(tmp_input_copy, tmp_output):
    assert run(tmp_input_copy, tmp_output, "--include", "synthetic_scanned.pdf") == EXIT_OK
    record = load_state(tmp_output)["documents"]["synthetic_scanned.pdf"]
    assert record["status"] == "completed" and record["warnings"] == []
    markdown = (tmp_output / record["output_path"]).read_text(encoding="utf-8")
    assert "[unreadable_page]" not in markdown and "recover these sentences reliably" in markdown
    document = DocumentModel.model_validate_json(
        (tmp_output / "_cache" / record["sha256"] / "document.json").read_text(encoding="utf-8"))
    assert document.stats.ocr_pages == 1 and document.ocr_signature.startswith("tesseract:")


@pytest.mark.requires_tesseract
def test_enabling_ocr_invalidates_cached_scanned_document(tmp_input_copy, tmp_output, no_ocr_config, capsys):
    args = ("--include", "synthetic_s*.pdf")
    assert run(tmp_input_copy, tmp_output, *args, "--config", str(no_ocr_config)) == EXIT_OK
    capsys.readouterr()
    # OCR açılınca yalnızca taranmış sayfalı belgenin önbelleği geçersiz olur; diğeri önbellekten gelir.
    assert run(tmp_input_copy, tmp_output, *args, "--force") == EXIT_OK
    capsys.readouterr()
    (tmp_output / load_state(tmp_output)["documents"]["synthetic_scanned.pdf"]["output_path"]).unlink()
    (tmp_output / load_state(tmp_output)["documents"]["synthetic_single_column.pdf"]["output_path"]).unlink()
    assert run(tmp_input_copy, tmp_output, *args, "--config", str(no_ocr_config)) == EXIT_OK
    assert "Ayrıştırma: 1 ayrıştırıldı, 1 önbellekten." in capsys.readouterr().out


def test_missing_tesseract_is_a_warning_not_an_error(tmp_input_copy, tmp_output, tmp_path, capsys):
    config = tmp_path / "missing_tesseract.yaml"
    config.write_text(f"ocr:\n  tesseract_path: {str(tmp_path / 'yok' / 'tesseract.exe')!r}\n", encoding="utf-8")
    assert run(tmp_input_copy, tmp_output, "--include", "synthetic_scanned.pdf", "--config", str(config)) == EXIT_OK
    assert "Tesseract bulunamadı" in capsys.readouterr().err
    record = load_state(tmp_output)["documents"]["synthetic_scanned.pdf"]
    assert record["status"] == "completed_with_warnings" and "ocr_unavailable: page 1" in record["warnings"]


# --- Faz 07: görsel model ve Ollama ---

def test_ollama_unreachable_exits_with_code_2(tmp_input_copy, tmp_output, capsys, fake_model_backend):
    fake_model_backend.unavailable = True
    assert run(tmp_input_copy, tmp_output) == EXIT_PREFLIGHT
    assert "Ollama'ya erişilemiyor" in capsys.readouterr().err and not tmp_output.exists()


def test_missing_text_model_shows_pull_command(tmp_input_copy, tmp_output, capsys, fake_model_backend):
    # §38 kriter 18
    fake_model_backend.models = ["minicpm-v4.5:8b"]
    assert run(tmp_input_copy, tmp_output) == EXIT_PREFLIGHT
    assert "Required model not found: gemma4:latest" in capsys.readouterr().err
    fake_model_backend.models = ["gemma4:latest"]
    assert run(tmp_input_copy, tmp_output, "--mode", "fast", "--include", "synthetic_single_column.pdf") == EXIT_OK


def test_mode_controls_vision_calls_and_log_records_triggers(tmp_input_copy, tmp_output, fake_model_backend):
    args = ("--include", "synthetic_table_equation.pdf")
    assert run(tmp_input_copy, tmp_output, *args, "--mode", "fast") == EXIT_OK
    assert fake_model_backend.calls == []  # FAST: formül/şekil için görsel model yok
    markdown = (tmp_output / "synthetic_table_equation" / "synthetic_table_equation.md").read_text(encoding="utf-8")
    assert "[latex_unavailable]" in markdown
    assert run(tmp_input_copy, tmp_output, *args, "--mode", "full", "--force") == EXIT_OK
    assert {call["task"] for call in fake_model_backend.calls} == {"EquationResult", "FigureResult"}
    # §38 kriter 24: log dosyasında her görsel çağrı tetikleyicisiyle
    log = "\n".join(p.read_text(encoding="utf-8") for p in (tmp_output / "logs").glob("*.log"))
    assert "tetikleyici=candidate_full" in log and "tetikleyici=equation_requested" in log


def test_vision_results_are_cached(tmp_input_copy, tmp_output, fake_model_backend):
    args = ("--include", "synthetic_table_equation.pdf")
    run(tmp_input_copy, tmp_output, *args)
    first = len(fake_model_backend.calls)
    record = load_state(tmp_output)["documents"]["synthetic_table_equation.pdf"]
    (tmp_output / record["output_path"]).unlink()
    assert run(tmp_input_copy, tmp_output, *args) == EXIT_OK
    assert first == 2 and len(fake_model_backend.calls) == first  # formül sonuçları önbellekten


def test_model_service_stopping_mid_run_stops_batch(tmp_input_copy, tmp_output, capsys, fake_model_backend):
    # §28: Ollama çalışma sırasında kapanırsa belge failed olmaz, batch durur, durum kaydedilir
    from src.model_clients import ModelUnavailable
    fake_model_backend.responses["EquationResult"] = [ModelUnavailable("bağlantı koptu")]
    args = ("--include", "synthetic_table_equation.pdf", "--include", "synthetic_two_column.pdf")
    assert run(tmp_input_copy, tmp_output, *args) == EXIT_DOC_FAILED
    assert "Batch durduruldu" in capsys.readouterr().err
    documents = load_state(tmp_output)["documents"]
    assert documents["synthetic_table_equation.pdf"]["status"] == "pending"
    assert documents["synthetic_two_column.pdf"]["status"] == "pending"  # sonraki belgeye geçilmedi
    assert run(tmp_input_copy, tmp_output, *args) == EXIT_OK  # servis döndü: kaldığı yerden devam


def test_vision_model_missing_with_vision_not_required(tmp_input_copy, tmp_output, fake_model_backend, tmp_path):
    fake_model_backend.models = ["gemma4:latest"]
    config = tmp_path / "no_vision.yaml"
    config.write_text("models:\n  vision_required: false\n", encoding="utf-8")
    assert run(tmp_input_copy, tmp_output, "--include", "synthetic_table_equation.pdf", "--config", str(config)) == EXIT_OK
    record = load_state(tmp_output)["documents"]["synthetic_table_equation.pdf"]
    assert record["status"] == "completed_with_warnings" and record["warnings"][0].startswith("vision_unavailable")
