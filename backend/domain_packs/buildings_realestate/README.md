# Agentic PMO Domain Pack — High-Rise Commercial Mixed-Use Tower

## What this pack is

This domain pack is the domain-knowledge backbone of an AI-powered Project Management Office (Agentic PMO) operating with three coordinated agents:

- **Plan Agent** — builds, sequences, and validates project plans using the lifecycle playbook, WBS template, permitting checklist, and procurement checklist.
- **Monitor Agent** — continuously tracks live project signals against the monitoring rules and KPI definitions to detect drift, slippage, and emerging risk.
- **Alert Agent** — raises severity-graded alerts and recommended actions when monitored thresholds or red-flag conditions are breached.

The pack encodes real-world high-rise construction practice: core-and-slab construction, post-tensioned floor plates, deep basements, tower crane logistics, curtain wall installation, MEP riser coordination, and phased commissioning/handover.

## Projects served

High-rise commercial **mixed-use towers**: typically 45–60 storeys, core-and-slab construction with post-tensioned floor plates, unitised or stick-system curtain wall facades, multi-level deep basements, tower cranes (climbing/flat-top), structural steel + reinforced concrete frame, MEP risers serving office/retail/residential floors, on constrained urban city sites adjacent to occupied neighbouring buildings, delivered for a developer-client working with external design consultants. Jurisdiction-agnostic: permitting references the generic "local authority / municipal planning authority".

## The 10 files

| # | File | Purpose |
|---|------|---------|
| 1 | `README.md` | Pack overview and usage guide |
| 2 | `playbook.md` | Phase-gate lifecycle (Phases 0–7) with objectives, activities, exit criteria |
| 3 | `wbs_template.json` | 106-task work breakdown structure template across all 8 phases |
| 4 | `risk_register.json` | 55 tower-specific risks with early-warning signals, mitigations, contingencies |
| 5 | `monitoring_rules.json` | 24 keyword-based trigger rules wired to risk register IDs |
| 6 | `kpi_definitions.json` | 18 KPIs covering schedule, safety, quality, construction, cost, handover |
| 7 | `permitting_checklist.json` | 16 permits/approvals with lead times and evidence requirements |
| 8 | `procurement_checklist.json` | 21 procurement packages with qualification criteria and acceptance tests |
| 9 | `commissioning_checklist.json` | 18 commissioning activities with hold points and acceptance criteria |
| 10 | `agent_context.md` | Red flags, domain nuances, and behavioural guidance for all three agents |

## How the agents use the pack

- **Plan Agent** ingests `playbook.md` + `wbs_template.json` to generate a phase-gated schedule; cross-checks `permitting_checklist.json` and `procurement_checklist.json` to place long-lead and authority-approval items on the critical path; uses `agent_context.md` red flags to validate plan completeness.
- **Monitor Agent** matches incoming project signals (task titles, site reports, progress records) against `monitoring_rules.json` trigger conditions; computes trends using `kpi_definitions.json`; links observed signals to `risk_register.json` entries via `related_risks`.
- **Alert Agent** grades alerts (`warning` / `high` / `critical`) from rule severity, attaches the recommended action, names the accountable owner role from the risk register, and escalates per `agent_context.md` alert red flags.

## Disclaimer

**PMO/domain reference — must be reviewed by qualified engineers and construction professionals.**
