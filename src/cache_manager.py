import json
import re
from pathlib import Path

from pydantic import ValidationError

from . import PARSER_VERSION
from .atomic_io import atomic_write_json
from .document_model import DOCUMENT_SCHEMA_VERSION, DocumentModel
from .paths import ensure_under_output

CACHE_DIR = "_cache"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
PLAN_HASH_RE = re.compile(r"^[0-9a-f]{8,64}$")


class CacheManager:
    """`<output>/_cache/<sha256>/` yönetimi (§6.2). Önbellek silinse de sistem doğru çalışır; yalnızca
    işlemler yeniden yapılır."""

    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.root = self.output_dir / CACHE_DIR

    def doc_dir(self, sha256):
        if not SHA_RE.match(sha256 or ""):
            raise ValueError(f"Geçersiz SHA-256: {sha256!r}")
        return ensure_under_output(self.root / sha256, self.output_dir)

    def document_json_path(self, sha256):
        return self.doc_dir(sha256) / "document.json"

    def renders_dir(self, sha256):
        return self.doc_dir(sha256) / "renders"

    def model_raw_dir(self, sha256):
        return self.doc_dir(sha256) / "model_raw"

    def errors_dir(self, sha256):
        return self.doc_dir(sha256) / "errors"

    def extraction_path(self, sha256, plan_hash):
        if not PLAN_HASH_RE.match(plan_hash or ""):
            raise ValueError(f"Geçersiz plan hash: {plan_hash!r}")
        return self.doc_dir(sha256) / "extractions" / f"{plan_hash}.json"

    def load_document(self, sha256, parse_config_hash, force=False):
        """Geçerli önbellek kaydı veya None. Dosya yok, JSON bozuk, şema/ayrıştırıcı sürümü ya da
        ayrıştırma ayarları farklıysa kayıt geçersiz sayılır."""
        if force:
            return None
        path = self.document_json_path(sha256)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict) or raw.get("schema_version") != DOCUMENT_SCHEMA_VERSION \
                or raw.get("parser_version") != PARSER_VERSION or raw.get("parse_config_hash") != parse_config_hash:
            return None
        try:
            document = DocumentModel.model_validate(raw)
        except ValidationError:
            return None
        return document if document.source.sha256 == sha256 else None

    def save_document(self, document):
        # Satır düzeyindeki koordinatlar dosyanın çoğunu oluşturur; girintisiz yazım boyutu ~%45 azaltır.
        atomic_write_json(self.document_json_path(document.source.sha256), document, indent=None)
