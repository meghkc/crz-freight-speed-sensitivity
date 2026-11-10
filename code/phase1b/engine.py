"""Vectorized rate evaluation and paired, exactly preaggregated speed scenarios."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
import json
import numpy as np,pandas as pd
from common import *
PAIR_KEYS=["period","truck_type","roadway_type","speed_mph"]
def mapped_road(name,mapping):
    if mapping=="bridge_tunnel4" and name in ("Bridge","Tunnel"):return 4
    if mapping=="extra_classes4" and name in ("Unknown","Non-Physical","U-Turn"):return 4
    return ROAD[name]
def interpolate(y,speeds):
    speeds=np.asarray(speeds,float)
    clipped=np.clip(speeds,SPEEDS[0],SPEEDS[-1])
    lower=np.clip(np.searchsorted(SPEEDS,clipped,side="right")-1,0,len(SPEEDS)-2)
    fraction=(clipped-SPEEDS[lower])/(SPEEDS[lower+1]-SPEEDS[lower])
    row=np.broadcast_to(np.arange(y.shape[0]),lower.shape)
    return y[row,lower,:]+fraction[...,None]*(y[row,lower+1,:]-y[row,lower,:])
def evaluate(y,speeds,variant):
    shift={"shift_minus5":-5.0,"shift_plus5":5.0}.get(variant,0.0)
    lookup=np.asarray(speeds)+shift
    values=interpolate(y,lookup)
    if variant in ("flat","steep"):
        anchor=interpolate(y,np.full(y.shape[0],25.0))
        factor=.75 if variant=="flat" else 1.25
        values=np.where((np.asarray(speeds)<=25)[...,None],anchor+factor*(values-anchor),values)
    return values,lookup,(lookup<SPEEDS[0])|(lookup>SPEEDS[-1])
class Surface:
    def __init__(self,composition="primary",legacy=False):
        self.legacy=legacy
        if legacy:
            self.curves=json.loads((locate("phase1a/current_curves.json")).read_text())["curves"]
        else:
            name={"primary":"moves5_composite_rates","short_haul":"moves5_short_haul_rates","long_haul":"moves5_long_haul_rates"}[composition]
            table=pd.read_csv(locate(f"phase1b/rates/{name}.csv"))
            self.tables={}
            for key,g in table.groupby(["context","period","truck_type","roadTypeID"]):
                wide=g.pivot(index="speed_mph",columns="pollutant",values="g_per_mile").reindex(index=SPEEDS,columns=POLS)
                if wide.isna().any().any():raise ValueError("Incomplete curve")
                self.tables[key]=wide.to_numpy(float)
    def cube(self,pairs,context,mapping="primary"):
        out=[]
        for row in pairs.itertuples():
            if self.legacy:
                out.append(np.column_stack([np.interp(SPEEDS,self.curves["moves_speed_bins"],self.curves[f"moves_rates_{p.lower()}_{row.truck_type.lower()}"]) for p in POLS]))
            else:out.append(self.tables[(context,row.period,row.truck_type,mapped_road(row.roadway_type,mapping))])
        return np.stack(out)
class Experiment:
    def __init__(self):
        self.cells=pd.read_csv(locate("phase1b/qa/scenario_cells.csv"))
        self.activity=pd.read_csv(locate("phase1b/qa/baseline_activity.csv"))
        self.pairs=self.cells[PAIR_KEYS].drop_duplicates().sort_values(PAIR_KEYS).reset_index(drop=True)
        self.pairs["pair_idx"]=np.arange(len(self.pairs))
        cells=self.cells.merge(self.pairs,on=PAIR_KEYS,validate="many_to_one")
        self.segment=cells.physical_idx.to_numpy(int);self.pair=cells.pair_idx.to_numpy(int)
        self.vmt=cells.analysis_vmt.to_numpy(float)
        self.ice=self.vmt*(1-cells.truck_type.map(EV).to_numpy(float))
        self.speed=self.pairs.speed_mph.to_numpy(float)
        self.legacy_changed=cells[[f"legacy_base_{p}_kg" for p in POLS]].sum().to_numpy(float)
        data=np.load(locate("phase1b/qa/paired_allocations.npz"))
        self.allocations=data["groups"];self.seeds=data["seeds"]
        self.legacy_reps=pd.read_csv(locate("phase1b/qa/legacy_replicates.csv")).sort_values(["slowdown_pct","replicate"])
    def setup(self,composition,variant,mapping,legacy=False,consistent_legacy=False):
        surface=Surface(composition,legacy)
        y=surface.cube(self.pairs,"window",mapping)
        baseline,_,_=evaluate(y,self.speed,variant)
        full_y=surface.cube(self.activity,"full_day",mapping)
        full_rates,full_lookup,full_clipped=evaluate(full_y,self.activity.speed_mph.to_numpy(float),variant)
        icefrac=1-self.activity.truck_type.map(EV).to_numpy(float)
        city=np.sum(full_rates*(self.activity.city_vmt.to_numpy()*icefrac)[:,None]/1000,axis=0)
        crz=np.sum(full_rates*(self.activity.crz_vmt.to_numpy()*icefrac)[:,None]/1000,axis=0)
        if legacy and not consistent_legacy:
            city=np.array([self.activity[f"city_base_{p}_kg"].sum() for p in POLS])
            crz=np.array([self.activity[f"crz_base_{p}_kg"].sum() for p in POLS])
        return dict(y=y,baseline=baseline,city=city,crz=crz,legacy=legacy and not consistent_legacy,variant=variant,baseline_lookup_min=float(full_lookup.min()),baseline_lookup_max=float(full_lookup.max()),baseline_city_clipped_vmt=float(self.activity.loc[full_clipped,"city_vmt"].sum()),baseline_crz_clipped_vmt=float(self.activity.loc[full_clipped,"crz_vmt"].sum()))
    def run_one(self,state,group,fast,slow):
        n=len(self.pairs)
        cellgroup=group[self.segment]
        index=cellgroup*n+self.pair
        activity=np.bincount(index,weights=self.ice,minlength=3*n).reshape(3,n)
        allvmt=np.bincount(index,weights=self.vmt,minlength=3*n).reshape(3,n)
        multipliers=np.array([1+fast/100,1,1-slow/100])
        speed=multipliers[:,None]*self.speed
        values,lookup,clipped=evaluate(state["y"],speed,state["variant"])
        if state["legacy"]:delta=np.sum(activity[...,None]*values/1000,axis=(0,1))-self.legacy_changed
        else:delta=np.sum(activity[...,None]*(values-state["baseline"])/1000,axis=(0,1))
        active=allvmt>0
        result=dict(solved_faster_pct=fast,min_scenario_speed=float(speed[active].min()),max_scenario_speed=float(speed[active].max()),min_lookup_speed=float(lookup[active].min()),max_lookup_speed=float(lookup[active].max()),clipped_vmt=float(allvmt[clipped].sum()),clipped_ice_vmt=float(activity[clipped].sum()),affected_vmt=float(allvmt.sum()),baseline_city_clipped_vmt=state["baseline_city_clipped_vmt"],baseline_crz_clipped_vmt=state["baseline_crz_clipped_vmt"],baseline_lookup_min=state["baseline_lookup_min"],baseline_lookup_max=state["baseline_lookup_max"])
        for i,p in enumerate(POLS):
            result[f"{p}_delta_kg"]=float(delta[i])
            result[f"crz_{p}_change_pct"]=float(100*delta[i]/state["crz"][i])
            result[f"city_{p}_change_pct"]=float(100*delta[i]/state["city"][i])
            result[f"crz_{p}_baseline_kg"]=float(state["crz"][i])
            result[f"city_{p}_baseline_kg"]=float(state["city"][i])
        return result
    def uniform(self,state):
        return self.run_one(state,np.zeros(self.allocations.shape[-1],dtype=np.int8),5.6,0)
    def run_all(self,state,label):
        rows=[]
        for si,slow in enumerate([5.,10.,15.,20.]):
            for rep in range(500):
                fast=float(self.legacy_reps.iloc[si*500+rep].solved_faster_pct)
                row=self.run_one(state,self.allocations[si,rep],fast,slow)
                rows.append(dict(specification=label,slowdown_pct=slow,replicate=rep,seed=int(self.seeds[si,rep]),**row))
        return pd.DataFrame(rows)

