"""Guard the numerical claims that enter the manuscript."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

ARCHIVED = Path(__file__).resolve().parents[1] / "archived"


def load_json(rel: str) -> dict:
    return json.loads((ARCHIVED / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ladder():
    with (ARCHIVED / "application/deterministic_ladder.csv").open(encoding="utf-8", newline="") as handle:
        return {row["rung"]: row for row in csv.DictReader(handle)}


def test_release_counts():
    sol = load_json("release/solana_core.json")
    assert sol["raw_reproduction"]["deduplicated_terminal_outcomes"] == 832941
    assert sol["raw_reproduction"]["graduated_tokens"] == 1651
    assert load_json("release/base_core.json")["tables"]["launches"]["rows"] == 62618
    assert load_json("release/bnb_core.json")["tables"]["launches"]["rows"] == 1593679
    assert load_json("release/tron_core.json")["tables"]["launches"]["rows"] == 104548


def test_market_ladder(ladder):
    assert float(ladder["L0"]["estimate"]) == pytest.approx(0.6687211175877295)
    assert float(ladder["L2"]["estimate"]) == pytest.approx(0.4116991342312808)
    wild = load_json("application/wild_cluster_bootstrap.json")
    assert float(wild["wild_bootstrap_p_value"]) == pytest.approx(0.6875)
    assert int(wild["cluster_count"]) == 4


def test_telegram_and_mechanism():
    telegram = load_json("application/telegram_mirror_design_summary.json")
    assert telegram["n_total"] == 832941
    assert telegram["n_treated_matched_supported"] == 20227
    assert telegram["n_control_matched_pool"] == 586581
    assert float(telegram["matched_att"]) == pytest.approx(0.009448529581818533)
    assert float(telegram["e_value"]) == pytest.approx(5.020807874760289)
    h1 = load_json("application/h1_rpc_mechanism_summary.json")
    assert int(h1["full_30d_observed_active_tokens"]) == 1636
    assert int(h1["complete_30d_tokens"]) == 762
    assert float(h1["complete_30d_active_share"]) == pytest.approx(1.0)


def test_fee_incidence():
    h3 = load_json("identification/h3_incidence.json")
    assert int(h3["stakeholders"]["creator"]["balance_delta_lamports"]) == 10732
    assert int(h3["support_upgrade_falsification"]["creator_vault_delta_lamports"]) == 0
    h0 = load_json("identification/h0_summary.json")
    launches = next(
        row
        for row in h0["estimates"]
        if row["specification"] == "comparative_hac7"
        and row["sample"] == "gross_21d"
        and row["outcome"] == "launches"
    )
    contrast = next(
        row
        for row in h0["estimates"]
        if row["outcome"] == "launch_minus_migrated_7d"
    )
    assert launches["estimate"] == pytest.approx(-0.9661147726512792)
    assert contrast["estimate"] == pytest.approx(0.18222254012935174)


def test_calibration_headlines():
    s1 = list(csv.DictReader((ARCHIVED / "calibration/s1_results_summary.csv").open(encoding="utf-8")))
    hetero = {row["method"]: row for row in s1 if row["arm"] == "heterogeneous"}
    assert float(hetero["twfe"]["rmse"]) == pytest.approx(0.005133663032560387)
    assert float(hetero["cs_att"]["rmse"]) == pytest.approx(0.017609652500995956)
    s3 = {row["method"]: row for row in csv.DictReader((ARCHIVED / "calibration/s3_results_summary.csv").open(encoding="utf-8")) if row["arm"] == "zero"}
    assert float(s3["crv1_normal"]["fpr"]) == pytest.approx(0.0646)
    assert float(s3["crv1_t3"]["fpr"]) == pytest.approx(0.0259)
    s4 = [row for row in csv.DictReader((ARCHIVED / "calibration/s4_results_summary.csv").open(encoding="utf-8")) if row["arm"] == "positive"]
    by_gamma = {float(row["gamma"]): row for row in s4}
    assert float(by_gamma[0.75]["bias_twfe"]) == pytest.approx(0.46516439540633053)
    assert float(by_gamma[1.5]["bias_twfe"]) == pytest.approx(0.7065832733781102)
    assert float(by_gamma[0.75]["bias_cs"]) == pytest.approx(0.01648016538841116)
    assert float(by_gamma[1.5]["bias_cs"]) == pytest.approx(0.026188314938866142)
