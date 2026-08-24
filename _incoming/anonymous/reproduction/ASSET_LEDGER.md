# Asset and licensing ledger

All paper charts and diagrams are generated from project data and code. No external icons, photographs, illustrations, or proprietary visual assets are used.

| Asset family | Source | License or status | Export command |
|---|---|---|---|
| Empirical figures | `reproduction/generate_figures.py` and archived evidence objects | Original project output | `make figures` |
| Conceptual overview | `reproduction/generate_figures.py` and archived evidence objects | Original project output | `make figures` exports SVG, PDF, and PNG |
| LaTeX tables | `reproduction/generate_tables.py` or `reproduction/source_ledger.md` | Original project output; cited literature remains under source terms | `make tables` |

The shared plotting configuration is `reproduction/theme.py`. DejaVu Sans is used through Matplotlib under its bundled permissive font license.
