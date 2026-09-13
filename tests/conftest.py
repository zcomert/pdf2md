import functools
import os
import shutil
import urllib.request
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PDF_SUFFIXES = {".pdf"}
WINDOWS_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def pytest_configure(config):
    import fitz
    fitz.TOOLS.mupdf_display_errors(False)  # bozuk fixture'lar için beklenen MuPDF mesajlarını gizle
    config.addinivalue_line("markers", "requires_tesseract: Tesseract kurulu değilse testi atlar")
    config.addinivalue_line("markers", "requires_ollama: yerel Ollama servisi erişilemiyorsa testi atlar")


@functools.cache
def tesseract_available():
    explicit = os.environ.get("TESSERACT_PATH")
    if explicit:
        return Path(explicit).is_file()
    return shutil.which("tesseract") is not None or WINDOWS_TESSERACT.is_file()


@functools.cache
def ollama_available():
    endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def pytest_runtest_setup(item):
    if item.get_closest_marker("requires_tesseract") and not tesseract_available():
        pytest.skip("Tesseract bulunamadı (PATH, TESSERACT_PATH veya varsayılan kurulum konumu)")
    if item.get_closest_marker("requires_ollama") and not ollama_available():
        pytest.skip("Ollama erişilemiyor (OLLAMA_ENDPOINT, varsayılan http://127.0.0.1:11434)")


@pytest.fixture
def valid_config():
    from src.config import AppConfig
    return AppConfig()


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    """Depo kökündeki olası config.yaml testleri etkilemesin."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _close_log_handlers():
    yield
    from src.logger import close_logging
    close_logging()


@pytest.fixture(scope="session")
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def synthetic_pdf():
    """`synthetic_pdf("synthetic_scanned.pdf")` -> fixture dosyasının yolu."""
    def resolve(name):
        path = FIXTURES_DIR / name
        if not path.is_file():
            raise FileNotFoundError(
                f"{name} yok. Üretmek için: python -m tests.fixtures.generate_fixtures")
        return path
    return resolve


def _ignore_non_pdf(directory, names):
    ignored = set()
    for name in names:
        path = Path(directory) / name
        if path.is_dir():
            if name in {"__pycache__", "reference", "real"}:
                ignored.add(name)
        elif path.suffix.lower() not in PDF_SUFFIXES:
            ignored.add(name)
    return ignored


@pytest.fixture
def tmp_input_copy(tmp_path):
    """Sentetik fixture PDF'lerini (alt klasörler dahil) geçici bir giriş klasörüne kopyalar.
    Gerçek makaleler (`real/`) büyük olduğu için kopyalanmaz; gerekirse `fixtures_dir / "real"` doğrudan kullanılır."""
    target = tmp_path / "input"
    shutil.copytree(FIXTURES_DIR, target, ignore=_ignore_non_pdf)
    return target


@pytest.fixture
def no_ocr_config(tmp_path):
    """OCR kapalı config dosyası: taranmış sayfa sonuçları makinede Tesseract kurulu olup olmamasına bağlı olmasın."""
    path = tmp_path / "no_ocr.yaml"
    path.write_text("ocr:\n  enabled: false\n", encoding="utf-8")
    return path


@pytest.fixture
def tmp_output(tmp_path):
    """Giriş klasörünün dışında, henüz oluşturulmamış çıktı klasörü yolu."""
    return tmp_path / "output"
