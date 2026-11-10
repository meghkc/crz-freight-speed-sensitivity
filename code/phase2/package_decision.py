"""Package the repaired, QA-approved paired exports for reviewer interpretation."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
D=locate('phase2r/results')
K=['slowdown_pct','pollutant']
def read(name):return pd.read_csv(D/(name+'.csv'))
def md(d):
 def fmt(v):
  if isinstance(v,(float,np.floating)):return f'{v:.6g}'
  return str(v)
 return '| '+' | '.join(d.columns)+' |\n| '+' | '.join(['---']*len(d.columns))+' |\n'+'\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in d.itertuples(index=False,name=None))
def table(d,cols,rename=None):return md(d[cols].rename(columns=rename or {}))
def pctcols(d,cols):
 d=d.copy()
 for c in cols:d[c]*=100
 return d

def main():
 for name in ['checks','persisted_checks']:
  checks=json.loads((locate('phase2r/qa')/f'{name}.json').read_text())
  if not checks or not all(x['passed'] for x in checks):raise RuntimeError('QA is not passed')
 if 'FAILED' in (locate('phase2r/PHASE2R_QA_REPORT.txt')).read_text():raise RuntimeError('QA failure recorded')
 primary=read('primary_repaired_summary');combined=read('attenuation_gap_combined_summary')
 flat=read('rate_flat_above_50_summary');cap=read('hard_50mph_speed_cap_summary');response=read('response_group_summary')
 rp=read('roadway_period_attenuation_summary');j=read('jensen_realized_attribution')
 totals=read('replicate_totals');comb_rep=read('attenuation_gap_combined_replicates')
 out=primary[K+['uniform_crz_change_pct_p50','primary_crz_change_pct_p50','primary_crz_change_pct_p05','primary_crz_change_pct_p95','attenuation_pct_p50']].rename(columns={'uniform_crz_change_pct_p50':'uniform_crz_change_pct','primary_crz_change_pct_p50':'heterogeneous_p50','primary_crz_change_pct_p05':'heterogeneous_p05','primary_crz_change_pct_p95':'heterogeneous_p95'})
 for name in ['high_speed_gt50','low_speed_lt20','street','highway_family']:
  fields={'signed_share_of_net_gap_p50':name+'_signed_share_p50','absolute_share_p50':name+'_absolute_share_p50'}
  if name in ['high_speed_gt50','low_speed_lt20']:fields['signed_gap_kg_p50']=name+'_signed_gap_kg_p50'
  out=out.merge(combined[combined.category==name][K+list(fields)].rename(columns=fields),on=K,validate='one_to_one')
 out=out.merge(flat[K+['rate_flat_crz_change_pct_p50','rate_flat_minus_primary_pp_p50']].rename(columns={'rate_flat_crz_change_pct_p50':'rate_flat_result_p50'}),on=K,validate='one_to_one')
 out=out.merge(cap[K+['hardcap_crz_change_pct_p50','difference_pp_p50','n_feasible']].rename(columns={'hardcap_crz_change_pct_p50':'hard_cap_result_p50','difference_pp_p50':'hard_cap_minus_primary_pp_p50','n_feasible':'hard_cap_feasible_n'}),on=K,validate='one_to_one')
 out=out.merge(response[K+['faster_group_delta_kg_p50','slower_group_delta_kg_p50','offset_ratio_p50']],on=K,validate='one_to_one')
 assert len(out)==12 and not out.isna().any().any()
 out.to_csv(locate('phase2r/results/phase2_reviewer_summary.csv'),index=False)
 # Ratios and exposure shares are computed within each replicate, then summarized.
 exp=comb_rep.merge(totals[K+['replicate_id','analysis_vmt']],on=K+['replicate_id'],validate='many_to_one',suffixes=('','_total'))
 exp['affected_vmt_share_pct']=100*exp.analysis_vmt/exp.analysis_vmt_total
 exp_summary=exp.groupby(K+['category']).affected_vmt_share_pct.quantile([.05,.5,.95]).unstack().reset_index().rename(columns={.05:'p05',.5:'p50',.95:'p95'})
 exp_summary.to_csv(locate('phase2r/results/combined_vmt_share_summary.csv'),index=False)
 high=combined[combined.category=='high_speed_gt50'];low=combined[combined.category=='low_speed_lt20'];street=combined[combined.category=='street'];family=combined[combined.category=='highway_family']
 hmin,hmax=100*high.absolute_share_p50.min(),100*high.absolute_share_p50.max()
 hsmin,hsmax=100*high.signed_share_of_net_gap_p50.min(),100*high.signed_share_of_net_gap_p50.max()
 lsmin,lsmax=100*low.absolute_share_p50.min(),100*low.absolute_share_p50.max()
 ssmin,ssmax=100*street.signed_share_of_net_gap_p50.min(),100*street.signed_share_of_net_gap_p50.max()
 fmax=flat.rate_flat_minus_primary_pp_p50.abs().max();cmax=cap.difference_pp_p50.abs().max()
 allflat=read('rate_flat_above_50_replicates');allcap=read('hard_50mph_speed_cap_replicates')
 fworst=allflat.rate_flat_minus_primary_pp.abs().max();cworst=allcap.difference_pp.abs().max()
 # This interpretation is specific to the measured small effects, not a universal cutoff.
 assert hmax<.1 and fmax<.01 and cmax<.01 and (cap.n_infeasible==0).all()
 top=rp.loc[rp.groupby(K).signed_gap_kg_p50.idxmax()]
 assert ((top.roadway_class=='Street')&(top.modeled_period=='midday')).all()
 sections=['# Phase 2R decision',
 '**QA passed. M2 classification: A — >50-mph behavior is negligible for these frozen experiments. M3 is numerically resolved for the modeled local mechanism.** These conclusions apply to the specified MOVES5 diesel fleet assumptions, road mapping, 08:00-18:00 intervention, and frozen random placements; they do not establish global convexity, observational validation of fleet composition, or robustness to structured placement.',
 'All results below come from paired replicate-level calculations. Each slowdown has 500 replicates. P05-P95 denotes empirical placement quantiles, not a confidence interval. Percent changes use the original full-day CRZ baseline; shares in the CSVs are fractions and are displayed as percentages below. Positive attenuation gaps mean lost uniform-speed benefit. Separate marginal medians need not add.',
 '## QA and repair scope',
 'All 2,000 Phase 1B primary replicates reproduced: maximum absolute error across checked metrics was 5.68434e-14, below 1e-10. The master contains 49,332,000 rows. Independent read-back of every Parquet row group found exact cell-formula closure, signed-total residual at most 5.68434e-14 kg, and cell-absolute-total residual at most 4.54747e-13 kg. Every categorical summary uses 500 replicates, including explicit zero-exposure groups. All 111 source files in the Phase 1B/Phase 2 snapshot and the allocation digest remained unchanged. No MOVES run, rate change, new random allocation, Phase 3 work, or manuscript edit occurred.',
 '## 1. Median affected VMT above 50 mph',
 table(exp_summary[(exp_summary.category=='high_speed_gt50')&(exp_summary.pollutant=='CO2')],['slowdown_pct','p05','p50','p95']),
 'Values are percentages of affected analysis-window CRZ VMT and are identical across pollutants. These exposure shares are descriptive; the emissions-based attribution below determines the M2 conclusion.',
 '## 2–3. Signed and absolute >50-mph contributions',
 f'Median signed shares range from {hsmin:.4f}% to {hsmax:.4f}% of the net gap: they are small and negative, so these high-speed cells slightly offset the attenuation. Their median share of total absolute cell contributions is only {hmin:.4f}–{hmax:.4f}%. The category-net magnitude is retained separately in the combined summary.',
 table(pctcols(high,['signed_share_of_net_gap_p50','absolute_share_p50']),K+['signed_gap_kg_p50','category_net_abs_gap_kg_p50','cell_abs_gap_kg_p50','signed_share_of_net_gap_p50','absolute_share_p50']),
 '## 4. Contributions below 20 mph',
 f'The <20-mph cells account for {lsmin:.2f}–{lsmax:.2f}% of median absolute contributions. Their signed shares exceed 100% because reductions in other cells offset much of their positive contribution; this is expected for a signed net denominator and is not a percentage error.',
 table(pctcols(low,['signed_share_of_net_gap_p50','absolute_share_p50']),K+['signed_gap_kg_p50','cell_abs_gap_kg_p50','signed_share_of_net_gap_p50','absolute_share_p50']),
 'The exact <10, 10-15, 15-20, and 20-40 combinations, with P05/P50/P95 and category-net magnitudes, are in [attenuation_gap_combined_summary.csv](results/attenuation_gap_combined_summary.csv). The full bins, including 20-30, are in [attenuation_gap_category_summary.csv](results/attenuation_gap_category_summary.csv).',
 '## 5. Rate-flat-above-50 test',
 f'The largest absolute median paired change is {fmax:.6f} CRZ percentage points; the largest individual paired change is {fworst:.6f} points. All heterogeneous medians remain emissions reductions. The positive paired differences indicate slightly weaker benefits after flattening over the actually occupied >50-mph range; this does not support an upturn-driven explanation. The effect is immaterial to the conclusion.',
 table(flat,K+['primary_crz_change_pct_p50','rate_flat_crz_change_pct_p50','rate_flat_minus_primary_pp_p50','attenuation_difference_pp_p50']),
 'The difference column is the median of paired differences, not the difference of marginal medians. Both attenuation calculations use the same frozen uniform benchmark, whose equality to the rate-flat uniform result was checked.',
 '## 6. True 50-mph speed cap',
 f'All 500/500 replicates at each slowdown are feasible (2,000 unique placements; zero infeasible). The original +5.6% aggregate speed constraint is recovered in every feasible case. The largest absolute median paired emission change is {cmax:.6f} percentage points; the largest individual paired change is {cworst:.6f} points. The cap does not materially change the conclusion.',
 table(cap[cap.pollutant=='CO2'],['slowdown_pct','n_feasible','n_infeasible','solved_faster_pct_p05','solved_faster_pct_p50','solved_faster_pct_p95','achieved_mean_speed_change_pct_p50']),
 table(cap,K+['hardcap_crz_change_pct_p05','hardcap_crz_change_pct_p50','hardcap_crz_change_pct_p95','difference_pp_p50']),
 '## 7. Dominant roadway class',
 f'Street accounts for {ssmin:.2f}–{ssmax:.2f}% of median signed net-gap shares. The exact combined Highway + Bridge + Ramp + Tunnel contribution is small; combined quantities were formed within each replicate, not by summing roadway medians.',
 table(pctcols(out,['street_signed_share_p50','street_absolute_share_p50','highway_family_signed_share_p50','highway_family_absolute_share_p50']),K+['street_signed_share_p50','street_absolute_share_p50','highway_family_signed_share_p50','highway_family_absolute_share_p50']),
 'Other/fallback contributes zero affected CRZ VMT and zero intervention attenuation in this model. Each separate roadway class is retained in the category export.',
 '## 8. Dominant roadway × period combinations',
 'Street × midday has the largest median signed contribution for every pollutant and slowdown. Street × PM is the next major positive contributor. At 20% slowdown, Street × AM also contributes positively; at lower slowdowns its net contribution is near zero despite appreciable absolute contributions, indicating cancellation.',
 table(pctcols(rp[rp.roadway_class=='Street'],['signed_share_of_net_gap_p50','absolute_share_p50']),K+['modeled_period','signed_gap_kg_p50','signed_share_of_net_gap_p50','absolute_share_p50']),
 'The response-specific roadway-period summaries distinguish faster-road offsets, slower-road penalties, and forgone uniform benefits on unchanged roads.',
 '## 9. Replicate-specific response-group offset ratios',
 'The table gives baseline-relative emissions changes in kg/day and the quantiles of slower increase / |faster reduction| calculated within each replicate. These ratios are not ratios of marginal medians. The unchanged group has zero baseline-relative change; the net column is calculated directly within each replicate.',
 table(response,K+['faster_group_delta_kg_p50','slower_group_delta_kg_p50','unchanged_group_delta_kg_p50','net_delta_kg_p50','offset_ratio_p05','offset_ratio_p50','offset_ratio_p95','invalid_offset_flag_n']),
 '## 10. Local J10/J20 at operating points that carry the VMT',
 'Street baseline speeds are 12 mph in AM, 18 mph at midday, and 10 mph in PM. The 18-mph Street midday cells carry 22,319.235 analysis-window vehicle-miles (about 73.695% of all affected VMT). J10 is numerically zero at 12 and 18 mph because the symmetric endpoints remain within one linear interpolation segment; J20 is positive at those speeds. At the 10-mph PM operating point, both J10 and J20 are positive. Thus the relevant finite-spread response is locally positive or linear, not a globally proven convex relationship.',
 table(j[(j.slowdown_pct==20)&(j.roadway_class=='Street')],['modeled_period','truck_class','pollutant','baseline_speed','analysis_window_vmt','baseline_rate_g_per_mile','J10','J20','signed_gap_kg_p50','absolute_share_p50']),
 'J values are g/mile; values around 1e-13 or smaller are floating-point zeros under the documented sign tolerance. The final two columns above are the separately calculated realized attenuation at 20% slowdown (absolute shares are fractions). All slowdowns and all occupied roadway/truck operating points are in [jensen_realized_attribution.csv](results/jensen_realized_attribution.csv). A local mean-preserving-spread test does not reproduce the heterogeneous allocation itself: class/period weights and asymmetric speed changes also matter.',
 '### Pollutant-specific numerical explanation',
 'The similar slower/faster offset ratios show that all three pollutants share the offset mechanism, but their attenuation percentages differ because their rate curves and uniform benefits differ. At 20% slowdown, Street midday supplies median signed shares of 48.61% for CO2, 68.66% for NOx, and 63.22% for PM2.5; Street PM supplies 38.52%, 23.31%, and 27.77%, respectively. At the 18-mph midday point, CT versus SU J20 is approximately 9.693 versus 8.706 g/mile for CO2, 0.165317 versus 0.044323 for NOx, and 0.000462 versus 0.000757 for PM2.5. Consistently, the realized CT midday contribution is larger than SU for NOx, whereas SU dominates for CO2 and PM2.5; these are within-pollutant comparisons, not comparisons of magnitudes across pollutant units.',
 '## 11. M2 classification',
 f'**A. >50-mph behavior negligible; attenuation is primarily a low-/moderate-speed nonlinear effect.** This is supported by emissions attribution, not VMT alone: (i) median >50-mph absolute contributions are at most {hmax:.4f}%; (ii) median signed contributions are slightly negative, not a positive driver; (iii) flattening changes the median paired result by at most {fmax:.6f} percentage points; and (iv) all hard-cap cases remain feasible with median paired effects at most {cmax:.6f} points. The high-speed concern is numerically resolved for the frozen scenarios.',
 '## 12. M3 conclusion',
 '**M3 is numerically resolved for these scenarios.** The exports now connect each local operating point to realized roadway-period/truck attenuation and retain all paired zero-exposure cases. Dominant low-speed Street cells have positive finite-spread effects at relevant spread sizes, and the realized attribution identifies Street midday and PM as the principal positive contributors. This establishes the modeled local mechanism; it does not assert a global Jensen theorem or replace future tests of structured spatial placement.',
 '## 13. Manuscript-ready mechanism statement',
 'Equal VMT-weighted mean speeds do not imply equal emissions because speed changes are evaluated through pollutant-, truck-, road-, and period-specific nonlinear MOVES5 rate curves. In the dominant Street operating cells, symmetric 20% speed spreads around 12 and 18 mph increase average emission rates, while the 10-mph PM point exhibits a positive response at both 10% and 20% spreads. The realized attenuation is concentrated in Street midday and PM activity, with <20-mph scenario cells contributing about 64–70% of total absolute cell-level effects and >50-mph cells contributing less than 0.03% at the median. As slowdown severity increases, slower-road emission increases offset a larger share of faster-road reductions despite retaining the same +5.6% aggregate mean-speed improvement.',
 '## Primary results retained unchanged',
 table(out,K+['uniform_crz_change_pct','heterogeneous_p05','heterogeneous_p50','heterogeneous_p95','attenuation_pct_p50']),
 '## Deliverables',
 '\n'.join('- ['+name+'](results/'+name+')' for name in ['phase2_reviewer_summary.csv','attenuation_gap_combined_summary.csv','roadway_period_attenuation_summary.csv','roadway_period_response_attenuation_summary.csv','jensen_realized_attribution.csv','rate_flat_above_50_summary.csv','hard_50mph_speed_cap_summary.csv','response_group_summary.csv']),
 'See [PHASE2R_QA_REPORT.txt](PHASE2R_QA_REPORT.txt), [METRIC_DEFINITIONS.md](METRIC_DEFINITIONS.md), the paired replicate CSVs, and raw/attenuation_gap_cell_level.parquet for auditability. The existing Phase 2 mechanism figures remain available unchanged in ../phase2/figures/. No manuscript was edited.'
 ]
 (locate('phase2r/PHASE2R_DECISION.md')).write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
 (locate('phase2r/README.md')).write_text('''# Phase 2R: repaired paired attribution exports

Start with [PHASE2R_DECISION.md](PHASE2R_DECISION.md), [PHASE2R_QA_REPORT.txt](PHASE2R_QA_REPORT.txt), and [results/phase2_reviewer_summary.csv](results/phase2_reviewer_summary.csv).

The 49,332,000-row compressed master is `raw/attenuation_gap_cell_level.parquet`. Numeric share columns are fractions; see [METRIC_DEFINITIONS.md](METRIC_DEFINITIONS.md). All result summaries retain empirical P05/P50/P95 and 500-replicate counts. The original Phase 2 directory remains an unchanged audit record; use Phase 2R outputs for corrected attribution.

## Reproducibility

Python scripts are run with `-B` to avoid changing bytecode in source directories. The only extra dependency, PyArrow, is isolated in `dependencies/`; exact package versions are recorded in `provenance/environment.json`.

1. `python -B code/repair_exports.py`: verify source hashes and Phase 1B reproduction, then export the frozen derived calculations; no MOVES or random allocations.
2. `python -B code/audit_exports.py`: independently read back the Parquet/CSV exports and check formulas, closure, Cartesian completeness, and the original mean-speed constraint.
3. `python -B code/package_decision.py`: only after both QA gates pass, produce the reviewer table and decision.

The first two steps have already completed successfully. Regeneration overwrites only Phase 2R derived artifacts; do not run merely to view results. If any required QA fails, stop before issuing conclusions. `provenance/source_sha256.json` freezes all existing Phase 1B and Phase 2 files; `provenance/physical_segment_index.csv` maps cell IDs back to frozen physical roads.

No Phase 3 or manuscript work is included. No duplicate multi-gigabyte master CSV is generated.
''',encoding='utf-8')
 print('Reviewer summary and decision created after both QA gates.')
 print(out.to_string(index=False))
if __name__=='__main__':main()
