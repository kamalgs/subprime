"""Full experiment-level analysis across all configs banked today."""
import json, glob, math, statistics
from collections import defaultdict

CONFIGS = [
  # (label, dir, advisor, judge, persona_set, expected_n_personas)
  ("01 Tog-235B → Tog-9B",     "results/20260418_ad23e2d_together/01_big_judge_small",   "235B-T", "9B-T",  "P25", 25),
  ("02 Tog-9B → Tog-235B",     "results/20260418_ad23e2d_together/02_small_judge_big",   "9B-T",  "235B-T","P25", 25),
  ("06 Tog-235B self",         "results/20260418_ad23e2d_together/06_big_selfjudge",     "235B-T","235B-T","P25", 25),
  ("07 Tog-9B self",           "results/20260418_ad23e2d_together/07_small_selfjudge",   "9B-T",  "9B-T",  "P25", 25),
  ("L40S-9B self",             "results/20260418_vllm_qwen9b_selfjudge",                 "9B-L",  "9B-L",  "P25", 25),
  ("F' 235B-T → 9B-L",         "results/20260418_together_fg_p25/F_235Bt_judge_9Bv_P25", "235B-T","9B-L",  "P25", 25),
  ("G' 9B-L → 235B-T",         "results/20260418_together_fg_p25/G_9Bv_judge_235Bt_P25", "9B-L",  "235B-T","P25", 25),
  ("S30/A 235B-T → 9B-L",      "results/20260418_crossmatrix_30/A_235Bt_judge_9Bv",      "235B-T","9B-L",  "S30", 30),
  ("S30/B 9B-L → 235B-T",      "results/20260418_crossmatrix_30/B_9Bv_judge_235Bt",      "9B-L",  "235B-T","S30", 30),
  ("S30/C 235B-T self",        "results/20260418_crossmatrix_30/C_235Bt_selfjudge",      "235B-T","235B-T","S30", 30),
  ("S30/9B-L self",            "results/20260418_vllm_qwen9b_stratified30",              "9B-L",  "9B-L",  "S30", 30),
  ("N=100 9B-L self",          "results/20260418_vllm_qwen9b_strat100",                  "9B-L",  "9B-L",  "H100",100),
]

def cohens_d(a, b):
    if len(a) < 2 or len(b) < 2: return None
    mean_diff = statistics.mean(a) - statistics.mean(b)
    pooled_sd = math.sqrt((statistics.variance(a) + statistics.variance(b)) / 2)
    return mean_diff / pooled_sd if pooled_sd > 0 else 0


print("="*135)
print(" EXPERIMENT-LEVEL SUMMARY — APS/PQS by config, condition")
print("="*135)
print(f"{'Config':<27} {'Adv':<7} {'Judge':<7} {'n':>3}|{'cond':<8}   {'APS mean±sd':<16} {'PQS mean±sd':<16}   {'ΔAPS':>7} {'ΔPQS':>7} {'d(APS)':>7}")
print("-"*135)

# Also collect for cross-config analysis
all_effects = []

for label, path, adv, jud, pset, n_exp in CONFIGS:
    data = defaultdict(lambda: {'aps':[],'pqs':[]})
    for f in glob.glob(f"{path}/*.json"):
        try:
            d = json.load(open(f))
            data[d["condition"]]['aps'].append(d["aps"]["composite_aps"])
            data[d["condition"]]['pqs'].append(d["pqs"]["composite_pqs"])
        except: pass
    if not data.get("baseline"): continue
    base_aps = data["baseline"]['aps']
    base_pqs = data["baseline"]['pqs']
    for cond in ("baseline", "lynch", "bogle"):
        if cond not in data: continue
        aps = data[cond]['aps']; pqs = data[cond]['pqs']
        m_aps, s_aps = statistics.mean(aps), statistics.stdev(aps) if len(aps)>1 else 0
        m_pqs, s_pqs = statistics.mean(pqs), statistics.stdev(pqs) if len(pqs)>1 else 0
        d_aps = m_aps - statistics.mean(base_aps) if cond != "baseline" else 0
        d_pqs = m_pqs - statistics.mean(base_pqs) if cond != "baseline" else 0
        d_val = cohens_d(aps, base_aps) if cond != "baseline" else None
        d_str = f"{d_val:+.2f}" if d_val is not None else "—"
        print(f"{label:<27} {adv:<7} {jud:<7} {len(aps):>3}|{cond:<8}   {m_aps:.3f}±{s_aps:.3f}      {m_pqs:.3f}±{s_pqs:.3f}       {d_aps:+7.3f} {d_pqs:+7.3f} {d_str:>7}")
        if cond != "baseline":
            all_effects.append({"config":label,"adv":adv,"jud":jud,"cond":cond,"n":len(aps),
                                "d_aps":d_aps,"d_pqs":d_pqs,"cohen_d":d_val,"pset":pset})
    print()

# -------- Cross-config summary --------
print("="*110)
print(" CROSS-CONFIG PATTERNS")
print("="*110)

print("\n--- BLIND SPOT RATIO: |ΔPQS| / |ΔAPS| across all (config × condition) effects ---")
print(f"{'Config':<27} {'Cond':<8} {'|ΔAPS|':>7} {'|ΔPQS|':>7} {'ratio':>7}")
for e in all_effects:
    aps, pqs = abs(e["d_aps"]), abs(e["d_pqs"])
    r = pqs/aps if aps > 0 else 0
    print(f"{e['config']:<27} {e['cond']:<8} {aps:>7.3f} {pqs:>7.3f} {r:>7.1%}")
mean_ratio = statistics.mean(abs(e["d_pqs"])/max(abs(e["d_aps"]),0.001) for e in all_effects)
print(f"\nAverage blind-spot ratio (lower = stronger blind spot): {mean_ratio:.1%}")

print("\n--- ΔAPS bogle aggregated by ADVISOR model ---")
by_adv = defaultdict(list)
for e in all_effects:
    if e["cond"] == "bogle":
        by_adv[e["adv"]].append(e["d_aps"])
for adv in sorted(by_adv):
    vals = by_adv[adv]
    print(f"  {adv:<8} n={len(vals)}  mean ΔAPS_bogle={statistics.mean(vals):+.3f}  ({vals})")

print("\n--- ΔAPS bogle aggregated by JUDGE model ---")
by_jud = defaultdict(list)
for e in all_effects:
    if e["cond"] == "bogle":
        by_jud[e["jud"]].append(e["d_aps"])
for jud in sorted(by_jud):
    vals = by_jud[jud]
    print(f"  {jud:<8} n={len(vals)}  mean ΔAPS_bogle={statistics.mean(vals):+.3f}")

print("\n--- Spread (bogle − lynch) ranked ---")
spreads = []
for label, path, adv, jud, pset, n_exp in CONFIGS:
    data = defaultdict(list)
    for f in glob.glob(f"{path}/*.json"):
        try:
            d = json.load(open(f))
            data[d["condition"]].append(d["aps"]["composite_aps"])
        except: pass
    if not all(c in data for c in ("baseline","lynch","bogle")): continue
    spread = statistics.mean(data["bogle"]) - statistics.mean(data["lynch"])
    spreads.append((label, adv, jud, spread, len(data["baseline"]), pset))
spreads.sort(key=lambda x: -x[3])
for label, adv, jud, sp, n, pset in spreads:
    print(f"  {label:<27} [{adv}→{jud}]  n={n:>3}  spread={sp:+.3f}")

# Overall meta-analysis
print("\n--- OVERALL META-ANALYSIS (pooled across all configs) ---")
all_base_aps=[];all_lynch_aps=[];all_bogle_aps=[]
all_base_pqs=[];all_lynch_pqs=[];all_bogle_pqs=[]
for label, path, *_ in CONFIGS:
    for f in glob.glob(f"{path}/*.json"):
        try:
            d = json.load(open(f))
            c = d["condition"]
            a = d["aps"]["composite_aps"]; p = d["pqs"]["composite_pqs"]
            if c == "baseline": all_base_aps.append(a); all_base_pqs.append(p)
            elif c == "lynch":  all_lynch_aps.append(a); all_lynch_pqs.append(p)
            elif c == "bogle":  all_bogle_aps.append(a); all_bogle_pqs.append(p)
        except: pass
print(f"  N total: baseline={len(all_base_aps)}, lynch={len(all_lynch_aps)}, bogle={len(all_bogle_aps)}")
print(f"  APS: base={statistics.mean(all_base_aps):.3f}  lynch={statistics.mean(all_lynch_aps):.3f}  bogle={statistics.mean(all_bogle_aps):.3f}")
print(f"  PQS: base={statistics.mean(all_base_pqs):.3f}  lynch={statistics.mean(all_lynch_pqs):.3f}  bogle={statistics.mean(all_bogle_pqs):.3f}")
print(f"  ΔAPS: lynch={statistics.mean(all_lynch_aps)-statistics.mean(all_base_aps):+.3f}  bogle={statistics.mean(all_bogle_aps)-statistics.mean(all_base_aps):+.3f}")
print(f"  ΔPQS: lynch={statistics.mean(all_lynch_pqs)-statistics.mean(all_base_pqs):+.3f}  bogle={statistics.mean(all_bogle_pqs)-statistics.mean(all_base_pqs):+.3f}")
d_lynch = cohens_d(all_lynch_aps, all_base_aps)
d_bogle = cohens_d(all_bogle_aps, all_base_aps)
print(f"  Cohen's d: lynch={d_lynch:+.2f}, bogle={d_bogle:+.2f}")
