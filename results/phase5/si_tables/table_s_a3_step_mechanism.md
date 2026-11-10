# Table S-A3. Decomposition of the -15% to -20% step

## Response-group contributions (medians across replicates)

Medians of components do not sum to the median of the net change; results/a3_decomposition_summary.csv also gives means, which do.

| Design | Slowdown | Pollutant | Faster (pp) | Slower (pp) | Net (pp) | Faster (kg/day) | Slower (kg/day) | Net (kg/day) |
|---|---|---|---|---|---|---|---|---|
| Random | -5% | CO2 | -1.2643 | 0.2045 | -1.0595 | -896.171 | 144.936 | -750.966 |
| Random | -5% | NOx | -2.3712 | 0.3804 | -1.9897 | -4.875 | 0.782 | -4.090 |
| Random | -5% | PM2.5 | -1.7008 | 0.2753 | -1.4238 | -0.051 | 0.008 | -0.043 |
| Random | -10% | CO2 | -1.4077 | 0.4135 | -0.9934 | -997.753 | 293.098 | -704.141 |
| Random | -10% | NOx | -2.6113 | 0.7689 | -1.8429 | -5.369 | 1.581 | -3.789 |
| Random | -10% | PM2.5 | -1.8768 | 0.5560 | -1.3200 | -0.057 | 0.017 | -0.040 |
| Random | -15% | CO2 | -1.5466 | 0.6174 | -0.9291 | -1096.228 | 437.604 | -658.516 |
| Random | -15% | NOx | -2.8486 | 1.1489 | -1.6976 | -5.856 | 2.362 | -3.490 |
| Random | -15% | PM2.5 | -2.0505 | 0.8306 | -1.2186 | -0.062 | 0.025 | -0.037 |
| Random | -20% | CO2 | -1.6855 | 0.9139 | -0.7732 | -1194.708 | 647.798 | -548.052 |
| Random | -20% | NOx | -3.0809 | 1.6815 | -1.4045 | -6.334 | 3.457 | -2.887 |
| Random | -20% | PM2.5 | -2.2226 | 1.2187 | -1.0062 | -0.067 | 0.037 | -0.030 |
| High-VMT | -5% | CO2 | -1.3910 | 0.4706 | -0.9204 | -985.979 | 333.591 | -652.388 |
| High-VMT | -5% | NOx | -2.5211 | 0.8761 | -1.6451 | -5.183 | 1.801 | -3.382 |
| High-VMT | -5% | PM2.5 | -1.8298 | 0.6321 | -1.1977 | -0.055 | 0.019 | -0.036 |
| High-VMT | -10% | CO2 | -1.6842 | 0.9413 | -0.7430 | -1193.798 | 667.181 | -526.617 |
| High-VMT | -10% | NOx | -3.0106 | 1.7521 | -1.2585 | -6.189 | 3.602 | -2.587 |
| High-VMT | -10% | PM2.5 | -2.1938 | 1.2642 | -0.9296 | -0.066 | 0.038 | -0.028 |
| High-VMT | -15% | CO2 | -1.9739 | 1.4119 | -0.5620 | -1399.087 | 1000.772 | -398.315 |
| High-VMT | -15% | NOx | -3.4958 | 2.6282 | -0.8677 | -7.187 | 5.403 | -1.784 |
| High-VMT | -15% | PM2.5 | -2.5553 | 1.8963 | -0.6590 | -0.077 | 0.057 | -0.020 |
| High-VMT | -20% | CO2 | -2.0959 | 2.0973 | 0.0014 | -1485.590 | 1486.585 | 0.995 |
| High-VMT | -20% | NOx | -3.8461 | 3.8675 | 0.0214 | -7.907 | 7.951 | 0.044 |
| High-VMT | -20% | PM2.5 | -2.7625 | 2.7912 | 0.0286 | -0.084 | 0.084 | 0.001 |

## Street contributions to each step, CO2

| Design | Component | Mean step -5 to -10 (pp) | Mean step -10 to -15 (pp) | Mean step -15 to -20 (pp) |
|---|---|---|---|---|
| Random | Street AM | 0.0000 | 0.0000 | 0.0493 |
| Random | Street midday | 0.0266 | 0.0257 | 0.0688 |
| Random | Street PM | 0.0387 | 0.0383 | 0.0374 |
| Random | Net (all classes) | 0.0666 | 0.0641 | 0.1567 |
| High-VMT | Street AM | 0.0224 | 0.0225 | 0.1366 |
| High-VMT | Street midday | 0.0717 | 0.0811 | 0.3311 |
| High-VMT | Street PM | 0.0903 | 0.0903 | 0.0903 |
| High-VMT | Net (all classes) | 0.1775 | 0.1878 | 0.5547 |

Other classes and all three pollutants by roadway class x period are in results/a3_step_by_component.csv.

## No-crossing counterfactual on the slowed roads

At -20%, slowed cells are evaluated on the linear rate segment they occupied at -15%. Everything else, including the -20% gain, is unchanged.

| Design | Pollutant | Median at -15 (%) | Median at -20 (%) | Step -10 to -15 (pp) | Step -15 to -20 (pp) | No-crossing median at -20 (%) | No-crossing step (pp) | Step removed (%) |
|---|---|---|---|---|---|---|---|---|
| Random | CO2 | -0.929 | -0.773 | 0.064 | 0.156 | -0.867 | 0.062 | 60.2 |
| Random | NOx | -1.698 | -1.404 | 0.145 | 0.293 | -1.560 | 0.137 | 53.1 |
| Random | PM2.5 | -1.219 | -1.006 | 0.101 | 0.212 | -1.120 | 0.098 | 53.8 |
| High-VMT | CO2 | -0.562 | 0.001 | 0.181 | 0.563 | -0.213 | 0.349 | 38.1 |
| High-VMT | NOx | -0.868 | 0.021 | 0.391 | 0.889 | -0.342 | 0.526 | 40.9 |
| High-VMT | PM2.5 | -0.659 | 0.029 | 0.271 | 0.688 | -0.234 | 0.425 | 38.2 |

## Faster-side 25 mph crossing, high-VMT design (paired means, pp)

| Pollutant | Allocations | n | Step -5 to -10 | Step -10 to -15 | Step -15 to -20 | No slower crossing | No slower or faster-25 crossing (-15 anchor) | No slower crossing, faster 25 anchored at -10 |
|---|---|---|---|---|---|---|---|---|
| CO2 | all allocations | 500 | 0.177 | 0.188 | 0.555 | 0.340 | 0.253 | 0.181 |
| CO2 | crosses between 15 and 20 | 295 | 0.177 | 0.178 | 0.543 | 0.328 | 0.181 | 0.181 |
| CO2 | already above 25 at 15 | 205 | 0.178 | 0.202 | 0.572 | 0.357 | 0.357 | 0.182 |
| NOx | all allocations | 500 | 0.386 | 0.396 | 0.883 | 0.520 | 0.449 | 0.391 |
| NOx | crosses between 15 and 20 | 295 | 0.386 | 0.388 | 0.874 | 0.510 | 0.390 | 0.390 |
| NOx | already above 25 at 15 | 205 | 0.387 | 0.408 | 0.898 | 0.534 | 0.534 | 0.391 |
| PM2.5 | all allocations | 500 | 0.268 | 0.278 | 0.679 | 0.416 | 0.338 | 0.273 |
| PM2.5 | crosses between 15 and 20 | 295 | 0.268 | 0.269 | 0.668 | 0.405 | 0.273 | 0.273 |
| PM2.5 | already above 25 at 15 | 205 | 0.268 | 0.291 | 0.694 | 0.432 | 0.432 | 0.274 |

## Smooth rate curve: PCHIP through the 16 bin centers, high-VMT design

PCHIP is applied to baseline, scenario and full-day denominator rates. Entries are median [P05, P95].

| Slowdown | CO2 (%) | NOx (%) | PM2.5 (%) | CO2 attenuation (%) | NOx attenuation (%) | PM2.5 attenuation (%) |
|---|---|---|---|---|---|---|
| -5% | -1.034 [-1.044, -1.023] | -1.683 [-1.709, -1.655] | -1.274 [-1.291, -1.258] | 9.4 | 24.6 | 20.1 |
| -10% | -0.882 [-0.905, -0.856] | -1.280 [-1.318, -1.241] | -1.011 [-1.040, -0.981] | 22.8 | 42.6 | 36.6 |
| -15% | -0.590 [-0.642, -0.536] | -0.747 [-0.800, -0.690] | -0.626 [-0.678, -0.575] | 48.3 | 66.5 | 60.7 |
| -20% | -0.171 [-0.240, -0.107] | -0.081 [-0.156, -0.005] | -0.120 [-0.192, -0.053] | 85.0 | 96.4 | 92.5 |

## Step pattern by profile and rate curve

| Profile | Rate curve | Design | Pollutant | Step -5 to -10 (pp) | Step -10 to -15 (pp) | Step -15 to -20 (pp) | Last step / mean earlier step |
|---|---|---|---|---|---|---|---|
| Base | Linear | Random | CO2 | 0.066 | 0.064 | 0.156 | 2.39 |
| Base | Linear | Random | NOx | 0.147 | 0.145 | 0.293 | 2.01 |
| Base | Linear | Random | PM2.5 | 0.104 | 0.101 | 0.212 | 2.07 |
| Base | Linear | High-VMT | CO2 | 0.177 | 0.181 | 0.563 | 3.14 |
| Base | Linear | High-VMT | NOx | 0.387 | 0.391 | 0.889 | 2.29 |
| Base | Linear | High-VMT | PM2.5 | 0.268 | 0.271 | 0.688 | 2.55 |
| Street x0.8 | Linear | Random | CO2 | 0.105 | 0.103 | 0.102 | 0.98 |
| Street x0.8 | Linear | Random | NOx | 0.167 | 0.166 | 0.161 | 0.96 |
| Street x0.8 | Linear | Random | PM2.5 | 0.125 | 0.123 | 0.121 | 0.98 |
| Street x0.8 | Linear | High-VMT | CO2 | 0.316 | 0.317 | 0.356 | 1.13 |
| Street x0.8 | Linear | High-VMT | NOx | 0.487 | 0.492 | 0.613 | 1.25 |
| Street x0.8 | Linear | High-VMT | PM2.5 | 0.369 | 0.373 | 0.455 | 1.23 |
| Street x1.2 | Linear | Random | CO2 | 0.131 | 0.149 | 0.173 | 1.24 |
| Street x1.2 | Linear | Random | NOx | 0.178 | 0.234 | 0.271 | 1.32 |
| Street x1.2 | Linear | Random | PM2.5 | 0.148 | 0.186 | 0.214 | 1.28 |
| Street x1.2 | Linear | High-VMT | CO2 | 0.312 | 0.332 | 0.163 | 0.51 |
| Street x1.2 | Linear | High-VMT | NOx | 0.437 | 0.565 | 0.549 | 1.10 |
| Street x1.2 | Linear | High-VMT | PM2.5 | 0.354 | 0.420 | 0.185 | 0.48 |
| Base | PCHIP | High-VMT | CO2 | 0.153 | 0.291 | 0.419 | 1.89 |
| Base | PCHIP | High-VMT | NOx | 0.403 | 0.533 | 0.666 | 1.42 |
| Base | PCHIP | High-VMT | PM2.5 | 0.263 | 0.385 | 0.506 | 1.56 |

Source: results/a3_*.csv.