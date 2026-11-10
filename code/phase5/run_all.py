"""Rerun the Phase 5 revision analyses (SI S12-S15). Needs the withheld inputs under CRZ_INPUTS.

Stages run in order and stop at the first failure; Step 0 first reproduces the
submitted Phase 1B and Phase 3 results. Each stage writes its CSVs to
results/phase5/ and its checks to results/phase5/qa/checks_<stage>.json.
"""
import subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from paths import INPUTS, missing_inputs

NEEDED = ["phase1b/qa/scenario_cells.csv", "phase1b/qa/physical_segments.csv", "phase1b/qa/baseline_activity.csv",
          "phase1b/qa/legacy_replicates.csv", "phase1b/qa/paired_allocations.npz", "phase3/provenance/structured_allocations.npz"]
STAGES = ["step0_reproduce.py", "a1_baseline_speed.py", "a2_unchanged_roads.py", "a3_step_mechanism.py",
          "a4_absolute_values.py", "crosscheck_pilot.py"]


def main():
    missing = missing_inputs(NEEDED)
    if missing:
        raise SystemExit(f"Cannot run: withheld inputs are missing from CRZ_INPUTS ({INPUTS}).\n  "
                         + "\n  ".join(missing) + "\nThese are available from the authors on request; see README.md.")
    for stage in STAGES:
        print("==", stage, flush=True)
        subprocess.run([sys.executable, "-B", str(HERE / stage)], cwd=HERE, check=True)


if __name__ == "__main__":
    main()
