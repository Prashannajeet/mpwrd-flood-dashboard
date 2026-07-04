# MP WRD Flood Report Dashboard

Streamlit dashboard for MP WRD Flood Season PDF capture, reservoir/river time-series review, dam map alerts, weather intelligence, rainfall monitoring, and operational DSS reporting.

## Streamlit Community Cloud

1. Push this folder to a GitHub repository.
2. Open `https://share.streamlit.io/`.
3. Click **New app**.
4. Select the repository and branch.
5. Main file path:

```text
flood_report_app.py
```

6. Click **Deploy**.

## Local Run

```bash
pip install -r requirements.txt
streamlit run flood_report_app.py
```

Optional secure data service:

```bash
uvicorn flood_report_api:app --host 0.0.0.0 --port 8600
```

## Operational Rainfall Database

The app includes a backend-ready rainfall store for MP rain gauges, dams, and GD sites:

```bash
python satellite_rainfall_refresh.py --include-dams --include-gd-sites
```

For a continuously running local refresh service:

```bash
run_satellite_rainfall_refresh.bat
```

For weather forecasts, dam forecast cache is designed to refresh once daily at 12:30 AM IST and display instantly from the database:

```bash
python weather_cache_refresh.py --daily-at 00:30 --forecast-all --include-dams
```

Local Windows runner:

```bash
run_daily_dam_weather_refresh.bat
```

Hosted deployment includes a scheduled job equivalent to `12:30 AM IST` to refresh town + dam weather forecast cache daily.

The script creates `data/satellite_rainfall_timeseries.sqlite` with:

- `rainfall_station_master`
- `rainfall_3hour_observations`
- `rainfall_refresh_log`

To add official MP rain-gauge stations, place `data/mp_raingauge_stations.csv` with these columns:

```text
station_id,station_name,district,basin,latitude,longitude
```

Secure rainfall feed credentials must be configured only as environment variables or Streamlit secrets. Do not commit credentials to the repository.

```text
SECURE_FEED_USERNAME
SECURE_FEED_PASSWORD
SECURE_FEED_BASE_URL
```

To verify operational feed login without exposing credentials, use the backend access-check workflow.

To import extracted 3-hour rainfall values from an approved operational source:

```bash
python satellite_rainfall_refresh.py --import-csv data/operational_3hour_station_extract.csv --source-product OPERATIONAL_RAINFALL_3H
```

Import CSV columns:

```text
station_id,observed_at,rainfall_3h_mm,rainfall_24h_mm,source_latency_hours,quality_flag
```

## Hosted Deployment

This repo includes hosted deployment configuration for the dashboard, secure data service, and scheduled refresh tasks.

Share service endpoints only through authorized operational documentation.

## Included Data

The repo includes parsed sample outputs for:

- `parsed_16-06-26_12PM`
- `parsed_18-06-26_8AM`

PDF uploads work in the app, but uploads on free Streamlit hosting are runtime/ephemeral unless persistent storage is added.
