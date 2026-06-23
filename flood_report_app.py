from __future__ import annotations

import json
import math
import os
import hmac
import sys
import re
import subprocess
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from html import escape
from pathlib import Path
from datetime import date, time

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


APP_DIR = Path(__file__).resolve().parent
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
DAM_SHAPEFILE = APP_DIR / "dam_shapefile" / "Dams_EinC_54_R2.shp"
GLOFAS_PROJECT_JSON = APP_DIR / "data" / "glofas_mp_project.json"
GRRR_PROJECT_JSON = APP_DIR / "data" / "grrr_mp_project.json"
MP_TOWNS_CSV = APP_DIR / "data" / "mp_towns.csv"
RESERVOIR_CAPACITY_ESTIMATES_CSV = APP_DIR / "data" / "reservoir_capacity_estimates.csv"
RESERVOIR_CAPACITY_CURVES_CSV = APP_DIR / "data" / "reservoir_capacity_curves.csv"
RESERVOIR_CAPACITY_CURVES_FABDEM_CSV = APP_DIR / "data" / "reservoir_capacity_curves_fabdem.csv"
MP_DISTRICTS_GEOJSON = (
    APP_DIR / "data" / "mp-districts.geojson"
    if (APP_DIR / "data" / "mp-districts.geojson").exists()
    else APP_DIR.parent / "nitageoai_platform" / "private_flood_dashboard" / "data" / "mpwrd" / "mp-districts.geojson"
)
MP_DRAINS_GEOJSON = (
    APP_DIR / "data" / "mp-drains.geojson"
    if (APP_DIR / "data" / "mp-drains.geojson").exists()
    else APP_DIR.parent / "nitageoai_platform" / "private_flood_dashboard" / "data" / "mpwrd" / "mp-drains.geojson"
)
ARCGIS_EMBED_ITEM_ID = "5f7c5ee24d104d31bc2f85ecba4bd17a"
ARCGIS_PORTAL_URL = "https://prashannajeet.maps.arcgis.com"
ARCGIS_EMBED_CENTER = "78.22922399768257,23.48361289099537"
ARCGIS_EMBED_SCALE = "4622324.434309"
GEOGLOWS_MEDIUM_URL = "https://livefeeds3.arcgis.com/arcgis/rest/services/GEOGLOWS/GlobalWaterModel_Medium/MapServer"
BUNDLED_SITE_PACKAGES = Path(
    r"C:\Users\Welcome\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages"
)
if BUNDLED_SITE_PACKAGES.exists() and str(BUNDLED_SITE_PACKAGES) not in sys.path:
    sys.path.append(str(BUNDLED_SITE_PACKAGES))

from flood_report_parser import parse_pdf  # noqa: E402


st.set_page_config(
    page_title="Nita AI & Geo-Analytics | MPWRD VBSR Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
)


COLUMN_LABEL_OVERRIDES = {
    "lsl_m": "LSL (m)",
    "frl_m": "FRL (m)",
    "frl_gap_m": "FRL Gap (m)",
    "water_level_m": "Water Level (m)",
    "current_live_capacity_mcm": "Current Live Capacity (MCM)",
    "live_capacity_frl_mcm": "Live Capacity at FRL (MCM)",
    "filling_percent": "Filling (%)",
    "display_filling": "Filling (%)",
    "rainfall_daily_mm": "Daily Rainfall (mm)",
    "rainfall_total_mm": "Total Rainfall (mm)",
    "danger_or_max_water_level_m": "Danger / Max Water Level (m)",
    "gate_opened_count": "Opened Gates",
    "total_no_of_gates": "Total Gates",
    "opening_m": "Opening (m)",
    "discharge_cumecs": "Discharge (cumecs)",
    "discharge_cusec": "Discharge (cusecs)",
    "wl_delta_m": "Water Level Change (m)",
    "elevation_m": "Elevation (m)",
    "area_sqkm": "Area (sq.km)",
    "volume_mcm": "Volume (MCM)",
    "waterbody_area_sqkm": "Waterbody Area (sq.km)",
    "alert_level": "Alert Level",
    "configured_alert": "Configured Alert",
    "alert_reason": "Alert Reason",
    "rapid_rise_alert": "Rapid Rise Alert",
    "reservoir_name": "Reservoir",
    "dam_name": "Dam",
    "gauge_station": "Gauge Station",
    "river_name": "River",
    "map_district": "Map District",
    "sub_basin": "Sub Basin",
    "major_basin": "Major Basin",
    "observed_at": "Observed At",
    "report_at": "Report At",
    "report_folder": "Report Folder",
    "source_filename": "Source File",
    "source_file_hash": "Source File Hash",
    "extraction_method": "Extraction Method",
    "season_year": "Season Year",
}

COOLORS_ALERT_PALETTE = [
    "#580aff",
    "#147df5",
    "#0aefff",
    "#0aff99",
    "#a1ff0a",
    "#deff0a",
    "#ffd300",
    "#ff8700",
    "#ff0000",
    "#be0aff",
]


def column_display_label(column: object) -> str:
    raw = str(column)
    if raw in COLUMN_LABEL_OVERRIDES:
        return COLUMN_LABEL_OVERRIDES[raw]
    label = raw.replace("_", " ").strip().title()
    replacements = {
        " Id": " ID",
        " Api": " API",
        " Url": " URL",
        " Sms": "SMS",
        " Pdf": "PDF",
        " Ocr": "OCR",
        " Frl": "FRL",
        " Lsl": "LSL",
        " Mcm": "MCM",
        " Wse": "WSE",
        " Dss": "DSS",
        " Glofas": "GloFAS",
        " Grrr": "GRRR",
        " Geoglows": "GEOGLOWS",
    }
    for old, new in replacements.items():
        label = label.replace(old, new)
    return label


def prettify_dataframe_columns(data: object) -> object:
    if isinstance(data, pd.DataFrame):
        return data.rename(columns={column: column_display_label(column) for column in data.columns})
    return data


def friendly_column_config(data: pd.DataFrame, existing: dict | None = None) -> dict:
    config = dict(existing or {})
    for column in data.columns:
        if column not in config:
            config[column] = st.column_config.Column(column_display_label(column))
    return config


_ORIGINAL_ST_DATAFRAME = st.dataframe


def _dataframe_with_friendly_headers(data=None, *args, **kwargs):
    return _ORIGINAL_ST_DATAFRAME(prettify_dataframe_columns(data), *args, **kwargs)


st.dataframe = _dataframe_with_friendly_headers

st.markdown(
    """
    <style>
    :root {
        --bg: #f4f8ff;
        --panel: #ffffff;
        --panel-soft: #f8fafc;
        --line: #e5eaf3;
        --line-strong: #c7d2e5;
        --text: #172033;
        --muted: #64748b;
        --blue: #2563eb;
        --green: #00a884;
        --amber: #f59e0b;
        --red: #ef4444;
        --rose: #fb7185;
        --cyan: #06b6d4;
        --violet: #8b5cf6;
    }
    html, body, [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 8% 8%, rgba(37, 99, 235, 0.14), transparent 28%),
            radial-gradient(circle at 92% 10%, rgba(6, 182, 212, 0.16), transparent 30%),
            linear-gradient(180deg, #fbfdff 0%, #f4f8ff 45%, #eef8ff 100%);
        font-family: "Roboto", "Inter", "Segoe UI", sans-serif;
    }
    header[data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"],
    #MainMenu {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
    }
    .block-container {
        max-width: 1540px;
        padding-top: 0.35rem;
        padding-bottom: 2rem;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
        border-right: 1px solid var(--line);
    }
    h1, h2, h3, p, label, div, span {
        color: var(--text);
        letter-spacing: 0 !important;
        font-family: "Roboto", "Inter", "Segoe UI", sans-serif;
    }
    h2 {
        font-size: 1.05rem !important;
    }
    .masthead {
        border: 1px solid var(--line);
        background:
            linear-gradient(135deg, rgba(255,255,255,0.96), rgba(239,246,255,0.96)),
            linear-gradient(120deg, rgba(37,99,235,0.14), rgba(20,184,166,0.13), rgba(245,158,11,0.10));
        border-radius: 8px;
        padding: 0.86rem 1.05rem 0.86rem 1.12rem;
        margin: 0.35rem 0 0.78rem;
        box-shadow: 0 16px 34px rgba(15, 23, 42, 0.065);
        position: relative;
        z-index: 1;
        overflow: hidden;
    }
    .masthead::before {
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: 5px;
        background: linear-gradient(180deg, #2563eb, #14b8a6, #f59e0b);
    }
    .masthead-top {
        display: flex;
        justify-content: space-between;
        gap: 1.2rem;
        align-items: center;
    }
    .brand-lockup {
        display: flex;
        align-items: center;
        gap: 0.78rem;
        min-width: 0;
    }
    .brand-logo {
        width: 54px;
        height: 54px;
        border-radius: 16px;
        display: grid;
        place-items: center;
        flex: 0 0 auto;
        background:
            radial-gradient(circle at 25% 20%, rgba(255,255,255,0.95), transparent 28%),
            linear-gradient(135deg, #2563eb 0%, #14b8a6 58%, #f59e0b 100%);
        box-shadow: 0 14px 30px rgba(37, 99, 235, 0.20);
        color: #ffffff;
        font-size: 1.45rem;
        font-weight: 900;
        letter-spacing: 0 !important;
    }
    .brand-kicker {
        color: #2563eb;
        font-size: 0.72rem;
        font-weight: 800;
        line-height: 1;
        text-transform: uppercase;
        letter-spacing: 0.08em !important;
        margin-bottom: 0.28rem;
    }
    .brand-name {
        color: #0f172a;
        font-size: 0.98rem;
        font-weight: 850;
        line-height: 1.15;
    }
    .brand-domain {
        color: #0f766e;
        font-size: 0.76rem;
        font-weight: 700;
        line-height: 1.2;
        margin-top: 0.12rem;
    }
    .title-group {
        border-left: 1px solid #dbe5f3;
        margin-left: 0.18rem;
        padding-left: 0.9rem;
        min-width: 0;
    }
    .title {
        font-size: 1.34rem;
        line-height: 1.15;
        font-weight: 850;
    }
    .subtitle {
        color: var(--muted);
        font-size: 0.82rem;
        margin-top: 0.24rem;
        max-width: 760px;
    }
    .meta-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
        justify-content: flex-end;
        flex: 0 0 auto;
    }
    .meta {
        border: 1px solid #c7d2fe;
        background: rgba(255,255,255,0.9);
        border-radius: 8px;
        padding: 0.48rem 0.58rem;
        color: #1e3a8a;
        font-size: 0.72rem;
        font-weight: 800;
        white-space: nowrap;
        box-shadow: 0 10px 22px rgba(37, 99, 235, 0.08);
    }
    .meta-label {
        color: #64748b;
        display: block;
        font-size: 0.58rem;
        font-weight: 850;
        letter-spacing: 0.06em !important;
        line-height: 1;
        margin-bottom: 0.18rem;
        text-transform: uppercase;
    }
    .meta-value {
        color: #0f172a;
        display: block;
        font-size: 0.78rem;
        font-weight: 850;
        line-height: 1.15;
    }
    .sidebar-brand {
        border: 1px solid var(--line);
        border-radius: 8px;
        background: linear-gradient(135deg, #ffffff 0%, #eef8ff 100%);
        padding: 0.82rem 0.78rem;
        margin: 0.25rem 0 0.9rem;
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
    }
    .sidebar-brand-row {
        display: flex;
        align-items: center;
        gap: 0.58rem;
    }
    .sidebar-logo {
        width: 38px;
        height: 38px;
        border-radius: 12px;
        display: grid;
        place-items: center;
        color: #fff;
        background: linear-gradient(135deg, #2563eb, #14b8a6 62%, #f59e0b);
        font-size: 1.05rem;
        font-weight: 900;
        box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
    }
    .sidebar-brand-title {
        color: #0f172a;
        font-size: 0.88rem;
        font-weight: 850;
        line-height: 1.15;
    }
    .sidebar-brand-subtitle {
        color: #0f766e;
        font-size: 0.72rem;
        font-weight: 700;
        margin-top: 0.1rem;
    }
    .dashboard-topnav-title {
        margin: 0.75rem 0 0;
        padding: 0.72rem 0.95rem 0.15rem;
        border: 1px solid var(--line);
        border-bottom: 0;
        border-radius: 8px 8px 0 0;
        background:
            linear-gradient(90deg, rgba(37,99,235,0.98), rgba(20,184,166,0.96), rgba(245,158,11,0.92));
        color: #ffffff;
        font-size: 0.74rem;
        font-weight: 850;
        letter-spacing: 0.08em !important;
        text-transform: uppercase;
        box-shadow: 0 14px 30px rgba(15, 23, 42, 0.08);
    }
    .dashboard-topnav-active {
        margin: -0.2rem 0 0.85rem;
        padding: 0.46rem 0.9rem;
        border: 1px solid var(--line);
        border-top: 0;
        border-radius: 0 0 8px 8px;
        background: rgba(255,255,255,0.92);
        color: var(--muted);
        font-size: 0.76rem;
    }
    .dashboard-topnav-active b {
        color: #0f172a;
    }
    div[data-testid="stButton"] button {
        border-radius: 8px;
        min-height: 38px;
        font-weight: 780;
    }
    div[data-testid="stButton"] button[kind="primary"],
    div[data-testid="stButton"] button[data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #14b8a6, #2563eb) !important;
        border-color: transparent !important;
        color: #ffffff !important;
        box-shadow: 0 8px 18px rgba(37,99,235,0.20);
    }
    div[data-testid="stButton"] button[kind="primary"] p,
    div[data-testid="stButton"] button[data-testid="baseButton-primary"] p {
        color: #ffffff !important;
        font-weight: 900 !important;
    }
    .main-nav-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.45rem;
        background: #172033;
        border: 1px solid #172033;
        padding: 0.42rem;
        margin-bottom: 0;
    }
    .main-nav-item {
        display: block;
        border-radius: 6px;
        padding: 0.58rem 0.72rem;
        color: #e5edf8;
        font-size: 0.84rem;
        font-weight: 780;
        text-align: center;
        background: rgba(255,255,255,0.06);
    }
    .main-nav-item.active {
        color: #ffffff;
        background: linear-gradient(135deg, #14b8a6, #2563eb);
        box-shadow: 0 8px 18px rgba(37,99,235,0.22);
    }
    @media (max-width: 900px) {
        .masthead-top {
            align-items: flex-start;
            flex-direction: column;
        }
        .title-group {
            border-left: 0;
            margin-left: 0;
            padding-left: 0;
        }
        .brand-lockup {
            align-items: flex-start;
        }
        .meta-row {
            justify-content: flex-start;
        }
    }
    div[data-testid="stMetric"] {
        background:
            linear-gradient(180deg, rgba(255,255,255,0.99), rgba(248,251,255,0.98));
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 0.72rem 0.78rem;
        min-height: 80px;
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
    }
    div[data-testid="stMetricLabel"] {
        color: var(--muted);
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.28rem;
        font-weight: 760;
        color: var(--text);
    }
    .panel-note {
        color: var(--muted);
        font-size: 0.8rem;
        line-height: 1.35;
    }
    .district-strip {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
        gap: 0.6rem;
        margin: 0.55rem 0 1rem;
    }
    .district-gauge-card {
        border: 1px solid var(--line);
        border-radius: 8px;
        background:
            linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.98)),
            linear-gradient(135deg, rgba(37,99,235,0.16), rgba(6,182,212,0.12), rgba(245,158,11,0.08));
        padding: 0.55rem 0.62rem;
        box-shadow: 0 14px 28px rgba(15, 23, 42, 0.07);
    }
    .district-gauge-title {
        display: block;
        color: var(--text);
        font-size: 0.78rem;
        font-weight: 760;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .district-gauge-meta {
        color: var(--muted);
        font-size: 0.72rem;
        display: block;
        margin-top: 0.2rem;
    }
    .speedometer {
        width: 100%;
        height: 58px;
        margin-top: 0.15rem;
    }
    .speed-value {
        font-size: 1rem;
        font-weight: 800;
        fill: #172033;
    }
    .side-kpi-panel {
        border: 1px solid var(--line);
        border-radius: 8px;
        background:
            linear-gradient(180deg, rgba(255,255,255,0.99), rgba(248,251,255,0.98)),
            linear-gradient(135deg, rgba(37,99,235,0.15), rgba(6,182,212,0.10), rgba(251,113,133,0.08));
        padding: 0.75rem;
        margin-bottom: 0.7rem;
        box-shadow: 0 16px 34px rgba(15, 23, 42, 0.07);
    }
    .alert-legend-panel {
        border: 1px solid #f1d9a8;
        border-radius: 8px;
        background:
            linear-gradient(180deg, rgba(255,255,255,0.98), rgba(255,251,235,0.96)),
            linear-gradient(135deg, rgba(239,68,68,0.12), rgba(245,158,11,0.12), rgba(37,99,235,0.08));
        padding: 0.68rem 0.75rem;
        margin-bottom: 0.7rem;
        box-shadow: 0 12px 26px rgba(15, 23, 42, 0.05);
        color: #334155;
        font-size: 0.75rem;
        line-height: 1.35;
    }
    .alert-legend-panel b {
        display: block;
        color: #172033;
        font-size: 0.76rem;
        margin-bottom: 0.28rem;
    }
    .legend-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 4px;
        vertical-align: middle;
    }
    .side-kpi-title {
        color: var(--muted);
        font-size: 0.72rem;
        font-weight: 760;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    .side-kpi-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.5rem;
    }
    .side-kpi {
        border: 1px solid #e5eaf3;
        border-radius: 8px;
        background: #ffffff;
        padding: 0.52rem 0.58rem;
    }
    .side-kpi span {
        display: block;
        color: var(--muted);
        font-size: 0.66rem;
        line-height: 1.15;
    }
    .side-kpi b {
        display: block;
        color: var(--text);
        font-size: 1.04rem;
        line-height: 1.25;
        margin-top: 0.12rem;
    }
    .selected-dam-panel {
        border: 1px solid var(--line);
        border-radius: 8px;
        background:
            linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.98)),
            linear-gradient(135deg, rgba(251,113,133,0.16), rgba(245,158,11,0.12), rgba(6,182,212,0.08));
        padding: 0.85rem;
        box-shadow: 0 16px 34px rgba(15, 23, 42, 0.07);
        margin-bottom: 0.7rem;
    }
    .infographic-frame {
        border: 1px solid var(--line);
        border-radius: 8px;
        background:
            linear-gradient(135deg, rgba(255,255,255,0.98), rgba(239,246,255,0.94)),
            linear-gradient(135deg, rgba(37,99,235,0.12), rgba(6,182,212,0.10), rgba(251,113,133,0.08));
        padding: 0.72rem;
        box-shadow: 0 18px 42px rgba(15, 23, 42, 0.07);
        margin-bottom: 0.55rem;
    }
    .infographic-title {
        color: var(--text);
        font-size: 1.15rem;
        font-weight: 820;
        line-height: 1.2;
        margin-bottom: 0.22rem;
    }
    .infographic-subtitle {
        color: var(--muted);
        font-size: 0.82rem;
        line-height: 1.35;
        margin-bottom: 0.48rem;
    }
    .infographic-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
        gap: 0.5rem;
    }
    .infographic-card {
        border: 1px solid rgba(199, 210, 229, 0.9);
        border-radius: 8px;
        background: rgba(255,255,255,0.92);
        padding: 0.55rem 0.62rem;
        min-height: 72px;
    }
    .infographic-card span {
        display: block;
        color: var(--muted);
        font-size: 0.66rem;
        font-weight: 760;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    .infographic-card b {
        display: block;
        color: var(--text);
        font-size: 1.22rem;
        line-height: 1.15;
        margin-top: 0.28rem;
    }
    .infographic-card small {
        display: block;
        color: var(--muted);
        font-size: 0.7rem;
        line-height: 1.25;
        margin-top: 0.26rem;
    }
    .glofas-status-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(155px, 1fr));
        gap: 0.65rem;
        margin: 0.4rem 0 0.75rem;
    }
    .glofas-card {
        border: 1px solid var(--line);
        border-radius: 8px;
        background:
            linear-gradient(180deg, rgba(255,255,255,0.99), rgba(248,251,255,0.98)),
            linear-gradient(135deg, rgba(220,38,38,0.09), rgba(245,158,11,0.09), rgba(37,99,235,0.08));
        padding: 0.7rem 0.78rem;
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
    }
    .glofas-card span {
        display: block;
        color: var(--muted);
        font-size: 0.67rem;
        text-transform: uppercase;
        font-weight: 700;
        margin-bottom: 0.18rem;
    }
    .glofas-card b {
        color: var(--text);
        font-size: 1.04rem;
        line-height: 1.2;
    }
    .api-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 0.65rem;
        margin: 0.75rem 0 1rem;
    }
    .api-card {
        border: 1px solid var(--line);
        background: #ffffff;
        border-radius: 8px;
        padding: 0.7rem 0.78rem;
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
    }
    .api-card b {
        display: block;
        font-size: 0.82rem;
        color: var(--text);
        margin-bottom: 0.28rem;
    }
    .api-card code {
        display: block;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        font-size: 0.72rem;
        color: #0f766e;
    }
    [data-testid="stTabs"] {
        background: #ffffff;
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 0.55rem;
        box-shadow: 0 16px 34px rgba(15, 23, 42, 0.05);
    }
    div[data-testid="stExpander"] {
        border: 1px solid var(--line);
        border-radius: 8px;
        background: #ffffff;
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.04);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

components.html(
    """
    <script>
    (() => {
        const collapseSidebar = () => {
            try {
                const doc = window.parent.document;
                const sidebar = doc.querySelector('[data-testid="stSidebar"]');
                if (!sidebar || sidebar.getAttribute("aria-expanded") !== "true") return;
                const buttons = Array.from(doc.querySelectorAll("button"));
                const collapseButton = buttons.find((button) => {
                    const testId = button.getAttribute("data-testid") || "";
                    const label = button.getAttribute("aria-label") || "";
                    const text = button.innerText || "";
                    return testId.includes("CollapseSidebar")
                        || label.toLowerCase().includes("collapse")
                        || text.includes("keyboard_double_arrow_left");
                });
                if (collapseButton) collapseButton.click();
            } catch (error) {
                // Parent access can be blocked in some Streamlit hosts; page_config still sets the default.
            }
        };
        collapseSidebar();
        window.setTimeout(collapseSidebar, 250);
        window.setTimeout(collapseSidebar, 900);
    })();
    </script>
    """,
    height=0,
)


def parsed_directories() -> list[Path]:
    return sorted(
        [
            path
            for path in APP_DIR.iterdir()
            if path.is_dir()
            and (path / "report_meta.json").exists()
            and (path / "river_water_level_observations.csv").exists()
        ],
        key=lambda path: path.name,
    )


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_json_url(url: str) -> tuple[dict | list | None, str | None]:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "mpwrd-vbsr-dashboard/1.0"})
        with urllib.request.urlopen(request, timeout=18) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.URLError as exc:
        try:
            result = subprocess.run(
                ["curl.exe", "-s", "--max-time", "18", url],
                capture_output=True,
                check=True,
                text=True,
                timeout=22,
            )
            if not result.stdout.strip():
                return None, f"Unable to reach weather API: {exc}"
            return json.loads(result.stdout), None
        except Exception:
            return None, f"Unable to reach weather API: {exc}"
    except Exception as exc:
        return None, f"Unable to read weather API response: {exc}"


def normalize_name(value: str | float | None) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    for word in ["project", "major", "medium", "dam", "tank", "sagar", "reservoir"]:
        text = re.sub(rf"\b{word}\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def best_match_name(source_name: str, candidates: list[str]) -> tuple[str | None, float]:
    source_norm = normalize_name(source_name)
    if not source_norm:
        return None, 0.0
    candidate_lookup = {candidate: normalize_name(candidate) for candidate in candidates}
    for candidate, candidate_norm in candidate_lookup.items():
        if source_norm == candidate_norm:
            return candidate, 1.0
    substring_matches = []
    source_tokens = set(source_norm.split())
    for candidate, candidate_norm in candidate_lookup.items():
        if source_norm and candidate_norm and (source_norm in candidate_norm or candidate_norm in source_norm):
            candidate_tokens = set(candidate_norm.split())
            token_overlap = len(source_tokens & candidate_tokens)
            length_score = min(len(source_norm), len(candidate_norm)) / max(len(source_norm), len(candidate_norm))
            substring_matches.append((candidate, 0.92, token_overlap, length_score, len(candidate_norm)))
    if substring_matches:
        return max(substring_matches, key=lambda item: (item[2], item[3], item[4]))[:2]
    scored = [
        (candidate, SequenceMatcher(None, source_norm, candidate_norm).ratio())
        for candidate, candidate_norm in candidate_lookup.items()
    ]
    if not scored:
        return None, 0.0
    return max(scored, key=lambda item: item[1])


@st.cache_data(show_spinner=False)
def load_dam_locations(locations_csv_path: str, shapefile_path: str) -> pd.DataFrame:
    csv_path = Path(locations_csv_path)
    if csv_path.exists():
        return pd.read_csv(csv_path)

    path = Path(shapefile_path)
    if not path.exists():
        return pd.DataFrame()
    import geopandas as gpd

    gdf = gpd.read_file(path)
    if "Lat" in gdf.columns and "Long" in gdf.columns:
        gdf["latitude"] = pd.to_numeric(gdf["Lat"], errors="coerce")
        gdf["longitude"] = pd.to_numeric(gdf["Long"], errors="coerce")
    else:
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)
        points = gdf.to_crs(epsg=4326).geometry.centroid
        gdf["latitude"] = points.y
        gdf["longitude"] = points.x

    columns = [
        column
        for column in ["DamName", "SUB_NAME", "MAJ_NAME", "dist_nm_e", "latitude", "longitude", "Water_Leve", "Filled"]
        if column in gdf.columns
    ]
    dams = pd.DataFrame(gdf[columns]).dropna(subset=["latitude", "longitude"])
    dams = dams.rename(
        columns={
            "DamName": "dam_name",
            "SUB_NAME": "sub_basin",
            "MAJ_NAME": "major_basin",
            "dist_nm_e": "map_district",
            "Water_Leve": "map_water_level_m",
            "Filled": "map_filled_percent",
        }
    )
    dams["dam_name"] = dams["dam_name"].astype(str)
    dams["map_district"] = dams.get("map_district", "").astype(str)
    dams["sub_basin"] = dams.get("sub_basin", "").astype(str)
    dams["major_basin"] = dams.get("major_basin", "").astype(str)
    return dams


def attach_dam_locations(dams: pd.DataFrame, reservoir_names: list[str]) -> pd.DataFrame:
    if dams.empty or not reservoir_names:
        return dams
    rows = []
    for row in dams.to_dict("records"):
        matched, score = best_match_name(row.get("dam_name", ""), reservoir_names)
        row["reservoir_name"] = matched
        row["match_score"] = score
        rows.append(row)
    return pd.DataFrame(rows)


def load_dataset(parsed_dir: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = pd.read_json(parsed_dir / "report_meta.json", typ="series").to_dict()
    river_master = read_csv(parsed_dir / "river_gauge_stations.csv")
    reservoir_master = read_csv(parsed_dir / "reservoirs.csv")
    rivers = read_csv(parsed_dir / "river_water_level_observations.csv")
    reservoirs = read_csv(parsed_dir / "reservoir_status_observations.csv")
    gates = read_csv(parsed_dir / "reservoir_gate_observations.csv")
    for frame in [rivers, reservoirs, gates]:
        if "observed_at" in frame:
            frame["observed_at"] = pd.to_datetime(frame["observed_at"], errors="coerce")
    if river_master.empty and not rivers.empty:
        river_master = rivers[
            ["river_name", "gauge_station", "district", "danger_or_max_water_level_m"]
        ].drop_duplicates()
    if reservoir_master.empty and not reservoirs.empty:
        reservoir_master = reservoirs[
            ["reservoir_name", "district", "lsl_m", "frl_m", "live_capacity_frl_mcm"]
        ].drop_duplicates()
    return meta, river_master, reservoir_master, rivers, reservoirs, gates


def report_datetime(meta: dict) -> pd.Timestamp:
    return pd.to_datetime(
        f"{meta.get('report_date', '')} {meta.get('report_time', '')}",
        errors="coerce",
    )


def add_report_context(frame: pd.DataFrame, meta: dict, report_id: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["report_id"] = report_id
    frame["report_at"] = report_datetime(meta)
    frame["report_date"] = meta.get("report_date")
    frame["report_time"] = meta.get("report_time")
    frame["source_filename"] = meta.get("source_filename", report_id)
    return frame


def load_time_series(parsed_paths: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta_rows = []
    river_master_rows = []
    reservoir_master_rows = []
    river_rows = []
    reservoir_rows = []
    gate_rows = []

    for parsed_path in parsed_paths:
        meta, river_master, reservoir_master, rivers, reservoirs, gates = load_dataset(parsed_path)
        report_id = parsed_path.name
        meta_rows.append(
            {
                "report_id": report_id,
                "report_at": report_datetime(meta),
                "report_date": meta.get("report_date"),
                "report_time": meta.get("report_time"),
                "source_filename": meta.get("source_filename", report_id),
                "extraction_method": meta.get("extraction_method", "-"),
            }
        )
        river_master_rows.append(add_report_context(river_master, meta, report_id))
        reservoir_master_rows.append(add_report_context(reservoir_master, meta, report_id))
        river_rows.append(add_report_context(rivers, meta, report_id))
        reservoir_rows.append(add_report_context(reservoirs, meta, report_id))
        gate_frame = add_report_context(gates, meta, report_id)
        if not gate_frame.empty:
            gate_frame["gate_opened_at"] = pd.to_datetime(
                gate_frame["gate_opening_date"].fillna("").astype(str)
                + " "
                + gate_frame["gate_opening_time"].fillna("").astype(str),
                errors="coerce",
            )
        gate_rows.append(gate_frame)

    meta_df = pd.DataFrame(meta_rows).sort_values("report_at")
    river_master_df = pd.concat(river_master_rows, ignore_index=True) if river_master_rows else pd.DataFrame()
    reservoir_master_df = pd.concat(reservoir_master_rows, ignore_index=True) if reservoir_master_rows else pd.DataFrame()
    rivers_df = pd.concat(river_rows, ignore_index=True) if river_rows else pd.DataFrame()
    reservoirs_df = pd.concat(reservoir_rows, ignore_index=True) if reservoir_rows else pd.DataFrame()
    gates_df = pd.concat(gate_rows, ignore_index=True) if gate_rows else pd.DataFrame()

    if not river_master_df.empty:
        river_master_df = river_master_df.drop_duplicates(["river_name", "gauge_station", "district"])
    if not reservoir_master_df.empty:
        reservoir_master_df = reservoir_master_df.drop_duplicates(["reservoir_name", "district"])
    return meta_df, river_master_df, reservoir_master_df, rivers_df, reservoirs_df, gates_df


def latest_by_asset(frame: pd.DataFrame, asset_col: str) -> pd.DataFrame:
    if frame.empty or "observed_at" not in frame:
        return frame
    ordered = frame.sort_values("observed_at")
    return ordered.groupby([asset_col, "district"], as_index=False).tail(1)


def fmt_number(value: float | int | None, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "-"
    if isinstance(value, float) and abs(value) < 100:
        return f"{value:,.2f}{suffix}"
    return f"{value:,.0f}{suffix}"


def time_label(value) -> str:
    if pd.isna(value):
        return "-"
    return pd.Timestamp(value).strftime("%d %b %Y %I:%M %p")


def return_period_label(value: float | int | None) -> str:
    rp = float(value or 0)
    if rp >= 50:
        return "Exceeds 50 yr"
    if rp >= 25:
        return "Exceeds 25 yr"
    if rp >= 10:
        return "Exceeds 10 yr"
    if rp >= 2:
        return "Exceeds 2 yr"
    return "Normal"


def risk_color(risk: str) -> str:
    return {
        "Danger": "#dc2626",
        "Flood": "#f97316",
        "Watch": "#f59e0b",
        "Normal": "#2563eb",
    }.get(str(risk), "#2563eb")


def build_mp_glofas_nodes(map_frame: pd.DataFrame, reservoir_frame: pd.DataFrame, forecast_days: int = 10) -> list[dict]:
    if map_frame.empty:
        return []

    work = map_frame.copy()
    work["glofas_basin"] = (
        work.get("sub_basin", pd.Series(index=work.index, dtype=object))
        .fillna(work.get("major_basin", pd.Series(index=work.index, dtype=object)))
        .fillna("Madhya Pradesh")
        .astype(str)
        .replace("", "Madhya Pradesh")
    )
    nodes = []
    latest_date = pd.Timestamp.utcnow().normalize()
    if not reservoir_frame.empty and "observed_at" in reservoir_frame:
        observed = pd.to_datetime(reservoir_frame["observed_at"], errors="coerce").dropna()
        if not observed.empty:
            latest_date = observed.max().normalize()

    for basin, group in work.groupby("glofas_basin"):
        located = group.dropna(subset=["latitude", "longitude"])
        if located.empty:
            continue
        representative = located.sort_values("display_filling", ascending=False).iloc[0]
        dam_count = int(group["dam_name"].nunique()) if "dam_name" in group else len(group)
        avg_filling = float(pd.to_numeric(group.get("display_filling"), errors="coerce").mean() or 0)
        avg_rain = float(pd.to_numeric(group.get("rainfall_daily_mm"), errors="coerce").fillna(0).mean() or 0)
        storage = float(pd.to_numeric(group.get("current_live_capacity_mcm"), errors="coerce").fillna(0).sum() or 0)
        base_flow = max(35.0, dam_count * 18.0 + avg_filling * 2.2 + avg_rain * 8.0)
        storage_factor = min(0.28, storage / 9000.0)
        watch = max(100.0, base_flow * 1.45)
        flood = watch * 1.28
        danger = flood * 1.32

        series = []
        for offset in range(10, 0, -1):
            day = latest_date - pd.Timedelta(days=offset)
            rainfall_shape = max(0.0, avg_rain * (0.45 + 0.08 * math.sin(offset)))
            flow = base_flow * (0.75 + 0.04 * math.cos(offset / 2.0)) + rainfall_shape * 3.5
            series.append(
                {
                    "date": day.date().isoformat(),
                    "period": "hindcast",
                    "chirps_hindcast_cms": round(flow, 3),
                    "glofas_p10_cms": None,
                    "glofas_p50_cms": round(flow * 1.04, 3),
                    "glofas_p90_cms": None,
                    "reservoir_attenuated_cms": round(flow * (1.0 - storage_factor), 3),
                    "return_period": max(0.0, flow / max(watch, 1.0) * 1.8),
                }
            )

        last_flow = series[-1]["glofas_p50_cms"] if series else base_flow
        for step in range(1, forecast_days + 1):
            event_shape = math.exp(-((step - 4.0) ** 2) / 8.0)
            p50 = base_flow * 0.95 + last_flow * (0.72**step) * 0.35 + (avg_rain + avg_filling / 18.0) * 7.0 * event_shape
            p10 = p50 * 0.72
            p90 = p50 * 1.42
            rp = 1.0
            if p90 >= danger:
                rp = 25.0
            elif p90 >= flood:
                rp = 10.0
            elif p90 >= watch:
                rp = 2.0
            series.append(
                {
                    "date": (latest_date + pd.Timedelta(days=step)).date().isoformat(),
                    "period": "forecast",
                    "chirps_hindcast_cms": None,
                    "glofas_p10_cms": round(p10, 3),
                    "glofas_p50_cms": round(p50, 3),
                    "glofas_p90_cms": round(p90, 3),
                    "reservoir_attenuated_cms": round(p50 * (1.0 - storage_factor), 3),
                    "return_period": rp,
                }
            )

        max_forecast = max(float(row.get("glofas_p90_cms") or row.get("glofas_p50_cms") or 0.0) for row in series)
        if max_forecast >= danger:
            risk = "Danger"
        elif max_forecast >= flood:
            risk = "Flood"
        elif max_forecast >= watch:
            risk = "Watch"
        else:
            risk = "Normal"
        nodes.append(
            {
                "name": f"{basin} basin GloFAS node",
                "basin": basin,
                "latitude": float(representative["latitude"]),
                "longitude": float(representative["longitude"]),
                "dam_count": dam_count,
                "avg_filling": round(avg_filling, 2),
                "storage_mcm": round(storage, 2),
                "forecast_days": forecast_days,
                "risk_band": risk,
                "source_status": "fallback_until_copernicus_api_configured",
                "thresholds": {
                    "watch_cms": round(watch, 3),
                    "flood_cms": round(flood, 3),
                    "danger_cms": round(danger, 3),
                },
                "series": series,
            }
        )
    return sorted(nodes, key=lambda item: (item["risk_band"] != "Danger", item["risk_band"] != "Flood", item["basin"]))


def build_mp_grrr_nodes(map_frame: pd.DataFrame, reservoir_frame: pd.DataFrame, forecast_days: int = 7) -> list[dict]:
    if map_frame.empty:
        return []

    work = map_frame.copy()
    work["grrr_basin"] = (
        work.get("sub_basin", pd.Series(index=work.index, dtype=object))
        .fillna(work.get("major_basin", pd.Series(index=work.index, dtype=object)))
        .fillna("Madhya Pradesh")
        .astype(str)
        .replace("", "Madhya Pradesh")
    )
    latest_date = pd.Timestamp.utcnow().normalize()
    if not reservoir_frame.empty and "observed_at" in reservoir_frame:
        observed = pd.to_datetime(reservoir_frame["observed_at"], errors="coerce").dropna()
        if not observed.empty:
            latest_date = observed.max().normalize()

    nodes = []
    for basin, group in work.groupby("grrr_basin"):
        located = group.dropna(subset=["latitude", "longitude"])
        if located.empty:
            continue
        representative = located.sort_values("display_filling", ascending=False).iloc[0]
        dam_count = int(group["dam_name"].nunique()) if "dam_name" in group else len(group)
        avg_filling = float(pd.to_numeric(group.get("display_filling"), errors="coerce").mean() or 0)
        avg_rain = float(pd.to_numeric(group.get("rainfall_daily_mm"), errors="coerce").fillna(0).mean() or 0)
        storage = float(pd.to_numeric(group.get("current_live_capacity_mcm"), errors="coerce").fillna(0).sum() or 0)
        catchment_proxy = max(80.0, dam_count * 125.0 + storage * 0.18)
        runoff_base = max(0.4, avg_rain * 0.38 + avg_filling / 130.0)
        attenuation = min(0.35, storage / 8500.0)
        watch = max(18.0, runoff_base * 2.1 + dam_count * 0.55)
        flood = watch * 1.45
        danger = flood * 1.35
        rows = []

        for offset in range(10, 0, -1):
            day = latest_date - pd.Timedelta(days=offset)
            runoff = runoff_base * (0.72 + 0.06 * math.cos(offset / 2.0))
            discharge = runoff * catchment_proxy * 0.0116
            rows.append(
                {
                    "date": day.date().isoformat(),
                    "period": "reanalysis",
                    "runoff_mm": round(runoff, 3),
                    "reanalysis_discharge_cms": round(discharge, 3),
                    "reforecast_p50_cms": None,
                    "reforecast_p90_cms": None,
                    "reservoir_adjusted_cms": round(discharge * (1.0 - attenuation), 3),
                }
            )

        last_discharge = rows[-1]["reanalysis_discharge_cms"] if rows else runoff_base * catchment_proxy * 0.0116
        for step in range(1, forecast_days + 1):
            pulse = math.exp(-((step - 3.0) ** 2) / 5.0)
            runoff = runoff_base * (0.95 + 0.16 * pulse + 0.025 * step)
            p50 = max(1.0, last_discharge * (0.68**step) * 0.42 + runoff * catchment_proxy * 0.0128)
            p90 = p50 * 1.55
            rows.append(
                {
                    "date": (latest_date + pd.Timedelta(days=step)).date().isoformat(),
                    "period": "reforecast",
                    "runoff_mm": round(runoff, 3),
                    "reanalysis_discharge_cms": None,
                    "reforecast_p50_cms": round(p50, 3),
                    "reforecast_p90_cms": round(p90, 3),
                    "reservoir_adjusted_cms": round(p50 * (1.0 - attenuation), 3),
                }
            )

        peak = max(float(row.get("reforecast_p90_cms") or row.get("reanalysis_discharge_cms") or 0.0) for row in rows)
        if peak >= danger:
            risk = "Danger"
        elif peak >= flood:
            risk = "Flood"
        elif peak >= watch:
            risk = "Watch"
        else:
            risk = "Normal"
        nodes.append(
            {
                "name": f"{basin} GRRR runoff node",
                "basin": basin,
                "latitude": float(representative["latitude"]),
                "longitude": float(representative["longitude"]),
                "dam_count": dam_count,
                "avg_rainfall_mm": round(avg_rain, 2),
                "catchment_proxy_sq_km": round(catchment_proxy, 2),
                "risk_band": risk,
                "source_status": "grrr_ready_fallback_until_notebook_export_or_api_configured",
                "thresholds": {
                    "watch_cms": round(watch, 3),
                    "flood_cms": round(flood, 3),
                    "danger_cms": round(danger, 3),
                },
                "series": rows,
            }
        )
    return sorted(nodes, key=lambda item: (item["risk_band"] != "Danger", item["risk_band"] != "Flood", item["basin"]))


def fetch_dynamic_nodes(endpoint: str, kind: str) -> tuple[list[dict], str | None]:
    url = str(endpoint or "").strip()
    if not url:
        return [], "endpoint_not_configured"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return [], f"{kind} endpoint failed: {exc}"

    if isinstance(payload, list):
        raw_nodes = payload
    elif isinstance(payload, dict):
        raw_nodes = (
            payload.get("nodes")
            or payload.get("features")
            or payload.get("data")
            or payload.get(f"{kind.lower()}_nodes")
            or []
        )
    else:
        raw_nodes = []

    nodes = []
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            continue
        props = raw.get("properties") if isinstance(raw.get("properties"), dict) else raw
        geometry = raw.get("geometry") if isinstance(raw.get("geometry"), dict) else {}
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        lon = props.get("longitude") or props.get("lon")
        lat = props.get("latitude") or props.get("lat")
        if isinstance(coordinates, list):
            if geometry.get("type") == "Point" and len(coordinates) >= 2:
                lon = lon or coordinates[0]
                lat = lat or coordinates[1]
            elif coordinates and isinstance(coordinates[0], list):
                first = coordinates[0][0] if coordinates[0] and isinstance(coordinates[0][0], list) else coordinates[0]
                if isinstance(first, list) and len(first) >= 2:
                    lon = lon or first[0]
                    lat = lat or first[1]
        series = props.get("series") or props.get("forecast") or props.get("timeseries") or props.get("rows") or []
        thresholds = props.get("thresholds") or {
            "watch_cms": props.get("watch_cms") or props.get("watch"),
            "flood_cms": props.get("flood_cms") or props.get("flood"),
            "danger_cms": props.get("danger_cms") or props.get("danger"),
        }
        nodes.append(
            {
                "name": props.get("name") or props.get("station_name") or props.get("basin") or f"{kind} node {index + 1}",
                "basin": props.get("basin") or props.get("sub_basin") or props.get("river_name") or "Dynamic",
                "latitude": float(lat) if lat not in (None, "") else None,
                "longitude": float(lon) if lon not in (None, "") else None,
                "dam_count": int(float(props.get("dam_count") or 0)),
                "avg_filling": float(props.get("avg_filling") or props.get("filling_percent") or 0),
                "avg_rainfall_mm": float(props.get("avg_rainfall_mm") or props.get("rainfall_mm") or 0),
                "storage_mcm": float(props.get("storage_mcm") or props.get("storage") or 0),
                "catchment_proxy_sq_km": float(props.get("catchment_proxy_sq_km") or props.get("catchment_sq_km") or 0),
                "forecast_days": int(float(props.get("forecast_days") or 0)),
                "risk_band": props.get("risk_band") or props.get("risk") or "Normal",
                "source_status": props.get("source_status") or "dynamic_endpoint",
                "thresholds": thresholds,
                "series": series if isinstance(series, list) else [],
            }
        )
    return nodes, None


RESERVOIR_METRICS = {
    "Filling %": ("filling_percent", "%"),
    "Water Level": ("water_level_m", "m"),
    "Current Storage": ("current_live_capacity_mcm", "MCM"),
    "Daily Rainfall": ("rainfall_daily_mm", "mm"),
    "FRL Gap": ("frl_gap_m", "m"),
}

RIVER_METRICS = {
    "Water Level": ("water_level_m", "m"),
    "Danger Gap": ("danger_gap_m", "m"),
}


def api_is_available(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url, timeout=1.2) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def clean_json_value(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def render_arcgis_dam_timeseries_map(map_frame: pd.DataFrame, reservoir_frame: pd.DataFrame, latest_label: str) -> None:
    feature_columns = [
        "dam_name",
        "reservoir_name",
        "map_district",
        "sub_basin",
        "major_basin",
        "observed_at",
        "water_level_m",
        "frl_m",
        "frl_gap_m",
        "display_filling",
        "current_live_capacity_mcm",
        "rainfall_daily_mm",
        "alert_level",
    ]
    features = []
    for index, row in map_frame.dropna(subset=["latitude", "longitude"]).reset_index(drop=True).iterrows():
        attributes = {"objectid": int(index) + 1}
        for column in feature_columns:
            attributes[column] = clean_json_value(row.get(column))
        features.append(
            {
                "longitude": float(row["longitude"]),
                "latitude": float(row["latitude"]),
                "attributes": attributes,
            }
        )

    history = {}
    if not reservoir_frame.empty:
        history_columns = [
            "reservoir_name",
            "observed_at",
            "water_level_m",
            "filling_percent",
            "frl_gap_m",
            "current_live_capacity_mcm",
            "rainfall_daily_mm",
        ]
        available_columns = [column for column in history_columns if column in reservoir_frame.columns]
        for reservoir_name, group in reservoir_frame[available_columns].sort_values("observed_at").groupby("reservoir_name"):
            history[str(reservoir_name)] = [
                {column: clean_json_value(value) for column, value in record.items()}
                for record in group.tail(12).to_dict("records")
            ]

    features_json = json.dumps(features, ensure_ascii=False).replace("</", "<\\/")
    history_json = json.dumps(history, ensure_ascii=False).replace("</", "<\\/")
    dss_nodes = {"glofas": [], "grrr": []}
    for key, path in [("glofas", GLOFAS_PROJECT_JSON), ("grrr", GRRR_PROJECT_JSON)]:
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                nodes = payload.get("nodes", []) if isinstance(payload, dict) else payload
                if isinstance(nodes, list):
                    dss_nodes[key] = nodes
            except (OSError, json.JSONDecodeError):
                dss_nodes[key] = []
    dss_nodes_json = json.dumps(dss_nodes, ensure_ascii=False).replace("</", "<\\/")
    geoglows_url = json.dumps(GEOGLOWS_MEDIUM_URL)

    components.html(
        f"""
        <link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/light/main.css">
        <style>
            body {{
                margin: 0;
                background: transparent;
                font-family: Roboto, Inter, Segoe UI, Arial, sans-serif;
            }}
            .map-frame {{
                position: relative;
                width: 100%;
                min-height: 520px;
                border: 1px solid #d9d4ef;
                border-radius: 8px;
                overflow: hidden;
                background: #eef6ff;
            }}
            #damMap {{
                height: 520px;
                width: 100%;
            }}
            .latest-badge {{
                position: absolute;
                left: 14px;
                bottom: 14px;
                z-index: 5;
                border: 1px solid rgba(217, 212, 239, 0.95);
                border-radius: 6px;
                background: rgba(255, 255, 255, 0.94);
                color: #172033;
                padding: 8px 10px;
                font-size: 12px;
                box-shadow: 0 10px 22px rgba(15, 23, 42, 0.12);
            }}
            .hover-card {{
                position: absolute;
                right: 14px;
                top: 14px;
                z-index: 6;
                min-width: 220px;
                max-width: 280px;
                border: 1px solid rgba(217, 212, 239, 0.95);
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.96);
                padding: 10px 12px;
                box-shadow: 0 16px 34px rgba(15, 23, 42, 0.13);
                display: none;
                pointer-events: none;
            }}
            .hover-card strong {{
                display: block;
                color: #0f172a;
                font-size: 13px;
                margin-bottom: 6px;
            }}
            .hover-card dl {{
                margin: 0;
                display: grid;
                gap: 4px;
            }}
            .hover-card div {{
                display: flex;
                justify-content: space-between;
                gap: 14px;
                color: #64748b;
                font-size: 11px;
            }}
            .hover-card dd {{
                margin: 0;
                color: #0f172a;
                font-weight: 700;
                text-align: right;
            }}
            .popup-title {{
                font-weight: 700;
                color: #172033;
                margin-bottom: 6px;
            }}
            .popup-meta {{
                color: #475569;
                font-size: 12px;
                line-height: 1.4;
                margin-bottom: 8px;
            }}
            .alert-chip {{
                display: inline-block;
                margin: 5px 0 8px;
                padding: 4px 8px;
                border-radius: 999px;
                color: #fff;
                font-size: 11px;
                font-weight: 700;
            }}
            .popup-chart {{
                width: 100%;
                min-width: 260px;
                margin-top: 4px;
            }}
            .chart-label {{
                color: #64748b;
                font-size: 11px;
                margin-top: 4px;
            }}
            .geoglows-panel {{
                margin-top: 8px;
                border: 1px solid #d9d4ef;
                border-radius: 8px;
                background: linear-gradient(180deg, #ffffff, #f8fbff);
                padding: 8px 10px 10px;
                box-shadow: 0 14px 28px rgba(15, 23, 42, 0.07);
            }}
            .geoglows-head {{
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 12px;
                margin-bottom: 8px;
            }}
            .geoglows-head span {{
                color: #7c5cff;
                display: block;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }}
            .geoglows-head strong {{
                color: #0f172a;
                display: block;
                font-size: 13px;
                line-height: 1.2;
                margin-top: 2px;
            }}
            .geoglows-head small {{
                color: #64748b;
                display: block;
                font-size: 11px;
                margin-top: 3px;
            }}
            .geoglows-grid {{
                display: grid;
                grid-template-columns: minmax(420px, 1.35fr) minmax(260px, 0.65fr);
                gap: 10px;
                align-items: stretch;
            }}
            .geoglows-chart {{
                min-height: 230px;
                border-radius: 8px;
                border: 1px solid #e5eaf3;
                background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
                overflow: hidden;
            }}
            .geoglows-table {{
                max-height: 230px;
                overflow: auto;
                border: 1px solid #e5eaf3;
                border-radius: 8px;
                background: #fff;
            }}
            .geoglows-table table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 11px;
            }}
            .geoglows-table th,
            .geoglows-table td {{
                padding: 7px 8px;
                border-bottom: 1px solid #edf2f7;
                text-align: left;
            }}
            .geoglows-table th {{
                color: #64748b;
                font-size: 10px;
                text-transform: uppercase;
                background: #f8fafc;
                position: sticky;
                top: 0;
            }}
            .dss-link-panel {{
                margin-top: 10px;
                border: 1px solid #c7d2fe;
                border-radius: 8px;
                background:
                    linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,251,255,0.98)),
                    linear-gradient(135deg, rgba(37,99,235,0.10), rgba(20,184,166,0.08));
                padding: 10px;
                box-shadow: 0 12px 26px rgba(15, 23, 42, 0.06);
            }}
            .dss-link-head {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                margin-bottom: 8px;
            }}
            .dss-link-head span {{
                color: #2563eb;
                display: block;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }}
            .dss-link-head strong {{
                color: #0f172a;
                display: block;
                font-size: 12px;
                margin-top: 2px;
            }}
            .dss-card-grid {{
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr)) minmax(260px, 1.05fr);
                gap: 8px;
                align-items: stretch;
            }}
            .dss-card {{
                border: 1px solid #e5eaf3;
                border-radius: 8px;
                background: #ffffff;
                min-height: 92px;
                padding: 9px 10px;
            }}
            .dss-card span {{
                color: #64748b;
                display: block;
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 0.06em;
                text-transform: uppercase;
            }}
            .dss-card strong {{
                color: #0f172a;
                display: block;
                font-size: 12px;
                line-height: 1.2;
                margin: 3px 0 5px;
            }}
            .dss-card small {{
                color: #475569;
                display: block;
                font-size: 10.5px;
                line-height: 1.35;
            }}
            .zoom-level-control {{
                width: 46px;
                max-height: 250px;
                overflow: auto;
                border-radius: 4px;
                background: rgba(255, 255, 255, 0.96);
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.16);
            }}
            .zoom-level-control button {{
                display: block;
                width: 100%;
                height: 24px;
                border: 0;
                border-bottom: 1px solid #e5e7eb;
                background: #ffffff;
                color: #0f172a;
                font: 700 11px/1 Roboto, Inter, Segoe UI, sans-serif;
                cursor: pointer;
            }}
            .zoom-level-control button:hover,
            .zoom-level-control button.is-active {{
                background: #2563eb;
                color: #ffffff;
            }}
            .hand-card {{
                border-color: #bfdbfe;
                background:
                    linear-gradient(180deg, rgba(255,255,255,0.99), rgba(239,246,255,0.98)),
                    linear-gradient(135deg, rgba(14,165,233,0.10), rgba(37,99,235,0.08), rgba(20,184,166,0.08));
            }}
            .hand-card strong {{
                margin-bottom: 7px;
            }}
            .hand-controls {{
                display: grid;
                grid-template-columns: minmax(110px, 1fr) minmax(96px, 0.75fr) minmax(96px, 0.75fr);
                gap: 6px;
                align-items: end;
            }}
            .hand-controls label {{
                display: grid;
                gap: 3px;
                color: #64748b;
                font-size: 9px;
                font-weight: 800;
                text-transform: uppercase;
            }}
            .hand-controls input,
            .hand-controls select {{
                width: 100%;
                box-sizing: border-box;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background: #ffffff;
                color: #0f172a;
                font: 700 11px/1.2 Roboto, Inter, Segoe UI, sans-serif;
                padding: 7px 8px;
            }}
            .hand-controls button {{
                grid-column: 1 / -1;
                border: 0;
                border-radius: 6px;
                background: #2563eb;
                color: #ffffff;
                cursor: pointer;
                font: 700 12px/1 Roboto, Inter, Segoe UI, sans-serif;
                padding: 9px 12px;
                min-height: 32px;
            }}
            .hand-controls button:hover {{
                background: #1d4ed8;
            }}
            .hand-status {{
                color: #475569;
                font-size: 10.5px;
                margin-top: 6px;
                line-height: 1.4;
            }}
            @media (max-width: 760px) {{
                .geoglows-grid {{
                    grid-template-columns: 1fr;
                }}
                .dss-card-grid {{
                    grid-template-columns: 1fr;
                }}
                .hand-controls {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
        <div class="map-frame">
            <div id="damMap"></div>
            <div id="hoverCard" class="hover-card"></div>
            <div class="latest-badge">Dynamic dam status linked to latest observation: {escape(latest_label)}</div>
        </div>
        <div class="geoglows-panel">
            <div class="geoglows-head">
                <div>
                    <span>GEOGLOWS Forecast at Selected Point</span>
                    <strong id="geoglowsTitle">Click a dam point to compare river forecast with dam water level</strong>
                    <small id="geoglowsStatus">Nearest GEOGLOWS reach and forecast table will load here.</small>
                </div>
            </div>
            <div class="geoglows-grid">
                <div id="geoglowsChart" class="geoglows-chart"></div>
                <div class="geoglows-table">
                    <table>
                        <thead><tr><th>Forecast Time</th><th>Mean Flow</th><th>Return Period</th></tr></thead>
                        <tbody id="geoglowsBody"><tr><td colspan="3">No GEOGLOWS reach selected.</td></tr></tbody>
                    </table>
                </div>
            </div>
        </div>
        <div class="dss-link-panel">
            <div class="dss-link-head">
                <div>
                    <span>GD Site Forecast Linkage</span>
                    <strong id="dssLinkTitle">Click a GD site, dam, GEOGLOWS stream, or map point to build linked DSS context.</strong>
                </div>
            </div>
            <div id="dssLinkCards" class="dss-card-grid">
                <div id="dssGeoglowsCard" class="dss-card"><span>GEOGLOWS</span><strong>Waiting for selection</strong><small>Nearest stream reach will drive downstream DSS context.</small></div>
                <div id="dssGlofasCard" class="dss-card"><span>GloFAS</span><strong>Waiting for selection</strong><small>Nearest project forecast node will be linked by location.</small></div>
                <div id="dssGrrrCard" class="dss-card"><span>GRRR</span><strong>Waiting for selection</strong><small>Nearest runoff reanalysis/reforecast node will be linked by location.</small></div>
                <div class="dss-card hand-card">
                    <span>HAND Scenario</span>
                    <strong id="handTitle">Inundation screening from selected GEOGLOWS reach</strong>
                    <div class="hand-controls">
                        <label>COMID
                            <input id="handComid" type="text" placeholder="Select site or enter COMID">
                        </label>
                        <label>Return
                            <select id="handReturnPeriod">
                                <option value="2">2 yr</option>
                                <option value="5">5 yr</option>
                                <option value="10" selected>10 yr</option>
                                <option value="25">25 yr</option>
                                <option value="50">50 yr</option>
                                <option value="100">100 yr</option>
                            </select>
                        </label>
                        <label>Stage
                            <select id="handStage">
                                <option value="1.0">1.0 m</option>
                                <option value="2.0">2.0 m</option>
                                <option value="3.5" selected>3.5 m</option>
                                <option value="5.0">5.0 m</option>
                                <option value="7.0">7.0 m</option>
                            </select>
                        </label>
                        <button id="handGenerate" type="button">Generate HAND Layer</button>
                    </div>
                    <div id="handNote" class="hand-status">Select a GD site, dam, stream, or enter COMID.</div>
                </div>
            </div>
        </div>
        <script src="https://js.arcgis.com/4.30/"></script>
        <script>
            const damFeatures = {features_json};
            const damHistory = {history_json};
            const dssForecastNodes = {dss_nodes_json};
            const geoglowsServiceUrl = {geoglows_url};
            let geoglowsTimeExtent = null;
            let geoglowsRequestId = 0;
            const alertColors = {{
                Critical: [239, 68, 68, 0.92],
                Warning: [245, 158, 11, 0.9],
                Watch: [250, 204, 21, 0.88],
                Normal: [37, 99, 235, 0.82]
            }};

            function fmt(value, suffix = "") {{
                if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
                const numberValue = Number(value);
                return `${{numberValue.toFixed(Math.abs(numberValue) < 100 ? 2 : 0)}}${{suffix}}`;
            }}

            function fmtDate(value) {{
                if (!value) return "-";
                const d = new Date(value);
                if (Number.isNaN(d.getTime())) return value;
                return d.toLocaleString("en-IN", {{ day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }});
            }}

            function geoglowsDate(value) {{
                const time = Number(value);
                if (!Number.isFinite(time)) return "-";
                return new Date(time).toLocaleString("en-IN", {{
                    day: "2-digit",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit"
                }});
            }}

            function escapeHtml(value) {{
                return String(value ?? "-")
                    .replaceAll("&", "&amp;")
                    .replaceAll("<", "&lt;")
                    .replaceAll(">", "&gt;")
                    .replaceAll('"', "&quot;")
                    .replaceAll("'", "&#039;");
            }}

            function alertColor(level) {{
                return {{
                    Critical: "#ef4444",
                    Warning: "#f59e0b",
                    Watch: "#eab308",
                    Normal: "#2563eb"
                }}[level || "Normal"] || "#2563eb";
            }}

            function returnPeriodLabel(value) {{
                const rp = Number(value) || 0;
                if (rp >= 50) return "Exceeds 50 yr";
                if (rp >= 25) return "Exceeds 25 yr";
                if (rp >= 10) return "Exceeds 10 yr";
                if (rp >= 2) return "Exceeds 2 yr";
                return "Normal";
            }}

            function returnPeriodColor(value) {{
                const rp = Number(value) || 0;
                if (rp >= 50) return "#ba25f5";
                if (rp >= 25) return "#fa4343";
                if (rp >= 10) return "#ff813d";
                if (rp >= 2) return "#f5d140";
                return "#4baecc";
            }}

            function haversineKm(lat1, lon1, lat2, lon2) {{
                const toRad = (value) => Number(value) * Math.PI / 180;
                const aLat = Number(lat1);
                const aLon = Number(lon1);
                const bLat = Number(lat2);
                const bLon = Number(lon2);
                if (![aLat, aLon, bLat, bLon].every(Number.isFinite)) return Infinity;
                const dLat = toRad(bLat - aLat);
                const dLon = toRad(bLon - aLon);
                const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLon / 2) ** 2;
                return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
            }}

            function nearestForecastNode(nodes, latitude, longitude) {{
                return (nodes || [])
                    .filter((node) => Number.isFinite(Number(node.latitude)) && Number.isFinite(Number(node.longitude)))
                    .map((node) => ({{ ...node, distance_km: haversineKm(latitude, longitude, node.latitude, node.longitude) }}))
                    .sort((a, b) => a.distance_km - b.distance_km)[0] || null;
            }}

            function latestNodeFlow(node, keys) {{
                const rows = Array.isArray(node?.series) ? node.series : [];
                for (let index = rows.length - 1; index >= 0; index -= 1) {{
                    for (const key of keys) {{
                        const value = Number(rows[index]?.[key]);
                        if (Number.isFinite(value)) return value;
                    }}
                }}
                return null;
            }}

            function dssCard(id, type, title, lines, color = "#2563eb") {{
                return `
                    <div id="${{id}}" class="dss-card">
                        <span style="color:${{color}}">${{type}}</span>
                        <strong>${{escapeHtml(title || "Not linked")}}</strong>
                        <small>${{lines.map(escapeHtml).join("<br>")}}</small>
                    </div>
                `;
            }}

            function replaceDssCard(id, html) {{
                const current = document.getElementById(id);
                if (current) current.outerHTML = html;
            }}

            function renderDssLinkage(context) {{
                const title = document.getElementById("dssLinkTitle");
                if (title) title.textContent = context?.label || "Linked forecast DSS context";
                if (context?.loading) {{
                    replaceDssCard("dssGeoglowsCard", dssCard("dssGeoglowsCard", "GEOGLOWS", "Loading nearest reach", ["Querying live medium-flow service..."]));
                    replaceDssCard("dssGlofasCard", dssCard("dssGlofasCard", "GloFAS", "Preparing linkage", ["Nearest project forecast node will be matched."]));
                    replaceDssCard("dssGrrrCard", dssCard("dssGrrrCard", "GRRR", "Preparing linkage", ["Nearest runoff node will be matched."]));
                    return;
                }}
                const lat = Number(context?.latitude);
                const lon = Number(context?.longitude);
                const attrs = context?.feature?.properties || context?.feature?.attributes || {{}};
                const glofasNode = nearestForecastNode(dssForecastNodes.glofas, lat, lon);
                const grrrNode = nearestForecastNode(dssForecastNodes.grrr, lat, lon);
                const geoglowsLines = attrs.comid
                    ? [
                        `COMID ${{attrs.comid}} | Stream order ${{attrs.streamorder ?? "n/a"}}`,
                        `${{fmt(attrs.meanflow, " cumecs")}} mean flow | ${{returnPeriodLabel(attrs.returnperiod)}}`
                    ]
                    : [context?.error || "No linked GEOGLOWS reach found near this selection."];
                const glofasFlow = latestNodeFlow(glofasNode, ["glofas_p50_cms", "reservoir_attenuated_cms", "chirps_hindcast_cms"]);
                const grrrFlow = latestNodeFlow(grrrNode, ["reforecast_p50_cms", "reservoir_adjusted_cms", "reanalysis_discharge_cms"]);
                replaceDssCard(
                    "dssGeoglowsCard",
                    dssCard("dssGeoglowsCard", "GEOGLOWS", attrs.comid ? "Live river forecast reach" : "No reach linked", geoglowsLines, returnPeriodColor(attrs.returnperiod))
                );
                replaceDssCard(
                    "dssGlofasCard",
                    dssCard(
                        "dssGlofasCard",
                        "GloFAS",
                        glofasNode?.name || "No GloFAS node",
                        glofasNode ? [
                            `${{glofasNode.basin || "Project basin"}} | ${{fmt(glofasNode.distance_km, " km away")}}`,
                            `Risk ${{glofasNode.risk_band || "Normal"}} | Flow ${{fmt(glofasFlow, " cumecs")}}`
                        ] : ["Project GloFAS JSON has no node with coordinates."],
                        "#7c3aed"
                    )
                );
                replaceDssCard(
                    "dssGrrrCard",
                    dssCard(
                        "dssGrrrCard",
                        "GRRR",
                        grrrNode?.name || "No GRRR node",
                        grrrNode ? [
                            `${{grrrNode.basin || "Project basin"}} | ${{fmt(grrrNode.distance_km, " km away")}}`,
                            `Risk ${{grrrNode.risk_band || "Normal"}} | Runoff flow ${{fmt(grrrFlow, " cumecs")}}`
                        ] : ["Project GRRR JSON has no node with coordinates."],
                        "#0f766e"
                    )
                );
            }}

            async function fetchJson(url) {{
                const response = await fetch(url);
                if (!response.ok) throw new Error(`ArcGIS request failed (${{response.status}})`);
                const data = await response.json();
                if (data?.error) throw new Error(data.error.message || "ArcGIS service returned an error");
                return data;
            }}

            async function getGeoglowsTimeExtent() {{
                if (Array.isArray(geoglowsTimeExtent)) return geoglowsTimeExtent;
                const service = await fetchJson(`${{geoglowsServiceUrl}}?f=json`);
                const extent = Array.isArray(service?.timeInfo?.timeExtent) ? service.timeInfo.timeExtent.map(Number) : null;
                geoglowsTimeExtent = extent?.every(Number.isFinite) ? extent : null;
                return geoglowsTimeExtent;
            }}

            async function queryGeoglowsNearby(latitude, longitude, distance = 50000) {{
                const timeExtent = await getGeoglowsTimeExtent().catch(() => null);
                const latestTime = Number(timeExtent?.[1]);
                const params = new URLSearchParams({{
                    f: "geojson",
                    where: "rivercountry = 'India' OR outletcountry = 'India'",
                    geometry: `${{longitude}},${{latitude}}`,
                    geometryType: "esriGeometryPoint",
                    inSR: "4326",
                    spatialRel: "esriSpatialRelIntersects",
                    distance: String(distance),
                    units: "esriSRUnit_Meter",
                    outFields: "comid,meanflow,returnperiod,timevalue,streamorder,rivercountry,outletcountry",
                    returnGeometry: "true",
                    outSR: "4326",
                    orderByFields: "streamorder desc,meanflow desc,timevalue asc",
                    resultRecordCount: "12"
                }});
                if (Number.isFinite(latestTime)) params.set("time", `${{latestTime}},${{latestTime}}`);
                const data = await fetchJson(`${{geoglowsServiceUrl}}/0/query?${{params.toString()}}`);
                return (data?.features || [])[0] || null;
            }}

            async function queryGeoglowsSeries(comid) {{
                if (!comid) return [];
                const timeExtent = await getGeoglowsTimeExtent().catch(() => null);
                const params = new URLSearchParams({{
                    f: "json",
                    where: `comid = ${{Number(comid)}}`,
                    outFields: "comid,meanflow,returnperiod,timevalue,streamorder,rivercountry,outletcountry",
                    returnGeometry: "false",
                    orderByFields: "timevalue asc",
                    resultRecordCount: "500"
                }});
                if (Array.isArray(timeExtent)) params.set("time", `${{timeExtent[0]}},${{timeExtent[1]}}`);
                const data = await fetchJson(`${{geoglowsServiceUrl}}/0/query?${{params.toString()}}`);
                return (data?.features || []).map((feature) => feature.attributes || {{}});
            }}

            async function queryGeoglowsFeatureByComid(comid) {{
                const numericComid = Number(String(comid || "").trim());
                if (!Number.isFinite(numericComid)) return null;
                const timeExtent = await getGeoglowsTimeExtent().catch(() => null);
                const latestTime = Number(timeExtent?.[1]);
                const params = new URLSearchParams({{
                    f: "geojson",
                    where: `comid = ${{numericComid}}`,
                    outFields: "comid,meanflow,returnperiod,timevalue,streamorder,rivercountry,outletcountry",
                    returnGeometry: "true",
                    outSR: "4326",
                    resultRecordCount: "1"
                }});
                if (Number.isFinite(latestTime)) params.set("time", `${{latestTime}},${{latestTime}}`);
                const data = await fetchJson(`${{geoglowsServiceUrl}}/0/query?${{params.toString()}}`);
                return (data?.features || [])[0] || null;
            }}

            function handDistanceMeters(returnPeriod, handStage) {{
                const rp = Number(returnPeriod) || 10;
                const stage = Number(handStage) || 3.5;
                const rpFactor = {{
                    2: 70,
                    5: 105,
                    10: 145,
                    25: 210,
                    50: 280,
                    100: 360
                }}[rp] || 145;
                return Math.max(60, Math.round(rpFactor + stage * 42));
            }}

            function updateHandNote(message, tone = "normal") {{
                const note = document.getElementById("handNote");
                if (!note) return;
                note.textContent = message;
                note.style.color = tone === "error" ? "#dc2626" : tone === "success" ? "#0f766e" : "#475569";
            }}

            function geoglowsChartSvg(rows) {{
                const cleanRows = rows.filter((row) => Number.isFinite(Number(row.meanflow)));
                if (!cleanRows.length) {{
                    return `<div class="chart-label" style="padding:16px">No forecast graph available.</div>`;
                }}
                const width = 720;
                const height = 230;
                const padLeft = 58;
                const padRight = 30;
                const padTop = 38;
                const padBottom = 42;
                const values = cleanRows.map((row) => Number(row.meanflow));
                const rps = cleanRows.map((row) => Number(row.returnperiod) || 0);
                const rawMin = Math.min(...values);
                const rawMax = Math.max(...values);
                const spread = Math.max(1, rawMax - rawMin);
                const min = Math.max(0, Math.floor(rawMin - spread * 0.18));
                const max = Math.ceil(rawMax + spread * 0.22);
                const rpMax = Math.max(2, ...rps);
                const chartWidth = width - padLeft - padRight;
                const chartHeight = height - padTop - padBottom;
                const x = (index) => padLeft + (cleanRows.length === 1 ? 0 : index * chartWidth / (cleanRows.length - 1));
                const y = (value) => padTop + (1 - ((value - min) / Math.max(0.001, max - min))) * chartHeight;
                const yRp = (value) => padTop + (1 - (value / Math.max(1, rpMax))) * chartHeight;
                const flowPoints = cleanRows.map((row, index) => `${{x(index).toFixed(1)}},${{y(Number(row.meanflow)).toFixed(1)}}`).join(" ");
                const rpPoints = cleanRows.map((row, index) => `${{x(index).toFixed(1)}},${{yRp(Number(row.returnperiod) || 0).toFixed(1)}}`).join(" ");
                const areaPath = `M ${{flowPoints.split(" ")[0]}} L ${{flowPoints}} L ${{x(cleanRows.length - 1).toFixed(1)}},${{(height - padBottom).toFixed(1)}} L ${{padLeft}},${{(height - padBottom).toFixed(1)}} Z`;
                const yTicks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => {{
                    const value = min + (max - min) * fraction;
                    const gy = y(value);
                    return `
                        <line x1="${{padLeft}}" x2="${{width - padRight}}" y1="${{gy.toFixed(1)}}" y2="${{gy.toFixed(1)}}" stroke="#e2e8f0" stroke-width="1" />
                        <text x="${{padLeft - 10}}" y="${{(gy + 3).toFixed(1)}}" fill="#64748b" font-size="10" text-anchor="end">${{Math.round(value)}}</text>
                    `;
                }}).join("");
                const markers = cleanRows.map((row, index) => {{
                    const rp = Number(row.returnperiod) || 0;
                    const color = returnPeriodColor(rp);
                    const radius = rp >= 10 ? 4.4 : rp >= 2 ? 3.8 : 3.2;
                    return `<circle cx="${{x(index).toFixed(1)}}" cy="${{y(Number(row.meanflow)).toFixed(1)}}" r="${{radius}}" fill="#ffffff" stroke="${{color}}" stroke-width="2"><title>${{geoglowsDate(row.timevalue)}} | ${{fmt(row.meanflow, " cumecs")}} | ${{returnPeriodLabel(rp)}}</title></circle>`;
                }}).join("");
                const latest = cleanRows[cleanRows.length - 1];
                const peak = cleanRows.reduce((best, row) => Number(row.meanflow) > Number(best.meanflow) ? row : best, cleanRows[0]);
                const latestText = `${{fmt(latest.meanflow, " cumecs")}} latest`;
                const peakText = `${{fmt(peak.meanflow, " cumecs")}} peak`;
                return `
                    <svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="${{height}}" role="img" aria-label="GEOGLOWS forecast graph">
                        <defs>
                            <linearGradient id="geoglowsFill" x1="0" x2="0" y1="0" y2="1">
                                <stop offset="0%" stop-color="#2563eb" stop-opacity="0.26" />
                                <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.03" />
                            </linearGradient>
                            <filter id="geoglowsShadow" x="-10%" y="-10%" width="120%" height="130%">
                                <feDropShadow dx="0" dy="5" stdDeviation="5" flood-color="#2563eb" flood-opacity="0.18"/>
                            </filter>
                        </defs>
                        <rect x="0" y="0" width="${{width}}" height="${{height}}" rx="8" fill="#ffffff" />
                        <rect x="${{padLeft}}" y="${{padTop}}" width="${{chartWidth}}" height="${{chartHeight}}" rx="6" fill="#f8fbff" />
                        ${{yTicks}}
                        <line x1="${{padLeft}}" x2="${{width - padRight}}" y1="${{height - padBottom}}" y2="${{height - padBottom}}" stroke="#94a3b8" stroke-width="1" />
                        <line x1="${{padLeft}}" x2="${{padLeft}}" y1="${{padTop}}" y2="${{height - padBottom}}" stroke="#94a3b8" stroke-width="1" />
                        <path d="${{areaPath}}" fill="url(#geoglowsFill)" />
                        <polyline fill="none" stroke="#2563eb" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" points="${{flowPoints}}" filter="url(#geoglowsShadow)" />
                        <polyline fill="none" stroke="#ef4444" stroke-width="1.7" stroke-dasharray="6 5" stroke-linejoin="round" stroke-linecap="round" points="${{rpPoints}}" opacity="0.82" />
                        ${{markers}}
                        <text x="${{padLeft}}" y="20" fill="#0f172a" font-size="12" font-weight="800">Mean flow forecast</text>
                        <text x="${{padLeft}}" y="34" fill="#64748b" font-size="10">cumecs | dynamic GEOGLOWS reach series</text>
                        <text x="${{width - padRight}}" y="20" fill="#ef4444" font-size="11" font-weight="800" text-anchor="end">Return period overlay</text>
                        <text x="${{width - padRight}}" y="34" fill="#64748b" font-size="10" text-anchor="end">${{returnPeriodLabel(latest.returnperiod)}}</text>
                        <rect x="${{padLeft + 8}}" y="${{padTop + 8}}" width="116" height="28" rx="14" fill="#eff6ff" stroke="#bfdbfe" />
                        <text x="${{padLeft + 66}}" y="${{padTop + 26}}" fill="#1d4ed8" font-size="11" font-weight="800" text-anchor="middle">${{latestText}}</text>
                        <rect x="${{padLeft + 132}}" y="${{padTop + 8}}" width="104" height="28" rx="14" fill="#fff7ed" stroke="#fed7aa" />
                        <text x="${{padLeft + 184}}" y="${{padTop + 26}}" fill="#c2410c" font-size="11" font-weight="800" text-anchor="middle">${{peakText}}</text>
                        <text x="${{padLeft}}" y="${{height - 12}}" fill="#64748b" font-size="10">${{geoglowsDate(cleanRows[0].timevalue)}}</text>
                        <text x="${{width - padRight}}" y="${{height - 12}}" fill="#64748b" font-size="10" text-anchor="end">${{geoglowsDate(cleanRows[cleanRows.length - 1].timevalue)}}</text>
                        <text transform="translate(14 ${{height / 2}}) rotate(-90)" fill="#64748b" font-size="10" text-anchor="middle">Mean flow (cumecs)</text>
                    </svg>
                `;
            }}

            function renderGeoglowsPanel(payload) {{
                const title = document.getElementById("geoglowsTitle");
                const status = document.getElementById("geoglowsStatus");
                const body = document.getElementById("geoglowsBody");
                const chart = document.getElementById("geoglowsChart");
                const attrs = payload?.feature?.properties || payload?.feature?.attributes || {{}};
                const rows = payload?.series || [];
                if (title) title.textContent = payload?.label || "GEOGLOWS forecast";
                if (status) {{
                    if (payload?.loading) status.textContent = "Finding nearest GEOGLOWS reach and forecast series...";
                    else if (payload?.error) status.textContent = payload.error;
                    else status.textContent = `COMID ${{attrs.comid || "n/a"}} | Stream order ${{attrs.streamorder ?? "n/a"}} | ${{returnPeriodLabel(attrs.returnperiod)}}`;
                }}
                if (chart) chart.innerHTML = payload?.loading ? `<div class="chart-label" style="padding:16px">Loading GEOGLOWS forecast...</div>` : geoglowsChartSvg(rows);
                if (!body) return;
                if (payload?.loading) {{
                    body.innerHTML = '<tr><td colspan="3">Loading GEOGLOWS forecast...</td></tr>';
                }} else if (!rows.length) {{
                    body.innerHTML = '<tr><td colspan="3">No GEOGLOWS forecast rows found near this point.</td></tr>';
                }} else {{
                    body.innerHTML = rows.slice(0, 14).map((row) => `
                        <tr>
                            <td>${{geoglowsDate(row.timevalue)}}</td>
                            <td>${{fmt(row.meanflow, " cumecs")}}</td>
                            <td><span style="color:${{returnPeriodColor(row.returnperiod)}};font-weight:700">${{returnPeriodLabel(row.returnperiod)}}</span></td>
                        </tr>
                    `).join("");
                }}
            }}

            async function loadGeoglowsForPoint(latitude, longitude, label = "Selected map point") {{
                const requestId = ++geoglowsRequestId;
                renderGeoglowsPanel({{ loading: true, label }});
                renderDssLinkage({{ loading: true, latitude, longitude, label }});
                try {{
                    let feature = await queryGeoglowsNearby(latitude, longitude, 50000);
                    if (!feature) feature = await queryGeoglowsNearby(latitude, longitude, 150000);
                    if (requestId !== geoglowsRequestId) return null;
                    const attrs = feature?.properties || feature?.attributes || {{}};
                    if (!attrs.comid) {{
                        const error = "No GEOGLOWS forecast reach found within 150 km of this point.";
                        renderGeoglowsPanel({{ label, error, series: [] }});
                        renderDssLinkage({{ label, latitude, longitude, error, series: [] }});
                        return null;
                    }}
                    const series = await queryGeoglowsSeries(attrs.comid);
                    if (requestId !== geoglowsRequestId) return null;
                    renderGeoglowsPanel({{ label, feature, series }});
                    renderDssLinkage({{ label, latitude, longitude, feature, series }});
                    return feature;
                }} catch (error) {{
                    if (requestId === geoglowsRequestId) {{
                        renderGeoglowsPanel({{ label, error: `GEOGLOWS query failed: ${{error.message}}`, series: [] }});
                        renderDssLinkage({{ label, latitude, longitude, error: `GEOGLOWS query failed: ${{error.message}}`, series: [] }});
                    }}
                    return null;
                }}
            }}

            function waterLevelChart(rows, attributes) {{
                const cleanRows = rows
                    .filter((row) => row.water_level_m !== null && row.water_level_m !== undefined)
                    .slice(-12);
                if (!cleanRows.length) {{
                    return `<div class="chart-label">Water level graph unavailable</div>`;
                }}
                const width = 310;
                const height = 126;
                const pad = 18;
                const frl = Number(attributes.frl_m);
                const waterValues = cleanRows.map((row) => Number(row.water_level_m));
                const referenceValues = [frl, frl - 0.5, frl - 1.5].filter((value) => Number.isFinite(value));
                const allValues = waterValues.concat(referenceValues);
                const min = Math.min(...allValues) - 0.25;
                const max = Math.max(...allValues) + 0.25;
                const x = (index) => pad + (cleanRows.length === 1 ? 0 : index * (width - pad * 2) / (cleanRows.length - 1));
                const y = (value) => height - pad - ((value - min) / Math.max(0.001, max - min)) * (height - pad * 2);
                const points = cleanRows.map((row, index) => `${{x(index).toFixed(1)}},${{y(Number(row.water_level_m)).toFixed(1)}}`).join(" ");
                const last = cleanRows[cleanRows.length - 1];
                const rules = Number.isFinite(frl) ? `
                    <line x1="${{pad}}" x2="${{width - pad}}" y1="${{y(frl).toFixed(1)}}" y2="${{y(frl).toFixed(1)}}" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4 3" />
                    <line x1="${{pad}}" x2="${{width - pad}}" y1="${{y(frl - 0.5).toFixed(1)}}" y2="${{y(frl - 0.5).toFixed(1)}}" stroke="#f97316" stroke-width="1" stroke-dasharray="3 3" />
                    <line x1="${{pad}}" x2="${{width - pad}}" y1="${{y(frl - 1.5).toFixed(1)}}" y2="${{y(frl - 1.5).toFixed(1)}}" stroke="#f59e0b" stroke-width="1" stroke-dasharray="3 3" />
                ` : "";
                return `
                    <div class="popup-chart">
                        <svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="${{height}}" role="img" aria-label="Reservoir water level graph">
                            <rect x="0" y="0" width="${{width}}" height="${{height}}" rx="8" fill="#f8fafc" />
                            ${{rules}}
                            <polyline fill="none" stroke="#2563eb" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" points="${{points}}" />
                            <circle cx="${{x(cleanRows.length - 1).toFixed(1)}}" cy="${{y(Number(last.water_level_m)).toFixed(1)}}" r="4.5" fill="${{alertColor(attributes.alert_level)}}" stroke="#fff" stroke-width="2" />
                            <text x="${{pad}}" y="${{height - 5}}" fill="#64748b" font-size="10">${{fmtDate(cleanRows[0].observed_at)}}</text>
                            <text x="${{width - pad}}" y="${{height - 5}}" fill="#64748b" font-size="10" text-anchor="end">${{fmtDate(last.observed_at)}}</text>
                            <text x="${{width - pad}}" y="14" fill="#ef4444" font-size="10" text-anchor="end">FRL alert bands</text>
                        </svg>
                        <div class="chart-label">Water level trend with FRL, warning and critical reference levels</div>
                    </div>
                `;
            }}

            function popupHtml(attributes) {{
                const name = attributes.reservoir_name || attributes.dam_name || "Dam";
                const rows = damHistory[name] || [];
                const basin = attributes.sub_basin || attributes.major_basin || "-";
                const district = attributes.district || attributes.map_district || "-";
                const alert = attributes.alert_level || "Normal";
                return `
                    <div class="popup-title">${{escapeHtml(name)}}</div>
                    <div class="popup-meta">
                        Current water level: <b>${{fmt(attributes.water_level_m, " m")}}</b><br>
                        Basin: <b>${{escapeHtml(basin)}}</b><br>
                        District: <b>${{escapeHtml(district)}}</b>
                    </div>
                    <span class="alert-chip" style="background:${{alertColor(alert)}}">${{escapeHtml(alert)}} alert</span>
                    ${{waterLevelChart(rows, attributes)}}
                `;
            }}

            require([
                "esri/config",
                "esri/WebMap",
                "esri/views/SceneView",
                "esri/layers/GraphicsLayer",
                "esri/layers/MapImageLayer",
                "esri/layers/TileLayer",
                "esri/widgets/LayerList",
                "esri/widgets/BasemapGallery",
                "esri/widgets/Expand",
                "esri/widgets/Home",
                "esri/geometry/Extent",
                "esri/geometry/Polyline",
                "esri/geometry/Polygon",
                "esri/geometry/geometryEngine",
                "esri/Graphic"
            ], function(esriConfig, WebMap, SceneView, GraphicsLayer, MapImageLayer, TileLayer, LayerList, BasemapGallery, Expand, Home, Extent, Polyline, Polygon, geometryEngine, Graphic) {{
                esriConfig.portalUrl = "{ARCGIS_PORTAL_URL}";
                const webmap = new WebMap({{
                    portalItem: {{ id: "{ARCGIS_EMBED_ITEM_ID}" }},
                    ground: "world-elevation"
                }});
                const mpExtent = new Extent({{
                    xmin: 74.029052,
                    ymin: 21.0707762,
                    xmax: 82.8066027,
                    ymax: 26.8683691,
                    spatialReference: {{ wkid: 4326 }}
                }});
                const view = new SceneView({{
                    container: "damMap",
                    map: webmap,
                    center: [78.22922399768257, 23.48361289099537],
                    zoom: 7,
                    qualityProfile: "high",
                    viewingMode: "global",
                    camera: {{
                        position: {{ longitude: 78.22922399768257, latitude: 23.48361289099537, z: 720000 }},
                        tilt: 42,
                        heading: 0
                    }},
                    environment: {{
                        atmosphereEnabled: true,
                        starsEnabled: false,
                        lighting: {{ directShadowsEnabled: true, ambientOcclusionEnabled: true }}
                    }},
                    popup: {{ dockEnabled: true, dockOptions: {{ position: "bottom-right", breakpoint: false }} }}
                }});
                const hillshadeLayer = new TileLayer({{
                    url: "https://services.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer",
                    title: "Esri World Hillshade",
                    opacity: 0.42,
                    visible: false
                }});
                const layer = new GraphicsLayer({{ title: "Latest dashboard dam status" }});
                const selectedGeoglowsLayer = new GraphicsLayer({{ title: "Selected GEOGLOWS reach" }});
                const handInundationLayer = new GraphicsLayer({{ title: "HAND inundation screening" }});
                const buildingRiskLayer = new GraphicsLayer({{
                    title: "OSM 3D building risk exposure",
                    elevationInfo: {{ mode: "on-the-ground" }}
                }});
                webmap.add(hillshadeLayer, 0);
                webmap.add(buildingRiskLayer);
                webmap.add(layer);
                webmap.add(selectedGeoglowsLayer);
                webmap.add(handInundationLayer);
                const geoglowsLayer = new MapImageLayer({{
                    url: geoglowsServiceUrl,
                    title: "GEOGLOWS medium flow forecast",
                    opacity: 0.72,
                    sublayers: [
                        {{
                            id: 0,
                            definitionExpression: "rivercountry = 'India' OR outletcountry = 'India'"
                        }}
                    ]
                }});
                webmap.add(geoglowsLayer);

                function makeSymbol(attributes, pulseOn = true) {{
                    const level = attributes.alert_level || "Normal";
                    const color = alertColors[level] || alertColors.Normal;
                    const size = Math.max(6, Math.min(13, 6 + Number(attributes.display_filling || 0) / 14));
                    const isAlert = level === "Critical" || level === "Warning";
                    return {{
                        type: "simple-marker",
                        style: "circle",
                        color,
                        size,
                        outline: {{
                            color: isAlert && pulseOn ? [255, 255, 255, 0.95] : [17, 24, 39, 0.45],
                            width: isAlert && pulseOn ? 3 : 1
                        }}
                    }};
                }}

                function buildingRiskColor(risk) {{
                    if (risk === "High") return [239, 68, 68, 0.86];
                    if (risk === "Moderate") return [245, 158, 11, 0.84];
                    return [20, 184, 166, 0.80];
                }}

                function damRiskScore(attributes) {{
                    const filling = Number(attributes.display_filling || 0);
                    const gap = Number(attributes.frl_gap_m);
                    const alert = attributes.alert_level || "Normal";
                    let score = filling;
                    if (alert === "Critical") score += 60;
                    if (alert === "Warning") score += 35;
                    if (alert === "Watch") score += 18;
                    if (Number.isFinite(gap)) score += Math.max(0, 12 - gap * 4);
                    return score;
                }}

                function buildingRiskForDam(attributes, distanceKm) {{
                    const alert = attributes.alert_level || "Normal";
                    const filling = Number(attributes.display_filling || 0);
                    if (alert === "Critical" || distanceKm <= 0.45 || filling >= 95) return "High";
                    if (alert === "Warning" || alert === "Watch" || distanceKm <= 1.1 || filling >= 85) return "Moderate";
                    return "Low";
                }}

                function parseOsmBuildingHeight(tags = {{}}) {{
                    const rawHeight = String(tags.height || tags["building:height"] || "").replace(",", ".").match(/[0-9.]+/);
                    if (rawHeight) return Math.max(3, Math.min(90, Number(rawHeight[0])));
                    const levels = Number(String(tags["building:levels"] || tags.levels || "").replace(",", "."));
                    if (Number.isFinite(levels) && levels > 0) return Math.max(3, Math.min(90, levels * 3.2));
                    return 10;
                }}

                async function addOsm3dBuildingsForDam(feature) {{
                    const attrs = feature.attributes || {{}};
                    const point = feature.geometry;
                    if (!point?.latitude || !point?.longitude) return;
                    const radiusMeters = Math.max(850, Math.min(2800, Math.round(850 + Number(attrs.display_filling || 0) * 18)));
                    const query = `[out:json][timeout:18];way["building"](around:${{radiusMeters}},${{point.latitude}},${{point.longitude}});out tags geom 70;`;
                    const endpoints = [
                        "https://overpass-api.de/api/interpreter?data=",
                        "https://overpass.kumi.systems/api/interpreter?data="
                    ];
                    let osm = null;
                    for (const endpoint of endpoints) {{
                        try {{
                            const response = await fetch(endpoint + encodeURIComponent(query));
                            if (response.ok) {{
                                osm = await response.json();
                                break;
                            }}
                        }} catch (error) {{
                            console.warn("OSM 3D building request failed", error);
                        }}
                    }}
                    if (!osm || !Array.isArray(osm.elements)) return;
                    osm.elements.slice(0, 70).forEach((element) => {{
                        if (!Array.isArray(element.geometry) || element.geometry.length < 4) return;
                        const ring = element.geometry.map((coord) => [coord.lon, coord.lat]);
                        const first = ring[0];
                        const last = ring[ring.length - 1];
                        if (first[0] !== last[0] || first[1] !== last[1]) ring.push(first);
                        const footprint = new Polygon({{
                            rings: [ring],
                            spatialReference: {{ wkid: 4326 }}
                        }});
                        const center = footprint.extent?.center;
                        const distanceKm = center
                            ? geometryEngine.distance(point, center, "kilometers")
                            : 0;
                        const risk = buildingRiskForDam(attrs, distanceKm || 0);
                        const height = parseOsmBuildingHeight(element.tags || {{}});
                        buildingRiskLayer.add(new Graphic({{
                            geometry: footprint,
                            attributes: {{
                                reservoir_name: attrs.reservoir_name || attrs.dam_name || "Dam",
                                district: attrs.map_district || "-",
                                risk,
                                distance_km: Number(distanceKm || 0).toFixed(2),
                                height_m: height.toFixed(1),
                                osm_id: element.id,
                                osm_building: (element.tags || {{}}).building || "yes",
                                source: "OpenStreetMap"
                            }},
                            symbol: {{
                                type: "polygon-3d",
                                symbolLayers: [{{
                                    type: "extrude",
                                    size: height,
                                    material: {{ color: buildingRiskColor(risk) }},
                                    edges: {{ type: "solid", color: [15, 23, 42, 0.42], size: 0.45 }}
                                }}]
                            }},
                            popupTemplate: {{
                                title: "3D Building Risk Exposure",
                                content: `
                                    <b>Nearest dam:</b> ${{escapeHtml(attrs.reservoir_name || attrs.dam_name || "Dam")}}<br>
                                    <b>Risk:</b> ${{risk}}<br>
                                    <b>Distance:</b> ${{Number(distanceKm || 0).toFixed(2)}} km<br>
                                    <b>Extruded height:</b> ${{height.toFixed(1)}} m<br>
                                    <b>OSM building:</b> ${{escapeHtml((element.tags || {{}}).building || "yes")}}<br>
                                    <span style="color:#64748b">Risk is screened from dam alert/filling and proximity. Replace with detailed flood depth rasters for engineering-grade exposure analysis.</span>
                                `
                            }}
                        }}));
                    }});
                }}

                async function loadOsm3dBuildingRiskLayer(graphics) {{
                    buildingRiskLayer.removeAll();
                    const priority = [...graphics]
                        .sort((a, b) => damRiskScore(b.attributes || {{}}) - damRiskScore(a.attributes || {{}}))
                        .slice(0, 6);
                    for (const graphic of priority) {{
                        await addOsm3dBuildingsForDam(graphic);
                    }}
                }}

                function addZoomLevelControl() {{
                    const container = document.createElement("div");
                    container.className = "zoom-level-control esri-widget";
                    const buttons = [];
                    for (let level = 0; level <= 16; level += 1) {{
                        const button = document.createElement("button");
                        button.type = "button";
                        button.textContent = String(level);
                        button.title = `Zoom level ${{level}}`;
                        button.setAttribute("aria-label", `Set map zoom level ${{level}}`);
                        button.addEventListener("click", () => {{
                            view.zoom = level;
                        }});
                        buttons.push(button);
                        container.appendChild(button);
                    }}
                    const sync = () => {{
                        const active = Math.round(Number(view.zoom) || 0);
                        buttons.forEach((button, index) => button.classList.toggle("is-active", index === active));
                    }};
                    view.watch("zoom", sync);
                    sync();
                    view.ui.add(container, "top-left");
                }}

                function trendForDam(name) {{
                    const rows = (damHistory[name] || [])
                        .filter((row) => Number.isFinite(Number(row.water_level_m)))
                        .sort((a, b) => String(a.observed_at).localeCompare(String(b.observed_at)));
                    if (rows.length < 2) return {{ label: "Insufficient data", delta: null, color: "#64748b" }};
                    const previous = Number(rows[rows.length - 2].water_level_m);
                    const current = Number(rows[rows.length - 1].water_level_m);
                    const delta = current - previous;
                    if (delta > 0.01) return {{ label: "Rising", delta, color: "#dc2626" }};
                    if (delta < -0.01) return {{ label: "Falling", delta, color: "#2563eb" }};
                    return {{ label: "Stable", delta, color: "#64748b" }};
                }}

                function hoverHtml(attributes) {{
                    const name = attributes.reservoir_name || attributes.dam_name || "Dam";
                    const trend = trendForDam(name);
                    const deltaText = trend.delta === null ? "" : ` (${{trend.delta > 0 ? "+" : ""}}${{fmt(trend.delta, " m")}})`;
                    return `
                        <strong>${{escapeHtml(name)}}</strong>
                        <dl>
                            <div><dt>Water Level</dt><dd>${{fmt(attributes.water_level_m, " m")}}</dd></div>
                            <div><dt>Alert</dt><dd style="color:${{alertColor(attributes.alert_level)}}">${{escapeHtml(attributes.alert_level || "Normal")}}</dd></div>
                            <div><dt>Filling</dt><dd>${{fmt(attributes.display_filling, "%")}}</dd></div>
                            <div><dt>Trend</dt><dd style="color:${{trend.color}}">${{trend.label}}${{deltaText}}</dd></div>
                        </dl>
                    `;
                }}

                function drawSelectedGeoglowsFeature(feature) {{
                    selectedGeoglowsLayer.removeAll();
                    if (!feature?.geometry) return;
                    const geometry = feature.geometry;
                    const attrs = feature.properties || feature.attributes || {{}};
                    let arcGeometry = null;
                    if (geometry.type === "LineString") {{
                        arcGeometry = {{
                            type: "polyline",
                            paths: [geometry.coordinates],
                            spatialReference: {{ wkid: 4326 }}
                        }};
                    }} else if (geometry.type === "MultiLineString") {{
                        arcGeometry = {{
                            type: "polyline",
                            paths: geometry.coordinates,
                            spatialReference: {{ wkid: 4326 }}
                        }};
                    }}
                    if (!arcGeometry) return;
                    selectedGeoglowsLayer.add(new Graphic({{
                        geometry: arcGeometry,
                        attributes: attrs,
                        symbol: {{
                            type: "simple-line",
                            color: returnPeriodColor(attrs.returnperiod),
                            width: 4.5,
                            style: "solid"
                        }}
                    }}));
                }}

                function geoglowsFeatureToPolyline(feature) {{
                    const geometry = feature?.geometry;
                    if (!geometry) return null;
                    if (geometry.type === "LineString") {{
                        return new Polyline({{
                            paths: [geometry.coordinates],
                            spatialReference: {{ wkid: 4326 }}
                        }});
                    }}
                    if (geometry.type === "MultiLineString") {{
                        return new Polyline({{
                            paths: geometry.coordinates,
                            spatialReference: {{ wkid: 4326 }}
                        }});
                    }}
                    return null;
                }}

                function handColor(returnPeriod) {{
                    const rp = Number(returnPeriod) || 10;
                    if (rp >= 100) return [124, 58, 237, 0.38];
                    if (rp >= 50) return [220, 38, 38, 0.34];
                    if (rp >= 25) return [249, 115, 22, 0.32];
                    if (rp >= 10) return [245, 158, 11, 0.30];
                    if (rp >= 5) return [14, 165, 233, 0.28];
                    return [37, 99, 235, 0.24];
                }}

                function drawHandInundation(feature, returnPeriod, stageMeters) {{
                    const attrs = feature?.properties || feature?.attributes || {{}};
                    const line = geoglowsFeatureToPolyline(feature);
                    if (!line) {{
                        updateHandNote("Selected GEOGLOWS feature does not include a line geometry for HAND screening.", "error");
                        return;
                    }}
                    const distance = handDistanceMeters(returnPeriod, stageMeters);
                    const inundation = geometryEngine.geodesicBuffer(line, distance, "meters");
                    handInundationLayer.removeAll();
                    handInundationLayer.add(new Graphic({{
                        geometry: inundation,
                        attributes: {{
                            comid: attrs.comid,
                            streamorder: attrs.streamorder,
                            return_period: returnPeriod,
                            hand_stage_m: stageMeters,
                            screening_width_m: distance,
                            model_note: "HAND screening buffer; replace with HAND raster threshold for production inundation."
                        }},
                        symbol: {{
                            type: "simple-fill",
                            color: handColor(returnPeriod),
                            outline: {{
                                color: [30, 64, 175, 0.86],
                                width: 1.2
                            }}
                        }},
                        popupTemplate: {{
                            title: "HAND screening inundation",
                            content: `
                                <b>GEOGLOWS COMID:</b> ${{escapeHtml(attrs.comid || "-")}}<br>
                                <b>Stream order:</b> ${{escapeHtml(attrs.streamorder ?? "-")}}<br>
                                <b>Return period:</b> ${{escapeHtml(returnPeriod)}} year<br>
                                <b>HAND stage:</b> ${{fmt(stageMeters, " m")}}<br>
                                <b>Screening width:</b> ${{fmt(distance, " m")}}<br>
                                <span style="color:#64748b">Screening layer only until a HAND raster is connected.</span>
                            `
                        }}
                    }}));
                    view.goTo(inundation.extent.expand(1.35)).catch(() => null);
                    updateHandNote(
                        `Generated HAND screening for COMID ${{attrs.comid || "selected stream"}} | return period ${{returnPeriod}} year | stage ${{stageMeters}} m | buffer ${{distance}} m.`,
                        "success"
                    );
                }}

                async function generateHandInundation() {{
                    const comidInput = document.getElementById("handComid");
                    const rpInput = document.getElementById("handReturnPeriod");
                    const stageInput = document.getElementById("handStage");
                    const comid = String(comidInput?.value || "").trim();
                    const returnPeriod = Number(rpInput?.value || 10);
                    const stageMeters = Number(stageInput?.value || 3.5);
                    updateHandNote("Generating HAND screening layer from GEOGLOWS stream geometry...");
                    try {{
                        let feature = null;
                        if (comid) feature = await queryGeoglowsFeatureByComid(comid);
                        if (!feature && selectedGeoglowsLayer.graphics.length) {{
                            const selected = selectedGeoglowsLayer.graphics.getItemAt(0);
                            feature = {{
                                type: "Feature",
                                geometry: {{
                                    type: "MultiLineString",
                                    coordinates: selected.geometry.paths
                                }},
                                properties: selected.attributes || {{}}
                            }};
                        }}
                        if (!feature) {{
                            updateHandNote("No GEOGLOWS stream selected. Click a dam/map point first or enter a valid COMID.", "error");
                            return;
                        }}
                        const attrs = feature.properties || feature.attributes || {{}};
                        if (comidInput && attrs.comid) comidInput.value = attrs.comid;
                        drawSelectedGeoglowsFeature(feature);
                        drawHandInundation(feature, returnPeriod, stageMeters);
                    }} catch (error) {{
                        updateHandNote(`HAND screening failed: ${{error.message}}`, "error");
                    }}
                }}

                async function selectGeoglows(latitude, longitude, label) {{
                    const feature = await loadGeoglowsForPoint(latitude, longitude, label);
                    drawSelectedGeoglowsFeature(feature);
                    const attrs = feature?.properties || feature?.attributes || {{}};
                    const handComid = document.getElementById("handComid");
                    if (handComid && attrs.comid) handComid.value = attrs.comid;
                }}

                const graphics = damFeatures.map((feature) => new Graphic({{
                    geometry: {{
                        type: "point",
                        longitude: feature.longitude,
                        latitude: feature.latitude
                    }},
                    attributes: feature.attributes,
                    symbol: makeSymbol(feature.attributes),
                    popupTemplate: {{
                        title: "{{reservoir_name}}",
                        content: (event) => {{
                            const wrapper = document.createElement("div");
                            wrapper.innerHTML = popupHtml(event.graphic.attributes);
                            return wrapper;
                        }}
                    }}
                }}));
                layer.addMany(graphics);
                if (graphics.length) {{
                    view.when(() => {{
                        view.goTo({{ center: [78.22922399768257, 23.48361289099537], zoom: 7 }}, {{ animate: false }}).catch(() => null);
                        loadOsm3dBuildingRiskLayer(graphics);
                        const layerList = new LayerList({{
                            view,
                            listItemCreatedFunction: (event) => {{
                                const item = event.item;
                                if (item.layer?.title === "Latest dashboard dam status") item.open = true;
                            }}
                        }});
                        const basemapGallery = new BasemapGallery({{
                            view,
                            source: {{
                                portal: {{
                                    url: "{ARCGIS_PORTAL_URL}"
                                }}
                            }}
                        }});
                        view.ui.add(new Home({{ view, viewpoint: {{ targetGeometry: mpExtent, scale: view.scale }} }}), "top-left");
                        addZoomLevelControl();
                        view.ui.add(new Expand({{
                            view,
                            content: layerList,
                            expandIcon: "layers",
                            expandTooltip: "Toggle map layers",
                            group: "top-right"
                        }}), "top-right");
                        view.ui.add(new Expand({{
                            view,
                            content: basemapGallery,
                            expandIcon: "basemap",
                            expandTooltip: "Select basemap",
                            group: "top-right"
                        }}), "top-right");
                        const handButton = document.getElementById("handGenerate");
                        if (handButton) handButton.addEventListener("click", generateHandInundation);
                    }});
                }}
                const hoverCard = document.getElementById("hoverCard");
                view.on("pointer-move", (event) => {{
                    view.hitTest(event).then((response) => {{
                        const hit = response.results.find((item) => item.graphic && item.graphic.layer === layer);
                        if (!hit) {{
                            if (hoverCard) hoverCard.style.display = "none";
                            return;
                        }}
                        if (hoverCard) {{
                            hoverCard.innerHTML = hoverHtml(hit.graphic.attributes);
                            hoverCard.style.display = "block";
                        }}
                    }}).catch(() => {{
                        if (hoverCard) hoverCard.style.display = "none";
                    }});
                }});
                view.on("click", (event) => {{
                    view.hitTest(event).then((response) => {{
                        const hit = response.results.find((item) => item.graphic && item.graphic.layer === layer);
                        if (hit) {{
                            const attrs = hit.graphic.attributes;
                            const point = hit.graphic.geometry;
                            const name = attrs.reservoir_name || attrs.dam_name || "Selected dam";
                            selectGeoglows(point.latitude, point.longitude, `${{name}} nearest GEOGLOWS reach`);
                        }} else {{
                            const linkedHit = response.results.find((item) => item.graphic && item.graphic.layer !== layer);
                            const linkedAttrs = linkedHit?.graphic?.attributes || {{}};
                            const layerTitle = linkedHit?.graphic?.layer?.title || "Map layer";
                            const siteName = linkedAttrs.name || linkedAttrs.Name || linkedAttrs.NAME || linkedAttrs.station_name || linkedAttrs.Station || linkedAttrs.site_name || linkedAttrs.Site_Name || linkedAttrs.gauge_station || linkedAttrs.Gauge || layerTitle;
                            const isGdLike = /gd|gauge|site|river|cwc|station/i.test(`${{layerTitle}} ${{siteName}}`);
                            const label = isGdLike ? `${{siteName}} GD/Gauge DSS linkage` : `${{siteName}} map DSS linkage`;
                            if (event.mapPoint) {{
                                selectGeoglows(event.mapPoint.latitude, event.mapPoint.longitude, label);
                            }}
                        }}
                    }}).catch(() => null);
                }});
                let pulseOn = true;
                window.setInterval(() => {{
                    pulseOn = !pulseOn;
                    graphics.forEach((graphic) => {{
                        if (["Critical", "Warning"].includes(graphic.attributes.alert_level)) {{
                            graphic.symbol = makeSymbol(graphic.attributes, pulseOn);
                        }}
                    }});
                }}, 850);
            }});
        </script>
        """,
        height=1040,
    )


def dam_status_geojson(frame: pd.DataFrame) -> dict:
    features = []
    if frame.empty:
        return {"type": "FeatureCollection", "features": features}

    export_columns = [
        "dam_name",
        "reservoir_name",
        "map_district",
        "sub_basin",
        "major_basin",
        "observed_at",
        "water_level_m",
        "frl_m",
        "frl_gap_m",
        "display_filling",
        "current_live_capacity_mcm",
        "rainfall_daily_mm",
        "alert_level",
    ]
    for row in frame.dropna(subset=["latitude", "longitude"]).to_dict("records"):
        properties = {}
        for column in export_columns:
            value = row.get(column)
            if pd.isna(value):
                value = None
            elif isinstance(value, pd.Timestamp):
                value = value.isoformat()
            properties[column] = value
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude"]), float(row["latitude"])],
                },
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def round_geojson_coordinates(value: object, places: int = 4) -> object:
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            return [round(float(item), places) if isinstance(item, (int, float)) else item for item in value]
        return [round_geojson_coordinates(item, places) for item in value]
    return value


@st.cache_data(show_spinner=False)
def load_light_district_geojson(path: str) -> dict:
    source = Path(path)
    if not source.exists():
        return {"type": "FeatureCollection", "features": []}
    data = json.loads(source.read_text(encoding="utf-8"))
    features = []
    for feature in data.get("features", []):
        props = feature.get("properties", {}) or {}
        geometry = feature.get("geometry") or {}
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "district": props.get("dist_nm_e") or props.get("district") or props.get("name") or "",
                    "area_sqkm": props.get("area_sqkm"),
                },
                "geometry": {
                    "type": geometry.get("type"),
                    "coordinates": round_geojson_coordinates(geometry.get("coordinates", []), places=4),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def geometry_coordinate_sample(geometry: dict) -> list[list[float]]:
    coords = geometry.get("coordinates", []) if geometry else []
    geom_type = geometry.get("type") if geometry else ""
    if geom_type == "LineString":
        return coords if isinstance(coords, list) else []
    if geom_type == "MultiLineString":
        points: list[list[float]] = []
        for part in coords if isinstance(coords, list) else []:
            if isinstance(part, list):
                points.extend(part)
        return points
    return []


@st.cache_data(show_spinner=False)
def load_light_drainage_geojson(path: str, dam_points_key: tuple[tuple[float, float], ...], max_features: int = 550) -> dict:
    source = Path(path)
    if not source.exists():
        return {"type": "FeatureCollection", "features": []}
    data = json.loads(source.read_text(encoding="utf-8"))
    dam_points = [(float(lon), float(lat)) for lon, lat in dam_points_key if pd.notna(lon) and pd.notna(lat)]
    if dam_points:
        min_lon = min(lon for lon, _ in dam_points) - 1.25
        max_lon = max(lon for lon, _ in dam_points) + 1.25
        min_lat = min(lat for _, lat in dam_points) - 1.25
        max_lat = max(lat for _, lat in dam_points) + 1.25
    else:
        min_lon, max_lon, min_lat, max_lat = 73.0, 83.5, 21.0, 27.0

    candidates = []
    for feature in data.get("features", []):
        geometry = feature.get("geometry") or {}
        points = geometry_coordinate_sample(geometry)
        if not points:
            continue
        in_box = any(
            isinstance(point, list)
            and len(point) >= 2
            and min_lon <= float(point[0]) <= max_lon
            and min_lat <= float(point[1]) <= max_lat
            for point in points[:: max(1, len(points) // 12)]
        )
        if not in_box:
            continue
        props = feature.get("properties", {}) or {}
        order_value = pd.to_numeric(pd.Series([props.get("ORD_STRA")]), errors="coerce").iloc[0]
        order_value = 1 if pd.isna(order_value) else int(order_value)
        length_value = pd.to_numeric(pd.Series([props.get("LENGTH_KM")]), errors="coerce").iloc[0]
        candidates.append(
            (
                order_value,
                0 if pd.isna(length_value) else float(length_value),
                {
                    "type": "Feature",
                    "properties": {
                        "ORD_STRA": order_value,
                        "ORD_CLAS": props.get("ORD_CLAS"),
                        "ORD_FLOW": props.get("ORD_FLOW"),
                        "HYRIV_ID": props.get("HYRIV_ID"),
                        "SUB_NAME": props.get("SUB_NAME") or "",
                        "MAJ_NAME": props.get("MAJ_NAME") or "",
                        "LENGTH_KM": props.get("LENGTH_KM"),
                        "DIS_AV_CMS": props.get("DIS_AV_CMS"),
                    },
                    "geometry": {
                        "type": geometry.get("type"),
                        "coordinates": round_geojson_coordinates(geometry.get("coordinates", []), places=4),
                    },
                },
            )
        )
    candidates = sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True)
    features = [item[2] for item in candidates[:max_features]]
    return {"type": "FeatureCollection", "features": features}


def render_infographic_leaflet_map(map_frame: pd.DataFrame, district_geojson: dict) -> None:
    if map_frame.empty or not {"latitude", "longitude"}.issubset(map_frame.columns):
        return

    alert_colors = {
        "Critical": "#ef4444",
        "Warning": "#f59e0b",
        "Watch": "#eab308",
        "Normal": "#2563eb",
    }
    records = []
    for row in map_frame.dropna(subset=["latitude", "longitude"]).to_dict("records"):
        area = pd.to_numeric(pd.Series([row.get("waterbody_area_sqkm")]), errors="coerce").iloc[0]
        filling = pd.to_numeric(pd.Series([row.get("display_filling")]), errors="coerce").iloc[0]
        water_level = pd.to_numeric(pd.Series([row.get("water_level_m")]), errors="coerce").iloc[0]
        frl_gap = pd.to_numeric(pd.Series([row.get("frl_gap_m")]), errors="coerce").iloc[0]
        alert_level = str(row.get("alert_level") or "Normal")
        records.append(
            {
                "dam_name": str(row.get("dam_name") or row.get("reservoir_name") or "Dam"),
                "reservoir_name": str(row.get("reservoir_name") or row.get("dam_name") or "Reservoir"),
                "district": str(row.get("district_label") or row.get("map_district") or row.get("district") or "Unassigned"),
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
                "alert": alert_level,
                "color": alert_colors.get(alert_level, "#2563eb"),
                "filling": None if pd.isna(filling) else round(float(filling), 2),
                "water_level": None if pd.isna(water_level) else round(float(water_level), 2),
                "frl_gap": None if pd.isna(frl_gap) else round(float(frl_gap), 2),
                "waterbody_area": 0 if pd.isna(area) else round(float(area), 3),
            }
        )
    if not records:
        return

    map_id = f"infographic-leaflet-{abs(hash(json.dumps(records[:5], sort_keys=True))) % 1000000}"
    records_json = json.dumps(records)
    districts_json = json.dumps(district_geojson)
    center_lat = sum(item["lat"] for item in records) / len(records)
    center_lon = sum(item["lon"] for item in records) / len(records)

    components.html(
        f"""
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            #{map_id} {{
                height: 300px;
                width: 100%;
                border: 1px solid #dbe6f4;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 14px 32px rgba(15,23,42,0.08);
                background: #eef6ff;
            }}
            .info-map-title {{
                font-family: Roboto, Inter, Segoe UI, sans-serif;
                font-size: 13px;
                font-weight: 800;
                color: #172033;
                margin: 0 0 6px;
            }}
            .info-map-note {{
                font-family: Roboto, Inter, Segoe UI, sans-serif;
                font-size: 11px;
                color: #64748b;
                margin: 0 0 8px;
            }}
            .leaflet-tooltip.district-label {{
                background: rgba(255,255,255,0.72);
                border: 0;
                box-shadow: none;
                color: #334155;
                font-size: 10px;
                font-weight: 700;
                padding: 1px 4px;
            }}
            .info-map-legend {{
                background: rgba(255,255,255,0.94);
                border: 1px solid #dbe6f4;
                border-radius: 8px;
                padding: 8px 10px;
                color: #334155;
                font: 11px Roboto, Inter, Segoe UI, sans-serif;
                line-height: 1.35;
                box-shadow: 0 8px 20px rgba(15,23,42,0.12);
            }}
            .info-map-legend b {{
                display: block;
                color: #172033;
                font-size: 11px;
                margin-bottom: 4px;
            }}
            .info-map-legend span {{
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                margin-right: 5px;
            }}
        </style>
        <div class="info-map-title">Infographic Map: Dams, Districts and Waterbody Footprint</div>
        <div class="info-map-note">Leaflet topographic basemap with MP district boundaries, dam FRL alerts, and waterbody-size circles.</div>
        <div id="{map_id}"></div>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
        (() => {{
            const dams = {records_json};
            const districts = {districts_json};
            const map = L.map("{map_id}", {{
                zoomControl: true,
                attributionControl: true,
                preferCanvas: true,
                scrollWheelZoom: false
            }}).setView([{center_lat:.5f}, {center_lon:.5f}], 7);
            L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
                maxZoom: 16,
                attribution: "Tiles &copy; Esri"
            }}).addTo(map);

            const districtLayer = L.geoJSON(districts, {{
                style: () => ({{
                    color: "#334155",
                    weight: 0.85,
                    opacity: 0.62,
                    fillColor: "#dbeafe",
                    fillOpacity: 0.08
                }}),
                onEachFeature: (feature, layer) => {{
                    const name = feature.properties?.district || "District";
                    layer.bindTooltip(name, {{ permanent: false, className: "district-label", sticky: true }});
                }}
            }}).addTo(map);

            const waterbodyLayer = L.layerGroup().addTo(map);
            const damLayer = L.layerGroup().addTo(map);
            dams.forEach((dam) => {{
                const area = Number(dam.waterbody_area || 0);
                const waterRadius = Math.max(1300, Math.min(17000, Math.sqrt(area) * 620));
                if (area > 0) {{
                    L.circle([dam.lat, dam.lon], {{
                        radius: waterRadius,
                        color: "#3160f7",
                        weight: 1,
                        opacity: 0.42,
                        fillColor: "#3160f7",
                        fillOpacity: 0.13
                    }}).addTo(waterbodyLayer);
                }}
                const marker = L.circleMarker([dam.lat, dam.lon], {{
                    radius: dam.alert === "Critical" ? 7 : dam.alert === "Warning" ? 6.5 : 5.4,
                    color: "#ffffff",
                    weight: 1.4,
                    fillColor: dam.color,
                    fillOpacity: 0.95
                }}).addTo(damLayer);
                marker.bindTooltip(`${{dam.reservoir_name}} | ${{dam.alert}}`, {{ sticky: true }});
                marker.bindPopup(`
                    <b>${{dam.reservoir_name}}</b><br/>
                    Dam: ${{dam.dam_name}}<br/>
                    District: ${{dam.district}}<br/>
                    Alert: <b style="color:${{dam.color}}">${{dam.alert}}</b><br/>
                    Filling: ${{dam.filling ?? "-"}}%<br/>
                    Water level: ${{dam.water_level ?? "-"}} m<br/>
                    FRL gap: ${{dam.frl_gap ?? "-"}} m<br/>
                    Waterbody: ${{dam.waterbody_area ?? 0}} sq.km
                `);
            }});

            const bounds = L.latLngBounds(dams.map((dam) => [dam.lat, dam.lon]));
            if (bounds.isValid()) map.fitBounds(bounds.pad(0.12), {{ maxZoom: 7 }});
            L.control.layers(null, {{
                "District boundary": districtLayer,
                "Waterbody footprint": waterbodyLayer,
                "Dam alert points": damLayer
            }}, {{ collapsed: true }}).addTo(map);
            const legend = L.control({{ position: "bottomright" }});
            legend.onAdd = () => {{
                const div = L.DomUtil.create("div", "info-map-legend");
                div.innerHTML = `
                    <b>FRL Alert</b>
                    <div><span style="background:#ef4444"></span>Critical</div>
                    <div><span style="background:#f59e0b"></span>Warning</div>
                    <div><span style="background:#eab308"></span>Watch</div>
                    <div><span style="background:#2563eb"></span>Normal</div>
                    <div style="margin-top:5px;color:#64748b">Blue rings show waterbody area</div>
                `;
                return div;
            }};
            legend.addTo(map);
            setTimeout(() => map.invalidateSize(), 350);
        }})();
        </script>
        """,
        height=470,
    )


def open_meteo_url(latitude: float, longitude: float, forecast_days: int = 7, past_days: int = 92) -> str:
    daily_vars = ",".join(
        [
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "precipitation_sum",
            "rain_sum",
            "showers_sum",
            "snowfall_sum",
            "wind_speed_10m_max",
            "uv_index_max",
        ]
    )
    hourly_vars = ",".join(["temperature_2m", "precipitation", "wind_speed_10m", "uv_index"])
    current_vars = ",".join(
        [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "rain",
            "showers",
            "weather_code",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        ]
    )
    return (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude:.5f}&longitude={longitude:.5f}"
        f"&daily={daily_vars}&hourly={hourly_vars}&current={current_vars}"
        "&timezone=Asia%2FKolkata"
        f"&forecast_days={forecast_days}&past_days={past_days}"
        "&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_open_meteo_weather(latitude: float, longitude: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str | None]:
    payload, error = fetch_json_url(open_meteo_url(latitude, longitude))
    if error or not isinstance(payload, dict):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), error or "Weather API returned an empty response."
    daily = pd.DataFrame(payload.get("daily") or {})
    hourly = pd.DataFrame(payload.get("hourly") or {})
    current = pd.DataFrame([payload.get("current") or {}])
    if not daily.empty and "time" in daily:
        daily["date"] = pd.to_datetime(daily["time"], errors="coerce")
        today = pd.Timestamp.now(tz="Asia/Kolkata").normalize().tz_localize(None)
        daily["period"] = daily["date"].apply(lambda value: "Forecast" if pd.notna(value) and value >= today else "Hindcast")
    if not hourly.empty and "time" in hourly:
        hourly["datetime"] = pd.to_datetime(hourly["time"], errors="coerce")
    if not current.empty and "time" in current:
        current["datetime"] = pd.to_datetime(current["time"], errors="coerce")
    for frame in [daily, hourly, current]:
        for column in frame.columns:
            if column not in {"time", "date", "datetime", "period"}:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return daily, hourly, current, None


def weather_risk_label(precipitation_mm: float | int | None, wind_kmh: float | int | None, uv_index: float | int | None) -> str:
    rain = 0 if precipitation_mm is None or pd.isna(precipitation_mm) else float(precipitation_mm)
    wind = 0 if wind_kmh is None or pd.isna(wind_kmh) else float(wind_kmh)
    uv = 0 if uv_index is None or pd.isna(uv_index) else float(uv_index)
    if rain >= 64.5 or wind >= 50 or uv >= 11:
        return "Severe"
    if rain >= 35.5 or wind >= 35 or uv >= 8:
        return "High"
    if rain >= 15.6 or wind >= 25 or uv >= 6:
        return "Moderate"
    return "Low"


def weather_risk_color(risk: str) -> str:
    return {"Severe": "#dc2626", "High": "#f97316", "Moderate": "#f59e0b", "Low": "#14b8a6"}.get(risk, "#2563eb")


def render_weather_town_leaflet_map(
    towns: pd.DataFrame,
    selected_town: str,
    weather_tile_api_key: str = "",
    district_geojson: dict | None = None,
) -> None:
    if towns.empty:
        return
    records = []
    for row in towns.dropna(subset=["latitude", "longitude"]).to_dict("records"):
        risk = str(row.get("weather_risk") or "Low")
        records.append(
            {
                "town": str(row.get("town_name") or "Town"),
                "district": str(row.get("district") or ""),
                "basin": str(row.get("basin") or ""),
                "priority": str(row.get("priority_flag") or ""),
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
                "risk": risk,
                "color": weather_risk_color(risk),
                "forecast_rain": round(float(row.get("forecast_rain_mm") or 0), 1),
                "max_temp": round(float(row.get("forecast_temp_max_c") or 0), 1),
                "max_wind": round(float(row.get("forecast_wind_max_kmh") or 0), 1),
                "max_uv": round(float(row.get("forecast_uv_max") or 0), 1),
                "selected": str(row.get("town_name") or "") == selected_town,
            }
        )
    map_id = f"weather-town-map-{abs(hash(selected_town)) % 1000000}"
    center = next((item for item in records if item["selected"]), records[0])
    tile_key = weather_tile_api_key.strip()
    districts_json = json.dumps(district_geojson or {"type": "FeatureCollection", "features": []})
    layer_note = (
        "Radar overlay is loaded from live radar tiles. Cloud and precipitation overlays require a configured weather-map API key."
        if not tile_key
        else "Satellite basemap, weather overlays, radar animation and MP administrative boundaries are enabled by default."
    )
    layer_badges_html = (
        """
        <span><i style="background:#0f172a"></i>Satellite default</span>
        <span><i style="background:#94a3b8"></i>Cloud cover default on</span>
        <span><i style="background:#2563eb"></i>Precipitation default on</span>
        <span><i style="background:#22c55e"></i>Radar default on</span>
        <span><i style="background:#111827"></i>MP admin boundary</span>
        """
        if tile_key
        else """
        <span><i style="background:#0f172a"></i>Satellite default</span>
        <span><i style="background:#ef4444"></i>Cloud/precip key missing online</span>
        <span><i style="background:#22c55e"></i>Radar default on</span>
        <span><i style="background:#111827"></i>MP admin boundary</span>
        """
    )
    components.html(
        f"""
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            #{map_id} {{
                height: 430px;
                width: 100%;
                border: 1px solid #dbe6f4;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 14px 32px rgba(15,23,42,0.08);
                background: #eef6ff;
            }}
            .weather-map-title {{
                font: 800 13px Roboto, Inter, Segoe UI, sans-serif;
                color: #172033;
                margin: 0 0 5px;
            }}
            .weather-map-note {{
                font: 11px Roboto, Inter, Segoe UI, sans-serif;
                color: #64748b;
                margin: 0 0 8px;
            }}
            .weather-layer-badges {{
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                margin: 0 0 8px;
            }}
            .weather-layer-badges span {{
                display: inline-flex;
                align-items: center;
                gap: 5px;
                border: 1px solid #dbe6f4;
                border-radius: 999px;
                background: rgba(255,255,255,0.92);
                color: #334155;
                font: 700 10px Roboto, Inter, Segoe UI, sans-serif;
                padding: 4px 8px;
                letter-spacing: 0.02em;
                text-transform: uppercase;
            }}
            .weather-layer-badges i {{
                width: 7px;
                height: 7px;
                border-radius: 999px;
                display: inline-block;
            }}
            .weather-legend {{
                background: rgba(255,255,255,0.94);
                border: 1px solid #dbe6f4;
                border-radius: 8px;
                padding: 8px 10px;
                color: #334155;
                font: 11px Roboto, Inter, Segoe UI, sans-serif;
                line-height: 1.35;
                box-shadow: 0 8px 20px rgba(15,23,42,0.12);
            }}
            .weather-legend b {{ display:block; color:#172033; margin-bottom:4px; }}
            .weather-legend span {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; }}
        </style>
        <div class="weather-map-title">Weather Forecast Map: MP Towns</div>
        <div class="weather-map-note">Town markers are colored by 7-day rainfall, wind and UV risk. {escape(layer_note)}</div>
        <div class="weather-layer-badges">
            {layer_badges_html}
        </div>
        <div id="{map_id}"></div>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
        (() => {{
            const towns = {json.dumps(records)};
            const districts = {districts_json};
            const weatherTileApiKey = {json.dumps(tile_key)};
            const map = L.map("{map_id}", {{ zoomControl: true, preferCanvas: true, scrollWheelZoom: true }})
                .setView([{center["lat"]:.5f}, {center["lon"]:.5f}], 7);
            const topo = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
                maxZoom: 16,
                attribution: "Tiles &copy; Esri | Mouse wheel zoom enabled"
            }});
            const streets = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
                maxZoom: 16,
                attribution: "Tiles &copy; Esri"
            }});
            const imagery = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
                maxZoom: 16,
                attribution: "Tiles &copy; Esri"
            }});
            const lightGray = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
                maxZoom: 16,
                attribution: "Tiles &copy; Esri"
            }});
            imagery.addTo(map);
            const overlays = {{}};
            const adminBoundary = L.geoJSON(districts, {{
                style: () => ({{
                    color: "#111827",
                    weight: 1.15,
                    opacity: 0.78,
                    fillColor: "#ffffff",
                    fillOpacity: 0.02,
                    dashArray: "4 3"
                }}),
                onEachFeature: (feature, layer) => {{
                    const name = feature.properties && feature.properties.district ? feature.properties.district : "MP boundary";
                    layer.bindTooltip(name, {{ sticky: true }});
                }}
            }}).addTo(map);
            overlays["MP admin boundaries"] = adminBoundary;
            if (weatherTileApiKey) {{
                const cloudLayer = L.tileLayer(
                    `https://tile.openweathermap.org/map/clouds_new/{{z}}/{{x}}/{{y}}.png?appid=${{weatherTileApiKey}}`,
                    {{ opacity: 0.55, maxZoom: 16, attribution: "Weather tiles &copy; OpenWeather" }}
                ).addTo(map);
                const precipitationLayer = L.tileLayer(
                    `https://tile.openweathermap.org/map/precipitation_new/{{z}}/{{x}}/{{y}}.png?appid=${{weatherTileApiKey}}`,
                    {{ opacity: 0.62, maxZoom: 16, attribution: "Weather tiles &copy; OpenWeather" }}
                ).addTo(map);
                overlays["Cloud cover"] = cloudLayer;
                overlays["Precipitation"] = precipitationLayer;
            }}
            const layerControl = L.control.layers(
                {{
                    "Satellite": imagery,
                    "Topographic": topo,
                    "Streets": streets,
                    "Light Gray": lightGray
                }},
                overlays,
                {{ collapsed: false, position: "topright" }}
            ).addTo(map);
            fetch("https://api.rainviewer.com/public/weather-maps.json")
                .then((response) => response.json())
                .then((payload) => {{
                    const radarFrames = (payload.radar && payload.radar.past ? payload.radar.past : []);
                    const latestRadar = radarFrames[radarFrames.length - 1];
                    if (!latestRadar || !payload.host || !latestRadar.path) return;
                    let radarIndex = radarFrames.length - 1;
                    let radarLayer = L.tileLayer(
                        `${{payload.host}}${{latestRadar.path}}/256/{{z}}/{{x}}/{{y}}/2/1_1.png`,
                        {{
                            opacity: 0.66,
                            maxZoom: 16,
                            attribution: 'Weather radar &copy; <a href="https://www.rainviewer.com/" target="_blank" rel="noreferrer">RainViewer</a>'
                        }}
                    ).addTo(map);
                    let radarTimer = null;
                    const setRadarFrame = (index) => {{
                        radarIndex = index;
                        const frame = radarFrames[radarIndex];
                        if (!frame) return;
                        radarLayer.setUrl(`${{payload.host}}${{frame.path}}/256/{{z}}/{{x}}/{{y}}/2/1_1.png`);
                    }};
                    const radarControl = L.control({{ position: "bottomleft" }});
                    radarControl.onAdd = () => {{
                        const div = L.DomUtil.create("div", "weather-legend");
                        div.innerHTML = '<b>Radar Animation</b><button type="button" style="margin-top:6px;padding:4px 8px;border:1px solid #cbd5e1;border-radius:6px;background:#ffffff;cursor:pointer;">Play</button><div style="margin-top:5px;color:#64748b">Latest radar is on by default</div>';
                        const button = div.querySelector("button");
                        L.DomEvent.disableClickPropagation(div);
                        button.addEventListener("click", () => {{
                            if (radarTimer) {{
                                clearInterval(radarTimer);
                                radarTimer = null;
                                button.textContent = "Play";
                                setRadarFrame(radarFrames.length - 1);
                                return;
                            }}
                            button.textContent = "Pause";
                            radarTimer = setInterval(() => {{
                                setRadarFrame((radarIndex + 1) % radarFrames.length);
                            }}, 750);
                        }});
                        return div;
                    }};
                    radarControl.addTo(map);
                    layerControl.addOverlay(radarLayer, "Latest weather radar");
                }})
                .catch(() => {{}});
            const bounds = [];
            towns.forEach((town) => {{
                bounds.push([town.lat, town.lon]);
                const marker = L.circleMarker([town.lat, town.lon], {{
                    radius: town.selected ? 8 : 5.6,
                    color: town.selected ? "#0f172a" : "#ffffff",
                    weight: town.selected ? 2.4 : 1.2,
                    fillColor: town.color,
                    fillOpacity: 0.94
                }}).addTo(map);
                marker.bindTooltip(`${{town.town}} | ${{town.risk}}`, {{ sticky: true }});
                marker.bindPopup(`
                    <b>${{town.town}}</b><br/>
                    District: ${{town.district}}<br/>
                    Basin: ${{town.basin}}<br/>
                    Risk: <b style="color:${{town.color}}">${{town.risk}}</b><br/>
                    7-day rain: ${{town.forecast_rain}} mm<br/>
                    Max temp: ${{town.max_temp}} &deg;C<br/>
                    Max wind: ${{town.max_wind}} km/h<br/>
                    Max UV: ${{town.max_uv}}
                `);
            }});
            const boundsObj = L.latLngBounds(bounds);
            if (boundsObj.isValid()) map.fitBounds(boundsObj.pad(0.15), {{ maxZoom: 7 }});
            const legend = L.control({{ position: "bottomright" }});
            legend.onAdd = () => {{
                const div = L.DomUtil.create("div", "weather-legend");
                div.innerHTML = `
                    <b>Weather Risk</b>
                    <div><span style="background:#dc2626"></span>Severe</div>
                    <div><span style="background:#f97316"></span>High</div>
                    <div><span style="background:#f59e0b"></span>Moderate</div>
                    <div><span style="background:#14b8a6"></span>Low</div>
                `;
                return div;
            }};
            legend.addTo(map);
            setTimeout(() => map.invalidateSize(), 350);
        }})();
        </script>
        """,
        height=480,
    )


def speedometer_svg(percent: float | int | None, label: str = "", width: int = 180, height: int = 96) -> str:
    value = 0 if percent is None or pd.isna(percent) else max(0, min(100, float(percent)))
    angle = 180 - (180 * value / 100)
    needle_x = 90 + 52 * math.cos(math.radians(angle))
    needle_y = 76 - 52 * math.sin(math.radians(angle))
    color = "#2563eb"
    if value >= 95:
        color = "#ef4444"
    elif value >= 85:
        color = "#f59e0b"
    elif value >= 65:
        color = "#06b6d4"
    return f"""
    <svg class="speedometer" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)} filling gauge">
        <path d="M 20 76 A 70 70 0 0 1 160 76" fill="none" stroke="#e5eaf3" stroke-width="15" stroke-linecap="round" />
        <path d="M 20 76 A 70 70 0 0 1 160 76" fill="none" stroke="{color}" stroke-width="15" stroke-linecap="round" pathLength="100" stroke-dasharray="{value:.2f} 100" />
        <line x1="90" y1="76" x2="{needle_x:.2f}" y2="{needle_y:.2f}" stroke="#172033" stroke-width="2.5" stroke-linecap="round" />
        <circle cx="90" cy="76" r="5" fill="#172033" />
        <text x="90" y="58" text-anchor="middle" class="speed-value">{value:.0f}%</text>
        <text x="90" y="92" text-anchor="middle" fill="#64748b" font-size="10">{escape(label)}</text>
    </svg>
    """


def scenario_radius_km(event_label: str, return_period: str, depth_m: float) -> float:
    event_factor = {
        "2019 Monsoon Flood": 1.15,
        "2020 High Rainfall Event": 0.95,
        "2021 Chambal-Betwa Event": 1.05,
        "2022 Narmada Event": 1.10,
        "Custom Planning Scenario": 1.0,
    }.get(event_label, 1.0)
    rp_factor = {
        "Normal floodplain": 0.75,
        "1 in 10 year": 1.0,
        "1 in 25 year": 1.25,
        "1 in 50 year": 1.55,
        "1 in 100 year": 1.9,
    }.get(return_period, 1.0)
    return max(3.0, min(45.0, (5.5 + depth_m * 4.2) * event_factor * rp_factor))


def render_arcgis_3d_sentinel_scene(
    dam_frame: pd.DataFrame,
    district_geojson: dict,
    drainage_geojson: dict,
    selected_dam_names: list[str],
    event_label: str,
    return_period: str,
    depth_m: float,
) -> None:
    if dam_frame.empty or not {"latitude", "longitude"}.issubset(dam_frame.columns):
        st.info("Dam coordinates are not available for the 3D scenario scene.")
        return
    scenario_frame = dam_frame.dropna(subset=["latitude", "longitude"]).copy()
    if selected_dam_names:
        scenario_frame = scenario_frame[scenario_frame["reservoir_name"].isin(selected_dam_names)]
    if scenario_frame.empty:
        st.info("No dam points match the selected 3D scenario filters.")
        return
    scenario_frame = scenario_frame.sort_values("display_filling", ascending=False).head(18)
    radius_km = scenario_radius_km(event_label, return_period, depth_m)
    dam_records = []
    for row in scenario_frame.to_dict("records"):
        filling = pd.to_numeric(pd.Series([row.get("display_filling")]), errors="coerce").iloc[0]
        frl_gap = pd.to_numeric(pd.Series([row.get("frl_gap_m")]), errors="coerce").iloc[0]
        dam_records.append(
            {
                "name": str(row.get("reservoir_name") or row.get("dam_name") or "Dam"),
                "dam": str(row.get("dam_name") or row.get("reservoir_name") or "Dam"),
                "district": str(row.get("district") or row.get("map_district") or ""),
                "basin": str(row.get("sub_basin") or row.get("major_basin") or ""),
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
                "filling": 0 if pd.isna(filling) else round(float(filling), 1),
                "frlGap": None if pd.isna(frl_gap) else round(float(frl_gap), 2),
                "alert": str(row.get("alert_level") or "Normal"),
                "waterLevel": None if pd.isna(row.get("water_level_m")) else round(float(row.get("water_level_m")), 2),
                "radiusKm": radius_km,
                "maxDepth": round(float(depth_m), 2),
            }
        )
    scene_id = f"sentinel-3d-scene-{abs(hash(event_label + return_period + str(depth_m))) % 1000000}"
    components.html(
        f"""
        <link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/light/main.css">
        <style>
            #{scene_id} {{
                height: 640px;
                width: 100%;
                border: 1px solid #dbe6f4;
                border-radius: 8px;
                overflow: hidden;
                background: #0f172a;
            }}
            .scenario-scene-note {{
                font: 11px Roboto, Inter, Segoe UI, sans-serif;
                color: #64748b;
                margin: 0 0 8px;
            }}
            .scenario-scene-title {{
                font: 800 14px Roboto, Inter, Segoe UI, sans-serif;
                color: #172033;
                margin: 0 0 5px;
            }}
        </style>
        <div class="scenario-scene-title">ArcGIS 3D Sentinel Inundation Scenario</div>
        <div class="scenario-scene-note">3D terrain scene with MP admin boundaries, dam alert markers, WSE depth zones, and scenario flood extents. Replace generated footprints with Sentinel-1 SAR polygons or FABDEM-derived depth rasters when event layers are available.</div>
        <div id="{scene_id}"></div>
        <script src="https://js.arcgis.com/4.30/"></script>
        <script>
        require([
            "esri/Map",
            "esri/views/SceneView",
            "esri/layers/GraphicsLayer",
            "esri/layers/GeoJSONLayer",
            "esri/Graphic",
            "esri/geometry/Point",
            "esri/geometry/Polyline",
            "esri/geometry/Polygon",
            "esri/geometry/geometryEngine",
            "esri/widgets/LayerList",
            "esri/widgets/Legend",
            "esri/widgets/Home",
            "esri/widgets/Expand"
        ], (Map, SceneView, GraphicsLayer, GeoJSONLayer, Graphic, Point, Polyline, Polygon, geometryEngine, LayerList, Legend, Home, Expand) => {{
            const dams = {json.dumps(dam_records)};
            const districts = {json.dumps(district_geojson)};
            const drains = {json.dumps(drainage_geojson)};
            const map = new Map({{
                basemap: "satellite",
                ground: "world-elevation"
            }});
            const view = new SceneView({{
                container: "{scene_id}",
                map,
                qualityProfile: "high",
                camera: {{
                    position: {{ longitude: 78.6, latitude: 23.7, z: 850000 }},
                    tilt: 48,
                    heading: 0
                }},
                environment: {{
                    atmosphereEnabled: true,
                    starsEnabled: false,
                    lighting: {{ directShadowsEnabled: true, ambientOcclusionEnabled: true }}
                }}
            }});
            const districtBlob = new Blob([JSON.stringify(districts)], {{ type: "application/json" }});
            const districtLayer = new GeoJSONLayer({{
                title: "MP admin boundaries",
                url: URL.createObjectURL(districtBlob),
                renderer: {{
                    type: "simple",
                    symbol: {{
                        type: "simple-fill",
                        color: [255,255,255,0.02],
                        outline: {{ color: [255,255,255,0.82], width: 1.1 }}
                    }}
                }},
                labelingInfo: [{{
                    labelExpressionInfo: {{ expression: "$feature.district" }},
                    symbol: {{
                        type: "label-3d",
                        symbolLayers: [{{
                            type: "text",
                            material: {{ color: [255,255,255,0.9] }},
                            size: 9,
                            halo: {{ color: [15,23,42,0.85], size: 1 }}
                        }}]
                    }}
                }}]
            }});
            map.add(districtLayer);
            const inundationLayer = new GraphicsLayer({{ title: "Sentinel inundation scenario footprint" }});
            const depthLayer = new GraphicsLayer({{ title: "Generated WSE depth / water-spread zones" }});
            const drainageLayer = new GraphicsLayer({{ title: "MP drainage layer by ORD_STRA" }});
            const drainageWseLayer = new GraphicsLayer({{ title: "Drainage-layer WSE spread depth" }});
            const buildingLayer = new GraphicsLayer({{ title: "OSM 3D building footprints" }});
            const damLayer = new GraphicsLayer({{ title: "VBSR dam alert points" }});
            map.addMany([inundationLayer, drainageWseLayer, depthLayer, drainageLayer, buildingLayer, damLayer]);
            const colorByAlert = (alert) => {{
                if (alert === "Critical") return [239,68,68,0.95];
                if (alert === "Warning") return [245,158,11,0.95];
                if (alert === "Watch") return [234,179,8,0.92];
                return [37,99,235,0.9];
            }};
            const drainageVector = (basin) => {{
                const label = String(basin || "").toLowerCase();
                if (label.includes("narmada")) return {{ dx: -0.52, dy: -0.06 }};
                if (label.includes("chambal")) return {{ dx: -0.28, dy: 0.20 }};
                if (label.includes("betwa")) return {{ dx: 0.28, dy: 0.12 }};
                if (label.includes("ken")) return {{ dx: 0.34, dy: 0.05 }};
                if (label.includes("son")) return {{ dx: 0.44, dy: 0.10 }};
                if (label.includes("ganges")) return {{ dx: 0.32, dy: 0.14 }};
                if (label.includes("mahanadi")) return {{ dx: 0.38, dy: -0.12 }};
                return {{ dx: 0.24, dy: -0.10 }};
            }};
            const drainageLineForDam = (dam) => {{
                const vector = drainageVector(dam.basin);
                const reachScale = Math.min(1.7, Math.max(0.65, dam.radiusKm / 18));
                const p0 = [dam.lon, dam.lat];
                const p1 = [dam.lon + vector.dx * reachScale * 0.45, dam.lat + vector.dy * reachScale * 0.45];
                const p2 = [dam.lon + vector.dx * reachScale, dam.lat + vector.dy * reachScale];
                return new Polyline({{
                    paths: [[p0, p1, p2]],
                    spatialReference: {{ wkid: 4326 }}
                }});
            }};
            const featurePolyline = (feature) => {{
                const geom = feature.geometry || {{}};
                if (geom.type === "LineString") {{
                    return new Polyline({{ paths: [geom.coordinates], spatialReference: {{ wkid: 4326 }} }});
                }}
                if (geom.type === "MultiLineString") {{
                    return new Polyline({{ paths: geom.coordinates, spatialReference: {{ wkid: 4326 }} }});
                }}
                return null;
            }};
            const orderWidth = (order) => Math.max(0.2, Math.min(1.5, 0.2 + (Number(order || 1) - 1) * 0.18));
            const buildingColor = (exposure) => {{
                if (exposure === "High") return [239,68,68,0.86];
                if (exposure === "Moderate") return [245,158,11,0.84];
                return [20,184,166,0.82];
            }};
            const exposureForDistance = (distanceKm, radiusKm) => {{
                if (distanceKm <= Math.max(0.6, radiusKm * 0.18)) return "High";
                if (distanceKm <= Math.max(1.2, radiusKm * 0.38)) return "Moderate";
                return "Low";
            }};
            const parseOsmHeight = (tags = {{}}) => {{
                const rawHeight = String(tags.height || tags["building:height"] || "").replace(",", ".").match(/[0-9.]+/);
                if (rawHeight) return Math.max(3, Math.min(90, Number(rawHeight[0])));
                const levels = Number(String(tags["building:levels"] || tags.levels || "").replace(",", "."));
                if (Number.isFinite(levels) && levels > 0) return Math.max(3, Math.min(90, levels * 3.2));
                return 10;
            }};
            const addOsmBuildingFootprints = async (dam) => {{
                const radiusMeters = Math.min(3500, Math.max(900, Math.round(dam.radiusKm * 180)));
                const query = `[out:json][timeout:20];way["building"](around:${{radiusMeters}},${{dam.lat}},${{dam.lon}});out tags geom 90;`;
                const endpoints = [
                    "https://overpass-api.de/api/interpreter?data=",
                    "https://overpass.kumi.systems/api/interpreter?data="
                ];
                let osm = null;
                for (const endpoint of endpoints) {{
                    try {{
                        const response = await fetch(endpoint + encodeURIComponent(query));
                        if (response.ok) {{
                            osm = await response.json();
                            break;
                        }}
                    }} catch (error) {{
                        console.warn("OSM building footprint request failed", error);
                    }}
                }}
                if (!osm || !Array.isArray(osm.elements)) return;
                osm.elements.slice(0, 90).forEach((element) => {{
                    if (!Array.isArray(element.geometry) || element.geometry.length < 4) return;
                    const ring = element.geometry.map((coord) => [coord.lon, coord.lat]);
                    const first = ring[0];
                    const last = ring[ring.length - 1];
                    if (first[0] !== last[0] || first[1] !== last[1]) ring.push(first);
                    const footprint = new Polygon({{
                        rings: [ring],
                        spatialReference: {{ wkid: 4326 }}
                    }});
                    const center = footprint.extent.center;
                    const distanceKm = geometryEngine.distance(
                        new Point({{ longitude: dam.lon, latitude: dam.lat, spatialReference: {{ wkid: 4326 }} }}),
                        center,
                        "kilometers"
                    );
                    const exposure = exposureForDistance(distanceKm || 0, dam.radiusKm);
                    const height = parseOsmHeight(element.tags || {{}});
                    buildingLayer.add(new Graphic({{
                        geometry: footprint,
                        attributes: {{
                            dam: dam.name,
                            district: dam.district,
                            exposure,
                            height,
                            osm_id: element.id,
                            osm_building: (element.tags || {{}}).building || "yes",
                            scenario: "{escape(event_label)}",
                            source: "OpenStreetMap building footprint"
                        }},
                        symbol: {{
                            type: "polygon-3d",
                            symbolLayers: [{{
                                type: "extrude",
                                size: height,
                                material: {{ color: buildingColor(exposure) }},
                                edges: {{ type: "solid", color: [15,23,42,0.42], size: 0.45 }}
                            }}]
                        }},
                        popupTemplate: {{
                            title: "OSM 3D building footprint",
                            content: `Nearest dam: <b>${{dam.name}}</b><br/>Exposure class: <b>${{exposure}}</b><br/>Extruded height: ${{height.toFixed(1)}} m<br/>OSM building: ${{(element.tags || {{}}).building || "yes"}}<br/>OSM way: ${{element.id}}<br/>Scenario: {escape(return_period)}`
                        }}
                    }}));
                }});
            }};
            const selectedDrainLines = [];
            (drains.features || []).forEach((feature) => {{
                const line = featurePolyline(feature);
                if (!line) return;
                const props = feature.properties || {{}};
                const order = Number(props.ORD_STRA || 1);
                const width = orderWidth(order);
                selectedDrainLines.push({{ line, props, order, width }});
                drainageLayer.add(new Graphic({{
                    geometry: line,
                    attributes: props,
                    symbol: {{
                        type: "simple-line",
                        color: order >= 6 ? [8,47,73,0.98] : order >= 4 ? [14,116,144,0.95] : [6,182,212,0.85],
                        width: width + 0.8,
                        style: "solid"
                    }},
                    popupTemplate: {{
                        title: `Drainage ORD_STRA ${{order}}`,
                        content: `Sub basin: <b>${{props.SUB_NAME || "-"}}</b><br/>Major basin: <b>${{props.MAJ_NAME || "-"}}</b><br/>Length: ${{props.LENGTH_KM || "-"}} km<br/>Average discharge: ${{props.DIS_AV_CMS || "-"}} cms`
                    }}
                }}));
            }});
            const addWseCorridor = (line, dam, zone, order, sourceLabel) => {{
                const corridorGeom = geometryEngine.geodesicBuffer(
                    line,
                    Math.max(250, dam.radiusKm * zone.ratio * (260 + Number(order || 1) * 34)),
                    "meters"
                );
                drainageWseLayer.add(new Graphic({{
                    geometry: corridorGeom,
                    attributes: {{ ...dam, depthZone: zone.label, modeledDepthM: zone.depth, streamOrder: order, source: sourceLabel }},
                    symbol: {{
                        type: "simple-fill",
                        color: [zone.color[0], zone.color[1], zone.color[2], Math.min(0.72, zone.color[3] + 0.08)],
                        outline: {{ color: [255,255,255,0.62], width: 0.35 }}
                    }},
                    popupTemplate: {{
                        title: `${{dam.name}} drainage-layer WSE`,
                        content: `Depth class: <b>${{zone.label}}</b><br/>Modeled WSE depth: ${{zone.depth.toFixed(2)}} m<br/>Drainage ORD_STRA: ${{order}}<br/>Source: ${{sourceLabel}}<br/>Elevation context: ArcGIS world elevation`
                    }}
                }}));
            }};
            const nearestDrainLines = (point, limit = 3) => {{
                const ranked = selectedDrainLines
                    .map((item) => ({{ ...item, distance: geometryEngine.distance(point, item.line, "kilometers") }}))
                    .filter((item) => Number.isFinite(item.distance))
                    .sort((a, b) => a.distance - b.distance || b.order - a.order);
                return ranked.slice(0, limit);
            }};
            dams.forEach((dam) => {{
                const point = new Point({{ longitude: dam.lon, latitude: dam.lat, spatialReference: {{ wkid: 4326 }} }});
                const buffer = geometryEngine.geodesicBuffer(point, dam.radiusKm, "kilometers");
                inundationLayer.add(new Graphic({{
                    geometry: buffer,
                    attributes: dam,
                    symbol: {{
                        type: "simple-fill",
                        color: [49,96,247,0.28],
                        outline: {{ color: [49,96,247,0.72], width: 1.2 }}
                    }},
                    popupTemplate: {{
                        title: "{escape(event_label)}",
                        content: `<b>${{dam.name}}</b><br/>Scenario: {escape(return_period)}<br/>Screening depth: {depth_m:.2f} m<br/>Approx. radius: ${{dam.radiusKm.toFixed(1)}} km`
                    }}
                }}));
                let nearbyDrainLines = nearestDrainLines(point, 3);
                if (!nearbyDrainLines.length) {{
                    const fallbackLine = drainageLineForDam(dam);
                    nearbyDrainLines = [{{ line: fallbackLine, order: Math.max(1, Math.min(8, Math.round(1 + dam.radiusKm / 6))), width: 0.8, props: {{}}, distance: null, fallback: true }}];
                    drainageLayer.add(new Graphic({{
                        geometry: fallbackLine,
                        attributes: {{ ...dam, ORD_STRA: nearbyDrainLines[0].order }},
                        symbol: {{
                            type: "simple-line",
                            color: [6,182,212,0.95],
                            width: orderWidth(nearbyDrainLines[0].order) + 0.8,
                            style: "short-dash"
                        }},
                        popupTemplate: {{
                            title: `${{dam.name}} fallback drainage`,
                            content: `No nearby MP drainage segment found in filtered layer. Generated fallback flow path used.`
                        }}
                    }}));
                }}
                const depthZones = [
                    {{ label: "0 - 25% WSE depth", ratio: 1.00, depth: dam.maxDepth * 0.25, color: [186,230,253,0.48] }},
                    {{ label: "25 - 50% WSE depth", ratio: 0.74, depth: dam.maxDepth * 0.50, color: [56,189,248,0.52] }},
                    {{ label: "50 - 75% WSE depth", ratio: 0.49, depth: dam.maxDepth * 0.75, color: [37,99,235,0.58] }},
                    {{ label: "75 - 100% WSE depth", ratio: 0.25, depth: dam.maxDepth, color: [30,64,175,0.66] }}
                ];
                depthZones.forEach((zone) => {{
                    const zoneGeom = geometryEngine.geodesicBuffer(point, Math.max(0.5, dam.radiusKm * zone.ratio), "kilometers");
                    nearbyDrainLines.forEach((item) => addWseCorridor(item.line, dam, zone, item.order, item.fallback ? "fallback inferred line" : "MP drains ORD_STRA layer"));
                    depthLayer.add(new Graphic({{
                        geometry: zoneGeom,
                        attributes: {{ ...dam, depthZone: zone.label, modeledDepthM: zone.depth }},
                        symbol: {{
                            type: "simple-fill",
                            color: zone.color,
                            outline: {{ color: [255,255,255,0.55], width: 0.5 }}
                        }},
                        popupTemplate: {{
                            title: `${{dam.name}} WSE depth zone`,
                            content: `Depth class: <b>${{zone.label}}</b><br/>Modeled WSE depth: ${{zone.depth.toFixed(2)}} m<br/>Water spread radius: ${{(dam.radiusKm * zone.ratio).toFixed(1)}} km<br/>Scenario: {escape(return_period)}`
                        }}
                    }}));
                }});
                addOsmBuildingFootprints(dam);
                damLayer.add(new Graphic({{
                    geometry: point,
                    attributes: dam,
                    symbol: {{
                        type: "point-3d",
                        symbolLayers: [{{
                            type: "object",
                            resource: {{ primitive: "cylinder" }},
                            material: {{ color: colorByAlert(dam.alert) }},
                            width: 18000,
                            depth: 18000,
                            height: Math.max(15000, dam.filling * 850),
                            anchor: "bottom"
                        }}],
                        verticalOffset: {{ screenLength: 16, maxWorldLength: 90000, minWorldLength: 5000 }},
                        callout: {{ type: "line", color: [255,255,255,0.72], size: 1 }}
                    }},
                    popupTemplate: {{
                        title: dam.name,
                        content: `District: <b>${{dam.district || "-"}}</b><br/>Basin: <b>${{dam.basin || "-"}}</b><br/>WL: ${{dam.waterLevel ?? "-"}} m<br/>FRL gap: ${{dam.frlGap ?? "-"}} m<br/>Filling: ${{dam.filling}}%<br/>Alert: <b>${{dam.alert}}</b>`
                    }}
                }}));
            }});
            view.ui.add(new Home({{ view }}), "top-left");
            view.ui.add(new Expand({{ view, content: new LayerList({{ view }}), expanded: false }}), "top-right");
            view.ui.add(new Expand({{ view, content: new Legend({{ view }}), expanded: false }}), "bottom-right");
            view.when(() => {{
                if (damLayer.graphics.length) {{
                    view.goTo(damLayer.graphics, {{ tilt: 52, heading: 0, duration: 1200 }}).catch(() => {{}});
                }}
            }});
        }});
        </script>
        """,
        height=705,
    )


def reservoir_snapshot_chart(
    plot_df: pd.DataFrame,
    metric_col: str,
    metric_label: str,
    metric_unit: str,
    chart_type: str,
    height: int,
    sort: str = "-x",
):
    tooltip = ["reservoir_name", "district", metric_col, "observed_at"]
    if chart_type == "Line":
        return (
            alt.Chart(plot_df)
            .mark_line(point=True)
            .encode(
                x=alt.X("reservoir_name:N", sort=sort, title="Reservoir"),
                y=alt.Y(f"{metric_col}:Q", title=f"{metric_label} ({metric_unit})"),
                color=alt.Color("district:N", legend=None),
                tooltip=tooltip,
            )
            .properties(height=height)
        )
    if chart_type == "Scatter":
        return (
            alt.Chart(plot_df)
            .mark_circle(size=92, opacity=0.8)
            .encode(
                x=alt.X(f"{metric_col}:Q", title=f"{metric_label} ({metric_unit})"),
                y=alt.Y("reservoir_name:N", sort=sort, title="Reservoir"),
                color=alt.Color("district:N", legend=None),
                tooltip=tooltip,
            )
            .properties(height=height)
        )
    return (
        alt.Chart(plot_df)
        .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X(f"{metric_col}:Q", title=f"{metric_label} ({metric_unit})"),
            y=alt.Y("reservoir_name:N", sort=sort, title="Reservoir"),
            color=alt.Color("district:N", legend=None),
            tooltip=tooltip,
        )
        .properties(height=height)
    )


def save_uploaded_pdf(uploaded_file) -> Path:
    upload_dir = APP_DIR / "uploaded_reports"
    upload_dir.mkdir(exist_ok=True)
    target = upload_dir / uploaded_file.name
    target.write_bytes(uploaded_file.getbuffer())
    return target


def get_app_secret(name: str, env_name: str, default: str = "") -> str:
    value = os.getenv(env_name, "")
    if value:
        return value
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


ADMIN_USER = get_app_secret("admin_user", "MPWRD_ADMIN_USER", "admin_nitaai")
ADMIN_PASSWORD = get_app_secret("admin_password", "MPWRD_ADMIN_PASSWORD", "")


def admin_login_panel() -> bool:
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False

    with st.expander("Administration", expanded=not st.session_state.admin_authenticated):
        if st.session_state.admin_authenticated:
            st.success(f"Signed in as {ADMIN_USER}")
            if st.button("Sign out", key="admin_sign_out", use_container_width=True):
                st.session_state.admin_authenticated = False
                st.rerun()
            return True

        st.caption("Upload and data refresh are restricted to administration users.")
        if not ADMIN_PASSWORD:
            st.warning("Admin upload is disabled until MPWRD_ADMIN_PASSWORD or Streamlit secret admin_password is configured.")
            return False

        with st.form("admin_login_form"):
            username = st.text_input("Admin user", value=ADMIN_USER)
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Unlock upload", use_container_width=True)
        if submitted:
            user_ok = hmac.compare_digest(username.strip(), ADMIN_USER)
            password_ok = bool(password and ADMIN_PASSWORD) and hmac.compare_digest(password, ADMIN_PASSWORD)
            if user_ok and password_ok:
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("Invalid admin credentials.")
    return bool(st.session_state.admin_authenticated)


with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
          <div class="sidebar-brand-row">
            <div class="sidebar-logo">N</div>
            <div>
              <div class="sidebar-brand-title">Nita AI</div>
              <div class="sidebar-brand-subtitle">Geo-Analytics Platform</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.header("Report Source")
    is_admin = admin_login_panel()
    if is_admin:
        uploaded = st.file_uploader("Upload MP WRD flood report PDF", type=["pdf"])
        if uploaded is not None:
            saved_pdf = save_uploaded_pdf(uploaded)
            output_dir = APP_DIR / f"parsed_{saved_pdf.stem.replace(' ', '_')}"
            with st.spinner("Parsing uploaded report..."):
                counts = parse_pdf(saved_pdf, output_dir)
            st.success(
                f"Captured {counts['river_observation_rows']} river, "
                f"{counts['reservoir_observation_rows']} reservoir, "
                f"{counts['gate_observation_rows']} gate rows."
            )
    else:
        st.info("Dashboard is in read-only mode. Sign in as admin to upload PDFs and refresh captured data.")

    dirs = parsed_directories()
    if not dirs:
        st.stop()
    selected_names = st.multiselect(
        "Captured reports",
        [path.name for path in dirs],
        default=[path.name for path in dirs],
        help="Select one or more parsed reports to build the time-series dashboard.",
    )
    if not selected_names:
        st.warning("Select at least one captured report.")
        st.stop()

selected_paths = [APP_DIR / name for name in selected_names]
meta_df, river_master, reservoir_master, rivers, reservoirs, gates = load_time_series(selected_paths)
capacity_estimates = read_csv(RESERVOIR_CAPACITY_ESTIMATES_CSV)
capacity_curves = read_csv(RESERVOIR_CAPACITY_CURVES_CSV)
capacity_curves_fabdem = read_csv(RESERVOIR_CAPACITY_CURVES_FABDEM_CSV)

if not reservoirs.empty:
    reservoirs["frl_gap_m"] = reservoirs["frl_m"] - reservoirs["water_level_m"]
if not rivers.empty:
    rivers["danger_gap_m"] = rivers["danger_or_max_water_level_m"] - rivers["water_level_m"]
    if "basin" not in rivers.columns:
        rivers["basin"] = rivers["river_name"]
if not river_master.empty and "basin" not in river_master.columns:
    river_master["basin"] = river_master["river_name"]

dam_locations = attach_dam_locations(
    load_dam_locations(str(DAM_LOCATIONS_CSV), str(DAM_SHAPEFILE)),
    sorted(reservoirs["reservoir_name"].dropna().unique()) if not reservoirs.empty else [],
)

with st.sidebar:
    st.header("Time Filters")
    observed_values = sorted(reservoirs["observed_at"].dropna().unique()) if not reservoirs.empty else []
    observed_timestamps = [pd.Timestamp(value) for value in observed_values]
    observed_dates = sorted({value.date() for value in observed_timestamps})
    selected_date_range = st.date_input(
        "Dates",
        value=(observed_dates[0], observed_dates[-1]) if observed_dates else None,
        min_value=observed_dates[0] if observed_dates else None,
        max_value=observed_dates[-1] if observed_dates else None,
        help="Filters reservoir and river observations by observation date.",
    )
    if isinstance(selected_date_range, tuple):
        start_date, end_date = selected_date_range
    elif selected_date_range:
        start_date = end_date = selected_date_range
    else:
        start_date = end_date = None

    time_options = sorted({value.strftime("%I:%M %p") for value in observed_timestamps})
    selected_time_labels = st.multiselect("Times", time_options, default=time_options)
    selected_observed = {
        value
        for value in observed_values
        if (start_date is None or pd.Timestamp(value).date() >= start_date)
        and (end_date is None or pd.Timestamp(value).date() <= end_date)
        and pd.Timestamp(value).strftime("%I:%M %p") in selected_time_labels
    }

    district_options = sorted(
        set(reservoirs["district"].dropna().unique()).union(set(rivers["district"].dropna().unique()))
    )
    selected_districts = st.multiselect("Districts", district_options, default=[])

    st.header("Asset Filters")
    reservoir_options = sorted(reservoirs["reservoir_name"].dropna().unique()) if not reservoirs.empty else []
    map_selected_reservoir = st.session_state.get("map_selected_reservoir")
    selected_reservoir_names = st.multiselect(
        "Name of Reservoir",
        reservoir_options,
        default=[],
        help="Applies to reservoir observations and reservoir gate rows only.",
    )
    basin_values = set(rivers["basin"].dropna().unique()) if not rivers.empty and "basin" in rivers else set()
    if not dam_locations.empty:
        basin_values.update(dam_locations["sub_basin"].dropna().unique())
        basin_values.update(dam_locations["major_basin"].dropna().unique())
    basin_options = sorted(value for value in basin_values if str(value).strip())
    selected_basins = st.multiselect(
        "Basin",
        basin_options,
        default=[],
        help="Applies to dam map and matched reservoir rows. For river rows, current PDF reports use river name where no basin field exists.",
    )
    gauge_options = sorted(rivers["gauge_station"].dropna().unique()) if not rivers.empty else []
    selected_gauge_stations = st.multiselect(
        "Name of Gauge Station",
        gauge_options,
        default=[],
        help="Applies to river gauge observations only.",
    )
    st.header("Forecast Data")
    forecast_data_mode = st.radio(
        "Forecast Mode",
        ["Full dynamic mode", "Fallback/demo mode"],
        index=0,
        help="Full dynamic mode uses only configured live/preprocessed endpoints. Fallback/demo mode keeps the synthetic MP screening panels available when endpoints are blank.",
    )
    glofas_endpoint = st.text_input(
        "GloFAS Timeseries Endpoint",
        value=GLOFAS_PROJECT_JSON.as_uri() if GLOFAS_PROJECT_JSON.exists() else "",
        placeholder="Required for full dynamic GloFAS mode",
        help="Defaults to the project-area GloFAS-compatible JSON. Paste a CDS/EWDS-backed or hosted preprocessed GloFAS JSON endpoint to replace it.",
    )
    grrr_endpoint = st.text_input(
        "Google Runoff Reanalysis/Reforecast Endpoint",
        value=GRRR_PROJECT_JSON.as_uri() if GRRR_PROJECT_JSON.exists() else "",
        placeholder="Required for full dynamic GRRR mode",
        help="Defaults to the project-area Google Runoff/GRRR-compatible JSON. Paste a published notebook/API JSON endpoint to replace it.",
    )

reservoir_view = reservoirs.copy()
river_view = rivers.copy()
gate_view_all = gates.copy()
effective_reservoir_names = list(selected_reservoir_names)
if map_selected_reservoir and map_selected_reservoir not in effective_reservoir_names:
    effective_reservoir_names.append(map_selected_reservoir)
if selected_observed:
    reservoir_view = reservoir_view[reservoir_view["observed_at"].isin(selected_observed)]
    river_view = river_view[river_view["observed_at"].isin(selected_observed)]
if selected_districts:
    reservoir_view = reservoir_view[reservoir_view["district"].isin(selected_districts)]
    river_view = river_view[river_view["district"].isin(selected_districts)]
    gate_view_all = gate_view_all[gate_view_all["district"].isin(selected_districts)]
if effective_reservoir_names:
    reservoir_view = reservoir_view[reservoir_view["reservoir_name"].isin(effective_reservoir_names)]
    gate_view_all = gate_view_all[gate_view_all["reservoir_name"].isin(effective_reservoir_names)]
if selected_basins and "basin" in river_view:
    river_view = river_view[river_view["basin"].isin(selected_basins)]
if selected_basins and not dam_locations.empty:
    basin_reservoirs = dam_locations[
        dam_locations["sub_basin"].isin(selected_basins) | dam_locations["major_basin"].isin(selected_basins)
    ]["reservoir_name"].dropna().unique()
    if len(basin_reservoirs):
        reservoir_view = reservoir_view[reservoir_view["reservoir_name"].isin(basin_reservoirs)]
        gate_view_all = gate_view_all[gate_view_all["reservoir_name"].isin(basin_reservoirs)]
if selected_gauge_stations:
    river_view = river_view[river_view["gauge_station"].isin(selected_gauge_stations)]

capacity_view = capacity_estimates.copy()
capacity_curve_view = capacity_curves.copy()
capacity_curve_fabdem_view = capacity_curves_fabdem.copy()
if not capacity_view.empty:
    if selected_districts and "district" in capacity_view:
        capacity_view = capacity_view[capacity_view["district"].isin(selected_districts)]
    if selected_districts and not capacity_curve_view.empty and "district" in capacity_curve_view:
        capacity_curve_view = capacity_curve_view[capacity_curve_view["district"].isin(selected_districts)]
    if selected_districts and not capacity_curve_fabdem_view.empty and "district" in capacity_curve_fabdem_view:
        capacity_curve_fabdem_view = capacity_curve_fabdem_view[capacity_curve_fabdem_view["district"].isin(selected_districts)]
    if effective_reservoir_names and "reservoir_name" in capacity_view:
        capacity_view = capacity_view[capacity_view["reservoir_name"].isin(effective_reservoir_names)]
    if effective_reservoir_names and not capacity_curve_view.empty and "reservoir_name" in capacity_curve_view:
        capacity_curve_view = capacity_curve_view[capacity_curve_view["reservoir_name"].isin(effective_reservoir_names)]
    if effective_reservoir_names and not capacity_curve_fabdem_view.empty and "reservoir_name" in capacity_curve_fabdem_view:
        capacity_curve_fabdem_view = capacity_curve_fabdem_view[capacity_curve_fabdem_view["reservoir_name"].isin(effective_reservoir_names)]
    if selected_basins:
        basin_mask = pd.Series(False, index=capacity_view.index)
        if "sub_basin" in capacity_view:
            basin_mask = basin_mask | capacity_view["sub_basin"].isin(selected_basins)
        if "major_basin" in capacity_view:
            basin_mask = basin_mask | capacity_view["major_basin"].isin(selected_basins)
        capacity_view = capacity_view[basin_mask]
        if not capacity_curve_view.empty:
            curve_basin_mask = pd.Series(False, index=capacity_curve_view.index)
            if "sub_basin" in capacity_curve_view:
                curve_basin_mask = curve_basin_mask | capacity_curve_view["sub_basin"].isin(selected_basins)
            if "major_basin" in capacity_curve_view:
                curve_basin_mask = curve_basin_mask | capacity_curve_view["major_basin"].isin(selected_basins)
            capacity_curve_view = capacity_curve_view[curve_basin_mask]
        if not capacity_curve_fabdem_view.empty:
            curve_fabdem_basin_mask = pd.Series(False, index=capacity_curve_fabdem_view.index)
            if "sub_basin" in capacity_curve_fabdem_view:
                curve_fabdem_basin_mask = curve_fabdem_basin_mask | capacity_curve_fabdem_view["sub_basin"].isin(selected_basins)
            if "major_basin" in capacity_curve_fabdem_view:
                curve_fabdem_basin_mask = curve_fabdem_basin_mask | capacity_curve_fabdem_view["major_basin"].isin(selected_basins)
            capacity_curve_fabdem_view = capacity_curve_fabdem_view[curve_fabdem_basin_mask]

latest_rivers = latest_by_asset(river_view, "gauge_station")
latest_reservoirs = latest_by_asset(reservoir_view, "reservoir_name")
open_gates = (
    gate_view_all[gate_view_all["gate_opened_count"].fillna(0).astype(float) > 0]
    if not gate_view_all.empty
    else gate_view_all
)
time_min = min(observed_values) if observed_values else pd.NaT
time_max = max(observed_values) if observed_values else pd.NaT

st.markdown(
    f"""
    <div class="masthead">
      <div class="masthead-top">
        <div class="brand-lockup">
          <div class="brand-logo">N</div>
          <div>
            <div class="brand-kicker">Nita AI &amp; Geo-Analytics</div>
            <div class="brand-name">Decision Intelligence for Water Resources</div>
            <div class="brand-domain">Flood, dam safety, geospatial analytics, and AI-enabled DSS</div>
          </div>
          <div class="title-group">
            <div class="title">MPWRD VBSR Dam Water Level Intelligent Dashboard and Analytics</div>
            <div class="subtitle">MPWRD VBSR Dam Water Level Status Monitoring and AI Analytics for DSS</div>
          </div>
        </div>
        <div class="meta-row">
          <div class="meta">
            <span class="meta-label">Observation Window</span>
            <span class="meta-value">{time_label(time_min)} to {time_label(time_max)}</span>
          </div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

map_status = dam_locations.copy()
if not map_status.empty and not latest_reservoirs.empty:
    map_status = map_status.merge(
        latest_reservoirs[
            [
                "reservoir_name",
                "district",
                "observed_at",
                "water_level_m",
                "frl_m",
                "frl_gap_m",
                "filling_percent",
                "current_live_capacity_mcm",
                "rainfall_daily_mm",
            ]
        ],
        on="reservoir_name",
        how="left",
    )
    map_status["display_filling"] = map_status["filling_percent"].fillna(map_status.get("map_filled_percent"))
else:
    map_status["display_filling"] = map_status.get("map_filled_percent", pd.Series(dtype=float))

if not map_status.empty:
    if selected_districts:
        map_status = map_status[
            map_status["map_district"].isin(selected_districts) | map_status.get("district", pd.Series(dtype=str)).isin(selected_districts)
        ]
    if effective_reservoir_names:
        map_status = map_status[map_status["reservoir_name"].isin(effective_reservoir_names)]
    if selected_basins:
        map_status = map_status[
            map_status["sub_basin"].isin(selected_basins) | map_status["major_basin"].isin(selected_basins)
        ]
    map_status["display_filling"] = pd.to_numeric(map_status["display_filling"], errors="coerce").fillna(0)
    map_status["frl_gap_m"] = pd.to_numeric(map_status.get("frl_gap_m"), errors="coerce")

    def frl_alert_level(row: pd.Series) -> str:
        filling = row.get("display_filling", 0)
        gap = row.get("frl_gap_m")
        if pd.notna(gap) and gap <= 0.5:
            return "Critical"
        if pd.notna(gap) and gap <= 1.5:
            return "Warning"
        if filling >= 90:
            return "Watch"
        return "Normal"

    def alert_color(level: str) -> list[int]:
        return {
            "Critical": [239, 68, 68, 235],
            "Warning": [245, 158, 11, 225],
            "Watch": [250, 204, 21, 215],
            "Normal": [37, 99, 235, 205],
        }.get(level, [37, 99, 235, 205])

    map_status["alert_level"] = map_status.apply(frl_alert_level, axis=1)
    map_status["fill_color"] = map_status["alert_level"].apply(alert_color)
    map_status["radius"] = (map_status["display_filling"].clip(0, 100) * 18 + 850).astype(float)
    map_status["pulse_radius"] = (map_status["radius"] * 2.35).astype(float)
    map_status["pulse_color"] = map_status["alert_level"].map(
        {
            "Critical": [239, 68, 68, 70],
            "Warning": [245, 158, 11, 56],
            "Watch": [250, 204, 21, 44],
            "Normal": [37, 99, 235, 0],
        }
    )
    map_status["line_color"] = map_status["alert_level"].map(
        {
            "Critical": [255, 255, 255, 255],
            "Warning": [255, 255, 255, 245],
            "Watch": [17, 24, 39, 175],
            "Normal": [255, 255, 255, 210],
        }
    )
    blink_on = pd.Timestamp.utcnow().second % 2 == 0
    alert_points = map_status[map_status["alert_level"].isin(["Critical", "Warning"])].copy()
    if not alert_points.empty and not blink_on:
        alert_points["pulse_color"] = alert_points["pulse_color"].apply(lambda _: [255, 255, 255, 0])


def build_dam_alert_rows(
    dams: pd.DataFrame,
    critical_gap_m: float,
    warning_gap_m: float,
    watch_filling_percent: float,
    rapid_rise_m: float,
) -> pd.DataFrame:
    if dams.empty:
        return pd.DataFrame()
    rows = dams.dropna(subset=["reservoir_name"]).copy()
    rows["frl_gap_m"] = pd.to_numeric(rows.get("frl_gap_m"), errors="coerce")
    rows["display_filling"] = pd.to_numeric(rows.get("display_filling"), errors="coerce")
    rows["water_level_m"] = pd.to_numeric(rows.get("water_level_m"), errors="coerce")

    def classify(row: pd.Series) -> str:
        gap = row.get("frl_gap_m")
        filling = row.get("display_filling")
        if pd.notna(gap) and gap <= critical_gap_m:
            return "Critical"
        if pd.notna(gap) and gap <= warning_gap_m:
            return "Warning"
        if pd.notna(filling) and filling >= watch_filling_percent:
            return "Watch"
        return "Normal"

    rows["configured_alert"] = rows.apply(classify, axis=1)
    if not reservoir_view.empty and {"reservoir_name", "observed_at", "water_level_m"}.issubset(reservoir_view.columns):
        trend_rows = reservoir_view.sort_values(["reservoir_name", "observed_at"]).copy()
        trend_rows["water_level_m"] = pd.to_numeric(trend_rows["water_level_m"], errors="coerce")
        trend_rows["wl_delta_m"] = trend_rows.groupby("reservoir_name")["water_level_m"].diff()
        latest_delta = trend_rows.groupby("reservoir_name", as_index=False).tail(1)[["reservoir_name", "wl_delta_m"]]
        rows = rows.merge(latest_delta, on="reservoir_name", how="left")
    else:
        rows["wl_delta_m"] = math.nan
    rows["rapid_rise_alert"] = pd.to_numeric(rows["wl_delta_m"], errors="coerce").fillna(0) >= rapid_rise_m
    rows = rows[(rows["configured_alert"] != "Normal") | rows["rapid_rise_alert"]].copy()
    if rows.empty:
        return rows
    rows["alert_reason"] = rows.apply(
        lambda row: (
            "Rapid rise"
            if bool(row.get("rapid_rise_alert")) and row.get("configured_alert") == "Normal"
            else (
                f"FRL gap {fmt_number(row.get('frl_gap_m'), ' m')}"
                if pd.notna(row.get("frl_gap_m"))
                else f"Filling {fmt_number(row.get('display_filling'), '%')}"
            )
        ),
        axis=1,
    )
    return rows.sort_values(
        by=["configured_alert", "frl_gap_m", "display_filling"],
        ascending=[True, True, False],
    )


def dam_alert_message(row: pd.Series) -> str:
    return (
        "MPWRD Dam Alert\n"
        f"Reservoir: {row.get('reservoir_name') or row.get('dam_name')}\n"
        f"District: {row.get('district') or row.get('map_district') or '-'}\n"
        f"Basin: {row.get('sub_basin') or row.get('major_basin') or '-'}\n"
        f"Current WL: {fmt_number(row.get('water_level_m'), ' m')}\n"
        f"FRL Gap: {fmt_number(row.get('frl_gap_m'), ' m')}\n"
        f"Filling: {fmt_number(row.get('display_filling'), '%')}\n"
        f"Alert Level: {row.get('configured_alert')}\n"
        "Action: Monitor inflow, gates, and downstream warning protocol."
    )


def parse_alert_recipients(recipients_text: str) -> list[dict[str, str]]:
    recipients = []
    for line in recipients_text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        email_match = re.search(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}", raw)
        phone_match = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", raw)
        phone = ""
        if phone_match:
            phone = re.sub(r"\D+", "", phone_match.group(1))
            if len(phone) == 10:
                phone = f"91{phone}"
        email = email_match.group(0) if email_match else ""
        label = raw
        if phone_match:
            label = label.replace(phone_match.group(1), "")
        if email:
            label = label.replace(email, "")
        label = label.strip(" -:,") or raw
        has_phone = bool(phone and len(phone) >= 11)
        has_email = bool(email)
        status = "Ready" if has_phone or has_email else "Missing phone/email"
        if phone and len(phone) < 11:
            status = "Check phone"
        recipients.append({"label": label, "phone": phone, "email": email, "status": status})
    return recipients


def build_alert_test_links(recipients: list[dict[str, str]], message: str, channels: list[str]) -> pd.DataFrame:
    rows = []
    encoded = urllib.parse.quote(message)
    subject = urllib.parse.quote("MPWRD Dam Alert")
    for recipient in recipients:
        phone = recipient.get("phone", "")
        email = recipient.get("email", "")
        if "WhatsApp" in channels:
            rows.append({**recipient, "channel": "WhatsApp", "test_link": f"https://wa.me/{phone}?text={encoded}" if phone else "", "status": recipient.get("status", "Ready") if phone else "Missing phone"})
        if "SMS" in channels:
            rows.append({**recipient, "channel": "SMS", "test_link": f"sms:+{phone}?&body={encoded}" if phone else "", "status": recipient.get("status", "Ready") if phone else "Missing phone"})
        if "Email" in channels:
            rows.append({**recipient, "channel": "Email", "test_link": f"mailto:{email}?subject={subject}&body={encoded}" if email else "", "status": recipient.get("status", "Ready") if email else "Missing email"})
        if not any(channel in channels for channel in ["WhatsApp", "SMS", "Email"]):
            rows.append({**recipient, "channel": "None", "test_link": "", "status": "No channel selected"})
    return pd.DataFrame(rows)


def save_alert_outbox_record(payload: dict) -> Path:
    outbox_dir = APP_DIR / "admin_alert_outbox"
    outbox_dir.mkdir(exist_ok=True)
    timestamp = pd.Timestamp.now(tz="Asia/Kolkata").strftime("%Y%m%d_%H%M%S")
    target = outbox_dir / f"alert_test_{timestamp}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_manual_entry_report(
    report_date: date,
    report_time: time,
    reservoirs_rows: list[dict],
    river_rows: list[dict],
    gate_rows: list[dict],
) -> tuple[Path, dict[str, int]]:
    observed_at = pd.Timestamp.combine(report_date, report_time)
    folder_name = f"manual_entry_{observed_at.strftime('%Y%m%d_%H%M')}"
    output_dir = APP_DIR / folder_name
    output_dir.mkdir(exist_ok=True)
    meta = {
        "report_date": report_date.isoformat(),
        "report_time": report_time.strftime("%H:%M:%S"),
        "season_year": int(report_date.year),
        "source_filename": f"{folder_name}.manual",
        "source_file_hash": "",
        "extraction_method": "manual_admin_entry",
    }
    (output_dir / "report_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    reservoir_obs = pd.DataFrame(reservoirs_rows)
    if reservoir_obs.empty:
        reservoir_obs = pd.DataFrame(columns=["source_row_no", "reservoir_name", "district", "lsl_m", "frl_m", "live_capacity_frl_mcm", "observed_at", "water_level_m", "current_live_capacity_mcm", "filling_percent", "rainfall_daily_mm", "rainfall_total_mm"])
    else:
        reservoir_obs.insert(0, "source_row_no", range(1, len(reservoir_obs) + 1))
        reservoir_obs["observed_at"] = observed_at
    reservoir_obs.to_csv(output_dir / "reservoir_status_observations.csv", index=False)
    reservoir_master_cols = ["reservoir_name", "district", "lsl_m", "frl_m", "live_capacity_frl_mcm", "total_no_of_gates"]
    reservoir_master = reservoir_obs[[col for col in reservoir_master_cols if col in reservoir_obs.columns]].drop_duplicates("reservoir_name") if not reservoir_obs.empty else pd.DataFrame(columns=reservoir_master_cols)
    reservoir_master.to_csv(output_dir / "reservoirs.csv", index=False)

    gates = pd.DataFrame(gate_rows)
    gate_cols = ["source_row_no", "reservoir_name", "district", "total_no_of_gates", "gate_opened_count", "opening_m", "gate_opening_date", "gate_opening_time", "discharge_cumecs", "discharge_cusec"]
    if gates.empty:
        gates = pd.DataFrame(columns=gate_cols)
    else:
        gates.insert(0, "source_row_no", range(1, len(gates) + 1))
    gates.to_csv(output_dir / "reservoir_gate_observations.csv", index=False)

    river_obs = pd.DataFrame(river_rows)
    river_obs_cols = ["source_row_no", "river_name", "gauge_station", "district", "danger_or_max_water_level_m", "observed_at", "water_level_m"]
    if river_obs.empty:
        river_obs = pd.DataFrame(columns=river_obs_cols)
    else:
        river_obs.insert(0, "source_row_no", range(1, len(river_obs) + 1))
        river_obs["observed_at"] = observed_at
    river_obs.to_csv(output_dir / "river_water_level_observations.csv", index=False)
    river_master_cols = ["river_name", "gauge_station", "district", "danger_or_max_water_level_m"]
    river_master = river_obs[[col for col in river_master_cols if col in river_obs.columns]].drop_duplicates("gauge_station") if not river_obs.empty else pd.DataFrame(columns=river_master_cols)
    river_master.to_csv(output_dir / "river_gauge_stations.csv", index=False)

    return output_dir, {
        "reservoir_observation_rows": len(reservoir_obs),
        "gate_observation_rows": len(gates),
        "river_observation_rows": len(river_obs),
    }


def render_admin_operations(is_admin: bool, map_status: pd.DataFrame, parsed_reports: list[Path]) -> None:
    st.subheader("Administration")
    if not is_admin:
        st.info("Administration is locked. Sign in as admin_nitaai to upload PDFs and manage SMS/WhatsApp alert messaging.")
        if not ADMIN_PASSWORD:
            st.warning("Admin access is disabled until MPWRD_ADMIN_PASSWORD or Streamlit secret admin_password is configured.")
            return
        with st.form("admin_page_login_form"):
            username = st.text_input("Admin user", value=ADMIN_USER, key="admin_page_user")
            password = st.text_input("Password", type="password", key="admin_page_password")
            submitted = st.form_submit_button("Unlock Administration", type="primary", use_container_width=True)
        if submitted:
            user_ok = hmac.compare_digest(username.strip(), ADMIN_USER)
            password_ok = bool(password and ADMIN_PASSWORD) and hmac.compare_digest(password, ADMIN_PASSWORD)
            if user_ok and password_ok:
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("Invalid admin credentials.")
        return

    admin_tabs = st.tabs(["PDF Upload & Data Refresh", "Manual Data Entry", "Messaging Alerts", "Audit Log"])
    with admin_tabs[0]:
        st.markdown(
            '<div class="panel-note">Upload official MP WRD flood report PDFs. The parser creates a new parsed report folder that becomes available in the dashboard report selector.</div>',
            unsafe_allow_html=True,
        )
        upload_cols = st.columns([0.58, 0.42])
        with upload_cols[0]:
            uploaded = st.file_uploader("Upload MP WRD flood report PDF", type=["pdf"], key="admin_module_pdf_upload")
            if uploaded is not None:
                saved_pdf = save_uploaded_pdf(uploaded)
                output_dir = APP_DIR / f"parsed_{saved_pdf.stem.replace(' ', '_')}"
                with st.spinner("Parsing uploaded report and refreshing captured tables..."):
                    counts = parse_pdf(saved_pdf, output_dir)
                st.success(
                    f"Captured {counts['river_observation_rows']} river rows, "
                    f"{counts['reservoir_observation_rows']} reservoir rows, "
                    f"and {counts['gate_observation_rows']} gate rows."
                )
                st.session_state.setdefault("admin_audit_log", []).insert(
                    0,
                    {
                        "time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y %I:%M %p"),
                        "module": "PDF Upload",
                        "action": f"Parsed {uploaded.name}",
                        "status": "Completed",
                    },
                )
        with upload_cols[1]:
            st.metric("Parsed Reports", len(parsed_reports))
            st.metric("Mapped Dam Points", int(map_status["dam_name"].dropna().nunique()) if not map_status.empty and "dam_name" in map_status else 0)
            st.caption("After upload, use the sidebar report selector to include the newly parsed report in the active dashboard window.")

        if parsed_reports:
            report_inventory = pd.DataFrame(
                [
                    {
                        "report_folder": report.name,
                        "modified": pd.Timestamp(report.stat().st_mtime, unit="s").strftime("%d %b %Y %I:%M %p"),
                    }
                    for report in parsed_reports
                ]
            ).sort_values("modified", ascending=False)
            st.dataframe(report_inventory, use_container_width=True, hide_index=True, height=220)

    with admin_tabs[1]:
        st.markdown(
            '<div class="panel-note">Use this as a secondary source when a PDF is delayed or OCR needs correction. Saved rows are written in the same parsed-report format as uploaded PDFs.</div>',
            unsafe_allow_html=True,
        )
        entry_meta_cols = st.columns(3)
        with entry_meta_cols[0]:
            manual_date = st.date_input("Report date", value=date.today(), key="manual_report_date")
        with entry_meta_cols[1]:
            manual_time = st.time_input("Report time", value=time(8, 0), key="manual_report_time")
        with entry_meta_cols[2]:
            st.caption("Tip: enter one or many rows, then save. The new manual report appears in the sidebar report selector after refresh.")

        reservoir_options_for_entry = sorted(map_status["reservoir_name"].dropna().unique()) if not map_status.empty and "reservoir_name" in map_status else []
        district_options_for_entry = sorted(
            set(map_status.get("map_district", pd.Series(dtype=str)).dropna().astype(str))
            | set(map_status.get("district", pd.Series(dtype=str)).dropna().astype(str))
        ) if not map_status.empty else []
        reservoir_template = pd.DataFrame(
            [
                {
                    "reservoir_name": reservoir_options_for_entry[0] if reservoir_options_for_entry else "",
                    "district": district_options_for_entry[0] if district_options_for_entry else "",
                    "lsl_m": 0.0,
                    "frl_m": 0.0,
                    "live_capacity_frl_mcm": 0.0,
                    "total_no_of_gates": 0,
                    "water_level_m": 0.0,
                    "current_live_capacity_mcm": 0.0,
                    "filling_percent": 0.0,
                    "rainfall_daily_mm": 0.0,
                    "rainfall_total_mm": 0.0,
                }
            ]
        )
        river_template = pd.DataFrame(
            [
                {
                    "river_name": "",
                    "gauge_station": "",
                    "district": district_options_for_entry[0] if district_options_for_entry else "",
                    "danger_or_max_water_level_m": 0.0,
                    "water_level_m": 0.0,
                }
            ]
        )
        gate_template = pd.DataFrame(
            [
                {
                    "reservoir_name": reservoir_options_for_entry[0] if reservoir_options_for_entry else "",
                    "district": district_options_for_entry[0] if district_options_for_entry else "",
                    "total_no_of_gates": 0,
                    "gate_opened_count": 0,
                    "opening_m": 0.0,
                    "gate_opening_date": manual_date,
                    "gate_opening_time": manual_time.strftime("%H:%M:%S"),
                    "discharge_cumecs": 0.0,
                    "discharge_cusec": 0.0,
                }
            ]
        )
        manual_entry_tabs = st.tabs(["Reservoir Levels", "River Gauges", "Reservoir Gates"])
        reservoir_column_config = {}
        if reservoir_options_for_entry:
            reservoir_column_config["reservoir_name"] = st.column_config.SelectboxColumn("Reservoir", options=reservoir_options_for_entry)
        if district_options_for_entry:
            reservoir_column_config["district"] = st.column_config.SelectboxColumn("District", options=district_options_for_entry)
        reservoir_column_config = friendly_column_config(reservoir_template, reservoir_column_config)
        river_column_config = friendly_column_config(river_template)
        gate_select_config = {}
        if reservoir_options_for_entry:
            gate_select_config["reservoir_name"] = st.column_config.SelectboxColumn("Reservoir", options=reservoir_options_for_entry)
        if district_options_for_entry:
            gate_select_config["district"] = st.column_config.SelectboxColumn("District", options=district_options_for_entry)
        gate_column_config = friendly_column_config(gate_template, gate_select_config)
        with manual_entry_tabs[0]:
            reservoir_entry_df = st.data_editor(
                reservoir_template,
                num_rows="dynamic",
                use_container_width=True,
                key="manual_reservoir_entries",
                column_config=reservoir_column_config,
            )
        with manual_entry_tabs[1]:
            river_entry_df = st.data_editor(
                river_template,
                num_rows="dynamic",
                use_container_width=True,
                key="manual_river_entries",
                column_config=river_column_config,
            )
        with manual_entry_tabs[2]:
            gate_entry_df = st.data_editor(
                gate_template,
                num_rows="dynamic",
                use_container_width=True,
                key="manual_gate_entries",
                column_config=gate_column_config,
            )

        if st.button("Save Manual Entry Report", type="primary", use_container_width=True, key="save_manual_entry_report"):
            reservoir_rows = reservoir_entry_df.dropna(how="all").to_dict("records") if isinstance(reservoir_entry_df, pd.DataFrame) else []
            river_rows = river_entry_df.dropna(how="all").to_dict("records") if isinstance(river_entry_df, pd.DataFrame) else []
            gate_rows = gate_entry_df.dropna(how="all").to_dict("records") if isinstance(gate_entry_df, pd.DataFrame) else []
            output_dir, counts = write_manual_entry_report(manual_date, manual_time, reservoir_rows, river_rows, gate_rows)
            st.session_state.setdefault("admin_audit_log", []).insert(
                0,
                {
                    "time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y %I:%M %p"),
                    "module": "Manual Data Entry",
                    "action": f"Saved {output_dir.name}",
                    "status": f"{counts['reservoir_observation_rows']} reservoir, {counts['river_observation_rows']} river, {counts['gate_observation_rows']} gate rows",
                },
            )
            st.success(f"Manual report saved: {output_dir.name}. Refresh/reselect reports from the sidebar to include it.")

    with admin_tabs[2]:
        st.markdown(
            '<div class="panel-note">Configure alert thresholds and prepare SMS/WhatsApp messages. Delivery is preview/log mode until provider credentials and approved templates are configured in deployment secrets.</div>',
            unsafe_allow_html=True,
        )
        if "alert_test_log" not in st.session_state:
            st.session_state.alert_test_log = []
        threshold_cols = st.columns(4)
        with threshold_cols[0]:
            dam_critical_gap = st.number_input("Critical FRL gap (m)", 0.0, 5.0, float(st.session_state.get("admin_dam_critical_gap", 0.5)), 0.1, key="admin_dam_critical_gap")
        with threshold_cols[1]:
            dam_warning_gap = st.number_input("Warning FRL gap (m)", 0.0, 10.0, float(st.session_state.get("admin_dam_warning_gap", 1.5)), 0.1, key="admin_dam_warning_gap")
        with threshold_cols[2]:
            dam_watch_filling = st.number_input("Watch filling (%)", 0.0, 100.0, float(st.session_state.get("admin_dam_watch_filling", 90.0)), 1.0, key="admin_dam_watch_filling")
        with threshold_cols[3]:
            rapid_rise_threshold = st.number_input("Rapid rise trigger (m/slot)", 0.0, 5.0, float(st.session_state.get("admin_rapid_rise_threshold", 0.30)), 0.05, key="admin_rapid_rise_threshold")

        weather_cols = st.columns(3)
        with weather_cols[0]:
            st.number_input("Extreme 24h rainfall (mm)", 0.0, 500.0, float(st.session_state.get("admin_weather_24h_extreme_mm", 100.0)), 5.0, key="admin_weather_24h_extreme_mm")
        with weather_cols[1]:
            st.number_input("Extreme forecast rain (mm/day)", 0.0, 500.0, float(st.session_state.get("admin_weather_forecast_extreme_mm", 120.0)), 5.0, key="admin_weather_forecast_extreme_mm")
        with weather_cols[2]:
            st.number_input("Extreme wind speed (km/h)", 0.0, 200.0, float(st.session_state.get("admin_weather_wind_extreme_kmh", 50.0)), 5.0, key="admin_weather_wind_extreme_kmh")

        gateway_cols = st.columns([0.32, 0.68])
        with gateway_cols[0]:
            selected_channels = st.multiselect("Alert channels", ["Email", "SMS", "WhatsApp"], default=st.session_state.get("admin_alert_channels", ["Email", "WhatsApp"]), key="admin_alert_channels")
            gateway_mode = st.selectbox("Gateway mode", ["Preview only", "Provider ready"], index=0, key="admin_alert_gateway_mode")
        with gateway_cols[1]:
            recipients_text = st.text_area(
                "Alert recipients",
                value=st.session_state.get("admin_alert_recipients", "Control Room control.room@example.com +91XXXXXXXXXX\nDam Safety Officer dam.safety@example.com +91XXXXXXXXXX"),
                key="admin_alert_recipients",
                height=86,
                help="One recipient per line. Use role/name with email and/or phone number.",
            )

        active_dam_alerts = build_dam_alert_rows(map_status, dam_critical_gap, dam_warning_gap, dam_watch_filling, rapid_rise_threshold)
        alert_kpis = st.columns(4)
        alert_kpis[0].metric("Active Dam Alerts", len(active_dam_alerts))
        alert_kpis[1].metric("Critical", int((active_dam_alerts.get("configured_alert", pd.Series(dtype=str)) == "Critical").sum()) if not active_dam_alerts.empty else 0)
        alert_kpis[2].metric("Warning", int((active_dam_alerts.get("configured_alert", pd.Series(dtype=str)) == "Warning").sum()) if not active_dam_alerts.empty else 0)
        alert_kpis[3].metric("Rapid Rise", int(active_dam_alerts.get("rapid_rise_alert", pd.Series(dtype=bool)).sum()) if not active_dam_alerts.empty else 0)

        if active_dam_alerts.empty:
            st.success("No dam alert exceeds the configured administration thresholds under the current filters.")
        else:
            alert_table_cols = ["reservoir_name", "district", "sub_basin", "observed_at", "water_level_m", "frl_m", "frl_gap_m", "display_filling", "wl_delta_m", "configured_alert", "alert_reason"]
            st.dataframe(active_dam_alerts[[col for col in alert_table_cols if col in active_dam_alerts.columns]], use_container_width=True, hide_index=True, height=230)
            alert_labels = [f"{row.reservoir_name} | {row.configured_alert}" for row in active_dam_alerts.itertuples(index=False)]
            selected_alert_label = st.selectbox("Message preview dam", alert_labels, key="admin_alert_preview_dam")
            selected_alert_row = active_dam_alerts.iloc[alert_labels.index(selected_alert_label)]
            alert_message = st.text_area("Email / SMS / WhatsApp alert message preview", value=dam_alert_message(selected_alert_row), key="admin_alert_message_preview", height=190)
            parsed_recipients = parse_alert_recipients(recipients_text)
            dispatch_links = build_alert_test_links(parsed_recipients, alert_message, selected_channels)
            if parsed_recipients:
                st.caption(f"Parsed {len(parsed_recipients)} recipient(s). Test links open email, WhatsApp Web, or the device SMS app where supported.")
            if not dispatch_links.empty:
                st.dataframe(
                    dispatch_links[["label", "email", "phone", "channel", "status"]],
                    use_container_width=True,
                    hide_index=True,
                    height=150,
                )
            action_cols = st.columns([0.22, 0.78])
            with action_cols[0]:
                if st.button("Create Test Dispatch", type="primary", use_container_width=True, key="admin_record_test_alert"):
                    outbox_payload = {
                        "created_at": pd.Timestamp.now(tz="Asia/Kolkata").isoformat(),
                        "gateway_mode": gateway_mode,
                        "channels": selected_channels,
                        "reservoir": selected_alert_row.get("reservoir_name"),
                        "alert": selected_alert_row.get("configured_alert"),
                        "message": alert_message,
                        "recipients": parsed_recipients,
                        "dispatch_links": dispatch_links.to_dict("records") if not dispatch_links.empty else [],
                    }
                    outbox_path = save_alert_outbox_record(outbox_payload)
                    st.session_state.alert_test_log.insert(
                        0,
                        {
                            "time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y %I:%M %p"),
                            "channels": ", ".join(selected_channels) if selected_channels else "None",
                            "mode": gateway_mode,
                            "reservoir": selected_alert_row.get("reservoir_name"),
                            "alert": selected_alert_row.get("configured_alert"),
                            "recipients": len([line for line in recipients_text.splitlines() if line.strip()]),
                            "status": f"Outbox created: {outbox_path.name}",
                        },
                    )
                    st.session_state.setdefault("admin_audit_log", []).insert(
                        0,
                        {
                            "time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y %I:%M %p"),
                            "module": "Messaging Alerts",
                            "action": f"Recorded {selected_alert_row.get('configured_alert')} alert for {selected_alert_row.get('reservoir_name')}",
                            "status": f"Outbox created: {outbox_path.name}",
                        },
                    )
                    st.success(f"Test dispatch created: {outbox_path.name}")
            with action_cols[1]:
                st.caption(f"Prepared for {gateway_mode}. Message length: {len(alert_message)} characters. Real sending requires SMS/WhatsApp provider credentials.")
                if not dispatch_links.empty:
                    link_items = []
                    for index, row in dispatch_links.head(8).iterrows():
                        if row.get("test_link"):
                            label = f"{row.get('channel')} - {row.get('label') or row.get('phone')}"
                            link_items.append(f'<a href="{escape(str(row.get("test_link")))}" target="_blank">{escape(label)}</a>')
                    if link_items:
                        st.markdown("<br/>".join(link_items), unsafe_allow_html=True)

    with admin_tabs[3]:
        st.markdown('<div class="panel-note">Local administration actions recorded during this browser session.</div>', unsafe_allow_html=True)
        audit_log = pd.DataFrame(st.session_state.get("admin_audit_log", []))
        alert_log = pd.DataFrame(st.session_state.get("alert_test_log", []))
        if not audit_log.empty:
            st.dataframe(audit_log, use_container_width=True, hide_index=True, height=180)
        if not alert_log.empty:
            st.dataframe(alert_log, use_container_width=True, hide_index=True, height=220)
        if audit_log.empty and alert_log.empty:
            st.info("No administration actions have been recorded in this session.")


if "main_dashboard_page" not in st.session_state:
    st.session_state.main_dashboard_page = "Infographics"

nav_pages = ["Infographics", "Dam DSS & Analytics", "Weather Forecast", "3D Flood Scenarios", "Data & Timeseries", "Administration"]
st.markdown('<div class="dashboard-topnav-title">Dashboard Navigation</div>', unsafe_allow_html=True)
nav_cols = st.columns(6)
for nav_col, page in zip(nav_cols, nav_pages):
    if nav_col.button(page, key=f"main_nav_{page}", type="primary" if page == st.session_state.main_dashboard_page else "secondary", use_container_width=True):
        st.session_state.main_dashboard_page = page
        st.rerun()
main_page = st.session_state.main_dashboard_page
st.markdown(f'<div class="dashboard-topnav-active">Active page: <b>{escape(main_page)}</b></div>', unsafe_allow_html=True)

if main_page == "Administration":
    render_admin_operations(is_admin, map_status, dirs)

if main_page == "Dam DSS & Analytics":
    st.subheader("Dam Locations and District Status")
    if map_status.empty:
        st.info("Dam location shapefile is not available or no dam points match the current filters.")
    else:
        district_counts = (
            map_status.assign(district_label=map_status["map_district"].where(map_status["map_district"].str.len() > 0, map_status.get("district", "")))
            .groupby("district_label", as_index=False)
            .agg(
                dams=("dam_name", "nunique"),
                avg_filling=("display_filling", "mean"),
                alerts=("alert_level", lambda values: values.isin(["Critical", "Warning"]).sum()),
            )
            .sort_values(["dams", "avg_filling"], ascending=False)
        )
        latest_map_observed_at = map_status["observed_at"].dropna().max() if "observed_at" in map_status else pd.NaT
        latest_map_label = time_label(latest_map_observed_at) if pd.notna(latest_map_observed_at) else "not available"

        render_arcgis_dam_timeseries_map(map_status, reservoir_view, latest_map_label)
        alert_counts = map_status["alert_level"].value_counts().to_dict()

        controls_left, controls_right = st.columns([0.58, 0.42])
        with controls_left:
            alert_legend_html = f"""
            <div class="alert-legend-panel">
              <b>FRL Alert Legend</b>
              <div><span class="legend-dot" style="background:#ef4444"></span>Critical: FRL gap <= 0.5 m</div>
              <div><span class="legend-dot" style="background:#f59e0b"></span>Warning: <= 1.5 m</div>
              <div><span class="legend-dot" style="background:#eab308"></span>Watch: >= 90% filling</div>
              <div><span class="legend-dot" style="background:#2563eb"></span>Normal</div>
              <div style="margin-top:0.35rem;color:#64748b">
                Current: Critical {alert_counts.get('Critical', 0)}, Warning {alert_counts.get('Warning', 0)}, Watch {alert_counts.get('Watch', 0)}, Normal {alert_counts.get('Normal', 0)}
              </div>
            </div>
            """
            st.markdown(alert_legend_html, unsafe_allow_html=True)
            st.markdown('<div class="panel-note">Hover a dam for water level, alert type, filling percent, and trend. Click a dam or map location to load the nearest GEOGLOWS forecast comparison below the map.</div>', unsafe_allow_html=True)
        show_selected_dam_accelerometer = True
        show_district_accelerometers = False
        if show_selected_dam_accelerometer:
            with controls_right:
                selectable_dams = (
                    map_status.assign(select_label=map_status["reservoir_name"].fillna(map_status["dam_name"]))
                    .dropna(subset=["select_label"])
                    .sort_values("select_label")
                )
                if not selectable_dams.empty:
                    selected_dam_label = st.selectbox(
                        "Selected dam filling",
                        selectable_dams["select_label"].drop_duplicates().tolist(),
                        key="selected_dam_speedometer",
                    )
                    selected_dam = selectable_dams[selectable_dams["select_label"] == selected_dam_label].sort_values("observed_at").tail(1)
                    if not selected_dam.empty:
                        selected_row = selected_dam.iloc[0]
                        selected_gauge_html = (
                            '<div class="selected-dam-panel">'
                            f'<span class="district-gauge-title">{escape(str(selected_dam_label))}</span>'
                            f'{speedometer_svg(selected_row.get("display_filling"), "filled")}'
                            f'<span class="district-gauge-meta">WL {fmt_number(selected_row.get("water_level_m"), " m")} | '
                            f'FRL gap {fmt_number(selected_row.get("frl_gap_m"), " m")} | '
                            f'{escape(str(selected_row.get("alert_level", "Normal")))} alert</span>'
                            '</div>'
                        )
                        st.markdown(selected_gauge_html, unsafe_allow_html=True)

        st.subheader("Alert DSS Administration")
        if "alert_test_log" not in st.session_state:
            st.session_state.alert_test_log = []
        if not is_admin:
            st.info("Alert configuration is restricted to administration users. Sign in from the sidebar to manage SMS/WhatsApp alert rules and recipients.")
        else:
            st.markdown(
                '<div class="panel-note">Configure operational thresholds and prepare SMS/WhatsApp alert messages. Sending remains in test/preview mode until a gateway provider is connected.</div>',
                unsafe_allow_html=True,
            )
            alert_settings = st.columns(4)
            with alert_settings[0]:
                dam_critical_gap = st.number_input(
                    "Critical FRL gap (m)",
                    min_value=0.0,
                    max_value=5.0,
                    value=float(st.session_state.get("dam_critical_gap", 0.5)),
                    step=0.1,
                    key="dam_critical_gap",
                    help="Dam alert becomes Critical when current water level is this close to FRL.",
                )
            with alert_settings[1]:
                dam_warning_gap = st.number_input(
                    "Warning FRL gap (m)",
                    min_value=0.0,
                    max_value=10.0,
                    value=float(st.session_state.get("dam_warning_gap", 1.5)),
                    step=0.1,
                    key="dam_warning_gap",
                )
            with alert_settings[2]:
                dam_watch_filling = st.number_input(
                    "Watch filling (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(st.session_state.get("dam_watch_filling", 90.0)),
                    step=1.0,
                    key="dam_watch_filling",
                )
            with alert_settings[3]:
                rapid_rise_threshold = st.number_input(
                    "Rapid rise trigger (m/slot)",
                    min_value=0.0,
                    max_value=5.0,
                    value=float(st.session_state.get("rapid_rise_threshold", 0.30)),
                    step=0.05,
                    key="rapid_rise_threshold",
                    help="Flags dams where the latest report slot rose by this many metres from the previous slot.",
                )

            weather_settings = st.columns(3)
            with weather_settings[0]:
                st.number_input(
                    "Extreme 24h rainfall (mm)",
                    min_value=0.0,
                    max_value=500.0,
                    value=float(st.session_state.get("weather_24h_extreme_mm", 100.0)),
                    step=5.0,
                    key="weather_24h_extreme_mm",
                    help="Used by the Weather Forecast page for future automatic alert triggering.",
                )
            with weather_settings[1]:
                st.number_input(
                    "Extreme forecast rain (mm/day)",
                    min_value=0.0,
                    max_value=500.0,
                    value=float(st.session_state.get("weather_forecast_extreme_mm", 120.0)),
                    step=5.0,
                    key="weather_forecast_extreme_mm",
                )
            with weather_settings[2]:
                st.number_input(
                    "Extreme wind speed (km/h)",
                    min_value=0.0,
                    max_value=200.0,
                    value=float(st.session_state.get("weather_wind_extreme_kmh", 50.0)),
                    step=5.0,
                    key="weather_wind_extreme_kmh",
                )

            channel_cols = st.columns([0.32, 0.68])
            with channel_cols[0]:
                selected_channels = st.multiselect(
                    "Alert channels",
                    ["SMS", "WhatsApp"],
                    default=st.session_state.get("alert_channels", ["SMS", "WhatsApp"]),
                    key="alert_channels",
                )
                gateway_mode = st.selectbox(
                    "Gateway mode",
                    ["Preview only", "Provider ready"],
                    index=0,
                    key="alert_gateway_mode",
                    help="Provider ready preserves configuration screens but does not send until gateway credentials are added in deployment secrets.",
                )
            with channel_cols[1]:
                recipients_text = st.text_area(
                    "Alert recipients",
                    value=st.session_state.get("alert_recipients", "Control Room +91XXXXXXXXXX\nDam Safety Officer +91XXXXXXXXXX"),
                    key="alert_recipients",
                    height=86,
                    help="One recipient per line. Use role/name and phone number. Real delivery will require an approved SMS/WhatsApp gateway.",
                )

            active_dam_alerts = build_dam_alert_rows(
                map_status,
                dam_critical_gap,
                dam_warning_gap,
                dam_watch_filling,
                rapid_rise_threshold,
            )
            alert_kpis = st.columns(4)
            alert_kpis[0].metric("Active Dam Alerts", len(active_dam_alerts))
            alert_kpis[1].metric("Critical", int((active_dam_alerts.get("configured_alert", pd.Series(dtype=str)) == "Critical").sum()) if not active_dam_alerts.empty else 0)
            alert_kpis[2].metric("Warning", int((active_dam_alerts.get("configured_alert", pd.Series(dtype=str)) == "Warning").sum()) if not active_dam_alerts.empty else 0)
            alert_kpis[3].metric("Rapid Rise", int(active_dam_alerts.get("rapid_rise_alert", pd.Series(dtype=bool)).sum()) if not active_dam_alerts.empty else 0)

            if active_dam_alerts.empty:
                st.success("No dam alert exceeds the configured administration thresholds under the current dashboard filters.")
            else:
                alert_table_cols = [
                    "reservoir_name",
                    "district",
                    "sub_basin",
                    "observed_at",
                    "water_level_m",
                    "frl_m",
                    "frl_gap_m",
                    "display_filling",
                    "wl_delta_m",
                    "configured_alert",
                    "alert_reason",
                ]
                display_alerts = active_dam_alerts[[col for col in alert_table_cols if col in active_dam_alerts.columns]].copy()
                st.dataframe(display_alerts, use_container_width=True, hide_index=True, height=230)
                alert_labels = [
                    f"{row.reservoir_name} | {row.configured_alert}"
                    for row in active_dam_alerts.itertuples(index=False)
                ]
                selected_alert_label = st.selectbox(
                    "Message preview dam",
                    alert_labels,
                    key="alert_preview_dam",
                )
                selected_alert_row = active_dam_alerts.iloc[alert_labels.index(selected_alert_label)]
                default_message = dam_alert_message(selected_alert_row)
                alert_message = st.text_area(
                    "SMS / WhatsApp alert message preview",
                    value=default_message,
                    key="alert_message_preview",
                    height=190,
                )
                test_cols = st.columns([0.25, 0.75])
                with test_cols[0]:
                    if st.button("Record Test Alert", type="primary", use_container_width=True, key="record_test_alert"):
                        st.session_state.alert_test_log.insert(
                            0,
                            {
                                "time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y %I:%M %p"),
                                "channels": ", ".join(selected_channels) if selected_channels else "None",
                                "mode": gateway_mode,
                                "reservoir": selected_alert_row.get("reservoir_name"),
                                "alert": selected_alert_row.get("configured_alert"),
                                "recipients": len([line for line in recipients_text.splitlines() if line.strip()]),
                                "status": "Preview logged",
                            },
                        )
                        st.success("Test alert recorded in local administration log.")
                with test_cols[1]:
                    st.caption("Real SMS/WhatsApp delivery will be enabled after gateway credentials, approved WhatsApp templates, and recipient governance are configured.")

            if st.session_state.alert_test_log:
                st.dataframe(pd.DataFrame(st.session_state.alert_test_log), use_container_width=True, hide_index=True, height=180)

        if show_district_accelerometers:
            strip_html = '<div class="district-strip">'
            for row in district_counts.head(10).itertuples(index=False):
                gauge_label = f"{int(row.dams)} dams"
                strip_html += (
                    '<div class="district-gauge-card">'
                    f'<span class="district-gauge-title">{escape(str(row.district_label))}</span>'
                    f'{speedometer_svg(row.avg_filling, gauge_label)}'
                    f'<span class="district-gauge-meta">Avg filling {row.avg_filling:,.1f}% | alerts {int(row.alerts)}</span>'
                    '</div>'
                )
            strip_html += "</div>"
            st.markdown(strip_html, unsafe_allow_html=True)

        show_dam_filling_gauge_chart = False
        if show_dam_filling_gauge_chart:
            gauge_districts = sorted(map_status["map_district"].dropna().unique())
            selected_gauge_district = st.selectbox(
                "Dam filling gauges by district",
                ["Top filled dams"] + gauge_districts,
                key="dam_gauge_district",
            )
            gauge_base = map_status.dropna(subset=["reservoir_name"]).copy()
            if selected_gauge_district != "Top filled dams":
                gauge_base = gauge_base[gauge_base["map_district"] == selected_gauge_district]
            gauge_source = gauge_base.sort_values("display_filling", ascending=False).head(16)[
                ["dam_name", "reservoir_name", "map_district", "display_filling", "frl_gap_m", "alert_level"]
            ]
            if not gauge_source.empty:
                gauge_chart = (
                    alt.Chart(gauge_source)
                    .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                    .encode(
                        x=alt.X("display_filling:Q", title="Filling %", scale=alt.Scale(domain=[0, 100])),
                        y=alt.Y("dam_name:N", sort="-x", title="Dam"),
                        color=alt.Color(
                            "display_filling:Q",
                            scale=alt.Scale(domain=[0, 45, 75, 100], range=["#2563eb", "#06b6d4", "#f59e0b", "#ef4444"]),
                            legend=None,
                        ),
                        tooltip=["dam_name", "reservoir_name", "map_district", "display_filling", "frl_gap_m", "alert_level"],
                    )
                    .properties(height=220)
                )
                st.altair_chart(gauge_chart, use_container_width=True)

        st.subheader("GloFAS Forecast")
        dynamic_mode = forecast_data_mode == "Full dynamic mode"
        if dynamic_mode:
            glofas_nodes, glofas_error = fetch_dynamic_nodes(glofas_endpoint, "GloFAS")
        else:
            glofas_nodes, glofas_error = build_mp_glofas_nodes(map_status, reservoir_view, forecast_days=10), None
        if not glofas_nodes:
            if dynamic_mode and glofas_error == "endpoint_not_configured":
                st.warning("Full dynamic GloFAS mode is active. Configure a live/preprocessed GloFAS endpoint in the sidebar to show forecast nodes.")
            elif dynamic_mode and glofas_error:
                st.error(glofas_error)
            else:
                st.info("No mapped MP basin locations are available for GloFAS context under the current filters.")
        else:
            live_mode = dynamic_mode
            risk_counts = pd.Series([node["risk_band"] for node in glofas_nodes]).value_counts().to_dict()
            highest_node = sorted(
                glofas_nodes,
                key=lambda item: {"Danger": 0, "Flood": 1, "Watch": 2, "Normal": 3}.get(item["risk_band"], 4),
            )[0]
            st.markdown(
                f"""
                <div class="glofas-status-grid">
                  <div class="glofas-card"><span>Source Mode</span><b>{'Full dynamic endpoint' if live_mode else 'Fallback/demo mode'}</b></div>
                  <div class="glofas-card"><span>MP Basin Nodes</span><b>{len(glofas_nodes)}</b></div>
                  <div class="glofas-card"><span>Highest Risk</span><b style="color:{risk_color(highest_node['risk_band'])}">{escape(highest_node['risk_band'])}</b></div>
                  <div class="glofas-card"><span>Forecast Lead</span><b>10 days</b></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if live_mode:
                st.caption("Full dynamic GloFAS mode is active. Rows are read from the configured endpoint and normalized into the dashboard schema.")
            else:
                st.caption("Fallback/demo mode is active. Switch Forecast Mode to Full dynamic mode and configure an endpoint to disable fallback data.")

            glofas_labels = [f"{node['basin']} | {node['risk_band']}" for node in glofas_nodes]
            selected_glofas_label = st.selectbox("GloFAS MP basin node", glofas_labels, key="selected_glofas_node")
            selected_glofas = glofas_nodes[glofas_labels.index(selected_glofas_label)]
            glofas_rows = pd.DataFrame(selected_glofas["series"])
            for column in ["chirps_hindcast_cms", "glofas_p10_cms", "glofas_p50_cms", "glofas_p90_cms", "reservoir_attenuated_cms", "return_period"]:
                if column in glofas_rows:
                    glofas_rows[column] = pd.to_numeric(glofas_rows[column], errors="coerce")
            glofas_rows["date"] = pd.to_datetime(glofas_rows["date"], errors="coerce")
            thresholds = selected_glofas["thresholds"]
            threshold_df = pd.DataFrame(
                [
                    {"level": "Watch", "flow_cms": thresholds["watch_cms"]},
                    {"level": "Flood", "flow_cms": thresholds["flood_cms"]},
                    {"level": "Danger", "flow_cms": thresholds["danger_cms"]},
                ]
            )
            glofas_left, glofas_right = st.columns([1.2, 0.8])
            with glofas_left:
                ensemble_base = glofas_rows.melt(
                    id_vars=["date", "period"],
                    value_vars=["glofas_p10_cms", "glofas_p50_cms", "glofas_p90_cms", "reservoir_attenuated_cms"],
                    var_name="series",
                    value_name="flow_cms",
                ).dropna(subset=["flow_cms"])
                line_chart = (
                    alt.Chart(ensemble_base)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("date:T", title="Forecast date"),
                        y=alt.Y("flow_cms:Q", title="Discharge (cumecs)"),
                        color=alt.Color(
                            "series:N",
                            title="GloFAS series",
                            scale=alt.Scale(
                                domain=["glofas_p10_cms", "glofas_p50_cms", "glofas_p90_cms", "reservoir_attenuated_cms"],
                                range=["#60a5fa", "#dc2626", "#7c3aed", "#0f766e"],
                            ),
                        ),
                        strokeDash=alt.StrokeDash("period:N", title="Period"),
                        tooltip=["date", "period", "series", "flow_cms"],
                    )
                    .properties(height=285)
                )
                rules = (
                    alt.Chart(threshold_df)
                    .mark_rule(strokeDash=[6, 4])
                    .encode(
                        y="flow_cms:Q",
                        color=alt.Color(
                            "level:N",
                            scale=alt.Scale(domain=["Watch", "Flood", "Danger"], range=["#f59e0b", "#f97316", "#dc2626"]),
                            title="Threshold",
                        ),
                        tooltip=["level", "flow_cms"],
                    )
                )
                st.altair_chart(line_chart + rules, use_container_width=True)
            with glofas_right:
                st.markdown(
                    f"""
                    <div class="selected-dam-panel">
                        <span class="district-gauge-title">{escape(selected_glofas['basin'])}</span>
                        <span class="district-gauge-meta">Risk band: <b style="color:{risk_color(selected_glofas['risk_band'])}">{escape(selected_glofas['risk_band'])}</b></span>
                        <span class="district-gauge-meta">Dams represented: {selected_glofas['dam_count']} | Avg filling {selected_glofas['avg_filling']:.1f}%</span>
                        <span class="district-gauge-meta">Storage context: {selected_glofas['storage_mcm']:,.0f} MCM | Location {selected_glofas['latitude']:.3f}, {selected_glofas['longitude']:.3f}</span>
                        <span class="district-gauge-meta">Watch {thresholds['watch_cms']:,.0f}, Flood {thresholds['flood_cms']:,.0f}, Danger {thresholds['danger_cms']:,.0f} cumecs</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                display_cols = [
                    "date",
                    "period",
                    "glofas_p10_cms",
                    "glofas_p50_cms",
                    "glofas_p90_cms",
                    "reservoir_attenuated_cms",
                    "return_period",
                ]
                display_rows = glofas_rows[display_cols].copy()
                display_rows["return_period"] = display_rows["return_period"].apply(return_period_label)
                st.dataframe(display_rows, use_container_width=True, hide_index=True, height=285)

        st.subheader("GRRR for Basins")
        if dynamic_mode:
            grrr_nodes, grrr_error = fetch_dynamic_nodes(grrr_endpoint, "GRRR")
        else:
            grrr_nodes, grrr_error = build_mp_grrr_nodes(map_status, reservoir_view, forecast_days=7), None
        if not grrr_nodes:
            if dynamic_mode and grrr_error == "endpoint_not_configured":
                st.warning("Full dynamic GRRR mode is active. Configure a published GRRR JSON/API endpoint in the sidebar to show runoff nodes.")
            elif dynamic_mode and grrr_error:
                st.error(grrr_error)
            else:
                st.info("No mapped MP basin locations are available for GRRR runoff context under the current filters.")
        else:
            grrr_live_mode = dynamic_mode
            grrr_highest = sorted(
                grrr_nodes,
                key=lambda item: {"Danger": 0, "Flood": 1, "Watch": 2, "Normal": 3}.get(item["risk_band"], 4),
            )[0]
            st.markdown(
                f"""
                <div class="glofas-status-grid">
                  <div class="glofas-card"><span>Source Mode</span><b>{'Full dynamic endpoint' if grrr_live_mode else 'Fallback/demo mode'}</b></div>
                  <div class="glofas-card"><span>MP Runoff Nodes</span><b>{len(grrr_nodes)}</b></div>
                  <div class="glofas-card"><span>Highest Risk</span><b style="color:{risk_color(grrr_highest['risk_band'])}">{escape(grrr_highest['risk_band'])}</b></div>
                  <div class="glofas-card"><span>Reforecast Lead</span><b>7 days</b></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if grrr_live_mode:
                st.caption("Full dynamic GRRR mode is active. Rows are read from the configured endpoint and normalized into the dashboard schema.")
            else:
                st.caption("Fallback/demo mode is active. Switch Forecast Mode to Full dynamic mode and configure an endpoint to disable fallback data.")

            grrr_labels = [f"{node['basin']} | {node['risk_band']}" for node in grrr_nodes]
            selected_grrr_label = st.selectbox("GRRR MP runoff node", grrr_labels, key="selected_grrr_node")
            selected_grrr = grrr_nodes[grrr_labels.index(selected_grrr_label)]
            grrr_rows = pd.DataFrame(selected_grrr["series"])
            for column in ["runoff_mm", "reanalysis_discharge_cms", "reforecast_p50_cms", "reforecast_p90_cms", "reservoir_adjusted_cms"]:
                grrr_rows[column] = pd.to_numeric(grrr_rows[column], errors="coerce")
            grrr_rows["date"] = pd.to_datetime(grrr_rows["date"], errors="coerce")
            grrr_thresholds = selected_grrr["thresholds"]
            grrr_threshold_df = pd.DataFrame(
                [
                    {"level": "Watch", "flow_cms": grrr_thresholds["watch_cms"]},
                    {"level": "Flood", "flow_cms": grrr_thresholds["flood_cms"]},
                    {"level": "Danger", "flow_cms": grrr_thresholds["danger_cms"]},
                ]
            )
            grrr_left, grrr_right = st.columns([1.2, 0.8])
            with grrr_left:
                grrr_long = grrr_rows.melt(
                    id_vars=["date", "period"],
                    value_vars=["reanalysis_discharge_cms", "reforecast_p50_cms", "reforecast_p90_cms", "reservoir_adjusted_cms"],
                    var_name="series",
                    value_name="flow_cms",
                ).dropna(subset=["flow_cms"])
                grrr_chart = (
                    alt.Chart(grrr_long)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("date:T", title="Date"),
                        y=alt.Y("flow_cms:Q", title="Runoff-derived discharge (cumecs)"),
                        color=alt.Color(
                            "series:N",
                            title="GRRR series",
                            scale=alt.Scale(
                                domain=["reanalysis_discharge_cms", "reforecast_p50_cms", "reforecast_p90_cms", "reservoir_adjusted_cms"],
                                range=["#0ea5e9", "#111827", "#dc2626", "#0f766e"],
                            ),
                        ),
                        strokeDash=alt.StrokeDash("period:N", title="Mode"),
                        tooltip=["date", "period", "series", "flow_cms"],
                    )
                    .properties(height=285)
                )
                grrr_rules = (
                    alt.Chart(grrr_threshold_df)
                    .mark_rule(strokeDash=[6, 4])
                    .encode(
                        y="flow_cms:Q",
                        color=alt.Color(
                            "level:N",
                            scale=alt.Scale(domain=["Watch", "Flood", "Danger"], range=["#f59e0b", "#f97316", "#dc2626"]),
                            title="Threshold",
                        ),
                        tooltip=["level", "flow_cms"],
                    )
                )
                st.altair_chart(grrr_chart + grrr_rules, use_container_width=True)
            with grrr_right:
                st.markdown(
                    f"""
                    <div class="selected-dam-panel">
                        <span class="district-gauge-title">{escape(selected_grrr['basin'])}</span>
                        <span class="district-gauge-meta">Risk band: <b style="color:{risk_color(selected_grrr['risk_band'])}">{escape(selected_grrr['risk_band'])}</b></span>
                        <span class="district-gauge-meta">Dams represented: {selected_grrr['dam_count']} | Rainfall signal {selected_grrr['avg_rainfall_mm']:.1f} mm</span>
                        <span class="district-gauge-meta">Catchment proxy: {selected_grrr['catchment_proxy_sq_km']:,.0f} sq.km | Location {selected_grrr['latitude']:.3f}, {selected_grrr['longitude']:.3f}</span>
                        <span class="district-gauge-meta">Watch {grrr_thresholds['watch_cms']:,.0f}, Flood {grrr_thresholds['flood_cms']:,.0f}, Danger {grrr_thresholds['danger_cms']:,.0f} cumecs</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.dataframe(grrr_rows, use_container_width=True, hide_index=True, height=285)


if main_page == "Weather Forecast":
    st.subheader("Weather Forecast")
    towns = read_csv(MP_TOWNS_CSV)
    if towns.empty:
        st.info("No MP towns master data is available. Add data/mp_towns.csv to enable town-wise weather forecasting.")
    else:
        towns["latitude"] = pd.to_numeric(towns["latitude"], errors="coerce")
        towns["longitude"] = pd.to_numeric(towns["longitude"], errors="coerce")
        towns = towns.dropna(subset=["latitude", "longitude"]).sort_values(["district", "town_name"]).reset_index(drop=True)
        weather_top = st.columns([0.42, 0.58])
        with weather_top[0]:
            district_filter_options = ["All districts"] + sorted(towns["district"].dropna().unique())
            selected_weather_district = st.selectbox("Weather district", district_filter_options, key="weather_district_filter")
        town_options_df = towns if selected_weather_district == "All districts" else towns[towns["district"] == selected_weather_district]
        town_labels = [
            f"{row.town_name} | {row.district}"
            for row in town_options_df.itertuples(index=False)
        ]
        if not town_labels:
            st.warning("No towns are available for the selected district.")
        else:
            with weather_top[1]:
                selected_town_label = st.selectbox("Town weather point", town_labels, key="selected_weather_town")
            selected_town_name = selected_town_label.split(" | ", 1)[0]
            selected_town = town_options_df[town_options_df["town_name"] == selected_town_name].iloc[0]
            daily_weather, hourly_weather, current_weather, weather_error = fetch_open_meteo_weather(
                float(selected_town["latitude"]),
                float(selected_town["longitude"]),
            )
            if weather_error:
                st.error(weather_error)
            elif daily_weather.empty:
                st.warning("Weather service returned no daily weather rows for the selected town.")
            else:
                forecast_daily = daily_weather[daily_weather["period"] == "Forecast"].head(7).copy()
                hindcast_daily = daily_weather[daily_weather["period"] == "Hindcast"].copy()
                if forecast_daily.empty:
                    forecast_daily = daily_weather.tail(7).copy()
                latest_forecast = forecast_daily.iloc[0]
                forecast_rain_total = pd.to_numeric(forecast_daily.get("precipitation_sum"), errors="coerce").sum()
                hindcast_rain_total = pd.to_numeric(hindcast_daily.get("precipitation_sum"), errors="coerce").sum()
                forecast_temp_max = pd.to_numeric(forecast_daily.get("temperature_2m_max"), errors="coerce").max()
                forecast_temp_min = pd.to_numeric(forecast_daily.get("temperature_2m_min"), errors="coerce").min()
                forecast_wind_max = pd.to_numeric(forecast_daily.get("wind_speed_10m_max"), errors="coerce").max()
                forecast_uv_max = pd.to_numeric(forecast_daily.get("uv_index_max"), errors="coerce").max()
                wettest_day = forecast_daily.sort_values("precipitation_sum", ascending=False).iloc[0]
                selected_weather_risk = weather_risk_label(forecast_rain_total, forecast_wind_max, forecast_uv_max)
                current_row = current_weather.iloc[0].to_dict() if not current_weather.empty else {}
                current_time = current_row.get("datetime")
                current_time_label = (
                    pd.Timestamp(current_time).strftime("%d %b %Y, %I:%M %p")
                    if pd.notna(current_time)
                    else "Latest weather model step"
                )
                past_24h_rainfall = math.nan
                past_24h_window_label = "Rolling hourly sum"
                if not hourly_weather.empty and {"datetime", "precipitation"}.issubset(hourly_weather.columns):
                    hourly_recent = hourly_weather[["datetime", "precipitation"]].copy()
                    hourly_recent["datetime"] = pd.to_datetime(hourly_recent["datetime"], errors="coerce")
                    hourly_recent["precipitation"] = pd.to_numeric(hourly_recent["precipitation"], errors="coerce")
                    window_end = pd.Timestamp(current_time).tz_localize(None) if pd.notna(current_time) else hourly_recent["datetime"].dropna().max()
                    if pd.notna(window_end):
                        window_start = window_end - pd.Timedelta(hours=24)
                        past_24h_rows = hourly_recent[
                            (hourly_recent["datetime"] > window_start)
                            & (hourly_recent["datetime"] <= window_end)
                        ]
                        past_24h_rainfall = past_24h_rows["precipitation"].sum()
                        past_24h_window_label = f"{window_start.strftime('%d %b %I:%M %p')} to {window_end.strftime('%d %b %I:%M %p')}"

                summary_towns = towns.copy()
                summary_towns["forecast_rain_mm"] = 0.0
                summary_towns["forecast_temp_max_c"] = 0.0
                summary_towns["forecast_wind_max_kmh"] = 0.0
                summary_towns["forecast_uv_max"] = 0.0
                summary_towns["weather_risk"] = "Low"
                selected_mask = summary_towns["town_name"] == selected_town_name
                summary_towns.loc[selected_mask, "forecast_rain_mm"] = forecast_rain_total
                summary_towns.loc[selected_mask, "forecast_temp_max_c"] = forecast_temp_max
                summary_towns.loc[selected_mask, "forecast_wind_max_kmh"] = forecast_wind_max
                summary_towns.loc[selected_mask, "forecast_uv_max"] = forecast_uv_max
                summary_towns.loc[selected_mask, "weather_risk"] = selected_weather_risk

                st.markdown(
                    f"""
                    <div class="infographic-frame">
                        <div class="infographic-title">Weather Data: {escape(str(selected_town['town_name']))}</div>
                        <div class="infographic-subtitle">7-day forecast and 3-month hindcast in SI units. Location: {float(selected_town['latitude']):.4f}, {float(selected_town['longitude']):.4f} | District: {escape(str(selected_town['district']))}</div>
                        <div class="infographic-grid">
                            <div class="infographic-card"><span>Forecast Temp Range</span><b>{fmt_number(forecast_temp_min, " deg C")} - {fmt_number(forecast_temp_max, " deg C")}</b><small>7-day min/max envelope</small></div>
                            <div class="infographic-card"><span>7-Day Precipitation</span><b>{fmt_number(forecast_rain_total, " mm")}</b><small>Rain + showers + snow</small></div>
                            <div class="infographic-card"><span>Max Wind Speed</span><b>{fmt_number(forecast_wind_max, " km/h")}</b><small>10 m wind, SI display</small></div>
                            <div class="infographic-card"><span>Max UV Index</span><b>{fmt_number(forecast_uv_max, "")}</b><small>Daily maximum UV risk</small></div>
                            <div class="infographic-card"><span>Wettest Forecast Day</span><b>{pd.Timestamp(wettest_day['date']).strftime('%d %b')}</b><small>{fmt_number(wettest_day.get('precipitation_sum'), ' mm')} expected</small></div>
                            <div class="infographic-card"><span>92-Day Hindcast Rain</span><b>{fmt_number(hindcast_rain_total, " mm")}</b><small>Past daily weather sequence</small></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(
                    f"""
                    <div class="infographic-frame">
                        <div class="infographic-title">Current Weather: {escape(str(selected_town['town_name']))}</div>
                        <div class="infographic-subtitle">Current conditions from 15-minute model data. Updated: {escape(str(current_time_label))}</div>
                        <div class="infographic-grid">
                            <div class="infographic-card"><span>Temperature</span><b>{fmt_number(current_row.get('temperature_2m'), " deg C")}</b><small>2 m air temperature</small></div>
                            <div class="infographic-card"><span>Feels Like</span><b>{fmt_number(current_row.get('apparent_temperature'), " deg C")}</b><small>Apparent temperature</small></div>
                            <div class="infographic-card"><span>Humidity</span><b>{fmt_number(current_row.get('relative_humidity_2m'), "%")}</b><small>Relative humidity at 2 m</small></div>
                            <div class="infographic-card"><span>Current Rainfall</span><b>{fmt_number(current_row.get('precipitation'), " mm")}</b><small>Rain + showers + snow</small></div>
                            <div class="infographic-card"><span>Past 24h Rainfall</span><b>{fmt_number(past_24h_rainfall, " mm")}</b><small>{escape(past_24h_window_label)}</small></div>
                            <div class="infographic-card"><span>Cloud Cover</span><b>{fmt_number(current_row.get('cloud_cover'), "%")}</b><small>Total cloud cover</small></div>
                            <div class="infographic-card"><span>Wind</span><b>{fmt_number(current_row.get('wind_speed_10m'), " km/h")}</b><small>Gust {fmt_number(current_row.get('wind_gusts_10m'), " km/h")} | Direction {fmt_number(current_row.get('wind_direction_10m'), " deg")}</small></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                weather_tile_api_key = get_app_secret("openweather_api_key", "OPENWEATHER_API_KEY", "")
                weather_district_geojson = load_light_district_geojson(str(MP_DISTRICTS_GEOJSON))
                render_weather_town_leaflet_map(
                    summary_towns,
                    selected_town_name,
                    weather_tile_api_key,
                    weather_district_geojson,
                )

                weather_cols = st.columns([1.05, 0.95])
                with weather_cols[0]:
                    temp_long = forecast_daily.melt(
                        id_vars=["date"],
                        value_vars=["temperature_2m_min", "temperature_2m_mean", "temperature_2m_max"],
                        var_name="series",
                        value_name="temperature_c",
                    )
                    temp_chart = (
                        alt.Chart(temp_long)
                        .mark_line(point=True)
                        .encode(
                            x=alt.X("date:T", title="Forecast date"),
                            y=alt.Y("temperature_c:Q", title="Temperature ( deg C)"),
                            color=alt.Color(
                                "series:N",
                                title="Temperature",
                                scale=alt.Scale(
                                    domain=["temperature_2m_min", "temperature_2m_mean", "temperature_2m_max"],
                                    range=["#2563eb", "#14b8a6", "#ef4444"],
                                ),
                            ),
                            tooltip=["date", "series", "temperature_c"],
                        )
                        .properties(height=285, title="7-Day Temperature Forecast")
                    )
                    st.altair_chart(temp_chart, use_container_width=True)
                with weather_cols[1]:
                    precip_base = (
                        alt.Chart(forecast_daily)
                        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                        .encode(
                            x=alt.X("date:T", title="Forecast date"),
                            y=alt.Y("precipitation_sum:Q", title="Precipitation (mm)"),
                            color=alt.value("#2563eb"),
                            tooltip=[
                                alt.Tooltip("date:T", title="Forecast date"),
                                alt.Tooltip("precipitation_sum:Q", title="Forecast rainfall (mm)", format=".2f"),
                                alt.Tooltip("rain_sum:Q", title="Rain (mm)", format=".2f"),
                                alt.Tooltip("showers_sum:Q", title="Showers (mm)", format=".2f"),
                                alt.Tooltip("snowfall_sum:Q", title="Snowfall (mm)", format=".2f"),
                            ],
                        )
                    )
                    precip_layers = [precip_base]
                    if pd.notna(past_24h_rainfall):
                        past_24h_chart_df = pd.DataFrame(
                            [{"rainfall_mm": past_24h_rainfall, "series": "Past 24h current rainfall"}]
                        )
                        precip_layers.append(
                            alt.Chart(past_24h_chart_df)
                            .mark_rule(color="#f97316", strokeDash=[7, 4], size=2.5)
                            .encode(
                                y=alt.Y("rainfall_mm:Q"),
                                tooltip=[
                                    alt.Tooltip("series:N", title="Series"),
                                    alt.Tooltip("rainfall_mm:Q", title="Rainfall (mm)", format=".2f"),
                                ],
                            )
                        )
                    precip_chart = (
                        alt.layer(*precip_layers)
                        .properties(
                            height=285,
                            title="7-Day Precipitation Forecast with Past 24h Current Rainfall",
                        )
                    )
                    st.altair_chart(precip_chart, use_container_width=True)

                weather_cols_2 = st.columns([1.0, 1.0])
                with weather_cols_2[0]:
                    wind_uv = forecast_daily.melt(
                        id_vars=["date"],
                        value_vars=["wind_speed_10m_max", "uv_index_max"],
                        var_name="metric",
                        value_name="value",
                    )
                    wind_uv_chart = (
                        alt.Chart(wind_uv)
                        .mark_line(point=True)
                        .encode(
                            x=alt.X("date:T", title="Forecast date"),
                            y=alt.Y("value:Q", title="Value"),
                            color=alt.Color(
                                "metric:N",
                                title="Metric",
                                scale=alt.Scale(domain=["wind_speed_10m_max", "uv_index_max"], range=["#0ea5e9", "#f59e0b"]),
                            ),
                            tooltip=["date", "metric", "value"],
                        )
                        .properties(height=255, title="Wind Speed and UV Index")
                    )
                    st.altair_chart(wind_uv_chart, use_container_width=True)
                with weather_cols_2[1]:
                    if not hindcast_daily.empty:
                        hindcast_chart = (
                            alt.Chart(hindcast_daily)
                            .mark_area(line=True, opacity=0.3, color="#2563eb")
                            .encode(
                                x=alt.X("date:T", title="Hindcast date"),
                                y=alt.Y("precipitation_sum:Q", title="Daily precipitation (mm)"),
                                tooltip=["date", "precipitation_sum", "temperature_2m_mean", "wind_speed_10m_max"],
                            )
                            .properties(height=255, title="3-Month Hindcast Precipitation")
                        )
                        st.altair_chart(hindcast_chart, use_container_width=True)

                st.dataframe(
                    forecast_daily[
                        [
                            "date",
                            "temperature_2m_min",
                            "temperature_2m_mean",
                            "temperature_2m_max",
                            "precipitation_sum",
                            "rain_sum",
                            "showers_sum",
                            "snowfall_sum",
                            "wind_speed_10m_max",
                            "uv_index_max",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    height=260,
                )


if main_page == "3D Flood Scenarios":
    st.subheader("3D Flood Scenarios")
    st.markdown(
        '<div class="panel-note">ArcGIS 3D terrain module for Sentinel historical inundation review and planning scenarios. The current version generates screening footprints from selected dams; Sentinel-1 SAR event polygons can be connected as GeoJSON/FeatureLayer inputs in the next data stage.</div>',
        unsafe_allow_html=True,
    )
    if map_status.empty:
        st.info("Dam map data is not available for 3D flood scenario generation under the current filters.")
    else:
        scenario_controls = st.columns([0.26, 0.22, 0.18, 0.34])
        with scenario_controls[0]:
            scenario_event = st.selectbox(
                "Historical / planning scenario",
                [
                    "2019 Monsoon Flood",
                    "2020 High Rainfall Event",
                    "2021 Chambal-Betwa Event",
                    "2022 Narmada Event",
                    "Custom Planning Scenario",
                ],
                key="sentinel_3d_event",
            )
        with scenario_controls[1]:
            scenario_return_period = st.selectbox(
                "Return period band",
                ["Normal floodplain", "1 in 10 year", "1 in 25 year", "1 in 50 year", "1 in 100 year"],
                index=2,
                key="sentinel_3d_return_period",
            )
        with scenario_controls[2]:
            scenario_depth = st.slider(
                "Water depth / HAND threshold (m)",
                min_value=0.5,
                max_value=8.0,
                value=2.5,
                step=0.5,
                key="sentinel_3d_depth",
            )
        with scenario_controls[3]:
            available_3d_dams = (
                map_status.dropna(subset=["reservoir_name"])
                .sort_values("display_filling", ascending=False)["reservoir_name"]
                .drop_duplicates()
                .tolist()
            )
            selected_3d_dams = st.multiselect(
                "Dams for 3D scenario",
                available_3d_dams,
                default=available_3d_dams[:6],
                key="sentinel_3d_dams",
                help="Keep this focused for faster 3D rendering. Real Sentinel event polygons can cover full districts/basins when connected.",
            )

        scenario_source = map_status.copy()
        if selected_3d_dams:
            scenario_source = scenario_source[scenario_source["reservoir_name"].isin(selected_3d_dams)]
        scenario_radius = scenario_radius_km(scenario_event, scenario_return_period, scenario_depth)
        scenario_dam_count = int(scenario_source["reservoir_name"].dropna().nunique()) if "reservoir_name" in scenario_source else 0
        scenario_alerts = int(scenario_source.get("alert_level", pd.Series(dtype=str)).isin(["Critical", "Warning"]).sum()) if not scenario_source.empty else 0
        scenario_area_proxy = math.pi * (scenario_radius ** 2) * max(1, scenario_dam_count)
        avg_filling_3d = pd.to_numeric(scenario_source.get("display_filling"), errors="coerce").mean() if not scenario_source.empty else math.nan
        scenario_kpis = st.columns(5)
        scenario_kpis[0].metric("Scenario Dams", scenario_dam_count)
        scenario_kpis[1].metric("Screening Radius", f"{scenario_radius:.1f} km")
        scenario_kpis[2].metric("Approx. Footprint", f"{scenario_area_proxy:,.0f} sq.km")
        scenario_kpis[3].metric("Critical/Warning Dams", scenario_alerts)
        scenario_kpis[4].metric("OSM 3D Footprints", f"{scenario_dam_count} dam zones")
        st.markdown(
            f"""
            <div class="alert-legend-panel">
              <b>Generated WSE Depth Legend</b>
              <div><span class="legend-dot" style="background:#bae6fd"></span>0 - 25% WSE depth: shallow fringe</div>
              <div><span class="legend-dot" style="background:#38bdf8"></span>25 - 50% WSE depth</div>
              <div><span class="legend-dot" style="background:#2563eb"></span>50 - 75% WSE depth</div>
              <div><span class="legend-dot" style="background:#1e40af"></span>75 - 100% WSE depth: deepest zone near source</div>
              <div><span class="legend-dot" style="background:#06b6d4"></span>Drainage alignment: MP Drains layer styled by ORD_STRA and draped on ArcGIS elevation</div>
              <div><span class="legend-dot" style="background:#ef4444"></span>OSM 3D buildings: high exposure</div>
              <div><span class="legend-dot" style="background:#f59e0b"></span>OSM 3D buildings: moderate exposure</div>
              <div><span class="legend-dot" style="background:#14b8a6"></span>OSM 3D buildings: low exposure</div>
              <div style="margin-top:0.35rem;color:#64748b">Current max WSE depth threshold: {scenario_depth:.2f} m. Replace generated WSE widths with FABDEM/Sentinel-derived WSE raster when available.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        drainage_points = tuple(
            (float(row.longitude), float(row.latitude))
            for row in scenario_source.dropna(subset=["longitude", "latitude"]).itertuples(index=False)
            if pd.notna(row.longitude) and pd.notna(row.latitude)
        )
        scenario_drainage_geojson = load_light_drainage_geojson(str(MP_DRAINS_GEOJSON), drainage_points)
        render_arcgis_3d_sentinel_scene(
            map_status,
            load_light_district_geojson(str(MP_DISTRICTS_GEOJSON)),
            scenario_drainage_geojson,
            selected_3d_dams,
            scenario_event,
            scenario_return_period,
            scenario_depth,
        )

        st.markdown(
            f"""
            <div class="glofas-status-grid">
              <div class="glofas-card"><span>Scenario Source</span><b>Sentinel-1 SAR ready</b></div>
              <div class="glofas-card"><span>Terrain Context</span><b>ArcGIS world elevation</b></div>
              <div class="glofas-card"><span>Avg Dam Filling</span><b>{fmt_number(avg_filling_3d, "%")}</b></div>
              <div class="glofas-card"><span>Layer Mode</span><b>WSE + OSM 3D buildings</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        scenario_table_cols = [
            "reservoir_name",
            "district",
            "sub_basin",
            "water_level_m",
            "frl_gap_m",
            "display_filling",
            "alert_level",
            "latitude",
            "longitude",
        ]
        scenario_table = scenario_source[[col for col in scenario_table_cols if col in scenario_source.columns]].copy()
        if not scenario_table.empty:
            scenario_table["scenario_event"] = scenario_event
            scenario_table["return_period"] = scenario_return_period
            scenario_table["screening_depth_m"] = scenario_depth
            scenario_table["screening_radius_km"] = scenario_radius
            scenario_table["wse_depth_zone_count"] = 4
            scenario_table["drainage_alignment"] = "MP Drains ORD_STRA layer on ArcGIS world elevation"
            scenario_table["building_footprint_layer"] = "Dynamic OpenStreetMap building footprints loaded in ArcGIS SceneView and extruded by OSM height/building-level tags"
            scenario_table["water_spread_method"] = "Generated WSE corridors along nearest MP drainage segments plus concentric depth zones; replace generated widths with DEM/Sentinel WSE raster"
            st.dataframe(scenario_table, use_container_width=True, hide_index=True, height=260)
            st.download_button(
                "Download 3D Scenario Table CSV",
                scenario_table.to_csv(index=False).encode("utf-8"),
                file_name="mpwrd_3d_sentinel_inundation_scenario.csv",
                mime="text/csv",
                use_container_width=True,
            )


if main_page == "Infographics":
    st.subheader("Infographics")
    if reservoir_view.empty and map_status.empty:
        st.info("No data is available for infographic generation under the current filters.")
    else:
        latest_label = time_label(latest_reservoirs["observed_at"].dropna().max()) if not latest_reservoirs.empty else "Current filter"
        infographic_alert_counts = (
            map_status["alert_level"].value_counts().to_dict()
            if not map_status.empty and "alert_level" in map_status
            else {}
        )
        latest_avg_filling = pd.to_numeric(latest_reservoirs.get("filling_percent"), errors="coerce").mean() if not latest_reservoirs.empty else math.nan
        latest_storage = pd.to_numeric(latest_reservoirs.get("current_live_capacity_mcm"), errors="coerce").sum() if not latest_reservoirs.empty else math.nan
        monitored_dams = int(map_status["reservoir_name"].dropna().nunique()) if not map_status.empty and "reservoir_name" in map_status else 0
        river_station_count = int(river_view["gauge_station"].dropna().nunique()) if not river_view.empty else 0
        active_alerts = int(infographic_alert_counts.get("Critical", 0) + infographic_alert_counts.get("Warning", 0))

        st.markdown(
            f"""
            <div class="infographic-frame">
                <div class="infographic-title">MPWRD VBSR Water Level Situation Board</div>
                <div class="infographic-subtitle">Presentation-ready snapshot from the selected report window. Values update with the sidebar date, time, district, basin, reservoir, and gauge filters.</div>
                <div class="infographic-grid">
                    <div class="infographic-card"><span>Latest Slot</span><b>{escape(str(latest_label))}</b><small>Current observation context</small></div>
                    <div class="infographic-card"><span>Monitored Dams</span><b>{monitored_dams}</b><small>Mapped reservoirs in view</small></div>
                    <div class="infographic-card"><span>Avg Filling</span><b>{fmt_number(latest_avg_filling, "%")}</b><small>Latest reservoir average</small></div>
                    <div class="infographic-card"><span>Live Storage</span><b>{fmt_number(latest_storage, " MCM")}</b><small>Latest summed storage</small></div>
                    <div class="infographic-card"><span>Active FRL Alerts</span><b>{active_alerts}</b><small>Critical + warning reservoirs</small></div>
                    <div class="infographic-card"><span>River Gauges</span><b>{river_station_count}</b><small>Gauge stations in selected data</small></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if not map_status.empty and {"latitude", "longitude"}.issubset(map_status.columns):
            infographic_map = map_status.copy()
            infographic_map["latitude"] = pd.to_numeric(infographic_map["latitude"], errors="coerce")
            infographic_map["longitude"] = pd.to_numeric(infographic_map["longitude"], errors="coerce")
            infographic_map = infographic_map.dropna(subset=["latitude", "longitude"])
            if not infographic_map.empty:
                if not capacity_view.empty and {"reservoir_name", "waterbody_area_sqkm"}.issubset(capacity_view.columns):
                    infographic_map = infographic_map.merge(
                        capacity_view[["reservoir_name", "waterbody_area_sqkm"]].drop_duplicates("reservoir_name"),
                        on="reservoir_name",
                        how="left",
                    )
                else:
                    infographic_map["waterbody_area_sqkm"] = 0
                infographic_map["waterbody_area_sqkm"] = pd.to_numeric(
                    infographic_map.get("waterbody_area_sqkm"), errors="coerce"
                ).fillna(0)
                map_district_series = infographic_map.get("map_district", pd.Series("", index=infographic_map.index)).fillna("").astype(str)
                infographic_map["district_label"] = map_district_series.where(
                    map_district_series.str.len() > 0,
                    infographic_map.get("district", pd.Series("Unassigned", index=infographic_map.index)).fillna("Unassigned").astype(str),
                )
                render_infographic_leaflet_map(
                    infographic_map,
                    load_light_district_geojson(str(MP_DISTRICTS_GEOJSON)),
                )

        info_cols = st.columns([0.92, 1.08])
        with info_cols[0]:
            alert_summary = pd.DataFrame(
                [
                    {"alert_level": "Critical", "reservoirs": infographic_alert_counts.get("Critical", 0), "color": "#ef4444"},
                    {"alert_level": "Warning", "reservoirs": infographic_alert_counts.get("Warning", 0), "color": "#f59e0b"},
                    {"alert_level": "Watch", "reservoirs": infographic_alert_counts.get("Watch", 0), "color": "#eab308"},
                    {"alert_level": "Normal", "reservoirs": infographic_alert_counts.get("Normal", 0), "color": "#2563eb"},
                ]
            )
            alert_chart = (
                alt.Chart(alert_summary)
                .mark_arc(innerRadius=62, outerRadius=112)
                .encode(
                    theta=alt.Theta("reservoirs:Q"),
                    color=alt.Color(
                        "alert_level:N",
                        scale=alt.Scale(
                            domain=["Critical", "Warning", "Watch", "Normal"],
                            range=["#ef4444", "#f59e0b", "#eab308", "#2563eb"],
                        ),
                        title="FRL alert",
                    ),
                    tooltip=["alert_level", "reservoirs"],
                )
                .properties(height=210, title="FRL Alert Composition")
            )
            st.altair_chart(alert_chart, use_container_width=True)
        with info_cols[1]:
            if not latest_reservoirs.empty:
                district_infographic = (
                    latest_reservoirs.assign(
                        district_label=latest_reservoirs["district"].fillna("Unassigned"),
                        filling_percent=pd.to_numeric(latest_reservoirs["filling_percent"], errors="coerce"),
                    )
                    .groupby("district_label", as_index=False)
                    .agg(
                        reservoirs=("reservoir_name", "nunique"),
                        avg_filling=("filling_percent", "mean"),
                        max_filling=("filling_percent", "max"),
                    )
                    .sort_values("avg_filling", ascending=False)
                    .head(14)
                )
                district_chart = (
                    alt.Chart(district_infographic)
                    .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                    .encode(
                        y=alt.Y("district_label:N", sort="-x", title="District"),
                        x=alt.X("avg_filling:Q", title="Average filling (%)"),
                        color=alt.Color(
                            "max_filling:Q",
                            scale=alt.Scale(domain=[0, 100], range=COOLORS_ALERT_PALETTE),
                            title="Max filling",
                        ),
                        tooltip=["district_label", "reservoirs", "avg_filling", "max_filling"],
                    )
                    .properties(height=210, title="District Reservoir Filling Snapshot")
                )
                st.altair_chart(district_chart, use_container_width=True)
            else:
                st.info("No latest reservoir rows are available for district infographic.")

        info_cols_2 = st.columns(2)
        with info_cols_2[0]:
            if not reservoir_view.empty:
                storage_timeline = (
                    reservoir_view.assign(
                        current_live_capacity_mcm=pd.to_numeric(reservoir_view["current_live_capacity_mcm"], errors="coerce"),
                        filling_percent=pd.to_numeric(reservoir_view["filling_percent"], errors="coerce"),
                    )
                    .groupby("observed_at", as_index=False)
                    .agg(total_storage_mcm=("current_live_capacity_mcm", "sum"), avg_filling=("filling_percent", "mean"))
                    .dropna(subset=["observed_at"])
                )
                storage_chart = (
                    alt.Chart(storage_timeline)
                    .mark_area(line=True, opacity=0.28, color="#06b6d4")
                    .encode(
                        x=alt.X("observed_at:T", title="Observation time"),
                        y=alt.Y("total_storage_mcm:Q", title="Total live storage (MCM)"),
                        tooltip=["observed_at", "total_storage_mcm", "avg_filling"],
                    )
                    .properties(height=205, title="Storage Timeline")
                )
                st.altair_chart(storage_chart, use_container_width=True)
        with info_cols_2[1]:
            if not latest_reservoirs.empty:
                top_filling = latest_reservoirs.assign(
                    filling_percent=pd.to_numeric(latest_reservoirs["filling_percent"], errors="coerce")
                ).nlargest(10, "filling_percent")
                top_filling_chart = (
                    alt.Chart(top_filling)
                    .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                    .encode(
                        x=alt.X("reservoir_name:N", sort="-y", title="Reservoir", axis=alt.Axis(labelAngle=-35)),
                        y=alt.Y("filling_percent:Q", title="Filling (%)"),
                        color=alt.Color(
                            "filling_percent:Q",
                            scale=alt.Scale(domain=[0, 100], range=COOLORS_ALERT_PALETTE),
                            legend=None,
                        ),
                        tooltip=["reservoir_name", "district", "water_level_m", "frl_gap_m", "filling_percent"],
                    )
                    .properties(height=205, title="Top Filled Reservoirs")
                )
                st.altair_chart(top_filling_chart, use_container_width=True)

        info_cols_3 = st.columns([0.58, 0.42])
        if not latest_reservoirs.empty:
            filling_snapshot = latest_reservoirs.assign(
                filling_percent=pd.to_numeric(latest_reservoirs["filling_percent"], errors="coerce")
            ).dropna(subset=["filling_percent"])
            with info_cols_3[0]:
                least_filled = filling_snapshot[filling_snapshot["filling_percent"] < 25].nsmallest(12, "filling_percent")
                if least_filled.empty:
                    st.success("No reservoirs are below 25% filling under the active filters.")
                else:
                    least_chart = (
                        alt.Chart(least_filled)
                        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                        .encode(
                            y=alt.Y("reservoir_name:N", sort="x", title="Reservoir"),
                            x=alt.X("filling_percent:Q", title="Filling (%)", scale=alt.Scale(domain=[0, 25])),
                            color=alt.Color(
                                "filling_percent:Q",
                                scale=alt.Scale(domain=[0, 25], range=["#580aff", "#147df5", "#0aefff", "#0aff99"]),
                                legend=None,
                            ),
                            tooltip=["reservoir_name", "district", "water_level_m", "frl_gap_m", "filling_percent"],
                        )
                        .properties(height=220, title="Least Filled Reservoirs Below 25%")
                    )
                    st.altair_chart(least_chart, use_container_width=True)
            with info_cols_3[1]:
                band_labels = ["0-25%", "25-50%", "50-75%", "75-100%"]
                band_colors = ["#580aff", "#0aefff", "#ffd300", "#ff0000"]
                banded = filling_snapshot.assign(
                    filling_band=pd.cut(
                        filling_snapshot["filling_percent"],
                        bins=[-0.01, 25, 50, 75, 100],
                        labels=band_labels,
                    )
                )
                band_summary = (
                    banded.groupby("filling_band", observed=False)
                    .agg(reservoirs=("reservoir_name", "nunique"), avg_filling=("filling_percent", "mean"))
                    .reindex(band_labels)
                    .reset_index()
                    .fillna({"reservoirs": 0, "avg_filling": 0})
                )
                band_summary["color"] = band_colors
                band_chart = (
                    alt.Chart(band_summary)
                    .mark_arc(innerRadius=58, outerRadius=112, cornerRadius=5, padAngle=0.02)
                    .encode(
                        theta=alt.Theta("reservoirs:Q", title="Reservoirs"),
                        color=alt.Color("filling_band:N", scale=alt.Scale(domain=band_labels, range=band_colors), title="Filling Band"),
                        tooltip=["filling_band", "reservoirs", "avg_filling"],
                    )
                    .properties(height=220, title="Reservoir Filling Bands")
                )
                band_text = (
                    alt.Chart(band_summary)
                    .mark_text(radius=138, size=12, fontWeight="bold")
                    .encode(
                        theta=alt.Theta("reservoirs:Q"),
                        text=alt.Text("reservoirs:Q", format=".0f"),
                        color=alt.value("#172033"),
                    )
                )
                st.altair_chart(band_chart + band_text, use_container_width=True)

            st.markdown('<div class="panel-note">Filling band drill-down: choose a category to view the reservoirs inside that percentage range.</div>', unsafe_allow_html=True)
            selected_band = st.radio(
                "Reservoir filling category",
                band_labels,
                horizontal=True,
                key="infographic_filling_band_drilldown",
            )
            band_detail = banded[banded["filling_band"].astype(str) == selected_band].sort_values("filling_percent")
            if band_detail.empty:
                st.info(f"No reservoirs are currently in the {selected_band} filling category.")
            else:
                selected_band_color = band_colors[band_labels.index(selected_band)]
                drill_cols = st.columns([0.68, 0.32])
                with drill_cols[0]:
                    band_detail_chart = (
                        alt.Chart(band_detail)
                        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                        .encode(
                            y=alt.Y("reservoir_name:N", sort="x", title="Reservoir"),
                            x=alt.X("filling_percent:Q", title="Filling (%)", scale=alt.Scale(domain=[0, 100])),
                            color=alt.Color(
                                "filling_percent:Q",
                                scale=alt.Scale(domain=[0, 100], range=COOLORS_ALERT_PALETTE),
                                legend=None,
                            ),
                            tooltip=["reservoir_name", "district", "water_level_m", "frl_gap_m", "filling_percent"],
                        )
                        .properties(height=max(220, min(360, 22 * len(band_detail))), title=f"{selected_band} Filled Reservoirs")
                    )
                    st.altair_chart(band_detail_chart, use_container_width=True)
                with drill_cols[1]:
                    st.markdown(
                        f"""
                        <div class="infographic-frame" style="padding:1rem;border-left:5px solid {selected_band_color}">
                            <div class="infographic-title" style="font-size:1rem">{escape(selected_band)} Filled</div>
                            <div class="infographic-grid" style="grid-template-columns:1fr;gap:.55rem">
                                <div class="infographic-card"><span>Reservoirs</span><b>{len(band_detail)}</b><small>inside selected category</small></div>
                                <div class="infographic-card"><span>Average Filling</span><b>{fmt_number(band_detail["filling_percent"].mean(), "%")}</b><small>selected category average</small></div>
                                <div class="infographic-card"><span>Lowest Reservoir</span><b>{escape(str(band_detail.iloc[0].get("reservoir_name", "-")))}</b><small>{fmt_number(band_detail.iloc[0].get("filling_percent"), "%")} filled</small></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                detail_cols = [
                    "reservoir_name",
                    "district",
                    "water_level_m",
                    "frl_gap_m",
                    "current_live_capacity_mcm",
                    "filling_percent",
                    "rainfall_daily_mm",
                ]
                st.dataframe(
                    band_detail[[col for col in detail_cols if col in band_detail.columns]],
                    use_container_width=True,
                    hide_index=True,
                    height=min(240, 64 + 26 * len(band_detail)),
                )

        st.markdown(
            '<div class="panel-note">This tab is intended for visual briefings, screenshots, and report exports. It does not change the source observations; it summarizes the active dashboard filters.</div>',
            unsafe_allow_html=True,
        )


if main_page == "Data & Timeseries":
    st.subheader("Reservoir Trends and Latest Ranking")
    if reservoir_view.empty:
        st.info("No reservoir observations match the current filters.")
    else:
        metric_label = st.selectbox("Reservoir metric", list(RESERVOIR_METRICS), index=0)
        metric_col, metric_unit = RESERVOIR_METRICS[metric_label]
        reservoir_options = sorted(reservoir_view["reservoir_name"].dropna().unique())
        default_reservoirs = [name for name in ["Bansagar", "Gandhisagar", "Kolar", "Tawa"] if name in reservoir_options]
        selected_reservoirs = st.multiselect(
            "Reservoirs",
            reservoir_options,
            default=default_reservoirs or reservoir_options[: min(6, len(reservoir_options))],
        )
        trend_df = reservoir_view[reservoir_view["reservoir_name"].isin(selected_reservoirs)].dropna(subset=[metric_col])
        latest_time = max(reservoir_view["observed_at"].dropna())
        snapshot = reservoir_view[reservoir_view["observed_at"] == latest_time].dropna(subset=[metric_col])
        rank_count = st.slider("Reservoirs in latest ranking", min_value=8, max_value=30, value=16, step=4)
        rank_df = snapshot.nlargest(rank_count, metric_col)
        res_left, res_right = st.columns([1.2, 0.8])
        with res_left:
            trend_chart = (
                alt.Chart(trend_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("observed_at:T", title="Observation time"),
                    y=alt.Y(f"{metric_col}:Q", title=f"{metric_label} ({metric_unit})"),
                    color=alt.Color("reservoir_name:N", title="Reservoir"),
                    tooltip=["reservoir_name", "district", "observed_at", metric_col, "report_id"],
                )
                .properties(height=300)
            )
            st.altair_chart(trend_chart, use_container_width=True)
        with res_right:
            st.caption(f"Latest Time Slot Ranking: {time_label(latest_time)}")
            rank_chart = reservoir_snapshot_chart(
                rank_df,
                metric_col,
                metric_label,
                metric_unit,
                "Bar",
                max(280, rank_count * 17),
            )
            st.altair_chart(rank_chart, use_container_width=True)

    tab_time, tab_rivers, tab_gates, tab_capacity, tab_data, tab_exports = st.tabs(
        ["Time Series", "River Trends", "Gate Timeline", "Capacity DSS", "Data Explorer", "Exports"]
    )

    with tab_time:
        st.subheader("Observation Timeline")
        if reservoir_view.empty:
            st.info("No reservoir observations match the current filters.")
        else:
            timeline = (
                reservoir_view.groupby("observed_at", as_index=False)
                .agg(
                    reservoirs=("reservoir_name", "nunique"),
                    avg_filling_percent=("filling_percent", "mean"),
                    max_filling_percent=("filling_percent", "max"),
                    total_storage_mcm=("current_live_capacity_mcm", "sum"),
                    daily_rainfall_mm=("rainfall_daily_mm", "sum"),
                )
                .sort_values("observed_at")
            )
            left, mid, right = st.columns([1, 1, 0.78])
            with left:
                filling_chart = (
                    alt.Chart(timeline)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("observed_at:T", title="Observation time"),
                        y=alt.Y("avg_filling_percent:Q", title="Average filling (%)"),
                        tooltip=["observed_at", "reservoirs", "avg_filling_percent", "max_filling_percent"],
                    )
                    .properties(height=260)
                )
                st.altair_chart(filling_chart, use_container_width=True)
            with mid:
                rainfall_chart = (
                    alt.Chart(timeline)
                    .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                    .encode(
                        x=alt.X("observed_at:T", title="Observation time"),
                        y=alt.Y("daily_rainfall_mm:Q", title="Total daily rainfall (mm)"),
                        tooltip=["observed_at", "daily_rainfall_mm", "total_storage_mcm"],
                    )
                    .properties(height=260)
                )
                st.altair_chart(rainfall_chart, use_container_width=True)
            with right:
                st.dataframe(timeline, use_container_width=True, hide_index=True, height=260)

            if not river_view.empty:
                river_timeline = (
                    river_view.groupby("observed_at", as_index=False)
                    .agg(
                        river_stations=("gauge_station", "nunique"),
                        avg_water_level_m=("water_level_m", "mean"),
                        min_danger_gap_m=("danger_gap_m", "min"),
                    )
                    .sort_values("observed_at")
                )
                river_chart = (
                    alt.Chart(river_timeline)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("observed_at:T", title="Observation time"),
                        y=alt.Y("min_danger_gap_m:Q", title="Minimum gap to danger level (m)"),
                        tooltip=["observed_at", "river_stations", "avg_water_level_m", "min_danger_gap_m"],
                    )
                    .properties(height=220)
                )
                st.altair_chart(river_chart, use_container_width=True)

    with tab_rivers:
        st.subheader("River Gauge Trends Over Time")
        if river_view.empty:
            st.info("No river observations match the current filters.")
        else:
            metric_label = st.selectbox("River metric", list(RIVER_METRICS), index=0)
            metric_col, metric_unit = RIVER_METRICS[metric_label]
            station_options = sorted(river_view["gauge_station"].dropna().unique())
            selected_stations = st.multiselect(
                "Gauge stations",
                station_options,
                default=station_options[: min(6, len(station_options))],
            )
            trend_df = river_view[river_view["gauge_station"].isin(selected_stations)].dropna(subset=[metric_col])
            river_chart = (
                alt.Chart(trend_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("observed_at:T", title="Observation time"),
                    y=alt.Y(f"{metric_col}:Q", title=f"{metric_label} ({metric_unit})"),
                    color=alt.Color("gauge_station:N", title="Gauge station"),
                    tooltip=["river_name", "gauge_station", "district", "observed_at", metric_col, "danger_or_max_water_level_m"],
                )
                .properties(height=300)
            )
            st.altair_chart(river_chart, use_container_width=True)

            st.dataframe(
                latest_rivers.sort_values("danger_gap_m", na_position="last"),
                use_container_width=True,
                hide_index=True,
                height=220,
            )

    with tab_gates:
        st.subheader("Gate Operations Timeline")
        if gate_view_all.empty:
            st.info("No gate rows are available.")
        else:
            gate_view = gate_view_all.copy()
            show_open_only = st.toggle("Show only open gate rows", value=False)
            if show_open_only:
                gate_view = gate_view[gate_view["gate_opened_count"].fillna(0).astype(float) > 0]
            gate_timeline = (
                gate_view.groupby("report_at", as_index=False)
                .agg(
                    reservoirs=("reservoir_name", "nunique"),
                    open_sites=("gate_opened_count", lambda values: (values.fillna(0).astype(float) > 0).sum()),
                    discharge_cumecs=("discharge_cumecs", "sum"),
                )
                .sort_values("report_at")
            )
            gate_chart = (
                alt.Chart(gate_timeline)
                .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("report_at:T", title="Report time"),
                    y=alt.Y("open_sites:Q", title="Open gate sites"),
                    tooltip=["report_at", "reservoirs", "open_sites", "discharge_cumecs"],
                )
                .properties(height=260)
            )
            st.altair_chart(gate_chart, use_container_width=True)
            st.dataframe(gate_view.sort_values(["report_at", "reservoir_name"]), use_container_width=True, hide_index=True, height=230)

    with tab_capacity:
        st.subheader("Reservoir Capacity DSS")
        st.markdown(
            '<div class="panel-note">First-stage remote-sensing capacity layer matching MPWRD dams to waterbody area, then calibrating storage with official FRL/LSL/live capacity. FABDEM/altimetry curves can replace the screening geometry estimate as the next processing stage.</div>',
            unsafe_allow_html=True,
        )
        if capacity_view.empty:
            st.info("No reservoir capacity estimates are available for the current filters. Run generate_reservoir_capacity_estimates.py to refresh the layer.")
        else:
            total_capacity = pd.to_numeric(capacity_view["calibrated_capacity_mcm"], errors="coerce").sum()
            matched_count = capacity_view["matched_waterbody_name"].notna().sum() if "matched_waterbody_name" in capacity_view else 0
            high_count = capacity_view["capacity_confidence"].astype(str).str.startswith("High").sum()
            cap_cols = st.columns(4)
            cap_cols[0].metric("Reservoirs", f"{len(capacity_view):,}")
            cap_cols[1].metric("Matched Waterbodies", f"{matched_count:,}")
            cap_cols[2].metric("High Confidence", f"{high_count:,}")
            cap_cols[3].metric("Calibrated Capacity", f"{total_capacity:,.0f} MCM")

            chart_cols = st.columns([1.15, 0.85])
            with chart_cols[0]:
                top_capacity = capacity_view.sort_values("calibrated_capacity_mcm", ascending=False).head(18)
                capacity_chart = (
                    alt.Chart(top_capacity)
                    .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
                    .encode(
                        y=alt.Y("reservoir_name:N", sort="-x", title="Reservoir"),
                        x=alt.X("calibrated_capacity_mcm:Q", title="Calibrated capacity (MCM)"),
                        color=alt.Color("capacity_confidence:N", title="Confidence"),
                        tooltip=[
                            "reservoir_name",
                            "district",
                            "official_live_capacity_mcm",
                            "waterbody_area_sqkm",
                            "matched_waterbody_name",
                            "capacity_confidence",
                        ],
                    )
                    .properties(height=360)
                )
                st.altair_chart(capacity_chart, use_container_width=True)
            with chart_cols[1]:
                confidence_df = capacity_view["capacity_confidence"].value_counts().rename_axis("confidence").reset_index(name="reservoirs")
                confidence_chart = (
                    alt.Chart(confidence_df)
                    .mark_arc(innerRadius=58, outerRadius=118)
                    .encode(
                        theta=alt.Theta("reservoirs:Q"),
                        color=alt.Color("confidence:N", title="Capacity confidence"),
                        tooltip=["confidence", "reservoirs"],
                    )
                    .properties(height=260)
                )
                st.altair_chart(confidence_chart, use_container_width=True)
                st.dataframe(
                    confidence_df,
                    use_container_width=True,
                    hide_index=True,
                    height=120,
                )

            curve_source_options: dict[str, pd.DataFrame] = {}
            if not capacity_curve_fabdem_view.empty:
                curve_source_options["Stage 2B FABDEM hypsometry"] = capacity_curve_fabdem_view
            if not capacity_curve_view.empty:
                curve_source_options["Stage 2A calibrated screening"] = capacity_curve_view

            if curve_source_options:
                selected_curve_source = st.radio(
                    "Curve source",
                    list(curve_source_options),
                    horizontal=True,
                    help="Stage 2B samples FABDEM within the matched waterbody polygon and calibrates the curve to official LSL, FRL, and live capacity. Stage 2A is the earlier calibrated screening curve.",
                )
                selected_capacity_curve_view = curve_source_options[selected_curve_source].copy()
                curve_options = sorted(selected_capacity_curve_view["reservoir_name"].dropna().unique())
                default_curve = curve_options[0] if curve_options else None
                if "calibrated_capacity_mcm" in capacity_view and not capacity_view.empty:
                    largest = capacity_view.sort_values("calibrated_capacity_mcm", ascending=False)["reservoir_name"].dropna()
                    if not largest.empty and largest.iloc[0] in curve_options:
                        default_curve = largest.iloc[0]
                selected_curve_reservoir = st.selectbox(
                    "Area-elevation-storage curve",
                    curve_options,
                    index=curve_options.index(default_curve) if default_curve in curve_options else 0,
                )
                curve_df = selected_capacity_curve_view[selected_capacity_curve_view["reservoir_name"] == selected_curve_reservoir].copy()
                curve_df["cumulative_storage_mcm"] = pd.to_numeric(curve_df["cumulative_storage_mcm"], errors="coerce")
                curve_df["water_spread_area_sqkm"] = pd.to_numeric(curve_df["water_spread_area_sqkm"], errors="coerce")
                curve_df["elevation_m"] = pd.to_numeric(curve_df["elevation_m"], errors="coerce")
                selected_curve_meta = curve_df.iloc[0] if not curve_df.empty else pd.Series(dtype=object)
                curve_method_label = str(selected_curve_meta.get("curve_method", "")).replace("_", " ").strip().title()
                sample_count = pd.to_numeric(pd.Series([selected_curve_meta.get("fabdem_sample_count")]), errors="coerce").iloc[0]
                p05 = pd.to_numeric(pd.Series([selected_curve_meta.get("fabdem_p05_m")]), errors="coerce").iloc[0]
                p95 = pd.to_numeric(pd.Series([selected_curve_meta.get("fabdem_p95_m")]), errors="coerce").iloc[0]
                if pd.notna(sample_count) and sample_count > 0:
                    st.caption(
                        f"{curve_method_label}. FABDEM samples: {int(sample_count):,}; DEM p05-p95: {p05:,.2f} m to {p95:,.2f} m."
                    )
                elif curve_method_label:
                    st.caption(f"{curve_method_label}.")

                selected_capacity_row = capacity_view[capacity_view["reservoir_name"] == selected_curve_reservoir]
                reference_rows = []
                datum_label = "LSL datum"
                datum_elevation = pd.to_numeric(curve_df["elevation_m"], errors="coerce").min()
                active_depth_domain = None
                if not selected_capacity_row.empty:
                    selected_capacity_record = selected_capacity_row.iloc[0]
                    lsl_value = pd.to_numeric(pd.Series([selected_capacity_record.get("lsl_m")]), errors="coerce").iloc[0]
                    frl_value = pd.to_numeric(pd.Series([selected_capacity_record.get("frl_m")]), errors="coerce").iloc[0]
                    if pd.notna(lsl_value):
                        datum_elevation = float(lsl_value)
                        datum_label = f"LSL datum ({datum_elevation:,.2f} m)"
                    if pd.notna(lsl_value) and pd.notna(frl_value) and frl_value > lsl_value:
                        active_depth_domain = [0, float(frl_value - lsl_value)]
                    for label, column, color in [
                        ("LSL", "lsl_m", "#64748b"),
                        ("FRL", "frl_m", "#ef4444"),
                        ("Current WL", "latest_water_level_m", "#0f766e"),
                    ]:
                        value = pd.to_numeric(pd.Series([selected_capacity_record.get(column)]), errors="coerce").iloc[0]
                        if pd.notna(value):
                            adjusted_value = float(value - datum_elevation)
                            if label == "Current WL" and active_depth_domain and not (-0.05 <= adjusted_value <= active_depth_domain[1] + 0.05):
                                continue
                            reference_rows.append(
                                {
                                    "level": label,
                                    "elevation_m": float(value),
                                    "datum_adjusted_elevation_m": adjusted_value,
                                    "color": color,
                                }
                            )
                curve_df["datum_adjusted_elevation_m"] = curve_df["elevation_m"] - datum_elevation
                curve_df = curve_df[
                    curve_df["datum_adjusted_elevation_m"].notna()
                    & (curve_df["datum_adjusted_elevation_m"] >= -0.001)
                ].copy()
                curve_df = curve_df.sort_values("elevation_m").reset_index(drop=True)
                curve_df["water_spread_area_msqm"] = curve_df["water_spread_area_sqkm"]
                curve_df["segmental_live_capacity_mcm"] = curve_df["cumulative_storage_mcm"].diff().fillna(0).clip(lower=0)
                curve_df["srs_level_label"] = ""
                if not curve_df.empty:
                    curve_df.loc[curve_df.index[0], "srs_level_label"] = "MDDL"
                    curve_df.loc[curve_df.index[-1], "srs_level_label"] = "FRL"
                reference_df = pd.DataFrame(reference_rows)

                base_curve = alt.Chart(curve_df).encode(
                    y=alt.Y(
                        "datum_adjusted_elevation_m:Q",
                        title=f"Elevation (m) above {datum_label}",
                        scale=alt.Scale(domain=active_depth_domain, nice=False) if active_depth_domain else alt.Scale(nice=True),
                        axis=alt.Axis(grid=True, tickCount=8, titleColor="#0f172a", labelColor="#0f172a", tickColor="#0f172a"),
                    )
                )
                area_curve = (
                    base_curve.mark_line(point=alt.OverlayMarkDef(filled=True, size=58, shape="square"), strokeWidth=2.8, color="#c2413c")
                    .encode(
                        x=alt.X(
                            "water_spread_area_msqm:Q",
                            title="Water spread area (M.Sqm) - bottom axis",
                            scale=alt.Scale(reverse=True, nice=True, zero=True),
                            axis=alt.Axis(
                                orient="bottom",
                                titleColor="#c2413c",
                                labelColor="#7f1d1d",
                                tickColor="#c2413c",
                                domainColor="#c2413c",
                                grid=True,
                            ),
                        ),
                        tooltip=[
                            "reservoir_name",
                            alt.Tooltip("datum_adjusted_elevation_m:Q", title="Elev. above datum (m)", format=",.2f"),
                            alt.Tooltip("elevation_m:Q", title="Elevation (m)", format=",.2f"),
                            alt.Tooltip("water_spread_area_msqm:Q", title="Water spread area (M.Sqm)", format=",.3f"),
                            "curve_method",
                            "capacity_confidence",
                        ],
                    )
                )
                volume_curve = (
                    base_curve.mark_line(point=alt.OverlayMarkDef(filled=True, size=52), strokeWidth=2.8, color="#3b6ea8")
                    .encode(
                        x=alt.X(
                            "cumulative_storage_mcm:Q",
                            title="Cumulative live capacity (M.Cum / MCM) - top axis",
                            scale=alt.Scale(nice=True, zero=True),
                            axis=alt.Axis(
                                orient="top",
                                titleColor="#3b6ea8",
                                labelColor="#1e3a8a",
                                tickColor="#3b6ea8",
                                domainColor="#3b6ea8",
                                grid=True,
                            ),
                        ),
                        tooltip=[
                            "reservoir_name",
                            alt.Tooltip("datum_adjusted_elevation_m:Q", title="Elev. above datum (m)", format=",.2f"),
                            alt.Tooltip("elevation_m:Q", title="Elevation (m)", format=",.2f"),
                            alt.Tooltip("cumulative_storage_mcm:Q", title="Storage (MCM)", format=",.2f"),
                            "curve_method",
                            "capacity_confidence",
                        ],
                    )
                )
                curve_layers = [area_curve, volume_curve]
                if not reference_df.empty:
                    reference_rules = (
                        alt.Chart(reference_df)
                        .mark_rule(strokeDash=[6, 4], strokeWidth=1.5)
                        .encode(
                            y="datum_adjusted_elevation_m:Q",
                            color=alt.Color("level:N", scale=alt.Scale(domain=["LSL", "FRL", "Current WL"], range=["#64748b", "#ef4444", "#0f766e"]), legend=alt.Legend(title="Reference")),
                            tooltip=[
                                "level",
                                alt.Tooltip("datum_adjusted_elevation_m:Q", title="Elev. above datum (m)", format=",.2f"),
                                alt.Tooltip("elevation_m:Q", title="Elevation (m)", format=",.2f"),
                            ],
                        )
                    )
                    curve_layers.append(reference_rules)
                curve_chart = (
                    alt.layer(*curve_layers)
                    .resolve_scale(x="independent")
                    .properties(
                        height=430,
                        title=alt.TitleParams(
                            text=f"Elevation - Water Spread Area - Capacity Curve (SRS Technique): {selected_curve_reservoir}",
                            anchor="middle",
                            fontSize=14,
                            fontWeight=700,
                        ),
                    )
                )
                st.altair_chart(curve_chart, use_container_width=True)
                st.caption(
                    "Red square curve: water spread area by trend line on the bottom axis. Blue curve: cumulative live capacity by SRS technique on the top axis. The supporting table below follows the SRS capacity format with segmental and cumulative live capacity."
                )
                st.markdown("**SRS Elevation-Area-Capacity Table**")
                srs_table = curve_df[
                    [
                        "srs_level_label",
                        "elevation_m",
                        "water_spread_area_msqm",
                        "segmental_live_capacity_mcm",
                        "cumulative_storage_mcm",
                    ]
                ].rename(
                    columns={
                        "srs_level_label": "",
                        "elevation_m": "Reservoir water level in Metre",
                        "water_spread_area_msqm": "Water spread area by trend line (M.Sqm)",
                        "segmental_live_capacity_mcm": "Segmental Live Capacity (Mcm) by SRS technique",
                        "cumulative_storage_mcm": "Cumulative Live Capacity (Mcm) by SRS technique",
                    }
                )
                st.dataframe(
                    srs_table,
                    use_container_width=True,
                    hide_index=True,
                    height=320,
                )

            review_cols = [
                "reservoir_name",
                "district",
                "sub_basin",
                "official_live_capacity_mcm",
                "waterbody_area_sqkm",
                "matched_waterbody_name",
                "waterbody_distance_km",
                "rs_geometry_capacity_mcm",
                "calibrated_capacity_mcm",
                "latest_water_level_m",
                "latest_reported_storage_mcm",
                "model_storage_from_level_mcm",
                "model_vs_reported_storage_pct_of_capacity",
                "capacity_confidence",
            ]
            available_review_cols = [column for column in review_cols if column in capacity_view.columns]
            st.dataframe(
                capacity_view[available_review_cols].sort_values(["capacity_confidence", "reservoir_name"]),
                use_container_width=True,
                hide_index=True,
                height=360,
            )
            st.download_button(
                "Download reservoir capacity estimates",
                data=capacity_view.to_csv(index=False).encode("utf-8"),
                file_name="reservoir_capacity_estimates.csv",
                mime="text/csv",
                key="download_capacity_estimates_capacity_tab",
            )

    with tab_data:
        st.subheader("Time-Aware Data Explorer")
        data_choice = st.radio(
            "Dataset",
            [
                "Reservoir observations",
                "River observations",
                "Gate observations",
                "Reservoir capacity estimates",
                "Reservoir capacity curves",
                "FABDEM capacity curves",
                "Reservoir master",
                "River master",
                "Reports",
            ],
            horizontal=True,
        )
        if data_choice == "Reservoir observations":
            st.dataframe(reservoir_view.sort_values(["observed_at", "reservoir_name"]), use_container_width=True, hide_index=True, height=360)
        elif data_choice == "River observations":
            st.dataframe(river_view.sort_values(["observed_at", "river_name", "gauge_station"]), use_container_width=True, hide_index=True, height=360)
        elif data_choice == "Gate observations":
            st.dataframe(gate_view_all.sort_values(["report_at", "reservoir_name"]), use_container_width=True, hide_index=True, height=360)
        elif data_choice == "Reservoir capacity estimates":
            st.dataframe(capacity_view.sort_values(["district", "reservoir_name"]), use_container_width=True, hide_index=True, height=360)
        elif data_choice == "Reservoir capacity curves":
            st.dataframe(capacity_curve_view.sort_values(["reservoir_name", "elevation_m"]), use_container_width=True, hide_index=True, height=360)
        elif data_choice == "FABDEM capacity curves":
            st.dataframe(capacity_curve_fabdem_view.sort_values(["reservoir_name", "elevation_m"]), use_container_width=True, hide_index=True, height=360)
        elif data_choice == "Reservoir master":
            st.dataframe(reservoir_master.sort_values(["district", "reservoir_name"]), use_container_width=True, hide_index=True, height=360)
        elif data_choice == "River master":
            st.dataframe(river_master.sort_values(["district", "river_name", "gauge_station"]), use_container_width=True, hide_index=True, height=360)
        else:
            st.dataframe(meta_df, use_container_width=True, hide_index=True, height=260)

    with tab_exports:
        st.subheader("Captured Data Files")
        st.markdown('<div class="panel-note">Downloads reflect the current report and sidebar time/district filters.</div>', unsafe_allow_html=True)
        export_cols = st.columns(3)
        export_cols[0].download_button(
            "Download river time series",
            data=river_view.to_csv(index=False).encode("utf-8"),
            file_name="river_water_level_observations.csv",
            mime="text/csv",
        )
        export_cols[1].download_button(
            "Download reservoir time series",
            data=reservoir_view.to_csv(index=False).encode("utf-8"),
            file_name="reservoir_status_observations.csv",
            mime="text/csv",
        )
        export_cols[2].download_button(
            "Download gates time series",
            data=gate_view_all.to_csv(index=False).encode("utf-8"),
            file_name="reservoir_gate_observations.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download reservoir capacity estimates",
            data=capacity_view.to_csv(index=False).encode("utf-8"),
            file_name="reservoir_capacity_estimates.csv",
            mime="text/csv",
            key="download_capacity_estimates_exports_tab",
        )
        st.download_button(
            "Download reservoir capacity curves",
            data=capacity_curve_view.to_csv(index=False).encode("utf-8"),
            file_name="reservoir_capacity_curves.csv",
            mime="text/csv",
            key="download_capacity_curves_exports_tab",
        )
        if not capacity_curve_fabdem_view.empty:
            st.download_button(
                "Download FABDEM capacity curves",
                data=capacity_curve_fabdem_view.to_csv(index=False).encode("utf-8"),
                file_name="reservoir_capacity_curves_fabdem.csv",
                mime="text/csv",
                key="download_capacity_curves_fabdem_exports_tab",
            )
        master_cols = st.columns(2)
        master_cols[0].download_button(
            "Download river master",
            data=river_master.to_csv(index=False).encode("utf-8"),
            file_name="river_gauge_stations.csv",
            mime="text/csv",
        )
        master_cols[1].download_button(
            "Download reservoir master",
            data=reservoir_master.to_csv(index=False).encode("utf-8"),
            file_name="reservoirs.csv",
            mime="text/csv",
        )

    api_base_url = "http://127.0.0.1:8600"
    api_status = api_is_available(api_base_url)
    with st.expander("External Data API / GeoJSON Sources", expanded=False):
        status_cols = st.columns([0.78, 2.2])
        status_cols[0].metric("API Status", "Online" if api_status else "Offline")
        if api_status:
            status_cols[1].success(f"REST and GeoJSON services are available at {api_base_url}")
        else:
            status_cols[1].warning("API server is not responding. Start it with Flood Reports\\run_api.ps1.")

        api_cards = [
            ("Reports", f"{api_base_url}/api/reports"),
            ("Reservoir Observations", f"{api_base_url}/api/reservoir-observations"),
            ("District Summary", f"{api_base_url}/api/district-summary"),
            ("Basin Summary", f"{api_base_url}/api/basin-summary"),
            ("Dam GeoJSON", f"{api_base_url}/api/geojson/dams"),
            ("Reservoir Status GeoJSON", f"{api_base_url}/api/geojson/reservoir-status"),
            ("Alert GeoJSON", f"{api_base_url}/api/geojson/alerts"),
            ("Bansagar Filter Example", f"{api_base_url}/api/reservoir-observations?reservoir=Bansagar"),
        ]
        cards_html = '<div class="api-grid">'
        for label, url in api_cards:
            cards_html += f'<div class="api-card"><b>{label}</b><code>{url}</code></div>'
        cards_html += "</div>"
        st.markdown(cards_html, unsafe_allow_html=True)
        link_cols = st.columns(3)
        link_cols[0].link_button("Open API Home", api_base_url)
        link_cols[1].link_button("Open Reservoir GeoJSON", f"{api_base_url}/api/geojson/reservoir-status")
        link_cols[2].link_button("Open Alert GeoJSON", f"{api_base_url}/api/geojson/alerts")
        st.caption("Use the GeoJSON URLs as external layers in ArcGIS Online, QGIS, web maps, Power BI, or the NITA AI platform.")

