from __future__ import annotations

import json
import math
import sys
import re
import unicodedata
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


APP_DIR = Path(__file__).resolve().parent
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
DAM_SHAPEFILE = APP_DIR / "dam_shapefile" / "Dams_EinC_54_R2.shp"
GLOFAS_PROJECT_JSON = APP_DIR / "data" / "glofas_mp_project.json"
GRRR_PROJECT_JSON = APP_DIR / "data" / "grrr_mp_project.json"
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
    .block-container {
        max-width: 1540px;
        padding-top: 1.35rem;
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
        if source_norm and candidate_norm and (source_norm in candidate_norm or candidate_norm in source_norm):
            return candidate, 0.92
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
                "esri/views/MapView",
                "esri/layers/GraphicsLayer",
                "esri/layers/MapImageLayer",
                "esri/layers/TileLayer",
                "esri/widgets/LayerList",
                "esri/widgets/BasemapGallery",
                "esri/widgets/Expand",
                "esri/widgets/Home",
                "esri/geometry/Extent",
                "esri/geometry/Polyline",
                "esri/geometry/geometryEngine",
                "esri/Graphic"
            ], function(esriConfig, WebMap, MapView, GraphicsLayer, MapImageLayer, TileLayer, LayerList, BasemapGallery, Expand, Home, Extent, Polyline, geometryEngine, Graphic) {{
                esriConfig.portalUrl = "{ARCGIS_PORTAL_URL}";
                const webmap = new WebMap({{
                    portalItem: {{ id: "{ARCGIS_EMBED_ITEM_ID}" }}
                }});
                const mpExtent = new Extent({{
                    xmin: 74.029052,
                    ymin: 21.0707762,
                    xmax: 82.8066027,
                    ymax: 26.8683691,
                    spatialReference: {{ wkid: 4326 }}
                }});
                const view = new MapView({{
                    container: "damMap",
                    map: webmap,
                    center: [78.22922399768257, 23.48361289099537],
                    zoom: 7,
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
                webmap.add(hillshadeLayer, 0);
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

    st.subheader("GloFAS Forecast Context for Madhya Pradesh")
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

    st.subheader("Google Runoff Reanalysis & Reforecast for Madhya Pradesh")
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

tab_time, tab_rivers, tab_gates, tab_data, tab_exports = st.tabs(
    ["Time Series", "River Trends", "Gate Timeline", "Data Explorer", "Exports"]
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

with tab_data:
    st.subheader("Time-Aware Data Explorer")
    data_choice = st.radio(
        "Dataset",
        ["Reservoir observations", "River observations", "Gate observations", "Reservoir master", "River master", "Reports"],
        horizontal=True,
    )
    if data_choice == "Reservoir observations":
        st.dataframe(reservoir_view.sort_values(["observed_at", "reservoir_name"]), use_container_width=True, hide_index=True, height=360)
    elif data_choice == "River observations":
        st.dataframe(river_view.sort_values(["observed_at", "river_name", "gauge_station"]), use_container_width=True, hide_index=True, height=360)
    elif data_choice == "Gate observations":
        st.dataframe(gate_view_all.sort_values(["report_at", "reservoir_name"]), use_container_width=True, hide_index=True, height=360)
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
