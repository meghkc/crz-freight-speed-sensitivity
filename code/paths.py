"""One place that says where every file lives.

The analysis scripts were written against the original working layout
(phase1b/qa/..., phase3/results/..., and so on). They now ask `locate()` for
each file by that original project-relative path, and this module maps it to
the repository layout:

    excluded inputs  -> $CRZ_INPUTS/<original path>   (default: <repo>/inputs)
    everything else  -> rates/, provenance/, results/ in this repository

Excluded inputs are the files derived from the proprietary freight assignment
(listed in WITHHELD), the assignment itself (data/), the upstream freight model
(freight_model/) and the large Phase 2R cell-level export (phase2r/raw/).
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODE = REPO / "code"
RATES = REPO / "rates"
PROVENANCE = REPO / "provenance"
RESULTS = REPO / "results"
INPUTS = Path(os.environ.get("CRZ_INPUTS") or REPO / "inputs").resolve()
# Only the MOVES launchers use this; set it to your MOVES5 installation folder.
MOVES_HOME = os.environ.get("MOVES_HOME", "")

# Files derived from the proprietary assignment. Available from the authors on request.
WITHHELD = [
    "phase1b/qa/scenario_cells.csv",
    "phase1b/qa/physical_segments.csv",
    "phase1b/qa/baseline_activity.csv",
    "phase1b/qa/legacy_replicates.csv",
    "phase1b/qa/paired_allocations.npz",
    "phase3/provenance/structured_allocations.npz",
    "phase3/provenance/physical_segment_eligibility.csv",
    "phase2r/provenance/physical_segment_index.csv",
]

# Original prefix -> new location. The first matching prefix wins.
ROUTES = [
    ("data/", INPUTS / "data"),
    ("freight_model/", INPUTS / "freight_model"),
    ("phase2r/raw/", INPUTS / "phase2r/raw"),
    ("phase1a/results/moves5_rateperdistance_nyc_2025.csv", RATES / "moves5_rateperdistance_nyc_2025.csv"),
    ("phase1a/", PROVENANCE / "phase1a"),
    ("phase1b/rates/", RATES),
    ("phase1b/provenance/", PROVENANCE / "phase1b"),
    ("phase1b/results/", RESULTS / "phase1b"),
    ("phase1b/qa/", RESULTS / "phase1b/qa"),
    ("phase1b/figures/", RESULTS / "phase1b/figures"),
    ("phase1b/code/", CODE / "phase1b"),
    ("phase2/results/", RESULTS / "phase2"),
    ("phase2/", RESULTS / "phase2"),
    ("phase2r/METRIC_DEFINITIONS.md", PROVENANCE / "phase2/METRIC_DEFINITIONS.md"),
    ("phase2r/provenance/", PROVENANCE / "phase2"),
    ("phase2r/results/", RESULTS / "phase2/repaired"),
    ("phase2r/", RESULTS / "phase2/repaired"),
    ("phase3/provenance/", PROVENANCE / "phase3"),
    ("phase3/results/", RESULTS / "phase3"),
    ("phase3/", RESULTS / "phase3"),
    ("phase4/", RESULTS / "figures_tables"),
    ("phase5_revision/results/", RESULTS / "phase5"),
    ("phase5_revision/", RESULTS / "phase5"),
]


def locate(original):
    """Return the path for a file named by its original project-relative path."""
    rel = str(original).replace("\\", "/").strip("/")
    if rel in WITHHELD:
        return INPUTS / rel
    for prefix, target in ROUTES:
        if rel == prefix.rstrip("/"):
            return target
        if prefix.endswith("/") and rel.startswith(prefix):
            path = target / rel[len(prefix):]
            if INPUTS not in path.parents:
                path.parent.mkdir(parents=True, exist_ok=True)
            return path
        if rel == prefix:
            return target
    raise KeyError(f"No location configured for {original!r}")


def phase_files(phase):
    """Files that came from one original phase folder (e.g. "phase1b"), for provenance hashes.

    The original scripts hashed whole phase folders; those files are now spread over
    code/, rates/, provenance/, results/ and CRZ_INPUTS. Each file is assigned to the
    most specific route that contains it.
    """
    phases = {prefix.split("/")[0] for prefix, _ in ROUTES} | {name.split("/")[0] for name in WITHHELD}
    routes = ROUTES + [(f"{ph}/", INPUTS / ph) for ph in phases]
    files = set()
    for prefix, target in routes:
        if prefix.startswith(phase + "/") and target.exists():
            files.update([target] if target.is_file() else (f for f in target.rglob("*") if f.is_file()))

    def owner(path):
        matches = [(len(t.parts) + (path == t), p) for p, t in routes if path == t or t in path.parents]
        return max(matches)[1].split("/")[0]
    return sorted(f for f in files if owner(f) == phase and "__pycache__" not in f.parts)


def display(path):
    """Path relative to the repository, or to $CRZ_INPUTS for excluded inputs."""
    path = Path(path)
    if path.is_relative_to(REPO):
        return path.relative_to(REPO).as_posix()
    return "$CRZ_INPUTS/" + path.relative_to(INPUTS).as_posix()


def missing_inputs(names=WITHHELD):
    """Withheld inputs that are not yet present under CRZ_INPUTS."""
    return [name for name in names if not (INPUTS / name).is_file()]
