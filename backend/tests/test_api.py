"""Agentic PMO — Test suite for API endpoints and agent fallbacks.

Run with:  pytest backend/tests/ -v --tb=short  (from /root/agentic-pmo/)
           pytest backend/tests/ -v -x         (stop on first failure)
"""
import pytest
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.auth import require_auth

# Auto-authenticate business-logic tests (TestAuth clears this for its own tests)
@pytest.fixture(scope="session", autouse=True)
def auto_auth():
    app.dependency_overrides[require_auth] = lambda: "test-user"
    yield
    app.dependency_overrides.pop(require_auth, None)


# ── In-memory test database ──────────────────────────────────────────────
TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def setup_db():
    """Create fresh tables before each test."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. HEALTH
# ══════════════════════════════════════════════════════════════════════════
class TestHealth:
    def test_health_returns_ok(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


# ══════════════════════════════════════════════════════════════════════════
# 2. PROJECT CRUD
# ══════════════════════════════════════════════════════════════════════════
class TestProjects:
    def test_create_project(self):
        resp = client.post("/api/projects", json={
            "name": "Test Project",
            "goal": "A test goal",
            "description": "A test description",
            "priority": "high",
            "tags": ["test", "demo"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Project"
        assert data["goal"] == "A test goal"
        assert data["priority"] == "high"
        assert data["tags"] == ["test", "demo"]
        assert data["status"] == "planning"
        assert data["id"] > 0

    def test_create_project_requires_name(self):
        resp = client.post("/api/projects", json={"name": ""})
        assert resp.status_code == 422  # validation error

    def test_list_projects(self):
        client.post("/api/projects", json={"name": "P1"})
        client.post("/api/projects", json={"name": "P2"})
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_list_projects_empty(self):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_project(self):
        created = client.post("/api/projects", json={"name": "Get Me"}).json()
        resp = client.get(f"/api/projects/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Me"

    def test_get_project_404(self):
        resp = client.get("/api/projects/999")
        assert resp.status_code == 404

    def test_update_project(self):
        created = client.post("/api/projects", json={"name": "Old Name"}).json()
        resp = client.patch(f"/api/projects/{created['id']}", json={
            "name": "New Name",
            "priority": "critical",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["priority"] == "critical"

    def test_update_project_404(self):
        resp = client.patch("/api/projects/999", json={"name": "Nope"})
        assert resp.status_code == 404

    def test_delete_project(self):
        created = client.post("/api/projects", json={"name": "Delete Me"}).json()
        resp = client.delete(f"/api/projects/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # Verify it's gone
        resp = client.get(f"/api/projects/{created['id']}")
        assert resp.status_code == 404

    def test_delete_project_404(self):
        resp = client.delete("/api/projects/999")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# 3. TASK CRUD
# ══════════════════════════════════════════════════════════════════════════
class TestTasks:
    def _make_project(self):
        return client.post("/api/projects", json={"name": "Task Test"}).json()

    def test_create_task(self):
        pid = self._make_project()["id"]
        resp = client.post(f"/api/projects/{pid}/tasks", json={
            "title": "Do the thing",
            "priority": "critical",
            "estimated_hours": 40,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Do the thing"
        assert data["priority"] == "critical"
        assert data["estimated_hours"] == 40.0
        assert data["status"] == "todo"
        assert data["project_id"] == pid

    def test_create_task_requires_title(self):
        pid = self._make_project()["id"]
        resp = client.post(f"/api/projects/{pid}/tasks", json={})
        assert resp.status_code == 422

    def test_list_tasks(self):
        pid = self._make_project()["id"]
        client.post(f"/api/projects/{pid}/tasks", json={"title": "T1"})
        client.post(f"/api/projects/{pid}/tasks", json={"title": "T2"})
        resp = client.get(f"/api/projects/{pid}/tasks")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_tasks_empty(self):
        pid = self._make_project()["id"]
        resp = client.get(f"/api/projects/{pid}/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_update_task_status(self):
        pid = self._make_project()["id"]
        task = client.post(f"/api/projects/{pid}/tasks", json={"title": "Move me"}).json()
        resp = client.patch(f"/api/projects/{pid}/tasks/{task['id']}", json={
            "status": "in_progress",
            "assignee": "AI Agent",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "in_progress"
        assert data["assignee"] == "AI Agent"

    def test_update_task_404(self):
        resp = client.patch("/api/projects/1/tasks/999", json={"status": "done"})
        assert resp.status_code == 404

    def test_delete_task(self):
        pid = self._make_project()["id"]
        task = client.post(f"/api/projects/{pid}/tasks", json={"title": "Delete"}).json()
        resp = client.delete(f"/api/projects/{pid}/tasks/{task['id']}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_task_404(self):
        resp = client.delete("/api/projects/1/tasks/999")
        assert resp.status_code == 404

    def test_tasks_ordered_by_sort_order(self):
        pid = self._make_project()["id"]
        t1 = client.post(f"/api/projects/{pid}/tasks", json={"title": "Z"}).json()
        t2 = client.post(f"/api/projects/{pid}/tasks", json={"title": "A"}).json()
        tasks = client.get(f"/api/projects/{pid}/tasks").json()
        assert tasks[0]["title"] == "Z"  # creation order preserved


# ══════════════════════════════════════════════════════════════════════════
# 4. PLAN AGENT FALLBACK (no LLM key — uses template)
# ══════════════════════════════════════════════════════════════════════════
class TestPlanAgentFallback:
    def test_plan_agent_creates_tasks_on_fresh_project(self):
        pid = client.post("/api/projects", json={"name": "Plan Me", "goal": "Build something"}).json()["id"]
        resp = client.post(f"/api/projects/{pid}/agents/plan", json={
            "project_id": pid,
            "additional_context": "",
        })
        assert resp.status_code == 200
        data = resp.json()
        # Even without an LLM key, the fallback plan should create at least 1 task
        assert data["status"] in ("planned", "already_planned")
        tasks = client.get(f"/api/projects/{pid}/tasks").json()
        assert len(tasks) >= 1

    def test_plan_agent_returns_already_planned(self):
        pid = client.post("/api/projects", json={"name": "Already Planned"}).json()["id"]
        # Run twice
        client.post(f"/api/projects/{pid}/agents/plan", json={"project_id": pid, "additional_context": ""})
        resp = client.post(f"/api/projects/{pid}/agents/plan", json={"project_id": pid, "additional_context": ""})
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_planned"

    def test_plan_agent_logs_action(self):
        pid = client.post("/api/projects", json={"name": "Audit Trail"}).json()["id"]
        client.post(f"/api/projects/{pid}/agents/plan", json={"project_id": pid, "additional_context": ""})
        actions = client.get(f"/api/projects/{pid}/agents/actions").json()
        assert len(actions) >= 1
        assert actions[0]["agent_type"] == "plan"

    def test_plan_agent_404(self):
        resp = client.post("/api/projects/999/agents/plan", json={"project_id": 999, "additional_context": ""})
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# 5. MONITOR AGENT
# ══════════════════════════════════════════════════════════════════════════
class TestMonitorAgent:
    def test_monitor_with_no_tasks(self):
        pid = client.post("/api/projects", json={"name": "Empty Monitor"}).json()["id"]
        resp = client.post(f"/api/projects/{pid}/agents/monitor")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_tasks"

    def test_monitor_with_tasks_generates_health_score(self):
        pid = client.post("/api/projects", json={"name": "Monitor Me"}).json()["id"]
        client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
        resp = client.post(f"/api/projects/{pid}/agents/monitor")
        assert resp.status_code == 200
        data = resp.json()
        assert "health_score" in data
        assert isinstance(data["health_score"], (int, float))

    def test_monitor_logs_actions(self):
        pid = client.post("/api/projects", json={"name": "Monitor Log"}).json()["id"]
        client.post(f"/api/projects/{pid}/tasks", json={"title": "T"})
        client.post(f"/api/projects/{pid}/agents/monitor")
        actions = client.get(f"/api/projects/{pid}/agents/actions").json()
        assert any(a["agent_type"] == "monitor" for a in actions)

    def test_monitor_404(self):
        resp = client.post("/api/projects/999/agents/monitor")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# 6. ALERT AGENT
# ══════════════════════════════════════════════════════════════════════════
class TestAlertAgent:
    def test_alert_returns_severity(self):
        pid = client.post("/api/projects", json={"name": "Alert Me"}).json()["id"]
        resp = client.post(f"/api/projects/{pid}/agents/alert")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alerted"
        assert data["severity"] in ("info", "warning", "critical")

    def test_alert_with_anomaly_description(self):
        pid = client.post("/api/projects", json={"name": "Alert Anomaly"}).json()["id"]
        resp = client.post(f"/api/projects/{pid}/agents/alert?anomaly=critical+delay+in+reactor+procurement")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alerted"

    def test_alert_logs_action(self):
        pid = client.post("/api/projects", json={"name": "Alert Log"}).json()["id"]
        client.post(f"/api/projects/{pid}/agents/alert")
        actions = client.get(f"/api/projects/{pid}/agents/actions").json()
        assert len(actions) >= 1
        assert any(a["agent_type"] == "alert" for a in actions)

    def test_alert_404(self):
        resp = client.post("/api/projects/999/agents/alert")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# 7. DASHBOARD
# ══════════════════════════════════════════════════════════════════════════
class TestDashboard:
    def test_dashboard_empty(self):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_projects"] == 0
        assert data["total_tasks"] == 0
        assert data["done_tasks"] == 0

    def test_dashboard_with_data(self):
        pid = client.post("/api/projects", json={"name": "Dash Test"}).json()["id"]
        client.post(f"/api/projects/{pid}/tasks", json={"title": "T1"})
        client.post(f"/api/projects/{pid}/tasks", json={"title": "T2"})
        resp = client.get("/api/dashboard")
        data = resp.json()
        assert data["total_projects"] == 1
        assert data["total_tasks"] == 2
        assert data["active_projects"] >= 1

    def test_dashboard_includes_recent_actions(self):
        pid = client.post("/api/projects", json={"name": "Dash Actions"}).json()["id"]
        client.post(f"/api/projects/{pid}/tasks", json={"title": "T"})
        client.post(f"/api/projects/{pid}/agents/monitor")
        resp = client.get("/api/dashboard")
        data = resp.json()
        assert len(data["recent_actions"]) >= 1


# ══════════════════════════════════════════════════════════════════════════
# 8. RESOLVE AGENT ACTION
# ══════════════════════════════════════════════════════════════════════════
class TestResolveAction:
    def test_resolve_action(self):
        pid = client.post("/api/projects", json={"name": "Resolve Me"}).json()["id"]
        client.post(f"/api/projects/{pid}/agents/alert")
        actions = client.get(f"/api/projects/{pid}/agents/actions").json()
        action_id = actions[0]["id"]
        assert actions[0]["resolved"] == 0

        resp = client.patch(f"/api/projects/{pid}/agents/actions/{action_id}/resolve")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_resolve_action_404(self):
        resp = client.patch("/api/projects/1/agents/actions/999/resolve")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# 9. AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════
class TestAuth:
    LOGIN_URL = "/api/auth/login"

    @pytest.fixture(autouse=True)
    def _real_auth(self):
        """Remove the auto-auth override so we test the real auth flow."""
        app.dependency_overrides.pop(require_auth, None)
        yield
        app.dependency_overrides[require_auth] = lambda: "test-user"

    def test_login_success(self):
        """Default credentials: admin / admin"""
        resp = client.post(self.LOGIN_URL, json={
            "username": "admin",
            "password": "admin",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["token_type"] == "bearer"
        assert len(data["token"]) > 20

    def test_login_wrong_password(self):
        resp = client.post(self.LOGIN_URL, json={
            "username": "admin",
            "password": "wrong",
        })
        assert resp.status_code == 401

    def test_login_wrong_username(self):
        resp = client.post(self.LOGIN_URL, json={
            "username": "nobody",
            "password": "admin",
        })
        assert resp.status_code == 401

    def test_unauthenticated_cannot_list_projects(self):
        """No auth header → 401"""
        resp = client.get("/api/projects")
        assert resp.status_code == 401
        assert "Authentication required" in resp.text

    def test_unauthenticated_cannot_create_project(self):
        resp = client.post("/api/projects", json={"name": "Hack"})
        assert resp.status_code == 401

    def test_unauthenticated_cannot_access_dashboard(self):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 401

    def test_unauthenticated_cannot_list_tasks(self):
        resp = client.get("/api/projects/1/tasks")
        assert resp.status_code == 401

    def test_unauthenticated_cannot_run_agents(self):
        resp = client.post("/api/projects/1/agents/monitor")
        assert resp.status_code == 401

    def test_authenticated_request_succeeds(self):
        """Login → use token → access projects"""
        token = client.post(self.LOGIN_URL, json={
            "username": "admin", "password": "admin",
        }).json()["token"]

        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/projects", headers=headers)
        assert resp.status_code == 200

    def test_health_is_public(self):
        """Health endpoint should not require auth"""
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_verify_token(self):
        token = client.post(self.LOGIN_URL, json={
            "username": "admin", "password": "admin",
        }).json()["token"]

        resp = client.get("/api/auth/verify", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        assert resp.json()["user"] == "admin"

    def test_verify_invalid_token(self):
        resp = client.get("/api/auth/verify", headers={
            "Authorization": "Bearer invalid-token-here"
        })
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# 10. ALERT CHANNELS
# ══════════════════════════════════════════════════════════════════════════
class TestAlertChannels:
    """Tests for alert channel status and test dispatch."""

    def test_alert_status_returns_config(self):
        resp = client.get("/api/alerts/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "email" in data
        assert "webhook" in data

    def test_test_alert_returns_results(self):
        resp = client.post("/api/alerts/test", json={
            "subject": "Test",
            "body": "Test body",
            "severity": "info",
            "project_name": "Test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_register_and_list_webhooks(self):
        resp = client.post("/api/alerts/webhooks", json={
            "name": "Slack",
            "url": "https://hooks.slack.com/services/xxx",
            "events": ["alert"],
        })
        assert resp.status_code == 200
        wid = resp.json()["id"]

        resp = client.get("/api/alerts/webhooks")
        assert resp.status_code == 200
        hooks = resp.json()
        assert any(h["id"] == wid for h in hooks)
        assert any(h["name"] == "Slack" for h in hooks)

    def test_delete_webhook(self):
        resp = client.post("/api/alerts/webhooks", json={
            "name": "Temp",
            "url": "https://example.com/hook",
        })
        wid = resp.json()["id"]

        resp = client.delete(f"/api/alerts/webhooks/{wid}")
        assert resp.status_code == 200

        resp = client.delete(f"/api/alerts/webhooks/{wid}")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# 11. SCHEDULER CONFIG
# ══════════════════════════════════════════════════════════════════════════
class TestScheduler:
    """Tests that the scheduler module loads and reports status correctly."""

    def test_scheduler_imports(self):
        """Verify scheduler module can be imported without errors."""
        from backend.scheduler import start_scheduler, stop_scheduler, scheduler
        assert scheduler is not None
        assert callable(start_scheduler)
        assert callable(stop_scheduler)
