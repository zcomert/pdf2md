from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ErrorStage

STATE_SCHEMA_VERSION = "1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    completed_with_warnings = "completed_with_warnings"
    failed = "failed"
    skipped = "skipped"


class ModelRef(StrictModel):
    name: str
    digest: str | None = None


class HistoryEntry(StrictModel):
    """Prompt/plan değişince önceki çıktının kaydı (§9.3)."""
    prompt_sha256: str | None = None
    plan_hash: str | None = None
    output_path: str | None = None
    status: DocumentStatus | None = None
    processed_at: str | None = None
    run_id: str | None = None


class DocumentState(StrictModel):
    sha256: str | None = Field(None, pattern=r"^[0-9a-f]{64}$")
    size_bytes: int | None = Field(None, ge=0)
    mtime: str | None = None
    status: DocumentStatus = DocumentStatus.pending
    warnings: list[str] = []
    plan_hash: str | None = None
    prompt_sha256: str | None = None
    models: dict[str, ModelRef] = {}
    output_path: str | None = None
    processing_time_sec: float | None = Field(None, ge=0)
    processed_at: str | None = None
    attempts: int = Field(0, ge=0)
    last_run_id: str | None = None
    error_stage: ErrorStage | None = None
    error: str | None = None
    history: list[HistoryEntry] = []


class CollectionState(StrictModel):
    document_hashes: list[str] = []
    prompt_sha256: str | None = None
    plan_hash: str | None = None
    models: dict[str, ModelRef] = {}
    output_path: str | None = None
    created_at: str | None = None
    status: str | None = None


class RunSummary(StrictModel):
    run_id: str
    started_at: str
    finished_at: str | None = None
    input_path: str
    output_path: str
    discovered: int = 0
    excluded_by_filter: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    discovery_failed: int = 0
    recovered_interrupted: int = 0
    parsed: int = 0
    parsed_from_cache: int = 0
    vision_calls: int = 0
    text_llm_calls: int = 0
    plan_hash: str | None = None
    completed: int = 0
    completed_with_warnings: int = 0
    failed: int = 0
    skipped: int = 0
    not_retried: int = Field(0, description="Önceki çalıştırmada başarısız olup --retry-failed olmadan denenmeyenler")
    total_time_sec: float | None = None


PLAN_SCHEMA_VERSION = "1.0"


class PlanTargets(StrictModel):
    include: list[str] = ["*.pdf"]


class PlanNeeds(StrictModel):
    tables: bool = False
    equations: bool = False
    figures: bool = False
    full_text: bool = False


class CustomField(StrictModel):
    key: str = Field(pattern=r"^custom\.[a-z0-9_]+$")
    description: str


class ProcessingPlan(StrictModel):
    """İşleme planı (§10.2). Planlayıcı modelin çıktısı da bu şemayla doğrulanır."""
    schema_version: str = PLAN_SCHEMA_VERSION
    # Şemalı üretimde alanlar sırayla üretilir: gerekçe kapsamdan önce gelir, model önce gerekçelendirir.
    scope_reason: str = Field(min_length=1)
    scope: Literal["document", "collection"]
    targets: PlanTargets = PlanTargets()
    requested_fields: list[str] = Field(min_length=1)
    custom_fields: list[CustomField] = []
    needs: PlanNeeds = PlanNeeds()
    comparison_dimensions: list[str] = []
    output_language: str = Field(description="ISO 639-1 kodu (tr, en, ...) veya belgenin dilini korumak için 'source'")
    output_outline: list[str] = Field(min_length=1)
    collection_name_suggestion: str | None = None

    @field_validator("requested_fields")
    @classmethod
    def fields_in_catalog(cls, fields):
        from .field_catalog import is_valid_field  # döngüsel içe aktarmayı önler
        unknown = [key for key in fields if not is_valid_field(key)]
        if unknown:
            raise ValueError(f"unknown fields {unknown}; use catalog keys or the 'custom.' prefix")
        return fields

    @field_validator("output_outline")
    @classmethod
    def outline_not_blank(cls, outline):
        if not any(item.strip() for item in outline):
            raise ValueError("output_outline must contain at least one heading")
        return outline

    @model_validator(mode="after")
    def custom_fields_requested(self):
        missing = [item.key for item in self.custom_fields if item.key not in self.requested_fields]
        if missing:
            raise ValueError(f"custom_fields {missing} are not listed in requested_fields")
        return self


EXTRACTION_SCHEMA_VERSION = "1.0"
FieldStatus = Literal["found", "not_found", "unclear"]
Verification = Literal["verified", "unverified", "source_not_found"]
Confidence = Literal["high", "medium", "low"]


class Evidence(StrictModel):
    """Model yalnızca `block_id` ve `page` verir; diğer alanlar belgeden deterministik doldurulur."""
    page: int | None = None
    block_id: str | None = None
    section: str | None = None
    table: str | None = Field(None, description="Tablo etiketi, ör. 'Table 9'")
    figure: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    source_method: Literal["text", "ocr", "vision"] | None = None
    resolved: bool = Field(False, description="Kanıt belgede bulundu (block_id/sayfa gerçek)")


def _empty_value(value):
    return value is None or value == []


class FieldValue(StrictModel):
    value: str | int | float | list[str] | None = None
    value_text: str | None = None
    status: FieldStatus
    evidence: list[Evidence] = []
    verification: Verification | None = Field(None, description="Yalnızca sayı içeren değerler için")
    confidence: Confidence | None = None
    in_evidence: bool | None = Field(None, description="Sayısal olmayan değerin metni kanıtta geçiyor mu")

    @model_validator(mode="after")
    def check_status(self):
        if self.status == "not_found" and not _empty_value(self.value):
            raise ValueError("not_found value must be null or []")
        if isinstance(self.value, str) and not self.value.strip():
            raise ValueError("empty string is not allowed; use status not_found with null")
        return self


class ResultItem(StrictModel):
    field: str = Field(description="Sonucun ait olduğu plan alanı, ör. results.best")
    claim: str
    model: str | None = None
    metric: str | None = None
    value: float | None = None
    value_text: str | None = None
    dataset: str | None = None
    evidence: list[Evidence] = []
    verification: Verification = "source_not_found"
    confidence: Confidence = "low"


class EquationSelection(StrictModel):
    equation_id: str
    description: str | None = None
    evidence: list[Evidence] = []


class ConflictValue(StrictModel):
    value: str | int | float | list[str] | None
    evidence: list[Evidence] = []


class Conflict(StrictModel):
    field: str
    values: list[ConflictValue]


class ExtractionSource(StrictModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Extraction(StrictModel):
    """`_cache/<sha>/extractions/<plan_hash>.json` (§18). Kullanıcıya teslim edilmez."""
    schema_version: str = EXTRACTION_SCHEMA_VERSION
    source: ExtractionSource
    plan_hash: str
    fields: dict[str, FieldValue] = {}
    results: list[ResultItem] = []
    equations_selected: list[EquationSelection] = []
    tables_selected: list[str] = []
    conflicts: list[Conflict] = []
    warnings: list[str] = []
    chunks: int = 0
    llm_calls: int = 0


class ProcessingState(StrictModel):
    schema_version: str = STATE_SCHEMA_VERSION
    documents: dict[str, DocumentState] = {}
    collections: dict[str, CollectionState] = {}
    runs: dict[str, RunSummary] = {}
