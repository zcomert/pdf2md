import contextlib
import json
import os
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel

TMP_SUFFIX = ".pdf2md.tmp"


def atomic_write_bytes(path, data, retries=5):
    """Geçici dosyaya yaz, diske aktar, `os.replace` ile yerine koy. Yarım dosya hedefte görünmez."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Önek kısa tutulur: Windows'ta 260 karakter yol sınırı uzun hash adlı dosyalarda aşılabiliyor.
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name[:16]}.", suffix=TMP_SUFFIX, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp_name, path, retries)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def atomic_write_text(path, text, encoding="utf-8", bom=False):
    atomic_write_bytes(path, text.encode("utf-8-sig" if bom else encoding))


def atomic_write_json(path, obj, indent=2):
    """`indent=None` sıkıştırılmış JSON yazar (büyük önbellek dosyaları için)."""
    if isinstance(obj, BaseModel):
        text = obj.model_dump_json(indent=indent)
    else:
        separators = (",", ":") if indent is None else None
        text = json.dumps(obj, ensure_ascii=False, indent=indent, separators=separators)
    atomic_write_text(path, text + "\n")


def cleanup_temp_files(root):
    """Önceki kesintiden kalan geçici dosyaları siler (§38 kriter 15). Yalnızca bu uygulamanın ekini hedefler."""
    removed = []
    for tmp in Path(root).rglob(f"*{TMP_SUFFIX}"):
        with contextlib.suppress(OSError):
            tmp.unlink()
            removed.append(tmp)
    return removed


def _replace_with_retry(source, target, retries):
    # Windows'ta hedef başka süreçte (antivirüs, Excel) açıksa os.replace geçici olarak başarısız olabilir.
    for attempt in range(retries):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(0.05 * 2 ** attempt)
