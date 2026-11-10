"""Export matched full-day activity and derive finest-cell diesel VMT weights."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
import sys,io,json
import numpy as np,pandas as pd
from common import *
sys.path.insert(0,str(locate("phase1a")))  # needs Phase 1A MOVES helpers (not included)
from moves_db import query
DB="phase1b_nyc2025_full_activity_output_20261002"
def table(sql):
    result=query(sql)
    return pd.read_csv(io.StringIO(result),sep="\t") if result.strip() else pd.DataFrame()
def main():
    run=table(f"SELECT * FROM {DB}.movesrun")
    r=run.iloc[0]
    if len(run)!=1 or r.expectedDONEFiles!=r.retrievedDONEFiles or r.distanceUnits!="mi" or r.outputTimePeriod!="Hour":raise ValueError("Incomplete/incorrect activity run")
    errors=table(f"SELECT * FROM {DB}.moveserror")
    if len(errors):raise ValueError("Activity errors")
    raw=table(f"SELECT * FROM {DB}.movesactivityoutput WHERE activityTypeID=1")
    raw.to_csv(locate("phase1b/provenance/moves_activity_distance_full_day.csv"),index=False)
    run.to_csv(locate("phase1b/provenance/activity_movesrun.csv"),index=False)
    errors.to_csv(locate("phase1b/provenance/activity_moveserror.csv"),index=False)
    use=raw[(raw.fuelTypeID==2)&raw.roadTypeID.isin([4,5])].copy()
    keys=["sourceTypeID","roadTypeID","monthID","hourID"]
    expected=pd.MultiIndex.from_product([[52,53,61,62],[4,5],range(1,11),range(1,25)],names=keys)
    actual=pd.MultiIndex.from_frame(use[keys])
    if len(use)!=1920 or use.duplicated(keys).any() or len(expected.difference(actual)):raise ValueError("Incomplete/duplicate diesel activity")
    if not ((use.yearID==2025)&(use.dayID==5)&(use.countyID==36061)&(use.MOVESRunID==1)).all():raise ValueError("Activity scope mismatch")
    if not np.isfinite(use.activity).all() or not (use.activity>0).all():raise ValueError("Nonpositive/nonfinite distance")
    for name in ["modelYearID","regClassID","SCC"]:
        if not use[name].fillna(0).astype(str).isin(["0","0.0"]).all():raise ValueError("Unaggregated activity strata")
    use["truck_type"]=use.sourceTypeID.map({52:"SU",53:"SU",61:"CT",62:"CT"})
    group=["truck_type","roadTypeID","monthID","hourID"]
    use["class_diesel_vmt"]=use.groupby(group).activity.transform("sum")
    use["source_vmt_weight"]=use.activity/use.class_diesel_vmt
    cols=keys+["truck_type","fuelTypeID","activity","class_diesel_vmt","source_vmt_weight"]
    weights=use[cols].rename(columns={"activity":"source_diesel_vmt"})
    weights.to_csv(locate("phase1b/provenance/source_type_vmt_weights.csv"),index=False)
    temporal=[]
    for context,periods in CONTEXTS.items():
        for period,hours in periods.items():
            for month,n in WEEKDAYS.items():
                for hour in hours:
                    temporal.append(dict(context=context,period=period,monthID=month,hourID=hour,weekdays=n,month_weight=n/sum(WEEKDAYS.values()),within_period_hour_weight=1/len(hours),temporal_weight=n/sum(WEEKDAYS.values())/len(hours)))
    temporal=pd.DataFrame(temporal);temporal.to_csv(locate("phase1b/provenance/temporal_weighting.csv"),index=False)
    merged=temporal.merge(weights,on=["monthID","hourID"],validate="many_to_many")
    merged["effective_weight"]=merged.temporal_weight*merged.source_vmt_weight
    effective=merged.groupby(["context","period","truck_type","roadTypeID","sourceTypeID"],as_index=False).effective_weight.sum()
    effective.to_csv(locate("phase1b/provenance/source_type_vmt_weights_period_summary.csv"),index=False)
    sums=weights.groupby(group).source_vmt_weight.sum()
    assert np.allclose(sums,1,atol=1e-14)
    save_json(locate("phase1b/provenance/activity_manifest.json"),dict(status="completed",database=DB,moves_run_id=1,raw_sha256=sha(locate("phase1b/provenance/moves_activity_distance_full_day.csv")),diesel_weight_rows=len(weights),weekdays=WEEKDAYS,weekday_total=sum(WEEKDAYS.values()),origin="EPA national-default fleet/activity normalized within a New York County-configured MOVES run; not measured local composition",units="miles; weights are dimensionless within identical month/hour/road/truck-class cells"))
    lines=["# Source-type VMT weighting","",
    "The primary is an EPA-default modeled-composition specification, not observed New York County fleet composition. Phase 1A used national population/VMT normalization and default fleet distributions. A new full-day Inventory-mode activity run cloned those inputs and emitted distance by source, fuel, road, month and hour. It does not calibrate those inputs to local truck counts.","",
    "Only diesel activityTypeID=1 and fuelTypeID=2 distances are used. At each roadTypeID x monthID x hourID, w52=VMT52/(VMT52+VMT53), w53=1-w52, and equivalently w61/w62. All 1,920 source-level cells are complete and positive. This is more granular than road x modeled-period weighting.","",
    "For each hourly cell, blend compatible g/mile rates using these within-cell VMT weights. Then aggregate the hourly blended rates using actual Monday-Friday counts in January-October 2025 and equal hour weights inside each modeled period. Holidays remain weekdays. Equal within-period hour weights preserve the model's 1/3 AM and 2/3 PM activity approximation. The period-summary CSV gives calendar/hour-averaged effective weights for interpretation; it is not a second, fixed-weight blending step.","",
    "The 'window' surface uses hourID 9, 10-16, and 17-18. The full-day denominator uses AM 7-9, midday 10-16, PM 17-19 and night 20-24 plus 1-6. Separate surfaces avoid applying the selected AM/PM hour's weather to unselected hours. Source blending before temporal averaging preserves source-composition/weather covariance.","",
    "Short-haul (52/61) and long-haul (53/62) cases are modeled composition alternatives, not observed bounds on NYC truck shares. MTA SU/MU entry shares are not used. ICE activity is treated as diesel; model EV fractions stay SU=0.02 and CT=0.005.","",
    f"Activity input database: {r.domainDatabaseName}; output: {DB}; version: {r.masterVersion}. The activity run's diagnostic NOx inventory is not used for emission rates. Emission rates remain separately audited rate-mode outputs."]
    (locate("phase1b/provenance/source_type_weight_method.md")).write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(effective[effective.context=="window"].to_string(index=False))
if __name__=="__main__":main()

