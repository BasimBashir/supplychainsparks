"""Desktop entry: single instance, API server thread, scheduler, tray + webview."""
from __future__ import annotations

import logging
import os
import threading
from logging.handlers import RotatingFileHandler

from sparks.config import load_settings


def acquire_lock(data_dir) -> bool:
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / "app.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release_lock(data_dir) -> None:
    lock_path = data_dir / "app.lock"
    if lock_path.exists():
        lock_path.unlink()


def _setup_logging(data_dir) -> None:
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / "sparks.log", maxBytes=1_000_000,
                                  backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO,
                        handlers=[handler, logging.StreamHandler()],
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _quit(server, tray, data_dir) -> None:
    server.should_exit = True
    tray.stop()
    release_lock(data_dir)
    os._exit(0)


def _open_window(url: str) -> None:
    import webview
    webview.create_window("Supply Chain Sparks", url, width=1280, height=800)
    if not getattr(webview, "_sparks_started", False):
        webview._sparks_started = True
        threading.Thread(target=webview.start, daemon=True).start()


def run() -> int:
    settings = load_settings()
    if not acquire_lock(settings.data_dir):
        return 0  # already running
    _setup_logging(settings.data_dir)
    logging.getLogger(__name__).info("starting SupplyChainSparks app")

    import uvicorn
    from sparks.pipeline import run_cycle
    from sparks.server.app import create_app
    from sparks.server.jobs import JobRunner
    from sparks.app.scheduler import FetchScheduler

    job_runner = JobRunner()
    app = create_app(settings, job_runner=job_runner)
    config = uvicorn.Config(app, host=settings.server.host, port=settings.server.port,
                            log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    FetchScheduler(settings, job_runner).start()

    from sparks.app.tray import build_tray
    token = app.state.db.get_setting("server_token")
    dashboard_url = (f"http://{settings.server.host}:{settings.server.port}"
                     f"/?token={token}")

    tray = build_tray(
        on_open=lambda: _open_window(dashboard_url),
        on_fetch=lambda: job_runner.submit("fetch", run_cycle, settings),
        on_quit=lambda: _quit(server, tray, settings.data_dir),
    )

    _open_window(dashboard_url)   # main window at startup
    tray.run()                    # blocks until quit
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
