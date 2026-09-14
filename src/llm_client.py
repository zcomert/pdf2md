"""Metin modeli istemcisi (§17, §18): şemalı JSON üretimi, Pydantic doğrulaması ve doğrulama hatasını modele
ileterek yeniden deneme. Ollama'ya doğrudan değil `ModelBackend` arayüzü üzerinden erişir."""
import json
import math
from dataclasses import dataclass

from pydantic import ValidationError

from .atomic_io import atomic_write_json
from .model_clients import ModelNotFound, ModelTimeout

CHARS_PER_TOKEN = 3.5


def estimate_tokens(text):
    """Kaba token tahmini (bağlam sığma kontrolü için, Faz 09)."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


@dataclass
class StructuredOutcome:
    result: object | None  # doğrulanmış Pydantic nesnesi
    error: str | None = None
    calls: int = 0
    raw_content: str | None = None


class TextClient:
    def __init__(self, backend, model, num_ctx, max_output_tokens, logger, log_content=False):
        self.backend = backend
        self.model = model
        self.num_ctx = num_ctx
        self.max_output_tokens = max_output_tokens
        self.logger = logger
        self.log_content = log_content
        self.calls = 0  # çalıştırma boyunca metin LLM çağrısı sayısı (RunSummary.text_llm_calls)

    def generate_structured(self, system, user, schema_model, task, max_retries, errors_dir=None, prepare=None,
                            max_output_tokens=None):
        """`schema_model` ile doğrulanmış sonuç üretir. `prepare(dict) -> dict` doğrulamadan önce deterministik
        düzeltme uygular (ör. alan adı eşleme). `ModelUnavailable` yayılır; zaman aşımı ve model yokluğu
        `StructuredOutcome.error` ile döner."""
        num_predict = min(max_output_tokens, self.max_output_tokens) if max_output_tokens else self.max_output_tokens
        feedback = ""
        content = None
        calls = 0
        for attempt in range(1, max_retries + 2):
            try:
                response = self.backend.chat(self.model, user + feedback, schema=schema_model.model_json_schema(),
                                             options={"temperature": 0, "num_ctx": self.num_ctx,
                                                      "num_predict": num_predict},
                                             system=system)
            except (ModelTimeout, ModelNotFound) as exc:
                self.logger.warning("Metin modeli çağrısı başarısız: model=%s görev=%s deneme=%d — %s",
                                    self.model, task, attempt, exc)
                return StructuredOutcome(None, error=str(exc), calls=calls)
            calls += 1
            self.calls += 1
            content = response.content
            duration = f"{response.duration_sec:.1f} sn" if response.duration_sec is not None else "-"
            try:
                data = json.loads(content)
                if prepare is not None and isinstance(data, dict):
                    data = prepare(data)
                parsed = schema_model.model_validate(data)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                message = short_error(exc)
                self.logger.info("Metin modeli çağrısı: model=%s görev=%s süre=%s deneme=%d hata=geçersiz yanıt: %s",
                                 self.model, task, duration, attempt, message)
                if errors_dir is not None:
                    atomic_write_json(errors_dir / f"{task}_{attempt}.json",
                                      {"task": task, "error": message, "content": content})
                feedback = (f"\n\nYour previous answer was invalid: {message}. Return only JSON that follows the "
                            "schema exactly.")
                continue
            self.logger.info("Metin modeli çağrısı: model=%s görev=%s süre=%s deneme=%d girdi≈%s token", self.model,
                             task, duration, attempt, response.prompt_tokens or estimate_tokens(system + user))
            if self.log_content:
                self.logger.debug("Metin modeli yanıtı (%s): %s", task, content)
            return StructuredOutcome(parsed, calls=calls, raw_content=content)
        return StructuredOutcome(None, error=f"{max_retries + 1} denemede geçerli yanıt alınamadı", calls=calls,
                                 raw_content=content)


def short_error(exc):
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'root'}: {e['msg']}" for e in exc.errors()[:3])
    return str(exc)[:200]
