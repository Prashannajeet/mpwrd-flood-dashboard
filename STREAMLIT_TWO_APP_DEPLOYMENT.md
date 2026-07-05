# Streamlit Two-App Deployment Plan

Deploy two separate Streamlit Community Cloud apps from the same GitHub repository.

Repository:

```text
Prashannajeet/mpwrd-flood-dashboard
```

Main file for both apps:

```text
flood_report_app.py
```

## App 1: V01 Stable

- App name: `mpwrd-flood-dashboard-v01`
- Branch: `v01`
- Purpose: old stable app, kept intact exactly as it was running before V02.
- Commit currently pinned by branch: `db2c4c5`
- Main file path: `flood_report_app.py`
- Python dependencies: `requirements.txt`

## App 2: V02 Enhanced DSS

- App name: `mpwrd-flood-dashboard-v02`
- Branch: `v02`
- Purpose: enhanced app with all V01 features plus CWC/GD analytics, lead/lag travel-time intelligence, downstream warning windows, hindcast intake, and bias-correction readiness.
- Commit currently pinned by branch: `2711c21`
- Main file path: `flood_report_app.py`
- Python dependencies: `requirements.txt`

## Required Streamlit Cloud Setup

Create two apps in Streamlit Community Cloud:

1. New app for V01:
   - Repository: `Prashannajeet/mpwrd-flood-dashboard`
   - Branch: `v01`
   - Main file path: `flood_report_app.py`
   - App URL/name: `mpwrd-flood-dashboard-v01`

2. New app for V02:
   - Repository: `Prashannajeet/mpwrd-flood-dashboard`
   - Branch: `v02`
   - Main file path: `flood_report_app.py`
   - App URL/name: `mpwrd-flood-dashboard-v02`

## Secrets

Keep V01 and V02 secrets separate in Streamlit Cloud.

Recommended common secrets where applicable:

```toml
admin_user = "admin_nitaai"
admin_password = "SET_IN_STREAMLIT_CLOUD"
```

Only add external API or email credentials to the app that needs them. Do not copy experimental V02 credentials into V01 unless required.

## Version Rule

- V01 app must always track branch `v01`.
- V02 app must always track branch `v02`.
- Do not point either app to `main` if the goal is strict parallel operation.
- `main` may follow V02 for development, but the public parallel apps should use `v01` and `v02` branches directly.
