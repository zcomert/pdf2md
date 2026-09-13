"""Testlerde gerçek Ollama yerine kullanılan sahte model arka ucu."""
import json

from src.model_clients import ModelInfo, ModelResponse, ModelTimeout, ModelUnavailable

TEXT_MODEL = "gemma4:latest"
VISION_MODEL = "minicpm-v4.5:8b"
FAKE_PAGE_TEXT = "Görsel modelden okunan sayfa metni."
FAKE_LATEX = "z = \\frac{x - \\mu}{s}"


def default_response(schema):
    title = (schema or {}).get("title", "")
    if title == "TableResult":
        return {"header": ["Model", "Accuracy"], "rows": [["Bi-LSTM", "0.99"]], "caption": None}
    if title == "EquationResult":
        return {"latex": FAKE_LATEX, "number": None}
    if title == "FigureResult":
        return {"figure_type": "chart", "caption": None}
    if title == "PageTextResult":
        return {"blocks": [{"type": "heading", "text": "Taranmış Başlık", "heading_level": 1},
                           {"type": "paragraph", "text": FAKE_PAGE_TEXT, "heading_level": None}]}
    if title == "PageLayoutResult":
        return {"columns": 2}
    return {}


class FakeBackend:
    """`responses`: şema başlığı → yanıt (dict, str veya istisna) listesi; liste bitince varsayılan yanıt."""

    def __init__(self, models=(TEXT_MODEL, VISION_MODEL), unavailable=False):
        self.models = list(models)
        self.unavailable = unavailable
        self.responses = {}
        self.calls = []

    def list_models(self):
        if self.unavailable:
            raise ModelUnavailable("sahte: Ollama kapalı")
        return {name: ModelInfo(name, f"{abs(hash(name)):064d}"[-64:], 5 * 2 ** 30) for name in self.models}

    def chat(self, model, prompt, images=None, schema=None, options=None):
        title = (schema or {}).get("title", "")
        self.calls.append({"model": model, "task": title, "images": len(images or []), "prompt": prompt})
        if self.unavailable:
            raise ModelUnavailable("sahte: Ollama kapalı")
        queue = self.responses.get(title)
        answer = queue.pop(0) if queue else default_response(schema)
        if isinstance(answer, Exception):
            raise answer
        content = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        return ModelResponse(content=content, prompt_tokens=100, output_tokens=20, duration_sec=0.01)

    def calls_for(self, title):
        return [call for call in self.calls if call["task"] == title]


__all__ = ["FakeBackend", "ModelTimeout", "ModelUnavailable", "FAKE_PAGE_TEXT", "FAKE_LATEX"]
