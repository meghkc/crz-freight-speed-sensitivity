"""Evaluate only the authorized Phase 1B scenarios after the legacy gate passes."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
import json
import numpy as np,pandas as pd
from common import *
from engine import Experiment,Surface,interpolate,evaluate
SPECS=[
 ("primary","primary","base","primary"),
 ("short_haul","short_haul","base","primary"),
 ("long_haul","long_haul","base","primary"),
 ("flat_low_speed","primary","flat","primary"),
 ("steep_low_speed","primary","steep","primary"),
 ("shift_minus5","primary","shift_minus5","primary"),
 ("shift_plus5","primary","shift_plus5","primary"),
 ("bridge_tunnel_road4","primary","base","bridge_tunnel4"),
 ("extra_classes_road4","primary","base","extra_classes4")]
def self_test():
    rows=[]
    for composition in ["primary","short_haul","long_haul"]:
        surface=Surface(composition)
        for key,y in surface.tables.items():
            for speed_idx,speed in enumerate(SPEEDS):
                actual=interpolate(y[None,:,:],np.array([speed]))[0]
                for pi,pol in enumerate(POLS):
                    expected=y[speed_idx,pi]
                    error=abs(actual[pi]-expected);tolerance=max(1e-12,abs(expected)*1e-12)
                    rows.append(dict(composition=composition,context=key[0],period=key[1],truck_type=key[2],roadTypeID=key[3],pollutant=pol,speed_mph=speed,expected_rate=expected,interpolated_rate=actual[pi],absolute_error=error,tolerance=tolerance,passed=error<=tolerance))
    result=pd.DataFrame(rows);result.to_csv(locate("phase1b/qa/interpolation_self_test.csv"),index=False)
    if not result.passed.all():raise ValueError("Interpolation self-test failed")
def summarize(frame,uniform,label):
    rows=[]
    for slowdown,group in frame.groupby("slowdown_pct"):
        for p in POLS:
            u=uniform[f"crz_{p}_change_pct"]
            record=dict(specification=label,slowdown_pct=slowdown,pollutant=p,n_replicates=len(group),
                uniform_crz_change_pct=u,uniform_city_change_pct=uniform[f"city_{p}_change_pct"],
                uniform_delta_kg=uniform[f"{p}_delta_kg"],crz_baseline_kg=uniform[f"crz_{p}_baseline_kg"],city_baseline_kg=uniform[f"city_{p}_baseline_kg"])
            for name,column in [("crz_change_pct",f"crz_{p}_change_pct"),("city_change_pct",f"city_{p}_change_pct"),("delta_kg",f"{p}_delta_kg"),("solved_faster_pct","solved_faster_pct")]:
                for q,suffix in [(.05,"p05"),(.5,"p50"),(.95,"p95")]:record[f"{name}_{suffix}"]=float(group[column].quantile(q))
            record["attenuation_pp"]=record["crz_change_pct_p50"]-u
            for suffix in ["p05","p50","p95"]:
                record[f"benefit_attenuation_pct_{suffix}"]=100*(1-record[f"crz_change_pct_{suffix}"]/u) if u<0 else np.nan
            record["uniform_has_benefit"]=u<0
            record["min_scenario_speed"]=group.min_scenario_speed.min()
            record["max_scenario_speed"]=group.max_scenario_speed.max()
            record["max_clipped_vmt"]=group.clipped_vmt.max()
            rows.append(record)
    return pd.DataFrame(rows)
def main():
    gate=json.loads((locate("phase1b/qa/framework_gate.json")).read_text())
    if gate["status"]!="passed" or gate["paired_allocation_sha256"]!=sha(locate("phase1b/qa/paired_allocations.npz")):raise ValueError("Legacy/paired-allocation gate failed")
    self_test()
    exp=Experiment();summaries=[];uniforms=[];bounds=[];reps=[]
    for label,composition,variant,mapping in SPECS:
        state=exp.setup(composition,variant,mapping)
        zero=exp.run_one(state,np.zeros(exp.allocations.shape[-1],dtype=np.int8),0,0)
        if max(abs(zero[f"{p}_delta_kg"]) for p in POLS)>1e-10:raise ValueError("Zero-speed-change emissions are not zero")
        uniform=exp.uniform(state)
        frame=exp.run_all(state,label)
        if not np.allclose(frame.affected_vmt,exp.vmt.sum(),rtol=0,atol=1e-7):raise ValueError("Scenario VMT does not close")
        summaries.append(summarize(frame,uniform,label))
        reps.append(frame)
        columns=["specification","slowdown_pct","replicate","seed","solved_faster_pct","min_scenario_speed","max_scenario_speed","min_lookup_speed","max_lookup_speed","clipped_vmt","clipped_ice_vmt","affected_vmt","baseline_city_clipped_vmt","baseline_crz_clipped_vmt","baseline_lookup_min","baseline_lookup_max"]
        bounds.append(frame[columns])
        for p in POLS:
            uniforms.append(dict(specification=label,pollutant=p,crz_change_pct=uniform[f"crz_{p}_change_pct"],city_change_pct=uniform[f"city_{p}_change_pct"],delta_kg=uniform[f"{p}_delta_kg"],crz_baseline_kg=uniform[f"crz_{p}_baseline_kg"],city_baseline_kg=uniform[f"city_{p}_baseline_kg"],min_scenario_speed=uniform["min_scenario_speed"],max_scenario_speed=uniform["max_scenario_speed"],clipped_vmt=uniform["clipped_vmt"]))
        print(f"{label}: 2000 paired replicates finished",flush=True)
    allsummary=pd.concat(summaries,ignore_index=True)
    alluniform=pd.DataFrame(uniforms)
    allreps=pd.concat(reps,ignore_index=True)
    allsummary.to_csv(locate("phase1b/results/all_specification_summaries.csv"),index=False)
    alluniform.to_csv(locate("phase1b/results/all_uniform_benchmarks.csv"),index=False)
    allreps.to_csv(locate("phase1b/results/all_specification_replicates.csv"),index=False)
    allsummary[allsummary.specification=="primary"].to_csv(locate("phase1b/results/moves_heterogeneous_summary.csv"),index=False)
    alluniform[alluniform.specification=="primary"].to_csv(locate("phase1b/results/moves_uniform_benchmark.csv"),index=False)
    allreps[allreps.specification=="primary"].to_csv(locate("phase1b/results/moves_heterogeneous_replicates.csv"),index=False)
    allsummary[allsummary.specification.isin(["primary","short_haul","long_haul"])].to_csv(locate("phase1b/results/source_type_composition_sensitivity.csv"),index=False)
    allsummary[allsummary.specification.isin(["primary","flat_low_speed","steep_low_speed","shift_minus5","shift_plus5"])].to_csv(locate("phase1b/results/curve_shape_sensitivity.csv"),index=False)
    primary=allsummary[allsummary.specification=="primary"][["slowdown_pct","pollutant","crz_change_pct_p50","city_change_pct_p50"]]
    for label,filename in [("bridge_tunnel_road4","bridge_tunnel_roadtype_sensitivity"),("extra_classes_road4","additional_roadtype_sensitivity")]:
        comparison=allsummary[allsummary.specification==label].merge(primary,on=["slowdown_pct","pollutant"],suffixes=("","_primary"),validate="one_to_one")
        comparison["mapping_effect_crz_pp"]=comparison.crz_change_pct_p50-comparison.crz_change_pct_p50_primary
        comparison["mapping_effect_city_pp"]=comparison.city_change_pct_p50-comparison.city_change_pct_p50_primary
        comparison.to_csv(locate(f"phase1b/results/{filename}.csv"),index=False)
    speed=pd.concat(bounds,ignore_index=True);speed.to_csv(locate("phase1b/qa/scenario_speed_bounds.csv"),index=False)
    speed.groupby(["specification","slowdown_pct"],as_index=False).agg(min_scenario_speed=("min_scenario_speed","min"),max_scenario_speed=("max_scenario_speed","max"),min_lookup_speed=("min_lookup_speed","min"),max_lookup_speed=("max_lookup_speed","max"),max_clipped_vmt=("clipped_vmt","max"),median_clipped_vmt=("clipped_vmt","median")).to_csv(locate("phase1b/qa/scenario_speed_bounds_summary.csv"),index=False)
    old_u=pd.read_csv(locate("phase1b/qa/legacy_uniform.csv")).iloc[0]
    old=exp.legacy_reps
    current=[]
    consistent_state=exp.setup("primary","base","primary",legacy=True,consistent_legacy=True)
    consistent=exp.run_all(consistent_state,"current_consistent_baseline")
    consistent_u=exp.uniform(consistent_state)
    consistent.to_csv(locate("phase1b/qa/current_consistent_baseline_replicates.csv"),index=False)
    for row in alluniform[alluniform.specification=="primary"].itertuples():
        p=row.pollutant;oldvalue=float(old_u[f"crz_{p}_change_pct"])
        current.append(dict(scenario="uniform",slowdown_pct=0,pollutant=p,current_crz_change_pct=oldvalue,current_consistent_crz_change_pct=consistent_u[f"crz_{p}_change_pct"],moves_crz_change_pct=row.crz_change_pct,change_vs_paper_pp=row.crz_change_pct-oldvalue,change_vs_consistent_current_pp=row.crz_change_pct-consistent_u[f"crz_{p}_change_pct"]))
    for row in allsummary[allsummary.specification=="primary"].itertuples():
        p=row.pollutant;oldvalue=float(old[old.slowdown_pct==row.slowdown_pct][f"crz_{p}_change_pct"].median())
        consistent_value=float(consistent[consistent.slowdown_pct==row.slowdown_pct][f"crz_{p}_change_pct"].median())
        current.append(dict(scenario="heterogeneous",slowdown_pct=row.slowdown_pct,pollutant=p,current_crz_change_pct=oldvalue,current_consistent_crz_change_pct=consistent_value,moves_crz_change_pct=row.crz_change_pct_p50,change_vs_paper_pp=row.crz_change_pct_p50-oldvalue,change_vs_consistent_current_pp=row.crz_change_pct_p50-consistent_value))
    pd.DataFrame(current).to_csv(locate("phase1b/results/current_vs_moves_results.csv"),index=False)
    save_json(locate("phase1b/qa/scenario_run_manifest.json"),dict(status="completed",specifications=len(SPECS),heterogeneous_rows=len(allreps),replicates_per_slowdown=500,master_seed=20261002,allocation_sha256=sha(locate("phase1b/qa/paired_allocations.npz")),seed_identity_verified=True,zero_change_tests_passed=True,vmt_closure_passed=True,denominators="full-day baseline under each rate/composition specification; identical kg change numerator for CRZ and city",extrapolation_used=False,legacy_rounding="Legacy QA uses stored baseline emissions exactly. MOVES baselines are recomputed from the same VMT and new rates; a consistent-current baseline control isolates the small saved-VMT rounding discrepancy."))
if __name__=="__main__":main()

