"""Tests for the schedule analysis the Monitor agent now receives.

These are pure functions over in-memory task objects: no database, no LLM. The point is that the
numbers an agent reasons over are computed deterministically and tested, not inferred by the model.
"""
import datetime

import pytest

from backend.agents.schedule import analyse, render


class T:
    """Stand-in for a Task row."""

    def __init__(self, id, title, status="todo", due=None, deps=None, priority="medium", hours=8.0):
        self.id = id
        self.title = title
        self.status = status
        self.due_date = due
        self.dependencies = deps or []
        self.priority = priority
        self.estimated_hours = hours


NOW = datetime.datetime(2026, 11, 19, 12, 0, 0)


def test_overdue_is_measured_in_days():
    tasks = [
        T(1, "Permit filing", due=datetime.datetime(2026, 11, 9)),      # 10 days late
        T(2, "Site survey", due=datetime.datetime(2026, 11, 17)),        # 2 days late
        T(3, "Charter", due=datetime.datetime(2026, 11, 25)),            # not late
    ]
    s = analyse(tasks, now=NOW)
    assert s["overdue_count"] == 2
    assert s["worst_late_days"] == 10
    assert s["overdue"][0]["title"] == "Permit filing"


def test_completed_tasks_are_never_overdue_or_blocked():
    tasks = [
        T(1, "Charter", status="done", due=datetime.datetime(2026, 1, 1)),
        T(2, "Design", status="done", deps=[1]),
    ]
    s = analyse(tasks, now=NOW)
    assert s["overdue_count"] == 0
    assert s["blocked_count"] == 0
    assert s["percent_done"] == 100.0


def test_blocked_means_predecessor_not_done():
    tasks = [
        T(1, "Charter", status="in_progress"),
        T(2, "Design", deps=[1]),
        T(3, "Procure", deps=[2]),
    ]
    s = analyse(tasks, now=NOW)
    titles = {r["title"]: r for r in s["blocked"]}
    assert titles["Design"]["blockers"] == [{"title": "Charter", "status": "in_progress"}]
    assert titles["Procure"]["blockers"][0]["title"] == "Design"


def test_finished_predecessor_unblocks_the_successor():
    tasks = [
        T(1, "Charter", status="done"),
        T(2, "Design", deps=[1]),
    ]
    s = analyse(tasks, now=NOW)
    assert s["blocked_count"] == 0


def test_dangling_dependency_ids_are_ignored_not_crashed():
    tasks = [T(1, "Design", deps=[999])]
    s = analyse(tasks, now=NOW)
    assert s["blocked_count"] == 0
    assert s["dangling_edges"] == 1


def test_most_blocked_sorted_first_and_chain_limit_applies():
    tasks = [T(0, "Root")]
    for i in range(1, 6):
        tasks.append(T(i, f"Child {i}", deps=[0]))
    tasks.append(T(99, "Wide", deps=[0, 1, 2]))
    s = analyse(tasks, now=NOW, chain_limit=3)
    assert len(s["blocked"]) == 3
    assert s["blocked"][0]["title"] == "Wide"     # three blockers, so worst
    # the count is the truth, the list is a sample — reporting the sample as the count understates
    assert s["blocked_count"] == 6
    assert s["blocked_shown"] == 3


def test_totals_and_resilience_to_missing_hours():
    tasks = [T(1, "A", hours=10.0), T(2, "B", hours=None)]
    s = analyse(tasks, now=NOW)
    assert s["total_hours"] == 10.0
    assert s["task_count"] == 2


def test_render_names_the_predecessor():
    tasks = [T(1, "Charter", status="in_progress"), T(2, "Design", deps=[1])]
    text = render(analyse(tasks, now=NOW))
    assert "SCHEDULE SIGNALS" in text
    assert "Design" in text and "Charter" in text
    assert "waiting on an unfinished predecessor" in text


def test_render_says_none_when_clean():
    text = render(analyse([T(1, "Charter", status="done")], now=NOW))
    assert "overdue: none" in text
    assert "predecessor: none" in text
