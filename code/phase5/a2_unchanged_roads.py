"""A2 (R1.2): nonzero change on "unchanged" roads, and allocation length-share diagnostics."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from p5_core import *

FIXED = [-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0]  # 0 is a control that must reproduce Table 1/2.
RANGES = [2.0, 3.0, 5.0]
DESIGNS = ["random", "high_vmt"]
TARGET_SHARES = np.array([37.0, 46.0, 16.0]) / 99.0


def scenario_runs(checks):
    exp = make_experiment()
    model = Model(exp)
    designs = load_designs()
    zero = model.run(np.ones(exp.n_seg))
    checks.add("Zero-change test", max(abs(zero[f"{p}_delta_kg_per_day"]) for p in POLS) <= 1e-10, "kg/day delta is zero")
    # One draw matrix from the recorded seed: U(-1, 1) per replicate and physical segment,
    # scaled to each half-range, so the +/-2, +/-3 and +/-5% cases share common random numbers.
    draws = np.random.default_rng(A2_SEED).uniform(-1.0, 1.0, size=(500, exp.n_seg))
    np.savez_compressed(locate("phase5_revision/qa/a2_unchanged_draws.npz"), unit_draws=draws, seed=np.array(A2_SEED))
    cases = [(f"fixed_{v:+g}pct", "fixed", v, None) for v in FIXED] + [(f"random_within_pm{r:g}pct", "random_draw", None, r) for r in RANGES]
    rows, closure = [], 0.0
    for case, kind, fixed_pct, half_range in cases:
        for design in DESIGNS:
            groups, seeds = designs[design]
            for li, slow in enumerate(SLOWS):
                for rep in range(500):
                    group = groups[li, rep]
                    unch = fixed_pct / 100 if kind == "fixed" else draws[rep] * half_range / 100
                    gain = solve_gain(exp.exposure, group, slow, unch)
                    multiplier = segment_multiplier(group, gain, slow, unch)
                    closure = max(closure, constraint_error_pp(exp.exposure, multiplier))
                    rows.append(dict(case=case, case_type=kind, fixed_unchanged_change_pct=fixed_pct, random_half_range_pct=half_range, design=design, slowdown_pct=slow, replicate=rep, seed=int(seeds[li, rep]), draw_seed=A2_SEED if kind == "random_draw" else None, gain_pct=gain, **model.run(multiplier)))
        print(case, "done", flush=True)
    frame = pd.DataFrame(rows)
    checks.add("+5.6% closure including unchanged term", closure <= 1e-10, f"{closure:.3e} pp")
    checks.add("VMT closure", np.abs(frame.scenario_vmt - exp.vmt.sum()).max() <= 1e-7, "scenario VMT equals analysis VMT")
    checks.add("No clipping or extrapolation", frame.clipped_vmt.max() == 0 and frame.min_scenario_speed_mph.min() >= SPEEDS[0] and frame.max_scenario_speed_mph.max() <= SPEEDS[-1], f"speed range {frame.min_scenario_speed_mph.min():.3f}-{frame.max_scenario_speed_mph.max():.3f} mph")
    uniform = exp.uniform(model.state)
    summary = summarize(frame, ["case", "case_type", "design", "slowdown_pct"], lambda r, p: uniform[f"crz_{p}_change_pct"])
    control = summary[summary.case.eq("fixed_+0pct")]
    saved = pd.read_csv(locate("phase3/results/placement_emissions_summary.csv"))
    merged = control.merge(saved, on=["design", "slowdown_pct", "pollutant"], suffixes=("", "_saved"), validate="one_to_one")
    difference = float(np.abs(merged.crz_change_pct_p50 - merged.crz_change_pct_p50_saved).max())
    checks.add("Zero-unchanged control equals submitted medians", difference <= 1e-9, f"max abs diff {difference:.3e} pp")
    frame.drop(columns=["scenario_vmt"]).to_csv(locate("phase5_revision/results/a2_replicates.csv"), index=False)
    summary.to_csv(locate("phase5_revision/results/a2_summary.csv"), index=False)
    return summary


def legacy_assignment(lengths, seed):
    """Re-implements assign_groups_by_length to test the written description of it."""
    rng = np.random.default_rng(int(seed))
    order = np.argsort(rng.random(len(lengths)), kind="stable")
    ordered = lengths[order]
    midpoint = np.cumsum(ordered) - 0.5 * ordered
    cuts = np.cumsum(TARGET_SHARES)[:2] * lengths.sum()
    group = np.empty(len(lengths), dtype=np.int8)
    group[order] = np.where(midpoint <= cuts[0], FAST, np.where(midpoint <= cuts[1], UNCH, SLOW))
    return group


def allocation_diagnostics(checks):
    data = np.load(locate("phase1b/qa/paired_allocations.npz"))
    groups, seeds = data["groups"], data["seeds"]
    segments = pd.read_csv(locate("phase1b/qa/physical_segments.csv")).sort_values("physical_idx")
    checks.add("Physical index is positional", np.array_equal(segments.physical_idx, np.arange(len(segments))), len(segments))
    lengths = segments.crz_length.to_numpy(float)
    rows, matches = [], 0
    for li, slow in enumerate(SLOWS):
        for rep in range(500):
            shares = 100 * np.bincount(groups[li, rep], weights=lengths, minlength=3) / lengths.sum()
            deviation = shares - 100 * TARGET_SHARES
            rows.append(dict(slowdown_pct=slow, replicate=rep, seed=int(seeds[li, rep]), faster_length_share_pct=shares[0], unchanged_length_share_pct=shares[1], slower_length_share_pct=shares[2], faster_abs_deviation_pp=abs(deviation[0]), unchanged_abs_deviation_pp=abs(deviation[1]), slower_abs_deviation_pp=abs(deviation[2]), n_faster_segments=int((groups[li, rep] == FAST).sum()), n_unchanged_segments=int((groups[li, rep] == UNCH).sum()), n_slower_segments=int((groups[li, rep] == SLOW).sum())))
            matches += int(np.array_equal(legacy_assignment(lengths, seeds[li, rep]), groups[li, rep]))
    frame = pd.DataFrame(rows)
    frame.to_csv(locate("phase5_revision/results/a2_allocation_shares.csv"), index=False)
    out = []
    for label, column, share in [("faster", "faster", TARGET_SHARES[0]), ("unchanged", "unchanged", TARGET_SHARES[1]), ("slower", "slower", TARGET_SHARES[2])]:
        deviation = frame[f"{column}_abs_deviation_pp"]
        achieved = frame[f"{column}_length_share_pct"]
        out.append(dict(group=label, target_length_share_pct=100 * share, achieved_share_pct_min=achieved.min(), achieved_share_pct_p50=achieved.median(), achieved_share_pct_max=achieved.max(), abs_deviation_pp_p50=deviation.median(), abs_deviation_pp_p95=deviation.quantile(0.95), abs_deviation_pp_max=deviation.max(), n_allocations=len(frame)))
    out = pd.DataFrame(out)
    out.to_csv(locate("phase5_revision/results/a2_allocation_diagnostics.csv"), index=False)
    print(out.to_string(index=False))
    checks.add("Written algorithm regenerates the frozen allocations", matches == 2000, f"{matches} of 2000 allocations regenerated exactly from their seeds", hard=False)
    return out


def main():
    checks = Checks("a2")
    summary = scenario_runs(checks)
    allocation_diagnostics(checks)
    checks.save()
    show = summary[summary.pollutant.eq("CO2") & summary.slowdown_pct.eq(20.0)][["case", "design", "crz_change_pct_p50", "crz_change_pct_p05", "crz_change_pct_p95", "gain_pct_p50", "min_scenario_speed_mph", "max_scenario_speed_mph"]]
    print(show.sort_values(["design", "case"]).to_string(index=False))


if __name__ == "__main__":
    main()
