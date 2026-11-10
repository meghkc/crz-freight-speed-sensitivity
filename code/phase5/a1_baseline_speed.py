"""A1 (R1.1): Street window-period baseline speeds x0.8 / x1.2, gain re-solved per allocation.

Default run: base_x1.0 (control), street_x0.8, street_x1.2. Pass --include-x07 to add x0.7;
that profile is not run unless asked and writes to separate *_x07 files.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
import argparse
from p5_core import *

DESIGNS = ["random", "high_vmt", "infrastructure_first"]


def run_profile(label, scale, designs, checks):
    exp = make_experiment(scale)
    state = exp.setup("primary", "base", "primary")
    # Guard against the cached-speed trap: the baseline must be evaluated at scaled speeds.
    expected = interpolate(state["y"], exp.pairs.speed_mph.to_numpy(float))
    street = exp.pairs.roadway_type.eq("Street").to_numpy()
    checks.add(f"{label}: baseline rebuilt at scaled speeds", np.array_equal(exp.speed, exp.pairs.speed_mph.to_numpy(float)) and np.abs(state["baseline"] - expected).max() == 0, f"Street speeds {sorted(exp.pairs.speed_mph[street].unique())}")
    night = exp.activity[exp.activity.period.eq("night")].speed_mph
    other = exp.activity[exp.activity.roadway_type.ne("Street") & exp.activity.period.ne("night")]
    reference = pd.read_csv(locate("phase1b/qa/baseline_activity.csv"))
    checks.add(f"{label}: night and non-Street speeds unchanged", np.array_equal(night, reference[reference.period.eq("night")].speed_mph) and np.array_equal(other.speed_mph, reference.loc[other.index, "speed_mph"]), f"{len(night)} night rows, {len(other)} other rows")

    zero = exp.run_one(state, np.zeros(exp.n_seg, dtype=np.int8), 0, 0)
    checks.add(f"{label}: zero-change test", max(abs(zero[f"{p}_delta_kg"]) for p in POLS) <= 1e-10, "kg/day delta is zero")
    uniform = exp.uniform(state)
    closure = constraint_error_pp(exp.exposure, np.full(exp.n_seg, 1.056))
    rows = []
    for design in DESIGNS:
        groups, seeds = designs[design]
        for li, slow in enumerate(SLOWS):
            for rep in range(500):
                group = groups[li, rep]
                gain = solve_gain(exp.exposure, group, slow)
                closure = max(closure, constraint_error_pp(exp.exposure, segment_multiplier(group, gain, slow)))
                result = exp.run_one(state, group, gain, slow)
                record = dict(profile=label, street_speed_scale_ratio=scale, design=design, slowdown_pct=slow, replicate=rep, seed=int(seeds[li, rep]), gain_pct=gain, min_scenario_speed_mph=result["min_scenario_speed"], max_scenario_speed_mph=result["max_scenario_speed"], scenario_vmt=result["affected_vmt"], clipped_vmt=result["clipped_vmt"])
                for pol in POLS:
                    record[f"crz_{pol}_change_pct"] = result[f"crz_{pol}_change_pct"]
                    record[f"{pol}_delta_kg_per_day"] = result[f"{pol}_delta_kg"]
                rows.append(record)
    frame = pd.DataFrame(rows)
    checks.add(f"{label}: +5.6% closure", closure <= 1e-10, f"{closure:.3e} pp")
    checks.add(f"{label}: VMT closure", np.abs(frame.scenario_vmt - exp.vmt.sum()).max() <= 1e-7, f"{np.abs(frame.scenario_vmt - exp.vmt.sum()).max():.3e} VMT")
    checks.add(f"{label}: no clipping or extrapolation", frame.clipped_vmt.max() == 0 and frame.min_scenario_speed_mph.min() >= SPEEDS[0] and frame.max_scenario_speed_mph.max() <= SPEEDS[-1] and state["baseline_crz_clipped_vmt"] == 0, f"speed range {frame.min_scenario_speed_mph.min():.3f}-{frame.max_scenario_speed_mph.max():.3f} mph")
    uni_rows = [dict(profile=label, street_speed_scale_ratio=scale, pollutant=p, uniform_crz_change_pct=uniform[f"crz_{p}_change_pct"], uniform_delta_kg_per_day=uniform[f"{p}_delta_kg"], crz_baseline_kg_per_day=uniform[f"crz_{p}_baseline_kg"], min_scenario_speed_mph=uniform["min_scenario_speed"], max_scenario_speed_mph=uniform["max_scenario_speed"]) for p in POLS]
    return frame, pd.DataFrame(uni_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-x07", action="store_true", help="also run the Street x0.7 profile (not run by default)")
    args = parser.parse_args()
    profiles = dict(OPTIONAL_PROFILES) if args.include_x07 else dict(PROFILES)
    suffix = "_x07" if args.include_x07 else ""
    checks = Checks("a1" + suffix)
    designs = load_designs()
    frames, uniforms = zip(*[run_profile(label, scale, designs, checks) for label, scale in profiles.items()])
    frame, uniform = pd.concat(frames, ignore_index=True), pd.concat(uniforms, ignore_index=True)
    lookup = uniform.set_index(["profile", "pollutant"]).uniform_crz_change_pct
    summary = summarize(frame, ["profile", "design", "slowdown_pct"], lambda r, p: lookup[(r["profile"], p)])
    summary = summary.merge(uniform[["profile", "pollutant", "crz_baseline_kg_per_day"]], on=["profile", "pollutant"], validate="many_to_one")
    frame.drop(columns=["scenario_vmt"]).to_csv(locate(f"phase5_revision/results/a1_replicates{suffix}.csv"), index=False)
    summary.to_csv(locate(f"phase5_revision/results/a1_summary{suffix}.csv"), index=False)
    uniform.to_csv(locate(f"phase5_revision/results/a1_uniform{suffix}.csv"), index=False)
    if not args.include_x07:
        base = summary[summary.profile.eq("base_x1.0")]
        saved = pd.read_csv(locate("phase3/results/placement_emissions_summary.csv"))
        merged = base.merge(saved, on=["design", "slowdown_pct", "pollutant"], validate="one_to_one")
        diff = float(np.abs(merged.crz_change_pct_p50_x - merged.crz_change_pct_p50_y).max())
        checks.add("Base control equals Phase 3 medians", diff <= 1e-9, f"max abs diff {diff}")
    checks.save()
    show = summary[summary.pollutant.eq("CO2") & summary.slowdown_pct.eq(20.0)][["profile", "design", "crz_change_pct_p50", "attenuation_pct_p50", "gain_pct_p50", "min_scenario_speed_mph", "max_scenario_speed_mph"]]
    print(show.to_string(index=False))
    print(uniform[["profile", "pollutant", "uniform_crz_change_pct", "crz_baseline_kg_per_day"]].to_string(index=False))


if __name__ == "__main__":
    main()
