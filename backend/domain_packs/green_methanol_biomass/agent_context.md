# Green Methanol via Biomass Gasification — Agent Context

## Domain Overview

This pack covers the project lifecycle of a **green methanol production facility** using **biomass gasification**. The facility converts solid biomass (agricultural residue, forestry residue, organic waste) into synthesis gas (syngas), which is cleaned, conditioned, and catalytically converted to methanol. The methanol is purified to fuel-grade spec and stored for dispatch.

The pathway is:

```
Feedstock Prep → Gasification → Syngas Cleanup → Ratio Adjustment → Methanol Synthesis → Purification → Storage
```

## Key Technical Facts for Agents

### Feedstock
- 1.5–2.2 tonnes of dry biomass yields approximately 1 tonne of methanol
- Feedstock moisture >30% significantly penalises gasifier efficiency (requires drying)
- Key contaminants to track: moisture, ash, alkali metals, chlorine, sulphur
- Feedstock variability (seasonal, source-dependent) is a systemic risk

### Gasification
- Operating temperature: 700–1,400°C depending on gasifier type
- Output gas is raw syngas containing CO, H2, CO2, CH4, tars, particulates, ash
- Air-blown produces nitrogen-diluted syngas; oxygen-blown yields higher quality
- Tar formation is the single biggest operational challenge
- Refractory wear is expected; replacement costs are high

### Syngas Cleanup
- Tars must be reduced to < 10–50 mg/Nm³ depending on downstream spec
- Sulphur (H2S, COS) must be removed to < 0.1 ppmv for methanol catalyst
- Chlorine (HCl) must be < 1 ppmv
- Alkali metals must be removed — poison methanol catalyst
- Guard beds provide final polishing protection

### Syngas Ratio Adjustment
- Ideal ratio for methanol synthesis: (H2 - CO2) / (CO + CO2) ≈ 2.0
- Water-gas shift converts CO + H2O → H2 + CO2 to adjust ratio
- CO2 removal or recycle may be needed
- Methane slip dilutes syngas and reduces methanol yield

### Methanol Synthesis
- Copper-based catalyst (Cu/ZnO/Al2O3)
- Typical operating conditions: 50–100 bar, 200–300°C
- Catalyst is highly sensitive to sulphur and chlorine poisoning
- Single-pass conversion is ~40–60%; unconverted gas is recycled
- Catalyst lifetime is typically 3–5 years; replacement cost is significant

### Purification
- Crude methanol contains water, ethanol, higher alcohols, ethers
- Two-column or three-column distillation yields fuel-grade (IMPCA spec) methanol
- Key impurities: ethanol, acetone, propanol

## Critical Red Flags for Agents

The Plan, Monitor, and Alert agents MUST flag the following issues if the project plan is vague, missing, or underspecified:

### Plan Agent — Must flag if missing:
- Syngas cleanup technology selection and performance targets
- Catalyst poison control strategy (sulphur, chlorine, metals)
- Feedstock variability and moisture management
- HAZID/HAZOP requirement
- EIA/permit application schedule
- Commissioning sequence (cold → hot → performance test)
- Product quality specification (IMPCA or equivalent)
- Ash/char disposal plan
- Flare/thermal oxidiser for off-gas handling

### Monitor Agent — Must flag if:
- Feedstock contracts not signed by end of Phase 2
- HAZOP not closed before Phase 4 construction start
- Syngas cleanup package procurement delayed beyond EPC start
- Catalyst procurement not initiated at least 12 months before commissioning
- H2/CO ratio target not defined or not being achieved in design
- EIA permit not submitted by Phase 2 gate
- Methanol synthesis loop design not started by Phase 3
- Commissioning readiness assessment not scheduled
- Product quality test plan not defined

### Alert Agent — Must generate alerts for:
- Feedstock moisture consistently above 30% in supply
- Gasifier vendor delay exceeding 30 days from contract date
- Missing HAZOP close-out 3 months before construction complete
- Catalyst procurement order not placed >12 months before commissioning
- H2/CO ratio unresolved at FEED completion
- EIA permit delayed beyond statutory timeline
- Commissioning punch list >10% open at scheduled start
- Methanol quality fails initial production sample

## Reference Documents
- Project playbook (playbook.md) — phase-gate structure
- WBS template (wbs_template.json) — task list by discipline
- Risk register (risk_register.json) — 50+ project risks
- Monitoring rules (monitoring_rules.json) — rule-based trigger conditions
- KPI definitions (kpi_definitions.json) — project and technical KPIs
- Permitting checklist (permitting_checklist.json)
- Procurement checklist (procurement_checklist.json)
- Commissioning checklist (commissioning_checklist.json)

## Disclaimer

This context is a PMO/domain reference and must be reviewed by qualified process engineers, safety professionals, and regulatory experts before application to a real project. The agent outputs are for planning and monitoring assistance only, not for engineering decision-making.
