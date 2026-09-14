"""Doğruluk ölçümü (§38 kriter 21–22): referans verili makalelerde mod bazında künye, tablo hücresi, formül ve
sayısal sonuç doğruluğu.

Kullanım:
    .venv\\Scripts\\python.exe tools\\evaluate.py [--modes fast balanced full] [--work reports\\eval_work]

Her mod için ayrı çıktı klasöründe iki çalıştırma yapılır:
  A) varsayılan prompt (tam dönüşüm) → tablolar ve formüller `.md` çıktısından, künye state'ten
  B) sonuç çıkarım promptu → doğrulanmış (`verified`) sonuçlar çıkarım dosyasından
Rapor: reports/accuracy_<tarih>.md ve .json
"""
import argparse
import difflib
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runner import RunOptions, run  # noqa: E402
from src.schemas import Extraction  # noqa: E402
from tests.reference_schema import load_reference, reference_files  # noqa: E402

RESULTS_PROMPT = "Makaledeki tüm sayısal sonuçları (model, metrik, değer ve veri seti) çıkar."


# --- Normalleştirme ----------------------------------------------------------------------------------------------

def norm_text(text):
    text = unicodedata.normalize("NFKC", str(text or "")).replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip().casefold()


def norm_cell(text):
    return re.sub(r"[\s*_`]", "", norm_text(text)).replace("−", "-").replace("–", "-")


def tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", norm_text(text)) if len(t) > 1 or t.isdigit()}


def norm_latex(latex):
    text = latex or ""
    for command in (r"\left", r"\right", r"\,", r"\!", r"\;", r"\:", r"\quad", r"\qquad", r"\displaystyle"):
        text = text.replace(command, "")
    text = re.sub(r"\\(?:mathrm|text|mathbf|boldsymbol|operatorname)\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:hat|bar|tilde)\s*\{([^{}]*)\}", r"\1", text)
    text = text.replace("\\times", "×").replace("*", "×").replace("\\cdot", "·")
    text = re.sub(r"[{}\s]", "", text)
    return text.replace("\\Sigma", "Σ").replace("\\sum", "Σ").casefold()


def number_values(value):
    """Karşılaştırma için değerin oran/yüzde karşılıkları."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return set()
    return {round(number, 6), round(number / 100, 6), round(number * 100, 6)}


def parse_number(text):
    match = re.search(r"-?\d+(?:[.,]\d+)?|-?[.,]\d+", str(text or "").replace(",", "."))
    if not match:
        return None
    raw = match.group(0)
    return float("0" + raw if raw.startswith(".") else raw)


# --- Çıktı ayrıştırma --------------------------------------------------------------------------------------------

def markdown_tables(markdown):
    tables, current = [], []
    for line in markdown.splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def markdown_equations(markdown):
    blocks = re.findall(r"\$\$\n(.*?)\n\$\$( \[latex_unverified\])?", markdown, flags=re.S)
    return [(latex.strip(), not flag) for latex, flag in blocks]


# --- Ölçütler ----------------------------------------------------------------------------------------------------

def score_bibliographic(reference, record):
    bib = (record or {}).get("bibliographic") or {}
    ref = reference.bibliographic
    ref_authors = {norm_text(a) for a in ref.authors}
    got_authors = {norm_text(a) for a in bib.get("authors") or []}
    scores = {
        "title": norm_text(re.sub(r"-\s+", "-", bib.get("title") or "")) == norm_text(ref.title),
        "authors": len(ref_authors & got_authors) / len(ref_authors) if ref_authors else None,
        "year": bib.get("year") == ref.year if ref.year else None,
        "venue": bool(bib.get("venue")) and (norm_text(ref.venue) in norm_text(bib["venue"])
                                             or norm_text(bib["venue"]) in norm_text(ref.venue)) if ref.venue else None,
        "doi": norm_text(bib.get("doi")) == norm_text(ref.doi) if ref.doi else None,
    }
    return scores


def score_tables(reference, markdown):
    found = markdown_tables(markdown)
    results = []
    for table in reference.tables:
        expected = [norm_cell(cell) for row in table.rows for cell in row if norm_cell(cell)]
        best, best_hits = None, 0
        for candidate in found:
            pool = [norm_cell(cell) for row in candidate for cell in row]
            hits = 0
            remaining = list(pool)
            for cell in expected:
                if cell in remaining:
                    remaining.remove(cell)
                    hits += 1
            if hits > best_hits:
                best, best_hits = candidate, hits
        # Yapılandırılmamış tablolar (ham metin + [table_structure_unavailable]) için hücre metninin çıktıda geçmesi
        text_tokens = re.findall(r"[^\s|]+", norm_text(markdown).replace("*", ""))
        in_text = sum(1 for cell in expected if cell in {norm_cell(t) for t in text_tokens} or cell in norm_cell(markdown))
        results.append({"table": table.number, "page": table.page, "cells": len(expected), "matched": best_hits,
                        "cells_in_text": in_text,
                        "cell_accuracy": round(best_hits / len(expected), 3) if expected else None,
                        "structured": best is not None})
    return results


def score_equations(reference, markdown):
    found = markdown_equations(markdown)
    normalized = [(norm_latex(latex), valid, latex) for latex, valid in found]
    results = []
    for equation in reference.equations:
        target = norm_latex(equation.latex)
        best_ratio, best = 0.0, None
        for candidate, valid, raw in normalized:
            ratio = difflib.SequenceMatcher(None, target, candidate).ratio()
            if ratio > best_ratio:
                best_ratio, best = ratio, (candidate, valid, raw)
        results.append({"number": equation.number, "page": equation.page, "exact": bool(best) and best[0] == target,
                        "similarity": round(best_ratio, 3), "latex_valid": best[1] if best else None,
                        "found": best[2] if best else None})
    return results, sum(1 for _, valid in found if valid) / len(found) if found else None


def model_match(reference_model, text):
    wanted = tokens(reference_model)
    have = tokens(text)
    return bool(wanted) and len(wanted & have) / len(wanted) >= 0.6


def metric_match(reference_metric, text):
    wanted, have = tokens(reference_metric), tokens(text)
    aliases = {"auc": {"auc", "roc"}, "f1": {"f1", "f", "fscore", "score"}, "accuracy": {"accuracy", "acc"}}
    for key, group in aliases.items():
        if key in wanted and have & group:
            return len((wanted - {key}) - have) == 0 or bool((wanted - {key}) & have)
    return bool(wanted) and len(wanted & have) / len(wanted) >= 0.6


def _jaccard(left, right):
    a, b = tokens(left), tokens(right)
    return len(a & b) / len(a | b) if a | b else 0.0


F_SCORE_RE = re.compile(r"\bf[\s_-]*1?[\s_-]*(?:score|measure)\b|\bf1\b")


def _metric_jaccard(left, right):
    return _jaccard(F_SCORE_RE.sub("f1", norm_text(left)), F_SCORE_RE.sub("f1", norm_text(right)))


def table_cell_verdict(reference, result):
    """Sonuç bir referans tablosunun satır/sütununa denk geliyorsa: True (hücre eşleşti), False (farklı hücre),
    None (tabloda karşılığı yok veya belirsiz). Satır, model adıyla en yüksek kelime örtüşmesine göre seçilir
    (MFCC-Bi-LSTM ile MFCC+Stat-Bi-LSTM karışmasın); sütun, metrik adıyla. Model adı birden çok satıra uyuyorsa
    ("Bi-LSTM") değer bu satırların hiçbirinin sütununda yoksa False."""
    value = result["value"]
    model_text = result["model"] or result["claim"]
    for table in reference.tables:
        headers = sorted(((_metric_jaccard(header, result["metric"] or ""), column)
                          for column, header in enumerate(table.header) if column), key=lambda item: -item[0])
        if not headers or headers[0][0] < 0.5 or (len(headers) > 1 and headers[1][0] == headers[0][0]):
            continue
        column = headers[0][1]
        scored = sorted(((_jaccard(row[0], model_text), row) for row in table.rows), key=lambda item: -item[0])
        if scored and scored[0][0] >= 0.6 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
            rows = [scored[0][1]]
        else:
            wanted = tokens(model_text)
            rows = [row for row in table.rows if wanted and wanted <= tokens(row[0])]
            if not rows:
                continue
        values = [parse_number(row[column]) for row in rows if column < len(row)]
        if any(number_values(cell) & number_values(value) for cell in values if cell is not None):
            return True if len(rows) == 1 else None
        if len(rows) == 1 and values[0] is None:
            continue
        return False
    return None


def score_results(reference, extraction):
    verified = []
    for item in extraction.results if extraction else []:
        if item.verification != "verified" or item.value is None:
            continue
        verified.append({"model": item.model or "", "metric": item.metric or "", "value": item.value,
                         "value_text": item.value_text, "claim": item.claim, "dataset": item.dataset or "",
                         "page": next((e.page for e in item.evidence if e.page), None)})
    matched_reference = 0
    for ref in reference.results:
        for item in verified:
            text = " ".join((item["model"], item["claim"], item["dataset"]))
            if number_values(ref.value) & number_values(item["value"]) and model_match(ref.model, text) \
                    and metric_match(ref.metric, item["metric"] + " " + item["claim"]):
                matched_reference += 1
                break
    contradictions, table_confirmed = [], 0
    for item in verified:
        verdict = table_cell_verdict(reference, item)
        if verdict is True:
            table_confirmed += 1
        elif verdict is False:
            contradictions.append(item)
    return {"reference_results": len(reference.results), "recall": round(matched_reference / len(reference.results), 3),
            "verified": len(verified), "table_confirmed": table_confirmed,
            "contradicting_verified": len(contradictions), "contradictions": contradictions}


# --- Çalıştırma --------------------------------------------------------------------------------------------------

def run_mode(mode, work, references):
    output = work / mode
    names = [ref.source.split("/", 1)[-1] for ref in references]
    includes = list(names)
    common = dict(input_dir=str(ROOT / "tests" / "fixtures" / "real"), output_dir=str(output), mode=mode,
                  include=includes, scope="document", console_logging=False)
    console = lambda text, error=False: print(f"  [{mode}] {text}")  # noqa: E731
    conversion = run(RunOptions(**common), console=console)
    # B çalıştırması aynı belge yollarına prompt cevabını yazar; tam dönüşüm çıktıları önce ayrı klasöre alınır.
    saved = work / f"{mode}_conversion"
    saved.mkdir(parents=True, exist_ok=True)
    for document in conversion.documents:
        if document.output_path and (output / document.output_path).is_file():
            target = saved / Path(document.relative_path).with_suffix(".md").name
            target.write_text((output / document.output_path).read_text(encoding="utf-8"), encoding="utf-8")
    extraction = run(RunOptions(**common, prompt=RESULTS_PROMPT), console=console)
    state = json.loads((output / "processing_state.json").read_text(encoding="utf-8"))
    return output, state, conversion, extraction


def evaluate(modes, work):
    references = [load_reference(path) for path in reference_files()]
    references = [ref for ref in references if ref.kind == "real" and ref.source_path.is_file()]
    report = {"generated": datetime.now().isoformat(timespec="seconds"), "prompt": RESULTS_PROMPT, "modes": {}}
    for mode in modes:
        print(f"== {mode}")
        output, state, conversion, extraction_run = run_mode(mode, work, references)
        per_paper = []
        for ref in references:
            name = ref.source.split("/", 1)[-1]
            record = state["documents"].get(name, {})
            extraction_file = None
            cache = output / "_cache" / ref.sha256 / "extractions"
            for path in sorted(cache.glob("*.json")) if cache.is_dir() else []:
                data = Extraction.model_validate_json(path.read_text(encoding="utf-8"))
                if any(key.startswith("results.") for key in data.fields):
                    extraction_file = data
            markdown = (work / f"{mode}_conversion" / name).with_suffix(".md")
            markdown_text = markdown.read_text(encoding="utf-8") if markdown.is_file() else ""
            tables = score_tables(ref, markdown_text)
            equations, valid_rate = score_equations(ref, markdown_text)
            per_paper.append({
                "paper": name, "bibliographic": score_bibliographic(ref, record), "tables": tables,
                "equations": equations, "latex_valid_rate": valid_rate,
                "results": score_results(ref, extraction_file),
            })
        report["modes"][mode] = {"papers": per_paper, "summary": summarize(per_paper)}
    return report


def summarize(papers):
    def mean(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 3) if values else None

    bib = [p["bibliographic"] for p in papers]
    return {
        "title": mean([1.0 if b["title"] else 0.0 for b in bib]),
        "authors": mean([b["authors"] for b in bib]),
        "year": mean([None if b["year"] is None else float(b["year"]) for b in bib]),
        "venue": mean([None if b["venue"] is None else float(b["venue"]) for b in bib]),
        "doi": mean([None if b["doi"] is None else float(b["doi"]) for b in bib]),
        "table_cells": round(sum(t["matched"] for p in papers for t in p["tables"])
                             / max(1, sum(t["cells"] for p in papers for t in p["tables"])), 3),
        "table_cells_in_text": round(sum(t["cells_in_text"] for p in papers for t in p["tables"])
                                     / max(1, sum(t["cells"] for p in papers for t in p["tables"])), 3),
        "equations_exact": mean([1.0 if e["exact"] else 0.0 for p in papers for e in p["equations"]]),
        "equations_similar_0_9": mean([1.0 if e["similarity"] >= 0.9 else 0.0 for p in papers for e in p["equations"]]),
        "latex_valid": mean([p["latex_valid_rate"] for p in papers]),
        "results_recall": mean([p["results"]["recall"] for p in papers]),
        "verified_results": sum(p["results"]["verified"] for p in papers),
        "table_confirmed_verified": sum(p["results"]["table_confirmed"] for p in papers),
        "contradicting_verified": sum(p["results"]["contradicting_verified"] for p in papers),
    }


def render_markdown(report):
    lines = [f"# Doğruluk Raporu — {report['generated'][:10]}", "",
             "Referans verili gerçek makaleler (§38.1, `tests/fixtures/reference/*.yaml`) üzerinde mod bazında ölçüm "
             "(§38 kriter 22). Tablo ve formüller varsayılan prompt çıktısından, künye state'ten, sayısal sonuçlar "
             f"\"{report['prompt']}\" promptunun doğrulanmış çıkarımından.", "",
             "| Ölçüt | " + " | ".join(report["modes"]) + " |", "|---|" + "---:|" * len(report["modes"])]
    labels = [("title", "Başlık (tam eşleşme)"), ("authors", "Yazarlar (referans yazar oranı)"), ("year", "Yıl"),
              ("venue", "Dergi/konferans"), ("doi", "DOI"), ("table_cells", "Tablo hücreleri (yapılandırılmış tabloda)"),
              ("table_cells_in_text", "Tablo hücre metni çıktıda (yapısız dahil)"),
              ("equations_exact", "Formül (normalize tam eşleşme)"), ("equations_similar_0_9", "Formül (benzerlik ≥ 0,9)"),
              ("latex_valid", "LaTeX geçerli oranı"), ("results_recall", "Sayısal sonuç geri çağırma (verified)"),
              ("verified_results", "Doğrulanmış sonuç sayısı"), ("table_confirmed_verified", "Referans tablo hücresiyle doğrulanan"),
              ("contradicting_verified", "Referans tablo hücresiyle ÇELİŞEN verified (kriter 21)")]
    for key, label in labels:
        values = [report["modes"][mode]["summary"][key] for mode in report["modes"]]
        lines.append(f"| {label} | " + " | ".join("—" if v is None else f"{v}" for v in values) + " |")
    for mode, data in report["modes"].items():
        lines += ["", f"## {mode}", ""]
        for paper in data["papers"]:
            lines.append(f"### {paper['paper']}")
            lines.append(f"- Künye: {paper['bibliographic']}")
            lines.append("- Tablolar: " + "; ".join(f"Tablo {t['table']}: {t['matched']}/{t['cells']} "
                                                    f"(metinde {t['cells_in_text']})"
                                                    for t in paper["tables"]))
            lines.append("- Formüller: " + "; ".join(f"({e['number']}) benzerlik {e['similarity']}"
                                                     + (" tam" if e["exact"] else "") for e in paper["equations"]))
            results = paper["results"]
            lines.append(f"- Sonuçlar: geri çağırma {results['recall']}, verified {results['verified']}, "
                         f"tablo hücresiyle doğrulanan {results['table_confirmed']}, çelişen {results['contradicting_verified']}")
            for item in results["contradictions"]:
                lines.append(f"  - çelişen: {item['model']} / {item['metric']} = {item['value_text']} (s. {item['page']})")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modes", nargs="+", default=["fast", "balanced", "full"], choices=["fast", "balanced", "full"])
    parser.add_argument("--work", default=str(ROOT / "reports" / "eval_work"))
    parser.add_argument("--reports", default=str(ROOT / "reports"))
    args = parser.parse_args(argv)
    work = Path(args.work)
    report = evaluate(args.modes, work)
    stamp = datetime.now().strftime("%Y%m%d")
    reports = Path(args.reports)
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"accuracy_{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (reports / f"accuracy_{stamp}.md").write_text(render_markdown(report), encoding="utf-8")
    sys.stdout.reconfigure(errors="replace")
    print(render_markdown(report))


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
