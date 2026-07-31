#!/usr/bin/env python3
"""Generate Paper 7 figures, tables, and causal buyer-flow analysis.

Outputs to /tmp/p7_artifacts/:
  - fig1_size_distribution.svg     — cohort size histogram
  - fig2_lorenz_curve.svg          — Lorenz curve of cohort activity concentration
  - fig3_score_vs_launches.svg     — score vs n_launches scatter (top cohorts identified)
  - table1_top10_cohorts.csv       — top 10 cohorts by score
  - table2_size_distribution.csv   — size bin -> count
  - table3_descriptive_stats.csv   — all headline numbers
  - causal_buyer_flow.csv          — cohort-touched vs untouched: buyer flow stats
  - causal_buyer_flow_summary.txt  — text summary of causal estimate
"""
import json
import os
from collections import defaultdict, Counter
import csv
import random

OUT = "/tmp/p7_artifacts"
os.makedirs(OUT, exist_ok=True)

COHORTS_FILE  = "sniper_cohorts.jsonl"
BUYERS_FILE   = "pumpfun_buyers.jsonl"
LAUNCHES_FILE = "data/pumpfun_launches.jsonl"

print("[P7] loading cohorts")
cohorts = []
with open(COHORTS_FILE) as f:
    for line in f:
        if not line.strip(): continue
        cohorts.append(json.loads(line))
print(f"  loaded {len(cohorts)} cohorts")

cohort_touched = set()
for c in cohorts:
    for m in c.get("mints_hit", []):
        cohort_touched.add(m["mint"])
print(f"  cohort-touched mints: {len(cohort_touched)}")

# Table 1: top 10 by score
top10 = sorted(cohorts, key=lambda c: c.get("score", 0), reverse=True)[:10]
with open(f"{OUT}/table1_top10_cohorts.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["rank", "cohort_id", "size", "n_launches", "avg_first_rank", "sol_total", "score", "first_seen", "last_seen"])
    for i, c in enumerate(top10, start=1):
        w.writerow([
            i, f"COH-{i:04d}",
            c.get("cohort_size", 0),
            c.get("n_launches", 0),
            c.get("avg_first_rank", 0),
            round(c.get("sol_total", 0), 4),
            round(c.get("score", 0), 2),
            c.get("first_seen_iso", ""),
            c.get("last_seen_iso", ""),
        ])
print("  wrote table1_top10_cohorts.csv")

# Table 2: size distribution
size_counter = Counter(c.get("cohort_size", 0) for c in cohorts)
with open(f"{OUT}/table2_size_distribution.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["cohort_size", "n_cohorts", "share_pct"])
    total = len(cohorts)
    for sz in sorted(size_counter.keys()):
        w.writerow([sz, size_counter[sz], round(100 * size_counter[sz] / total, 2)])
print("  wrote table2_size_distribution.csv")

# Table 3: descriptive stats
sizes    = [c.get("cohort_size", 0) for c in cohorts]
scores   = [c.get("score", 0) for c in cohorts]
launches = [c.get("n_launches", 0) for c in cohorts]
ranks    = [c.get("avg_first_rank", 0) for c in cohorts]
sols     = [c.get("sol_total", 0) for c in cohorts]
def med(xs): return sorted(xs)[len(xs)//2]
def mean(xs): return sum(xs) / len(xs)
high_tier = [c for c in cohorts if c.get("n_launches", 0) >= 10 or c.get("score", 0) >= 100]
premium   = [c for c in cohorts if c.get("n_launches", 0) >= 20]
all_wallets = set()
for c in cohorts: all_wallets.update(c.get("wallets", []))
with open(f"{OUT}/table3_descriptive_stats.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["metric", "value"])
    w.writerow(["n_cohorts", len(cohorts)])
    w.writerow(["unique_cohort_wallets", len(all_wallets)])
    w.writerow(["n_cohort_touched_mints", len(cohort_touched)])
    w.writerow(["high_tier_cohorts", len(high_tier)])
    w.writerow(["premium_cohorts", len(premium)])
    w.writerow(["size_median", med(sizes)])
    w.writerow(["size_mean", round(mean(sizes), 2)])
    w.writerow(["size_max", max(sizes)])
    w.writerow(["score_median", round(med(scores), 2)])
    w.writerow(["score_max", round(max(scores), 2)])
    w.writerow(["launches_hit_median", med(launches)])
    w.writerow(["launches_hit_mean", round(mean(launches), 2)])
    w.writerow(["launches_hit_max", max(launches)])
    w.writerow(["avg_first_rank_median", round(med(ranks), 2)])
    w.writerow(["sol_total_median", round(med(sols), 4)])
    w.writerow(["sol_total_max", round(max(sols), 4)])
print("  wrote table3_descriptive_stats.csv")

# Causal: buyer-flow effect
print("[P7] loading launch timestamps")
launch_ts = {}
with open(LAUNCHES_FILE) as f:
    for line in f:
        if not line.strip(): continue
        try: l = json.loads(line)
        except: continue
        m = l.get("mint")
        if m:
            launch_ts[m] = l.get("created_timestamp") or l.get("t")
print(f"  loaded {len(launch_ts)} launches")

print("[P7] scanning buyers for first-30-min buyer counts")
n30m = defaultdict(int)
ntotal = defaultdict(int)
sol30m = defaultdict(float)
n = 0
with open(BUYERS_FILE) as f:
    for line in f:
        if not line.strip(): continue
        try: b = json.loads(line)
        except: continue
        n += 1
        m = b.get("mint")
        bt = b.get("blockTime")
        if not m or not bt: continue
        ntotal[m] += 1
        lt = launch_ts.get(m)
        if lt and abs(int(lt) - int(bt) * 1000) <= 30 * 60 * 1000:
            n30m[m] += 1
            sol30m[m] += float(b.get("sol_in", 0) or 0)
        if n % 300000 == 0:
            print(f"  ...{n} buyer rows scanned")
print(f"  scanned {n} rows; mints w/ activity: {len(ntotal)}")

all_mints = set(launch_ts.keys()) & set(ntotal.keys())
touched_in_sample = list(cohort_touched & all_mints)
untouched_in_sample = list(all_mints - cohort_touched)
print(f"  touched: {len(touched_in_sample)}  untouched: {len(untouched_in_sample)}")

random.seed(42)
sampled_untouched = random.sample(untouched_in_sample, min(len(untouched_in_sample), len(touched_in_sample) * 3))
print(f"  sampled untouched (3:1): {len(sampled_untouched)}")

def stats(mint_list, label):
    n_buyers = [n30m[m] for m in mint_list]
    total = [ntotal[m] for m in mint_list]
    sol = [sol30m[m] for m in mint_list]
    return {
        "label": label,
        "n_mints": len(mint_list),
        "mean_buyers_30m": round(mean(n_buyers) if n_buyers else 0, 2),
        "median_buyers_30m": med(n_buyers) if n_buyers else 0,
        "mean_total_buyers": round(mean(total) if total else 0, 2),
        "median_total_buyers": med(total) if total else 0,
        "mean_sol_30m": round(mean(sol) if sol else 0, 4),
        "median_sol_30m": round(med(sol) if sol else 0, 4),
    }

touched_stats = stats(touched_in_sample, "cohort_touched")
untouched_stats = stats(sampled_untouched, "untouched_3to1")
with open(f"{OUT}/causal_buyer_flow.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(touched_stats.keys())
    w.writerow(touched_stats.values())
    w.writerow(untouched_stats.values())
print("  wrote causal_buyer_flow.csv")

def safe_lift(a, b): return (a - b) / max(b, 1e-9) * 100
lift_30m = safe_lift(touched_stats["mean_buyers_30m"], untouched_stats["mean_buyers_30m"])
lift_total = safe_lift(touched_stats["mean_total_buyers"], untouched_stats["mean_total_buyers"])
lift_sol = safe_lift(touched_stats["mean_sol_30m"], untouched_stats["mean_sol_30m"])

with open(f"{OUT}/causal_buyer_flow_summary.txt", "w") as f:
    f.write("CAUSAL BUYER-FLOW ESTIMATE (cohort-touched vs random untouched)\n")
    f.write("=" * 64 + "\n\n")
    f.write(f"Sample design: 3:1 random-matched\n")
    f.write(f"  Treated (cohort-touched): n={touched_stats['n_mints']}\n")
    f.write(f"  Control (random untouched): n={untouched_stats['n_mints']}\n\n")
    f.write("First-30-min buyer count:\n")
    f.write(f"  Treated mean: {touched_stats['mean_buyers_30m']}  median: {touched_stats['median_buyers_30m']}\n")
    f.write(f"  Control mean: {untouched_stats['mean_buyers_30m']}  median: {untouched_stats['median_buyers_30m']}\n")
    f.write(f"  Mean lift: {lift_30m:+.1f}%\n\n")
    f.write("Total observed buyer count:\n")
    f.write(f"  Treated mean: {touched_stats['mean_total_buyers']}  median: {touched_stats['median_total_buyers']}\n")
    f.write(f"  Control mean: {untouched_stats['mean_total_buyers']}  median: {untouched_stats['median_total_buyers']}\n")
    f.write(f"  Mean lift: {lift_total:+.1f}%\n\n")
    f.write("First-30-min SOL inflow:\n")
    f.write(f"  Treated mean: {touched_stats['mean_sol_30m']}  median: {touched_stats['median_sol_30m']}\n")
    f.write(f"  Control mean: {untouched_stats['mean_sol_30m']}  median: {untouched_stats['median_sol_30m']}\n")
    f.write(f"  Mean lift: {lift_sol:+.1f}%\n")
print("  wrote causal_buyer_flow_summary.txt")
print()
print(f"CAUSAL: first-30-min buyer lift {lift_30m:+.1f}%, total {lift_total:+.1f}%, SOL inflow {lift_sol:+.1f}%")

# Figures (SVG hand-built)
def write_svg(path, body):
    open(path, "w").write(body)

# Fig 1: size histogram
W, H = 600, 400; mx, my = 60, 40
max_sz = max(size_counter.keys())
max_v = max(size_counter.values())
bar_w = (W - 2*mx) / (max_sz + 1)
bars = []
for sz in range(2, max_sz + 1):
    cnt = size_counter.get(sz, 0)
    h = (cnt / max_v) * (H - 2*my)
    x = mx + (sz - 2) * bar_w
    y = H - my - h
    bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*0.85:.1f}" height="{h:.1f}" fill="#0d7377"/>')
    if cnt > 0:
        bars.append(f'<text x="{x + bar_w/2:.1f}" y="{y - 5:.1f}" font-size="9" text-anchor="middle">{cnt}</text>')
        bars.append(f'<text x="{x + bar_w/2:.1f}" y="{H - my + 14:.1f}" font-size="10" text-anchor="middle">{sz}</text>')
svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"><style>text{{font-family:Arial,sans-serif;fill:#0a0d14;}}</style>'.format(W=W, H=H)
svg += '<text x="{cx}" y="20" text-anchor="middle" font-size="14" font-weight="bold">Fig 1. Cohort size distribution (n={n})</text>'.format(cx=W/2, n=len(cohorts))
svg += '<text x="{cx}" y="{by}" text-anchor="middle" font-size="11">Cohort size (wallets per cohort)</text>'.format(cx=W/2, by=H-8)
svg += '<text x="14" y="{cy}" font-size="11" transform="rotate(-90 14 {cy})" text-anchor="middle">Number of cohorts</text>'.format(cy=H/2)
svg += "\n".join(bars)
svg += '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#888"/>'.format(x1=mx, y1=H-my, x2=W-mx, y2=H-my)
svg += '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#888"/></svg>'.format(x1=mx, y1=my, x2=mx, y2=H-my)
write_svg(f"{OUT}/fig1_size_distribution.svg", svg)
print("  wrote fig1_size_distribution.svg")

# Fig 2: Lorenz curve
sorted_l = sorted(launches, reverse=True)
total_l = sum(sorted_l)
cum_l = 0
points = [(0.0, 0.0)]
for i, l in enumerate(sorted_l, start=1):
    cum_l += l
    points.append((i / len(sorted_l), cum_l / total_l))
W, H = 600, 400; mx, my = 60, 40
plot_w, plot_h = W - 2*mx, H - 2*my
path_d = "M " + " L ".join("{x:.1f},{y:.1f}".format(x=mx + p[0]*plot_w, y=H - my - p[1]*plot_h) for p in points)
svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"><style>text{{font-family:Arial,sans-serif;fill:#0a0d14;}}</style>'.format(W=W, H=H)
svg += '<text x="{cx}" y="20" text-anchor="middle" font-size="14" font-weight="bold">Fig 2. Lorenz curve of cohort activity concentration</text>'.format(cx=W/2)
svg += '<text x="{cx}" y="{by}" text-anchor="middle" font-size="11">Cumulative share of cohorts (sorted by launches hit, descending)</text>'.format(cx=W/2, by=H-8)
svg += '<text x="14" y="{cy}" font-size="11" transform="rotate(-90 14 {cy})" text-anchor="middle">Cumulative share of launches hit</text>'.format(cy=H/2)
svg += '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#888" stroke-dasharray="4,4"/>'.format(x1=mx, y1=H-my, x2=mx + plot_w, y2=my)
svg += '<path d="{d}" stroke="#c9922a" stroke-width="2.5" fill="none"/>'.format(d=path_d)
svg += '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#888"/>'.format(x1=mx, y1=H-my, x2=W-mx, y2=H-my)
svg += '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#888"/>'.format(x1=mx, y1=my, x2=mx, y2=H-my)
svg += '</svg>'
write_svg(f"{OUT}/fig2_lorenz_curve.svg", svg)
print("  wrote fig2_lorenz_curve.svg")

# Fig 3: score vs launches scatter
W, H = 600, 400; mx, my = 60, 40
max_score = max(scores)
max_l_v = max(launches)
dots = []
for c in cohorts:
    x = mx + (c.get("n_launches", 0) / max_l_v) * (W - 2*mx)
    y = H - my - (c.get("score", 0) / max_score) * (H - 2*my)
    sz = max(2, c.get("cohort_size", 0))
    color = "#dc2626" if c.get("n_launches", 0) >= 20 else ("#c9922a" if c.get("n_launches", 0) >= 10 else "#8891a4")
    dots.append('<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{c}" fill-opacity="0.55"/>'.format(x=x, y=y, r=sz/3, c=color))
svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"><style>text{{font-family:Arial,sans-serif;fill:#0a0d14;}}</style>'.format(W=W, H=H)
svg += '<text x="{cx}" y="20" text-anchor="middle" font-size="14" font-weight="bold">Fig 3. Cohort score vs launches hit (color: tier)</text>'.format(cx=W/2)
svg += '<text x="{cx}" y="{by}" text-anchor="middle" font-size="11">Number of launches hit</text>'.format(cx=W/2, by=H-8)
svg += '<text x="14" y="{cy}" font-size="11" transform="rotate(-90 14 {cy})" text-anchor="middle">Cohort score</text>'.format(cy=H/2)
svg += '<text x="{x}" y="{y}" font-size="10" fill="#dc2626">red: premium tier (n_launches&gt;=20)</text>'.format(x=W-mx-180, y=my+12)
svg += '<text x="{x}" y="{y}" font-size="10" fill="#c9922a">gold: high tier (n_launches&gt;=10)</text>'.format(x=W-mx-180, y=my+26)
svg += '<text x="{x}" y="{y}" font-size="10" fill="#8891a4">grey: standard tier</text>'.format(x=W-mx-180, y=my+40)
svg += "\n".join(dots)
svg += '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#888"/>'.format(x1=mx, y1=H-my, x2=W-mx, y2=H-my)
svg += '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#888"/></svg>'.format(x1=mx, y1=my, x2=mx, y2=H-my)
write_svg(f"{OUT}/fig3_score_vs_launches.svg", svg)
print("  wrote fig3_score_vs_launches.svg")
print()
print("DONE")
