"""§28 hata yönetimi tablosu tek yerde: istisna → belge durumu ve batch davranışı.

| Hata                                | Aşama             | Belge   | Batch                              |
|-------------------------------------|-------------------|---------|------------------------------------|
| Bozuk / şifreli PDF                 | parse             | failed  | devam                              |
| Model servisi erişilemiyor          | vision / llm      | pending | durur                              |
| Metin modeli zaman aşımı            | llm               | failed  | devam                              |
| JSON / şema hatası (denemeler sonu) | validation        | failed  | devam                              |
| Disk yazma hatası                   | write             | failed  | devam; art arda ikinci hatada durur|
| Disk dolu (ENOSPC) / yetersiz alan  | write             | pending | durur                              |
| İptal (Ctrl+C)                      | —                 | pending | durur                              |
| Beklenmeyen hata                    | o anki aşama      | failed  | devam                              |

Görsel model zaman aşımı ve görsel işleme hataları belge hatası değildir: bölge işaretli kalır, uyarı yazılır
(`vision_enrichment`). Tek sayfa okuma hatası `parse_error` uyarısıdır (`pdf_parser`).

Karar (§28'den sapma): model servisi kapandığında belge `failed` değil `pending` bırakılır; `failed` belgeler
`--retry-failed` olmadan denenmediği için servis dönünce belge atlanırdı (Faz 07).
"""
import errno
from dataclasses import dataclass

from .errors import DocumentError, ErrorStage, FatalBatchError
from .model_clients import ModelUnavailable
from .schemas import DocumentStatus

FAIL, STOP, CANCEL = "fail", "stop", "cancel"
MAX_CONSECUTIVE_WRITE_ERRORS = 2


@dataclass(frozen=True)
class ErrorOutcome:
    action: str  # fail | stop | cancel
    stage: ErrorStage
    error_type: str
    message: str

    @property
    def document_status(self):
        return DocumentStatus.failed if self.action == FAIL else DocumentStatus.pending


def classify(exc, stage, cancelled_type=None):
    """`stage`: istisna anındaki aşama (istisna kendi aşamasını taşımıyorsa kullanılır)."""
    stage = ErrorStage(stage)
    if cancelled_type is not None and isinstance(exc, cancelled_type):
        return ErrorOutcome(CANCEL, stage, "cancelled", "Kullanıcı iptal etti")
    if isinstance(exc, FatalBatchError):
        return ErrorOutcome(STOP, exc.stage, exc.error_type, exc.message)
    if isinstance(exc, ModelUnavailable):
        model_stage = stage if stage in (ErrorStage.vision, ErrorStage.llm) else ErrorStage.llm
        return ErrorOutcome(STOP, model_stage, "model_unavailable", str(exc))
    if isinstance(exc, DocumentError):
        return ErrorOutcome(FAIL, exc.stage, exc.error_type, exc.message)
    if isinstance(exc, OSError):
        if exc.errno == errno.ENOSPC:
            return ErrorOutcome(STOP, ErrorStage.write, "disk_full", f"Disk dolu: {exc}")
        return ErrorOutcome(FAIL, ErrorStage.write, "write_error", f"Yazılamadı: {exc}")
    return ErrorOutcome(FAIL, stage, "unexpected_error", f"{type(exc).__name__}: {exc}")


class WriteErrorTracker:
    """§28: aynı (yazma) hatası art arda tekrarlanırsa batch durur; başarılı bir belge sayacı sıfırlar."""

    def __init__(self, limit=MAX_CONSECUTIVE_WRITE_ERRORS):
        self.limit = limit
        self.consecutive = 0

    def record(self, outcome):
        """Döner: batch durmalı mı."""
        if outcome.action == FAIL and outcome.error_type == "write_error":
            self.consecutive += 1
            return self.consecutive >= self.limit
        self.consecutive = 0
        return False

    def success(self):
        self.consecutive = 0
