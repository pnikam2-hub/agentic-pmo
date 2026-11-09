# Highway EPC – UK Smart Motorway / All-Purpose Trunk Road Upgrade

**Pack name:** `highway_epc_uk`
**Domain:** Highway construction EPC (Engineering, Procurement & Construction) on the UK Strategic Road Network (SRN).
**Typical schemes:** M62 Junction 10–12 Smart Motorway Upgrade; A14 Cambridge to Huntingdon Improvement; 40–55 km motorway widening or all-purpose trunk road (APTR) upgrade.
**Design leader / client:** National Highways (formerly Highways England), under DBFO / DPR-type delivery arrangements.
**Lifecycle model:** Eight phase-gated phases (0 Strategic Framing → 7 Completion, Handover & Optimisation).

> PMO/domain reference — must be reviewed by qualified highway/structural engineers.

## Scope of this pack

This pack gives the Agentic PMO agents (Plan, Monitor, Alert) a UK-specific reference for delivering a large highway EPC scheme. It encodes the work breakdown, risk register, monitoring rules, KPIs and checklists aligned to National Highways standards, the Design Manual for Roads and Bridges (DMRB), CDM 2015 and the consenting routes applicable to Nationally Significant Infrastructure Projects (NSIPs).

Coverage includes: traffic data and modelling; DMRB Stage 1–3 scheme assessment; preliminary and detailed design (alignment, pavement to CD 236, structures, drainage to CD 527, lighting to BS 5489); Environmental Impact Assessment; ecology mitigation (bats, badgers, great crested newts); archaeology; DCO/TWAO consents and Public Inquiry; CPO/land acquisition; utility diversions; Section 278 / street works agreements; procurement of long-lead and smart-motorway packages; earthworks, pavement, structures, drainage, VRS, gantries and VMS, smart motorway technology (MIDAS, ERF, HSR); traffic management and night closures/lane rental; commissioning; road safety audits (DMRB CD 377); and as-built handover.

## Files in this pack

| File | Purpose |
| --- | --- |
| `README.md` | This overview — scope and file index. |
| `playbook.md` | Phase-gate lifecycle narration of the 8 phases with UK-specific gates. |
| `agent_context.md` | Agent instructions, red flags, standards context and monitoring cadence. |
| `wbs_template.json` | Flat work-breakdown task list (T001–T100) across all 8 phases. |
| `risk_register.json` | UK highway EPC risks (R01–R56) with mitigations and contingencies. |
| `monitoring_rules.json` | Trigger-based monitoring rules (M01–M30) linked to phase and risk IDs. |
| `kpi_definitions.json` | KPI definitions (KPI01–KPI20) for schedule, cost, quality, HSE, environment. |
| `procurement_checklist.json` | Procurement packages (long-lead and standard) with acceptance tests. |
| `commissioning_checklist.json` | Commissioning activities with hold points and acceptance criteria. |
| `highway_epc_demo_seed.json` | Realistic mid-construction demo project instance of this pack. |

## Phase mapping (0–7)

- **0** Strategic Framing
- **1** Feasibility & Option Assessment (DMRB Stage 2)
- **2** Scheme Design & Pre-Construction (Preliminary Design / DMRB Stage 3)
- **3** Detailed Design & Consents (DCO/TWAO, EIA, Public Inquiry, CPO/land)
- **4** Procurement & Construction Preparation
- **5** Construction Execution (main works, TM, night closures)
- **6** Commissioning & Performance Testing (incl. safety audits)
- **7** Completion, Handover & Optimisation

## How to use

1. Load `wbs_template.json` to instantiate the task baseline for a scheme.
2. Seed the risk register and KPI tracker from the pack files.
3. Enable the monitoring rules so the Monitor and Alert agents can fire against live status.
4. Use the demo seed (`highway_epc_demo_seed.json`) to exercise the agents on a realistic mid-construction project.

**Disclaimer:** PMO/domain reference data generated for demonstration only — must be reviewed by qualified highway/structural engineers before use on a real scheme.
