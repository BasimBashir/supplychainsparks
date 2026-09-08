"""Scheduled fetching via APScheduler (injectable background for tests)."""
from __future__ import annotations

from sparks.config import Settings
from sparks.pipeline import run_cycle


class FetchScheduler:
    def __init__(self, settings: Settings, job_runner, background=None):
        self.settings = settings
        self.job_runner = job_runner
        if background is None:
            from apscheduler.schedulers.background import BackgroundScheduler
            background = BackgroundScheduler()
        self.scheduler = background

    def start(self) -> None:
        hours = self.settings.fetch.schedule_hours
        if not hours or hours <= 0:
            return  # scheduling fully disabled: manual "Fetch Now" only
        self.job_runner.submit("fetch", run_cycle, self.settings)  # immediate first run
        self.scheduler.add_job(
            lambda: self.job_runner.submit("fetch", run_cycle, self.settings),
            "interval", hours=hours, id="fetch-cycle")
        self.scheduler.start()

    def shutdown(self) -> None:
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass
