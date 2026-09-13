import random
import re

import pytest

from src.config import AppConfig, OcrConfig
from src.layout_analyzer import RawBlock, RawLine
from src.ocr import (OCR_UNAVAILABLE_SIGNATURE, OcrSettings, TesseractInfo, build_ocr_blocks, find_tesseract,
                     merge_ocr_blocks, resolve_ocr_settings, select_languages, whitespace_gutter)
from src.preflight import check_ocr

W = 595.0


def fake_install(root, languages=("eng", "osd")):
    tessdata = root / "tessdata"
    tessdata.mkdir(parents=True)
    for language in languages:
        (tessdata / f"{language}.traineddata").write_bytes(b"x")
    return root


# --- kurulum keşfi ---

def test_find_via_config_install_dir_exe_and_tessdata(tmp_path):
    root = fake_install(tmp_path / "Tesseract-OCR", ("eng", "tur", "osd"))
    (root / "tesseract.exe").write_bytes(b"")
    by_dir = find_tesseract(str(root), environ={}, known_locations=[])
    assert by_dir.languages == ("eng", "tur") and by_dir.found_via == "config"  # osd dil olarak sayılmaz
    assert find_tesseract(str(root / "tesseract.exe"), environ={}, known_locations=[]).tessdata == root / "tessdata"
    assert find_tesseract(str(root / "tessdata"), environ={}, known_locations=[]).executable == root / "tesseract.exe"


def test_config_path_without_languages_is_not_found(tmp_path):
    empty = tmp_path / "empty"
    (empty / "tessdata").mkdir(parents=True)
    assert find_tesseract(str(empty), environ={}, known_locations=[]) is None
    assert find_tesseract(str(tmp_path / "yok"), environ={}, known_locations=[]) is None


def test_known_location_and_tessdata_prefix(tmp_path, monkeypatch):
    import src.ocr as module
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    monkeypatch.setattr(module.os, "name", "nt")
    root = fake_install(tmp_path / "Program Files" / "Tesseract-OCR")
    assert find_tesseract(None, environ={}, known_locations=[tmp_path / "nope", root]).found_via == "known_location"
    prefix = fake_install(tmp_path / "custom")
    found = find_tesseract(None, environ={"TESSDATA_PREFIX": str(prefix / "tessdata")}, known_locations=[])
    assert found.found_via == "tessdata_prefix" and found.languages == ("eng",)


def test_select_languages():
    assert select_languages(["eng", "tur", "deu"], ("eng", "deu")) == (["eng", "deu"], ["tur"])


def test_resolve_settings_cases():
    info = TesseractInfo(tessdata="C:/t", languages=("eng",), version="v5.4.0")
    settings, messages = resolve_ocr_settings(OcrConfig(languages=["eng", "tur"]), 250, info=info)
    assert settings.languages == "eng" and settings.signature == "tesseract:v5.4.0:eng:250"
    assert messages == ["Kurulu olmayan OCR dilleri: tur"]
    assert resolve_ocr_settings(OcrConfig(languages=["tur"]), 250, info=info)[0] is None
    assert resolve_ocr_settings(OcrConfig(enabled=False), 250, info=info)[0] is None
    assert OcrSettings("eng+tur", "x", 300).signature != OcrSettings("eng", "x", 300).signature


def test_check_ocr_results(monkeypatch):
    info = TesseractInfo(tessdata="C:/t", languages=("eng",), version="v5")
    ok, settings = check_ocr(AppConfig(), info=info)
    assert ok.ok and settings is not None
    warning, settings = check_ocr(AppConfig.model_validate({"ocr": {"languages": ["eng", "tur"]}}), info=info)
    assert warning.severity == "warning" and "tur" in warning.message and settings.languages == "eng"
    import src.preflight as module
    monkeypatch.setattr(module, "find_tesseract", lambda path: None)
    missing, settings = check_ocr(AppConfig())
    assert missing.severity == "warning" and "winget install" in missing.hint and settings is None
    disabled, settings = check_ocr(AppConfig.model_validate({"ocr": {"enabled": False}}))
    assert disabled.ok and settings is None


# --- OCR düzeni ---

def word(x0, y0, text, width=None, height=10):
    return (x0, y0, x0 + (width or 5.5 * len(text)), y0 + height, text, 0, 0, 0)


def justified_row(y, x_start, x_end, seed):
    """Sütunu kenardan kenara dolduran, kelime uzunlukları ve aralıkları satıra göre değişen iki yana yaslı satır."""
    rng = random.Random(seed)
    words, x = [], x_start
    while True:
        length = rng.randint(2, 10)
        width = 5.5 * length
        if x + width > x_end:
            break
        words.append((x, y, x + width, y + 10, "w" * length, 0, 0, 0))
        x += width + rng.uniform(3, 6)
    last = words[-1]
    words[-1] = (last[0], y, x_end, y + 10, last[4], 0, 0, 0)  # iki yana yaslı: son kelime kenara dayanır
    return words


def two_column_words(rows=20, gutter_gap=5):
    """İki yana yaslı iki sütun; kelime aralıkları satırdan satıra değişir, sütun boşluğu dar (5 pt) ama sabittir."""
    words = []
    for r in range(rows):
        y = 100 + r * 12
        words += justified_row(y, 62, 296, r)
        words += justified_row(y, 296 + gutter_gap, 550, r + 11)
    return words


def test_whitespace_gutter_finds_narrow_column_gap():
    gutter = whitespace_gutter(two_column_words(), W)
    assert gutter is not None and 293 <= gutter <= 302


def test_whitespace_gutter_single_column_none():
    words = [w for r in range(20) for w in justified_row(100 + r * 12, 62, 550, r)]
    assert whitespace_gutter(words, W) is None


def test_build_ocr_blocks_separates_columns():
    blocks = build_ocr_blocks(1, two_column_words(rows=20), [], W)
    assert len(blocks) == 2 and all(b.source == "ocr" for b in blocks)
    left, right = sorted(blocks, key=lambda b: b.bbox[0])
    assert left.bbox[2] <= 297 and right.bbox[0] >= 300, "bloklar sütun boşluğunu kesmemeli"
    assert len(left.lines) == len(right.lines) == 20


def test_build_ocr_blocks_drops_text_layer_words_and_noise():
    words = [word(12, 100, "6", width=6), word(62, 100, "majority"), word(120, 100, "of"), word(140, 100, "road"),
             word(62, 112, ":", width=3), word(70, 112, "‘", width=3)]
    stamp_box = (10, 50, 20, 700)  # metin katmanındaki dikey damga
    blocks = build_ocr_blocks(1, words, [((60, 98, 170, 112), 9.5)], W, text_line_boxes=[stamp_box])
    assert [b.text for b in blocks] == ["majority of road"]
    assert blocks[0].lines[0].size == 9.5


def test_build_ocr_blocks_splits_on_gap_indent_and_size():
    lines = [("First paragraph line", 62, 100, 10), ("continues here", 62, 112, 10),
             ("Indented new paragraph", 75, 124, 10), ("after big gap", 62, 170, 10), ("HEADING", 62, 184, 16)]
    words = []
    for text, x, y, height in lines:
        words.append(word(x, y, text, height=height))
    sizes = [((0, y, 600, y + h), 14.0 if h == 16 else 9.0) for _, _, y, h in lines]
    blocks = build_ocr_blocks(1, words, sizes, W)
    assert [b.text for b in blocks] == ["First paragraph line\ncontinues here", "Indented new paragraph",
                                        "after big gap", "HEADING"]


def test_merge_ocr_blocks_prefers_text_layer():
    text_line = RawLine("Existing text", (50, 50, 200, 62), "Times", 10, False, False, 12, 0)
    text_block = RawBlock(1, text_line.bbox, [text_line])
    duplicate = RawLine("Existing text", (51, 50, 199, 62), "ocr", 10, False, False, 12, 0)
    new = RawLine("Only in scan", (50, 300, 200, 312), "ocr", 10, False, False, 10, 0)
    blocks, added = merge_ocr_blocks([text_block], [RawBlock(1, (50, 50, 200, 312), [duplicate, new])])
    assert added == 1 and blocks[1].text == "Only in scan" and blocks[1].source == "ocr"


def test_unavailable_signature_constant():
    assert OCR_UNAVAILABLE_SIGNATURE == "unavailable"


# --- gerçek OCR (Tesseract kuruluysa) ---

@pytest.fixture(scope="module")
def ocr_settings():
    settings, _ = resolve_ocr_settings(OcrConfig(), 250)
    if settings is None:
        pytest.skip("Tesseract kullanılamıyor")
    return settings


@pytest.mark.requires_tesseract
def test_synthetic_scanned_pdf_ocr_accuracy(synthetic_pdf, ocr_settings):
    from src.config import PdfConfig
    from src.pdf_parser import parse_pdf
    from tests.fixtures.generate_fixtures import EXPECTED
    document = parse_pdf(synthetic_pdf("synthetic_scanned.pdf"), "s.pdf", "0" * 64, PdfConfig(), ocr_settings)
    page = document.pages[0]
    assert page.ocr_applied and document.stats.ocr_pages == 1 and document.warnings == []
    recovered = re.findall(r"\w+", " ".join(b.text for b in document.blocks).lower())
    expected = re.findall(r"\w+", " ".join(EXPECTED["synthetic_scanned.pdf"]["ocr_lines"]).lower())
    matched = sum(1 for token in expected if token in recovered)
    assert matched / len(expected) >= 0.9
    assert all(b.source_method.value == "ocr" for b in document.blocks if b.text)
    assert document.headings()[0].text == "Scanned Document Sample"


@pytest.mark.requires_tesseract
def test_real_vector_text_article_is_recovered_by_ocr(fixtures_dir, ocr_settings):
    path = fixtures_dir / "real" / "2025_Shilaskar_Intelligent.pdf"
    if not path.is_file():
        pytest.skip("Gerçek makale yok")
    from src.config import PdfConfig
    from src.markdown_builder import unreadable_pages
    from src.pdf_parser import parse_pdf
    document = parse_pdf(path, path.name, "0" * 64, PdfConfig(), ocr_settings)
    assert document.stats.ocr_pages == 6 and unreadable_pages(document) == []
    assert not any(w.code == "vector_text_suspected" for w in document.warnings)
    text = " ".join(b.text for b in document.blocks)
    assert "Deeply Nonverbal Vocalization Dataset" in text
    assert "I. INTRODUCTION" in [h.text for h in document.headings()]
    assert document.pages[0].columns == 2
    # kenardaki dikey IEEE damgasının OCR kopyası sütun satırlarına karışmaz
    assert not any(re.match(r"^\W?\w{1,2} (majority|intrusive|Self-driving)", b.text) for b in document.blocks)
