"""Desktop entry: single instance, API server thread, scheduler, tray + webview."""
from __future__ import annotations

import logging
import os
import threading
from logging.handlers import RotatingFileHandler

from sparks.config import load_settings


_WINDOW = None


def _pid_alive(pid: int) -> bool:
    """True if a process with this pid is running (Windows + POSIX)."""
    try:
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return code.value == STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(handle)
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ValueError):
        return False


def acquire_lock(data_dir) -> bool:
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / "app.lock"
    if lock_path.exists():
        # stale lock from a hard kill / crash: steal it if that pid is gone
        try:
            old_pid = int(lock_path.read_text().strip() or 0)
        except (OSError, ValueError):
            old_pid = 0
        if old_pid and _pid_alive(old_pid):
            return False  # genuinely another instance (or ourselves)
        lock_path.unlink(missing_ok=True)
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


def _ensure_sources(settings, log) -> None:
    """First run of a packaged install has an empty db and no CLI init step —
    seed the bundled default sources so the fetch cycle has work to do."""
    from sparks.db import Database
    from sparks.seed import SOURCES_SEED, ensure_seeded
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    seeded = ensure_seeded(db, SOURCES_SEED)
    if seeded:
        log.info("seeded %d default sources (first run)", seeded)


def _open_window(url: str):
    """Create the main webview window once; later calls just re-show it.

    The X button hides the window to the tray instead of quitting (standard
    Windows tray-app behavior) — webview.start() therefore never unblocks and
    the app lives until Quit in the tray. webview.start() must own the MAIN
    thread on Windows (WebView2 message loop)."""
    import webview
    global _WINDOW
    if _WINDOW is None:
        _WINDOW = webview.create_window("Supply Chain Sparks", url,
                                        width=1280, height=800)

        def hide_to_tray():
            _WINDOW.hide()
            # pywebview cancels the close only when the handler returns False
            # (verified against 6.2.1 winforms: True lets the window close).
            # Returning True here is what left a zombie process behind: the
            # window vanished, the app kept running with no tray icon, and
            # interpreter-exit waited for a mid-flight fetch/judge cycle.
            return False
        _WINDOW.events.closing += hide_to_tray
    else:
        _WINDOW.show()
    return _WINDOW


def _show_running_instance(settings) -> None:
    """Relaunch while another instance runs: ask it to show its window."""
    import httpx
    from sparks.db import Database
    try:
        token = Database(settings.db_path).get_setting("server_token")
        if token:
            httpx.post(
                f"http://{settings.server.host}:{settings.server.port}/api/show",
                headers={"X-Sparks-Token": token}, timeout=2.0)
    except Exception:
        pass  # unreachable instance — nothing more we can do here


def run() -> int:
    settings = load_settings()
    if not acquire_lock(settings.data_dir):
        _show_running_instance(settings)
        return 0  # already running
    _setup_logging(settings.data_dir)
    log = logging.getLogger(__name__)
    log.info("starting SupplyChainSparks app")
    try:
        _ensure_sources(settings, log)
        _run_app(settings)
    except Exception:
        log.exception("fatal error in app main loop")
        release_lock(settings.data_dir)
        return 1
    return 0


def _run_app(settings) -> None:
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
    threading.Thread(target=server.run, daemon=True,
                     name="uvicorn").start()

    FetchScheduler(settings, job_runner).start()

    from sparks.app.tray import build_tray
    token = app.state.db.get_setting("server_token")
    dashboard_url = (f"http://{settings.server.host}:{settings.server.port}"
                     f"/?token={token}")
    # second-instance /api/show reveals the already-created window
    app.state.show_window = lambda: _open_window(dashboard_url)

    tray = build_tray(
        on_open=lambda: _open_window(dashboard_url),
        on_fetch=lambda: job_runner.submit("fetch", run_cycle, settings),
        on_quit=lambda: _quit(server, tray, settings.data_dir),
    )

    # Tray runs in a background thread; webview owns the main thread (Windows
    # requires the WebView2 message loop on the main thread).
    threading.Thread(target=tray.run, daemon=True, name="tray").start()
    _open_window(dashboard_url)   # main window at startup
    import webview
    webview.start()   # blocks for the app's lifetime: the X button only hides
                       # the window; the process exits via tray Quit (os._exit)
    # Reaching here means the window closed for real (OS shutdown / a close
    # the closing-handler could not cancel). Exit immediately instead of
    # falling into interpreter shutdown, which would join the JobRunner
    # threads and hang on a mid-flight fetch/judge cycle for minutes.
    _quit(server, tray, settings.data_dir)


if __name__ == "__main__":
    raise SystemExit(run())
