"""Toplu envanter tablosu `papers_summary.csv` (§22): state'teki tüm belgeler, sabit sütunlar ve isteğe bağlı
analitik sütunlar. Özet sayılar CSV'ye satır olarak eklenmez (§22.5)."""
import contextlib
import csv
import io
import os
import re
import tempfile
from pathlib import Path

from .atomic_io import TMP_SUFFIX, atomic_write_text
from .field_catalog import FIELDS, derived_metric
from .schemas import ProcessingPlan

SUMMARY_CSV = "papers_summary.csv"
SUMMARY_XLSX = "papers_summary.xlsx"
FIXED_COLUMNS = (
    "relative_path", "filename", "sha256", "status", "pages", "scanned_pages", "ocr_pages", "vision_calls",
    "text_llm_calls", "warnings_count", "error_stage", "error_message", "output_path", "prompt_sha256",
    "processing_time_sec", "processed_at", "title", "authors", "year", "venue", "doi",
)
MAX_ERROR_MESSAGE = 200
METRIC_ALIASES = {
    "accuracy": ("accuracy", "acc"),
    "f1": ("f1", "f1score", "fscore", "fmeasure", "f1macro", "macrof1"),
    "precision": ("precision",),
    "recall": ("recall", "sensitivity"),
    "auc": ("auc", "rocauc", "auroc"),
}


def _short(message):
    if not message:
        return ""
    line = " ".join(str(message).split())
    return line if len(line) <= MAX_ERROR_MESSAGE else line[:MAX_ERROR_MESSAGE - 1] + "…"


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def rows(state, extra_fields=()):
    result = []
    for relative_path, record in sorted(state.documents.items()):
        bib = record.bibliographic
        row = {
            "relative_path": relative_path,
            "filename": relative_path.rsplit("/", 1)[-1],
            "sha256": record.sha256,
            "status": record.status.value,
            "pages": record.pages,
            "scanned_pages": record.scanned_pages,
            "ocr_pages": record.ocr_pages,
            "vision_calls": record.vision_calls,
            "text_llm_calls": record.text_llm_calls,
            "warnings_count": len(record.warnings),
            "error_stage": record.error_stage.value if record.error_stage else None,
            "error_message": _short(record.error),
            "output_path": record.output_path,
            "prompt_sha256": record.prompt_sha256,
            "processing_time_sec": record.processing_time_sec,
            "processed_at": record.processed_at,
            "title": bib.title if bib else None,
            "authors": "; ".join(bib.authors) if bib and bib.authors else None,
            "year": bib.year if bib else None,
            "venue": bib.venue if bib else None,
            "doi": bib.doi if bib else None,
        }
        for key in extra_fields:
            row[key] = record.summary_values.get(key)
        result.append({column: _cell(value) for column, value in row.items()})
    return result


def columns(extra_fields=()):
    return list(FIXED_COLUMNS) + [key for key in extra_fields if key not in FIXED_COLUMNS]


def render_csv(state, extra_fields=()):
    """Excel uyumu: BOM'lu UTF-8 (yazımda), `\\r\\n` satır sonu, `QUOTE_MINIMAL`."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns(extra_fields), quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows(state, extra_fields))
    return buffer.getvalue()


def write_summary(output_dir, state, extra_fields=(), save_xlsx=False, logger=None):
    """`papers_summary.csv` (ve istenirse `.xlsx`) atomik yazılır. XLSX hatası CSV'yi etkilemez."""
    output_dir = Path(output_dir)
    atomic_write_text(output_dir / SUMMARY_CSV, render_csv(state, extra_fields), bom=True)
    if save_xlsx:
        try:
            _write_xlsx(output_dir / SUMMARY_XLSX, state, extra_fields)
        except ImportError:
            if logger:
                logger.warning("papers_summary.xlsx yazılmadı: openpyxl kurulu değil (pip install openpyxl)")
        except OSError as exc:
            if logger:
                logger.warning("papers_summary.xlsx yazılamadı: %s", exc)


def _write_xlsx(path, state, extra_fields):
    import openpyxl  # noqa: F401 — pandas motoru; yoksa ImportError
    import pandas as pd

    frame = pd.DataFrame(rows(state, extra_fields), columns=columns(extra_fields))
    fd, temporary = tempfile.mkstemp(prefix=".papers_summary.", suffix=".xlsx" + TMP_SUFFIX, dir=path.parent)
    try:
        # pandas motoru dosya uzantısından doğrular; geçici ad `.tmp` ile bittiği için dosya nesnesi verilir.
        with os.fdopen(fd, "wb") as handle, pd.ExcelWriter(handle, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name="papers")
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


# --- Analitik sütunlar (§22.4) ------------------------------------------------------------------------------------

def summary_plan(extra_fields):
    """Prompttan bağımsız özet planı: türetilmiş `results.best_<metrik>` alanları `results.best` sonuçlarından seçilir."""
    fields = []
    for key in extra_fields:
        catalog_key = "results.best" if derived_metric(key) is not None else key
        if catalog_key in FIELDS and catalog_key not in fields:
            fields.append(catalog_key)
    return ProcessingPlan(scope="document", scope_reason="envanter analitik sütunları (§22.4)",
                          requested_fields=fields, output_language="source", output_outline=["Özet"])


def _metric_key(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").casefold())


def _as_fraction(result):
    value = result.value
    if value is None:
        return None
    if "%" in (result.value_text or "") or value > 1:
        return value / 100
    return value


def best_result(extraction, metric):
    """`metric` adına uyan `verified` sonuçlar arasında en yüksek değer (yüzdeler oran olarak karşılaştırılır)."""
    aliases = METRIC_ALIASES.get(metric, (metric.replace("_", ""),))
    candidates = []
    for result in extraction.results:
        if result.verification != "verified" or result.value is None:
            continue
        key = _metric_key(result.metric)
        if any(key == alias or key.startswith(alias) for alias in aliases):
            candidates.append(result)
    return max(candidates, key=_as_fraction, default=None)


def analytic_values(extraction, extra_fields):
    """CSV'ye yalnızca doğrulanmış değerler yazılır (§22.4). Sayısal alanlarda `verified`; sayısal olmayan alanlarda
    doğrulama etiketi olmadığından değer metninin kanıtta geçmesi (`in_evidence`) ve düşük olmayan güven aranır."""
    values = {}
    for key in extra_fields:
        metric = derived_metric(key)
        if metric is not None:
            best = best_result(extraction, metric)
            if best is not None:
                values[key] = best.value_text or _cell(best.value)
            continue
        field_value = extraction.fields.get(key)
        if key == "results.best_model" and (field_value is None or not _trusted(field_value)):
            verified = [r for r in extraction.results if r.verification == "verified" and r.model and r.value is not None]
            best = max(verified, key=_as_fraction, default=None)
            if best is not None:
                values[key] = best.model
            continue
        if field_value is not None and _trusted(field_value):
            value = field_value.value
            values[key] = "; ".join(value) if isinstance(value, list) else _cell(field_value.value_text or value)
    return values


def _trusted(field_value):
    if field_value.status != "found" or field_value.value in (None, []):
        return False
    if field_value.verification is not None:
        return field_value.verification == "verified"
    return field_value.in_evidence is True and field_value.confidence != "low"
