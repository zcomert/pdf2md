"""Kullanıcı ayarları (§41.3): yalnızca form seçenekleri ve son promptlar. PDF içeriği, model çıktısı veya log
saklanmaz; ağ çağrısı yoktur. Bozuk veya uyumsuz dosya varsayılanlarla açılır."""
import json
import os
from dataclasses import asdict, fields
from pathlib import Path

from ..atomic_io import atomic_write_json
from .form import FormState

SETTINGS_FILE = "gui_settings.json"
MAX_RECENT_PROMPTS = 10
_ALLOWED = {f.name for f in fields(FormState)} - {"selected"}  # grup seçimi oturuma özgü, saklanmaz


def settings_dir():
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "pdf2md"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "pdf2md"


class SettingsStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else settings_dir() / SETTINGS_FILE

    def load(self):
        """Döner: (FormState, son promptlar)."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return FormState(), []
        if not isinstance(data, dict):
            return FormState(), []
        form = FormState()
        for name in _ALLOWED:
            value = data.get("form", {}).get(name) if isinstance(data.get("form"), dict) else None
            default = getattr(form, name)
            if value is not None and isinstance(value, type(default)):
                setattr(form, name, value)
        recent = [p for p in data.get("recent_prompts", []) if isinstance(p, str) and p.strip()][:MAX_RECENT_PROMPTS]
        return form, recent

    def save(self, form, recent_prompts=()):
        data = {name: value for name, value in asdict(form).items() if name in _ALLOWED}
        recent = list(dict.fromkeys(p for p in recent_prompts if p.strip()))[:MAX_RECENT_PROMPTS]
        try:
            atomic_write_json(self.path, {"version": 1, "form": data, "recent_prompts": recent})
        except OSError:
            return False
        return True


def remember_prompt(recent, prompt):
    if not prompt.strip():
        return list(recent)
    return [prompt] + [p for p in recent if p != prompt][:MAX_RECENT_PROMPTS - 1]
