# EPC Project Playbook

> How to run an EPC capital project using the **`epc_project`** domain pack.
> This playbook is the operating guide; `wbs_template.json` is the execution plan; `agent_context.md` is the domain knowledge.

---

## Phase 0 — Strategic Framing & Project Initiation (Weeks 1-4)

**Objective:** Establish governance, secure funding, define project scope, and prepare for FEED.

Begin by securing the **project charter** with the project sponsor. Define project objectives — capacity, product specifications, battery limits, and target schedule and budget. Establish the **project governance** including steering committee, project manager, core team RACI, and change control board.

Develop the **project execution plan (PEP)** that defines contracting strategy (EPC lump-sum, reimbursable, split packages), procurement philosophy, and quality plan. Complete a **preliminary risk assessment** and risk register.

Prepare the **FEED scope of work package** for bidding. Issue pre-FEED RFQ to qualified engineering contractors. Evaluate and select the FEED contractor.

### Exit Criteria
- Project charter signed by sponsor
- PEP approved
- FEED contractor selected and notice to proceed issued
- Preliminary risk register established

---

## Phase 1 — FEL / FEED / Basic Engineering (Weeks 5-20)

**Objective:** Complete front-end engineering to freeze process design, major equipment specifications, and enable detailed engineering.

The FEED contractor develops the **process design package** including Process Flow Diagrams (PFDs), heat and mass balances, and preliminary Piping & Instrumentation Diagrams (P&IDs). The **process control philosophy** and **safety philosophy** are established.

Conduct the **HAZOP study** on the P&ID set. Based on HAZOP findings, carry out **SIL/LOPA studies** for safety instrumented functions. Issue HAZOP action close-out report.

Develop **preliminary equipment datasheets** and **Material Take-Offs (MTOs)** for bulk materials. Issue **long-lead equipment (LLE) inquiry packages** — compressors, turbines, reactors, columns, heat exchangers, pumps, vessels, and packaged units.

Establish the **project cost estimate (Class 3)** and **project schedule** with critical path identified. Finalize the **project controls baseline** (budget and schedule) for client approval.

### Exit Criteria
- PFDs and P&IDs issued for design (IFD)
- HAZOP completed and actions closed
- LLE inquiry packages issued
- Class 3 cost estimate approved
- Project controls baseline established

---

## Phase 2 — Detailed Engineering (Weeks 21-40)

**Objective:** Complete all detailed engineering deliverables for procurement and construction.

The engineering team produces **Issued for Construction (IFC) drawings**: plot plan, equipment layout, piping general arrangement, isometrics, structural steel, foundations, electrical single-line, cable routing, instrument hook-ups, and junction box schedules.

Complete **3D model reviews** at 30%, 60%, and 90% progress milestones with input from construction, commissioning, and operations teams. Resolve all interdisciplinary clashes.

Finalize **datasheets and specifications** for all equipment and bulk materials. Prepare and issue **Material Requisitions (MRs)** for all engineered equipment and bulks.

Update **P&IDs to IFC status**. Complete **civil/structural design**, **piping stress analysis**, **electrical design** (load list, cable sizing, MCC schedule), and **instrumentation design** (loop diagrams, IO lists, DCS/PLC architecture).

### Exit Criteria
- 90% 3D model review completed
- All IFC drawings issued
- All MRs for long-lead and engineered equipment issued
- P&IDs at IFC status
- Design freezes in place to control change orders

---

## Phase 3 — Permitting & Statutory Approvals (Weeks 1-40, parallel)

**Objective:** Obtain all statutory approvals and permits required for construction and operation.

Engage regulatory bodies early. Apply for **Environmental Clearance (EC)** with EIA report. Obtain **Consent to Establish (CTE)** from pollution control board. Secure **factory license** and **boiler registration** under applicable regulations.

Apply for **building / construction permits** from local municipal authority. Obtain **fire department NOC**. Secure **electrical safety approval** from the electrical inspectorate.

For hazardous process plants: obtain **chemical / major accident hazard (MAH) approvals**, **explosives license** if applicable, and **hazardous waste authorisation**.

Engage third-party **statutory audit agencies** for pressure vessels, lifting equipment, and electrical installations. Plan the permit-to-work (PTW) system for construction phase.

### Exit Criteria
- Environmental clearance / EIA approval received
- CTE issued
- Construction permit / building approval received
- Boiler registration (if applicable) initiated
- All major statutory approvals in hand before construction

---

## Phase 4 — Procurement & Supply Chain (Weeks 8-52, parallel from Phase 1 onward)

**Objective:** Procure all equipment and materials on time, within budget, and to specification.

Execute the procurement strategy. Issue **Material Requisitions (MRs)** to approved vendor list (AVL). Evaluate **Technical Bid Evaluations (TBEs)** — engineering reviews all vendor proposals for compliance. Resolve technical clarifications via Technical Queries (TQs). Commercial evaluations and negotiations follow.

Place **Purchase Orders (POs)** for all packages. For **long-lead equipment** — reactors, columns, compressors, turbines, heat exchanges — place POs as early as possible to secure manufacturing slots.

Manage **vendor document review (VDR)** process: vendor submits design/datasheet/G.A. drawings, engineering reviews and returns marked-up, cycle repeats until approval. Track VDR status by package.

Perform **expediting** at critical manufacturing milestones (raw material release, welding, assembly, testing). For critical packages, conduct **stage-wise inspection** per ITP. Witness **Factory Acceptance Tests (FAT)** for packaged equipment, control systems, and DCS.

Manage **logistics** — pack and preserve equipment for ocean/road transport. Oversee freight forwarding, customs clearance, and site delivery. Verify completeness against packing list at site receipt.

### Exit Criteria
- All POs placed for long-lead equipment (minimum)
- VDR minimum 80% approved for fabrication
- FATs completed for all critical packages
- First major deliveries arriving at site
- Logistics plan implemented

---

## Phase 5 — Construction: Civil, Structural & Mechanical (Weeks 20-68)

**Objective:** Complete site preparation, foundations, civil/structural works, and mechanical installation.

Site preparation: clear and grade the site, establish site facilities (laydown, offices, stores), set up temporary utilities (power, water, drainage). Survey and set out grid lines.

Excavate and pour **foundations** for all equipment following the foundation schedule. Install **structural steel** — columns, beams, platforms, pipe racks. Apply industrial flooring and paving as needed.

**Mechanical installation**: receive, inspect, and set equipment. Procedure: lift plan → rigging → placement on foundation → alignment (shafts, couplings, elevations) → grouting → secondary alignment. Equipment includes columns, reactors, compressors, turbines, pumps, heat exchangers, packaged units.

Complete **piping fabrication** (spool welding in shop) and **piping erection** (spool installation, fit-up, welding at site). Manage weld traceability — WPS/PQR/WPQ qualification, weld mapping, NDT (RT/UT/MPI/PT). Apply bolted flange management (joint integrity).

### Exit Criteria
- All major foundations poured and cured
- Structural steel erected to 90%
- Critical equipment set, aligned, and grouted
- Piping erection 50%+ progress
- Weld NDT statistics within acceptable range (weld rejection rate < 3%)

---

## Phase 6 — Construction: E&I, HSE & Quality (Weeks 40-76, parallel with Phase 5)

**Objective:** Complete electrical, instrumentation installation, maintain HSE, and ensure quality compliance.

**Electrical**: install cable trays, pull and terminate power and control cables per cable schedule. Mount and connect MCCs, VFDs, switchgear, transformers, lighting panels. Complete earthing and lightning protection system.

**Instrumentation**: install field instruments (pressure, temperature, level, flow, analysers), junction boxes, and marshalling panels. Run tubing and impulse lines. Install DCS/PLC/SIS cabinets and marshalling racks. Install telecom, fire alarm, and PA/GA systems.

**HSE**: implement permit-to-work (PTW) system for all construction activities. Manage Simultaneous Operations (SIMOPS) where multiple disciplines work in the same area. Controls for: lifting operations, confined space entry, hot work, working at height, excavation, LOTO (Lock-Out Tag-Out). Maintain emergency response plan and site medical facilities. Track leading/lagging HSE KPIs.

**Quality**: implement Inspection and Test Plans (ITPs) as defined in the Project Quality Plan. Conduct **welding inspections** — visual, RT/UT review, WPQR compliance. Perform **hydrostatic testing** of piping systems (hydrotest packages). Issue **Non-Conformance Reports (NCRs)** for deviations and track root cause analysis and corrective action. Compile **punch lists** for incomplete or defective work.

### Exit Criteria
- Cable pulling and termination at 80%+ progress
- Field instruments installed and tubed per P&ID
- HSE performance within target (LTI rate, near-miss reporting)
- Hydrotest packages at 70%+ completion
- Punch list items being tracked and resolved

---

## Phase 7 — Pre-Commissioning, Commissioning & Handover (Weeks 68-88)

**Objective:** Achieve mechanical completion, pre-commission, commission, start up, and hand over to operations.

**Pre-Commissioning / Mechanical Completion (MC):** Verify that construction is complete in a system-by-system zone approach. Complete all punch list items. Submit **Mechanical Completion (MC) dossiers** for each system — including design docs, as-builts, test records, material certificates, NCR close-out.

Conduct **pre-commissioning activities**: cleaning and flushing of piping systems, chemical cleaning, drying, leak testing (hydrostatic / pneumatic). Rotate and run-in major equipment: compressors run-in, pump run, motor meggar and no-load test. Energise electrical systems — HV/LV switchgear, MCCs, UPS — and complete loop checks. Load DCS/SIS/PLC software and verify IO signal mapping.

**Commissioning**: introduce process fluids (water batching, inert gas purging, catalyst loading). Commission utilities — cooling water, instrument air, nitrogen, steam. Conduct **punch list walkdowns** with operations team. Obtain **Ready for Start-Up (RFSU)** certificate.

**Start-Up and Performance Test**: ramp up the plant to design capacity. Run the **Performance Guarantee Test** — verify throughput, product quality, utility consumption, emissions, and other guarantee parameters as per the EPC contract. Operate for the agreed test duration (typically 72 hours continuous). If guarantees are met, issue the **Provisional Acceptance Certificate (PAC)**.

**Handover and Close-Out**: transfer spare parts, special tools, operating manuals, and maintenance procedures. Train operators and maintenance teams. Complete the **as-built documentation** handover. Close out all project contracts, finalize the cost account, resolve claims and back-charges. Issue the **Final Acceptance Certificate (FAC)** after the warranty period (typically 12-24 months).

Conduct the **lessons learned workshop**. Archive project documentation. Hand the project to the operations organisation.

### Exit Criteria
- Mechanical completion certificates issued for all systems
- RFSU signed
- Performance guarantee test passed
- PAC issued
- Operators trained and operations team in place
- Project close-out report submitted
- FAC issued (or FAC timeline agreed)

---

> **Note:** Phase durations are indicative. EPC project durations typically range from 18-48 months depending on complexity, size, and regulatory environment. The WBS provides estimated hours per task as a guideline for project controls.
