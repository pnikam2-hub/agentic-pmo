# Industry 4.0 Domain Knowledge — Agent Context

> Reference knowledge for any agent working the **`industry_4_0`** domain pack.
> Use this to ground task scoping, risk reasoning, KPI selection, and client conversations.

---

## Domain Overview

**Industry 4.0** is the integration of digital technologies into manufacturing operations to create smart, connected, and self-optimizing factories. It moves production from isolated, manual, and reactive systems toward real-time visibility, data-driven decisions, and closed-loop control.

The transformation rests on four pillars:

1. **Connectivity** — every critical asset speaks a common digital language (OPC UA, MQTT/Sparkplug B) and streams data.
2. **Data & Visibility** — a unified data platform (historian + data lake + context layer) powers real-time control towers and traceability.
3. **Analytics & AI** — descriptive, diagnostic, predictive, and prescriptive analytics, including computer vision and ML models, often with edge inference.
4. **Cybersecurity & Governance** — IEC 62443-aligned OT security and operating governance that make the connected factory safe to run and scale.

A defining rule of thumb for this domain: **connectivity comes before analytics, and security comes before scale.** Programs that invert this order fail to realize value or create unacceptable production risk.

---

## Key Concepts

### ISA-95 Architecture Layers (L0–L4)

ISA-95 (IEC 62264) is the reference model for integrating enterprise and control systems. It defines a hierarchy from the physical process to the enterprise, and a common vocabulary (enterprise → site → area → line → cell → equipment) that the data model and tag naming should follow.

| Layer | Level | Examples | Role |
|-------|-------|----------|------|
| **L0** | Process | Sensors, actuators, motors, drives | Physical measurement and actuation |
| **L1** | Sensing/Manipulation | PLCs, PID controllers, I/O | Real-time control of the process |
| **L2** | Monitoring/Supervision | SCADA, HMI, DCS | Supervise and coordinate L1 control loops |
| **L3** | Operations/MES | MES, historian, QMS, scheduling | Manage production execution, traceability, and site-level operations |
| **L4** | Business Planning | ERP, supply chain, finance | Order-to-cash, demand, and enterprise logistics |

The boundary between **L3 (operations/OT)** and **L4 (enterprise/IT)** is where IT/OT convergence happens and where the DMZ, historian, and integration platform live.

### IT/OT Convergence Patterns

IT (enterprise systems) and OT (control systems) have historically been separate, with different priorities: OT optimizes for **safety, availability, and determinism**; IT optimizes for **confidentiality, flexibility, and efficiency**. Convergence enables value but introduces risk.

Common patterns:

- **Purdue Model / IEC 62443 zones & conduits** — segment networks into zones (cell, line, site DMZ, enterprise) connected only by explicitly approved conduits with inspection. The OT/IT DMZ (historically Purdue Level 3.5) is the controlled bridge.
- **Edge-first** — push data collection, normalization, and low-latency analytics to edge gateways near machines; send only needed data to the cloud.
- **One-way data flow** for monitoring where possible; bidirectional only where control is required and hardened.
- **Separate identities and change control** for OT vs IT, unified by governance.

### OPC UA and MQTT Protocols

- **OPC UA (IEC 62541)** — the standard for secure, platform-independent industrial data exchange. It defines an **information model** (objects with type, attributes, methods) and built-in security (authentication, authorization, encryption). It is the preferred northbound protocol for normalized machine data. Use OPC UA with security enabled (Sign & Encrypt) and mutual TLS.
- **MQTT** — a lightweight publish/subscribe protocol ideal for edge-to-cloud messaging at scale. **Sparkplug B** defines a payload and state-management spec on top of MQTT for industrial use (birth/death certificates, automatic tag discovery). Use MQTT/Sparkplug B for scalable edge-to-platform telemetry.

Typical pattern: legacy protocols (Modbus, Profinet, EtherNet/IP) are **bridged at the edge gateway** into OPC UA and/or MQTT/Sparkplug B for northbound consumption. Avoid carrying insecure legacy protocols across the converged network.

### IEC 62443 Cybersecurity Standard

IEC 62443 is the dominant standard for OT/industrial cybersecurity. It is risk-based and defines **zones and conduits**, **security levels (SL)**, and **requirements** across the lifecycle.

- **62443-2-1** — security program requirements for asset owners (operating a security management system).
- **62443-3-2** — security risk assessment (define zones/conduits, target security levels SL-T).
- **62443-3-3** — system security requirements and security levels (what a *system* must provide to reach SL 1–4).
- **62443-4-1 / 4-2** — secure product development and component requirements (vendor/product side).

Most discrete/process manufacturers target **Security Level 2 (SL-T 2)** for protected zones and **SL-T 3** for high-risk/critical infrastructure, with protection against intentional violation using moderate resources. The program should define target security levels per zone and close gaps toward certification for the certified scope.

### Edge vs Cloud Computing in Manufacturing

| Concern | Edge | Cloud |
|---------|------|-------|
| Latency | Very low (ms) — real-time control, operator HMI | Higher — not for safety-critical control |
| Use cases | Protocol bridging, local buffering, vision inference, PdM scoring at source | Data lake, ML training, enterprise analytics, long-term storage, cross-site benchmarking |
| Connectivity dependency | Continues operating offline | Dependent on link; use store-and-forward |
| Cost model | Capital (hardware) | Operating (subscription/consumption) |

**Design principle:** put low-latency and safety-relevant workloads on the edge; put data-intensive training and enterprise analytics in the cloud; bridge with buffering so cloud outages do not break operations.

### MES, SCADA, PLC Roles

- **PLC (Programmable Logic Controller)** — the L1 controller executing real-time logic on a machine/cell.
- **SCADA / HMI (L2)** — supervises and visualizes plant/line operation; coordinates PLCs; the operator's window into the process.
- **MES (Manufacturing Execution System) (L3)** — manages execution: production orders, dispatch, equipment status, batch records, traceability, and OEE; the bridge between ERP orders and shop-floor execution.
- **ERP (L4)** — enterprise business processes (orders, finance, supply chain).

Integration targets: machine data → historian/lake; MES for orders/status/batch; QMS for quality/defects; WMS for material; ERP for business context.

### Digital Twin Maturity Levels

1. **Descriptive** — a 3D/structural model showing the asset/line.
2. **Informational** — model enriched with real-time and historical data (live dashboards).
3. **Predictive** — model uses analytics to forecast behavior/failures.
4. **Prescriptive / Living** — model recommends or drives actions, and is continuously updated from live data; used for what-if simulation and closed-loop optimization.

Start at level 1–2 for the pilot line and evolve toward level 4 only after data quality and model trust are established.

### OEE Calculation Methodology

**OEE = Availability × Performance × Quality**, each a ratio of actual to ideal:

- **Availability = Run Time / Planned Production Time** (accounts for downtime losses).
- **Performance = (Ideal Cycle Time × Total Count) / Run Time** (accounts for speed losses).
- **Quality = Good Count / Total Count** (accounts for quality losses).

World-class OEE is ~85%; most plants start at 50–65%. OEE is the single most important operational KPI and must be defined consistently (ideal cycle time, planned time, what counts as "good") and reconciled against MES. Always baseline before instrumenting so gains are credible.

---

## Typical Client Personas

- **Plant Manager** — *cares about throughput, OEE, downtime, and on-time delivery.* Speak in terms of units/shift, line availability, and lost-production cost. Wins: real-time visibility and faster problem resolution.
- **CIO / Head of IT** — *cares about security, architecture, integration, and scalability.* Speak in terms of IEC 62443, IT/OT governance, platform scalability, and total cost of ownership. Wins: a coherent, secure, maintainable architecture.
- **Quality Head** — *cares about yield, defect rate, traceability, and CAPA.* Speak in terms of first-pass yield, defect Pareto, genealogy, and recall risk. Wins: closed-loop quality and root-cause diagnostics.
- **CFO** — *cares about ROI, payback period, and cost reduction.* Speak in terms of pilot cost, projected yield/OEE gains, payback, and scaling economics. Wins: quantified, defensible business case.
- **OT / Controls Engineering Lead** — *cares about not breaking production, protocol access, and safe control.* Speak in terms of production windows, non-invasive connections, and safe-state fallback. Wins: improved reliability without disruption.
- **Operators / Supervisors** — *care about usable tools and not being overloaded.* Speak in terms of simpler workflows, fewer surprises, and reduced burden. Wins: dashboards and alerts that actually help.

---

## Engagement Phases Reference

- **Phase 0 — Strategic Framing (Weeks 1–4):** Charter, stakeholders, the 10-dimension readiness diagnostic, business case, target operating model, RFP prep, and PMO setup. This phase sets scope, governance, and the financial case that funds everything else.
- **Phase 1 — Site Assessment & OT Discovery (Weeks 5–8):** Asset inventory, OT/IT audit, connectivity survey, sensor gap analysis, protocol capture, ISA-95 data model, OT security baseline, and process mapping. This is where brownfield reality is discovered; do not skimp here.
- **Phase 2 — Solution Architecture (Weeks 9–14):** Edge/cloud architecture, converged network design, IEC 62443 security blueprint, data platform architecture, MES/QMS integration design, technology selection, and architecture review board sign-off.
- **Phase 3 — Technology Procurement (Weeks 15–20):** RFPs, vendor selection, and procurement of edge gateways, sensors, security appliances, historian/platform licenses, edge compute/GPU, vision systems, and the system integrator. Mind long lead times and customs.
- **Phase 4 — Network & IT/OT Infrastructure (Weeks 21–28):** Cabling, VLAN segmentation, DMZ/firewalls, edge gateway commissioning, protocol bridging, sensor install, edge compute, time sync, and segmentation validation. The connectivity foundation for everything above.
- **Phase 5 — IIoT, Data Platform & Visibility (Weeks 29–40):** Historian, data lake, pipelines, control tower dashboards, MES/QMS/WMS integration, end-to-end traceability, data quality, and UAT with operations. This is where leadership first sees value.
- **Phase 6 — Analytics, AI & Optimization (Weeks 41–56):** Computer vision defect detection, predictive maintenance, yield/root-cause analytics, digital twin, closed-loop control, MLOps, and pilot ROI validation. Value compounds here but depends entirely on Phases 4–5.
- **Phase 7 — Operations Handover & Continuous Improvement (Weeks 57–64):** Training, SOP handover, continuous improvement framework, quarterly ROI reviews, IEC 62443 maturity progression, workforce upskilling, governance, and the scale-out roadmap.

---

## Common Pitfalls

1. **Starting with analytics before connectivity.** Models need reliable, contextualized data. Skipping the connectivity and data foundation guarantees poor models and eroded trust. *Data must come first.*
2. **Ignoring OT security until production is affected.** Converging networks without IEC 62443 segmentation creates ransomware exposure that can halt production. Bake security in from Phase 1–2, not after an incident.
3. **Vendor lock-in through proprietary protocols.** Accepting closed formats and connectors inflates cost and blocks scaling. Mandate OPC UA, MQTT/Sparkplug B, and open APIs in procurement.
4. **Underinvesting in change management and training.** Brilliant dashboards that operators ignore deliver zero value. Co-design with the floor, train role-by-role, and show quick wins.
5. **Trying to digitize broken processes instead of redesigning them.** Digitizing waste makes waste run faster. Fix and standardize the process first, then instrument and optimize it.
6. **Pilot that cannot scale.** A bespoke pilot with no path to replication burns money. Design the pilot as a repeatable pattern from day one.

---

## Related Pack Artifacts

- `wbs_template.json` — 92 tasks across the 8 phases above.
- `risk_register.json` — 41 risks across OT integration, cybersecurity, data, vendor, scaling, and commercial categories.
- `kpi_definitions.json` — 26 KPIs across operational, maintenance, data, AI/ML, and cybersecurity dimensions.
- `monitoring_rules.json` — 28 rules for edge, pipeline, production, ML, and security monitoring.
- `procurement_checklist.json` — 11 procurement packages for hardware, platforms, and services.
- `commissioning_checklist.json` — 22 go-live checks across network, edge, platform, and security.
- `playbook.md` — how to run an Industry 4.0 engagement end-to-end.

> **Disclaimer:** This context is a PMO/domain reference for smart manufacturing engagements. Must be reviewed by qualified OT, IT, data, and AI engineering professionals before application to a real client engagement. Agent outputs are for planning, monitoring, and alert assistance only, not for operational decision-making or safety-critical actions.
