# Industry 4.0 Engagement Playbook

> How to run an Industry 4.0 smart-manufacturing engagement using the **`industry_4_0`** domain pack.
> This playbook is the operating guide; `wbs_template.json` is the execution plan; `agent_context.md` is the domain knowledge.

---

## 1. Pre-Sales

The pre-sales motion establishes credibility, surfaces value, and sets up a fundable roadmap. Lead with diagnosis, not technology.

1. **Run the Readiness Diagnostic (10-dimension assessment).** Assess strategy, governance, OT maturity, connectivity, data, analytics, cybersecurity, workforce, change capacity, and ROI. Score each dimension with evidence and benchmark against Industry 4.0 maturity. The output is a maturity heatmap and the gap-to-target that justifies the engagement.
2. **Map the client's maturity to AI-Native stages (Curious → Aware → Capable → Advanced → Native).** Place the client honestly on this trajectory and show the staged path forward. Most clients are between Curious and Capable; the goal is to move them one or two stages with measurable outcomes.
3. **Identify quick wins for a 90-day pilot.** Choose interventions that are high-impact, feasible with current data, and visible to leadership — e.g., OEE visibility on a bottleneck line, downtime reason capture, or a vision QA proof on a defect with high scrap cost.
4. **Present the phased roadmap with ROI projections.** Show the 8-phase plan mapped to weeks, with the pilot de-risking the larger investment. Quantify the business case and payback so the CFO can sponsor it.

> **Pre-sales principle:** Diagnose before you prescribe. A credible diagnostic earns the right to propose a roadmap.

---

## 2. Phase 0 — Strategic Framing (Weeks 1–4)

Phase 0 converts the pre-sales narrative into a governed, funded program.

Begin by securing the **project charter**: objectives, in/out-of-scope plants and lines, the executive sponsor, the budget envelope, and the 64-week timeline. In parallel, run **stakeholder mapping and a RACI** that explicitly separates OT and IT decision rights — ambiguity here is the single biggest cause of approval delays later. Charter and RACI together give you a defensible scope boundary and an escalation path.

Next, stand up the **PMO machinery** (RAID log, status reporting, steering committee cadence, change control) and the **business case**. The business case must be quantified and signed off by finance and plant leadership: baseline OEE, yield, downtime, and scrap from plant data; benefit assumptions for each lever (yield uplift, OEE gain, downtime reduction, energy savings); payback period and NPV; and scaling economics across the full footprint. A business case that finance has not validated will not survive a stage gate.

Finally, align the diagnostic maturity to the **AI-Native roadmap**, select the pilot line, prepare the **partner/vendor RFPs and longlists**, and define the **target operating model and governance** for the converged IT/OT organization. The exit criterion for Phase 0 is a charter, a validated business case, a pilot line, and an RFP package ready to issue.

---

## 3. Phases 1–7 — Execution Guidance

### Phase 1 — Site Assessment & OT Discovery (Weeks 5–8)
Discover brownfield reality before designing anything. Walk every in-scope line; build the asset register with criticality and connectivity; capture exact protocols and tag lists; survey connectivity and the sensor gap; map the process and sequence of operations; baseline OT security. **This phase is frequently underestimated — protect its time budget, because every gap discovered here is far cheaper to fix now than in build.**

### Phase 2 — Solution Architecture (Weeks 9–14)
Design the end-to-end architecture: edge/cloud tiers, converged network with IEC 62443 zones/conduits, security blueprint with target security levels, data platform (historian + lake + edge), MES/QMS/WMS integration, the ISA-95 information model and OPC UA/MQTT namespaces, HA/DR, and governance. Exit only with **Architecture Review Board sign-off and ADRs** — do not procure or build against an unsigned design.

### Phase 3 — Technology Procurement (Weeks 15–20)
Convert the architecture into RFPs and purchase orders. Evaluate vendors against the procurement checklist (open protocols, ruggedization, security, scalability, references). Negotiate license models to avoid escalation at scale. Plan logistics and customs early — industrial hardware lead times can slip deployment waves. Receive, inspect, and baseline every device in the asset register before deployment.

### Phase 4 — Network & IT/OT Infrastructure (Weeks 21–28)
Build the connectivity foundation. Cable, terminate, and certify; configure VLAN segmentation and the OT/IT DMZ with deny-by-default; commission edge gateways and bridging; install sensors during approved production windows; bring up edge compute and GPU; synchronize time (PTP/NTP); and validate segmentation with an internal pen test. **No analytics work is credible until this layer is signed off.**

### Phase 5 — IIoT, Data Platform & Visibility (Weeks 29–40)
Stand up the historian and data lake, build machine-to-historian-to-lake pipelines with contextualization, and deliver the real-time **control tower** (OEE, yield, downtime). Integrate MES, QMS, and WMS; enable end-to-end traceability (module genealogy); enforce data quality rules. This phase produces the first leadership-visible value: a plant that can finally *see itself* in real time.

### Phase 6 — Analytics, AI & Optimization (Weeks 41–56)
Now that trusted data exists, build computer vision defect detection (e.g., electroluminescence imaging for solar cell/module micro-cracks and solder defects), predictive maintenance from vibration/thermal data, yield and root-cause analytics, a digital twin, and closed-loop control with safe-state fallback. Stand up MLOps for reproducible training, registry, and deployment. Validate models for accuracy and bias, operationalize with monitoring and retraining, and document AI governance. **Exit with pilot results and validated ROI.**

### Phase 7 — Operations Handover & Continuous Improvement (Weeks 57–64)
Make it stick. Deliver role-based training, hand over SOPs and maintenance procedures, and stand up the continuous-improvement framework and quarterly ROI reviews. Progress OT cybersecurity toward IEC 62443 certification for the certified scope, build the workforce upskilling roadmap, and establish steady-state governance (model risk, change control, CAB). Close with the **scale-out roadmap** to replicate the pattern across remaining lines and sites.

---

## 4. Pilot Strategy — The 90-Day Proof of Value

The pilot is the linchpin of the engagement: it de-risks full rollout and earns continued funding.

**Define the 90-Day Proof of Value as:**

- **Pick one production line** — representative of the broader plant, with a clear bottleneck or quality pain point and adequate data potential. Avoid the hardest line (too risky) and the easiest (results won't generalize).
- **Instrument it** — connectivity, edge, sensors, historian, and dashboards come first. You cannot prove what you cannot measure.
- **Prove OEE/visibility gains** — baseline the line rigorously before instrumenting, then demonstrate measurable improvement in OEE, downtime, and/or yield within 90 days.
- **De-risk full rollout** — use the pilot to validate the architecture, the SI, the operating model, and the unit economics. Capture lessons learned into the scale-out plan.

A successful pilot answers three questions for the steering committee: *Did it work? Was the value real and measured? Can we replicate it profitably?* If yes, scaling is straightforward; if not, pivot scope before committing more capital.

---

## 5. Vendor Management

Industry 4.0 programs span OT hardware vendors, system integrators, and software platform vendors — each with different incentives.

- **OT hardware vendors (gateways, sensors, cameras, PLCs).** Engage OEMs early for protocol documentation and support. Buy ruggedized, environmentally rated hardware with documented patch SLAs and IEC 62443-4-x conformance where possible. Pre-position spares and define the RMA process. Beware proprietary protocols — require OPC UA/MQTT or documented APIs.
- **System integrators (SI).** Select an SI with proven Industry 4.0 and OT credentials, verified references, and relevant case studies. Write **precise SOWs tied to deliverables and acceptance criteria** (loose SOWs generate change orders). Insist on knowledge transfer and post-go-live support so the client is not perpetually dependent. Stage payments against milestones.
- **Software platform vendors (historian, data platform, MES, cloud, ML).** Negotiate license models that scale without punitive cost curves (model full-plant economics). Retain **ownership of data, derived data, and custom models** in contracts; define vendor usage rights and exit/portability clauses. Prefer open APIs and standard formats to limit lock-in.

**Cross-cutting:** maintain a single vendor governance view, manage interfaces and data ownership explicitly, and never let any single vendor own the critical data abstraction that everything else depends on — that belongs to the client.

---

## 6. ROI Calculation

Build the business case bottom-up from plant data, then stress-test the assumptions with finance.

### ROI Template

1. **Pilot cost** — hardware (edge, sensors, cameras, security appliances), platform licenses, SI services, and internal time. Express as total pilot investment.
2. **Projected gains** — quantify each lever against baseline:
   - Yield uplift (first-pass yield / scrap reduction) → recovered units × contribution margin.
   - OEE gain (availability, performance, quality) → recovered production hours × throughput value.
   - Unplanned downtime reduction → downtime hours avoided × cost per hour.
   - Energy savings → kWh saved × energy cost.
   - Maintenance cost reduction → fewer emergency repairs, lower MTTR, optimized spares.
3. **Payback period** — pilot + scale investment ÷ annualized benefit. Target within the sponsor's threshold (often 12–24 months for the program, faster for the pilot).
4. **Scaling economics** — marginal cost per additional line drops sharply once the architecture, platform, and patterns exist; model the full-plant NPV, not just the pilot.

### Reference Example — Vikram Solar 5 GW

For a large solar module manufacturer at **5 GW annual capacity** (e.g., Vikram Solar), yield is the dominant value driver because output is sold at full module value. A **0.5–1% yield improvement** translates to roughly **₹25–75 crore/year** in incremental revenue/value, depending on module mix and pricing. Because this improvement recurs every year and compounds with OEE and downtime gains, the program can pay back well within the sponsor threshold and scale profitably across the full footprint.

> **ROI discipline:** baseline before instrumenting, measure the delta honestly, and have finance co-sign the assumptions. An overstated case collapses at the first stage gate; a conservative, validated case scales.

---

## 7. Cadence and Governance (Cross-Phase)

- **Steering committee** — monthly, with phase stage gates as decision points.
- **Weekly status** — progress, RAID, EV/forecast, upcoming production windows.
- **Change control** — all scope changes via CAB with ROI linkage; park new asks in the backlog.
- **Security governance** — OT change advisory, patch cadence, incident response readiness reviewed quarterly.
- **Benefits tracking** — quarterly ROI review comparing realized vs. business case, with corrective action for shortfalls.

Use the pack artifacts to operationalize this: `wbs_template.json` for planning, `risk_register.json` for RAID, `kpi_definitions.json` for measurement, `monitoring_rules.json` (28 rules) for steady-state operations, and the procurement/commissioning checklists for vendor selection and go-live gates.
