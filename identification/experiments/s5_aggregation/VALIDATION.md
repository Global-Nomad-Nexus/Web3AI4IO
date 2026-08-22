# S5 Temporal Aggregation — VALIDATION

对照修订版 plan(2026-08-14 研究者批准)§9 验收标准逐条核对。总体状态:**三市场 primary formal Monte Carlo 已完成**(2026-08-14 批准,仅覆盖 primary;Meteora restricted-window sensitivity 未批准、未实现,无 runner/tests/outputs)。Fidelity gate 的正式判据为 SD_null 是否落入至少一个 empirical MBB CI;KS 等分布对比只是支持性 diagnostic。

## §9 逐条核对

1. **Event、chain、markets、corrected panel 与 source 724-row 要求固定 — PASS。** `panel_validation.json` 15 项检查全过:source 724 rows / 4 units × 181 days、原始值保留、Meteora 01-17 前 missing(28 天)且 01-17 起 corrected(153 天)、primary 543 rows 无缺失无零值。`data_manifest.json` 记录 source/corrected panel 与 evidence metadata 的 sha256。
2. **Primary calibration 只用 pre-event data 且只用通过 audit 的三市场 — PASS。** `coverage_audit_primary_markets.json`(pump/raydium/orca 全过);`calibrate()` 只取 `rel_day < 0` 的三市场 corrected panel。
3. **Daily 与 weekly methods 源于同一 daily realization — PASS(设计与测试)。** Weight-matrix 实现;`test_weekly_difference_equals_mean_of_daily_differences`、`test_weights_reproduce_direct_estimators` 通过。
4. **四种 methods 估计同一 rel_day=0..6 target — PASS(设计层面)。** design lock estimand;`test_arm_specs` 固定五 cells 的 truth 全部落在 seven-day ATT 尺度。
5. **Thursday 与全部 7 个 offsets 均报告 — PASS。** `results_summary.csv` 含 offsets 0–6 全部 cells;RESULTS.md §5 报告全部七个;`test_all_seven_offsets` 等通过。
6. **每 cell ≥2,000 paired runs + MC uncertainty — PASS。** `run_meta.json`:n_reps_per_cell = 2000,5 arm cells × 7 offsets;`results_summary.csv` 每行含 `mcse_bias`;`results_long.parquet` 280,000 rows。
7. **Tests 覆盖 — PASS。** `pytest tests/ -q` → **15 passed**(2026-08-14 实测):§9.7 要求的六项 + corrected panel validation(`test_corrected_panel_validation`)、arm specs(`test_arm_specs`)、SD_null lock roundtrip(`test_sd_null_lock_roundtrip`)、sliding-window 数学(`test_sliding_window_estimates`)、fidelity 机制与固定 block-length 集合(`test_fidelity_check_mechanics`)。
8. **Persistent arms 中 exposure/aligned/daily 一致 — PASS。** 正式运行:persistent arms 的 attenuation——exposure 0.896–0.943、daily/aligned 0.878–0.933,差异在 MC uncertainty(MCSE 0.006–0.011,约 ±0.02)内一致;解析层面 aligned ≡ daily(代数恒等),exposure 对 constant effect 无偏(`test_exposure_recovers_constant_effect_all_offsets`)。
9. **Fresh rerun 可从 source CSV 重建全部 outputs(含 corrected panel)— PASS。** `bash run.sh` 于 2026-08-14 完整执行:15 tests passed → coverage audit → corrected panel → validation → calibration → SD_null lock 核对 → fidelity gate → 5×7×2,000 Monte Carlo(84 s)→ figure_s5.pdf/.png。
10. **无 conflict 时报告 stability,不得调 DGP — PASS(如实报告)。** 点估计层面 conflict 存在(naive 稀释、exposure-transient weekday 失真),decision 层面无 conflict(FPR=0/FNR=1/disagreement=0),均如实报告;未做任何结果驱动的 DGP/effect 调整。
11. **Claim boundary — PASS。** design lock / METHOD / RESULTS 均注明;当前无外推 claim。
12. **SD_null 在 positive-arm simulation 前锁定 — PASS。** `design_lock.yaml` `sd_null_lock` 块:value = 0.3306990(MCSE 0.0010,50,000 draws,seed 20260322,block_len 7),由 data-prep 机器写入;run 阶段核对一致否则拒绝。正式运行未执行,锁定先于任何 positive arm。
13. **Substantive 与 calibration 分别报告 — PASS。** RESULTS.md §5 按 family 分行报告,未合并汇总;figure 两 family 分别绘制(solid vs faint dotted)。

## §10 stop conditions 核对

未触发:coverage audit 通过、corrected panel validation 通过、pre residual 无缺失、**fidelity gate 通过**(SD_null 0.3307 vs empirical 0.3355,CI 内含;ratio 0.986)、SD_null 锁定一致、weekly estimators 可映射到 seven-day target、未修改 shared environment(复用 venv,未装新包;写入仅限 `s5_aggregation/` 与研究者批准的 plan/lock 文件;S3 仅提交独立 blocker memo,未改 S3 本体)。

## 环境

Python 3.12(`../s2_timing/.venv`,复用未改动);numpy 2.5.2 / pandas 3.0.5 / scipy 1.18.0 / statsmodels 0.14.6 / pyarrow 25.0.1 / pytest。Seeds:Y0 = 20260320,bootstrap = 20260321,SD_null = 20260322,fidelity = 20260323。
