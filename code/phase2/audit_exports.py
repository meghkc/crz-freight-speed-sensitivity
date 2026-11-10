"""Audit persisted exports independently, without evaluating rate functions."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import sys,json
import numpy as np,pandas as pd
import pyarrow.parquet as pq
checks=[]
def check(name,ok,detail):
 checks.append(dict(test=name,passed=bool(ok),detail=str(detail)))
 if not ok:raise RuntimeError(name+': '+str(detail))
try:
 total=pd.read_csv(locate('phase2r/results/replicate_totals.csv')).set_index(['slowdown_pct','replicate_id','pollutant'])
 raw=pq.ParquetFile(locate('phase2r/raw/attenuation_gap_cell_level.parquet'))
 check('Parquet row groups',raw.num_row_groups==2000,raw.num_row_groups)
 maxima=dict(raw_formula=0.,signed_sum=0.,absolute_sum=0.,speed_constraint=0.)
 exact60=0
 for i in range(raw.num_row_groups):
  d=raw.read_row_group(i,columns=['slowdown_pct','replicate_id','pollutant','analysis_vmt','baseline_speed','scenario_speed','baseline_emission_kg','uniform_emission_kg','heterogeneous_emission_kg','attenuation_gap_cell_kg','hetero_delta_kg','uniform_delta_kg']).to_pandas()
  for a,b,c in [('heterogeneous_emission_kg','uniform_emission_kg','attenuation_gap_cell_kg'),('heterogeneous_emission_kg','baseline_emission_kg','hetero_delta_kg'),('uniform_emission_kg','baseline_emission_kg','uniform_delta_kg')]:maxima['raw_formula']=max(maxima['raw_formula'],float(abs(d[a]-d[b]-d[c]).max()))
  for pol,g in d.groupby('pollutant'):
   k=(g.slowdown_pct.iloc[0],g.replicate_id.iloc[0],pol);t=total.loc[k]
   maxima['signed_sum']=max(maxima['signed_sum'],abs(g.attenuation_gap_cell_kg.sum()-t.signed_gap_kg))
   maxima['absolute_sum']=max(maxima['absolute_sum'],abs(abs(g.attenuation_gap_cell_kg).sum()-t.cell_abs_gap_kg))
  a=d[d.pollutant=='CO2'];achieved=100*((a.analysis_vmt*a.scenario_speed).sum()/(a.analysis_vmt*a.baseline_speed).sum()-1)
  maxima['speed_constraint']=max(maxima['speed_constraint'],abs(achieved-5.6))
  exact60+=int((a.scenario_speed==60).sum())
 for name,error in maxima.items():check('Persisted '+name,error<=1e-10,error)
 check('No ambiguous exact-60 cells',exact60==0,exact60)
 c=pd.read_csv(locate('phase2r/results/attenuation_gap_category_replicates.csv'))
 expected={'scenario_speed_bin':9,'baseline_speed_bin':9,'roadway_class':6,'response_group':3,'modeled_period':3}
 for dim,n in expected.items():
  a=c[c.decomposition_dimension==dim]
  check(dim+' complete unique Cartesian rows',len(a)==4*500*3*n and not a.duplicated(['slowdown_pct','replicate_id','pollutant','category']).any(),len(a))
 z=c[c.analysis_vmt==0]
 check('Explicit zero-exposure emissions',len(z)>0 and z[['signed_gap_kg','category_net_abs_gap_kg','cell_abs_gap_kg','hetero_delta_kg']].eq(0).all().all(),len(z))
 for name,n,keys in [('roadway_period_attenuation_replicates.csv',18,['roadway_class','modeled_period']),('roadway_period_response_attenuation_replicates.csv',54,['roadway_class','modeled_period','response_group']),('attenuation_gap_combined_replicates.csv',9,['category'])]:
  a=pd.read_csv(locate('phase2r/results')/name)
  check(name+' complete unique rows',len(a)==4*500*3*n and not a.duplicated(['slowdown_pct','replicate_id','pollutant']+keys).any(),len(a))
  check(name+' category-net absolute definition',np.allclose(a.category_net_abs_gap_kg,abs(a.signed_gap_kg),rtol=0,atol=1e-12),'abs(sum) separately retained')
  check(name+' absolute shares in range',a.absolute_share.between(-1e-12,1+1e-12).all(),'checked every row')
 (locate('phase2r/qa/persisted_checks.json')).write_text(json.dumps(checks,indent=2))
 with (locate('phase2r/PHASE2R_QA_REPORT.txt')).open('a') as f:f.write('\nPERSISTED EXPORT AUDIT\n'+'\n'.join('PASS '+x['test']+': '+x['detail'] for x in checks)+'\n')
 print(json.dumps(checks,indent=2))
except Exception as e:
 with (locate('phase2r/PHASE2R_QA_REPORT.txt')).open('a') as f:f.write('\nStatus: FAILED - STOP\n'+str(e)+'\n')
 raise
