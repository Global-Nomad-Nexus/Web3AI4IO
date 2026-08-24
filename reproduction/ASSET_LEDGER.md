# Asset and licensing ledger

All paper charts and diagrams are generated from project data and code. No external icons, photographs, illustrations, or proprietary visual assets are used.

| Asset family | Source | License or status | Export command |
|---|---|---|---|
| Empirical figures | `reproduction/generate_figures.py` and archived evidence objects | Original project output | `make figures` |
| Conceptual overview | `reproduction/figures/teaser_figure.tex` with counts generated from `reproduction/scope.json` | Original project output; no external visual assets | `python reproduction/build_teaser.py` exports PDF, SVG, and PNG |
| LaTeX tables | `reproduction/generate_tables.py` or `reproduction/source_ledger.md` | Original project output; cited literature remains under source terms | `make tables` |

The shared plotting configuration is `reproduction/theme.py`. Empirical figures use DejaVu Sans through Matplotlib under its bundled permissive font license. The standalone conceptual overview uses Latin Modern Sans from TeX Live.
