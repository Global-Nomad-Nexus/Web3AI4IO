"""Generate empirical LaTeX tables from archived artifacts. No hand-typed cells."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ARCHIVED, GENERATED, PAPER, REPRO

SCOPE = json.loads((REPRO / "scope.json").read_text(encoding="utf-8"))


def load_json(rel: str) -> dict:
    return json.loads((ARCHIVED / rel).read_text(encoding="utf-8"))


def load_csv(rel: str) -> list[dict[str, str]]:
    with (ARCHIVED / rel).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def fmt_int(n: int) -> str:
    return f"{n:,}"


def r3(x: float) -> str:
    return f"{x:.3f}"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def generate_data_scope() -> str:
    rows = []
    for chain in SCOPE["chains"]:
        rows.append(
            "    \\textbf{"
            + chain["chain"]
            + "}, "
            + chain["platform"]
            + " & "
            + chain["core_units_label"]
            + " & "
            + chain["lifecycle_units_label"]
            + " & "
            + chain["window_start"]
            + " to "
            + chain["window_end"]
            + " \\\\"
        )
    body = "\n".join(rows)
    header = r"""\begin{table}[t]
  \centering
  \caption{Canonical v1 scope. All boundaries are reported as UTC observation windows. Denominators represent different protocol entities and are not direct cross-chain comparison samples.}
  \label{tab:data-scope}
  \small
  \setlength{\tabcolsep}{4.5pt}
  \renewcommand{\arraystretch}{1.10}
  \rowcolors{2}{tablealt}{white}
  \begin{tabularx}{\linewidth}{@{}>{\raggedright\arraybackslash}X R{0.19\linewidth} R{0.18\linewidth} C{0.28\linewidth}@{}}
    \toprule
    \rowcolor{tablehead}
    \textbf{Chain and platform} & \textbf{Core units} & \textbf{Lifecycle units} & \textbf{Observation window (UTC)} \\
    \midrule
"""
    footer = r"""
    \bottomrule
  \end{tabularx}
\end{table}
"""
    return header + body + footer


def generate_claim_evidence() -> str:
    ladder = {row["rung"]: row for row in load_csv("application/deterministic_ladder.csv")}
    wild = load_json("application/wild_cluster_bootstrap.json")
    telegram = load_json("application/telegram_mirror_design_summary.json")
    h1 = load_json("application/h1_rpc_mechanism_summary.json")
    h0 = load_json("identification/h0_summary.json")
    h3 = load_json("identification/h3_incidence.json")
    agent = load_json("application/agent_provenance.json")

    l2 = ladder["L2"]
    twfe = float(l2["estimate"])
    twfe_lo = float(l2["ci95_low"])
    twfe_hi = float(l2["ci95_high"])
    wild_p = float(wild["wild_bootstrap_p_value"])

    att = 100 * float(telegram["matched_att"])
    att_lo = 100 * float(telegram["cluster_bootstrap_ci95"][0])
    att_hi = 100 * float(telegram["cluster_bootstrap_ci95"][1])
    e_value = float(telegram["e_value"])
    risk_pp = 100 * float(ladder["L5"]["estimate"])

    fee_est = next(
        row
        for row in h0["estimates"]
        if row["specification"] == "comparative_hac7"
        and row["sample"] == "gross_21d"
        and row["outcome"] == "launches"
    )
    lamports = int(h3["stakeholders"]["creator"]["balance_delta_lamports"])

    market = (
        f"Daily/TWFE estimate ${r3(twfe)}$, CI $[{r3(twfe_lo)},{r3(twfe_hi)}]$; "
        f"pretrend risk and four-cluster exact $p={wild_p:g}$. "
        r"\newline\textbf{\textcolor{scopered}{Not identified}}."
    )
    venue = (
        f"RPC: {fmt_int(int(h1['full_30d_observed_active_tokens']))}/{fmt_int(int(h1['post_30d_tokens']))} "
        f"lower-bound active tokens; {fmt_int(int(h1['complete_30d_tokens']))} complete windows, all active. "
        r"\newline\textbf{\textcolor{okgreen}{Mechanism claim supported}}."
    )
    social = (
        f"Telegram association: ${r3(att)}$ percentage points, CI $[{r3(att_lo)},{r3(att_hi)}]$, "
        f"E-value ${e_value:.2f}$; no qualifying shock. Concentration proxy: ${risk_pp:.1f}$ percentage points higher risk. "
        r"\newline\textbf{\textcolor{partialamber}{Predictive/proxy, not causal}}."
    )
    fee = (
        f"Verified $+{fmt_int(lamports)}$ lamport vault transfer; Pump--Moonshot launch diagnostic "
        f"${r3(fee_est['estimate'])}$, CI $[{r3(fee_est['ci_low'])},{r3(fee_est['ci_high'])}]$; no accepted control. "
        r"\newline\textbf{\textcolor{partialamber}{Mechanical incidence supported; welfare not identified}}."
    )
    requested_model = agent["requested_model_aliases"][0]
    returned_model = agent["returned_models"][0]
    ai = (
        f"DeepSeek alias \\texttt{{{requested_model}}}, returned \\texttt{{{returned_model}}}; "
        r"ten runs per rung, temperature zero, archived raw responses. Exact runtime prompt payload not archived. "
        r"\newline\textbf{\textcolor{partialamber}{Bounded demonstration}}."
    )

    header = r"""\begin{table}[t]
  \centering
  \scriptsize
  \setlength{\tabcolsep}{3.2pt}
  \renewcommand{\arraystretch}{1.04}
  \caption{Claim--evidence--stakeholder map. Status denotes the narrowest supported claim, not an aggregate platform verdict. Numerical cells are generated from archived artifacts.}
  \label{tab:claim-evidence}
  \rowcolors{2}{tablealt}{white}
  \begin{tabularx}{\linewidth}{@{}L{0.195\linewidth} L{0.145\linewidth} L{0.275\linewidth} >{\raggedright\arraybackslash}X@{}}
    \toprule
    \rowcolor{tablehead}
    \textbf{Claim evaluated} & \textbf{Affected stakeholder} & \textbf{Required evidence and assumptions} & \textbf{Available evidence and status} \\
    \midrule
"""
    rows = [
        "    Market migration effect & Operators; creators; traders & Protocol-day outcome, activation, DEX controls, stable window, valid inference & "
        + market
        + r" \\",
        "    Post-migration venue operation & Creators and traders & Token-level activity, fixed horizon, explicit coverage-complete windows & "
        + venue
        + r" \\",
        "    Social signal and retail risk & Token creators; communities; retail traders & Matched terminal outcomes, timing falsifications, holder snapshots, and an exogenous shock for causality & "
        + social
        + r" \\",
        "    Creator-fee rule incidence & Creators; traders; operators & Activation transaction, vault transfer, admissible control, stakeholder welfare & "
        + fee
        + r" \\",
        "    AI evidence following & Reviewers and users of AI-assisted analysis & Fixed prompts, rung disclosures, model/version, repeated runs, raw responses, prespecified scoring & "
        + ai
        + r" \\",
    ]
    footer = r"""
    \bottomrule
  \end{tabularx}
\end{table}
"""
    return header + "\n".join(rows) + footer


def main() -> None:
    tables = {
        "tab_data_scope.tex": generate_data_scope(),
        "tab_claim_evidence.tex": generate_claim_evidence(),
    }
    GENERATED.mkdir(parents=True, exist_ok=True)
    (PAPER / "tabs").mkdir(parents=True, exist_ok=True)
    for name, text in tables.items():
        write(GENERATED / name, text)
        write(PAPER / "tabs" / name, text)
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
