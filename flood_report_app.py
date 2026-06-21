from __future__ import annotations

import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

try:
    from flood_report_parser import parse_pdf
except Exception:
    parse_pdf = None

APP_DIR = Path(__file__).resolve().parent
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
API_BASE_URL = os.getenv("FLOOD_API_URL", "").rstrip("/")
try:
    SECRET_PASSWORD = st.secrets.get("ADMIN_UPLOAD_PASSWORD", "")
except Exception:
    SECRET_PASSWORD = ""
ADMIN_UPLOAD_PASSWORD = os.getenv("ADMIN_UPLOAD_PASSWORD", SECRET_PASSWORD)

st.set_page_config(page_title="MP WRD Flood Season 2026", layout="wide")
st.markdown("""
<style>
html,body,[data-testid="stAppViewContainer"]{background:linear-gradient(135deg,#fff7ed 0%,#f7f4ff 45%,#ecfeff 100%)}
.block-container{max-width:1520px;padding-top:1rem}.stTabs [data-baseweb="tab-list"]{gap:.25rem}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#fff 0%,#f1f7ff 55%,#fff7ed 100%);border-right:1px solid #d9d4ef}
h1,h2,h3,p,label{color:#172033;letter-spacing:0!important}.small{font-size:.78rem;color:#64748b}
.masthead{border:1px solid #d9d4ef;background:rgba(255,255,255,.92);border-radius:8px;padding:1rem 1.1rem;margin-bottom:.8rem;box-shadow:0 14px 34px rgba(79,70,229,.1)}
.title{font-size:1.45rem;font-weight:800;line-height:1.15}.subtitle{color:#64748b;font-size:.86rem;margin-top:.25rem}
.badges{display:flex;gap:.4rem;flex-wrap:wrap;justify-content:flex-end}.badge{border:1px solid #d9d4ef;background:#f8fbff;border-radius:6px;padding:.34rem .48rem;font-size:.74rem;color:#334155}
div[data-testid="stMetric"]{background:linear-gradient(180deg,#fff,#f8fbff);border:1px solid #d9d4ef;border-radius:8px;padding:.68rem .75rem;min-height:78px;box-shadow:0 9px 20px rgba(15,23,42,.05)}
.district-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.65rem;margin:.25rem 0 1rem}.district-pill{border:1px solid #d9d4ef;border-left:5px solid #06b6d4;border-radius:8px;background:rgba(255,255,255,.88);padding:.65rem .75rem}.district-pill b{display:block;font-size:1.15rem}.district-pill span{font-size:.72rem;color:#64748b}
.api-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.65rem}.api-card{border:1px solid #d9d4ef;background:rgba(255,255,255,.88);border-radius:8px;padding:.7rem}.api-card b{display:block;font-size:.82rem}.api-card code{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.72rem;color:#0f766e}
</style>
""", unsafe_allow_html=True)


def norm(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii").lower()
    for word in ["project", "major", "medium", "dam", "tank", "sagar", "reservoir"]:
        text = re.sub(rf"\b{word}\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def best_match(name: str, candidates: list[str]) -> str | None:
    source = norm(name)
    if not source:
        return None
    pairs = [(c, norm(c)) for c in candidates]
    for candidate, candidate_norm in pairs:
        if source == candidate_norm or source in candidate_norm or candidate_norm in source:
            return candidate
    scored = [(c, SequenceMatcher(None, source, cn).ratio()) for c, cn in pairs]
    candidate, score = max(scored, key=lambda x: x[1]) if scored else (None, 0)
    return candidate if score >= 0.58 else None


def parsed_directories() -> list[Path]:
    return sorted([p for p in APP_DIR.iterdir() if p.is_dir() and (p / "report_meta.json").exists() and (p / "reservoir_status_observations.csv").exists()], key=lambda p: p.name)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() and path.stat().st_size else pd.DataFrame()


def report_at(meta: dict) -> pd.Timestamp:
    return pd.to_datetime(f"{meta.get('report_date','')} {meta.get('report_time','')}", errors="coerce")


def context(frame: pd.DataFrame, meta: dict, report_id: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["report_id"] = report_id
    frame["report_at"] = report_at(meta)
    frame["report_date"] = meta.get("report_date")
    frame["report_time"] = meta.get("report_time")
    return frame


@st.cache_data(show_spinner=False)
def load_reports(names: tuple[str, ...]):
    metas, rivers, reservoirs, gates = [], [], [], []
    for name in names:
        folder = APP_DIR / name
        meta = pd.read_json(folder / "report_meta.json", typ="series").to_dict()
        metas.append({"report_id": name, "report_at": report_at(meta), "report_date": meta.get("report_date"), "report_time": meta.get("report_time"), "source_filename": meta.get("source_filename", name)})
        for target, filename in [(rivers, "river_water_level_observations.csv"), (reservoirs, "reservoir_status_observations.csv"), (gates, "reservoir_gate_observations.csv")]:
            frame = read_csv(folder / filename)
            if "observed_at" in frame:
                frame["observed_at"] = pd.to_datetime(frame["observed_at"], errors="coerce")
            target.append(context(frame, meta, name))
    def cat(items):
        return pd.concat(items, ignore_index=True) if items else pd.DataFrame()
    meta_df, river_df, reservoir_df, gate_df = pd.DataFrame(metas), cat(rivers), cat(reservoirs), cat(gates)
    if not reservoir_df.empty:
        reservoir_df["frl_gap_m"] = pd.to_numeric(reservoir_df.get("frl_m"), errors="coerce") - pd.to_numeric(reservoir_df.get("water_level_m"), errors="coerce")
    if not river_df.empty:
        river_df["danger_gap_m"] = pd.to_numeric(river_df.get("danger_or_max_water_level_m"), errors="coerce") - pd.to_numeric(river_df.get("water_level_m"), errors="coerce")
        river_df["basin"] = river_df.get("river_name", "")
    return meta_df.sort_values("report_at"), river_df, reservoir_df, gate_df


@st.cache_data(show_spinner=False)
def load_dams(reservoir_names: tuple[str, ...]) -> pd.DataFrame:
    if not DAM_LOCATIONS_CSV.exists():
        return pd.DataFrame()
    dams = pd.read_csv(DAM_LOCATIONS_CSV)
    dams["reservoir_name"] = dams["dam_name"].apply(lambda x: best_match(x, list(reservoir_names)))
    return dams


def alert_level(row):
    gap = row.get("frl_gap_m")
    filling = row.get("display_filling", 0)
    if pd.notna(gap) and gap <= 0.5:
        return "Critical"
    if pd.notna(gap) and gap <= 1.5:
        return "Warning"
    if pd.notna(filling) and filling >= 90:
        return "Watch"
    return "Normal"


def fill_color(level):
    return {"Critical": [239, 68, 68, 235], "Warning": [245, 158, 11, 225], "Watch": [250, 204, 21, 215], "Normal": [37, 99, 235, 205]}[level]


def pulse_color(level, blink_on: bool):
    if not blink_on and level in ["Critical", "Warning"]:
        return [255, 255, 255, 0]
    return {"Critical": [239, 68, 68, 70], "Warning": [245, 158, 11, 56], "Watch": [250, 204, 21, 0], "Normal": [37, 99, 235, 0]}[level]


def fnum(value, suffix=""):
    return "-" if value is None or pd.isna(value) else (f"{value:,.1f}{suffix}" if abs(float(value)) < 100 else f"{value:,.0f}{suffix}")


with st.sidebar:
    st.header("Report Source")
    dirs = parsed_directories()
    if ADMIN_UPLOAD_PASSWORD and parse_pdf:
        with st.expander("Admin PDF upload", expanded=False):
            password = st.text_input("Admin password", type="password")
            upload = st.file_uploader("Upload MP WRD PDF", type=["pdf"], disabled=password != ADMIN_UPLOAD_PASSWORD)
            if upload is not None and password == ADMIN_UPLOAD_PASSWORD:
                source = APP_DIR / "uploaded_reports" / upload.name
                source.parent.mkdir(exist_ok=True)
                source.write_bytes(upload.getbuffer())
                out = APP_DIR / f"parsed_{Path(upload.name).stem.replace(' ', '_')}"
                with st.spinner("Parsing report..."):
                    counts = parse_pdf(source, out)
                st.success(f"Captured {counts.get('river_observation_rows',0)} river, {counts.get('reservoir_observation_rows',0)} reservoir and {counts.get('gate_observation_rows',0)} gate rows.")
                st.cache_data.clear()
                dirs = parsed_directories()
    elif parse_pdf:
        st.caption("Admin upload disabled. Set ADMIN_UPLOAD_PASSWORD in hosting settings to enable it.")
    if not dirs:
        st.error("No parsed report folders found. Upload a PDF after setting the admin password.")
        st.stop()
    selected_reports = st.multiselect("Captured reports", [p.name for p in dirs], default=[p.name for p in dirs])
    if not selected_reports:
        st.stop()

meta_df, rivers, reservoirs, gates = load_reports(tuple(selected_reports))
reservoir_names = tuple(sorted(reservoirs.get("reservoir_name", pd.Series(dtype=str)).dropna().unique()))
dams = load_dams(reservoir_names)

with st.sidebar:
    st.header("Filters")
    times = sorted(pd.Timestamp(v) for v in reservoirs.get("observed_at", pd.Series(dtype="datetime64[ns]")).dropna().unique())
    dates = sorted({t.date() for t in times})
    date_range = st.date_input("Dates", value=(dates[0], dates[-1]) if dates else None, min_value=dates[0] if dates else None, max_value=dates[-1] if dates else None)
    start_date, end_date = (date_range if isinstance(date_range, tuple) else (date_range, date_range)) if date_range else (None, None)
    selected_time_labels = st.multiselect("Times", sorted({t.strftime("%I:%M %p") for t in times}), default=sorted({t.strftime("%I:%M %p") for t in times}))
    districts = st.multiselect("Districts", sorted(set(reservoirs.get("district", pd.Series(dtype=str)).dropna()).union(set(rivers.get("district", pd.Series(dtype=str)).dropna()))))
    basins = st.multiselect("Basins / Rivers", sorted(rivers.get("basin", pd.Series(dtype=str)).dropna().unique()))
    selected_reservoirs = st.multiselect("Reservoirs", sorted(reservoir_names))
    selected_gauges = st.multiselect("Gauge stations", sorted(rivers.get("gauge_station", pd.Series(dtype=str)).dropna().unique()))


def apply_time(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "observed_at" not in df:
        return df
    out = df[df["observed_at"].notna()].copy()
    if start_date:
        out = out[out["observed_at"].dt.date >= start_date]
    if end_date:
        out = out[out["observed_at"].dt.date <= end_date]
    if selected_time_labels:
        out = out[out["observed_at"].dt.strftime("%I:%M %p").isin(selected_time_labels)]
    return out

reservoir_view, river_view = apply_time(reservoirs), apply_time(rivers)
if districts:
    reservoir_view = reservoir_view[reservoir_view["district"].isin(districts)]
    river_view = river_view[river_view["district"].isin(districts)]
if basins:
    river_view = river_view[river_view["basin"].isin(basins)]
if selected_reservoirs:
    reservoir_view = reservoir_view[reservoir_view["reservoir_name"].isin(selected_reservoirs)]
if selected_gauges:
    river_view = river_view[river_view["gauge_station"].isin(selected_gauges)]
gate_view = gates[gates["reservoir_name"].isin(selected_reservoirs)] if selected_reservoirs and not gates.empty else gates
latest_res = reservoir_view.sort_values("observed_at").groupby(["reservoir_name", "district"], as_index=False).tail(1) if not reservoir_view.empty else pd.DataFrame()
latest_riv = river_view.sort_values("observed_at").groupby(["river_name", "gauge_station", "district"], as_index=False).tail(1) if not river_view.empty else pd.DataFrame()

latest_at = meta_df["report_at"].max() if not meta_df.empty else pd.NaT
st.markdown(f"""
<div class="masthead"><div style="display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;flex-wrap:wrap">
<div><div class="title">MP WRD Flood Season 2026 Dashboard</div><div class="subtitle">Time-wise reservoir, river gauge, gate and dam alert monitoring.</div></div>
<div class="badges"><div class="badge">Reports {len(meta_df)}</div><div class="badge">Latest {latest_at.strftime('%d %b %Y %I:%M %p') if pd.notna(latest_at) else '-'}</div><div class="badge">API {'configured' if API_BASE_URL else 'ready'}</div></div>
</div></div>
""", unsafe_allow_html=True)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Reservoirs", latest_res["reservoir_name"].nunique() if not latest_res.empty else 0)
m2.metric("Avg Filling", fnum(latest_res.get("filling_percent", pd.Series(dtype=float)).mean(), "%"))
m3.metric("Storage", fnum(latest_res.get("current_live_capacity_mcm", pd.Series(dtype=float)).sum(), " MCM"))
m4.metric("River Gauges", latest_riv["gauge_station"].nunique() if not latest_riv.empty else 0)
m5.metric("Open Gate Sites", int((gate_view.get("gate_opened_count", pd.Series(dtype=float)).fillna(0).astype(float) > 0).sum()) if not gate_view.empty else 0)

st.subheader("Dam Locations and FRL Alerts")
map_status = pd.DataFrame()
if not dams.empty:
    map_status = dams.merge(latest_res, on="reservoir_name", how="left", suffixes=("", "_report")) if not latest_res.empty else dams.copy()
    if districts and "map_district" in map_status:
        map_status = map_status[map_status["map_district"].isin(districts) | map_status.get("district", pd.Series(dtype=str)).isin(districts)]
    fallback = pd.to_numeric(map_status.get("map_filled_percent", 0), errors="coerce")
    map_status["display_filling"] = pd.to_numeric(map_status.get("filling_percent", fallback), errors="coerce").fillna(fallback).fillna(0)
    map_status["frl_gap_m"] = pd.to_numeric(map_status.get("frl_gap_m"), errors="coerce")
    map_status["alert_level"] = map_status.apply(alert_level, axis=1)
    blink_on = pd.Timestamp.utcnow().second % 2 == 0
    map_status["fill_color"] = map_status["alert_level"].apply(fill_color)
    map_status["pulse_color"] = map_status["alert_level"].apply(lambda x: pulse_color(x, blink_on))
    map_status["radius"] = (map_status["display_filling"].clip(0, 100) * 18 + 850).astype(float)
    map_status["pulse_radius"] = map_status["radius"] * 2.35

if map_status.empty:
    st.info("Dam coordinate data is not available for the selected filters.")
else:
    districts_summary = map_status.assign(district_label=map_status.get("map_district", "")).groupby("district_label", as_index=False).agg(dams=("dam_name", "nunique"), avg_filling=("display_filling", "mean"), alerts=("alert_level", lambda x: x.isin(["Critical", "Warning"]).sum())).sort_values(["alerts", "dams"], ascending=False)
    html = '<div class="district-strip">' + ''.join(f'<div class="district-pill"><b>{int(r.dams)}</b><span>{r.district_label} dams | avg {r.avg_filling:,.1f}% | alerts {int(r.alerts)}</span></div>' for r in districts_summary.head(8).itertuples(index=False)) + '</div>'
    st.markdown(html, unsafe_allow_html=True)
    left, right = st.columns([1.35, .65])
    with left:
        background = st.radio("Map background", ["Dam points only", "ArcGIS Online"], horizontal=True)
        alerts = map_status[map_status["alert_level"].isin(["Critical", "Warning"])]
        layers = [
            pdk.Layer("ScatterplotLayer", data=alerts, get_position="[longitude, latitude]", get_radius="pulse_radius", get_fill_color="pulse_color", radius_min_pixels=10, radius_max_pixels=28),
            pdk.Layer("ScatterplotLayer", data=map_status, get_position="[longitude, latitude]", get_radius="radius", get_fill_color="fill_color", get_line_color=[255,255,255,230], line_width_min_pixels=1, radius_min_pixels=4, radius_max_pixels=13, pickable=True, auto_highlight=True),
        ]
        style = "https://basemaps.arcgis.com/arcgis/rest/services/World_Basemap_v2/VectorTileServer/resources/styles/root.json" if background == "ArcGIS Online" else None
        deck = pdk.Deck(map_style=style, initial_view_state=pdk.ViewState(latitude=float(map_status["latitude"].mean()), longitude=float(map_status["longitude"].mean()), zoom=5.7), layers=layers, tooltip={"html":"<b>{dam_name}</b><br/>Alert: {alert_level}<br/>Reservoir: {reservoir_name}<br/>District: {map_district}<br/>Filling: {display_filling}%<br/>FRL gap: {frl_gap_m} m", "style":{"backgroundColor":"#111827","color":"white"}})
        st.pydeck_chart(deck, height=520)
        st.caption("FRL alert legend: Critical red blinking ring, Warning amber blinking ring, Watch yellow, Normal blue.")
    with right:
        gauge_district = st.selectbox("Dam filling gauges by district", ["Top filled dams"] + sorted(map_status.get("map_district", pd.Series(dtype=str)).dropna().unique()))
        gauge = map_status if gauge_district == "Top filled dams" else map_status[map_status["map_district"] == gauge_district]
        gauge = gauge.sort_values("display_filling", ascending=False).head(16)
        chart = alt.Chart(gauge).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(x=alt.X("display_filling:Q", title="Filling %", scale=alt.Scale(domain=[0, 100])), y=alt.Y("dam_name:N", sort="-x", title="Dam"), color=alt.Color("display_filling:Q", scale=alt.Scale(domain=[0,45,75,100], range=["#2563eb","#06b6d4","#f59e0b","#ef4444"]), legend=None), tooltip=["dam_name","reservoir_name","map_district","display_filling","frl_gap_m","alert_level"]).properties(height=360)
        st.altair_chart(chart, use_container_width=True)

api_tab, time_tab, reservoir_tab, river_tab, gate_tab, data_tab = st.tabs(["API", "Time Series", "Reservoir Trends", "River Trends", "Gate Timeline", "Data Explorer"])
with api_tab:
    st.subheader("REST API / GeoJSON")
    base = API_BASE_URL or "https://YOUR-RENDER-API.onrender.com"
    cards = [("Reservoir GeoJSON", "/api/geojson/reservoir-status"), ("Alert GeoJSON", "/api/geojson/alerts"), ("Reservoir observations", "/api/reservoir-observations"), ("River gauges", "/api/river-gauges"), ("District summary", "/api/district-summary"), ("Basin summary", "/api/basin-summary")]
    st.markdown('<div class="api-grid">' + ''.join(f'<div class="api-card"><b>{n}</b><code>{base}{p}</code></div>' for n, p in cards) + '</div>', unsafe_allow_html=True)
with time_tab:
    st.subheader("Observation Timeline")
    if reservoir_view.empty:
        st.info("No reservoir observations match the filters.")
    else:
        timeline = reservoir_view.groupby("observed_at", as_index=False).agg(reservoirs=("reservoir_name","nunique"), avg_filling_percent=("filling_percent","mean"), total_storage_mcm=("current_live_capacity_mcm","sum"), rainfall_daily_mm=("rainfall_daily_mm","sum")).sort_values("observed_at")
        a, b = st.columns([1.2, .8])
        a.altair_chart(alt.Chart(timeline).mark_line(point=True).encode(x="observed_at:T", y=alt.Y("avg_filling_percent:Q", title="Average filling (%)"), tooltip=list(timeline.columns)).properties(height=350), use_container_width=True)
        b.altair_chart(alt.Chart(timeline).mark_bar().encode(x="observed_at:T", y=alt.Y("rainfall_daily_mm:Q", title="Daily rainfall (mm)"), tooltip=list(timeline.columns)).properties(height=350), use_container_width=True)
        st.dataframe(timeline, use_container_width=True, hide_index=True)
with reservoir_tab:
    st.subheader("Reservoir Trends")
    if reservoir_view.empty:
        st.info("No reservoir data.")
    else:
        metric = st.selectbox("Reservoir metric", ["filling_percent", "water_level_m", "current_live_capacity_mcm", "rainfall_daily_mm", "frl_gap_m"])
        opts = sorted(reservoir_view["reservoir_name"].dropna().unique())
        chosen = st.multiselect("Reservoirs", opts, default=opts[:min(8, len(opts))])
        df = reservoir_view[reservoir_view["reservoir_name"].isin(chosen)].dropna(subset=[metric])
        st.altair_chart(alt.Chart(df).mark_line(point=True).encode(x="observed_at:T", y=f"{metric}:Q", color="reservoir_name:N", tooltip=["reservoir_name","district","observed_at",metric]).properties(height=430), use_container_width=True)
with river_tab:
    st.subheader("River Gauge Trends")
    if river_view.empty:
        st.info("No river data.")
    else:
        metric = st.selectbox("River metric", ["water_level_m", "danger_gap_m"])
        opts = sorted(river_view["gauge_station"].dropna().unique())
        chosen = st.multiselect("Gauge stations", opts, default=opts[:min(8, len(opts))])
        df = river_view[river_view["gauge_station"].isin(chosen)].dropna(subset=[metric])
        st.altair_chart(alt.Chart(df).mark_line(point=True).encode(x="observed_at:T", y=f"{metric}:Q", color="gauge_station:N", tooltip=["river_name","gauge_station","district","observed_at",metric]).properties(height=430), use_container_width=True)
        st.dataframe(latest_riv.sort_values("danger_gap_m", na_position="last"), use_container_width=True, hide_index=True)
with gate_tab:
    st.subheader("Gate Operations")
    if gate_view.empty:
        st.info("No gate rows available.")
    else:
        open_only = st.toggle("Show only open gate rows", value=False)
        df = gate_view[gate_view["gate_opened_count"].fillna(0).astype(float) > 0] if open_only else gate_view
        st.dataframe(df.sort_values(["report_at", "reservoir_name"]), use_container_width=True, hide_index=True)
with data_tab:
    st.subheader("Data Explorer")
    choice = st.radio("Dataset", ["Reservoir observations", "River observations", "Gate observations", "Reports", "Dam locations"], horizontal=True)
    data = {"Reservoir observations": reservoir_view, "River observations": river_view, "Gate observations": gate_view, "Reports": meta_df, "Dam locations": map_status}.get(choice, pd.DataFrame())
    st.dataframe(data, use_container_width=True, hide_index=True)
    st.download_button("Download CSV", data.to_csv(index=False).encode("utf-8"), file_name=f"{choice.lower().replace(' ', '_')}.csv", mime="text/csv")
