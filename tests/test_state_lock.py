import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.errors import PreflightError
from src.schemas import DocumentStatus, RunSummary
from src.state_manager import LOCK_FILE, OutputLock, StateManager

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHA = "c" * 64


def test_missing_state_loads_empty(tmp_path):
    state = StateManager(tmp_path)
    assert state.load().documents == {}
    assert not state.path.exists()


def test_state_round_trip(tmp_path):
    state = StateManager(tmp_path)
    state.update("fatigue/a.pdf", sha256=SHA, size_bytes=10, mtime="2026-09-01T10:22:31",
                 status=DocumentStatus.completed_with_warnings, warnings=["ocr_unavailable: page 4"])
    state.record_run(RunSummary(run_id="r1", started_at="t", input_path="i", output_path="o"))
    loaded = StateManager(tmp_path).load()
    assert loaded.documents["fatigue/a.pdf"].warnings == ["ocr_unavailable: page 4"]
    assert "r1" in loaded.runs


def test_update_validates_fields(tmp_path):
    state = StateManager(tmp_path)
    with pytest.raises(Exception):
        state.update("a.pdf", status="bitti")
    with pytest.raises(Exception):
        state.update("a.pdf", unknown_field=1)


def test_recover_interrupted_keeps_attempts(tmp_path):
    state = StateManager(tmp_path)
    state.update("a.pdf", status=DocumentStatus.processing, attempts=2)
    state.update("b.pdf", status=DocumentStatus.completed)
    assert state.recover_interrupted() == ["a.pdf"]
    reloaded = StateManager(tmp_path).load()
    assert reloaded.documents["a.pdf"].status == DocumentStatus.pending
    assert reloaded.documents["a.pdf"].attempts == 2
    assert reloaded.documents["b.pdf"].status == DocumentStatus.completed


@pytest.mark.parametrize("content, match", [
    ("{bozuk", "okunamadı"),
    ('{"schema_version": "0.9", "documents": {}}', "sürümü uyumsuz"),
    ('{"schema_version": "1.0", "documents": {"a.pdf": {"status": "bitti"}}}', "geçersiz"),
])
def test_invalid_state_is_not_overwritten(tmp_path, content, match):
    path = tmp_path / "processing_state.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PreflightError, match=match):
        StateManager(tmp_path).load()
    assert path.read_text(encoding="utf-8") == content


def test_lock_blocks_second_holder_and_is_removed_on_release(tmp_path):
    first = OutputLock(tmp_path, "run-1").acquire()
    info = json.loads((tmp_path / LOCK_FILE).read_text(encoding="utf-8"))
    assert info["run_id"] == "run-1"
    with pytest.raises(PreflightError, match="run|kullanılıyor"):
        OutputLock(tmp_path, "run-2").acquire()
    first.release()
    assert not (tmp_path / LOCK_FILE).exists()
    with OutputLock(tmp_path, "run-3") as third:
        assert third.stale_info is None


def test_stale_lock_file_is_taken_over(tmp_path):
    (tmp_path / LOCK_FILE).write_text(json.dumps({"pid": 999999, "run_id": "old-run"}), encoding="utf-8")
    with OutputLock(tmp_path, "new-run") as lock:
        assert lock.stale_info["run_id"] == "old-run"
        assert json.loads((tmp_path / LOCK_FILE).read_text(encoding="utf-8"))["run_id"] == "new-run"


HOLD_LOCK = """
import sys
from src.state_manager import OutputLock
lock = OutputLock(sys.argv[1], "holder").acquire()
print("ready", flush=True)
sys.stdin.readline()
"""


@pytest.fixture
def lock_holder(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    process = subprocess.Popen([sys.executable, "-c", HOLD_LOCK, str(output)], cwd=PROJECT_ROOT,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert process.stdout.readline().strip() == "ready"
    yield output, process
    if process.poll() is None:
        process.stdin.close()
        process.wait(timeout=10)


def test_lock_held_by_other_process(lock_holder):
    output, _ = lock_holder
    with pytest.raises(PreflightError, match="kullanılıyor"):
        OutputLock(output, "second").acquire()


def test_lock_released_when_holder_is_killed(lock_holder):
    output, process = lock_holder
    process.kill()
    process.wait(timeout=10)
    with OutputLock(output, "after-kill") as lock:
        assert lock.stale_info["run_id"] == "holder"
