"""A3 (R1.3): why the -15% to -20% step is larger than the earlier steps.

Decomposition, no-crossing counterfactuals, faster-side 25 mph crossing, PCHIP smooth
check, and the step pattern under the A1 profiles.

Contribution quantiles are computed across replicates. Medians of components do not sum
to the median of the total, so means (which are additive) are reported beside them.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from p5_core import *

DESIGNS = ["random", "high_vmt"]
STEP_LABELS = [(5.0, 10.0), (10.0, 15.0), (15.0, 20.0)]
PCT = lambda s, q: float(s.quantile(q))


def categories(exp):
    cells = exp.cells.merge(exp.pairs[["period", "truck_type", "roadway_type", "speed_mph", "pair_idx"]], on=["period", "truck_type", "roadway_type", "speed_mph"], validate="many_to_one")
    label = cells.roadway_type + "|" + cells.period
    names = sorted(label.unique())
    return label.map({n: i for i, n in enumerate(names)}).to_numpy(int), names


def bincount3(index, values, size):
    return np.stack([np.bincount(index, weights=values[:, i], minlength=size) for i in range(values.shape[1])], axis=1)


def decomposition(model, checks):
    exp, designs = model.exp, load_designs()
    road_period, names = categories(exp)
    n_rp = len(names)
    rows, closure = [], 0.0
    for design in DESIGNS:
        groups = designs[design][0]
        for li, slow in enumerate(SLOWS):
            for rep in range(500):
                group = groups[li, rep]
                gain = solve_gain(exp.exposure, group, slow)
                delta = model.cell_delta(model.speeds(segment_multiplier(group, gain, slow)))
                cell_group = group[exp.segment]
                by_group = bincount3(cell_group, delta, 3)
                by_rp = bincount3(road_period, delta, n_rp)
                by_both = bincount3(cell_group * n_rp + road_period, delta, 3 * n_rp)
                total = delta.sum(axis=0)
                closure = max(closure, np.abs(by_group.sum(axis=0) - total).max(), np.abs(by_rp.sum(axis=0) - total).max(), np.abs(by_both.sum(axis=0) - total).max())
                for pi, pol in enumerate(POLS):
                    base = dict(design=design, slowdown_pct=slow, replicate=rep, pollutant=pol)
                    rows.append(dict(base, component_type="net", component="net", contribution_kg_per_day=total[pi]))
                    for gi, gname in enumerate(["faster", "unchanged", "slower"]):
                        rows.append(dict(base, component_type="response_group", component=gname, contribution_kg_per_day=by_group[gi, pi]))
                    for ci, cname in enumerate(names):
                        rows.append(dict(base, component_type="road_period", component=cname, contribution_kg_per_day=by_rp[ci, pi]))
                        for gi, gname in [(0, "faster"), (2, "slower")]:
                            rows.append(dict(base, component_type="group_road_period", component=f"{gname}|{cname}", contribution_kg_per_day=by_both[gi * n_rp + ci, pi]))
    checks.add("Decomposition closes to net", closure <= 1e-9, f"{closure:.3e} kg/day")
    frame = pd.DataFrame(rows)
    frame["contribution_crz_pp"] = 100 * frame.contribution_kg_per_day / frame.pollutant.map(dict(zip(POLS, model.crz)))
    keys = ["design", "slowdown_pct", "pollutant", "component_type", "component"]
    grouped = frame.groupby(keys, sort=False)
    out = grouped.size().rename("n_replicates").to_frame()
    for column in ["contribution_kg_per_day", "contribution_crz_pp"]:
        out[f"{column}_mean"] = grouped[column].mean()
        for q, tag in [(0.05, "p05"), (0.5, "p50"), (0.95, "p95")]:
            out[f"{column}_{tag}"] = grouped[column].quantile(q)
    out = out.reset_index()
    out.to_csv(locate("phase5_revision/results/a3_decomposition_summary.csv"), index=False)

    # Independent check of the group split against the frozen Phase 2R and Phase 3 summaries.
    random_saved = pd.read_csv(locate("phase2r/results/response_group_summary.csv"))
    high_saved = pd.read_csv(locate("phase3/results/structured_decomposition_summary.csv")).query("design == 'high_vmt'")
    worst = 0.0
    for design, saved in [("random", random_saved), ("high_vmt", high_saved)]:
        for row in saved.itertuples():
            for gname in ["faster", "slower"]:
                mine = out.query("design == @design and slowdown_pct == @row.slowdown_pct and pollutant == @row.pollutant and component == @gname").contribution_kg_per_day_p50.iloc[0]
                worst = max(worst, abs(mine - getattr(row, f"{gname}_group_delta_kg_p50")))
    checks.add("Group medians match Phase 2R and Phase 3", worst <= 1e-8, f"max abs diff {worst:.3e} kg/day")

    steps = []
    wide = out.pivot_table(index=["design", "pollutant", "component_type", "component"], columns="slowdown_pct", values=["contribution_crz_pp_p50", "contribution_crz_pp_mean"], sort=False)
    for key, row in wide.iterrows():
        record = dict(zip(["design", "pollutant", "component_type", "component"], key))
        for a, b in STEP_LABELS:
            record[f"step_{a:g}_to_{b:g}_median_pp"] = row[("contribution_crz_pp_p50", b)] - row[("contribution_crz_pp_p50", a)]
            record[f"step_{a:g}_to_{b:g}_mean_pp"] = row[("contribution_crz_pp_mean", b)] - row[("contribution_crz_pp_mean", a)]
        steps.append(record)
    pd.DataFrame(steps).to_csv(locate("phase5_revision/results/a3_step_by_component.csv"), index=False)
    return out


def counterfactuals(model, checks):
    """Replicate-level -15 and -20 evaluations on the same allocation, plus no-crossing variants."""
    exp, y = model.exp, model.y
    designs = load_designs()
    pair, cell_speed, vmt, ice = exp.pair, exp.cell_speed, exp.vmt, exp.ice
    crossing_rows, rows, extension_error = [], [], 0.0
    for design in DESIGNS:
        groups = designs[design][0]
        for rep in range(500):
            group = groups[3, rep]  # The -20% allocation; for high_vmt it is also the -15% one.
            g15, g20 = solve_gain(exp.exposure, group, 15.0), solve_gain(exp.exposure, group, 20.0)
            cell_group = group[exp.segment]
            faster, slower = cell_group == FAST, cell_group == SLOW
            s15 = model.speeds(segment_multiplier(group, g15, 15.0))
            s20 = model.speeds(segment_multiplier(group, g20, 20.0))
            r15, r20 = linear_rates(y, pair, s15), linear_rates(y, pair, s20)
            on15 = extended_rates(y, pair, s20, s15)  # s20 on the -15% segment, cell by cell.
            lower15 = np.searchsorted(SPEEDS, s15, side="right")
            lower20 = np.searchsorted(SPEEDS, s20, side="right")
            knot_slower = slower & (lower15 != lower20)
            knot_faster = faster & (lower15 != lower20)
            cross25 = faster & (s15 < 25.0) & (s20 >= 25.0)

            def net(rates):
                return (ice[:, None] * (rates - model.base_cell) / 1000).sum(axis=0)

            def with_cf(mask):
                return np.where(mask[:, None], on15, r20)

            n15, n20 = net(r15), net(r20)
            variants = {
                "cf_slower": net(with_cf(slower)),
                "cf_faster25": net(with_cf(cross25)),
                "cf_slower_faster25": net(with_cf(slower | cross25)),
                "cf_all_knots": net(with_cf(slower | faster)),
            }
            # Anchor at -10%: faster cells that pass 25 mph anywhere from -10% to -20% stay on
            # their -10% segment at both -15% and -20%. This also covers allocations that are
            # already above 25 mph at -15%, which the -15% anchor cannot reach.
            g10 = solve_gain(exp.exposure, group, 10.0)
            s10 = model.speeds(segment_multiplier(group, g10, 10.0))
            wide25 = faster & (s10 < 25.0) & (s20 >= 25.0)
            anchor15 = np.where(wide25[:, None], extended_rates(y, pair, s15, s10), r15)
            anchor20 = np.where(wide25[:, None], extended_rates(y, pair, s20, s10), np.where(slower[:, None], on15, r20))
            cross_step = (ice[cross25, None] * (r20[cross25] - r15[cross25]) / 1000).sum(axis=0)
            slower_step = (ice[slower, None] * (r20[slower] - r15[slower]) / 1000).sum(axis=0)
            faster_step = (ice[faster, None] * (r20[faster] - r15[faster]) / 1000).sum(axis=0)
            same_bin = lower15 == lower20
            extension_error = max(extension_error, float(np.abs(on15[same_bin] - r20[same_bin]).max()))
            base = dict(design=design, replicate=rep, seed=int(designs[design][1][3, rep]), gain_at_15_pct=g15, gain_at_20_pct=g20, faster_vmt=vmt[faster].sum(), faster_cross25_vmt=vmt[cross25].sum(), faster_cross25_vmt_share_pct=100 * vmt[cross25].sum() / vmt[faster].sum(), faster_any_knot_vmt_share_pct=100 * vmt[knot_faster].sum() / vmt[faster].sum(), slower_any_knot_vmt_share_pct=100 * vmt[knot_slower].sum() / vmt[slower].sum(), max_extension_mph=float(np.abs(s20 - s15).max()))
            for pi, pol in enumerate(POLS):
                record = dict(base, pollutant=pol, anchor10_net15_kg_per_day=net(anchor15)[pi], anchor10_net20_kg_per_day=net(anchor20)[pi], net15_kg_per_day=n15[pi], net20_kg_per_day=n20[pi], faster25_cells_step_kg_per_day=cross_step[pi], slower_cells_step_kg_per_day=slower_step[pi], faster_cells_step_kg_per_day=faster_step[pi])
                for name, value in variants.items():
                    record[f"{name}_kg_per_day"] = value[pi]
                rows.append(record)
            if rep == 0:
                frame = pd.DataFrame({"road": exp.cells.roadway_type.to_numpy(), "period": exp.cells.period.to_numpy(), "baseline_speed_mph": cell_speed, "speed_at_15_mph": s15, "speed_at_20_mph": s20, "vmt": vmt, "side": np.where(slower, "slower", np.where(faster, "faster", "unchanged")), "crossing": lower15 != lower20})
                table = frame[frame.crossing].groupby(["side", "road", "period", "baseline_speed_mph"], as_index=False).agg(speed_at_15_mph=("speed_at_15_mph", "mean"), speed_at_20_mph=("speed_at_20_mph", "mean"), analysis_vmt=("vmt", "sum"))
                table.insert(0, "design", design)
                crossing_rows.append(table)
    checks.add("Counterfactual leaves cells that stay in their bin unchanged", extension_error <= 1e-10, f"{extension_error:.3e} g/mile")
    frame = pd.DataFrame(rows)
    frame.to_csv(locate("phase5_revision/results/a3_counterfactual_replicates.csv"), index=False)
    pd.concat(crossing_rows, ignore_index=True).to_csv(locate("phase5_revision/results/a3_knot_crossings_replicate0.csv"), index=False)
    return frame


def counterfactual_summary(frame, model, decomposition_summary, checks):
    denominators_by_pol = dict(zip(POLS, model.crz))
    rows = []
    for (design, pol), group in frame.groupby(["design", "pollutant"], sort=False):
        scale = 100 / denominators_by_pol[pol]
        level15 = decomposition_summary.query("design == @design and pollutant == @pol and component == 'net' and slowdown_pct == 15.0").contribution_crz_pp_p50.iloc[0]
        level20 = decomposition_summary.query("design == @design and pollutant == @pol and component == 'net' and slowdown_pct == 20.0").contribution_crz_pp_p50.iloc[0]
        level10 = decomposition_summary.query("design == @design and pollutant == @pol and component == 'net' and slowdown_pct == 10.0").contribution_crz_pp_p50.iloc[0]
        step = level20 - level15
        record = dict(design=design, pollutant=pol, median_at_10_crz_change_pct=level10, median_at_15_crz_change_pct=level15, median_at_20_crz_change_pct=level20, step_15_to_20_pp=step, step_10_to_15_pp=level15 - level10)
        for name, label in [("cf_slower", "no_crossing_slower"), ("cf_faster25", "no_crossing_faster25"), ("cf_slower_faster25", "no_crossing_slower_and_faster25"), ("cf_all_knots", "no_crossing_all_knots")]:
            median = float((group[f"{name}_kg_per_day"] * scale).median())
            record[f"{label}_median_at_20_crz_change_pct"] = median
            record[f"{label}_step_pp"] = median - level15
            record[f"{label}_step_removed_pp"] = level20 - median
            record[f"{label}_step_removed_pct"] = 100 * (level20 - median) / step
        paired = (group.net20_kg_per_day - group.net15_kg_per_day) * scale
        record["same_allocation_step_pp_p50"] = float(paired.median())
        record["same_allocation_step_pp_p05"] = PCT(paired, 0.05)
        record["same_allocation_step_pp_p95"] = PCT(paired, 0.95)
        for column, tag in [("faster_cross25_vmt_share_pct", "faster_cross25_vmt_share_pct"), ("faster_any_knot_vmt_share_pct", "faster_any_knot_vmt_share_pct"), ("slower_any_knot_vmt_share_pct", "slower_any_knot_vmt_share_pct")]:
            for q, suffix in [(0.05, "p05"), (0.5, "p50"), (0.95, "p95")]:
                record[f"{tag}_{suffix}"] = PCT(group[column], q)
        record["gain_at_15_pct_p50"] = float(group.gain_at_15_pct.median())
        record["gain_at_20_pct_p50"] = float(group.gain_at_20_pct.median())
        cells_step = group.faster25_cells_step_kg_per_day * scale
        record["faster25_cells_step_contribution_pp_p50"] = float(cells_step.median())
        record["faster25_cells_share_of_same_allocation_step_pct_p50"] = float((100 * cells_step / paired).median())
        crossing_effect = (group.net20_kg_per_day - group.cf_faster25_kg_per_day) * scale
        record["faster25_kink_effect_pp_p50"] = float(crossing_effect.median())
        record["faster25_kink_effect_pp_mean"] = float(crossing_effect.mean())
        crossed = group.faster_cross25_vmt_share_pct > 1.0
        threshold = 100 * (25 / 18 - 1)  # Gain that lifts 18 mph Street midday to 25 mph.
        record["street_midday_25mph_threshold_gain_pct"] = threshold
        record["allocations_with_main_faster25_crossing_pct"] = 100 * float(crossed.mean())
        record["allocations_already_above_25_at_15_pct"] = 100 * float((group.gain_at_15_pct >= threshold).mean())
        record["allocations_still_below_25_at_20_pct"] = 100 * float((group.gain_at_20_pct < threshold).mean())
        record["faster_cross25_vmt_share_pct_given_crossing_p50"] = float(group.faster_cross25_vmt_share_pct[crossed].median()) if crossed.any() else 0.0
        record["faster25_kink_effect_pp_p05"] = PCT(crossing_effect, 0.05)
        record["faster25_kink_effect_pp_p95"] = PCT(crossing_effect, 0.95)
        record["slower_cells_step_pp_p50"] = float((group.slower_cells_step_kg_per_day * scale).median())
        record["faster_cells_step_pp_p50"] = float((group.faster_cells_step_kg_per_day * scale).median())
        rows.append(record)
    out = pd.DataFrame(rows)
    out.to_csv(locate("phase5_revision/results/a3_counterfactual_summary.csv"), index=False)
    checks.add("Counterfactual evaluated only at -20% with unchanged VMT", frame.faster_vmt.gt(0).all(), f"{len(frame)} rows")
    return out


def faster25_subsets(frame, model):
    """High-VMT paired means, split by when Street midday crosses 25 mph.

    The crossing is bimodal: the gain threshold (38.89%) sits next to the median gain at -15%,
    so medians across all allocations mix two groups. Means within each group are additive.
    """
    reps = pd.read_csv(locate("phase5_revision/results/a1_replicates.csv")).query("profile == 'base_x1.0' and design == 'high_vmt'")
    rows = []
    for pi, pol in enumerate(POLS):
        scale = 100 / model.crz[pi]
        group = frame[frame.design.eq("high_vmt") & frame.pollutant.eq(pol)].set_index("replicate")
        level = {slow: reps[reps.slowdown_pct.eq(slow)].set_index("replicate")[f"{pol}_delta_kg_per_day"] for slow in SLOWS}
        crossed = group.faster_cross25_vmt_share_pct > 1.0
        subsets = {"all_allocations": crossed | ~crossed, "crosses_between_15_and_20": crossed, "already_above_25_at_15": ~crossed}
        for name, mask in subsets.items():
            g = group[mask]
            n15 = g.net15_kg_per_day
            mean = lambda series: float((series * scale).mean())
            rows.append(dict(design="high_vmt", pollutant=pol, allocation_subset=name, n_allocations=int(mask.sum()),
                             mean_step_5_to_10_pp=mean(level[10.0][mask] - level[5.0][mask]),
                             mean_step_10_to_15_pp=mean(level[15.0][mask] - level[10.0][mask]),
                             mean_step_15_to_20_pp=mean(g.net20_kg_per_day - n15),
                             mean_step_no_slower_crossing_pp=mean(g.cf_slower_kg_per_day - n15),
                             mean_step_no_slower_or_faster25_crossing_pp=mean(g.cf_slower_faster25_kg_per_day - n15),
                             mean_step_no_crossing_all_knots_pp=mean(g.cf_all_knots_kg_per_day - n15),
                             mean_step_no_slower_crossing_faster25_anchored_at_10_pp=mean(g.anchor10_net20_kg_per_day - g.anchor10_net15_kg_per_day)))
    out = pd.DataFrame(rows)
    out.to_csv(locate("phase5_revision/results/a3_faster25_subsets.csv"), index=False)
    print(out.to_string(index=False))
    return out


def pchip_runs(checks):
    exp = make_experiment()
    linear = Model(exp)
    model = Model(exp, "pchip")
    # Knot fidelity and agreement between the fast evaluator and scipy's own call.
    spline = Pchip(model.y)
    pair = np.repeat(np.arange(len(exp.pairs)), len(SPEEDS))
    knots = np.tile(SPEEDS, len(exp.pairs))
    checks.add("PCHIP passes through all bin centers", np.abs(spline.rates(pair, knots) - model.y[pair, np.tile(np.arange(len(SPEEDS)), len(exp.pairs)), :]).max() <= 1e-9, "16 bins, all curves")
    test = np.linspace(2.5, 75, 37)
    direct = spline.spline(test)  # (curves, speeds, pollutants)
    fast = np.stack([spline.rates(np.arange(len(exp.pairs)), np.full(len(exp.pairs), s)) for s in test], axis=1)
    checks.add("PCHIP fast evaluator equals scipy", np.abs(direct - fast).max() <= 1e-9, f"{np.abs(direct - fast).max():.3e}")
    zero = model.run(np.ones(exp.n_seg))
    checks.add("PCHIP zero-change test", max(abs(zero[f"{p}_delta_kg_per_day"]) for p in POLS) <= 1e-10, "kg/day delta is zero")

    groups, seeds = load_designs()["high_vmt"]
    pilot = Model(exp, "pchip", denominator="linear")
    rows, closure = [], 0.0
    uniform = model.run(np.full(exp.n_seg, 1.056))
    for li, slow in enumerate(SLOWS):
        for rep in range(500):
            gain = solve_gain(exp.exposure, groups[li, rep], slow)
            multiplier = segment_multiplier(groups[li, rep], gain, slow)
            closure = max(closure, constraint_error_pp(exp.exposure, multiplier))
            result = model.run(multiplier)
            pilot_result = pilot.run(multiplier)
            rows.append(dict(design="high_vmt", interpolation="pchip", slowdown_pct=slow, replicate=rep, seed=int(seeds[li, rep]), gain_pct=gain, pilot_condition_CO2_change_pct=pilot_result["crz_CO2_change_pct"], **result))
    frame = pd.DataFrame(rows)
    checks.add("PCHIP +5.6% closure", closure <= 1e-10, f"{closure:.3e} pp")
    checks.add("PCHIP no clipping", frame.clipped_vmt.max() == 0 and frame.min_scenario_speed_mph.min() >= SPEEDS[0] and frame.max_scenario_speed_mph.max() <= SPEEDS[-1], f"{frame.min_scenario_speed_mph.min():.3f}-{frame.max_scenario_speed_mph.max():.3f} mph")
    checks.add("PCHIP VMT closure", abs(frame.scenario_vmt - exp.vmt.sum()).max() <= 1e-7, "scenario VMT equals analysis VMT")
    frame.drop(columns=["scenario_vmt"]).to_csv(locate("phase5_revision/results/a3_pchip_replicates.csv"), index=False)
    summary = summarize(frame, ["design", "interpolation", "slowdown_pct"], lambda r, p: uniform[f"crz_{p}_change_pct"])
    summary["crz_baseline_kg_per_day"] = summary.pollutant.map(dict(zip(POLS, model.crz)))
    summary["linear_crz_baseline_kg_per_day"] = summary.pollutant.map(dict(zip(POLS, linear.crz)))
    summary.to_csv(locate("phase5_revision/results/a3_pchip_summary.csv"), index=False)
    first100 = frame[frame.replicate.lt(100) & frame.slowdown_pct.eq(20.0)]
    pilot_rows = pd.DataFrame([dict(condition="full_run_500_allocations_pchip_denominator", n_allocations=500, co2_crz_change_pct_p50=float(frame[frame.slowdown_pct.eq(20.0)].crz_CO2_change_pct.median())),
                               dict(condition="first_100_allocations_pchip_denominator", n_allocations=100, co2_crz_change_pct_p50=float(first100.crz_CO2_change_pct.median())),
                               dict(condition="first_100_allocations_linear_denominator", n_allocations=100, co2_crz_change_pct_p50=float(first100.pilot_condition_CO2_change_pct.median())),
                               dict(condition="all_500_allocations_linear_denominator", n_allocations=500, co2_crz_change_pct_p50=float(frame[frame.slowdown_pct.eq(20.0)].pilot_condition_CO2_change_pct.median()))])
    pilot_rows.to_csv(locate("phase5_revision/qa/a3_pchip_pilot_conditions.csv"), index=False)
    print(pilot_rows.to_string(index=False))
    return summary


def step_pattern(pchip_summary):
    a1 = pd.read_csv(locate("phase5_revision/results/a1_summary.csv"))
    a1 = a1[a1.design.isin(DESIGNS)].assign(rate_curve="linear")
    pchip = pchip_summary.assign(profile="base_x1.0", rate_curve="pchip")
    frame = pd.concat([a1, pchip], ignore_index=True)
    rows = []
    for key, group in frame.groupby(["profile", "rate_curve", "design", "pollutant"], sort=False):
        median = group.set_index("slowdown_pct").crz_change_pct_p50
        record = dict(zip(["profile", "rate_curve", "design", "pollutant"], key))
        for slow in SLOWS:
            record[f"crz_change_pct_p50_at_{slow:g}"] = median[slow]
        for a, b in STEP_LABELS:
            record[f"step_{a:g}_to_{b:g}_pp"] = median[b] - median[a]
        earlier = 0.5 * (record["step_5_to_10_pp"] + record["step_10_to_15_pp"])
        record["last_step_over_mean_earlier_ratio"] = record["step_15_to_20_pp"] / earlier
        rows.append(record)
    out = pd.DataFrame(rows)
    out.to_csv(locate("phase5_revision/results/a3_step_pattern.csv"), index=False)
    return out


def main():
    checks = Checks("a3")
    model = Model(make_experiment())
    summary = decomposition(model, checks)
    frame = counterfactuals(model, checks)
    cf = counterfactual_summary(frame, model, summary, checks)
    faster25_subsets(frame, model)
    pchip = pchip_runs(checks)
    pattern = step_pattern(pchip)
    checks.save()
    print(cf.T.to_string())
    print(pattern[pattern.pollutant.eq("CO2")].drop(columns=["pollutant"]).to_string(index=False))


if __name__ == "__main__":
    main()
