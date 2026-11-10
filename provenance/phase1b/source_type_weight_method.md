# Source-type VMT weighting

The primary is an EPA-default modeled-composition specification, not observed New York County fleet composition. Phase 1A used national population/VMT normalization and default fleet distributions. A new full-day Inventory-mode activity run cloned those inputs and emitted distance by source, fuel, road, month and hour. It does not calibrate those inputs to local truck counts.

Only diesel activityTypeID=1 and fuelTypeID=2 distances are used. At each roadTypeID x monthID x hourID, w52=VMT52/(VMT52+VMT53), w53=1-w52, and equivalently w61/w62. All 1,920 source-level cells are complete and positive. This is more granular than road x modeled-period weighting.

For each hourly cell, blend compatible g/mile rates using these within-cell VMT weights. Then aggregate the hourly blended rates using actual Monday-Friday counts in January-October 2025 and equal hour weights inside each modeled period. Holidays remain weekdays. Equal within-period hour weights preserve the model's 1/3 AM and 2/3 PM activity approximation. The period-summary CSV gives calendar/hour-averaged effective weights for interpretation; it is not a second, fixed-weight blending step.

The 'window' surface uses hourID 9, 10-16, and 17-18. The full-day denominator uses AM 7-9, midday 10-16, PM 17-19 and night 20-24 plus 1-6. Separate surfaces avoid applying the selected AM/PM hour's weather to unselected hours. Source blending before temporal averaging preserves source-composition/weather covariance.

Short-haul (52/61) and long-haul (53/62) cases are modeled composition alternatives, not observed bounds on NYC truck shares. MTA SU/MU entry shares are not used. ICE activity is treated as diesel; model EV fractions stay SU=0.02 and CT=0.005.

Activity input database: phase1b_nyc2025_full_activity_input_20261002; output: phase1b_nyc2025_full_activity_output_20261002; version: MOVES5.0.1. The activity run's diagnostic NOx inventory is not used for emission rates. Emission rates remain separately audited rate-mode outputs.
