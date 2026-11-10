"""Build manuscript Table 1, Figure 1-2 data and Figures 1-2 from saved results (no model runs).

Excerpt of phase4/build_phase4.py: lines 28-92 (helpers), 93-104 (source names), 187-215
(Table 1 and figure data) and 400-441 (figures), copied verbatim except for the path and
font-fallback lines marked "repo:". The manuscript, SI and DOCX parts are not included.
"""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo: code/, for paths.py
from paths import locate
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


POLS = ['CO2', 'NOx', 'PM25']
LABEL = {'CO2': 'CO₂', 'NOx': 'NOₓ', 'PM25': 'PM₂.₅'}
AUDIT, HASHES, CACHE = [], {}, {}
MILE_KM = 1.609344


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source(rel):
    path = locate(rel)  # repo: was the project folder / rel
    assert path.is_file(), f'Missing frozen source: {rel}'
    HASHES.setdefault(rel, digest(path))
    return path


def csv(rel):
    if rel not in CACHE:
        CACHE[rel] = pd.read_csv(source(rel))
    return CACHE[rel].copy()


def js(rel):
    return json.loads(source(rel).read_text(encoding='utf-8'))


def record(statement, value, rel, column, selector, verified=True):
    assert verified, f'Unverified statement: {statement}'
    AUDIT.append({'manuscript_statement': statement, 'value_used': str(value),
                  'source_file': rel, 'source_column': column,
                  'source_row/scenario': str(selector), 'verified': True})
    return value


def row(rel, **where):
    frame = csv(rel)
    for key, val in where.items():
        frame = frame[frame[key] == val]
    assert len(frame) == 1, (rel, where, len(frame))
    return frame.iloc[0]


def number(rel, col, where, statement, fmt='.3f', multiplier=1):
    value = float(row(rel, **where)[col]) * multiplier
    assert np.isfinite(value)
    return record(statement, format(value, fmt), rel,
                  col + (f' * {multiplier}' if multiplier != 1 else ''), where)


def interval(rel, col, where, statement, decimals=3):
    return '{} [{}, {}]'.format(*[number(rel, col + '_' + q, where, statement + ' ' + q,
                                        f'.{decimals}f') for q in ['p50', 'p05', 'p95']])


def audit_frame(frame, rel, context):
    # Preserve exact values and source row keys for exported figure/table data.
    for idx, item in frame.iterrows():
        key = '; '.join(f'{k}={item[k]}' for k in ['design', 'specification', 'slowdown_pct',
                     'pollutant', 'period', 'truck_type', 'speed_mph', 'modeled_period',
                     'truck_class', 'roadway_class', 'baseline_speed'] if k in item)
        for col, val in item.items():
            if isinstance(val, (int, float, np.integer, np.floating)) and pd.notna(val):
                record(context, val, rel, col, f'data row {idx + 1}; {key}')


U = 'phase1b/results/moves_uniform_benchmark.csv'
R = 'phase1b/results/moves_heterogeneous_summary.csv'
P = 'phase3/results/placement_emissions_summary.csv'
D = 'phase2r/results/phase2_reviewer_summary.csv'
CHAR = 'phase3/results/slower_group_characteristics.csv'
M6 = 'phase3/results/structured_averaging_definition_sensitivity.csv'
VMT = 'phase1b/qa/vmt_closure.csv'
RATE = 'phase1b/rates/moves5_composite_rates.csv'
J = 'phase2r/results/jensen_realized_attribution.csv'

# Main table: one common rounding rule, four decimals for all emission changes.
headers = ['Scenario', 'Faster-road gain (%)', 'CO2 change (%)', 'NOx change (%)', 'PM2.5 change (%)']
table_rows = [['Uniform +5.6%', '5.60', *[number(U, 'crz_change_pct', {'pollutant': pol}, 'Table 1 uniform ' + pol, '.4f') for pol in POLS]]]
names = {'random': 'Random, slower', 'high_vmt': 'High-VMT slower', 'infrastructure_first': 'Infrastructure-first', 'low_vmt': 'Low-VMT bound'}
for design, slow in [('random', 5), ('random', 10), ('random', 15), ('random', 20), ('high_vmt', 20), ('infrastructure_first', 20)]:
    where = dict(design=design, slowdown_pct=slow)
    scenario_label = f'Random, slower −{slow}%' if design == 'random' else f'{names[design]}, −{slow}%'
    table_rows.append([scenario_label, interval(P, 'solved_faster_pct', dict(**where, pollutant='CO2'), 'Table 1 gain', 2),
                       *[interval(P, 'crz_change_pct', dict(**where, pollutant=pol), 'Table 1 ' + pol, 4) for pol in POLS]])
pd.DataFrame(table_rows, columns=headers).to_csv(locate('phase4/Table1_final.csv'), index=False, encoding='utf-8-sig')
table_note = ('Primary 08:00–18:00 intervention; full-day CRZ baseline denominator. Entries are median [P05, P95] placement percentiles, not confidence intervals. Negative emissions changes indicate reductions. Structured cases are stress tests. The high-VMT −20% case requires a 45.03% median balancing gain. Emissions: four decimals; speed gains: two. Body emissions use three decimals, except near-zero stress-test medians use four.')

# Figure data are copied from frozen surfaces/diagnostics. Unit conversions only.
curve = csv(RATE).query("context == 'window' and roadTypeID == 5").copy()
audit_frame(curve, RATE, 'Figure 1 curve knots')
curve['record_type'] = 'curve'
baseline = csv(J).query("roadway_class == 'Street' and slowdown_pct == 5").copy()
audit_frame(baseline[['pollutant', 'modeled_period', 'truck_class', 'baseline_speed', 'baseline_rate_g_per_mile']], J, 'Figure 1 baseline markers')
markers = pd.DataFrame({'period': baseline.modeled_period.map({'AM': 'am_peak', 'midday': 'midday', 'PM': 'pm_peak'}),
                        'roadTypeID': 5, 'truck_type': baseline.truck_class, 'pollutant': baseline.pollutant,
                        'speed_mph': baseline.baseline_speed, 'g_per_mile': baseline.baseline_rate_g_per_mile,
                        'context': 'window', 'composition': 'primary', 'record_type': 'baseline'})
fig1 = pd.concat([curve, markers], ignore_index=True)
fig1['speed_kmh'] = fig1.speed_mph * MILE_KM
fig1['g_per_km'] = fig1.g_per_mile / MILE_KM
fig1.to_csv(locate('phase4/Figure1_data.csv'), index=False)
fig2 = csv(P).query("design != 'low_vmt'").copy()
audit_frame(fig2, P, 'Figure 2 frozen summary')
fig2.to_csv(locate('phase4/Figure2_data.csv'), index=False)

# Publication graphics: fixed typography and unit conversion, no model execution.
plt.rcParams.update({'font.family': 'Times New Roman', 'font.size': 10, 'axes.grid': False,
                     'figure.facecolor': 'white', 'axes.facecolor': 'white', 'pdf.fonttype': 42})
from matplotlib import font_manager
try:  # repo: the original stopped if Times New Roman was missing; fall back to the default serif font
    font_manager.findfont('Times New Roman', fallback_to_default=False)
except ValueError:
    plt.rcParams['font.family'] = 'serif'
period_colors = {'am_peak': '#0072B2', 'midday': '#D55E00', 'pm_peak': '#009E73'}
period_names = {'am_peak': 'AM', 'midday': 'Midday', 'pm_peak': 'PM'}
fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.8))
for ax, pol in zip(axs, POLS):
    for period, color in period_colors.items():
        for truck, style in [('SU', '-'), ('CT', '--')]:
            g = fig1.query("record_type == 'curve' and pollutant == @pol and period == @period and truck_type == @truck").sort_values('speed_mph')
            g = g[g.speed_mph.between(5, 60)]
            ax.plot(g.speed_kmh, g.g_per_km, color=color, linestyle=style, linewidth=1.25)
            m = fig1.query("record_type == 'baseline' and pollutant == @pol and period == @period and truck_type == @truck")
            ax.scatter(m.speed_kmh, m.g_per_km, color=color, marker='o' if truck == 'SU' else 's', s=26, zorder=5)
    ax.set(title=LABEL[pol], xlabel='Speed (km/h)', ylabel='Running-exhaust rate (g/km)')
    ax.set_xlim(8, 97); ax.spines[['top', 'right']].set_visible(False)
handles = [Line2D([0], [0], color=c, label=period_names[p]) for p, c in period_colors.items()]
handles += [Line2D([0], [0], color='black', linestyle=s, marker=m, label=t) for t,s,m in [('SU','-','o'),('CT','--','s')]]
fig.legend(handles=handles, loc='lower center', ncol=5, frameon=False, bbox_to_anchor=(.5, .005))
fig.suptitle('MOVES5 Street rate curves and baseline operating points', fontsize=12)
fig.tight_layout(rect=(0, .11, 1, .94))
for ext in ['png', 'pdf', 'jpeg']: fig.savefig(locate(f'phase4/Figure1.{ext}'), dpi=350)
plt.close(fig)
fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.8))
styles = {'random': ('#0072B2', 'o'), 'high_vmt': ('#D55E00', 's'), 'infrastructure_first': ('#009E73', '^')}
for ax, pol in zip(axs, POLS):
    for design, (color, marker) in styles.items():
        g = fig2.query('pollutant == @pol and design == @design').sort_values('slowdown_pct')
        ax.plot(g.slowdown_pct, g.crz_change_pct_p50, color=color, marker=marker, label=names[design].replace(', slower',''))
        ax.fill_between(g.slowdown_pct, g.crz_change_pct_p05, g.crz_change_pct_p95, color=color, alpha=.14)
    ax.axhline(float(row(U, pollutant=pol).crz_change_pct), color='.45', linestyle='--', linewidth=.9, label='Uniform +5.6%')
    ax.axhline(0, color='.25', linewidth=.7)
    ax.set(title=LABEL[pol], xlabel='Slower-road speed reduction (%)', ylabel='CRZ emissions change (%)', xticks=[5,10,15,20])
    ax.spines[['top', 'right']].set_visible(False)
handles, labs = axs[0].get_legend_handles_labels()
fig.legend(handles, labs, loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(.5, .005))
fig.suptitle('Primary 08:00–18:00 intervention; full-day CRZ denominator', fontsize=12)
fig.tight_layout(rect=(0, .11, 1, .94))
for ext in ['png', 'pdf', 'jpeg']: fig.savefig(locate(f'phase4/Figure2.{ext}'), dpi=350)
plt.close(fig)
