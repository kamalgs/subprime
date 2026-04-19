"""Unified analysis across all subprime experiments (Apr 15-18 2026).
Groups configs by MODEL (ignoring provider/host)."""
import json, glob, math, statistics
from collections import defaultdict

def norm_model(s):
    """Normalize model strings — strip provider prefixes and variants."""
    if not s: return "?"
    s = s.replace("anthropic:","").replace("openai:","").replace("together:","").replace("vllm:","").replace("bedrock:","")
    s = s.replace("-Instruct-2507-tput","").replace("-Instruct-2507","").replace("Qwen/","")
    s = s.replace("us.anthropic.","").replace("-20251001-v1:0","")
    # Coalesce -fp8 / -FP8 as same model
    return s.replace("-A22B-fp8","-A22B").replace("Qwen3.5-35B-A3B-FP8","Qwen3.5-35B-A3B")

# All configs to include
ALL = [
  # v3 Anthropic (Apr 16-17)
  ("v3/A Haiku self",        "results/20260416_04c5459_haiku"),
  ("v3/B Sonnet self",       "results/20260416_eeb52fe_sonnet"),
  ("v3/C Haiku+think self",  "results/20260416_eeb52fe_haiku_thinking"),
  ("v3/D Haiku→Haiku+think", "results/20260416_nothink_plans_think_judge"),
  ("v3/E Haiku+think→Haiku", "results/20260416_think_plans_nothink_judge"),
  ("v3/F Haiku+think→Sonnet+think", "results/20260417_think_haiku_sonnet_judge"),
  ("v3/G Sonnet→Haiku+think", "results/20260417_sonnet_haiku_think_judge"),
  # v3 Qwen3-8B (Apr 17)
  ("v3/Qwen3-8B FF",         "results/20260417_1143_qwen3_FF"),
  ("v3/Qwen3-8B TT",         "results/20260417_1154_qwen3_TT"),
  ("v3/Qwen3-8B FT",         "results/20260417_qwen3_FT"),
  ("v3/Qwen3-8B TF",         "results/20260417_qwen3_TF"),
  # Today — Qwen experiments (Apr 18)
  ("P25 235B→9B",            "results/20260418_ad23e2d_together/01_big_judge_small"),
  ("P25 9B→235B",            "results/20260418_ad23e2d_together/02_small_judge_big"),
  ("P25 235B self",          "results/20260418_ad23e2d_together/06_big_selfjudge"),
  ("P25 9B self",            "results/20260418_ad23e2d_together/07_small_selfjudge"),
  ("P25 9B-v self",          "results/20260418_vllm_qwen9b_selfjudge"),
  ("P25 235B→9B-v (F')",     "results/20260418_together_fg_p25/F_235Bt_judge_9Bv_P25"),
  ("P25 9B-v→235B (G')",     "results/20260418_together_fg_p25/G_9Bv_judge_235Bt_P25"),
  ("S30 235B→9B",            "results/20260418_crossmatrix_30/A_235Bt_judge_9Bv"),
  ("S30 9B→235B",            "results/20260418_crossmatrix_30/B_9Bv_judge_235Bt"),
  ("S30 235B self",          "results/20260418_crossmatrix_30/C_235Bt_selfjudge"),
  ("S30 9B-v self",          "results/20260418_vllm_qwen9b_stratified30"),
  ("N=100 9B-v self",        "results/20260418_vllm_qwen9b_strat100"),
]

def cohens_d(a, b):
    if len(a) < 2 or len(b) < 2: return None
    m = statistics.mean(a) - statistics.mean(b)
    sd = math.sqrt((statistics.variance(a) + statistics.variance(b)) / 2)
    return m/sd if sd > 0 else 0

def welch_t(a, b):
    """Welch's t-test quick p-value approximation via t-stat (not rigorous)."""
    if len(a)<2 or len(b)<2: return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    na, nb = len(a), len(b)
    se = math.sqrt(va/na + vb/nb)
    return (ma-mb)/se if se>0 else 0

# Per-config analysis
print("="*140)
print(" MILESTONE 1.1 — ALL EXPERIMENTS (Anthropic + Qwen), grouped by MODEL")
print("="*140)

records = []
for label, path in ALL:
    data = defaultdict(lambda: {'aps':[],'pqs':[]})
    adv = jud = None
    for f in glob.glob(f"{path}/*.json"):
        try:
            d = json.load(open(f))
            data[d["condition"]]['aps'].append(d["aps"]["composite_aps"])
            data[d["condition"]]['pqs'].append(d["pqs"]["composite_pqs"])
            if adv is None:
                adv = norm_model(d.get("model",""))
                jud = norm_model(d.get("judge_model") or d.get("model",""))
        except: pass
    if "baseline" not in data: continue
    rec = {"label":label, "adv":adv, "jud":jud, "data":data}
    rec["n_base"] = len(data["baseline"]["aps"])
    rec["base_aps"] = statistics.mean(data["baseline"]["aps"])
    rec["base_pqs"] = statistics.mean(data["baseline"]["pqs"])
    for c in ("lynch","bogle"):
        if c in data:
            rec[f"{c}_aps"] = statistics.mean(data[c]["aps"])
            rec[f"{c}_pqs"] = statistics.mean(data[c]["pqs"])
            rec[f"d_aps_{c}"] = cohens_d(data[c]["aps"], data["baseline"]["aps"])
            rec[f"d_pqs_{c}"] = cohens_d(data[c]["pqs"], data["baseline"]["pqs"])
    rec["spread"] = (rec.get("bogle_aps",0) - rec.get("lynch_aps",0)) if "bogle_aps" in rec and "lynch_aps" in rec else None
    records.append(rec)

# Table
print(f"\n{'Config':<35} {'Advisor':<20} {'Judge':<20} {'n':>3}  {'ΔAPS-L':>7} {'ΔAPS-B':>7} {'d-B':>5}  {'ΔPQS-L':>7} {'ΔPQS-B':>7} {'spread':>7}")
print("-"*140)
for r in records:
    da_l = r.get("lynch_aps",0) - r["base_aps"]
    da_b = r.get("bogle_aps",0) - r["base_aps"]
    dp_l = r.get("lynch_pqs",0) - r["base_pqs"]
    dp_b = r.get("bogle_pqs",0) - r["base_pqs"]
    d_b  = r.get("d_aps_bogle")
    sp   = r.get("spread") or 0
    print(f"{r['label']:<35} {r['adv'][:20]:<20} {r['jud'][:20]:<20} {r['n_base']:>3}  "
          f"{da_l:>+7.3f} {da_b:>+7.3f} {d_b:>+5.2f}  {dp_l:>+7.3f} {dp_b:>+7.3f} {sp:>+7.3f}")

# -- Aggregated by advisor class --
print("\n" + "="*140)
print(" AGGREGATED BY ADVISOR MODEL (bogle effect, pooled)")
print("="*140)
by_adv_all = defaultdict(lambda: {'base':[],'lynch':[],'bogle':[]})
for r in records:
    for c in ("baseline","lynch","bogle"):
        if c in r["data"]:
            by_adv_all[r["adv"]][c if c!="baseline" else "base"].extend(r["data"][c]["aps"])

print(f"\n{'Advisor model':<25} {'n':>4}  {'base APS':>9} {'lynch APS':>9} {'bogle APS':>9}  {'ΔAPS-L':>7} {'ΔAPS-B':>7}  {'d-B':>5}")
for adv in sorted(by_adv_all):
    a = by_adv_all[adv]
    if not a['base']: continue
    nb = len(a['base'])
    mb_b = statistics.mean(a['base'])
    mb_l = statistics.mean(a['lynch']) if a['lynch'] else None
    mb_bo = statistics.mean(a['bogle']) if a['bogle'] else None
    dl = (mb_l - mb_b) if mb_l is not None else None
    db = (mb_bo - mb_b) if mb_bo is not None else None
    dB = cohens_d(a['bogle'], a['base']) if a['bogle'] else None
    print(f"{adv:<25} {nb:>4}  {mb_b:>9.3f} {mb_l or 0:>9.3f} {mb_bo or 0:>9.3f}  {dl or 0:>+7.3f} {db or 0:>+7.3f}  {dB or 0:>+5.2f}")

# -- Blind spot pooled --
print("\n" + "="*140)
print(" BLIND SPOT POOLED ACROSS ALL EXPERIMENTS")
print("="*140)
all_base_aps=[];all_lynch_aps=[];all_bogle_aps=[]
all_base_pqs=[];all_lynch_pqs=[];all_bogle_pqs=[]
for r in records:
    all_base_aps.extend(r["data"]["baseline"]["aps"])
    all_base_pqs.extend(r["data"]["baseline"]["pqs"])
    if "lynch" in r["data"]:
        all_lynch_aps.extend(r["data"]["lynch"]["aps"])
        all_lynch_pqs.extend(r["data"]["lynch"]["pqs"])
    if "bogle" in r["data"]:
        all_bogle_aps.extend(r["data"]["bogle"]["aps"])
        all_bogle_pqs.extend(r["data"]["bogle"]["pqs"])
print(f"\nN: baseline={len(all_base_aps)}, lynch={len(all_lynch_aps)}, bogle={len(all_bogle_aps)}")
print(f"APS means: base={statistics.mean(all_base_aps):.3f}, lynch={statistics.mean(all_lynch_aps):.3f}, bogle={statistics.mean(all_bogle_aps):.3f}")
print(f"PQS means: base={statistics.mean(all_base_pqs):.3f}, lynch={statistics.mean(all_lynch_pqs):.3f}, bogle={statistics.mean(all_bogle_pqs):.3f}")
print(f"\nΔAPS lynch={statistics.mean(all_lynch_aps)-statistics.mean(all_base_aps):+.3f}")
print(f"ΔAPS bogle={statistics.mean(all_bogle_aps)-statistics.mean(all_base_aps):+.3f}")
print(f"ΔPQS lynch={statistics.mean(all_lynch_pqs)-statistics.mean(all_base_pqs):+.3f}")
print(f"ΔPQS bogle={statistics.mean(all_bogle_pqs)-statistics.mean(all_base_pqs):+.3f}")
print(f"\nCohen's d APS lynch: {cohens_d(all_lynch_aps, all_base_aps):+.2f}")
print(f"Cohen's d APS bogle: {cohens_d(all_bogle_aps, all_base_aps):+.2f}")
print(f"Cohen's d PQS lynch: {cohens_d(all_lynch_pqs, all_base_pqs):+.2f}")
print(f"Cohen's d PQS bogle: {cohens_d(all_bogle_pqs, all_base_pqs):+.2f}")

# blind spot ratio
abs_aps = abs(statistics.mean(all_bogle_aps) - statistics.mean(all_base_aps))
abs_pqs = abs(statistics.mean(all_bogle_pqs) - statistics.mean(all_base_pqs))
print(f"\nBLIND SPOT RATIO (|ΔPQS|/|ΔAPS| bogle): {abs_pqs/abs_aps:.1%}")
