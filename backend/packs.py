"""Domain pack loader — curated domain intelligence shipped with the platform.

A pack is a folder under backend/domain_packs/<pack_id>/ containing:
  README.md, agent_context.md, playbook.md, wbs_template.json,
  risk_register.json, kpi_definitions.json, monitoring_rules.json and
  permitting/procurement/commissioning checklists.

The packs are reference material for the agents, not just documentation:
plan uses agent_context + risk themes, monitor uses monitoring_rules and KPI
definitions, alert uses the top risks.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Optional

PACK_DIR = pathlib.Path(__file__).parent / "domain_packs"

DISPLAY = {
    "epc_project": (
        "EPC / Capital Project",
        "Generic engineering, procurement and construction delivery — FEED through commissioning.",
    ),
    "industry_4_0": (
        "Industry 4.0 Engagement",
        "Smart manufacturing implementation: assessment, pilots, OT/IT integration, scale-up.",
    ),
    "green_methanol_biomass": (
        "Green Methanol (Biomass Gasification)",
        "Biomass gasification to green methanol — feedstock, syngas, synthesis, offtake.",
    ),
    "saf_biomass_ft": (
        "SAF (Biomass Gasification / FT)",
        "Sustainable aviation fuel via gasification and Fischer-Tropsch — certification and offtake.",
    ),
    "highway_epc_uk": (
        "Highway EPC (UK)",
        "UK trunk road and smart motorway upgrades — DCO, highways standards, traffic management.",
    ),
    "buildings_realestate": (
        "High-Rise Commercial Real Estate",
        "High-rise commercial mixed-use tower — design, permitting, construction, handover.",
    ),
    "board_diversity": (
        "Board Diversity & Governance",
        "Board diversity policy work — mandate, search, appointment, disclosure and review.",
    ),
}

_cache: dict[str, dict[str, Any]] = {}


def _read_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def pack_ids() -> list[str]:
    if not PACK_DIR.exists():
        return []
    return sorted(p.name for p in PACK_DIR.iterdir() if p.is_dir())


def load(pack_id: str) -> Optional[dict[str, Any]]:
    """Load a pack once, cache it, return None if it does not exist."""
    if pack_id in _cache:
        return _cache[pack_id]
    base = PACK_DIR / pack_id
    if not base.is_dir():
        return None

    wbs = _read_json(base / "wbs_template.json")
    risks = _read_json(base / "risk_register.json")
    kpis = _read_json(base / "kpi_definitions.json")
    rules = _read_json(base / "monitoring_rules.json")

    name, description = DISPLAY.get(pack_id, (pack_id.replace("_", " ").title(), ""))

    pack = {
        "id": pack_id,
        "name": name,
        "description": description,
        "template_name": wbs.get("template_name", name),
        "tags": wbs.get("tags", []),
        "agent_context": _read_text(base / "agent_context.md"),
        "playbook": _read_text(base / "playbook.md"),
        "wbs": wbs,
        "risks": risks.get("risks", []),
        "kpis": kpis.get("kpis", []),
        "rules": rules.get("rules", []),
        "checklists": {
            "permitting": _read_json(base / "permitting_checklist.json"),
            "procurement": _read_json(base / "procurement_checklist.json"),
            "commissioning": _read_json(base / "commissioning_checklist.json"),
        },
        "categories": {
            "risks": risks.get("category_counts", {}),
            "kpis": kpis.get("dimension_counts", {}),
            "rules": rules.get("category_counts", {}),
        },
    }
    _cache[pack_id] = pack
    return pack


def summarise(pack_id: str) -> Optional[dict[str, Any]]:
    pack = load(pack_id)
    if not pack:
        return None
    wbs = pack["wbs"]
    tasks = wbs.get("tasks", [])
    return {
        "id": pack["id"],
        "name": pack["name"],
        "description": pack["description"],
        "tags": pack["tags"],
        "phase_count": len(wbs.get("phases", [])) or len({t.get("phase", 0) for t in tasks}),
        "total_tasks": len(tasks),
        "total_estimated_hours": int(sum(float(t.get("estimated_hours", 0) or 0) for t in tasks)),
        "risk_count": len(pack["risks"]),
        "kpi_count": len(pack["kpis"]),
        "rule_count": len(pack["rules"]),
        "checklists": {
            k: len(v.get("items", v.get("checklist", []))) if isinstance(v, dict) else 0
            for k, v in pack["checklists"].items()
        },
        "categories": pack["categories"],
    }


def all_summaries() -> list[dict[str, Any]]:
    out = []
    for pid in pack_ids():
        s = summarise(pid)
        if s:
            out.append(s)
    return out


def phases_of(pack: dict[str, Any]) -> dict[int, str]:
    """phase index → display name, synthesising names when the WBS omits them."""
    declared = {p.get("id", i): p.get("name", f"Phase {i + 1}")
                for i, p in enumerate(pack["wbs"].get("phases", []) or [])}
    used = {int(t.get("phase", 0) or 0) for t in pack["wbs"].get("tasks", [])}
    return {i: declared.get(i, f"Phase {i + 1}") for i in sorted(used | set(declared))}


def top_risks(pack: dict[str, Any], limit: int = 15) -> list[dict[str, Any]]:
    weight = {"high": 3, "medium": 2, "low": 1}
    return sorted(
        pack["risks"],
        key=lambda r: weight.get((r.get("impact") or "").lower(), 0)
        * weight.get((r.get("probability") or "").lower(), 0),
        reverse=True,
    )[:limit]


# ── Agent context ────────────────────────────────────────────────────────────

def for_project(db, project_id: int):
    """The ProjectPack row attached to a project, or None."""
    from backend.models import ProjectPack
    return db.query(ProjectPack).filter(ProjectPack.project_id == project_id).first()


def agent_context(project_pack, kind: str) -> str:
    """Compact domain context injected into an agent prompt.

    project_pack is a models.ProjectPack row (or None). Returns "" when the
    project has no pack attached, so callers can concatenate unconditionally.
    """
    if project_pack is None:
        return ""
    pack = load(project_pack.pack_id)
    if not pack:
        return ""

    if kind == "plan":
        risks = top_risks(pack, 12)
        kpi_names = ", ".join(k.get("name", "") for k in pack["kpis"][:15] if k.get("name"))
        lines = [
            f"DOMAIN PACK: {pack['name']}",
            pack["agent_context"].strip()[:4000],
            "KEY RISK THEMES (design the plan and its gates around these):",
            *[f"- {r.get('title')} ({r.get('probability')} probability / {r.get('impact')} impact)"
              for r in risks],
        ]
        if kpi_names:
            lines.append(f"MEASURE PROGRESS WITH THESE KPIs: {kpi_names}")
        return "\n".join(lines)

    if kind == "monitor":
        rules = pack["rules"][:25]
        kpis = pack["kpis"][:15]
        lines = [
            f"DOMAIN PACK MONITORING RULES ({pack['name']}):",
            *[f"- [{r.get('severity', 'info')}] {r.get('trigger_condition')} → {r.get('recommended_action')}"
              for r in rules],
        ]
        if kpis:
            lines.append("KPIs TO WATCH: " + ", ".join(
                f"{k.get('name')} (target {k.get('target')})" for k in kpis if k.get("name")))
        return "\n".join(lines)

    if kind == "alert":
        risks = top_risks(pack, 10)
        return "\n".join([
            f"DOMAIN PACK RISK REGISTER ({pack['name']}) — match the anomaly against these:",
            *[f"- {r.get('title')}: warning signs = {r.get('early_warning_signals')}; "
              f"mitigation = {r.get('mitigation')}" for r in risks],
        ])

    return ""
