import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import dependencies
from .errors import PreflightError
from .paths import input_root, is_pdf_path, is_within


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    severity: Literal["error", "warning", "info"]
    message: str
    hint: str | None = None


def _ok(name, message):
    return CheckResult(name, True, "info", message)


def check_python(version_info=None):
    if dependencies.python_supported(version_info):
        return _ok("python", f"Python {sys.version.split()[0]}")
    return CheckResult("python", False, "error", f"Python {dependencies.MIN_PYTHON[0]}.{dependencies.MIN_PYTHON[1]}+ gerekir")


def check_virtualenv(prefix=None, base_prefix=None):
    prefix = prefix or sys.prefix
    base_prefix = base_prefix or sys.base_prefix
    if prefix != base_prefix:
        return _ok("virtualenv", f"Sanal ortam: {prefix}")
    return CheckResult("virtualenv", False, "warning", "Uygulama sanal ortam dışında çalışıyor",
                       f"{dependencies.venv_python_command()} process_papers.py ...")


def check_dependencies(find_spec=None):
    missing = dependencies.missing_packages(find_spec)
    if not missing:
        return _ok("dependencies", "Zorunlu Python paketleri kurulu")
    return CheckResult("dependencies", False, "error", f"Eksik Python paketleri: {', '.join(missing)}",
                       dependencies.install_command())


def check_input(input_path):
    path = Path(input_path)
    if not path.exists():
        return CheckResult("input", False, "error", f"Giriş yolu bulunamadı: {path}")
    try:
        if path.is_dir():
            with os.scandir(path) as entries:
                next(entries, None)
        else:
            if not is_pdf_path(path):
                return CheckResult("input", False, "error", f"Giriş dosyası PDF değil: {path}")
            with open(path, "rb") as handle:
                handle.read(1)
    except OSError as exc:
        return CheckResult("input", False, "error", f"Giriş yolu okunamıyor: {path}: {exc}")
    return _ok("input", f"Giriş: {path}")


def check_output(input_path, output_dir):
    root = input_root(input_path)
    output = Path(output_dir)
    if is_within(output, root):
        return CheckResult("output", False, "error",
                           f"Çıktı klasörü giriş klasörüyle aynı veya onun içinde olamaz: {output}",
                           "Giriş klasörünün dışında bir --output verin")
    if output.exists() and not output.is_dir():
        return CheckResult("output", False, "error", f"Çıktı yolu bir dosya: {output}")
    return _ok("output", f"Çıktı: {output}")


def check_disk(output_dir, min_free_mb):
    probe = Path(output_dir)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        free_mb = shutil.disk_usage(probe).free // (1024 * 1024)
    except OSError as exc:
        return CheckResult("disk", False, "error", f"Boş disk alanı okunamadı: {probe}: {exc}")
    if free_mb < min_free_mb:
        return CheckResult("disk", False, "error",
                           f"Yetersiz disk alanı: {free_mb} MB boş, en az {min_free_mb} MB gerekli ({probe})")
    return _ok("disk", f"Boş disk alanı: {free_mb} MB")


def run_preflight(config, input_path, output_dir):
    """§26 kontrolleri (Ollama, model, Tesseract, GPU hariç). Kilit ayrıca `OutputLock` ile alınır."""
    results = [check_python(), check_virtualenv(), check_dependencies(), _ok("config", "Yapılandırma geçerli"),
               check_input(input_path)]
    results.append(check_output(input_path, output_dir))
    results.append(check_disk(output_dir, config.processing.min_free_disk_mb))
    return results


def raise_on_errors(results):
    errors = [result for result in results if not result.ok and result.severity == "error"]
    if not errors:
        return
    message = "\n".join(f"- {result.message}" + (f"\n  Öneri: {result.hint}" if result.hint else "")
                        for result in errors)
    raise PreflightError(f"Başlangıç kontrolleri başarısız:\n{message}")
