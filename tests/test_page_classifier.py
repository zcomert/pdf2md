import pytest

from src.config import PdfConfig
from src.document_model import PageClass
from src.page_classifier import VECTOR_TEXT_MIN_DRAWINGS, classify_page, image_area_ratio, union_area

CONFIG = PdfConfig()


def test_union_area_counts_overlap_once():
    assert union_area([(0, 0, 10, 10), (5, 5, 15, 15)], (0, 0, 100, 100)) == 175
    assert union_area([(0, 0, 10, 10), (0, 0, 10, 10)], (0, 0, 100, 100)) == 100


def test_union_area_is_clipped_to_page():
    assert union_area([(-10, -10, 10, 10)], (0, 0, 100, 100)) == 100
    assert union_area([(200, 200, 300, 300)], (0, 0, 100, 100)) == 0


def test_image_ratio_never_exceeds_one():
    assert image_area_ratio([(0, 0, 100, 100), (0, 0, 100, 100)], 100, 100) == 1.0


@pytest.mark.parametrize("chars, ratio, drawings, expected, codes", [
    (500, 0.1, None, PageClass.text, []),
    (500, 0.3, None, PageClass.mixed, []),
    (100, 0.29, None, PageClass.text, []),
    (10, 0.5, None, PageClass.scanned, []),
    (10, 0.2, None, PageClass.text, ["low_text_page"]),
    (10, 0.0, 50, PageClass.text, ["low_text_page"]),
    (10, 0.0, VECTOR_TEXT_MIN_DRAWINGS, PageClass.scanned, ["vector_text_suspected"]),
    (115, 0.0, 5289, PageClass.scanned, ["vector_text_suspected"]),   # damga satırlı vektör metin sayfası
    (3457, 0.0, 3867, PageClass.text, []),                             # logo/grafik yoğun normal ilk sayfa
    (400, 0.0, 999, PageClass.text, []),
])
def test_classify_page(chars, ratio, drawings, expected, codes):
    assert classify_page(chars, ratio, drawings, CONFIG) == (expected, codes)


def test_thresholds_come_from_config():
    strict = PdfConfig(min_text_chars=1000, mixed_image_ratio=0.1)
    assert classify_page(500, 0.6, None, strict) == (PageClass.scanned, [])
    assert classify_page(1500, 0.15, None, strict) == (PageClass.mixed, [])
