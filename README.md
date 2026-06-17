# Neurobiological-Fitness Consequence Separation

**Research by [Ana Diez](https://github.com/anadiezmartini),  RFI-IRFOS**

(https://rfi-irfos.github.io/foodchain-analysis/) | [Whitepaper (PDF)](Ana%20Diez%20-%20Neurobiological-Fitness%20Consequence%20Separation.pdf) | [RFI-IRFOS](https://ternlang.com)

---
<img width="1854" height="929" alt="image" src="https://github.com/user-attachments/assets/63c2c9f1-48f9-40c1-9336-6f6742f2bb82" />

## What This Is

The global food system produces **1.64 times the calories needed** to feed every person on Earth. Yet nearly a billion people face chronic hunger. This research asks: *why?*

Ana Diez developed an agent-based model (ABM) that separates the problem into two measurable components:

**Consequence Separation** — the structural gap between what the food system *produces* and what reaches people's *bodies* and *fitness*. The model shows that even under conservative waste and distribution assumptions, the planet operates at a **manufactured scarcity** equilibrium, not a physical one.

Key finding: after accounting for post-harvest loss, processing waste, and access barriers, the effective caloric surplus collapses from 1.64x to approximately 0.94x — tipping just below sufficiency threshold at the aggregate. The scarcity is not thermodynamic. It is organizational.

---

## Repository Structure

```
.
├── index.html                  # Interactive dashboard v2 (live tool)
├── simulation/
│   ├── sim.py                  # ABM simulation v1
│   ├── sim_v2.py               # ABM simulation v2 (production)
│   ├── build_findings.py       # Sobol sensitivity + ABC estimation
│   └── dashboard_v1.html       # Earlier dashboard for comparison
├── figures/
│   ├── Concept Diagram (page 1).png
│   ├── Concept Diagram (page 2).png
│   ├── Figure 2 — Main Simulation Results.png
│   ├── Figure 3 — Sobol Sensitivity Analysis.png
│   ├── Figure 4 — ABC Parameter Estimation.png
│   └── Figure 5 — Validation and Interventions (*.png)
└── Ana Diez - Neurobiological-Fitness Consequence Separation.pdf
```

---

## Using the Tool

The live dashboard runs entirely in your browser. No backend, no signup.

You can:
- Run the simulation with custom parameters
- Explore Sobol sensitivity indices (which variables matter most)
- Trace the surplus-to-scarcity collapse step by step
- Export results as CSV

**To run locally:**
```bash
git clone https://github.com/rfi-irfos/foodchain-analysis.git
cd foodchain-analysis
# Open index.html in any browser. Done.
```

**To run the Python simulation:**
```bash
pip install numpy scipy matplotlib
python simulation/sim_v2.py
```

---

## Running the ABM Yourself

`sim_v2.py` implements the full agent-based model:

- **Agents:** producer nodes, distribution hubs, household consumers
- **Parameters:** waste rate, access barrier coefficient, redistribution capacity
- **Outputs:** caloric surplus at each stage, Gini index of distribution, consequence separation score

The `build_findings.py` script runs Sobol sensitivity analysis and approximate Bayesian computation (ABC) to estimate parameter posteriors from empirical FAO data.

---

## Key Results

| Stage | Surplus Factor |
|---|---|
| Production | 1.64x caloric need |
| After post-harvest loss | 1.41x |
| After processing & transport waste | 1.19x |
| After access barriers | 0.94x |

The model crosses the scarcity threshold **at the access layer**, not at any physical limit. This is the consequence separation: biology and fitness bear a cost manufactured by systemic design, not thermodynamic necessity.

---

## Authors

**Ana Diez** — primary researcher, model design, simulation, findings  
Head of Research & Wellbeing, RFI-IRFOS  
Mendoza, Argentina

**RFI-IRFOS** — research infrastructure, publication, open science commitment  
ZVR 1015608684 | GISA 39261441 | Steuernummer 68 028/0989  
Regulated not-for-profit. Surplus reinvested into research and public tools.

---

## License

This work is released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). You are free to share, adapt, and build on it with attribution.

If you use this work in academic or policy contexts, please cite:

> Diez, A. (2026). *Neurobiological-Fitness Consequence Separation: An Agent-Based Analysis of Structural Food Scarcity*. RFI-IRFOS. https://github.com/rfi-irfos/foodchain-analysis

---

*Published by RFI-IRFOS — ternlang.com*
