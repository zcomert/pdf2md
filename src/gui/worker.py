"""Arka plan yürütme (§41.3): çekirdek ayrı iş parçacığında çalışır; olaylar kuyrukla arayüz iş parçacığına aktarılır.
Arayüz iş parçacığı hiçbir zaman çekirdeği beklemez."""
import queue
import threading
import traceback

from ..batch_processor import BatchEvents, CancelToken
from .. import runner


class QueueEvents(BatchEvents):
    """Çekirdek olaylarını `(tür, veri)` olarak kuyruğa yazar."""

    def __init__(self, sink):
        self.sink = sink

    def on_checks(self, results):
        self.sink.put(("checks", list(results)))

    def on_run_start(self, total):
        self.sink.put(("run_start", total))

    def on_document_start(self, relative_path, index, total):
        self.sink.put(("document_start", (relative_path, index, total)))

    def on_stage(self, relative_path, stage):
        self.sink.put(("stage", (relative_path, stage)))

    def on_document_warnings(self, relative_path, stage, warnings):
        self.sink.put(("document_warnings", (relative_path, stage, list(warnings))))

    def on_document_failed(self, relative_path, stage, error_type, message):
        self.sink.put(("document_failed", (relative_path, stage, error_type, message)))

    def on_document_end(self, relative_path, status, warnings, output_path, error=None):
        self.sink.put(("document_end", (relative_path, getattr(status, "value", status), output_path)))

    def on_collection_output(self, path):
        self.sink.put(("collection", str(path)))

    def on_run_end(self, summary):
        self.sink.put(("run_end", summary))


class Worker:
    """Tek çalıştırma. `run_function` testlerde değiştirilebilir (varsayılan `runner.run`)."""

    def __init__(self, options, run_function=None):
        self.options = options
        self.events = queue.Queue()
        self.token = CancelToken()
        self._run = run_function or runner.run
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._target, name="pdf2md-worker", daemon=True)
        self._thread.start()
        return self

    def _target(self):
        try:
            result = self._run(self.options, events=QueueEvents(self.events), cancel_token=self.token,
                               console=lambda text, error=False: self.events.put(("console", (text, error))))
        except Exception:  # noqa: BLE001 — arayüze iletilir, iş parçacığı sessizce ölmez
            self.events.put(("crashed", traceback.format_exc()))
        else:
            self.events.put(("finished", result))

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def pause(self):
        self.token.pause()

    def resume(self):
        self.token.resume()

    def cancel(self):
        self.token.cancel()  # duraklatılmışsa da uyanır ve güvenli noktada durur

    def drain(self, limit=500):
        """Kuyruktaki olaylar (arayüz iş parçacığında `after` ile çağrılır)."""
        items = []
        for _ in range(limit):
            try:
                items.append(self.events.get_nowait())
            except queue.Empty:
                break
        return items

    def join(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)
