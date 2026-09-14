import pytest

from src.errors import PreflightError
from src.paths import (default_output_dir, document_output_path, ensure_under_output, is_within,
                       resolve_output_paths, safe_filename, safe_stem)

SHA_A = "a" * 64
SHA_B = "b" * 64


@pytest.mark.parametrize("name, expected", [
    ("CON.pdf", "_CON"),
    ("con.pdf", "_con"),
    ("LPT9.pdf", "_LPT9"),
    ("COM10.pdf", "COM10"),
    ("a:b?.pdf", "a_b_"),
    ('x<y>|"z*.pdf', "x_y___z_"),
    ("tab\tname.pdf", "tab_name"),
    ("Makale Çalışması.PDF", "Makale Çalışması"),
])
def test_safe_stem(name, expected):
    assert safe_stem(name) == expected


@pytest.mark.parametrize("name, expected", [
    ("x. ", "x"),
    ("...", "_"),
    ("", "_"),
    ("NUL.backup", "_NUL.backup"),
    ("AUX .txt", "_AUX .txt"),
])
def test_safe_filename(name, expected):
    assert safe_filename(name) == expected


def test_document_output_path_keeps_subfolders():
    assert document_output_path("fatigue/article_003.pdf") == "fatigue/article_003/article_003.md"


def test_document_output_path_avoids_reserved_output_dirs():
    assert document_output_path("logs.pdf") == "logs_/logs_.md"
    assert document_output_path("_cache/a.pdf") == "_cache_/a/a.md"
    assert document_output_path("sub/logs.pdf") == "sub/logs/logs.md"


def test_collision_after_normalization_gets_sha_suffix():
    result = resolve_output_paths([("A?.pdf", SHA_A), ("A_.pdf", SHA_B)])
    assert result["A?.pdf"] == "A_/A_.md"
    assert result["A_.pdf"] == f"A_{'_' + SHA_B[:8]}/A__{SHA_B[:8]}.md"


def test_collision_is_case_insensitive():
    result = resolve_output_paths([("Paper.pdf", SHA_A), ("paper.PDF", SHA_B)])
    assert len({path.casefold() for path in result.values()}) == 2


def test_same_name_in_different_folders_does_not_collide():
    result = resolve_output_paths([("a.pdf", SHA_A), ("sub/a.pdf", SHA_B)])
    assert result == {"a.pdf": "a/a.md", "sub/a.pdf": "sub/a/a.md"}


def test_existing_output_paths_are_preserved():
    # A_.pdf daha önce işlenmiş; sonradan eklenen ve alfabetik olarak önce gelen A?.pdf onun yolunu alamaz.
    result = resolve_output_paths([("A?.pdf", SHA_A), ("A_.pdf", SHA_B)], existing={"A_.pdf": "A_/A_.md"})
    assert result["A_.pdf"] == "A_/A_.md"
    assert result["A?.pdf"] == f"A__{SHA_A[:8]}/A__{SHA_A[:8]}.md"


def test_output_paths_of_documents_outside_current_run_are_reserved():
    # b.pdf önceki çalıştırmada "a/a.md" yolunu almış (ör. "a?.pdf" olarak); bu çalıştırmada filtre dışı.
    result = resolve_output_paths([("a.pdf", SHA_A)], existing={"b.pdf": "a/a.md"})
    assert result["a.pdf"] == f"a_{SHA_A[:8]}/a_{SHA_A[:8]}.md"


def test_identical_sha_prefix_still_unique():
    result = resolve_output_paths([("A?.pdf", SHA_A), ("A_.pdf", SHA_A), ("A*.pdf", SHA_A)])
    assert len({path.casefold() for path in result.values()}) == 3


def test_default_output_dir_for_folder_and_file(tmp_path):
    papers = tmp_path / "papers"
    papers.mkdir()
    pdf = papers / "a.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    assert default_output_dir(papers) == tmp_path / "papers_output"
    assert default_output_dir(pdf) == tmp_path / "papers_output"


def test_default_output_dir_rejects_drive_root(tmp_path):
    with pytest.raises(PreflightError):
        default_output_dir(tmp_path.anchor)


def test_is_within(tmp_path):
    assert is_within(tmp_path / "a" / "b", tmp_path / "a")
    assert is_within(tmp_path / "a", tmp_path / "a")
    assert not is_within(tmp_path / "ab", tmp_path / "a")
    assert not is_within(tmp_path, tmp_path / "a")


def test_ensure_under_output_blocks_traversal(tmp_path):
    output = tmp_path / "out"
    assert ensure_under_output(output / "x" / "y.md", output) == (output / "x" / "y.md").resolve()
    with pytest.raises(ValueError):
        ensure_under_output(output / ".." / "escape.md", output)


def test_extended_length_prefix_is_removed():
    from pathlib import Path

    from src.paths import _strip_extended_prefix
    assert str(_strip_extended_prefix(Path(r"\\?\C:\Users\a\output\_cache"))) == r"C:\Users\a\output\_cache"
    assert str(_strip_extended_prefix(Path(r"\\?\UNC\server\share\x"))) == r"\\server\share\x"
    assert str(_strip_extended_prefix(Path(r"C:\normal"))) == r"C:\normal"
