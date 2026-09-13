import atexit
import contextlib
import json
import os
import socket
import threading
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .atomic_io import atomic_write_json
from .config import format_validation_error
from .errors import PreflightError
from .schemas import STATE_SCHEMA_VERSION, DocumentState, DocumentStatus, ProcessingState

STATE_FILE = "processing_state.json"
LOCK_FILE = ".lock"
# Windows'ta kilitlenen bayt aralığı dosya içeriğinin çok ötesinde tutulur; böylece kilit bilgisi okunabilir kalır.
_WINDOWS_LOCK_OFFSET = 1 << 30


class StateManager:
    """`processing_state.json` okuma/yazma. Yazım yalnızca ana süreçten yapılır."""

    def __init__(self, output_dir):
        self.path = Path(output_dir) / STATE_FILE
        self.state = ProcessingState()
        self._lock = threading.RLock()

    def load(self):
        with self._lock:
            if not self.path.exists():
                self.state = ProcessingState()
                return self.state
            hint = "Dosyayı düzeltin ya da yedekleyip silin (silinirse tüm belgeler yeniden işlenir)"
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PreflightError(f"State dosyası okunamadı: {self.path}: {exc}", hint) from exc
            version = raw.get("schema_version") if isinstance(raw, dict) else None
            if version != STATE_SCHEMA_VERSION:
                raise PreflightError(
                    f"State şema sürümü uyumsuz: {version!r} (beklenen {STATE_SCHEMA_VERSION!r}): {self.path}", hint)
            try:
                self.state = ProcessingState.model_validate(raw)
            except ValidationError as exc:
                raise PreflightError(f"State dosyası geçersiz: {self.path}\n{format_validation_error(exc)}", hint) from exc
            return self.state

    def save(self):
        with self._lock:
            atomic_write_json(self.path, self.state)

    def get(self, relative_path):
        return self.state.documents.get(relative_path)

    def update(self, relative_path, save=True, **fields):
        """Kaydı alan bazında günceller ve şemayla yeniden doğrular."""
        with self._lock:
            current = self.state.documents.get(relative_path)
            data = current.model_dump() if current else {}
            data.update(fields)
            record = DocumentState.model_validate(data)
            self.state.documents[relative_path] = record
            if save:
                self.save()
            return record

    def recover_interrupted(self):
        """Yarıda kalmış `processing` kayıtlarını `pending` yapar; deneme sayısı korunur (§9.4)."""
        with self._lock:
            recovered = [rel for rel, record in self.state.documents.items()
                         if record.status == DocumentStatus.processing]
            for rel in recovered:
                self.update(rel, save=False, status=DocumentStatus.pending)
            if recovered:
                self.save()
            return recovered

    def record_run(self, summary):
        with self._lock:
            self.state.runs[summary.run_id] = summary
            self.save()


class OutputLock:
    """Aynı çıktı klasöründe ikinci çalıştırmayı engeller (§9.5).

    Karşılıklı dışlama işletim sistemi dosya kilidiyle yapılır (Windows `msvcrt.locking`, diğerleri
    `flock`); süreç çökse bile kilidi işletim sistemi bırakır. Dosyadaki JSON yalnızca bilgi amaçlıdır:
    kilit alındığında dosyada önceki bir çalıştırmanın bilgisi varsa o çalıştırma kilidi temizlemeden
    sonlanmıştır ve `stale_info` olarak raporlanır.
    """

    def __init__(self, output_dir, run_id):
        self.path = Path(output_dir) / LOCK_FILE
        self.run_id = run_id
        self.stale_info = None
        self._fd = None

    def acquire(self):
        if self._fd is not None:
            return self
        while True:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                _lock_fd(fd)
            except OSError:
                info = _read_info(fd)
                os.close(fd)
                owner = f" (pid {info.get('pid')}, {info.get('hostname')}, başlangıç {info.get('started_at')})" if info else ""
                raise PreflightError(
                    f"Çıktı klasörü başka bir çalıştırma tarafından kullanılıyor: {self.path.parent}{owner}",
                    "Diğer çalıştırmanın bitmesini bekleyin veya farklı bir --output verin") from None
            if _same_file(fd, self.path):
                break
            # POSIX: kilit alınırken dosya önceki sahibi tarafından silinmiş; yeni dosyayla yeniden dene.
            _unlock_fd(fd)
            os.close(fd)
        self.stale_info = _read_info(fd) or None
        payload = json.dumps({"pid": os.getpid(), "hostname": socket.gethostname(),
                              "started_at": datetime.now().isoformat(timespec="seconds"),
                              "run_id": self.run_id}).encode("utf-8")
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, payload)
        os.fsync(fd)
        self._fd = fd
        atexit.register(self.release)
        return self

    def release(self):
        fd, self._fd = self._fd, None
        if fd is None:
            return
        atexit.unregister(self.release)
        if os.name == "nt":
            # Windows'ta açık dosya silinemez: önce kilidi bırak ve kapat, sonra sil. Bu arada başka
            # bir süreç dosyayı açtıysa silme başarısız olur ve onun kilidi bozulmaz.
            _unlock_fd(fd)
            os.close(fd)
            with contextlib.suppress(OSError):
                self.path.unlink()
        else:
            with contextlib.suppress(OSError):
                self.path.unlink()
            _unlock_fd(fd)
            os.close(fd)

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc_info):
        self.release()


def _lock_fd(fd):
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_fd(fd):
    with contextlib.suppress(OSError):
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)


def _same_file(fd, path):
    if os.name == "nt":
        return True
    try:
        return os.path.samestat(os.fstat(fd), os.stat(path))
    except OSError:
        return False


def _read_info(fd):
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        data = os.read(fd, 4096)
        return json.loads(data.decode("utf-8")) if data.strip() else {}
    except (OSError, ValueError):
        return {}
