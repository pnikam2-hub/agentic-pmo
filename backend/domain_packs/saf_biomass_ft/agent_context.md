# SAF Biomass Gasification FT — Agent Context

## Process Overview

This domain pack covers a Sustainable Aviation Fuel (SAF) production facility using the biomass gasification + Fischer-Tropsch (FT) synthesis pathway (ASTM D7566 Annex A1 — FT-SPK).

Core process steps:
1. **Biomass handling & pre-treatment**: Drying (<15-20% moisture), sizing, screening, blending
2. **Gasification**: Converts biomass to raw syngas (CO, H2, CO2, CH4, tars, particulates, ash, sulfur, chlorine, alkali metals, nitrogen)
3. **Syngas cleanup & conditioning**: Particulate removal → tar reforming/cracking → acid gas removal (H2S, COS, HCl) → guard beds → H2/CO ratio adjustment (WGS or membrane)
4. **Fischer-Tropsch synthesis**: Converts cleaned syngas to paraffinic hydrocarbons over Co or Fe catalyst; slurry bubble column or fixed bed reactor
5. **Hydrocracking/isomerization**: Cracks FT wax to jet-range hydrocarbons; improves cold-flow properties
6. **Product fractionation**: Separates naphtha, jet-range SAF, diesel, wax/heavy products, offgas, and water
7. **ASTM D7566 Annex A1 qualification**: Fuel must satisfy FT-SPK specification before blending up to 50% v/v with Jet A-1
8. **Sustainability certification**: CORSIA, ISCC, RSB, or local equivalent — chain-of-custody documentation
9. **Offtake & blending**: Fuel quality assurance, blending logistics, airport fuel terminal coordination

**Key contamination limits**: FT catalyst (especially cobalt) requires sulfur <10 ppbv, chlorine <10 ppbv. Syngas cleanup is mission-critical.

---

## Plan Agent — Must Flag Missing

When creating or evaluating a project plan, flag if any of the following are missing:

- **Feedstock**: availability and seasonality assessment; moisture/ash/contaminant management strategy; supply agreement framework
- **Gasification**: technology selection (fluidised bed, entrained flow, indirect); oxidant selection (air/oxygen/steam); gasifier performance targets (cold gas efficiency, carbon conversion)
- **Syngas cleanup**: performance targets for each step (particulate removal spec, tar reformer outlet, sulfur/chlorine outlet spec); cleanup train configuration
- **FT synthesis**: catalyst selection (cobalt vs iron); reactor type (slurry bubble column, fixed bed, microchannel); conversion and selectivity targets
- **H2/CO ratio**: syngas conditioning design basis; WGS or membrane sizing; H2 make-up strategy
- **Hydroprocessing**: hydrocracker/isomerization package; catalyst type; jet yield target; cold-flow property targets
- **Product fractionation**: fractionation scheme (naphtha, jet, diesel, wax); product quality specs
- **ASTM D7566**: FT-SPK qualification route; required fuel property testing plan (freeze point, flash point, density, T90/T95, aromatics, JFTOT)
- **Sustainability certification**: CORSIA / ISCC / RSB scheme selection; lifecycle carbon intensity calculation; chain-of-custody documentation system
- **HAZID/HAZOP/LOPA**: schedule aligned with FEED completion
- **Commissioning**: system turnover plan; catalyst loading and activation procedure; performance test run plan
- **Offtake**: blending logistics; airport fuel terminal interface; offtake agreement; chain-of-custody documentation

---

## Monitor Agent — Must Flag

When monitoring a SAF biomass FT project, flag these conditions:

- **Feedstock**: contracts not secured by pre-FEED gate; feedstock moisture or ash consistently outside design basis
- **Gasification**: gasifier vendor/license/technology not selected; cold gas efficiency below guarantee
- **Syngas cleanup**: cleanup package procurement delayed; tar/sulfur/chlorine breakthrough
- **H2/CO ratio**: unresolved at FEED stage; syngas conditioning package not spec'd
- **FT synthesis**: FT reactor/catalyst package delayed; catalyst not ordered by early EPC
- **Hydroprocessing**: hydrocracking/isomerization vendor delay; catalyst procurement not started
- **Product fractionation**: fractionation column specification not initiated by EPC
- **ASTM qualification**: qualification plan not started by FEED; fuel property testing not scheduled
- **Sustainability certification**: certification evidence gaps; chain-of-custody documentation not initiated
- **HAZOP**: recommendations not closed before construction start
- **Commissioning**: readiness assessment below threshold; punch list too high near start-up
- **Product quality**: quality test plan not established; specification failures in commissioning runs
- **Offtake**: offtake agreement not signed before commissioning; blending logistics not arranged

---

## Alert Agent — Must Generate Alerts

Generate alerts for the following conditions:

- **Feedstock**: moisture consistently above design limit (>20 wt%); biomass ash/alkali/chlorine/sulfur exceeding gasifier or catalyst limits
- **Gasifier**: vendor delay exceeding 30 days; gasifier performance below guarantee in commissioning
- **Syngas cleanup**: tar breakthrough risk; sulfur or chlorine breakthrough in guard bed effluent
- **H2/CO ratio**: ratio unresolved before FEED close; ratio adjustment system not specified
- **FT catalyst**: procurement or activation delay > 30 days from plan; catalyst performance below target
- **Hydrocracker**: hydrocracking/isomerization package delayed > 30 days
- **ASTM D7566**: qualification documentation missing or incomplete; fuel property testing failures
- **Sustainability certification**: CORSIA/ISCC/RSB chain-of-custody gaps identified; evidence package incomplete
- **SAF product**: failing jet fuel quality tests (freeze point, flash point, density, thermal stability)
- **Commissioning**: punch list items exceeding threshold 30 days before planned start-up
- **Offtake/blending**: logistics not confirmed before first production; blending not tested
- **HAZOP**: overdue recommendations blocking construction or commissioning readiness

---

## Critical Risk Categories

- **Feedstock**: supply reliability, quality variability, price volatility, seasonality
- **Gasification**: technology risk, refractory life, slagging/fouling, carbon conversion
- **Syngas cleanup**: catalyst poisoning from residual contaminants, tar fouling, reliability
- **FT synthesis**: catalyst deactivation (S/Cl poisoning, carbon deposition, attrition), reactor fouling
- **Hydroprocessing**: low jet yield, hydrogen consumption, catalyst deactivation
- **Product quality**: off-specification fuel, blending compatibility, thermal stability
- **ASTM certification**: failure to meet FT-SPK specification, delayed testing, blending waiver issues
- **Sustainability certification**: carbon intensity non-compliance, chain-of-custody audit failure
- **Offtake/commercial**: no offtake agreement, pricing risk, blending logistics failure

---

**Note for agents:** This context is injected into Plan/Monitor/Alert agent prompts when a project has the `domain-pack:saf_biomass_ft` tag. Use the monitoring rules (`monitoring_rules.json`) and risk register (`risk_register.json`) for deterministic checks.

> **Disclaimer:** This context is a PMO/domain reference. Must be reviewed by qualified process engineers, safety professionals, and regulatory experts before application to a real project. The agent outputs are for planning and monitoring assistance only, not for engineering decision-making.
