#!/usr/bin/env python3
# ============================================================
# analyze_sniper_cohorts.py
# Cross-launch recurring-cohort analyzer for pump.fun first-buyer-window
# data.
#
# Reads:
#   data/pumpfun_buyers.jsonl       (per-buy rows from upstream collection)
#   data/sniper_cohorts_intra.jsonl (per-launch intra-cohort hints)
# Writes:
#   data/sniper_cohorts.jsonl       (persistent multi-launch cohorts)
#   data/sniper_cohorts_report.md   (human-readable summary)
#
# Algorithm:
#   1. For each mint, take the first N (default 10) buyers by buyer_rank.
#   2. Build a co-occurrence counter over wallet PAIRS:
#        pair_count[(w_a, w_b)] = number of distinct mints both appear in
#   3. Filter pairs with count >= MIN_LAUNCHES (default 3).
#   4. Union those pairs into connected components (greedy clique merge):
#        any two wallets sharing >=MIN_LAUNCHES co-occurrences with the
#        same third wallet are grouped.
#   5. For each component, recompute: distinct mints where >=2 of its
#      wallets appeared together, first_seen / last_seen, avg first-buyer
#      rank, total SOL deployed.
#   6. Persist as sniper_cohorts.jsonl, one row per cohort.
#
# Plain counting only. No bootstrap and no Monte Carlo edge claims are
# computed here; this is a structural cohort detector that surfaces
# wallet sets that repeatedly appear together at launch. Statistical
# theater (synthetic-sample p-values from small n) is deliberately not
# used.
# ============================================================

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

BUYERS_FILE         = os.path.join(DATA_DIR, "pumpfun_buyers.jsonl")
INTRA_FILE          = os.path.join(DATA_DIR, "sniper_cohorts_intra.jsonl")
COHORTS_OUT         = os.path.join(DATA_DIR, "sniper_cohorts.jsonl")
REPORT_OUT          = os.path.join(DATA_DIR, "sniper_cohorts_report.md")

FIRST_N_BUYERS = int(os.environ.get("PFCD_FIRST_N", "10"))
MIN_LAUNCHES   = int(os.environ.get("PFCD_MIN_LAUNCHES", "3"))
MAX_COHORT_SIZE = int(os.environ.get("PFCD_MAX_COHORT", "12"))


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def load_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ------------------------------------------------------------
# Build per-mint wallet lists
# ------------------------------------------------------------
def group_buyers_by_mint(rows, first_n):
    by_mint = defaultdict(list)
    for r in rows:
        mint = r.get("mint")
        if not mint:
            continue
        by_mint[mint].append(r)
    out = {}
    for mint, lst in by_mint.items():
        lst.sort(key=lambda x: (x.get("buyer_rank") or 9999,
                                x.get("blockTime") or 0))
        out[mint] = lst[:first_n]
    return out


# ------------------------------------------------------------
# Pair co-occurrence
# ------------------------------------------------------------
def build_pair_counts(per_mint):
    pair_count = defaultdict(int)         # (w_a, w_b) -> n_mints
    pair_mints = defaultdict(set)         # (w_a, w_b) -> set of mints
    for mint, buys in per_mint.items():
        wallets = sorted({b["wallet"] for b in buys if b.get("wallet")})
        for i, a in enumerate(wallets):
            for b in wallets[i + 1:]:
                key = (a, b)
                pair_count[key] += 1
                pair_mints[key].add(mint)
    return pair_count, pair_mints


# ------------------------------------------------------------
# Component merge (Union-Find on wallets connected by qualifying pairs)
# ------------------------------------------------------------
class UF:
    def __init__(self):
        self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def merge_into_cohorts(pair_count, min_launches):
    uf = UF()
    for (a, b), n in pair_count.items():
        if n >= min_launches:
            uf.union(a, b)
    groups = defaultdict(set)
    for w in list(uf.p):
        groups[uf.find(w)].add(w)
    return [sorted(g) for g in groups.values() if len(g) >= 2]


# ------------------------------------------------------------
# Score cohorts
# ------------------------------------------------------------
def score_cohort(wallets, per_mint):
    wset = set(wallets)
    mints_hit = []
    first_ranks = []
    sol_total = 0.0
    for mint, buys in per_mint.items():
        present = [b for b in buys if b.get("wallet") in wset]
        if len(present) < 2:
            continue
        mints_hit.append({
            "mint":        mint,
            "n_wallets":   len(present),
            "first_rank":  min(b.get("buyer_rank") or 9999 for b in present),
            "min_time":    min(b.get("blockTime") or 0 for b in present),
            "max_time":    max(b.get("blockTime") or 0 for b in present),
            "sum_sol":     sum(b.get("sol_in") or 0 for b in present),
        })
        first_ranks.append(mints_hit[-1]["first_rank"])
        sol_total += mints_hit[-1]["sum_sol"]

    if not mints_hit:
        return None

    mints_hit.sort(key=lambda m: m["min_time"])
    first_seen = mints_hit[0]["min_time"]
    last_seen  = mints_hit[-1]["max_time"]
    avg_first_rank = sum(first_ranks) / len(first_ranks)

    # Score: more launches, earlier ranks, more SOL deployed = higher.
    score = (len(mints_hit) * 10.0) + (1.0 / max(avg_first_rank, 1)) * 5.0 + (sol_total ** 0.5)

    return {
        "wallets":         wallets,
        "cohort_size":     len(wallets),
        "n_launches":      len(mints_hit),
        "first_seen":      first_seen,
        "last_seen":       last_seen,
        "first_seen_iso":  datetime.utcfromtimestamp(first_seen).isoformat() + "Z" if first_seen else None,
        "last_seen_iso":   datetime.utcfromtimestamp(last_seen).isoformat() + "Z" if last_seen else None,
        "avg_first_rank":  round(avg_first_rank, 2),
        "sol_total":       round(sol_total, 4),
        "score":           round(score, 3),
        "mints_hit":       mints_hit,
    }


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():
    print(f"[ANL] reading {BUYERS_FILE}")
    buyer_rows = load_jsonl(BUYERS_FILE)
    print(f"[ANL] loaded {len(buyer_rows)} buyer rows")

    per_mint = group_buyers_by_mint(buyer_rows, FIRST_N_BUYERS)
    print(f"[ANL] mints with first-{FIRST_N_BUYERS} buyer data: {len(per_mint)}")

    pair_count, _ = build_pair_counts(per_mint)
    qualifying_pairs = [(p, n) for p, n in pair_count.items() if n >= MIN_LAUNCHES]
    print(f"[ANL] wallet pairs with co-occurrence >= {MIN_LAUNCHES}: {len(qualifying_pairs)}")

    components = merge_into_cohorts(pair_count, MIN_LAUNCHES)
    print(f"[ANL] connected components: {len(components)}")

    cohorts = []
    for comp in components:
        if len(comp) > MAX_COHORT_SIZE:
            continue                              # likely a noise hub, skip
        scored = score_cohort(comp, per_mint)
        if scored is None:
            continue
        if scored["n_launches"] < MIN_LAUNCHES:
            continue
        cohorts.append(scored)

    cohorts.sort(key=lambda c: c["score"], reverse=True)
    for i, c in enumerate(cohorts):
        c["cohort_id"] = f"COH-{i + 1:04d}"

    write_jsonl(COHORTS_OUT, cohorts)
    print(f"[ANL] wrote {len(cohorts)} cohorts -> {COHORTS_OUT}")

    # Report
    lines = []
    lines.append(f"# Sniper Cohort Report")
    lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
    lines.append("")
    lines.append(f"- Buyer rows analyzed: {len(buyer_rows)}")
    lines.append(f"- Mints with first-{FIRST_N_BUYERS}-buyer data: {len(per_mint)}")
    lines.append(f"- Qualifying wallet pairs (>= {MIN_LAUNCHES} co-occurrences): {len(qualifying_pairs)}")
    lines.append(f"- Cohorts surfaced: {len(cohorts)}")
    lines.append("")
    if cohorts:
        lines.append("## Top cohorts by score")
        lines.append("")
        for c in cohorts[:20]:
            lines.append(f"### {c['cohort_id']}  (score {c['score']})")
            lines.append(f"- Size: {c['cohort_size']} wallets, hit {c['n_launches']} launches")
            lines.append(f"- First seen: {c['first_seen_iso']}, last seen: {c['last_seen_iso']}")
            lines.append(f"- Avg first-buyer rank: {c['avg_first_rank']}, total SOL: {c['sol_total']}")
            short_wallets = ", ".join(f"`{w[:8]}..{w[-4:]}`" for w in c["wallets"][:6])
            if len(c["wallets"]) > 6:
                short_wallets += f", … (+{len(c['wallets']) - 6})"
            lines.append(f"- Wallets: {short_wallets}")
            lines.append("")

    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[ANL] report -> {REPORT_OUT}")


if __name__ == "__main__":
    sys.exit(main())
