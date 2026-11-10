"""Compare Phase 5 results with the cloud pilot values quoted in the brief (flag > 0.002 pp)."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from p5_core import *

LIMIT = 0.002


def median_of(frame, **keys):
    mask = np.logical_and.reduce([frame[c].eq(v) for c, v in keys.items()])
    return frame.loc[mask, "crz_change_pct_p50"].iloc[0]


def main():
    checks = Checks("crosscheck")
    a1, uni = pd.read_csv(locate("phase5_revision/results/a1_summary.csv")), pd.read_csv(locate("phase5_revision/results/a1_uniform.csv"))
    a2, cf = pd.read_csv(locate("phase5_revision/results/a2_summary.csv")), pd.read_csv(locate("phase5_revision/results/a3_counterfactual_summary.csv"))
    pchip = pd.read_csv(locate("phase5_revision/results/a3_pchip_summary.csv"))
    alloc = pd.read_csv(locate("phase5_revision/results/a2_allocation_diagnostics.csv")).set_index("group")
    co2 = dict(pollutant="CO2", slowdown_pct=20.0)
    high_cf = cf[cf.design.eq("high_vmt") & cf.pollutant.eq("CO2")].iloc[0]
    uniform = lambda profile: uni[uni.profile.eq(profile) & uni.pollutant.eq("CO2")].uniform_crz_change_pct.iloc[0]
    items = [
        ("A1", "random -20% CO2, x0.8", -0.852, median_of(a1, profile="street_x0.8", design="random", **co2), "a1_summary.csv"),
        ("A1", "random -20% CO2, x1.2", -0.664, median_of(a1, profile="street_x1.2", design="random", **co2), "a1_summary.csv"),
        ("A1", "uniform CO2, x0.8", -1.597, uniform("street_x0.8"), "a1_uniform.csv"),
        ("A1", "uniform CO2, x1.2", -1.229, uniform("street_x1.2"), "a1_uniform.csv"),
        ("A1", "high-VMT -20% CO2, x0.8", 0.052, median_of(a1, profile="street_x0.8", design="high_vmt", **co2), "a1_summary.csv"),
        ("A1", "high-VMT -20% CO2, x1.2", 0.028, median_of(a1, profile="street_x1.2", design="high_vmt", **co2), "a1_summary.csv"),
        ("A2", "high-VMT -20% CO2, unchanged -3%", 0.202, median_of(a2, case="fixed_-3pct", design="high_vmt", **co2), "a2_summary.csv"),
        ("A2", "high-VMT -20% CO2, unchanged +3%", -0.152, median_of(a2, case="fixed_+3pct", design="high_vmt", **co2), "a2_summary.csv"),
        ("A2", "random -20% CO2, unchanged -3%", -0.653, median_of(a2, case="fixed_-3pct", design="random", **co2), "a2_summary.csv"),
        ("A2", "random -20% CO2, unchanged +3%", -0.820, median_of(a2, case="fixed_+3pct", design="random", **co2), "a2_summary.csv"),
        ("A3", "high-VMT CO2 step -15 to -20", 0.563, high_cf.step_15_to_20_pp, "a3_counterfactual_summary.csv"),
        ("A3", "high-VMT CO2 no-crossing -20%", -0.213, high_cf.no_crossing_slower_median_at_20_crz_change_pct, "a3_counterfactual_summary.csv"),
        ("A3", "high-VMT CO2 PCHIP -20% (500 allocations, PCHIP denominator)", -0.168, median_of(pchip, **co2), "a3_pchip_summary.csv"),
        ("Allocation", "max deviation faster", 0.17, alloc.abs_deviation_pp_max["faster"], "a2_allocation_diagnostics.csv"),
        ("Allocation", "max deviation unchanged", 0.26, alloc.abs_deviation_pp_max["unchanged"], "a2_allocation_diagnostics.csv"),
        ("Allocation", "max deviation slower", 0.16, alloc.abs_deviation_pp_max["slower"], "a2_allocation_diagnostics.csv"),
    ]
    rows = []
    for block, name, pilot, value, source in items:
        decimals = 2 if block == "Allocation" else 3
        rows.append(dict(block=block, item=name, pilot_value_pp=pilot, phase5_value_pp=value, abs_difference_pp=abs(value - pilot), exceeds_0p002_pp=abs(value - pilot) > LIMIT, rounds_to_pilot_value=round(value, decimals) == pilot, source_file=source))
    out = pd.DataFrame(rows)
    out.to_csv(locate("phase5_revision/results/pilot_crosscheck.csv"), index=False)
    print(out.drop(columns="source_file").to_string(index=False))
    conditions = pd.read_csv(locate("phase5_revision/qa/a3_pchip_pilot_conditions.csv")).set_index("condition").co2_crz_change_pct_p50
    pilot_like = conditions["first_100_allocations_linear_denominator"]
    flagged = out[out.exceeds_0p002_pp]
    checks.add("PCHIP pilot conditions reproduce the pilot value", abs(pilot_like + 0.168) <= LIMIT, f"first 100 allocations, linear denominator: {pilot_like:.6f}")
    unexplained = flagged[~flagged.rounds_to_pilot_value & ~flagged.item.str.contains("PCHIP")]
    checks.add("Every pilot difference above 0.002 pp is explained", unexplained.empty, f"{len(flagged)} flagged: " + "; ".join(flagged.item))
    checks.save()


if __name__ == "__main__":
    main()
