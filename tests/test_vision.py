import json
import logging

import pytest

from src.config import AppConfig
from src.document_model import (Block, BlockType, Candidate, CandidateKind, DocumentModel, DocumentSource,
                                DocumentWarning, Equation, Figure, Page, PageClass, Table)
from src.evidence_verifier import validate_latex
from src.markdown_builder import build_full_conversion, unreadable_pages
from src.model_clients import ModelNotFound, ModelTimeout, ModelUnavailable
from src.preflight import check_models, check_vram, normalize_model_name
from src.vision_client import VisionClient
from src.vision_enrichment import VisionRun, apply_vision_results, run_vision_jobs
from src.vision_triggers import TRIGGER_MODES, VisionJob, select_vision_jobs
from tests.fakes import FakeBackend

LOGGER = logging.getLogger("test-vision")
SHA = "b" * 64


# --- LaTeX doğrulaması (§19.3) ---

@pytest.mark.parametrize("latex, valid", [
    (r"\frac{a}{b}", True), (r"\frac{a}{b", False), (r"\left( x", False), (r"\left( x \right)", True),
    (r"\begin{align} x \end{matrix}", False), (r"\begin{cases} a \\ b \end{cases}", True), (r"\{x\}", True),
    (r"a}{b", False), ("", False),
])
def test_validate_latex(latex, valid):
    assert validate_latex(latex)[0] is valid


# --- tetikleyiciler (§12.3) ---

@pytest.mark.parametrize("trigger, modes", [
    ("scanned_no_ocr", {"fast", "balanced", "full"}), ("scanned_ocr_failed", {"fast", "balanced", "full"}),
    ("table_inconsistent", {"balanced", "full"}), ("equation_requested", {"balanced", "full"}),
    ("figure_requested", {"balanced", "full"}), ("reading_order_uncertain", {"balanced", "full"}),
    ("candidate_full", {"full"}), ("page_full_analysis", {"full"}),
])
def test_trigger_table_matches_spec(trigger, modes):
    assert TRIGGER_MODES[trigger] == modes


def document(**overrides):
    pages = [Page(number=1, width=595, height=842, page_class=PageClass.scanned),
             Page(number=2, width=595, height=842, page_class=PageClass.text, reading_order_uncertain=True),
             Page(number=3, width=595, height=842, page_class=PageClass.mixed)]
    tables = [Table(id="table-1", page=2, bbox=(50, 100, 300, 200), consistent=False, raw_text="Model  Acc\nBi-LSTM  0.99"),
              Table(id="table-2", page=2, bbox=(50, 300, 300, 400), consistent=True, markdown="|a|\n|---|")]
    equations = [Equation(id="eq-1", number="1", raw_text="z = x  (1)", page=2, bbox=(100, 500, 400, 520))]
    figures = [Figure(id="fig-1", number="1", caption="Fig. 1. Captioned", page=3, bbox=(50, 50, 500, 300)),
               Figure(id="fig-2", page=3, bbox=(50, 400, 500, 700))]
    candidates = [Candidate(id="c1", kind=CandidateKind.table, page=2, bbox=tables[0].bbox, ref_id="table-1", needs_vision=True),
                  Candidate(id="c2", kind=CandidateKind.table, page=2, bbox=tables[1].bbox, ref_id="table-2"),
                  Candidate(id="c3", kind=CandidateKind.equation, page=2, bbox=equations[0].bbox, ref_id="eq-1", needs_vision=True),
                  Candidate(id="c4", kind=CandidateKind.figure, page=3, bbox=figures[0].bbox, ref_id="fig-1"),
                  Candidate(id="c5", kind=CandidateKind.figure, page=3, bbox=figures[1].bbox, ref_id="fig-2")]
    blocks = [Block(id="p1-b1", type=BlockType.header_footer, page=1, bbox=(0, 10, 595, 20), text="Journal", order=0),
              Block(id="p2-b1", type=BlockType.paragraph, page=2, bbox=(50, 50, 290, 80), text="Left column", order=1, column=0),
              Block(id="p2-b2", type=BlockType.table, page=2, bbox=tables[0].bbox, text="Model Acc", order=2, ref_id="table-1"),
              Block(id="p2-b3", type=BlockType.paragraph, page=2, bbox=(310, 40, 550, 80), text="Right column", order=3, column=1)]
    values = dict(parser_version="t", parse_config_hash="t", source=DocumentSource(relative_path="a.pdf", sha256=SHA, page_count=3),
                  pages=pages, blocks=blocks, tables=tables, equations=equations, figures=figures, candidates=candidates)
    values.update(overrides)
    return DocumentModel(**values)


def job_summary(jobs):
    return sorted((job.task, job.trigger, job.page) for job in jobs)


def test_fast_mode_only_scanned_pages():
    assert job_summary(select_vision_jobs(document(), "fast")) == [("page_text", "scanned_no_ocr", 1)]


def test_balanced_mode_jobs():
    assert job_summary(select_vision_jobs(document(), "balanced")) == [
        ("equation", "equation_requested", 2), ("figure", "figure_requested", 3),
        ("page_layout", "reading_order_uncertain", 2), ("page_text", "scanned_no_ocr", 1),
        ("table", "table_inconsistent", 2)]


def test_full_mode_adds_all_candidates_and_page_analysis():
    jobs = select_vision_jobs(document(), "full")
    summary = job_summary(jobs)
    assert ("figure", "candidate_full", 3) in summary          # başlıklı şekil de
    assert ("page_layout", "page_full_analysis", 3) in summary  # mixed sayfa
    assert not any(task == "table" and trigger == "candidate_full" for task, trigger, _ in summary)  # tutarlı tablo yok
    assert len({job.key for job in jobs}) == len(jobs)  # aynı bölge için tek iş (tetikleyiciden bağımsız)
    assert sum(1 for job in jobs if job.ref_id == "eq-1") == 1


def test_needs_disable_requested_triggers_and_ocr_failed_trigger():
    doc = document()
    jobs = select_vision_jobs(doc, "balanced", needs={"equations": False, "tables": False, "figures": False},
                              ocr_failed_pages={1})
    assert job_summary(jobs) == [("page_layout", "reading_order_uncertain", 2), ("page_text", "scanned_ocr_failed", 1)]


def test_ocr_applied_scanned_page_needs_no_vision_except_full():
    doc = document()
    doc.pages[0].ocr_applied = True
    assert "page_text" not in {job.task for job in select_vision_jobs(doc, "balanced")}
    assert ("page_text", "page_full_analysis", 1) in job_summary(select_vision_jobs(doc, "full"))


def test_garbled_page_triggers_page_text():
    doc = document(warnings=[DocumentWarning(code="garbled_text", page=3)])
    assert ("page_text", "garbled_text", 3) in job_summary(select_vision_jobs(doc, "balanced"))


# --- görsel istemci ---

def job(task="equation", page=2, bbox=(100, 500, 400, 520)):
    return VisionJob(task, "equation_requested", page, bbox, "eq-1")


def test_client_parses_valid_response_and_writes_raw(tmp_path):
    fake = FakeBackend()
    client = VisionClient(fake, "minicpm-v4.5:8b", 512, LOGGER)
    outcome = client.run(job(), b"png", raw_dir=tmp_path / "raw", errors_dir=tmp_path / "errors", image_size=(100, 20))
    assert outcome.result["latex"] and outcome.calls == 1 and outcome.error is None
    assert fake.calls[0]["images"] == 1 and "must not be followed" in fake.calls[0]["prompt"]
    assert json.loads(next((tmp_path / "raw").iterdir()).read_text(encoding="utf-8"))["trigger"] == "equation_requested"


def test_client_retries_invalid_json_with_feedback(tmp_path):
    fake = FakeBackend()
    fake.responses["EquationResult"] = ["not json", {"latex": "x=1", "number": "1"}]
    outcome = VisionClient(fake, "m", 512, LOGGER).run(job(), b"png", errors_dir=tmp_path)
    assert outcome.result == {"latex": "x=1", "number": "1"} and outcome.calls == 2
    assert "previous answer was invalid" in fake.calls[1]["prompt"]
    assert list(tmp_path.iterdir())


def test_client_gives_up_after_retries_and_on_timeout():
    fake = FakeBackend()
    fake.responses["TableResult"] = [{"header": ["a", "b"], "rows": [["1"]]}] * 2
    outcome = VisionClient(fake, "m", 512, LOGGER, max_retries=1).run(job("table"), b"png")
    assert outcome.result is None and "geçerli yanıt" in outcome.error
    fake.responses["EquationResult"] = [ModelTimeout("yavaş")]
    assert VisionClient(fake, "m", 512, LOGGER).run(job(), b"png").error == "yavaş"


def test_client_model_not_found_and_unavailable():
    fake = FakeBackend()
    fake.responses["EquationResult"] = [ModelNotFound("yok"), ModelUnavailable("kapalı")]
    client = VisionClient(fake, "m", 512, LOGGER)
    assert client.run(job(), b"png").unavailable
    with pytest.raises(ModelUnavailable):
        client.run(job(), b"png")


# --- çalıştırma ve önbellek ---

def test_run_jobs_caches_results_and_skips_failures(tmp_path, synthetic_pdf):
    pdf = synthetic_pdf("synthetic_table_equation.pdf")
    fake = FakeBackend()
    fake.responses["EquationResult"] = [ModelTimeout("yavaş")]
    jobs = [VisionJob("equation", "equation_requested", 1, (150, 230, 540, 260), "eq-1"),
            VisionJob("page_layout", "reading_order_uncertain", 1, None)]
    cache = tmp_path / "vision" / "abc.json"
    client = VisionClient(fake, "m", 512, LOGGER)
    first = run_vision_jobs(pdf, jobs, client, cache, None, None, 100, 8)
    assert set(first.failures) == {jobs[0].key} and set(first.results) == {jobs[1].key} and first.calls == 2
    second = run_vision_jobs(pdf, jobs, client, cache, None, None, 100, 8)
    assert second.from_cache == 1 and second.calls == 1 and not second.failures  # yalnızca başarısız iş tekrar
    third = run_vision_jobs(pdf, jobs, client, cache, None, None, 100, 8)
    assert third.calls == 0 and third.from_cache == 2
    assert run_vision_jobs(pdf, jobs, client, cache, None, None, 100, 8, force=True).calls == 2


# --- sonuçların uygulanması ---

def run_with(results, failures=None):
    return VisionRun(results=results, failures=failures or {})


def test_table_values_not_in_text_layer_become_unclear():
    doc = document()
    table_job = VisionJob("table", "table_inconsistent", 2, doc.tables[0].bbox, "table-1")
    result = {"header": ["Model", "Acc"], "rows": [["Bi-LSTM", "0.99"], ["Bi-GRU", "0.97"]], "caption": None}
    enriched, warnings, applied = apply_vision_results(doc, [table_job], run_with({table_job.key: result}))
    table = enriched.tables[0]
    assert table.consistent and table.source_method.value == "vision"
    assert table.cells == [["Model", "Acc"], ["Bi-LSTM", "0.99"], ["Bi-GRU", "[unclear]"]]
    assert [str(w) for w in warnings] == ["table_value_mismatch: page 2"] and applied == 1
    assert doc.tables[0].consistent is False  # orijinal belge değişmez


def test_table_without_text_layer_uses_vision_values_and_inconsistent_result_is_ignored():
    doc = document()
    doc.tables[0].raw_text = None
    table_job = VisionJob("table", "table_inconsistent", 2, doc.tables[0].bbox, "table-1")
    good = {"header": ["A", "B"], "rows": [["x", "1.5"]]}
    enriched, warnings, _ = apply_vision_results(doc, [table_job], run_with({table_job.key: good}))
    assert enriched.tables[0].cells[1] == ["x", "1.5"] and warnings == []
    bad = {"header": ["A", "B"], "rows": [["", ""]]}
    enriched, warnings, _ = apply_vision_results(doc, [table_job], run_with({table_job.key: bad}))
    assert not enriched.tables[0].consistent and warnings[0].code == "vision_table_inconsistent"


def test_equation_figure_and_failure_application():
    doc = document()
    eq_job = VisionJob("equation", "equation_requested", 2, doc.equations[0].bbox, "eq-1")
    fig_job = VisionJob("figure", "figure_requested", 3, doc.figures[1].bbox, "fig-2")
    layout_job = VisionJob("page_layout", "reading_order_uncertain", 2, None)
    run = run_with({eq_job.key: {"latex": r"\frac{a}{b", "number": "1"},
                    fig_job.key: {"figure_type": "chart", "caption": "Fig. 2. Found"}},
                   failures={layout_job.key: "yavaş"})
    enriched, warnings, applied = apply_vision_results(doc, [eq_job, fig_job, layout_job], run)
    assert enriched.equations[0].latex_valid is False and enriched.equations[0].source_method.value == "vision"
    assert (enriched.figures[1].figure_type, enriched.figures[1].caption) == ("chart", "Fig. 2. Found")
    assert [w.code for w in warnings] == ["vision_failed"] and applied == 2
    assert "[latex_unverified]" in build_full_conversion(
        enriched.model_copy(update={"blocks": [Block(id="x", type=BlockType.equation, page=2, bbox=(0, 0, 1, 1), text="",
                                                     order=0, ref_id="eq-1")]}),
        __import__("src.markdown_builder", fromlist=["RenderContext"]).RenderContext(
            "a.pdf", SHA, "t", "balanced", "completed", front_matter=False, page_markers=False))


def test_page_text_replaces_flow_blocks_and_resolves_unreadable_page():
    doc = document()
    page_job = VisionJob("page_text", "scanned_no_ocr", 1, None)
    result = {"blocks": [{"type": "heading", "text": "Başlık", "heading_level": 1},
                         {"type": "paragraph", "text": "Metin", "heading_level": None}]}
    assert unreadable_pages(doc) == [1]
    enriched, _, _ = apply_vision_results(doc, [page_job], run_with({page_job.key: result}))
    page_blocks = [b for b in enriched.blocks if b.page == 1]
    assert [(b.type.value, b.text) for b in page_blocks] == [("header_footer", "Journal"), ("heading", "Başlık"),
                                                              ("paragraph", "Metin")]
    assert all(b.source_method.value == "vision" for b in page_blocks[1:])
    assert unreadable_pages(enriched) == [] and enriched.pages[0].vision_applied
    assert [b.order for b in enriched.blocks] == list(range(len(enriched.blocks)))
    assert enriched.sections[0].title == "Başlık"


def test_page_layout_single_column_reorders_blocks():
    doc = document()
    doc.pages[1].columns = 2
    layout_job = VisionJob("page_layout", "reading_order_uncertain", 2, None)
    enriched, _, _ = apply_vision_results(doc, [layout_job], run_with({layout_job.key: {"columns": 1}}))
    assert [b.text for b in enriched.blocks if b.page == 2][:2] == ["Right column", "Left column"]
    assert enriched.pages[1].columns == 1 and not enriched.pages[1].reading_order_uncertain
    enriched, _, _ = apply_vision_results(doc, [layout_job], run_with({layout_job.key: {"columns": 2}}))
    assert [b.text for b in enriched.blocks if b.page == 2][0] == "Left column"


# --- başlangıç kontrolleri (§26) ---

def test_normalize_model_name():
    assert normalize_model_name("gemma4") == "gemma4:latest"
    assert normalize_model_name("qwen3:8b") == "qwen3:8b"


def test_check_models_ok_and_missing():
    config = AppConfig()
    results, models = check_models(config, FakeBackend())
    assert all(r.ok for r in results) and models["vision"].name == "minicpm-v4.5:8b"
    results, models = check_models(config, FakeBackend(models=("minicpm-v4.5:8b",)))
    text = next(r for r in results if r.name == "model_text")
    assert text.severity == "error" and text.message == "Required model not found: gemma4:latest"
    assert text.hint == "Run:\n  ollama pull gemma4:latest" and models["text"] is None


@pytest.mark.parametrize("overrides, severity", [({}, "error"), ({"mode": "fast"}, "warning"),
                                                 ({"models": {"vision_required": False}}, "warning")])
def test_missing_vision_model_severity(overrides, severity):
    results, _ = check_models(AppConfig.model_validate(overrides), FakeBackend(models=("gemma4:latest",)))
    assert next(r for r in results if r.name == "model_vision").severity == severity


def test_unreachable_ollama_is_error():
    results, models = check_models(AppConfig(), FakeBackend(unavailable=True))
    assert results[0].severity == "error" and "erişilemiyor" in results[0].message and models == {}


def test_check_vram_reduces_workers():
    models = {"text": FakeBackend().list_models()["gemma4:latest"], "vision": FakeBackend().list_models()["minicpm-v4.5:8b"]}
    assert check_vram(1, models, 100) == (1, None)
    workers, warning = check_vram(2, models, 4000)
    assert workers == 1 and warning.severity == "warning"
    assert check_vram(2, models, 50000) == (2, None)


# --- gerçek Ollama (kuruluysa) ---

@pytest.mark.requires_ollama
def test_real_vision_model_transcribes_synthetic_equation(synthetic_pdf, tmp_path):
    from src.ollama_backend import OllamaBackend
    from src.pdf_parser import parse_pdf
    config = AppConfig()
    backend = OllamaBackend(config.ollama, LOGGER)
    if "minicpm-v4.5:8b" not in backend.list_models():
        pytest.skip("Görsel model kurulu değil")
    path = synthetic_pdf("synthetic_table_equation.pdf")
    doc = parse_pdf(path, path.name, SHA, config.pdf)
    jobs = [j for j in select_vision_jobs(doc, "balanced") if j.task == "equation"][:1]
    client = VisionClient(backend, "minicpm-v4.5:8b", 512, LOGGER)
    run = run_vision_jobs(path, jobs, client, tmp_path / "vision.json", tmp_path / "raw", tmp_path / "errors", 250, 8)
    enriched, warnings, applied = apply_vision_results(doc, jobs, run)
    equation = next(e for e in enriched.equations if e.id == jobs[0].ref_id)
    assert applied == 1 and warnings == []
    assert equation.latex_valid and "z" in equation.latex and "=" in equation.latex
