import pytest
from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.server.app import create_app


@pytest.fixture
def client(settings, tmp_path):
    db = Database(settings.db_path)
    app = create_app(settings, db=db)
    return TestClient(app), db


def test_health_requires_token(client):
    tc, db = client
    assert tc.get("/api/health").status_code == 401
    token = db.get_setting("server_token")
    assert token  # generated on first app creation
    r = tc.get("/api/health", headers={"X-Sparks-Token": token})
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_wrong_token_rejected(client):
    tc, db = client
    assert tc.get("/api/health", headers={"X-Sparks-Token": "nope"}).status_code == 401


def test_token_stable_across_apps(settings, tmp_path):
    db1 = Database(settings.db_path)
    create_app(settings, db=db1)
    token = db1.get_setting("server_token")
    db2 = Database(settings.db_path)
    create_app(settings, db=db2)
    assert db2.get_setting("server_token") == token
