"""Gate MOVES scenarios on reproduction by the new vectorized framework."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
import json
import numpy as np,pandas as pd
from common import *
from engine import Experiment
def main():
    exp=Experiment()
    state=exp.setup("primary","base","primary",legacy=True)
    actual=exp.run_all(state,"legacy_framework")
    reference=exp.legacy_reps
    checks=[]
    for name in ["solved_faster_pct"]+[f"{scope}_{p}_change_pct" for scope in ["crz","city"] for p in POLS]:
        error=float(np.max(np.abs(actual[name].to_numpy()-reference[name].to_numpy())))
        checks.append(dict(test="new_framework_2000_replicates",metric=name,abs_error=error,tolerance=1e-8,passed=error<=1e-8))
    uniform=exp.uniform(state)
    ref_uniform=pd.read_csv(locate("phase1b/qa/legacy_uniform.csv")).iloc[0]
    for name in [f"{scope}_{p}_change_pct" for scope in ["crz","city"] for p in POLS]:
        error=abs(uniform[name]-ref_uniform[name])
        checks.append(dict(test="new_framework_uniform",metric=name,reference=ref_uniform[name],actual=uniform[name],abs_error=error,tolerance=1e-8,passed=error<=1e-8))
    result=pd.DataFrame(checks)
    result.to_csv(locate("phase1b/qa/framework_legacy_reproduction.csv"),index=False)
    combined=pd.concat([pd.read_csv(locate("phase1b/qa/legacy_reproduction.csv")),result],ignore_index=True)
    combined.to_csv(locate("phase1b/qa/legacy_reproduction.csv"),index=False)
    if not result.passed.all():raise RuntimeError("STOP: new framework fails legacy reproduction")
    actual.to_csv(locate("phase1b/qa/framework_legacy_replicates.csv"),index=False)
    # Quantify the pre-existing rounded-VMT/stored-emission inconsistency.
    consistent=exp.setup("primary","base","primary",legacy=True,consistent_legacy=True)
    control=exp.uniform(consistent)
    control_rows=[dict(pollutant=p,archived_change_pct=uniform[f"crz_{p}_change_pct"],consistent_baseline_change_pct=control[f"crz_{p}_change_pct"],difference_pp=control[f"crz_{p}_change_pct"]-uniform[f"crz_{p}_change_pct"]) for p in POLS]
    pd.DataFrame(control_rows).to_csv(locate("phase1b/qa/legacy_rounding_control.csv"),index=False)
    save_json(locate("phase1b/qa/framework_gate.json"),dict(status="passed",max_abs_error=float(result.abs_error.max()),tolerance=1e-8,paired_allocation_sha256=sha(locate("phase1b/qa/paired_allocations.npz")),rows=2000,ev_fractions=EV))
    print(result.to_string(index=False))
    print(pd.DataFrame(control_rows).to_string(index=False))
if __name__=="__main__":main()

