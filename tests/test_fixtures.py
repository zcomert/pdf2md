import fitz
import pytest

from tests.fixtures.generate_fixtures import EXPECTED, NONDETERMINISTIC, generate
from tests.helpers import input_snapshot, sha256_file
from tests.reference_schema import load_reference, reference_files

DETERMINISTIC = sorted(set(EXPECTED) - NONDETERMINISTIC)


@pytest.fixture(scope="module")
def generated_twice(tmp_path_factory):
    first = tmp_path_factory.mktemp("gen1")
    second = tmp_path_factory.mktemp("gen2")
    generate(first)
    generate(second)
    return first, second


def test_all_expected_fixtures_exist(fixtures_dir):
    missing = [name for name in EXPECTED if not (fixtures_dir / name).is_file()]
    assert not missing, f"Eksik fixture: {missing}. Üretmek için: python -m tests.fixtures.generate_fixtures"


def test_generator_is_deterministic(generated_twice):
    first, second = generated_twice
    for name in DETERMINISTIC:
        assert sha256_file(first / name) == sha256_file(second / name), name


def test_committed_fixtures_match_generator(generated_twice, fixtures_dir):
    first, _ = generated_twice
    stale = [name for name in DETERMINISTIC if sha256_file(first / name) != sha256_file(fixtures_dir / name)]
    assert not stale, f"Fixture'lar üreticiyle uyuşmuyor, yeniden üretin: {stale}"


def test_generator_keeps_existing_encrypted_files(tmp_path):
    generate(tmp_path)
    before = {name: sha256_file(tmp_path / name) for name in NONDETERMINISTIC}
    generate(tmp_path)
    assert before == {name: sha256_file(tmp_path / name) for name in NONDETERMINISTIC}


@pytest.mark.parametrize("name", [n for n, e in EXPECTED.items() if "pages" in e])
def test_valid_fixture_page_counts(synthetic_pdf, name):
    with fitz.open(synthetic_pdf(name)) as doc:
        assert doc.page_count == EXPECTED[name]["pages"]


def test_single_column_contains_headings_and_list(synthetic_pdf):
    expected = EXPECTED["synthetic_single_column.pdf"]
    with fitz.open(synthetic_pdf("synthetic_single_column.pdf")) as doc:
        text = doc[0].get_text()
    for heading in expected["headings"]:
        assert heading["text"] in text
    for item in expected["list_items"]:
        assert f"- {item}" in text


def test_two_column_markers_and_table(synthetic_pdf):
    expected = EXPECTED["synthetic_two_column.pdf"]
    with fitz.open(synthetic_pdf("synthetic_two_column.pdf")) as doc:
        page = doc[0]
        text = page.get_text()
        tables = [table.extract() for table in page.find_tables().tables]
    for marker in expected["reading_order_markers"]:
        assert marker in text
    assert expected["table"] in tables


def test_table_equation_fixture(synthetic_pdf):
    expected = EXPECTED["synthetic_table_equation.pdf"]
    with fitz.open(synthetic_pdf("synthetic_table_equation.pdf")) as doc:
        page = doc[0]
        text = page.get_text()
        tables = [table.extract() for table in page.find_tables().tables]
        images = page.get_images()
    assert tables == [expected["table"]]
    assert len(images) == expected["embedded_images"]
    assert expected["table_caption"] in text and expected["figure_caption"] in text
    for equation in expected["equations"]:
        assert equation["text"] in text and f"({equation['number']})" in text


def test_header_footer_repeats_on_every_page(synthetic_pdf):
    expected = EXPECTED["synthetic_header_footer.pdf"]
    with fitz.open(synthetic_pdf("synthetic_header_footer.pdf")) as doc:
        for n, page in enumerate(doc, start=1):
            text = page.get_text()
            assert expected["header"] in text
            assert expected["footer_pattern"].format(n=n) in text


def test_scanned_fixture_has_no_text_layer(synthetic_pdf):
    with fitz.open(synthetic_pdf("synthetic_scanned.pdf")) as doc:
        page = doc[0]
        assert page.get_text().strip() == ""
        assert len(page.get_images()) == 1


def test_encrypted_fixture_rejects_empty_password(synthetic_pdf):
    expected = EXPECTED["synthetic_encrypted.pdf"]
    with fitz.open(synthetic_pdf("synthetic_encrypted.pdf")) as doc:
        assert doc.needs_pass
        assert not doc.authenticate("")
        assert doc.authenticate(expected["user_password"])


def test_owner_only_encrypted_fixture_opens(synthetic_pdf):
    with fitz.open(synthetic_pdf("synthetic_encrypted_empty_pw.pdf")) as doc:
        if doc.needs_pass:
            assert doc.authenticate("")
        assert "Encrypted Document" in doc[0].get_text()


@pytest.mark.parametrize("name", ["corrupt.pdf", "not_a_pdf.PDF"])
def test_invalid_fixtures_fail_to_open(synthetic_pdf, name):
    with pytest.raises(fitz.FileDataError):
        fitz.open(synthetic_pdf(name))


def test_same_name_different_content(synthetic_pdf):
    root = synthetic_pdf("synthetic_single_column.pdf")
    nested = synthetic_pdf("subdir/synthetic_single_column.pdf")
    assert root.name == nested.name
    assert sha256_file(root) != sha256_file(nested)


def test_duplicate_copy_has_same_content(synthetic_pdf):
    assert sha256_file(synthetic_pdf("duplicate_copy.pdf")) == sha256_file(synthetic_pdf("synthetic_single_column.pdf"))


def test_tmp_input_copy_contains_only_pdfs(tmp_input_copy, fixtures_dir):
    snapshot = input_snapshot(tmp_input_copy)
    assert "subdir/synthetic_single_column.pdf" in snapshot
    assert "not_a_pdf.PDF" in snapshot
    assert all(name.lower().endswith(".pdf") for name in snapshot)
    assert snapshot["synthetic_scanned.pdf"] == sha256_file(fixtures_dir / "synthetic_scanned.pdf")


def test_tmp_output_is_outside_input(tmp_input_copy, tmp_output):
    assert not tmp_output.exists()
    assert tmp_input_copy not in tmp_output.parents


@pytest.mark.parametrize("path", reference_files(), ids=lambda p: p.name)
def test_reference_yaml_is_valid(path):
    reference = load_reference(path)
    if not reference.source_path.is_file():
        pytest.skip(f"Kaynak PDF yok: {reference.source}")
    assert sha256_file(reference.source_path) == reference.sha256


def test_real_reference_requires_minimums():
    from pydantic import ValidationError
    from tests.reference_schema import ReferenceData
    data = load_reference(reference_files()[0]).model_dump()
    data["kind"] = "real"
    with pytest.raises(ValidationError, match="en az"):
        ReferenceData.model_validate(data)


@pytest.mark.requires_tesseract
def test_requires_tesseract_marker_runs_only_when_available():
    from tests.conftest import tesseract_available
    assert tesseract_available()


@pytest.mark.requires_ollama
def test_requires_ollama_marker_runs_only_when_available():
    from tests.conftest import ollama_available
    assert ollama_available()
