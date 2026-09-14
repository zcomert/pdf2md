from enum import Enum

class ErrorStage(str, Enum):
    discovery = "discovery"
    parse = "parse"
    ocr = "ocr"
    vision = "vision"
    llm = "llm"
    validation = "validation"
    write = "write"

class PipelineError(Exception):
    """Aşama bilgisi taşıyan işlem hatalarının ortak tabanı. `error_type` kısa makine okunur tür (§28 hata kaydı)."""
    def __init__(self, stage, message, error_type=None):
        self.stage, self.message = ErrorStage(stage), message
        self.error_type = error_type or f"{self.stage.value}_error"
        super().__init__(f"[{self.stage.value}] {message}")

    def __reduce__(self):
        # Paralel ayrıştırmada worker süreçten ana sürece taşınabilsin (varsayılan pickle yalnızca args'ı taşır).
        return type(self), (self.stage, self.message, self.error_type)

class DocumentError(PipelineError):
    """Yalnızca ilgili belgeyi başarısız yapar; batch devam eder."""

class FatalBatchError(PipelineError):
    """Batch'i durdurur (Ollama kapalı, disk dolu). DocumentError'dan türemez,
    böylece `except DocumentError` bu hatayı yutamaz."""

class PreflightError(Exception):
    """Başlangıç kontrolü hatası; çıkış kodu 2."""
    def __init__(self, message, hint=None):
        self.message, self.hint = message, hint
        super().__init__(message if not hint else f"{message}\nÖneri: {hint}")

    def __reduce__(self):
        return type(self), (self.message, self.hint)
