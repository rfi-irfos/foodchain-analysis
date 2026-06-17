#!/usr/bin/env python3
"""
Neurobiological-Fitness Consequence Separation — Interactive Simulation
Ana Diez (2026)  ·  RFI-IRFOS Research

Run:  python3 sim.py
      Browser opens automatically at http://localhost:8765
"""
import numpy as np
import json, threading, webbrowser, math, csv, io
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

PORT = 8765
BASE = Path(__file__).parent
DASH = BASE / "dashboard.html"

# ── Empirical Earth Overshoot Day (day-of-year) ───────────────────────────────
# Source: Global Footprint Network
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
    "base_habituation_rate":           1.012,   # ABC posterior mean
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
    "n_ticks":                         300,
    "n_agents":                        100,
    "seed":                            42,
}

PARAM_RANGES = {
    "base_habituation_rate":           (1.000, 1.030),
    "base_status_impulse_sensitivity": (0.05,  1.00),
    "status_consumption_conversion":   (0.05,  2.00),
    "resource_acquisition_drive":      (0.002, 0.040),
    "cultural_selection_rate":         (0.001, 0.020),
    "wellbeing_prestige_weight":       (0.00,  1.00),
}

# ─────────────────────────────────────────────────────────────────────────────
#  CORE ABM  (8 rules, synchronous update)
# ─────────────────────────────────────────────────────────────────────────────
def run_simulation(params=None, null_model=False):
    p          = {**DEFAULTS, **(params or {})}
    n_agents   = int(p["n_agents"])
    n_ticks    = int(p["n_ticks"])
    edc_delay  = int(p["edc_delay"])
    rng        = np.random.default_rng(int(p["seed"]))

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

    # ── Initial conditions  (≈ 1970: 1 Earth = 365 biocap-days/agent) ──
    consumption            = rng.uniform(350.0, 380.0, n_agents)
    synaptic_habituation   = np.ones(n_agents)
    reproductive_physiology = np.ones(n_agents)

    # Per-agent parameters that drift via cultural transmission (Rule 8)
    a_hab = np.full(n_agents, hab_rate)
    a_sip = np.full(n_agents, base_sip)
    a_scc = np.full(n_agents, scc)
    a_rad = np.full(n_agents, rad)

    # Circular buffer for EDC 20-tick delay
    buf   = np.tile(consumption, (edc_delay + 1, 1))
    bptr  = 0

    keys = [
        "tick","year","mean_consumption","eod","eod_empirical",
        "cs_mean","cs_p25","cs_p75",
        "dlc_mean","rsr","sh_mean",
        "repro_mean","repro_p25","repro_p75",
        "fertility_mean","commons_health","sip_mean",
    ]
    out = {k: [] for k in keys}

    for t in range(n_ticks):
        year = 1970 + t

        # ── RULE 1: Shared environment — commons health ──────────────────────
        mc             = float(np.mean(consumption))
        commons_health = max(0.05, 1.0 - max(0.0, mc - 365.0) / (3000.0 - 365.0))

        # ── RULE 2: Dopamine substitute reward ──────────────────────────────
        dsr = (consumption / 365.0) * commons_health

        # ── RULE 3: Synaptic habituation (computed now, applied synchronously)
        new_sh = synaptic_habituation * a_hab

        # ── RULE 4: Dopamine loop closure ───────────────────────────────────
        dlc = dsr / np.maximum(synaptic_habituation, 1e-9)

        # ── RULE 5: Real satisfaction reward — suppressed by info environment
        info_env = min(1.0, info_supp * max(0.0, mc / 365.0 - 1.0))
        rsr      = 0.30 * max(0.0, 1.0 - info_env)

        # ── RULE 6: Status impulse pressure (10 random neighbours) ──────────
        nbr     = rng.integers(0, n_agents, size=(n_agents, 10))
        excess  = np.maximum(0.0, consumption[nbr] - consumption[:, None])
        sip     = np.mean(excess, axis=1) * a_sip

        # ── RULE 7a: Fertility intention ────────────────────────────────────
        fertility = np.maximum(0.0, 1.0 - sip * 0.4)

        # ── RULE 7b: Reproductive physiology (HPA-HPG + EDC pathways) ───────
        hpa_s  = hpa_coef * max(0.0, hpa_thresh - rsr)    # HPA fires when rsr < threshold
        edc_s  = edc_coef * (buf[bptr] / 365.0)            # EDC: 20-tick delayed consumption
        new_rp = reproductive_physiology * (1.0 - hpa_s - edc_s)

        # ── Consequence separation measure ───────────────────────────────────
        cs = np.maximum(0.0, consumption / 365.0 - dlc)

        # ── Earth Overshoot Day ──────────────────────────────────────────────
        eod     = (365.0 * 365.0 / mc) if mc > 365.0 else 365.0
        eod_emp = EOD_EMPIRICAL.get(year)

        # ── RULE 8: Bidirectional cultural transmission ──────────────────────
        # Pathway A: top-quartile consumers  (consumption prestige)
        top_c  = consumption >= np.percentile(consumption, 75)
        # Pathway B: highest wellbeing-per-ecological-cost  (wellbeing prestige)
        wb_eff = rsr / (consumption + 1.0)
        top_wb = np.zeros(n_agents, dtype=bool)
        top_wb[np.argsort(wb_eff)[-max(1, n_agents // 4):]] = True

        for arr in (a_rad, a_sip, a_scc):
            mu_a = float(np.mean(arr[top_c]))  if top_c.any()  else float(np.mean(arr))
            mu_b = float(np.mean(arr[top_wb])) if top_wb.any() else float(np.mean(arr))
            arr += csr * ((1.0 - wpw) * mu_a + wpw * mu_b - arr)

        # ── Synchronous consumption update ───────────────────────────────────
        gf    = 1.0 - consumption / 3000.0                             # soft logistic ceiling
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
        out["commons_health"].append(round(commons_health,            4))
        out["sip_mean"].append(round(float(np.mean(sip)),            4))

        # ── Apply synchronous updates ─────────────────────────────────────────
        consumption             = new_c
        synaptic_habituation    = new_sh
        reproductive_physiology = new_rp
        bptr = (bptr + 1) % (edc_delay + 1)
        buf[bptr] = consumption

    # ── Summary statistics ────────────────────────────────────────────────────
    r54   = [out["eod"][t] for t in range(min(54, n_ticks))]
    emp54 = [EOD_EMPIRICAL.get(1970 + t) for t in range(min(54, n_ticks))]
    pairs = [(s, e) for s, e in zip(r54, emp54) if e is not None]
    rmse  = math.sqrt(sum((s - e) ** 2 for s, e in pairs) / len(pairs)) if pairs else 0.0

    repro_arr     = np.array(out["repro_mean"])
    n_r           = len(repro_arr)
    annual_decline = ((repro_arr[-1] ** (1.0 / max(1, n_r - 1))) - 1.0) * 100 if n_r > 1 else 0.0

    out["stats"] = {
        "final_cs":              round(float(out["cs_mean"][-1]), 4),
        "final_repro":           round(float(out["repro_mean"][-1]), 4),
        "annual_repro_decline":  round(annual_decline, 3),
        "abc_rmse_54ticks":      round(rmse, 2),
        "final_eod":             round(float(out["eod"][-1]), 1),
        "final_sh":              round(float(out["sh_mean"][-1]), 4),
        "null_model":            null_model,
    }
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  SENSITIVITY  (Latin Hypercube Sampling)
# ─────────────────────────────────────────────────────────────────────────────
def run_lhs(n_samples=120, n_ticks=50, seed=99):
    rng  = np.random.default_rng(seed)
    keys = [
        "base_habituation_rate",
        "base_status_impulse_sensitivity",
        "status_consumption_conversion",
        "resource_acquisition_drive",
        "cultural_selection_rate",
    ]
    ranges = {k: PARAM_RANGES[k] for k in keys}
    k      = len(keys)

    lhs = np.zeros((n_samples, k))
    for j, key in enumerate(keys):
        lo, hi = ranges[key]
        intervals     = np.linspace(lo, hi, n_samples + 1)
        samples       = rng.uniform(intervals[:-1], intervals[1:])
        rng.shuffle(samples)
        lhs[:, j]    = samples

    results = []
    for i in range(n_samples):
        p = {keys[j]: float(lhs[i, j]) for j in range(k)}
        p["n_ticks"] = n_ticks
        try:
            r = run_simulation(p)
            results.append({
                "cs":          r["cs_mean"][-1],
                "repro":       r["repro_mean"][-1],
                "eod_final":   r["eod"][-1],
                "cs_positive": int(r["cs_mean"][-1] > 0),
                "overshoot":   int(r["eod"][-1] < 365),
                "repro_dec":   int(r["repro_mean"][-1] < 1.0),
                **{keys[j]: round(float(lhs[i, j]), 5) for j in range(k)},
            })
        except Exception:
            pass

    if not results:
        return {"error": "no results"}

    n        = len(results)
    cs_vals  = [r["cs"] for r in results]
    rp_vals  = [r["repro"] for r in results]

    return {
        "n_samples":          n,
        "n_ticks":            n_ticks,
        "pct_cs_positive":   round(100 * sum(r["cs_positive"] for r in results) / n, 1),
        "pct_overshoot":     round(100 * sum(r["overshoot"]   for r in results) / n, 1),
        "pct_repro_decline": round(100 * sum(r["repro_dec"]   for r in results) / n, 1),
        "cs_mean":  round(float(np.mean(cs_vals)), 4),
        "cs_std":   round(float(np.std(cs_vals)),  4),
        "cs_min":   round(float(np.min(cs_vals)),  4),
        "cs_max":   round(float(np.max(cs_vals)),  4),
        "cs_p25":   round(float(np.percentile(cs_vals, 25)), 4),
        "cs_p75":   round(float(np.percentile(cs_vals, 75)), 4),
        "repro_mean": round(float(np.mean(rp_vals)), 4),
        "repro_min":  round(float(np.min(rp_vals)),  4),
        "repro_max":  round(float(np.max(rp_vals)),  4),
        "cs_distribution":    [round(x, 4) for x in sorted(cs_vals)],
        "repro_distribution": [round(x, 4) for x in sorted(rp_vals)],
        "sample_results":     results[:40],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  SOBOL  (Saltelli 2002 estimator)
# ─────────────────────────────────────────────────────────────────────────────
def run_sobol(n_base=64, n_ticks=50, seed=77):
    rng  = np.random.default_rng(seed)
    keys = [
        "base_status_impulse_sensitivity",
        "status_consumption_conversion",
        "base_habituation_rate",
        "resource_acquisition_drive",
        "cultural_selection_rate",
    ]
    k = len(keys)

    def lhs_matrix(n):
        m = np.zeros((n, k))
        for j, key in enumerate(keys):
            lo, hi = PARAM_RANGES[key]
            ivs = np.linspace(0.0, 1.0, n + 1)
            s   = rng.uniform(ivs[:-1], ivs[1:])
            rng.shuffle(s)
            m[:, j] = lo + s * (hi - lo)
        return m

    def evaluate(mat):
        out = np.zeros(len(mat))
        for i in range(len(mat)):
            p = {keys[j]: float(mat[i, j]) for j in range(k)}
            p["n_ticks"] = n_ticks
            try:
                r       = run_simulation(p)
                out[i]  = r["cs_mean"][-1]
            except Exception:
                out[i]  = 0.0
        return out

    A  = lhs_matrix(n_base)
    B  = lhs_matrix(n_base)
    fA = evaluate(A)
    fB = evaluate(B)

    V = float(np.var(np.concatenate([fA, fB])))
    if V < 1e-10:
        V = 1e-10

    S1, ST = {}, {}
    for i, key in enumerate(keys):
        AB_i      = A.copy()
        AB_i[:, i] = B[:, i]
        fAB       = evaluate(AB_i)
        S1[key]   = round(max(0.0, float(np.mean(fB * (fAB - fA))) / V), 4)
        ST[key]   = round(max(0.0, float(np.mean((fA - fAB) ** 2)) / (2 * V)), 4)

    return {
        "n_evaluations": n_base * (k + 2),
        "n_base":        n_base,
        "n_ticks":       n_ticks,
        "output_var":    "consequence_separation at final tick",
        "param_names":   keys,
        "S1":            S1,
        "ST":            ST,
        "ST_minus_S1":   {k: round(ST[k] - S1[k], 4) for k in keys},
    }


# ─────────────────────────────────────────────────────────────────────────────
#  ABC  (rejection sampler)
# ─────────────────────────────────────────────────────────────────────────────
def run_abc(n_sims=200, acceptance_pct=5, n_ticks=54, seed=55):
    rng  = np.random.default_rng(seed)
    keys = [
        "base_habituation_rate",
        "base_status_impulse_sensitivity",
        "status_consumption_conversion",
    ]
    ranges = {
        "base_habituation_rate":           (1.000, 1.030),
        "base_status_impulse_sensitivity": (0.05,  1.00),
        "status_consumption_conversion":   (0.05,  2.00),
    }

    emp = [EOD_EMPIRICAL.get(1970 + t) for t in range(n_ticks)]

    records = []
    for _ in range(n_sims):
        p = {k: float(rng.uniform(*ranges[k])) for k in keys}
        p["n_ticks"] = n_ticks
        try:
            r     = run_simulation(p)
            sim   = r["eod"][:n_ticks]
            pairs = [(s, e) for s, e in zip(sim, emp) if e is not None]
            rmse  = math.sqrt(sum((s - e) ** 2 for s, e in pairs) / len(pairs)) if pairs else 999.0
            records.append({**{k: p[k] for k in keys}, "rmse": rmse})
        except Exception:
            pass

    records.sort(key=lambda r: r["rmse"])
    n_acc    = max(1, int(len(records) * acceptance_pct / 100))
    accepted = records[:n_acc]

    posteriors = {}
    for key in keys:
        vals = [r[key] for r in accepted]
        posteriors[key] = {
            "mean": round(float(np.mean(vals)),             5),
            "std":  round(float(np.std(vals)),              5),
            "ci_lo": round(float(np.percentile(vals, 2.5)), 5),
            "ci_hi": round(float(np.percentile(vals, 97.5)),5),
            "values": [round(v, 5) for v in vals],
        }

    return {
        "n_simulations": len(records),
        "n_accepted":    n_acc,
        "acceptance_pct": acceptance_pct,
        "best_rmse":     round(records[0]["rmse"], 2) if records else 0.0,
        "all_rmse":      [round(r["rmse"], 2) for r in records],
        "posteriors":    posteriors,
        "param_names":   keys,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP SERVER
# ─────────────────────────────────────────────────────────────────────────────
CACHE = {}   # simple result cache per endpoint+seed

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass   # suppress default logging

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/dashboard.html"):
            content = DASH.read_bytes()
            self._send(200, "text/html; charset=utf-8", content)
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
            elif path == "/sensitivity":
                result = run_lhs(
                    n_samples=int(data.get("n_samples", 120)),
                    n_ticks=int(data.get("n_ticks", 50)),
                )
            elif path == "/sobol":
                result = run_sobol(
                    n_base=int(data.get("n_base", 64)),
                    n_ticks=int(data.get("n_ticks", 50)),
                )
            elif path == "/abc":
                result = run_abc(
                    n_sims=int(data.get("n_sims", 200)),
                    acceptance_pct=float(data.get("acceptance_pct", 5)),
                )
            elif path == "/export":
                sim = run_simulation(data.get("params"))
                buf = io.StringIO()
                cols = [k for k in sim if isinstance(sim[k], list)]
                w    = csv.writer(buf)
                w.writerow(cols)
                n = len(sim[cols[0]])
                for i in range(n):
                    w.writerow([sim[c][i] for c in cols])
                content = buf.getvalue().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition",
                                 'attachment; filename="ana_diez_simulation.csv"')
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


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print()
    print("  Neurobiological-Fitness Consequence Separation")
    print("  Ana Diez (2026)  ·  RFI-IRFOS Research")
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
