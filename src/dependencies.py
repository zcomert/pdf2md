"""Bağımlılık ön kontrolü. Yalnızca standart kütüphaneyi kullanır ve eski Python sürümlerinde de
ayrıştırılabilir kalmalıdır: üçüncü taraf paketler içe aktarılmadan önce çalışır (§26, §38 kriter 19)."""
import importlib.util
import os
import sys

MIN_PYTHON = (3, 11)
# pip paket adı -> içe aktarılan modül adı
REQUIRED_PACKAGES = {
    "pymupdf": "pymupdf",
    "ollama": "ollama",
    "pydantic": "pydantic",
    "pyyaml": "yaml",
    "pandas": "pandas",
    "tqdm": "tqdm",
    "pillow": "PIL",
    "pylatexenc": "pylatexenc",
}


def python_supported(version_info=None):
    return tuple((version_info or sys.version_info)[:2]) >= MIN_PYTHON


def missing_packages(find_spec=None):
    find_spec = find_spec or importlib.util.find_spec
    missing = []
    for package, module in REQUIRED_PACKAGES.items():
        try:
            found = find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(package)
    return missing


def venv_python_command():
    if os.name == "nt":
        return ".venv\\Scripts\\python.exe"
    return ".venv/bin/python"


def install_command():
    return "{0} -m pip install -r requirements.txt".format(venv_python_command())


def bootstrap_check(stream=None, version_info=None, find_spec=None):
    """Sorun varsa mesajı yazar ve çıkış kodu 2 döndürür; sorun yoksa None."""
    stream = stream or sys.stderr
    if not python_supported(version_info):
        current = ".".join(str(part) for part in (version_info or sys.version_info)[:3])
        stream.write("Hata: Python {0}.{1} veya üzeri gerekir (mevcut: {2}).\n".format(
            MIN_PYTHON[0], MIN_PYTHON[1], current))
        return 2
    missing = missing_packages(find_spec)
    if missing:
        stream.write("Hata: Eksik Python paketleri: {0}\nKurulum:\n  {1}\n".format(
            ", ".join(missing), install_command()))
        return 2
    return None
