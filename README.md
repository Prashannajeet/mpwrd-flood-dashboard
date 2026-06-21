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
