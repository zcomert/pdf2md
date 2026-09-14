"""Ana pencere (§41.1): giriş/çıktı, kapsam, prompt, mod, seçenekler, Başlat/Duraklat/İptal ve paneller."""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..paths import default_output_dir, normalize
from . import strings_tr as T
from .form import FormState, ProgressTracker, default_output_hint, list_pdfs, to_options, validate
from .settings_store import SettingsStore, remember_prompt
from .widgets import ChecksPanel, ConsolePanel, IssuesPanel, ProgressPanel, ResultsPanel, open_path
from .worker import Worker

POLL_MS = 100
ERROR_COLOR = "#b00020"


class MainWindow(tk.Tk):
    def __init__(self, settings=None, run_function=None, ask=None):
        super().__init__()
        self.title(T.APP_TITLE)
        self.geometry("1000x840")
        self.minsize(820, 640)
        self.settings = settings or SettingsStore()
        self.run_function = run_function
        # Onay diyalogları testlerde değiştirilebilir: ask(kind, title, message) -> bool
        self.ask = ask or self._ask
        self.worker = None
        self.tracker = ProgressTracker()
        self.closing = False
        self.last_result = None
        self._stage = None
        self._available = []
        form, self.recent_prompts = self.settings.load()
        self._configure_style()
        self._build(form)
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._set_running(False)

    # --- Kurulum ---------------------------------------------------------------------------------------------------

    def _configure_style(self):
        style = ttk.Style(self)
        default = ("Segoe UI", 10)
        self.option_add("*Font", default)
        style.configure(".", font=default)
        style.configure("Error.TLabel", foreground=ERROR_COLOR)
        style.configure("Hint.TLabel", foreground="#666666")
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    def _build(self, form):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        settings = ttk.LabelFrame(root, text="Ayarlar", padding=8)
        settings.grid(row=0, column=0, sticky="ew")
        settings.columnconfigure(1, weight=1)
        self.errors = {}

        # Giriş
        ttk.Label(settings, text="Giriş:", underline=0).grid(row=0, column=0, sticky="w")
        self.input_var = tk.StringVar(value=form.input_path)
        self.input_entry = self._entry(settings, self.input_var, row=0)
        browse = ttk.Frame(settings)
        browse.grid(row=0, column=2, sticky="w", padx=(6, 0))
        ttk.Button(browse, text="Klasör seç…", command=self.choose_input_folder).pack(side="left")
        ttk.Button(browse, text="Tek PDF seç…", command=self.choose_input_file).pack(side="left", padx=(4, 0))
        self.errors["input"] = self._error_label(settings, row=1)

        # Çıktı
        ttk.Label(settings, text="Çıktı:", underline=0).grid(row=2, column=0, sticky="w")
        self.output_var = tk.StringVar(value=form.output_path)
        self.output_entry = self._entry(settings, self.output_var, row=2)
        ttk.Button(settings, text="Seç…", command=self.choose_output).grid(row=2, column=2, sticky="w", padx=(6, 0))
        self.output_hint = ttk.Label(settings, style="Hint.TLabel")
        self.output_hint.grid(row=3, column=1, sticky="w")
        self.errors["output"] = self._error_label(settings, row=4)
        self.input_var.trace_add("write", lambda *_: self._refresh_output_hint())

        # Kapsam ve grup listesi
        ttk.Label(settings, text="Kapsam:", underline=0).grid(row=5, column=0, sticky="nw", pady=(6, 0))
        scopes = ttk.Frame(settings)
        scopes.grid(row=5, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self.scope_var = tk.StringVar(value=form.scope)
        for key, label in T.SCOPES:
            ttk.Radiobutton(scopes, text=label, value=key, variable=self.scope_var,
                            command=self._on_scope_change).pack(side="left", padx=(0, 10))
        self.group_frame = ttk.Frame(settings)
        self.group_frame.grid(row=6, column=1, columnspan=2, sticky="ew")
        ttk.Label(self.group_frame, text=T.GROUP_HINT, style="Hint.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(self.group_frame, text="Listeyi yenile", command=self.refresh_group_list).grid(row=0, column=1,
                                                                                               sticky="e")
        self.group_list = tk.Listbox(self.group_frame, selectmode="extended", height=5, exportselection=False)
        group_scroll = ttk.Scrollbar(self.group_frame, orient="vertical", command=self.group_list.yview)
        self.group_list.configure(yscrollcommand=group_scroll.set)
        self.group_list.grid(row=1, column=0, columnspan=2, sticky="ew")
        group_scroll.grid(row=1, column=2, sticky="ns")
        self.group_frame.columnconfigure(0, weight=1)
        self.errors["group"] = self._error_label(settings, row=7)

        # Prompt
        ttk.Label(settings, text="İstek (prompt):", underline=0).grid(row=8, column=0, sticky="nw", pady=(6, 0))
        prompt_frame = ttk.Frame(settings)
        prompt_frame.grid(row=8, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        self.prompt_text = tk.Text(prompt_frame, height=4, wrap="word", undo=True, highlightthickness=1,
                                   highlightbackground="#bbbbbb", highlightcolor="#3a7bd5")
        self.prompt_text.pack(fill="x")
        self.prompt_text.insert("1.0", form.prompt)
        ttk.Label(prompt_frame, text=T.PROMPT_HINT, style="Hint.TLabel").pack(anchor="w")
        self.recent_var = tk.StringVar()
        self.recent_combo = ttk.Combobox(prompt_frame, textvariable=self.recent_var, values=self.recent_prompts,
                                         state="readonly")
        if self.recent_prompts:
            ttk.Label(prompt_frame, text="Son istekler:").pack(anchor="w")
            self.recent_combo.pack(fill="x")
            self.recent_combo.bind("<<ComboboxSelected>>", self._use_recent_prompt)
        self.errors["prompt"] = self._error_label(settings, row=9)

        # Mod ve seçenekler
        ttk.Label(settings, text="Mod:", underline=0).grid(row=10, column=0, sticky="nw", pady=(6, 0))
        modes = ttk.Frame(settings)
        modes.grid(row=10, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self.mode_var = tk.StringVar(value=form.mode)
        self.mode_description = ttk.Label(modes, style="Hint.TLabel")
        for key, label, _ in T.MODES:
            ttk.Radiobutton(modes, text=label, value=key, variable=self.mode_var,
                            command=self._refresh_mode_description).pack(side="left", padx=(0, 10))
        self.mode_description.pack(side="left", padx=(8, 0))
        options = ttk.Frame(settings)
        options.grid(row=11, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self.recursive_var = tk.BooleanVar(value=form.recursive)
        self.retry_var = tk.BooleanVar(value=form.retry_failed)
        self.skip_var = tk.BooleanVar(value=form.skip_completed)
        ttk.Checkbutton(options, text="Alt klasörleri tara", variable=self.recursive_var,
                        command=self._on_recursive_change).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(options, text="Başarısızları yeniden dene", variable=self.retry_var).pack(side="left",
                                                                                                padx=(0, 14))
        ttk.Checkbutton(options, text="Tamamlananları atla", variable=self.skip_var).pack(side="left")

        # Düğmeler
        buttons = ttk.Frame(root)
        buttons.grid(row=1, column=0, sticky="ew", pady=8)
        self.start_button = ttk.Button(buttons, text="Başlat", underline=0, style="Accent.TButton", command=self.start)
        self.start_button.pack(side="left")
        self.plan_button = ttk.Button(buttons, text="Planı göster", underline=0, command=self.show_plan)
        self.plan_button.pack(side="left", padx=6)
        self.pause_button = ttk.Button(buttons, text="Duraklat", underline=0, command=self.toggle_pause)
        self.pause_button.pack(side="left")
        self.cancel_button = ttk.Button(buttons, text="İptal", underline=0, command=self.cancel)
        self.cancel_button.pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="Hazır.")
        ttk.Label(buttons, textvariable=self.status_var).pack(side="right")

        # Sekmeler
        self.tabs = ttk.Notebook(root)
        self.tabs.grid(row=2, column=0, sticky="nsew")
        self.progress_panel = ProgressPanel(self.tabs, self.open_log_file, self.open_log_folder)
        self.checks_panel = ChecksPanel(self.tabs)
        self.issues_panel = IssuesPanel(self.tabs)
        self.results_panel = ResultsPanel(self.tabs)
        self.console_panel = ConsolePanel(self.tabs)
        self.tabs.add(self.progress_panel, text="İlerleme")
        self.tabs.add(self.checks_panel, text="Başlangıç kontrolleri")
        self.tabs.add(self.issues_panel, text="Hatalar ve uyarılar")
        self.tabs.add(self.results_panel, text="Sonuçlar")
        self.tabs.add(self.console_panel, text="Günlük")

        self._refresh_output_hint()
        self._refresh_mode_description()
        self._on_scope_change()

    def _entry(self, parent, variable, row):
        entry = tk.Entry(parent, textvariable=variable, highlightthickness=1, highlightbackground="#bbbbbb",
                         highlightcolor="#3a7bd5", relief="solid", borderwidth=0)
        entry.grid(row=row, column=1, sticky="ew", ipady=3)
        return entry

    def _error_label(self, parent, row):
        label = ttk.Label(parent, style="Error.TLabel")
        label.grid(row=row, column=1, columnspan=2, sticky="w")
        label.grid_remove()  # boşken yer kaplamaz
        return label

    def _bind_keys(self):
        self.bind("<Return>", self._on_enter)
        self.bind("<Escape>", lambda _e: self.cancel())
        for key, action in (("b", self.start), ("p", self.show_plan), ("d", self.toggle_pause), ("i", self.cancel),
                            ("g", lambda: self.input_entry.focus_set()),
                            ("ccedilla", lambda: self.output_entry.focus_set()),
                            ("k", lambda: self.focus_scope()), ("m", lambda: self.focus_mode())):
            self.bind(f"<Alt-{key}>", lambda _e, fn=action: fn())
        self.bind("<Alt-KeyPress>", self._on_alt_key, add="+")

    def _on_alt_key(self, event):
        if event.char and event.char.lower() == "ı":  # Türkçe klavye: Alt+İ
            self.cancel()

    def _on_enter(self, event):
        if event.widget is self.prompt_text or isinstance(event.widget, (tk.Text, ttk.Treeview)):
            return None
        self.start()
        return "break"

    def focus_scope(self):
        self.scope_var.set(self.scope_var.get())
        self.group_list.focus_set() if self.scope_var.get() == "group" else self.focus_set()

    def focus_mode(self):
        self.focus_set()

    # --- Form ------------------------------------------------------------------------------------------------------

    def form_state(self):
        selected = [self.group_list.get(index) for index in self.group_list.curselection()]
        return FormState(input_path=self.input_var.get(), output_path=self.output_var.get(), scope=self.scope_var.get(),
                         selected=selected, prompt=self.prompt_text.get("1.0", "end-1c"), mode=self.mode_var.get(),
                         recursive=self.recursive_var.get(), retry_failed=self.retry_var.get(),
                         skip_completed=self.skip_var.get())

    def choose_input_folder(self):
        path = filedialog.askdirectory(parent=self, title="Giriş klasörü")
        if path:
            self.input_var.set(str(Path(path)))
            if self.scope_var.get() == "single":
                self.scope_var.set("auto")
            self._on_scope_change()

    def choose_input_file(self):
        path = filedialog.askopenfilename(parent=self, title="PDF seç", filetypes=[("PDF", "*.pdf"), ("Tümü", "*.*")])
        if path:
            self.input_var.set(str(Path(path)))
            self.scope_var.set("single")
            self._on_scope_change()

    def choose_output(self):
        path = filedialog.askdirectory(parent=self, title="Çıktı klasörü")
        if path:
            self.output_var.set(str(Path(path)))

    def _refresh_output_hint(self):
        hint = default_output_hint(self.input_var.get())
        self.output_hint.configure(text=T.OUTPUT_HINT.format(default=hint) if hint else "")

    def _refresh_mode_description(self):
        description = next((text for key, _, text in T.MODES if key == self.mode_var.get()), "")
        self.mode_description.configure(text=description)

    def _on_scope_change(self):
        if self.scope_var.get() == "group":
            self.group_frame.grid()
            self.refresh_group_list()
        else:
            self.group_frame.grid_remove()

    def _on_recursive_change(self):
        if self.scope_var.get() == "group":
            self.refresh_group_list()

    def refresh_group_list(self):
        previous = {self.group_list.get(i) for i in self.group_list.curselection()}
        self._available = list_pdfs(self.input_var.get(), self.recursive_var.get())
        self.group_list.delete(0, "end")
        for index, path in enumerate(self._available):
            self.group_list.insert("end", path)
            if path in previous:
                self.group_list.selection_set(index)

    def _use_recent_prompt(self, _event=None):
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", self.recent_var.get())

    def show_errors(self, errors):
        widgets = {"input": self.input_entry, "output": self.output_entry, "prompt": self.prompt_text,
                   "group": self.group_list}
        for name, label in self.errors.items():
            message = errors.get(name, "")
            label.configure(text=message)
            label.grid() if message else label.grid_remove()
            widget = widgets[name]
            color = ERROR_COLOR if message else "#bbbbbb"
            widget.configure(highlightbackground=color, highlightthickness=2 if message else 1)
        for name in ("input", "output", "group", "prompt"):
            if name in errors:
                widgets[name].focus_set()
                break

    # --- Çalıştırma ------------------------------------------------------------------------------------------------

    def start(self, plan_only=False):
        if self.worker is not None and self.worker.running:
            return False
        form = self.form_state()
        errors = validate(form, self._available if form.scope == "group" else None)
        self.show_errors(errors)
        if errors:
            self.status_var.set("Eksik veya geçersiz alanlar var.")
            return False
        self.recent_prompts = remember_prompt(self.recent_prompts, form.prompt)
        self.settings.save(form, self.recent_prompts)
        self.tracker.reset()
        self._stage = None
        self.issues_panel.clear()
        self.results_panel.clear()
        self.progress_panel.update_from(self.tracker)
        self.console_panel.append(("Plan hazırlanıyor: " if plan_only else "Başlatılıyor: ") + form.input_path)
        self.worker = Worker(to_options(form, plan_only=plan_only), run_function=self.run_function).start()
        self._set_running(True)
        self.status_var.set("Plan hazırlanıyor…" if plan_only else "Başlangıç kontrolleri yapılıyor…")
        self.tabs.select(self.console_panel if plan_only else self.progress_panel)
        self.after(POLL_MS, self.poll)
        return True

    def show_plan(self):
        return self.start(plan_only=True)

    def toggle_pause(self):
        if self.worker is None or not self.worker.running:
            return
        if self.worker.token.paused:
            self.worker.resume()
            self.pause_button.configure(text="Duraklat")
            self.status_var.set("Devam ediliyor…")
        else:
            self.worker.pause()
            self.pause_button.configure(text="Devam")
            self.status_var.set("Duraklatıldı: mevcut aşama bitince bekleniyor.")

    def cancel(self, confirm=True):
        if self.worker is None or not self.worker.running:
            return
        if confirm and not self.ask("yesno", T.CANCEL_TITLE, T.CANCEL_MESSAGE):
            return
        self.worker.cancel()
        self.pause_button.configure(text="Duraklat")
        self.status_var.set("Güvenli durduruluyor: mevcut aşama bitince durulacak…")

    def poll(self):
        if self.worker is None:
            return
        finished = False
        for kind, payload in self.worker.drain():
            finished = self.handle_event(kind, payload) or finished
        if self.tracker.total:
            self.progress_panel.update_from(self.tracker, T.STAGES.get(self._stage, self._stage))
        if not finished:
            self.after(POLL_MS, self.poll)

    def handle_event(self, kind, payload):
        """Döner: çalıştırma bitti mi."""
        if kind == "checks":
            self.checks_panel.show(payload)
        elif kind == "run_start":
            self.tracker.run_start(payload)
            self.status_var.set("İşleniyor…")
        elif kind == "document_start":
            self.tracker.document_start(payload[0])
            self._stage = None
        elif kind == "stage":
            self._stage = payload[1]
        elif kind == "document_warnings":
            relative_path, stage, warnings = payload
            for warning in warnings:
                code, _, detail = warning.partition(":")
                self.issues_panel.add(relative_path, stage, "Uyarı: " + code.strip(), detail.strip() or code)
        elif kind == "document_failed":
            relative_path, stage, error_type, message = payload
            self.issues_panel.add(relative_path, stage, "Hata: " + error_type, message, error=True)
        elif kind == "document_end":
            self.tracker.document_end(payload[0], payload[1])
        elif kind == "collection":
            self.results_panel.set_collection(payload)
        elif kind == "console":
            self.console_panel.append(*payload)
        elif kind == "finished":
            self.on_finished(payload)
            return True
        elif kind == "crashed":
            self.console_panel.append(payload, True)
            self._set_running(False)
            self.status_var.set("Beklenmeyen hata.")
            if not self.closing:
                self.ask("error", T.CRASH_TITLE, payload.strip().splitlines()[-1])
            else:
                self.destroy()
            return True
        return False

    def on_finished(self, result):
        self.last_result = result
        self._set_running(False)
        self.progress_panel.update_from(self.tracker)
        if result.plan_lines:
            self.status_var.set("Plan gösterildi (PDF işlenmedi).")
        elif result.exit_code == 2:
            self.status_var.set("Başlatılamadı.")
            if result.checks:
                self.checks_panel.show(result.checks)
                self.tabs.select(self.checks_panel)
            if not self.closing:
                title = T.LOCK_TITLE if result.error and "başka bir çalıştırma" in result.error else T.PREFLIGHT_TITLE
                self.ask("error", title, T.PREFLIGHT_MESSAGE.format(error=result.error or "") if title ==
                         T.PREFLIGHT_TITLE else (result.error or "") + ("\n\n" + result.hint if result.hint else ""))
        else:
            self.results_panel.show(result)
            if result.cancelled:
                self.status_var.set("Güvenli durduruldu. Yeniden başlatınca kaldığı yerden devam edilir.")
            elif result.stopped:
                self.status_var.set(f"Durduruldu: {result.stopped}")
            else:
                summary = result.summary
                self.status_var.set(f"Bitti: {summary.completed + summary.completed_with_warnings} tamamlandı, "
                                    f"{summary.failed} başarısız, {summary.skipped} atlandı.")
            if not self.closing:
                self.tabs.select(self.issues_panel if self.issues_panel.count() and result.exit_code else
                                 self.results_panel)
        if self.closing:
            self.settings.save(self.form_state(), self.recent_prompts)
            self.destroy()

    def _set_running(self, running):
        self.start_button.configure(state="disabled" if running else "normal")
        self.plan_button.configure(state="disabled" if running else "normal")
        self.pause_button.configure(state="normal" if running else "disabled", text="Duraklat")
        self.cancel_button.configure(state="normal" if running else "disabled")

    # --- Kapatma ve dosya açma -------------------------------------------------------------------------------------

    def on_close(self):
        if self.worker is not None and self.worker.running:
            if not self.ask("yesno", T.RUNNING_CLOSE_TITLE, T.RUNNING_CLOSE_MESSAGE):
                return
            self.closing = True
            self.cancel(confirm=False)
            self.status_var.set("Güvenli durduruluyor; işlem bitince pencere kapanacak…")
            return
        self.settings.save(self.form_state(), self.recent_prompts)
        self.destroy()

    def output_dir(self):
        if self.last_result is not None and self.last_result.output_dir:
            return Path(self.last_result.output_dir)
        if self.output_var.get().strip():
            return Path(self.output_var.get().strip())
        try:
            return default_output_dir(normalize(self.input_var.get())) if self.input_var.get().strip() else None
        except (OSError, ValueError):
            return None

    def open_log_folder(self):
        folder = self.output_dir()
        if folder is not None and (folder / "logs").is_dir():
            open_path(folder / "logs")
        else:
            self.status_var.set("Log klasörü henüz yok.")

    def open_log_file(self):
        if self.last_result is not None and self.last_result.log_path:
            open_path(self.last_result.log_path)
            return
        folder = self.output_dir()
        logs = sorted((folder / "logs").glob("*.log"), key=lambda p: p.stat().st_mtime) if folder and (
            folder / "logs").is_dir() else []
        if logs:
            open_path(logs[-1])
        else:
            self.status_var.set("Log dosyası henüz yok.")

    def _ask(self, kind, title, message):
        if kind == "yesno":
            return messagebox.askyesno(title, message, parent=self)
        messagebox.showerror(title, message, parent=self)
        return True


def run_app():
    window = MainWindow()
    window.mainloop()
