from enum import Enum

class ErrorStage(str, Enum):
    discovery = "discovery"
    parse = "parse"
    ocr = "ocr"
    vision = "vision"
    llm = "llm"
    validation = "validation"
    write = "write"

class DocumentError(Exception):
    def __init__(self, stage, message):
        self.stage, self.message = stage, message
        super().__init__(f"[{stage.value}] {message}")

class FatalBatchError(DocumentError):
    pass

class PreflightError(Exception):
    def __init__(self, message, hint=None):
        self.message, self.hint = message, hint
        super().__init__(message if not hint else f"{message}\nHint: {hint}")

