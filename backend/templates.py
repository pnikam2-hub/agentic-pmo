"""Project templates for green fuel and manufacturing.

Each template provides:
- name, description, goal (used by Plan Agent)
- suggested_phases: list of phase dicts with tasks
- tags: auto-applied to the project
- estimated_duration: rough timeline hint

Templates are used to pre-populate projects and give the Plan Agent
a running start on domain-specific workflows.
"""

GREEN_FUEL_TEMPLATES = [
    # ── 1. Green Methanol ────────────────────────────────────────────────
    {
        "id": "green-methanol",
        "name": "Green Methanol Plant",
        "category": "green-fuel",
        "description": "End-to-end project for a green methanol production facility using captured CO₂ and green hydrogen via catalytic hydrogenation.",
        "goal": "Design, build, and commission a green methanol production facility. Scope covers feedstock preprocessing (CO₂ capture + H₂ electrolysis), catalytic reactor design, methanol distillation/purification, storage, quality control, and offtake logistics.",
        "tags": ["green-fuel", "methanol", "hydrogen", "EPC", "chemical-processing"],
        "estimated_duration": "18-24 months",
        "suggested_phases": [
            {
                "name": "Phase 1: Feasibility & FEL",
                "tasks": [
                    {"title": "Feedstock availability study (CO₂ + H₂ sources)", "estimated_hours": 120, "priority": "high"},
                    {"title": "Site selection & geotechnical survey", "estimated_hours": 80, "priority": "high"},
                    {"title": "Technology licensor evaluation & selection", "estimated_hours": 100, "priority": "critical"},
                    {"title": "Preliminary mass & energy balance", "estimated_hours": 60, "priority": "high"},
                    {"title": "CAPEX/OPEX estimate (Class 5)", "estimated_hours": 80, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 2: Basic Engineering",
                "tasks": [
                    {"title": "Process flow diagrams (PFD) & P&IDs", "estimated_hours": 200, "priority": "critical"},
                    {"title": "Reactor sizing & catalyst selection", "estimated_hours": 120, "priority": "critical"},
                    {"title": "Heat integration & utility design", "estimated_hours": 100, "priority": "high"},
                    {"title": "H2 supply system design (electrolyzer interface)", "estimated_hours": 80, "priority": "high"},
                    {"title": "CO₂ capture unit design spec", "estimated_hours": 60, "priority": "high"},
                    {"title": "Distillation column design & specification", "estimated_hours": 80, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 3: Detailed Engineering & Procurement",
                "tasks": [
                    {"title": "Long-lead equipment procurement (reactor, columns)", "estimated_hours": 160, "priority": "critical"},
                    {"title": "Instrumentation & control system design", "estimated_hours": 120, "priority": "high"},
                    {"title": "Structural & civil engineering drawings", "estimated_hours": 160, "priority": "high"},
                    {"title": "Electrical & piping isometrics", "estimated_hours": 140, "priority": "medium"},
                    {"title": "Vendor document review & approval", "estimated_hours": 100, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 4: Construction & Commissioning",
                "tasks": [
                    {"title": "Site preparation & foundation work", "estimated_hours": 200, "priority": "critical"},
                    {"title": "Equipment installation & alignment", "estimated_hours": 240, "priority": "critical"},
                    {"title": "Piping & electrical installation", "estimated_hours": 200, "priority": "high"},
                    {"title": "Pre-commissioning: leak test, loop check, flush", "estimated_hours": 120, "priority": "high"},
                    {"title": "Catalyst loading & reactor commissioning", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Performance test run & product certification", "estimated_hours": 100, "priority": "critical"},
                ]
            },
        ],
    },

    # ── 2. DME (Dimethyl Ether) ──────────────────────────────────────────
    {
        "id": "dme",
        "name": "DME Production Facility",
        "category": "green-fuel",
        "description": "Project for a renewable DME production plant via methanol dehydration or direct CO₂ hydrogenation route.",
        "goal": "Develop a DME production facility as a clean-burning fuel alternative for industrial heating and transportation. Covers feedstock integration, dehydration reactor, storage (pressurized), and distribution.",
        "tags": ["green-fuel", "DME", "chemical-processing", "low-carbon-fuel"],
        "estimated_duration": "16-22 months",
        "suggested_phases": [
            {
                "name": "Phase 1: Concept & Licencing",
                "tasks": [
                    {"title": "Technology route selection (methanol dehydration vs direct synthesis)", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Feedstock methanol supply agreement", "estimated_hours": 60, "priority": "high"},
                    {"title": "Environmental & safety permit scoping", "estimated_hours": 80, "priority": "high"},
                    {"title": "Project economics & market analysis", "estimated_hours": 60, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 2: Engineering",
                "tasks": [
                    {"title": "Dehydration reactor design & catalyst selection", "estimated_hours": 120, "priority": "critical"},
                    {"title": "DME purification & compression system", "estimated_hours": 100, "priority": "high"},
                    {"title": "Pressurized storage tank specification", "estimated_hours": 60, "priority": "high"},
                    {"title": "Loading/unloading & truck bay design", "estimated_hours": 40, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 3: Construction",
                "tasks": [
                    {"title": "Reactor vessel procurement & installation", "estimated_hours": 160, "priority": "critical"},
                    {"title": "Compressor & utility installation", "estimated_hours": 120, "priority": "high"},
                    {"title": "Storage tank fabrication & hydrotest", "estimated_hours": 100, "priority": "high"},
                    {"title": "Safety system (flare, ESD, gas detection) installation", "estimated_hours": 80, "priority": "critical"},
                ]
            },
        ],
    },

    # ── 3. SAF (Sustainable Aviation Fuel) ────────────────────────────────
    {
        "id": "saf",
        "name": "SAF Production (HEFA/ATJ)",
        "category": "green-fuel",
        "description": "Sustainable Aviation Fuel plant using HEFA (Hydroprocessed Esters and Fatty Acids) or ATJ (Alcohol-to-Jet) pathway.",
        "goal": "Design and build a SAF production facility. Covers feedstock pre-treatment (used cooking oil/fats), hydroprocessing, isomerization/hydrocracking, distillation, blending, and ASTM certification for D7566/D1655 compliance.",
        "tags": ["green-fuel", "SAF", "aviation", "HEFA", "renewable-fuel"],
        "estimated_duration": "20-28 months",
        "suggested_phases": [
            {
                "name": "Phase 1: Feedstock & Technology",
                "tasks": [
                    {"title": "Feedstock supply chain assessment (UCO, tallow, vegetable oils)", "estimated_hours": 100, "priority": "high"},
                    {"title": "HEFA/ATJ technology licensor evaluation", "estimated_hours": 120, "priority": "critical"},
                    {"title": "ASTM D7566 certification pathway planning", "estimated_hours": 60, "priority": "critical"},
                    {"title": "Co-product management (renewable diesel, naphtha)", "estimated_hours": 40, "priority": "medium"},
                    {"title": "Blending & logistics for airport delivery", "estimated_hours": 60, "priority": "high"},
                ]
            },
            {
                "name": "Phase 2: Process Design",
                "tasks": [
                    {"title": "Feedstock pre-treatment unit design (degumming, bleaching)", "estimated_hours": 100, "priority": "high"},
                    {"title": "Hydroprocessing reactor design (HDO + isomerization)", "estimated_hours": 160, "priority": "critical"},
                    {"title": "Hydrogen supply & recovery system", "estimated_hours": 100, "priority": "high"},
                    {"title": "Fractionation & distillation train design", "estimated_hours": 80, "priority": "medium"},
                    {"title": "Wastewater & spent catalyst handling", "estimated_hours": 60, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 3: Execution",
                "tasks": [
                    {"title": "FEL-3 cost estimate & funding approval", "estimated_hours": 100, "priority": "critical"},
                    {"title": "EPC contractor selection & award", "estimated_hours": 80, "priority": "high"},
                    {"title": "Construction: hydroprocessing unit", "estimated_hours": 300, "priority": "critical"},
                    {"title": "Construction: pre-treatment & fractionation", "estimated_hours": 200, "priority": "high"},
                    {"title": "Commissioning: cold/hot oil circulation, catalyst activation", "estimated_hours": 160, "priority": "critical"},
                    {"title": "Certification run & ASTM fuel sampling", "estimated_hours": 80, "priority": "critical"},
                ]
            },
        ],
    },

    # ── 4. Green Hydrogen ────────────────────────────────────────────────
    {
        "id": "green-hydrogen",
        "name": "Green Hydrogen Production (Electrolysis)",
        "category": "green-fuel",
        "description": "Green hydrogen production facility using PEM or alkaline electrolysis powered by renewable energy.",
        "goal": "Develop a green hydrogen production facility with grid-connected or behind-the-meter renewable power. Scope includes electrolyser system design, water treatment, compression, storage (Type IV or salt cavern), and pipeline/gaseous offtake infrastructure.",
        "tags": ["green-fuel", "hydrogen", "electrolysis", "renewable-energy", "decarbonization"],
        "estimated_duration": "14-20 months",
        "suggested_phases": [
            {
                "name": "Phase 1: Pre-FEED",
                "tasks": [
                    {"title": "Renewable power sourcing & PPA negotiation", "estimated_hours": 100, "priority": "critical"},
                    {"title": "Electrolyser technology selection (PEM vs Alkaline vs AEM)", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Water source & treatment assessment", "estimated_hours": 40, "priority": "high"},
                    {"title": "Site layout & environmental screening", "estimated_hours": 60, "priority": "medium"},
                    {"title": "Green hydrogen certification scheme registration", "estimated_hours": 40, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 2: FEED & Procurement",
                "tasks": [
                    {"title": "Electrolyser system design package", "estimated_hours": 160, "priority": "critical"},
                    {"title": "Compression & drying system design", "estimated_hours": 100, "priority": "high"},
                    {"title": "Storage system design (Type IV vessels or cavern)", "estimated_hours": 80, "priority": "high"},
                    {"title": "Balance of plant: cooling, power, water treatment", "estimated_hours": 120, "priority": "high"},
                    {"title": "Long-lead equipment procurement (electrolyser stack)", "estimated_hours": 60, "priority": "critical"},
                    {"title": "Grid interconnection application", "estimated_hours": 80, "priority": "high"},
                ]
            },
            {
                "name": "Phase 3: Construction & Start-up",
                "tasks": [
                    {"title": "Civil works & foundation for electrolyser hall", "estimated_hours": 160, "priority": "critical"},
                    {"title": "Electrolyser & BOP installation", "estimated_hours": 200, "priority": "critical"},
                    {"title": "Compression & storage installation", "estimated_hours": 120, "priority": "high"},
                    {"title": "H2 piping, valves, and safety system installation", "estimated_hours": 100, "priority": "critical"},
                    {"title": "Leak test, dry-out, and system purge", "estimated_hours": 60, "priority": "high"},
                    {"title": "Electrolyser stack activation & performance ramp", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Green H2 certification audit & first production", "estimated_hours": 60, "priority": "critical"},
                ]
            },
        ],
    },

    # ── 5. Commissioning ──────────────────────────────────────────────────
    {
        "id": "commissioning",
        "name": "Industrial Plant Commissioning",
        "category": "manufacturing",
        "description": "Pre-commissioning, commissioning, and start-up of a process/manufacturing plant.",
        "goal": "Systematic commissioning plan covering pre-commissioning checks, system turnover, loop checks, flushing, leak testing, catalyst loading, chemical cleaning, first firing, performance testing, and handover to operations.",
        "tags": ["manufacturing", "commissioning", "start-up", "EPC", "handover"],
        "estimated_duration": "4-8 months",
        "suggested_phases": [
            {
                "name": "Phase 1: Commissioning Planning",
                "tasks": [
                    {"title": "Develop commissioning & start-up philosophy", "estimated_hours": 60, "priority": "high"},
                    {"title": "System/sub-system breakdown & turnover package creation", "estimated_hours": 100, "priority": "critical"},
                    {"title": "Commissioning team mobilization & training", "estimated_hours": 60, "priority": "high"},
                    {"title": "Commissioning schedule & milestone integration", "estimated_hours": 40, "priority": "medium"},
                    {"title": "Safety review: PTW, SIMOPS, HAZOP close-out", "estimated_hours": 80, "priority": "critical"},
                ]
            },
            {
                "name": "Phase 2: Pre-Commissioning",
                "tasks": [
                    {"title": "Hydrostatic/pneumatic leak testing of pressure systems", "estimated_hours": 200, "priority": "critical"},
                    {"title": "Instrument loop checks & DCS signal verification", "estimated_hours": 160, "priority": "high"},
                    {"title": "Flushing & chemical cleaning of piping systems", "estimated_hours": 120, "priority": "high"},
                    {"title": "Electrical: megger testing, motor bump, rotation check", "estimated_hours": 80, "priority": "high"},
                    {"title": "Mechanical run-in for rotating equipment", "estimated_hours": 100, "priority": "critical"},
                ]
            },
            {
                "name": "Phase 3: Start-up & Performance Test",
                "tasks": [
                    {"title": "System turnover & responsibility transfer", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Feedstock/utility introduction", "estimated_hours": 60, "priority": "critical"},
                    {"title": "Catalyst loading & activation (if applicable)", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Gradual system ramp-up to design conditions", "estimated_hours": 160, "priority": "critical"},
                    {"title": "72-hour performance guarantee test run", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Punch list close-out & final handover to operations", "estimated_hours": 60, "priority": "high"},
                ]
            },
        ],
    },

    # ── 6. Offtake & Commercial ──────────────────────────────────────────
    {
        "id": "offtake",
        "name": "Offtake & Commercial Structuring",
        "category": "commercial",
        "description": "Offtake agreement structuring, pricing model, logistics, and contracting for green fuel products.",
        "goal": "Develop and execute offtake strategy for green fuel products (methanol, SAF, H2, DME). Includes market analysis, offtake term sheets, pricing models (fixed/floors/index), logistics design, credit assessment, and contract negotiation.",
        "tags": ["commercial", "offtake", "contracting", "green-fuel", "logistics"],
        "estimated_duration": "3-6 months",
        "suggested_phases": [
            {
                "name": "Phase 1: Market Analysis",
                "tasks": [
                    {"title": "Green fuel demand assessment (domestic + export)", "estimated_hours": 60, "priority": "high"},
                    {"title": "Competitor benchmarking & price discovery", "estimated_hours": 40, "priority": "high"},
                    {"title": "Regulatory framework review (blending mandates, subsidies)", "estimated_hours": 40, "priority": "medium"},
                    {"title": "Counterparty identification & pre-qualification", "estimated_hours": 60, "priority": "critical"},
                ]
            },
            {
                "name": "Phase 2: Contracting",
                "tasks": [
                    {"title": "Term sheet development (volume, tenure, pricing mechanism)", "estimated_hours": 60, "priority": "critical"},
                    {"title": "Offtake agreement drafting (GTC + schedule)", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Credit assessment & security package negotiation", "estimated_hours": 40, "priority": "high"},
                    {"title": "Logistics & delivery terms (FOB/CIF / ex-works)", "estimated_hours": 40, "priority": "medium"},
                    {"title": "Force majeure & risk allocation review", "estimated_hours": 30, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 3: Closure",
                "tasks": [
                    {"title": "Board approval & signing", "estimated_hours": 40, "priority": "critical"},
                    {"title": "Credit support / LC establishment", "estimated_hours": 40, "priority": "high"},
                    {"title": "Logistics service provider appointment", "estimated_hours": 30, "priority": "medium"},
                    {"title": "First lifting planning & scheduling", "estimated_hours": 30, "priority": "high"},
                ]
            },
        ],
    },

    # ── 7. Safety (HSE) ──────────────────────────────────────────────────
    {
        "id": "safety",
        "name": "Process Safety & HSE Management",
        "category": "manufacturing",
        "description": "Comprehensive process safety and HSE programme for green fuel/manufacturing facilities.",
        "goal": "Develop and implement a Process Safety Management (PSM) and HSE programme covering HAZID/HAZOP, SIL/LOPA assessment, safety case development, emergency response planning, permit-to-work systems, and regulatory compliance (OSHA PSM / ISG Model Code / Indian Factories Act).",
        "tags": ["safety", "HSE", "process-safety", "compliance", "PSM"],
        "estimated_duration": "4-8 months (ongoing)",
        "suggested_phases": [
            {
                "name": "Phase 1: Hazard Assessment",
                "tasks": [
                    {"title": "HAZID (Hazard Identification) workshop", "estimated_hours": 60, "priority": "critical"},
                    {"title": "HAZOP study for all major process units", "estimated_hours": 200, "priority": "critical"},
                    {"title": "SIL/LOPA assignment for safety instrumented functions", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Quantitative risk assessment (QRA)", "estimated_hours": 100, "priority": "high"},
                    {"title": "Consequence modelling (dispersion, BLEVE, VCE)", "estimated_hours": 80, "priority": "high"},
                ]
            },
            {
                "name": "Phase 2: Safety Systems",
                "tasks": [
                    {"title": "Safety case development & ALARP demonstration", "estimated_hours": 160, "priority": "critical"},
                    {"title": "ESD & fire & gas system design basis", "estimated_hours": 100, "priority": "critical"},
                    {"title": "Flare / relief system sizing & design", "estimated_hours": 80, "priority": "high"},
                    {"title": "Active/passive fire protection design", "estimated_hours": 80, "priority": "high"},
                    {"title": "H2/flammable gas detection layout optimisation", "estimated_hours": 40, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 3: Operational Safety",
                "tasks": [
                    {"title": "Permit-to-work (PTW) system implementation", "estimated_hours": 60, "priority": "critical"},
                    {"title": "Emergency response plan (ERP) & drill schedule", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Management of change (MOC) procedure", "estimated_hours": 40, "priority": "high"},
                    {"title": "HSE training matrix & competency assurance", "estimated_hours": 60, "priority": "medium"},
                    {"title": "Regulatory dossier submission (Factory Inspectorate/PCB)", "estimated_hours": 80, "priority": "high"},
                ]
            },
        ],
    },

    # ── 8. Permits & Regulatory ──────────────────────────────────────────
    {
        "id": "permits",
        "name": "Environmental & Regulatory Permitting",
        "category": "manufacturing",
        "description": "Permitting pathway for green fuel / chemical processing facilities.",
        "goal": "Secure all environmental and regulatory permits required for construction and operation: EIA, EC, CTE, CTO, PESO, Factory Licence, building approval, fire NOC, and hazardous waste authorisation.",
        "tags": ["permits", "regulatory", "compliance", "EPC", "environmental"],
        "estimated_duration": "6-12 months (overlaps with EPC)",
        "suggested_phases": [
            {
                "name": "Phase 1: Environmental Clearance",
                "tasks": [
                    {"title": "Environmental Impact Assessment (EIA) scoping", "estimated_hours": 60, "priority": "critical"},
                    {"title": "Baseline data collection (air, water, soil, noise, ecology)", "estimated_hours": 120, "priority": "high"},
                    {"title": "EIA report preparation & public hearing", "estimated_hours": 200, "priority": "critical"},
                    {"title": "Environment Clearance (EC) application to MoEFCC/SEIAA", "estimated_hours": 80, "priority": "critical"},
                ]
            },
            {
                "name": "Phase 2: Consents & Licences",
                "tasks": [
                    {"title": "Consent to Establish (CTE) from State PCB", "estimated_hours": 60, "priority": "critical"},
                    {"title": "PESO licence for hazardous chemical storage & processing", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Factory Licence approval from Chief Inspector of Factories", "estimated_hours": 60, "priority": "high"},
                    {"title": "Fire NOC from State Fire Services", "estimated_hours": 40, "priority": "high"},
                    {"title": "Building plan approval from local municipal authority", "estimated_hours": 60, "priority": "high"},
                    {"title": "Explosives licence (if applicable — H2 storage, etc.)", "estimated_hours": 60, "priority": "critical"},
                ]
            },
            {
                "name": "Phase 3: Operational Compliance",
                "tasks": [
                    {"title": "Consent to Operate (CTO) submission", "estimated_hours": 40, "priority": "critical"},
                    {"title": "Hazardous waste authorisation & disposal tie-up", "estimated_hours": 40, "priority": "high"},
                    {"title": "Environmental compliance report & CGWA clearance", "estimated_hours": 40, "priority": "medium"},
                    {"title": "Public liability insurance policy placement", "estimated_hours": 20, "priority": "medium"},
                ]
            },
        ],
    },

    # ── 9. EPC ───────────────────────────────────────────────────────────
    {
        "id": "epc",
        "name": "EPC Project — Full Lifecycle",
        "category": "manufacturing",
        "description": "Greenfield Engineering, Procurement, and Construction project for a process/manufacturing facility.",
        "goal": "Full EPC lifecycle: FEL/basic engineering → detailed design → procurement & fabrication → construction → pre-commissioning → commissioning → performance testing → handover. Includes project controls, quality assurance, HSE, and contract administration.",
        "tags": ["manufacturing", "EPC", "project-delivery", "construction", "engineering"],
        "estimated_duration": "24-36 months",
        "suggested_phases": [
            {
                "name": "Phase 1: Front-End Loading (FEL)",
                "tasks": [
                    {"title": "FEL-1: Feasibility study & technology selection", "estimated_hours": 160, "priority": "critical"},
                    {"title": "FEL-2: Conceptual design & Class 4 cost estimate", "estimated_hours": 240, "priority": "critical"},
                    {"title": "FEL-3: Detailed scope definition & funding approval package", "estimated_hours": 200, "priority": "critical"},
                    {"title": "EPC contract strategy (lump sum / reimbursable / EPCM)", "estimated_hours": 80, "priority": "high"},
                    {"title": "Long-lead equipment enquiry & quotation (LEE list)", "estimated_hours": 60, "priority": "high"},
                ]
            },
            {
                "name": "Phase 2: Detailed Engineering",
                "tasks": [
                    {"title": "Process design package (PFDs, P&IDs, line list, valve list)", "estimated_hours": 300, "priority": "critical"},
                    {"title": "Civil/structural design & foundation drawings", "estimated_hours": 240, "priority": "high"},
                    {"title": "Mechanical equipment & package unit specs", "estimated_hours": 200, "priority": "high"},
                    {"title": "Electrical: SLD, schematics, cable schedule, lighting", "estimated_hours": 160, "priority": "high"},
                    {"title": "Instrumentation & control: IO list, DCS architecture, logic diagrams", "estimated_hours": 160, "priority": "high"},
                    {"title": "3D model review & clash detection", "estimated_hours": 120, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 3: Procurement & Fabrication",
                "tasks": [
                    {"title": "Reactor/pressure vessel fabrication ITB & award", "estimated_hours": 160, "priority": "critical"},
                    {"title": "Rotating equipment (compressors, pumps, fans) procurement", "estimated_hours": 120, "priority": "high"},
                    {"title": "Bulk materials: piping, cable, structural steel procurement", "estimated_hours": 100, "priority": "high"},
                    {"title": "Package equipment: DCS, analysers, water treatment, flare", "estimated_hours": 80, "priority": "high"},
                    {"title": "Expediting, inspection & vendor document management", "estimated_hours": 160, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 4: Construction",
                "tasks": [
                    {"title": "Site mobilisation, temporary facilities, laydown area", "estimated_hours": 80, "priority": "critical"},
                    {"title": "Civil: earthworks, foundations, paving, drainage", "estimated_hours": 320, "priority": "critical"},
                    {"title": "Structural steel erection & cladding", "estimated_hours": 240, "priority": "high"},
                    {"title": "Mechanical equipment setting & alignment", "estimated_hours": 200, "priority": "critical"},
                    {"title": "Piping fabrication & erection (shop + field)", "estimated_hours": 300, "priority": "high"},
                    {"title": "Electrical & instrumentation installation", "estimated_hours": 240, "priority": "high"},
                    {"title": "Insulation, painting, fireproofing", "estimated_hours": 100, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 5: Commissioning & Handover",
                "tasks": [
                    {"title": "Mechanical completion & system walk-down", "estimated_hours": 120, "priority": "critical"},
                    {"title": "Pre-commissioning: flush, leak test, loop check, megger", "estimated_hours": 200, "priority": "critical"},
                    {"title": "Commissioning & start-up sequence execution", "estimated_hours": 240, "priority": "critical"},
                    {"title": "Performance guarantee test run", "estimated_hours": 100, "priority": "critical"},
                    {"title": "Punch-list closeout, as-built handover, O&M manuals", "estimated_hours": 120, "priority": "high"},
                    {"title": "Project close-out: cost report, lessons learned, asset register", "estimated_hours": 60, "priority": "medium"},
                ]
            },
        ],
    },

    # ── 10. Procurement ──────────────────────────────────────────────────
    {
        "id": "procurement",
        "name": "Capital Procurement (EPC/Industrial)",
        "category": "manufacturing",
        "description": "Strategic procurement for capital equipment and EPC packages in green fuel / process manufacturing.",
        "goal": "Execute procurement strategy covering ITB preparation, bid evaluation, vendor qualification, commercial negotiation, expediting, logistics, and warehouse receipt for critical process equipment, bulk materials, and package units.",
        "tags": ["manufacturing", "procurement", "supply-chain", "EPC", "logistics"],
        "estimated_duration": "6-14 months (overlaps with project)",
        "suggested_phases": [
            {
                "name": "Phase 1: Strategy",
                "tasks": [
                    {"title": "Procurement strategy & contracting plan", "estimated_hours": 60, "priority": "critical"},
                    {"title": "Vendor pre-qualification & long-list development", "estimated_hours": 80, "priority": "high"},
                    {"title": "Long-lead equipment identification & ordering timeline", "estimated_hours": 40, "priority": "critical"},
                    {"title": "Make vs buy analysis for non-standard items", "estimated_hours": 40, "priority": "medium"},
                ]
            },
            {
                "name": "Phase 2: Tendering",
                "tasks": [
                    {"title": "ITT/ITB package preparation (technical + commercial)", "estimated_hours": 120, "priority": "critical"},
                    {"title": "Bid evaluation: technical compliance + commercial comparison", "estimated_hours": 100, "priority": "critical"},
                    {"title": "Vendor clarification meetings & BAFO rounds", "estimated_hours": 60, "priority": "high"},
                    {"title": "Commercial negotiation & PO/contract award", "estimated_hours": 80, "priority": "high"},
                ]
            },
            {
                "name": "Phase 3: Execution",
                "tasks": [
                    {"title": "Vendor document review & approval schedule", "estimated_hours": 80, "priority": "high"},
                    {"title": "Expediting plan & factory inspection visits", "estimated_hours": 100, "priority": "high"},
                    {"title": "Logistics: shipping, customs clearance, transport arrangement", "estimated_hours": 80, "priority": "high"},
                    {"title": "Warehouse receipt, preservation, and inventory management", "estimated_hours": 60, "priority": "medium"},
                    {"title": "Warranty & performance guarantee tracking", "estimated_hours": 40, "priority": "medium"},
                ]
            },
        ],
    },
]
