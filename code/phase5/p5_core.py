"""Shared Phase 5 helpers built on the frozen Phase 1B engine.

Nothing here edits frozen inputs. Bytecode writing is disabled before importing
phase1b/code so that its __pycache__ is not touched.
"""
from pathlib import Path
import json, sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate
RESULTS, QA, SI = locate("phase5_revision/results"), locate("phase5_revision/qa"), locate("phase5_revision/si_tables")
sys.path.insert(0, str(locate("phase1b/code")))

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

from common import POLS, EV, SPEEDS, sha
from engine import Experiment, Surface, interpolate, evaluate

SLOWS = [5.0, 10.0, 15.0, 20.0]
TARGET_GAIN = 0.056
WINDOW_PERIODS = ["am_peak", "midday", "pm_peak"]
A2_SEED = 20261104
PROFILES = {"base_x1.0": 1.0, "street_x0.8": 0.8, "street_x1.2": 1.2}
OPTIONAL_PROFILES = {"street_x0.7": 0.7}
FAST, UNCH, SLOW = 0, 1, 2


class Checks:
    """Named QA results for one stage, persisted to qa/checks_<stage>.json."""

    def __init__(self, stage):
        self.stage, self.rows = stage, []

    def add(self, name, passed, detail, hard=True):
        self.rows.append({"stage": self.stage, "test": name, "passed": bool(passed), "detail": str(detail)})
        print(("PASS " if passed else "FAIL ") + f"{name}: {detail}", flush=True)
        if hard and not passed:
            self.save()
            raise RuntimeError(f"{name}: {detail}")

    def save(self):
        (locate(f"phase5_revision/qa/checks_{self.stage}.json")).write_text(json.dumps(self.rows, indent=2), encoding="utf-8")


def make_experiment(scale=1.0):
    """Experiment with Street window-period speeds scaled in every place they are held.

    Experiment caches self.speed at construction and setup()/run_one() read that copy,
    so changing pairs.speed_mph alone would silently leave the baseline unscaled.
    """
    exp = Experiment()
    if scale != 1.0:
        for frame in (exp.pairs, exp.activity, exp.cells):
            mask = frame.roadway_type.eq("Street") & frame.period.isin(WINDOW_PERIODS)
            frame.loc[mask, "speed_mph"] = frame.loc[mask, "speed_mph"] * scale
        exp.speed = exp.pairs.speed_mph.to_numpy(float)
    exp.cell_speed = exp.speed[exp.pair]
    exp.n_seg = exp.allocations.shape[-1]
    exp.exposure = np.bincount(exp.segment, weights=exp.vmt * exp.cell_speed, minlength=exp.n_seg)
    return exp


def solve_gain(exposure, group, slow_pct, unch=0.0):
    """Faster-road gain (%) that keeps the VMT-weighted mean speed change at +5.6%.

    unch is a signed fraction: a scalar for a fixed change, or an array with one value
    per physical segment. Only unchanged-group segments contribute.
    """
    a_fast = exposure[group == FAST].sum()
    a_slow = exposure[group == SLOW].sum()
    unchanged = group == UNCH
    u = np.broadcast_to(np.asarray(unch, float), exposure.shape)
    unch_term = np.dot(u[unchanged], exposure[unchanged])
    return 100 * (TARGET_GAIN * exposure.sum() + slow_pct / 100 * a_slow - unch_term) / a_fast


def segment_multiplier(group, gain_pct, slow_pct, unch=0.0):
    """Per-physical-segment speed multiplier."""
    u = np.broadcast_to(np.asarray(unch, float), group.shape)
    return np.where(group == FAST, 1 + gain_pct / 100, np.where(group == SLOW, 1 - slow_pct / 100, 1 + u))


def constraint_error_pp(exposure, multiplier):
    """Achieved minus target VMT-weighted speed change, in percentage points."""
    return abs(100 * (np.dot(exposure, multiplier) / exposure.sum() - 1) - 100 * TARGET_GAIN)


def linear_rates(y, pair, speed):
    """Same arithmetic as engine.interpolate, gathering each cell's curve by pair index."""
    return extended_rates(y, pair, speed, speed)


def extended_rates(y, pair, speed, anchor_speed):
    """Rate at speed on the linear segment occupied by anchor_speed, extended if necessary."""
    lower = np.clip(np.searchsorted(SPEEDS, anchor_speed, side="right") - 1, 0, len(SPEEDS) - 2)
    fraction = (speed - SPEEDS[lower]) / (SPEEDS[lower + 1] - SPEEDS[lower])
    return y[pair, lower, :] + fraction[:, None] * (y[pair, lower + 1, :] - y[pair, lower, :])


class Pchip:
    """Monotone cubic through the 16 MOVES bin centers for a (curve, bin, pollutant) cube."""

    def __init__(self, y):
        self.spline = PchipInterpolator(SPEEDS, y, axis=1)
        self.c = self.spline.c  # (4, 15, curves, pollutants)

    def rates(self, pair, speed):
        lower = np.clip(np.searchsorted(SPEEDS, speed, side="right") - 1, 0, len(SPEEDS) - 2)
        dx = (speed - SPEEDS[lower])[:, None]
        c = self.c
        return ((c[0, lower, pair] * dx + c[1, lower, pair]) * dx + c[2, lower, pair]) * dx + c[3, lower, pair]


def denominators(exp, rates):
    """Full-day CRZ and city baselines (kg/day) from full-day rates, as in Experiment.setup."""
    ice = 1 - exp.activity.truck_type.map(EV).to_numpy(float)
    crz = np.sum(rates * (exp.activity.crz_vmt.to_numpy() * ice)[:, None] / 1000, axis=0)
    city = np.sum(rates * (exp.activity.city_vmt.to_numpy() * ice)[:, None] / 1000, axis=0)
    return crz, city


class Model:
    """Cell-level evaluator; supports per-segment multipliers the frozen run_one cannot."""

    def __init__(self, exp, interpolation="linear", denominator=None):
        self.exp, self.interpolation = exp, interpolation
        self.state = exp.setup("primary", "base", "primary")
        self.y = self.state["y"]
        self.pairs_idx = np.arange(len(exp.pairs))
        if interpolation == "linear":
            self.crz = self.state["crz"]
            self.baseline = self.state["baseline"]
            self._rates = lambda pair, speed: linear_rates(self.y, pair, speed)
        elif interpolation == "pchip":
            window = Pchip(self.y)
            full_y = Surface("primary").cube(exp.activity, "full_day", "primary")
            full = Pchip(full_y)
            activity_speed = exp.activity.speed_mph.to_numpy(float)
            self.crz, _ = denominators(exp, full.rates(np.arange(len(exp.activity)), activity_speed))
            if denominator == "linear":  # Pilot-condition diagnostic only.
                self.crz = self.state["crz"]
            self.baseline = window.rates(self.pairs_idx, exp.speed)
            self._rates = window.rates
        else:
            raise ValueError(interpolation)
        self.base_cell = self.baseline[exp.pair]

    def speeds(self, multiplier_by_segment):
        return self.exp.cell_speed * multiplier_by_segment[self.exp.segment]

    def cell_delta(self, speed):
        """kg/day change for every cell at the supplied scenario speeds."""
        return self.exp.ice[:, None] * (self._rates(self.exp.pair, speed) - self.base_cell) / 1000

    def run(self, multiplier_by_segment):
        speed = self.speeds(multiplier_by_segment)
        delta = self.cell_delta(speed).sum(axis=0)
        out = {
            "min_scenario_speed_mph": float(speed.min()),
            "max_scenario_speed_mph": float(speed.max()),
            "scenario_vmt": float(self.exp.vmt.sum()),
            "clipped_vmt": float(self.exp.vmt[(speed < SPEEDS[0]) | (speed > SPEEDS[-1])].sum()),
        }
        for i, pol in enumerate(POLS):
            out[f"{pol}_delta_kg_per_day"] = float(delta[i])
            out[f"crz_{pol}_change_pct"] = float(100 * delta[i] / self.crz[i])
        return out


def load_designs():
    """{name: (groups[4 levels, 500, n_seg], seeds[4, 500])} for each allocation design."""
    random = np.load(locate("phase1b/qa/paired_allocations.npz"))
    structured = np.load(locate("phase3/provenance/structured_allocations.npz"))
    designs = {"random": (random["groups"], random["seeds"])}
    for index, name in enumerate(["high_vmt", "infrastructure_first", "low_vmt"]):
        # One allocation set is reused at all four slowdown levels for structured designs.
        groups = np.broadcast_to(structured[name], (4,) + structured[name].shape)
        seeds = np.broadcast_to(structured["seeds"][index], (4, 500))
        designs[name] = (groups, seeds)
    return designs


def summarize(frame, keys, uniform=None):
    """Long P05/P50/P95 summary per pollutant from a wide replicate frame."""
    rows = []
    for key, group in frame.groupby(keys, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        for pol in POLS:
            record = dict(zip(keys, key))
            record.update(pollutant=pol, n_replicates=len(group))
            pct, kg = group[f"crz_{pol}_change_pct"], group[f"{pol}_delta_kg_per_day"]
            for q, tag in [(0.05, "p05"), (0.5, "p50"), (0.95, "p95")]:
                record[f"crz_change_pct_{tag}"] = pct.quantile(q)
                record[f"delta_kg_per_day_{tag}"] = kg.quantile(q)
                record[f"gain_pct_{tag}"] = group.gain_pct.quantile(q)
            if uniform is not None:
                u = uniform(record, pol)
                record["uniform_crz_change_pct"] = u
                attenuation = 100 * (1 - pct / u)
                for q, tag in [(0.05, "p05"), (0.5, "p50"), (0.95, "p95")]:
                    record[f"attenuation_pct_{tag}"] = attenuation.quantile(q)
            record["min_scenario_speed_mph"] = group.min_scenario_speed_mph.min()
            record["max_scenario_speed_mph"] = group.max_scenario_speed_mph.max()
            rows.append(record)
    return pd.DataFrame(rows)
