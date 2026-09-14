"""Paneller: başlangıç kontrolleri, ilerleme, hata/uyarı listesi, sonuçlar, günlük (§41.2–41.3)."""
import os
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import strings_tr as T
from .form import format_duration

STATUS_ICONS = {"ok": "✓", "warning": "⚠", "error": "✗"}


def open_path(path):
    """Dosya veya klasörü işletim sisteminin varsayılan uygulamasıyla açar."""
    path = str(path)
    if os.name == "nt":
        os.startfile(path)  # noqa: S606 — kullanıcının kendi yerel dosyası
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])  # noqa: S603,S607
    else:
        subprocess.Popen(["xdg-open", path])  # noqa: S603,S607


def solution_commands(hint):
    """Çözüm önerisindeki çalıştırılabilir komutlar (ör. `ollama pull …`); yoksa önerinin tamamı."""
    if not hint:
        return ""
    commands = [line.strip() for line in hint.splitlines() if re.match(r"^\s*(ollama|pip|winget|apt|brew)\b", line)]
    commands += re.findall(r"`([^`]+)`", hint)
    return "\n".join(dict.fromkeys(commands)) or hint


def scrolled_tree(parent, columns, headings, widths, height=8):
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
    for column, heading, width in zip(columns, headings, widths):
        tree.heading(column, text=heading)
        tree.column(column, width=width, stretch=column == columns[-1])
    scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    return frame, tree


class ChecksPanel(ttk.Frame):
    """Ollama, modeller, Tesseract, GPU… ✓/⚠/✗ ve kopyalanabilir çözüm komutu (§41.4 kriter 5)."""

    def __init__(self, parent):
        super().__init__(parent, padding=6)
        frame, self.tree = scrolled_tree(self, ("check", "status", "message"), ("Kontrol", "Durum", "Mesaj"),
                                         (150, 60, 520))
        frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        ttk.Label(self, text="Çözüm önerisi:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.copy_button = ttk.Button(self, text="Komutu kopyala", command=self.copy_command, state="disabled")
        self.copy_button.grid(row=1, column=1, sticky="e", pady=(6, 0))
        self.hint = tk.Text(self, height=4, wrap="word", font=("Consolas", 10))
        self.hint.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._hints = {}
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def show(self, results):
        self.tree.delete(*self.tree.get_children())
        self._hints = {}
        first_problem = None
        for result in results:
            status = "ok" if result.ok else result.severity
            item = self.tree.insert("", "end", values=(T.CHECKS.get(result.name, result.name), STATUS_ICONS[status],
                                                       result.message), tags=(status,))
            self._hints[item] = result.hint or ""
            if first_problem is None and status == "error":
                first_problem = item
            elif first_problem is None and status == "warning" and result.hint:
                first_problem = item
        self.tree.tag_configure("error", foreground="#b00020")
        self.tree.tag_configure("warning", foreground="#8a6d00")
        if first_problem:
            self.tree.selection_set(first_problem)
            self.tree.see(first_problem)
            self._on_select()

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        hint = self._hints.get(selection[0], "") if selection else ""
        self.hint.delete("1.0", "end")
        self.hint.insert("1.0", hint)
        self.copy_button.configure(state="normal" if hint else "disabled")

    def copy_command(self):
        selection = self.tree.selection()
        command = solution_commands(self._hints.get(selection[0], "")) if selection else ""
        if command:
            self.clipboard_clear()
            self.clipboard_append(command)


class ProgressPanel(ttk.Frame):
    """Sayaçlar, aktif PDF, aşama, yüzde, geçen ve kalan süre; log açma düğmeleri (§41.2)."""

    COUNTERS = (("total", "Toplam"), ("completed", "Tamamlanan"), ("in_progress", "Devam eden"),
                ("completed_with_warnings", "Uyarılı"), ("failed", "Başarısız"), ("skipped", "Atlanan"))

    def __init__(self, parent, open_log_file, open_log_folder):
        super().__init__(parent, padding=8)
        counters = ttk.Frame(self)
        counters.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.counter_vars = {}
        for column, (key, label) in enumerate(self.COUNTERS):
            box = ttk.Frame(counters, padding=(0, 0, 18, 0))
            box.grid(row=0, column=column, sticky="w")
            ttk.Label(box, text=label).pack(anchor="w")
            var = tk.StringVar(value="0")
            ttk.Label(box, textvariable=var, font=("Segoe UI", 14, "bold")).pack(anchor="w")
            self.counter_vars[key] = var
        self.current = tk.StringVar(value="—")
        self.stage = tk.StringVar(value="—")
        self.times = tk.StringVar(value="Geçen süre: — · Tahmini kalan: —")
        ttk.Label(self, text="Aktif PDF:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Label(self, textvariable=self.current).grid(row=1, column=1, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(self, text="Aşama:").grid(row=2, column=0, sticky="w")
        ttk.Label(self, textvariable=self.stage).grid(row=2, column=1, columnspan=2, sticky="w")
        self.bar = ttk.Progressbar(self, maximum=100)
        self.bar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)
        self.percent = tk.StringVar(value="%0")
        ttk.Label(self, textvariable=self.percent, width=6).grid(row=3, column=2, sticky="w")
        ttk.Label(self, textvariable=self.times).grid(row=4, column=0, columnspan=3, sticky="w")
        buttons = ttk.Frame(self)
        buttons.grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.log_file_button = ttk.Button(buttons, text="Log dosyasını aç", command=open_log_file)
        self.log_file_button.pack(side="left")
        self.log_folder_button = ttk.Button(buttons, text="Log klasörünü aç", command=open_log_folder)
        self.log_folder_button.pack(side="left", padx=6)
        self.columnconfigure(1, weight=1)

    def update_from(self, tracker, stage_label=None):
        values = {"total": tracker.total, "in_progress": tracker.in_progress, **tracker.counts}
        for key, var in self.counter_vars.items():
            var.set(str(values.get(key, 0)))
        self.current.set(tracker.current or "—")
        self.stage.set(stage_label or "—")
        self.bar["value"] = tracker.percent
        self.percent.set(f"%{tracker.percent}")
        self.times.set(f"Geçen süre: {format_duration(tracker.elapsed)} · "
                       f"Tahmini kalan: {format_duration(tracker.remaining)}")


class IssuesPanel(ttk.Frame):
    """Hata ve uyarılar: PDF, aşama, tür, mesaj; seçilen satırın ayrıntısı (§41.2)."""

    def __init__(self, parent):
        super().__init__(parent, padding=6)
        frame, self.tree = scrolled_tree(self, ("pdf", "stage", "kind", "message"),
                                         ("PDF", "Aşama", "Tür", "Mesaj"), (220, 110, 150, 420), height=10)
        frame.grid(row=0, column=0, sticky="nsew")
        self.detail = tk.Text(self, height=5, wrap="word")
        self.detail.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.tag_configure("error", foreground="#b00020")
        self._details = {}

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.detail.delete("1.0", "end")
        self._details = {}

    def add(self, pdf, stage, kind, message, error=False):
        stage_label = T.STAGES.get(stage, stage or "—")
        item = self.tree.insert("", "end", values=(pdf, stage_label, kind, message.splitlines()[0][:200] if message else ""),
                                tags=("error",) if error else ())
        self._details[item] = f"{pdf}\nAşama: {stage_label}\nTür: {kind}\n\n{message}"
        return item

    def count(self):
        return len(self.tree.get_children())

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        self.detail.delete("1.0", "end")
        if selection:
            self.detail.insert("1.0", self._details.get(selection[0], ""))


class ResultsPanel(ttk.Frame):
    """Belge → Markdown yolu listesi, koleksiyon dosyası (ayrı ve belirgin) ve açma düğmeleri (§41.3)."""

    def __init__(self, parent):
        super().__init__(parent, padding=6)
        self.output_dir = None
        self.collection_path = None
        self.collection_var = tk.StringVar(value="")
        self.collection_frame = collection = ttk.Frame(self)
        collection.grid(row=0, column=0, sticky="ew")
        self.collection_label = ttk.Label(collection, textvariable=self.collection_var, font=("Segoe UI", 10, "bold"))
        self.collection_label.pack(side="left")
        self.collection_button = ttk.Button(collection, text="Koleksiyon Markdown'ını aç", state="disabled",
                                            command=lambda: self.collection_path and open_path(self.collection_path))
        self.collection_button.pack(side="right")
        frame, self.tree = scrolled_tree(self, ("pdf", "status", "output"), ("PDF", "Durum", "Çıktı"),
                                         (240, 110, 420), height=10)
        frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.open_markdown_button = ttk.Button(buttons, text="Markdown'ı aç", command=self.open_selected, state="disabled")
        self.open_markdown_button.pack(side="left")
        self.open_output_button = ttk.Button(buttons, text="Çıktı klasörünü aç", state="disabled",
                                             command=lambda: self.output_dir and open_path(self.output_dir))
        self.open_output_button.pack(side="left", padx=6)
        self.open_csv_button = ttk.Button(buttons, text="papers_summary.csv aç", state="disabled",
                                          command=self.open_csv)
        self.open_csv_button.pack(side="left")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        collection.grid_remove()  # yalnızca koleksiyon çalıştırmasında görünür
        self.tree.bind("<Double-1>", lambda _e: self.open_selected())
        self.tree.bind("<Return>", lambda _e: self.open_selected())
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self._paths = {}

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._paths = {}
        self.collection_path = None
        self.collection_var.set("")
        self.collection_frame.grid_remove()
        for button in (self.collection_button, self.open_markdown_button, self.open_csv_button):
            button.configure(state="disabled")

    def show(self, result):
        self.clear()
        self.output_dir = result.output_dir
        for document in result.documents:
            output = document.output_path or ""
            path = Path(result.output_dir) / output if output else None
            label = T.STATUSES.get(document.status, document.status)
            item = self.tree.insert("", "end", values=(document.relative_path, label, output or (document.error or "—")))
            if path is not None and path.is_file():
                self._paths[item] = path
        if result.collection_path:
            self.set_collection(result.collection_path, result.collection_unchanged)
        self.open_output_button.configure(state="normal" if self.output_dir else "disabled")
        csv_path = Path(self.output_dir) / "papers_summary.csv" if self.output_dir else None
        self.open_csv_button.configure(state="normal" if csv_path and csv_path.is_file() else "disabled")

    def set_collection(self, path, unchanged=False):
        self.collection_path = Path(path)
        note = " (değişmedi)" if unchanged else ""
        self.collection_var.set(f"Koleksiyon: {self.collection_path.name}{note}")
        self.collection_button.configure(state="normal")
        self.collection_frame.grid()

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        self.open_markdown_button.configure(state="normal" if selection and selection[0] in self._paths else "disabled")

    def selected_path(self):
        selection = self.tree.selection()
        return self._paths.get(selection[0]) if selection else None

    def open_selected(self):
        path = self.selected_path()
        if path is not None:
            open_path(path)

    def open_csv(self):
        if self.output_dir:
            open_path(Path(self.output_dir) / "papers_summary.csv")


class ConsolePanel(ttk.Frame):
    """Çekirdeğin kısa konsol satırları (keşif, sonuç özeti, çıktı ve log yolu)."""

    def __init__(self, parent):
        super().__init__(parent, padding=6)
        self.text = tk.Text(self, height=10, wrap="word", state="disabled", font=("Consolas", 10))
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.tag_configure("error", foreground="#b00020")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def append(self, line, error=False):
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", ("error",) if error else ())
        self.text.see("end")
        self.text.configure(state="disabled")

    def content(self):
        return self.text.get("1.0", "end").strip()
