# Asset and licensing ledger

All paper charts and diagrams are generated from project data and code. No external icons, photographs, illustrations, or proprietary visual assets are used. No generative raster assets are used.

| Asset family | Source | License or status | Export command |
|---|---|---|---|
| All nine paper figures | `reproduction/generate_figures.py` | Original project output; PDF canonical, SVG native text, PNG 300 dpi | `make figures` |
| Figure 1 semantic spec | `reproduction/figures/teaser_pipeline.yaml` | Original project output | `make figures` |
| Figure 1 Draw.io master | `reproduction/figures/teaser_figure.drawio` | Original project output | `make figures` |
| LaTeX tables | `reproduction/generate_tables.py` or `reproduction/source_ledger.md` | Original project output; cited literature remains under source terms | `make tables` |

The shared plotting configuration is `reproduction/theme.py` (Scholar Blue 1.1.0). Arial is a system font at `/System/Library/Fonts/Supplemental/Arial.ttf` (macOS Supplemental).
