# Freight Emissions Sensitivity to Spatially Uneven Truck-Speed Changes in New York City's Congestion Relief Zone

Code and derived results for the Transport Findings paper by Megh Bahadur KC and Sujata Basnet: how far the spatial pattern of truck-speed changes can move modeled CRZ freight running emissions (MOVES5) when the same +5.6% average speed gain is preserved.

**Citation:** KC, M. B., & Basnet, S. (2026). *Freight Emissions Sensitivity to Spatially Uneven Truck-Speed Changes in New York City's Congestion Relief Zone*. Transport Findings. DOI: to be added. Code and data: Zenodo DOI to be added.

## Included and not included

Included: the analysis code used for the paper, the MOVES5 RunSpecs and rate tables, and the aggregated results behind every table and figure. The freight assignment and the segment-level inputs derived from it are proprietary and not included; they are available from the authors on request, subject to the data owner's terms ([inputs/README.md](inputs/README.md) lists them). MOVES5 (U.S. EPA) is needed only to regenerate the rate tables.

## Quick start

Python 3.14 with the pinned packages in `requirements.txt`:

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt   # Windows: .venv\Scripts\activate
python verify/verify_reported_numbers.py        # checks Tables 1-2 and key text values against results/
CRZ_INPUTS=/path/to/inputs python code/phase5/run_all.py   # needs the inputs available on request
```

## Contents

| Folder | What it holds | Paper |
|---|---|---|
| `code/paths.py` | Where every file lives; `CRZ_INPUTS` points to the excluded inputs | — |
| `code/phase1b/`, `rates/`, `provenance/` | MOVES5 setup, rate surfaces, scenario engine, uniform and random runs | Methods; SI S1-S5 |
| `code/phase2/`, `results/phase2/` | Mechanism and high-speed checks (`repaired/` holds the corrected attribution) | SI S6 |
| `code/phase3/`, `results/phase3/` | Structured placement and average-speed definitions | Table 2; Figure 2; SI S7-S8 |
| `code/phase4/`, `results/figures_tables/` | Table 1 (percentages) and Figure 1-2 data; Figure 2 image | Table 1; Figures 1-2 |
| `code/phase5/`, `results/phase5/` | Revision analyses: baseline speeds, unchanged roads, 15-20% step, absolute values (Table 1 kg/day); QA (`qa/checks.json`) and SI table drafts (`si_tables/`) | Table 1; SI S10, S12-S15 |
| `results/phase1b/` | Uniform and random results, source-composition, curve-shape and road-mapping sensitivity | Table 1; SI S3-S5 |
| `code/excerpts/` | Baseline speed profiles and the random allocation routine from the upstream freight model | Methods; SI S2, S5 |
| `verify/` | `verify_reported_numbers.py` | Tables 1-2; text |

The published Figure 1 uses the same data (`results/figures_tables/Figure1_data.csv`) with revised styling; `build_figures_tables.py` reproduces the data and an earlier layout of the figure.

The scenario scripts (`code/phase1b/run_scenarios.py`, `code/phase2/run_phase2.py`, `code/phase5/run_all.py`) need the inputs available on request. `code/phase1b/legacy_qa.py` and `code/phase3/run_phase3.py` also need the assignment and the upstream freight model, and the MOVES preparation scripts need MOVES5 and local MOVES database helpers that are not included.

**Seeds:** 20261002 (random placement), 20261003 (structured placement), 20261104 (unchanged-road draws). Runs are deterministic.

## License and contact

Code: MIT ([LICENSE](LICENSE)). Data and results: CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)). Corresponding author: Megh Bahadur KC.