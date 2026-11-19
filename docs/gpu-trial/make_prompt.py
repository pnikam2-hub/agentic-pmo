#!/usr/bin/env python3
"""Build the monitor-agent prompt set from a PMO task export.

The point of the trial is to compare models on *our* workload, so the prompt has to be the real one:
the same schedule signals block and the same task list the Monitor agent sends, not a toy question.

Produce the export on the server that holds the PMO database:

    sqlite3 -json data/agentic_pmo.db \\
      "select id,title,status,priority,estimated_hours,due_date,dependencies
       from tasks where project_id=3 order by sort_order" > tasks.json

then:  python make_prompt.py tasks.json --project "EPC Project — AI Native PMO pilot" \\
                                    -o sample_prompt.json
"""
import argparse
import datetime
import json
import re
import sys

SYSTEM = (
    "You are an AI project monitor. Review the task status summary and identify:\n"
    "1. Tasks at risk of delay\n2. Blocked dependencies\n3. Resource bottlenecks\n"
    "4. Overdue items\n5. Recommended actions\n\n"
    "The summary opens with SCHEDULE SIGNALS: lateness in days and dependency chains computed from "
    "the data. Treat them as facts, do not recompute them, and do not restate them as findings. Use "
    "them to reason about consequence: when a task waits on an unfinished predecessor, name that "
    "predecessor and say what slips if it does not move, and which tasks it unblocks when it does.\n\n"
    "Return JSON with keys: 'risks' (list), 'blocked_dependencies' (list), 'recommendations' (list), "
    "'health_score' (0-100), 'summary'."
)

CODING_SYSTEM = (
    "You are a senior engineer on a FastAPI codebase. Answer with a single unified diff and nothing "
    "else — no prose, no explanation. The code must run as written."
)
CODING_USER = (
    "Add GET /api/projects/{project_id}/tasks.csv to backend/routers/tasks.py. It returns a CSV "
    "attachment named tasks.csv with the header: id,title,status,priority,assignee,estimated_hours,"
    "actual_hours,due_date. Rows are ordered by sort_order then id. Missing dates are empty strings. "
    "Add two tests: one that a project with two tasks returns three lines with the header, and one "
    "that an unknown project returns 404. Reply with the diff only."
)


def build_signals(tasks, now=None, chain_limit=12):
    now = now or datetime.datetime.utcnow()
    by_id = {t["id"]: t for t in tasks}
    overdue, blocked, dangling = [], [], 0
    total_hours = sum(float(t.get("estimated_hours") or 0) for t in tasks)
    done = [t for t in tasks if t["status"] == "done"]

    for t in tasks:
        if t["status"] == "done":
            continue
        due = t.get("due_date")
        if due:
            try:
                d = datetime.datetime.fromisoformat(str(due).replace("Z", "+00:00").split(".")[0])
                d = d.replace(tzinfo=None)
            except ValueError:
                d = None
            if d:
                days = (now - d).days
                if days > 0:
                    overdue.append((days, t))
        preds = [by_id[x] for x in (t.get("dependencies") or []) if x in by_id]
        dangling += len([x for x in (t.get("dependencies") or []) if x not in by_id])
        unfinished = [p for p in preds if p["status"] != "done"]
        if unfinished:
            blocked.append((t, unfinished))

    overdue.sort(key=lambda r: -r[0])
    blocked.sort(key=lambda r: (-len(r[1]), r[0]["title"]))

    lines = [
        "SCHEDULE SIGNALS (computed from dates and dependency edges, not guessed):",
        f"- tasks: {len(tasks)} | done: {len(done)} "
        f"({round(100.0 * len(done) / len(tasks), 1) if tasks else 0}%) | estimated effort: {round(total_hours, 1)} h",
    ]
    if overdue:
        lines.append(f"- overdue: {len(overdue)} task(s), worst {overdue[0][0]} day(s) late")
        for days, t in overdue[:5]:
            lines.append(f"    · {t['title']} — {days}d late (priority {t['priority']})")
    else:
        lines.append("- overdue: none")

    if blocked:
        shown = min(chain_limit, len(blocked))
        extra = (f" — the {shown} worst chains are listed below; the rest follow the same pattern"
                 if len(blocked) > shown else "")
        lines.append(f"- waiting on an unfinished predecessor: {len(blocked)} task(s) "
                     f"(these cannot complete until the named predecessor does){extra}")
        for t, preds in blocked[:shown]:
            names = "; ".join(f"{p['title']} [{p['status']}]" for p in preds)
            lines.append(f"    · {t['title']} [{t['status']}] <- {names}")
    else:
        lines.append("- waiting on an unfinished predecessor: none")

    if dangling:
        lines.append(f"- note: {dangling} dependency edge(s) point at tasks outside this project and "
                     "were ignored")
    lines.append("Reason over these chains: for anything late or waiting, name the predecessor that "
                 "has to move and say what it unblocks. Do not restate the numbers as findings.")
    return "\n".join(lines)


def build_task_list(tasks, limit=180):
    out = []
    for t in tasks[:limit]:
        bits = [f"priority: {t['priority']}", f"est: {t.get('estimated_hours', 0)}h"]
        if t.get("due_date"):
            bits.append(f"due: {str(t['due_date'])[:10]}")
        if t.get("dependencies"):
            bits.append(f"waits on {len(t['dependencies'])} task(s)")
        out.append(f"- [{t['status']}] {t['title']} ({', '.join(bits)})")
    if len(tasks) > limit:
        out.append(f"- … {len(tasks) - limit} further tasks omitted")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks_json")
    ap.add_argument("--project", default="EPC Project — AI Native PMO pilot")
    ap.add_argument("-o", "--out", default="sample_prompt.json")
    args = ap.parse_args()

    tasks = json.load(open(args.tasks_json))
    if isinstance(tasks, dict) and "tasks" in tasks:
        tasks = tasks["tasks"]
    for t in tasks:
        deps = t.get("dependencies")
        if isinstance(deps, str):
            t["dependencies"] = json.loads(deps) if deps.strip().startswith("[") else []

    reasoning = (f"Project: {args.project}\nTasks: {build_signals(tasks)}\n\n"
                 f"TASK LIST:\n{build_task_list(tasks)}\n\nAnalyse and report issues.")

    prompts = [
        {"name": "monitor-165-task-epc", "expect": "json", "system": SYSTEM, "user": reasoning},
        {"name": "csv-export-endpoint", "expect": "text", "system": CODING_SYSTEM, "user": CODING_USER},
    ]
    json.dump(prompts, open(args.out, "w"), indent=1)
    chars = len(reasoning)
    print(f"wrote {args.out}: {len(prompts)} prompts | reasoning prompt {chars:,} chars "
          f"(~{chars // 4:,} tokens) | {len(tasks)} tasks")


if __name__ == "__main__":
    main()
