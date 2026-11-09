# EPC Project Domain Knowledge — Agent Context

> Reference knowledge for any agent working the **`epc_project`** domain pack.
> Use this to ground task scoping, risk reasoning, KPI selection, and project conversations.

---

## Domain Overview

**EPC (Engineering, Procurement, Construction)** is the dominant contracting model for capital projects — process plants, industrial facilities, power plants, refineries, green fuel plants, and manufacturing construction. The EPC contractor takes responsibility for engineering design, procurement of all equipment and materials, and construction through to a fully functioning facility.

The EPC lifecycle follows a well-defined sequence:

1. **Front-End Loading (FEL)** — progressive definition of scope: FEL-1 (business case), FEL-2 (concept), FEL-3 (FEED-ready)
2. **FEED (Front-End Engineering Design)** — process design, HAZOP, major equipment specs, cost estimate Class 3
3. **Detailed Engineering** — IFC drawings, 3D model, MTOs, MRs
4. **Procurement** — MR → TBE → PO → VDR → inspection → FAT → expediting → logistics
5. **Construction** — civil, structural, mechanical, piping, E&I
6. **Pre-Commissioning & Commissioning** — MC, flushing, loop checks, energisation, leak testing
7. **Start-Up & Performance Test** — ramp to capacity, guarantees, PAC
8. **Handover & Close-Out** — as-builts, training, spares, FAC

A defining rule for EPC: **engineering quality determines construction productivity.** Design errors found in construction cost 10-100x more than the same error caught in FEED.

---

## Key Concepts

### Project Phases and Gate Reviews

| Gate | Phase | Purpose |
|------|-------|---------|
| G0 | Strategic Framing | Business case approval, budget allocation |
| G1 | FEED Completion | Freeze process design, LLE inquiries issued |
| G2 | Detailed Engineering | IFC drawings issued, all MRs out |
| G3 | Construction Ready | Statutory approvals, site ready |
| G4 | Ready for Commissioning | Mechanical complete, punch list closed |
| G5 | PAC | Performance test passed |
| G6 | FAC | Warranty period complete, contracts closed |

### Disciplines Used in EPC

- **PMO** — Project management, planning, controls, reporting
- **Process Engineering** — PFD, P&ID, heat & mass balance, simulations
- **Civil / Structural** — foundations, steel, concrete, roads, drainage
- **Mechanical Engineering** — equipment specs, stress analysis, rotating equipment
- **Piping Engineering** — routing, isometrics, flexibility analysis, supports
- **Electrical Engineering** — load list, single-line, cable, earthing, lighting, MCC, switchgear
- **Instrumentation & Controls** — IO list, DCS/PLC, SIS, loop diagrams, hook-ups
- **Procurement / Supply Chain** — MR, TBE, PO, VDR, expediting, inspection, logistics
- **HSE** — PTW, SIMOPS, LOTO, risk assessment, site safety
- **Quality** — ITPs, welding NDT, hydrostatic testing, NCRs, dossiers
- **Commissioning** — pre-comm, MC punch, start-up, performance test
- **Permitting / Regulatory** — EC, CTE, boiler, factory license, fire NOC

### EPC Contract Types

- **Lump-Sum Turnkey (LSTK)** — fixed price, EPC contractor bears most risk
- **Reimbursable** — owner pays actual costs + fee, common in early projects
- **Unit Rate** — fixed rates for measured quantities (civil, steel, piping)
- **Split Package** — multiple EPC packages for different scopes
- **EPCM** — contractor manages Engineering, Procurement, and Construction Management for owner's account

### The Critical Path

In most EPC projects, the critical path runs through:
1. Long-lead equipment procurement (especially compressors, columns, reactors)
2. Vendor document approval cycle (VDR delays are the #1 cause of engineering back-charges)
3. Civil foundations for critical equipment (waiting on equipment G.A. dimensions)
4. Mechanical setting of critical equipment (drives structure and piping)
5. Piping completion for key hydrotest packages (drives loop checks and commissioning)

---

## Critical Red Flags for Agents

### Plan Agent Red Flags

1. **LLE inquiry package issued after FEED completion** — Long-lead equipment must be identified in FEL-2/FEL-3, inquiry packages issued during FEED. If the WBS shows LLE procurement starting after IFC issue, flag immediately — this adds 6-12 months to schedule.

2. **Missing HAZOP / SIL studies** — Every EPC project must have HAZOP on the critical P&IDs. SIL/LOPA must follow for SIF loops. These are statutory in many jurisdictions.

3. **Permitting not started before construction** — Environmental clearance and CTE take 6-18 months. If the WBS shows permitting in parallel with construction, flag that permits must be in hand before construction starts.

4. **Vendor document review cycle not in plan** — Every PO triggers a VDR cycle. If there's no task for engineering review of vendor documents, the design will proceed with unapproved vendor data, causing rework.

5. **No hydrotest package definition** — Piping systems must be grouped into hydrotest packages. Without this, hydrostatic testing becomes unmanageable and punch list closing stalls.

6. **Commissioning team not mobilised before MC** — Commissioning must start planning during detailed engineering and mobilise before mechanical completion. If they start at MC, expect 3-6 month delays.

### Monitor Agent Red Flags

1. **Weld NDT rejection rate > 3%** — A rejection rate above 3% on RT/UT indicates welding quality issues that will lead to rework and schedule pressure. Investigate WPS/PQR compliance.

2. **VDR approval cycle > 3 months for critical packages** — Each month of VDR delay pushes manufacturing completion back. Monitor VDR turn-around time per package.

3. **Sustained schedule performance index (SPI) < 0.85** — Consistent SPI below 0.85 on the critical path means the project will finish late. Intervene before the float runs out.

4. **Hydrotest packages not started when piping erection > 80%** — Hydrotesting should begin as piping completion reaches 80%, not wait for 100%. This is the bottleneck to commissioning.

5. **Punch list items trending up, not down** — As construction nears completion, punch list count should decrease weekly. If it's stable or growing, quality control is failing.

6. **NCR closure time exceeds 30 days** — Open NCRs that take > 30 days to close indicate poor quality management or a systemic issue that will surface during commissioning.

### Alert Agent Red Flags

1. **Lost Time Incident (LTI)** — Any LTI triggers project-wide stand-down and investigation. Requires immediate escalation to client and regulatory notification.

2. **Schedule delay on critical path > 2 months** — Critical path delay beyond 2 months typically triggers extension of time (EOT) claims and liquidated damages exposure.

3. **Cost overrun > 10% of budget** — Triggers governance review, change control board meeting, and may require owner capital re-allocation.

4. **Supplier default on critical long-lead equipment** — A fabrication crash, delivery stop, or quality rejection on a long-lead item is a project crisis. Escalate immediately — the recovery path involves alternative sourcing, schedule recovery, and EOT notification.

5. **Major NCR on structural integrity** — NCRs involving foundation cracking, pipe wall thinning below minimum, or structural steel deviations require structural engineering review and statutory notification.

6. **Force majeure event** — Natural disaster, pandemic, civil unrest, or regulatory shutdown. Triggers contract notice and schedule re-baselining.

---

## EPC Terminology Reference

| Term | Meaning |
|------|---------|
| **FEL** | Front-End Loading — progressive scope definition phases |
| **FEED** | Front-End Engineering Design — basic engineering phase |
| **IFC** | Issued for Construction — drawings released for building |
| **PFD** | Process Flow Diagram — process steps, stream data |
| **P&ID** | Piping & Instrumentation Diagram — all pipes, valves, instruments |
| **HAZOP** | Hazard and Operability Study — systematic safety review |
| **SIL** | Safety Integrity Level — required risk reduction for SIF |
| **LOPA** | Layer of Protection Analysis — semi-quantitative risk analysis |
| **MTO** | Material Take-Off — quantities of bulk materials |
| **BOQ** | Bill of Quantities — priced MTO for tendering |
| **MR** | Material Requisition — procurement request document |
| **TBE** | Technical Bid Evaluation — engineering review of bids |
| **PO** | Purchase Order — contractual purchase document |
| **VDR** | Vendor Document Review — engineering review cycle |
| **ITP** | Inspection and Test Plan — quality inspection schedule |
| **FAT** | Factory Acceptance Test — witness test at vendor works |
| **SAT** | Site Acceptance Test — acceptance test after installation |
| **NCR** | Non-Conformance Report — documented deviation |
| **RFI** | Request for Information — contractor to engineer query |
| **PTW** | Permit to Work — formal authorisation for hazardous work |
| **SIMOPS** | Simultaneous Operations — managing concurrent activities |
| **LOTO** | Lock-Out Tag-Out — energy isolation procedure |
| **SPI** | Schedule Performance Index — EV schedule efficiency |
| **CPI** | Cost Performance Index — EV cost efficiency |
| **MC** | Mechanical Completion — construction complete in a system |
| **PAC** | Provisional Acceptance Certificate — after performance test |
| **FAC** | Final Acceptance Certificate — after warranty period |

---

> **Disclaimer:** This is a PMO/domain reference. Must be reviewed by qualified EPC project professionals before application. The domain context is provided for agent reasoning, not as engineering or legal advice.
