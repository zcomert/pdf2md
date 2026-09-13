import logging
import threading
import time
from types import SimpleNamespace

import httpx
import ollama
import pytest

from src.config import OllamaConfig
from src.errors import PreflightError
from src.model_clients import ModelNotFound, ModelTimeout, ModelUnavailable
from src.ollama_backend import ModelCallQueue, OllamaBackend, validate_endpoint

LOGGER = logging.getLogger("test-ollama")


@pytest.mark.parametrize("endpoint", ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434",
                                      "https://127.0.0.5:8443"])
def test_loopback_endpoints_accepted(endpoint):
    assert validate_endpoint(endpoint) == endpoint


@pytest.mark.parametrize("endpoint", ["http://192.168.1.10:11434", "http://ollama.example.com", "ftp://127.0.0.1",
                                      "127.0.0.1:11434"])
def test_remote_or_invalid_endpoints_rejected(endpoint):
    with pytest.raises(PreflightError):
        validate_endpoint(endpoint)


class ScriptedClient:
    """ollama.Client yerine: `script` sırasıyla istisna veya yanıt döndürür."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def list(self):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def response(content='{"ok": true}'):
    return SimpleNamespace(model_dump=lambda: {"message": {"content": content}, "prompt_eval_count": 10, "eval_count": 5})


def backend(script, retries=2):
    sleeps = []
    instance = OllamaBackend(OllamaConfig(max_retries=retries, retry_backoff_sec=1), LOGGER,
                             client=ScriptedClient(script), sleep=sleeps.append)
    return instance, sleeps


def test_chat_retries_transient_errors_with_exponential_backoff():
    instance, sleeps = backend([ConnectionError("down"), ollama.ResponseError("boom", 503), response()])
    result = instance.chat("m", "p", images=[b"png"], schema={"type": "object"})
    assert result.content == '{"ok": true}' and result.attempts == 3 and result.output_tokens == 5
    assert sleeps == [1, 2]


def test_model_not_found_is_not_retried():
    instance, sleeps = backend([ollama.ResponseError("model not found", 404)])
    with pytest.raises(ModelNotFound):
        instance.chat("yok", "p")
    assert sleeps == []


def test_exhausted_timeouts_raise_model_timeout():
    instance, _ = backend([httpx.ReadTimeout("slow")] * 3)
    with pytest.raises(ModelTimeout):
        instance.chat("m", "p")


def test_exhausted_connection_errors_raise_unavailable():
    instance, _ = backend([httpx.ConnectError("refused")] * 3)
    with pytest.raises(ModelUnavailable):
        instance.chat("m", "p")


def test_list_models_maps_digests_and_unavailable():
    listing = SimpleNamespace(models=[SimpleNamespace(model="gemma4:latest", digest="abc", size=10)])
    instance, _ = backend([listing, ConnectionError("down")])
    assert instance.list_models()["gemma4:latest"].reference == "gemma4:latest@sha256:abc"
    with pytest.raises(ModelUnavailable):
        instance.list_models()


def test_call_queue_limits_concurrency():
    queue = ModelCallQueue(workers=1)
    active, peak = [0], [0]

    def work():
        with queue:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            active[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak[0] == 1
