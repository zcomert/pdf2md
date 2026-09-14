"""Arayüzden bağımsız form mantığı: doğrulama (§41.3), `RunOptions` eşlemesi ve ilerleme/kalan süre hesabı (§41.2).
tkinter içermez; birim testleriyle doğrulanır."""
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import default_output_dir, input_root, is_pdf_path, is_within, normalize
from ..pdf_discovery import discover, matches_include
from ..runner import RunOptions
from . import strings_tr as T

COLLECTION_SCOPES = {"group", "collection"}


@dataclass
class FormState:
    input_path: str = ""
    output_path: str = ""
    scope: str = "auto"  # auto | document | single | group | collection
    selected: list = field(default_factory=list)  # grup kapsamında seçilen göreli yollar
    prompt: str = ""
    mode: str = "balanced"
    recursive: bool = False
    retry_failed: bool = False
    skip_completed: bool = True


def default_output_hint(input_path):
    try:
        return str(default_output_dir(normalize(input_path))) if input_path.strip() else ""
    except (OSError, ValueError):
        return ""


def list_pdfs(input_path, recursive):
    """Grup seçimi için keşfedilen PDF'lerin göreli yolları."""
    try:
        return [pdf.relative_path for pdf in discover(normalize(input_path), recursive).documents]
    except Exception:  # noqa: BLE001 — geçersiz yol: boş liste, doğrulama ayrıca mesaj verir
        return []


def group_patterns(selected):
    """Seçili grup → `--include` desenleri. Göreli yol aynen desen olur (`*`/`?` Windows dosya adında olamaz)."""
    return list(dict.fromkeys(path.replace("\\", "/") for path in selected))


def validate(form, available=None):
    """Döner: alan → hata mesajı (boşsa geçerli). `available`: grup kapsamında keşfedilen göreli yollar."""
    errors = {}
    raw = form.input_path.strip()
    if not raw:
        errors["input"] = T.ERR_INPUT_MISSING
        return errors
    path = Path(raw)
    if not path.exists():
        errors["input"] = T.ERR_INPUT_NOT_FOUND
        return errors
    if form.scope == "single":
        if not (path.is_file() and is_pdf_path(path)):
            errors["input"] = T.ERR_SINGLE_NOT_PDF
    elif form.scope in COLLECTION_SCOPES and not path.is_dir():
        errors["input"] = T.ERR_NEEDS_FOLDER
    output = form.output_path.strip()
    if output:
        target = Path(output)
        if target.exists() and not target.is_dir():
            errors["output"] = T.ERR_OUTPUT_IS_FILE
        elif is_within(target, input_root(normalize(raw))):
            errors["output"] = T.ERR_OUTPUT_INSIDE
    if form.scope == "group":
        if not form.selected:
            errors["group"] = T.ERR_GROUP_EMPTY
        elif available is not None:
            patterns = group_patterns(form.selected)
            extra = [rel for rel in available if rel not in form.selected and matches_include(rel, patterns)]
            if extra:
                errors["group"] = T.ERR_GROUP_AMBIGUOUS.format(names=", ".join(extra[:3]))
    if form.scope in COLLECTION_SCOPES and not form.prompt.strip():
        errors["prompt"] = T.ERR_COLLECTION_PROMPT
    return errors


def to_options(form, plan_only=False):
    scope = {"single": "document", "group": "collection"}.get(form.scope, form.scope)
    return RunOptions(
        input_dir=form.input_path.strip(),
        output_dir=form.output_path.strip() or None,
        prompt=form.prompt if form.prompt.strip() else None,
        scope=scope,
        include=group_patterns(form.selected) if form.scope == "group" else None,
        mode=form.mode,
        recursive=form.recursive,
        retry_failed=form.retry_failed,
        force=not form.skip_completed,
        plan_only=plan_only,
        console_logging=False,
    )


class ProgressTracker:
    """Sayaçlar, yüzde, geçen ve tahmini kalan süre. Kalan süre işlenen (atlanmayan) belgelerin ortalamasıyla."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.reset()

    def reset(self):
        self.started = self.clock()
        self.total = 0
        self.counts = {"completed": 0, "completed_with_warnings": 0, "failed": 0, "skipped": 0}
        self.current = None
        self.stage = None
        self._doc_started = None
        self._durations = []

    def run_start(self, total):
        self.started = self.clock()
        self.total = total

    def document_start(self, relative_path):
        self.current, self.stage, self._doc_started = relative_path, None, self.clock()

    def document_end(self, relative_path, status):
        status = getattr(status, "value", status)
        if status in self.counts:
            self.counts[status] += 1
        if status != "skipped" and self._doc_started is not None and relative_path == self.current:
            self._durations.append(self.clock() - self._doc_started)
        if relative_path == self.current:
            self.current, self.stage, self._doc_started = None, None, None

    @property
    def handled(self):
        return sum(self.counts.values())

    @property
    def in_progress(self):
        return 1 if self.current else 0

    @property
    def percent(self):
        return 0 if not self.total else min(100, round(100 * self.handled / self.total))

    @property
    def elapsed(self):
        return self.clock() - self.started

    @property
    def remaining(self):
        """Saniye veya None (henüz işlenmiş belge yok)."""
        if not self._durations:
            return None
        left = max(0, self.total - self.handled)
        average = sum(self._durations) / len(self._durations)
        current_spent = self.clock() - self._doc_started if self._doc_started is not None else 0
        return max(0.0, left * average - min(current_spent, average))


def format_duration(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
