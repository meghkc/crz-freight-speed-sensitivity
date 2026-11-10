"""Repair Phase 2 exports from frozen Phase 1B allocations; no random draws or MOVES runs."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import sys, json, itertools, shutil, platform, traceback
import numpy as np
import pandas as pd
sys.path.insert(0,str(locate('phase1b/code')))
import pyarrow as pa
import pyarrow.parquet as pq
from common import EV,POLS,SPEEDS,sha
from engine import Experiment,interpolate,mapped_road
RESULTS=locate('phase2r/results')
SLOWS=[5.,10.,15.,20.]
ROADS=['Street','Highway','Bridge','Tunnel','Ramp','Other/fallback']
PERIODS=['AM','midday','PM']; PERIOD_MAP={'am_peak':'AM','midday':'midday','pm_peak':'PM'}
RESP=['faster','unchanged','slower']
BINS=['<10','10-15','15-20','20-30','30-40','40-50','50-55','55-60','>60']
EDGES=np.array([10,15,20,30,40,50,55,60])
COMBINED=['high_speed_gt50','low_speed_lt20','very_low_lt10','speed_10_15','speed_15_20','moderate_20_40','highway_family','street','other']
KEYS=['slowdown_pct','replicate_id','pollutant']
CHECKS=[]

def check(name,passed,detail):
    CHECKS.append(dict(test=name,passed=bool(passed),detail=str(detail)))
    if not passed: raise RuntimeError(name+': '+str(detail))

def freeze():
    files={str(f):sha(f) for ph in ['phase1b','phase2'] for f in phase_files(ph)}
    path=locate('phase2r/provenance/source_sha256.json')
    if path.exists():
        check('Pre-existing source snapshot unchanged',files==json.loads(path.read_text()),len(files))
    else:path.write_text(json.dumps(files,indent=2))
    return files

def summary(df,keys,filename,metrics=None):
    if metrics is None:
        metrics=[c for c in df.select_dtypes(include='number').columns if c not in keys+['replicate_id']]
    gb=df.groupby(keys,sort=False,dropna=False)
    out=gb.size().rename('n_replicates').to_frame()
    check(filename+' replicate counts',out.n_replicates.eq(500).all(),out.n_replicates.unique())
    for q,suffix in [(.05,'p05'),(.5,'p50'),(.95,'p95')]:
        z=gb[metrics].quantile(q).rename(columns=lambda x:x+'_'+suffix)
        out=out.join(z)
    for c in [x for x in df.columns if x.endswith('_flag')]:
        out=out.join(gb[c].sum().rename(c+'_n'))
    out=out.reset_index();out.to_csv(RESULTS/filename,index=False)
    return out

def metrics(vmt,gap,delta,codes,n):
    return [np.bincount(codes,weights=z,minlength=n) for z in [vmt,gap,np.abs(gap),delta]]

def records(base,names,m,total,totalabs):
    v,g,a,d=m
    near=abs(total)<=max(1e-12,1e-12*totalabs)
    anear=totalabs<=1e-12
    out=[]
    for i,name in enumerate(names):
        labels=name if isinstance(name,dict) else {'category':name}
        out.append(dict(**base,**labels,analysis_vmt=float(v[i]),signed_gap_kg=float(g[i]),category_net_abs_gap_kg=float(abs(g[i])),cell_abs_gap_kg=float(a[i]),hetero_delta_kg=float(d[i]),signed_share_of_net_gap=float(g[i]/total) if not near else np.nan,absolute_share=float(a[i]/totalabs) if not anear else np.nan,near_zero_net_flag=near,near_zero_absolute_flag=anear))
    return out

def main():
    for sub in ['raw','results','qa','provenance']: locate(f'phase2r/{sub}').mkdir(parents=True,exist_ok=True)
    frozen=freeze()
    manifest=json.loads((locate('phase1b/qa/scenario_run_manifest.json')).read_text())
    check('Frozen allocation digest',sha(locate('phase1b/qa/paired_allocations.npz'))==manifest['allocation_sha256'],manifest['allocation_sha256'])
    check('Frozen master seed',manifest['master_seed']==20261002,manifest['master_seed'])
    exp=Experiment();state=exp.setup('primary','base','primary')
    saved=pd.read_csv(locate('phase1b/results/moves_heterogeneous_replicates.csv')).sort_values(['slowdown_pct','replicate']).reset_index(drop=True)
    check('Saved counts',saved.groupby('slowdown_pct').size().eq(500).all() and len(saved)==2000 and not saved.duplicated(['slowdown_pct','replicate']).any(),saved.groupby('slowdown_pct').size().to_dict())
    check('Saved seed identity',np.array_equal(saved.seed.to_numpy().reshape(4,500),exp.seeds),exp.seeds.shape)
    check('Saved slowdown levels',saved.slowdown_pct.unique().tolist()==SLOWS,saved.slowdown_pct.unique())
    reproduced=exp.run_all(state,'primary').sort_values(['slowdown_pct','replicate']).reset_index(drop=True)
    columns=['solved_faster_pct']+[f'{scope}_{p}_change_pct' for scope in ['crz','city'] for p in POLS]+[f'{p}_delta_kg' for p in POLS]
    errors={c:float(abs(saved[c]-reproduced[c]).max()) for c in columns}
    check('A Phase 1B all-replicate reproduction',max(errors.values())<=1e-10,errors)
    uniform=exp.uniform(state);su=pd.read_csv(locate('phase1b/results/moves_uniform_benchmark.csv')).set_index('pollutant')
    ue=max(abs(uniform[f'{p}_delta_kg']-su.loc[p,'delta_kg']) for p in POLS)
    check('Phase 1B uniform reproduction',ue<=1e-10,ue)
    (locate('phase2r/qa/reproduction.json')).write_text(json.dumps(errors,indent=2))
    print('Primary reproduction passed before derived exports.',flush=True)
    source_long=pd.concat([saved[['slowdown_pct','replicate',f'crz_{p}_change_pct',f'{p}_delta_kg']].rename(columns={'replicate':'replicate_id',f'crz_{p}_change_pct':'primary_crz_change_pct',f'{p}_delta_kg':'primary_delta_kg'}).assign(pollutant=p) for p in POLS],ignore_index=True)
    cells=exp.cells.merge(exp.pairs,on=['period','truck_type','roadway_type','speed_mph'],validate='many_to_one')
    vmt=cells.analysis_vmt.to_numpy(float); v=cells.speed_mph.to_numpy(float)
    ice=vmt*(1-cells.truck_type.map(EV).to_numpy(float))
    road=cells.roadway_type.where(cells.roadway_type.isin(ROADS),'Other/fallback').to_numpy()
    period=cells.period.map(PERIOD_MAP).to_numpy();truck=cells.truck_type.to_numpy()
    segment=cells.physical_idx.to_numpy(int)
    roadcode=pd.Categorical(road,categories=ROADS).codes.astype(int)
    percode=pd.Categorical(period,categories=PERIODS).codes.astype(int)
    bcode=np.searchsorted(EDGES,v,side='right')
    y=state['y'][cells.pair_idx.to_numpy(int)]
    br=state['baseline'][cells.pair_idx.to_numpy(int)]
    ur=interpolate(y,v*1.056)
    bem=ice[:,None]*br/1000;uem=ice[:,None]*ur/1000
    uniformflat=np.sum(ice[:,None]*(interpolate(y,np.minimum(v*1.056,50))-br)/1000,axis=0)
    check('Same uniform benchmark for flat test',np.max(abs(uniformflat-np.array([uniform[f'{p}_delta_kg'] for p in POLS])))<1e-10,uniformflat)
    check('Baseline <=50 mph for hard-cap audit',v.max()<=50,v.max())
    jkeys=['roadway_class','modeled_period','truck_class','baseline_speed']
    jcell=pd.DataFrame(dict(roadway_class=road,modeled_period=period,truck_class=truck,baseline_speed=v))
    jindex=pd.MultiIndex.from_frame(jcell).unique()
    jcode=jindex.get_indexer(pd.MultiIndex.from_frame(jcell))
    jnames=[dict(zip(jkeys,x)) for x in jindex]
    rpnames=[dict(roadway_class=r,modeled_period=t) for r,t in itertools.product(ROADS,PERIODS)]
    rprnames=[dict(roadway_class=r,modeled_period=t,response_group=g) for r,t,g in itertools.product(ROADS,PERIODS,RESP)]
    catrows=[];combinedrows=[];rprows=[];rprrows=[];jrows=[];totalrows=[];flatrows=[];caprows=[];resprows=[]
    closure_max={}; closure_tol={}
    def close(name,actual,expected):
        error=float(abs(actual-expected));tol=max(1e-10,256*np.finfo(float).eps*max(abs(expected),1.0))
        closure_max[name]=max(closure_max.get(name,0),error);closure_tol[name]=max(closure_tol.get(name,0),tol)
        if error>tol:check(name,False,dict(error=error,tolerance=tol))
    rawpath=locate('phase2r/raw/attenuation_gap_cell_level.parquet')
    writer=None
    try:
        for si,slow in enumerate(SLOWS):
            for rep in range(500):
                group=exp.allocations[si,rep][segment]
                fast=float(saved.iloc[si*500+rep].solved_faster_pct)
                speed=v*np.choose(group,[1+fast/100,1,1-slow/100])
                scode=np.searchsorted(EDGES,speed,side='right')
                hr=interpolate(y,speed);hem=ice[:,None]*hr/1000
                delta=hem-bem;gap=hem-uem
                flatdelta=np.sum(ice[:,None]*(interpolate(y,np.minimum(speed,50))-br)/1000,axis=0)
                fm=group==0;sm=group==2;um=group==1
                target=np.dot(vmt,v)*1.056
                fixed=np.dot(vmt[sm],v[sm]*(1-slow/100))+np.dot(vmt[um],v[um])
                max_speed_sum=fixed+50*vmt[fm].sum()
                feasible=bool(fm.any() and target<=max_speed_sum+1e-8)
                if feasible:
                    lo=0.;hi=max(2.,float(np.max(50/v[fm]-1)))
                    for _ in range(70):
                        mid=(lo+hi)/2
                        if fixed+np.dot(vmt[fm],np.minimum(v[fm]*(1+mid),50))<target:lo=mid
                        else:hi=mid
                    capv=v.copy();capv[fm]=np.minimum(v[fm]*(1+hi),50);capv[sm]*=1-slow/100
                    achieved=100*(np.dot(vmt,capv)/np.dot(vmt,v)-1)
                    capdelta=np.sum(ice[:,None]*(interpolate(y,capv)-br)/1000,axis=0)
                    close('I hard-cap mean-speed constraint',achieved,5.6)
                    close('Hard-cap maximum speed',max(0,float(capv.max()-50)),0)
                else:hi=achieved=np.nan;capdelta=np.full(3,np.nan)
                masks=[speed>50,speed<20,speed<10,(speed>=10)&(speed<15),(speed>=15)&(speed<20),(speed>=20)&(speed<40),np.isin(road,['Highway','Bridge','Ramp','Tunnel']),road=='Street',road=='Other/fallback']
                for pi,p in enumerate(POLS):
                    base=dict(slowdown_pct=slow,replicate_id=rep,pollutant=p)
                    g=gap[:,pi];d=delta[:,pi];tot=float(g.sum());ab=float(abs(g).sum())
                    ref=saved.iloc[si*500+rep]
                    close('Cell reconstruction saved heterogeneous delta',d.sum(),ref[f'{p}_delta_kg'])
                    close('Cell reconstruction saved attenuation gap',tot,ref[f'{p}_delta_kg']-uniform[f'{p}_delta_kg'])
                    totalrows.append(dict(**base,analysis_vmt=vmt.sum(),signed_gap_kg=tot,cell_abs_gap_kg=ab,hetero_delta_kg=d.sum(),uniform_delta_kg=uniform[f'{p}_delta_kg'],uniform_crz_change_pct=uniform[f'crz_{p}_change_pct'],near_zero_net_flag=abs(tot)<=max(1e-12,1e-12*ab)))
                    for dimension,names,codes in [('scenario_speed_bin',BINS,scode),('baseline_speed_bin',BINS,bcode),('roadway_class',ROADS,roadcode),('response_group',RESP,group),('modeled_period',PERIODS,percode)]:
                        m=metrics(vmt,g,d,codes,len(names))
                        close(dimension+' signed closure',m[1].sum(),tot)
                        close(dimension+' cell-absolute closure',m[2].sum(),ab)
                        close(dimension+' VMT closure',m[0].sum(),vmt.sum())
                        close(dimension+' response-delta closure',m[3].sum(),d.sum())
                        catrows.extend(records(dict(**base,decomposition_dimension=dimension),names,m,tot,ab))
                    m=np.array([[vmt[mask].sum(),g[mask].sum(),abs(g[mask]).sum(),d[mask].sum()] for mask in masks]).T
                    combinedrows.extend(records(base,COMBINED,m,tot,ab))
                    for targetrows,names,codes in [(rprows,rpnames,roadcode*3+percode),(rprrows,rprnames,(roadcode*3+percode)*3+group),(jrows,jnames,jcode)]:
                        m=metrics(vmt,g,d,codes,len(names))
                        close('Joint attribution signed closure',m[1].sum(),tot)
                        close('Joint attribution cell-absolute closure',m[2].sum(),ab)
                        targetrows.extend(records(base,names,m,tot,ab))
                    gd=np.bincount(group,weights=d,minlength=3)
                    ok=bool(gd[0]<0 and gd[2]>0)
                    resprows.append(dict(**base,faster_group_delta_kg=gd[0],unchanged_group_delta_kg=gd[1],slower_group_delta_kg=gd[2],net_delta_kg=d.sum(),offset_ratio=gd[2]/abs(gd[0]) if ok else np.nan,invalid_offset_flag=not ok))
                    flatrows.append(dict(**base,rate_flat_crz_change_pct=100*flatdelta[pi]/state['crz'][pi]))
                    caprows.append(dict(**base,feasible=feasible,solved_faster_pct=100*hi,achieved_mean_speed_change_pct=achieved,hardcap_crz_change_pct=100*capdelta[pi]/state['crz'][pi],infeasible_reason='' if feasible else 'Maximum attainable capped speed sum below target, or no faster roads'))
                # One row per frozen preaggregated physical/period/truck/speed cell and pollutant.
                n=len(cells)
                frame=pd.DataFrame(dict(slowdown_pct=np.full(n*3,slow),replicate_id=np.full(n*3,rep,dtype=np.int32),pollutant=np.tile(POLS,n),physical_segment_id=np.repeat(segment,3),roadway_class=np.repeat(road,3),modeled_period=np.repeat(period,3),truck_class=np.repeat(truck,3),response_group=np.repeat(np.array(RESP)[group],3),baseline_speed=np.repeat(v,3),scenario_speed=np.repeat(speed,3),baseline_speed_bin=np.repeat(np.array(BINS)[bcode],3),scenario_speed_bin=np.repeat(np.array(BINS)[scode],3),analysis_vmt=np.repeat(vmt,3),baseline_emission_kg=bem.ravel(),uniform_emission_kg=uem.ravel(),heterogeneous_emission_kg=hem.ravel(),hetero_delta_kg=delta.ravel(),uniform_delta_kg=(uem-bem).ravel(),attenuation_gap_cell_kg=gap.ravel()))
                table=pa.Table.from_pandas(frame,preserve_index=False)
                if writer is None:writer=pq.ParquetWriter(rawpath,table.schema,compression='zstd',use_dictionary=True)
                writer.write_table(table)
                if (rep+1)%100==0:print(f'Slowdown {slow:g}: {rep+1}/500 exported',flush=True)
    finally:
        if writer is not None:writer.close()
    for name,error in closure_max.items():check(name,True,dict(max_abs_error=error,max_allowed_tolerance=closure_tol[name]))
    rawrows=pq.ParquetFile(rawpath).metadata.num_rows
    check('Raw master row count',rawrows==len(cells)*3*2000,rawrows)
    # Explicit keyed joins ensure counterfactual references come only from saved primary results.
    totals=pd.DataFrame(totalrows).merge(source_long,on=KEYS,validate='one_to_one')
    totals['attenuation_pct']=100*(1-totals.primary_crz_change_pct/totals.uniform_crz_change_pct)
    totals.to_csv(locate('phase2r/results/replicate_totals.csv'),index=False)
    primary_summary=summary(totals,['slowdown_pct','pollutant'],'primary_repaired_summary.csv')
    cat=pd.DataFrame(catrows);cat.to_csv(locate('phase2r/results/attenuation_gap_category_replicates.csv'),index=False)
    summary(cat,['slowdown_pct','pollutant','decomposition_dimension','category'],'attenuation_gap_category_summary.csv')
    comb=pd.DataFrame(combinedrows);comb.to_csv(locate('phase2r/results/attenuation_gap_combined_replicates.csv'),index=False)
    summary(comb,['slowdown_pct','pollutant','category'],'attenuation_gap_combined_summary.csv')
    for rows,keys,stem in [(rprows,['roadway_class','modeled_period'],'roadway_period_attenuation'),(rprrows,['roadway_class','modeled_period','response_group'],'roadway_period_response_attenuation'),(jrows,jkeys,'roadway_period_truck_attenuation')]:
        df=pd.DataFrame(rows);df.to_csv(RESULTS/(stem+'_replicates.csv'),index=False)
        summary(df,['slowdown_pct','pollutant']+keys,stem+'_summary.csv')
    flat=pd.DataFrame(flatrows).merge(source_long,on=KEYS,validate='one_to_one')
    flat['rate_flat_minus_primary_pp']=flat.rate_flat_crz_change_pct-flat.primary_crz_change_pct
    flat['uniform_crz_change_pct']=flat.pollutant.map({p:uniform[f'crz_{p}_change_pct'] for p in POLS})
    flat['primary_attenuation_pct']=100*(1-flat.primary_crz_change_pct/flat.uniform_crz_change_pct)
    flat['rate_flat_attenuation_pct']=100*(1-flat.rate_flat_crz_change_pct/flat.uniform_crz_change_pct)
    flat['attenuation_difference_pp']=flat.rate_flat_attenuation_pct-flat.primary_attenuation_pct
    joined=flat.merge(source_long,on=KEYS,suffixes=('','_saved'),validate='one_to_one')
    check('H flat primary reference exact',np.array_equal(joined.primary_crz_change_pct,joined.primary_crz_change_pct_saved),len(joined))
    flat.to_csv(locate('phase2r/results/rate_flat_above_50_replicates.csv'),index=False)
    summary(flat,['slowdown_pct','pollutant'],'rate_flat_above_50_summary.csv')
    cap=pd.DataFrame(caprows).merge(source_long,on=KEYS,validate='one_to_one')
    cap['difference_pp']=cap.hardcap_crz_change_pct-cap.primary_crz_change_pct
    cap.to_csv(locate('phase2r/results/hard_50mph_speed_cap_replicates.csv'),index=False)
    caps=summary(cap,['slowdown_pct','pollutant'],'hard_50mph_speed_cap_summary.csv')
    counts=cap.groupby(['slowdown_pct','pollutant']).feasible.agg(n_feasible='sum',n_total='size').reset_index();counts['n_infeasible']=counts.n_total-counts.n_feasible
    caps.merge(counts,on=['slowdown_pct','pollutant']).to_csv(locate('phase2r/results/hard_50mph_speed_cap_summary.csv'),index=False)
    oldcap=pd.read_csv(locate('phase2/results/hard_50mph_speed_cap_sensitivity.csv')).rename(columns={'replicate':'replicate_id'})
    cc=cap.merge(oldcap,on=KEYS,validate='one_to_one',suffixes=('','_old'))
    check('Existing hard-cap feasibility reproduced',np.array_equal(cc.feasible,cc.feasible_old),len(cc))
    check('Existing hard-cap results reproduced',float(abs(cc.hardcap_crz_change_pct-cc.crz_change_pct).max())<=1e-10,float(abs(cc.hardcap_crz_change_pct-cc.crz_change_pct).max()))
    response=pd.DataFrame(resprows);response.to_csv(locate('phase2r/results/response_group_replicates.csv'),index=False)
    summary(response,['slowdown_pct','pollutant'],'response_group_summary.csv')
    # Local diagnostics are evaluated at the exact frozen operating cells and linked by keys.
    local=[]
    for ji,labels in enumerate(jnames):
        idx=int(np.flatnonzero(jcode==ji)[0]);vv=v[idx];yy=y[idx:idx+1]
        base=interpolate(yy,np.array([vv]))[0]
        j10=.5*interpolate(yy,np.array([.9*vv]))[0]+.5*interpolate(yy,np.array([1.1*vv]))[0]-base
        j20=.5*interpolate(yy,np.array([.8*vv]))[0]+.5*interpolate(yy,np.array([1.2*vv]))[0]-base
        for pi,p in enumerate(POLS):
            sign=lambda x: 'positive' if x>1e-10 else ('negative' if x< -1e-10 else 'zero')
            local.append(dict(**labels,pollutant=p,analysis_window_vmt=float(vmt[jcode==ji].sum()),baseline_rate_g_per_mile=base[pi],J10=j10[pi],J20=j20[pi],J10_sign=sign(j10[pi]),J20_sign=sign(j20[pi])))
    local=pd.DataFrame(local)
    oldj=pd.read_csv(locate('phase2/results/jensen_local_diagnostics.csv')).rename(columns={'period':'original_period','truck_type':'truck_class','baseline_speed_mph':'baseline_speed'})
    oldj['modeled_period']=oldj.original_period.map(PERIOD_MAP)
    jj=oldj.merge(local,on=jkeys+['pollutant'],validate='one_to_one',suffixes=('_old',''))
    check('Existing J10/J20 reproduced',len(jj)==len(oldj) and max(abs(jj.J10-jj.J10_old).max(),abs(jj.J20-jj.J20_old).max())<1e-10,len(jj))
    realized=pd.read_csv(locate('phase2r/results/roadway_period_truck_attenuation_summary.csv'))
    realized.merge(local,on=jkeys+['pollutant'],validate='many_to_one').to_csv(locate('phase2r/results/jensen_realized_attribution.csv'),index=False)
    check('Source files unchanged',all(Path(f).exists() and sha(Path(f))==digest for f,digest in frozen.items()),len(frozen))
    check('K frozen allocations unchanged',sha(locate('phase1b/qa/paired_allocations.npz'))==manifest['allocation_sha256'],manifest['allocation_sha256'])
    shutil.copyfile(locate('phase1b/qa/physical_segments.csv'),locate('phase2r/provenance/physical_segment_index.csv'))
    (locate('phase2r/provenance/environment.json')).write_text(json.dumps(dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,pyarrow=pa.__version__,raw_rows=rawrows,raw_bytes=rawpath.stat().st_size,csv_master_omitted='49 million rows; Parquet preserves all rows without a multi-gigabyte text duplicate'),indent=2))
    (locate('phase2r/qa/checks.json')).write_text(json.dumps(CHECKS,indent=2))
    (locate('phase2r/PHASE2R_QA_REPORT.txt')).write_text('PHASE 2R QA REPORT\nStatus: PASSED\n'+ '\n'.join(f"PASS {x['test']}: {x['detail']}" for x in CHECKS)+'\n')
    print('All core QA passed. Reviewer packaging may proceed.',flush=True)

if __name__=='__main__':
    try:main()
    except Exception:
        (locate('phase2r/PHASE2R_QA_REPORT.txt')).write_text('PHASE 2R QA REPORT\nStatus: FAILED - STOP\n'+json.dumps(CHECKS,indent=2)+'\n'+traceback.format_exc())
        raise
