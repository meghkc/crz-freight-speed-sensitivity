# Table S-A2b. Achieved length shares of the random allocations

Algorithm (`assign_groups_by_length` in ../freight_model/analyze_heterogeneous_speed_emissions.py): each physical segment receives a random number, segments are sorted by it, and cumulative CRZ length is computed at each segment's midpoint. A whole segment is faster if its midpoint falls at or below 37.37% of total length, unchanged if at or below 83.84%, and slower otherwise. Because whole segments are assigned, achieved shares differ slightly from the targets.

| Group | Target length share (%) | Achieved range (%) | Median abs deviation (pp) | P95 abs deviation (pp) | Max abs deviation (pp) |
|---|---|---|---|---|---|
| Faster | 37.37 | 37.21-37.54 | 0.022 | 0.087 | 0.165 |
| Unchanged | 46.46 | 46.21-46.68 | 0.033 | 0.114 | 0.255 |
| Slower | 16.16 | 16.00-16.32 | 0.021 | 0.076 | 0.163 |

n = 2,000 allocations (4 levels x 500). Source: results/a2_allocation_diagnostics.csv; per-allocation values in results/a2_allocation_shares.csv.