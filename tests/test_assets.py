import pytest

from src.assets import asset_relative_path, sync_assets
from src.config import PdfConfig
from src.figure_extractor import materialize_assets
from src.pdf_parser import parse_pdf
from tests.helpers import sha256_file


@pytest.fixture(scope="module")
def table_equation_document(synthetic_pdf):
    path = synthetic_pdf("synthetic_table_equation.pdf")
    return path, parse_pdf(path, path.name, sha256_file(path), PdfConfig())


def test_materialize_writes_embedded_figure_and_skips_existing(tmp_path, table_equation_document):
    path, document = table_equation_document
    figure = document.figures[0]
    result = materialize_assets(path, document, tmp_path, 150, 8)
    image = tmp_path / figure.cache_path
    assert result.available == {figure.id} and result.written == 1 and not result.failed
    assert image.read_bytes().startswith(b"\x89PNG")
    before = image.stat().st_mtime_ns
    again = materialize_assets(path, document, tmp_path, 150, 8)
    assert again.written == 0 and again.available == {figure.id} and image.stat().st_mtime_ns == before
    assert materialize_assets(path, document, tmp_path, 150, 8, overwrite=True).written == 1


def test_inconsistent_table_region_is_rendered(tmp_path, table_equation_document):
    path, document = table_equation_document
    table = document.tables[0].model_copy(update={"consistent": False, "cache_path": "tables/table_01.png"})
    changed = document.model_copy(update={"tables": [table], "figures": []})
    result = materialize_assets(path, changed, tmp_path, 100, 8)
    assert result.available == {table.id}
    assert (tmp_path / "tables" / "table_01.png").stat().st_size > 0


def test_failed_extraction_is_reported(tmp_path, table_equation_document):
    path, document = table_equation_document
    broken = document.figures[0].model_copy(update={"image_xref": None, "bbox": (5000, 5000, 5100, 5100)})
    result = materialize_assets(path, document.model_copy(update={"figures": [broken]}), tmp_path, 100, 8)
    assert result.available == set() and result.failed and result.failed[0][0] == broken.id


def test_sync_assets_copies_referenced_and_removes_stale(tmp_path):
    cache = tmp_path / "cache"
    (cache / "figures").mkdir(parents=True)
    (cache / "figures" / "figure_01.png").write_bytes(b"one")
    (cache / "figures" / "figure_02.png").write_bytes(b"two")
    doc_dir = tmp_path / "doc"
    assert sync_assets(doc_dir, cache, ["figures/figure_01.png", "figures/figure_02.png"]) == 2
    assert sync_assets(doc_dir, cache, ["figures/figure_01.png"]) == 0
    assert (doc_dir / "assets" / "figures" / "figure_01.png").read_bytes() == b"one"
    assert not (doc_dir / "assets" / "figures" / "figure_02.png").exists()
    sync_assets(doc_dir, cache, [])
    assert not (doc_dir / "assets").exists()


def test_sync_assets_without_references_creates_nothing(tmp_path):
    sync_assets(tmp_path / "doc", tmp_path / "cache", [])
    assert not (tmp_path / "doc").exists()


def test_asset_relative_path():
    assert asset_relative_path("figures/figure_03.png") == "assets/figures/figure_03.png"
