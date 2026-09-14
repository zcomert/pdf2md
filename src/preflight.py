import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import dependencies
from .errors import PreflightError
from .model_clients import ModelUnavailable
from .ocr import find_tesseract, resolve_ocr_settings
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


def check_collection_output(collection_output, input_path):
    """§21.5, §32.3: `--collection-output` var olan dosyanın üzerine yazmaz ve giriş klasörünün içinde olamaz."""
    if not collection_output:
        return None
    target = Path(collection_output)
    if target.exists():
        return CheckResult("collection_output", False, "error", f"Koleksiyon çıktı dosyası zaten var: {target}",
                           "Farklı bir --collection-output verin; mevcut dosyanın üzerine yazılmaz")
    if is_within(target, input_root(input_path)):
        return CheckResult("collection_output", False, "error",
                           f"Koleksiyon çıktısı giriş klasörünün içinde olamaz: {target}")
    return _ok("collection_output", f"Koleksiyon çıktısı: {target}")


def check_xlsx(config, find_spec=None):
    """§22.1: `output.save_xlsx` için `openpyxl` gerekir; yoksa uyarı, yalnızca CSV yazılır."""
    if not config.output.save_xlsx:
        return None
    import importlib.util
    find_spec = find_spec or importlib.util.find_spec
    if find_spec("openpyxl") is None:
        return CheckResult("xlsx", False, "warning", "output.save_xlsx açık ama openpyxl kurulu değil; yalnızca CSV yazılacak",
                           "pip install -r requirements-optional.txt")
    return _ok("xlsx", "papers_summary.xlsx yazılacak (openpyxl kurulu)")


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


OCR_INSTALL_HINT = ("Windows: winget install UB-Mannheim.TesseractOCR (Türkçe için tur.traineddata dosyasını "
                    "tessdata klasörüne ekleyin); Linux: apt install tesseract-ocr tesseract-ocr-tur; "
                    "macOS: brew install tesseract tesseract-lang. Farklı konumdaysa ocr.tesseract_path ayarlayın")


def check_ocr(config, info=None):
    """§26: OCR etkinse Tesseract ve dil paketleri. Eksiklik uyarıdır; taranmış sayfalar görsel modele
    yönlendirilir (Faz 07). Döner: (CheckResult, OcrSettings veya None)."""
    if not config.ocr.enabled:
        return _ok("ocr", "OCR kapalı"), None
    info = info if info is not None else find_tesseract(config.ocr.tesseract_path)
    settings, messages = resolve_ocr_settings(config.ocr, config.pdf.render_dpi, info=info)
    if info is None:
        return CheckResult("ocr", False, "warning", "Tesseract bulunamadı; taranmış sayfalar OCR'lanamayacak",
                           OCR_INSTALL_HINT), None
    if settings is None:
        return CheckResult("ocr", False, "warning", "; ".join(messages) + f" (kurulu: {', '.join(info.languages)})",
                           OCR_INSTALL_HINT), None
    detail = f"Tesseract {info.version or '?'} ({info.tessdata}), diller: {settings.languages}"
    if messages:
        return CheckResult("ocr", False, "warning", f"{'; '.join(messages)}. {detail}", OCR_INSTALL_HINT), settings
    return _ok("ocr", detail), settings


def normalize_model_name(name):
    """Ollama etiketsiz adı `:latest` olarak saklar (`gemma4` → `gemma4:latest`)."""
    return name if ":" in name else f"{name}:latest"


def check_models(config, backend):
    """§26: Ollama erişimi, metin ve görsel modeli. Döner: (CheckResult listesi, {"text": ModelInfo|None,
    "vision": ModelInfo|None}). Görsel model eksikliği `fast` modunda veya `vision_required: false` ise uyarıdır."""
    try:
        installed = backend.list_models()
    except ModelUnavailable:
        return [CheckResult("ollama", False, "error", f"Ollama'ya erişilemiyor: {config.ollama.endpoint}",
                            "Ollama'yı başlatın (Ollama uygulaması veya `ollama serve`)")], {}
    results = [_ok("ollama", f"Ollama erişilebilir ({config.ollama.endpoint}), {len(installed)} model kurulu")]
    models = {}
    for role, name, required in (("text", config.models.text, True),
                                 ("vision", config.models.vision,
                                  config.models.vision_required and config.mode != "fast")):
        info = installed.get(normalize_model_name(name))
        models[role] = info
        if info is not None:
            results.append(_ok(f"model_{role}", f"{info.reference}"))
            continue
        message = f"Required model not found: {name}"
        hint = f"Run:\n  ollama pull {name}"
        if required:
            results.append(CheckResult(f"model_{role}", False, "error", message, hint))
        else:
            results.append(CheckResult(f"model_{role}", False, "warning", message + " (görsel model olmadan devam "
                                       "ediliyor; OCR'sız taranmış sayfalar okunamaz, tablo/formüller işaretli kalır)", hint))
    return results, models


def check_gpu():
    """§26: GPU bilgisi (nvidia-smi). Bulunamazsa uyarı; model çağrıları CPU'da çok yavaş olabilir."""
    try:
        completed = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
                                    "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        line = completed.stdout.strip().splitlines()[0]
        name, total, free = (part.strip() for part in line.split(","))
        return _ok("gpu", f"GPU: {name}, VRAM {int(total)} MiB ({int(free)} MiB boş)")
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return CheckResult("gpu", False, "warning", "GPU bilgisi alınamadı (nvidia-smi yok veya çalışmadı)")


def check_vram(workers, models, free_mib):
    """§27: `llm_workers > 1` ve iki modelin toplam boyutu boş VRAM'i aşıyorsa 1'e düşürülür. Döner: (worker, uyarı)."""
    if workers <= 1:
        return workers, None
    total_mib = sum(info.size_bytes for info in models.values() if info) / 2 ** 20
    if free_mib is None or total_mib > free_mib:
        return 1, CheckResult("vram", False, "warning", f"Modeller ({total_mib:.0f} MiB) boş VRAM'e sığmıyor; "
                                                     "llm_workers 1'e düşürüldü")
    return workers, None


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
