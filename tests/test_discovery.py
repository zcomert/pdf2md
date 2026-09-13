import logging
import os
import shutil

import pytest

from src.errors import ErrorStage, PreflightError
from src.pdf_discovery import compute_sha256, discover, matches_include, resolve_identity, sync_with_state
from src.schemas import DocumentStatus, RunSummary
from src.state_manager import StateManager

LOGGER = logging.getLogger("test")


@pytest.fixture
def papers(tmp_path):
    root = tmp_path / "papers"
    (root / "fatigue" / "deep").mkdir(parents=True)
    for rel in ["b.pdf", "A.PDF", "notes.txt", "fatigue/c.pdf", "fatigue/deep/d.pdf"]:
        (root / rel).write_bytes(f"%PDF-1.7 {rel}".encode())
    return root


def rels(result):
    return [doc.relative_path for doc in result.documents]


def summary():
    return RunSummary(run_id="20260913-120000", started_at="2026-09-13T12:00:00", input_path="in", output_path="out")


def test_non_recursive_discovery_is_sorted_and_case_insensitive(papers):
    result = discover(papers)
    assert rels(result) == ["A.PDF", "b.pdf"]
    assert result.input_root == papers.resolve()


def test_recursive_discovery(papers):
    assert rels(discover(papers, recursive=True)) == ["A.PDF", "b.pdf", "fatigue/c.pdf", "fatigue/deep/d.pdf"]


def test_include_filter_and_excluded_list(papers):
    result = discover(papers, recursive=True, include=["fatigue/*.pdf"])
    assert rels(result) == ["fatigue/c.pdf"]
    assert result.excluded_by_filter == ["A.PDF", "b.pdf", "fatigue/deep/d.pdf"]


def test_single_file_input(papers):
    result = discover(papers / "fatigue" / "c.pdf")
    assert rels(result) == ["c.pdf"]
    assert result.input_root == (papers / "fatigue").resolve()


def test_non_pdf_and_missing_input_rejected(papers):
    with pytest.raises(PreflightError):
        discover(papers / "notes.txt")
    with pytest.raises(PreflightError):
        discover(papers / "missing")


@pytest.mark.parametrize("path, patterns, expected", [
    ("fatigue/c.pdf", ["fatigue/*.pdf"], True),
    ("fatigue/deep/d.pdf", ["fatigue/*.pdf"], False),
    ("fatigue/deep/d.pdf", ["fatigue/**/*.pdf"], True),
    ("fatigue/c.pdf", ["fatigue/**/*.pdf"], True),
    ("fatigue/deep/d.pdf", ["*.pdf"], True),
    ("Fatigue/C.PDF", ["fatigue/*.pdf"], True),
    ("fatigue/c.pdf", ["fatigue\\*.pdf"], True),
    ("fatigue/c.pdf", ["./fatigue/*.pdf"], True),
    ("a.pdf", ["b*.pdf", "a?pdf"], True),
    ("a.pdf", [], True),
])
def test_matches_include(path, patterns, expected):
    assert matches_include(path, patterns) is expected


def test_identity_uses_stored_hash_when_size_and_mtime_match(papers, tmp_path):
    state = StateManager(tmp_path / "out")
    doc = discover(papers).documents[0]
    sha, rehashed = resolve_identity(doc, None)
    assert rehashed and sha == compute_sha256(doc.absolute_path)
    record = state.update(doc.relative_path, save=False, sha256=sha, size_bytes=doc.size_bytes, mtime=doc.mtime)
    assert resolve_identity(doc, record) == (sha, False)


def test_sync_registers_new_documents(papers, tmp_path):
    state = StateManager(tmp_path / "out")
    result = sync_with_state(discover(papers, recursive=True), state, summary(), LOGGER)
    assert (result.discovered, result.new, result.unchanged) == (4, 4, 0)
    assert all(record.status == DocumentStatus.pending and record.sha256 for record in state.state.documents.values())
    assert state.path.exists()


def test_mtime_only_change_does_not_reset_status(papers, tmp_path):
    state = StateManager(tmp_path / "out")
    sync_with_state(discover(papers), state, summary(), LOGGER)
    state.update("b.pdf", status=DocumentStatus.completed)
    stat = (papers / "b.pdf").stat()
    os.utime(papers / "b.pdf", (stat.st_atime, stat.st_mtime + 100))
    result = sync_with_state(discover(papers), state, summary(), LOGGER)
    record = state.get("b.pdf")
    assert (result.changed, result.unchanged) == (0, 2)
    assert record.status == DocumentStatus.completed
    assert record.mtime == discover(papers).documents[1].mtime


def test_content_change_resets_to_pending(papers, tmp_path):
    state = StateManager(tmp_path / "out")
    sync_with_state(discover(papers), state, summary(), LOGGER)
    state.update("b.pdf", status=DocumentStatus.failed, attempts=3, error_stage=ErrorStage.parse, error="x")
    (papers / "b.pdf").write_bytes(b"%PDF-1.7 changed content")
    result = sync_with_state(discover(papers), state, summary(), LOGGER)
    record = state.get("b.pdf")
    assert result.changed == 1
    assert (record.status, record.attempts, record.error) == (DocumentStatus.pending, 0, None)


def test_filtered_out_records_are_untouched(papers, tmp_path):
    state = StateManager(tmp_path / "out")
    sync_with_state(discover(papers), state, summary(), LOGGER)
    state.update("b.pdf", status=DocumentStatus.completed)
    result = sync_with_state(discover(papers, include=["A.pdf"]), state, summary(), LOGGER)
    assert result.excluded_by_filter == 1
    assert state.get("b.pdf").status == DocumentStatus.completed


def test_unreadable_file_marked_failed(papers, tmp_path, monkeypatch):
    state = StateManager(tmp_path / "out")
    import src.pdf_discovery as module

    def broken(path):
        raise PermissionError("erişim reddedildi")

    monkeypatch.setattr(module, "compute_sha256", broken)
    result = sync_with_state(discover(papers), state, summary(), LOGGER)
    assert result.discovery_failed == 2
    record = state.get("b.pdf")
    assert record.status == DocumentStatus.failed and record.error_stage == ErrorStage.discovery


def test_fixture_duplicates_share_hash(tmp_input_copy, tmp_path):
    state = StateManager(tmp_path / "out")
    sync_with_state(discover(tmp_input_copy, recursive=True), state, summary(), LOGGER)
    docs = state.state.documents
    assert docs["duplicate_copy.pdf"].sha256 == docs["synthetic_single_column.pdf"].sha256
    assert docs["subdir/synthetic_single_column.pdf"].sha256 != docs["synthetic_single_column.pdf"].sha256
