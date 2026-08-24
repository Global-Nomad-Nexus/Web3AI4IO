"""S5 temporal aggregation experiment — paths and constants.

Revision locked 2026-08-14 (researcher approval):
* Primary controls = raydium + orca equal-weight index. Meteora is excluded
  from the primary specification (zero_day_audit.md: upstream coverage
  failure) and enters only the restricted-window secondary sensitivity.
* Analysis panel = identification-arm derived corrected panel; the immutable
  upstream bundle is never modified. Source panel still validates at
  724 rows / 4 units x 181 days; the primary analysis uses 3 markets x
  181 days = 543 rows.
* The old daily-residual-SD effect gate is deleted. 0.30 is a substantive
  low-power arm and never stops for low power.
"""

from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parents[2]  # experiments/s5_aggregation/
REPO_ROOT = EXPERIMENT_DIR.parents[2]  # Web3AI4IO/

BUNDLE = REPO_ROOT / "data/external/pumpswap/20260810/bundle"
PANEL_CSV = (
    BUNDLE
    / "01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local"
    / "data/processed/solana_dex_daily_did_panel.csv"
)
EVIDENCE_FILES = [
    BUNDLE / "Web3AI4IO/application/configs/pumpswap_case.json",
    BUNDLE / "Web3AI4IO/application/benchmark_release/data/events.csv",
]

CORRECTED_PANEL_CSV = EXPERIMENT_DIR / "data" / "solana_dex_daily_did_panel_corrected.csv"
CORRECTED_PROVENANCE_JSON = EXPERIMENT_DIR / "data" / "panel_correction_provenance.json"
COVERAGE_AUDIT_JSON = EXPERIMENT_DIR / "coverage_audit_primary_markets.json"
DESIGN_LOCK = EXPERIMENT_DIR / "design_lock.yaml"

ARTIFACTS = EXPERIMENT_DIR / "artifacts"

EVENT_DATE = "2025-03-20"  # Thursday
EVENT_ID = "PUMP_PUMPSWAP_MIGRATION_20250320"
TREATED = "pump_ecosystem"
CONTROLS = ["raydium", "orca"]  # primary, equal-weight (locked 2026-08-14)
UNITS = [TREATED] + CONTROLS    # pump is column 0 everywhere
METEORA = "meteora_combined"    # restricted-window sensitivity only
SOURCE_UNITS = UNITS + [METEORA]

COVERAGE_BOUNDARY = "2025-01-17"
SENSITIVITY_CAL_START = "2025-01-17"   # meteora sensitivity calibration window
SENSITIVITY_CAL_END = "2025-03-19"     # = rel_day -62..-1, 62 days

# Arms (locked 2026-08-14): the zero arm runs once per weekday offset; each
# non-zero arm runs in BOTH temporal profiles. Every method is scored on the
# same estimand: average log ATT over rel_day = 0..6 (seven-day ATT).
# Substantive and calibration effects are reported separately, never pooled.
EFFECT_SUBSTANTIVE = 0.30      # substantive low-power arm (daily amplitude)
CALIBRATION_MULTIPLIER = 0.5   # T = 0.5 x SD_null, on the seven-day ATT scale
PROFILES = {"transient": 3, "persistent": 7}  # active days from rel_day 0
# calibration amplitudes: persistent = T; transient = 7T/3 (same seven-day ATT T)

N_OFFSETS = 7
N_REPS_FULL = 2000
N_BOOT = 499

SEED_Y0 = 20260320
SEED_BOOT = 20260321
SEED_SDNULL = 20260322   # SD_null draws (locked before any positive-arm simulation)
SEED_FID = 20260323      # empirical sliding-window SD bootstrap CIs
N_SDNULL_DRAWS = 50000

# DGP fidelity: empirical sliding-window benchmark (56 overlapping 35-day
# windows over the 90 pre days) with MBB CIs; block-length sensitivity is a
# FIXED comparison set — no block length is chosen by fit to the benchmark.
FID_WINDOW_PRE = 28
FID_WINDOW_POST = 7
FID_BLOCK_LENGTHS = (14, 21, 28)  # MBB CIs for the empirical SD
FID_N_BOOT = 10000
DGP_BLOCK_LENGTHS = (7, 14, 21, 28)  # fixed DGP sensitivity set; L=7 primary

METHODS = ["daily", "naive_weekly", "exposure_weekly", "aligned_weekly"]
