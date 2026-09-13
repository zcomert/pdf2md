import os
import re
from pathlib import Path, PurePosixPath

from .errors import PreflightError

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
# Çıktı kökünde sistemin kullandığı klasörler; belge veya giriş alt klasörü bu adları alamaz (§6.2)
RESERVED_OUTPUT_DIRS = {"_cache", "logs", "collections"}


def normalize(path):
    return Path(path).expanduser().resolve()


def is_pdf_path(path):
    return Path(path).suffix.lower() == ".pdf"


def input_root(input_path):
    """Göreli yolların ve 'giriş klasörü' kurallarının kökü: klasörün kendisi veya tek PDF'in klasörü."""
    path = normalize(input_path)
    if path.is_dir():
        return path
    if path.is_file() or is_pdf_path(path):
        return path.parent
    return path


def default_output_dir(input_path):
    """`D:\\papers` → `D:\\papers_output`. Tek PDF için PDF'in klasörü esas alınır:
    `D:\\papers\\a.pdf` → `D:\\papers_output` (çıktı giriş klasörünün içine yazılmaz, §32.2)."""
    root = input_root(input_path)
    if not root.name:
        raise PreflightError(f"Sürücü kökü için varsayılan çıktı klasörü belirlenemez: {root}",
                             "--output ile bir çıktı klasörü verin")
    return root.with_name(f"{root.name}_output")


def is_within(child, parent):
    """`child`, `parent` ile aynı veya onun altındaysa True. Windows'ta büyük/küçük harf duyarsız."""
    child_str = os.path.normcase(str(normalize(child)))
    parent_str = os.path.normcase(str(normalize(parent))).rstrip("\\/")
    return child_str == parent_str or child_str.startswith(parent_str + os.sep)


def ensure_under_output(path, output_dir):
    resolved = normalize(path)
    if not is_within(resolved, output_dir):
        raise ValueError(f"Yol çıktı klasörünün dışında: {resolved}")
    return resolved


def safe_filename(name):
    """§20.1: geçersiz karakterler `_`, sondaki nokta/boşluk silinir, ayrılmış adlara `_` öneki."""
    cleaned = INVALID_CHARS.sub("_", name).rstrip(". ")
    if not cleaned:
        return "_"
    if cleaned.split(".")[0].rstrip(" ").upper() in RESERVED_NAMES:
        cleaned = "_" + cleaned
    return cleaned


def safe_stem(filename):
    name = PurePosixPath(filename).name
    return safe_filename(name[:-4] if name.lower().endswith(".pdf") else name)


def document_output_path(relative_path, suffix=""):
    """`fatigue/article_003.pdf` → `fatigue/article_003/article_003.md` (çıktı klasörüne göre)."""
    rel = PurePosixPath(relative_path)
    folders = [safe_filename(part) for part in rel.parent.parts]
    stem = safe_stem(rel.name) + suffix
    if folders:
        if folders[0].casefold() in RESERVED_OUTPUT_DIRS:
            folders[0] += "_"
    elif stem.casefold() in RESERVED_OUTPUT_DIRS:
        stem += "_"
    return PurePosixPath(*folders, stem, f"{stem}.md").as_posix()


def _folder_key(output_path):
    return PurePosixPath(output_path).parent.as_posix().casefold()


def resolve_output_paths(documents, existing=None):
    """`documents`: (göreli_yol, sha256) çiftleri. Normalizasyon sonrası çakışan belge klasörlerine
    `_<sha8>` eklenir (§20.1). State'te kayıtlı yollar (`existing`) önce ayrılır; bu çalıştırmada filtre
    dışında kalan belgelerinkiler de dahil. Böylece sonradan eklenen bir PDF, mevcut bir belgenin çıktı
    yolunu alamaz."""
    existing = existing or {}
    ordered = sorted(documents, key=lambda item: (item[0].casefold(), item[0]))
    listed = {rel for rel, _ in ordered}
    result, taken = {}, set()
    for rel in sorted(existing, key=lambda item: (item not in listed, item.casefold(), item)):
        path = existing[rel]
        if path and _folder_key(path) not in taken:
            taken.add(_folder_key(path))
            if rel in listed:
                result[rel] = path
    for rel, sha in ordered:
        if rel in result:
            continue
        path = document_output_path(rel)
        attempt = 0
        while _folder_key(path) in taken:
            attempt += 1
            suffix = f"_{sha[:8]}" if attempt == 1 else f"_{sha[:8]}_{attempt}"
            path = document_output_path(rel, suffix)
        result[rel] = path
        taken.add(_folder_key(path))
    return result
