import gc
import json
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.batch_processor import CancelToken
from src.gui import strings_tr as T
from src.gui.form import FormState, ProgressTracker, format_duration, group_patterns, to_options, validate
from src.gui.settings_store import SettingsStore, remember_prompt
from src.gui.widgets import solution_commands
from src.gui.worker import Worker


# --- Form doğrulama ve seçenek eşleme (§41.3) ---------------------------------------------------------------------

def test_validate_required_and_scope_rules(tmp_input_copy, tmp_path):
    assert validate(FormState()) == {"input": T.ERR_INPUT_MISSING}
    assert validate(FormState(input_path=str(tmp_path / "yok"))) == {"input": T.ERR_INPUT_NOT_FOUND}
    pdf = tmp_input_copy / "synthetic_single_column.pdf"
    assert validate(FormState(input_path=str(tmp_input_copy), scope="single"))["input"] == T.ERR_SINGLE_NOT_PDF
    assert validate(FormState(input_path=str(pdf), scope="single")) == {}
    assert validate(FormState(input_path=str(pdf), scope="collection", prompt="karşılaştır"))["input"] == T.ERR_NEEDS_FOLDER
    inside = validate(FormState(input_path=str(tmp_input_copy), output_path=str(tmp_input_copy / "out")))
    assert inside == {"output": T.ERR_OUTPUT_INSIDE}
    assert validate(FormState(input_path=str(tmp_input_copy), scope="collection")) == {"prompt": T.ERR_COLLECTION_PROMPT}
    assert validate(FormState(input_path=str(tmp_input_copy), scope="group", prompt="x"))["group"] == T.ERR_GROUP_EMPTY


def test_group_selection_ambiguity_is_reported(tmp_input_copy):
    available = ["alt/synthetic_single_column.pdf", "synthetic_single_column.pdf", "synthetic_two_column.pdf"]
    form = FormState(input_path=str(tmp_input_copy), scope="group", prompt="x", selected=["synthetic_single_column.pdf"])
    assert "alt/synthetic_single_column.pdf" in validate(form, available)["group"]
    form.selected = ["alt/synthetic_single_column.pdf", "synthetic_two_column.pdf"]
    assert validate(form, available) == {}


def test_to_options_mapping():
    base = dict(input_path="  D:/Makaleler ", output_path="", prompt="  ")
    options = to_options(FormState(**base, scope="single", skip_completed=False))
    assert (options.input_dir, options.output_dir, options.prompt, options.scope, options.force) == \
           ("D:/Makaleler", None, None, "document", True)
    group = to_options(FormState(**{**base, "prompt": "Karşılaştır"}, scope="group",
                                 selected=["a.pdf", "alt\\b.pdf"], mode="full", recursive=True))
    assert (group.scope, group.include, group.mode, group.recursive, group.prompt) == \
           ("collection", ["a.pdf", "alt/b.pdf"], "full", True, "Karşılaştır")
    assert to_options(FormState(**base), plan_only=True).plan_only and not to_options(FormState(**base)).console_logging
    assert group_patterns(["x.pdf", "x.pdf"]) == ["x.pdf"]


def test_progress_tracker_counts_and_eta():
    now = [0.0]
    tracker = ProgressTracker(clock=lambda: now[0])
    tracker.run_start(4)
    tracker.document_start("a.pdf")
    now[0] = 10
    tracker.document_end("a.pdf", "completed")
    tracker.document_start("b.pdf")
    tracker.document_end("b.pdf", SimpleNamespace(value="skipped"))
    tracker.document_start("c.pdf")
    now[0] = 14
    assert (tracker.handled, tracker.in_progress, tracker.percent) == (2, 1, 50)
    assert tracker.remaining == pytest.approx(2 * 10 - 4)  # atlanan ortalamaya girmez; aktif belgede geçen süre düşülür
    tracker.document_end("c.pdf", "failed")
    assert tracker.counts == {"completed": 1, "completed_with_warnings": 0, "failed": 1, "skipped": 1}
    assert format_duration(None) == "—" and format_duration(75) == "01:15" and format_duration(3725) == "1:02:05"


def test_solution_commands():
    assert solution_commands("Run:\n  ollama pull gemma4:latest") == "ollama pull gemma4:latest"
    assert solution_commands("Ollama'yı başlatın (Ollama uygulaması veya `ollama serve`)") == "ollama serve"
    assert solution_commands("Farklı bir --output verin") == "Farklı bir --output verin"


# --- Ayarlar (§41.3) ----------------------------------------------------------------------------------------------

def test_settings_round_trip_and_corruption(tmp_path):
    store = SettingsStore(tmp_path / "pdf2md" / "gui_settings.json")
    assert store.load() == (FormState(), [])
    form = FormState(input_path="D:/Makaleler/Yorgunluk Çalışmaları", scope="group", selected=["a.pdf"],
                     prompt="Veri setlerini karşılaştır", mode="full", recursive=True)
    assert store.save(form, ["Veri setlerini karşılaştır", "  "])
    loaded, recent = store.load()
    assert loaded.input_path == "D:/Makaleler/Yorgunluk Çalışmaları" and loaded.mode == "full"
    assert loaded.selected == [] and recent == ["Veri setlerini karşılaştır"]
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert set(raw) == {"version", "form", "recent_prompts"}  # PDF içeriği veya model çıktısı yok
    store.path.write_text("{bozuk", encoding="utf-8")
    assert store.load() == (FormState(), [])
    store.path.write_text(json.dumps({"form": {"mode": 5, "recursive": "evet", "scope": "group"}}), encoding="utf-8")
    loaded, _ = store.load()
    assert (loaded.mode, loaded.recursive, loaded.scope) == ("balanced", False, "group")
    assert remember_prompt(["a", "b"], "b") == ["b", "a"] and remember_prompt(["a"], " ") == ["a"]


# --- Arka plan iş parçacığı ---------------------------------------------------------------------------------------

def test_worker_forwards_events_and_cancel():
    seen = {}

    def fake_run(options, events, cancel_token, console):
        events.on_run_start(2)
        events.on_document_start("a.pdf", 1, 2)
        events.on_document_failed("a.pdf", "parse", "corrupt_pdf", "bozuk")
        console("Sonuç: …", False)
        seen["token"] = cancel_token
        while not cancel_token.cancelled:
            time.sleep(0.01)
        return SimpleNamespace(exit_code=130)

    worker = Worker(SimpleNamespace(), run_function=fake_run).start()
    deadline = time.monotonic() + 5
    while "token" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    assert worker.running
    worker.cancel()
    worker.join(5)
    kinds = [kind for kind, _ in worker.drain()]
    assert kinds == ["run_start", "document_start", "document_failed", "console", "finished"]
    assert isinstance(seen["token"], CancelToken) and seen["token"].cancelled


def test_worker_reports_crash():
    def broken(options, events, cancel_token, console):
        raise RuntimeError("patladı")

    worker = Worker(SimpleNamespace(), run_function=broken).start()
    worker.join(5)
    (kind, payload), = worker.drain()
    assert kind == "crashed" and "RuntimeError: patladı" in payload


# --- Pencere ile kabul senaryoları (§41.4) ------------------------------------------------------------------------

@pytest.fixture
def window_factory(tmp_path):
    tk = pytest.importorskip("tkinter")
    from src.gui.app import MainWindow
    windows, asked = [], []

    def create():
        # Önceki pencerenin worker'ı bitmeli; Tk nesneleri ana iş parçacığında toplanır.
        for previous in windows:
            if previous.worker is not None:
                previous.worker.join(30)
        gc.collect()
        # pytest'in dosya tanıtıcısı düzeyindeki çıktı yakalaması testler arasında stdout/stderr tanıtıcılarını
        # değiştirirken Tcl başlatması ara sıra kendi dosyalarını okuyamıyor ("usable init.tcl"); `-s` ile hiç
        # görülmüyor, tek başına yeniden üretilemiyor. Uygulama tek pencere açtığı için etkilenmez; test yeniden dener.
        errors = []
        for _ in range(5):
            try:
                window = MainWindow(settings=SettingsStore(tmp_path / "settings.json"),
                                    ask=lambda kind, title, message: asked.append((kind, title, message)) or True)
                break
            except tk.TclError as exc:
                errors.append(str(exc).splitlines()[0])
                gc.collect()
                time.sleep(0.2)
        else:
            pytest.skip(f"Tk başlatılamadı: {errors}")
        if errors:
            print(f"Tk yeniden denendi: {errors}")
        window.withdraw()
        windows.append(window)
        return window

    create.asked = asked
    yield create
    for window in windows:
        if window.worker is not None:
            window.worker.cancel()
            window.worker.join(30)
        try:
            window.destroy()
        except Exception:  # noqa: BLE001 — pencere zaten kapatılmış olabilir
            pass
    windows.clear()
    gc.collect()


def pump(window, until, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            window.update()
        except Exception:  # noqa: BLE001 — pencere kapandı
            return True
        if until():
            return True
        time.sleep(0.02)
    raise AssertionError("GUI zaman aşımı")


def destroyed(window):
    try:
        return not window.winfo_exists()
    except Exception:  # noqa: BLE001 — Tk uygulaması yok edildi
        return True


def fill(window, input_path, output_path, prompt="", scope="auto", mode="fast"):
    window.input_var.set(str(input_path))
    window.output_var.set(str(output_path))
    window.prompt_text.delete("1.0", "end")
    window.prompt_text.insert("1.0", prompt)
    window.scope_var.set(scope)
    window._on_scope_change()
    window.mode_var.set(mode)


def test_start_progress_errors_and_results(window_factory, tmp_input_copy, tmp_output):
    """Kriter 1–3: terminal olmadan başlatma, ilerleme ve bozuk PDF hatası panelde, sonuç dosyaları açılabilir."""
    window = window_factory()
    fill(window, tmp_input_copy, tmp_output)
    assert window.start()
    pump(window, lambda: window.last_result is not None)
    result = window.last_result
    assert result.exit_code == 1 and window.tracker.total == 10 and window.tracker.counts["failed"] == 3
    assert window.progress_panel.counter_vars["failed"].get() == "3"
    issues = [window.issues_panel.tree.item(item, "values") for item in window.issues_panel.tree.get_children()]
    assert ("corrupt.pdf", "Ayrıştırma", "Hata: corrupt_pdf") == tuple(issues[0][:3]) or \
           any(row[0] == "corrupt.pdf" and row[2] == "Hata: corrupt_pdf" for row in issues)
    assert window.checks_panel.tree.get_children()  # başlangıç kontrolleri gösterildi
    rows = {window.results_panel.tree.item(item, "values")[0]: item for item in window.results_panel.tree.get_children()}
    window.results_panel.tree.selection_set(rows["synthetic_single_column.pdf"])
    window.update()
    path = window.results_panel.selected_path()
    assert path.name == "synthetic_single_column.md" and path.is_file()
    assert str(window.results_panel.open_markdown_button["state"]) == "normal"
    assert str(window.results_panel.open_csv_button["state"]) == "normal"
    assert "Sonuç: toplam 10" in window.console_panel.content()
    assert window.start_button.instate(["!disabled"])


def test_validation_errors_block_start(window_factory, tmp_input_copy, tmp_output):
    window = window_factory()
    fill(window, tmp_input_copy, tmp_output, scope="collection")
    assert not window.start()
    assert window.errors["prompt"].cget("text") == T.ERR_COLLECTION_PROMPT and window.worker is None


def test_close_during_run_then_resume(window_factory, tmp_input_copy, tmp_output, monkeypatch):
    """Kriter 4: işlem sürerken kapatma → güvenli durdurma → yeniden açınca kalanlar işlenir, tamamlananlar atlanır."""
    window = window_factory()
    fill(window, tmp_input_copy, tmp_output)
    original = window.handle_event
    closed = []

    def close_after_first_document(kind, payload):
        finished = original(kind, payload)
        if kind == "document_end":
            closed.append(payload)
            if len(closed) == 2:  # ilk belge (alfabetik) bozuk PDF; ikincisi tamamlanır
                window.on_close()  # ask → True: güvenli durdur ve kapat
        return finished

    monkeypatch.setattr(window, "handle_event", close_after_first_document)
    window.start()
    pump(window, lambda: destroyed(window))
    assert window_factory.asked[0][1] == T.RUNNING_CLOSE_TITLE
    state = json.loads((tmp_output / "processing_state.json").read_text(encoding="utf-8"))
    first_run = next(iter(state["runs"].values()))
    processed = first_run["completed"] + first_run["completed_with_warnings"] + first_run["failed"]
    assert 1 <= processed < 10 and not (tmp_output / ".lock").exists()

    second = window_factory()  # aynı ayarlar dosyasından açılır
    assert second.input_var.get() == str(tmp_input_copy)
    second.start()
    pump(second, lambda: second.last_result is not None)
    summary = second.last_result.summary
    completed_first = first_run["completed"] + first_run["completed_with_warnings"]
    assert completed_first >= 1 and summary.skipped == completed_first  # tamamlananlar atlandı
    assert summary.not_retried == first_run["failed"] - first_run["discovery_failed"]  # başarısızlar denenmedi
    assert summary.completed + summary.completed_with_warnings >= 1  # kalanlar işlendi
    handled = (summary.skipped + summary.not_retried + summary.completed + summary.completed_with_warnings
               + summary.failed - summary.discovery_failed)
    assert handled == 10 - summary.discovery_failed


def test_ollama_down_shows_solution_command(window_factory, tmp_input_copy, tmp_output, fake_model_backend):
    """Kriter 5: Ollama çalışmıyor → çözüm önerisi ve komut."""
    fake_model_backend.unavailable = True
    window = window_factory()
    fill(window, tmp_input_copy, tmp_output)
    window.start()
    pump(window, lambda: window.last_result is not None)
    assert window.last_result.exit_code == 2
    rows = [window.checks_panel.tree.item(item, "values") for item in window.checks_panel.tree.get_children()]
    assert ("Ollama", "✗") == tuple(rows[-1][:2]) or any(row[0] == "Ollama" and row[1] == "✗" for row in rows)
    assert window.checks_panel.hint.get("1.0", "end").strip().startswith("Ollama'yı başlatın")
    window.checks_panel.copy_command()
    assert window.clipboard_get() == "ollama serve"
    assert window_factory.asked[-1][1] == T.PREFLIGHT_TITLE


def test_missing_model_shows_pull_command(window_factory, tmp_input_copy, tmp_output, fake_model_backend):
    fake_model_backend.models = ["minicpm-v4.5:8b"]
    window = window_factory()
    fill(window, tmp_input_copy, tmp_output)
    window.start()
    pump(window, lambda: window.last_result is not None)
    window.checks_panel.copy_command()
    assert window.clipboard_get() == "ollama pull gemma4:latest"


def test_lock_conflict_dialog(window_factory, tmp_input_copy, tmp_output):
    from src.state_manager import OutputLock
    tmp_output.mkdir()
    with OutputLock(tmp_output, "baska-calistirma"):
        window = window_factory()
        fill(window, tmp_input_copy, tmp_output)
        window.start()
        pump(window, lambda: window.last_result is not None)
    assert window_factory.asked[-1][1] == T.LOCK_TITLE


def test_turkish_folder_name_and_pause(window_factory, tmp_path, fixtures_dir):
    """Türkçe karakterli klasör ve prompt; duraklat/devam iptal edilmeden sürer."""
    source = tmp_path / "Makaleler" / "Yorgunluk Çalışmaları İğüşöç"
    source.mkdir(parents=True)
    shutil.copy(fixtures_dir / "synthetic_single_column.pdf", source / "Çalışma_1.pdf")
    output = tmp_path / "Çıktı Ğ"
    window = window_factory()
    fill(window, source, output, scope="document")
    window.start()
    window.toggle_pause()
    assert window.worker.token.paused and window.pause_button.cget("text") == "Devam"
    window.toggle_pause()
    pump(window, lambda: window.last_result is not None)
    assert window.last_result.exit_code == 0
    markdown = output / "Çalışma_1" / "Çalışma_1.md"
    assert markdown.is_file() and window.results_panel.tree.get_children()


def test_plan_only_button(window_factory, tmp_input_copy, tmp_output):
    window = window_factory()
    fill(window, tmp_input_copy, tmp_output, prompt="Veri setlerini karşılaştır.")
    window.show_plan()
    pump(window, lambda: window.last_result is not None)
    assert "Kapsam: collection" in window.console_panel.content() and not Path(tmp_output).exists()


def test_collection_output_shown_separately(window_factory, tmp_input_copy, tmp_output, fake_model_backend):
    """§41.4 kriter 3: koleksiyon çalıştırmasında üretilen tek Markdown ayrıca ve belirgin gösterilir."""
    window = window_factory()
    fill(window, tmp_input_copy, tmp_output, prompt="Veri setlerini karşılaştır.", scope="group")
    window.refresh_group_list()
    for index, name in enumerate(window._available):
        if name in ("synthetic_single_column.pdf", "synthetic_table_equation.pdf"):
            window.group_list.selection_set(index)
    assert window.start()
    pump(window, lambda: window.last_result is not None)
    assert window.last_result.exit_code == 0 and window.last_result.collection_path
    assert window.results_panel.collection_frame.winfo_manager() == "grid"
    assert window.results_panel.collection_var.get().startswith("Koleksiyon: dataset_comparison_")
    assert str(window.results_panel.collection_button["state"]) == "normal"
    assert window.results_panel.collection_path.is_file()
