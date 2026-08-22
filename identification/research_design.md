# identification study research design

Status: approved design direction, 2026-08-02

This study started from the now archived legacy manuscript and the assignment in `records/0730-did-improve.docx`. The current paper is `paper/neurips_2026.tex`. The previous MVP is excluded from the research design. It is not a baseline, data source, event source, result source, or prior for expected findings.

## Role in the paper

The paper evaluates whether causal claims about token launch platform design survive a transparent identification protocol and whether an AI agent follows that protocol when its evidence scaffold changes.

identification's contribution has two linked roles.

1. A substantive platform economics study tests H0 and H3 with newly collected platform rule events and newly constructed lifecycle outcomes.
2. The same claims become real world evaluation cases for the deterministic and agentic arms. A small known truth calibration set separately evaluates causal correctness. Real world estimates are not treated as ground truth.

This separation preserves the paper's three pillars: platform economics defines the claims, causal econometrics defines admissible evidence, and AI evaluation measures protocol compliance and error against cases with known answers.

## Hypotheses

### H0: market thickness

Stronger creator side participation incentives, through lower entry costs or higher creator subsidies, increase gross market thickness, but the increase in quality adjusted thickness is smaller because marginal launches are less likely to graduate, survive, or sustain liquidity.

Gross thickness outcomes are launches, unique creators, active traders, and tokens with at least one trade. Quality adjusted thickness outcomes are graduation within a fixed horizon, post graduation survival, persistent trading, trader breadth, and liquidity at fixed horizons.

The treatment must change an observable creator net participation incentive, such as an entry cost, listing requirement, or creator revenue share. A generic platform launch is not automatically eligible because it can bundle entry cost, branding, liquidity, migration, and marketing changes.

### H3: governance and cross side redistribution

Governance rules that change graduation, migration, trader protection, or fee incidence can improve one platform side while imposing costs on another, so aggregate activity can conceal opposing stakeholder effects.

Creator outcomes are launch participation, unique creators, graduation probability, time to graduation, and creator revenue. Trader outcomes are active traders per token, trading persistence, liquidity, holder concentration, execution costs, and harm incidence. Platform outcomes are fee revenue and sustainable activity when those fields can be measured consistently. Mechanical transfers, behavioral responses, and net welfare are separate claims.

H1 characterizes the platform's cross side pricing architecture. H3 asks who receives and who pays when a dated rule changes, and whether net responses can be identified. This boundary prevents a gross transfer from being mislabeled as welfare and prevents H1 and H3 from making the same contribution.

## Event families

The event registry contains two separate treatment families.

1. Entry incentive events include fee reductions, waived creation fees, creator subsidy changes, relaxed eligibility, and comparable changes that alter the net payoff from creating or listing a token.
2. Governance events include graduation threshold changes, migration eligibility changes, liquidity lock requirements, mandatory fee allocation changes, anti bot rules, and quality screening changes.

Events from different families are never pooled as one staggered treatment. Events within a family are pooled only if the rule mechanism and outcome definitions are comparable.

## Event eligibility gate

An event enters the causal sample only if all of the following are satisfied.

1. A first party source states the rule and its effective time.
2. An onchain transaction, contract version, program instruction, or archived interface provides an independent activation reference when technically possible.
3. The outcome has the same meaning before and after the event.
4. The event has enough pre and post observations for the registered horizon.
5. At least one credible comparison unit is untreated during the clean event window.
6. Announced anticipation and concurrent platform or chain shocks are recorded.
7. Repeated events inside the window are either excluded or modeled explicitly.

The registry records rejected events and exclusion reasons. Event selection must not depend on the sign or significance of an estimated effect.

## Units, panels, and horizons

The primary panel is platform by day. Token cohorts are assigned by creation date and evaluated at fixed 7 day and 30 day horizons so that lifecycle completion is not mechanically distorted by unequal exposure time. Gross cohorts use April 17 through May 7 and May 14 through June 3. Seven-day quality pre cohorts end on April 30, and 30-day quality pre cohorts end on April 7, so their outcome horizons cannot cross the May 8 anticipation boundary. Migration lookup extends beyond the cohort-date cutoff. Raydium LaunchLab was rejected because it began operating on April 15 and therefore confounds the event with platform maturation. Moonshot supplies an exact diagnostic comparison but is not a valid causal control because of concurrent product changes and interference between competitors.

The minimum common schema contains platform, chain, calendar date, rule state, launches, unique creators, unique traders, tokens traded, fixed horizon graduations, fixed horizon active tokens, fixed horizon liquidity, and a concurrent shock indicator. Wallet level and trade level records are retained only when needed to compute the registered aggregates.

Daily data are primary. Weekly aggregation is a sensitivity analysis rather than a replacement estimand.

## Identification protocol

Selection into timing is an identification threat, not H0.

1. Declare the treatment family, unit, outcome, horizon, target population, and group time ATT before estimation.
2. Use not yet treated or clean window comparison units. Never use already treated units as controls without an estimator that explicitly supports treatment histories.
3. Diagnose anticipation and differential pre trends with event time estimates and substantive timing evidence.
4. Use a heterogeneity robust group time or stacked event estimator selected for the realized treatment structure.
5. Treat repeated and overlapping rules as sequential treatments. Use event specific clean windows or a multiple treatment design rather than a single absorbing indicator.
6. Report few cluster uncertainty, leave one platform out results, alternative control pools, placebo dates, and negative control outcomes.
7. Report functional form and parallel trends sensitivity. A non significant pretrend test is not evidence that parallel trends holds.
8. Report right censoring rules and fixed horizon denominators for lifecycle outcomes.

If the registry yields too few comparable events, Result 2 becomes a set of transparent event specific estimates. It will not present an invalid pooled staggered estimate merely to preserve the current Introduction wording.

The preferred low burden design has two feasibility paths. Path A uses staggered adoption only if at least three comparable mandatory events are verified across at least three platforms with a common outcome schema. Path B uses one strongly verified platform wide event with a comparative interrupted time series, synthetic control, or matched token cohort design. Path B is preferable to pooling incomparable rules.

## Identification ladder

The linear ladder changes identification support while keeping the claim, sample definition, outcome, horizon, and decision rule fixed.

1. L0 uses a treated only before and after comparison.
2. L1 adds a contemporaneous comparison group.
3. L2 adds unit and calendar time effects in a conventional two way fixed effects specification.
4. L3 replaces the pooled estimator with a heterogeneity robust group time or stacked estimator.
5. L4 evaluates event-time pretrends and anticipation diagnostics against the already registered five-day exclusion; it does not redefine the sample after seeing outcomes.
6. L5 adds sequential event handling and the concurrent shock registry.
7. L6 adds honest few cluster inference.
8. L7 adds the registered sensitivity envelope, including functional form, parallel trends sensitivity, placebo dates, and negative controls.

Stakeholder measurement is a separate axis, not an identification rung. The deterministic and agentic arms receive the same claim and evidence at each rung.

The paper may show the linear ladder for interpretability, but component attribution requires at least a leave one component out analysis from L7. A conclusion change along one fixed order is not described as the unique causal contribution of that component.

## Minimal known truth calibration

The benchmark includes a small reproducible calibration set generated from empirical covariate and outcome distributions after the real data schema is fixed. It contains known null effects, homogeneous effects, heterogeneous effects, anticipation, and repeated treatment cases. Sixteen cases are sufficient for the first complete version because they require no manual annotation and directly test sign, interval coverage, estimand choice, treatment timing, control validity, and decision accuracy.

The real platform cases measure external validity and substantive economic effects. The calibration cases measure whether deterministic and agentic pipelines recover known answers.

## Data infrastructure decision

### Primary layer: Dune

Dune is the default discovery and extraction layer. Its current official catalog reports raw, decoded, and curated data across more than 100 chains, including raw and decoded coverage for Solana, Base, BNB, and Tron. Its Data API can execute saved queries, retrieve results, manage uploads, and materialize intermediate views.

We will store query SQL, query identifiers, retrieval timestamps, source table names, hashes of exported analysis inputs, and small analysis ready outputs. We will not copy full chain history into the repository.

Official references:

https://docs.dune.com/data-catalog/overview

https://docs.dune.com/api-reference/api-overview

### Targeted fallback: Bitquery or Helius

Bitquery is used only when a launchpad lifecycle field is expensive to reconstruct from general tables. Its official Pump.fun interface exposes token creation, creator identity, bonding curve progress, graduation related trades, first buyers, holders, liquidity, and historical trading fields. Its broader interface covers Solana, BNB, Base, and Tron through GraphQL and historical datasets.

https://docs.bitquery.io/docs/blockchain/Solana/Pumpfun/Pump-Fun-API/

https://docs.bitquery.io/docs/intro/

Helius is a Solana only fallback for targeted transaction history, decoded instructions, and validation of specific program addresses. It is not the primary cross chain source.

https://www.helius.dev/docs

### Escalation layer: Goldsky

Goldsky supports BNB, Solana, and Tron and can stream decoded contract or program events into PostgreSQL, ClickHouse, or object storage. It is appropriate if Dune cannot reproduce a required lifecycle table or if the project later needs a maintained data pipeline. We do not deploy it during event discovery because that would add infrastructure before the identification sample is known.

https://docs.goldsky.com/chains/supported-networks

https://docs.goldsky.com/mirror/introduction

### Explicitly deferred

We do not begin with self hosted archive nodes, a custom indexer, real time streams, or a warehouse. These solve scale and latency problems that the first causal design does not yet have. They become justified only after an accepted event fails the Dune and targeted API feasibility checks.

No Dune, Bitquery, or Helius API credential was available in the local environment on 2026-08-02. The public Dune catalog is readable without login, but running and exporting a new schema query requires a signed in account or API credential. Event discovery and schema design continue without credentials; no paid resource is needed until the accepted event set is known.

## identification deliverables mapped to the design

1. Related work positions staggered adoption, heterogeneous effects, sequential treatments, honest inference, and sensitivity around the launchpad identification gap.
2. H0 and H3 use the definitions in this memo after event feasibility is checked.
3. Pillar 3 presents the identification protocol and its named failure modes.
4. The independent identification draft of Section 2.2 specifies the identification ladder, measurement axis, real world cases, and known truth calibration boundary.
5. Result 2 reports the event registry, H0 estimates, H3 estimates, sequential event handling, and robustness envelope.
6. Result 3 contributes the identification ladder, deterministic results, and component omission analysis.
7. Both LaTeX tables must read deterministic conclusions from one generated result artifact so agreement is structural rather than a manual proofreading task.

## Immediate execution order

1. Populate the event registry from first party policy records and onchain activation evidence.
2. Run a Dune schema feasibility query for every candidate event before downloading large data.
3. Lock the accepted event set, outcomes, horizons, comparison rules, and estimators.
4. Only then implement extraction and estimation.
5. Update the Introduction, H0, H3, Pillar 3, Section 2.2, and Result 2 after the design is empirically feasible.
