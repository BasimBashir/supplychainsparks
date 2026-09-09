"""Second-instance / show-window behavior: close hides to tray, relaunch shows."""
import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.server.app import create_app


@pytest.fixture
def env(settings):
    db = Database(settings.db_path)
    db.set_setting("server_token", "tok123")
    return db, {"X-Sparks-Token": "tok123"}


def test_show_endpoint_invokes_callback(env, settings):
    db, h = env
    shown = []
    app = create_app(settings, db=db, show_window=lambda: shown.append(1))
    tc = TestClient(app)
    r = tc.post("/api/show", headers=h)
    assert r.status_code == 200 and r.json() == {"status": "shown"}
    assert shown == [1]


def test_show_endpoint_503_without_window(env, settings):
    db, h = env
    tc = TestClient(create_app(settings, db=db))
    assert tc.post("/api/show", headers=h).status_code == 503


def test_show_endpoint_requires_token(env, settings):
    db, h = env
    shown = []
    tc = TestClient(create_app(settings, db=db, show_window=shown.append))
    assert tc.post("/api/show").status_code == 401
    assert shown == []


@respx.mock
def test_second_instance_posts_show(env, settings):
    """A relaunch while the app runs asks the running instance to show."""
    from sparks.app.main import _show_running_instance
    db, h = env
    settings.server.host, settings.server.port = "127.0.0.1", 8765
    route = respx.post("http://127.0.0.1:8765/api/show").respond(200, json={})
    _show_running_instance(settings)
    assert route.called
    req = route.calls.last.request
    assert req.headers["X-Sparks-Token"] == "tok123"


@respx.mock
def test_second_instance_tolerates_unreachable_server(env, settings):
    from sparks.app.main import _show_running_instance
    db, h = env
    settings.server.host, settings.server.port = "127.0.0.1", 8765
    respx.post("http://127.0.0.1:8765/api/show").mock(side_effect=httpx.ConnectError("no"))
    _show_running_instance(settings)  # must not raise
