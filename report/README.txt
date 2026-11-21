OVERLEAF PROJECT

Revised edition: exactly 20 pages including the cover and three appendices.
The layout keeps related explanations, figures and tables in coherent blocks.
The expanded query-mix table is an analytical model from existing batch costs;
it is labelled separately from measured benchmark throughput.

Upload the complete ZIP through Overleaf > New Project > Upload Project.
Set main.tex as the Main document and use pdfLaTeX (TeX Live 2024 or newer).
Recompile; BibTeX is handled by Overleaf. No shell escape is required.

main.tex + sections/*.tex are editable text. Figures are vector PDFs, with PNG
previews where useful. Tables and numeric macros were generated from the
included CSV data. The PDF was compiled and visually inspected before delivery.

This report preserves the authors/institution/course information from the
supplied previous report. Measured results, archived results, and literature
reference values are labelled separately. The exact host/container setup and
source/data checksums are under reproducibility/ and data/.
source_manifest.json describes the final packaged code; the separately named
source_manifest_run_start.json is the earlier execution snapshot.

To regenerate report figures and tables after new measurements, use the
updated code ZIP: python3 scripts/make_research_assets.py --out <this folder>.
Requires numpy, pandas and matplotlib. Compilation does not require
Python or the benchmark datasets. Large generated .bin datasets are omitted;
commands, seeds, exact audits and hashes are retained for reproduction.
