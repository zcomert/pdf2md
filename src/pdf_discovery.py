import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

from .errors import ErrorStage, PreflightError
from .paths import input_root, is_pdf_path, normalize
from .schemas import DocumentStatus

HASH_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class DiscoveredPdf:
    relative_path: str
    absolute_path: Path
    size_bytes: int
    mtime: str


@dataclass(frozen=True)
class DiscoveryResult:
    input_root: Path
    documents: list[DiscoveredPdf]
    excluded_by_filter: list[str] = field(default_factory=list)


def discover(input_path, recursive=False, include=()):
    """§8.1: klasör veya tek PDF; `.pdf` harf duyarsız; göreli yola göre deterministik sıra."""
    path = normalize(input_path)
    if path.is_file():
        if not is_pdf_path(path):
            raise PreflightError(f"Giriş dosyası PDF değil: {path}")
        candidates = [path]
    elif path.is_dir():
        entries = path.rglob("*") if recursive else path.glob("*")
        candidates = [entry for entry in entries if is_pdf_path(entry) and entry.is_file()]
    else:
        raise PreflightError(f"Giriş yolu bulunamadı: {path}")
    root = input_root(path)
    documents, excluded = [], []
    for candidate in candidates:
        relative = candidate.relative_to(root).as_posix()
        if not matches_include(relative, include):
            excluded.append(relative)
            continue
        stat = candidate.stat()
        documents.append(DiscoveredPdf(relative, candidate, stat.st_size, format_mtime(stat.st_mtime)))
    documents.sort(key=lambda doc: (doc.relative_path.casefold(), doc.relative_path))
    excluded.sort(key=lambda rel: (rel.casefold(), rel))
    return DiscoveryResult(root, documents, excluded)


def matches_include(relative_path, patterns):
    """`/` içermeyen desen dosya adıyla (her derinlikte), içeren desen göreli yolun tamamıyla eşleşir.
    `*` ve `?` klasör ayırıcıyı geçmez, `**` geçer. Harf duyarsızdır."""
    if not patterns:
        return True
    name = PurePosixPath(relative_path).name
    for pattern in patterns:
        normalized = pattern.replace("\\", "/").removeprefix("./")
        target = relative_path if "/" in normalized else name
        if _glob_regex(normalized).fullmatch(target):
            return True
    return False


def _glob_regex(pattern):
    parts, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(parts), re.IGNORECASE)


def format_mtime(timestamp):
    return datetime.fromtimestamp(timestamp).isoformat(timespec="microseconds")


def compute_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_identity(pdf, record):
    """§8.2: boyut ve mtime kayıtla aynıysa kayıtlı hash kullanılır; değilse dosya yeniden hash'lenir.
    Döner: (sha256, yeniden_hashlendi_mi)."""
    if record is not None and record.sha256 and record.size_bytes == pdf.size_bytes and record.mtime == pdf.mtime:
        return record.sha256, False
    return compute_sha256(pdf.absolute_path), True


def sync_with_state(result, state, summary, logger):
    """Keşfedilen belgeleri state'e işler. Değişmeyen belgelerin durumuna dokunulmaz; içeriği değişen
    belge yeni bir belge gibi `pending` olur. Filtre dışı kalan kayıtlar değiştirilmez."""
    for pdf in result.documents:
        rel = pdf.relative_path
        record = state.get(rel)
        stat_fields = {"size_bytes": pdf.size_bytes, "mtime": pdf.mtime}
        try:
            sha, rehashed = resolve_identity(pdf, record)
        except OSError as exc:
            state.update(rel, save=False, status=DocumentStatus.failed, error_stage=ErrorStage.discovery,
                         error=f"Dosya okunamadı: {exc}", last_run_id=summary.run_id, **stat_fields)
            summary.discovery_failed += 1
            logger.error("Okunamadı: %s (%s)", rel, exc)
            continue
        if record is None or record.sha256 is None:
            state.update(rel, save=False, sha256=sha, status=DocumentStatus.pending,
                         error_stage=None, error=None, **stat_fields)
            summary.new += 1
            logger.debug("Yeni: %s %s", rel, sha)
        elif record.sha256 != sha:
            state.update(rel, save=False, sha256=sha, status=DocumentStatus.pending, attempts=0,
                         error_stage=None, error=None, **stat_fields)
            summary.changed += 1
            logger.info("İçerik değişti: %s", rel)
        else:
            if rehashed:
                state.update(rel, save=False, **stat_fields)
                logger.debug("Yalnızca boyut/mtime değişti, içerik aynı: %s", rel)
            summary.unchanged += 1
    summary.discovered = len(result.documents)
    summary.excluded_by_filter = len(result.excluded_by_filter)
    state.save()
    return summary
