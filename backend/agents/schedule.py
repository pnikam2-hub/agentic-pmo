"""Schedule analysis for the agents.

The Monitor agent used to receive one flat line per task — status, priority, estimate, due date. It
could not see that a task was waiting on a predecessor that had not started, which is the most common
real cause of slippage on an EPC plan, and it could not see how late anything actually was.

Everything here is deterministic: dates, dependency edges and statuses in, a small set of named
breaches out. The LLM's job is judgement over those numbers, not arithmetic.
"""
import datetime

DONE = "done"


def _as_naive(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if getattr(value, "tzinfo", None) is not None:
        return value.replace(tzinfo=None)
    return value


def analyse(tasks, now: datetime.datetime | None = None, chain_limit: int = 12) -> dict:
    """Return the schedule facts an agent can reason about.

    Overdue = past its due date and not done.
    Blocked = not done, and at least one predecessor is not done either — i.e. it cannot finish
    tomorrow no matter who is assigned, because the thing it waits on has not happened.
    """
    now = _as_naive(now) or datetime.datetime.utcnow()
    by_id = {t.id: t for t in tasks}

    total_hours = sum(float(t.estimated_hours or 0) for t in tasks)
    done_tasks = [t for t in tasks if t.status == DONE]

    overdue = []
    blocked = []
    dangling = 0

    for t in tasks:
        if t.status == DONE:
            continue

        due = _as_naive(t.due_date)
        if due is not None:
            days_late = (now - due).days
            if days_late > 0:
                overdue.append({
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "days_late": days_late,
                    "due_date": due.strftime("%Y-%m-%d"),
                })

        preds = []
        for dep_id in (t.dependencies or []):
            pred = by_id.get(dep_id)
            if pred is None:
                dangling += 1
                continue
            if pred.status != DONE:
                preds.append(pred)
        if preds:
            blocked.append({
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "blockers": [
                    {"title": p.title, "status": p.status} for p in preds
                ],
            })

    overdue.sort(key=lambda r: -r["days_late"])
    # most-blocked first: a task waiting on three predecessors is a worse signal than one waiting on one
    blocked.sort(key=lambda r: (-len(r["blockers"]), r["title"]))
    blocked = blocked[:chain_limit]

    return {
        "task_count": len(tasks),
        "done_count": len(done_tasks),
        "percent_done": round(100.0 * len(done_tasks) / len(tasks), 1) if tasks else 0.0,
        "total_hours": round(total_hours, 1),
        "overdue": overdue,
        "overdue_count": len(overdue),
        "worst_late_days": overdue[0]["days_late"] if overdue else 0,
        "blocked": blocked,
        "blocked_count": len(blocked),
        "dangling_edges": dangling,
    }


def render(signals: dict) -> str:
    """A compact text block for the prompt. Deterministic wording, no prose the model has to undo."""
    lines = [
        "SCHEDULE SIGNALS (computed from dates and dependency edges, not guessed):",
        f"- tasks: {signals['task_count']} | done: {signals['done_count']} "
        f"({signals['percent_done']}%) | estimated effort: {signals['total_hours']} h",
    ]

    if signals["overdue_count"]:
        lines.append(f"- overdue: {signals['overdue_count']} task(s), worst {signals['worst_late_days']} day(s) late")
        for rec in signals["overdue"][:5]:
            lines.append(
                f"    · {rec['title']} — {rec['days_late']}d late (due {rec['due_date']}, "
                f"status {rec['status']}, priority {rec['priority']})"
            )
    else:
        lines.append("- overdue: none")

    if signals["blocked_count"]:
        lines.append(
            f"- waiting on an unfinished predecessor: {signals['blocked_count']} task(s) "
            "(these cannot complete until the named predecessor does)"
        )
        for rec in signals["blocked"]:
            blockers = "; ".join(f"{b['title']} [{b['status']}]" for b in rec["blockers"])
            lines.append(f"    · {rec['title']} [{rec['status']}] <- {blockers}")
    else:
        lines.append("- waiting on an unfinished predecessor: none")

    if signals["dangling_edges"]:
        lines.append(
            f"- note: {signals['dangling_edges']} dependency edge(s) point at tasks outside this project "
            "and were ignored"
        )

    lines.append(
        "Reason over these chains: for anything late or waiting, name the predecessor that has to move "
        "and say what it unblocks. Do not restate the numbers as findings."
    )
    return "\n".join(lines)
