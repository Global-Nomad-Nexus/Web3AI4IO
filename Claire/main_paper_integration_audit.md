# Main paper integration audit

Audit date: 2026-08-02. Scope: Claire-owned content in `manuscript/neurips_2026.tex`, following `records/0730-did-improve.docx`.

## Outcome

Claire's verified contribution is integrated into the active manuscript. The main LaTeX source compiles successfully to a 23-page PDF with no undefined references or citations. Visual inspection of pages 10 through 12 confirms that the event registry, estimates table, and rule-event ladder fit within the page and remain legible.

## Claim audit

No Claire result is presented as an identified causal treatment effect. The manuscript states that Pump.fun economic activation and gross creator transfer mechanics are verified. It also states that Moonshot fails the causal control gate, H0 is unsupported as a comparative diagnostic, and net creator, trader, and platform welfare remain unidentified.

The main reported diagnostics reproduce the machine-readable artifacts: gross launches `-0.966`, gross unique creators `-0.685`, seven-day launches `-1.008`, seven-day migrations `-1.190`, the launch-minus-migration contrast `0.182`, the Pump.fun-only rerun `-0.187`, and the in-time placebo `p=0.111`.

## Assignment trace

The manuscript now contains Claire's related-work positioning, H0 and H3 definitions, Method Pillar 3, independent benchmark design, Result 2 data and estimates, robustness judgments, sequential-event distinction, naive rerun, and the L0 through L7 rule-event ladder. The deterministic parser confirms exact agreement across all eight shared-table decision cells.

## Remaining paper-level blockers outside Claire's scope

### CRITICAL

None found in Claire's empirical claims or integration.

### MAJOR

The active full paper still contains private notes and placeholder author information owned by the shared manuscript workflow. These must be removed before submission. Existing sentence-connector dashes in non-Claire sections conflict with the project writing convention and need a paper-wide edit.

### MINOR

The log contains existing overfull boxes in headings, figures, and the prompt appendix. Claire's new tables do not produce new overfull-box warnings. Bibliography entries `defillama` and `ritteripo` have empty years, and `makarovschoar2022` has a number without a volume.

## Verification commands

```text
latexmk -pdf -interaction=nonstopmode -halt-on-error neurips_2026.tex
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m web3io_claire.crosscheck_ladder
```
