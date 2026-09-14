"""CPU aşamasının paralel yürütülmesi (§27): `parse_pdf` (+ OCR) süreç havuzunda çalışır.

Worker yalnızca `_cache/<sha>/document.json` yazar (atomik); state ve log yalnızca ana süreçtedir. Aynı SHA-256'lı
belgeler bir kez ayrıştırılır (§9.5). Model aşaması ana süreçte belge sırasıyla ilerler; havuz önündeki belgeleri
sınırlı bir tamponla önceden hazırlar.
"""
import re
import signal
from concurrent.futures import ProcessPoolExecutor

from .cache_manager import CacheManager
from .pdf_parser import parse_pdf


def _ignore_interrupts():
    """Ctrl+C konsoldaki tüm süreçlere gider; iptal kararını ana süreç verir, worker yarıda kesilmez."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)


def parse_to_cache(absolute_path, relative_path, sha256, pdf_config, ocr_settings, output_dir):
    """Worker görevi. Döner: sayfa sayısı (ayrıntılar önbellekten okunur)."""
    document = parse_pdf(absolute_path, relative_path, sha256, pdf_config, ocr_settings)
    CacheManager(output_dir).save_document(document)
    return document.stats.pages


class ParsePool:
    def __init__(self, workers, output_dir):
        self.workers = workers
        self.output_dir = output_dir
        self._executor = None
        self._futures = {}

    def submit(self, pdf, sha256, pdf_config, ocr_settings):
        if sha256 in self._futures:
            return self._futures[sha256]
        if self._executor is None:
            self._executor = ProcessPoolExecutor(max_workers=self.workers, initializer=_ignore_interrupts)
        future = self._executor.submit(parse_to_cache, pdf.absolute_path, pdf.relative_path, sha256, pdf_config,
                                       ocr_settings, self.output_dir)
        self._futures[sha256] = future
        return future

    def pending(self, sha256):
        return self._futures.get(sha256)

    def shutdown(self, cancel=False):
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=cancel)
            self._executor = None


_HEADER_RE = re.compile(r'"schema_version":"([^"]*)","parser_version":"([^"]*)","parse_config_hash":"([^"]*)"')


def cache_header_matches(cache, sha256, schema_version, parser_version, config_hash):
    """Önceden ayrıştırma kararı için ucuz kontrol: `document.json`'ın ilk baytları. Tam doğrulama (şema, OCR
    imzası) belge işlenirken yapılır; burada geçen ama orada geçmeyen belge sırayla ayrıştırılır."""
    try:
        with open(cache.document_json_path(sha256), "rb") as handle:
            head = handle.read(512).decode("utf-8", errors="ignore")
    except OSError:
        return False
    match = _HEADER_RE.search(head)
    return bool(match) and match.groups() == (schema_version, parser_version, config_hash)
