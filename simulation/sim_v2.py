#!/usr/bin/env python3
"""
Neurobiological-Fitness Consequence Separation — v2 Extended
Ana Diez (2026) + RFI-IRFOS Distribution Extension

New in v2:
  - Rule 9: Distribution layer (cosmetic waste, supply chain loss, consumer waste)
  - Policy intervention parameter (removes cosmetic standards)
  - Sufficiency proof embedded as a live calculation
  - Hope scenarios: what actually fixes the trajectory

Run:  python3 sim_v2.py
      Browser opens at http://localhost:8766
"""
import numpy as np
import json, threading, webbrowser, math, csv, io
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

PORT = 8766
BASE = Path(__file__).parent
DASH = BASE / "dashboard_v2.html"

EOD_EMPIRICAL = {
    1970:363,1971:360,1972:355,1973:349,1974:352,
    1975:348,1976:339,1977:332,1978:327,1979:319,
    1980:326,1981:326,1982:333,1983:330,1984:323,
    1985:323,1986:316,1987:311,1988:302,1989:296,
    1990:298,1991:298,1992:299,1993:302,1994:295,
    1995:289,1996:285,1997:281,1998:290,1999:282,
    2000:275,2001:278,2002:271,2003:264,2004:257,
    2005:253,2006:248,2007:242,2008:242,2009:251,
    2010:244,2011:237,2012:233,2013:229,2014:226,
    2015:223,2016:220,2017:214,2018:211,2019:209,
    2020:229,2021:212,2022:208,2023:209,
}

DEFAULTS = {
    # ── Original Ana Diez parameters ──────────────────────────────────────
    "base_habituation_rate":           1.012,
    "base_status_impulse_sensitivity": 0.30,
    "status_consumption_conversion":   0.50,
    "resource_acquisition_drive":      0.008,
    "cultural_selection_rate":         0.005,
    "wellbeing_prestige_weight":       0.50,
    "edc_delay":                       20,
    "edc_coefficient":                 0.005,
    "hpa_coefficient":                 0.043,
    "hpa_threshold":                   0.30,
    "info_suppression":                0.50,
    "n_ticks":                         150,
    "n_agents":                        100,
    "seed":                            42,
    # ── v2: Distribution layer (Rule 9) ───────────────────────────────────
    "cosmetic_waste_rate":             0.20,   # fraction rejected for appearance
    "supply_chain_waste_rate":         0.14,   # farm-to-retail loss
    "consumer_waste_rate":             0.17,   # household waste
    "distribution_equity":             0.60,   # how evenly food is distributed (0=feudal, 1=equal)
    "policy_intervention":             0.00,   # 0=status quo, 1=full cosmetic reform
}

PARAM_RANGES = {
    "base_habituation_rate":           (1.000, 1.030),
    "base_status_impulse_sensitivity": (0.05,  1.00),
    "status_consumption_conversion":   (0.05,  2.00),
    "resource_acquisition_drive":      (0.002, 0.040),
    "cultural_selection_rate":         (0.001, 0.020),
    "wellbeing_prestige_weight":       (0.00,  1.00),
    "cosmetic_waste_rate":             (0.00,  0.35),
    "supply_chain_waste_rate":         (0.02,  0.30),
    "consumer_waste_rate":             (0.02,  0.35),
    "distribution_equity":             (0.10,  1.00),
    "policy_intervention":             (0.00,  1.00),
}

# ── Global food production data (FAO 2022) ────────────────────────────────────
GLOBAL_KCAL_PRODUCED    = 2950.0   # kcal/person/day at farm level
KCAL_MINIMUM            = 1800.0   # WHO minimum
PEAK_POPULATION_BILLION = 10.4     # UN median 2080 projection


# ─────────────────────────────────────────────────────────────────────────────
#  SUFFICIENCY PROOF (live calculation)
# ─────────────────────────────────────────────────────────────────────────────
def sufficiency_proof(cosmetic=0.20, supply=0.14, consumer=0.17, policy=0.00):
    effective_cosmetic = cosmetic * (1.0 - policy)
    total_waste = 1.0 - (1.0 - supply) * (1.0 - effective_cosmetic) * (1.0 - consumer)
    available   = GLOBAL_KCAL_PRODUCED * (1.0 - total_waste)
    ratio_now   = available / KCAL_MINIMUM
    ratio_prod  = GLOBAL_KCAL_PRODUCED / KCAL_MINIMUM

    # How many people can we feed at peak population?
    total_daily = GLOBAL_KCAL_PRODUCED * 8_100_000_000
    pop_feedable = (total_daily * (1.0 - total_waste)) / KCAL_MINIMUM
    headroom_vs_peak = (pop_feedable / (PEAK_POPULATION_BILLION * 1e9) - 1.0) * 100.0

    eu_cosmetic_saved_M_people = (
        50_000_000 * 400_000 * (1.0 - policy) / (KCAL_MINIMUM * 365)
    ) / 1_000_000

    return {
        "total_waste_pct":          round(total_waste * 100, 1),
        "effective_cosmetic_pct":   round(effective_cosmetic * 100, 1),
        "available_kcal":           round(available, 0),
        "ratio_after_waste":        round(ratio_now, 3),
        "ratio_production_only":    round(ratio_prod, 3),
        "pop_feedable_billions":    round(pop_feedable / 1e9, 2),
        "headroom_vs_peak_pct":     round(headroom_vs_peak, 1),
        "eu_cosmetic_saves_M_ppl":  round(eu_cosmetic_saved_M_people, 1),
        "in_surplus":               ratio_now >= 1.0,
        "policy_applied":           round(policy * 100, 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  CORE ABM v2 (9 rules, synchronous update)
# ─────────────────────────────────────────────────────────────────────────────
def run_simulation(params=None, null_model=False):
    p         = {**DEFAULTS, **(params or {})}
    n_agents  = int(p["n_agents"])
    n_ticks   = int(p["n_ticks"])
    edc_delay = int(p["edc_delay"])
    rng       = np.random.default_rng(int(p["seed"]))

    hab_rate   = 1.000 if null_model else float(p["base_habituation_rate"])
    base_sip   = float(p["base_status_impulse_sensitivity"])
    scc        = float(p["status_consumption_conversion"])
    rad        = float(p["resource_acquisition_drive"])
    csr        = float(p["cultural_selection_rate"])
    wpw        = float(p["wellbeing_prestige_weight"])
    edc_coef   = float(p["edc_coefficient"])
    hpa_coef   = float(p["hpa_coefficient"])
    hpa_thresh = float(p["hpa_threshold"])
    info_supp  = float(p["info_suppression"])

    # v2 distribution parameters
    cosmetic   = float(p["cosmetic_waste_rate"])
    supply     = float(p["supply_chain_waste_rate"])
    consumer_w = float(p["consumer_waste_rate"])
    equity     = float(p["distribution_equity"])
    policy     = float(p["policy_intervention"])

    # Initial conditions
    consumption             = rng.uniform(350.0, 380.0, n_agents)
    synaptic_habituation    = np.ones(n_agents)
    reproductive_physiology = np.ones(n_agents)

    a_hab = np.full(n_agents, hab_rate)
    a_sip = np.full(n_agents, base_sip)
    a_scc = np.full(n_agents, scc)
    a_rad = np.full(n_agents, rad)

    buf  = np.tile(consumption, (edc_delay + 1, 1))
    bptr = 0

    keys = [
        "tick","year","mean_consumption","eod","eod_empirical",
        "cs_mean","cs_p25","cs_p75",
        "dlc_mean","rsr","sh_mean",
        "repro_mean","repro_p25","repro_p75",
        "fertility_mean","commons_health","sip_mean",
        # v2 additions
        "distribution_efficiency","available_kcal_per_agent",
        "distribution_cs_gap","hope_index",
    ]
    out = {k: [] for k in keys}

    for t in range(n_ticks):
        year = 1970 + t

        # ── RULE 1: Commons health ───────────────────────────────────────────
        mc             = float(np.mean(consumption))
        commons_health = max(0.05, 1.0 - max(0.0, mc - 365.0) / (3000.0 - 365.0))

        # ── RULE 9 (v2): Distribution layer ─────────────────────────────────
        # Effective cosmetic waste reduced by policy intervention
        eff_cosmetic = cosmetic * (1.0 - policy)
        # Total distribution efficiency: what fraction of commons actually reaches agents
        dist_eff = (1.0 - supply) * (1.0 - eff_cosmetic) * (1.0 - consumer_w)
        # Available per agent after distribution losses
        available_per_agent = mc * dist_eff
        # Distribution equity: wealth-weighted Gini correction
        # equity=1.0 → all agents get equal share; equity=0 → top 20% take 80%
        pareto_factor = 1.0 - (1.0 - equity) * 0.6
        agent_ranks   = np.argsort(np.argsort(consumption))  # rank agents by consumption
        equity_weight = pareto_factor + (1.0 - pareto_factor) * (agent_ranks / (n_agents - 1))
        equity_weight = equity_weight / np.mean(equity_weight)   # normalise
        effective_available = available_per_agent * equity_weight

        # ── RULE 2: Dopamine substitute reward ──────────────────────────────
        dsr = (consumption / 365.0) * commons_health

        # ── RULE 3: Synaptic habituation ────────────────────────────────────
        new_sh = synaptic_habituation * a_hab

        # ── RULE 4: Dopamine loop closure ───────────────────────────────────
        dlc = dsr / np.maximum(synaptic_habituation, 1e-9)

        # ── RULE 5: Real satisfaction reward ────────────────────────────────
        # v2: RSR now also depends on distribution efficiency — you feel better
        # when what you consume actually reaches you without systemic waste
        info_env = min(1.0, info_supp * max(0.0, mc / 365.0 - 1.0))
        rsr_base = 0.30 * max(0.0, 1.0 - info_env)
        # distribution bonus: when equity is high and waste is low, satisfaction rises
        dist_bonus = 0.15 * dist_eff * equity
        rsr = min(1.0, rsr_base + dist_bonus)

        # ── RULE 6: Status impulse pressure ─────────────────────────────────
        nbr    = rng.integers(0, n_agents, size=(n_agents, 10))
        excess = np.maximum(0.0, consumption[nbr] - consumption[:, None])
        sip    = np.mean(excess, axis=1) * a_sip

        # ── RULE 7a: Fertility ───────────────────────────────────────────────
        fertility = np.maximum(0.0, 1.0 - sip * 0.4)

        # ── RULE 7b: Reproductive physiology ────────────────────────────────
        hpa_s  = hpa_coef * max(0.0, hpa_thresh - rsr)
        edc_s  = edc_coef * (buf[bptr] / 365.0)
        new_rp = reproductive_physiology * (1.0 - hpa_s - edc_s)

        # ── Consequence separation ───────────────────────────────────────────
        cs = np.maximum(0.0, consumption / 365.0 - dlc)

        # ── Distribution consequence separation gap (v2) ─────────────────────
        # How much of the CS gap is due to distribution failure vs neurobiological mechanism?
        # If distribution were perfect (dist_eff=1), what would CS be?
        ideal_rsr        = min(1.0, 0.30 + 0.15 * equity)
        ideal_hpa_s      = hpa_coef * max(0.0, hpa_thresh - ideal_rsr)
        dist_cs_gap      = float(np.mean(cs)) * (1.0 - dist_eff)

        # ── Hope index (v2): composite of distribution efficiency + repro health ─
        hope = dist_eff * equity * float(np.mean(reproductive_physiology))

        # ── EOD ─────────────────────────────────────────────────────────────
        eod     = (365.0 * 365.0 / mc) if mc > 365.0 else 365.0
        eod_emp = EOD_EMPIRICAL.get(year)

        # ── RULE 8: Cultural transmission ───────────────────────────────────
        top_c  = consumption >= np.percentile(consumption, 75)
        wb_eff = rsr / (consumption + 1.0)
        top_wb = np.zeros(n_agents, dtype=bool)
        top_wb[np.argsort(wb_eff)[-max(1, n_agents // 4):]] = True

        for arr in (a_rad, a_sip, a_scc):
            mu_a = float(np.mean(arr[top_c]))  if top_c.any()  else float(np.mean(arr))
            mu_b = float(np.mean(arr[top_wb])) if top_wb.any() else float(np.mean(arr))
            arr += csr * ((1.0 - wpw) * mu_a + wpw * mu_b - arr)

        # ── Synchronous update ───────────────────────────────────────────────
        gf    = 1.0 - consumption / 3000.0
        new_c = np.clip(consumption * (1.0 + a_rad * gf) + sip * a_scc, 0.0, 3000.0)

        # ── Record ───────────────────────────────────────────────────────────
        out["tick"].append(t)
        out["year"].append(year)
        out["mean_consumption"].append(round(mc, 2))
        out["eod"].append(round(eod, 1))
        out["eod_empirical"].append(eod_emp)
        out["cs_mean"].append(round(float(np.mean(cs)),             4))
        out["cs_p25"].append(round(float(np.percentile(cs, 25)),    4))
        out["cs_p75"].append(round(float(np.percentile(cs, 75)),    4))
        out["dlc_mean"].append(round(float(np.mean(dlc)),           4))
        out["rsr"].append(round(rsr,                                 4))
        out["sh_mean"].append(round(float(np.mean(synaptic_habituation)), 4))
        out["repro_mean"].append(round(float(np.mean(reproductive_physiology)), 4))
        out["repro_p25"].append(round(float(np.percentile(reproductive_physiology, 25)), 4))
        out["repro_p75"].append(round(float(np.percentile(reproductive_physiology, 75)), 4))
        out["fertility_mean"].append(round(float(np.mean(fertility)), 4))
        out["commons_health"].append(round(commons_health,           4))
        out["sip_mean"].append(round(float(np.mean(sip)),            4))
        out["distribution_efficiency"].append(round(dist_eff,        4))
        out["available_kcal_per_agent"].append(round(available_per_agent, 2))
        out["distribution_cs_gap"].append(round(dist_cs_gap,         4))
        out["hope_index"].append(round(hope,                         4))

        consumption             = new_c
        synaptic_habituation    = new_sh
        reproductive_physiology = new_rp
        bptr = (bptr + 1) % (edc_delay + 1)
        buf[bptr] = consumption

    r54   = [out["eod"][t] for t in range(min(54, n_ticks))]
    emp54 = [EOD_EMPIRICAL.get(1970 + t) for t in range(min(54, n_ticks))]
    pairs = [(s, e) for s, e in zip(r54, emp54) if e is not None]
    rmse  = math.sqrt(sum((s - e) ** 2 for s, e in pairs) / len(pairs)) if pairs else 0.0

    out["stats"] = {
        "final_cs":             round(float(out["cs_mean"][-1]),   4),
        "final_repro":          round(float(out["repro_mean"][-1]),4),
        "abc_rmse_54ticks":     round(rmse,                        2),
        "final_eod":            round(float(out["eod"][-1]),       1),
        "final_sh":             round(float(out["sh_mean"][-1]),   4),
        "final_hope":           round(float(out["hope_index"][-1]),4),
        "final_dist_eff":       round(float(out["distribution_efficiency"][-1]), 4),
        "null_model":           null_model,
        "sufficiency":          sufficiency_proof(
                                    cosmetic=float(p["cosmetic_waste_rate"]),
                                    supply=float(p["supply_chain_waste_rate"]),
                                    consumer=float(p["consumer_waste_rate"]),
                                    policy=float(p["policy_intervention"]),
                                ),
    }
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  POLICY SCENARIOS (v2)
# ─────────────────────────────────────────────────────────────────────────────
def run_scenarios(n_ticks=150):
    scenarios = [
        ("Status Quo",              {"policy_intervention": 0.00, "distribution_equity": 0.60}),
        ("Remove Cosmetic Rules",   {"policy_intervention": 1.00, "distribution_equity": 0.60}),
        ("Fix Distribution Equity", {"policy_intervention": 0.00, "distribution_equity": 0.95}),
        ("Optimise Supply Chain",   {"policy_intervention": 0.00, "supply_chain_waste_rate": 0.05,
                                     "consumer_waste_rate": 0.05, "distribution_equity": 0.60}),
        ("Full Reform",             {"policy_intervention": 1.00, "distribution_equity": 0.95,
                                     "supply_chain_waste_rate": 0.05, "consumer_waste_rate": 0.05}),
    ]
    results = []
    for name, overrides in scenarios:
        p = {**DEFAULTS, **overrides, "n_ticks": n_ticks}
        r = run_simulation(p)
        results.append({
            "name":       name,
            "eod":        r["eod"],
            "cs_mean":    r["cs_mean"],
            "repro_mean": r["repro_mean"],
            "hope_index": r["hope_index"],
            "year":       r["year"],
            "stats":      r["stats"],
            "sufficiency": r["stats"]["sufficiency"],
        })
    return {"scenarios": results, "n_ticks": n_ticks}


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP SERVER
# ─────────────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/dashboard_v2.html"):
            self._send(200, "text/html; charset=utf-8", DASH.read_bytes())
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        path = urlparse(self.path).path
        try:
            if path == "/run":
                result = run_simulation(data.get("params"))
            elif path == "/run_null":
                result = run_simulation(data.get("params"), null_model=True)
            elif path == "/scenarios":
                result = run_scenarios(int(data.get("n_ticks", 150)))
            elif path == "/sufficiency":
                p = data.get("params", {})
                result = sufficiency_proof(
                    cosmetic=float(p.get("cosmetic_waste_rate", 0.20)),
                    supply=float(p.get("supply_chain_waste_rate", 0.14)),
                    consumer=float(p.get("consumer_waste_rate", 0.17)),
                    policy=float(p.get("policy_intervention", 0.00)),
                )
            elif path == "/export":
                sim = run_simulation(data.get("params"))
                buf = io.StringIO()
                cols = [k for k in sim if isinstance(sim[k], list)]
                w = csv.writer(buf)
                w.writerow(cols)
                n = len(sim[cols[0]])
                for i in range(n):
                    w.writerow([sim[c][i] for c in cols])
                content = buf.getvalue().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition",
                                 'attachment; filename="ana_diez_sim_v2.csv"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self._send(404, "text/plain", b"Unknown endpoint")
                return

            self._send(200, "application/json", json.dumps(result).encode())

        except Exception as e:
            import traceback
            err = json.dumps({"error": str(e), "trace": traceback.format_exc()}).encode()
            self._send(500, "application/json", err)


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print()
    print("  Neurobiological-Fitness Consequence Separation — v2")
    print("  Ana Diez (2026) + RFI-IRFOS Distribution Extension")
    print()
    print(f"  Dashboard  →  http://localhost:{PORT}")
    print("  Press Ctrl+C to stop")
    print()

    webbrowser.open(f"http://localhost:{PORT}")

    try:
        thread.join()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.shutdown()
