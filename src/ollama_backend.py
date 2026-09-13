"""Yerel Ollama arka ucu: loopback zorunluluğu (§32.1), tek model çağrı kuyruğu (§27), yeniden deneme ve hata
sınıflandırması (§28), çağrı günlüğü (§29)."""
import ipaddress
import threading
import time
from urllib.parse import urlparse

import httpx
import ollama

from .errors import PreflightError
from .model_clients import ModelInfo, ModelNotFound, ModelResponse, ModelTimeout, ModelUnavailable

LOOPBACK_HOSTS = {"localhost"}


def validate_endpoint(endpoint):
    """Ollama adresi yalnızca loopback olabilir (§32.1). PDF içeriği bilgisayardan çıkmaz."""
    parsed = urlparse(endpoint)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host:
        raise PreflightError(f"Geçersiz Ollama adresi: {endpoint}", "Örnek: http://127.0.0.1:11434")
    if host.lower() in LOOPBACK_HOSTS:
        return endpoint
    try:
        if ipaddress.ip_address(host).is_loopback:
            return endpoint
    except ValueError:
        pass
    raise PreflightError(f"Ollama adresi yerel (loopback) olmalı: {endpoint}",
                         "Uzak Ollama sunucusu desteklenmez; 127.0.0.1, localhost veya ::1 kullanın")


class ModelCallQueue:
    """Aynı anda en fazla `workers` model çağrısı (§27; varsayılan 1). Görsel ve metin modeli aynı kuyruğu kullanır."""

    def __init__(self, workers=1):
        self._semaphore = threading.BoundedSemaphore(max(1, workers))

    def __enter__(self):
        self._semaphore.acquire()
        return self

    def __exit__(self, *exc_info):
        self._semaphore.release()


class OllamaBackend:
    def __init__(self, ollama_config, logger, workers=1, client=None, sleep=time.sleep):
        self.config = ollama_config
        self.endpoint = validate_endpoint(ollama_config.endpoint)
        self.logger = logger
        self.queue = ModelCallQueue(workers)
        self._client = client or ollama.Client(host=self.endpoint, timeout=ollama_config.timeout_sec)
        self._sleep = sleep

    def list_models(self):
        """Kurulu modeller: ad → ModelInfo (digest dahil, §17.1)."""
        try:
            response = self._client.list()
        except (ConnectionError, httpx.TransportError) as exc:
            raise ModelUnavailable(f"Ollama'ya erişilemiyor ({self.endpoint}): {exc}") from exc
        return {model.model: ModelInfo(model.model, model.digest, model.size or 0) for model in response.models}

    def running_models(self):
        try:
            return [model.model for model in self._client.ps().models]
        except Exception:
            return []

    def chat(self, model, prompt, images=None, schema=None, options=None):
        """Yeniden denenebilir hatalarda (bağlantı, zaman aşımı, 5xx) `ollama.max_retries` kadar üstel beklemeyle
        tekrarlar. Model yoksa hemen `ModelNotFound`."""
        message = {"role": "user", "content": prompt}
        if images:
            message["images"] = list(images)
        attempts = self.config.max_retries + 1
        last_error = None
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                with self.queue:
                    response = self._client.chat(model=model, messages=[message], format=schema,
                                                 options=options or {}, keep_alive=self.config.keep_alive)
                data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
                return ModelResponse(content=data["message"]["content"], prompt_tokens=data.get("prompt_eval_count"),
                                     output_tokens=data.get("eval_count"), duration_sec=time.monotonic() - started,
                                     attempts=attempt, raw=data)
            except ollama.ResponseError as exc:
                if exc.status_code == 404:
                    raise ModelNotFound(f"Model bulunamadı: {model}") from exc
                if exc.status_code < 500:
                    raise ModelUnavailable(f"Ollama isteği reddetti ({exc.status_code}): {exc}") from exc
                last_error = exc
            except (ConnectionError, httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_error = ModelUnavailable(f"Ollama'ya erişilemiyor ({self.endpoint}): {exc}")
            except httpx.TimeoutException as exc:
                last_error = ModelTimeout(f"{model} yanıtı {self.config.timeout_sec} sn içinde gelmedi")
            self.logger.warning("Model çağrısı başarısız (deneme %d/%d): %s — %s", attempt, attempts, model, last_error)
            if attempt < attempts:
                self._sleep(self.config.retry_backoff_sec * 2 ** (attempt - 1))
        if isinstance(last_error, (ModelUnavailable, ModelTimeout)):
            raise last_error
        raise ModelUnavailable(f"Ollama hatası: {last_error}")
