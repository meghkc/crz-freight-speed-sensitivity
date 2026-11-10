"""Check every number in manuscript Tables 1-2 and the key text values against results/.

Runs from a clean clone with only the files in this repository (no withheld inputs).
Each reported value is recomputed from the saved result CSVs, rounded the way the
manuscript displays it, and compared as text. Prints PASS/FAIL per number and exits
with status 1 if any check fails.

    python verify/verify_reported_numbers.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RES = REPO / "results"
POLS = ["CO2", "NOx", "PM25"]
RESULTS = []


def csv(rel):
    return pd.read_csv(RES / rel)


def one(frame, **where):
    for key, value in where.items():
        frame = frame[frame[key] == value]
    if len(frame) != 1:
        raise ValueError(f"{where}: {len(frame)} rows")
    return frame.iloc[0]


def fmt(value, spec):
    text = format(value, spec)
    return "0" + text[2:] if text.startswith("-0") and float(text) == 0 else text  # no "-0"


def check(label, expected, value, spec):
    got = fmt(float(value), spec)
    RESULTS.append((got == expected, label, expected, got))


def triple(label, expected, row, column, spec):
    """expected = 'p50 [p05, p95]' as displayed."""
    got = "{} [{}, {}]".format(*(fmt(float(row[f"{column}_{q}"]), spec) for q in ["p50", "p05", "p95"]))
    RESULTS.append((got == expected, label, expected, got))


def text_check(label, expected, got):
    RESULTS.append((got == expected, label, expected, got))


# ------------------------------------------------------------------ sources
uniform = csv("phase1b/moves_uniform_benchmark.csv").set_index("pollutant")
random_summary = csv("phase1b/moves_heterogeneous_summary.csv")
placement = csv("phase3/placement_emissions_summary.csv")
averaging = csv("phase3/structured_averaging_definition_sensitivity.csv")
characteristics = csv("phase3/slower_group_characteristics.csv")
a1 = csv("phase5/a1_summary.csv")
a1_uniform = csv("phase5/a1_uniform.csv")
a2 = csv("phase5/a2_summary.csv")
a2_alloc = csv("phase5/a2_allocation_diagnostics.csv")
a2_seeds = pd.read_csv(RES / "phase5/a2_replicates.csv", usecols=["case_type", "draw_seed"])
a3_subsets = csv("phase5/a3_faster25_subsets.csv")
pchip = csv("phase5/a3_pchip_summary.csv")
baselines = csv("phase5/a4_baselines.csv").set_index("pollutant")
mechanism = csv("phase2/repaired/phase2_reviewer_summary.csv")
vmt = csv("phase1b/qa/vmt_closure.csv").set_index("quantity").value
run_manifest = json.loads((RES / "phase1b/qa/scenario_run_manifest.json").read_text(encoding="utf-8"))
p3_manifest = json.loads((REPO / "provenance/phase3/phase3_manifest.json").read_text(encoding="utf-8"))

# ------------------------------------------------------------------ Table 1
check("Table 1 | Uniform +5.6% | CO2 %", "-1.169", uniform.loc["CO2", "crz_change_pct"], ".3f")
check("Table 1 | Uniform +5.6% | CO2 kg/day", "-828", uniform.loc["CO2", "delta_kg"], ".0f")
check("Table 1 | Uniform +5.6% | NOx %", "-2.292", uniform.loc["NOx", "crz_change_pct"], ".3f")
check("Table 1 | Uniform +5.6% | PM2.5 %", "-1.629", uniform.loc["PM25", "crz_change_pct"], ".3f")
TABLE1 = [  # design, slowdown, gain, CO2 %, CO2 kg/day, NOx %, PM2.5 %
    ("random", 5, "17.11 [16.09, 18.29]", "-1.059 [-1.074, -1.044]", "-751 [-762, -740]", "-1.990 [-2.031, -1.949]", "-1.424 [-1.451, -1.399]"),
    ("random", 10, "19.32 [18.12, 20.64]", "-0.993 [-1.014, -0.971]", "-704 [-719, -688]", "-1.843 [-1.895, -1.787]", "-1.320 [-1.353, -1.285]"),
    ("random", 15, "21.50 [19.95, 23.22]", "-0.929 [-0.955, -0.903]", "-659 [-677, -640]", "-1.698 [-1.762, -1.633]", "-1.219 [-1.263, -1.177]"),
    ("random", 20, "23.59 [21.91, 25.50]", "-0.773 [-0.814, -0.723]", "-548 [-577, -513]", "-1.404 [-1.499, -1.292]", "-1.006 [-1.067, -0.932]"),
    ("high_vmt", 20, "45.03 [42.79, 47.29]", "0.001 [-0.067, 0.065]", "1 [-48, 46]", "0.021 [-0.058, 0.097]", "0.029 [-0.045, 0.093]"),
    ("infrastructure_first", 20, "31.22 [29.82, 32.97]", "-0.651 [-0.663, -0.638]", "-462 [-470, -452]", "-1.112 [-1.146, -1.072]", "-0.788 [-0.809, -0.767]"),
]
for design, slow, gain, co2, co2kg, nox, pm in TABLE1:
    name = f"Table 1 | {design} -{slow}%"
    rows = {p: one(placement, design=design, slowdown_pct=float(slow), pollutant=p) for p in POLS}
    triple(f"{name} | faster-road gain %", gain, rows["CO2"], "solved_faster_pct", ".2f")
    triple(f"{name} | CO2 %", co2, rows["CO2"], "crz_change_pct", ".3f")
    triple(f"{name} | CO2 kg/day", co2kg, rows["CO2"], "delta_kg", ".0f")
    triple(f"{name} | NOx %", nox, rows["NOx"], "crz_change_pct", ".3f")
    triple(f"{name} | PM2.5 %", pm, rows["PM25"], "crz_change_pct", ".3f")

# ------------------------------------------------------------------ Table 2
TABLE2 = [  # definition, slowdown, gain, CO2, NOx, PM2.5 (medians)
    ("vmt_weighted", 5, "26.01", "-0.920", "-1.645", "-1.198"),
    ("vmt_weighted", 10, "32.35", "-0.743", "-1.259", "-0.930"),
    ("vmt_weighted", 15, "38.69", "-0.562", "-0.868", "-0.659"),
    ("vmt_weighted", 20, "45.03", "0.001", "0.021", "0.029"),
    ("road_length_weighted", 5, "17.22", "-0.491", "-0.918", "-0.663"),
    ("road_length_weighted", 10, "19.43", "-0.128", "-0.226", "-0.165"),
    ("road_length_weighted", 15, "21.63", "0.234", "0.466", "0.332"),
    ("road_length_weighted", 20, "23.83", "0.810", "1.521", "1.091"),
    ("equal_segment", 5, "14.82", "-0.372", "-0.719", "-0.515"),
    ("equal_segment", 10, "15.91", "0.045", "0.066", "0.050"),
    ("equal_segment", 15, "16.99", "0.461", "0.851", "0.615"),
    ("equal_segment", 20, "18.07", "1.093", "1.999", "1.444"),
]
for definition, slow, gain, *changes in TABLE2:
    name = f"Table 2 | {definition} -{slow}%"
    rows = {p: one(averaging, averaging_definition=definition, slowdown_pct=float(slow), pollutant=p) for p in POLS}
    check(f"{name} | faster-road gain %", gain, rows["CO2"]["solved_faster_pct_p50"], ".2f")
    for p, expected in zip(POLS, changes):
        check(f"{name} | {p} %", expected, rows[p]["crz_change_pct_p50"], ".3f")

# ------------------------------------------------------------------ key text values
for p, expected in zip(POLS, ["-1.169", "-2.292", "-1.629"]):
    check(f"Text | uniform {p} %", expected, uniform.loc[p, "crz_change_pct"], ".3f")
for p, expected in zip(POLS, ["-0.773", "-1.404", "-1.006"]):
    check(f"Text | random -20% {p} %", expected, one(random_summary, slowdown_pct=20.0, pollutant=p)["crz_change_pct_p50"], ".3f")
for p, expected in zip(POLS, ["33.8", "38.7", "38.2"]):
    check(f"Text | random -20% attenuation {p} %", expected, one(random_summary, slowdown_pct=20.0, pollutant=p)["benefit_attenuation_pct_p50"], ".1f")
for p, expected in zip(POLS, ["+0.001", "+0.021", "+0.029"]):
    check(f"Text | high-VMT -20% {p} %", expected, one(placement, design="high_vmt", slowdown_pct=20.0, pollutant=p)["crz_change_pct_p50"], "+.3f")
check("Text | high-VMT -20% faster-road gain %", "45.03", one(placement, design="high_vmt", slowdown_pct=20.0, pollutant="CO2")["solved_faster_pct_p50"], ".2f")
for p, expected in zip(POLS, ["-0.651", "-1.112", "-0.788"]):
    check(f"Text | infrastructure-first -20% {p} %", expected, one(placement, design="infrastructure_first", slowdown_pct=20.0, pollutant=p)["crz_change_pct_p50"], ".3f")
road_length = one(averaging, averaging_definition="road_length_weighted", slowdown_pct=20.0, pollutant="CO2")
check("Text | road-length weighting -20% gain %", "23.83", road_length["solved_faster_pct_p50"], ".2f")
check("Text | road-length weighting -20% CO2 %", "+0.810", road_length["crz_change_pct_p50"], "+.3f")
check("Text | CRZ baseline CO2 kg/day", "70,880.2", baselines.loc["CO2", "crz_baseline_kg_per_day"], ",.1f")
check("Text | CRZ baseline NOx kg/day", "205.58", baselines.loc["NOx", "crz_baseline_kg_per_day"], ".2f")
check("Text | CRZ baseline PM2.5 kg/day", "3.024", baselines.loc["PM25", "crz_baseline_kg_per_day"], ".3f")
for p in POLS:  # baselines are the same in the Phase 1B uniform benchmark
    check(f"Text | CRZ baseline {p} (Phase 1B copy)", fmt(baselines.loc[p, "crz_baseline_kg_per_day"], ".6f"), uniform.loc[p, "crz_baseline_kg"], ".6f")
random20 = a1[(a1.design == "random") & (a1.slowdown_pct == 20.0)]
for p, expected in zip(POLS, ["33.8-46.7", "38.7-43.9", "38.2-43.7"]):
    values = random20[random20.pollutant == p].attenuation_pct_p50
    text_check(f"Text | Phase 5 baseline-speed range, random -20% attenuation {p} %", expected, f"{values.min():.1f}-{values.max():.1f}")
for p, expected in zip(POLS, ["-0.171", "-0.081", "-0.120"]):
    check(f"Text | PCHIP high-VMT -20% {p} %", expected, one(pchip, design="high_vmt", slowdown_pct=20.0, pollutant=p)["crz_change_pct_p50"], ".3f")

# ------------------------------------------------------------------ other text values (Abstract, Methods, Findings)
text_check("Abstract | random -20% attenuation range across pollutants and profiles %", "34-47",
           f"{random20.attenuation_pct_p50.min():.0f}-{random20.attenuation_pct_p50.max():.0f}")
check("Methods | assigned truck VMT/day", "609,874", vmt["raw_assignment_VMT"], ",.0f")
check("Methods | CRZ truck VMT/day", "53,979", vmt["CRZ_VMT"], ",.0f")
check("Methods | 8:00-18:00 CRZ VMT/day", "30,286", vmt["analysis_window_CRZ_VMT"], ",.0f")
text_check("Methods | normalized length shares %", "37.37/46.46/16.16",
           "/".join(f"{100 * p3_manifest['target_length_shares'][g]:.2f}" for g in ["faster", "unchanged", "slower"]))
text_check("Methods | physical CRZ roads", "1689", str(p3_manifest["physical_segments"]))
text_check("Methods | allocations per slowdown", "500", str(run_manifest["replicates_per_slowdown"]))
check("Methods | max achieved-share deviation pp", "0.26", a2_alloc.abs_deviation_pp_max.max(), ".2f")
check("Findings | uniform CO2 kg/day", "-828", uniform.loc["CO2", "delta_kg"], ".0f")
check("Findings | uniform NOx kg/day", "-4.71", uniform.loc["NOx", "delta_kg"], ".2f")
check("Findings | uniform PM2.5 g/day", "-49", 1000 * uniform.loc["PM25", "delta_kg"], ".0f")
low = 100 * mechanism.low_speed_lt20_absolute_share_p50
text_check("Findings | <20 mph share of absolute attenuation %", "64-70", f"{low.min():.0f}-{low.max():.0f}")
text_check("Findings | >50 mph share of absolute attenuation below 0.03%", "True", str(bool((100 * mechanism.high_speed_gt50_absolute_share_p50).max() < 0.03)))
flat_cap = max(mechanism.rate_flat_minus_primary_pp_p50.abs().max(), mechanism.hard_cap_minus_primary_pp_p50.abs().max())
text_check("Findings | rate-flat / hard-cap change at most about 0.002 pp", "True", str(bool(round(flat_cap, 3) <= 0.002)))
ucols = a1_uniform.uniform_crz_change_pct[a1_uniform.pollutant == "CO2"].abs()
text_check("Findings | uniform CO2 reduction range across Street profiles %", "1.17-1.60", f"{ucols.min():.2f}-{ucols.max():.2f}")
a2_random = a2[(a2.design == "random") & (a2.slowdown_pct == 20.0) & (a2.pollutant == "CO2")].crz_change_pct_p50
text_check("Findings | unchanged-road tests, random -20% CO2 median range %", "-0.653 to -0.820", f"{a2_random.max():.3f} to {a2_random.min():.3f}")
check("Findings | high-VMT slower set length share %", "16.13", 100 * one(characteristics, design="high_vmt")["roadway_length_share"], ".2f")
check("Findings | high-VMT slower set intervention VMT share %", "36.55", 100 * one(characteristics, design="high_vmt")["analysis_window_vmt_share"], ".2f")
check("Findings | high-VMT -20% CO2 kg/day", "+1", one(placement, design="high_vmt", slowdown_pct=20.0, pollutant="CO2")["delta_kg_p50"], "+.0f")
hv = a1[(a1.design == "high_vmt") & (a1.slowdown_pct == 20.0) & a1.profile.isin(["street_x0.8", "street_x1.2"])].crz_change_pct_p50
text_check("Findings | high-VMT -20% range under Street x0.8/x1.2 %", "+0.052 to -0.151", f"{hv.max():+.3f} to {hv.min():.3f}")
for case, expected in [("fixed_-1pct", "+0.068"), ("fixed_+1pct", "-0.050")]:
    check(f"Findings | high-VMT -20% CO2 with {case} on unchanged roads", expected,
          one(a2, case=case, design="high_vmt", slowdown_pct=20.0, pollutant="CO2")["crz_change_pct_p50"], "+.3f")
check("Findings | high-VMT CO2 step with both crossings held fixed pp", "0.18",
      one(a3_subsets, pollutant="CO2", allocation_subset="all_allocations")["mean_step_no_slower_crossing_faster25_anchored_at_10_pp"], ".2f")
text_check("Seeds | random placement", "20261002", str(run_manifest["master_seed"]))
text_check("Seeds | structured placement", "20261003", str(p3_manifest["phase3_master_seed"]))
draws = a2_seeds[a2_seeds.case_type == "random_draw"].draw_seed.unique()
text_check("Seeds | unchanged-road draws", "20261104", ",".join(str(int(s)) for s in draws))

# ------------------------------------------------------------------ report
width = max(len(label) for _, label, _, _ in RESULTS)
for passed, label, expected, got in RESULTS:
    note = "" if passed else f"   (got {got})"
    print(f"{'PASS' if passed else 'FAIL'}  {label:<{width}}  {expected}{note}")
failed = sum(not passed for passed, *_ in RESULTS)
print(f"\n{len(RESULTS) - failed} of {len(RESULTS)} PASS" + ("" if not failed else f"; {failed} FAIL"))
sys.exit(1 if failed else 0)
