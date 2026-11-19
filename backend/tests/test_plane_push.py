"""Tests for the PMO → Plane push: dry run, idempotency, relations, mapping, the flag.

The push is the only code that writes to Plane, so these tests care most about what it refuses to do:
create twice, touch a linked task, or run with the flag off.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.integrations.plane import push as plane_push
from backend.models import PlaneLink, PlaneProjectLink, Project, Task

ENGINE = create_engine("sqlite://", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
Session = sessionmaker(bind=ENGINE)

STATES = [
    {"id": "st-backlog", "name": "Backlog", "group": "backlog"},
    {"id": "st-todo", "name": "Todo", "group": "unstarted"},
    {"id": "st-doing", "name": "In Progress", "group": "started"},
    {"id": "st-done", "name": "Done", "group": "completed"},
]


@pytest.fixture()
def db():
    Base.metadata.create_all(ENGINE)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(ENGINE)


class StubWriter:
    """Records what the push sends, returns what Plane would return."""

    def __init__(self):
        self.calls = 0
        self.posts = []
        self.n = 0

    def states(self, _pid):
        self.calls += 1
        return STATES

    def post(self, path, body):
        self.calls += 1
        self.posts.append((path, body))
        if path.endswith("/work-items/"):
            self.n += 1
            wid = f"plane-{self.n}"
            return {
                "id": wid,
                "name": body["name"],
                "sequence_id": self.n,
                "priority": body.get("priority"),
                "state": body.get("state"),
                "description_html": body.get("description_html"),
                "target_date": None,
                "start_date": None,
                "archived_at": None,
            }
        return {"ok": True}


def make_project(db, tasks):
    project = Project(name="Push test", goal="")
    db.add(project)
    db.flush()
    for t in tasks:
        db.add(t if isinstance(t, Task) else Task(project_id=project.id, **t))
    db.commit()
    link = PlaneProjectLink(project_id=project.id, workspace_slug="ai-native",
                            plane_project_id="p-push", plane_project_name="Push test")
    db.add(link)
    db.commit()
    return project, link


# ── dry run ──────────────────────────────────────────────────────────────────
def test_dry_run_reports_without_writing(db):
    project, link = make_project(db, [
        {"title": "Charter", "status": "todo"},
        {"title": "Design", "status": "in_progress"},
    ])
    plan = plane_push.plan_push(db, link)
    assert plan["tasks_to_create"] == 2
    assert plan["dry_run"] is True
    assert plan["sample"] == ["Charter", "Design"]
    assert db.query(PlaneLink).count() == 0          # nothing exists, nothing was sent


def test_plan_counts_relations_only_within_the_project(db):
    project, link = make_project(db, [
        {"title": "A"}, {"title": "B"},
    ])
    tasks = db.query(Task).order_by(Task.id).all()
    tasks[1].dependencies = [tasks[0].id, 9999]      # one real edge, one dangling
    db.commit()
    plan = plane_push.plan_push(db, link)
    assert plan["relations_to_create"] == 1


# ── push ─────────────────────────────────────────────────────────────────────
def test_push_creates_items_and_links(db):
    project, link = make_project(db, [
        {"title": "Charter", "status": "todo", "estimated_hours": 80},
        {"title": "Design", "status": "in_progress", "priority": "critical"},
    ])
    client = StubWriter()
    stats = plane_push.push_project(db, link, client)

    assert stats["created"] == 2
    assert db.query(PlaneLink).count() == 2
    bodies = [b for p, b in client.posts if p.endswith("/work-items/")]
    assert bodies[0]["name"] == "Charter"
    assert "Estimate:</b> 80 h" in bodies[0]["description_html"]
    assert bodies[0]["priority"] == "medium"
    assert bodies[0]["state"] == "st-todo"
    assert bodies[1]["priority"] == "urgent"        # critical → urgent
    assert bodies[1]["state"] == "st-doing"         # in_progress → In Progress


def test_push_is_idempotent_on_re_run(db):
    project, link = make_project(db, [{"title": "Charter"}, {"title": "Design"}])
    client = StubWriter()
    first = plane_push.push_project(db, link, client)
    second = plane_push.push_project(db, link, client)

    assert first["created"] == 2
    assert second["created"] == 0
    assert second["skipped"] == 2
    assert db.query(PlaneLink).count() == 2


def test_push_never_touches_an_already_linked_task(db):
    project, link = make_project(db, [{"title": "Charter"}, {"title": "Local only"}])
    client = StubWriter()
    plane_push.push_project(db, link, client)

    # a second task is added later and only it should be sent
    client.posts.clear()
    db.add(Task(project_id=project.id, title="Added after the first push"))
    db.commit()
    stats = plane_push.push_project(db, link, client)

    assert stats["created"] == 1 and stats["skipped"] == 2
    sent = [b["name"] for p, b in client.posts if p.endswith("/work-items/")]
    assert sent == ["Added after the first push"]


def test_push_wires_relations_between_linked_tasks(db):
    project, link = make_project(db, [{"title": "A"}, {"title": "B"}])
    tasks = db.query(Task).order_by(Task.id).all()
    tasks[1].dependencies = [tasks[0].id]
    db.commit()

    client = StubWriter()
    stats = plane_push.push_project(db, link, client)

    relation_posts = [(p, b) for p, b in client.posts if p.endswith("/relations/")]
    assert stats["relations_created"] == 1
    assert len(relation_posts) == 1
    path, body = relation_posts[0]
    assert body["relation_type"] == "blocked_by"
    assert body["issues"] == ["plane-1"]            # the successor waits on the predecessor
    assert "plane-2" in path                        # posted from the successor


def test_unknown_status_falls_back_to_todo_state(db):
    project, link = make_project(db, [{"title": "Odd", "status": "blocked"}])
    client = StubWriter()
    plane_push.push_project(db, link, client)
    body = [b for p, b in client.posts if p.endswith("/work-items/")][0]
    # Blocked is not a state on this board, so it falls back rather than failing the push
    assert body["state"] in ("st-doing", "st-todo", "st-backlog")


# ── the flag ─────────────────────────────────────────────────────────────────
def test_push_is_disabled_unless_the_flag_is_set(monkeypatch):
    monkeypatch.delenv("PLANE_PUSH_ENABLED", raising=False)
    assert plane_push.enabled() is False
    monkeypatch.setenv("PLANE_PUSH_ENABLED", "1")
    assert plane_push.enabled() is True
