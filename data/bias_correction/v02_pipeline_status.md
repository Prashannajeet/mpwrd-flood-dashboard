# V02 Bias-Correction Pipeline Status

- Run status: success
- Generated at: 2026-07-05T08:02:41.281465+00:00
- Database: `D:\01 Project\Development\mpwrd_streamlit_deploy_V02\data\bias_correction\cwc_bias_correction.sqlite`
- Input directory: `D:\01 Project\Development\mpwrd_streamlit_deploy_V02\data\bias_correction`

## Metrics

- cwc_daily_rows: 274733
- cwc_stations: 67
- training_ready_stations: 58
- review_approved_links: 31
- gauge_travel_links: 207
- hindcast_rows: 0
- training_overlap_rows: 0
- bias_factor_rows: 0
- calibrated_rows: 162
- bias_mode: readiness mode - raw forecast retained until hindcast/observed overlap is supplied

## Steps

- Build CWC bias database: success (0)
- Build hindcast/CWC training overlap: success (0)
- Train/apply baseline bias correction: success (0)
