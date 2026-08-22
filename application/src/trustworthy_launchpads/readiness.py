"""Machine-readable readiness audit for the application replication package."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .io import CaseConfig, write_csv, write_json


def _read_json(path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _status(ok: bool, *, warning: bool = False) -> str:
    if ok:
        return "pass"
    return "warning" if warning else "gap"


def build_readiness_audit(config: CaseConfig, ladder: pd.DataFrame, agent_scores: pd.DataFrame) -> pd.DataFrame:
    """Write a compact audit of the remaining top-conference evidence risks.

    The audit is intentionally conservative: it rewards claim boundaries and
    reproducibility, but it does not convert proxy data into causal evidence.
    """

    tables = config.tables_dir
    pretrend = _read_json(tables / "pretrend_diagnostics.json")
    bootstrap = _read_json(tables / "wild_cluster_bootstrap.json")
    dune = _read_json(tables / "dune_indexer_export_summary.json")
    moralis = _read_json(tables / "moralis_decoded_outcomes_summary.json")
    external = _read_json(tables / "external_validation_summary.json")
    h1_mechanism = _read_json(tables / "h1_rpc_mechanism_summary.json")
    identification = _read_json(tables / "identification_strength_summary.json")
    claim_scope_path = tables / "claim_scope_ledger.csv"
    claim_scope = pd.read_csv(claim_scope_path) if claim_scope_path.exists() else pd.DataFrame()
    selection_path = tables / "moralis_sample_selection_audit.csv"
    selection = pd.read_csv(selection_path) if selection_path.exists() else pd.DataFrame()

    rows: list[dict[str, object]] = []

    l0 = ladder.loc[ladder["rung"].eq("L0")]
    l6 = ladder.loc[ladder["rung"].eq("L6")]
    conclusion_flip = bool(
        len(l0)
        and len(l6)
        and str(l0.iloc[0]["worked_decision"]) == "yes"
        and str(l6.iloc[0]["worked_decision"]) != "yes"
    )
    rows.append(
        {
            "area": "benchmark_ladder",
            "status": _status(conclusion_flip),
            "evidence": "L0 says yes while L6 is no_or_uncertain",
            "remaining_work": "Use this as the paper's benchmark finding, not as proof that PumpSwap caused welfare gains.",
        }
    )

    pretrend_flag = bool(pretrend.get("pretrend_flag"))
    rows.append(
        {
            "area": "parallel_trends",
            "status": _status(not pretrend_flag, warning=pretrend_flag),
            "evidence": (
                f"{pretrend.get('significant_pretrend_weeks', 'NA')} significant pre-event weeks; "
                f"max |pre|={pretrend.get('max_abs_pretrend_log_points', 'NA')}"
            ),
            "remaining_work": "Do not report market-level event-study effects as clean causal estimates unless a better control design removes this risk.",
        }
    )

    clusters = int(bootstrap.get("cluster_count", 0) or 0)
    rows.append(
        {
            "area": "few_cluster_inference",
            "status": _status(clusters >= 10, warning=clusters > 0),
            "evidence": f"{clusters} protocol clusters; wild p={bootstrap.get('wild_bootstrap_p_value', 'NA')}",
            "remaining_work": "Treat the four-protocol market panel as a diagnostic benchmark; rely on cross-chain or token-level designs for stronger inference.",
        }
    )

    placebo_count = int(identification.get("placebo_positive_significant_count", 0) or 0)
    event_positive_share = identification.get("event_date_positive_share", np.nan)
    window_positive_share = identification.get("twfe_window_positive_share", np.nan)
    leave_one_positive_share = identification.get("leave_one_control_positive_share", np.nan)
    permutation_p = identification.get("unit_permutation_p_value", np.nan)
    synthetic_gap = identification.get("synthetic_control_gap_change", np.nan)
    synthetic_p = identification.get("synthetic_control_placebo_p_value", np.nan)
    stress_present = int(identification.get("event_date_sensitivity_rows", 0) or 0) > 0
    stress_pass = (
        stress_present
        and placebo_count == 0
        and float(event_positive_share or 0) >= 0.80
        and float(window_positive_share or 0) >= 0.80
        and float(leave_one_positive_share or 0) >= 0.80
    )
    rows.append(
        {
            "area": "identification_stress_tests",
            "status": _status(stress_pass, warning=stress_present),
            "evidence": (
                f"event-date positive share={event_positive_share}; "
                f"window positive share={window_positive_share}; "
                f"leave-one-control positive share={leave_one_positive_share}; "
                f"positive placebo count={placebo_count}; "
                f"unit permutation p={permutation_p}; "
                f"synthetic gap change={synthetic_gap}; "
                f"synthetic placebo p={synthetic_p}"
            ),
            "remaining_work": (
                "Use these stress tests to defend the bounded benchmark claim. If any stress-test warning remains, "
                "do not present the market DiD as a clean standalone causal estimate."
            ),
        }
    )

    post_rows = int(dune.get("outputs", {}).get("post_migration", {}).get("rows", 0) or 0)
    early_rows = int(dune.get("outputs", {}).get("early_wallets", {}).get("rows", 0) or 0)
    dune_ready = dune.get("status") == "computed_dune_indexer_exports" and post_rows > 0 and early_rows > 0
    moralis_rows = int(moralis.get("decoded_swap_rows", 0) or 0)
    moralis_30d_tokens = int(moralis.get("decoded_30d_tokens_with_swaps", 0) or 0)
    moralis_credible = moralis.get("credible_sample_status") == "credible_moralis_decoded_sample"
    decoded_ready = dune_ready or moralis_credible
    decoded_warning = moralis_rows > 0 or post_rows > 0 or early_rows > 0
    rows.append(
        {
            "area": "decoded_indexer_outcomes",
            "status": _status(decoded_ready, warning=decoded_warning),
            "evidence": (
                f"Dune status={dune.get('status', 'missing')}; post rows={post_rows}; early rows={early_rows}; "
                f"Moralis status={moralis.get('status', 'missing')}; decoded swap rows={moralis_rows}; "
                f"30d decoded tokens with swaps={moralis_30d_tokens}"
            ),
            "remaining_work": (
                "Use the Moralis decoded sample for covered-token H1 outcome measurement, but scale to the full cohort and "
                "add same-cohort early-wallet decoded outcomes before making full token-level H1/H4 causal claims."
                if moralis_rows > 0
                else "Run Dune/Helius/Moralis/Birdeye decoded exports before making full token-level H1/H4 causal claims."
            ),
        }
    )

    rpc_tokens = int(external.get("post_migration_tokens", 0) or 0)
    rpc_complete_tokens = int(external.get("post_30d_complete_tokens", 0) or 0)
    rpc_complete_share = float(external.get("share_30d_post_windows_complete", 0) or 0)
    rpc_complete_active_share = external.get("share_complete_30d_pool_activity", "NA")
    rpc_truncated_zero = external.get("post_30d_truncated_zero_observed_tokens", "NA")
    rpc_credible = str(external.get("credible_sample_status", "")) == "credible_complete_rpc_post_migration_sample"
    rpc_ready = rpc_credible and rpc_complete_tokens >= 300 and rpc_complete_share >= 0.50
    rows.append(
        {
            "area": "rpc_external_validation",
            "status": _status(rpc_ready, warning=rpc_tokens > 0),
            "evidence": (
                f"{rpc_tokens} token RPC sample; "
                f"complete-window 30d activity share={rpc_complete_active_share}; "
                f"complete tokens={rpc_complete_tokens}; "
                f"truncation share={external.get('share_30d_post_windows_potentially_truncated', 'NA')}; "
                f"truncated-zero observed={rpc_truncated_zero}; "
                f"status={external.get('credible_sample_status', 'NA')}"
            ),
            "remaining_work": (
                "Use complete RPC windows as post-migration mechanism validation. Treat truncated rows as screening "
                "until Dune/Helius/Moralis/Birdeye decoded exports recover full token-level USD-volume windows."
            ),
        }
    )

    h1_mechanism_pass = (
        h1_mechanism.get("mechanism_claim_status") == "pass_mechanism_level_not_welfare_causal"
    )
    rows.append(
        {
            "area": "h1_rpc_mechanism_validation",
            "status": _status(h1_mechanism_pass, warning=bool(h1_mechanism)),
            "evidence": (
                f"full observed 30d active lower bound="
                f"{h1_mechanism.get('full_30d_observed_active_lower_bound_share', 'NA')}; "
                f"complete active share={h1_mechanism.get('complete_30d_active_share', 'NA')}; "
                f"complete median tx proxy={h1_mechanism.get('complete_30d_median_tx_proxy', 'NA')}; "
                f"temporal violations={h1_mechanism.get('temporal_order_violations_complete_30d', 'NA')}"
            ),
            "remaining_work": (
                "Report as H1 mechanism-level evidence only: PumpSwap operated as a post-migration liquidity venue. "
                "Decoded USD volume, active traders, market quality, and H4 early-wallet outcomes remain separate gaps."
            ),
        }
    )

    max_selection_smd = (
        float(pd.to_numeric(selection["standardized_mean_difference"], errors="coerce").abs().max())
        if not selection.empty and "standardized_mean_difference" in selection
        else np.nan
    )
    selection_present = not selection.empty and int(selection.get("covered_n", pd.Series([0])).max() or 0) > 0
    selection_balanced = selection_present and (pd.isna(max_selection_smd) or max_selection_smd < 0.25)
    rows.append(
        {
            "area": "moralis_sample_selection",
            "status": _status(selection_balanced, warning=selection_present),
            "evidence": (
                f"selection audit rows={len(selection)}; "
                f"max |standardized mean difference|={max_selection_smd}"
            ),
            "remaining_work": (
                "If the decoded sample is selected toward high-activity tokens, describe it as a covered-token measurement "
                "sample and do not generalize its medians to the full 1,651-token cohort."
            ),
        }
    )

    if not agent_scores.empty:
        min_runs = int(pd.to_numeric(agent_scores["runs"], errors="coerce").min())
        scored = bool(agent_scores["status"].astype(str).eq("scored").all())
    else:
        min_runs = 0
        scored = False
    rows.append(
        {
            "area": "agentic_execution",
            "status": _status(scored and min_runs >= 10),
            "evidence": f"minimum runs per rung={min_runs}; all scored={scored}",
            "remaining_work": "Record the exact returned model version in the paper appendix, because API aliases can resolve to newer model names.",
        }
    )

    claim_boundary_ok = bool(
        len(claim_scope)
        and claim_scope["claim_not_allowed"].astype(str).str.contains("Do not", case=False, na=False).all()
    )
    rows.append(
        {
            "area": "claim_boundary",
            "status": _status(claim_boundary_ok),
            "evidence": f"{len(claim_scope)} claim-scope rows with explicit forbidden claims",
            "remaining_work": "Keep these boundaries synchronized with every result paragraph and table caption.",
        }
    )

    audit = pd.DataFrame(rows)
    pass_count = int(audit["status"].eq("pass").sum())
    warning_count = int(audit["status"].eq("warning").sum())
    gap_count = int(audit["status"].eq("gap").sum())
    summary = {
        "areas": int(len(audit)),
        "pass": pass_count,
        "warning": warning_count,
        "gap": gap_count,
        "readiness_label": (
            "workshop_ready_as_benchmark_with_limitations"
            if gap_count == 0 and warning_count <= 4
            else "strong_replication_draft_not_submission_ready"
        ),
        "minimum_standard_note": (
            "The code package is reproducible and now includes event-date, window, control-set, placebo, unit-permutation, "
            "and decoded-sample selection audits. These raise the artifact standard for a workshop benchmark paper, but "
            "full welfare-causal claims still require full-cohort decoded outcomes and same-cohort H4 early-wallet features."
        ),
    }
    write_csv(tables / "paper_readiness_audit.csv", audit)
    write_json(tables / "paper_readiness_summary.json", summary)
    return audit
