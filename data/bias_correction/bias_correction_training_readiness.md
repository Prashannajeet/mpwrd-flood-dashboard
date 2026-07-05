# MP CWC Discharge Bias-Correction Training Readiness

## Historical Observation Dataset

- Source rows: 298,373
- Clean daily station rows: 274,733
- Stations: 67
- Districts: 22
- Rivers: 5
- Basins: 5
- Date range: 2001-01-01 to 2025-12-31
- Missing discharge rows: 0
- Duplicate station-date rows aggregated: 23,640
- Exact duplicate station-timestamp rows: 14,538
- Negative discharge rows requiring review: 1
- Zero discharge share: 15.37%

## Training Suitability

The CWC daily discharge file is suitable as the observed target dataset for discharge modelling and forecast bias correction. 61 stations have at least three years of data and at least 10% non-zero observations, which is adequate for station-wise or pooled basin-wise training.

## Linkage With Existing Forecast System

- Forecast/GD stations available in the app cache: 126
- Candidate CWC-to-forecast station links generated: 335
- High-confidence top links with score >= 0.65: 31

The current app forecast cache is a recent operational forecast window, while the CWC file is historical through 2025. Therefore, true historical bias correction requires a matching historical hindcast/reforecast archive for the same CWC dates. The generated linkage table provides the station/reach mapping needed to pull or attach those hindcast values.

## Recommended Bias-Correction Workflow

1. Use `cwc_daily_discharge_clean.csv` as the observation target.
2. Use `cwc_station_forecast_linkage_candidates.csv` to approve station-to-forecast reach matches.
3. Fetch or attach historical hindcast/reforecast discharge for the approved linked reaches.
4. Join observations and model values by station/reach, date, forecast issue time, and lead hours.
5. Train correction models:
   - Baseline: monthly median ratio and additive bias by station.
   - Operational: gradient boosting or TensorFlow model using lead time, month, basin, rainfall, upstream lag, and raw forecast.
   - Safety layer: monotonic clipping and return-period alert class validation.
6. Save corrected forecasts into the app database for dashboard display.

## Suggested Model Targets

- `observed_discharge_cms`: direct discharge target.
- `bias_cms = observed - raw_forecast`.
- `bias_ratio = observed / raw_forecast` with safe handling for very low flow.
- Alert class target: Normal, Watch, Warning, Critical based on observed return period or station thresholds.

## Generated Files

- `cwc_daily_discharge_clean.csv`
- `cwc_station_summary.csv`
- `cwc_station_forecast_linkage_candidates.csv`
- `bias_correction_training_schema.csv`
- `training_readiness_audit.json`
