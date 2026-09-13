from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

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
    completed: int = 0
    completed_with_warnings: int = 0
    failed: int = 0
    skipped: int = 0
    not_retried: int = Field(0, description="Önceki çalıştırmada başarısız olup --retry-failed olmadan denenmeyenler")
    total_time_sec: float | None = None


class ProcessingState(StrictModel):
    schema_version: str = STATE_SCHEMA_VERSION
    documents: dict[str, DocumentState] = {}
    collections: dict[str, CollectionState] = {}
    runs: dict[str, RunSummary] = {}
