# EPC Project Domain Pack

> **Generic EPC / Capital Project domain pack for Agentic PMO**
> Suitable for process plants, industrial facilities, green fuel plants, and manufacturing construction projects.

## Overview

This domain pack provides a comprehensive Work Breakdown Structure (WBS), risk register, monitoring rules, KPIs, and checklists for Engineering, Procurement, and Construction (EPC) capital projects. It covers the full project lifecycle from initiation through commissioning and handover.

## When to Use This Pack

- **Greenfield capital projects** — new process plants, manufacturing facilities, industrial complexes
- **Brownfield expansions** — additions to existing facilities with tie-in management
- **Green fuel / SAF / Methanol EPC** — once technology selection and FEED are complete
- **Infrastructure construction** — where the project requires civil, structural, mechanical, piping, E&I, and commissioning

## What's Included

| File | Content | Count |
|------|---------|-------|
| `wbs_template.json` | Work Breakdown Structure across 8 EPC phases | 143 tasks |
| `risk_register.json` | EPC-specific risks across 10 categories | 85+ risks |
| `monitoring_rules.json` | PMO monitoring and alert rules | 40+ rules |
| `kpi_definitions.json` | Schedule, cost, quality, HSE, and progress KPIs | 32 KPIs |
| `permitting_checklist.json` | Statutory permits and approvals | 28 permits |
| `procurement_checklist.json` | Long-lead equipment, vendor documents, expediting | 32 packages |
| `commissioning_checklist.json` | Pre-comm, mechanical completion, start-up, handover | 38 activities |
| `playbook.md` | Phase-gate project lifecycle playbook | 8 phases |
| `agent_context.md` | Agent instructions for Plan/Monitor/Alert agents | — |
| `README.md` | This file | — |

## EPC Lifecycle Phases

| Phase | Name | Focus |
|-------|------|-------|
| 0 | Strategic Framing & Initiation | Charter, governance, pre-FEED scope |
| 1 | FEL / FEED / Basic Engineering | PFDs, P&IDs, HAZOP, SIL, MTOs |
| 2 | Detailed Engineering | IFC drawings, specs, 3D model, BOQs |
| 3 | Permitting & Statutory Approvals | EC, CTE, factory/boiler licenses |
| 4 | Procurement & Supply Chain | LLE, MR/TBE/PO, VDR, expediting |
| 5 | Construction — Civil & Mechanical | Foundations, steel, equipment setting, piping |
| 6 | Construction — E&I, HSE, Quality | Electrical, instrumentation, ITPs, NCRs |
| 7 | Pre-Commissioning, Commissioning & Handover | MC, pre-comm, start-up, performance test, PAC |

## Key Terminology

FEL, FEED, IFC, PFD, P&ID, HAZOP, SIL, LOPA, MTO, BOQ, MR, TBE, PO, VDR, ITP, FAT, SAT, NCR, RFI, PTW, SIMOPS, LOTO, S-curve, earned value, mechanical completion, pre-commissioning, punch list, PAC, FAC.

## Usage

1. **Create a project** in Agentic PMO
2. **Apply the template** — all 125+ tasks are created across all phases
3. The project gets tagged `domain-pack:epc_project`
4. Plan Agent, Monitor Agent, and Alert Agent use the domain context automatically

> **Disclaimer:** This is a PMO/domain reference pack. Must be reviewed by qualified EPC project professionals before real project execution. The authors assume no liability for project outcomes based on this template.
