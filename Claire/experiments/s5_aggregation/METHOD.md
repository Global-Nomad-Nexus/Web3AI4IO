# S5 Temporal Aggregation — METHOD

Plan: `Claire/experiment_plans/S5_temporal_aggregation.md`(以下称 plan,2026-08-14 研究者批准修订版)。
Design lock: `design_lock.yaml`(§4 公式逐字复制;含 machine-written `sd_null_lock` 块)。Claim boundary 仅为 PumpSwap-panel-calibrated aggregation evaluation。

## Data

- Source panel(immutable upstream bundle,不修改):`data/external/shilin/20260810/bundle/01_Pumpfun_PumpSwap_Project/pumpfun_pumpswap_did_mvp_full_local/data/processed/solana_dex_daily_did_panel.csv`(724 rows / 4 units × 181 days,sha256 见 `data_manifest.json`)。
- **Corrected panel(Claire 侧派生)**:`data/solana_dex_daily_did_panel_corrected.csv`,由 `src/s5agg/build_corrected_panel.py` 构造,保留原始列与 provenance(`daily_volume_usd_original` / `daily_volume_usd_corrected` / `coverage_status` / `correction_reason` / `source_fields` / `log_volume_corrected`;`data/panel_correction_provenance.json`)。Meteora 修正规则:2025-01-17 前 missing(不填零、不插值、不推算);01-17 起只用 parent total(含 DLMM),不再叠加独立 dlmm 序列。依据:`zero_day_audit.md`。
- **Primary analysis panel**:pump_ecosystem + raydium + orca,3 × 181 = 543 rows,全窗口 observed 且 definition-consistent。Coverage audit:`coverage_audit_primary_markets.json`(三市场全过;raydium LaunchLab 2025-04-16、orca Wavebreak 2025-05-29 的子项新增均在 post-event,不影响 pre-only calibration,已记录 caveat)。
- Missing-data policy 与 Meteora sensitivity 限定:见 design lock 与 plan §1/§5a。

## Calibration(plan §3,pre-event only)

只用 corrected primary panel `rel_day=-90..-1` 的 90 天。模型:`log_volume[u,t] = unit_fe[u] + weekday_effect[w(t)] + day_shock[t] + resid[u,t]`,balanced 双向固定效应;day effect 分解为 weekday mean + within-weekday deviation。Residual 为同日 3-market vector(90×3)。

**Effect gate 已删除**(2026-08-14):原 daily-residual-SD gate 被 Meteora 稀有 zero regime 主导,与 seven-day ATT 难度不同尺度。0.30 是 substantive low-power arm,不因 power 停止。

## SD_null 与 arms(锁定)

`SD_null` = 修订后三市场 null DGP 中 daily estimator 的 seven-day ATT sampling SD(50,000 null draws,seed 20260322,block length 7),在任何 positive-arm simulation 前由 data-prep 写入 `design_lock.yaml` 的 `sd_null_lock` 块;run 阶段重新计算不一致即拒绝运行。当前锁定值:**0.3307**(MCSE 0.0010;种子 1/2/3:0.3294–0.3309)。

Arms(zero 每 offset 一次;非零 arm 各跑 transient + persistent;统一 seven-day ATT estimand;substantive 与 calibration 分别报告):

| arm | profile | amplitude | truth |
|---|---|---|---|
| zero | — | 0 | 0 |
| substantive | transient | 0.30 (rel_day 0..2) | 3×0.30/7 ≈ 0.1286 |
| substantive | persistent | 0.30 (rel_day 0..6) | 0.30 |
| calibration | transient | 7T/3 ≈ 0.3858 | T ≈ 0.1653 |
| calibration | persistent | T ≈ 0.1653 | T ≈ 0.1653 |

T = 0.5 × SD_null。安全检查:7T/3 ≈ 0.386,处于经验合理范围(panel 内 |Δlog| 极端值约 1–2),未触发"需再次批准"条款。

## DGP fidelity gate(正式运行前)

- Benchmark A:empirical sliding-window SD(90 pre days 上 56 个 overlapping 35-day windows;MBB 95% CI,block lengths 14/21/28,各 10,000 resamples,seed 20260323)。
- Benchmark B:SD_null(MCSE + 种子敏感性)。
- 判定:B 落在至少一个 A 的 CI 内 → 通过(唯一正式判据;KS、skewness、quantile 对比仅为支持性 diagnostic)。另固定报告 block-length sensitivity(7/14/21/28)、ACF、zero-state frequency、run length、skewness、quantiles、35-day ATT distribution 对比;不得按与 A 的接近程度选 block length。

当前结果(2026-08-14):**A = 0.3355,CI 最宽 [0.139, 0.493];B = 0.3307,ratio 0.986 → 通过。** KS(empirical vs simulated 35-day ATT 分布)= 0.116,p = 0.41;skewness −0.86 vs −0.99;L=14/21/28 的 SD_null 为 0.330 / 0.357 / 0.344。三市场 panel 无零成交量日,LRV ratio 1.69(4-market 时 7.98)。

## Estimators(plan §2、§4)

所有方法都是对 daily treated-control difference `D_t = log_volume_pump,t − mean(log_volume_raydium,t, log_volume_orca,t)` 在 42-day union window 上的线性泛函(`src/s5agg/estimators.py` 的 weight matrix 实现,并由 test 与直接定义互相验证):

1. `daily`:`mean(D, rel_day=0..6) − mean(D, rel_day=-28..-1)`。
2. `naive_weekly`:Monday-to-Sunday 六 bins;两个 post-labelled week differences 的 mean 减四个纯 pre weeks 的 mean。
3. `exposure_weekly`:六个 week differences 对 exposure(0/0/0/0/4/7 分位…即 4/7、3/7)含截距 OLS。
4. `aligned_weekly`:post bin 03-20..03-26 减四个 pre seven-day bins 的 mean;锁定窗口下与 `daily` 代数恒等,分别报告。

## Weekday offsets(plan §5)

Offset k = 0..6:event 依次落在 Thursday..Wednesday;bin edges 相对 event time 平移,effect path 固定在 event time。七个 offsets 全部报告。

## Inference(plan §4,secondary)

每个 generated daily panel:499 次 7-day moving-block bootstrap(42-day window,6 blocks/draw),四种 methods 共享 resampled blocks;percentile 95% interval;完全高于 0 判 `positive`,否则 `null`。Block starts 每 offset 抽一次、跨 arms 共享,保持 paired。

## Reproducibility

- Python 3.12,依赖锁定 numpy / pandas / scipy / statsmodels / pyarrow(解释器 `../s2_timing/.venv/bin/python`,复用未改动)。
- Seeds:Y0 = 20260320,bootstrap = 20260321,SD_null = 20260322,fidelity = 20260323。
- Fresh rerun:`bash run.sh`(pytest → `runner all`:coverage audit → corrected panel → validation → calibration → SD_null lock → fidelity gate → 正式 Monte Carlo → figure)。当前状态:fidelity 已通过,正式 Monte Carlo 待研究者批准后执行。

## Code layout

```
src/s5agg/paths.py                 常量、seeds、arm/DGP 参数
src/s5agg/coverage_audit.py        三市场 upstream coverage audit
src/s5agg/build_corrected_panel.py corrected panel 构造(含 provenance)
src/s5agg/panel.py                 corrected panel 验证、primary/sensitivity 加载、manifest
src/s5agg/dgp.py                   calibration、SD_null、fidelity、诊断、arms、lock 读写
src/s5agg/estimators.py            offset 参数、四种 estimator weight matrix、bin composition
src/s5agg/inference.py             499-draw shared-block bootstrap、percentile interval
src/s5agg/metrics.py               bias/RMSE/coverage/FPR/FNR/sign/claim/attenuation/disagreement/paired
src/s5agg/runner.py                data-prep(至 fidelity)/ run / all
src/s5agg/figures.py               figure_s5
tests/test_s5.py                   15 tests(见 VALIDATION.md)
run.sh                             fresh rerun command
```
