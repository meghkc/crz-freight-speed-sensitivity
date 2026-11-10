"""Reproduce the archived primary experiment before any MOVES scenario evaluation."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import sys, importlib.util, json, hashlib, types
import numpy as np
import pandas as pd
sys.path.insert(0,str(locate("freight_model").parent))
# Avoid freight_model.__init__, which imports unrelated full-model dependencies.
package=types.ModuleType("freight_model"); package.__path__=[str(locate("freight_model"))]
sys.modules["freight_model"]=package
spec=importlib.util.spec_from_file_location("original_fast",locate("freight_model/analyze_aggregation_robustness_fast.py"))
ref=importlib.util.module_from_spec(spec); spec.loader.exec_module(ref)
POLS=["CO2","NOx","PM25"]
def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def main():
    coverage=ref.period_coverage("geotab_8to18")
    links=ref.load_links(locate("data/assignment_link_detail.csv"),"EPSG:2263")
    crz,crzpath=ref.load_crz(data,None,"EPSG:2263")
    edge,physical=ref.build_edge_physical(links,crz)
    emissions=ref.load_emissions(locate("data/emissions_assignment_link_detail.csv"))
    if not set(emissions.edge_uid)<=set(edge.edge_uid):raise ValueError("Unmatched emission links")
    mapping={"Street":5,"Highway":4,"Ramp":4,"Bridge":5,"Tunnel":5,"Unknown":5,"Non-Physical":5,"U-Turn":5}
    unknown=set(emissions.loc[emissions.vmt>0,"roadway_type"])-set(mapping)
    if unknown: raise ValueError("Unresolved road classes: "+str(unknown))
    base=ref.attach_base(emissions,edge,coverage)
    base[base.roadway_type.isin(["Unknown","Non-Physical","U-Turn"])].groupby(["roadway_type","period"],as_index=False).agg(city_vmt=("vmt","sum"),crz_vmt=("crz_vmt","sum"),analysis_vmt=("analysis_vmt","sum")).to_csv(locate("phase1b/provenance/unresolved_road_types.csv"),index=False)
    cells,pairs=ref.build_fast_cells(base)
    exposures=ref.build_segment_exposures(base,physical,coverage)[0]
    arrays=ref.prepare_cell_arrays(cells)
    city=np.array([emissions[f"{p}_kg"].sum() for p in POLS])
    crzbase=np.array([(base[f"{p}_kg"]*base.crz_fraction).sum() for p in POLS])
    uniform=ref.uniform_reference_fast(arrays,pairs,5.6,60.0,city,crzbase)
    reference_uniform=pd.read_csv(locate("data/aggregation_robustness_fast/aggregation_uniform_reference.csv")).iloc[0]
    lengths=physical.crz_length.to_numpy(float)
    seeds=np.random.default_rng(20261002).integers(0,np.iinfo(np.uint32).max,size=(4,500),dtype=np.uint32)
    groups=np.empty((4,500,len(physical)),dtype=np.int8)
    rows=[]
    for si,slow in enumerate([5.,10.,15.,20.]):
        for rep in range(500):
            group,achieved=ref.assign_groups_fast(lengths,ref.normalized_shares(37,46,16),np.random.default_rng(int(seeds[si,rep])))
            groups[si,rep]=group
            fast=ref.solve_faster_pct(exposures,group,5.6,slow)
            result=ref.scenario_emissions_fast(arrays,pairs,group,fast,slow,60.0,city,crzbase)
            rows.append(dict(slowdown_pct=slow,replicate=rep,seed=int(seeds[si,rep]),solved_faster_pct=fast,**result))
        print(f"Legacy slowdown {slow:g}: 500 replicates finished",flush=True)
    actual=pd.DataFrame(rows)
    expected=pd.read_csv(locate("data/aggregation_robustness_fast/aggregation_robustness_replicates.csv"))
    expected=expected[expected.aggregation_mode=="vmt_weighted"].set_index(["slowdown_pct","replicate"]).sort_index()
    indexed=actual.set_index(["slowdown_pct","replicate"]).sort_index()
    if not np.array_equal(indexed.seed,expected.seed):raise ValueError("Child seeds differ")
    comparisons=[]
    for k,v in uniform.items():
        comparisons.append(dict(test="uniform",metric=k,reference=reference_uniform[k],actual=v,abs_error=abs(v-reference_uniform[k]),tolerance=1e-8))
    for k in ["solved_faster_pct"]+[f"{scope}_{p}_change_pct" for scope in ["crz","city"] for p in POLS]:
        error=float(np.max(np.abs(indexed[k]-expected[k])))
        comparisons.append(dict(test="all_2000_replicates",metric=k,reference=np.nan,actual=np.nan,abs_error=error,tolerance=1e-8))
    for slow in [5.,10.,15.,20.]:
        for k in ["solved_faster_pct"]+[f"crz_{p}_change_pct" for p in POLS]:
            a=float(indexed.loc[slow,k].median()); b=float(expected.loc[slow,k].median())
            comparisons.append(dict(test=f"median_slow_{slow:g}",metric=k,reference=b,actual=a,abs_error=abs(a-b),tolerance=1e-8))
    checks=pd.DataFrame(comparisons);checks["passed"]=checks.abs_error<=checks.tolerance
    checks.to_csv(locate("phase1b/qa/legacy_reproduction.csv"),index=False)
    if not checks.passed.all():raise RuntimeError("STOP: legacy reproduction failed")
    np.savez_compressed(locate("phase1b/qa/paired_allocations.npz"),groups=groups,seeds=seeds)
    actual.to_csv(locate("phase1b/qa/legacy_replicates.csv"),index=False)
    pd.DataFrame([uniform]).to_csv(locate("phase1b/qa/legacy_uniform.csv"),index=False)
    physical.to_csv(locate("phase1b/qa/physical_segments.csv"),index=False)
    use=base[(base.analysis_vmt>0)&(base.physical_idx>=0)]
    newcells=use.groupby(["physical_idx","period","truck_type","roadway_type","speed_mph"],as_index=False,sort=False).agg(analysis_vmt=("analysis_vmt","sum"), **{f"legacy_base_{pol}_kg":(f"analysis_base_{pol}_kg","sum") for pol in POLS})
    newcells.to_csv(locate("phase1b/qa/scenario_cells.csv"),index=False)
    for pol in POLS: base[f"crz_base_{pol}_kg"]=base[f"{pol}_kg"]*base.crz_fraction
    activity=base.groupby(["period","truck_type","roadway_type","speed_mph"],as_index=False).agg(city_vmt=("vmt","sum"),crz_vmt=("crz_vmt","sum"),analysis_vmt=("analysis_vmt","sum"), **{f"city_base_{pol}_kg":(f"{pol}_kg","sum") for pol in POLS}, **{f"crz_base_{pol}_kg":(f"crz_base_{pol}_kg","sum") for pol in POLS})
    activity.to_csv(locate("phase1b/qa/baseline_activity.csv"),index=False)
    ev={t:ref.ev_fraction(t) for t in ["SU","CT"]}
    share=float(base.loc[base.roadway_type.isin(["Bridge","Tunnel"]),"analysis_vmt"].sum()/base.analysis_vmt.sum())
    speed_unique=base[base.physical_idx>=0].groupby(["physical_idx","period"]).speed_mph.nunique()
    true_exposure=np.bincount(use.physical_idx.to_numpy(int),weights=(use.analysis_vmt*use.speed_mph).to_numpy(float),minlength=len(physical))
    relative_error=float(np.max(np.abs(exposures-true_exposure))/max(1,float(true_exposure.max())))
    if relative_error>1e-10:raise RuntimeError("STOP: archived speed constraint differs from actual VMT-weighted constraint")
    closure=pd.DataFrame([
        dict(quantity="raw_assignment_VMT",value=float(links.vmt.sum()),reference=609873.7714383239),
        dict(quantity="emissions_detail_VMT",value=float(base.vmt.sum()),reference=609852.75),
        dict(quantity="CRZ_VMT",value=float(base.crz_vmt.sum()),reference=53978.77084511842),
        dict(quantity="analysis_window_CRZ_VMT",value=float(newcells.analysis_vmt.sum()),reference=30285.969118816167),
        dict(quantity="preaggregation_closure",value=float(newcells.analysis_vmt.sum()),reference=float(base.analysis_vmt.sum()))])
    closure["difference"]=closure.value-closure.reference
    closure.to_csv(locate("phase1b/qa/vmt_closure.csv"),index=False)
    pd.DataFrame([dict(roadway_type=k,primary_roadTypeID=v,bridge_tunnel_sensitivity_roadTypeID=4 if k in ["Bridge","Tunnel"] else v,extra_class_sensitivity_roadTypeID=4 if k in ["Unknown","Non-Physical","U-Turn"] else v,basis="User-specified fallback; assignment has no explicit access-control flag") for k,v in mapping.items()]).to_csv(locate("phase1b/provenance/road_type_mapping.csv"),index=False)
    metadata=dict(status="passed",master_seed=20261002,replicates_per_slowdown=500,ev_fractions=ev,raw_rows=len(base),scenario_cells=len(newcells),legacy_cells=len(cells),physical_segments=len(physical),bridge_tunnel_analysis_vmt_share=share,legacy_max_abs_error=float(checks.abs_error.max()),speed_constraint_relative_error=relative_error,physical_periods_with_multiple_speeds=int((speed_unique>1).sum()),coverage=coverage,legacy_denominator="full-day CRZ and city emissions, while changes affect only selected daytime activity")
    (locate("phase1b/qa/legacy_qa_metadata.json")).write_text(json.dumps(metadata,indent=2))
    files=[locate("freight_model/config.py"),locate("freight_model/emissions.py"),locate("freight_model/analyze_aggregation_robustness_fast.py"),locate("data/assignment_link_detail.csv"),locate("data/emissions_assignment_link_detail.csv")]+list(crzpath.parent.glob("NYC_CRZ.*"))
    (locate("phase1b/provenance/original_inputs_sha256.json")).write_text(json.dumps({str(p):digest(p) for p in files},indent=2))
    print(json.dumps(metadata,indent=2))
if __name__=="__main__":main()

