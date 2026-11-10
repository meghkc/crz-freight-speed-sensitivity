"""STEP 0: reproduce the submitted numbers with the frozen engine before anything new."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from p5_core import *

SUBMITTED = {  # Values quoted in the Phase 5 brief.
    "uniform": {"CO2": -1.1685, "NOx": -2.2923, "PM25": -1.6287},
    "random_20": {"CO2": -0.773, "NOx": -1.404, "PM25": -1.006},
    "high_20": {"CO2": 0.0014, "NOx": 0.0214, "PM25": 0.0286},
    "high_gain_20": 45.03,
    "crz_baseline_kg": {"CO2": 70880.2, "NOx": 205.58, "PM25": 3.024},
}


def main():
    checks = Checks("step0")
    exp = make_experiment()
    state = exp.setup("primary", "base", "primary")
    designs = load_designs()
    saved_uniform = pd.read_csv(locate("phase1b/results/moves_uniform_benchmark.csv")).set_index("pollutant")
    saved_random = pd.read_csv(locate("phase1b/results/moves_heterogeneous_replicates.csv")).sort_values(["slowdown_pct", "replicate"]).reset_index(drop=True)
    saved_summary = pd.read_csv(locate("phase1b/results/moves_heterogeneous_summary.csv"))
    saved_struct = pd.read_csv(locate("phase3/results/structured_replicates.csv"))
    saved_place = pd.read_csv(locate("phase3/results/placement_emissions_summary.csv"))
    rows = []

    def compare(block, slow, pol, metric, reproduced, saved, tolerance=1e-9):
        rows.append({"block": block, "slowdown_pct": slow, "pollutant": pol, "metric": metric, "reproduced_value_metric_units": reproduced, "saved_value_metric_units": saved, "abs_difference_metric_units": abs(reproduced - saved), "tolerance_metric_units": tolerance})

    uniform = exp.uniform(state)
    baseline_tolerance = {"CO2": 0.05, "NOx": 0.005, "PM25": 5e-4}
    for pol in POLS:
        compare("uniform", 0.0, pol, "crz_change_pct", uniform[f"crz_{pol}_change_pct"], saved_uniform.loc[pol, "crz_change_pct"])
        compare("uniform", 0.0, pol, "delta_kg_per_day", uniform[f"{pol}_delta_kg"], saved_uniform.loc[pol, "delta_kg"])
        compare("uniform_vs_brief", 0.0, pol, "crz_change_pct", uniform[f"crz_{pol}_change_pct"], SUBMITTED["uniform"][pol], 5e-5)
        compare("crz_baseline_vs_brief", 0.0, pol, "crz_baseline_kg_per_day", uniform[f"crz_{pol}_baseline_kg"], SUBMITTED["crz_baseline_kg"][pol], baseline_tolerance[pol])

    # Random: re-solve the gain from scratch and compare every replicate with the saved files.
    groups = designs["random"][0]
    gain_err, legacy_gain_err, closure, frame = 0.0, 0.0, 0.0, []
    for li, slow in enumerate(SLOWS):
        saved_level = saved_random[saved_random.slowdown_pct.eq(slow)].reset_index(drop=True)
        legacy_level = exp.legacy_reps[exp.legacy_reps.slowdown_pct.eq(slow)].reset_index(drop=True)
        for rep in range(500):
            gain = solve_gain(exp.exposure, groups[li, rep], slow)
            gain_err = max(gain_err, abs(gain - saved_level.solved_faster_pct[rep]))
            legacy_gain_err = max(legacy_gain_err, abs(gain - legacy_level.solved_faster_pct[rep]))
            closure = max(closure, constraint_error_pp(exp.exposure, segment_multiplier(groups[li, rep], gain, slow)))
            frame.append(dict(slowdown_pct=slow, replicate=rep, **exp.run_one(state, groups[li, rep], gain, slow)))
    frame = pd.DataFrame(frame)
    for pol in POLS:
        for col in [f"crz_{pol}_change_pct", f"{pol}_delta_kg"]:
            compare("random_all_replicates", 0.0, pol, col + "_max_abs_diff", float(abs(frame[col] - saved_random[col]).max()), 0.0)
        for slow in SLOWS:
            level = frame[frame.slowdown_pct.eq(slow)]
            expected = saved_summary.query("slowdown_pct == @slow and pollutant == @pol").crz_change_pct_p50.iloc[0]
            compare("random_median", slow, pol, "crz_change_pct_p50", level[f"crz_{pol}_change_pct"].median(), expected)
        compare("random_vs_brief", 20.0, pol, "crz_change_pct_p50", frame[frame.slowdown_pct.eq(20)][f"crz_{pol}_change_pct"].median(), SUBMITTED["random_20"][pol], 5e-4)

    # Structured designs, including infrastructure-first, against Phase 3.
    for design in ["high_vmt", "infrastructure_first"]:
        groups = designs[design][0]
        for li, slow in enumerate(SLOWS):
            level = []
            for rep in range(500):
                gain = solve_gain(exp.exposure, groups[li, rep], slow)
                closure = max(closure, constraint_error_pp(exp.exposure, segment_multiplier(groups[li, rep], gain, slow)))
                level.append(dict(gain=gain, **exp.run_one(state, groups[li, rep], gain, slow)))
            level = pd.DataFrame(level)
            ref = saved_struct.query("design == @design and slowdown_pct == @slow")
            for pol in POLS:
                saved = ref[ref.pollutant.eq(pol)].sort_values("replicate").reset_index(drop=True)
                gain_err = max(gain_err, float(abs(level.gain - saved.solved_faster_pct).max()))
                compare(f"{design}_all_replicates", slow, pol, "crz_change_pct_max_abs_diff", float(abs(level[f"crz_{pol}_change_pct"] - saved.crz_change_pct).max()), 0.0)
                expected = saved_place.query("design == @design and slowdown_pct == @slow and pollutant == @pol").crz_change_pct_p50.iloc[0]
                compare(f"{design}_median", slow, pol, "crz_change_pct_p50", level[f"crz_{pol}_change_pct"].median(), expected)
                if design == "high_vmt" and slow == 20.0:
                    compare("high_vmt_vs_brief", slow, pol, "crz_change_pct_p50", level[f"crz_{pol}_change_pct"].median(), SUBMITTED["high_20"][pol], 5e-5)
            if design == "high_vmt" and slow == 20.0:
                compare("high_vmt_vs_brief", slow, "all", "gain_pct_p50", level.gain.median(), SUBMITTED["high_gain_20"], 5e-3)

    out = pd.DataFrame(rows)
    out["passed"] = out.abs_difference_metric_units <= out.tolerance_metric_units
    out.to_csv(locate("phase5_revision/results/step0_reproduction.csv"), index=False)
    print(out.groupby("block").abs_difference_metric_units.max().sort_values(ascending=False).to_string())

    checks.add("Gain formula reproduces legacy solved_faster_pct (random)", legacy_gain_err <= 2e-13, f"max abs diff {legacy_gain_err:.3e} pp")
    checks.add("Gain formula reproduces saved gains (all designs)", gain_err <= 2e-13, f"max abs diff {gain_err:.3e} pp")
    checks.add("+5.6% closure on frozen allocations", closure <= 1e-10, f"{closure:.3e} pp")
    failures = out[~out.passed]
    saved_only = out[~out.block.str.contains("brief")]
    checks.add("All Step 0 comparisons within tolerance", failures.empty, failures.to_dict("records") if len(failures) else f"{len(out)} comparisons; max diff vs saved files {saved_only.abs_difference_metric_units.max():.3e}")
    zero = exp.run_one(state, np.zeros(exp.n_seg, dtype=np.int8), 0, 0)
    checks.add("Zero-change test", max(abs(zero[f"{p}_delta_kg"]) for p in POLS) <= 1e-10, "base profile")

    # The new evaluator must match the frozen run_one before it is trusted for A2/A3.
    model = Model(exp)
    worst = 0.0
    for li, slow in enumerate(SLOWS):
        for rep in range(0, 500, 50):
            group = designs["random"][0][li, rep]
            gain = solve_gain(exp.exposure, group, slow)
            mine = model.run(segment_multiplier(group, gain, slow))
            frozen = exp.run_one(state, group, gain, slow)
            worst = max(worst, max(abs(mine[f"{p}_delta_kg_per_day"] - frozen[f"{p}_delta_kg"]) for p in POLS))
    checks.add("Cell-level evaluator equals frozen run_one", worst <= 1e-8, f"max abs diff {worst:.3e} kg/day")
    speed = np.array([2.5, 3.1, 7.7, 10.0, 21.3, 49.9, 75.0])
    pair = np.zeros(len(speed), dtype=int)
    ref = np.stack([interpolate(model.y[:1], np.array([s]))[0] for s in speed])
    checks.add("linear_rates equals engine.interpolate", np.abs(linear_rates(model.y, pair, speed) - ref).max() <= 1e-12, "spot speeds")
    checks.save()


if __name__ == "__main__":
    main()
