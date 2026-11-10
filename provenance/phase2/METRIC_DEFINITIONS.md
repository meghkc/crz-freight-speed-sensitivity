# Phase 2R metric definitions

Phase 2R re-evaluates only frozen Phase 1B scenarios and the previously specified counterfactuals. It does not run MOVES, draw allocations, change fleet weights or rate tables, or revise the intervention design. Seed 20261002, 500 replicates for each 5/10/15/20% slowdown, full-day CRZ denominators, and the 08:00-18:00 intervention are retained.

## Cell and units

The master Parquet file has one row per replicate, pollutant, and frozen preaggregated physical-segment/period/truck/roadway/baseline-speed cell. `physical_segment_id` is the Phase 1B `physical_idx`; `provenance/physical_segment_index.csv` maps it to the physical road key. AM, midday, and PM mean the original `am_peak`, `midday`, and `pm_peak` period labels, with the original intervention fractions already incorporated in `analysis_vmt`.

Rates are g/mile. Emissions are modeled kg/day: analysis VMT times the preserved non-EV fraction times the rate, divided by 1,000. SU EV share is 2%; CT EV share is 0.5%. The remaining activity is treated as diesel. VMT is repeated for each pollutant; never sum VMT across pollutants. Likewise, replicate VMT is not additional independent observed traffic.

## Signed and absolute attribution

For cell i, gap_i = heterogeneous_emission_kg_i - uniform_emission_kg_i. A positive gap is a loss of uniform-speed benefit; a negative gap offsets that loss. Baseline-relative emission changes are separately saved and must not be confused with this heterogeneous-versus-uniform gap. An unchanged road has zero baseline-relative change but may have a positive gap because it forgoes the uniform scenario's benefit.

For a category within ONE replicate:

- signed_gap_kg = sum(gap_i).
- category_net_abs_gap_kg = abs(sum(gap_i)).
- cell_abs_gap_kg = sum(abs(gap_i)).
- signed_share_of_net_gap = category signed_gap_kg / total replicate signed_gap_kg.
- absolute_share = category cell_abs_gap_kg / total replicate cell_abs_gap_kg.

Share columns are fractions, not percentages; multiply by 100 for presentation. Signed shares may be negative or exceed 100% because opposing contributions cancel in the net gap. Absolute shares are nonnegative. Combined groups overlap (for example <10 lies within <20), so they must not be summed as a partition.

Net denominators with magnitude <= max(1e-12 kg, 1e-12 times total cell-absolute gap) are flagged and their ratios saved as missing. Cell-absolute denominators <=1e-12 kg are similarly flagged. Summaries include flag counts.

## Completeness and quantiles

The full Cartesian categories are inserted for every slowdown, replicate, and pollutant, including absent categories with VMT and contributions equal to zero. Baseline/scenario speed bins, roadway classes, response groups, periods, and roadway-period-response combinations have 500 observations per summary group. The high-speed combined group uses the strict test scenario_speed >50; <20 is also strict. Ordinary speed-bin boundaries are lower-inclusive and upper-exclusive; the legacy label >60 denotes the final 60-and-above bin. The strict >50 combined group is calculated directly rather than inferred from bin labels.

Each combined contribution, share, attenuation percentage, paired counterfactual difference, and response offset ratio is calculated within a replicate FIRST. P05/P50/P95 are then empirical quantiles across the 500 fixed random-placement replicates using linear interpolation. They are placement-distribution quantiles, not confidence intervals. Marginal medians are never summed to reconstruct a net median.

Attenuation percentage = 100 * (1 - heterogeneous CRZ percentage change / uniform CRZ percentage change), using the same negative uniform benchmark. An attenuation of 100% means the uniform benefit is fully lost. Counterfactual differences in CRZ percentage changes are percentage points, not relative percentages. The rate-flat attenuation difference is also expressed in percentage points of attenuation.

The offset ratio is slower-group baseline-relative increase / abs(faster-group baseline-relative reduction) only where faster delta <0 and slower delta >0. Other replicates are flagged, with no imputed ratio.

## Counterfactuals

Rate-flat uses EF(min(scenario speed,50)) but retains all actual scenario speeds, allocations, and the original +5.6% mean-speed constraint. Both primary and rate-flat attenuation use the same frozen uniform benchmark; its equality to the rate-flat uniform calculation is checked. Saved Phase 1B primary values are joined with explicit slowdown/replicate/pollutant keys.

Hard-cap retains the allocation and slowdown, caps faster-road speeds at 50 mph, and solves their pre-cap multiplier to recover the +5.6% VMT-weighted mean-speed change. The frozen intervention baseline has no speed above 50 mph, so unchanged/slower roads also satisfy the cap. Feasibility is checked against the maximum attainable speed sum. Infeasible records have no imputed emissions or uplift. The numerical bracket reaches saturation of every faster road, avoiding an arbitrary upper bound. Existing Phase 2 hard-cap outputs are cross-checked.

## Local diagnostics and realized contribution

J10 = 0.5 EF(0.9v) + 0.5 EF(1.1v) - EF(v); J20 uses 0.8v and 1.2v. Units are g/mile. Positive/negative values indicate a positive/negative symmetric mean-preserving-spread response at that operating point and spread size. Zero may mean both endpoints lie on one linear interpolation segment. These finite-spread diagnostics do not establish global convexity or a universal Jensen result.

Local diagnostics are joined to realized paired attenuation by roadway, period, truck class, pollutant, and baseline speed; slowdown remains explicit. The local tests are not substitutes for the realized attribution.

## Preservation and numerical tolerance

SHA-256 snapshots cover all existing Phase 1B and Phase 2 files. The complete primary replicate results must reproduce within 1e-10 before derived exports. Aggregate closure uses max(1e-10, 256 * machine epsilon * max(abs(reference),1)) to accommodate floating-point summation at the relevant scale; each maximum observed residual and tolerance is recorded. No changes are made to source results or manuscripts.

The master has about 49 million rows. Only the compressed Parquet master is written, avoiding an unnecessary multi-gigabyte CSV duplicate. Smaller paired and summary tables are CSV.
