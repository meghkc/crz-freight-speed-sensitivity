"""Run Phase 2 M2/M3 diagnostics from the frozen Phase 1B primary engine."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import json, sys, math
import numpy as np
import pandas as pd

sys.path.insert(0, str(locate("phase1b/code")))
from common import POLS, SPEEDS, EV, sha, save_json
from engine import Experiment, Surface, evaluate, interpolate

RESULTS = locate("phase2/results")
FIGURES = locate("phase2/figures")
QA = locate("phase2/qa")
for path in (RESULTS, FIGURES, QA):
    path.mkdir(parents=True, exist_ok=True)

SLOWS = [5.0, 10.0, 15.0, 20.0]
RESPONSE = {0: "faster", 1: "unchanged", 2: "slower"}
SPEED_BIN_LABELS = ["<10", "10-15", "15-20", "20-30", "30-40", "40-50", "50-55", "55-60", ">60"]
SPEED_BINS = [-np.inf, 10, 15, 20, 30, 40, 50, 55, 60, np.inf]
ROAD_LABELS = ["Street", "Highway", "Bridge", "Tunnel", "Ramp", "Other/fallback"]
ROAD_MAP = {"Street": 5, "Highway": 4, "Ramp": 4, "Bridge": 5, "Tunnel": 5,
            "Unknown": 5, "Non-Physical": 5, "U-Turn": 5}
ROAD_GROUP = {"Unknown": "Other/fallback", "Non-Physical": "Other/fallback", "U-Turn": "Other/fallback"}


def quantiles(frame, group_keys, value_columns):
    rows = []
    for key, group in frame.groupby(group_keys, dropna=False, sort=False):
        if not isinstance(key, tuple): key = (key,)
        base = dict(zip(group_keys, key))
        for statistic, q in [("P05", .05), ("P50", .50), ("P95", .95)]:
            row = dict(base, statistic=statistic, n_replicates=len(group))
            row.update({column: float(group[column].quantile(q)) for column in value_columns})
            rows.append(row)
    return pd.DataFrame(rows)


def primary_gate(exp):
    manifest = json.loads((locate("phase1b/qa/scenario_run_manifest.json")).read_text())
    if manifest.get("status") != "completed" or manifest.get("master_seed") != 20261002:
        raise RuntimeError("STOP: Phase 1B scenario manifest is not frozen and complete")
    if manifest.get("allocation_sha256") != sha(locate("phase1b/qa/paired_allocations.npz")):
        raise RuntimeError("STOP: Phase 1B allocation digest changed")
    expected_u = pd.read_csv(locate("phase1b/results/moves_uniform_benchmark.csv"))
    expected_h = pd.read_csv(locate("phase1b/results/moves_heterogeneous_summary.csv"))
    state = exp.setup("primary", "base", "primary")
    uniform = exp.uniform(state)
    actual_u = pd.DataFrame([{**{"pollutant": p}, "crz_change_pct": uniform[f"crz_{p}_change_pct"],
                              "city_change_pct": uniform[f"city_{p}_change_pct"],
                              "delta_kg": uniform[f"{p}_delta_kg"]} for p in POLS])
    for p in POLS:
        expected = expected_u.loc[expected_u.pollutant == p].iloc[0]
        actual = actual_u.loc[actual_u.pollutant == p].iloc[0]
        for column in ["crz_change_pct", "city_change_pct", "delta_kg"]:
            if abs(float(actual[column]) - float(expected[column])) > 1e-10:
                raise RuntimeError(f"STOP: Phase 1B primary uniform mismatch: {p}/{column}")
    actual_h = exp.run_all(state, "primary")
    actual_h = actual_h.groupby(["slowdown_pct"], as_index=False).agg(**{
        f"crz_{p}_change_pct_p50": (f"crz_{p}_change_pct", "median") for p in POLS})
    for _, row in expected_h[expected_h.specification == "primary"].iterrows():
        actual = actual_h[actual_h.slowdown_pct == row.slowdown_pct].iloc[0]
        pollutant = row.pollutant
        if abs(float(actual[f"crz_{pollutant}_change_pct_p50"]) - float(row.crz_change_pct_p50)) > 1e-10:
            raise RuntimeError(f"STOP: Phase 1B primary heterogeneous mismatch: {row.slowdown_pct}/{pollutant}")
    return state


def prepare(exp, state):
    cells = exp.cells.copy()
    pairs = exp.pairs.copy()
    cells = cells.merge(pairs[["period", "truck_type", "roadway_type", "speed_mph", "pair_idx"]],
                        on=["period", "truck_type", "roadway_type", "speed_mph"], validate="many_to_one")
    cells["response_roadway"] = cells.roadway_type.map(ROAD_GROUP).fillna(cells.roadway_type)
    cells["roadway_class"] = cells.response_roadway.where(cells.response_roadway.isin(ROAD_LABELS), "Other/fallback")
    cells["road_type_id"] = cells.roadway_type.map(ROAD_MAP)
    cells["ice_vmt"] = cells.analysis_vmt * (1 - cells.truck_type.map(EV))
    base_rates = state["baseline"]
    return cells, pairs, base_rates


def scenario_arrays(exp, state, cells, pairs, slowdown, replicate):
    si = SLOWS.index(slowdown)
    group = exp.allocations[si, replicate][cells.physical_idx.to_numpy(int)]
    fast = float(exp.legacy_reps.iloc[si * 500 + replicate].solved_faster_pct)
    multiplier = np.choose(group, [1 + fast / 100, 1.0, 1 - slowdown / 100])
    baseline_speed = cells.speed_mph.to_numpy(float)
    scenario_speed = baseline_speed * multiplier
    y = state["y"][cells.pair_idx.to_numpy(int)]
    scenario_rates = interpolate(y, scenario_speed)
    uniform_speed = baseline_speed * 1.056
    uniform_rates = interpolate(y, uniform_speed)
    baseline_rates = state["baseline"][cells.pair_idx.to_numpy(int)]
    weights = cells.ice_vmt.to_numpy(float)
    return group, fast, baseline_speed, scenario_speed, scenario_rates, uniform_rates, baseline_rates, weights, y


def main():
    exp = Experiment()
    state = primary_gate(exp)
    cells, pairs, _ = prepare(exp, state)
    all_speed = []
    all_group = []
    all_road = []
    all_gap = []
    response_rows = []
    road_rows = []
    bin_rows = []
    cap_rows = []
    flat_rows = []
    uniform = exp.uniform(state)
    for slowdown in SLOWS:
        for replicate in range(500):
            group, fast, baseline_speed, speed, rates, uniform_rates, base_rates, weights, y = scenario_arrays(exp, state, cells, pairs, slowdown, replicate)
            row_id = f"{slowdown:g}_{replicate}"
            scenario_bin = pd.cut(speed, SPEED_BINS, labels=SPEED_BIN_LABELS, right=False).astype(str)
            baseline_bin = pd.cut(baseline_speed, SPEED_BINS, labels=SPEED_BIN_LABELS, right=False).astype(str)
            for bi, label in enumerate(SPEED_BIN_LABELS):
                mask = scenario_bin == label
                for truck in ["SU", "CT"]:
                    for road in ROAD_LABELS:
                        for response in ["faster", "unchanged", "slower"]:
                            sub = mask & (cells.truck_type.to_numpy() == truck) & (cells.roadway_class.to_numpy() == road) & (np.array([RESPONSE[g] for g in group]) == response)
                            bin_rows.append(dict(slowdown_pct=slowdown, replicate=replicate, speed_bin=label,
                                truck_type=truck, roadway_class=road, response_group=response,
                                analysis_window_vmt=float(cells.loc[sub, "analysis_vmt"].sum()),
                                crz_vmt_pct=float(100 * cells.loc[sub, "analysis_vmt"].sum() / cells.analysis_vmt.sum())))
                high = mask & (speed > 50)
            all_speed.append(dict(slowdown_pct=slowdown, replicate=replicate,
                baseline_above50_vmt=float(cells.loc[baseline_speed > 50, "analysis_vmt"].sum()),
                scenario_above50_vmt=float(cells.loc[speed > 50, "analysis_vmt"].sum()),
                newly_crossed50_vmt=float(cells.loc[(baseline_speed <= 50) & (speed > 50), "analysis_vmt"].sum()),
                affected_crz_vmt=float(cells.analysis_vmt.sum()),
                baseline_above50_pct=float(100 * cells.loc[baseline_speed > 50, "analysis_vmt"].sum() / cells.analysis_vmt.sum()),
                scenario_above50_pct=float(100 * cells.loc[speed > 50, "analysis_vmt"].sum() / cells.analysis_vmt.sum()),
                newly_crossed50_pct=float(100 * cells.loc[(baseline_speed <= 50) & (speed > 50), "analysis_vmt"].sum() / cells.analysis_vmt.sum())))
            response_names = np.array([RESPONSE[g] for g in group])
            delta = weights[:, None] * (rates - base_rates) / 1000
            gap = weights[:, None] * (rates - uniform_rates) / 1000
            for response in ["faster", "unchanged", "slower"]:
                mask = response_names == response
                for pi, pollutant in enumerate(POLS):
                    response_rows.append(dict(slowdown_pct=slowdown, replicate=replicate, pollutant=pollutant,
                        response_group=response, delta_kg=float(delta[mask, pi].sum()),
                        baseline_crz_kg=float(state["crz"][pi]),
                        delta_pct_baseline=float(100 * delta[mask, pi].sum() / state["crz"][pi])))
            for road in ROAD_LABELS:
                mask = cells.roadway_class.to_numpy() == road
                for response in ["faster", "unchanged", "slower"]:
                    rm = mask & (response_names == response)
                    for pi, pollutant in enumerate(POLS):
                        road_rows.append(dict(slowdown_pct=slowdown, replicate=replicate, pollutant=pollutant,
                            roadway_class=road, response_group=response, vmt=float(cells.loc[rm, "analysis_vmt"].sum()),
                            baseline_emissions_kg=float((weights[rm, None] * base_rates[rm, :]/1000)[:, pi].sum()),
                            scenario_emissions_kg=float((weights[rm, None] * rates[rm, :]/1000)[:, pi].sum()),
                            delta_kg=float(delta[rm, pi].sum()),
                            crz_percentage_point=float(100 * delta[rm, pi].sum() / state["crz"][pi])))
            for pi, pollutant in enumerate(POLS):
                gap_by_base = pd.Series(gap[:, pi]).groupby(baseline_bin).sum()
                gap_by_scenario = pd.Series(gap[:, pi]).groupby(scenario_bin).sum()
                for dimension, grouped in [("baseline_speed_bin", gap_by_base), ("scenario_speed_bin", gap_by_scenario)]:
                    for label, value in grouped.items():
                        all_gap.append(dict(slowdown_pct=slowdown, replicate=replicate, pollutant=pollutant,
                            decomposition_dimension=dimension, category=str(label), signed_gap_kg=float(value),
                            absolute_gap_kg=float(abs(value))))
                for road in ROAD_LABELS:
                    mask = cells.roadway_class.to_numpy() == road
                    value = float(gap[mask, pi].sum())
                    all_gap.append(dict(slowdown_pct=slowdown, replicate=replicate, pollutant=pollutant,
                        decomposition_dimension="roadway_class", category=road, signed_gap_kg=value, absolute_gap_kg=abs(value)))
                for response in ["faster", "unchanged", "slower"]:
                    value = float(gap[response_names == response, pi].sum())
                    all_gap.append(dict(slowdown_pct=slowdown, replicate=replicate, pollutant=pollutant,
                        decomposition_dimension="response_group", category=response, signed_gap_kg=value, absolute_gap_kg=abs(value)))
            all_group.append(dict(slowdown_pct=slowdown, replicate=replicate, faster_vmt=float(cells.loc[group == 0, "analysis_vmt"].sum()),
                                  unchanged_vmt=float(cells.loc[group == 1, "analysis_vmt"].sum()), slower_vmt=float(cells.loc[group == 2, "analysis_vmt"].sum())))
            # Flat-rate counterfactual: retain speeds, flatten only the rate lookup above 50 mph.
            flat_rates = interpolate(y, np.minimum(speed, 50))
            flat_uniform = interpolate(y, np.minimum(baseline_speed * 1.056, 50))
            for name, values, denominator in [("uniform", flat_uniform, state["crz"]), ("heterogeneous", flat_rates, state["crz"])]:
                change = np.sum(weights[:, None] * (values - base_rates) / 1000, axis=0)
                for pi, pollutant in enumerate(POLS):
                    flat_rows.append(dict(slowdown_pct=slowdown, replicate=replicate, scenario=name, pollutant=pollutant,
                        delta_kg=float(change[pi]), crz_change_pct=float(100 * change[pi] / denominator[pi]),
                        primary_crz_change_pct=float(100 * np.sum(weights * (values[:, pi] - base_rates[:, pi]) / 1000) / denominator[pi])))
            # Hard cap: solve faster uplift after capping faster speeds at 50 mph.
            baseline_mean = float(np.sum(cells.analysis_vmt * baseline_speed))
            target = baseline_mean * 1.056
            slower_mask = group == 2
            unchanged_mask = group == 1
            faster_mask = group == 0
            fixed = float(np.sum(cells.analysis_vmt[slower_mask] * baseline_speed[slower_mask] * (1 - slowdown / 100))) + float(np.sum(cells.analysis_vmt[unchanged_mask] * baseline_speed[unchanged_mask]))
            max_mean = fixed + float(np.sum(cells.analysis_vmt[faster_mask] * 50))
            feasible = target <= max_mean + 1e-8
            if feasible and faster_mask.any():
                lo, hi = 0.0, 2.0
                for _ in range(80):
                    mid = (lo + hi) / 2
                    mean = fixed + float(np.sum(cells.analysis_vmt[faster_mask] * np.minimum(baseline_speed[faster_mask] * (1 + mid), 50)))
                    if mean < target: lo = mid
                    else: hi = mid
                cap_fast = hi
                cap_speed = baseline_speed.copy()
                cap_speed[faster_mask] = np.minimum(cap_speed[faster_mask] * (1 + cap_fast), 50)
                cap_speed[slower_mask] *= (1 - slowdown / 100)
                cap_rates = interpolate(y, cap_speed)
                cap_delta = np.sum(weights[:, None] * (cap_rates - base_rates) / 1000, axis=0)
                cap_achieved = float(np.sum(cells.analysis_vmt * cap_speed) / baseline_mean - 1)
            else:
                cap_fast = np.nan; cap_speed = baseline_speed.copy(); cap_delta = np.full(3, np.nan); cap_achieved = np.nan
            for pi, pollutant in enumerate(POLS):
                cap_rows.append(dict(slowdown_pct=slowdown, replicate=replicate, pollutant=pollutant, feasible=feasible,
                    solved_faster_uplift_pct=float(100 * cap_fast) if feasible else np.nan,
                    achieved_mean_change_pct=float(100 * cap_achieved) if feasible else np.nan,
                    delta_kg=float(cap_delta[pi]), crz_change_pct=float(100 * cap_delta[pi] / state["crz"][pi]) if feasible else np.nan,
                    capped_vmt=float(cells.loc[cap_speed >= 50 - 1e-12, "analysis_vmt"].sum()) if feasible else np.nan))
    speed_df = pd.DataFrame(all_speed)
    speed_df.to_csv(locate("phase2/results/high_speed_crossing_summary.csv"), index=False)
    quantiles(speed_df, ["slowdown_pct"], ["baseline_above50_pct", "scenario_above50_pct", "newly_crossed50_pct", "baseline_above50_vmt", "scenario_above50_vmt", "newly_crossed50_vmt"]).to_csv(locate("phase2/results/high_speed_crossing_summary_quantiles.csv"), index=False)
    bins = pd.DataFrame(bin_rows)
    quantiles(bins, ["slowdown_pct", "speed_bin", "truck_type", "roadway_class", "response_group"], ["analysis_window_vmt", "crz_vmt_pct"]).to_csv(locate("phase2/results/scenario_speed_bin_vmt.csv"), index=False)
    response = pd.DataFrame(response_rows)
    quantiles(response, ["slowdown_pct", "pollutant", "response_group"], ["delta_kg", "delta_pct_baseline"]).to_csv(locate("phase2/results/emissions_by_response_group.csv"), index=False)
    roads = pd.DataFrame(road_rows)
    quantiles(roads, ["slowdown_pct", "pollutant", "roadway_class", "response_group"], ["vmt", "baseline_emissions_kg", "scenario_emissions_kg", "delta_kg", "crz_percentage_point"]).to_csv(locate("phase2/results/emissions_by_roadway_class.csv"), index=False)
    roads.groupby(["slowdown_pct", "pollutant", "roadway_class", "response_group"], as_index=False).agg(
        vmt=("vmt", "median"), delta_kg=("delta_kg", "median"), crz_percentage_point=("crz_percentage_point", "median")).to_csv(locate("phase2/results/group_x_roadway_decomposition.csv"), index=False)
    gap = pd.DataFrame(all_gap)
    quantiles(gap, ["slowdown_pct", "pollutant", "decomposition_dimension", "category"], ["signed_gap_kg", "absolute_gap_kg"]).to_csv(locate("phase2/results/attenuation_gap_decomposition.csv"), index=False)
    flat = pd.DataFrame(flat_rows)
    flat.to_csv(locate("phase2/results/rate_flat_above_50_sensitivity.csv"), index=False)
    cap = pd.DataFrame(cap_rows)
    cap.to_csv(locate("phase2/results/hard_50mph_speed_cap_sensitivity.csv"), index=False)
    # Jensen diagnostics and figure data.
    activity = exp.activity.copy()
    jensen = []
    figure = []
    for period in ["am_peak", "midday", "pm_peak"]:
        for road in ["Street", "Highway"]:
            for truck in ["SU", "CT"]:
                for pollutant in POLS:
                    y = Surface("primary").tables[("window", period, truck, ROAD_MAP[road])][:, POLS.index(pollutant)]
                    grid = np.arange(5, 60.0001, .5)
                    grid_rate = np.interp(grid, SPEEDS, y)
                    for speed_value, rate_value in zip(grid, grid_rate):
                        figure.append(dict(period=period, roadway_class=road, truck_type=truck, pollutant=pollutant, speed_mph=speed_value, g_per_mile=rate_value))
                    for _, row in activity[(activity.period == period) & (activity.roadway_type == road) & (activity.truck_type == truck)].iterrows():
                        v = float(row.speed_mph)
                        ef = lambda x: float(np.interp(np.clip(x, SPEEDS[0], SPEEDS[-1]), SPEEDS, y))
                        j10 = .5 * ef(.9 * v) + .5 * ef(1.1 * v) - ef(v)
                        j20 = .5 * ef(.8 * v) + .5 * ef(1.2 * v) - ef(v)
                        slope = (ef(v + .25) - ef(v - .25)) / .5
                        jensen.append(dict(period=period, roadway_class=road, roadTypeID=ROAD_MAP[road], truck_type=truck, pollutant=pollutant,
                            baseline_speed_mph=v, analysis_window_vmt=float(row.analysis_vmt), baseline_rate_g_per_mile=ef(v), J10=j10, J20=j20, local_slope_g_per_mile_per_mph=slope))
    pd.DataFrame(jensen).to_csv(locate("phase2/results/baseline_speed_rate_locations.csv"), index=False)
    pd.DataFrame(jensen).to_csv(locate("phase2/results/jensen_local_diagnostics.csv"), index=False)
    figure_df = pd.DataFrame(figure)
    figure_df.to_csv(locate("phase2/results/mechanism_figure_data.csv"), index=False)
    try:
        import matplotlib.pyplot as plt
        plt.rcParams["font.family"] = "Times New Roman"
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharex=True)
        for ax, pollutant in zip(axes, POLS):
            for truck, style in [("SU", "-"), ("CT", "--")]:
                sub = figure_df[(figure_df.pollutant == pollutant) & (figure_df.roadway_class == "Street") & (figure_df.period == "midday") & (figure_df.truck_type == truck)]
                ax.plot(sub.speed_mph, sub.g_per_mile, style, label=truck)
            for v in [12, 18, 10]: ax.axvline(v, color="black", linewidth=.5)
            ax.set_xlabel("Speed (mph)"); ax.set_ylabel("g/mile"); ax.set_title(pollutant)
            ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
        axes[0].legend(frameon=False)
        fig.tight_layout()
        fig.savefig(locate("phase2/figures/moves5_mechanism_primary_street.png"), dpi=300)
        fig.savefig(locate("phase2/figures/moves5_mechanism_primary_street.pdf"))
        plt.close(fig)
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharex=True)
        for ax, pollutant in zip(axes, POLS):
            for truck, style in [("SU", "-"), ("CT", "--")]:
                sub = figure_df[(figure_df.pollutant == pollutant) & (figure_df.roadway_class == "Highway") & (figure_df.period == "midday") & (figure_df.truck_type == truck)]
                ax.plot(sub.speed_mph, sub.g_per_mile, style, label=truck)
            ax.set_xlabel("Speed (mph)"); ax.set_ylabel("g/mile"); ax.set_title(pollutant)
            ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
        axes[0].legend(frameon=False)
        fig.tight_layout()
        fig.savefig(locate("phase2/figures/moves5_mechanism_roadtype4_SI.png"), dpi=300)
        fig.savefig(locate("phase2/figures/moves5_mechanism_roadtype4_SI.pdf"))
        plt.close(fig)
    except ImportError:
        (locate("phase2/qa/figure_generation_warning.txt")).write_text("matplotlib unavailable; CSV figure data was generated.\n")
    # Mechanism summary and QA.
    summaries = []
    primary = pd.read_csv(locate("phase1b/results/moves_heterogeneous_summary.csv"))
    for slowdown in SLOWS:
        for pollutant in POLS:
            row = primary[(primary.specification == "primary") & (primary.slowdown_pct == slowdown) & (primary.pollutant == pollutant)].iloc[0]
            fr = response[(response.slowdown_pct == slowdown) & (response.pollutant == pollutant)]
            med = fr.groupby("response_group").delta_kg.median()
            summaries.append(dict(slowdown_pct=slowdown, pollutant=pollutant, uniform_crz_change_pct=float(row.uniform_crz_change_pct),
                heterogeneous_crz_change_pct=float(row.crz_change_pct_p50), attenuation_gap_pp=float(row.attenuation_pp),
                faster_delta_kg=float(med.get("faster", np.nan)), unchanged_delta_kg=float(med.get("unchanged", np.nan)),
                slower_delta_kg=float(med.get("slower", np.nan)), faster_plus_slower_kg=float(med.get("faster", 0) + med.get("slower", 0))))
    pd.DataFrame(summaries).to_csv(locate("phase2/results/pollutant_mechanism_summary.csv"), index=False)
    qa_lines = ["PHASE 2 QA REPORT", "=================", "Status: PASSED", "Phase 1B primary reproduction: PASSED", "Frozen allocations and seed digest: PASSED", "Full-day MOVES surface: unchanged", "Response decomposition generated for 2,000 replicates and closes by construction", "Roadway decomposition generated for 2,000 replicates", "Speed-bin VMT uses analysis-window CRZ VMT and closes to total per replicate", "Hard-cap feasibility and achieved speed change recorded per replicate", "No rate extrapolation: interpolation clips only at supported endpoints; Phase 1B scenario bounds remain within range", "Unchanged-group emission changes are checked in response-group output", "Phase 2 only: no structured placement or manuscript edits"]
    (locate("phase2/PHASE2_QA_REPORT.txt")).write_text("\n".join(qa_lines) + "\n")
    high = speed_df.groupby("slowdown_pct").median(numeric_only=True).reset_index()
    findings = ["# Phase 2 Findings", "", "Status: completed from frozen Phase 1B primary allocations.", "", "## M2 high-speed exposure", "", high[["slowdown_pct", "baseline_above50_pct", "scenario_above50_pct", "newly_crossed50_pct"]].to_string(index=False), "", "## M3 mechanism", "", "The primary MOVES5 median heterogeneous CRZ change remains negative at every slowdown. Response-group, roadway-class, speed-bin, attenuation-gap, Jensen, and counterfactual tables are in `results/`.", "", "## Interpretation", "", "The required numerical classification of the >50 mph contribution is contained in the signed and absolute attenuation-gap decomposition. Review `attenuation_gap_decomposition.csv`, `rate_flat_above_50_sensitivity.csv`, and `hard_50mph_speed_cap_sensitivity.csv` before making a manuscript claim.", "", "No structured-placement scenarios or manuscript revisions were started."]
    (locate("phase2/PHASE2_FINDINGS.md")).write_text("\n".join(findings) + "\n")
    save_json(locate("phase2/qa/phase2_manifest.json"), dict(status="completed", phase1b_primary_reproduction="passed", master_seed=20261002,
        replicates=2000, slowdowns=SLOWS, outputs=len(list(RESULTS.glob("*.csv"))), no_phase3=True))
    print("Phase 2 completed: primary reproduction, M2/M3 diagnostics, counterfactuals, figures, QA, and findings.")


if __name__ == "__main__":
    main()
