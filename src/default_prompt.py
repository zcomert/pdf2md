"""Yerleşik varsayılan prompt ve prompt kaynağının çözümlenmesi (§10.1, §10.3)."""
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .errors import PreflightError

DEFAULT_PROMPT = (
    "Bu PDF belgesinin tam yapısal Markdown dönüşümünü üret. Başlık hiyerarşisini, paragrafları, listeleri, "
    "tabloları, formülleri, şekil referanslarını ve algoritmaları koru. Belgenin kendi dilini koru, çeviri yapma."
)


@dataclass(frozen=True)
class ResolvedPrompt:
    text: str
    source: str  # default | cli | cli_file | config | config_file
    is_default: bool
    empty_prompt: bool = False

    @property
    def sha256(self):
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def run_warnings(self):
        return ["empty_prompt: varsayılan prompt kullanıldı"] if self.empty_prompt else []


def _read_prompt_file(path, label):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PreflightError(f"{label} okunamadı: {path}: {exc}") from exc


def resolve_prompt(args, config):
    """Öncelik: `--prompt` > `--prompt-file` > config `prompt` > config `prompt_file` > varsayılan.

    `merge_cli` CLI değerlerini config'e yazdığı için kaynak ayrımı `args` üzerinden yapılır.
    Boş veya yalnızca boşluk prompt varsayılana düşer ve belgeler `completed_with_warnings` olur. Hash,
    verilen ham metinden hesaplanır; böylece boş prompt ile prompt'suz çalıştırma birbirinin yerine atlanmaz.
    """
    if getattr(args, "prompt", None) is not None:
        raw, source = args.prompt, "cli"
    elif getattr(args, "prompt_file", None):
        raw, source = _read_prompt_file(args.prompt_file, "Prompt dosyası"), "cli_file"
    elif config.prompt is not None:
        raw, source = config.prompt, "config"
    elif config.prompt_file:
        raw, source = _read_prompt_file(config.prompt_file, "Config prompt dosyası"), "config_file"
    else:
        return ResolvedPrompt(DEFAULT_PROMPT, "default", is_default=True)
    if not raw.strip():
        return ResolvedPrompt(raw, source, is_default=True, empty_prompt=True)
    return ResolvedPrompt(raw, source, is_default=False)
