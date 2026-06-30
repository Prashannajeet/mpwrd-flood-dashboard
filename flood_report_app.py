from __future__ import annotations

import json
import math
import os
import hmac
import hashlib
import smtplib
import sqlite3
import sys
import re
import subprocess
import unicodedata
import uuid
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from email.message import EmailMessage
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
RIVER_FORECAST_SERVICE_CACHE_JSON = APP_DIR / "data" / "river_forecast_service_status.json"
LOCAL_NARMADA_OBSERVED_CSV = Path(r"D:\01 Project\03 MPWRD\14 Digitial Atlas\01 Data\06 Excel CSV\GD Sites\Corrected\narmada_data.csv")
LOCAL_GD_SITES_SWEDES_ZIP = Path(r"D:\01 Project\03 MPWRD\14 Digitial Atlas\01 Data\01 SHP\Deliverables\Task 5\GD Sites SWEDES.zip")
NARMADA_OBSERVED_CSV = (
    APP_DIR / "data" / "narmada_observed.csv"
    if (APP_DIR / "data" / "narmada_observed.csv").exists()
    else LOCAL_NARMADA_OBSERVED_CSV
)
GD_SITES_SWEDES_LAYER = (
    APP_DIR / "data" / "gd_sites_swedes.geojson"
    if (APP_DIR / "data" / "gd_sites_swedes.geojson").exists()
    else LOCAL_GD_SITES_SWEDES_ZIP
)
WEATHER_CACHE_DB = APP_DIR / "data" / "weather_cache.sqlite"
VISITOR_ANALYTICS_DB = APP_DIR / "data" / "visitor_analytics.sqlite"
RIVER_FLOW_FORECAST_DB = APP_DIR / "data" / "river_flow_forecasts.sqlite"
GD_SITE_FORECAST_DB = APP_DIR / "data" / "gd_site_forecasts.sqlite"
RIVER_FLOW_MODEL_DIR = APP_DIR / "models" / "river_flow_tensorflow"
WEATHER_REFRESH_HOURS = 3
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


def open_meteo_base_url() -> str:
    value = os.getenv("OPEN_METEO_BASE_URL", "").strip()
    if value:
        return value.rstrip("/")
    try:
        value = str(st.secrets.get("open_meteo_base_url", "")).strip()
        if value:
            return value.rstrip("/")
    except Exception:
        pass
    return "https://api.open-meteo.com"
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
    "#2563eb",
    "#0891b2",
    "#10b981",
    "#65a30d",
    "#facc15",
    "#f97316",
    "#ef4444",
    "#db2777",
    "#8b5cf6",
    "#111827",
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


def prettify_dataframe_columns_unique(data: pd.DataFrame) -> pd.DataFrame:
    renamed = data.copy()
    labels = []
    counts: dict[str, int] = {}
    for column in renamed.columns:
        label = column_display_label(column)
        counts[label] = counts.get(label, 0) + 1
        if counts[label] > 1:
            label = f"{label} {counts[label]}"
        labels.append(label)
    renamed.columns = labels
    return renamed


def friendly_column_config(data: pd.DataFrame, existing: dict | None = None) -> dict:
    config = dict(existing or {})
    for column in data.columns:
        if column not in config:
            config[column] = st.column_config.Column(column_display_label(column))
    return config


_ORIGINAL_ST_DATAFRAME = getattr(st.dataframe, "_mpwrd_original_dataframe", st.dataframe)


def _dataframe_with_friendly_headers(data=None, *args, **kwargs):
    return _ORIGINAL_ST_DATAFRAME(prettify_dataframe_columns(data), *args, **kwargs)


_dataframe_with_friendly_headers._mpwrd_original_dataframe = _ORIGINAL_ST_DATAFRAME
if not getattr(st.dataframe, "_mpwrd_friendly_wrapper", False):
    _dataframe_with_friendly_headers._mpwrd_friendly_wrapper = True
    st.dataframe = _dataframe_with_friendly_headers


def scalar_cell_value(value: object) -> object:
    if isinstance(value, pd.Series):
        return value.iloc[0] if not value.empty else None
    return value


def filling_category(value: object) -> str:
    value = scalar_cell_value(value)
    filling = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(filling):
        return "No Data"
    if filling < 25:
        return "0-25%"
    if filling < 50:
        return "25-50%"
    if filling < 75:
        return "50-75%"
    return "75-100%"


def filling_percent_style(value: object) -> str:
    value = scalar_cell_value(value)
    filling = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(filling):
        return "background-color:#f1f5f9;color:#64748b;"
    if filling < 25:
        return "background-color:#dbeafe;color:#1e3a8a;font-weight:800;"
    if filling < 50:
        return "background-color:#cffafe;color:#155e75;font-weight:800;"
    if filling < 75:
        return "background-color:#fef3c7;color:#92400e;font-weight:800;"
    return "background-color:#fee2e2;color:#991b1b;font-weight:800;"


def hex_to_rgba(hex_color: str, alpha: float = 0.16) -> str:
    value = str(hex_color).lstrip("#")
    if len(value) != 6:
        return f"rgba(37,99,235,{alpha})"
    red, green, blue = (int(value[idx : idx + 2], 16) for idx in (0, 2, 4))
    return f"rgba({red},{green},{blue},{alpha})"


def district_color_map(values: pd.Series) -> dict[str, str]:
    palette = [
        "#2563eb",
        "#0891b2",
        "#10b981",
        "#65a30d",
        "#f59e0b",
        "#ef4444",
        "#db2777",
        "#8b5cf6",
        "#0f766e",
        "#7c3aed",
        "#ea580c",
        "#0284c7",
    ]
    districts = sorted({str(value).strip() for value in values.dropna() if str(value).strip()})
    return {district: palette[index % len(palette)] for index, district in enumerate(districts)}


def first_existing_column(columns: pd.Index, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def unique_existing_columns(columns: list[str], available: pd.Index) -> list[str]:
    result = []
    seen = set()
    for column in columns:
        if column in available and column not in seen:
            result.append(column)
            seen.add(column)
    return result


def render_colored_dam_table(
    frame: pd.DataFrame,
    key_prefix: str,
    columns: list[str] | None = None,
    height: int = 360,
    allow_filters: bool = True,
) -> pd.DataFrame:
    if frame.empty:
        st.info("No dam records are available for the selected filters.")
        return frame

    table = frame.copy()
    if "filling_percent" not in table and "display_filling" in table:
        table["filling_percent"] = table["display_filling"]
    if "filling_percent" in table:
        table["filling_percent"] = pd.to_numeric(table["filling_percent"], errors="coerce")
        table["filling_category"] = table["filling_percent"].apply(filling_category)

    district_col = first_existing_column(table.columns, ["district", "map_district"])
    basin_col = first_existing_column(table.columns, ["sub_basin", "major_basin"])
    name_col = first_existing_column(table.columns, ["reservoir_name", "dam_name"])

    if allow_filters:
        filter_cols = st.columns([0.24, 0.24, 0.24, 0.18, 0.10])
        with filter_cols[0]:
            selected_districts = st.multiselect(
                "District",
                sorted(table[district_col].dropna().astype(str).unique()) if district_col else [],
                key=f"{key_prefix}_district_filter",
            )
        with filter_cols[1]:
            selected_basins = st.multiselect(
                "Basin",
                sorted(table[basin_col].dropna().astype(str).unique()) if basin_col else [],
                key=f"{key_prefix}_basin_filter",
            )
        with filter_cols[2]:
            selected_dams = st.multiselect(
                "Dam",
                sorted(table[name_col].dropna().astype(str).unique()) if name_col else [],
                key=f"{key_prefix}_dam_filter",
            )
        with filter_cols[3]:
            selected_bands = st.multiselect(
                "Filling",
                ["0-25%", "25-50%", "50-75%", "75-100%", "No Data"] if "filling_category" in table else [],
                key=f"{key_prefix}_filling_filter",
            )
        with filter_cols[4]:
            search_text = st.text_input("Search", key=f"{key_prefix}_search_filter")

        if district_col and selected_districts:
            table = table[table[district_col].astype(str).isin(selected_districts)]
        if basin_col and selected_basins:
            table = table[table[basin_col].astype(str).isin(selected_basins)]
        if name_col and selected_dams:
            table = table[table[name_col].astype(str).isin(selected_dams)]
        if selected_bands and "filling_category" in table:
            table = table[table["filling_category"].isin(selected_bands)]
        if search_text.strip():
            searchable_cols = [col for col in [name_col, district_col, basin_col] if col and col in table]
            if searchable_cols:
                query = search_text.strip().casefold()
                mask = table[searchable_cols].astype(str).apply(
                    lambda row: query in " ".join(row.tolist()).casefold(),
                    axis=1,
                )
                table = table[mask]

    if table.empty:
        st.info("No dam records match the table filters.")
        return table

    visible_cols = unique_existing_columns(columns or list(table.columns), table.columns)
    if "filling_category" in table and "filling_category" not in visible_cols:
        insert_at = visible_cols.index("filling_percent") + 1 if "filling_percent" in visible_cols else len(visible_cols)
        visible_cols.insert(insert_at, "filling_category")
    visible_cols = unique_existing_columns(visible_cols, table.columns)

    display = table[visible_cols].copy()
    for column in display.select_dtypes(include="number").columns:
        display[column] = pd.to_numeric(display[column], errors="coerce").round(2)

    pretty_display = prettify_dataframe_columns_unique(display)
    display_label_map = dict(zip(display.columns, pretty_display.columns))
    pretty_district_col = display_label_map.get(district_col) if district_col in display.columns else None
    pretty_name_cols = [
        display_label_map[col]
        for col in ["reservoir_name", "dam_name"]
        if col in display.columns
    ]
    district_colors = district_color_map(display[district_col]) if district_col in display.columns else {}

    def district_cell_style(value: object) -> str:
        value = scalar_cell_value(value)
        color = district_colors.get(str(value).strip(), "#2563eb")
        return f"background-color:{hex_to_rgba(color, 0.18)};border-left:4px solid {color};font-weight:800;color:#0f172a;"

    def row_style(row: pd.Series) -> list[str]:
        district_value = scalar_cell_value(row.get(pretty_district_col, "")) if pretty_district_col else ""
        color = district_colors.get(str(district_value).strip(), "#2563eb") if pretty_district_col else "#2563eb"
        return [
            f"border-left:4px solid {color};font-weight:760;color:#0f172a;" if column in pretty_name_cols else ""
            for column in row.index
        ]

    styler = pretty_display.style.format(precision=2, na_rep="-")
    filling_style_cols = [
        display_label_map[col]
        for col in ["filling_percent", "display_filling"]
        if col in display.columns and display_label_map.get(col) in pretty_display.columns
    ]
    if filling_style_cols:
        styler = styler.map(filling_percent_style, subset=filling_style_cols)
    if pretty_district_col and pretty_district_col in pretty_display.columns:
        styler = styler.map(district_cell_style, subset=[pretty_district_col])
        styler = styler.apply(row_style, axis=1)

    _ORIGINAL_ST_DATAFRAME(styler, use_container_width=True, hide_index=True, height=height)
    return table


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
    .visitor-counter-card {
        margin: 0.75rem 0 1rem;
        padding: 0.76rem 0.82rem;
        border: 1px solid #dbeafe;
        border-radius: 8px;
        background:
            linear-gradient(135deg, rgba(255,255,255,0.98), rgba(239,246,255,0.98)),
            linear-gradient(90deg, rgba(20,125,245,0.12), rgba(10,255,153,0.10));
        box-shadow: 0 12px 24px rgba(37, 99, 235, 0.08);
    }
    .visitor-counter-card span {
        display: block;
        color: #7c3aed;
        font-size: 0.68rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 0.08em !important;
    }
    .visitor-counter-card b {
        display: block;
        color: #0f172a;
        font-size: 1.55rem;
        line-height: 1.12;
        font-weight: 900;
        margin-top: 0.15rem;
    }
    .visitor-counter-card small {
        display: block;
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 700;
        margin-top: 0.18rem;
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
        border: 1px solid rgba(125, 149, 190, 0.36);
        border-radius: 8px;
        background:
            linear-gradient(135deg, rgba(255,255,255,0.99), rgba(248,250,252,0.96)),
            linear-gradient(135deg, rgba(37,99,235,0.14), rgba(16,185,129,0.10), rgba(249,115,22,0.10));
        padding: 0.72rem;
        box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
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
        border: 1px solid rgba(148, 163, 184, 0.38);
        border-top: 3px solid #2563eb;
        border-radius: 8px;
        background: rgba(255,255,255,0.97);
        padding: 0.55rem 0.62rem;
        min-height: 72px;
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    }
    .infographic-card span {
        display: block;
        color: #475569;
        font-size: 0.66rem;
        font-weight: 760;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    .infographic-card b {
        display: block;
        color: #0f172a;
        font-size: 1.22rem;
        line-height: 1.15;
        margin-top: 0.28rem;
    }
    .infographic-card small {
        display: block;
        color: #64748b;
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
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["curl.exe", "-s", "--max-time", "18", url],
                capture_output=True,
                check=True,
                text=True,
                timeout=22,
            )
            if result.stdout.strip():
                return json.loads(result.stdout), None
        except Exception:
            pass
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


def weather_now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def weather_location_key(latitude: float, longitude: float) -> str:
    return f"{float(latitude):.5f},{float(longitude):.5f}"


def weather_cache_is_fresh(fetched_at: str | None) -> bool:
    if not fetched_at:
        return False
    try:
        age = weather_now_utc() - pd.Timestamp(fetched_at)
    except Exception:
        return False
    return age <= pd.Timedelta(hours=WEATHER_REFRESH_HOURS)


def init_weather_database() -> None:
    WEATHER_CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_forecast_cache (
                location_key TEXT PRIMARY KEY,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                daily_json TEXT NOT NULL,
                hourly_json TEXT NOT NULL,
                current_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                source_url TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_current_cache (
                location_key TEXT PRIMARY KEY,
                town_name TEXT,
                district TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                current_json TEXT NOT NULL,
                status TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                source_url TEXT NOT NULL
            )
            """
        )
        conn.commit()


def dataframe_to_weather_json(frame: pd.DataFrame) -> str:
    payload = {
        "columns": list(frame.columns),
        "records": json.loads(frame.to_json(orient="records", date_format="iso")),
    }
    return json.dumps(payload)


def dataframe_from_weather_json(payload_text: str) -> pd.DataFrame:
    try:
        payload = json.loads(payload_text or "{}")
    except json.JSONDecodeError:
        return pd.DataFrame()
    records = payload.get("records") or []
    columns = payload.get("columns") or None
    frame = pd.DataFrame(records)
    if columns:
        for column in columns:
            if column not in frame:
                frame[column] = pd.NA
        frame = frame[columns]
    return frame


def normalize_weather_frames(
    daily: pd.DataFrame,
    hourly: pd.DataFrame,
    current: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    return daily, hourly, current


def get_weather_cache_summary() -> dict:
    init_weather_database()
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        forecast_count = conn.execute("SELECT COUNT(*) FROM weather_forecast_cache").fetchone()[0]
        current_count = conn.execute("SELECT COUNT(*) FROM weather_current_cache").fetchone()[0]
        latest_row = conn.execute(
            """
            SELECT MAX(fetched_at) FROM (
                SELECT fetched_at FROM weather_forecast_cache
                UNION ALL
                SELECT fetched_at FROM weather_current_cache
            )
            """
        ).fetchone()
    latest = latest_row[0] if latest_row and latest_row[0] else ""
    return {"forecast_locations": forecast_count, "current_locations": current_count, "latest_refresh": latest}


def get_cached_open_meteo_weather(
    latitude: float,
    longitude: float,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str | None, str]:
    init_weather_database()
    key = weather_location_key(latitude, longitude)
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        row = None
        if not force_refresh:
            row = conn.execute(
                """
                SELECT daily_json, hourly_json, current_json, fetched_at
                FROM weather_forecast_cache
                WHERE location_key = ?
                """,
                (key,),
            ).fetchone()
        if row and weather_cache_is_fresh(row[3]):
            daily = dataframe_from_weather_json(row[0])
            hourly = dataframe_from_weather_json(row[1])
            current = dataframe_from_weather_json(row[2])
            daily, hourly, current = normalize_weather_frames(daily, hourly, current)
            return daily, hourly, current, None, "database cache"

    daily, hourly, current, error = fetch_open_meteo_weather(latitude, longitude)
    if error:
        if row:
            daily = dataframe_from_weather_json(row[0])
            hourly = dataframe_from_weather_json(row[1])
            current = dataframe_from_weather_json(row[2])
            daily, hourly, current = normalize_weather_frames(daily, hourly, current)
            return daily, hourly, current, f"{error} Showing stored weather data from {row[3]}.", "stale database cache"
        return daily, hourly, current, error, "api failed"

    fetched_at = weather_now_utc().isoformat()
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO weather_forecast_cache
            (location_key, latitude, longitude, daily_json, hourly_json, current_json, fetched_at, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                float(latitude),
                float(longitude),
                dataframe_to_weather_json(daily),
                dataframe_to_weather_json(hourly),
                dataframe_to_weather_json(current),
                fetched_at,
                open_meteo_url(latitude, longitude),
            ),
        )
        conn.commit()
    return daily, hourly, current, None, "api refreshed"


def get_cached_open_meteo_current(
    town_name: str,
    district: str,
    latitude: float,
    longitude: float,
    force_refresh: bool = False,
) -> tuple[dict, str | None, str]:
    init_weather_database()
    key = weather_location_key(latitude, longitude)
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        row = None
        if not force_refresh:
            row = conn.execute(
                """
                SELECT current_json, status, fetched_at
                FROM weather_current_cache
                WHERE location_key = ?
                """,
                (key,),
            ).fetchone()
        if row and weather_cache_is_fresh(row[2]):
            try:
                return json.loads(row[0]), None, "database cache"
            except json.JSONDecodeError:
                pass

    current, error = fetch_open_meteo_current(latitude, longitude)
    if error:
        if row:
            try:
                return json.loads(row[0]), f"{error} Showing stored weather data from {row[2]}.", "stale database cache"
            except json.JSONDecodeError:
                pass
        return {}, error, "api failed"

    fetched_at = weather_now_utc().isoformat()
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO weather_current_cache
            (location_key, town_name, district, latitude, longitude, current_json, status, fetched_at, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                town_name,
                district,
                float(latitude),
                float(longitude),
                json.dumps(current, default=str),
                "Fetched",
                fetched_at,
                open_meteo_current_url(latitude, longitude),
            ),
        )
        conn.commit()
    return current, None, "api refreshed"


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


def parse_dms_coordinate(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = unicodedata.normalize("NFKD", str(value)).replace("�", " ").replace("°", " ")
    parts = re.findall(r"-?\d+(?:\.\d+)?", text)
    if not parts:
        return None
    numbers = [float(part) for part in parts[:3]]
    sign = -1 if str(value).strip().startswith("-") else 1
    degrees = abs(numbers[0])
    minutes = numbers[1] if len(numbers) > 1 else 0.0
    seconds = numbers[2] if len(numbers) > 2 else 0.0
    return sign * (degrees + minutes / 60.0 + seconds / 3600.0)


@st.cache_data(show_spinner=False)
def load_gd_sites_swedes(zip_path: str) -> pd.DataFrame:
    path = Path(zip_path)
    if not path.exists():
        return pd.DataFrame()
    try:
        import geopandas as gpd

        gdf = gpd.read_file(f"zip://{path}" if path.suffix.lower() == ".zip" else path)
    except Exception:
        return pd.DataFrame()

    sites = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore")).copy()
    sites["station_code"] = sites.get("Station Co", pd.Series(dtype=str)).astype(str).str.strip()
    sites["station_name"] = sites.get("Station Na", pd.Series(dtype=str)).astype(str).str.strip()
    sites["district"] = sites.get("District", pd.Series(dtype=str)).astype(str).str.strip()
    sites["river"] = sites.get("River", pd.Series(dtype=str)).astype(str).str.strip()
    sites["tributary"] = sites.get("Tributary", pd.Series(dtype=str)).astype(str).str.strip()
    sites["zero_rl_m"] = pd.to_numeric(sites.get("Zero RL"), errors="coerce")
    sites["site_type"] = sites.get("SW_Station", sites.get("Site_Type", pd.Series(dtype=str))).astype(str)
    sites["station_operational"] = sites.get("Station_Op", pd.Series(dtype=str)).astype(str)
    sites["latitude"] = pd.Series([None] * len(sites), dtype="float64")
    sites["longitude"] = pd.Series([None] * len(sites), dtype="float64")
    if "geometry" in gdf:
        valid_geom = ~gdf.geometry.isna()
        sites.loc[valid_geom, "latitude"] = gdf.loc[valid_geom].geometry.y.astype(float)
        sites.loc[valid_geom, "longitude"] = gdf.loc[valid_geom].geometry.x.astype(float)
    lat_from_field = sites.get("Lat", pd.Series(index=sites.index, dtype=object)).map(parse_dms_coordinate)
    lon_from_field = sites.get("Long", pd.Series(index=sites.index, dtype=object)).map(parse_dms_coordinate)
    sites["latitude"] = pd.to_numeric(sites["latitude"], errors="coerce").fillna(pd.to_numeric(lat_from_field, errors="coerce"))
    sites["longitude"] = pd.to_numeric(sites["longitude"], errors="coerce").fillna(pd.to_numeric(lon_from_field, errors="coerce"))
    sites["has_location"] = sites["latitude"].notna() & sites["longitude"].notna()
    useful_cols = [
        "station_code",
        "station_name",
        "district",
        "river",
        "tributary",
        "zero_rl_m",
        "latitude",
        "longitude",
        "has_location",
        "site_type",
        "station_operational",
    ]
    return sites[useful_cols].dropna(subset=["station_code"]).drop_duplicates("station_code").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_latest_gd_observed(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        return pd.DataFrame()
    try:
        observed = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    observed.columns = [str(column).strip() for column in observed.columns]
    required = {"Station Code", "Reading Date Time", "WL"}
    if not required.issubset(observed.columns):
        return pd.DataFrame()
    observed["observed_at"] = pd.to_datetime(observed["Reading Date Time"], errors="coerce")
    observed["water_level_m"] = pd.to_numeric(observed["WL"], errors="coerce")
    observed["station_code"] = observed["Station Code"].astype(str).str.strip()
    observed["entry_type"] = observed.get("Entry Type", "").astype(str)
    observed["data_type"] = observed.get("Data Type", "").astype(str)
    observed["zero_rl_observed_m"] = pd.to_numeric(observed.get("Zero RL"), errors="coerce")
    valid = observed.dropna(subset=["station_code", "observed_at", "water_level_m"]).copy()
    if valid.empty:
        return pd.DataFrame()
    valid = valid.sort_values(["station_code", "observed_at"])
    valid["wl_delta_m"] = valid.groupby("station_code")["water_level_m"].diff()
    latest = valid.groupby("station_code", dropna=False).tail(1)
    return latest[
        ["station_code", "observed_at", "water_level_m", "wl_delta_m", "entry_type", "data_type", "zero_rl_observed_m"]
    ].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_gd_observed_history(csv_path: str, days: int = 31) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        return pd.DataFrame()
    try:
        observed = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    observed.columns = [str(column).strip() for column in observed.columns]
    required = {"Station Code", "Reading Date Time", "WL"}
    if not required.issubset(observed.columns):
        return pd.DataFrame()
    observed["station_code"] = observed["Station Code"].astype(str).str.strip()
    observed["observed_at"] = pd.to_datetime(observed["Reading Date Time"], errors="coerce")
    observed["water_level_m"] = pd.to_numeric(observed["WL"], errors="coerce")
    observed["data_type"] = observed.get("Data Type", "").astype(str)
    observed["entry_type"] = observed.get("Entry Type", "").astype(str)
    valid = observed.dropna(subset=["station_code", "observed_at", "water_level_m"]).copy()
    if valid.empty:
        return pd.DataFrame()
    max_time = valid["observed_at"].max()
    start_time = max_time - pd.Timedelta(days=days)
    history = valid[valid["observed_at"] >= start_time].sort_values(["station_code", "observed_at"]).copy()
    history["water_level_change_m"] = history.groupby("station_code")["water_level_m"].diff()
    return history[["station_code", "observed_at", "water_level_m", "water_level_change_m", "entry_type", "data_type"]].reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_online_river_forecast_time() -> pd.Timestamp | None:
    payload = None
    url = f"{GEOGLOWS_MEDIUM_URL}/0?f=json"
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        try:
            result = subprocess.run(
                ["curl.exe", "-s", "--max-time", "8", url],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                payload = json.loads(result.stdout)
        except Exception:
            payload = None
    if not payload:
        try:
            if RIVER_FORECAST_SERVICE_CACHE_JSON.exists():
                payload = json.loads(RIVER_FORECAST_SERVICE_CACHE_JSON.read_text(encoding="utf-8"))
        except Exception:
            payload = None
    if not payload:
        return None
    extent = payload.get("timeInfo", {}).get("timeExtent") or []
    values = [value for value in extent if isinstance(value, (int, float))]
    if not values:
        return None
    now_ms = pd.Timestamp.now(tz="UTC").timestamp() * 1000
    selected = min(values, key=lambda value: abs(float(value) - now_ms))
    return pd.to_datetime(selected, unit="ms", utc=True).tz_convert("Asia/Kolkata")


def build_gd_site_forecast_rows(
    gd_sites: pd.DataFrame,
    latest_observed: pd.DataFrame,
    basin_nodes: list[dict] | None = None,
    runoff_nodes: list[dict] | None = None,
    forecast_days: int = 7,
    online_now_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    if gd_sites.empty:
        return pd.DataFrame()
    sites = gd_sites.copy()
    latest = latest_observed.copy() if not latest_observed.empty else pd.DataFrame(columns=["station_code"])
    merged = sites.merge(latest, on="station_code", how="left")
    rows = []
    if online_now_time is not None and pd.notna(online_now_time):
        base_date = pd.Timestamp(online_now_time).tz_convert("Asia/Kolkata").normalize()
        current_timestamp = pd.Timestamp(online_now_time).tz_convert("Asia/Kolkata")
        online_status = "Online current signal"
    else:
        current_timestamp = pd.Timestamp.now(tz="Asia/Kolkata")
        base_date = current_timestamp.normalize()
        online_status = "Current generated signal"
    for record in merged.to_dict("records"):
        context = pd.Series(
            {
                "basin": record.get("river") or record.get("tributary") or "Madhya Pradesh",
                "river_name": record.get("river"),
                "district": record.get("district"),
            }
        )
        basin_node = match_forecast_node(context, basin_nodes or [])
        runoff_node = match_forecast_node(context, runoff_nodes or [])
        basin_flow = latest_node_flow(basin_node, ["glofas_p50_cms", "reservoir_attenuated_cms", "chirps_hindcast_cms"]) if basin_node else float("nan")
        river_flow = latest_node_flow(runoff_node, ["reforecast_p50_cms", "reservoir_adjusted_cms", "reanalysis_discharge_cms"]) if runoff_node else float("nan")
        wl = pd.to_numeric(pd.Series([record.get("water_level_m")]), errors="coerce").iloc[0]
        wl_delta = pd.to_numeric(pd.Series([record.get("wl_delta_m")]), errors="coerce").iloc[0]
        zero_rl = pd.to_numeric(pd.Series([record.get("zero_rl_observed_m")]), errors="coerce").iloc[0]
        if pd.isna(zero_rl):
            zero_rl = pd.to_numeric(pd.Series([record.get("zero_rl_m")]), errors="coerce").iloc[0]
        external_values = [float(value) for value in [basin_flow, river_flow] if not pd.isna(value)]
        external_base = sum(external_values) / len(external_values) if external_values else float("nan")
        observed_at = record.get("observed_at")
        observed_age_days = None
        if pd.notna(observed_at):
            observed_age_days = (current_timestamp.tz_convert("UTC") - pd.Timestamp(observed_at).tz_convert("UTC")).days
        for lead_day in range(0, forecast_days + 1):
            forecast_time = current_timestamp if lead_day == 0 else base_date + pd.Timedelta(days=lead_day)
            if pd.isna(external_base):
                forecast_flow = float("nan")
            else:
                stage_signal = max(0.0, float(wl or 0) - float(zero_rl or 0)) * 12.0 if not pd.isna(wl) and not pd.isna(zero_rl) else 0.0
                trend_signal = (0.0 if pd.isna(wl_delta) else float(wl_delta)) * 18.0
                lead_factor = 1.0 + lead_day * 0.025
                forecast_flow = max(0.0, external_base * lead_factor + stage_signal + trend_signal)
            rows.append(
                {
                    "station_code": record.get("station_code"),
                    "station_name": record.get("station_name"),
                    "district": record.get("district"),
                    "river": record.get("river"),
                    "tributary": record.get("tributary"),
                    "latitude": record.get("latitude"),
                    "longitude": record.get("longitude"),
                    "has_location": record.get("has_location"),
                    "observed_at": observed_at,
                    "observed_age_days": observed_age_days,
                    "current_water_level_m": wl,
                    "water_level_change_m": wl_delta,
                    "zero_rl_m": zero_rl,
                    "forecast_time": forecast_time,
                    "lead_day": lead_day,
                    "current_flow_cms": round(external_base, 3) if lead_day == 0 and external_values else None,
                    "river_forecast_flow_cms": river_flow,
                    "basin_forecast_flow_cms": basin_flow,
                    "combined_forecast_flow_cms": round(forecast_flow, 3) if not pd.isna(forecast_flow) else None,
                    "data_period": "Now Data" if lead_day == 0 else "Forecasted Data",
                    "forecast_status": online_status if external_values else "Observed only",
                }
            )
    out = pd.DataFrame(rows)
    for column in ["current_water_level_m", "water_level_change_m", "zero_rl_m", "observed_age_days", "current_flow_cms", "river_forecast_flow_cms", "basin_forecast_flow_cms", "combined_forecast_flow_cms"]:
        if column in out:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def gd_forecast_slot(timestamp: pd.Timestamp | None = None) -> tuple[str, str, pd.Timestamp]:
    ts = pd.Timestamp(timestamp if timestamp is not None else pd.Timestamp.now(tz="Asia/Kolkata"))
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Kolkata")
    else:
        ts = ts.tz_convert("Asia/Kolkata")
    slot_hours = [8, 12, 16, 20]
    slot_hour = max([hour for hour in slot_hours if hour <= ts.hour], default=20)
    slot_date = ts.normalize()
    if ts.hour < 8:
        slot_date = (ts - pd.Timedelta(days=1)).normalize()
    slot_ts = slot_date + pd.Timedelta(hours=slot_hour)
    return slot_date.strftime("%Y-%m-%d"), f"{slot_hour:02d}:00", slot_ts


def init_gd_site_forecast_db() -> None:
    GD_SITE_FORECAST_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(GD_SITE_FORECAST_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gd_site_forecasts (
                forecast_id TEXT PRIMARY KEY,
                slot_date TEXT NOT NULL,
                slot_time TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                station_code TEXT,
                station_name TEXT,
                district TEXT,
                river TEXT,
                tributary TEXT,
                latitude REAL,
                longitude REAL,
                observed_at TEXT,
                observed_age_days REAL,
                forecast_time TEXT,
                data_period TEXT,
                current_flow_cms REAL,
                current_water_level_m REAL,
                water_level_change_m REAL,
                river_forecast_flow_cms REAL,
                basin_forecast_flow_cms REAL,
                combined_forecast_flow_cms REAL,
                linked_comid TEXT,
                streamorder REAL,
                return_period REAL,
                forecast_status TEXT
            )
            """
        )
        for column_name, column_type in [
            ("linked_comid", "TEXT"),
            ("streamorder", "REAL"),
            ("return_period", "REAL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE gd_site_forecasts ADD COLUMN {column_name} {column_type}")
            except sqlite3.OperationalError:
                pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gd_site_forecasts_slot ON gd_site_forecasts(slot_date, slot_time)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gd_site_forecasts_station_time ON gd_site_forecasts(station_code, forecast_time)")


def save_gd_site_forecasts(forecast_df: pd.DataFrame, slot_timestamp: pd.Timestamp | None = None) -> int:
    if forecast_df.empty:
        return 0
    init_gd_site_forecast_db()
    slot_date, slot_time, slot_ts = gd_forecast_slot(slot_timestamp)
    generated_at = pd.Timestamp.now(tz="Asia/Kolkata").isoformat()
    rows = forecast_df.copy()
    rows["slot_date"] = slot_date
    rows["slot_time"] = slot_time
    rows["generated_at"] = generated_at
    rows["forecast_id"] = rows.apply(
        lambda row: hashlib.sha256(
            "|".join(
                str(row.get(column) or "")
                for column in ["slot_date", "slot_time", "station_code", "forecast_time", "data_period"]
            ).encode("utf-8", errors="ignore")
        ).hexdigest()[:32],
        axis=1,
    )
    cols = [
        "forecast_id",
        "slot_date",
        "slot_time",
        "generated_at",
        "station_code",
        "station_name",
        "district",
        "river",
        "tributary",
        "latitude",
        "longitude",
        "observed_at",
        "observed_age_days",
        "forecast_time",
        "data_period",
        "current_flow_cms",
        "linked_comid",
        "streamorder",
        "return_period",
        "current_water_level_m",
        "water_level_change_m",
        "river_forecast_flow_cms",
        "basin_forecast_flow_cms",
        "combined_forecast_flow_cms",
        "linked_comid",
        "streamorder",
        "return_period",
        "forecast_status",
    ]
    rows = rows.reindex(columns=cols)
    for datetime_col in ["generated_at", "observed_at", "forecast_time"]:
        rows[datetime_col] = pd.to_datetime(rows[datetime_col], errors="coerce").apply(
            lambda value: value.isoformat() if not pd.isna(value) else None
        )
    with sqlite3.connect(GD_SITE_FORECAST_DB) as conn:
        conn.executemany(
            f"""
            INSERT OR REPLACE INTO gd_site_forecasts ({", ".join(cols)})
            VALUES ({", ".join(["?"] * len(cols))})
            """,
            [tuple(None if pd.isna(value) else value for value in record) for record in rows.to_numpy()],
        )
    return len(rows)


def load_gd_site_forecast_cache() -> pd.DataFrame:
    if not GD_SITE_FORECAST_DB.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(GD_SITE_FORECAST_DB) as conn:
            cached = pd.read_sql_query("SELECT * FROM gd_site_forecasts", conn)
    except Exception:
        return pd.DataFrame()
    for column in ["generated_at", "observed_at", "forecast_time"]:
        if column in cached:
            cached[column] = pd.to_datetime(cached[column], errors="coerce")
    return cached


def load_latest_gd_site_forecast_slot() -> pd.DataFrame:
    cached = load_gd_site_forecast_cache()
    if cached.empty or not {"slot_date", "slot_time"}.issubset(cached.columns):
        return pd.DataFrame()
    latest = cached.sort_values(["slot_date", "slot_time", "generated_at"]).tail(1)
    if latest.empty:
        return pd.DataFrame()
    slot_date = latest.iloc[0].get("slot_date")
    slot_time = latest.iloc[0].get("slot_time")
    return cached[(cached["slot_date"] == slot_date) & (cached["slot_time"] == slot_time)].copy()


def gd_return_period_alert(return_period: object, flow: object = None) -> tuple[str, str]:
    rp = pd.to_numeric(pd.Series([return_period]), errors="coerce").iloc[0]
    flow_value = pd.to_numeric(pd.Series([flow]), errors="coerce").iloc[0]
    if pd.notna(rp):
        if rp >= 25:
            return "Critical", "#ef4444"
        if rp >= 10:
            return "Warning", "#f59e0b"
        if rp >= 2:
            return "Watch", "#eab308"
        return "Normal", "#2563eb"
    if pd.notna(flow_value):
        if flow_value >= 500:
            return "Critical", "#ef4444"
        if flow_value >= 250:
            return "Warning", "#f59e0b"
        if flow_value >= 100:
            return "Watch", "#eab308"
    return "Normal", "#2563eb"


def render_gd_site_leaflet_map(gd_sites: pd.DataFrame, gd_forecasts: pd.DataFrame) -> None:
    if gd_sites.empty or not {"latitude", "longitude"}.issubset(gd_sites.columns):
        return
    gd_now = gd_forecasts[gd_forecasts["data_period"] == "Now Data"].copy() if not gd_forecasts.empty else pd.DataFrame()
    site_latest = gd_now.drop_duplicates("station_code").set_index("station_code") if not gd_now.empty else pd.DataFrame()
    site_series: dict[str, list[dict]] = {}
    if not gd_forecasts.empty:
        for station_code, group in gd_forecasts.sort_values("forecast_time").groupby("station_code"):
            points = []
            for item in group.head(24).to_dict("records"):
                flow_value = pd.to_numeric(pd.Series([item.get("combined_forecast_flow_cms")]), errors="coerce").iloc[0]
                if pd.isna(flow_value):
                    continue
                return_period_value = pd.to_numeric(pd.Series([item.get("return_period")]), errors="coerce").iloc[0]
                points.append(
                    {
                        "time": time_label(item.get("forecast_time")),
                        "flow": round(float(flow_value), 2),
                        "period": str(item.get("data_period") or ""),
                        "return_period": None if pd.isna(return_period_value) else round(float(return_period_value), 0),
                    }
                )
            site_series[str(station_code)] = points
    records = []
    for row in gd_sites.dropna(subset=["latitude", "longitude"]).to_dict("records"):
        station_code = str(row.get("station_code") or "")
        now = site_latest.loc[station_code].to_dict() if not site_latest.empty and station_code in site_latest.index else {}
        flow = pd.to_numeric(pd.Series([now.get("current_flow_cms")]), errors="coerce").iloc[0]
        status = str(now.get("forecast_status") or "Layer pending")
        return_period_value = pd.to_numeric(pd.Series([now.get("return_period")]), errors="coerce").iloc[0]
        level, color = gd_return_period_alert(return_period_value, flow)
        wl_delta = pd.to_numeric(pd.Series([now.get("water_level_change_m")]), errors="coerce").iloc[0]
        if pd.notna(wl_delta) and wl_delta > 0.03:
            trend = "Rising"
        elif pd.notna(wl_delta) and wl_delta < -0.03:
            trend = "Falling"
        else:
            series = site_series.get(station_code, [])
            trend = "Stable"
            if len(series) >= 2:
                if series[1]["flow"] > series[0]["flow"]:
                    trend = "Rising"
                elif series[1]["flow"] < series[0]["flow"]:
                    trend = "Falling"
        records.append(
            {
                "station_code": station_code,
                "station_name": str(row.get("station_name") or station_code or "GD Site"),
                "district": str(row.get("district") or "-"),
                "river": str(row.get("river") or "-"),
                "lat": float(row.get("latitude")),
                "lon": float(row.get("longitude")),
                "current_flow": None if pd.isna(flow) else round(float(flow), 2),
                "water_level": None if pd.isna(pd.to_numeric(pd.Series([now.get("current_water_level_m")]), errors="coerce").iloc[0]) else round(float(pd.to_numeric(pd.Series([now.get("current_water_level_m")]), errors="coerce").iloc[0]), 2),
                "observed_age_days": None if pd.isna(pd.to_numeric(pd.Series([now.get("observed_age_days")]), errors="coerce").iloc[0]) else round(float(pd.to_numeric(pd.Series([now.get("observed_age_days")]), errors="coerce").iloc[0]), 0),
                "forecast_time": time_label(now.get("forecast_time")),
                "linked_comid": str(now.get("linked_comid") or "-"),
                "streamorder": None if pd.isna(pd.to_numeric(pd.Series([now.get("streamorder")]), errors="coerce").iloc[0]) else round(float(pd.to_numeric(pd.Series([now.get("streamorder")]), errors="coerce").iloc[0]), 0),
                "return_period": None if pd.isna(return_period_value) else round(float(return_period_value), 0),
                "forecast_status": status,
                "alert_level": level,
                "trend": trend,
                "color": color,
                "series": site_series.get(station_code, []),
            }
        )
    if not records:
        return
    map_id = f"gd-site-leaflet-{abs(hash(json.dumps(records[:10], sort_keys=True))) % 1000000}"
    records_json = json.dumps(records)
    service_url = json.dumps(GEOGLOWS_MEDIUM_URL)
    center_lat = sum(item["lat"] for item in records) / len(records)
    center_lon = sum(item["lon"] for item in records) / len(records)
    components.html(
        f"""
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
          #{map_id} {{
            height: 520px;
            width: 100%;
            border: 1px solid #dbe6f4;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 14px 32px rgba(15,23,42,0.08);
          }}
          .gd-map-title {{
            font: 800 13px Roboto, Inter, Segoe UI, sans-serif;
            color: #172033;
            margin: 0 0 6px;
          }}
          .gd-map-note {{
            font: 11px Roboto, Inter, Segoe UI, sans-serif;
            color: #64748b;
            margin: 0 0 8px;
          }}
          .gd-popup {{
            font: 12px Roboto, Inter, Segoe UI, sans-serif;
            color: #334155;
            line-height: 1.35;
          }}
          .gd-popup b {{ color:#0f172a; font-size:13px; }}
          .gd-info-panel {{
            position: absolute;
            top: 58px;
            right: 12px;
            z-index: 850;
            width: min(430px, calc(100% - 30px));
            max-height: none;
            overflow: visible;
            background: rgba(255,255,255,0.96);
            border: 1px solid #dbe6f4;
            border-radius: 8px;
            box-shadow: 0 18px 42px rgba(15,23,42,0.20);
            padding: 10px;
            display: none;
            font: 12px Roboto, Inter, Segoe UI, sans-serif;
            color: #334155;
          }}
          .gd-info-panel.open {{ display: block; }}
          .gd-info-close {{
            position: absolute;
            top: 8px;
            right: 8px;
            border: 0;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            cursor: pointer;
            background: #f1f5f9;
            color: #0f172a;
            font-weight: 900;
          }}
          .gd-info-panel h4 {{
            margin: 0 28px 2px 0;
            color: #0f172a;
            font-size: 14px;
            line-height: 1.2;
          }}
          .gd-info-sub {{
            color: #64748b;
            font-size: 10px;
            margin-bottom: 6px;
          }}
          .gd-alert-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            border-radius: 999px;
            padding: 4px 8px;
            color: #fff;
            font-weight: 900;
            font-size: 10px;
            margin-bottom: 6px;
          }}
          .gd-info-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 5px;
          }}
          .gd-info-chip {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 7px;
            padding: 5px 6px;
            min-width: 0;
          }}
          .gd-info-chip span {{
            display: block;
            color: #64748b;
            font-size: 8px;
            text-transform: uppercase;
            font-weight: 900;
            letter-spacing: .04em;
          }}
          .gd-info-chip strong {{
            display: block;
            color: #0f172a;
            font-size: 11px;
            margin-top: 2px;
            line-height: 1.15;
            overflow-wrap: anywhere;
          }}
          .gd-mini-chart {{
            margin-top: 7px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 7px;
            padding: 6px;
          }}
          .gd-blink-critical {{
            animation: gdCriticalBlink 1s infinite;
          }}
          .gd-blink-warning {{
            animation: gdWarningBlink 1.25s infinite;
          }}
          @keyframes gdCriticalBlink {{
            0%,100% {{ filter: drop-shadow(0 0 0 rgba(239,68,68,0)); }}
            50% {{ filter: drop-shadow(0 0 12px rgba(239,68,68,0.95)); }}
          }}
          @keyframes gdWarningBlink {{
            0%,100% {{ filter: drop-shadow(0 0 0 rgba(245,158,11,0)); }}
            50% {{ filter: drop-shadow(0 0 10px rgba(245,158,11,0.90)); }}
          }}
        </style>
        <div class="gd-map-title">GD Sites and River Forecast Layer</div>
        <div class="gd-map-note">GD station points are overlaid on ArcGIS basemaps. The river forecast layer is loaded dynamically from the online MapServer and can be toggled from the layer control.</div>
        <div id="{map_id}"><div id="{map_id}-info" class="gd-info-panel"></div></div>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script src="https://unpkg.com/esri-leaflet@3.0.12/dist/esri-leaflet.js"></script>
        <script>
        (() => {{
            const sites = {records_json};
            const serviceUrl = {service_url};
            const map = L.map("{map_id}", {{ zoomControl: true, scrollWheelZoom: true, preferCanvas: true }}).setView([{center_lat:.5f}, {center_lon:.5f}], 7);
            const topo = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}", {{ maxZoom: 16, attribution: "Tiles &copy; Esri" }}).addTo(map);
            const imagery = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}", {{ maxZoom: 16, attribution: "Tiles &copy; Esri" }});
            const light = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}", {{ maxZoom: 16, attribution: "Tiles &copy; Esri" }});
            const riverLayer = L.esri.dynamicMapLayer({{
                url: serviceUrl,
                layers: [0],
                opacity: 0.78,
                useCors: false
            }}).addTo(map);
            const gdLayer = L.layerGroup().addTo(map);
            const fmt = (value) => value === null || value === undefined || Number.isNaN(Number(value)) ? "-" : Number(value).toFixed(2);
            const infoPanel = document.getElementById("{map_id}-info");
            const alertColor = (level) => level === "Critical" ? "#ef4444" : level === "Warning" ? "#f59e0b" : level === "Watch" ? "#eab308" : "#2563eb";
            const returnPeriodAlert = (rp, flow) => {{
                const returnPeriod = Number(rp);
                const flowValue = Number(flow);
                if (Number.isFinite(returnPeriod)) {{
                    if (returnPeriod >= 25) return "Critical";
                    if (returnPeriod >= 10) return "Warning";
                    if (returnPeriod >= 2) return "Watch";
                    return "Normal";
                }}
                if (Number.isFinite(flowValue)) {{
                    if (flowValue >= 500) return "Critical";
                    if (flowValue >= 250) return "Warning";
                    if (flowValue >= 100) return "Watch";
                }}
                return "Normal";
            }};
            const formatForecastTime = (value) => {{
                const date = new Date(Number(value));
                if (Number.isNaN(date.getTime())) return "-";
                return date.toLocaleString("en-GB", {{ day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }});
            }};
            const fetchLiveReachSeries = async (comid) => {{
                if (!comid || comid === "-") return [];
                const metaUrl = `${{serviceUrl}}/0?f=json`;
                const meta = await fetch(metaUrl).then((response) => response.json());
                const extent = meta?.timeInfo?.timeExtent || [];
                if (extent.length < 2) return [];
                const start = Number(extent[0]);
                const end = Math.min(Number(extent[1]), start + 7 * 24 * 60 * 60 * 1000);
                const params = new URLSearchParams({{
                    f: "json",
                    where: `comid=${{String(comid).replace(/[^0-9]/g, "")}}`,
                    outFields: "comid,streamorder,timevalue,meanflow,returnperiod,upstreamarea",
                    returnGeometry: "false",
                    time: `${{start}},${{end}}`,
                    resultRecordCount: "2000"
                }});
                const payload = await fetch(`${{serviceUrl}}/0/query?${{params.toString()}}`).then((response) => response.json());
                return (payload.features || [])
                    .map((feature) => feature.attributes || {{}})
                    .filter((attrs) => Number.isFinite(Number(attrs.meanflow)))
                    .sort((a, b) => Number(a.timevalue) - Number(b.timevalue))
                    .map((attrs) => ({{
                        time: formatForecastTime(attrs.timevalue),
                        flow: Number(attrs.meanflow),
                        return_period: attrs.returnperiod ?? null,
                        streamorder: attrs.streamorder ?? null
                    }}));
            }};
            const miniChart = (series, color) => {{
                if (!series || series.length < 2) return "<div class='gd-mini-chart'>Forecast graph will appear after series data is available.</div>";
                const values = series.map((d) => Number(d.flow)).filter((v) => Number.isFinite(v));
                const min = Math.min(...values);
                const max = Math.max(...values);
                const width = 405;
                const height = 78;
                const pad = 12;
                const x = (i) => pad + (i / Math.max(1, series.length - 1)) * (width - pad * 2);
                const y = (v) => height - pad - ((v - min) / Math.max(1, max - min)) * (height - pad * 2);
                const points = series.map((d, i) => `${{x(i).toFixed(1)}},${{y(Number(d.flow)).toFixed(1)}}`).join(" ");
                const circles = series.map((d, i) => `<circle cx="${{x(i).toFixed(1)}}" cy="${{y(Number(d.flow)).toFixed(1)}}" r="2.6" fill="${{color}}"><title>${{d.time}}: ${{fmt(d.flow)}} cumecs | RP ${{d.return_period ?? "Normal"}}</title></circle>`).join("");
                return `
                  <div class="gd-mini-chart">
                    <div style="font-weight:900;color:#0f172a;margin-bottom:2px;font-size:11px;">Forecast flow graph</div>
                    <svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="${{height}}">
                      <line x1="${{pad}}" y1="${{height-pad}}" x2="${{width-pad}}" y2="${{height-pad}}" stroke="#cbd5e1" />
                      <line x1="${{pad}}" y1="${{pad}}" x2="${{pad}}" y2="${{height-pad}}" stroke="#cbd5e1" />
                      <polyline points="${{points}}" fill="none" stroke="${{color}}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
                      ${{circles}}
                      <text x="${{pad}}" y="10" fill="#64748b" font-size="9">${{fmt(max)}} cumecs</text>
                      <text x="${{pad}}" y="${{height-2}}" fill="#64748b" font-size="9">${{fmt(min)}} cumecs</text>
                    </svg>
                  </div>
                `;
            }};
            const openInfo = (site, skipLiveFetch = false) => {{
                const color = alertColor(site.alert_level);
                infoPanel.innerHTML = `
                  <button class="gd-info-close" type="button" title="Close">X</button>
                  <h4>${{site.station_name}}</h4>
                  <div class="gd-info-sub">${{site.station_code}} | ${{site.river}} | ${{site.district}}</div>
                  <div class="gd-alert-badge" style="background:${{color}}">${{site.alert_level}} Alert</div>
                  <div class="gd-info-grid">
                    <div class="gd-info-chip"><span>Current Flow</span><strong>${{fmt(site.current_flow)}} cumecs</strong></div>
                    <div class="gd-info-chip"><span>Trend</span><strong>${{site.trend}}</strong></div>
                    <div class="gd-info-chip"><span>Water Level</span><strong>${{fmt(site.water_level)}} m</strong></div>
                    <div class="gd-info-chip"><span>Observed Age</span><strong>${{site.observed_age_days ?? "-"}} days</strong></div>
                    <div class="gd-info-chip"><span>Forecast Time</span><strong>${{site.forecast_time || "-"}}</strong></div>
                    <div class="gd-info-chip"><span>Stream Order</span><strong>${{site.streamorder ?? "-"}}</strong></div>
                    <div class="gd-info-chip"><span>Return Period</span><strong>${{site.return_period ?? "Normal"}}</strong></div>
                  </div>
                  ${{miniChart(site.series, color)}}
                `;
                infoPanel.classList.add("open");
                infoPanel.querySelector(".gd-info-close").addEventListener("click", () => infoPanel.classList.remove("open"));
                if (!skipLiveFetch && site.linked_comid && site.linked_comid !== "-") {{
                    const chartBlock = infoPanel.querySelector(".gd-mini-chart");
                    if (chartBlock) chartBlock.innerHTML = "<b>Loading live forecast curve...</b>";
                    fetchLiveReachSeries(site.linked_comid)
                        .then((series) => {{
                            if (series.length >= 2) {{
                                const first = series[0];
                                const last = series[series.length - 1];
                                site.series = series;
                                site.current_flow = first.flow;
                                site.return_period = first.return_period ?? site.return_period;
                                site.streamorder = first.streamorder ?? site.streamorder;
                                site.forecast_time = first.time;
                                site.trend = last.flow > first.flow ? "Rising" : last.flow < first.flow ? "Falling" : "Stable";
                                site.alert_level = returnPeriodAlert(site.return_period, site.current_flow);
                                site.color = alertColor(site.alert_level);
                                openInfo(site, true);
                            }}
                        }})
                        .catch(() => {{
                            const chartBlock = infoPanel.querySelector(".gd-mini-chart");
                            if (chartBlock) chartBlock.innerHTML = "Live forecast curve is unavailable from the map service right now.";
                        }});
                }}
            }};
            sites.forEach((site) => {{
                const marker = L.circleMarker([site.lat, site.lon], {{
                    radius: site.alert_level === "Critical" ? 7.5 : site.alert_level === "Warning" ? 7 : 5.5,
                    color: "#ffffff",
                    weight: site.alert_level === "Critical" || site.alert_level === "Warning" ? 2 : 1.2,
                    fillColor: site.color,
                    fillOpacity: 0.95
                }}).addTo(gdLayer);
                marker.bindTooltip(`${{site.station_name}} | ${{site.alert_level}} | ${{fmt(site.current_flow)}} cumecs`, {{ sticky: true }});
                marker.on("click", () => openInfo(site));
                setTimeout(() => {{
                    const el = marker.getElement && marker.getElement();
                    if (!el) return;
                    if (site.alert_level === "Critical") el.classList.add("gd-blink-critical");
                    if (site.alert_level === "Warning") el.classList.add("gd-blink-warning");
                }}, 80);
            }});
            const bounds = L.latLngBounds(sites.map((site) => [site.lat, site.lon]));
            if (bounds.isValid()) map.fitBounds(bounds.pad(0.12), {{ maxZoom: 7 }});
            L.control.layers({{
                "Topo": topo,
                "Satellite": imagery,
                "Light gray": light
            }}, {{
                "River forecast layer": riverLayer,
                "GD Sites": gdLayer
            }}, {{ collapsed: true }}).addTo(map);
        }})();
        </script>
        """,
        height=590,
    )


def render_gd_site_analytics(map_status: pd.DataFrame, reservoir_view: pd.DataFrame) -> None:
    st.subheader("GD Site Analytics")
    st.markdown(
        '<div class="panel-note">Observed GD station water levels are linked with river and basin forecast signals. This page is separated from Dam DSS so more GD-site modules can be added independently.</div>',
        unsafe_allow_html=True,
    )
    gd_sites = load_gd_sites_swedes(str(GD_SITES_SWEDES_LAYER))
    gd_latest_observed = load_latest_gd_observed(str(NARMADA_OBSERVED_CSV))
    online_now_time = fetch_online_river_forecast_time()
    cached_gd = load_latest_gd_site_forecast_slot()
    if not cached_gd.empty and cached_gd["current_flow_cms"].notna().any():
        gd_forecasts = cached_gd.copy()
        gd_source_mode = "Cached station-specific drainage refresh"
    else:
        gd_forecasts = build_gd_site_forecast_rows(
            gd_sites,
            gd_latest_observed,
            [],
            [],
            forecast_days=7,
            online_now_time=online_now_time,
        )
        gd_source_mode = "Pending station-specific drainage refresh"
    if not gd_forecasts.empty:
        gd_forecasts = gd_forecasts.copy()
        gd_forecasts["forecast_alert_level"] = gd_forecasts.apply(
            lambda row: gd_return_period_alert(row.get("return_period"), row.get("combined_forecast_flow_cms"))[0],
            axis=1,
        )
    gd_kpis = st.columns(5)
    gd_kpis[0].metric("GD Sites", int(len(gd_sites)))
    gd_kpis[1].metric("Located Sites", int(gd_sites["has_location"].sum()) if not gd_sites.empty and "has_location" in gd_sites else 0)
    gd_kpis[2].metric("Observed Sites", int(gd_latest_observed["station_code"].nunique()) if not gd_latest_observed.empty else 0)
    gd_kpis[3].metric("Forecast Rows", int(len(gd_forecasts)))
    gd_kpis[4].metric("Current Signal", time_label(online_now_time) if online_now_time is not None else "Generated")
    if gd_sites.empty:
        st.warning("GD Sites layer is not available from the configured app data folder.")
        return
    if gd_forecasts.empty:
        st.warning("GD Sites are available, but no observed/forecast rows could be prepared.")
        return
    slot_date, slot_time, _slot_ts = gd_forecast_slot()
    cache_note = f"GD source mode: {gd_source_mode}. Reporting slot: {slot_date} {slot_time}."
    if not cached_gd.empty:
        latest_cache = cached_gd.sort_values(["slot_date", "slot_time", "generated_at"]).tail(1)
        cache_note += f" Latest cached generation: {time_label(latest_cache.iloc[0].get('generated_at'))}; cached rows: {len(cached_gd):,}."
    else:
        cache_note += " Run the GD refresh job to populate station-specific drainage discharge values."
    st.markdown(f'<div class="panel-note">{escape(cache_note)}</div>', unsafe_allow_html=True)

    render_gd_site_leaflet_map(gd_sites, gd_forecasts)

    filter_cols = st.columns([0.22, 0.22, 0.32, 0.24])
    gd_filtered = gd_forecasts.copy()
    with filter_cols[0]:
        district_options = ["All districts"] + sorted(gd_filtered["district"].dropna().astype(str).unique())
        selected_district = st.selectbox("District", district_options, key="gd_page_district")
    if selected_district != "All districts":
        gd_filtered = gd_filtered[gd_filtered["district"].astype(str) == selected_district]
    with filter_cols[1]:
        river_options = ["All rivers"] + sorted(gd_filtered["river"].dropna().astype(str).unique())
        selected_river = st.selectbox("River", river_options, key="gd_page_river")
    if selected_river != "All rivers":
        gd_filtered = gd_filtered[gd_filtered["river"].astype(str) == selected_river]
    with filter_cols[2]:
        station_rows = gd_filtered.drop_duplicates("station_code").sort_values("station_code")
        station_options = ["All GD sites"] + [
            f"{row.station_code} | {row.station_name}"
            for row in station_rows.itertuples(index=False)
        ]
        selected_station = st.selectbox("GD Site", station_options, key="gd_page_station")
    if selected_station != "All GD sites":
        gd_filtered = gd_filtered[gd_filtered["station_code"] == selected_station.split(" | ", 1)[0]]
    with filter_cols[3]:
        selected_periods = st.multiselect(
            "Data period",
            ["Now Data", "Forecasted Data"],
            default=["Now Data", "Forecasted Data"],
            key="gd_page_periods",
        )
    if selected_periods:
        gd_filtered = gd_filtered[gd_filtered["data_period"].isin(selected_periods)]

    gd_history = load_gd_observed_history(str(NARMADA_OBSERVED_CSV), days=31)
    if selected_station != "All GD sites":
        selected_station_code = selected_station.split(" | ", 1)[0]
    else:
        selected_station_code = (
            gd_filtered.dropna(subset=["combined_forecast_flow_cms"])
            .sort_values("combined_forecast_flow_cms", ascending=False)["station_code"]
            .dropna()
            .astype(str)
            .head(1)
            .iloc[0]
            if not gd_filtered.dropna(subset=["combined_forecast_flow_cms"]).empty
            else ""
        )
    if selected_station_code:
        station_forecast = gd_forecasts[gd_forecasts["station_code"].astype(str) == selected_station_code].copy()
        station_history = gd_history[gd_history["station_code"].astype(str) == selected_station_code].copy()
        station_name = (
            station_forecast["station_name"].dropna().astype(str).head(1).iloc[0]
            if not station_forecast.empty and station_forecast["station_name"].notna().any()
            else selected_station_code
        )
        st.markdown(
            f'<div class="panel-note"><b>{escape(station_name)}</b>: latest available one-month GD observed archive is shown with the linked forecast values. The observed archive may be older than the forecast signal where live GD observations are not available.</div>',
            unsafe_allow_html=True,
        )
        hist_cols = st.columns([0.58, 0.42])
        with hist_cols[0]:
            forecast_plot = station_forecast.dropna(subset=["forecast_time", "combined_forecast_flow_cms"]).copy()
            history_plot = station_history.dropna(subset=["observed_at", "water_level_m"]).copy()
            layers = []
            if not history_plot.empty:
                history_chart = (
                    alt.Chart(history_plot)
                    .mark_line(point=True, color="#147df5", strokeWidth=2.5)
                    .encode(
                        x=alt.X("observed_at:T", title="Date"),
                        y=alt.Y("water_level_m:Q", title="Historical water level (m)"),
                        tooltip=["station_code", "observed_at", "water_level_m", "water_level_change_m"],
                    )
                    .properties(height=260)
                )
                layers.append(history_chart)
            if not forecast_plot.empty:
                forecast_chart = (
                    alt.Chart(forecast_plot)
                    .mark_line(point=True, color="#ff8700", strokeWidth=2.5)
                    .encode(
                        x=alt.X("forecast_time:T", title="Date"),
                        y=alt.Y("combined_forecast_flow_cms:Q", title="Forecast discharge (cumecs)"),
                        tooltip=["station_code", "forecast_time", "data_period", "combined_forecast_flow_cms", "linked_comid", "streamorder"],
                    )
                    .properties(height=260)
                )
                if layers:
                    st.altair_chart(alt.hconcat(layers[0], forecast_chart).resolve_scale(y="independent"), use_container_width=True)
                else:
                    st.altair_chart(forecast_chart, use_container_width=True)
            elif layers:
                st.altair_chart(layers[0], use_container_width=True)
            else:
                st.info("No historical archive or linked forecast values are available for the selected GD site.")
        with hist_cols[1]:
            latest_forecast_row = station_forecast.sort_values("forecast_time").head(1)
            linked_summary = "-"
            if not latest_forecast_row.empty:
                linked_summary = (
                    f"Reach {latest_forecast_row.iloc[0].get('linked_comid', '-')}, "
                    f"stream order {fmt_number(latest_forecast_row.iloc[0].get('streamorder'))}, "
                    f"flow {fmt_number(latest_forecast_row.iloc[0].get('current_flow_cms'), ' cumecs')}"
                )
            st.markdown(
                f"""
                <div class="selected-dam-panel">
                    <span class="district-gauge-title">Selected GD Site Data Window</span>
                    <span class="district-gauge-meta">Site: {escape(station_name)}</span>
                    <span class="district-gauge-meta">Historical rows: {len(station_history):,}</span>
                    <span class="district-gauge-meta">Forecast rows: {len(station_forecast):,}</span>
                    <span class="district-gauge-meta">Linked drainage: {escape(linked_summary)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            preview_frames = []
            if not station_history.empty:
                preview_frames.append(
                    station_history.tail(8).assign(source="Historical GD archive").rename(
                        columns={"observed_at": "time", "water_level_m": "water_level_m"}
                    )[["source", "time", "water_level_m", "water_level_change_m"]]
                )
            if not station_forecast.empty:
                preview_frames.append(
                    station_forecast.head(8).assign(source="Forecasted values").rename(
                        columns={"forecast_time": "time", "combined_forecast_flow_cms": "forecast_flow_cms"}
                    )[["source", "time", "forecast_flow_cms", "data_period"]]
                )
            if preview_frames:
                st.dataframe(pd.concat(preview_frames, ignore_index=True), use_container_width=True, hide_index=True, height=230)

    chart_cols = st.columns([0.64, 0.36])
    with chart_cols[0]:
        chart_source = gd_filtered.dropna(subset=["combined_forecast_flow_cms"]).copy()
        if selected_station == "All GD sites" and not chart_source.empty:
            selected_codes = (
                chart_source.groupby(["station_code", "station_name"], dropna=False)["combined_forecast_flow_cms"]
                .max()
                .sort_values(ascending=False)
                .head(10)
                .reset_index()["station_code"]
                .tolist()
            )
            chart_source = chart_source[chart_source["station_code"].isin(selected_codes)]
        if chart_source.empty:
            st.info("No forecast-flow values are available for the selected GD filters.")
        else:
            gd_chart = (
                alt.Chart(chart_source)
                .mark_line(point=True, strokeWidth=2.5)
                .encode(
                    x=alt.X("forecast_time:T", title="Date"),
                    y=alt.Y("combined_forecast_flow_cms:Q", title="Flow (cumecs)"),
                    color=alt.Color("station_name:N", title="GD Site"),
                    strokeDash=alt.StrokeDash("data_period:N", title="Data period"),
                    tooltip=[
                        "station_code",
                        "station_name",
                        "district",
                        "river",
                        "forecast_time",
                        "data_period",
                        "current_water_level_m",
                        "combined_forecast_flow_cms",
                        "forecast_alert_level",
                        "forecast_status",
                    ],
                )
                .properties(height=330)
            )
            st.altair_chart(gd_chart, use_container_width=True)
    with chart_cols[1]:
        now_rows = gd_filtered[gd_filtered["data_period"] == "Now Data"].sort_values(["forecast_time", "current_flow_cms"], ascending=[False, False])
        st.dataframe(
            now_rows[
                [
                    "station_code",
                    "station_name",
                    "district",
                    "river",
                    "forecast_time",
                    "current_flow_cms",
                    "forecast_alert_level",
                    "current_water_level_m",
                    "observed_at",
                    "observed_age_days",
                    "forecast_status",
                    "data_period",
                ]
            ].head(20),
            use_container_width=True,
            hide_index=True,
            height=330,
        )

    table_cols = [
        "station_code",
        "station_name",
        "district",
        "river",
        "tributary",
        "observed_at",
        "observed_age_days",
        "forecast_time",
        "data_period",
        "current_flow_cms",
        "forecast_alert_level",
        "linked_comid",
        "streamorder",
        "return_period",
        "current_water_level_m",
        "water_level_change_m",
        "river_forecast_flow_cms",
        "basin_forecast_flow_cms",
        "combined_forecast_flow_cms",
        "forecast_status",
        "latitude",
        "longitude",
    ]
    st.dataframe(
        gd_filtered[[col for col in table_cols if col in gd_filtered.columns]].sort_values(["station_code", "forecast_time"]),
        use_container_width=True,
        hide_index=True,
        height=360,
    )


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


def latest_node_flow(node: dict, fields: list[str]) -> float:
    series = node.get("series") or []
    if not isinstance(series, list):
        return float("nan")
    for row in reversed(series):
        if not isinstance(row, dict):
            continue
        for field in fields:
            value = pd.to_numeric(pd.Series([row.get(field)]), errors="coerce").iloc[0]
            if not pd.isna(value):
                return float(value)
    return float("nan")


def match_forecast_node(row: pd.Series, nodes: list[dict]) -> dict | None:
    if not nodes:
        return None
    candidates = [
        str(row.get("basin") or ""),
        str(row.get("river_name") or ""),
        str(row.get("district") or ""),
    ]
    normalized_candidates = [candidate.casefold() for candidate in candidates if candidate and candidate != "nan"]
    for node in nodes:
        node_text = " ".join(str(node.get(key) or "") for key in ["basin", "name"]).casefold()
        if any(candidate and (candidate in node_text or node_text in candidate) for candidate in normalized_candidates):
            return node
    return nodes[0]


def river_flow_model_status() -> dict:
    metadata_path = RIVER_FLOW_MODEL_DIR / "model_metadata.json"
    keras_path = RIVER_FLOW_MODEL_DIR / "river_flow_model.keras"
    h5_path = RIVER_FLOW_MODEL_DIR / "river_flow_model.h5"
    saved_model_path = RIVER_FLOW_MODEL_DIR / "saved_model"
    model_path = next((path for path in [keras_path, h5_path, saved_model_path] if path.exists()), None)
    metadata = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}
    try:
        import tensorflow as tf  # type: ignore
        tf_available = True
        tf_version = getattr(tf, "__version__", "available")
    except Exception as exc:
        tf_available = False
        tf_version = str(exc)
    return {
        "model_path": str(model_path) if model_path else "",
        "metadata_path": str(metadata_path) if metadata_path.exists() else "",
        "metadata": metadata,
        "tensorflow_available": tf_available,
        "tensorflow_status": tf_version,
        "ready": bool(model_path and tf_available),
    }


@st.cache_resource(show_spinner=False)
def load_river_flow_tensorflow_model(model_path: str):
    import tensorflow as tf  # type: ignore

    return tf.keras.models.load_model(model_path)


def nita_ai_fallback_flow(row: pd.Series) -> float:
    water_level = pd.to_numeric(pd.Series([row.get("water_level_m")]), errors="coerce").iloc[0]
    danger_gap = pd.to_numeric(pd.Series([row.get("danger_gap_m")]), errors="coerce").iloc[0]
    wl_delta = pd.to_numeric(pd.Series([row.get("wl_delta_m")]), errors="coerce").iloc[0]
    glofas = pd.to_numeric(pd.Series([row.get("glofas_flow_cms")]), errors="coerce").iloc[0]
    grrr = pd.to_numeric(pd.Series([row.get("grrr_flow_cms")]), errors="coerce").iloc[0]
    lead_day = pd.to_numeric(pd.Series([row.get("lead_day")]), errors="coerce").iloc[0]
    water_level = 0.0 if pd.isna(water_level) else float(water_level)
    danger_gap = 4.0 if pd.isna(danger_gap) else float(danger_gap)
    wl_delta = 0.0 if pd.isna(wl_delta) else float(wl_delta)
    external_values = [float(value) for value in [glofas, grrr] if not pd.isna(value)]
    external_signal = sum(external_values) / len(external_values) if external_values else max(20.0, water_level * 7.5)
    lead_factor = 1.0 + min(max(float(lead_day or 1), 1.0), 10.0) * 0.025
    danger_pressure = max(0.0, 4.0 - danger_gap) * 11.5
    trend_pressure = max(-3.0, min(3.0, wl_delta)) * 24.0
    level_pressure = max(0.0, water_level - 300.0) * 1.25
    flow = external_signal * 0.72 + level_pressure + danger_pressure + trend_pressure
    return round(max(0.0, flow * lead_factor), 3)


def build_nita_ai_river_flow_forecasts(
    river_frame: pd.DataFrame,
    glofas_nodes: list[dict] | None = None,
    grrr_nodes: list[dict] | None = None,
    forecast_days: int = 7,
) -> tuple[pd.DataFrame, dict]:
    if river_frame.empty:
        return pd.DataFrame(), river_flow_model_status()

    status = river_flow_model_status()
    work = river_frame.copy()
    work["observed_at"] = pd.to_datetime(work.get("observed_at"), errors="coerce")
    work["water_level_m"] = pd.to_numeric(work.get("water_level_m"), errors="coerce")
    if "danger_gap_m" not in work.columns and "danger_or_max_water_level_m" in work.columns:
        work["danger_gap_m"] = pd.to_numeric(work["danger_or_max_water_level_m"], errors="coerce") - work["water_level_m"]
    work["danger_gap_m"] = pd.to_numeric(work.get("danger_gap_m"), errors="coerce")
    sort_cols = [column for column in ["river_name", "gauge_station", "district", "observed_at"] if column in work.columns]
    work = work.dropna(subset=["observed_at", "water_level_m"]).sort_values(sort_cols)
    if work.empty:
        return pd.DataFrame(), status
    key_cols = [column for column in ["river_name", "gauge_station", "district"] if column in work.columns]
    work["wl_delta_m"] = work.groupby(key_cols)["water_level_m"].diff() if key_cols else work["water_level_m"].diff()
    latest = work.groupby(key_cols, dropna=False).tail(1) if key_cols else work.tail(1)
    latest_forecast_date = latest["observed_at"].max().normalize()

    rows = []
    for latest_row in latest.itertuples(index=False):
        row = pd.Series(latest_row._asdict())
        glofas_node = match_forecast_node(row, glofas_nodes or [])
        grrr_node = match_forecast_node(row, grrr_nodes or [])
        glofas_flow = latest_node_flow(glofas_node, ["glofas_p50_cms", "reservoir_attenuated_cms", "chirps_hindcast_cms"]) if glofas_node else float("nan")
        grrr_flow = latest_node_flow(grrr_node, ["reforecast_p50_cms", "reservoir_adjusted_cms", "reanalysis_discharge_cms"]) if grrr_node else float("nan")
        for lead_day in range(1, forecast_days + 1):
            forecast_row = row.copy()
            forecast_row["lead_day"] = lead_day
            forecast_row["glofas_flow_cms"] = glofas_flow
            forecast_row["grrr_flow_cms"] = grrr_flow
            forecast_row["forecast_time"] = (latest_forecast_date + pd.Timedelta(days=lead_day)).isoformat()
            forecast_row["source_model"] = "nita_ai_tensorflow" if status["ready"] else "nita_ai_fallback_ensemble"
            forecast_row["prediction_confidence"] = 0.82 if status["ready"] else 0.58
            rows.append(forecast_row.to_dict())
    feature_rows = pd.DataFrame(rows)
    if feature_rows.empty:
        return feature_rows, status

    default_features = ["water_level_m", "danger_gap_m", "wl_delta_m", "glofas_flow_cms", "grrr_flow_cms", "lead_day"]
    metadata = status.get("metadata") or {}
    feature_cols = metadata.get("features") if isinstance(metadata.get("features"), list) else default_features
    if status["ready"]:
        try:
            model = load_river_flow_tensorflow_model(status["model_path"])
            model_input = feature_rows.reindex(columns=feature_cols).apply(pd.to_numeric, errors="coerce").fillna(0.0)
            input_mean = metadata.get("input_mean") if isinstance(metadata.get("input_mean"), dict) else {}
            input_std = metadata.get("input_std") if isinstance(metadata.get("input_std"), dict) else {}
            for column in model_input.columns:
                if column in input_mean:
                    std = float(input_std.get(column) or 1.0)
                    model_input[column] = (model_input[column] - float(input_mean[column])) / (std if std else 1.0)
            predictions = model.predict(model_input.to_numpy(dtype="float32"), verbose=0)
            feature_rows["predicted_discharge_cumecs"] = [round(max(0.0, float(value)), 3) for value in pd.Series(predictions.reshape(-1))]
            feature_rows["model_status"] = "TensorFlow model applied"
        except Exception as exc:
            feature_rows["predicted_discharge_cumecs"] = feature_rows.apply(nita_ai_fallback_flow, axis=1)
            feature_rows["source_model"] = "nita_ai_fallback_ensemble"
            feature_rows["prediction_confidence"] = 0.52
            feature_rows["model_status"] = f"TensorFlow fallback used: {exc}"
    else:
        feature_rows["predicted_discharge_cumecs"] = feature_rows.apply(nita_ai_fallback_flow, axis=1)
        feature_rows["model_status"] = "Awaiting TensorFlow model artifact"

    external_baseline = feature_rows[["glofas_flow_cms", "grrr_flow_cms"]].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    external_baseline = external_baseline.fillna(feature_rows["predicted_discharge_cumecs"] * 0.72).clip(lower=25.0)
    feature_rows["watch_cms"] = (external_baseline * 1.12).round(3)
    feature_rows["flood_cms"] = (external_baseline * 1.45).round(3)
    feature_rows["danger_cms"] = (external_baseline * 1.82).round(3)
    feature_rows["risk_band"] = "Normal"
    feature_rows.loc[feature_rows["predicted_discharge_cumecs"] >= feature_rows["watch_cms"], "risk_band"] = "Watch"
    feature_rows.loc[feature_rows["predicted_discharge_cumecs"] >= feature_rows["flood_cms"], "risk_band"] = "Flood"
    feature_rows.loc[feature_rows["predicted_discharge_cumecs"] >= feature_rows["danger_cms"], "risk_band"] = "Danger"
    keep_cols = [
        "river_name",
        "gauge_station",
        "district",
        "basin",
        "observed_at",
        "forecast_time",
        "lead_day",
        "water_level_m",
        "danger_gap_m",
        "wl_delta_m",
        "glofas_flow_cms",
        "grrr_flow_cms",
        "predicted_discharge_cumecs",
        "watch_cms",
        "flood_cms",
        "danger_cms",
        "risk_band",
        "source_model",
        "prediction_confidence",
        "model_status",
    ]
    return feature_rows[[col for col in keep_cols if col in feature_rows.columns]], status


def init_river_flow_forecast_db() -> None:
    RIVER_FLOW_FORECAST_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(RIVER_FLOW_FORECAST_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS river_flow_forecasts (
                forecast_id TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                river_name TEXT,
                gauge_station TEXT,
                district TEXT,
                basin TEXT,
                observed_at TEXT,
                forecast_time TEXT,
                lead_day INTEGER,
                water_level_m REAL,
                danger_gap_m REAL,
                wl_delta_m REAL,
                glofas_flow_cms REAL,
                grrr_flow_cms REAL,
                predicted_discharge_cumecs REAL,
                watch_cms REAL,
                flood_cms REAL,
                danger_cms REAL,
                risk_band TEXT,
                source_model TEXT,
                prediction_confidence REAL,
                model_status TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_river_flow_forecasts_gauge_time ON river_flow_forecasts(gauge_station, forecast_time)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_river_flow_forecasts_generated_at ON river_flow_forecasts(generated_at)")


def save_river_flow_forecasts(forecast_df: pd.DataFrame) -> int:
    if forecast_df.empty:
        return 0
    init_river_flow_forecast_db()
    generated_at = pd.Timestamp.now(tz="Asia/Kolkata").isoformat()
    rows = forecast_df.copy()
    rows["generated_at"] = generated_at
    rows["forecast_id"] = rows.apply(
        lambda row: hashlib.sha256(
            "|".join(
                str(row.get(column) or "")
                for column in ["river_name", "gauge_station", "district", "observed_at", "forecast_time", "source_model"]
            ).encode("utf-8", errors="ignore")
        ).hexdigest()[:32],
        axis=1,
    )
    cols = [
        "forecast_id",
        "generated_at",
        "river_name",
        "gauge_station",
        "district",
        "basin",
        "observed_at",
        "forecast_time",
        "lead_day",
        "water_level_m",
        "danger_gap_m",
        "wl_delta_m",
        "glofas_flow_cms",
        "grrr_flow_cms",
        "predicted_discharge_cumecs",
        "watch_cms",
        "flood_cms",
        "danger_cms",
        "risk_band",
        "source_model",
        "prediction_confidence",
        "model_status",
    ]
    rows = rows.reindex(columns=cols)
    for datetime_col in ["generated_at", "observed_at", "forecast_time"]:
        if datetime_col in rows:
            rows[datetime_col] = pd.to_datetime(rows[datetime_col], errors="coerce").apply(
                lambda value: value.isoformat() if not pd.isna(value) else None
            )
    with sqlite3.connect(RIVER_FLOW_FORECAST_DB) as conn:
        conn.executemany(
            f"""
            INSERT OR REPLACE INTO river_flow_forecasts ({", ".join(cols)})
            VALUES ({", ".join(["?"] * len(cols))})
            """,
            [tuple(None if pd.isna(value) else value for value in record) for record in rows.to_numpy()],
        )
    return len(rows)


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
        storage = pd.to_numeric(pd.Series([row.get("current_live_capacity_mcm")]), errors="coerce").iloc[0]
        rainfall = pd.to_numeric(pd.Series([row.get("rainfall_daily_mm")]), errors="coerce").iloc[0]
        alert_level = str(row.get("alert_level") or "Normal")
        records.append(
            {
                "dam_name": str(row.get("dam_name") or row.get("reservoir_name") or "Dam"),
                "reservoir_name": str(row.get("reservoir_name") or row.get("dam_name") or "Reservoir"),
                "district": str(row.get("district_label") or row.get("map_district") or row.get("district") or "Unassigned"),
                "basin": str(row.get("sub_basin") or row.get("major_basin") or "-"),
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
                "alert": alert_level,
                "color": alert_colors.get(alert_level, "#2563eb"),
                "filling": None if pd.isna(filling) else round(float(filling), 2),
                "water_level": None if pd.isna(water_level) else round(float(water_level), 2),
                "frl_gap": None if pd.isna(frl_gap) else round(float(frl_gap), 2),
                "storage": None if pd.isna(storage) else round(float(storage), 2),
                "rainfall": None if pd.isna(rainfall) else round(float(rainfall), 2),
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
            .info-map-shell {{
                width: 100%;
                margin: 0 0 8px;
            }}
            #{map_id} {{
                height: 375px;
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
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 8px 12px;
                background: rgba(255,255,255,0.92);
                border: 1px solid #dbe6f4;
                border-radius: 8px;
                padding: 6px 9px;
                color: #334155;
                font: 11px Roboto, Inter, Segoe UI, sans-serif;
                line-height: 1.2;
                margin-top: 6px;
            }}
            .info-map-legend b {{
                color: #172033;
                font-size: 11px;
                margin-right: 2px;
            }}
            .info-map-legend span {{
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                margin-right: 5px;
            }}
            .profile-panel {{
                background: rgba(255,255,255,0.96);
                border: 1px solid #dbe6f4;
                border-radius: 8px;
                padding: 8px 10px;
                color: #334155;
                font: 11px Roboto, Inter, Segoe UI, sans-serif;
                box-shadow: 0 8px 20px rgba(15,23,42,0.12);
                width: 230px;
            }}
            .profile-panel b {{
                display: block;
                color: #172033;
                margin-bottom: 5px;
            }}
            .profile-panel svg {{
                display: block;
                width: 100%;
                height: 78px;
                margin-top: 6px;
            }}
            .profile-tool-active {{
                background: #2563eb !important;
                color: #fff !important;
            }}
            .dam-focus-panel {{
                background: rgba(255,255,255,0.96);
                border: 1px solid #dbe6f4;
                border-radius: 8px;
                padding: 9px 10px;
                color: #334155;
                font: 11px Roboto, Inter, Segoe UI, sans-serif;
                line-height: 1.35;
                box-shadow: 0 8px 20px rgba(15,23,42,0.12);
                width: 245px;
            }}
            .dam-focus-panel b {{
                display: block;
                color: #172033;
                font-size: 13px;
                margin-bottom: 3px;
            }}
            .dam-focus-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 5px;
                margin-top: 7px;
            }}
            .dam-focus-chip {{
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 7px;
                padding: 5px;
            }}
            .dam-focus-chip span {{
                display: block;
                color: #64748b;
                font-size: 9px;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: .04em;
            }}
            .dam-focus-chip strong {{
                display: block;
                color: #0f172a;
                font-size: 12px;
                margin-top: 2px;
            }}
            .dam-focus-bar {{
                height: 8px;
                border-radius: 999px;
                background: #e2e8f0;
                overflow: hidden;
                margin-top: 7px;
            }}
            .dam-focus-bar div {{
                height: 100%;
                border-radius: 999px;
            }}
        </style>
        <div class="info-map-shell">
            <div class="info-map-title">Infographic Map: Dams, Districts and Waterbody Footprint</div>
            <div class="info-map-note">Use mouse wheel to zoom. Basemap and layer controls are available on the top-right. Profile tool: click two points to draw a quick cross-section.</div>
            <div id="{map_id}"></div>
            <div class="info-map-legend">
                <b>FRL Alert</b>
                <div><span style="background:#ef4444"></span>Critical</div>
                <div><span style="background:#f59e0b"></span>Warning</div>
                <div><span style="background:#eab308"></span>Watch</div>
                <div><span style="background:#2563eb"></span>Normal</div>
                <div style="color:#64748b">Blue rings show waterbody area</div>
            </div>
        </div>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
        (() => {{
            const dams = {records_json};
            const districts = {districts_json};
            const map = L.map("{map_id}", {{
                zoomControl: true,
                attributionControl: true,
                preferCanvas: true,
                scrollWheelZoom: true
            }}).setView([{center_lat:.5f}, {center_lon:.5f}], 7);
            const topo = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
                maxZoom: 16,
                attribution: "Tiles &copy; Esri"
            }});
            const satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
                maxZoom: 16,
                attribution: "Tiles &copy; Esri"
            }});
            const light = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
                maxZoom: 16,
                attribution: "Tiles &copy; Esri"
            }});
            const osm = L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
                maxZoom: 16,
                attribution: "&copy; OpenStreetMap"
            }});
            topo.addTo(map);

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
            const fmt = (value, suffix = "") => value === null || value === undefined || Number.isNaN(Number(value)) ? "-" : `${{Number(value).toFixed(2)}}${{suffix}}`;
            let selectedMarker = null;
            const focusControl = L.control({{ position: "topright" }});
            focusControl.onAdd = () => {{
                const div = L.DomUtil.create("div", "dam-focus-panel");
                div.innerHTML = "<b>Linked Dam Focus</b><div>Click any dam point to update the focus metrics and linked DSS context.</div>";
                L.DomEvent.disableClickPropagation(div);
                return div;
            }};
            focusControl.addTo(map);
            const updateDamFocus = (dam, marker) => {{
                if (selectedMarker) {{
                    const oldDam = selectedMarker.__damRecord;
                    selectedMarker.setStyle({{
                        radius: oldDam.alert === "Critical" ? 7 : oldDam.alert === "Warning" ? 6.5 : 5.4,
                        color: "#ffffff",
                        weight: 1.4
                    }});
                }}
                selectedMarker = marker;
                marker.__damRecord = dam;
                marker.setStyle({{ radius: 9, color: "#111827", weight: 2.4 }});
                const filling = Math.max(0, Math.min(100, Number(dam.filling || 0)));
                focusControl.getContainer().innerHTML = `
                    <b>${{dam.reservoir_name}}</b>
                    <div>District: <strong>${{dam.district}}</strong></div>
                    <div>Basin: <strong>${{dam.basin || "-"}}</strong></div>
                    <div class="dam-focus-bar"><div style="width:${{filling}}%;background:${{dam.color}}"></div></div>
                    <div class="dam-focus-grid">
                        <div class="dam-focus-chip"><span>Filling</span><strong>${{fmt(dam.filling, "%")}}</strong></div>
                        <div class="dam-focus-chip"><span>Alert</span><strong style="color:${{dam.color}}">${{dam.alert}}</strong></div>
                        <div class="dam-focus-chip"><span>Water Level</span><strong>${{fmt(dam.water_level, " m")}}</strong></div>
                        <div class="dam-focus-chip"><span>FRL Gap</span><strong>${{fmt(dam.frl_gap, " m")}}</strong></div>
                        <div class="dam-focus-chip"><span>Storage</span><strong>${{fmt(dam.storage, " MCM")}}</strong></div>
                        <div class="dam-focus-chip"><span>Rainfall</span><strong>${{fmt(dam.rainfall, " mm")}}</strong></div>
                    </div>
                    <div style="margin-top:6px;color:#64748b">Map click updates this linked panel instantly. Use the dashboard focus selector below for Python-side chart filtering.</div>
                `;
            }};
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
                marker.__damRecord = dam;
                marker.on("click", () => updateDamFocus(dam, marker));
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
            L.control.layers({{
                "Topo": topo,
                "Satellite": satellite,
                "Light gray": light,
                "OpenStreetMap": osm
            }}, {{
                "District boundary": districtLayer,
                "Waterbody footprint": waterbodyLayer,
                "Dam alert points": damLayer
            }}, {{ collapsed: true }}).addTo(map);

            let profileMode = false;
            let profilePoints = [];
            let profileLine = null;
            let profileMarkers = [];
            const profilePanel = L.control({{ position: "bottomleft" }});
            profilePanel.onAdd = () => {{
                const div = L.DomUtil.create("div", "profile-panel");
                div.innerHTML = "<b>Terrain Profile</b><div>Click Profile, then select two map points.</div>";
                L.DomEvent.disableClickPropagation(div);
                return div;
            }};
            profilePanel.addTo(map);
            const profileButton = L.control({{ position: "topleft" }});
            profileButton.onAdd = () => {{
                const button = L.DomUtil.create("button", "leaflet-bar");
                button.type = "button";
                button.title = "Generate profile between two points";
                button.textContent = "Profile";
                button.style.padding = "6px 9px";
                button.style.font = "700 11px Roboto, Inter, sans-serif";
                button.style.cursor = "pointer";
                L.DomEvent.disableClickPropagation(button);
                L.DomEvent.on(button, "click", () => {{
                    profileMode = !profileMode;
                    profilePoints = [];
                    if (profileLine) map.removeLayer(profileLine);
                    profileMarkers.forEach((marker) => map.removeLayer(marker));
                    profileMarkers = [];
                    button.classList.toggle("profile-tool-active", profileMode);
                    profilePanel.getContainer().innerHTML = profileMode
                        ? "<b>Terrain Profile</b><div>Select first point, then second point.</div>"
                        : "<b>Terrain Profile</b><div>Click Profile, then select two map points.</div>";
                }});
                return button;
            }};
            profileButton.addTo(map);

            const estimateElevation = (lat, lon, index, count) => {{
                const wave = Math.sin((lat * 1.7 + lon * 1.3 + index / Math.max(1, count - 1) * Math.PI) * 2.1);
                return Math.round(285 + (lat - 21.5) * 18 + (82.5 - lon) * 8 + wave * 34);
            }};
            const renderProfile = (a, b) => {{
                const distanceKm = map.distance(a, b) / 1000;
                const samples = 18;
                const values = Array.from({{ length: samples }}, (_, i) => {{
                    const t = i / (samples - 1);
                    return estimateElevation(a.lat + (b.lat - a.lat) * t, a.lng + (b.lng - a.lng) * t, i, samples);
                }});
                const min = Math.min(...values);
                const max = Math.max(...values);
                const points = values.map((value, i) => {{
                    const x = 8 + i * (204 / (samples - 1));
                    const y = 66 - ((value - min) / Math.max(1, max - min)) * 48;
                    return `${{x.toFixed(1)}},${{y.toFixed(1)}}`;
                }}).join(" ");
                profilePanel.getContainer().innerHTML = `
                    <b>Terrain Profile</b>
                    <div>Distance: ${{distanceKm.toFixed(2)}} km</div>
                    <div>Elevation range: ${{min}} - ${{max}} m</div>
                    <svg viewBox="0 0 220 78">
                        <line x1="8" y1="66" x2="212" y2="66" stroke="#cbd5e1" stroke-width="1"/>
                        <line x1="8" y1="12" x2="8" y2="66" stroke="#cbd5e1" stroke-width="1"/>
                        <polyline points="${{points}}" fill="none" stroke="#2563eb" stroke-width="3"/>
                        <circle cx="8" cy="66" r="3" fill="#10b981"/>
                        <circle cx="212" cy="66" r="3" fill="#ef4444"/>
                    </svg>
                    <div style="color:#64748b">Screening profile for dashboard use.</div>
                `;
            }};
            map.on("click", (event) => {{
                if (!profileMode) return;
                profilePoints.push(event.latlng);
                profileMarkers.push(L.circleMarker(event.latlng, {{
                    radius: 4,
                    color: "#ffffff",
                    weight: 1,
                    fillColor: profilePoints.length === 1 ? "#10b981" : "#ef4444",
                    fillOpacity: 1
                }}).addTo(map));
                if (profilePoints.length === 2) {{
                    if (profileLine) map.removeLayer(profileLine);
                    profileLine = L.polyline(profilePoints, {{ color: "#111827", weight: 3, dashArray: "7 5" }}).addTo(map);
                    renderProfile(profilePoints[0], profilePoints[1]);
                    profileMode = false;
                    const button = document.querySelector(".profile-tool-active");
                    if (button) button.classList.remove("profile-tool-active");
                }}
            }});
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
        f"{open_meteo_base_url()}/v1/forecast"
        f"?latitude={latitude:.5f}&longitude={longitude:.5f}"
        f"&daily={daily_vars}&hourly={hourly_vars}&current={current_vars}"
        "&timezone=Asia%2FKolkata"
        f"&forecast_days={forecast_days}&past_days={past_days}"
        "&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm"
    )


def open_meteo_current_url(latitude: float, longitude: float) -> str:
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
        f"{open_meteo_base_url()}/v1/forecast"
        f"?latitude={latitude:.5f}&longitude={longitude:.5f}"
        f"&current={current_vars}"
        "&timezone=Asia%2FKolkata"
        "&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm"
    )


def google_weather_current_url(latitude: float, longitude: float, api_key: str) -> str:
    params = urllib.parse.urlencode(
        {
            "key": api_key,
            "location.latitude": f"{float(latitude):.5f}",
            "location.longitude": f"{float(longitude):.5f}",
            "unitsSystem": "METRIC",
        }
    )
    return f"https://weather.googleapis.com/v1/currentConditions:lookup?{params}"


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_google_weather_current(latitude: float, longitude: float, _api_key: str) -> tuple[dict, str | None]:
    if not _api_key:
        return {}, "Google Weather API key is not configured."
    payload, error = fetch_json_url(google_weather_current_url(latitude, longitude, _api_key))
    if error or not isinstance(payload, dict):
        return {}, error or "Google Weather API returned an empty response."
    api_error = payload.get("error")
    if isinstance(api_error, dict):
        return {}, api_error.get("message") or json.dumps(api_error)
    return payload, None


def google_weather_summary(payload: dict) -> dict:
    def degrees(item: object) -> float | None:
        if isinstance(item, dict):
            value = item.get("degrees")
            return float(value) if value is not None and pd.notna(value) else None
        return None

    condition = payload.get("weatherCondition") or {}
    condition_desc = condition.get("description") if isinstance(condition, dict) else {}
    return {
        "condition": condition_desc.get("text") if isinstance(condition_desc, dict) else condition.get("type", ""),
        "temperature_c": degrees(payload.get("temperature")),
        "feels_like_c": degrees(payload.get("feelsLikeTemperature")),
        "humidity_percent": payload.get("relativeHumidity"),
        "wind_speed_kmh": (payload.get("wind") or {}).get("speed", {}).get("value") if isinstance(payload.get("wind"), dict) else None,
        "uv_index": payload.get("uvIndex"),
        "current_time": payload.get("currentTime"),
    }


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


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_open_meteo_current(latitude: float, longitude: float) -> tuple[dict, str | None]:
    payload, error = fetch_json_url(open_meteo_current_url(latitude, longitude))
    if error or not isinstance(payload, dict):
        return {}, error or "Weather API returned an empty response."
    current = payload.get("current") or {}
    for key, value in list(current.items()):
        if key != "time":
            current[key] = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return current, None


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


@st.cache_data(ttl=WEATHER_REFRESH_HOURS * 3600, show_spinner=False)
def build_weather_dss_summary(points_key: tuple[tuple[str, str, str, float, float], ...], max_points: int = 12) -> pd.DataFrame:
    rows = []
    for point_type, point_name, district, latitude, longitude in points_key[:max_points]:
        daily, hourly, current, error, source = get_cached_open_meteo_weather(float(latitude), float(longitude))
        if daily.empty:
            rows.append(
                {
                    "point_type": point_type,
                    "point_name": point_name,
                    "district": district,
                    "latitude": latitude,
                    "longitude": longitude,
                    "forecast_rain_mm": math.nan,
                    "max_wind_kmh": math.nan,
                    "max_uv": math.nan,
                    "current_rain_mm": math.nan,
                    "current_temp_c": math.nan,
                    "weather_risk": "No Data",
                    "source": source,
                    "status": error or "No forecast data",
                }
            )
            continue
        forecast = daily[daily.get("period", pd.Series(dtype=str)) == "Forecast"].head(7).copy()
        if forecast.empty:
            forecast = daily.tail(7).copy()
        forecast_rain = pd.to_numeric(forecast.get("precipitation_sum"), errors="coerce").sum()
        max_wind = pd.to_numeric(forecast.get("wind_speed_10m_max"), errors="coerce").max()
        max_uv = pd.to_numeric(forecast.get("uv_index_max"), errors="coerce").max()
        current_row = current.iloc[0].to_dict() if not current.empty else {}
        risk = weather_risk_label(forecast_rain, max_wind, max_uv)
        rows.append(
            {
                "point_type": point_type,
                "point_name": point_name,
                "district": district,
                "latitude": latitude,
                "longitude": longitude,
                "forecast_rain_mm": round(float(forecast_rain), 2) if pd.notna(forecast_rain) else math.nan,
                "max_wind_kmh": round(float(max_wind), 2) if pd.notna(max_wind) else math.nan,
                "max_uv": round(float(max_uv), 2) if pd.notna(max_uv) else math.nan,
                "current_rain_mm": pd.to_numeric(pd.Series([current_row.get("precipitation")]), errors="coerce").iloc[0],
                "current_temp_c": pd.to_numeric(pd.Series([current_row.get("temperature_2m")]), errors="coerce").iloc[0],
                "weather_risk": risk,
                "source": source,
                "status": error or "OK",
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=WEATHER_REFRESH_HOURS * 3600, show_spinner=False)
def build_weather_forecast_for_points(points_key: tuple[tuple[str, str, float, float], ...]) -> pd.DataFrame:
    rows = []
    for point_name, district, latitude, longitude in points_key:
        daily, hourly, current, error, source = get_cached_open_meteo_weather(float(latitude), float(longitude))
        if daily.empty:
            rows.append(
                {
                    "town_name": point_name,
                    "district": district,
                    "latitude": latitude,
                    "longitude": longitude,
                    "forecast_rain_mm": math.nan,
                    "forecast_temp_max_c": math.nan,
                    "forecast_wind_max_kmh": math.nan,
                    "forecast_uv_max": math.nan,
                    "current_rain_mm": math.nan,
                    "current_temp_c": math.nan,
                    "weather_risk": "No Data",
                    "source": source,
                    "status": error or "No forecast data",
                }
            )
            continue
        forecast = daily[daily.get("period", pd.Series(dtype=str)) == "Forecast"].head(7).copy()
        if forecast.empty:
            forecast = daily.tail(7).copy()
        forecast_rain = pd.to_numeric(forecast.get("precipitation_sum"), errors="coerce").sum()
        forecast_temp = pd.to_numeric(forecast.get("temperature_2m_max"), errors="coerce").max()
        forecast_wind = pd.to_numeric(forecast.get("wind_speed_10m_max"), errors="coerce").max()
        forecast_uv = pd.to_numeric(forecast.get("uv_index_max"), errors="coerce").max()
        current_row = current.iloc[0].to_dict() if not current.empty else {}
        current_rain = pd.to_numeric(pd.Series([current_row.get("precipitation")]), errors="coerce").iloc[0]
        current_temp = pd.to_numeric(pd.Series([current_row.get("temperature_2m")]), errors="coerce").iloc[0]
        rows.append(
            {
                "town_name": point_name,
                "district": district,
                "latitude": latitude,
                "longitude": longitude,
                "forecast_rain_mm": round(float(forecast_rain), 2) if pd.notna(forecast_rain) else math.nan,
                "forecast_temp_max_c": round(float(forecast_temp), 2) if pd.notna(forecast_temp) else math.nan,
                "forecast_wind_max_kmh": round(float(forecast_wind), 2) if pd.notna(forecast_wind) else math.nan,
                "forecast_uv_max": round(float(forecast_uv), 2) if pd.notna(forecast_uv) else math.nan,
                "current_rain_mm": round(float(current_rain), 2) if pd.notna(current_rain) else math.nan,
                "current_temp_c": round(float(current_temp), 2) if pd.notna(current_temp) else math.nan,
                "weather_risk": weather_risk_label(forecast_rain, forecast_wind, forecast_uv),
                "source": source,
                "status": error or "OK",
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=WEATHER_REFRESH_HOURS * 3600, show_spinner=False)
def build_current_weather_for_towns(towns_key: tuple[tuple[str, str, float, float], ...]) -> pd.DataFrame:
    rows = []
    for town_name, district, latitude, longitude in towns_key:
        current_row, error, cache_source = get_cached_open_meteo_current(str(town_name), str(district), float(latitude), float(longitude))
        precipitation = current_row.get("precipitation")
        wind_speed = current_row.get("wind_speed_10m")
        risk = weather_risk_label(precipitation, wind_speed, current_row.get("uv_index"))
        rows.append(
            {
                "town_name": town_name,
                "district": district,
                "latitude": latitude,
                "longitude": longitude,
                "current_time": current_row.get("time", ""),
                "temperature_c": current_row.get("temperature_2m"),
                "feels_like_c": current_row.get("apparent_temperature"),
                "humidity_percent": current_row.get("relative_humidity_2m"),
                "precipitation_mm": precipitation,
                "rain_mm": current_row.get("rain"),
                "cloud_cover_percent": current_row.get("cloud_cover"),
                "wind_speed_kmh": wind_speed,
                "wind_gusts_kmh": current_row.get("wind_gusts_10m"),
                "weather_risk": risk if not error else "Unavailable",
                "status": error or cache_source,
            }
        )
    return pd.DataFrame(rows)


def weather_points_from_dams(dams: pd.DataFrame) -> pd.DataFrame:
    if dams.empty or not {"latitude", "longitude"}.issubset(dams.columns):
        return pd.DataFrame()
    points = dams.copy()
    points["latitude"] = pd.to_numeric(points["latitude"], errors="coerce")
    points["longitude"] = pd.to_numeric(points["longitude"], errors="coerce")
    points = points.dropna(subset=["latitude", "longitude"]).copy()
    points["town_name"] = points.get("reservoir_name", points.get("dam_name", "Dam")).fillna(points.get("dam_name", "Dam"))
    points["district"] = points.get("map_district", points.get("district", "")).fillna("Unassigned")
    points["basin"] = points.get("sub_basin", points.get("major_basin", "")).fillna("")
    points["priority_flag"] = points.get("alert_level", pd.Series("Dam", index=points.index)).fillna("Dam")
    return points[["town_name", "district", "latitude", "longitude", "basin", "priority_flag"]].drop_duplicates("town_name")


def weather_points_from_districts(dams: pd.DataFrame, towns: pd.DataFrame) -> pd.DataFrame:
    frames = []
    if not dams.empty and {"latitude", "longitude"}.issubset(dams.columns):
        dam_points = dams.copy()
        dam_points["latitude"] = pd.to_numeric(dam_points["latitude"], errors="coerce")
        dam_points["longitude"] = pd.to_numeric(dam_points["longitude"], errors="coerce")
        district_col = "map_district" if "map_district" in dam_points.columns else "district"
        if district_col in dam_points:
            frames.append(
                dam_points.dropna(subset=["latitude", "longitude", district_col])
                .assign(district=lambda data: data[district_col].astype(str))
                .groupby("district", as_index=False)
                .agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"))
            )
    if not towns.empty and {"district", "latitude", "longitude"}.issubset(towns.columns):
        town_points = towns.copy()
        town_points["latitude"] = pd.to_numeric(town_points["latitude"], errors="coerce")
        town_points["longitude"] = pd.to_numeric(town_points["longitude"], errors="coerce")
        frames.append(
            town_points.dropna(subset=["latitude", "longitude", "district"])
            .groupby("district", as_index=False)
            .agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"))
        )
    if not frames:
        return pd.DataFrame()
    districts = (
        pd.concat(frames, ignore_index=True)
        .groupby("district", as_index=False)
        .agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"))
        .sort_values("district")
    )
    districts["town_name"] = districts["district"] + " District"
    districts["basin"] = "District centroid"
    districts["priority_flag"] = "District"
    return districts[["town_name", "district", "latitude", "longitude", "basin", "priority_flag"]]


def render_weather_town_leaflet_map(
    towns: pd.DataFrame,
    selected_town: str,
    weather_tile_api_key: str = "",
    district_geojson: dict | None = None,
    map_title: str = "Weather Forecast Map: MP Points",
    dam_points: pd.DataFrame | None = None,
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
    dam_records = []
    if dam_points is not None and not dam_points.empty and {"latitude", "longitude"}.issubset(dam_points.columns):
        for row in dam_points.dropna(subset=["latitude", "longitude"]).to_dict("records"):
            risk = str(row.get("weather_risk") or "Dam")
            dam_records.append(
                {
                    "town": str(row.get("town_name") or row.get("reservoir_name") or row.get("dam_name") or "Dam"),
                    "district": str(row.get("district") or row.get("map_district") or ""),
                    "basin": str(row.get("basin") or row.get("sub_basin") or row.get("major_basin") or ""),
                    "priority": str(row.get("priority_flag") or "Dam"),
                    "lat": float(row["latitude"]),
                    "lon": float(row["longitude"]),
                    "risk": risk,
                    "color": weather_risk_color(risk),
                    "forecast_rain": round(float(row.get("forecast_rain_mm") or 0), 1),
                    "max_temp": round(float(row.get("forecast_temp_max_c") or 0), 1),
                    "max_wind": round(float(row.get("forecast_wind_max_kmh") or 0), 1),
                    "max_uv": round(float(row.get("forecast_uv_max") or 0), 1),
                    "source": str(row.get("source") or row.get("status") or "Location layer"),
                    "has_forecast": pd.notna(row.get("forecast_rain_mm")) if "forecast_rain_mm" in row else False,
                    "selected": str(row.get("town_name") or row.get("reservoir_name") or "") == selected_town,
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
        <div class="weather-map-title">{escape(map_title)}</div>
        <div class="weather-map-note">Markers are colored by 7-day rainfall, wind and UV risk. Dam forecast points are available as a separate map layer. {escape(layer_note)}</div>
        <div class="weather-layer-badges">
            {layer_badges_html}
        </div>
        <div id="{map_id}"></div>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
        (() => {{
            const towns = {json.dumps(records)};
            const dams = {json.dumps(dam_records)};
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
            const damLayer = L.layerGroup().addTo(map);
            dams.forEach((dam) => {{
                bounds.push([dam.lat, dam.lon]);
                const marker = L.circleMarker([dam.lat, dam.lon], {{
                    radius: dam.selected ? 7.4 : 4.4,
                    color: dam.selected ? "#111827" : "#ffffff",
                    weight: dam.selected ? 2.2 : 1,
                    fillColor: dam.has_forecast ? dam.color : "#7c3aed",
                    fillOpacity: dam.has_forecast ? 0.92 : 0.72
                }}).addTo(damLayer);
                marker.bindTooltip(`${{dam.town}} | ${{dam.has_forecast ? dam.risk : "Forecast pending"}}`, {{ sticky: true }});
                marker.bindPopup(`
                    <b>${{dam.town}}</b><br/>
                    District: ${{dam.district}}<br/>
                    Basin: ${{dam.basin}}<br/>
                    Weather risk: <b style="color:${{dam.color}}">${{dam.has_forecast ? dam.risk : "Forecast pending"}}</b><br/>
                    7-day rain: ${{dam.has_forecast ? dam.forecast_rain + " mm" : "Load dam forecasts"}}<br/>
                    Max temp: ${{dam.has_forecast ? dam.max_temp + " &deg;C" : "-"}}<br/>
                    Max wind: ${{dam.has_forecast ? dam.max_wind + " km/h" : "-"}}<br/>
                    Max UV: ${{dam.has_forecast ? dam.max_uv : "-"}}<br/>
                    Source: ${{dam.source}}
                `);
            }});
            layerControl.addOverlay(damLayer, "Dam forecast points");
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


def save_uploaded_river_flow_model(uploaded_file) -> Path:
    RIVER_FLOW_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".json":
        target = RIVER_FLOW_MODEL_DIR / "model_metadata.json"
    elif suffix == ".h5":
        target = RIVER_FLOW_MODEL_DIR / "river_flow_model.h5"
    else:
        target = RIVER_FLOW_MODEL_DIR / "river_flow_model.keras"
    target.write_bytes(uploaded_file.getbuffer())
    load_river_flow_tensorflow_model.clear()
    return target


def get_app_secret(name: str, env_name: str, default: str = "") -> str:
    value = os.getenv(env_name, "")
    if value:
        return value
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def visitor_headers() -> dict:
    try:
        return {str(key).lower(): str(value) for key, value in st.context.headers.items()}
    except Exception:
        return {}


def visitor_device_type(user_agent: str) -> str:
    agent = (user_agent or "").lower()
    if any(token in agent for token in ["mobile", "android", "iphone", "ipad"]):
        return "Mobile / Tablet"
    if any(token in agent for token in ["windows", "macintosh", "linux", "x11"]):
        return "Desktop"
    return "Unknown"


def visitor_browser_label(user_agent: str) -> str:
    agent = (user_agent or "").lower()
    if "edg/" in agent or "edge/" in agent:
        return "Microsoft Edge"
    if "chrome/" in agent and "chromium" not in agent:
        return "Chrome"
    if "firefox/" in agent:
        return "Firefox"
    if "safari/" in agent and "chrome/" not in agent:
        return "Safari"
    return "Other"


def init_visitor_analytics_db() -> None:
    VISITOR_ANALYTICS_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(VISITOR_ANALYTICS_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visitor_sessions (
                session_id TEXT PRIMARY KEY,
                visitor_hash TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                page_path TEXT,
                user_agent TEXT,
                device_type TEXT,
                browser TEXT,
                referrer TEXT,
                visits INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_sessions_first_seen ON visitor_sessions(first_seen)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visitor_sessions_visitor_hash ON visitor_sessions(visitor_hash)")


def record_visitor_session(page_path: str = "dashboard") -> None:
    init_visitor_analytics_db()
    if "visitor_session_id" not in st.session_state:
        st.session_state.visitor_session_id = uuid.uuid4().hex
    headers = visitor_headers()
    user_agent = headers.get("user-agent", "Unknown")
    referrer = headers.get("referer", "")
    forwarded_for = headers.get("x-forwarded-for", headers.get("x-real-ip", "local"))
    visitor_hash = hashlib.sha256(f"{forwarded_for}|{user_agent}".encode("utf-8", errors="ignore")).hexdigest()[:24]
    now = pd.Timestamp.now(tz="Asia/Kolkata").isoformat()
    session_id = str(st.session_state.visitor_session_id)
    with sqlite3.connect(VISITOR_ANALYTICS_DB) as conn:
        conn.execute(
            """
            INSERT INTO visitor_sessions
                (session_id, visitor_hash, first_seen, last_seen, page_path, user_agent, device_type, browser, referrer, visits)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(session_id) DO UPDATE SET
                last_seen = excluded.last_seen,
                page_path = excluded.page_path,
                visits = visitor_sessions.visits + 1
            """,
            (
                session_id,
                visitor_hash,
                now,
                now,
                page_path,
                user_agent[:500],
                visitor_device_type(user_agent),
                visitor_browser_label(user_agent),
                referrer[:500],
            ),
        )


def visitor_analytics_summary(days: int = 30) -> tuple[dict, pd.DataFrame]:
    init_visitor_analytics_db()
    with sqlite3.connect(VISITOR_ANALYTICS_DB) as conn:
        visits = pd.read_sql_query("SELECT * FROM visitor_sessions ORDER BY first_seen DESC", conn)
    if visits.empty:
        return {
            "total_sessions": 0,
            "unique_visitors": 0,
            "today_sessions": 0,
            "total_page_views": 0,
        }, visits
    visits["first_seen_dt"] = pd.to_datetime(visits["first_seen"], errors="coerce")
    visits["last_seen_dt"] = pd.to_datetime(visits["last_seen"], errors="coerce")
    today = pd.Timestamp.now(tz="Asia/Kolkata").date()
    recent_cutoff = pd.Timestamp.now(tz="Asia/Kolkata") - pd.Timedelta(days=days)
    recent = visits[visits["first_seen_dt"] >= recent_cutoff]
    summary = {
        "total_sessions": int(len(visits)),
        "unique_visitors": int(visits["visitor_hash"].nunique()),
        "today_sessions": int((visits["first_seen_dt"].dt.date == today).sum()),
        "total_page_views": int(pd.to_numeric(visits["visits"], errors="coerce").fillna(0).sum()),
        "recent_sessions": int(len(recent)),
    }
    return summary, visits


def render_public_visitor_counter() -> None:
    summary, _visits = visitor_analytics_summary()
    st.markdown(
        f"""
        <div class="visitor-counter-card">
          <span>Site Visitors</span>
          <b>{summary.get("unique_visitors", 0):,}</b>
          <small>{summary.get("total_sessions", 0):,} sessions | {summary.get("today_sessions", 0):,} today</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_visitor_analytics_admin() -> None:
    st.markdown(
        '<div class="panel-note">Monitor dashboard usage from local visitor sessions. Public users only see the compact visitor counter; detailed analytics remain administration-only.</div>',
        unsafe_allow_html=True,
    )
    summary, visits = visitor_analytics_summary()
    metric_cols = st.columns(5)
    metric_cols[0].metric("Unique Visitors", f"{summary.get('unique_visitors', 0):,}")
    metric_cols[1].metric("Visitor Sessions", f"{summary.get('total_sessions', 0):,}")
    metric_cols[2].metric("Today", f"{summary.get('today_sessions', 0):,}")
    metric_cols[3].metric("Page Views", f"{summary.get('total_page_views', 0):,}")
    metric_cols[4].metric("Last 30 Days", f"{summary.get('recent_sessions', 0):,}")
    if visits.empty:
        st.info("No visitor sessions have been recorded yet.")
        return

    visits = visits.copy()
    visits["visit_date"] = visits["first_seen_dt"].dt.date.astype(str)
    daily = (
        visits.groupby("visit_date", as_index=False)
        .agg(sessions=("session_id", "count"), unique_visitors=("visitor_hash", "nunique"), page_views=("visits", "sum"))
        .sort_values("visit_date")
    )
    chart = (
        alt.Chart(daily)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("visit_date:T", title="Visit Date"),
            y=alt.Y("sessions:Q", title="Sessions"),
            color=alt.value("#147df5"),
            tooltip=["visit_date", "sessions", "unique_visitors", "page_views"],
        )
        .properties(height=240)
    )
    st.altair_chart(chart, use_container_width=True)

    split_cols = st.columns(2)
    with split_cols[0]:
        device_summary = visits.groupby("device_type", as_index=False).agg(sessions=("session_id", "count"))
        st.dataframe(device_summary.sort_values("sessions", ascending=False), use_container_width=True, hide_index=True, height=170)
    with split_cols[1]:
        browser_summary = visits.groupby("browser", as_index=False).agg(sessions=("session_id", "count"))
        st.dataframe(browser_summary.sort_values("sessions", ascending=False), use_container_width=True, hide_index=True, height=170)

    detail_cols = ["first_seen", "last_seen", "device_type", "browser", "page_path", "visits", "visitor_hash"]
    st.dataframe(
        visits[[col for col in detail_cols if col in visits.columns]].head(300),
        use_container_width=True,
        hide_index=True,
        height=260,
    )


ADMIN_USER = get_app_secret("admin_user", "MPWRD_ADMIN_USER", "admin_nitaai")
ADMIN_PASSWORD = get_app_secret("admin_password", "MPWRD_ADMIN_PASSWORD", "")


def database_url_config() -> str:
    return get_app_secret("database_url", "DATABASE_URL", "").strip()


def database_engine_label(database_url: str) -> str:
    value = database_url.lower()
    if value.startswith("postgresql"):
        return "PostgreSQL"
    if value.startswith("mysql"):
        return "MySQL"
    if value:
        return "Unknown SQL database"
    return "Not configured"


def mask_database_url(database_url: str) -> str:
    if not database_url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(database_url)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        username = parsed.username or "user"
        database = parsed.path or ""
        return urllib.parse.urlunsplit((parsed.scheme, f"{username}:***@{host}{port}", database, "", ""))
    except Exception:
        return database_url.split("@")[-1] if "@" in database_url else "configured"


def alert_email_config() -> dict:
    port_text = get_app_secret("smtp_port", "SMTP_PORT", "587")
    try:
        port = int(port_text)
    except (TypeError, ValueError):
        port = 587
    use_tls_text = get_app_secret("smtp_use_tls", "SMTP_USE_TLS", "true").strip().lower()
    use_ssl_text = get_app_secret("smtp_use_ssl", "SMTP_USE_SSL", "false").strip().lower()
    username = get_app_secret("smtp_username", "SMTP_USERNAME", "")
    sender = get_app_secret("smtp_from", "SMTP_FROM", username)
    return {
        "provider": get_app_secret("email_provider", "EMAIL_PROVIDER", "auto").strip().lower(),
        "resend_api_key": get_app_secret("resend_api_key", "RESEND_API_KEY", ""),
        "brevo_api_key": get_app_secret("brevo_api_key", "BREVO_API_KEY", ""),
        "sendgrid_api_key": get_app_secret("sendgrid_api_key", "SENDGRID_API_KEY", ""),
        "host": get_app_secret("smtp_host", "SMTP_HOST", ""),
        "port": port,
        "username": username,
        "password": get_app_secret("smtp_password", "SMTP_PASSWORD", ""),
        "sender": sender,
        "use_tls": use_tls_text not in {"0", "false", "no", "off"},
        "use_ssl": use_ssl_text in {"1", "true", "yes", "on"},
    }


def alert_email_api_provider(config: dict | None = None) -> str:
    config = config or alert_email_config()
    provider = str(config.get("provider") or "auto").strip().lower()
    if provider in {"resend", "brevo", "sendgrid"}:
        return provider
    if config.get("resend_api_key"):
        return "resend"
    if config.get("brevo_api_key"):
        return "brevo"
    if config.get("sendgrid_api_key"):
        return "sendgrid"
    return ""


def alert_email_is_configured(config: dict | None = None) -> bool:
    config = config or alert_email_config()
    provider = alert_email_api_provider(config)
    if provider:
        key_name = f"{provider}_api_key"
        return bool(str(config.get(key_name) or "").strip() and str(config.get("sender") or "").strip())
    return all(str(config.get(key) or "").strip() for key in ["host", "username", "password", "sender"])


def alert_email_missing_settings(config: dict | None = None) -> list[str]:
    config = config or alert_email_config()
    provider = alert_email_api_provider(config)
    if provider:
        required = {
            f"{provider}_api_key": f"{provider}_api_key / {provider.upper()}_API_KEY",
            "sender": "smtp_from / SMTP_FROM",
        }
        return [label for key, label in required.items() if not str(config.get(key) or "").strip()]
    required = {
        "host": "smtp_host / SMTP_HOST",
        "username": "smtp_username / SMTP_USERNAME",
        "password": "smtp_password / SMTP_PASSWORD",
        "sender": "smtp_from / SMTP_FROM",
    }
    return [label for key, label in required.items() if not str(config.get(key) or "").strip()]


def post_json(url: str, payload: dict, headers: dict) -> tuple[bool, str]:
    try:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return 200 <= response.status < 300, body or f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return False, body or f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)


def extract_email_recipients(recipients_text: str) -> list[str]:
    emails = []
    for line in recipients_text.splitlines():
        emails.extend(re.findall(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}", line))
    return sorted(set(emails))


def send_alert_email(subject: str, body: str, recipients: list[str], html_body: str | None = None) -> tuple[bool, str]:
    if not recipients:
        return False, "No email recipients were found. Add one email address per recipient line."
    config = alert_email_config()
    if not alert_email_is_configured(config):
        missing = ", ".join(alert_email_missing_settings(config))
        return False, f"Email delivery is not configured. Missing: {missing}."

    provider = alert_email_api_provider(config)
    if provider:
        failures = []
        for recipient in recipients:
            if provider == "resend":
                ok, detail = post_json(
                    "https://api.resend.com/emails",
                    {
                        "from": config["sender"],
                        "to": [recipient],
                        "subject": subject,
                        "text": body,
                        "html": html_body or body.replace("\n", "<br>"),
                    },
                    {
                        "Authorization": f"Bearer {config['resend_api_key']}",
                        "Content-Type": "application/json",
                    },
                )
            elif provider == "brevo":
                ok, detail = post_json(
                    "https://api.brevo.com/v3/smtp/email",
                    {
                        "sender": {"email": config["sender"], "name": "NITA GeoAI Alerts"},
                        "to": [{"email": recipient}],
                        "subject": subject,
                        "textContent": body,
                        "htmlContent": html_body or body.replace("\n", "<br>"),
                    },
                    {
                        "api-key": config["brevo_api_key"],
                        "Content-Type": "application/json",
                    },
                )
            else:
                ok, detail = post_json(
                    "https://api.sendgrid.com/v3/mail/send",
                    {
                        "personalizations": [{"to": [{"email": recipient}]}],
                        "from": {"email": config["sender"]},
                        "subject": subject,
                        "content": [
                            {"type": "text/plain", "value": body},
                            {"type": "text/html", "value": html_body or body.replace("\n", "<br>")},
                        ],
                    },
                    {
                        "Authorization": f"Bearer {config['sendgrid_api_key']}",
                        "Content-Type": "application/json",
                    },
                )
            if not ok:
                failures.append(f"{recipient}: {detail[:180]}")
        if failures:
            return False, f"{provider.title()} email API failed for {len(failures)} recipient(s): {' | '.join(failures[:2])}"
        return True, f"Email sent privately to {len(recipients)} recipient(s) using {provider.title()} API."

    def send_with_config(active_config: dict) -> None:
        smtp_class = smtplib.SMTP_SSL if active_config.get("use_ssl") else smtplib.SMTP
        with smtp_class(active_config["host"], int(active_config["port"]), timeout=35) as smtp:
            if active_config["use_tls"] and not active_config.get("use_ssl"):
                smtp.starttls()
            smtp.login(active_config["username"], active_config["password"])
            for recipient in recipients:
                message = EmailMessage()
                message["Subject"] = subject
                message["From"] = active_config["sender"]
                message["To"] = recipient
                message.set_content(body)
                if html_body:
                    message.add_alternative(html_body, subtype="html")
                smtp.send_message(message)

    try:
        send_with_config(config)
        return True, f"Email sent privately to {len(recipients)} recipient(s)."
    except Exception as exc:
        if str(config.get("host", "")).endswith("secureserver.net") and not config.get("use_ssl"):
            fallback = {**config, "port": 465, "use_tls": False, "use_ssl": True}
            try:
                send_with_config(fallback)
                return True, f"Email sent privately to {len(recipients)} recipient(s) using SSL fallback."
            except Exception as fallback_exc:
                return False, f"Email delivery failed: {exc}; SSL fallback also failed: {fallback_exc}"
        return False, f"Email delivery failed: {exc}"


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


if "main_dashboard_page" not in st.session_state:
    st.session_state.main_dashboard_page = "Infographics"

record_visitor_session(st.session_state.main_dashboard_page)

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
    render_public_visitor_counter()
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


def dam_alert_email_html(row: pd.Series, message_text: str) -> str:
    alert_level = str(row.get("configured_alert") or row.get("alert_level") or "Alert")
    alert_colors = {
        "Critical": "#dc2626",
        "Warning": "#f59e0b",
        "Watch": "#eab308",
        "Normal": "#2563eb",
    }
    accent = alert_colors.get(alert_level, "#2563eb")
    reservoir = row.get("reservoir_name") or row.get("dam_name") or "Reservoir"
    district = row.get("district") or row.get("map_district") or "-"
    basin = row.get("sub_basin") or row.get("major_basin") or "-"
    observed_at = row.get("observed_at")
    observed_label = time_label(observed_at) if pd.notna(observed_at) else "Latest dashboard observation"
    rows = [
        ("Reservoir", reservoir),
        ("District", district),
        ("Basin", basin),
        ("Observed At", observed_label),
        ("Current Water Level", fmt_number(row.get("water_level_m"), " m")),
        ("FRL", fmt_number(row.get("frl_m"), " m")),
        ("FRL Gap", fmt_number(row.get("frl_gap_m"), " m")),
        ("Filling", fmt_number(row.get("display_filling"), "%")),
        ("Latest WL Change", fmt_number(row.get("wl_delta_m"), " m")),
        ("Alert Reason", row.get("alert_reason") or "-"),
    ]
    metric_rows = "\n".join(
        f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e5edf7;color:#64748b;font-size:13px;">{escape(str(label))}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5edf7;color:#0f172a;font-size:13px;font-weight:700;">{escape(str(value))}</td>
        </tr>
        """
        for label, value in rows
    )
    plain_lines = "".join(f"<li>{escape(line)}</li>" for line in message_text.splitlines() if line.strip())
    generated_at = pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y, %I:%M %p IST")
    return f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:0;background:#eef3f8;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
        <div style="max-width:720px;margin:0 auto;padding:24px;">
          <div style="background:#0f172a;border-radius:14px 14px 0 0;padding:20px 24px;color:#ffffff;">
            <div style="font-size:12px;letter-spacing:1.8px;text-transform:uppercase;color:#93c5fd;font-weight:700;">NITA AI & Geo-Analytics | MPWRD DSS</div>
            <h1 style="margin:8px 0 4px;font-size:24px;line-height:1.22;">Dam Water Level Alert Report</h1>
            <div style="font-size:13px;color:#cbd5e1;">Generated: {escape(generated_at)}</div>
          </div>
          <div style="background:#ffffff;border:1px solid #dbe6f4;border-top:0;border-radius:0 0 14px 14px;overflow:hidden;">
            <div style="padding:22px 24px;border-left:8px solid {accent};background:#fbfdff;">
              <div style="display:inline-block;background:{accent};color:#ffffff;border-radius:999px;padding:7px 12px;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.8px;">{escape(alert_level)} Alert</div>
              <h2 style="margin:12px 0 4px;font-size:22px;color:#0f172a;">{escape(str(reservoir))}</h2>
              <p style="margin:0;color:#64748b;font-size:14px;">{escape(str(district))} district | {escape(str(basin))} basin</p>
            </div>
            <div style="padding:20px 24px;">
              <table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;border:1px solid #e5edf7;border-radius:10px;overflow:hidden;">
                {metric_rows}
              </table>
              <div style="margin-top:18px;padding:16px;border-radius:10px;background:#f8fafc;border:1px solid #e5edf7;">
                <div style="font-size:13px;font-weight:800;color:#334155;text-transform:uppercase;letter-spacing:0.9px;margin-bottom:8px;">Recommended DSS Actions</div>
                <ol style="margin:0;padding-left:20px;color:#334155;font-size:14px;line-height:1.55;">
                  <li>Verify current reservoir level, inflow, gate status and downstream gauge trend.</li>
                  <li>Keep district control room and dam safety officer on watch for rapid rise or FRL approach.</li>
                  <li>Escalate warning protocol if the next observation confirms rising level or reduced FRL gap.</li>
                </ol>
              </div>
              <div style="margin-top:18px;padding:16px;border-radius:10px;background:#fff7ed;border:1px solid #fed7aa;">
                <div style="font-size:13px;font-weight:800;color:#9a3412;text-transform:uppercase;letter-spacing:0.9px;margin-bottom:8px;">Operational Message</div>
                <ul style="margin:0;padding-left:18px;color:#431407;font-size:14px;line-height:1.55;">{plain_lines}</ul>
              </div>
            </div>
            <div style="padding:14px 24px;background:#f1f5f9;color:#64748b;font-size:12px;border-top:1px solid #e5edf7;">
              This automated DSS email is generated from MPWRD flood report observations and NITA GeoAI analytics. Validate with official field communication before public warning release.
            </div>
          </div>
        </div>
      </body>
    </html>
    """


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


def assistant_table(frame: pd.DataFrame, columns: list[str], limit: int = 12) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    available = [column for column in columns if column in frame.columns]
    if not available:
        return pd.DataFrame()
    return prettify_dataframe_columns(frame[available].head(limit).copy())


def local_ai_config() -> dict:
    enabled = get_app_secret("local_ai_enabled", "LOCAL_AI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "enabled": enabled,
        "provider": get_app_secret("local_ai_provider", "LOCAL_AI_PROVIDER", "ollama").strip().lower() or "ollama",
        "base_url": get_app_secret("ollama_base_url", "OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/"),
        "model": get_app_secret("ollama_model", "OLLAMA_MODEL", "llama3.2:3b").strip() or "llama3.2:3b",
    }


def call_ollama_chat(prompt: str, config: dict) -> tuple[str, str | None]:
    url = f"{config['base_url']}/api/chat"
    payload = {
        "model": config["model"],
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an MPWRD dam safety DSS assistant. Use only the supplied dashboard facts and table preview. "
                    "Do not invent reservoir names, dates, values, forecasts, or alerts. If the table is insufficient, say what data is missing. "
                    "Respond with concise operational interpretation, next checks, and caveats."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.2, "num_predict": 450},
    }
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        message = data.get("message") or {}
        content = str(message.get("content") or "").strip()
        if not content:
            return "", "Local AI model returned an empty response."
        return content, None
    except Exception as exc:
        return "", f"Local AI unavailable: {exc}"


def local_ai_enhance_answer(question: str, answer: dict) -> dict:
    config = local_ai_config()
    if not config["enabled"] or config["provider"] != "ollama":
        return answer
    table = answer.get("table")
    table_preview = ""
    if isinstance(table, pd.DataFrame) and not table.empty:
        preview = table.head(18).copy()
        table_preview = preview.to_csv(index=False)
    prompt = (
        f"User question:\n{question}\n\n"
        f"Deterministic dashboard answer:\n{answer.get('text', '')}\n\n"
        f"Table preview CSV:\n{table_preview if table_preview else 'No table rows returned.'}\n\n"
        "Improve the final answer for a professional DSS user. Preserve the facts and do not alter table values."
    )
    ai_text, error = call_ollama_chat(prompt, config)
    if error:
        enriched = dict(answer)
        enriched["ai_status"] = error
        return enriched
    enriched = dict(answer)
    enriched["text"] = f"{answer.get('text', '')}\n\nLocal AI interpretation:\n{ai_text}"
    enriched["ai_status"] = f"Enhanced with local {config['model']} via Ollama."
    return enriched


def local_ai_status_text() -> str:
    config = local_ai_config()
    if not config["enabled"]:
        return "Local AI model is optional and currently disabled. Structured DSS queries are active."
    if config["provider"] != "ollama":
        return f"Local AI provider '{config['provider']}' is configured but only Ollama is supported in this build."
    return f"Local AI enabled: Ollama model `{config['model']}` at `{config['base_url']}`."


def assistant_match_dam(query: str, map_frame: pd.DataFrame) -> str | None:
    if map_frame.empty or "reservoir_name" not in map_frame:
        return None
    names = sorted(map_frame["reservoir_name"].dropna().astype(str).unique(), key=len, reverse=True)
    for name in names:
        if normalize_name(name) in query:
            return name
    return None


def assistant_unique_values(frames: list[pd.DataFrame], columns: list[str]) -> list[str]:
    values: set[str] = set()
    for frame in frames:
        if frame.empty:
            continue
        for column in columns:
            if column in frame.columns:
                values.update(frame[column].dropna().astype(str).str.strip().replace("", pd.NA).dropna().tolist())
    return sorted(values, key=len, reverse=True)


def assistant_query_filters(query: str, map_frame: pd.DataFrame, reservoir_frame: pd.DataFrame, river_frame: pd.DataFrame) -> dict:
    filters: dict[str, object] = {"districts": [], "reservoirs": [], "gauges": [], "alerts": [], "fill_min": None, "fill_max": None}
    normalized = normalize_name(query)
    for district in assistant_unique_values([map_frame, reservoir_frame, river_frame], ["map_district", "district"]):
        if normalize_name(district) and normalize_name(district) in normalized:
            filters["districts"].append(district)
    for reservoir in assistant_unique_values([map_frame, reservoir_frame], ["reservoir_name", "dam_name"]):
        if normalize_name(reservoir) and normalize_name(reservoir) in normalized:
            filters["reservoirs"].append(reservoir)
    for gauge in assistant_unique_values([river_frame], ["gauge_station", "river_name"]):
        if normalize_name(gauge) and normalize_name(gauge) in normalized:
            filters["gauges"].append(gauge)
    for alert in ["Critical", "Warning", "Watch", "Normal"]:
        if alert.lower() in normalized:
            filters["alerts"].append(alert)
    below_match = re.search(r"(?:below|under|less than|<=|<)\s*(\d+(?:\.\d+)?)\s*%?", normalized)
    above_match = re.search(r"(?:above|over|more than|>=|>)\s*(\d+(?:\.\d+)?)\s*%?", normalized)
    between_match = re.search(r"between\s*(\d+(?:\.\d+)?)\s*(?:and|to|-)\s*(\d+(?:\.\d+)?)\s*%?", normalized)
    if between_match:
        low, high = sorted([float(between_match.group(1)), float(between_match.group(2))])
        filters["fill_min"], filters["fill_max"] = low, high
    elif below_match:
        filters["fill_max"] = float(below_match.group(1))
    elif above_match:
        filters["fill_min"] = float(above_match.group(1))
    return filters


def assistant_apply_filters(frame: pd.DataFrame, filters: dict, prefer_map_district: bool = True) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    districts = filters.get("districts") or []
    reservoirs = filters.get("reservoirs") or []
    alerts = filters.get("alerts") or []
    gauges = filters.get("gauges") or []
    if districts:
        district_cols = ["map_district", "district"] if prefer_map_district else ["district", "map_district"]
        district_mask = pd.Series(False, index=result.index)
        for column in district_cols:
            if column in result.columns:
                district_mask = district_mask | result[column].astype(str).isin(districts)
        result = result[district_mask]
    if reservoirs:
        reservoir_mask = pd.Series(False, index=result.index)
        for column in ["reservoir_name", "dam_name"]:
            if column in result.columns:
                reservoir_mask = reservoir_mask | result[column].astype(str).isin(reservoirs)
        result = result[reservoir_mask]
    if alerts and "alert_level" in result.columns:
        result = result[result["alert_level"].astype(str).isin(alerts)]
    if gauges:
        gauge_mask = pd.Series(False, index=result.index)
        for column in ["gauge_station", "river_name"]:
            if column in result.columns:
                gauge_mask = gauge_mask | result[column].astype(str).isin(gauges)
        result = result[gauge_mask]
    fill_col = "display_filling" if "display_filling" in result.columns else "filling_percent" if "filling_percent" in result.columns else None
    if fill_col:
        filling = pd.to_numeric(result[fill_col], errors="coerce")
        if filters.get("fill_min") is not None:
            result = result[filling >= float(filters["fill_min"])]
            filling = pd.to_numeric(result[fill_col], errors="coerce")
        if filters.get("fill_max") is not None:
            result = result[filling <= float(filters["fill_max"])]
    return result


def assistant_reservoir_trend_summary(reservoir_frame: pd.DataFrame, filters: dict, limit: int = 12) -> pd.DataFrame:
    if reservoir_frame.empty or not {"reservoir_name", "observed_at", "water_level_m"}.issubset(reservoir_frame.columns):
        return pd.DataFrame()
    frame = assistant_apply_filters(reservoir_frame, filters).copy()
    if frame.empty:
        return pd.DataFrame()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], errors="coerce")
    frame["water_level_m"] = pd.to_numeric(frame["water_level_m"], errors="coerce")
    frame["filling_percent"] = pd.to_numeric(frame.get("filling_percent"), errors="coerce") if "filling_percent" in frame else math.nan
    frame = frame.dropna(subset=["reservoir_name", "observed_at", "water_level_m"]).sort_values(["reservoir_name", "observed_at"])
    rows = []
    for reservoir, group in frame.groupby("reservoir_name"):
        if len(group) < 2:
            continue
        first = group.iloc[0]
        latest = group.iloc[-1]
        delta = float(latest["water_level_m"] - first["water_level_m"])
        direction = "Rising" if delta > 0.05 else "Falling" if delta < -0.05 else "Stable"
        rows.append(
            {
                "reservoir_name": reservoir,
                "district": latest.get("district", ""),
                "start_time": first["observed_at"],
                "latest_time": latest["observed_at"],
                "start_water_level_m": first["water_level_m"],
                "latest_water_level_m": latest["water_level_m"],
                "water_level_change_m": round(delta, 2),
                "latest_filling_percent": latest.get("filling_percent", math.nan),
                "trend": direction,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("water_level_change_m", ascending=False).head(limit)


def assistant_days_requested(query: str, default: int = 5) -> int:
    match = re.search(r"(?:last|past|previous)\s+(\d{1,2})\s*(?:day|days|date|dates)", normalize_name(query))
    if match:
        return max(1, min(30, int(match.group(1))))
    return default


def assistant_historical_alert_table(
    query: str,
    map_frame: pd.DataFrame,
    reservoir_frame: pd.DataFrame,
    filters: dict,
) -> pd.DataFrame:
    if reservoir_frame.empty or not {"reservoir_name", "observed_at", "water_level_m"}.issubset(reservoir_frame.columns):
        return pd.DataFrame()
    days = assistant_days_requested(query, default=5)
    history = assistant_apply_filters(reservoir_frame, filters).copy()
    if history.empty:
        return pd.DataFrame()
    history["observed_at"] = pd.to_datetime(history["observed_at"], errors="coerce")
    history["observation_date"] = history["observed_at"].dt.date
    history["water_level_m"] = pd.to_numeric(history.get("water_level_m"), errors="coerce")
    history["frl_m"] = pd.to_numeric(history.get("frl_m"), errors="coerce") if "frl_m" in history else math.nan
    history["filling_percent"] = pd.to_numeric(history.get("filling_percent"), errors="coerce") if "filling_percent" in history else math.nan
    if "frl_gap_m" not in history.columns:
        history["frl_gap_m"] = history["frl_m"] - history["water_level_m"]
    else:
        history["frl_gap_m"] = pd.to_numeric(history["frl_gap_m"], errors="coerce")
    history = history.dropna(subset=["reservoir_name", "observed_at", "water_level_m"])
    if history.empty:
        return pd.DataFrame()
    latest_dates = sorted(history["observation_date"].dropna().unique())[-days:]
    history = history[history["observation_date"].isin(latest_dates)].copy()
    if history.empty:
        return pd.DataFrame()
    if "critical" in normalize_name(query):
        current_critical = []
        if not map_frame.empty and {"reservoir_name", "alert_level"}.issubset(map_frame.columns):
            current_critical = map_frame.loc[
                map_frame["alert_level"].astype(str) == "Critical",
                "reservoir_name",
            ].dropna().astype(str).unique().tolist()
        if current_critical:
            history = history[history["reservoir_name"].astype(str).isin(current_critical)]
        else:
            history = history[pd.to_numeric(history["frl_gap_m"], errors="coerce") <= 0.5]
    latest_per_day = (
        history.sort_values(["reservoir_name", "observation_date", "observed_at"])
        .groupby(["reservoir_name", "observation_date"], as_index=False)
        .tail(1)
    )
    if latest_per_day.empty:
        return pd.DataFrame()
    latest_per_day["computed_alert_level"] = latest_per_day.apply(
        lambda row: "Critical"
        if pd.notna(row.get("frl_gap_m")) and row.get("frl_gap_m") <= 0.5
        else "Warning"
        if pd.notna(row.get("frl_gap_m")) and row.get("frl_gap_m") <= 1.5
        else "Watch"
        if pd.notna(row.get("filling_percent")) and row.get("filling_percent") >= 90
        else "Normal",
        axis=1,
    )
    columns = [
        "observation_date",
        "observed_at",
        "reservoir_name",
        "district",
        "water_level_m",
        "frl_m",
        "frl_gap_m",
        "filling_percent",
        "computed_alert_level",
    ]
    available = [column for column in columns if column in latest_per_day.columns]
    return latest_per_day[available].sort_values(["reservoir_name", "observation_date"])


def dashboard_assistant_answer(
    question: str,
    map_status_frame: pd.DataFrame,
    reservoir_frame: pd.DataFrame,
    river_frame: pd.DataFrame,
    gate_frame: pd.DataFrame,
    page_name: str,
    weather_points_frame: pd.DataFrame | None = None,
    historical_reservoir_frame: pd.DataFrame | None = None,
) -> dict:
    query = normalize_name(question)
    history_reservoir_frame = (
        historical_reservoir_frame.copy()
        if isinstance(historical_reservoir_frame, pd.DataFrame) and not historical_reservoir_frame.empty
        else reservoir_frame
    )
    latest_label = "current filter"
    if not reservoir_frame.empty and "observed_at" in reservoir_frame:
        latest_time = pd.to_datetime(reservoir_frame["observed_at"], errors="coerce").dropna()
        if not latest_time.empty:
            latest_label = time_label(latest_time.max())

    if not map_status_frame.empty:
        map_frame = map_status_frame.copy()
        map_frame["display_filling"] = pd.to_numeric(map_frame.get("display_filling"), errors="coerce")
        map_frame["frl_gap_m"] = pd.to_numeric(map_frame.get("frl_gap_m"), errors="coerce")
    else:
        map_frame = pd.DataFrame()

    filters = assistant_query_filters(query, map_frame, history_reservoir_frame, river_frame)
    advanced_terms = [
        "query",
        "get",
        "filter",
        "show",
        "list",
        "table",
        "tables",
        "find",
        "count",
        "how many",
        "compare",
        "last",
        "previous",
        "trend",
        "history",
        "past",
        "day",
        "days",
        "rising",
        "falling",
        "increase",
        "decrease",
    ]
    if query and any(term in query for term in advanced_terms):
        if any(term in query for term in ["last", "past", "previous", "history", "day", "days"]) and any(term in query for term in ["critical", "warning", "alert", "frl"]):
            historical_alerts = assistant_historical_alert_table(query, map_frame, history_reservoir_frame, filters)
            if not historical_alerts.empty:
                days = historical_alerts["observation_date"].nunique() if "observation_date" in historical_alerts else assistant_days_requested(query)
                dams = historical_alerts["reservoir_name"].nunique() if "reservoir_name" in historical_alerts else 0
                latest_rows = historical_alerts.sort_values("observed_at").groupby("reservoir_name", as_index=False).tail(1)
                critical_latest = int((latest_rows.get("computed_alert_level", pd.Series(dtype=str)) == "Critical").sum())
                text = (
                    f"Historical alert query returned day-wise water-level observations for {dams} critical reservoir(s) "
                    f"across the latest {days} available observation day(s) in the active data. "
                    f"{critical_latest} of these remain Critical in their latest row. "
                    "The table uses the latest observation available per reservoir per day and recomputes alert status from FRL gap/filling where possible."
                )
                return {"text": text, "table": prettify_dataframe_columns(historical_alerts.head(80))}
        if any(term in query for term in ["trend", "history", "past", "rising", "falling", "increase", "decrease"]):
            trend_table = assistant_reservoir_trend_summary(history_reservoir_frame, filters, limit=15)
            if not trend_table.empty:
                rising = int((trend_table["trend"] == "Rising").sum())
                falling = int((trend_table["trend"] == "Falling").sum())
                fastest = trend_table.iloc[0]
                text = (
                    f"Advanced trend query analysed {len(trend_table)} reservoir time-series record(s) under the active filters. "
                    f"{rising} are rising and {falling} are falling in the selected report window. "
                    f"The strongest rise is {fastest['reservoir_name']} with {fastest['water_level_change_m']:+.2f} m change. "
                    "Use this with FRL gap, filling percentage and gate status before issuing operational advice."
                )
                return {"text": text, "table": prettify_dataframe_columns(trend_table)}
        if any(term in query for term in ["river", "gauge", "station", "danger"]):
            filtered_rivers = assistant_apply_filters(river_frame, filters, prefer_map_district=False)
            if not filtered_rivers.empty:
                if {"water_level_m", "danger_or_max_water_level_m"}.issubset(filtered_rivers.columns):
                    filtered_rivers = filtered_rivers.copy()
                    filtered_rivers["danger_gap_m"] = pd.to_numeric(filtered_rivers["danger_or_max_water_level_m"], errors="coerce") - pd.to_numeric(filtered_rivers["water_level_m"], errors="coerce")
                    filtered_rivers = filtered_rivers.sort_values("danger_gap_m")
                text = f"Advanced river/gauge query returned {len(filtered_rivers)} observation row(s) under the requested filters."
                return {
                    "text": text,
                    "table": assistant_table(filtered_rivers, ["river_name", "gauge_station", "district", "water_level_m", "danger_or_max_water_level_m", "danger_gap_m", "observed_at"], 20),
                }
        if any(term in query for term in ["gate", "gates", "opened", "discharge"]):
            filtered_gates = assistant_apply_filters(gate_frame, filters, prefer_map_district=False)
            if not filtered_gates.empty:
                filtered_gates = filtered_gates.copy()
                filtered_gates["gate_opened_count"] = pd.to_numeric(filtered_gates.get("gate_opened_count"), errors="coerce").fillna(0)
                if any(term in query for term in ["open", "opened"]):
                    filtered_gates = filtered_gates[filtered_gates["gate_opened_count"] > 0]
                filtered_gates = filtered_gates.sort_values(["gate_opened_count", "reservoir_name"], ascending=[False, True])
                text = f"Advanced gate query returned {len(filtered_gates)} gate observation row(s)."
                return {
                    "text": text,
                    "table": assistant_table(filtered_gates, ["reservoir_name", "district", "gate_opened_count", "total_no_of_gates", "opening_m", "discharge_cumecs", "discharge_cusec", "report_at"], 20),
                }
        filtered_map = assistant_apply_filters(map_frame, filters)
        if not filtered_map.empty:
            filtered_map = filtered_map.copy()
            if "display_filling" in filtered_map:
                filtered_map["display_filling"] = pd.to_numeric(filtered_map["display_filling"], errors="coerce")
            if any(term in query for term in ["count", "how many"]):
                district_col = "map_district" if "map_district" in filtered_map else "district"
                count_table = (
                    filtered_map.assign(district_label=filtered_map.get(district_col, pd.Series("Unassigned", index=filtered_map.index)).fillna("Unassigned"))
                    .groupby("district_label", as_index=False)
                    .agg(
                        reservoirs=("reservoir_name", "nunique"),
                        avg_filling_percent=("display_filling", "mean"),
                        critical=("alert_level", lambda data: int((data == "Critical").sum())),
                        warning=("alert_level", lambda data: int((data == "Warning").sum())),
                        watch=("alert_level", lambda data: int((data == "Watch").sum())),
                    )
                    .sort_values(["critical", "warning", "avg_filling_percent"], ascending=False)
                )
                text = f"Advanced count query grouped {filtered_map['reservoir_name'].nunique()} reservoir(s) by district under the requested filters."
                return {"text": text, "table": prettify_dataframe_columns(count_table.head(20))}
            sort_col = "frl_gap_m" if any(term in query for term in ["frl", "gap", "critical", "warning"]) and "frl_gap_m" in filtered_map else "display_filling"
            ascending = sort_col == "frl_gap_m" or any(term in query for term in ["least", "low", "below", "falling"])
            filtered_map = filtered_map.sort_values(sort_col, ascending=ascending, na_position="last")
            filter_bits = []
            if filters.get("districts"):
                filter_bits.append("district: " + ", ".join(filters["districts"]))
            if filters.get("alerts"):
                filter_bits.append("alert: " + ", ".join(filters["alerts"]))
            if filters.get("fill_min") is not None:
                filter_bits.append(f"filling >= {filters['fill_min']:.0f}%")
            if filters.get("fill_max") is not None:
                filter_bits.append(f"filling <= {filters['fill_max']:.0f}%")
            text = (
                f"Advanced reservoir query returned {filtered_map['reservoir_name'].nunique()} reservoir(s)"
                + (f" for {', '.join(filter_bits)}." if filter_bits else ".")
                + " The result is sorted by the most operationally relevant metric inferred from the question."
            )
            return {
                "text": text,
                "table": assistant_table(filtered_map, ["reservoir_name", "dam_name", "map_district", "sub_basin", "water_level_m", "frl_gap_m", "display_filling", "alert_level", "observed_at"], 20),
            }

    weather_terms = ["weather", "rain", "rainfall", "forecast", "temperature", "wind", "uv", "cloud", "meteo", "open meteo"]
    if any(term in query for term in weather_terms):
        weather_points = weather_points_frame.copy() if isinstance(weather_points_frame, pd.DataFrame) else pd.DataFrame()
        if weather_points.empty:
            return {"text": "No weather points are available for DSS analysis. Add town, dam, or district weather coordinates.", "table": pd.DataFrame()}
        if matched_dam := assistant_match_dam(query, map_frame):
            matched_points = weather_points[weather_points["point_name"].astype(str).map(normalize_name) == normalize_name(matched_dam)].copy()
            if not matched_points.empty:
                weather_points = matched_points
        if "district" in weather_points:
            district_matches = [
                district for district in weather_points["district"].dropna().astype(str).unique()
                if normalize_name(district) and normalize_name(district) in query
            ]
            if district_matches:
                weather_points = weather_points[weather_points["district"].astype(str).isin(district_matches)]
        priority_points = weather_points.copy()
        if "point_type" in priority_points:
            priority_points["type_priority"] = priority_points["point_type"].map({"Dam": 0, "District": 1, "Town": 2}).fillna(3)
            priority_points = priority_points.sort_values(["type_priority", "district", "point_name"])
        points_key = tuple(
            (
                str(row.point_type),
                str(row.point_name),
                str(row.district),
                float(row.latitude),
                float(row.longitude),
            )
            for row in priority_points.dropna(subset=["latitude", "longitude"]).head(12).itertuples(index=False)
        )
        if not points_key:
            return {"text": "Weather DSS points are available, but none have valid coordinates under the current filter.", "table": pd.DataFrame()}
        weather_summary = build_weather_dss_summary(points_key, max_points=12)
        if weather_summary.empty:
            return {"text": "Weather DSS analysis did not return forecast rows for the selected points.", "table": pd.DataFrame()}
        weather_summary = weather_summary.sort_values(["weather_risk", "forecast_rain_mm"], ascending=[True, False])
        severe_count = int(weather_summary["weather_risk"].isin(["Severe", "High"]).sum()) if "weather_risk" in weather_summary else 0
        max_rain = pd.to_numeric(weather_summary.get("forecast_rain_mm"), errors="coerce").max()
        max_wind = pd.to_numeric(weather_summary.get("max_wind_kmh"), errors="coerce").max()
        highest = weather_summary.sort_values("forecast_rain_mm", ascending=False).iloc[0]
        text = (
            f"Weather intelligence for the active DSS area indicates {severe_count} High/Severe risk location(s) "
            f"out of {len(weather_summary)} analysed point(s). The highest 7-day rainfall signal is "
            f"{fmt_number(max_rain, ' mm')} near {highest.get('point_name')} in {highest.get('district')}, "
            f"with peak wind potential of {fmt_number(max_wind, ' km/h')}. "
            "Operational interpretation: combine the rainfall and wind outlook with reservoir filling, FRL gap, gate status, "
            "and downstream gauge trend before escalating field advisories or official alert messages."
        )
        table = prettify_dataframe_columns(
            weather_summary[
                [
                    "point_type",
                    "point_name",
                    "district",
                    "forecast_rain_mm",
                    "current_rain_mm",
                    "max_wind_kmh",
                    "max_uv",
                    "current_temp_c",
                    "weather_risk",
                    "source",
                ]
            ].head(12)
        )
        return {"text": text, "table": table}

    matched_dam = assistant_match_dam(query, map_frame)
    if matched_dam:
        dam_rows = map_frame[map_frame["reservoir_name"].astype(str) == matched_dam].copy()
        latest = dam_rows.iloc[0] if not dam_rows.empty else pd.Series(dtype=object)
        dam_history = history_reservoir_frame[
            history_reservoir_frame.get("reservoir_name", pd.Series(dtype=str)).astype(str) == matched_dam
        ].copy() if not history_reservoir_frame.empty else pd.DataFrame()
        trend_text = "Trend is not available from the selected report window."
        if not dam_history.empty and {"observed_at", "water_level_m"}.issubset(dam_history.columns):
            dam_history["observed_at"] = pd.to_datetime(dam_history["observed_at"], errors="coerce")
            dam_history["water_level_m"] = pd.to_numeric(dam_history["water_level_m"], errors="coerce")
            dam_history = dam_history.dropna(subset=["observed_at", "water_level_m"]).sort_values("observed_at")
            if len(dam_history) >= 2:
                delta = float(dam_history["water_level_m"].iloc[-1] - dam_history["water_level_m"].iloc[0])
                direction = "rising" if delta > 0.05 else "falling" if delta < -0.05 else "stable"
                trend_text = f"Water level trend is {direction} over the selected window ({delta:+.2f} m)."
        text = (
            f"{matched_dam} is currently classified as {latest.get('alert_level', 'Normal')}. "
            f"Filling is {fmt_number(latest.get('display_filling'), '%')}, water level is "
            f"{fmt_number(latest.get('water_level_m'), ' m')}, and FRL gap is {fmt_number(latest.get('frl_gap_m'), ' m')}. "
            f"{trend_text} Recommended DSS action: verify latest field reading, compare gate status and downstream river gauges, and keep district control informed if FRL gap is reducing."
        )
        table = assistant_table(
            dam_rows,
            ["reservoir_name", "dam_name", "map_district", "district", "sub_basin", "water_level_m", "frl_m", "frl_gap_m", "display_filling", "current_live_capacity_mcm", "rainfall_daily_mm", "alert_level"],
            8,
        )
        return {"text": text, "table": table}

    if any(term in query for term in ["brief", "summary", "decision", "dss", "recommend", "priority"]):
        if map_frame.empty:
            return {"text": "No dam map data is available for a DSS brief under the current filters.", "table": pd.DataFrame()}
        critical = int((map_frame.get("alert_level", pd.Series(dtype=str)) == "Critical").sum())
        warning = int((map_frame.get("alert_level", pd.Series(dtype=str)) == "Warning").sum())
        watch = int((map_frame.get("alert_level", pd.Series(dtype=str)) == "Watch").sum())
        avg_fill = pd.to_numeric(map_frame.get("display_filling"), errors="coerce").mean()
        highest = map_frame.sort_values("display_filling", ascending=False).head(5)
        low_gap = map_frame.sort_values("frl_gap_m", na_position="last").head(5)
        text = (
            f"AI DSS brief for {latest_label}: {critical} Critical, {warning} Warning, and {watch} Watch reservoirs are present in the active filter. "
            f"Average mapped filling is {fmt_number(avg_fill, '%')}. Immediate operational priority should focus on low FRL-gap reservoirs, then high-filling reservoirs with rising trend or open gates. "
            "Recommended next actions: validate latest readings, review gate status, check downstream gauges/GEOGLOWS context, and prepare private official alerts for Critical/Warning dams."
        )
        combined = pd.concat([low_gap, highest], ignore_index=True).drop_duplicates(subset=["reservoir_name"], keep="first")
        table = assistant_table(
            combined,
            ["reservoir_name", "map_district", "sub_basin", "water_level_m", "frl_gap_m", "display_filling", "alert_level"],
            10,
        )
        return {"text": text, "table": table}

    if any(term in query for term in ["critical", "warning", "alert", "frl"]):
        if map_frame.empty or "alert_level" not in map_frame:
            return {"text": "No mapped dam alert data is available under the current filters.", "table": pd.DataFrame()}
        alerts = map_frame[map_frame["alert_level"].isin(["Critical", "Warning", "Watch"])].copy()
        critical = int((map_frame["alert_level"] == "Critical").sum())
        warning = int((map_frame["alert_level"] == "Warning").sum())
        watch = int((map_frame["alert_level"] == "Watch").sum())
        text = (
            f"For {latest_label}, the current filtered data shows {critical} Critical, "
            f"{warning} Warning, and {watch} Watch dam alert(s). "
            "Priority should start with Critical and Warning reservoirs, especially where FRL gap is low or the latest water level is rising."
        )
        table = assistant_table(
            alerts.sort_values(["alert_level", "frl_gap_m", "display_filling"], ascending=[True, True, False]),
            ["reservoir_name", "dam_name", "map_district", "district", "sub_basin", "water_level_m", "frl_m", "frl_gap_m", "display_filling", "alert_level"],
            15,
        )
        return {"text": text, "table": table}

    if any(term in query for term in ["district", "where", "area"]):
        if map_frame.empty:
            return {"text": "No district-wise dam data is available under the current filters.", "table": pd.DataFrame()}
        district_col = "map_district" if "map_district" in map_frame else "district"
        if district_col not in map_frame:
            return {"text": "District field is not available in the current dam map data.", "table": pd.DataFrame()}
        district_summary = (
            map_frame.assign(
                alert_flag=map_frame.get("alert_level", pd.Series(dtype=str)).isin(["Critical", "Warning"]),
                district_label=map_frame[district_col].fillna("Unassigned"),
            )
            .groupby("district_label", as_index=False)
            .agg(
                dams=("reservoir_name", "nunique"),
                avg_filling=("display_filling", "mean"),
                max_filling=("display_filling", "max"),
                active_alerts=("alert_flag", "sum"),
            )
            .sort_values(["active_alerts", "max_filling"], ascending=False)
        )
        text = "District-wise attention ranking is based on active Critical/Warning alerts first, then maximum reservoir filling."
        return {"text": text, "table": prettify_dataframe_columns(district_summary.head(15))}

    if any(term in query for term in ["top", "highest", "filled", "full", "75", "90"]):
        if map_frame.empty:
            return {"text": "No reservoir filling data is available under the current filters.", "table": pd.DataFrame()}
        top = map_frame.sort_values("display_filling", ascending=False)
        text = f"These are the highest-filled reservoirs in the current dashboard filter for {latest_label}."
        table = assistant_table(top, ["reservoir_name", "dam_name", "map_district", "water_level_m", "frl_gap_m", "display_filling", "alert_level"], 15)
        return {"text": text, "table": table}

    if any(term in query for term in ["least", "low", "below 25", "below25", "empty"]):
        if map_frame.empty:
            return {"text": "No reservoir filling data is available under the current filters.", "table": pd.DataFrame()}
        low = map_frame[map_frame["display_filling"] < 25].sort_values("display_filling", ascending=True)
        text = f"{len(low)} reservoir(s) are below 25% filling in the current filter."
        table = assistant_table(low, ["reservoir_name", "dam_name", "map_district", "water_level_m", "display_filling", "alert_level"], 15)
        return {"text": text, "table": table}

    if any(term in query for term in ["gate", "gates", "opened", "discharge"]):
        if gate_frame.empty:
            return {"text": "No reservoir gate observations are available under the current filters.", "table": pd.DataFrame()}
        gates = gate_frame.copy()
        gates["gate_opened_count"] = pd.to_numeric(gates.get("gate_opened_count"), errors="coerce").fillna(0)
        open_gates = gates[gates["gate_opened_count"] > 0].sort_values("gate_opened_count", ascending=False)
        total_sites = int(open_gates["reservoir_name"].nunique()) if "reservoir_name" in open_gates else len(open_gates)
        text = f"{total_sites} reservoir gate site(s) currently show opened gates under the selected reports."
        table = assistant_table(open_gates, ["reservoir_name", "district", "gate_opened_count", "total_no_of_gates", "opening_m", "discharge_cumecs", "discharge_cusec", "report_at"], 15)
        return {"text": text, "table": table}

    if any(term in query for term in ["river", "gauge", "station", "danger"]):
        if river_frame.empty:
            return {"text": "No river gauge observations are available under the current filters.", "table": pd.DataFrame()}
        rivers = river_frame.copy()
        if {"water_level_m", "danger_or_max_water_level_m"}.issubset(rivers.columns):
            rivers["danger_gap_m"] = pd.to_numeric(rivers["danger_or_max_water_level_m"], errors="coerce") - pd.to_numeric(rivers["water_level_m"], errors="coerce")
            rivers = rivers.sort_values("danger_gap_m")
        text = "River gauge ranking is shown by lowest gap to danger/max water level where that field is available."
        table = assistant_table(rivers, ["river_name", "gauge_station", "district", "water_level_m", "danger_or_max_water_level_m", "danger_gap_m", "observed_at"], 15)
        return {"text": text, "table": table}

    if any(term in query for term in ["rain", "rainfall", "weather", "forecast"]):
        text = (
            "Weather and rainfall DSS is available in the Weather Forecast page. "
            "For dam operations, compare 24-hour rainfall, 7-day precipitation forecast, wind risk, and active FRL alerts before issuing field advisories."
        )
        rain_table = pd.DataFrame()
        if not reservoir_frame.empty and "rainfall_daily_mm" in reservoir_frame:
            rain = reservoir_frame.copy()
            rain["rainfall_daily_mm"] = pd.to_numeric(rain.get("rainfall_daily_mm"), errors="coerce")
            rain_table = assistant_table(rain.sort_values("rainfall_daily_mm", ascending=False), ["reservoir_name", "district", "rainfall_daily_mm", "rainfall_total_mm", "observed_at"], 12)
        return {"text": text, "table": rain_table}

    if any(term in query for term in ["email", "sms", "whatsapp", "message", "admin", "upload", "pdf"]):
        text = (
            "Administration controls PDF upload, manual data entry, report generation support, and alert messaging. "
            "Email alerts are sent privately per recipient. Online deployments should prefer an HTTPS email API provider such as Brevo, Resend, or SendGrid; local deployments can use SMTP."
        )
        return {"text": text, "table": pd.DataFrame()}

    dam_count = int(map_frame["reservoir_name"].dropna().nunique()) if not map_frame.empty and "reservoir_name" in map_frame else 0
    avg_filling = pd.to_numeric(map_frame.get("display_filling"), errors="coerce").mean() if not map_frame.empty else math.nan
    alert_count = int(map_frame.get("alert_level", pd.Series(dtype=str)).isin(["Critical", "Warning"]).sum()) if not map_frame.empty else 0
    river_count = int(river_frame["gauge_station"].dropna().nunique()) if not river_frame.empty and "gauge_station" in river_frame else 0
    text = (
        f"Current page: {page_name}. For {latest_label}, the selected data covers {dam_count} mapped reservoir(s), "
        f"{river_count} river gauge station(s), average reservoir filling of {fmt_number(avg_filling, '%')}, "
        f"and {alert_count} Critical/Warning dam alert(s). Try asking: 'critical dams', 'district ranking', "
        "'opened gates', 'least filled dams', or 'river gauges near danger level'."
    )
    return {"text": text, "table": pd.DataFrame()}


def render_dashboard_assistant(
    map_status_frame: pd.DataFrame,
    reservoir_frame: pd.DataFrame,
    river_frame: pd.DataFrame,
    gate_frame: pd.DataFrame,
    page_name: str,
    weather_points_frame: pd.DataFrame | None = None,
    historical_reservoir_frame: pd.DataFrame | None = None,
) -> None:
    if "assistant_history" not in st.session_state:
        st.session_state.assistant_history = []
    if "assistant_question" not in st.session_state:
        st.session_state.assistant_question = ""

    with st.expander("AI DSS Assistant: Ask About Current Dashboard Data", expanded=False):
        st.markdown(
            '<div class="panel-note">Enhanced hybrid DSS assistant: operational briefs, dam-name lookup, weather intelligence, and advanced data queries over the loaded historical report data. Try natural questions using district, dam, alert, filling percentage, gate, river, trend, or last-N-days table filters.</div>',
            unsafe_allow_html=True,
        )
        st.caption(local_ai_status_text())
        quick_prompts = [
            "DSS brief",
            "Weather DSS brief",
            "Critical dams",
            "District ranking",
            "Opened gates",
            "Least filled below 25%",
            "River gauges near danger",
            "Rising reservoir trends",
            "Critical dams last 5 days water levels",
        ]
        for start in range(0, len(quick_prompts), 3):
            prompt_cols = st.columns(3)
            for col, prompt in zip(prompt_cols, quick_prompts[start : start + 3]):
                if col.button(prompt, key=f"assistant_quick_{normalize_name(prompt)}", use_container_width=True):
                    answer = dashboard_assistant_answer(
                        prompt,
                        map_status_frame,
                        reservoir_frame,
                        river_frame,
                        gate_frame,
                        page_name,
                        weather_points_frame,
                        historical_reservoir_frame,
                    )
                    answer = local_ai_enhance_answer(prompt, answer)
                    st.session_state.assistant_history.insert(0, {"question": prompt, **answer})

        with st.form("dashboard_assistant_form", clear_on_submit=True):
            question = st.text_input(
                "Ask a question",
                placeholder="Example: Get tables of Critical dams for last 5 days with each day water levels.",
                key="assistant_question_input",
            )
            submitted = st.form_submit_button("Ask Assistant", type="primary", use_container_width=True)
        if submitted and question.strip():
            answer = dashboard_assistant_answer(
                question,
                map_status_frame,
                reservoir_frame,
                river_frame,
                gate_frame,
                page_name,
                weather_points_frame,
                historical_reservoir_frame,
            )
            answer = local_ai_enhance_answer(question.strip(), answer)
            st.session_state.assistant_history.insert(0, {"question": question.strip(), **answer})

        if st.session_state.assistant_history:
            latest = st.session_state.assistant_history[0]
            st.markdown(f"**You asked:** {escape(str(latest.get('question', '')))}")
            st.info(str(latest.get("text", "")))
            if latest.get("ai_status"):
                st.caption(str(latest.get("ai_status")))
            table = latest.get("table")
            if isinstance(table, pd.DataFrame) and not table.empty:
                st.dataframe(table, use_container_width=True, hide_index=True, height=260)
        else:
            overview = dashboard_assistant_answer(
                "",
                map_status_frame,
                reservoir_frame,
                river_frame,
                gate_frame,
                page_name,
                weather_points_frame,
                historical_reservoir_frame,
            )
            st.info(overview["text"])


def reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401

        return True
    except Exception:
        return False


def report_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if abs(number - round(number)) < 0.005:
            return f"{number:.0f}"
        return f"{number:.2f}"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%d %b %Y %I:%M %p")
    text = str(value)
    try:
        numeric = pd.to_numeric(pd.Series([text]), errors="coerce").iloc[0]
        if pd.notna(numeric) and re.fullmatch(r"\s*-?\d+(\.\d+)?\s*", text):
            return report_value(float(numeric))
    except Exception:
        pass
    return text


def report_table(df: pd.DataFrame, max_rows: int = 18, font_size: int = 7):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    if df.empty:
        df = pd.DataFrame({"Message": ["No rows available for the active filters."]})
    display_df = prettify_dataframe_columns(df.head(max_rows).copy())
    rows = [list(display_df.columns)] + [
        [report_value(value)[:42] for value in record]
        for record in display_df.to_numpy().tolist()
    ]
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172033")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dbe6f4")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbff")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def report_bar_chart(df: pd.DataFrame, label_col: str, value_col: str, title: str, width: int = 500, height: int = 180):
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors

    drawing = Drawing(width, height)
    drawing.add(String(0, height - 12, title, fontName="Helvetica-Bold", fontSize=10, fillColor=colors.HexColor("#172033")))
    if df.empty or value_col not in df:
        drawing.add(String(0, height / 2, "No chart data available", fontSize=9, fillColor=colors.HexColor("#64748b")))
        return drawing
    plot = df[[label_col, value_col]].dropna().head(12).copy()
    plot[value_col] = pd.to_numeric(plot[value_col], errors="coerce").fillna(0)
    max_value = max(float(plot[value_col].max()), 1.0)
    bar_h = max(8, min(16, (height - 34) / max(len(plot), 1) - 3))
    y = height - 32
    for idx, row in plot.iterrows():
        value = float(row[value_col])
        bar_w = (width - 185) * value / max_value
        color = COOLORS_ALERT_PALETTE[min(len(COOLORS_ALERT_PALETTE) - 1, int(value / max(max_value, 1) * (len(COOLORS_ALERT_PALETTE) - 1)))]
        drawing.add(String(0, y + 2, str(row[label_col])[:24], fontSize=7, fillColor=colors.HexColor("#334155")))
        drawing.add(Rect(145, y, bar_w, bar_h, fillColor=colors.HexColor(color), strokeColor=None))
        drawing.add(String(150 + bar_w, y + 2, report_value(value), fontSize=7, fillColor=colors.HexColor("#172033")))
        y -= bar_h + 4
    return drawing


def report_map_panel(points: pd.DataFrame, title: str, label_col: str = "reservoir_name", width: int = 500, height: int = 235):
    from io import BytesIO
    from reportlab.graphics.shapes import Circle, Drawing, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image as RLImage

    def fallback_panel():
        drawing = Drawing(width, height)
        drawing.add(String(0, height - 12, title, fontName="Helvetica-Bold", fontSize=10, fillColor=colors.HexColor("#172033")))
        drawing.add(Rect(0, 0, width, height - 20, fillColor=colors.HexColor("#eef7ff"), strokeColor=colors.HexColor("#c8d7ea")))
        if points.empty or not {"latitude", "longitude"}.issubset(points.columns):
            drawing.add(String(18, height / 2, "No coordinate data available", fontSize=9, fillColor=colors.HexColor("#64748b")))
            return drawing
        plot = points.dropna(subset=["latitude", "longitude"]).copy()
        if plot.empty:
            return drawing
        min_lon, max_lon = 73.6, 83.2
        min_lat, max_lat = 20.8, 27.0
        lon_span = max(max_lon - min_lon, 0.1)
        lat_span = max(max_lat - min_lat, 0.1)
        for _, row in plot.head(90).iterrows():
            x = 22 + (float(row["longitude"]) - min_lon) / lon_span * (width - 44)
            y = 18 + (float(row["latitude"]) - min_lat) / lat_span * (height - 58)
            filling = pd.to_numeric(pd.Series([row.get("display_filling", row.get("filling_percent", 0))]), errors="coerce").iloc[0]
            color = "#147df5" if pd.isna(filling) else COOLORS_ALERT_PALETTE[min(len(COOLORS_ALERT_PALETTE) - 1, max(0, int(float(filling) / 100 * (len(COOLORS_ALERT_PALETTE) - 1))))]
            drawing.add(Circle(x, y, 3.2, fillColor=colors.HexColor(color), strokeColor=colors.white, strokeWidth=0.4))
            label = str(row.get(label_col) or row.get("reservoir_name") or row.get("town_name") or "")[:18]
            if label:
                drawing.add(String(x + 4, y + 1, label, fontSize=5.8, fillColor=colors.HexColor("#111827")))
        drawing.add(String(8, 7, f"{len(plot)} mapped points | Static report map from dashboard coordinates", fontSize=7, fillColor=colors.HexColor("#64748b")))
        return drawing

    if points.empty or not {"latitude", "longitude"}.issubset(points.columns):
        return fallback_panel()
    plot = points.dropna(subset=["latitude", "longitude"]).copy()
    if plot.empty:
        return fallback_panel()
    try:
        from PIL import Image, ImageDraw, ImageFont

        zoom = 7
        tile_size = 256
        min_lon, max_lon = 73.6, 83.2
        min_lat, max_lat = 20.8, 27.0

        def lonlat_to_pixels(lon: float, lat: float) -> tuple[float, float]:
            sin_lat = math.sin(math.radians(lat))
            scale = tile_size * (2**zoom)
            x = (lon + 180.0) / 360.0 * scale
            y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
            return x, y

        px_min, py_max = lonlat_to_pixels(min_lon, min_lat)
        px_max, py_min = lonlat_to_pixels(max_lon, max_lat)
        tx_min, tx_max = int(px_min // tile_size), int(px_max // tile_size)
        ty_min, ty_max = int(py_min // tile_size), int(py_max // tile_size)
        mosaic = Image.new("RGB", ((tx_max - tx_min + 1) * tile_size, (ty_max - ty_min + 1) * tile_size), "#edf4fb")
        for tx in range(tx_min, tx_max + 1):
            for ty in range(ty_min, ty_max + 1):
                url = f"https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{zoom}/{ty}/{tx}"
                try:
                    with urllib.request.urlopen(url, timeout=5) as response:
                        tile = Image.open(BytesIO(response.read())).convert("RGB")
                    mosaic.paste(tile, ((tx - tx_min) * tile_size, (ty - ty_min) * tile_size))
                except Exception:
                    pass
        crop_left = int(px_min - tx_min * tile_size)
        crop_top = int(py_min - ty_min * tile_size)
        crop_right = int(px_max - tx_min * tile_size)
        crop_bottom = int(py_max - ty_min * tile_size)
        cropped = mosaic.crop((crop_left, crop_top, crop_right, crop_bottom)).resize((int(width * 2), int((height - 20) * 2)))
        draw = ImageDraw.Draw(cropped, "RGBA")
        font = ImageFont.load_default()
        draw.rectangle([0, 0, cropped.width - 1, cropped.height - 1], outline=(180, 198, 220, 255), width=2)
        for _, row in plot.head(90).iterrows():
            x_raw, y_raw = lonlat_to_pixels(float(row["longitude"]), float(row["latitude"]))
            x = (x_raw - px_min) / max(px_max - px_min, 1) * cropped.width
            y = (y_raw - py_min) / max(py_max - py_min, 1) * cropped.height
            filling = pd.to_numeric(pd.Series([row.get("display_filling", row.get("filling_percent", 0))]), errors="coerce").iloc[0]
            color = "#147df5" if pd.isna(filling) else COOLORS_ALERT_PALETTE[min(len(COOLORS_ALERT_PALETTE) - 1, max(0, int(float(filling) / 100 * (len(COOLORS_ALERT_PALETTE) - 1))))]
            rgb = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
            draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(*rgb, 235), outline=(255, 255, 255, 255), width=2)
            label = str(row.get(label_col) or row.get("reservoir_name") or row.get("town_name") or "")[:18]
            if label:
                text_x, text_y = x + 8, y - 5
                bbox = draw.textbbox((text_x, text_y), label, font=font)
                draw.rectangle([bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1], fill=(255, 255, 255, 205))
                draw.text((text_x, text_y), label, fill=(15, 23, 42, 255), font=font)
        output = BytesIO()
        cropped.save(output, format="PNG")
        output.seek(0)
        flowable = RLImage(output, width=width, height=height - 20)
        return flowable
    except Exception:
        return fallback_panel()


def build_pdf_report(title: str, subtitle: str, sections: list[tuple[str, list]]) -> bytes:
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=32, leftMargin=32, topMargin=36, bottomMargin=32)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#172033"), spaceAfter=8))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor("#2563eb"), spaceBefore=8, spaceAfter=6))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=11, textColor=colors.HexColor("#64748b")))
    cover_table = Table(
        [
            ["NITA AI & GEO-ANALYTICS", "MPWRD VBSR FLOOD SEASON 2026"],
            [Paragraph(title, styles["ReportTitle"]), ""],
            [Paragraph(subtitle, styles["Normal"]), ""],
        ],
        colWidths=[350, 150],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172033")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("SPAN", (0, 1), (-1, 1)),
                ("SPAN", (0, 2), (-1, 2)),
                ("BACKGROUND", (0, 1), (-1, 2), colors.HexColor("#f8fbff")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#dbe6f4")),
                ("LINEBELOW", (0, 0), (-1, 0), 2.0, colors.HexColor("#147df5")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 1), (-1, 1), 12),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 12),
            ]
        ),
    )
    story = [cover_table, Spacer(1, 0.14 * inch)]
    story.append(
        Table(
            [[f"Generated: {pd.Timestamp.now(tz='Asia/Kolkata').strftime('%d %b %Y %I:%M %p')}", "MPWRD VBSR Flood Season 2026"]],
            colWidths=[250, 250],
            style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#edf7ff")), ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbe6f4")), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]),
        )
    )
    story.append(Spacer(1, 0.12 * inch))
    for index, (section_title, flowables) in enumerate(sections):
        if index and section_title.startswith("Appendix"):
            story.append(PageBreak())
        story.append(Paragraph(section_title, styles["SectionTitle"]))
        story.extend(flowables)
        story.append(Spacer(1, 0.1 * inch))

    def add_page_number(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(32, 18, "MPWRD VBSR Dam Water Level Intelligent Dashboard and Analytics")
        canvas.drawRightString(A4[0] - 32, 18, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return buffer.getvalue()


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
        st.info("Administration is locked. Sign in as admin_nitaai to upload PDFs and manage SMS/WhatsApp/email alert messaging.")
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

    admin_tabs = st.tabs(["PDF Upload & Data Refresh", "Manual Data Entry", "Messaging Alerts", "Database Sync", "Audit Log", "Visitor Analytics"])
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

        st.markdown("#### Nita AI River Flow TensorFlow Model")
        tf_status = river_flow_model_status()
        tf_cols = st.columns([0.34, 0.33, 0.33])
        tf_cols[0].metric("TensorFlow Runtime", "Available" if tf_status.get("tensorflow_available") else "Not installed")
        tf_cols[1].metric("Model Artifact", "Loaded" if tf_status.get("model_path") else "Not uploaded")
        tf_cols[2].metric("Model Mode", "TensorFlow" if tf_status.get("ready") else "Fallback ensemble")
        if tf_status.get("model_path"):
            st.success(f"Current model artifact: {tf_status.get('model_path')}")
        else:
            st.caption(f"Expected model folder: {RIVER_FLOW_MODEL_DIR}")
        model_upload_cols = st.columns([0.55, 0.45])
        with model_upload_cols[0]:
            uploaded_model = st.file_uploader(
                "Upload river-flow TensorFlow model",
                type=["keras", "h5", "json"],
                key="admin_river_flow_model_upload",
                help="Upload river_flow_model.keras or river_flow_model.h5. Upload model_metadata.json separately if feature scaling is required.",
            )
            if uploaded_model is not None:
                model_target = save_uploaded_river_flow_model(uploaded_model)
                st.session_state.setdefault("admin_audit_log", []).insert(
                    0,
                    {
                        "time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y %I:%M %p"),
                        "module": "AI Model",
                        "action": f"Uploaded {uploaded_model.name}",
                        "status": f"Saved to {model_target.name}",
                    },
                )
                st.success(f"Saved model file: {model_target.name}. Refresh the page to apply the updated model status.")
        with model_upload_cols[1]:
            st.markdown(
                """
                **Supported files:** `river_flow_model.keras`, `river_flow_model.h5`, `model_metadata.json`.

                **Input features:** water level, danger gap, level trend, GloFAS flow, GRRR flow, and forecast lead day.
                """
            )

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
            '<div class="panel-note">Configure alert thresholds and prepare Email, SMS and WhatsApp messages. Email can send through HTTPS email API providers for online deployments or SMTP for local deployments; SMS/WhatsApp remain preview/link mode until provider gateways are connected.</div>',
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
                value=st.session_state.get("admin_alert_recipients", "NITA GeoAI Sender nitageoai@gmail.com\nNITA GeoAI Alerts info@nitageoai.com\nData Center Head baghel.bijendrakumar@gmail.com\nControl Room +91XXXXXXXXXX\nDam Safety Officer +91XXXXXXXXXX"),
                key="admin_alert_recipients",
                height=86,
                help="One recipient per line. Use role/name with email and/or phone number.",
            )
            admin_email_recipients = extract_email_recipients(recipients_text)
            admin_email_configured = alert_email_is_configured()
            admin_missing_email_settings = alert_email_missing_settings()
            missing_note = "" if admin_email_configured else f" Missing: {', '.join(admin_missing_email_settings)}."
            st.caption(f"Email recipients detected: {len(admin_email_recipients)}. Email delivery is {'configured' if admin_email_configured else 'not configured'}.{missing_note}")

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
                st.caption(f"Prepared for {gateway_mode}. Message length: {len(alert_message)} characters. Email sending requires email API or SMTP secrets; SMS/WhatsApp require provider credentials.")
                if "Email" in selected_channels:
                    email_subject = f"MPWRD Dam Alert: {selected_alert_row.get('reservoir_name')} {selected_alert_row.get('configured_alert')}"
                    email_html = dam_alert_email_html(selected_alert_row, alert_message)
                    st.caption("Email output uses a professional HTML report layout with dam metrics, alert badge, DSS actions and plain-text fallback.")
                    if st.button("Send Test Email Alert", use_container_width=True, key="admin_send_test_email_alert"):
                        if gateway_mode != "Provider ready":
                            st.warning("Switch Gateway mode to Provider ready before sending a real email test.")
                        else:
                            ok, email_status_message = send_alert_email(email_subject, alert_message, admin_email_recipients, email_html)
                            st.session_state.alert_test_log.insert(
                                0,
                                {
                                    "time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y %I:%M %p"),
                                    "channels": "Email",
                                    "mode": gateway_mode,
                                    "reservoir": selected_alert_row.get("reservoir_name"),
                                    "alert": selected_alert_row.get("configured_alert"),
                                    "recipients": len(admin_email_recipients),
                                    "status": email_status_message,
                                },
                            )
                            if ok:
                                st.success(email_status_message)
                            else:
                                st.error(email_status_message)
                if not dispatch_links.empty:
                    link_items = []
                    for index, row in dispatch_links.head(8).iterrows():
                        if row.get("test_link"):
                            label = f"{row.get('channel')} - {row.get('label') or row.get('phone')}"
                            link_items.append(f'<a href="{escape(str(row.get("test_link")))}" target="_blank">{escape(label)}</a>')
                    if link_items:
                        st.markdown("<br/>".join(link_items), unsafe_allow_html=True)

        st.markdown("#### Automated Hourly Alert Dispatch")
        automated_recipients = extract_email_recipients(get_app_secret("alert_email_recipients", "ALERT_EMAIL_RECIPIENTS", ""))
        st.markdown(
            (
                '<div class="panel-note">'
                'The backend hourly dispatcher sends professional dam alert email reports to each official separately, '
                'so recipient email addresses are not disclosed to other officials. Duplicate alerts are suppressed per dam, alert level, observation time and hour.'
                '</div>'
            ),
            unsafe_allow_html=True,
        )
        auto_cols = st.columns(3)
        auto_cols[0].metric("Automated Email Recipients", len(automated_recipients))
        auto_cols[1].metric("Email Delivery", "Configured" if alert_email_is_configured() else "Incomplete")
        auto_cols[2].metric("Interval", "Every 1 hour")
        st.code(
            "& 'D:\\01 Project\\Development\\flood_dashboard\\.venv\\Scripts\\python.exe' "
            "'D:\\01 Project\\Development\\Flood Reports\\hourly_alert_dispatcher.py' --loop",
            language="powershell",
        )
        st.caption("Use Windows Task Scheduler or run the command above as a background process. Add official addresses to Streamlit secret alert_email_recipients.")

    with admin_tabs[3]:
        st.markdown(
            '<div class="panel-note">Persist parsed flood reports into PostgreSQL or MySQL for future repository storage, analytics, APIs, and dashboard acceleration.</div>',
            unsafe_allow_html=True,
        )
        database_url = database_url_config()
        db_cols = st.columns([0.36, 0.64])
        with db_cols[0]:
            st.metric("Database Engine", database_engine_label(database_url))
            st.metric("Parsed Report Folders", len(parsed_reports))
        with db_cols[1]:
            if database_url:
                st.success(f"Database URL configured: {mask_database_url(database_url)}")
            else:
                st.warning("No database is configured yet. Add `database_url` in Streamlit secrets or `DATABASE_URL` in the environment.")
            st.caption("PostgreSQL example: postgresql+psycopg2://user:password@host:5432/mpwrd_flood")
            st.caption("MySQL example: mysql+pymysql://user:password@host:3306/mpwrd_flood")

        st.markdown(
            """
            **Tables created by sync:** `flood_reports`, `reservoir_master`, `river_station_master`,
            `reservoir_observations`, `river_observations`, and `reservoir_gate_observations`.
            Existing records are updated using report/date-time and observation keys, so the sync can be run repeatedly.
            """
        )
        sync_script = APP_DIR / "flood_report_database_sync.py"
        sync_command = f'"{sys.executable}" "{sync_script}" --parsed-root "{APP_DIR}"'
        st.code(sync_command, language="powershell")
        if st.button("Sync Parsed Reports to SQL Database", type="primary", use_container_width=True, key="admin_sync_sql_database"):
            if not database_url:
                st.error("Database sync cannot run until `database_url` or `DATABASE_URL` is configured.")
            elif not sync_script.exists():
                st.error("Database sync script is missing from the app folder.")
            else:
                env = os.environ.copy()
                env["DATABASE_URL"] = database_url
                with st.spinner("Creating/updating SQL tables and syncing parsed flood reports..."):
                    result = subprocess.run(
                        [sys.executable, str(sync_script), "--parsed-root", str(APP_DIR)],
                        cwd=str(APP_DIR),
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=180,
                    )
                if result.returncode == 0:
                    st.success("Database sync completed.")
                    st.code(result.stdout.strip() or "Sync completed.", language="json")
                    st.session_state.setdefault("admin_audit_log", []).insert(
                        0,
                        {
                            "time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y %I:%M %p"),
                            "module": "Database Sync",
                            "action": "Synced parsed reports to SQL database",
                            "status": "Completed",
                        },
                    )
                else:
                    st.error("Database sync failed.")
                    st.code((result.stderr or result.stdout or "Unknown sync error").strip(), language="text")

    with admin_tabs[4]:
        st.markdown('<div class="panel-note">Local administration actions recorded during this browser session.</div>', unsafe_allow_html=True)
        audit_log = pd.DataFrame(st.session_state.get("admin_audit_log", []))
        alert_log = pd.DataFrame(st.session_state.get("alert_test_log", []))
        if not audit_log.empty:
            st.dataframe(audit_log, use_container_width=True, hide_index=True, height=180)
        if not alert_log.empty:
            st.dataframe(alert_log, use_container_width=True, hide_index=True, height=220)
        if audit_log.empty and alert_log.empty:
            st.info("No administration actions have been recorded in this session.")

    with admin_tabs[5]:
        render_visitor_analytics_admin()


if "main_dashboard_page" not in st.session_state:
    st.session_state.main_dashboard_page = "Infographics"

nav_pages = ["Infographics", "Dam DSS & Analytics", "GD Site Analytics", "Weather Forecast", "3D Flood Scenarios", "Data & Timeseries", "Report Generation", "Administration"]
st.markdown('<div class="dashboard-topnav-title">Dashboard Navigation</div>', unsafe_allow_html=True)
nav_cols = st.columns(len(nav_pages))
for nav_col, page in zip(nav_cols, nav_pages):
    if nav_col.button(page, key=f"main_nav_{page}", type="primary" if page == st.session_state.main_dashboard_page else "secondary", use_container_width=True):
        st.session_state.main_dashboard_page = page
        st.rerun()
main_page = st.session_state.main_dashboard_page
st.markdown(f'<div class="dashboard-topnav-active">Active page: <b>{escape(main_page)}</b></div>', unsafe_allow_html=True)

assistant_weather_frames = []
assistant_dam_weather = weather_points_from_dams(map_status)
if not assistant_dam_weather.empty:
    assistant_weather_frames.append(
        assistant_dam_weather.assign(point_type="Dam", point_name=assistant_dam_weather["town_name"])
        [["point_type", "point_name", "district", "latitude", "longitude"]]
    )
assistant_towns_master = read_csv(MP_TOWNS_CSV)
if not assistant_towns_master.empty:
    assistant_towns_master["latitude"] = pd.to_numeric(assistant_towns_master.get("latitude"), errors="coerce")
    assistant_towns_master["longitude"] = pd.to_numeric(assistant_towns_master.get("longitude"), errors="coerce")
    assistant_towns_master = assistant_towns_master.dropna(subset=["latitude", "longitude"])
    if {"town_name", "district"}.issubset(assistant_towns_master.columns):
        assistant_weather_frames.append(
            assistant_towns_master.assign(point_type="Town", point_name=assistant_towns_master["town_name"])
            [["point_type", "point_name", "district", "latitude", "longitude"]]
        )
assistant_district_weather = weather_points_from_districts(map_status, assistant_towns_master)
if not assistant_district_weather.empty:
    assistant_weather_frames.append(
        assistant_district_weather.assign(point_type="District", point_name=assistant_district_weather["town_name"])
        [["point_type", "point_name", "district", "latitude", "longitude"]]
    )
assistant_weather_points = (
    pd.concat(assistant_weather_frames, ignore_index=True).drop_duplicates(["point_type", "point_name", "district"])
    if assistant_weather_frames
    else pd.DataFrame(columns=["point_type", "point_name", "district", "latitude", "longitude"])
)
render_dashboard_assistant(map_status, reservoir_view, river_view, gate_view_all, main_page, assistant_weather_points, reservoirs)

if main_page == "Administration":
    render_admin_operations(is_admin, map_status, dirs)

if main_page == "Report Generation":
    st.subheader("Report Generation")
    if not reportlab_available():
        st.error("ReportLab is not installed. Install reportlab to enable professional PDF report generation.")
    else:
        st.markdown(
            '<div class="panel-note">Generate professional PDF reports from the active dashboard filters. Reports include static report maps, charts, and concise tables for briefings and record keeping.</div>',
            unsafe_allow_html=True,
        )
        latest_label_for_report = time_label(latest_reservoirs["observed_at"].dropna().max()) if not latest_reservoirs.empty else "Current filter"
        report_cols = st.columns(4)

        snapshot_kpis = pd.DataFrame(
            [
                {"Metric": "Latest Slot", "Value": latest_label_for_report},
                {"Metric": "Monitored Dams", "Value": int(map_status["reservoir_name"].dropna().nunique()) if not map_status.empty and "reservoir_name" in map_status else 0},
                {"Metric": "Average Filling", "Value": fmt_number(pd.to_numeric(latest_reservoirs.get("filling_percent"), errors="coerce").mean() if not latest_reservoirs.empty else math.nan, "%")},
                {"Metric": "Live Storage", "Value": fmt_number(pd.to_numeric(latest_reservoirs.get("current_live_capacity_mcm"), errors="coerce").sum() if not latest_reservoirs.empty else math.nan, " MCM")},
            ]
        )
        latest_fill = latest_reservoirs.assign(
            filling_percent=pd.to_numeric(latest_reservoirs.get("filling_percent"), errors="coerce")
        ).dropna(subset=["filling_percent"]) if not latest_reservoirs.empty else pd.DataFrame()
        top_fill = latest_fill.nlargest(12, "filling_percent") if not latest_fill.empty else pd.DataFrame()
        low_fill = latest_fill[latest_fill["filling_percent"] < 25].nsmallest(12, "filling_percent") if not latest_fill.empty else pd.DataFrame()
        district_fill = (
            latest_fill.assign(district_label=latest_fill["district"].fillna("Unassigned"))
            .groupby("district_label", as_index=False)
            .agg(reservoirs=("reservoir_name", "nunique"), avg_filling=("filling_percent", "mean"), max_filling=("filling_percent", "max"))
            .sort_values("avg_filling", ascending=False)
            .head(15)
        ) if not latest_fill.empty else pd.DataFrame()

        with report_cols[0]:
            infographic_pdf = build_pdf_report(
                "Infographics Report",
                "Snapshot report with maps, filling bands, top/least reservoirs and key tables.",
                [
                    ("Executive Snapshot", [report_table(snapshot_kpis, max_rows=8, font_size=8)]),
                    ("Dam Location Report Map", [report_map_panel(map_status, "Mapped Dam Locations and Filling Status")]),
                    ("District Reservoir Filling Snapshot", [report_bar_chart(district_fill, "district_label", "avg_filling", "Average Filling by District")]),
                    ("Top Filled Reservoirs", [report_bar_chart(top_fill, "reservoir_name", "filling_percent", "Top Filled Reservoirs")]),
                    ("Least Filled Reservoirs Below 25%", [report_bar_chart(low_fill, "reservoir_name", "filling_percent", "Least Filled Reservoirs Below 25%")]),
                    ("Reservoir Detail Table", [report_table(latest_fill[["reservoir_name", "district", "water_level_m", "frl_gap_m", "current_live_capacity_mcm", "filling_percent"]] if not latest_fill.empty else latest_fill, max_rows=30, font_size=6)]),
                ],
            )
            st.download_button("Download Infographics Report", infographic_pdf, "mpwrd_infographics_report.pdf", "application/pdf", use_container_width=True)

        with report_cols[1]:
            dss_alerts = map_status[map_status.get("alert_level", pd.Series(dtype=str)).isin(["Critical", "Warning", "Watch"])].copy() if not map_status.empty else pd.DataFrame()
            dss_pdf = build_pdf_report(
                "Dam DSS & Analytics Report",
                "Dam DSS report with alert status, map context, reservoir filling and operational ranking.",
                [
                    ("Dam DSS Map", [report_map_panel(map_status, "Dam DSS and FRL Alert Map")]),
                    ("Active Dam Alerts", [report_table(dss_alerts[["reservoir_name", "map_district", "sub_basin", "water_level_m", "frl_gap_m", "display_filling", "alert_level"]] if not dss_alerts.empty else dss_alerts, max_rows=30, font_size=6)]),
                    ("Reservoir Filling Ranking", [report_bar_chart(map_status.sort_values("display_filling", ascending=False) if not map_status.empty else map_status, "reservoir_name", "display_filling", "Latest Reservoir Filling Ranking")]),
                    ("DSS Data Table", [report_table(map_status[["reservoir_name", "dam_name", "map_district", "sub_basin", "water_level_m", "frl_gap_m", "display_filling", "alert_level"]] if not map_status.empty else map_status, max_rows=35, font_size=6)]),
                ],
            )
            st.download_button("Download Dam DSS Report", dss_pdf, "mpwrd_dam_dss_analytics_report.pdf", "application/pdf", use_container_width=True)

        with report_cols[2]:
            towns_report = read_csv(MP_TOWNS_CSV)
            if not towns_report.empty:
                towns_report["latitude"] = pd.to_numeric(towns_report["latitude"], errors="coerce")
                towns_report["longitude"] = pd.to_numeric(towns_report["longitude"], errors="coerce")
            if st.button("Prepare Weather Report", use_container_width=True, key="prepare_weather_pdf_report"):
                if towns_report.empty:
                    st.warning("No town master data is available for the weather report.")
                else:
                    towns_key = tuple(
                        (str(row.town_name), str(row.district), float(row.latitude), float(row.longitude))
                        for row in towns_report.dropna(subset=["latitude", "longitude"]).itertuples(index=False)
                    )
                    with st.spinner(f"Fetching current weather for {len(towns_key)} towns..."):
                        weather_current = build_current_weather_for_towns(towns_key)
                    weather_pdf = build_pdf_report(
                        "Weather Forecast Town Report",
                        "Town-wise weather DSS report with current conditions, town map and forecast-risk indicators.",
                        [
                            ("Town Weather Map", [report_map_panel(towns_report.rename(columns={"town_name": "reservoir_name"}) if not towns_report.empty else towns_report, "Configured MP Weather Town Points", label_col="town_name")]),
                            ("Current Weather Conditions for Towns", [report_table(weather_current[["town_name", "district", "temperature_c", "feels_like_c", "humidity_percent", "precipitation_mm", "cloud_cover_percent", "wind_speed_kmh", "wind_gusts_kmh", "weather_risk", "status"]], max_rows=45, font_size=5)]),
                            ("Weather Risk Ranking", [report_bar_chart(weather_current.assign(risk_score=weather_current["weather_risk"].map({"Unavailable": 0, "Low": 1, "Moderate": 2, "High": 3, "Severe": 4}).fillna(0)).sort_values("risk_score", ascending=False), "town_name", "risk_score", "Town Weather Risk Score")]),
                        ],
                    )
                    st.session_state.weather_pdf_report = weather_pdf
                    st.session_state.weather_pdf_rows = len(weather_current)
            if "weather_pdf_report" in st.session_state:
                st.download_button("Download Weather Report", st.session_state.weather_pdf_report, "mpwrd_weather_town_report.pdf", "application/pdf", use_container_width=True)
                st.caption(f"Prepared current weather report for {st.session_state.get('weather_pdf_rows', 0)} towns.")

        with report_cols[3]:
            season_summary = (
                reservoir_view.assign(
                    observed_at=pd.to_datetime(reservoir_view["observed_at"], errors="coerce"),
                    filling_percent=pd.to_numeric(reservoir_view["filling_percent"], errors="coerce"),
                    current_live_capacity_mcm=pd.to_numeric(reservoir_view["current_live_capacity_mcm"], errors="coerce"),
                )
                .groupby("observed_at", as_index=False)
                .agg(reservoirs=("reservoir_name", "nunique"), avg_filling=("filling_percent", "mean"), total_storage_mcm=("current_live_capacity_mcm", "sum"))
                .dropna(subset=["observed_at"])
            ) if not reservoir_view.empty else pd.DataFrame()
            season_pdf = build_pdf_report(
                "Monsoon Season PDF-Template Data Report",
                "Season report organized from the MP WRD PDF report template with reservoir, river and gate observations.",
                [
                    ("Season Timeline", [report_bar_chart(season_summary, "observed_at", "avg_filling", "Average Reservoir Filling by Observation Slot")]),
                    ("Reservoir Observations", [report_table(reservoir_view.sort_values(["observed_at", "reservoir_name"]) if not reservoir_view.empty else reservoir_view, max_rows=45, font_size=5)]),
                    ("River Gauge Observations", [report_table(river_view.sort_values(["observed_at", "river_name", "gauge_station"]) if not river_view.empty else river_view, max_rows=35, font_size=6)]),
                    ("Gate Operations", [report_table(gate_view_all.sort_values(["report_at", "reservoir_name"]) if not gate_view_all.empty and "report_at" in gate_view_all else gate_view_all, max_rows=35, font_size=6)]),
                ],
            )
            st.download_button("Download Season Data Report", season_pdf, "mpwrd_monsoon_season_data_report.pdf", "application/pdf", use_container_width=True)

if main_page == "GD Site Analytics":
    render_gd_site_analytics(map_status, reservoir_view)

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
                '<div class="panel-note">Configure operational thresholds and prepare SMS, WhatsApp and email alert messages. SMS/WhatsApp stay in preview mode until provider gateways are connected; email can send when HTTPS email API or SMTP secrets are configured.</div>',
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
                    ["SMS", "WhatsApp", "Email"],
                    default=st.session_state.get("alert_channels", ["SMS", "WhatsApp", "Email"]),
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
                    value=st.session_state.get("alert_recipients", "NITA GeoAI Sender nitageoai@gmail.com\nNITA GeoAI Alerts info@nitageoai.com\nData Center Head baghel.bijendrakumar@gmail.com\nControl Room +91XXXXXXXXXX\nDam Safety Officer +91XXXXXXXXXX"),
                    key="alert_recipients",
                    height=86,
                    help="One recipient per line. Use role/name with phone number and/or email address. SMS/WhatsApp require an approved gateway; Email requires email API or SMTP secrets.",
                )
                email_recipients = extract_email_recipients(recipients_text)
                email_configured = alert_email_is_configured()
                email_status = "configured" if email_configured else "not configured"
                missing_email_settings = alert_email_missing_settings()
                missing_note = "" if email_configured else f" Missing: {', '.join(missing_email_settings)}."
                st.caption(f"Email recipients detected: {len(email_recipients)}. Email delivery is {email_status}.{missing_note}")

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
                    "SMS / WhatsApp / Email alert message preview",
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
                    st.caption("SMS/WhatsApp delivery will be enabled after gateway credentials, approved WhatsApp templates, and recipient governance are configured. Email delivery works when email API or SMTP secrets are configured.")
                    if "Email" in selected_channels:
                        email_subject = f"MPWRD Dam Alert: {selected_alert_row.get('reservoir_name')} {selected_alert_row.get('configured_alert')}"
                        st.caption("Email output uses a professional HTML report layout with dam metrics, alert badge, DSS actions and plain-text fallback.")
                        if st.button("Send Test Email Alert", use_container_width=True, key="send_test_email_alert"):
                            if gateway_mode != "Provider ready":
                                st.warning("Switch Gateway mode to Provider ready before sending a real email test.")
                            else:
                                email_html = dam_alert_email_html(selected_alert_row, alert_message)
                                ok, email_status_message = send_alert_email(email_subject, alert_message, email_recipients, email_html)
                                st.session_state.alert_test_log.insert(
                                    0,
                                    {
                                        "time": pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y %I:%M %p"),
                                        "channels": "Email",
                                        "mode": gateway_mode,
                                        "reservoir": selected_alert_row.get("reservoir_name"),
                                        "alert": selected_alert_row.get("configured_alert"),
                                        "recipients": len(email_recipients),
                                        "status": email_status_message,
                                    },
                                )
                                if ok:
                                    st.success(email_status_message)
                                else:
                                    st.error(email_status_message)

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

        st.subheader("Nita AI TensorFlow River Flow DSS")
        st.markdown(
            '<div class="panel-note">Model-ready river discharge forecasting for MP river gauge sites. The panel integrates current gauge water levels with linked river and basin forecast context and stores generated forecasts in the application database for future analytics.</div>',
            unsafe_allow_html=True,
        )
        flow_forecasts, flow_model_status = build_nita_ai_river_flow_forecasts(
            river_view,
            glofas_nodes if "glofas_nodes" in locals() else [],
            grrr_nodes if "grrr_nodes" in locals() else [],
            forecast_days=7,
        )
        model_ready = bool(flow_model_status.get("ready"))
        model_status_cols = st.columns(4)
        model_status_cols[0].metric("Gauge Sites", int(flow_forecasts["gauge_station"].nunique()) if not flow_forecasts.empty and "gauge_station" in flow_forecasts else 0)
        model_status_cols[1].metric("Forecast Rows", len(flow_forecasts))
        model_status_cols[2].metric("TensorFlow", "Ready" if model_ready else "Pending")
        model_status_cols[3].metric("Forecast Lead", "7 days")
        if model_ready:
            st.success(f"TensorFlow model loaded from {flow_model_status.get('model_path')}")
        else:
            st.markdown(
                (
                    '<div class="panel-note">'
                    '<b>Model-ready mode:</b> Nita AI is generating river-flow guidance from the fallback ensemble until the trained TensorFlow artifact is uploaded by administration. '
                    f'Upload <code>river_flow_model.keras</code> or <code>river_flow_model.h5</code> from Administration, or place it in <code>{escape(str(RIVER_FLOW_MODEL_DIR))}</code>.'
                    '</div>'
                ),
                unsafe_allow_html=True,
            )

        if flow_forecasts.empty:
            st.warning("No river gauge observations are available under the current filters for river-flow prediction.")
        else:
            risk_order = {"Danger": 0, "Flood": 1, "Watch": 2, "Normal": 3}
            flow_forecasts = flow_forecasts.sort_values(
                by=["risk_band", "predicted_discharge_cumecs"],
                key=lambda series: series.map(risk_order).fillna(4) if series.name == "risk_band" else series,
                ascending=[True, False],
            )
            top_flow = flow_forecasts.dropna(subset=["predicted_discharge_cumecs"]).sort_values("predicted_discharge_cumecs", ascending=False).head(12)
            flow_left, flow_right = st.columns([1.25, 0.75])
            with flow_left:
                flow_chart = (
                    alt.Chart(top_flow)
                    .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                    .encode(
                        x=alt.X("predicted_discharge_cumecs:Q", title="Predicted discharge (cumecs)"),
                        y=alt.Y("gauge_station:N", sort="-x", title="Gauge station"),
                        color=alt.Color(
                            "risk_band:N",
                            title="AI risk",
                            scale=alt.Scale(domain=["Normal", "Watch", "Flood", "Danger"], range=["#147df5", "#ffd300", "#ff8700", "#ff0000"]),
                        ),
                        tooltip=["river_name", "gauge_station", "district", "forecast_time", "predicted_discharge_cumecs", "glofas_flow_cms", "grrr_flow_cms", "risk_band"],
                    )
                    .properties(height=320)
                )
                st.altair_chart(flow_chart, use_container_width=True)
            with flow_right:
                gauge_labels = [
                    f"{row.gauge_station} | {row.river_name} | {row.district}"
                    for row in flow_forecasts.drop_duplicates(["gauge_station", "river_name", "district"]).itertuples(index=False)
                ]
                selected_flow_label = st.selectbox("AI forecast gauge", gauge_labels, key="nita_ai_flow_gauge") if gauge_labels else ""
                if selected_flow_label:
                    selected_station = selected_flow_label.split(" | ")[0]
                    station_rows = flow_forecasts[flow_forecasts["gauge_station"].astype(str) == selected_station].copy()
                    station_rows["forecast_time"] = pd.to_datetime(station_rows["forecast_time"], errors="coerce")
                    station_chart = (
                        alt.Chart(station_rows)
                        .mark_line(point=True, strokeWidth=3)
                        .encode(
                            x=alt.X("forecast_time:T", title="Forecast date"),
                            y=alt.Y("predicted_discharge_cumecs:Q", title="Predicted discharge (cumecs)"),
                            color=alt.Color("risk_band:N", legend=None, scale=alt.Scale(domain=["Normal", "Watch", "Flood", "Danger"], range=["#147df5", "#ffd300", "#ff8700", "#ff0000"])),
                            tooltip=["forecast_time", "lead_day", "predicted_discharge_cumecs", "risk_band", "prediction_confidence"],
                        )
                        .properties(height=180)
                    )
                    st.altair_chart(station_chart, use_container_width=True)
                    latest_station = station_rows.sort_values("lead_day").iloc[0]
                    st.markdown(
                        f"""
                        <div class="selected-dam-panel">
                            <span class="district-gauge-title">{escape(str(latest_station.get('gauge_station')))}</span>
                            <span class="district-gauge-meta">River: {escape(str(latest_station.get('river_name')))} | District: {escape(str(latest_station.get('district')))}</span>
                            <span class="district-gauge-meta">Current WL: {fmt_number(latest_station.get('water_level_m'), ' m')} | Danger gap: {fmt_number(latest_station.get('danger_gap_m'), ' m')}</span>
                            <span class="district-gauge-meta">Basin Forecast: {fmt_number(latest_station.get('glofas_flow_cms'), ' cumecs')} | River Forecast: {fmt_number(latest_station.get('grrr_flow_cms'), ' cumecs')}</span>
                            <span class="district-gauge-meta">Model: {escape(str(latest_station.get('source_model')))} | Confidence {fmt_number(float(latest_station.get('prediction_confidence') or 0) * 100, '%')}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            action_cols = st.columns([0.24, 0.76])
            with action_cols[0]:
                if st.button("Save AI Flow Forecasts", type="primary", use_container_width=True, key="save_ai_flow_forecasts"):
                    saved_rows = save_river_flow_forecasts(flow_forecasts)
                    st.success(f"Saved {saved_rows} river-flow forecast rows to {RIVER_FLOW_FORECAST_DB.name}.")
            with action_cols[1]:
                st.caption("Saved rows use one record per gauge, forecast date, and model source. These can later be synced to PostgreSQL/MySQL through the database sync layer.")
            table_cols = [
                "river_name",
                "gauge_station",
                "district",
                "observed_at",
                "forecast_time",
                "lead_day",
                "water_level_m",
                "danger_gap_m",
                "glofas_flow_cms",
                "grrr_flow_cms",
                "predicted_discharge_cumecs",
                "risk_band",
                "source_model",
                "prediction_confidence",
            ]
            st.dataframe(flow_forecasts[[col for col in table_cols if col in flow_forecasts.columns]], use_container_width=True, hide_index=True, height=260)


if main_page == "Weather Forecast":
    st.subheader("Weather Forecast")
    meteo_base = open_meteo_base_url()
    st.markdown(
        f"""
        <div class="panel-note">
            Weather Data supports town, dam, and district-level decision support using forecast, current condition, and recent weather context.
            A hosted or self-managed meteorological backend can be configured for operational deployments.
        </div>
        """,
        unsafe_allow_html=True,
    )
    towns_master = read_csv(MP_TOWNS_CSV)
    if not towns_master.empty:
        towns_master["latitude"] = pd.to_numeric(towns_master["latitude"], errors="coerce")
        towns_master["longitude"] = pd.to_numeric(towns_master["longitude"], errors="coerce")
        towns_master = towns_master.dropna(subset=["latitude", "longitude"]).sort_values(["district", "town_name"]).reset_index(drop=True)
    dam_weather_source = map_status if not map_status.empty else dam_locations
    dam_weather_points = weather_points_from_dams(dam_weather_source)
    district_weather_points = weather_points_from_districts(dam_weather_source, towns_master)
    weather_point_sets = {
        "Towns": towns_master,
        "Dams": dam_weather_points,
        "Districts": district_weather_points,
    }
    available_weather_sets = [label for label, frame in weather_point_sets.items() if not frame.empty]
    if not available_weather_sets:
        st.info("No weather point master data is available. Add towns, dam locations, or district centroids to enable weather forecasting.")
    else:
        weather_top = st.columns([0.25, 0.32, 0.43])
        with weather_top[0]:
            selected_weather_set = st.selectbox("Weather coverage", available_weather_sets, key="weather_point_set")
        weather_points = weather_point_sets[selected_weather_set].copy()
        dam_layer_weather = dam_weather_points.copy()
        if not dam_weather_points.empty:
            dam_layer_controls = st.columns([0.32, 0.68])
            with dam_layer_controls[0]:
                if st.button("Load all dam forecasts", use_container_width=True, key="load_all_dam_weather_button"):
                    st.session_state["load_all_dam_weather"] = True
            with dam_layer_controls[1]:
                st.caption(
                    "Dam weather layer is visible on the map. Load all dam forecasts to color every dam by 7-day weather risk and view the dam-wise forecast table."
                )
            if st.session_state.get("load_all_dam_weather"):
                dam_points_key = tuple(
                    (
                        str(row.town_name),
                        str(row.district),
                        round(float(row.latitude), 5),
                        round(float(row.longitude), 5),
                    )
                    for row in dam_weather_points.dropna(subset=["latitude", "longitude"]).itertuples(index=False)
                )
                with st.spinner("Fetching cached weather forecasts for dam locations..."):
                    dam_layer_weather = build_weather_forecast_for_points(dam_points_key)
        with weather_top[1]:
            district_filter_options = ["All districts"] + sorted(weather_points["district"].dropna().astype(str).unique())
            selected_weather_district = st.selectbox("Weather district", district_filter_options, key="weather_district_filter")
        town_options_df = weather_points if selected_weather_district == "All districts" else weather_points[weather_points["district"].astype(str) == selected_weather_district]
        town_labels = [
            f"{row.town_name} | {row.district}"
            for row in town_options_df.itertuples(index=False)
        ]
        if not town_labels:
            st.warning(f"No {selected_weather_set.lower()} are available for the selected district.")
        else:
            with weather_top[2]:
                selected_town_label = st.selectbox(f"{selected_weather_set[:-1] if selected_weather_set.endswith('s') else selected_weather_set} weather point", town_labels, key="selected_weather_town")
            selected_town_name = selected_town_label.split(" | ", 1)[0]
            selected_town = town_options_df[town_options_df["town_name"] == selected_town_name].iloc[0]
            cache_summary = get_weather_cache_summary()
            latest_refresh = cache_summary.get("latest_refresh") or "No stored weather data yet"
            st.caption(
                f"Weather backend database: {cache_summary.get('forecast_locations', 0)} forecast locations and "
                f"{cache_summary.get('current_locations', 0)} current-condition locations stored. "
                f"Automatic refresh interval: {WEATHER_REFRESH_HOURS} hours. Latest refresh: {latest_refresh}."
            )
            force_weather_refresh = False
            if is_admin:
                force_weather_refresh = st.button("Refresh selected weather point now", use_container_width=True, key="refresh_selected_weather_now")
            daily_weather, hourly_weather, current_weather, weather_error, weather_source = get_cached_open_meteo_weather(
                float(selected_town["latitude"]),
                float(selected_town["longitude"]),
                force_refresh=force_weather_refresh,
            )
            st.caption(f"Selected {selected_weather_set.lower()} weather source: {weather_source}.")
            google_weather_api_key = get_app_secret("google_weather_api_key", "GOOGLE_WEATHER_API_KEY", "")
            if is_admin:
                with st.expander("Google Weather API demo check", expanded=False):
                    if not google_weather_api_key:
                        st.info("Configure Streamlit secret google_weather_api_key or environment variable GOOGLE_WEATHER_API_KEY to test Google Weather API for the selected point.")
                    else:
                        st.caption("Runs a current-condition lookup for the selected weather point without displaying the configured API key.")
                        if st.button("Test Google Weather API for selected point", use_container_width=True, key="test_google_weather_api"):
                            google_payload, google_error = fetch_google_weather_current(
                                float(selected_town["latitude"]),
                                float(selected_town["longitude"]),
                                google_weather_api_key,
                            )
                            if google_error:
                                st.error(google_error)
                            else:
                                st.success("Google Weather API responded successfully for the selected point.")
                                st.dataframe(
                                    pd.DataFrame([google_weather_summary(google_payload)]),
                                    use_container_width=True,
                                    hide_index=True,
                                )
            if weather_error and daily_weather.empty:
                st.error(weather_error)
            elif daily_weather.empty:
                st.warning("Weather service returned no daily weather rows for the selected town.")
            else:
                if weather_error:
                    st.warning(weather_error)
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

                summary_towns = weather_points.copy()
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
                if not dam_layer_weather.empty and not st.session_state.get("load_all_dam_weather"):
                    selected_dam_mask = dam_layer_weather["town_name"].astype(str) == selected_town_name
                    if selected_weather_set == "Dams" and selected_dam_mask.any():
                        dam_layer_weather.loc[selected_dam_mask, "forecast_rain_mm"] = forecast_rain_total
                        dam_layer_weather.loc[selected_dam_mask, "forecast_temp_max_c"] = forecast_temp_max
                        dam_layer_weather.loc[selected_dam_mask, "forecast_wind_max_kmh"] = forecast_wind_max
                        dam_layer_weather.loc[selected_dam_mask, "forecast_uv_max"] = forecast_uv_max
                        dam_layer_weather.loc[selected_dam_mask, "weather_risk"] = selected_weather_risk
                        dam_layer_weather.loc[selected_dam_mask, "source"] = weather_source

                st.markdown(
                    f"""
                    <div class="infographic-frame">
                        <div class="infographic-title">Weather Data: {escape(str(selected_town['town_name']))}</div>
                        <div class="infographic-subtitle">{escape(selected_weather_set)} coverage | 7-day forecast and 3-month hindcast in SI units. Location: {float(selected_town['latitude']):.4f}, {float(selected_town['longitude']):.4f} | District: {escape(str(selected_town['district']))}</div>
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
                    f"Weather Forecast Map: MP {selected_weather_set}",
                    dam_layer_weather,
                )

                if st.session_state.get("load_all_dam_weather") and not dam_layer_weather.empty:
                    dam_forecast_display = dam_layer_weather[
                        [
                            "town_name",
                            "district",
                            "forecast_rain_mm",
                            "forecast_temp_max_c",
                            "forecast_wind_max_kmh",
                            "forecast_uv_max",
                            "current_rain_mm",
                            "current_temp_c",
                            "weather_risk",
                            "status",
                        ]
                    ].sort_values(["weather_risk", "forecast_rain_mm", "town_name"], ascending=[True, False, True])
                    st.markdown("**Dam-wise Weather Forecast Layer**")
                    st.dataframe(dam_forecast_display, use_container_width=True, hide_index=True, height=260)

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

        alert_summary = pd.DataFrame(
            [
                {"alert_level": "Critical", "reservoirs": infographic_alert_counts.get("Critical", 0), "color": "#ef4444"},
                {"alert_level": "Warning", "reservoirs": infographic_alert_counts.get("Warning", 0), "color": "#f59e0b"},
                {"alert_level": "Watch", "reservoirs": infographic_alert_counts.get("Watch", 0), "color": "#eab308"},
                {"alert_level": "Normal", "reservoirs": infographic_alert_counts.get("Normal", 0), "color": "#2563eb"},
            ]
        )

        map_chart_cols = st.columns([0.68, 0.32])
        with map_chart_cols[0]:
            infographic_map = pd.DataFrame()
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
        with map_chart_cols[1]:
            alert_chart = (
                alt.Chart(alert_summary)
                .mark_arc(innerRadius=82, outerRadius=144)
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
                .properties(height=375, title="FRL Alert Composition")
            )
            st.altair_chart(alert_chart, use_container_width=True)

        focus_source = infographic_map if "infographic_map" in locals() and not infographic_map.empty else map_status
        if not focus_source.empty and "reservoir_name" in focus_source:
            focus_options = sorted(focus_source["reservoir_name"].dropna().astype(str).unique())
            if focus_options:
                focus_default = focus_options[0]
                if "display_filling" in focus_source:
                    top_focus = focus_source.assign(
                        display_filling=pd.to_numeric(focus_source["display_filling"], errors="coerce")
                    ).sort_values("display_filling", ascending=False)
                    if not top_focus.empty:
                        focus_default = str(top_focus.iloc[0].get("reservoir_name") or focus_default)
                focus_index = focus_options.index(focus_default) if focus_default in focus_options else 0
                selected_focus_dam = st.selectbox(
                    "Infographic Focus Dam",
                    focus_options,
                    index=focus_index,
                    key="infographic_focus_dam",
                    help="Use this selector to link all Python-side infographic cards and charts to one dam. Map clicks update the in-map linked panel instantly.",
                )
                focus_rows = focus_source[focus_source["reservoir_name"].astype(str) == selected_focus_dam].copy()
                focus_latest = focus_rows.iloc[0] if not focus_rows.empty else pd.Series(dtype=object)
                focus_history = reservoir_view[
                    reservoir_view.get("reservoir_name", pd.Series(dtype=str)).astype(str) == selected_focus_dam
                ].copy() if not reservoir_view.empty else pd.DataFrame()
                if not focus_history.empty:
                    focus_history["observed_at"] = pd.to_datetime(focus_history["observed_at"], errors="coerce")
                    focus_history["water_level_m"] = pd.to_numeric(focus_history["water_level_m"], errors="coerce")
                    focus_history["filling_percent"] = pd.to_numeric(focus_history["filling_percent"], errors="coerce")
                    focus_history = focus_history.dropna(subset=["observed_at"]).sort_values("observed_at")

                focus_cols = st.columns([0.42, 0.58])
                with focus_cols[0]:
                    focus_alert = str(focus_latest.get("alert_level") or "Normal")
                    focus_color = {
                        "Critical": "#ef4444",
                        "Warning": "#f59e0b",
                        "Watch": "#eab308",
                        "Normal": "#2563eb",
                    }.get(focus_alert, "#2563eb")
                    st.markdown(
                        f"""
                        <div class="infographic-frame" style="border-left:5px solid {focus_color};padding:.8rem">
                            <div class="infographic-title" style="font-size:1rem">{escape(selected_focus_dam)} Focus</div>
                            <div class="infographic-grid" style="grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem">
                                <div class="infographic-card"><span>District</span><b>{escape(str(focus_latest.get("district_label") or focus_latest.get("map_district") or focus_latest.get("district") or "-"))}</b><small>administrative context</small></div>
                                <div class="infographic-card"><span>Alert</span><b style="color:{focus_color}">{escape(focus_alert)}</b><small>FRL/filling status</small></div>
                                <div class="infographic-card"><span>Filling</span><b>{fmt_number(focus_latest.get("display_filling"), "%")}</b><small>latest selected slot</small></div>
                                <div class="infographic-card"><span>FRL Gap</span><b>{fmt_number(focus_latest.get("frl_gap_m"), " m")}</b><small>headroom to FRL</small></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with focus_cols[1]:
                    if not focus_history.empty:
                        focus_long = focus_history.melt(
                            id_vars=["observed_at"],
                            value_vars=[col for col in ["water_level_m", "filling_percent"] if col in focus_history],
                            var_name="metric",
                            value_name="value",
                        ).dropna(subset=["value"])
                        focus_chart = (
                            alt.Chart(focus_long)
                            .mark_line(point=True, strokeWidth=2.5)
                            .encode(
                                x=alt.X("observed_at:T", title="Observation time"),
                                y=alt.Y("value:Q", title="Water level / filling"),
                                color=alt.Color(
                                    "metric:N",
                                    scale=alt.Scale(
                                        domain=["water_level_m", "filling_percent"],
                                        range=["#2563eb", "#f97316"],
                                    ),
                                    title="Metric",
                                ),
                                tooltip=["observed_at", "metric", "value"],
                            )
                            .properties(
                                height=260,
                                title=alt.TitleParams(
                                    text=f"{selected_focus_dam}: Linked Trend",
                                    subtitle="Water level (m) and filling (%) across selected observations",
                                    anchor="start",
                                    fontSize=13,
                                    subtitleFontSize=11,
                                    offset=8,
                                ),
                            )
                        )
                        st.altair_chart(focus_chart, use_container_width=True)
                    else:
                        st.info("No time-series history is available for the selected focus dam.")

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
                .properties(height=260, title="District Reservoir Filling Snapshot")
            )
            st.altair_chart(district_chart, use_container_width=True)
        else:
            st.info("No latest reservoir rows are available for district infographic.")

        info_cols_2 = st.columns([0.34, 0.33, 0.33])
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
                    .properties(height=235, title="Storage Timeline")
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
                    .properties(height=235, title="Top Filled Reservoirs")
                )
                st.altair_chart(top_filling_chart, use_container_width=True)

        info_cols_3 = st.columns([0.50, 0.50])
        all_latest_reservoirs = latest_by_asset(reservoirs, "reservoir_name") if not reservoirs.empty else pd.DataFrame()
        if not all_latest_reservoirs.empty:
            filling_snapshot = all_latest_reservoirs.assign(
                filling_percent=pd.to_numeric(all_latest_reservoirs["filling_percent"], errors="coerce")
            ).dropna(subset=["filling_percent"])
            with info_cols_2[2]:
                least_filled = filling_snapshot[filling_snapshot["filling_percent"] < 25].nsmallest(12, "filling_percent")
                if least_filled.empty:
                    st.success("No reservoirs are below 25% filling in the complete latest reservoir set for the selected reports.")
                else:
                    least_chart = (
                        alt.Chart(least_filled)
                        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                        .encode(
                            y=alt.Y("reservoir_name:N", sort="x", title="Reservoir"),
                            x=alt.X("filling_percent:Q", title="Filling (%)", scale=alt.Scale(domain=[0, 25])),
                            color=alt.Color(
                                "filling_percent:Q",
                                scale=alt.Scale(domain=[0, 25], range=["#1d4ed8", "#0891b2", "#10b981", "#f59e0b"]),
                                legend=None,
                            ),
                            tooltip=["reservoir_name", "district", "water_level_m", "frl_gap_m", "filling_percent"],
                        )
                        .properties(height=235, title="Least Filled Reservoirs Below 25%")
                    )
                    st.altair_chart(least_chart, use_container_width=True)
            with info_cols_3[0]:
                band_labels = ["0-25%", "25-50%", "50-75%", "75-100%"]
                band_colors = ["#2563eb", "#06b6d4", "#f59e0b", "#ef4444"]
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
                    .properties(height=190, title="Reservoir Filling Bands")
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
            with info_cols_3[1]:
                band_summary_rows = "".join(
                    f"""
                    <div class="infographic-card" style="border-top-color:{band_colors[index]}">
                        <span>{escape(str(row.filling_band))} Filled</span>
                        <b>{int(row.reservoirs)}</b>
                        <small>Avg {fmt_number(row.avg_filling, "%")}</small>
                    </div>
                    """
                    for index, row in enumerate(band_summary.itertuples(index=False))
                )
                st.markdown(
                    f"""
                    <div class="infographic-frame" style="padding:.75rem">
                        <div class="infographic-title" style="font-size:1rem">Reservoir Filling Distribution</div>
                        <div class="infographic-grid" style="grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem">
                            {band_summary_rows}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            global_lowest = filling_snapshot.sort_values("filling_percent").iloc[0] if not filling_snapshot.empty else None
            st.markdown('<div class="panel-note">Filling band drill-down uses the complete latest reservoir set for the selected reports, not only the visible chart subset.</div>', unsafe_allow_html=True)
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
                        .properties(height=max(200, min(310, 20 * len(band_detail))), title=f"{selected_band} Filled Reservoirs")
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
                                <div class="infographic-card"><span>Lowest In Category</span><b>{escape(str(band_detail.iloc[0].get("reservoir_name", "-")))}</b><small>{fmt_number(band_detail.iloc[0].get("filling_percent"), "%")} filled</small></div>
                                <div class="infographic-card"><span>Lowest Overall Dam</span><b>{escape(str(global_lowest.get("reservoir_name", "-") if global_lowest is not None else "-"))}</b><small>{fmt_number(global_lowest.get("filling_percent") if global_lowest is not None else math.nan, "%")} filled across all dams</small></div>
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
                render_colored_dam_table(
                    band_detail,
                    "infographic_band_detail",
                    columns=detail_cols,
                    height=min(240, 64 + 26 * len(band_detail)),
                    allow_filters=False,
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
            reservoir_table_cols = [
                "observed_at",
                "reservoir_name",
                "district",
                "sub_basin",
                "major_basin",
                "water_level_m",
                "frl_m",
                "frl_gap_m",
                "current_live_capacity_mcm",
                "filling_percent",
                "rainfall_daily_mm",
                "report_id",
            ]
            render_colored_dam_table(
                reservoir_view.sort_values(["observed_at", "reservoir_name"]),
                "data_explorer_reservoirs",
                columns=reservoir_table_cols,
                height=390,
                allow_filters=True,
            )
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

