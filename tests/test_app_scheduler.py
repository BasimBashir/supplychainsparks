from sparks.app.scheduler import FetchScheduler


class FakeBgScheduler:
    def __init__(self):
        self.jobs = []
        self.started = False

    def add_job(self, fn, trigger=None, **kwargs):
        self.jobs.append((fn, trigger, kwargs))

    def start(self):
        self.started = True

    def shutdown(self):
        pass


def test_start_registers_interval_job_and_runs_now(settings):
    settings.fetch.schedule_hours = 6
    called = []
    runner = type("R", (), {"submit": lambda self, name, fn, *a: called.append(name)})()
    sched = FetchScheduler(settings, runner, background=FakeBgScheduler())
    sched.start()
    assert called == ["fetch"]  # immediate first run
    fn, trigger, kwargs = sched.scheduler.jobs[0]
    assert trigger == "interval" and kwargs["hours"] == 6 and sched.scheduler.started


def test_zero_hours_disables(settings):
    settings.fetch.schedule_hours = 0
    called = []
    runner = type("R", (), {"submit": lambda self, name, fn, *a: called.append(name)})()
    sched = FetchScheduler(settings, runner, background=FakeBgScheduler())
    sched.start()
    assert sched.scheduler.jobs == [] and called == []
