import pytest

from src.config import PdfConfig
from src.document_model import BlockType, DocumentModel, PageClass
from src.errors import DocumentError, ErrorStage
from src.pdf_parser import build_sections, parse_pdf
from tests.fixtures.generate_fixtures import EXPECTED
from tests.helpers import sha256_file

CONFIG = PdfConfig()


def parse(path):
    return parse_pdf(path, path.name, sha256_file(path), CONFIG)


@pytest.fixture(scope="module")
def parsed(request):
    cache = {}

    def get(path):
        if path not in cache:
            cache[path] = parse(path)
        return cache[path]
    return get


def test_single_column_headings_match_expected(synthetic_pdf, parsed):
    doc = parsed(synthetic_pdf("synthetic_single_column.pdf"))
    expected = EXPECTED["synthetic_single_column.pdf"]
    assert doc.title == expected["title"]
    assert [(b.text, b.heading_level) for b in doc.headings()] == [(h["text"], h["level"]) for h in expected["headings"]]
    assert [b.text for b in doc.blocks if b.type == BlockType.list] == [f"- {i}" for i in expected["list_items"]]
    assert doc.pages[0].page_class == PageClass.text and doc.pages[0].columns == 1


def test_sections_tree(synthetic_pdf, parsed):
    doc = parsed(synthetic_pdf("synthetic_single_column.pdf"))
    sections = {s.title: s for s in doc.sections}
    assert sections["2.1 Dataset"].parent_id == sections["2. Method"].id
    assert sections["2.1 Dataset"].number == "2.1"
    assert sections["2. Method"].end_order == sections["3. Conclusion"].start_order - 1
    assert sections["1. Introduction"].parent_id == sections[EXPECTED["synthetic_single_column.pdf"]["title"]].id


def test_two_column_reading_order(synthetic_pdf, parsed):
    doc = parsed(synthetic_pdf("synthetic_two_column.pdf"))
    text = [b.text for b in doc.blocks]
    positions = [next(i for i, t in enumerate(text) if t.startswith(marker))
                 for marker in EXPECTED["synthetic_two_column.pdf"]["reading_order_markers"]]
    assert positions == sorted(positions)
    assert doc.pages[0].columns == 2 and not doc.pages[0].reading_order_uncertain


def test_header_footer_detected(synthetic_pdf, parsed):
    doc = parsed(synthetic_pdf("synthetic_header_footer.pdf"))
    marked = [b.text for b in doc.blocks if b.type == BlockType.header_footer]
    assert marked.count(EXPECTED["synthetic_header_footer.pdf"]["header"]) == 4
    assert sum(t.startswith("Page ") for t in marked) == 4
    assert all(b.type != BlockType.header_footer for b in doc.blocks if b.text.startswith("Section"))


def test_scanned_page(synthetic_pdf, parsed):
    doc = parsed(synthetic_pdf("synthetic_scanned.pdf"))
    assert doc.pages[0].page_class == PageClass.scanned
    assert doc.pages[0].image_area_ratio == pytest.approx(1.0, abs=1e-3)
    assert doc.stats.scanned_pages == 1


def test_caption_and_figure_blocks(synthetic_pdf, parsed):
    doc = parsed(synthetic_pdf("synthetic_table_equation.pdf"))
    captions = [b.text for b in doc.blocks if b.type == BlockType.caption]
    assert captions == ["Table 1. Classification results", "Figure 1. Proposed pipeline"]
    assert sum(b.type == BlockType.figure for b in doc.blocks) == 1


@pytest.mark.parametrize("name", ["synthetic_encrypted.pdf", "corrupt.pdf", "not_a_pdf.PDF"])
def test_unopenable_pdfs_raise_parse_error(synthetic_pdf, name):
    with pytest.raises(DocumentError) as info:
        parse(synthetic_pdf(name))
    assert info.value.stage == ErrorStage.parse
    assert str(synthetic_pdf(name).parent) not in info.value.message


def test_owner_password_pdf_opens(synthetic_pdf, parsed):
    assert parsed(synthetic_pdf("synthetic_encrypted_empty_pw.pdf")).title == "Encrypted Document"


def test_pdf_is_not_modified(synthetic_pdf):
    path = synthetic_pdf("synthetic_table_equation.pdf")
    before = sha256_file(path)
    parse(path)
    assert sha256_file(path) == before


def test_round_trip_through_json(synthetic_pdf, parsed):
    doc = parsed(synthetic_pdf("synthetic_two_column.pdf"))
    assert DocumentModel.model_validate_json(doc.model_dump_json()) == doc


def test_block_ids_and_order(synthetic_pdf, parsed):
    doc = parsed(synthetic_pdf("synthetic_header_footer.pdf"))
    assert [b.order for b in doc.blocks] == list(range(len(doc.blocks)))
    assert doc.blocks_on_page(2)[0].id == "p2-b1"


def test_single_page_error_is_a_warning(synthetic_pdf, monkeypatch):
    import src.pdf_parser as module
    original = module._extract_blocks

    def flaky(page, number):
        if number == 2:
            raise RuntimeError("bozuk sayfa")
        return original(page, number)

    monkeypatch.setattr(module, "_extract_blocks", flaky)
    doc = parse(synthetic_pdf("synthetic_header_footer.pdf"))
    assert doc.pages[1].parse_error and "bozuk sayfa" in doc.pages[1].parse_error
    assert "page_parse_error: page 2" in [str(w) for w in doc.warnings]
    assert doc.blocks_on_page(3)


def test_build_sections_nesting():
    from src.document_model import Block
    def heading(i, text, level):
        return Block(id=f"p1-b{i}", type=BlockType.heading, page=1, bbox=(0, 0, 1, 1), text=text, heading_level=level, order=i)
    blocks = [heading(0, "1. A", 1), heading(1, "1.1 B", 2), heading(2, "1.2 C", 2), heading(3, "2. D", 1)]
    sections = build_sections(blocks)
    assert [(s.title, s.parent_id, s.end_order) for s in sections] == [
        ("1. A", None, 2), ("1.1 B", "s1", 1), ("1.2 C", "s1", 2), ("2. D", None, 3)]


# --- Gerçek makaleler: regresyon kontrolleri (dosya yoksa atlanır) ---

def real(fixtures_dir, name):
    path = fixtures_dir / "real" / name
    if not path.is_file():
        pytest.skip(f"Gerçek makale yok: {name}")
    return path


def test_real_elsevier_title_and_subsections(fixtures_dir, parsed):
    doc = parsed(real(fixtures_dir, "2024_Pokorny_VocDoc.pdf"))
    assert doc.title.startswith("VocDoc, what happened to my voice?")
    headings = [(" ".join(b.text.split()), b.heading_level) for b in doc.headings()]
    for expected in [("1. Introduction", 2), ("1.1. State of the art", 3), ("2.1.1. VocDoc-pilotSet", 4),
                     ("3. Results", 2), ("References", 2)]:
        assert expected in headings
    assert all(p.columns == 2 for p in doc.pages[1:])


def test_real_journal_name_is_not_title(fixtures_dir, parsed):
    doc = parsed(real(fixtures_dir, "2024_Lambay_Machine.pdf"))
    assert doc.title.startswith("Machine learning assisted human fatigue detection")


def test_real_section_order_across_columns(fixtures_dir, parsed):
    doc = parsed(real(fixtures_dir, "2024_Imran_Designing.pdf"))
    numbers = [b.text.split()[0] for b in doc.headings() if b.text[:1].isdigit()]
    assert numbers.index("4.2.") < numbers.index("4.3.")


def test_real_single_column_article(fixtures_dir, parsed):
    doc = parsed(real(fixtures_dir, "2025_Berardi_Voice.pdf"))
    assert all(p.columns == 1 for p in doc.pages)
    levels = {" ".join(b.text.split()): b.heading_level for b in doc.headings()}
    assert levels["Methods"] == 2 and levels["Participants"] == 3
    assert "OPEN" not in levels


def test_real_ieee_roman_sections(fixtures_dir, parsed):
    doc = parsed(real(fixtures_dir, "2025_Vekkot_Continuous.pdf"))
    assert [b.text for b in doc.headings() if b.heading_level == 2][:3] == ["I. INTRODUCTION", "II. BACKGROUND", "III. METHODOLOGY"]
    assert ("A. EARLY STUDIES", 3) in [(b.text, b.heading_level) for b in doc.headings()]


def test_real_vector_text_pages(fixtures_dir, parsed):
    doc = parsed(real(fixtures_dir, "2025_Shilaskar_Intelligent.pdf"))
    assert [p.page_class for p in doc.pages] == [PageClass.scanned] * 6
    assert all(p.vector_text_suspected for p in doc.pages)
    assert any(b.type == BlockType.header_footer for b in doc.blocks)
