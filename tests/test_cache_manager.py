import json

import pytest

from src.cache_manager import CacheManager
from src.config import PdfConfig
from src.pdf_parser import parse_config_hash, parse_pdf
from tests.helpers import sha256_file

CONFIG_HASH = parse_config_hash(PdfConfig())


@pytest.fixture(scope="module")
def document(synthetic_pdf):
    path = synthetic_pdf("synthetic_single_column.pdf")
    return parse_pdf(path, path.name, sha256_file(path), PdfConfig())


def test_save_and_load(tmp_path, document):
    cache = CacheManager(tmp_path)
    cache.save_document(document)
    path = cache.document_json_path(document.source.sha256)
    assert path.is_file() and "\n  " not in path.read_text(encoding="utf-8")
    assert cache.load_document(document.source.sha256, CONFIG_HASH) == document


def test_force_skips_cache(tmp_path, document):
    cache = CacheManager(tmp_path)
    cache.save_document(document)
    assert cache.load_document(document.source.sha256, CONFIG_HASH, force=True) is None


@pytest.mark.parametrize("field, value", [
    ("schema_version", "0.9"), ("parser_version", "0.0.1"), ("parse_config_hash", "different"),
])
def test_version_or_config_change_invalidates(tmp_path, document, field, value):
    cache = CacheManager(tmp_path)
    cache.save_document(document)
    path = cache.document_json_path(document.source.sha256)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw[field] = value
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert cache.load_document(document.source.sha256, CONFIG_HASH) is None


def test_parse_config_change_changes_hash():
    assert parse_config_hash(PdfConfig(min_text_chars=50)) != CONFIG_HASH
    assert parse_config_hash(PdfConfig(render_dpi=300)) == CONFIG_HASH


def test_corrupt_or_missing_cache_returns_none(tmp_path, document):
    cache = CacheManager(tmp_path)
    sha = document.source.sha256
    assert cache.load_document(sha, CONFIG_HASH) is None
    cache.document_json_path(sha).parent.mkdir(parents=True)
    cache.document_json_path(sha).write_text("{bozuk", encoding="utf-8")
    assert cache.load_document(sha, CONFIG_HASH) is None


@pytest.mark.parametrize("bad", ["../../etc", "abc", "A" * 64, ""])
def test_invalid_sha_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        CacheManager(tmp_path).doc_dir(bad)


def test_paths_layout(tmp_path):
    cache = CacheManager(tmp_path)
    sha = "a" * 64
    assert cache.extraction_path(sha, "9f1e2d3c").relative_to(tmp_path).as_posix() == f"_cache/{sha}/extractions/9f1e2d3c.json"
    assert cache.renders_dir(sha).name == "renders" and cache.errors_dir(sha).name == "errors"
    with pytest.raises(ValueError):
        cache.extraction_path(sha, "../x")
