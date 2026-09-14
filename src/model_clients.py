"""Model istemcisi arayüzü (§33 son paragraf): görsel ve metin istemcileri bu arayüzü kullanır; model veya
servis değişikliği diğer modülleri etkilemez. Testler `tests/fakes.py` içindeki sahte arka ucu kullanır."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ModelInfo:
    name: str
    digest: str
    size_bytes: int = 0

    @property
    def reference(self):
        """Front matter ve state için `ad@sha256:digest` biçimi (§20.2)."""
        return f"{self.name}@sha256:{self.digest}"


@dataclass(frozen=True)
class ModelResponse:
    content: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    duration_sec: float | None = None
    attempts: int = 1
    raw: dict = field(default_factory=dict)


class ModelError(Exception):
    """Model çağrısı hatalarının tabanı."""


class ModelUnavailable(ModelError):
    """Model servisine erişilemiyor (yeniden denemelerden sonra). Batch'i durdurur (§28)."""


class ModelTimeout(ModelError):
    """Model yanıtı zaman aşımına uğradı (yeniden denemelerden sonra)."""


class ModelNotFound(ModelError):
    """İstenen model serviste kurulu değil."""


class ModelBackend(Protocol):
    def list_models(self) -> dict[str, ModelInfo]:
        ...

    def chat(self, model: str, prompt: str, images: list[bytes] | None = None, schema: dict | None = None,
             options: dict | None = None, system: str | None = None) -> ModelResponse:
        ...
