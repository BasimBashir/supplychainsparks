from sparks.app.scheduler import FetchScheduler


class FakeBgScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, fn, **kwargs):
        self.jobs.append((fn, kwargs))

    def shutdown(self):
        pass


def test_start_registers_interval_job_and_runs_now(settings):
    settings.fetch.schedule_hours = 6
    called = []
    runner = type("R", (), {"submit": lambda self, name, fn, *a: called.append(name)})()
    sched = FetchScheduler(settings, runner, background=FakeBgScheduler())
    sched.start()
    assert called == ["fetch"]  # immediate first run
    fn, kwargs = sched.scheduler.jobs[0]
    assert kwargs["hours"] == 6


def test_zero_hours_disables(settings):
    settings.fetch.schedule_hours = 0
    called = []
    runner = type("R", (), {"submit": lambda self, name, fn, *a: called.append(name)})()
    sched = FetchScheduler(settings, runner, background=FakeBgScheduler())
    sched.start()
    assert sched.scheduler.jobs == [] and called == []
