# Pump.fun to PumpSwap Research Report

## Overview

This report summarizes my Pump.fun to PumpSwap research package. The project asks whether the move from Pump.fun's original graduation path to the PumpSwap migration regime improved post-graduation market persistence. The empirical answer is deliberately cautious. A simple dashboard-style comparison says that activity increased after the migration. A more trustworthy pipeline still finds positive mechanism evidence, but it does not support a broad claim that PumpSwap caused a clean welfare gain for all market participants.

The project began as a Difference-in-Differences MVP. I combined Pump.fun and PumpSwap into a treated "Pump ecosystem" and compared it with Solana DEX controls around March 20, 2025. The first result was useful but incomplete: the static DiD estimate was about 0.412 log points, roughly a 50.9 percent relative increase in daily volume, while the confidence interval crossed zero. That result shaped the later design. Instead of treating the positive estimate as a final answer, I rebuilt the project as a replication and audit package that measures how conclusions change as stronger evidence is added.

![Naive-to-trustworthy conclusion flip](artifacts/figures/fig_ladder_decision_flip_shilin.png)

## Research Motivation

Token launch platforms are not only trading venues. They are market-design institutions that decide who can create tokens, how tokens move into secondary liquidity, and which risks are shifted to retail traders. Pump.fun is especially important because it reduced the cost of token creation to nearly zero and generated a very large token lifecycle system. In the RED-PUMP data used in this package, there are 832,941 matched launches, but only 1,651 graduate. This creates a sharp research problem: a platform can increase activity while also producing a very thin graduation funnel.

For that reason, my research question is not simply whether volume rose. The more precise question is whether the PumpSwap migration created evidence of post-graduation persistence that survives controls, diagnostics, and stakeholder interpretation. This distinction matters because aggregate volume is an imperfect proxy. It can rise during a broader Solana market cycle, and it cannot show whether creators, traders, or reviewers face different outcomes.

## Methodology

The core method is an L0 to L7 evidence ladder. L0 is the naive before-after comparison. It only compares Pump ecosystem volume in the 90 days before and after the event. L1 adds Solana DEX controls. L2 adds protocol and date fixed effects. L3 estimates a dynamic event-study view. L4 checks pre-trends. L5 moves below aggregate volume to token-level heterogeneity and risk proxies. L6 applies exact Rademacher wild-cluster inference because the market panel has only four protocol clusters. L7 interprets the result through a stakeholder metric battery.

This ladder is my main methodological contribution. It makes trustworthiness observable. Rather than saying that robustness matters in general, the package records where the conclusion changes. In this case, the naive L0 estimate is strongly positive, about 0.669 log points. After controls and fixed effects, the estimate remains positive but becomes statistically uncertain. After few-cluster inference, the interval expands substantially and the p-value becomes 0.6875. The result is no longer a simple "yes." It becomes a bounded claim: market activity is directionally positive, but the aggregate design is not strong enough to prove welfare causality.

![Event-study diagnostics](artifacts/figures/fig_event_study_shilin.png)

The project also includes an agentic evaluation arm. DeepSeek is run ten times per rung under controlled prompts. The agent does not replace the statistical model. It is used to test whether an AI research assistant becomes overconfident when evidence is weak, and whether it updates its claims when controls, pre-trend warnings, inference corrections, and stakeholder metrics are added. This is useful because many current research workflows now include AI summaries over raw data. The package treats that behavior as something to evaluate, not as a source of causal proof.

## Data and Validation

The project combines several layers of evidence. DeFiLlama daily volume data supports the market-level DiD. RED-PUMP supplies the token lifecycle table, including launches, graduations, timeouts, and social metadata. HuggingFace Pump.fun snapshots support holder-concentration and risk-proxy analysis. Solana RPC outputs test whether graduated tokens actually show post-migration pool activity. Moralis decoded swap data adds a covered-token sample with wallet-level and USD-valued outcomes. Rendered Dune SQL is included as the registered path for a full indexer export.

This structure is important because each layer has a different claim boundary. The RPC layer can validate venue activity, but it cannot prove USD volume or welfare. The Moralis sample contains decoded swaps, but it is selected toward higher-activity tokens and cannot be generalized to the full cohort. The Dune path remains the stronger future validation layer for full-cohort decoded outcomes.

![H1 mechanism audit](artifacts/figures/fig_h1_mechanism_audit_shilin.png)

## Main Results

The strongest result is mechanism-level. Among 1,651 graduated RED-PUMP tokens, 1,636 have observed 30-day pool activity. This gives a 99.09 percent all-token observed active lower bound. Among tokens with complete 30-day windows, the active share is 100 percent, the median transaction-count proxy is 826, and there are zero temporal-order violations. This supports the claim that PumpSwap operated as an active post-migration liquidity venue for graduated tokens.

The market-level DiD result is weaker. It remains positive, but it is not robust enough to carry the stronger claim that PumpSwap caused broad welfare improvement. The event-study evidence shows positive post-event coefficients, but the pre-trend screen flags risk. With only four protocol clusters, exact wild-cluster inference widens uncertainty. The right interpretation is that the aggregate market evidence is useful as a benchmark and diagnostic, not as standalone proof.

The token-level results also change the story. Graduation is rare, at about 0.198 percent. Tokens with at least one social link graduate at about 0.240 percent, compared with about 0.110 percent for tokens without social links. Telegram metadata has a positive association with graduation, about 1.23 percentage points in the linear probability model. I treat this as a mechanism clue, not a causal estimate, because social links may proxy for project quality or community effort.

For H4, the project finds that high-concentration tokens have a 52.4 percentage point higher probability of receiving a high or critical source-coded risk label. This result is also a proxy association rather than proof of sniper causality. However, it shows why the stakeholder battery matters. More activity can coexist with higher exposure to concentrated token ownership.

![Stakeholder metric battery](artifacts/figures/fig_metric_battery_status_shilin.png)

## Interpretation

The final conclusion is stronger than the original MVP because the project now has a clearer evidence hierarchy. PumpSwap is supported as a functioning post-migration venue, and reduced migration friction is a credible mechanism. At the same time, the market-level causal claim is disciplined by pre-trend risk, few-cluster uncertainty, and the difference between aggregate activity and stakeholder outcomes.

The main academic value of the package is therefore methodological. It shows how a crypto platform claim can move from a naive dashboard result to a reproducible causal audit. The reportable finding is not "PumpSwap worked" in a universal sense. It is that the evidence supports post-migration venue activation, while welfare, price-quality, active-trader, and early-wallet causal claims require full-cohort decoded indexer outcomes.
