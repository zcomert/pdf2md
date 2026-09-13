import logging
import threading
from types import SimpleNamespace

import pytest

from src.batch_processor import BatchEvents, BatchProcessor, Cancelled, CancelToken, decide
from src.cache_manager import CacheManager
from src.config import AppConfig
from src.default_prompt import resolve_prompt
from src.errors import ErrorStage
from src.pdf_discovery import discover, sync_with_state
from src.schemas import DocumentState, DocumentStatus, RunSummary
from src.state_manager import StateManager

LOGGER = logging.getLogger("test-batch")
SHA = "c" * 64


def summary():
    return RunSummary(run_id="r", started_at="t", input_path="i", output_path="o")


class Recorder(BatchEvents):
    def __init__(self, cancel_after=None, token=None):
        self.calls, self.cancel_after, self.token = [], cancel_after, token

    def on_run_start(self, total):
        self.calls.append(("run_start", total))

    def on_document_start(self, relative_path, index, total):
        self.calls.append(("start", relative_path))

    def on_stage(self, relative_path, stage):
        self.calls.append(("stage", relative_path, stage))
        if self.cancel_after == (relative_path, stage):
            self.token.cancel()

    def on_document_end(self, relative_path, status, warnings, output_path, error=None):
        self.calls.append(("end", relative_path, status))

    def on_run_end(self, summary):
        self.calls.append(("run_end",))


@pytest.fixture
def workspace(tmp_input_copy, tmp_output):
    def build(include=("synthetic_single_column.pdf", "synthetic_two_column.pdf"), prompt=None, events=None,
              token=None, force=False, config=None):
        config = config or AppConfig()
        state = StateManager(tmp_output)
        state.load()
        result = discover(tmp_input_copy, include=list(include))
        run_summary = summary()
        sync_with_state(result, state, run_summary, LOGGER)
        resolved = resolve_prompt(SimpleNamespace(prompt=prompt, prompt_file=None), config)
        processor = BatchProcessor(config, state, CacheManager(tmp_output), tmp_output, "run-1", LOGGER, resolved,
                                   force=force, events=events, cancel_token=token, now=lambda: "2026-09-13T12:00:00")
        return processor, result, state, run_summary
    return build


@pytest.mark.parametrize("status, prompt_sha, output_exists, retry, force, expected", [
    (DocumentStatus.pending, None, False, False, False, "process"),
    (DocumentStatus.processing, None, False, False, False, "process"),
    (DocumentStatus.completed, "p", True, False, False, "skip"),
    (DocumentStatus.completed_with_warnings, "p", True, False, False, "skip"),
    (DocumentStatus.completed, "other", True, False, False, "process"),
    (DocumentStatus.completed, "p", False, False, False, "process"),
    (DocumentStatus.completed, "p", True, False, True, "process"),
    (DocumentStatus.failed, None, False, False, False, "not_selected"),
    (DocumentStatus.failed, None, False, True, False, "process"),
])
def test_decide(tmp_path, status, prompt_sha, output_exists, retry, force, expected):
    output = tmp_path / "a.md"
    if output_exists:
        output.write_text("içerik", encoding="utf-8")
    record = DocumentState(sha256=SHA, status=status, prompt_sha256=prompt_sha)
    assert decide(record, "p", output, retry, force) == expected


def test_empty_output_file_is_not_skipped(tmp_path):
    output = tmp_path / "a.md"
    output.write_text("", encoding="utf-8")
    record = DocumentState(sha256=SHA, status=DocumentStatus.completed, prompt_sha256="p")
    assert decide(record, "p", output, False, False) == "process"


def test_cancel_token_checkpoint_and_pause():
    token = CancelToken()
    token.checkpoint()
    token.pause()
    assert token.paused
    threading.Timer(0.3, token.resume).start()
    token.checkpoint()  # devam edilene kadar bekler
    token.cancel()
    with pytest.raises(Cancelled):
        token.checkpoint()


def test_processes_documents_and_emits_events(workspace, tmp_output):
    events = Recorder()
    processor, result, state, run_summary = workspace(events=events)
    processor.run(result, run_summary)
    assert (run_summary.completed, run_summary.parsed) == (2, 2)
    record = state.get("synthetic_single_column.pdf")
    assert record.status == DocumentStatus.completed and record.attempts == 1
    assert record.output_path == "synthetic_single_column/synthetic_single_column.md"
    assert (tmp_output / record.output_path).read_text(encoding="utf-8").startswith("---\nsource: synthetic_single_column.pdf")
    kinds = [call[0] for call in events.calls]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"
    assert ("stage", "synthetic_two_column.pdf", "parse") in events.calls


def test_cancel_during_document_reverts_to_pending_and_resume_completes(workspace):
    token = CancelToken()
    events = Recorder(cancel_after=("synthetic_single_column.pdf", "write"), token=token)
    processor, result, state, run_summary = workspace(events=events, token=token)
    with pytest.raises(Cancelled):
        processor.run(result, run_summary)
    assert state.get("synthetic_single_column.pdf").status == DocumentStatus.pending
    assert state.get("synthetic_two_column.pdf").status == DocumentStatus.pending
    assert not any(call[0] == "start" and call[1] == "synthetic_two_column.pdf" for call in events.calls)

    processor, result, state, run_summary = workspace()
    processor.run(result, run_summary)
    assert run_summary.completed == 2


def test_prompt_change_records_history(workspace):
    processor, result, state, run_summary = workspace()
    processor.run(result, run_summary)
    processor, result, state, run_summary = workspace(prompt="  ")
    processor.run(result, run_summary)
    record = state.get("synthetic_single_column.pdf")
    assert record.status == DocumentStatus.completed_with_warnings
    assert len(record.history) == 1 and record.history[0].status == DocumentStatus.completed
    assert run_summary.parsed_from_cache == 2 and run_summary.parsed == 0


def test_deleted_output_is_regenerated(workspace, tmp_output):
    processor, result, state, run_summary = workspace()
    processor.run(result, run_summary)
    (tmp_output / state.get("synthetic_two_column.pdf").output_path).unlink()
    processor, result, state, run_summary = workspace()
    processor.run(result, run_summary)
    assert (run_summary.skipped, run_summary.completed_with_warnings + run_summary.completed) == (1, 1)


def test_write_error_marks_failed_and_continues(workspace, monkeypatch):
    import src.batch_processor as module
    real_write = module.atomic_write_text

    def failing(path, text, **kwargs):
        if "two_column" in str(path):
            raise PermissionError("erişim reddedildi")
        return real_write(path, text, **kwargs)

    monkeypatch.setattr(module, "atomic_write_text", failing)
    processor, result, state, run_summary = workspace()
    processor.run(result, run_summary)
    record = state.get("synthetic_two_column.pdf")
    assert (record.status, record.error_stage) == (DocumentStatus.failed, ErrorStage.write)
    assert run_summary.failed == 1 and run_summary.completed == 1


def test_options_front_matter_and_page_markers(workspace, tmp_output):
    config = AppConfig.model_validate({"output": {"front_matter": False, "page_markers": False}})
    processor, result, state, run_summary = workspace(config=config, include=("synthetic_single_column.pdf",))
    processor.run(result, run_summary)
    markdown = (tmp_output / state.get("synthetic_single_column.pdf").output_path).read_text(encoding="utf-8")
    assert markdown.startswith("# Synthetic Study of Fatigue Detection") and "<!-- page" not in markdown
