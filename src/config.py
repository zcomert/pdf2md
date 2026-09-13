from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .errors import PreflightError

DEFAULT_CONFIG_PATH = Path("config.yaml")

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
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
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

# CLI argüman adı -> config içindeki yol (§24 tablosu)
CLI_TO_CONFIG = {
    "input_dir": ("input_dir",),
    "output_dir": ("output_dir",),
    "mode": ("mode",),
    "scope": ("scope",),
    "recursive": ("recursive",),
    "include": ("include",),
    "prompt": ("prompt",),
    "prompt_file": ("prompt_file",),
    "model_vision": ("models", "vision"),
    "model_text": ("models", "text"),
    "dpi": ("pdf", "render_dpi"),
    "cpu_workers": ("processing", "cpu_workers"),
    "retry_failed": ("processing", "retry_failed"),
    "log_level": ("logging", "level"),
}

def load_config(path=None):
    """`path` açıkça verildiyse dosya bulunmalıdır; verilmediyse ./config.yaml varsa okunur."""
    if path is not None:
        chosen = Path(path)
        if not chosen.is_file():
            raise PreflightError(f"Yapılandırma dosyası bulunamadı: {chosen}",
                                 "--config ile geçerli bir dosya yolu verin")
    elif DEFAULT_CONFIG_PATH.is_file():
        chosen = DEFAULT_CONFIG_PATH
    else:
        return AppConfig()
    try:
        data = yaml.safe_load(chosen.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PreflightError(f"{chosen} geçerli bir YAML dosyası değil: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise PreflightError(f"{chosen} en üst düzeyde anahtar/değer eşlemesi içermelidir")
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise PreflightError(f"{chosen} geçersiz:\n{format_validation_error(exc)}") from exc

def merge_cli(config, args):
    """Öncelik: CLI > config.yaml > varsayılan. Sonuç yeniden doğrulanır."""
    data = config.model_dump()
    for attr, path in CLI_TO_CONFIG.items():
        value = getattr(args, attr, None)
        if value is None:
            continue
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise PreflightError(f"Geçersiz komut satırı değeri:\n{format_validation_error(exc)}") from exc

def format_validation_error(exc):
    lines = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err["loc"]) or "(kök)"
        lines.append(f"  - {location}: {err['msg']}")
    return "\n".join(lines)
