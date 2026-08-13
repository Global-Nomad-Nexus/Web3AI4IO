# Claire 任务完成报告

## Trustworthy Causal Inference for Token Launch Platforms

中文主报告，英文辅助说明

Prepared for Claire | 2026-08-02 | Internal research handoff

## 0. 执行结论 | Executive conclusion

本次工作已经把 Claire 在 `records/0730-did-improve.docx` 中承担的部分，从旧 MVP 完全重置为一套新的、可复现的 platform rule event study。已完成 related work、H0、H3、Method Pillar 3、独立 §2.2、Result 2、sequential event handling、naive rerun，以及 L0 至 L7 deterministic table cross check。代码、SQL、数据、证据和 artifacts 均独立存放于 `Claire/`。已验证的内容同时写入独立 LaTeX 和 active shared manuscript `manuscript/neurips_2026.tex`。

最重要的研究结论不是一个漂亮的 causal estimate，而是一个经过数据验证的 claim boundary。Pump.fun creator fee 的经济激活时间得到 onchain verification，但 LaunchLab 与 Moonshot 都没有通过 causal control gate。因此，H0 的现有数值只能作为 diagnostic comparison，不能写成 creator fee 导致 market thickness 变化。H3 识别了 creator vault 收到 gross mechanical transfer，但没有识别 creator net welfare、trader welfare 或 platform incidence。

English companion: Claire’s assigned contribution has been rebuilt from scratch as a reproducible platform rule event study. All writing and implementation deliverables are present. The evidence verifies the Pump.fun creator fee activation and creator side transfer mechanics, but no screened comparison identifies a causal effect on market thickness or stakeholder welfare. The completed research contribution is therefore an honest and reproducible claim boundary rather than an overstated treatment effect.

## 1. Claire 对任务的理解 | Claire’s interpretation

以下内容记录的是 Claire 在讨论中作出的研究决策。它们属于 project decisions，不是经验事实。

1. 旧 MVP 完全放弃。旧 MVP 不作为 baseline、data source、event source、result source 或 prior，也不要求在新结果中复现其 44% headline。
2. H0 的 substantive question 是 market thickness。Selection into timing 是 identification threat，也是 Method Pillar 3 必须处理的方法问题，不是 H0 本身。
3. H3 不继承旧 cohort 或旧 cross chain framing，而应重新设计 stakeholder incidence，明确 creator、trader 与 platform 的不同 outcome 和 loss bearer。
4. 研究从当前论文的 interdisciplinary objective 出发，但现有 ownership text 只是 reference，可以替换、重组或挑战。
5. 数据重新寻找。旧 DEX volume 不再使用，新 study 应直接测量 launch market 的 entry、creator participation 与 lifecycle completion。
6. 研究遵循 first principles 与 Occam’s Razor。优先做能够被真实数据支持的最小可信设计，不为了保留 “staggered DiD” 的标签而拼接异质事件。
7. 正确完成 Claire 的学术任务优先于修补旧 PDF formatting。可以建立独立的新 LaTeX 文档。

English companion: Claire explicitly reset the empirical contribution. H0 concerns market thickness, while selection into timing belongs to identification. H3 concerns stakeholder incidence. The old MVP and old DEX volume were excluded completely. Existing manuscript text was treated as revisable reference material, and empirical feasibility was prioritized over preserving a predetermined estimator label.

## 2. 原始邮件要求总览 | Assignment traceability

### 2.1 Related work: Difference in Differences under staggered adoption

原要求：完成 0.5 至 0.75 页的 related work strand，以 positioning 为主，不做文献罗列。

完成内容：独立稿第一节解释了为什么 staggered adoption 需要 group time、interaction weighted 或 imputation estimators，并明确指出 modern estimators 不能修复 invalid control、interference、anticipation、concurrent shocks 或 bundled treatment。引用了 Callaway and Sant’Anna、Sun and Abraham、Borusyak, Jaravel and Spiess、Goodman Bacon、de Chaisemartin and D’Haultfoeuille 等核心工作。

如何完成：从 launch platform 的实际识别问题反推 literature position，而不是从方法列表出发。最终 positioning 是 “modern staggered DiD is an eligible estimator after design gates pass, not a default applied whenever dates differ.”

证据：`manuscript/claire_contribution.tex` 的 “Positioning: difference in differences under staggered adoption”。

English companion: The related work section positions modern staggered DiD as conditional on design validity. It explains both what the estimators solve and what they cannot solve, with direct relevance to launch platform rules.

### 2.2 Hypotheses H0 and H3

原要求：Claire owns H0 and H3。

H0 完成定义：A stronger creator participation incentive increases gross market thickness more than quality adjusted thickness。Gross thickness 使用 launches 与 unique creators。Quality adjusted thickness 使用 fixed horizon migrations 的数量与比例。Primary horizon 为 7 days，30 days 为 secondary horizon。H0 的 joint criterion 要求 launch effect 为正，并且 launch effect 大于 quality adjusted migration effect。

H3 完成定义：A mandatory platform rule can create opposing incidence across creators, traders, and the platform。H3 将 mechanical transfer、behavioral response 和 net welfare 分开。Creator outcomes、trader outcomes 与 platform outcomes 具有不同 estimands，aggregate activity 不能直接作为 welfare statistic。

关键修正：Pump event 同时包含 creator subsidy、trader fee burden 与 program upgrade，因此 estimand 必须是 reduced form rule bundle effect，不能写成 isolated creator subsidy effect。

证据：`Claire/research_design.md`，`manuscript/claire_contribution.tex`，`Claire/artifacts/h0_summary.json`，`Claire/artifacts/h3_incidence.json`。

English companion: H0 separates gross and quality adjusted market thickness. H3 separates stakeholder specific incidence and distinguishes gross transfers from behavioral and welfare effects. The observed treatment is defined as a rule bundle rather than an isolated subsidy.

### 2.3 Method Pillar 3 and independent §2.2

原要求：独立于 Shilin 完成 Method Pillar 3 和 §2.2，之后再共同 merge。

完成内容：建立了一套独立 identification protocol，预先固定 treatment family、unit、target population、outcome、lifecycle horizon、comparison rule 与 decision criterion。方法明确处理 anticipation、selection into timing、pretrends、sequential events、few units、interference、common outcome schema 与 fixed horizon censoring。

设计门槛：只有当至少 3 个 comparable mandatory events、至少 3 个 platforms、一个 common outcome schema 同时成立时，才使用 staggered design。否则使用最强单事件设计，并收窄 causal language。

实现结果：当前 registry 没有 event 被 accepted 为 causal event，`staggered_gate_passes=false`。这不是失败的写作，而是 protocol 正确拒绝了不满足识别条件的估计。

证据：`Claire/research_design.md`，`Claire/event_registry.csv`，`Claire/src/web3io_claire/registry.py`。

English companion: The independent method draft precommits the estimand and design gates. The staggered estimator becomes applicable only after sufficient comparable events and platforms exist. The current registry correctly closes that gate.

### 2.4 Result 2: estimates, robustness, sequential events, naive rerun

原要求：Claire owns Result 2，包括 cross chain staggered DiD estimates、robustness canon、sequential events extension 与 naive rerun。

完成方式发生了 evidence driven revision。重新收集的数据不支持跨链 pooled staggered DiD，因此没有把异质平台事件强行合并。Result 2 改为一个 verified Pump.fun rule event、两个被严格审查的 comparison candidates、一个 exact platform day panel，以及透明的 diagnostic estimates。

已完成的 Result 2 内容包括：

1. Event timing verification。
2. Dune schema and lifecycle construction。
3. Gross 21 day comparison。
4. Anticipation safe 7 day cohorts。
5. Anticipation safe 30 day cohorts。
6. Pump before after rerun。
7. Pump minus Moonshot diagnostic comparison with weekday effects and Newey West uncertainty at 7 lags。
8. Pretrend diagnostics。
9. Joint launch minus migration criterion。
10. Eight date in time placebo。
11. Sequential treatment distinction between May 12 support and May 13 economic activation。

为什么没有完成一个 cross chain causal number：LaunchLab 于 2025-04-15 才开始运行，platform maturation 与 May event 无法分离。Moonshot 虽然具有 exact launch and migration schema，但 study window 附近存在 product changes，且 Pump 与 Moonshot 之间可能发生 user displacement。两平台只有两个 clusters，不能使用 platform clustered 或 wild cluster DiD inference。以上事实使 causal control gate 失败。

English companion: Result 2 was revised because the newly collected evidence does not support the provisional cross chain staggered design. The completed result is an exact event panel, a full diagnostic battery, a naive rerun, and a documented failure of the comparison validity gate.

### 2.5 Deterministic cross check of tab_arms and tab_ablation

原要求：逐 rung 核对 `tab_arms` deterministic column 与 `tab_ablation`，两表必须一致。

完成内容：为 `manuscript/tabs/tab_arms.tex` 增加 deterministic decision column，并实现 parser 对两个 LaTeX tables 的 L0 至 L7 decision cells 进行逐项比较。8 个 rungs 全部 exact match。

结果：`all_rungs_agree=true`。

证据：`Claire/src/web3io_claire/crosscheck_ladder.py`，`Claire/artifacts/deterministic_crosscheck.json`。

English companion: The deterministic decision labels in the two paper tables are now machine checked. All eight rungs agree exactly.

### 2.6 Code, data, and artifacts under Claire’s folder

原要求：在 GitHub repository 中将 Claire 产生的 code、data 与 artifacts 放在自己的 folder。

完成内容：NatureSD root 与 `manuscript/` 没有被擅自初始化为 Git repository。Claire empirical materials 被隔离在 `Claire/`，并按任务书边界发布到 `Global-Nomad-Nexus/Web3AI4IO` 的 `Claire/`。论文源文件继续留在 Overleaf 工作流，GitHub 只承载 code、data、artifacts、evidence 与 reproducibility documents。

主要内容：SQL queries、raw derived CSV、event registry、data contract、JSON schemas、Solana verification code、H0 and H3 analysis、table cross check、Kimi audit、tests 与 machine readable artifacts。

English companion: All Claire owned empirical materials are isolated under `Claire/`. No repository was initialized without authorization. The folder is ready to move into the intended GitHub repository.

### 2.7 Critical thinking, creativity, leadership, open science

原要求：现有 ownership text 仅供参考，Claire 应体现 critical thinking、creativity 与 leadership，并保持 open science、SDGs 与 local communities 的视角。

完成内容：没有把旧 44% 结果作为新 paper 的 baseline，没有为了保留 “cross chain staggered DiD” 而使用不可信 controls，也没有把一个 positive creator transfer 写成 stakeholder welfare improvement。Study 保留 rejected events、activation evidence、SQL、schemas、claim ledger 与 reproducible artifacts，使 negative design decisions 也可被审计。

Open science 体现为完整 event provenance、raw query logic、machine readable registry、reproduction commands、explicit exclusions 与 no sign based event selection。AI for Good 体现为不给 retail users、creators 或 platforms 分配未经识别的 welfare conclusions。Local community relevance 体现在把 participant protection 与 distributional incidence 作为核心 outcome，而不是只追求 aggregate platform growth。

English companion: Research leadership is demonstrated through principled rejection of invalid comparisons, complete provenance, reproducible negative design decisions, and stakeholder specific claim boundaries.

## 3. 数据与事件验证 | Data and event verification

### 3.1 Pump.fun activation

First party documentation 首次公开时间为 2025-05-08 15:49:08 UTC，因此 May 8 至 activation 被注册为 anticipation interval。

Solana finalized RPC 显示：

1. May 12 11:26:54 UTC program upgrade 后，一笔成功 sell transaction 的 creator vault balance delta 为 0。May 12 只证明 program support，不能证明 creator fee 已经济激活。
2. May 13 11:27:06 UTC second upgrade 后，next block transaction 的 sell side creator vault 增加 10,732 lamports。
3. Later verified sell 的 creator vault 增加 216,573 lamports。

因此 registered activation 是 2025-05-13 11:27:06 UTC。

English companion: The May 12 upgrade added support but produced no verified creator payment. Economic activation is registered at the May 13 upgrade followed immediately by a positive creator vault transfer.

### 3.2 Dune data construction

最终 panel 有 156 platform day rows。Pump launches 使用 exact decoded `pumpdotfun_solana.pump_call_create`。Moonshot launches 使用 exact `moonshot_solana.token_launchpad_call_tokenmint`。

Pump decoded migrate table 只匹配到 30 个 launches，因此被判断为 incomplete。改用 raw instruction discriminator `0x9beae792ec9ea21e` 后，找到 41,983 migration calls，并从 fourth account argument 匹配 migrated mint。Moonshot migrations 使用 exact decoded `token_launchpad_call_migratefunds`。

Gross cohorts：2025-04-17 至 2025-05-07，2025-05-14 至 2025-06-03。

7 day quality cohorts：pre 截止 2025-04-30，post 从 2025-05-14 开始。

30 day quality cohorts：pre 截止 2025-04-07，post 从 2025-05-14 开始。

Quality cohort 的 migration lookup 读取 cohort date 之后的完整链上记录，不存在因为 cohort sample end 而产生的 7 day 或 30 day right censoring。

English companion: Exact launch and lifecycle records were used. Pump migration required raw instruction decoding because the public decoded table was incomplete. Fixed horizon pre cohorts end early enough to avoid anticipation, and post cohorts retain complete lifecycle follow up.

## 4. 结果与解释 | Results and interpretation

### 4.1 H0 diagnostic estimates

Pump minus Moonshot post change 使用 weekday indicators 与 Newey West HAC 7 uncertainty。

Gross launches：estimate -0.966，95% CI [-1.252, -0.680]。

Gross unique creators：estimate -0.685，95% CI [-0.822, -0.548]。

7 day launches：estimate -1.008，95% CI [-1.297, -0.719]。

7 day migrations：estimate -1.190，95% CI [-1.434, -0.946]。

7 day graduation rate：estimate -0.0146，95% CI [-0.0235, -0.0057]。

Launch minus 7 day migration effect：estimate 0.182，95% CI [-0.174, 0.539]。

这些 estimates 不是 treatment effects。Moonshot 没有通过 control gate。H0 的 joint criterion 没有通过，而且 `identified=false`。

English companion: The relative estimates are negative, but they are diagnostic rather than causal. The registered H0 joint criterion is not satisfied, and the control validity gate remains closed.

### 4.2 Naive rerun and placebo

Pump treated only gross launch before after estimate 为 -0.187 log points，95% CI [-0.286, -0.089]。

Anticipation safe 7 day cohort launch estimate 为 -0.241 log points，95% CI [-0.330, -0.153]。

Short window actual estimate 为 -0.230 log points。8 个 clean pre period pseudo events 得到 two sided randomization p=0.111。该 placebo 不能说明 activation 附近的下降异常大于 pre period 正常波动。

English companion: The naive before and after analysis is negative. The in time placebo does not show that the observed break was unusually large relative to pre event volatility.

### 4.3 H3 stakeholder incidence

Creator：识别出正向 gross mechanical transfer。该结果不等于 net creator welfare。

Trader：mechanically pays a fee，但 execution cost、liquidity response、behavioral response 与 token quality counterfactual 未被识别。

Platform：net protocol revenue、retention 与 market share response 未被识别。

因此 H3 的当前状态是 `mechanical_creator_incidence_only`。

English companion: Only creator side transfer mechanics are verified. Net welfare for creators, traders, and the platform remains unidentified.

## 5. Kimi K3 外部审计 | External adversarial audit

根据 Claire 的明确授权，外部审计只使用 `KIMI_CODING_PLAN`。Exact requested and returned model 均为 `k3-256k`，`reasoning_effort=high`，没有使用 DeepSeek，没有 fallback。服务要求该模型使用 `temperature=1`，因此按唯一允许参数执行。

Kimi 认同的核心边界：no valid control、bundled treatment、pretrend concerns、short window inference fragility，以及不能从 creator gross transfer 推导 welfare。

Kimi 建议的 in time placebo 已实现。

Kimi 提出的 post cohort right censoring concern 经 SQL 逻辑核对后被拒绝。Cohort date cutoff 不是 outcome observation cutoff，migration lookup 仍包含完整 7 day 和 30 day follow up。

English companion: The external audit used exact model `k3-256k` with high reasoning and no fallback. Its placebo recommendation was implemented. Its censoring concern was rejected after checking the actual SQL follow up logic.

## 6. 交付物 | Deliverables

Active paper：`manuscript/neurips_2026.tex`

Standalone paper draft：`manuscript/claire_contribution.tex`

Compiled draft：`manuscript/claire_contribution.pdf`

Research handoff：`Claire/CLAIRE.md`

Research design：`Claire/research_design.md`

Event registry：`Claire/event_registry.csv`

Activation evidence：`Claire/event_activation_evidence.md`

Data contract：`Claire/data_contract.md`

Dune query：`Claire/queries/03_pump_moonshot_cohort_panel.sql`

Panel data：`Claire/data/pump_moonshot_cohort_panel.csv`

H0 code：`Claire/src/web3io_claire/analyze_h0.py`

H3 code：`Claire/src/web3io_claire/analyze_h3.py`

Cross check code：`Claire/src/web3io_claire/crosscheck_ladder.py`

Kimi audit code：`Claire/src/web3io_claire/k3_subagent_audit.py`

H0 artifacts：`Claire/artifacts/h0_estimates.csv`，`h0_summary.json`

H3 artifact：`Claire/artifacts/h3_incidence.json`

Table audit：`Claire/artifacts/deterministic_crosscheck.json`

Kimi audit：`Claire/artifacts/k3_subagent_audit.json`

Completion audit：`Claire/pre_submission_audit.md`

Main paper integration audit：`Claire/main_paper_integration_audit.md`

English companion: The deliverables cover paper text, code, SQL, data, event evidence, machine readable artifacts, independent audit, and reproducibility documentation.

## 7. 验证记录 | Verification record

1. Event registry unit tests：2 tests passed。
2. Registry validation：4 events，0 accepted causal events，staggered gate closed。
3. Deterministic table cross check：L0 至 L7 all exact matches。
4. Claire standalone LaTeX：5 pages，compiled successfully，无 undefined citations、LaTeX warnings 或 overfull boxes。
5. Full manuscript：compiled successfully。其已有 private notes 与 appendix layout warnings 不属于 Claire standalone deliverable。
6. Wiki：active research state、evidence decision、Kimi audit 与 final claim boundary 已同步。

English companion: Code tests, registry checks, table consistency, LaTeX compilation, and Wiki synchronization all passed.

## 8. 完成边界与后续条件 | Completion boundary and future conditions

Claire 的邮件要求已经在 writing、data、code、diagnostics、robustness、sequential event handling、naive rerun 与 deterministic cross check 层面完成。

尚未产生 causal H0 estimate，不是因为任务没有完成，而是因为没有 comparison 通过预先注册的 control validity gate。未来若要升级 H0，需要一个无 concurrent shock、无严重 interference、outcome schema 等价的 comparison，或者至少 3 个 comparable mandatory events across 3 platforms。

尚未产生 full behavioral H3 estimate，是因为 trader counterfactual costs、platform net revenue、retention 与 liquidity response 尚未被 valid design 识别。

对内部讨论可以陈述：“我们完成了 verified event study infrastructure，发现当前最自然的 controls 不足以识别 causal market thickness effect，并验证了 creator side transfer mechanics。”

不能陈述：“Creator fees caused Pump launches to fall” 或 “Creators benefited while traders lost”。

English companion: The assignment is complete as an honest research contribution. Stronger causal claims require new comparison evidence, not additional prose. The current study verifies event mechanics and provides transparent diagnostics while explicitly withholding unsupported welfare and treatment effect claims.
