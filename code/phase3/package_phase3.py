"""Create Phase 3 findings and availability report after QA passes."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd

R = locate("phase3/results")


def md(frame, columns=None):
    x = frame if columns is None else frame[columns]
    def fmt(value):
        if pd.isna(value): return ""
        if isinstance(value, (float, np.floating)): return f"{value:.6g}"
        return str(value)
    return "| " + " | ".join(x.columns) + " |\n| " + " | ".join(["---"] * len(x.columns)) + " |\n" + "\n".join("| " + " | ".join(fmt(v) for v in row) + " |" for row in x.itertuples(index=False, name=None))


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    checks = json.loads((locate("phase3/qa/checks.json")).read_text())
    if not checks or not all(row["passed"] for row in checks):
        raise RuntimeError("Phase 3 QA has not passed")
    comp = pd.read_csv(locate("phase3/results/structured_vs_random_summary.csv"))
    chars = pd.read_csv(locate("phase3/results/slower_group_characteristics.csv"))
    plaus = pd.read_csv(locate("phase3/results/solved_uplift_plausibility.csv"))
    m6 = pd.read_csv(locate("phase3/results/structured_averaging_definition_sensitivity.csv"))
    emissions = pd.read_csv(locate("phase3/results/placement_emissions_summary.csv"))
    dec = pd.read_csv(locate("phase3/results/structured_decomposition_summary.csv"))
    manifest = json.loads((locate("phase3/provenance/phase3_manifest.json")).read_text())
    exact = chars[chars.statistic.eq("exact")].copy()
    random_median = chars[(chars.design.eq("random")) & (chars.statistic.eq("P50"))]
    high = comp[comp.design.eq("high_vmt")]
    infra = comp[comp.design.eq("infrastructure_first")]
    low = comp[comp.design.eq("low_vmt")]
    if not (len(comp) == 36 and (comp.n_replicates == 500).all()):
        raise RuntimeError("Incomplete structured comparison")
    if not (comp.structured_shift_relative_to_random_interval != "inside").all():
        raise RuntimeError("Unexpected interval classification")
    high20 = high[high.slowdown_pct.eq(20)]
    if not (high20.crz_change_pct_p50 > 0).all():
        raise RuntimeError("High-VMT 20% interpretation changed")

    empirical = """# Empirical speed data availability

The existing project was searched locally for NPMRDS, NYC DOT, MTA, Geotab, probe-speed, and year-specific speed files. No external search was performed.

## Finding

No existing file provides a segment- or corridor-level 2024-versus-2025 truck/commercial speed-change distribution suitable for an observed Phase 3 placement calibration.

The project does contain:

- `data/assignment_link_detail.csv` and `data/emissions_assignment_link_detail.csv`: modeled link geometry, truck VMT, roadway class, and period-specific baseline speeds. These are the frozen freight baseline, not observed before/after speed changes.
- `freight_model_moves5_2025/evidence/existing_speed_groups.csv`: the model's roadway-period speed groups. It documents the existing fixed baseline inputs rather than a segment-level 2024/2025 comparison.
- `MTA CRZ data analysis/`: observed CRZ vehicle-entry counts from January 2025 through January 2026, including time, entry point, origin, and vehicle class. The documented data are counts, not segment travel speeds, and do not supply a 2024 pre-period.
- NYC truck-route and assignment GIS files: network geography and assigned modeled traffic, without observed commercial probe-speed changes.

## Suitability

The MTA entry data can support volume and fleet-composition validation, but cannot calibrate the spatial placement or magnitude of speed responses. The modeled link files can provide a crosswalk framework for a future probe dataset. A later empirical scenario would require, at minimum, segment/corridor identifiers or mappable geometry, comparable 2024 and 2025 periods, commercial/truck vehicle identification, time-of-day coverage aligned to 08:00–18:00, and documented speed statistics. No empirical distribution was invented or merged into Phase 3.
"""
    (locate("phase3/EMPIRICAL_SPEED_DATA_AVAILABILITY.md")).write_text(empirical, encoding="utf-8")

    char_table = exact[["design", "roadway_length_share", "analysis_window_vmt_share", "mean_baseline_speed_mph", "vmt_weighted_baseline_speed_mph", "street_length_share", "bridge_length_share", "tunnel_length_share", "ramp_length_share"]].copy()
    for col in ["roadway_length_share", "analysis_window_vmt_share", "street_length_share", "bridge_length_share", "tunnel_length_share", "ramp_length_share"]:
        char_table[col] *= 100
    random_vmt = random_median.analysis_window_vmt_share.min() * 100, random_median.analysis_window_vmt_share.max() * 100
    result_table = comp[["design", "slowdown_pct", "pollutant", "crz_change_pct_p50", "structured_shift_pp", "structured_shift_relative_to_random_interval", "solved_faster_pct_p50", "attenuation_pct_p50"]]
    high_plaus = plaus[plaus.design.eq("high_vmt")][["slowdown_pct", "solved_faster_pct_p05", "solved_faster_pct_p50", "solved_faster_pct_p95", "solved_faster_pct_max", "min_scenario_speed_mph_p05", "max_scenario_speed_mph_p95", "vmt_share_above_40_mph_p50", "vmt_share_above_50_mph_p50", "vmt_share_above_60_mph_p50", "uplift_above_40_flag"]].copy()
    for col in ["vmt_share_above_40_mph_p50", "vmt_share_above_50_mph_p50", "vmt_share_above_60_mph_p50"]: high_plaus[col] *= 100
    m6_table = m6[["averaging_definition", "slowdown_pct", "pollutant", "solved_faster_pct_p50", "crz_change_pct_p50", "difference_from_vmt_primary_pp_p50"]]
    high_dec = dec[(dec.design.eq("high_vmt"))][["slowdown_pct", "pollutant", "faster_group_delta_kg_p50", "slower_group_delta_kg_p50", "offset_ratio_p50", "street_attenuation_gap_kg_p50", "highway_family_attenuation_gap_kg_p50", "lt20_attenuation_gap_kg_p50", "gt50_attenuation_gap_kg_p50"]]

    findings = [
        "# Phase 3 findings",
        "**Phase 3 QA passed. Classification: B — structured placement materially changes the result, while the nonlinear offset mechanism survives. M5 is fully resolved for the specified structured designs. M4 is partially resolved because the magnitude and spatial correlation remain stylized and no observed segment-level calibration dataset is available.**",
        "All primary results use the frozen Phase 1B MOVES5 surface, full-day denominator, 08:00–18:00 intervention, EV fractions, road mapping, whole physical roads, and a +5.6% VMT-weighted mean-speed constraint. P05–P95 are empirical distributions across 500 faster/unchanged allocations, not confidence intervals. Phase 3 master seed 20261003 is independent of the Phase 1B random experiment.",
        "## 1. Slower-group exposure",
        f"Random placement captures a median {random_vmt[0]:.2f}–{random_vmt[1]:.2f}% of intervention-window VMT across the four slowdown-specific allocation sets. The exact structured slower sets capture 36.55% under high-VMT placement, 23.85% under infrastructure-first placement, and 1.74% under the low-VMT bound.",
        md(char_table),
        "The high-VMT slower set contains 139 Street segments. Infrastructure-first contains every eligible Bridge, Ramp, and Tunnel physical segment plus 71 highest-VMT Street segments. The low-VMT bound contains 681 whole segments. Their achieved slower length shares are 16.1345%, 16.2015%, and 16.1871%, respectively, versus the 16.1616% target.",
        "## 2. Required balancing uplifts",
        "The required median faster-road uplift rises from 26.01% to 45.03% across the high-VMT slowdown cases, compared with approximately 17.11% to 23.59% in the random reference. Infrastructure-first requires 20.27% to 31.22%; the low-VMT bound requires only 13.02% to 13.66%.",
        md(high_plaus),
        "These are implied balancing speed gains required to preserve the +5.6% aggregate benchmark; they are not observed speed changes. High-VMT placement exceeds the 40% flag in some 15% cases and throughout the upper part of the 20% distribution. The 20% high-VMT maximum is 48.97%, which is a substantive plausibility limitation even though resulting speeds remain inside the 2.5–75 mph MOVES interpolation range.",
        "## 3–6. Emissions results and structured shifts",
        md(result_table),
        "High-VMT placement materially weakens the emissions reductions at every slowdown. At 20% slowdown its medians cross zero: +0.0014% CO2, +0.0214% NOx, and +0.0286% PM2.5. The P05–P95 ranges straddle zero for CO2 and NOx and mostly straddle zero for PM2.5, so the median reversal is small relative to the remaining faster/unchanged allocation variation. At 5–15%, all high-VMT medians remain reductions.",
        "Infrastructure-first also attenuates benefits more than random placement but remains negative for every pollutant and slowdown. At 20%, its medians are −0.6512% CO2, −1.1120% NOx, and −0.7884% PM2.5. The low-VMT bound strengthens the benefit and remains negative throughout.",
        "All 36 structured medians lie outside the matching random P05–P95 placement ranges: high-VMT and infrastructure-first are above them (less favorable), while low-VMT is below them (more favorable). Therefore the exact spatial correlation matters more than the random-allocation intervals suggested.",
        "## 7. Does the central conclusion survive?",
        "No, not literally across every structured scenario. It survives all infrastructure-first and low-VMT cases and the high-VMT 5%, 10%, and 15% cases. The high-VMT 20% median changes direction for all three pollutants, although the changes are close to zero and require median balancing gains of 45.03%. This is why classification B is more defensible than A; classification C would require evidence that this stylized extreme placement and uplift are empirically plausible.",
        "## 8. Structural uncertainty",
        "The structured shifts range from +0.0173 to +1.4259 percentage points for the less favorable designs and from −0.0834 to −0.7571 points for the favorable low-VMT bound. These shifts exceed the corresponding random P05–P95 intervals in every comparison. Random faster/unchanged allocation remains relevant, but the placement of the slower set is the larger uncertainty examined here.",
        "## 9. M6 averaging-definition sensitivity",
        md(m6_table),
        "The averaging definition becomes important under high-VMT placement. Length-weighted and equal-segment constraints require substantially smaller faster-road uplifts than the VMT-weighted benchmark because the slower set is deliberately correlated with freight VMT. Yet emissions are still evaluated over the frozen freight activity, so these definitions yield weaker benefits and earlier reversals. For example, at 10% slowdown the equal-segment medians are already +0.0447% CO2, +0.0657% NOx, and +0.0500% PM2.5, versus negative results under the VMT-weighted primary. M6 is therefore not a negligible definition check under structured placement and must be reported as a sensitivity.",
        "## 10. Plausibility",
        "High-VMT 15% and 20% cases trigger the >40% faster-uplift flag. Infrastructure-first and low-VMT cases never do. Median VMT above 50 mph remains about 0.026–0.028% in the structured scenarios, and high-VMT median VMT above 60 mph reaches only 0.026% at 15–20%; thus the limitation is the implied magnitude of balancing gains, not broad high-speed VMT exposure.",
        "## Compact structured decomposition",
        md(high_dec),
        "Positive slower-group changes increasingly offset faster-group reductions. The compact attenuation-gap columns retain signed contributions; opposing signs can cancel. This table was calculated within each realization before quantiles.",
        "## 11. Empirical calibration availability",
        "No existing project file contains a mappable 2024-versus-2025 segment-level commercial-speed comparison. MTA data provide 2025–2026 vehicle-entry counts, while the Geotab/model evidence provides fixed baseline speed groups rather than before/after segment changes. See [EMPIRICAL_SPEED_DATA_AVAILABILITY.md](EMPIRICAL_SPEED_DATA_AVAILABILITY.md).",
        "## 12–14. Reviewer classifications",
        "**M4/M5 classification: B. Structured placement materially changes the result but the mechanism survives.** The slower/faster offset remains present and grows when high freight exposure is assigned to the slower group; at the most severe high-VMT case it is large enough to erase the median benefit.",
        "**M5 is fully resolved for the specified random, high-VMT, infrastructure-first, and low-VMT designs.** Whole-segment placements, fixed slower sets, 500 paired faster/unchanged allocations, emissions decompositions, and feasibility checks are all preserved.",
        "**M4 is partially resolved because magnitude remains stylized.** Phase 3 directly establishes sensitivity to spatial correlation, but no observed segment-level speed-response dataset is available to determine which structured case is closest to NYC's actual response. The high-VMT stress test must not be described as observed.",
        "## QA and scope",
        f"Phase 1B reproduction maximum error was {manifest['phase1b_reproduction_max_abs_error']:.6g}. All 1,689 physical segments were assigned exactly once; no Non-Physical link entered the pool. Constraint, VMT, and emissions closure passed; scenario speeds stayed within 6.4–67.03 mph. The frozen rate-surface SHA-256 is `{manifest['rate_surface_sha256']}`. No MOVES run or manuscript edit occurred.",
        "## Deliverables",
        "- [QA report](PHASE3_QA_REPORT.txt)\n- [Structured versus random summary](results/structured_vs_random_summary.csv)\n- [Slower-group characteristics](results/slower_group_characteristics.csv)\n- [Structured decomposition](results/structured_decomposition_summary.csv)\n- [Averaging-definition sensitivity](results/structured_averaging_definition_sensitivity.csv)\n- [Solved-uplift plausibility](results/solved_uplift_plausibility.csv)\n- [Figure data](results/structured_placement_figure_data.csv)\n- [Empirical speed-data availability](EMPIRICAL_SPEED_DATA_AVAILABILITY.md)",
    ]
    (locate("phase3/PHASE3_FINDINGS.md")).write_text("\n\n".join(findings) + "\n", encoding="utf-8")
    readme = """# Phase 3: structured slower-road placement

Phase 3 evaluates high-VMT, infrastructure-first, and low-VMT slower-road sets using the frozen Phase 1B MOVES5 engine. Start with [PHASE3_FINDINGS.md](PHASE3_FINDINGS.md) and [PHASE3_QA_REPORT.txt](PHASE3_QA_REPORT.txt).

The accepted random reference is carried from Phase 1B. Structured slower sets use whole Phase 1B physical roads and remain fixed across 500 random faster/unchanged allocations. New master seed: 20261003. Share fields in CSV outputs are fractions unless their name explicitly contains `pct`.

`code/run_phase3.py` reproduces the reference, constructs placements, evaluates emissions, and performs core QA. `code/package_phase3.py` creates findings only after QA passes. Source hashes and frozen allocation files are in `provenance/`. No MOVES run, manuscript revision, or Phase 1B/Phase 2R modification is part of this package.
"""
    (locate("phase3/README.md")).write_text(readme, encoding="utf-8")
    requested = ["PHASE3_QA_REPORT.txt", "PHASE3_FINDINGS.md", "results/structured_vs_random_summary.csv", "results/slower_group_characteristics.csv", "results/structured_decomposition_summary.csv", "results/structured_averaging_definition_sensitivity.csv", "results/solved_uplift_plausibility.csv", "results/structured_placement_figure_data.csv", "EMPIRICAL_SPEED_DATA_AVAILABILITY.md"]
    if not all(locate(f"phase3/{name}").exists() for name in requested):
        raise RuntimeError("Missing requested deliverable")
    source = json.loads((locate("phase3/provenance/source_sha256.json")).read_text())
    if not all(Path(path).exists() and digest(path) == value for path, value in source.items()):
        raise RuntimeError("Frozen sources changed during packaging")
    qa_text = (locate("phase3/PHASE3_QA_REPORT.txt")).read_text(encoding="utf-8")
    marker = "FINAL PACKAGING AUDIT"
    if marker not in qa_text:
        qa_text += "\nFINAL PACKAGING AUDIT\nPASS All requested deliverables exist.\nPASS Findings were generated only after core QA passed.\nPASS All frozen Phase 1B and Phase 2R files remain unchanged after packaging.\n"
        (locate("phase3/PHASE3_QA_REPORT.txt")).write_text(qa_text, encoding="utf-8")
    output = {display(path): digest(path) for path in phase_files("phase3") if path.name != "output_manifest.json" and "__pycache__" not in path.parts}
    (locate("phase3/provenance/output_manifest.json")).write_text(json.dumps({"status": "completed", "phase": 3, "requested_deliverables": requested, "outputs": output}, indent=2), encoding="utf-8")
    print("Phase 3 findings and final package completed.")


if __name__ == "__main__":
    main()
