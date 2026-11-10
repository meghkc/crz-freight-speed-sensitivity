"""Phase 3 structured placement using the frozen Phase 1B MOVES engine."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import sys, json, hashlib, types, importlib.util, itertools, traceback
import numpy as np
import pandas as pd
from shapely import wkt

DATA = locate("data")
RESULTS = locate("phase3/results")
QA = locate("phase3/qa")
PROV = locate("phase3/provenance")
for directory in (RESULTS, QA, PROV):
    directory.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(locate("phase1b/code")))
from common import POLS, EV, sha
from engine import Experiment, interpolate

SLOWS = [5.0, 10.0, 15.0, 20.0]
ROADS = ["Street", "Highway", "Bridge", "Tunnel", "Ramp"]
PERIODS = ["am_peak", "midday", "pm_peak"]
PERIOD_LABEL = {"am_peak": "AM", "midday": "midday", "pm_peak": "PM"}
RESP = np.array(["faster", "unchanged", "slower"])
TARGET = np.array([37.0, 46.0, 16.0]) / 99.0
MASTER_SEED = 20261003
CHECKS = []


def check(name, passed, detail):
    CHECKS.append({"test": name, "passed": bool(passed), "detail": str(detail)})
    if not passed:
        raise RuntimeError(f"{name}: {detail}")


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def quantile_summary(frame, keys, columns):
    grouped = frame.groupby(keys, sort=False, dropna=False)
    out = grouped.size().rename("n_replicates").to_frame()
    for q, suffix in [(0.05, "p05"), (0.50, "p50"), (0.95, "p95")]:
        out = out.join(grouped[columns].quantile(q).rename(columns=lambda c: f"{c}_{suffix}"))
    out = out.reset_index()
    return out


def canonical_key(text):
    geom = wkt.loads(text)
    coords = list(geom.coords)
    a = (round(coords[0][0], 2), round(coords[0][1], 2))
    b = (round(coords[-1][0], 2), round(coords[-1][1], 2))
    lo, hi = sorted([a, b])
    return f"{lo[0]}|{lo[1]}|{hi[0]}|{hi[1]}|{round(float(geom.length), 2)}"


def original_exposures():
    """Rebuild the three frozen M6 exposure vectors with the original helper."""
    package = types.ModuleType("freight_model")
    package.__path__ = [str(locate("freight_model"))]
    sys.modules["freight_model"] = package
    spec = importlib.util.spec_from_file_location(
        "original_fast", locate("freight_model/analyze_aggregation_robustness_fast.py")
    )
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    coverage = ref.period_coverage("geotab_8to18")
    links = ref.load_links(locate("data/assignment_link_detail.csv"), "EPSG:2263")
    crz, _ = ref.load_crz(DATA, None, "EPSG:2263")
    edge, physical = ref.build_edge_physical(links, crz)
    emissions = ref.load_emissions(locate("data/emissions_assignment_link_detail.csv"))
    base = ref.attach_base(emissions, edge, coverage)
    exposures = ref.build_segment_exposures(base, physical, coverage)
    return physical, exposures, ["vmt_weighted", "road_length_weighted", "equal_segment"]


def nearest_prefix(order, lengths, target):
    """Whole-segment prefix closest to target; ties choose the smaller prefix."""
    cumulative = np.r_[0.0, np.cumsum(lengths[order])]
    distance = np.abs(cumulative - target)
    k = int(np.flatnonzero(distance == distance.min())[0])
    return order[:k]


def fixed_slower_sets(segment):
    length = segment.crz_length.to_numpy(float)
    ids = segment.physical_idx.to_numpy(int)
    total = length.sum()
    target = TARGET[2] * total
    high_order = np.lexsort((ids, -segment.analysis_vmt.to_numpy(float)))
    low_order = np.lexsort((ids, segment.analysis_vmt.to_numpy(float)))
    high = nearest_prefix(high_order, length, target)
    low = nearest_prefix(low_order, length, target)
    facility = segment.roadway_class.isin(["Bridge", "Ramp", "Tunnel"]).to_numpy()
    chosen = list(np.flatnonzero(facility))
    facility_length = length[facility].sum()
    if facility_length < target:
        street = np.flatnonzero(segment.roadway_class.eq("Street").to_numpy())
        street = street[np.lexsort((ids[street], -segment.analysis_vmt.to_numpy(float)[street]))]
        chosen.extend(nearest_prefix(street, length, target - facility_length).tolist())
    else:
        facilities = np.flatnonzero(facility)
        facilities = facilities[np.lexsort((ids[facilities], -segment.analysis_vmt.to_numpy(float)[facilities]))]
        chosen = nearest_prefix(facilities, length, target).tolist()
    return {
        "high_vmt": np.array(high, dtype=int),
        "infrastructure_first": np.array(sorted(set(chosen)), dtype=int),
        "low_vmt": np.array(low, dtype=int),
    }


def structured_allocations(lengths, slower, seeds):
    """Fix slower roads and draw whole faster roads nearest their relative target."""
    n = len(lengths)
    remaining = np.setdiff1d(np.arange(n), slower, assume_unique=True)
    target_fast = TARGET[0] / (TARGET[0] + TARGET[1]) * lengths[remaining].sum()
    allocations = np.ones((len(seeds), n), dtype=np.int8)
    allocations[:, slower] = 2
    for i, seed in enumerate(seeds):
        rng = np.random.default_rng(int(seed))
        order = remaining[np.argsort(rng.random(len(remaining)), kind="stable")]
        faster = nearest_prefix(order, lengths, target_fast)
        allocations[i, faster] = 0
    return allocations


def evaluate_one(exp, state, group, exposure, slow):
    amounts = np.bincount(group, weights=exposure, minlength=3)
    if amounts[0] <= 0 or amounts.sum() <= 0:
        raise RuntimeError("Infeasible structured speed constraint")
    fast = 100 * (0.056 * amounts.sum() + slow / 100 * amounts[2]) / amounts[0]
    result = exp.run_one(state, group, fast, slow)
    return fast, result


def setup_cells(exp, state):
    cells = exp.cells.merge(
        exp.pairs,
        on=["period", "truck_type", "roadway_type", "speed_mph"],
        validate="many_to_one",
    )
    cells["ice_vmt"] = cells.analysis_vmt * (1 - cells.truck_type.map(EV))
    baseline = state["baseline"][cells.pair_idx.to_numpy(int)]
    cube = state["y"][cells.pair_idx.to_numpy(int)]
    return cells, baseline, cube


def cell_details(cells, baseline, cube, group, fast, slow):
    cell_group = group[cells.physical_idx.to_numpy(int)]
    speed = cells.speed_mph.to_numpy(float) * np.choose(
        cell_group, [1 + fast / 100, 1.0, 1 - slow / 100]
    )
    scenario = interpolate(cube, speed)
    uniform = interpolate(cube, cells.speed_mph.to_numpy(float) * 1.056)
    weight = cells.ice_vmt.to_numpy(float)[:, None] / 1000
    delta = weight * (scenario - baseline)
    gap = weight * (scenario - uniform)
    return cell_group, speed, delta, gap


def slower_characteristics(design, statistic, slowdown, groups, segment, cells, baseline):
    rows = []
    length = segment.crz_length.to_numpy(float)
    for group in groups:
        slower = group == 2
        mask = slower[cells.physical_idx.to_numpy(int)]
        vmt = cells.analysis_vmt.to_numpy(float)
        slow_vmt = vmt[mask].sum()
        unique_pp = cells.loc[mask, ["physical_idx", "period", "speed_mph"]].drop_duplicates()
        base_emissions = cells.ice_vmt.to_numpy(float)[:, None] * baseline / 1000
        record = {
            "roadway_length_share": length[slower].sum() / length.sum(),
            "analysis_window_vmt_share": slow_vmt / vmt.sum(),
            "mean_baseline_speed_mph": unique_pp.speed_mph.mean(),
            "vmt_weighted_baseline_speed_mph": np.average(cells.loc[mask, "speed_mph"], weights=vmt[mask]) if slow_vmt else np.nan,
        }
        for road in ROADS:
            record[f"{road.lower()}_length_share"] = length[slower & segment.roadway_class.eq(road).to_numpy()].sum() / length[slower].sum()
        for truck in ["SU", "CT"]:
            record[f"{truck.lower()}_vmt_share"] = vmt[mask & cells.truck_type.eq(truck).to_numpy()].sum() / slow_vmt if slow_vmt else np.nan
        for period in PERIODS:
            record[f"{PERIOD_LABEL[period].lower()}_vmt_share"] = vmt[mask & cells.period.eq(period).to_numpy()].sum() / slow_vmt if slow_vmt else np.nan
        for pi, pol in enumerate(POLS):
            record[f"baseline_{pol}_share"] = base_emissions[mask, pi].sum() / base_emissions[:, pi].sum()
        rows.append(record)
    frame = pd.DataFrame(rows)
    if statistic == "exact":
        record = frame.iloc[0].to_dict()
    else:
        q = {"P05": .05, "P50": .50, "P95": .95}[statistic]
        record = frame.quantile(q).to_dict()
    return dict(design=design, slowdown_pct=slowdown, statistic=statistic, n_realizations=len(groups), **record)


def main():
    source_files = [p for ph in ("phase1b", "phase2r") for p in phase_files(ph)]
    frozen = {str(p): digest(p) for p in source_files}
    (locate("phase3/provenance/source_sha256.json")).write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    exp = Experiment()
    state = exp.setup("primary", "base", "primary")
    saved = pd.read_csv(locate("phase1b/results/moves_heterogeneous_replicates.csv")).sort_values(["slowdown_pct", "replicate"]).reset_index(drop=True)
    reproduced = exp.run_all(state, "primary").sort_values(["slowdown_pct", "replicate"]).reset_index(drop=True)
    compare = ["solved_faster_pct"] + [f"crz_{p}_change_pct" for p in POLS] + [f"{p}_delta_kg" for p in POLS]
    max_error = max(float(abs(saved[c] - reproduced[c]).max()) for c in compare)
    check("Phase 1B random reference reproduced", max_error <= 1e-10, max_error)
    expected_summary = pd.read_csv(locate("phase1b/results/moves_heterogeneous_summary.csv"))
    for pol in POLS:
        for slow in SLOWS:
            actual = saved.loc[saved.slowdown_pct.eq(slow), f"crz_{pol}_change_pct"].median()
            expected = expected_summary.query("specification == 'primary' and slowdown_pct == @slow and pollutant == @pol").crz_change_pct_p50.iloc[0]
            check(f"Random median {slow:g}/{pol}", abs(actual - expected) <= 1e-10, actual - expected)

    physical, exposures, modes = original_exposures()
    archived = pd.read_csv(locate("phase1b/qa/physical_segments.csv"))
    physical_match = (
        len(physical) == len(archived)
        and np.array_equal(physical.physical_key, archived.physical_key)
        and np.array_equal(physical.physical_idx, archived.physical_idx)
        and np.array_equal(physical.n_directed_edges, archived.n_directed_edges)
        and np.allclose(physical.crz_length, archived.crz_length, rtol=0, atol=1e-10)
    )
    check("Physical IDs match frozen Phase 1B", physical_match, (len(physical), len(archived)))
    assignment = pd.read_csv(locate("data/assignment_link_detail.csv"), usecols=["RW_TYPE_name", "geometry_wkt"])
    assignment["physical_key"] = assignment.geometry_wkt.map(canonical_key)
    class_map = assignment.loc[assignment.physical_key.isin(physical.physical_key), ["physical_key", "RW_TYPE_name"]].drop_duplicates()
    check("One roadway class per physical geometry", class_map.groupby("physical_key").RW_TYPE_name.nunique().max() == 1, "unambiguous")
    segment = physical.merge(class_map, on="physical_key", how="left", validate="one_to_many")
    segment = segment.drop_duplicates("physical_idx").rename(columns={"RW_TYPE_name": "roadway_class"}).sort_values("physical_idx").reset_index(drop=True)
    check("Physical class coverage", segment.roadway_class.notna().all() and segment.roadway_class.isin(ROADS).all(), segment.roadway_class.value_counts().to_dict())
    check("No Non-Physical placement links", not segment.roadway_class.eq("Non-Physical").any(), len(segment))
    cells, baseline, cube = setup_cells(exp, state)
    seg_vmt = cells.groupby("physical_idx").analysis_vmt.sum()
    segment["analysis_vmt"] = segment.physical_idx.map(seg_vmt).fillna(0.0)
    check("Scenario cells use only physical pool", cells.physical_idx.isin(segment.physical_idx).all(), cells.physical_idx.nunique())
    check("Frozen VMT exposure reproduced", np.max(abs(exposures[0] - np.bincount(cells.physical_idx, weights=cells.analysis_vmt * cells.speed_mph, minlength=len(segment)))) <= 1e-10, "exact")
    sets = fixed_slower_sets(segment)
    lengths = segment.crz_length.to_numpy(float)
    seeds = np.random.default_rng(MASTER_SEED).integers(0, np.iinfo(np.uint32).max, size=(3, 500), dtype=np.uint32)
    designs = {}
    for di, (name, slower) in enumerate(sets.items()):
        designs[name] = structured_allocations(lengths, slower, seeds[di])
        check(name + " assigns every physical segment", np.all(np.isin(designs[name], [0, 1, 2])), designs[name].shape)
        check(name + " slower set fixed", np.all(designs[name][:, slower] == 2) and np.all((designs[name] == 2).sum(axis=1) == len(slower)), len(slower))
    np.savez_compressed(locate("phase3/provenance/structured_allocations.npz"), seeds=seeds, **designs)
    segment.assign(**{f"slower_{k}": segment.index.isin(v) for k, v in sets.items()}).to_csv(locate("phase3/provenance/physical_segment_eligibility.csv"), index=False)
    pd.DataFrame([{"design": name, "seed": int(seed), "replicate": rep} for di, name in enumerate(designs) for rep, seed in enumerate(seeds[di])]).to_csv(locate("phase3/provenance/structured_seeds.csv"), index=False)

    uniform = exp.uniform(state)
    random_rows = []
    for row in saved.itertuples(index=False):
        for pol in POLS:
            random_rows.append({"design": "random", "slowdown_pct": row.slowdown_pct, "replicate": row.replicate, "seed": row.seed, "pollutant": pol, "solved_faster_pct": row.solved_faster_pct, "crz_change_pct": getattr(row, f"crz_{pol}_change_pct"), "city_change_pct": getattr(row, f"city_{pol}_change_pct"), "delta_kg": getattr(row, f"{pol}_delta_kg"), "uniform_crz_change_pct": uniform[f"crz_{pol}_change_pct"]})
    random_frame = pd.DataFrame(random_rows)
    random_frame["attenuation_pct"] = 100 * (1 - random_frame.crz_change_pct / random_frame.uniform_crz_change_pct)
    result_rows, decomposition_rows, plausibility_rows = [], [], []
    max_constraint_error = 0.0
    max_vmt_error = 0.0
    max_emissions_error = 0.0
    max_lookup = 0.0
    for design, allocations in designs.items():
        for si, slow in enumerate(SLOWS):
            for rep, group in enumerate(allocations):
                fast, result = evaluate_one(exp, state, group, exposures[0], slow)
                cell_group, speed, delta, gap = cell_details(cells, baseline, cube, group, fast, slow)
                achieved = 100 * (np.dot(exposures[0], np.choose(group, [1 + fast / 100, 1, 1 - slow / 100])) / exposures[0].sum() - 1)
                max_constraint_error = max(max_constraint_error, abs(achieved - 5.6))
                max_vmt_error = max(max_vmt_error, abs(result["affected_vmt"] - cells.analysis_vmt.sum()))
                max_lookup = max(max_lookup, result["max_lookup_speed"])
                for pi, pol in enumerate(POLS):
                    max_emissions_error = max(max_emissions_error, abs(delta[:, pi].sum() - result[f"{pol}_delta_kg"]))
                    result_rows.append({"design": design, "slowdown_pct": slow, "replicate": rep, "seed": int(seeds[list(designs).index(design), rep]), "pollutant": pol, "solved_faster_pct": fast, "crz_change_pct": result[f"crz_{pol}_change_pct"], "city_change_pct": result[f"city_{pol}_change_pct"], "delta_kg": result[f"{pol}_delta_kg"], "uniform_crz_change_pct": uniform[f"crz_{pol}_change_pct"], "attenuation_pct": 100 * (1 - result[f"crz_{pol}_change_pct"] / uniform[f"crz_{pol}_change_pct"])})
                    group_delta = np.bincount(cell_group, weights=delta[:, pi], minlength=3)
                    ok = group_delta[0] < 0 and group_delta[2] > 0
                    road = cells.roadway_type.to_numpy()
                    masks = {"street": road == "Street", "highway_family": np.isin(road, ["Highway", "Bridge", "Ramp", "Tunnel"]), "lt20": speed < 20, "gt50": speed > 50}
                    decomposition_rows.append({"design": design, "slowdown_pct": slow, "replicate": rep, "pollutant": pol, "faster_group_delta_kg": group_delta[0], "unchanged_group_delta_kg": group_delta[1], "slower_group_delta_kg": group_delta[2], "net_delta_kg": delta[:, pi].sum(), "offset_ratio": group_delta[2] / abs(group_delta[0]) if ok else np.nan, "invalid_offset_flag": not ok, **{f"{name}_attenuation_gap_kg": gap[mask, pi].sum() for name, mask in masks.items()}})
                total_vmt = cells.analysis_vmt.sum()
                plausibility_rows.append({"design": design, "slowdown_pct": slow, "replicate": rep, "solved_faster_pct": fast, "min_scenario_speed_mph": speed.min(), "max_scenario_speed_mph": speed.max(), **{f"vmt_share_above_{threshold}_mph": cells.loc[speed > threshold, "analysis_vmt"].sum() / total_vmt for threshold in [40, 50, 60]}})
            print(f"{design} slowdown {slow:g}: 500 realizations", flush=True)
    structured = pd.DataFrame(result_rows)
    structured.to_csv(locate("phase3/results/structured_replicates.csv"), index=False)
    all_results = pd.concat([random_frame, structured], ignore_index=True)
    summary_columns = ["solved_faster_pct", "crz_change_pct", "city_change_pct", "delta_kg", "attenuation_pct"]
    summary = quantile_summary(all_results, ["design", "slowdown_pct", "pollutant"], summary_columns)
    summary.to_csv(locate("phase3/results/placement_emissions_summary.csv"), index=False)
    random_summary = summary[summary.design.eq("random")].drop(columns="design")
    comparisons = summary[~summary.design.eq("random")].merge(random_summary, on=["slowdown_pct", "pollutant"], suffixes=("", "_random"), validate="many_to_one")
    comparisons["structured_shift_pp"] = comparisons.crz_change_pct_p50 - comparisons.crz_change_pct_p50_random
    comparisons["structured_shift_relative_to_random_interval"] = np.where(comparisons.crz_change_pct_p50 < comparisons.crz_change_pct_p05_random, "below", np.where(comparisons.crz_change_pct_p50 > comparisons.crz_change_pct_p95_random, "above", "inside"))
    comparisons.to_csv(locate("phase3/results/structured_vs_random_summary.csv"), index=False)

    characteristics = []
    for si, slow in enumerate(SLOWS):
        groups = exp.allocations[si]
        for stat in ["P05", "P50", "P95"]:
            characteristics.append(slower_characteristics("random", stat, slow, groups, segment, cells, baseline))
    for design, groups in designs.items():
        characteristics.append(slower_characteristics(design, "exact", np.nan, groups[:1], segment, cells, baseline))
    pd.DataFrame(characteristics).to_csv(locate("phase3/results/slower_group_characteristics.csv"), index=False)

    decomposition = pd.DataFrame(decomposition_rows)
    dec_columns = ["faster_group_delta_kg", "unchanged_group_delta_kg", "slower_group_delta_kg", "net_delta_kg", "offset_ratio", "street_attenuation_gap_kg", "highway_family_attenuation_gap_kg", "lt20_attenuation_gap_kg", "gt50_attenuation_gap_kg"]
    dec_summary = quantile_summary(decomposition[decomposition.design.isin(["high_vmt", "infrastructure_first"])], ["design", "slowdown_pct", "pollutant"], dec_columns)
    dec_summary["invalid_offset_n"] = decomposition[decomposition.design.isin(["high_vmt", "infrastructure_first"])].groupby(["design", "slowdown_pct", "pollutant"]).invalid_offset_flag.sum().to_numpy()
    dec_summary.to_csv(locate("phase3/results/structured_decomposition_summary.csv"), index=False)

    plausibility = pd.DataFrame(plausibility_rows)
    plaus_columns = ["solved_faster_pct", "min_scenario_speed_mph", "max_scenario_speed_mph", "vmt_share_above_40_mph", "vmt_share_above_50_mph", "vmt_share_above_60_mph"]
    plaus = quantile_summary(plausibility, ["design", "slowdown_pct"], plaus_columns)
    maxima = plausibility.groupby(["design", "slowdown_pct"]).solved_faster_pct.max().rename("solved_faster_pct_max").reset_index()
    plaus = plaus.merge(maxima, on=["design", "slowdown_pct"], validate="one_to_one")
    plaus["uplift_above_40_flag"] = plaus.solved_faster_pct_max > 40
    plaus["interpretation"] = "implied balancing speed gains required to preserve the +5.6% aggregate benchmark"
    plaus.to_csv(locate("phase3/results/solved_uplift_plausibility.csv"), index=False)

    # M6: all four slowdowns, same high-VMT slower set and paired remaining allocations.
    sensitivity_rows = []
    high_groups = designs["high_vmt"]
    primary_high = structured[structured.design.eq("high_vmt")]
    for mode_idx, mode in enumerate(modes):
        for slow in SLOWS:
            for rep, group in enumerate(high_groups):
                fast, result = evaluate_one(exp, state, group, exposures[mode_idx], slow)
                for pol in POLS:
                    primary = primary_high.query("slowdown_pct == @slow and replicate == @rep and pollutant == @pol").iloc[0]
                    sensitivity_rows.append({"averaging_definition": mode, "slowdown_pct": slow, "replicate": rep, "pollutant": pol, "solved_faster_pct": fast, "crz_change_pct": result[f"crz_{pol}_change_pct"], "difference_from_vmt_primary_pp": result[f"crz_{pol}_change_pct"] - primary.crz_change_pct})
    sensitivity_raw = pd.DataFrame(sensitivity_rows)
    sensitivity_raw.to_csv(locate("phase3/results/structured_averaging_definition_replicates.csv"), index=False)
    quantile_summary(sensitivity_raw, ["averaging_definition", "slowdown_pct", "pollutant"], ["solved_faster_pct", "crz_change_pct", "difference_from_vmt_primary_pp"]).to_csv(locate("phase3/results/structured_averaging_definition_sensitivity.csv"), index=False)

    figure = summary.copy()
    figure["retained_uniform_benefit_pct_p50"] = 100 * figure.crz_change_pct_p50 / figure.pollutant.map({p: uniform[f"crz_{p}_change_pct"] for p in POLS})
    figure["include_main_figure"] = figure.design.isin(["random", "high_vmt", "infrastructure_first"])
    figure.to_csv(locate("phase3/results/structured_placement_figure_data.csv"), index=False)

    target = TARGET[2]
    max_length_deviation = 0.0
    allocation_rows = []
    for design, groups in designs.items():
        for rep, group in enumerate(groups):
            shares = np.bincount(group, weights=lengths, minlength=3) / lengths.sum()
            max_length_deviation = max(max_length_deviation, abs(shares[2] - target))
            allocation_rows.append({"design": design, "replicate": rep, "faster_length_share": shares[0], "unchanged_length_share": shares[1], "slower_length_share": shares[2], "slower_deviation_from_target": shares[2] - target})
    pd.DataFrame(allocation_rows).to_csv(locate("phase3/provenance/achieved_length_shares.csv"), index=False)
    check("All structured realization counts", structured.groupby(["design", "slowdown_pct", "pollutant"]).size().eq(500).all(), len(structured))
    check("Aggregate +5.6% constraint", max_constraint_error <= 1e-10, max_constraint_error)
    check("VMT closure", max_vmt_error <= 1e-7, max_vmt_error)
    check("Emissions closure", max_emissions_error <= 1e-10, max_emissions_error)
    check("No MOVES extrapolation", plausibility.max_scenario_speed_mph.max() <= 75 and plausibility.min_scenario_speed_mph.min() >= 2.5, (plausibility.min_scenario_speed_mph.min(), plausibility.max_scenario_speed_mph.max()))
    check("Same frozen denominators", all(abs(uniform[f"crz_{p}_baseline_kg"] - saved[f"crz_{p}_baseline_kg"].iloc[0]) <= 1e-10 for p in POLS), "unchanged")
    check("Source files unchanged", all(Path(path).exists() and digest(path) == value for path, value in frozen.items()), len(frozen))
    metadata = {"phase3_master_seed": MASTER_SEED, "target_length_shares": {"faster": TARGET[0], "unchanged": TARGET[1], "slower": TARGET[2]}, "physical_segments": len(segment), "total_physical_length_feet": float(lengths.sum()), "analysis_window_vmt": float(cells.analysis_vmt.sum()), "max_slower_length_share_deviation": max_length_deviation, "phase1b_reproduction_max_abs_error": max_error, "allocation_sha256": sha(locate("phase3/provenance/structured_allocations.npz")), "frozen_phase1b_allocation_sha256": sha(locate("phase1b/qa/paired_allocations.npz")), "rate_surface_sha256": sha(locate("phase1b/rates/moves5_composite_rates.csv")), "full_day_denominator_source": "Frozen Phase 1B state using the matched full-day MOVES composite surface", "scenario_counts": {"designs": 3, "realizations_per_design": 500, "slowdowns": 4, "pollutants": 3}}
    (locate("phase3/provenance/phase3_manifest.json")).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (locate("phase3/qa/checks.json")).write_text(json.dumps(CHECKS, indent=2), encoding="utf-8")
    report = ["PHASE 3 QA REPORT", "Status: PASSED", ""] + [f"PASS {x['test']}: {x['detail']}" for x in CHECKS]
    report += ["", f"Physical segments: {len(segment)}", f"Total physical length (feet): {lengths.sum():.12f}", f"Analysis-window VMT: {cells.analysis_vmt.sum():.12f}", f"New Phase 3 master seed: {MASTER_SEED}", "No MOVES run, rate changes, new baseline assignment, or manuscript edits were performed."]
    (locate("phase3/PHASE3_QA_REPORT.txt")).write_text("\n".join(report) + "\n", encoding="utf-8")
    print("Phase 3 computation and QA passed.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        (locate("phase3/PHASE3_QA_REPORT.txt")).write_text("PHASE 3 QA REPORT\nStatus: FAILED - STOP\n" + json.dumps(CHECKS, indent=2) + "\n" + traceback.format_exc(), encoding="utf-8")
        raise
