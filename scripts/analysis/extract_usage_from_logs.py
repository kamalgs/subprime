"""Extract per-run usage + latency from shell logs and emit sidecar files
in the corresponding results directories. Does not modify existing result JSONs.

Per results-dir output:
    _usage_mined.jsonl   — one line per successfully parsed run

Each line:
    {
      "persona_id": "P01", "condition": "bogle",
      "elapsed_s": 192, "input_tokens": 52493, "output_tokens": 6351,
      "cache_read_tokens": 3072, "cache_write_tokens": 0,
      "tps": 33,
      "source_log": "/tmp/batch1_together.log",
      "section": "01_big_judge_small"
    }
"""
import glob, json, re, os
from collections import defaultdict

# Map shell-log section labels to results directory paths. Shell scripts we
# wrote set this via ROOT=… + $label/ — we reconstruct by label.
SECTION_TO_RESULTS = {
    "01_big_judge_small":     "results/20260418_ad23e2d_together/01_big_judge_small",
    "02_small_judge_big":     "results/20260418_ad23e2d_together/02_small_judge_big",
    "03_haiku_judge_big":     "results/20260418_ad23e2d_together/03_haiku_judge_big",
    "06_big_selfjudge":       "results/20260418_ad23e2d_together/06_big_selfjudge",
    "07_small_selfjudge":     "results/20260418_ad23e2d_together/07_small_selfjudge",
    "A_235Bt_judge_9Bv":      "results/20260418_crossmatrix_30/A_235Bt_judge_9Bv",
    "B_9Bv_judge_235Bt":      "results/20260418_crossmatrix_30/B_9Bv_judge_235Bt",
    "C_235Bt_selfjudge":      "results/20260418_crossmatrix_30/C_235Bt_selfjudge",
    "D_235B_selfjudge":       "results/20260418_selfhost_matrix30/D_235B_selfjudge",
    "E_235B_selfjudge_P25":   "results/20260418_selfhost_p25/E_235B_selfjudge_P25",
    "F_235Bt_judge_9Bv_P25":  "results/20260418_together_fg_p25/F_235Bt_judge_9Bv_P25",
    "G_9Bv_judge_235Bt_P25":  "results/20260418_together_fg_p25/G_9Bv_judge_235Bt_P25",
}

# Logs whose runs all map to a single results dir (no section header)
SINGLE_DIR_LOGS = {
    "/tmp/vllm_qwen9b.log":        "results/20260418_vllm_qwen9b_selfjudge",
    "/tmp/vllm_qwen9b_v2.log":     "results/20260418_vllm_qwen9b_selfjudge",
    "/tmp/vllm_strat30.log":       "results/20260418_vllm_qwen9b_stratified30",
    "/tmp/vllm_strat30_v2.log":    "results/20260418_vllm_qwen9b_stratified30",
    "/tmp/n100_retry.log":         "results/20260418_vllm_qwen9b_strat100",
    "/tmp/g_topup.log":            "results/20260418_together_fg_p25/G_9Bv_judge_235Bt_P25",
}

# Pattern catches BOTH: runs with tps= and those without
# Plus optional cache fields
summary_re = re.compile(
    r"^\s*(?P<cond>baseline|lynch|bogle)\s*x\s*(?P<pid>\w+)\s*—\s*"
    r"APS=\S+\s+PQS=\S+\s+(?P<elapsed>\d+)s\s+"
    r"in=(?P<intok>[\d,]+)\s+out=(?P<outtok>[\d,]+)"
    r"(?:\s+tps=(?P<tps>\d+))?"
    r"(?:\s+cache_rd=(?P<crd>[\d,]+))?"
    r"(?:\s+cache_wr=(?P<cwr>[\d,]+))?"
)

section_re = re.compile(r"^===\s*\[(?P<label>[^\]]+)\].*===\s*$")

# bucket records by target results dir
by_dir = defaultdict(list)

for logf in sorted(glob.glob("/tmp/*.log")):
    current_section = None
    # Determine if this log is a single-dir log
    single_dir = SINGLE_DIR_LOGS.get(logf)
    try:
        with open(logf, errors="ignore") as f:
            for line in f:
                sm = section_re.match(line)
                if sm:
                    current_section = sm.group("label").strip()
                    continue
                m = summary_re.match(line)
                if not m:
                    continue
                # Pick target dir
                target = None
                if current_section and current_section in SECTION_TO_RESULTS:
                    target = SECTION_TO_RESULTS[current_section]
                elif single_dir:
                    target = single_dir
                if not target:
                    continue
                record = {
                    "persona_id": m.group("pid"),
                    "condition": m.group("cond"),
                    "elapsed_s": int(m.group("elapsed")),
                    "input_tokens": int(m.group("intok").replace(",", "")),
                    "output_tokens": int(m.group("outtok").replace(",", "")),
                }
                if m.group("tps"): record["tps"] = int(m.group("tps"))
                if m.group("crd"): record["cache_read_tokens"] = int(m.group("crd").replace(",", ""))
                if m.group("cwr"): record["cache_write_tokens"] = int(m.group("cwr").replace(",", ""))
                record["source_log"] = logf
                record["section"] = current_section or ""
                by_dir[target].append(record)
    except Exception as e:
        print(f"  WARN: {logf}: {e}")

# Write sidecar jsonl per directory (sorted by persona_id, condition)
total = 0
for d, recs in sorted(by_dir.items()):
    if not os.path.exists(d):
        print(f"  MISS dir: {d} ({len(recs)} records) — skipping")
        continue
    # Dedup by (persona_id, condition), keep the latest (highest elapsed_s sum — crude)
    seen = {}
    for r in recs:
        key = (r["persona_id"], r["condition"])
        # Keep the first seen (usually the successful run); ignore retries
        if key not in seen:
            seen[key] = r
    out_path = os.path.join(d, "_usage_mined.jsonl")
    with open(out_path, "w") as f:
        for key in sorted(seen):
            f.write(json.dumps(seen[key]) + "\n")
    # Count vs JSON files in dir
    n_json = len([x for x in os.listdir(d) if x.endswith(".json") and not x.startswith("_")])
    print(f"  {d}: {len(seen)} usage records (vs {n_json} results)")
    total += len(seen)

print(f"\nTotal usage records mined: {total}")
