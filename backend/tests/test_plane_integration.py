"""Tests for the Plane integration — pull semantics, mapping, idempotency, cascade.

The client is stubbed: these tests prove the PMO's behaviour, not Plane's. Talking to a real
instance is a smoke test, not a unit test.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.integrations.plane.sync import pull
from backend.models import PlaneLink, PlaneProjectLink, Project, Task

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


class StubClient:
    """Minimal stand-in for PlaneClient."""

    def __init__(self, items, states, relations=None, members=None):
        self._items = items
        self._states = states
        self._relations = relations or {}
        self._members = members or []
        self.calls = 0

    def states(self, _pid):
        self.calls += 1
        return self._states

    def work_items(self, _pid):
        self.calls += 1
        return self._items

    def relations(self, _pid, work_item_id):
        self.calls += 1
        return self._relations.get(work_item_id, {})

    def paginate(self, _path, **_kw):
        self.calls += 1
        return iter(self._members)


STATES = [
    {"id": "s-backlog", "name": "Backlog", "group": "backlog"},
    {"id": "s-doing", "name": "In Progress", "group": "started"},
    {"id": "s-done", "name": "Done", "group": "completed"},
    {"id": "s-blocked", "name": "Blocked", "group": "started"},
]


def item(wid, name, state="s-backlog", priority="medium", seq=1, target=None, hours=80):
    return {
        "id": wid, "name": name, "state": state, "priority": priority,
        "sequence_id": seq, "target_date": target, "assignees": [],
        "description_html": (
            f"<div><p>desc for {name}</p>"
            f"<p><b>Discipline:</b> PMO<br><b>Estimate:</b> {hours} h</p></div>"
        ),
    }


def make_link(db):
    project = Project(name="EPC mirror", description="", goal="")
    db.add(project)
    db.flush()
    link = PlaneProjectLink(project_id=project.id, workspace_slug="ai-native",
                            plane_project_id="plane-proj-1", plane_project_name="EPC")
    db.add(link)
    db.commit()
    return project, link


def test_pull_creates_tasks_and_links(db):
    project, link = make_link(db)
    client = StubClient(
        items=[item("w1", "Develop Project Charter", priority="urgent"),
               item("w2", "Establish Governance", state="s-doing", seq=2)],
        states=STATES,
    )
    stats = pull(db, link, client)

    assert stats["created"] == 2
    tasks = db.query(Task).filter(Task.project_id == project.id).all()
    assert len(tasks) == 2
    assert db.query(PlaneLink).count() == 2

    charter = next(t for t in tasks if t.title == "Develop Project Charter")
    assert charter.status == "todo"
    assert charter.priority == "critical"       # urgent → critical
    assert "desc for Develop Project Charter" in charter.description

    gov = next(t for t in tasks if t.title == "Establish Governance")
    assert gov.status == "in_progress"          # started group → in_progress


def test_pull_is_idempotent(db):
    _project, link = make_link(db)
    client = StubClient(items=[item("w1", "Charter"), item("w2", "Governance", seq=2)],
                        states=STATES)
    pull(db, link, client)
    first_count = db.query(Task).count()

    second = pull(db, link, client)
    assert second["created"] == 0
    assert second["unchanged"] == 2
    assert db.query(Task).count() == first_count


def test_pull_updates_changed_fields_only(db):
    _project, link = make_link(db)
    client = StubClient(items=[item("w1", "Charter")], states=STATES)
    pull(db, link, client)

    client._items = [item("w1", "Charter", state="s-done", priority="high")]
    stats = pull(db, link, client)
    assert stats["updated"] == 1
    task = db.query(Task).filter(Task.title == "Charter").one()
    assert task.status == "done"
    assert task.priority == "high"


def test_blocked_state_name_wins_over_group(db):
    _project, link = make_link(db)
    client = StubClient(items=[item("w1", "Permit filing", state="s-blocked")], states=STATES)
    pull(db, link, client)
    assert db.query(Task).filter(Task.title == "Permit filing").one().status == "blocked"


def test_relations_become_local_dependency_ids(db):
    project, link = make_link(db)
    client = StubClient(
        items=[item("w1", "Charter", seq=1), item("w2", "Governance", seq=2)],
        states=STATES,
        relations={"w2": {"blocked_by": [{"issue_id": "w1"}], "blocking": []}},
    )
    stats = pull(db, link, client, include_relations=True)

    gov = db.query(Task).filter(Task.title == "Governance").one()
    charter = db.query(Task).filter(Task.title == "Charter").one()
    assert gov.dependencies == [charter.id]
    assert stats["relations_linked"] == 1


def test_stale_links_reported_not_deleted(db):
    _project, link = make_link(db)
    client = StubClient(items=[item("w1", "Charter"), item("w2", "Governance", seq=2)],
                        states=STATES)
    pull(db, link, client)

    client._items = [item("w1", "Charter")]
    stats = pull(db, link, client)
    assert stats["stale_links"] == 1
    assert db.query(Task).count() == 2      # nothing is deleted on a pull


def test_deleting_project_cascades_links(db):
    project, link = make_link(db)
    client = StubClient(items=[item("w1", "Charter")], states=STATES,
                        relations={"w1": {"blocked_by": []}})
    pull(db, link, client, include_relations=True)
    assert db.query(PlaneLink).count() == 1

    db.delete(project)
    db.commit()
    assert db.query(PlaneLink).count() == 0
    assert db.query(PlaneProjectLink).count() == 0
    assert db.query(Task).count() == 0


def test_date_mapping(db):
    _project, link = make_link(db)
    client = StubClient(items=[item("w1", "Charter", target="2026-12-01")], states=STATES)
    pull(db, link, client)
    task = db.query(Task).filter(Task.title == "Charter").one()
    assert task.due_date is not None and task.due_date.year == 2026


def test_description_html_is_stripped_and_estimate_recovered(db):
    """Plane has no hours field; the estimate comes back out of the description text."""
    _project, link = make_link(db)
    client = StubClient(items=[item("w1", "Charter", hours=80),
                               item("w2", "Governance", seq=2, hours=0)], states=STATES)
    pull(db, link, client)

    charter = db.query(Task).filter(Task.title == "Charter").one()
    assert "<b>" not in charter.description and "<div>" not in charter.description
    assert "desc for Charter" in charter.description
    assert charter.estimated_hours == 80.0

    # an item with no estimate must come through as zero, not as a parse failure
    gov = db.query(Task).filter(Task.title == "Governance").one()
    assert gov.estimated_hours == 0.0


def test_estimate_not_confused_by_other_numbers(db):
    _project, link = make_link(db)
    raw = item("w1", "Charter")
    raw["description_html"] = "<p>Phase 2 of 5. Estimate: 120.5 h. Budget 4000.</p>"
    pull(db, link, StubClient(items=[raw], states=STATES))
    assert db.query(Task).filter(Task.title == "Charter").one().estimated_hours == 120.5


# ── boundary: Plane owns a mirrored task ─────────────────────────────────────
def _admin_actor():
    """Direct handler calls bypass dependency injection, so the role guards'
    actor arrives by hand. Admin because the guards require at least
    contributor, and the editable-task test also sends a field a contributor
    may not send."""
    from backend.models import User
    return User(username="test-user", display_name="Test User", role="admin")


def _mirrored(db):
    project, link = make_link(db)
    pull(db, link, StubClient(items=[item("w1", "Charter")], states=STATES))
    return project, db.query(Task).filter(Task.title == "Charter").one()


def test_mirrored_task_cannot_be_edited(db):
    from fastapi import HTTPException

    from backend.routers.tasks import update_task
    from backend.schemas import TaskUpdate

    project, task = _mirrored(db)
    with pytest.raises(HTTPException) as exc:
        update_task(project.id, task.id, TaskUpdate(status="done"), db=db,
                    actor=_admin_actor())
    assert exc.value.status_code == 409
    assert "owned by Plane" in exc.value.detail
    assert "next sync" in exc.value.detail

    db.refresh(task)
    assert task.status == "todo"          # the write did not happen


def test_mirrored_task_cannot_be_deleted(db):
    from fastapi import HTTPException

    from backend.routers.tasks import delete_task

    project, task = _mirrored(db)
    with pytest.raises(HTTPException) as exc:
        delete_task(project.id, task.id, db=db, actor=_admin_actor())
    assert exc.value.status_code == 409
    assert db.query(Task).filter(Task.id == task.id).count() == 1


def test_unmirrored_task_is_still_editable(db):
    from backend.routers.tasks import update_task
    from backend.schemas import TaskUpdate

    project, link = make_link(db)
    pull(db, link, StubClient(items=[item("w1", "Charter")], states=STATES))
    local = Task(project_id=project.id, title="Local task the PMO owns", status="todo")
    db.add(local)
    db.commit()

    updated = update_task(project.id, local.id, TaskUpdate(status="done", assignee="prashant"), db=db,
                          actor=_admin_actor())
    assert updated.status == "done"
    assert updated.assignee == "prashant"
