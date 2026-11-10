"""A4 (R1.4): absolute kg/day and g/day values from the same replicates as the percentages."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from p5_core import *

EXPECTED_BASELINE = {"CO2": 70880.2, "NOx": 205.58, "PM25": 3.024}
TOLERANCE = {"CO2": 0.05, "NOx": 0.005, "PM25": 0.0005}
TABLE1 = {("random", 5.0), ("random", 10.0), ("random", 15.0), ("random", 20.0), ("high_vmt", 20.0), ("infrastructure_first", 20.0)}
COLUMNS = [("CO2", "co2_delta_kg_per_day", 1), ("NOx", "nox_delta_kg_per_day", 1), ("PM25", "pm25_delta_g_per_day", 1000)]


def main():
    checks = Checks("a4")
    frame = pd.read_csv(locate("phase5_revision/results/a1_replicates.csv")).query("profile == 'base_x1.0'")
    uniform = pd.read_csv(locate("phase5_revision/results/a1_uniform.csv")).query("profile == 'base_x1.0'").set_index("pollutant")
    baseline = uniform.crz_baseline_kg_per_day
    for pol in POLS:
        checks.add(f"{pol} full-day CRZ baseline", abs(baseline[pol] - EXPECTED_BASELINE[pol]) <= TOLERANCE[pol], f"{baseline[pol]:.4f} kg/day")
    record = dict(design="uniform", slowdown_pct=0.0, in_manuscript_table1=True, gain_pct_p50=5.6, n_replicates=1)
    for pol, key, factor in COLUMNS:
        record[f"{key}_p50"] = factor * uniform.uniform_delta_kg_per_day[pol]
        record[f"{key}_p05"] = record[f"{key}_p95"] = np.nan  # Uniform is one deterministic case.
        record[f"{pol.lower()}_crz_change_pct_p50"] = uniform.uniform_crz_change_pct[pol]
    rows, worst = [record], 0.0
    for (design, slow), group in frame.groupby(["design", "slowdown_pct"], sort=False):
        record = dict(design=design, slowdown_pct=slow, in_manuscript_table1=(design, slow) in TABLE1, gain_pct_p50=group.gain_pct.median(), n_replicates=len(group))
        for pol, key, factor in COLUMNS:
            values = group[f"{pol}_delta_kg_per_day"]
            for q, tag in [(0.05, "p05"), (0.5, "p50"), (0.95, "p95")]:
                record[f"{key}_{tag}"] = factor * values.quantile(q)
                worst = max(worst, abs(100 * values.quantile(q) / baseline[pol] - group[f"crz_{pol}_change_pct"].quantile(q)))
            record[f"{pol.lower()}_crz_change_pct_p50"] = group[f"crz_{pol}_change_pct"].median()
        rows.append(record)
    out = pd.DataFrame(rows)
    out.to_csv(locate("phase5_revision/results/a4_absolute_changes.csv"), index=False)
    pd.DataFrame([dict(pollutant=p, crz_baseline_kg_per_day=baseline[p], crz_baseline_g_per_day=1000 * baseline[p]) for p in POLS]).to_csv(locate("phase5_revision/results/a4_baselines.csv"), index=False)
    checks.add("Absolute and percentage quantiles are the same replicates", worst <= 1e-10, f"max abs diff {worst:.3e} pp")
    checks.save()
    print(out[out.in_manuscript_table1][["design", "slowdown_pct", "co2_delta_kg_per_day_p50", "co2_delta_kg_per_day_p05", "co2_delta_kg_per_day_p95", "nox_delta_kg_per_day_p50", "pm25_delta_g_per_day_p50"]].to_string(index=False))


if __name__ == "__main__":
    main()
