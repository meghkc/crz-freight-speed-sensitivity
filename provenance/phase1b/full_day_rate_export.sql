SELECT 36061 AS countyID,r.* FROM phase1b_nyc2025_full_rates_output_20261002.rateperdistance r
WHERE MOVESRunID=2 AND yearID=2025 AND dayID=5 AND monthID BETWEEN 1 AND 10
AND hourID BETWEEN 1 AND 24 AND fuelTypeID=2 AND processID=1
AND sourceTypeID IN (52,53,61,62) AND roadTypeID IN (4,5)
AND pollutantID IN (90,3,110) AND avgSpeedBinID BETWEEN 1 AND 16
ORDER BY sourceTypeID,roadTypeID,pollutantID,avgSpeedBinID,monthID,hourID;
