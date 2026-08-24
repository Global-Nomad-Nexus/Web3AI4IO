# S5 Temporal Aggregation — RESULTS

**Status: 三市场 primary formal Monte Carlo 已完成(2026-08-14 批准;仅覆盖 primary,Meteora sensitivity 未批准未实现)。** 本文档记录修订链、zero-day audit 结论、calibration/fidelity 结果与 primary 运行结果(§5)。

## 0. 修订链(全部可追溯,详见 `design_lock.yaml` revision_history)

1. 2026-08-13 初版(4-market,effect gate = pooled residual SD):0.30 越界 → stop。
2. 2026-08-13/14 两轮 gate 口径(estimator sampling SD;daily difference residual SD):0.30 均未过;期间以 0.40 运行过一轮 Monte Carlo,当日废止——artifacts 隔离于 `artifacts/superseded_effect_0.40_20260814/`,**不得引用**。
3. 2026-08-14 **zero-day provenance audit**(`zero_day_audit.md`):7 个 Meteora 零值 = 上游 DefiLlama coverage/adapter failure(2025-01-17 前 parent listing 只覆盖 DAMM V1,adapter 间歇上报字面 0;live API 复核零仍未回填);另发现 01-17 起 DLMM 双重计算(1.94–2.00×)。
4. 2026-08-14 **研究者批准修订**:primary controls = raydium + orca;identification 侧 corrected panel;missing-data policy;Meteora 仅限 restricted-window sensitivity;删除 effect gate;三臂设计;SD_null 预锁定。S3 单独 blocker:`identification/experiment_plans/S3_meteora_coverage_blocker.md`。

## 1. Coverage audit(`coverage_audit_primary_markets.json`)

Pump / Raydium / Orca 全部通过:注册窗口 181/181 天观测完整、无零值日、calibration 窗口内 breakdown 子项定义稳定。Caveat(已记录,不影响 pre-only calibration):raydium 自 2025-04-16 增加 LaunchLab 子项、orca 自 2025-05-29 增加 Wavebreak 子项,均在 post-event;pump_swap 序列 2025-03-17 才开始,之前为 documented structural zero。

## 2. Corrected panel(`data/`,provenance 完整)

724 rows(source 要求满足);primary = 543 rows(3 markets × 181 days),无缺失、无零值。Meteora:01-17 前 28 天 `missing_coverage_gap`,01-17 起 153 天 `observed_corrected`(parent total,去除双计)。Validation 15 项检查全过(`panel_validation.json`)。

## 3. 三市场 calibration 与 fidelity(`calibration_summary.json`、`dgp_fidelity.json`)

- d_resid SD = 0.4659(4-market 时 1.9892);skewness −1.81;ACF lag1 = 0.62 快速衰减;LRV ratio 1.69(原 7.98);无零成交量日;top |residual| ≈ 1.0–2.0(原 6.4)。
- **SD_null = 0.3307**(MCSE 0.0010,种子 1/2/3 = 0.3294–0.3309)已写入 design lock `sd_null_lock` 块。
- **Fidelity gate:通过。** 正式判据(唯一):SD_null 是否落入至少一个 empirical MBB CI。Empirical sliding-window SD(A)= 0.3355,MBB 95% CI:L=14 [0.138, 0.493] / L=21 [0.151, 0.489] / L=28 [0.182, 0.478];B = 0.3307 落入全部三个 CI,ratio B/A = 0.986 → 通过。支持性 diagnostic(非通过条件):分布对比 KS = 0.116,p = 0.41;skewness −0.86(empirical)vs −0.99(simulated);分位数吻合。
- Block-length sensitivity(固定集合,未择优):SD_null L=7/14/21/28 = 0.3307 / 0.3298 / 0.3568 / 0.3443,差异 < 8%。

## 4. Arms(锁定,待运行)

| arm | profile | amplitude | truth(seven-day ATT) |
|---|---|---|---|
| zero | — | 0 | 0 |
| substantive | transient | 0.30 | 0.1286 |
| substantive | persistent | 0.30 | 0.30 |
| calibration | transient | 7T/3 = 0.3858 | T = 0.1653 |
| calibration | persistent | T = 0.1653 | T = 0.1653 |

T = 0.5 × SD_null = 0.1653。安全检查:7T/3 ≈ 0.386 在经验合理范围内(panel 极端日 |Δlog| ≈ 1–2),未触发需批准条款。0.30 substantive arm 在修订后 DGP 下约为 0.91 × SD_null——不再是极端 low-power。

## 5. Primary formal Monte Carlo 结果(2026-08-14 批准并执行;5 arm cells × 7 offsets × 2,000 paired reps × 499 shared-block bootstrap,runtime 84 s)

Thursday primary(offset 0),MCSE of bias 0.006–0.011:

| arm | truth | daily / aligned bias (att) | naive bias (att) | exposure bias (att) |
|---|---|---|---|---|
| zero | 0 | −0.020 (—) | −0.009 (—) | −0.017 (—) |
| substantive transient | 0.1286 | −0.020 (0.843) | **−0.073 (0.430)** | +0.006 (1.045) |
| substantive persistent | 0.3000 | −0.020 (0.933) | **−0.159 (0.470)** | −0.017 (0.943) |
| calibration transient | T = 0.1653 | −0.020 (0.878) | −0.092 (0.446) | +0.012 (1.074) |
| calibration persistent | T = 0.1653 | −0.020 (0.878) | −0.092 (0.446) | −0.017 (0.896) |

(daily ≡ aligned,代数恒等,分别报告。四个非零 cells 共享同一 Y0 与同一零臂 deviate −0.020,paired 设计下这是同一实现噪声,|bias| ≈ 2.7 × MCSE。)

**Weekday sensitivity(全部 7 offsets,attenuation):**

- naive weekly:transient 0.430–0.442、persistent 0.470–0.475,对 weekday 稳健——稀释由"两个 post weeks 只含一半 target days"驱动,不随 weekday 变化。
- exposure weekly:transient 随 weekday 大幅 U 形摆动(substantive:Thu 1.045 → Sat 0.467 → Wed 1.162;calibration 同形 1.074 → 0.500 → 1.190);persistent 稳定 0.87–0.95。Constant-effect 假设在 transient 下失效,且失真方向由 event weekday 决定。
- daily / aligned:所有 offsets、所有 arms 恒定(att 0.843 / 0.878 / 0.933),不受 calendar boundary 影响。

**Inference 层面**:FPR = 0(zero),FNR = 1.0(所有非零 arms),decision disagreement = 0——修订后 DGP 噪声(SD_null 0.33)相对 truth(0.13–0.30)仍使 percentile 区间从不完全高于 0,方法间无 sign-decision 冲突。**Aggregation conflict 体现在点估计的 bias/attenuation 上**:naive calendar-week 稳定稀释 53–57%,exposure-weighted 对 persistent 近似无偏但对 transient 产生 weekday-dependent 双向失真(0.47–1.19)。Coverage(Thursday):daily persistent 0.840、naive persistent 0.644(严重欠覆盖,由 bias 驱动)、exposure persistent 0.976;zero arm 全部 1.000。

**结论边界**:PumpSwap-panel-calibrated aggregation evaluation(3-market primary:pump vs raydium + orca)。Injected effects 不是真实 PumpSwap effect 的估计。Substantive 与 calibration families 分别报告,未合并。

Artifacts:`results_long.parquet`(280,000 rows = 5 arm cells × 7 offsets × 2,000 reps × 4 methods)、`results_summary.csv`、`bin_composition.csv`、`paired_differences.parquet`、`y0_panels.npz`、`run_meta.json`、`figure_s5.pdf/.png`。Rerun:`bash run.sh`。

## 6. 下一步(未批准,未执行)

Meteora restricted-window sensitivity:需先实现 restricted-window four-market runner + 同窗口(2025-01-17..03-19)two-control comparator + 专项 tests(blocks 不跨 coverage boundary、两 specification 共享 draws/estimand/offsets),小规模 pilot + fidelity check 后再提交正式 sensitivity run 批准。S3 blocker 保持 open。
