"""Wait for and export the matched full-day rate run, then audit daytime overlap."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
import sys,io,time,json
from datetime import datetime,timezone
import numpy as np,pandas as pd
from common import *
sys.path.insert(0,str(locate("phase1a")))  # needs Phase 1A MOVES helpers (not included)
from moves_db import query
from phase1_moves5_validate import select_rates
DB="phase1b_nyc2025_full_rates_output_20261002"
def table(sql):
    answer=query(sql)
    return pd.read_csv(io.StringIO(answer),sep="\t") if answer.strip() else pd.DataFrame()
def main():
    deadline=time.monotonic()+4*3600
    previous=None
    while True:
        run=table(f"SELECT * FROM {DB}.movesrun ORDER BY MOVESRunID DESC LIMIT 1")
        errors=table(f"SELECT * FROM {DB}.moveserror")
        if len(errors):raise RuntimeError("MOVES supplemental run failed")
        if not len(run):
            if time.monotonic()>deadline:raise TimeoutError("MOVES run metadata did not appear")
            time.sleep(30)
            continue
        if len(run)!=1:raise RuntimeError("Ambiguous supplemental run")
        r=run.iloc[0]
        progress=(int(r.retrievedDONEFiles),int(r.expectedDONEFiles))
        log=(locate("phase1b/provenance/full_day_rates_console.log")).read_text(errors="replace")
        if progress!=previous:
            state=dict(status="running",completed_bundles=progress[0],expected_bundles=progress[1],updated_utc=datetime.now(timezone.utc).isoformat())
            save_json(locate("phase1b/qa/full_day_run_status.json"),state);print(json.dumps(state),flush=True);previous=progress
        if progress[0]==progress[1] and progress[1]>0 and "Java Result: 1" not in log:break
        if "BUILD FAILED" in log or "Java Result: 1" in log:raise RuntimeError("Supplemental MOVES process failed")
        if time.monotonic()>deadline:raise TimeoutError("Wait limit reached; MOVES has not been stopped")
        time.sleep(30)
    if not (r.massUnits=="g" and r.distanceUnits=="mi" and r.scale=="Rates" and r.masterVersion=="MOVES5.0.1" and r.domainCountyID==36061 and r.defaultDatabaseUsed=="movesdb20241112"):raise ValueError("Supplemental configuration differs")
    moves_run_id=int(r.MOVESRunID)
    sql=f"""SELECT 36061 AS countyID,r.* FROM {DB}.rateperdistance r
WHERE MOVESRunID={moves_run_id} AND yearID=2025 AND dayID=5 AND monthID BETWEEN 1 AND 10
AND hourID BETWEEN 1 AND 24 AND fuelTypeID=2 AND processID=1
AND sourceTypeID IN (52,53,61,62) AND roadTypeID IN (4,5)
AND pollutantID IN (90,3,110) AND avgSpeedBinID BETWEEN 1 AND 16
ORDER BY sourceTypeID,roadTypeID,pollutantID,avgSpeedBinID,monthID,hourID;
"""
    raw=table(sql);select_rates(raw,list(range(1,11)),list(range(1,25)))
    raw.to_csv(locate("phase1b/rates/moves5_full_day_raw.csv"),index=False)
    (locate("phase1b/provenance/full_day_rate_export.sql")).write_text(sql)
    run.to_csv(locate("phase1b/provenance/full_day_rate_movesrun.csv"),index=False)
    old=pd.read_csv(locate("phase1a/results/moves5_rateperdistance_nyc_2025.csv"))
    keys=["sourceTypeID","roadTypeID","pollutantID","avgSpeedBinID","monthID","hourID"]
    overlap=old[keys+["ratePerDistance"]].merge(raw[keys+["ratePerDistance"]],on=keys,suffixes=("_phase1a","_full_day"),validate="one_to_one")
    if len(overlap)!=38400:raise ValueError("Daytime overlap incomplete")
    overlap["abs_difference"]=abs(overlap.ratePerDistance_phase1a-overlap.ratePerDistance_full_day)
    overlap["relative_difference"]=overlap.abs_difference/overlap.ratePerDistance_phase1a
    overlap.to_csv(locate("phase1b/qa/daytime_overlap_comparison.csv"),index=False)
    maximum=float(overlap.relative_difference.max())
    if maximum>1e-4:raise RuntimeError("STOP: overlapping daytime rates differ by more than 0.01%")
    manifest=dict(status="completed",database=DB,input_database=r.domainDatabaseName,moves_version=r.masterVersion,default_database=r.defaultDatabaseUsed,units="g/mile",county_id=36061,year=2025,months=list(range(1,11)),hours=list(range(1,25)),day_id=5,fuel_id=2,source_types=[52,53,61,62],road_types=[4,5],pollutants=[90,3,110],process_id=1,rows=len(raw),minutes_duration=float(r.minutesDuration),completed_bundles=progress[0],error_rows=0,max_daytime_relative_difference=maximum,overlap_tolerance=1e-4,raw_sha256=sha(locate("phase1b/rates/moves5_full_day_raw.csv")),phase1a_raw_sha256=sha(locate("phase1a/results/moves5_rateperdistance_nyc_2025.csv")),runspec_sha256=sha(locate("phase1b/provenance/full_day_rates.mrs")))
    save_json(locate("phase1b/provenance/full_day_rate_manifest.json"),manifest)
    save_json(locate("phase1b/qa/full_day_run_status.json"),dict(status="completed",rows=len(raw),daytime_overlap_passed=True))
    print(json.dumps(manifest,indent=2))
if __name__=="__main__":main()

