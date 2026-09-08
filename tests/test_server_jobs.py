import time

from sparks.server.jobs import JobRunner


def test_job_runs_and_reports_done():
    runner = JobRunner()
    job_id = runner.submit("double", lambda x: x * 2, 21)
    for _ in range(100):
        if runner.status(job_id)["state"] != "running":
            break
        time.sleep(0.02)
    assert runner.status(job_id) == {"name": "double", "state": "done", "result": 42}


def test_job_error_captured():
    runner = JobRunner()
    job_id = runner.submit("boom", lambda: 1 / 0)
    for _ in range(100):
        if runner.status(job_id)["state"] != "running":
            break
        time.sleep(0.02)
    status = runner.status(job_id)
    assert status["state"] == "error" and "ZeroDivisionError" in status["error"]
