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
    """Aşama bilgisi taşıyan işlem hatalarının ortak tabanı."""
    def __init__(self, stage, message):
        self.stage, self.message = ErrorStage(stage), message
        super().__init__(f"[{self.stage.value}] {message}")

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
