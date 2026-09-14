"""Künye çıkarımı (§22.3): prompttan bağımsız, her belge için, düşük maliyet sırasıyla.

1. PDF metadata (`title`, çok yazarlı `author`, yayıncı `subject` kalıpları: Elsevier "Dergi, 90 (2024) … doi:…",
   IEEE "Dergi;2025;13; ;10.1109/…")
2. İlk 2 sayfada DOI düzenli ifadesi
3. Ayrıştırıcının başlık tespiti (§16.2) ve plan çıkarımında zaten doğrulanmış `bibliographic.*` değerleri
4. Hâlâ eksik alan varsa ilk 2 sayfa üzerinde tek metin LLM çağrısı (Faz 11 kararı: `summary.bibliographic_llm`)

LLM değerleri tahmin yasağına tabidir: yıl ve DOI ilk sayfaların metninde birebir geçmeli, başlık/yazar/dergi
metni kanıt bloğunda geçmeli; aksi halde boş bırakılır. Bulunamayan değer boş kalır.
"""
import re
from dataclasses import dataclass, field

from .atomic_io import atomic_write_json
from .document_model import DocumentModel
from .evidence_verifier import normalize_text
from .llm_extractor import extract, verify_extraction
from .model_clients import ModelUnavailable
from .errors import DocumentError
from .schemas import Bibliographic, ProcessingPlan

BIBLIOGRAPHIC_VERSION = "2"  # 2: başlıkta satır sonu tireleme kalıntısı temizliği
FIELDS = ("title", "authors", "year", "venue", "doi")
FIRST_PAGES = 2
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
JUNK_TITLE_RE = re.compile(r"^(untitled|microsoft word\s*-|document\d*$|slide\s*\d*$)|\.(docx?|pdf|tex|indd)$", re.IGNORECASE)
ELSEVIER_SUBJECT_RE = re.compile(r"^(?P<venue>[^,;]{3,}?),\s*\d+\s*\((?P<year>(?:19|20)\d{2})\)")
IEEE_SUBJECT_RE = re.compile(r"^(?P<venue>[^;]{3,});(?P<year>(?:19|20)\d{2});")
AUTHOR_SPLIT_RE = re.compile(r"\s*(?:;|\band\b|&|,(?=\s*[A-ZÇĞİÖŞÜ][^,]*\s[A-ZÇĞİÖŞÜ]))\s*")


@dataclass
class BibliographicResult:
    record: Bibliographic
    llm_calls: int = 0
    warnings: list = field(default_factory=list)
    from_cache: bool = False


def clean_doi(text):
    match = DOI_RE.search(text or "")
    if not match:
        return None
    doi = match.group(0).rstrip(".,;:]}")
    # Sondaki ")" yalnızca DOI içinde açılmamışsa cümle noktalamasıdır ("(doi: 10.1/x)")
    while doi.endswith(")") and doi.count(")") > doi.count("("):
        doi = doi[:-1].rstrip(".,;:")
    return doi


def clean_title(title):
    """Satır sonu tirelemesinden kalan boşluk kaldırılır, tire korunur: "pre- trained" → "pre-trained"."""
    return re.sub(r"(?<=\w)-\s+(?=\w)", "-", " ".join(title.split()))


def usable_title(title, filename):
    if not title or len(title.strip()) < 5 or JUNK_TITLE_RE.search(title.strip()):
        return None
    stem = re.sub(r"\.pdf$", "", filename or "", flags=re.IGNORECASE)
    if normalize_text(title) == normalize_text(stem):
        return None
    return clean_title(title)


def from_metadata(metadata, filename):
    values, sources = {}, {}
    title = usable_title(metadata.get("title"), filename)
    if title:
        values["title"], sources["title"] = title, "metadata"
    author = (metadata.get("author") or "").strip()
    parts = [p for p in AUTHOR_SPLIT_RE.split(author) if p and len(p) > 2]
    # Tek isim yayıncı metadata'sında çoğunlukla yalnızca ilk yazardır (Elsevier); yazar listesi sayılmaz.
    if len(parts) > 1:
        values["authors"], sources["authors"] = parts, "metadata"
    subject = (metadata.get("subject") or "").strip()
    match = ELSEVIER_SUBJECT_RE.match(subject) or IEEE_SUBJECT_RE.match(subject)
    if match:
        values["venue"], sources["venue"] = match.group("venue").strip(), "metadata"
        values["year"], sources["year"] = int(match.group("year")), "metadata"
    doi = clean_doi(subject) or clean_doi(metadata.get("keywords"))
    if doi:
        values["doi"], sources["doi"] = doi, "metadata"
    return values, sources


def first_pages_text(document):
    return "\n".join(block.text for block in document.blocks if block.page <= FIRST_PAGES)


def _missing(values):
    return [name for name in FIELDS if values.get(name) in (None, [], "")]


def _accepted(field_value, name, source_text):
    """LLM veya çıkarım değeri künyeye alınabilir mi (tahmin yasağı)."""
    if field_value is None or field_value.status != "found" or field_value.value in (None, []):
        return None
    value = field_value.value
    normalized_source = normalize_text(source_text)
    if name == "year":
        text = str(field_value.value_text or value).strip()
        year = text[:4] if re.match(r"^\d{4}", text) else ""
        if YEAR_RE.match(year) and re.search(rf"(?<!\d){year}(?!\d)", source_text):
            return int(year)
        return None
    if name == "doi":
        doi = clean_doi(str(value))
        return doi if doi and doi.lower() in source_text.lower() else None
    if name == "authors":
        authors = value if isinstance(value, list) else [a for a in AUTHOR_SPLIT_RE.split(str(value)) if a]
        kept = [a.strip() for a in authors if a.strip() and normalize_text(a) in normalized_source]
        return kept or None
    if field_value.in_evidence is False:
        return None
    text = " ".join(str(value).split())
    return text if normalize_text(text) in normalized_source or field_value.in_evidence else None


def extract_bibliographic(document, text_client=None, text_model=None, extraction=None, cache_dir=None, force=False,
                          use_llm=True, max_retries=1, num_ctx=16384, max_output_tokens=1024, errors_dir=None,
                          logger=None):
    """Döner: `BibliographicResult`. LLM adımı hiçbir durumda belgeyi başarısız yapmaz (uyarı yazılır)."""
    llm_available = use_llm and text_client is not None and text_model is not None
    cache_path = None
    if cache_dir is not None:
        suffix = text_model.digest[:8] if llm_available else "nollm"
        cache_path = cache_dir / f"bibliographic_v{BIBLIOGRAPHIC_VERSION}_{suffix}.json"
        if not force and cache_path.is_file():
            try:
                return BibliographicResult(Bibliographic.model_validate_json(cache_path.read_text(encoding="utf-8")),
                                           from_cache=True)
            except (OSError, ValueError):
                pass

    values, sources = from_metadata(document.pdf_metadata, document.source.relative_path.rsplit("/", 1)[-1])
    source_text = first_pages_text(document)
    if "doi" not in values:
        doi = clean_doi(source_text)
        if doi:
            values["doi"], sources["doi"] = doi, "doi_regex"
    if "title" not in values and document.title:
        values["title"], sources["title"] = clean_title(document.title), "parser"
    if extraction is not None:
        for name in _missing(values):
            accepted = _accepted(extraction.fields.get(f"bibliographic.{name}"), name, source_text)
            if accepted:
                values[name], sources[name] = accepted, "extraction"

    warnings, calls = [], 0
    missing = _missing(values)
    if missing and llm_available:
        first_pages = DocumentModel.model_validate({**document.model_dump(), "blocks": [
            b.model_dump() for b in document.blocks if b.page <= FIRST_PAGES], "sections": []})
        plan = ProcessingPlan(scope="document", scope_reason="künye (§22.3)",
                              requested_fields=[f"bibliographic.{name}" for name in missing],
                              output_language="source", output_outline=["Künye"])
        try:
            partial = extract(first_pages, plan, "bibliographic", text_client, max_retries, num_ctx,
                              max_output_tokens, errors_dir=errors_dir, logger=None)
            calls = partial.llm_calls
            verified = verify_extraction(partial, first_pages)
            for name in missing:
                accepted = _accepted(verified.fields.get(f"bibliographic.{name}"), name, source_text)
                if accepted:
                    values[name], sources[name] = accepted, "llm"
        except ModelUnavailable as exc:
            warnings.append(f"bibliographic_llm_unavailable: {exc}")
        except DocumentError as exc:
            warnings.append(f"bibliographic_llm_failed: {exc.error_type}")
            calls = max(calls, 1)
    record = Bibliographic(**{name: values.get(name) for name in FIELDS if values.get(name) not in (None, [])},
                           sources=sources)
    if cache_path is not None and not warnings:
        atomic_write_json(cache_path, record)
    if logger:
        found = ", ".join(f"{name}={sources[name]}" for name in FIELDS if name in sources) or "-"
        logger.info("Künye: %s — %s%s", document.source.relative_path, found,
                    f", LLM çağrısı {calls}" if calls else "")
    return BibliographicResult(record, calls, warnings)
