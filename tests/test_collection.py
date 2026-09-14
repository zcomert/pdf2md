import json
from pathlib import Path

import pytest

from src.cli import EXIT_DOC_FAILED, EXIT_OK, EXIT_PREFLIGHT, main
from src.model_clients import ModelUnavailable
from src.paths import collection_safe_name

# Belgeler göreli yola göre sıralı: P1 single_column, P2 table_equation, P3 two_column
DOCS = ("synthetic_single_column.pdf", "synthetic_table_equation.pdf", "synthetic_two_column.pdf")
NOT_FOUND = {"dataset.name": {"status": "not_found", "value": None, "evidence": []},
             "results.best": {"status": "not_found", "value": None, "evidence": []}}


def extraction(fields=None, results=()):
    return {"fields": {**NOT_FOUND, **(fields or {})}, "results": list(results), "equations": [], "tables": []}


TABLE_DOC = extraction(
    {"results.best": {"status": "found", "value": "Bi-LSTM", "evidence": [{"block_id": "p1-b4", "page": 1}]}},
    [{"field": "results.best", "claim": "Bi-LSTM", "model": "Bi-LSTM", "metric": "Accuracy", "value_text": "0.99",
      "dataset": None, "evidence": [{"block_id": "p1-b4", "page": 1}]},
     {"field": "results.best", "claim": "SVM", "model": "SVM", "metric": "Accuracy", "value_text": "0.97",
      "dataset": None, "evidence": [{"block_id": "p1-b4", "page": 1}]}])
SYNTHESIS = {"sections": [
    {"heading": "Veri Setleri", "claims": [
        {"text": "Veri seti adı hiçbir makalede belirtilmemiştir.", "paper_ids": ["P1", "P2", "P3"]},
        {"text": "Kaynaksız genel bir iddia.", "paper_ids": []}]},
    {"heading": "En İyi Sonuçlar", "claims": [
        {"text": "En yüksek doğruluk Bi-LSTM ile 0.99 olarak raporlanmıştır.", "paper_ids": ["P2"]},
        {"text": "Bir makalede 0.97 doğruluk vardır.", "paper_ids": ["P2", "P9"]}]}]}


@pytest.fixture
def collection_config(tmp_path):
    path = tmp_path / "collection.yaml"
    path.write_text("ocr:\n  enabled: false\nsummary:\n  bibliographic_llm: false\n", encoding="utf-8")
    return path


def run(tmp_input_copy, tmp_output, config, *extra, docs=DOCS):
    includes = [arg for name in docs for arg in ("--include", name)]
    return main([str(tmp_input_copy), "--output", str(tmp_output), "--config", str(config), *includes,
                 "--prompt", "Veri setlerini ve en iyi sonuçları karşılaştır.", *extra])


def queue(backend, *extractions, synthesis=SYNTHESIS):
    backend.responses["LlmExtraction"] = [json.loads(json.dumps(item)) for item in extractions]
    backend.responses["SynthesisResponse"] = [json.loads(json.dumps(synthesis))]


def load_state(output):
    return json.loads((output / "processing_state.json").read_text(encoding="utf-8"))


def collection_files(output):
    return sorted((output / "collections").glob("*.md"))


def test_collection_end_to_end(tmp_input_copy, tmp_output, collection_config, fake_model_backend, capsys):
    queue(fake_model_backend, extraction(), TABLE_DOC, extraction())
    assert run(tmp_input_copy, tmp_output, collection_config) == EXIT_OK

    # §38 kriter 8: collections/ altında tek dosya, belge başına A.md yok
    files = collection_files(tmp_output)
    assert len(files) == 1 and files[0].name.startswith("dataset_comparison_")
    assert [p for p in tmp_output.rglob("*.md") if "collections" not in p.parts] == []
    markdown = files[0].read_text(encoding="utf-8")
    front = markdown.split("---")[1]
    assert "scope: collection" in front and "synthetic_table_equation.pdf" in front and "sha256:" in front
    assert "## Prompt\n\n> Veri setlerini ve en iyi sonuçları karşılaştır." in markdown
    assert "- İşlenen belge: 3" in markdown and "Makale kimliği olmayan 1 iddia çıkarıldı." in markdown

    # §38 kriter 9: her bulgu makale kimliği ve adıyla; sayısal bulgu sayfa ve tabloyla
    assert ("- En yüksek doğruluk Bi-LSTM ile 0.99 olarak raporlanmıştır. "
            "*(P2: Tables Equations and Figures, s. 1, Table 1)*") in markdown
    assert "Kaynaksız genel bir iddia" not in markdown
    # Doğrulanmamış sayı içeren iddia işaretli; geçersiz kimlik (P9) atılır
    assert "- Bir makalede 0.97 doğruluk vardır. [unverified] *(P2: Tables Equations and Figures)*" in markdown

    # Sentez girdisi: yalnızca doğrulanmış değerler, ham PDF metni yok
    synthesis_call = fake_model_backend.calls_for("SynthesisResponse")[0]
    assert '"value": "0.99"' in synthesis_call["prompt"] and "0.97" not in synthesis_call["prompt"]
    assert "physiological signals" not in synthesis_call["prompt"]
    records = json.loads(synthesis_call["prompt"].split("<records>")[1].split("</records>")[0])
    assert records[0]["not_found"] == ["dataset.name", "results.best"]  # eksik değer açıkça iletilir
    assert [r["value"] for r in records[1]["results"]] == ["0.99"]

    # Deterministik tablolar
    assert "## Makale Bazlı Bulgular" in markdown and "| P1 | not_found |" in markdown
    assert "| P2 | Bi-LSTM | Accuracy | 0.99 | - | (s. 1, Table 1) |" in markdown
    assert "| P2 | SVM |" not in markdown

    state = load_state(tmp_output)
    (collection,) = state["collections"].values()
    assert collection["documents"] == list(DOCS) and collection["output_path"].startswith("collections/")
    assert next(iter(state["runs"].values()))["collection_output"] == str(files[0])
    assert all(record["output_path"] is None for record in state["documents"].values())
    assert "Koleksiyon: " in capsys.readouterr().out


def test_unchanged_collection_is_skipped(tmp_input_copy, tmp_output, collection_config, fake_model_backend, capsys):
    queue(fake_model_backend, extraction(), TABLE_DOC, extraction())
    run(tmp_input_copy, tmp_output, collection_config)
    calls = len(fake_model_backend.calls)
    capsys.readouterr()
    assert run(tmp_input_copy, tmp_output, collection_config) == EXIT_OK
    output = capsys.readouterr().out
    assert len(fake_model_backend.calls) == calls and "skipped 3" in output
    assert "(değişmedi, sentez atlandı)" in output and len(collection_files(tmp_output)) == 1


def test_changed_pdf_reextracts_only_that_document(tmp_input_copy, tmp_output, collection_config, fake_model_backend,
                                                   capsys):
    queue(fake_model_backend, extraction(), TABLE_DOC, extraction())
    run(tmp_input_copy, tmp_output, collection_config)
    first = collection_files(tmp_output)
    extraction_calls = len(fake_model_backend.calls_for("LlmExtraction"))
    (tmp_input_copy / "synthetic_two_column.pdf").write_bytes(
        (tmp_input_copy / "synthetic_header_footer.pdf").read_bytes())
    queue(fake_model_backend, extraction())
    capsys.readouterr()
    assert run(tmp_input_copy, tmp_output, collection_config) == EXIT_OK
    assert len(fake_model_backend.calls_for("LlmExtraction")) == extraction_calls + 1
    assert "skipped 2" in capsys.readouterr().out
    files = collection_files(tmp_output)
    assert len(files) == 2 and first[0] in files  # eski dosya korunur, yeni zaman damgalı dosya
    assert len(load_state(tmp_output)["collections"]) == 2


def test_failed_documents_listed(tmp_input_copy, tmp_output, collection_config, fake_model_backend):
    queue(fake_model_backend, extraction(), TABLE_DOC)
    code = run(tmp_input_copy, tmp_output, collection_config, docs=("corrupt.pdf",) + DOCS[:2])
    assert code == EXIT_DOC_FAILED  # başarısız belge çıkış kodunu etkiler, koleksiyon yine yazılır
    markdown = collection_files(tmp_output)[0].read_text(encoding="utf-8")
    assert "## İşlenemeyen Belgeler" in markdown and "| corrupt.pdf | parse |" in markdown
    assert "- İşlenen belge: 2" in markdown and "- İşlenemeyen belge: 1" in markdown
    assert "corrupt.pdf" not in markdown.split("---")[1]  # front matter yalnızca sentezlenen belgeler


def test_collection_output_and_name_options(tmp_input_copy, tmp_output, tmp_path, collection_config,
                                            fake_model_backend, capsys):
    existing = tmp_path / "var.md"
    existing.write_text("eski", encoding="utf-8")
    assert run(tmp_input_copy, tmp_output, collection_config, "--collection-output", str(existing)) == EXIT_PREFLIGHT
    assert "zaten var" in capsys.readouterr().err and existing.read_text(encoding="utf-8") == "eski"
    inside = tmp_input_copy / "sonuc.md"
    assert run(tmp_input_copy, tmp_output, collection_config, "--collection-output", str(inside)) == EXIT_PREFLIGHT
    assert "giriş klasörünün içinde olamaz" in capsys.readouterr().err

    target = tmp_path / "raporlar" / "karşılaştırma.md"
    queue(fake_model_backend, extraction(), TABLE_DOC, extraction())
    assert run(tmp_input_copy, tmp_output, collection_config, "--collection-output", str(target)) == EXIT_OK
    assert target.is_file() and not (tmp_output / "collections").exists()
    assert load_state(tmp_output)["collections"].popitem()[1]["output_path"] == str(target)

    other = tmp_path / "out2"
    queue(fake_model_backend, synthesis=SYNTHESIS)
    assert run(tmp_input_copy, other, collection_config, "--collection-name", "Yorgunluk: Veri/Setleri") == EXIT_OK
    assert collection_files(other)[0].name.startswith("Yorgunluk_ Veri_Setleri_")


def test_synthesis_model_unavailable_stops(tmp_input_copy, tmp_output, collection_config, fake_model_backend, capsys):
    queue(fake_model_backend, extraction(), TABLE_DOC, extraction())
    fake_model_backend.responses["SynthesisResponse"] = [ModelUnavailable("kapalı")]
    assert run(tmp_input_copy, tmp_output, collection_config) == EXIT_DOC_FAILED
    assert "Batch durduruldu" in capsys.readouterr().err and not (tmp_output / "collections").exists()


def test_default_prompt_with_collection_scope_rejected(tmp_input_copy, tmp_output, collection_config, capsys):
    code = main([str(tmp_input_copy), "--output", str(tmp_output), "--config", str(collection_config),
                 "--scope", "collection"])
    assert code == EXIT_PREFLIGHT and "Koleksiyon kapsamı bir prompt gerektirir" in capsys.readouterr().err


@pytest.mark.parametrize("name, expected", [
    (None, "collection"), ("", "collection"), ("dataset_comparison", "dataset_comparison"),
    ("a" * 80, "a" * 50), ("CON", "_CON"), ("veri: setleri?", "veri_ setleri"),
])
def test_collection_safe_name(name, expected):
    assert collection_safe_name(name) == expected


@pytest.mark.requires_ollama
def test_real_synthesis_cites_papers(tmp_path):
    import logging

    from src.collection_analyzer import PaperEntry, synthesize
    from src.config import AppConfig
    from src.llm_client import TextClient
    from src.ollama_backend import OllamaBackend
    from src.schemas import Bibliographic, Evidence, Extraction, ExtractionSource, FieldValue, ProcessingPlan, ResultItem

    def paper(pid, name, dataset, model, value):
        evidence = [Evidence(page=3, block_id="p3-b1", table="Table 2", source_method="text", resolved=True)]
        extraction = Extraction(
            source=ExtractionSource(path=name, sha256=pid[-1] * 64), plan_hash="h",
            fields={"dataset.name": FieldValue(value=[dataset], status="found", evidence=evidence, in_evidence=True,
                                                confidence="high"),
                    "results.best": FieldValue(status="found")},
            results=[ResultItem(field="results.best", claim=f"{model} best", model=model, metric="Accuracy",
                                value=float(value), value_text=value, evidence=evidence, verification="verified",
                                confidence="high")])
        return PaperEntry(pid, name, pid[-1] * 64, extraction, Bibliographic(title=name, year=2024))

    entries = [paper("P1", "a.pdf", "DROZY", "Bi-LSTM", "0.99"), paper("P2", "b.pdf", "NTHU-DDD", "SVM", "0.91")]
    plan = ProcessingPlan(scope="collection", scope_reason="t", requested_fields=["dataset.name", "results.best"],
                          comparison_dimensions=["dataset", "results"], output_language="tr",
                          output_outline=["Veri Setleri", "En İyi Sonuçlar"])
    config = AppConfig()
    client = TextClient(OllamaBackend(config.ollama, logging.getLogger("t")), config.models.text, 16384, 4096,
                        logging.getLogger("t"))
    result = synthesize(entries, plan, "Veri setlerini ve en iyi sonuçları karşılaştır.", client, 1, 16384, 4096,
                        errors_dir=tmp_path)
    claims = [claim for section in result.sections.values() for claim in section]
    assert claims and all(paper_ids for _, paper_ids, _ in claims)
    assert not any(marked for _, _, marked in claims), claims  # yalnızca kayıttaki sayılar kullanıldı
    assert {"P1", "P2"} <= {pid for _, paper_ids, _ in claims for pid in paper_ids}
