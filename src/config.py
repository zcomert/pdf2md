from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class OllamaConfig(StrictModel):
    endpoint: str = "http://127.0.0.1:11434"
    timeout_sec: int = Field(300, ge=1)
    max_retries: int = Field(3, ge=0)
    retry_backoff_sec: int = Field(5, ge=0)
    keep_alive: str = "10m"

class ModelsConfig(StrictModel):
    vision: str = "minicpm-v4.5:8b"
    text: str = "gemma4:latest"
    text_num_ctx: int = Field(16384, ge=1)
    max_output_tokens: int = Field(4096, ge=1)
    vision_required: bool = True

class PdfConfig(StrictModel):
    render_dpi: int = Field(250, ge=150, le=400)
    crop_padding_pt: int = Field(8, ge=0)
    min_text_chars: int = Field(100, ge=0)
    mixed_image_ratio: float = Field(.3, ge=0, le=1)
    scanned_image_ratio: float = Field(.5, ge=0, le=1)

class OcrConfig(StrictModel):
    enabled: bool = True
    languages: list[str] = ["eng"]
    tesseract_path: str | None = None

class ProcessingConfig(StrictModel):
    retry_failed: bool = False
    cpu_workers: int = Field(4, ge=1)
    llm_workers: int = Field(1, ge=1)
    min_free_disk_mb: int = Field(1024, ge=0)

class OutputConfig(StrictModel):
    front_matter: bool = True
    page_markers: bool = True
    citation_style: str = "(s. {page}{table_or_figure})"
    save_xlsx: bool = False

class SummaryConfig(StrictModel):
    extra_fields: list[str] = []

class LoggingConfig(StrictModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_model_content: bool = False

class AppConfig(StrictModel):
    input_dir: str | None = None
    output_dir: str | None = None
    mode: Literal["fast", "balanced", "full"] = "balanced"
    recursive: bool = False
    include: list[str] = []
    scope: Literal["auto", "document", "collection"] = "auto"
    prompt: str | None = None
    prompt_file: str | None = None
    ollama: OllamaConfig = OllamaConfig()
    models: ModelsConfig = ModelsConfig()
    pdf: PdfConfig = PdfConfig()
    ocr: OcrConfig = OcrConfig()
    processing: ProcessingConfig = ProcessingConfig()
    output: OutputConfig = OutputConfig()
    summary: SummaryConfig = SummaryConfig()
    logging: LoggingConfig = LoggingConfig()

def load_config(path=None):
    chosen = Path(path) if path else Path("config.yaml")
    data = yaml.safe_load(chosen.read_text(encoding="utf-8")) if chosen.exists() else {}
    return AppConfig.model_validate(data or {})

def merge_cli(config, args):
    updates = {}
    for key in ("input_dir", "output_dir", "mode", "recursive", "scope", "prompt", "prompt_file"):
        value = getattr(args, key, None)
        if value is not None: updates[key] = value
    if getattr(args, "include", None): updates["include"] = args.include
    return config.model_copy(update=updates)

