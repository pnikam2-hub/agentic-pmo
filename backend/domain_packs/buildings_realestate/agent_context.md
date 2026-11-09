# Agent Context — High-Rise Commercial Mixed-Use Tower

## Disclaimer

**PMO/domain reference — must be reviewed by qualified engineers and construction professionals.** This domain context is provided for agent reasoning, not as engineering or legal advice.

This file governs how the Plan, Monitor, and Alert agents reason about high-rise mixed-use tower projects. Agents must combine this context with `wbs_template.json`, `risk_register.json`, `monitoring_rules.json`, and the checklists rather than acting on generic construction heuristics.

---

## Critical Red Flags for Plan Agent

Flag these conditions whenever generating or validating a plan. Any occurrence requires plan revision before release:

1. **Missing long-lead items on the critical path.** A tower plan that does not explicitly place tower cranes, elevators/escalators, curtain wall units, switchgear, and facade access cradles as ordered long-lead packages with delivery milestones is structurally flawed. Elevator orders must precede shaft handover by the factory lead time; curtain wall orders must precede topping-out by fabrication + shipping lead time.
2. **Missing permitting critical path.** Plans must sequence outline consent → full planning permission → building control approval → fire strategy approval → party-wall agreements → highway/oversail licences, with condition discharge *before* mobilisation. A plan starting construction while approvals are "assumed" is invalid.
3. **No contingency in the slab cycle.** The repetitive post-tensioned floor cycle must carry explicit contingency (weather, concrete strength gain, crane availability, labour absence). A plan assuming the theoretical best-case cycle for 45+ floors will cascade slippage into facade, MEP, and commissioning.
4. **Core lead floors not protected.** The core must stay a minimum number of floors ahead of slab production; plans that let facade or MEP start compress this lead create structural access conflicts.
5. **Commissioning window unprotected.** Life-safety commissioning (fire alarm cause-and-effect, smoke control, sprinkler hydro, lift safe-mode tests) needs a protected window; plans that let construction overrun eat it will fail at handover.
6. **Urban logistics underestimated.** Constrained city sites need consolidation centres, booked delivery slots, and out-of-hours pour permissions baked into the plan — not improvised later.
7. **Neighbour interfaces unscheduled.** Condition surveys, party-wall notices, and monitoring installation must precede piling/excavation in the plan, not run concurrently.

---

## Critical Red Flags for Monitor Agent

Escalate to the Alert Agent when these patterns appear in live signals:

1. **Crane inspection overdue.** Any tower crane operating with a lapsed or expiring thorough-examination certificate is an immediate high-severity finding; correlate with lift-plan deviation counts.
2. **Concrete cycle slipped.** Rolling slab cycle exceeding baseline by >15%, or core jump cycle stretching, indicates buffer erosion that compounds floor over floor — quantify cumulative programme impact, not just the single-floor variance.
3. **Subcontractor claims rising.** Rising claim submission frequency plus growing change-order backlog signals commercial destabilisation; check for insolvency warning signs (late supplier payments, staff departures) in parallel.
4. **Cladding airtightness fails.** Failed facade air/water tests, or missing fire-performance evidence for delivered cladding batches, block zone sign-off — treat evidence gaps as critical, not administrative.
5. **Punch list growing.** When snag raising rate exceeds closure rate for multiple weeks, practical completion date is at risk; project the crossover mathematically.
6. **Groundwater and movement triggers.** Piezometer exceedances or neighbouring-building movement approaching amber triggers require immediate linkage to dewatering and excavation status.
7. **MEP clash burn-down reversing.** A rising clash count in the federated model two weeks ahead of affected riser installation predicts site rework.
8. **Under-reporting safety signal.** Falling near-miss reports alongside steady work volume is itself a red flag — it usually precedes an injury trend, not follows it.

---

## Critical Red Flags for Alert Agent

Issue immediate, severity-graded alerts for:

1. **Working-at-height incident.** Any fall, arrested fall, or near-fall from slab edge, shaft, or facade zone → critical alert to HSE Manager and Project Manager; recommend zone stand-down and tower-wide edge-protection re-inspection.
2. **Crane over-capacity or lift-plan breach.** Any lift exceeding rated capacity, unapproved tandem lift, or climb outside wind limits → critical alert; recommend immediate lifting stand-down and engineering review.
3. **Fire strategy non-compliance.** Non-conforming cladding fire evidence, cavity barrier gaps, or failed smoke-control performance → critical alert to Facade Manager, Quality Manager, and Permitting Lead; recommend halting affected installations and notifying building control.
4. **Basement water ingress.** Active ingress post-tanking or rising sump duty beyond design → critical alert to Foundation/Geotech Engineer and Quality Manager; recommend diagnostic deployment and protection of finishes.
5. **Cost overrun threshold.** Forecast final cost breaching contingency consumption thresholds (e.g., CPI < 0.95 or >50% contingency consumed ahead of progress) → critical alert to Commercial Manager and developer-client sponsor with earned-value decomposition.
6. **Life-safety commissioning shortcut attempts.** Any pressure to skip, compress, or defer witnessed fire/lift/smoke tests → critical alert; recommend firm refusal and client escalation.
7. **Neighbour settlement trigger breach.** Monitoring exceeding red-line values → critical alert recommending excavation pause and compensation-grouting readiness.

---

## Domain Nuances

- **High-rise safety regime:** Working at height dominates risk exposure — collective edge protection before trades, permit-to-work systems, rescue plans, and crane/exclusion-zone discipline are non-negotiable. Multi-trade simultaneous operation across 50+ floors demands floor-zoned logistics and strict interface management.
- **Tower crane coordination:** Climbing luffing cranes on constrained sites involve engineered climb sequences, tie-ins to the structure, oversail licensing over public highway and neighbours, and wind-ceiling stoppages. Crane time is the scarcest site resource — hook-time conflicts between concrete, facade, and steel drives most productivity loss.
- **Basement dewatering:** Deep basements in urban settings require redundant dewatering capacity, piezometer trigger regimes, recharge strategies to protect neighbouring foundations, and permitted discharge — all linked to settlement monitoring of adjacent occupied buildings.
- **Post-tensioned slab cycle:** The economic engine of the tower. Cycle time depends on concrete strength gain for stressing, formwork sets in rotation, crane hook availability, and PT crew continuity. Elongation (+/-7%) and grouting QA on every slab protects both structure and programme.
- **Curtain wall quality:** Unitised facades are won or lost in the factory and the mock-up. Factory QA residency, incoming inspection, zone air/water testing, and slab-to-facade fire-stopping continuity determine whether the building closes in on schedule and passes building control.
- **MEP coordination:** Riser congestion is the chronic clash zone. Weekly federated-model reviews with burn-down targets, prefabricated riser modules, and penetration drawings issued to structure before pouring prevent the most expensive class of rework.
- **Handover of stratified assets:** Mixed-use towers hand over in layers — retail podium, office floors, residential/hotel levels — each with distinct operators, tenancy fit-outs, and completion certificates. Commissioning, snagging, O&M documentation, and DLP regimes must be structured per stratum while sharing core plant and life-safety systems.

---

## Estimated Hours Guidance

Agents should treat `estimated_hours` in `wbs_template.json` as **guidelines, not commitments**. They represent typical planning magnitudes for a 45–60 storey tower and must be recalibrated against: actual site productivity data, subcontractor resource plans, weather seasonality, approval authority lead times, and the specific floor count and basement depth of the target project. Never present estimated_hours to users as fixed durations; always express derived dates as ranges with stated confidence, and re-baseline when monitoring signals show systematic variance.
