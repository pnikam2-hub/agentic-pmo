# SAF — Biomass Gasification Fischer-Tropsch Pathway

## Purpose

This domain pack provides a structured project management framework (phase-gate playbook, WBS, risk register, monitoring rules, KPIs, and checklists) for planning a **Sustainable Aviation Fuel (SAF)** production facility using the **Biomass Gasification + Fischer-Tropsch Synthesis (FT-SPK)** pathway.

The pack covers the full project lifecycle from strategic framing and investment case through feedstock feasibility, technology selection, FEED, EPC, commissioning, product qualification to ASTM D7566 FT-SPK, and operations handover.

## Scope

This pack enables a PMO or project team to:

- Scope and plan a SAF biomass FT project systematically
- Identify and manage key technical, commercial, regulatory, and sustainability risks
- Track certification readiness for ASTM D7566 Annex A1 (FT-SPK) and sustainability certification (CORSIA, ISCC, RSB)
- Monitor critical-path procurement, commissioning, and product quality milestones
- Integrate plan / monitor / alert agent capabilities for digital project oversight

## Important Disclaimer

**This is a PMO / project-planning reference pack. It is NOT engineering design, detailed process engineering, or certified project cost estimate. All technical parameters (temperatures, pressures, yields, catalyst loadings, emissions) are illustrative. Actual project execution requires qualified process engineers, technology licensors, EPC contractors, certification bodies, and regulatory specialists.**

## How to Apply in Agentic PMO

### Via the Template Selector (recommended)

1. Create a new project in Agentic PMO
2. Open the project detail view
3. When the task list is empty, the template selector appears automatically
4. Select **"SAF - Biomass Gasification Fischer-Tropsch Pathway"** from the dropdown
5. Click **Apply Template**
6. All 100+ WBS tasks are created across 8 phases
7. The project is tagged with `domain-pack:saf_biomass_ft`, activating domain-specific Plan, Monitor, and Alert agent behaviours

### Via API

```bash
# Create a project
curl -X POST /api/projects \
  -H "Authorization: Bearer <token>" \
  -d '{"name": "My SAF FT Project"}'

# Apply the domain pack template
curl -X POST /api/templates/domain-saf_biomass_ft/apply \
  -H "Authorization: Bearer <token>" \
  -d '{"project_id": <id>}'
```

## Agent Integration

Once applied, the project gets the `domain-pack:saf_biomass_ft` tag. This enables:

- **Plan Agent** — receives alerts for missing feedstock assessment, gasifier technology selection, syngas cleanup targets, FT catalyst/reactor technology, H2/CO ratio design basis, ASTM qualification route, commissioning plan
- **Monitor Agent** — runs deterministic checks against feedstock contracts, moisture/ash, syngas cleanup delays, H2/CO ratio, FT catalyst/reactor package, ASTM qualification plan, HAZOP close-out
- **Alert Agent** — matches anomalies against 30+ domain monitoring rules and escalates severity

## Pack Contents

| File | Description |
|------|-------------|
| `playbook.md` | 8-phase phase-gate project lifecycle |
| `agent_context.md` | Red flags for Plan, Monitor, and Alert agents |
| `wbs_template.json` | 100+ WBS tasks across all phases |
| `risk_register.json` | 60+ project risks by category |
| `monitoring_rules.json` | 30+ PMO alert rules with severity |
| `kpi_definitions.json` | 25+ schedule, technical, and quality KPIs |
| `permitting_checklist.json` | 25+ environmental and regulatory permits |
| `procurement_checklist.json` | 30+ equipment procurement packages |
| `commissioning_checklist.json` | 30+ commissioning activities and hold points |

## Related Domain Packs

- `green_methanol_biomass` — Green Methanol via Biomass Gasification (separate pathway, analogous gasifier island but different downstream synthesis)
