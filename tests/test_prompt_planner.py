import json
import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.cli import EXIT_OK, main
from src.default_prompt import resolve_prompt
from src.field_catalog import FIELDS, FULL_CONVERSION, catalog_needs, custom_key, resolve_alias
from src.llm_client import TextClient, estimate_tokens
from src.model_clients import ModelInfo, ModelUnavailable
from src.prompt_planner import (PlanContext, compute_plan_hash, create_plan, default_plan, detect_language,
                                filter_targets, finalize_plan, normalize_plan_data)
from src.schemas import ProcessingPlan
from tests.fakes import FAKE_PLAN, FakeBackend

LOGGER = logging.getLogger("test-planner")
TEXT = ModelInfo("gemma4:latest", "a" * 64)
VISION = ModelInfo("minicpm-v4.5:8b", "b" * 64)
FOLDER = PlanContext(input_is_file=False, pdf_count=3)


def prompt_of(text=None, prompt_file=None, config=None):
    from src.config import AppConfig
    return resolve_prompt(SimpleNamespace(prompt=text, prompt_file=prompt_file), config or AppConfig())


def client(backend):
    return TextClient(backend, TEXT.name, 16384, 4096, LOGGER)


def plan_with(**changes):
    return ProcessingPlan.model_validate({**FAKE_PLAN, **changes})


# --- Katalog ve şema ----------------------------------------------------------------------------------------------

def test_catalog_covers_section_17_3_groups():
    assert {spec.group for spec in FIELDS.values()} == {"bibliographic", "research", "dataset", "methodology",
                                                        "results", "equations", "evaluation"}
    assert resolve_alias("title") == "bibliographic.title" and resolve_alias("unknown") is None
    assert custom_key("Etik Kurul Onayı") == "custom.etik_kurul_onayi"


def test_catalog_needs():
    assert catalog_needs(["results.best"])["tables"] is True
    assert catalog_needs(["equations.important"]) == {"tables": False, "equations": True, "figures": False,
                                                      "full_text": False}
    assert all(catalog_needs([FULL_CONVERSION]).values())


def test_plan_schema_rejects_unknown_fields_and_empty_outline():
    with pytest.raises(ValidationError, match="unknown fields"):
        plan_with(requested_fields=["dataset.size"])
    with pytest.raises(ValidationError):
        plan_with(output_outline=[])
    with pytest.raises(ValidationError, match="not listed"):
        plan_with(custom_fields=[{"key": "custom.ethics", "description": "x"}])


def test_normalize_maps_aliases_and_custom_fields():
    data = normalize_plan_data({**FAKE_PLAN, "requested_fields": ["title", "Ethics approval", "title",
                                                                  "custom.code_link"],
                                "custom_fields": [{"key": "custom.code_link", "description": "Kod bağlantısı"}]})
    assert data["requested_fields"] == ["bibliographic.title", "custom.ethics_approval", "custom.code_link"]
    assert {item["key"]: item["description"] for item in data["custom_fields"]} == {
        "custom.ethics_approval": "Ethics approval", "custom.code_link": "Kod bağlantısı"}
    ProcessingPlan.model_validate(data)


# --- Prompt kaynağı -----------------------------------------------------------------------------------------------

def test_prompt_source_priority(tmp_path):
    from src.config import AppConfig
    file_prompt = tmp_path / "p.md"
    file_prompt.write_text("Dosyadaki prompt", encoding="utf-8")
    config_file = tmp_path / "c.md"
    config_file.write_text("Config dosyası", encoding="utf-8")
    assert prompt_of("CLI", str(file_prompt)).source == "cli"
    assert prompt_of(None, str(file_prompt)).text == "Dosyadaki prompt"
    config = AppConfig(prompt="Config metni", prompt_file=str(config_file))
    assert prompt_of(None, None, config).text == "Config metni"
    assert prompt_of(None, None, AppConfig(prompt_file=str(config_file))).source == "config_file"
    assert prompt_of().is_default


# --- Planlama -----------------------------------------------------------------------------------------------------

def test_default_prompt_does_not_call_llm():
    backend = FakeBackend()
    result = create_plan(prompt_of(), FOLDER, client(backend), TEXT)
    assert result.source == "default" and not backend.calls
    assert result.plan.requested_fields == [FULL_CONVERSION] and result.plan.output_language == "source"


def test_llm_plan_merges_catalog_needs_and_sends_system_prompt():
    backend = FakeBackend()
    result = create_plan(prompt_of("Veri setlerini ve en iyi sonuçları karşılaştır."), FOLDER, client(backend), TEXT)
    assert result.source == "llm" and result.uses_text_model
    assert result.plan.scope == "collection"
    assert result.plan.needs.tables is True  # model false dedi; results.best tablo gerektirir
    call = backend.calls_for("ProcessingPlan")[0]
    assert "dataset.sample_count" in call["system"] and "<<<REQUEST" in call["prompt"]
    assert call["options"]["temperature"] == 0 and call["options"]["num_ctx"] == 16384


def test_invalid_plan_retried_once_then_default_with_warning(tmp_path):
    backend = FakeBackend()
    backend.responses["ProcessingPlan"] = ["{not json", {"scope": "document"}]
    result = create_plan(prompt_of("Başlıkları çıkar"), FOLDER, client(backend), TEXT, errors_dir=tmp_path)
    assert len(backend.calls) == 2 and result.source == "fallback"
    assert result.plan.requested_fields == [FULL_CONVERSION]
    assert result.warnings[0].startswith("plan_fallback_default")
    assert "Your previous answer was invalid" in backend.calls[1]["prompt"]
    assert len(list(tmp_path.glob("plan_*.json"))) == 2


def test_retry_success_after_invalid_answer():
    backend = FakeBackend()
    backend.responses["ProcessingPlan"] = [{"scope": "galaxy"}]
    result = create_plan(prompt_of("Veri setlerini çıkar"), FOLDER, client(backend), TEXT)
    assert result.source == "llm" and len(backend.calls) == 2


def test_model_unavailable_propagates():
    backend = FakeBackend()
    backend.responses["ProcessingPlan"] = [ModelUnavailable("kapalı")]
    with pytest.raises(ModelUnavailable):
        create_plan(prompt_of("Veri setlerini çıkar"), FOLDER, client(backend), TEXT)


def test_cli_scope_overrides_plan():
    plan, _ = finalize_plan(plan_with(), PlanContext(False, 3, cli_scope="document"), "karşılaştır")
    assert plan.scope == "document" and "--scope document" in plan.scope_reason
    assert plan.collection_name_suggestion is None


def test_single_pdf_input_forces_document_scope():
    # §38 kriter 8: tek PDF + karşılaştırma promptu (auto) → document
    plan, _ = finalize_plan(plan_with(), PlanContext(True, 1), "Veri setlerini karşılaştır")
    assert plan.scope == "document"
    plan, _ = finalize_plan(plan_with(), PlanContext(True, 1, cli_scope="collection"), "")
    assert plan.scope == "collection"


def test_cli_include_overrides_targets_and_filter():
    docs = [SimpleNamespace(relative_path=name) for name in ("2024_a.pdf", "2025_b.pdf")]
    planned = plan_with(targets={"include": ["2024*.pdf"]})
    plan, _ = finalize_plan(planned, FOLDER, "")
    assert [d.relative_path for d in filter_targets(docs, plan, FOLDER)] == ["2024_a.pdf"]
    context = PlanContext(False, 2, cli_include=("2025*.pdf",))
    plan, _ = finalize_plan(planned, context, "")
    assert plan.targets.include == ["2025*.pdf"] and len(filter_targets(docs, plan, context)) == 2


def test_collection_without_dimensions_warns():
    _, warnings = finalize_plan(plan_with(comparison_dimensions=[]), FOLDER, "")
    assert warnings and warnings[0].startswith("plan_no_comparison_dimensions")


@pytest.mark.parametrize("text, expected", [
    ("Veri setlerini karşılaştır", "tr"),
    ("Extract datasets and best results", "en"),
    ("Extract datasets, answer in Turkish", "tr"),
    ("Veri setlerini İngilizce yaz", "en"),
    ("veri seti ve sonuc", "tr"),
])
def test_language_fallback(text, expected):
    assert detect_language(text) == expected
    plan, _ = finalize_plan(plan_with(output_language=" "), FOLDER, text)
    assert plan.output_language == expected


def test_plan_cache_reused_and_force_skips(tmp_path):
    backend = FakeBackend()
    prompt = prompt_of("Veri setlerini karşılaştır")
    first = create_plan(prompt, FOLDER, client(backend), TEXT, cache_dir=tmp_path)
    second = create_plan(prompt, FOLDER, client(backend), TEXT, cache_dir=tmp_path)
    assert (first.source, second.source, len(backend.calls)) == ("llm", "cache", 1)
    assert second.plan == first.plan
    create_plan(prompt, FOLDER, client(backend), TEXT, cache_dir=tmp_path, force=True)
    assert len(backend.calls) == 2
    other_model = ModelInfo(TEXT.name, "c" * 64)
    create_plan(prompt, FOLDER, client(backend), other_model, cache_dir=tmp_path)
    assert len(backend.calls) == 3


def test_plan_cache_not_written_when_disabled(tmp_path):
    create_plan(prompt_of("Veri setlerini karşılaştır"), FOLDER, client(FakeBackend()), TEXT, cache_dir=tmp_path,
                write_cache=False)
    assert not list(tmp_path.glob("*.json"))


# --- Plan hash ----------------------------------------------------------------------------------------------------

def test_plan_hash_properties():
    plan = default_plan()
    base = compute_plan_hash(plan, "p", "balanced", TEXT, VISION)
    assert base == compute_plan_hash(plan, "p", "balanced", TEXT, VISION)
    assert base != compute_plan_hash(plan, "p", "fast", TEXT, VISION)
    assert base != compute_plan_hash(plan, "q", "balanced", TEXT, VISION)
    assert base != compute_plan_hash(plan, "p", "balanced", TEXT, ModelInfo(VISION.name, "d" * 64))
    # Varsayılan plan metin modelini kullanmaz: metin modeli digest'i hash'i değiştirmez.
    assert base == compute_plan_hash(plan, "p", "balanced", ModelInfo(TEXT.name, "e" * 64), VISION)
    llm = compute_plan_hash(plan, "p", "balanced", TEXT, VISION, uses_text_model=True)
    assert llm != compute_plan_hash(plan, "p", "balanced", ModelInfo(TEXT.name, "e" * 64), VISION,
                                    uses_text_model=True)
    # Hedef filtresi hash'e girmez
    assert base == compute_plan_hash(plan.model_copy(update={"targets": {"include": ["a*.pdf"]}}), "p", "balanced",
                                     TEXT, VISION)


def test_estimate_tokens():
    assert estimate_tokens("a" * 35) == 10


# --- CLI ----------------------------------------------------------------------------------------------------------

def test_plan_only_prints_collection_plan_without_processing(tmp_input_copy, tmp_output, capsys, fake_model_backend):
    code = main([str(tmp_input_copy), "--output", str(tmp_output), "--plan-only",
                 "--prompt", "Veri setlerini ve en iyi sonuçları karşılaştır."])
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "Kapsam: collection" in out and "dataset.name (Veri seti adı)" in out and "plan_hash: " in out
    assert "synthetic_single_column.pdf" in out and "PDF işlenmedi" in out
    assert not tmp_output.exists()
    assert not fake_model_backend.calls_for("TableResult")


def test_plan_only_single_pdf_is_document_scope(tmp_input_copy, tmp_output, capsys):
    code = main([str(tmp_input_copy / "synthetic_single_column.pdf"), "--output", str(tmp_output), "--plan-only",
                 "--prompt", "Veri setlerini karşılaştır."])
    assert code == EXIT_OK and "Kapsam: document" in capsys.readouterr().out


def test_plan_only_scope_flag_overrides(tmp_input_copy, tmp_output, capsys):
    main([str(tmp_input_copy), "--output", str(tmp_output), "--plan-only", "--scope", "document",
          "--prompt", "Veri setlerini karşılaştır."])
    assert "Kapsam: document — --scope document" in capsys.readouterr().out


def test_run_records_plan_hash_in_state_and_summary(tmp_input_copy, tmp_output, no_ocr_config, fake_model_backend):
    assert main([str(tmp_input_copy), "--output", str(tmp_output), "--config", str(no_ocr_config),
                 "--include", "synthetic_single_column.pdf"]) == EXIT_OK
    state = json.loads((tmp_output / "processing_state.json").read_text(encoding="utf-8"))
    record = state["documents"]["synthetic_single_column.pdf"]
    run = next(iter(state["runs"].values()))
    assert len(record["plan_hash"]) == 64 and run["plan_hash"] == record["plan_hash"]
    # Varsayılan promptta plan için çağrı yok; tek metin çağrısı künye adımı (Faz 11)
    assert run["text_llm_calls"] == 1 and not fake_model_backend.calls_for("ProcessingPlan")
    log = next((tmp_output / "logs").glob("*.log")).read_text(encoding="utf-8")
    assert f"plan_hash={record['plan_hash']}" in log


@pytest.mark.requires_ollama
@pytest.mark.parametrize("prompt, fields, scope", [
    ("Başlık, veri seti, yöntem ve en iyi sonuçları çıkar.", {"bibliographic.title", "dataset.name", "results.best"},
     "document"),
    ("Bu makale grubunu akademik olarak özetle.", set(), "collection"),
    ("İlgili makalelerde kullanılan veri setlerini karşılaştır.", {"dataset.name"}, "collection"),
    ("Çalışmaların özgün yönlerini ve ortak katkılarını çıkar.", {"research.contributions"}, "collection"),
    ("Kullanılan yöntemleri, modelleri ve performans metriklerini tablo halinde karşılaştır.",
     {"methodology.models", "results.metrics"}, "collection"),
    ("Sınırlılıkları ve gelecek çalışma önerilerini sentezle.", {"evaluation.limitations", "evaluation.future_work"},
     "collection"),
])
def test_real_planner_produces_valid_plans(prompt, fields, scope, tmp_path):
    from src.config import AppConfig
    from src.ollama_backend import OllamaBackend
    config = AppConfig()
    backend = OllamaBackend(config.ollama, LOGGER)
    text = backend.list_models()[config.models.text]
    result = create_plan(prompt_of(prompt), PlanContext(False, 9), client(backend), text, errors_dir=tmp_path)
    snapshot = tmp_path / "plan.json"
    snapshot.write_text(result.plan.model_dump_json(indent=2), encoding="utf-8")
    assert result.source == "llm", result.warnings
    assert fields <= set(result.plan.requested_fields), result.plan.requested_fields
    assert result.plan.scope == scope and result.plan.output_language == "tr"
