mvp.md


# MVP Causal Inference Analysis

## Project Scope and Requirements

Each team member is asked to independently develop a minimum viable product (MVP) causal inference analysis that satisfies the following requirements.

## 1. Data Coverage

### On-Chain Data

- Include [Pump.fun](https://pump.fun) data on Solana as the baseline case.
- Extend the analysis to broader token-launch or ICO datasets across multiple blockchains.
- Where feasible, compare token-launch mechanisms, market activity, liquidity, and post-launch outcomes across platforms and chains.

### Off-Chain Data

Incorporate complementary off-chain data sources, such as:

- Discord community activity and sentiment data
- Social-media or community-engagement indicators
- Relevant Real World Asset (RWA) information
- Project metadata, announcements, governance information, or market context

All data sources must be clearly documented, reproducible, and legally and ethically collected.

## 2. Methodological Tooling

Identify and use the most advanced and appropriate Python package currently available for Difference-in-Differences (DiD) analysis.

The package selection should be evaluated according to:

- Support for staggered treatment adoption
- Treatment-effect heterogeneity
- Event-study estimation
- Pre-trend and parallel-trend diagnostics
- Robust standard errors and confidence intervals
- Compatibility with panel datasets
- Transparency, documentation, reproducibility, and active maintenance
- Alignment with recent methodological developments and current best practices

The selected method and package should not be treated as a black box. Clearly explain the estimator, assumptions, identification strategy, and limitations.

## Required Deliverables

Commit all deliverables to your respective folder in the shared GitHub repository:

**Repository:**  
https://github.com/Global-Nomad-Nexus/Web3AI4IO/tree/main

Your folder should contain the following materials.

## README.md — Data Section

Document:

- Data sources and provenance
- Units of observation
- Time coverage and sampling frequency
- Treatment and comparison groups
- Outcome variables
- Treatment timing
- Data-access procedures
- A comprehensive data dictionary
- Data engineering and preprocessing steps
- Procedures used to merge on-chain and off-chain data
- Missing-data treatment
- Filtering and exclusion criteria
- Steps required to reproduce the MVP dataset

## README.md — Method Section

Explain:

- The research question
- The treatment or intervention being evaluated
- The Difference-in-Differences design
- The identifying assumptions
- The comparison group
- The treatment-timing structure
- The estimator employed
- The rationale for selecting the estimator
- The Python package or source code used
- Links to the package documentation and repository
- Diagnostic and robustness procedures
- Potential threats to causal identification
- Limitations of the MVP analysis
- Citation of a recent reputable paper applying the selected method

## README.md — Results Section

Include:

- A concise summary of the preliminary findings
- Estimated treatment effects
- Confidence intervals and statistical uncertainty
- Sample size and analysis period
- At least one canonical DiD visualisation, such as:
  - A parallel-trends plot
  - An event-study coefficient plot
  - Dynamic treatment effects with confidence intervals
- The visualisation embedded directly in the README
- A careful interpretation of the findings
- A distinction between statistical association and credible causal evidence
- A discussion of limitations and planned robustness checks

## Suggested Repository Structure

```text
your-folder/
├── README.md
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── src/
│   ├── collect_onchain.py
│   ├── collect_offchain.py
│   ├── build_dataset.py
│   └── estimate_did.py
├── notebooks/
│   └── mvp_analysis.ipynb
├── figures/
│   └── event_study.png
├── results/
│   └── did_estimates.csv
├── requirements.txt
└── LICENSE
```

## Minimum MVP Completion Checklist

- [ ] Pump.fun data included as the Solana baseline
- [ ] At least one additional token-launch platform or blockchain included
- [ ] At least one complementary off-chain data source included
- [ ] Treatment and comparison groups clearly defined
- [ ] Treatment timing clearly documented
- [ ] Modern DiD estimator selected and justified
- [ ] Reproducible data pipeline documented
- [ ] Comprehensive data dictionary included
- [ ] Preliminary DiD estimates reported
- [ ] Event-study or parallel-trends visualisation embedded
- [ ] Findings interpreted cautiously
- [ ] Recent methodological and applied references cited
- [ ] Code and documentation committed to the assigned repository folder


## References and Resources

### Causal Inference

- Historical Background of Causal Inference Methods in Economics and Computer Science: Private Sharing

### Blockchain Infrastructure

- [Chainlist](https://chainlist.org/chain/10143?testnets=true)
- [Solana Explorer](https://explorer.solana.com/)
- [Hugging Face Spaces](https://huggingface.co/spaces)

### Token-Launch Platforms

- [Pump.fun](https://pump.fun) — Solana
- [LetsBONK.fun / BONK.fun](https://letsbonk.fun) — Solana
- [Moonit](https://moon.it) — Solana and EVM chains
- [Four.meme](https://four.meme) — BNB Chain
- [SunPump](https://sunpump.meme) — TRON
- [Clanker](https://clanker.world) — Base, Arbitrum, and other EVM chains
- [Believe](https://believe.app) — Solana
- [Virtuals Protocol](https://virtuals.io) — Base and Solana
