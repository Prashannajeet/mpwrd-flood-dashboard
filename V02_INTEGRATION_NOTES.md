# MPWRD Dashboard V02 Integration Notes

V02 starts from the preserved app state in `mpwrd_streamlit_deploy` and introduces the CWC historical discharge integration layer for better GD-site analytics, forecast confidence, and future bias correction.

## Stage 1 Implemented

- Created V02 app copy at `D:\01 Project\Development\mpwrd_streamlit_deploy_V02`.
- Prepared CWC daily discharge observations into clean station-day training data.
- Built `data/bias_correction/cwc_bias_correction.sqlite` for fast dashboard access.
- Added SQLite tables for:
  - `cwc_daily_discharge`
  - `cwc_station_summary`
  - `cwc_flow_thresholds`
  - `gd_cwc_station_linkage_candidates`
  - `gd_cwc_station_linkage`
  - `forecast_station_inventory`
  - `current_forecast_cwc_context`
  - `gauge_travel_time_correlations`
- Added GD Site Analytics summary metrics for CWC history, training-ready stations, linked GD sites, and forecast context coverage.
- Added selected-station CWC historical calibration context with percentile thresholds.
- Added gauge-to-gauge lead/lag correlation screening for flood travel-time intelligence.
- Added `gd_cwc_station_linkage_review.csv` as the manual review/approval control file for GD-to-CWC station matching.
- Added a GD Site Analytics linkage review panel with approved/pending views and CSV download.
- Added baseline bias-correction training/apply framework.
- Added hindcast/reforecast intake and overlap builder framework.
- Added `historical_model_hindcast_template.csv` for importing historical model flow values.
- Added `historical_forecast_observation_training.csv` template for hindcast/observed overlap records.
- Added SQLite tables:
  - `historical_model_hindcast`
  - `historical_forecast_observation_training`
  - `forecast_bias_correction_factors`
  - `calibrated_gd_forecasts`
- Added GD Site Analytics bias-correction readiness, hindcast intake status, template downloads, and selected-site raw/corrected forecast status.
- Added one-command V02 refresh pipeline:
  - `scripts/run_v02_bias_pipeline.py`
  - `run_v02_bias_pipeline.bat`
- Added dashboard pipeline status panel and downloadable `v02_pipeline_status.md`.
- Added downstream warning-window table for selected GD/CWC stations using gauge-to-gauge lead/lag correlation.

## Current Data Readiness

- CWC daily rows: 274,733
- CWC stations: 67
- Training-ready stations: 58
- Auto-linked GD/CWC stations: 31
- Linkages needing review: 36
- Reviewed/approved links currently active: 31
- Gauge-to-gauge lead/lag links: 207
- High-confidence lead/lag links: 7
- Baseline correction mode: readiness mode until historical forecast/observed overlap is supplied
- Hindcast rows currently loaded: 0
- Training overlap rows currently loaded: 0
- Calibrated forecast rows currently written: 162
- Latest V02 pipeline status: success
- Downstream warning windows: active in GD Site Analytics selected-station context

## Next Stage

1. Review and approve GD-to-CWC station linkages in `data/bias_correction/gd_cwc_station_linkage_review.csv`.
2. Add historical hindcast/reforecast flow series to `data/bias_correction/historical_model_hindcast_template.csv`.
3. Run `scripts/build_hindcast_training_overlap.py` to join hindcast values with CWC daily observations.
4. Run `scripts/train_baseline_bias_correction.py` to train station/month/lead-time correction factors.
5. Review gauge-to-gauge lead/lag links and add drainage-network chainage for upstream/downstream confirmation.
6. Add trained corrected forecast flow and confidence intervals into GD Site Analytics.
7. Refine downstream warning windows with 3-hour/sub-daily data and drainage-network chainage.
8. Use `run_v02_bias_pipeline.bat` to refresh all V02 bias-correction assets after any linkage, hindcast, or CWC data update.
9. Promote final V02 changes to the online app after validation.
