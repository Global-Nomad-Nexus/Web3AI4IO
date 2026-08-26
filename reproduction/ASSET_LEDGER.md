# Asset and licensing ledger

All paper charts and diagrams are generated from project data and code. No external icons, photographs, illustrations, or proprietary visual assets are used.

| Asset family | Source | License or status | Export command |
|---|---|---|---|
| Empirical figures | `reproduction/generate_figures.py` and archived evidence objects | Original project output | `make figures` |
| Conceptual overview | Original draw.io, SVG, and PNG sources in `reproduction/figures/teaser_figure_original.*`; cropped vector print source in `teaser_figure_print.html` | Original project output; no external visual assets; original ratio retained on a 297 mm-wide cropped canvas | `python reproduction/build_teaser.py --paper-dir ../paper` exports vector PDF, SVG, and 300 dpi PNG variants |
| LaTeX tables | `reproduction/generate_tables.py` or `reproduction/source_ledger.md` | Original project output; cited literature remains under source terms | `make tables` |

The shared plotting configuration is `reproduction/theme.py`. Empirical figures use DejaVu Sans through Matplotlib under its bundled permissive font license. The conceptual overview preserves its original Inter/Helvetica/Arial font stack; the vector PDF embeds the available Helvetica fallback.
