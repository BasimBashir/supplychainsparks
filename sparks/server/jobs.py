"""Tiny background job registry on a ThreadPoolExecutor."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor


class JobRunner:
    def __init__(self, workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=workers)
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def submit(self, name: str, fn, *args) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"name": name, "state": "running"}
        future = self._pool.submit(fn, *args)
        future.add_done_callback(lambda f: self._finish(job_id, f))
        return job_id

    def _finish(self, job_id: str, future) -> None:
        with self._lock:
            if future.exception():
                self._jobs[job_id] = {"name": self._jobs[job_id]["name"], "state": "error",
                                      "error": f"{type(future.exception()).__name__}: "
                                               f"{future.exception()}"}
            else:
                self._jobs[job_id] = {"name": self._jobs[job_id]["name"], "state": "done",
                                      "result": future.result()}

    def status(self, job_id: str) -> dict:
        with self._lock:
            return dict(self._jobs.get(job_id, {"name": "?", "state": "unknown"}))
