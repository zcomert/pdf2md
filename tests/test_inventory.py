import csv
import io
import json
import logging
from pathlib import Path

import pytest

from src.bibliographic import clean_doi, clean_title, extract_bibliographic, from_metadata, usable_title
from src.cli import EXIT_OK, main
from src.config import AppConfig, load_config
from src.errors import PreflightError
from src.llm_client import TextClient
from src.llm_extractor import merge_partials, verify_extraction, LlmExtraction
from src.model_clients import ModelInfo, ModelUnavailable
from src.pdf_parser import parse_pdf
from src.schemas import Bibliographic, DocumentState, DocumentStatus, ProcessingPlan, ProcessingState
from src.summary_writer import FIXED_COLUMNS, SUMMARY_CSV, analytic_values, render_csv, write_summary
from tests.fakes import FakeBackend

LOGGER = logging.getLogger("test-inventory")
FIXTURES = Path(__file__).parent / "fixtures"
TEXT = ModelInfo("gemma4:latest", "c" * 64)


@pytest.fixture(scope="module")
def table_doc():
    return parse_pdf(FIXTURES / "synthetic_table_equation.pdf", "synthetic_table_equation.pdf", "a" * 64,
                     AppConfig().pdf)


def client(backend):
    return TextClient(backend, TEXT.name, 16384, 4096, LOGGER)


# --- DOI ve metadata (§22.3 adım 1–2) -----------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("https://doi.org/10.1016/j.eswa.2023.119001.", "10.1016/j.eswa.2023.119001"),
    ("doi:10.1109/ACCESS.2024.3524452;", "10.1109/ACCESS.2024.3524452"),
    ("(see 10.1000/xyz123)", "10.1000/xyz123"),
    ("10.1002/(SICI)1097-4571(199806)49:8<693::AID-ASI4>3.0.CO;2-O", "10.1002/(SICI)1097-4571(199806)49:8"),
    ("no identifier here", None),
])
def test_clean_doi(text, expected):
    assert clean_doi(text) == expected


@pytest.mark.parametrize("title, usable", [
    ("Microsoft Word - paper.docx", False),
    ("untitled", False),
    ("paper.pdf", False),
    ("Kısa", False),
    ("2025_Polle_Meta", False),  # dosya adıyla aynı
    ("Meta-Learning Approaches for Speaker-Dependent Voice Fatigue Models", True),
])
def test_usable_title(title, usable):
    assert (usable_title(title, "2025_Polle_Meta.pdf") is not None) is usable


def test_publisher_subject_patterns_and_single_author():
    values, sources = from_metadata({
        "title": "Designing a practical fatigue detection system", "author": "Md Abdullah Al Imran",
        "subject": "Journal of Safety Research, 90 (2024) 100-114. doi:10.1016/j.jsr.2024.05.015"}, "a.pdf")
    assert values == {"title": "Designing a practical fatigue detection system", "venue": "Journal of Safety Research",
                      "year": 2024, "doi": "10.1016/j.jsr.2024.05.015"}
    assert "authors" not in values and set(sources.values()) == {"metadata"}
    ieee, _ = from_metadata({"subject": "IEEE Access;2025;13; ;10.1109/ACCESS.2024.3524452"}, "b.pdf")
    assert (ieee["venue"], ieee["year"], ieee["doi"]) == ("IEEE Access", 2025, "10.1109/ACCESS.2024.3524452")
    many, _ = from_metadata({"author": "Fixture Author; Second Author"}, "c.pdf")
    assert many["authors"] == ["Fixture Author", "Second Author"]


# --- LLM adımı ve tahmin yasağı (§22.3 adım 3) --------------------------------------------------------------------

def bib_response(**fields):
    return {"fields": {f"bibliographic.{name}": value for name, value in fields.items()}, "results": [],
            "equations": [], "tables": []}


def test_llm_values_must_appear_in_first_pages(table_doc, tmp_path):
    document = table_doc.model_copy(deep=True)
    document.pdf_metadata = {}
    document.blocks[1].text = "Published in Journal of Fatigue Studies, 2023. Authors: Ayşe Yılmaz and John Doe."
    backend = FakeBackend()
    backend.responses["LlmExtraction"] = [bib_response(
        authors={"status": "found", "value": ["Ayşe Yılmaz", "Uydurma Yazar"], "evidence": [{"block_id": "p1-b2", "page": 1}]},
        year={"status": "found", "value": 2021, "value_text": "2021", "evidence": [{"block_id": "p1-b2", "page": 1}]},
        venue={"status": "found", "value": "Journal of Fatigue Studies", "evidence": [{"block_id": "p1-b2", "page": 1}]},
        doi={"status": "found", "value": "10.9999/uydurma", "evidence": [{"block_id": "p1-b2", "page": 1}]})]
    result = extract_bibliographic(document, client(backend), TEXT, cache_dir=tmp_path)
    record = result.record
    assert record.title == "Tables Equations and Figures" and record.sources["title"] == "parser"
    assert record.authors == ["Ayşe Yılmaz"]  # kaynakta geçmeyen yazar atıldı
    assert record.year is None  # 2021 kaynakta yok → boş (tahmin yasağı)
    assert record.venue == "Journal of Fatigue Studies" and record.doi is None
    assert result.llm_calls == 1 and len(backend.calls) == 1
    call = backend.calls[0]
    assert "bibliographic.title" not in call["prompt"] and "bibliographic.year" in call["prompt"]


def test_bibliographic_cache_and_llm_switch(table_doc, tmp_path):
    backend = FakeBackend()
    first = extract_bibliographic(table_doc, client(backend), TEXT, cache_dir=tmp_path)
    second = extract_bibliographic(table_doc, client(backend), TEXT, cache_dir=tmp_path)
    assert (first.llm_calls, second.from_cache, len(backend.calls)) == (1, True, 1)
    off = extract_bibliographic(table_doc, client(backend), TEXT, cache_dir=tmp_path, use_llm=False)
    assert off.llm_calls == 0 and len(backend.calls) == 1 and off.record.title


def test_unavailable_model_is_only_a_warning(table_doc):
    backend = FakeBackend()
    backend.responses["LlmExtraction"] = [ModelUnavailable("kapalı")]
    result = extract_bibliographic(table_doc, client(backend), TEXT)
    assert result.warnings[0].startswith("bibliographic_llm_unavailable") and result.record.title


def test_prompt_extraction_values_are_reused(table_doc):
    document = table_doc.model_copy(deep=True)
    document.pdf_metadata = {"author": "A One; B Two", "subject": "Venue X, 1 (2022) 1-2. doi:10.1234/abc"}
    document.blocks[1].text = "Venue X 2022 doi 10.1234/abc by A One and B Two"
    plan = ProcessingPlan(scope="document", scope_reason="t", requested_fields=["bibliographic.title"],
                          output_language="tr", output_outline=["Başlık"])
    extraction = verify_extraction(merge_partials([LlmExtraction.model_validate({"fields": [
        {"key": "bibliographic.title", "status": "found", "value": "Tables Equations and Figures",
         "evidence": [{"block_id": "p1-b1", "page": 1}]}]})], plan, document, "h" * 64), document)
    document.title = None
    backend = FakeBackend()
    result = extract_bibliographic(document, client(backend), TEXT, extraction=extraction)
    assert result.record.sources["title"] == "extraction" and not backend.calls  # eksik alan kalmadı


# --- CSV (§22.1–22.2, §22.5) --------------------------------------------------------------------------------------

def state_with_records():
    state = ProcessingState()
    state.documents["alt/yorgunluk.pdf"] = DocumentState(
        sha256="b" * 64, status=DocumentStatus.completed, pages=12, scanned_pages=1, ocr_pages=1, vision_calls=3,
        text_llm_calls=1, warnings=["x: page 1", "y: page 2"], output_path="alt/yorgunluk/yorgunluk.md",
        prompt_sha256="p" * 64, processing_time_sec=12.5, processed_at="2026-09-14T10:00:00",
        bibliographic=Bibliographic(title="Yorgunluk Tespiti İçin Derin Öğrenme", authors=["Ayşe Çınar", "Ömer Şahin"],
                                    year=2024, venue="Uygulamalı Bilimler, Cilt 3", doi="10.1/xyz"))
    state.documents["bozuk.pdf"] = DocumentState(sha256="c" * 64, status=DocumentStatus.failed, error_stage="parse",
                                                  error="satır 1\nsatır 2 " + "x" * 300)
    state.documents["hic_calismamis.pdf"] = DocumentState(sha256="d" * 64)
    return state


def test_csv_columns_bom_turkish_and_rows(tmp_path):
    write_summary(tmp_path, state_with_records())
    raw = (tmp_path / SUMMARY_CSV).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    assert "Yorgunluk Tespiti İçin Derin Öğrenme".encode("utf-8") in raw
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    assert list(rows[0].keys()) == list(FIXED_COLUMNS)
    assert [row["relative_path"] for row in rows] == ["alt/yorgunluk.pdf", "bozuk.pdf", "hic_calismamis.pdf"]
    first = rows[0]
    assert (first["filename"], first["warnings_count"], first["authors"], first["year"], first["processing_time_sec"]) == \
           ("yorgunluk.pdf", "2", "Ayşe Çınar; Ömer Şahin", "2024", "12.5")
    assert rows[0]["venue"] == "Uygulamalı Bilimler, Cilt 3"  # virgül tırnakla korunur
    failed = rows[1]
    assert failed["error_stage"] == "parse" and "\n" not in failed["error_message"]
    assert len(failed["error_message"]) == 200
    assert rows[2]["status"] == "pending" and rows[2]["title"] == ""
    assert len(rows) == 3  # §22.5: özet satırı yok


def test_xlsx_written_when_enabled(tmp_path):
    pandas = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    write_summary(tmp_path, state_with_records(), save_xlsx=True)
    frame = pandas.read_excel(tmp_path / "papers_summary.xlsx", dtype=str)
    assert list(frame.columns) == list(FIXED_COLUMNS)
    assert frame.loc[0, "title"] == "Yorgunluk Tespiti İçin Derin Öğrenme"
    assert not list(tmp_path.glob("*.pdf2md.tmp"))


# --- Analitik sütunlar (§22.4) ------------------------------------------------------------------------------------

def test_extra_fields_validation(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("summary:\n  extra_fields: [dataset.name, results.best_accuracy, results.best_f1]\n", encoding="utf-8")
    assert load_config(path).summary.extra_fields == ["dataset.name", "results.best_accuracy", "results.best_f1"]
    path.write_text("summary:\n  extra_fields: [dataset.size]\n", encoding="utf-8")
    with pytest.raises(PreflightError, match="dataset.size"):
        load_config(path)


def test_analytic_values_only_verified(table_doc):
    plan = ProcessingPlan(scope="document", scope_reason="t", requested_fields=["results.best", "dataset.name"],
                          output_language="source", output_outline=["Özet"])
    partial = LlmExtraction.model_validate({"fields": [
        {"key": "dataset.name", "status": "found", "value": ["UydurmaSet"], "evidence": [{"block_id": "p1-b2", "page": 1}]}],
        "results": [
            {"field": "results.best", "claim": "a", "model": "Bi-LSTM", "metric": "Accuracy", "value_text": "0.99",
             "evidence": [{"block_id": "p1-b4", "page": 1}]},
            {"field": "results.best", "claim": "b", "model": "SVM", "metric": "Accuracy", "value_text": "0.995",
             "evidence": [{"block_id": "p1-b4", "page": 1}]},
            {"field": "results.best", "claim": "c", "model": "Bi-GRU", "metric": "F1-score", "value_text": "0.95",
             "evidence": [{"block_id": "p1-b4", "page": 1}]}]})
    extraction = verify_extraction(merge_partials([partial], plan, table_doc, "h" * 64), table_doc)
    values = analytic_values(extraction, ["results.best_accuracy", "results.best_f1", "results.best_model",
                                          "dataset.name"])
    # 0.995 unverified → yok sayılır; F1 0.95 Bi-GRU satırında → verified; uydurma veri seti adı yazılmaz
    assert values == {"results.best_accuracy": "0.99", "results.best_f1": "0.95", "results.best_model": "Bi-LSTM"}


# --- CLI uçtan uca ------------------------------------------------------------------------------------------------

def test_inventory_end_to_end_and_cache(tmp_input_copy, tmp_output, tmp_path, fake_model_backend, capsys):
    config = tmp_path / "inv.yaml"
    config.write_text("ocr:\n  enabled: false\nsummary:\n  extra_fields: [results.best_accuracy]\n", encoding="utf-8")
    empty_summary = {"fields": {"results.best": {"status": "not_found", "value": None, "evidence": []}},
                     "results": [], "equations": [], "tables": []}
    # Belgeler alfabetik sırayla: single_column (künye, özet), table_equation (künye, özet)
    fake_model_backend.responses["LlmExtraction"] = [
        bib_response(), empty_summary, bib_response(),
        {"fields": {"results.best": {"status": "found", "value": "Bi-LSTM", "evidence": [{"block_id": "p1-b4", "page": 1}]}},
         "results": [{"field": "results.best", "claim": "x", "model": "Bi-LSTM", "metric": "Accuracy",
                      "value_text": "0.99", "dataset": None, "evidence": [{"block_id": "p1-b4", "page": 1}]}],
         "equations": [], "tables": []}]
    args = [str(tmp_input_copy), "--output", str(tmp_output), "--config", str(config), "--include",
            "synthetic_table_equation.pdf", "--include", "synthetic_single_column.pdf"]
    assert main(args) == EXIT_OK
    rows = {row["relative_path"]: row for row in csv.DictReader(
        io.StringIO((tmp_output / SUMMARY_CSV).read_text(encoding="utf-8-sig"), newline=""))}
    single, table = rows["synthetic_single_column.pdf"], rows["synthetic_table_equation.pdf"]
    assert single["title"] == "Synthetic Study of Fatigue Detection" and single["authors"] == "Fixture Author; Second Author"
    assert table["results.best_accuracy"] == "0.99" and table["pages"] == "1"
    assert int(table["text_llm_calls"]) >= 2 and table["vision_calls"] == "0"

    # Çıktı silinip belge yeniden işlenince künye ve analitik sütunlar önbellekten: metin çağrısı yok
    state = json.loads((tmp_output / "processing_state.json").read_text(encoding="utf-8"))
    (tmp_output / state["documents"]["synthetic_table_equation.pdf"]["output_path"]).unlink()
    before = len(fake_model_backend.calls)
    capsys.readouterr()
    assert main(args) == EXIT_OK
    assert len(fake_model_backend.calls) == before
    state = json.loads((tmp_output / "processing_state.json").read_text(encoding="utf-8"))
    assert state["documents"]["synthetic_table_equation.pdf"]["text_llm_calls"] == 0

    # Envanter ayarı değişince belgeler (önbellekten) yeniden işlenir
    config.write_text("ocr:\n  enabled: false\nsummary:\n  bibliographic_llm: false\n", encoding="utf-8")
    assert main(args) == EXIT_OK
    assert "skipped 0" in capsys.readouterr().out
    header = (tmp_output / SUMMARY_CSV).read_text(encoding="utf-8-sig").splitlines()[0]
    assert "results.best_accuracy" not in header


def test_csv_written_at_run_end_with_discovery_failures(tmp_input_copy, tmp_output, no_ocr_config):
    main([str(tmp_input_copy), "--output", str(tmp_output), "--config", str(no_ocr_config), "--recursive"])
    rows = list(csv.DictReader(io.StringIO((tmp_output / SUMMARY_CSV).read_text(encoding="utf-8-sig"), newline="")))
    state = json.loads((tmp_output / "processing_state.json").read_text(encoding="utf-8"))
    assert sorted(row["relative_path"] for row in rows) == sorted(state["documents"])
    corrupt = next(row for row in rows if row["relative_path"] == "corrupt.pdf")
    assert (corrupt["status"], corrupt["error_stage"]) == ("failed", "parse")
    # Filtre dışı kalan belge son durumuyla CSV'de kalır
    main([str(tmp_input_copy), "--output", str(tmp_output), "--config", str(no_ocr_config),
          "--include", "synthetic_single_column.pdf"])
    rows = list(csv.DictReader(io.StringIO((tmp_output / SUMMARY_CSV).read_text(encoding="utf-8-sig"), newline="")))
    assert len(rows) == len(state["documents"])


def test_xlsx_preflight_warning():
    from src.preflight import check_xlsx
    config = AppConfig.model_validate({"output": {"save_xlsx": True}})
    result = check_xlsx(config, find_spec=lambda name: None)
    assert (result.ok, result.severity) == (False, "warning")
    assert check_xlsx(AppConfig()) is None


def test_clean_title_keeps_hyphen():
    assert clean_title("A hybrid approach using a pre-\n trained model") == "A hybrid approach using a pre-trained model"
    assert clean_title("Speaker - Dependent") == "Speaker - Dependent"
