"""Tests for the inbound Plane webhook: signature, dedupe, routing, failure handling."""
import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.integrations.plane import webhook as plane_webhook
from backend.main import app
from backend.models import PlaneLink, PlaneProjectLink, PlaneWebhookEvent, Project, Task

SECRET = "test-webhook-secret"
ENGINE = create_engine("sqlite://", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
Session = sessionmaker(bind=ENGINE)


@pytest.fixture()
def db():
    Base.metadata.create_all(ENGINE)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(ENGINE)


@pytest.fixture()
def client(db, monkeypatch):
    monkeypatch.setenv("PLANE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("PLANE_WORKSPACE", "ai-native")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def sign(payload: dict, scheme="dumps") -> tuple[bytes, str]:
    if scheme == "compact":
        body = json.dumps(payload, separators=(",", ":")).encode()
    else:
        body = json.dumps(payload).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, sig


def post(client, payload, scheme="dumps", signature=None, delivery=None):
    body, sig = sign(payload, scheme)
    headers = {
        "Content-Type": "application/json",
        "X-Plane-Event": str(payload.get("event", "")),
        "X-Plane-Delivery": delivery or str(uuid.uuid4()),
        "X-Plane-Signature": signature if signature is not None else sig,
    }
    return client.post("/api/integrations/plane/webhook", content=body, headers=headers)


# ── signature ────────────────────────────────────────────────────────────────
def test_signature_accepted_for_both_serialisations(db):
    payload = {"event": "issue", "action": "updated", "data": {"id": "w1"}}
    raw, sig = sign(payload, "dumps")
    # with default separators the raw body and json.dumps() are byte-identical, so either name wins
    assert plane_webhook.verify(raw, sig, SECRET) in ("raw", "dumps")
    raw, sig = sign(payload, "compact")
    assert plane_webhook.verify(raw, sig, SECRET) in ("raw", "compact")


def test_signature_rejects_a_wrong_secret(db):
    payload = {"event": "issue", "action": "updated", "data": {"id": "w1"}}
    raw, sig = sign(payload)
    assert plane_webhook.verify(raw, sig, "the-wrong-secret") is None


def test_missing_signature_is_rejected(db, client):
    payload = {"event": "issue", "action": "updated", "data": {"id": "w1"}}
    resp = post(client, payload, signature="")
    assert resp.status_code == 401
    assert db.query(PlaneWebhookEvent).count() == 0


def test_no_secret_configured_fails_closed(db, client, monkeypatch):
    monkeypatch.setenv("PLANE_WEBHOOK_SECRET", "")
    monkeypatch.setenv("PLANE_WEBHOOK_SECRET_FILE", "/nonexistent")
    resp = post(client, {"event": "issue", "action": "updated", "data": {"id": "w1"}})
    assert resp.status_code == 503


# ── delivery handling ────────────────────────────────────────────────────────
def test_valid_delivery_is_recorded(db, client):
    payload = {"event": "module", "action": "updated", "data": {"id": "m1"}}
    resp = post(client, payload, delivery="d-1")
    assert resp.status_code == 200
    rows = db.query(PlaneWebhookEvent).all()
    assert len(rows) == 1
    assert rows[0].delivery_id == "d-1"
    assert rows[0].status == "ignored"        # modules are recorded, not acted on
    assert rows[0].signature_scheme


def test_same_delivery_id_is_processed_once(db, client):
    payload = {"event": "module", "action": "updated", "data": {"id": "m1"}}
    first = post(client, payload, delivery="d-dup")
    second = post(client, payload, delivery="d-dup")
    assert first.status_code == 200 and first.json()["status"] == "ignored"
    assert second.json()["status"] == "duplicate"
    assert db.query(PlaneWebhookEvent).count() == 1


def test_deletion_does_not_delete_the_local_task(db, client):
    project = Project(name="EPC", goal="")
    db.add(project)
    db.flush()
    task = Task(project_id=project.id, title="Charter")
    db.add(task)
    db.flush()
    db.add(PlaneLink(project_id=project.id, task_id=task.id, plane_work_item_id="w-del"))
    db.commit()

    resp = post(client, {"event": "issue", "action": "deleted", "data": {"id": "w-del"}})
    assert resp.status_code == 200
    assert resp.json()["handled"] is False
    assert db.query(Task).filter(Task.id == task.id).count() == 1


def test_work_item_update_pulls_just_that_item(db, client, monkeypatch):
    project = Project(name="EPC", goal="")
    db.add(project)
    db.flush()
    task = Task(project_id=project.id, title="Charter")
    db.add(task)
    db.flush()
    db.add(PlaneLink(project_id=project.id, task_id=task.id, plane_work_item_id="w-1"))
    db.add(PlaneProjectLink(project_id=project.id, workspace_slug="ai-native",
                            plane_project_id="p-1", plane_project_name="EPC"))
    db.commit()

    called = {}

    def fake_pull_work_item(_db, link, _client, work_item_id):
        called["work_item_id"] = work_item_id
        called["project"] = link.project_id
        return {"work_item_id": work_item_id, "outcome": "updated", "api_calls": 3}

    monkeypatch.setattr(plane_webhook.sync, "pull_work_item", fake_pull_work_item)
    monkeypatch.setattr(plane_webhook.sync, "make_client", lambda: None)

    resp = post(client, {"event": "issue", "action": "updated", "data": {"id": "w-1"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["handled"] is True and body["mode"] == "single_item"
    assert called["work_item_id"] == "w-1"
    assert db.query(PlaneWebhookEvent).first().status == "ok"


def test_unknown_work_item_in_a_linked_project_triggers_a_project_pull(db, client, monkeypatch):
    project = Project(name="EPC", goal="")
    db.add(project)
    db.flush()
    db.add(PlaneProjectLink(project_id=project.id, workspace_slug="ai-native",
                            plane_project_id="p-9", plane_project_name="EPC"))
    db.commit()

    monkeypatch.setattr(plane_webhook.sync, "make_client", lambda: None)
    monkeypatch.setattr(plane_webhook.sync, "pull",
                        lambda _db, _link, _client: {"created": 1, "updated": 0, "items_seen": 1})

    resp = post(client, {"event": "issue", "action": "created",
                         "data": {"id": "brand-new", "project": "p-9"}})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "project_pull"


def test_processing_failure_is_recorded_not_raised(db, client, monkeypatch):
    project = Project(name="EPC", goal="")
    db.add(project)
    db.flush()
    task = Task(project_id=project.id, title="Charter")
    db.add(task)
    db.flush()
    db.add(PlaneLink(project_id=project.id, task_id=task.id, plane_work_item_id="w-err"))
    db.add(PlaneProjectLink(project_id=project.id, workspace_slug="ai-native",
                            plane_project_id="p-err", plane_project_name="EPC"))
    db.commit()

    def boom(*_a, **_k):
        raise RuntimeError("Plane is unreachable")

    monkeypatch.setattr(plane_webhook.sync, "make_client", boom)

    resp = post(client, {"event": "issue", "action": "updated", "data": {"id": "w-err"}})
    # 200 so Plane does not disable the webhook; the failure is visible in the event log
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"
    row = db.query(PlaneWebhookEvent).first()
    assert row.status == "error"
    assert "Plane is unreachable" in row.detail["error"]


# ── payload generations ──────────────────────────────────────────────────────
def test_normalise_handles_v1_and_v2():
    v1 = plane_webhook.normalise({"event": "issue", "action": "updated", "data": {"id": "x"}})
    assert v1[0] == "issue" and v1[1] == "updated"

    v2 = plane_webhook.normalise({"event": "workitem.updated", "data": {"id": "y"}})
    assert v2[0] == "workitem" and v2[1] == "updated"
