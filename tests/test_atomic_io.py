import json
import os

import pytest

from src.atomic_io import TMP_SUFFIX, atomic_write_bytes, atomic_write_json, atomic_write_text, cleanup_temp_files
from src.schemas import ProcessingState


def leftovers(folder):
    return list(folder.glob(f"*{TMP_SUFFIX}"))


def test_write_text_creates_parents_and_content(tmp_path):
    target = tmp_path / "a" / "b" / "x.md"
    atomic_write_text(target, "Türkçe ığüşöç\n")
    assert target.read_text(encoding="utf-8") == "Türkçe ığüşöç\n"
    assert leftovers(target.parent) == []


def test_write_text_with_bom(tmp_path):
    target = tmp_path / "x.csv"
    atomic_write_text(target, "a,b\r\n", bom=True)
    assert target.read_bytes() == b"\xef\xbb\xbfa,b\r\n"


def test_write_json_from_model_and_dict(tmp_path):
    atomic_write_json(tmp_path / "m.json", ProcessingState())
    atomic_write_json(tmp_path / "d.json", {"ad": "ığ"})
    assert json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))["schema_version"] == "1.0"
    assert "ığ" in (tmp_path / "d.json").read_text(encoding="utf-8")


def test_failure_during_write_keeps_old_file(tmp_path, monkeypatch):
    target = tmp_path / "x.txt"
    target.write_text("eski", encoding="utf-8")

    def broken_fsync(fd):
        raise OSError("disk hatası")

    monkeypatch.setattr(os, "fsync", broken_fsync)
    with pytest.raises(OSError, match="disk hatası"):
        atomic_write_text(target, "yeni")
    assert target.read_text(encoding="utf-8") == "eski"
    assert leftovers(tmp_path) == []


def test_failure_during_replace_keeps_old_file(tmp_path, monkeypatch):
    target = tmp_path / "x.txt"
    target.write_text("eski", encoding="utf-8")

    def broken_replace(src, dst):
        raise OSError("replace hatası")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        atomic_write_text(target, "yeni")
    assert target.read_text(encoding="utf-8") == "eski"
    assert leftovers(tmp_path) == []


def test_replace_retries_permission_error(tmp_path, monkeypatch):
    target = tmp_path / "x.txt"
    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("dosya kullanımda")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)
    atomic_write_bytes(target, b"ok")
    assert target.read_bytes() == b"ok"
    assert calls["n"] == 3


def test_cleanup_removes_only_own_temp_files(tmp_path):
    nested = tmp_path / "doc"
    nested.mkdir()
    own = nested / f".x.md.abc{TMP_SUFFIX}"
    own.write_text("yarım", encoding="utf-8")
    user_tmp = tmp_path / "notes.tmp"
    user_tmp.write_text("kullanıcı", encoding="utf-8")
    removed = cleanup_temp_files(tmp_path)
    assert removed == [own]
    assert not own.exists() and user_tmp.exists()
