"""Belge çıktı klasöründeki `assets/` yönetimi (§6.2, §15): yalnızca Markdown'ın referans verdiği görseller
kopyalanır, artık referans verilmeyenler silinir, hiç referans yoksa `assets/` kaldırılır."""
import contextlib
import filecmp
import shutil
from pathlib import Path, PurePosixPath

ASSETS_DIR = "assets"


def asset_relative_path(cache_path):
    """Önbellekteki `figures/figure_03.png` → Markdown'daki `assets/figures/figure_03.png`."""
    return str(PurePosixPath(ASSETS_DIR) / PurePosixPath(cache_path))


def sync_assets(document_dir, doc_cache_dir, cache_paths):
    """`cache_paths`: Markdown'da referans verilen önbellek yolları. Döner: kopyalanan dosya sayısı."""
    document_dir = Path(document_dir)
    assets_root = document_dir / ASSETS_DIR
    wanted = {assets_root / PurePosixPath(path) for path in cache_paths}
    copied = 0
    for path in sorted(cache_paths):
        source = Path(doc_cache_dir) / PurePosixPath(path)
        target = assets_root / PurePosixPath(path)
        if target.is_file() and filecmp.cmp(source, target, shallow=False):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.pdf2md.tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
        copied += 1
    if assets_root.is_dir():
        for existing in sorted(assets_root.rglob("*"), reverse=True):
            if existing.is_file() and existing not in wanted:
                existing.unlink()
            elif existing.is_dir():
                with contextlib.suppress(OSError):
                    existing.rmdir()  # yalnızca boşsa silinir
        with contextlib.suppress(OSError):
            assets_root.rmdir()
    return copied
