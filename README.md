# MP WRD Flood Report Dashboard

Streamlit dashboard and REST/GeoJSON API for MP WRD Flood Season PDF capture, reservoir/river time-series review, dam map alerts, and external GIS data sharing.

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

API:

```bash
uvicorn flood_report_api:app --host 0.0.0.0 --port 8600
```

## 3-Hour Rainfall Database

The app now includes a backend-ready satellite rainfall store for MP rain gauges, dams, and GD sites:

```bash
python satellite_rainfall_refresh.py --include-dams --include-gd-sites
```

For a continuously running local refresh service:

```bash
run_satellite_rainfall_refresh.bat
```

The script creates `data/satellite_rainfall_timeseries.sqlite` with:

- `rainfall_station_master`
- `rainfall_3hour_observations`
- `rainfall_refresh_log`

To add official MP rain-gauge stations, place `data/mp_raingauge_stations.csv` with these columns:

```text
station_id,station_name,district,basin,latitude,longitude
```

To import extracted 3-hour rainfall values from NASA IMERG or another approved source:

```bash
python satellite_rainfall_refresh.py --import-csv data/imerg_3hour_station_extract.csv --source-product IMERG_EARLY_3H
```

Import CSV columns:

```text
station_id,observed_at,rainfall_3h_mm,rainfall_24h_mm,source_latency_hours,quality_flag
```

## Render Deployment

This repo includes `render.yaml` with two web services:

- `mpwrd-flood-dashboard`
- `mpwrd-flood-api`

Deploy from Render Blueprints using this GitHub repository.

Important API endpoints:

- `/api/reports`
- `/api/reservoir-observations`
- `/api/district-summary`
- `/api/basin-summary`
- `/api/geojson/dams`
- `/api/geojson/reservoir-status`
- `/api/geojson/alerts`

## Included Data

The repo includes parsed sample outputs for:

- `parsed_16-06-26_12PM`
- `parsed_18-06-26_8AM`

PDF uploads work in the app, but uploads on free Streamlit hosting are runtime/ephemeral unless persistent storage is added.
