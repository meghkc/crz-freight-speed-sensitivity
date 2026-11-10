"""Construct calendar-weighted period curves without median pooling."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
import json
import numpy as np,pandas as pd
from common import *
def main():
    manifest=json.loads((locate("phase1b/provenance/full_day_rate_manifest.json")).read_text())
    if manifest["status"]!="completed" or manifest["raw_sha256"]!=sha(locate("phase1b/rates/moves5_full_day_raw.csv")):raise ValueError("Unverified full-day export")
    if manifest["phase1a_raw_sha256"]!=sha(locate("phase1a/results/moves5_rateperdistance_nyc_2025.csv")):raise ValueError("Phase 1A export changed")
    weights=pd.read_csv(locate("phase1b/provenance/source_type_vmt_weights.csv"))
    temporal=pd.read_csv(locate("phase1b/provenance/temporal_weighting.csv"))
    frames=[];source_frames=[]
    for context,path in [("window",locate("phase1a/results/moves5_rateperdistance_nyc_2025.csv")),("full_day",locate("phase1b/rates/moves5_full_day_raw.csv"))]:
        raw=pd.read_csv(path)
        joined=raw.merge(weights[["sourceTypeID","roadTypeID","monthID","hourID","source_vmt_weight","truck_type"]],on=["sourceTypeID","roadTypeID","monthID","hourID"],validate="many_to_one")
        if len(joined)!=len(raw) or joined.source_vmt_weight.isna().any():raise ValueError("Missing activity weights")
        tw=temporal[temporal.context==context]
        x=joined.merge(tw[["period","monthID","hourID","temporal_weight"]],on=["monthID","hourID"],validate="many_to_one")
        x["pollutant"]=x.pollutantID.map(POLLUTANT_IDS)
        x["speed_mph"]=x.avgSpeedBinID.map(dict(enumerate(SPEEDS,1)))
        x["weighted_rate"]=x.ratePerDistance*x.temporal_weight
        key=["period","roadTypeID","truck_type","pollutant","speed_mph"]
        src=x.groupby(key+["sourceTypeID"],as_index=False).weighted_rate.sum().rename(columns={"weighted_rate":"g_per_mile"})
        src["context"]=context;source_frames.append(src)
        for composition,sources in [("primary",None),("short_haul",[52,61]),("long_haul",[53,62])]:
            z=x.copy() if sources is None else x[x.sourceTypeID.isin(sources)].copy()
            z["contribution"]=z.weighted_rate*(z.source_vmt_weight if sources is None else 1)
            out=z.groupby(key,as_index=False).contribution.sum().rename(columns={"contribution":"g_per_mile"})
            out["context"]=context;out["composition"]=composition;frames.append(out)
    surface=pd.concat(frames,ignore_index=True)
    if len(surface)!=4032 or surface.g_per_mile.isna().any() or not np.isfinite(surface.g_per_mile).all():raise ValueError("Incomplete rate surface")
    for comp,name in [("primary","moves5_composite_rates"),("short_haul","moves5_short_haul_rates"),("long_haul","moves5_long_haul_rates")]:
        surface[surface.composition==comp].to_csv(locate(f"phase1b/rates/{name}.csv"),index=False)
    pd.concat(source_frames,ignore_index=True).to_csv(locate("phase1b/rates/source_type_rate_comparison.csv"),index=False)
    primary=surface[surface.composition=="primary"]
    anchor=primary[primary.speed_mph==25].drop(columns=["speed_mph"]).rename(columns={"g_per_mile":"anchor"})
    for factor,name in [(0.75,"flat_low_speed"),(1.25,"steep_low_speed")]:
        z=primary.merge(anchor,on=["context","composition","period","roadTypeID","truck_type","pollutant"],validate="many_to_one")
        z["g_per_mile"]=np.where(z.speed_mph<=25,z.anchor+factor*(z.g_per_mile-z.anchor),z.g_per_mile)
        z.drop(columns="anchor").to_csv(locate(f"phase1b/rates/moves5_composite_rates_{name}.csv"),index=False)
    save_json(locate("phase1b/provenance/rate_surface_manifest.json"),dict(status="completed",units="g/mile",rows=len(surface),temporal_weighting_sha256=sha(locate("phase1b/provenance/temporal_weighting.csv")),source_weight_sha256=sha(locate("phase1b/provenance/source_type_vmt_weights.csv")),phase1a_window_source_sha256=sha(locate("phase1a/results/moves5_rateperdistance_nyc_2025.csv")),full_day_source_sha256=manifest["raw_sha256"],window_source="unchanged Phase 1A full run, 08:00-18:00",full_day_source="matched supplemental full-day run; daytime overlap audited",method="blend diesel source types within each month/hour/road cell, then weekday-calendar/equal-hour aggregation"))
    print("Built 4032 composition/context/period/road/pollutant/speed rates.")
if __name__=="__main__":main()

