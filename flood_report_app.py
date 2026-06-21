from __future__ import annotations

import os
import re
import unicodedata
import urllib.error
import urllib.request
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
ADMIN_UPLOAD_PASSWORD = os.getenv("ADMIN_UPLOAD_PASSWORD", st.secrets.get("ADMIN_UPLOAD_PASSWORD", "") if hasattr(st, "secrets") else "")

st.set_page_config(page_title="MP WRD Flood Season 2026", layout="wide")

st.markdown("""
<style>
:root{--line:#d9d4ef;--ink:#172033;--muted:#64748b;--blue:#2563eb;--cyan:#06b6d4;--amber:#f59e0b;--red:#ef4444}
html,body,[data-testid="stAppViewContainer"]{background:linear-gradient(135deg,#fff7ed 0%,#f7f4ff 45%,#ecfeff 100%)}
.block-container{max-width:1540px;padding-top:1rem;padding-bottom:2rem}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#ffffff 0%,#f1f7ff 55%,#fff7ed 100%);border-right:1px solid var(--line)}
h1,h2,h3,p,label{color:var(--ink);letter-spacing:0!important}.small{font-size:.78rem;color:var(--muted)}
.masthead{border:1px solid var(--line);background:rgba(255,255,255,.9);border-radius:8px;padding:1rem 1.1rem;margin-bottom:.8rem;box-shadow:0 14px 34px rgba(79,70,229,.10)}
.title{font-size:1.45rem;font-weight:800;line-height:1.15}.subtitle{color:var(--muted);font-size:.86rem;margin-top:.25rem}
.badges{display:flex;gap:.4rem;flex-wrap:wrap;justify-content:flex-end}.badge{border:1px solid var(--line);background:#f8fbff;border-radius:6px;padding:.34rem .48rem;font-size:.74rem;color:#334155}
div[data-testid="stMetric"]{background:linear-gradient(180deg,#fff,#f8fbff);border:1px solid var(--line);border-radius:8px;padding:.68rem .75rem;min-height:78px;box-shadow:0 9px 20px rgba(15,23,42,.05)}
.district-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.65rem;margin:.25rem 0 1rem}.district-pill{border:1px solid var(--line);border-left:5px solid var(--cyan);border-radius:8px;background:rgba(255,255,255,.88);padding:.65rem .75rem}.district-pill b{display:block;font-size:1.15rem}.district-pill span{font-size:.72rem;color:var(--muted)}
.api-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.65rem;margin:.75rem 0 1rem}.api-card{border:1px solid var(--line);background:rgba(255,255,255,.88);border-radius:8px;padding:.7rem .78rem}.api-card b{display:block;font-size:.82rem;margin-bottom:.28rem}.api-card code{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.72rem;color:#0f766e}
</style>
""", unsafe_allow_html=True)


def norm(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii").lower()
    for word in ["project", "major", "medium", "dam", "tank", "sagar", "reservoir"]:
        text = re.sub(rf"\b{word}\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def best_match(name: str, candidates: list[str]) -> tuple[str | None, float]:
    source = norm(name)
    if not source:
        return None, 0.0
    pairs = [(candidate, norm(candidate)) for candidate in candidates]
    for candidate, candidate_norm in pairs:
        if source == candidate_norm:
            return candidate, 1.0
        if source in candidate_norm or candidate_norm in source:
            return candidate, 0.92
    scored = [(candidate, SequenceMatcher(None, source, candidate_norm).ratio()) for candidate, candidate_norm in pairs]
    return max(scored, key=lambda x: x[1]) if scored else (None, 0.0)


def parsed_directories() -> list[Path]:
    return sorted([
        path for path in APP_DIR.iterdir()
        if path.is_dir() and (path / "report_meta.json").exists() and (path / "reservoir_status_observations.csv").exists()
    ], key=lambda p: p.name)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def report_at(meta: dict) -> pd.Timestamp:
    return pd.to_datetime(f"{meta.get('report_date','')} {meta.get('report_time','')}", errors="coerce")


def with_context(frame: pd.DataFrame, meta: dict, report_id: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["report_id"] = report_id
    frame["report_at"] = report_at(meta)
    frame["report_date"] = meta.get("report_date")
    frame["report_time"] = meta.get("report_time")
    return frame


def load_one(path: Path):
    meta = pd.read_json(path / "report_meta.json", typ="series").to_dict()
    rivers = read_csv(path / "river_water_level_observations.csv")
    reservoirs = read_csv(path / "reservoir_status_observations.csv")
    gates = read_csv(path / "reservoir_gate_observations.csv")
    river_master = read_csv(path / "river_gauge_stations.csv")
    reservoir_master = read_csv(path / "reservoirs.csv")
    for frame in [rivers, reservoirs, gates]:
        if "observed_at" in frame:
            frame["observed_at"] = pd.to_datetime(frame["observed_at"], errors="coerce")
    report_id = path.name
    return (
        {"report_id": report_id, "report_at": report_at(meta), "report_date": meta.get("report_date"), "report_time": meta.get("report_time"), "source_filename": meta.get("source_filename", report_id)},
        with_context(rivers, meta, report_id),
        with_context(reservoirs, meta, report_id),
        with_context(gates, meta, report_id),
        with_context(river_master, meta, report_id),
        with_context(reservoir_master, meta, report_id),
    )


@st.cache_data(show_spinner=False)
def load_all(names: tuple[str, ...]):
    rows, rivers, reservoirs, gates, river_master, reservoir_master = [], [], [], [], [], []
    for name in names:
        meta, r, res, g, rm, rem = load_one(APP_DIR / name)
        rows.append(meta); rivers.append(r); reservoirs.append(res); gates.append(g); river_master.append(rm); reservoir_master.append(rem)
    def cat(items):
        return pd.concat(items, ignore_index=True) if items else pd.DataFrame()
    meta_df = pd.DataFrame(rows).sort_values("report_at")
    rivers_df, reservoirs_df, gates_df = cat(rivers), cat(reservoirs), cat(gates)
    if not reservoirs_df.empty:
        reservoirs_df["frl_gap_m"] = pd.to_numeric(reservoirs_df.get("frl_m"), errors="coerce") - pd.to_numeric(reservoirs_df.get("water_level_m"), errors="coerce")
    if not rivers_df.empty:
        rivers_df["danger_gap_m"] = pd.to_numeric(rivers_df.get("danger_or_max_water_level_m"), errors="coerce") - pd.to_numeric(rivers_df.get("water_level_m"), errors="coerce")
        if "basin" not in rivers_df:
            rivers_df["basin"] = rivers_df.get("river_name", "")
    return meta_df, rivers_df, reservoirs_df, gates_df, cat(river_master), cat(reservoir_master)


@st.cache_data(show_spinner=False)
def load_dams(names: tuple[str, ...]) -> pd.DataFrame:
    if not DAM_LOCATIONS_CSV.exists():
        return pd.DataFrame()
    dams = pd.read_csv(DAM_LOCATIONS_CSV)
    rows = []
    for row in dams.to_dict("records"):
        matched, score = best_match(row.get("dam_name", ""), list(names))
        row["reservoir_name"] = matched
        row["match_score"] = score
        rows.append(row)
    return pd.DataFrame(rows)


def fnum(value, suffix=""):
    if value is None or pd.isna(value):
        return "-"
    return f"{value:,.1f}{suffix}" if abs(float(value)) < 100 else f"{value:,.0f}{suffix}"


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


def color(level):
    return {"Critical":[239,68,68,235],"Warning":[245,158,11,225],"Watch":[250,204,21,215],"Normal":[37,99,235,205]}.get(level,[37,99,235,205])


def api_ok(url: str) -> bool:
    if not url:
        return False
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


with st.sidebar:
    st.header("Report Source")
    dirs = parsed_directories()
    if ADMIN_UPLOAD_PASSWORD and parse_pdf is not None:
        with st.expander("Admin PDF upload", expanded=False):
            password = st.text_input("Admin password", type="password")
            uploaded = st.file_uploader("Upload MP WRD PDF", type=["pdf"], disabled=password != ADMIN_UPLOAD_PASSWORD)
            if uploaded is not None and password == ADMIN_UPLOAD_PASSWORD:
                target_dir = APP_DIR / f"parsed_{Path(uploaded.name).stem.replace(' ', '_')}"
                source = APP_DIR / "uploaded_reports" / uploaded.name
                source.parent.mkdir(exist_ok=True)
                source.write_bytes(uploaded.getbuffer())
                with st.spinner("Parsing report..."):
                    counts = parse_pdf(source, target_dir)
                st.success(f"Captured {counts.get('river_observation_rows',0)} river, {counts.get('reservoir_observation_rows',0)} reservoir, {counts.get('gate_observation_rows',0)} gate rows.")
                st.cache_data.clear()
                dirs = parsed_directories()
    elif parse_pdf is not None:
        st.caption("Public upload is disabled. Set ADMIN_UPLOAD_PASSWORD to enable admin uploads.")

    if not dirs:
        st.error("No parsed report folders are available in this deployment.")
        st.stop()
    selected_reports = st.multiselect("Captured reports", [p.name for p in dirs], default=[p.name for p in dirs])
    if not selected_reports:
        st.stop()

meta_df, rivers, reservoirs, gates, river_master, reservoir_master = load_all(tuple(selected_reports))
reservoir_names = tuple(sorted(reservoirs["reservoir_name"].dropna().unique())) if not reservoirs.empty else tuple()
dams = load_dams(reservoir_names)

with st.sidebar:
    st.header("Time Filters")
    timestamps = sorted(pd.Timestamp(v) for v in reservoirs.get("observed_at", pd.Series(dtype="datetime64[ns]")).dropna().unique())
    dates = sorted({t.date() for t in timestamps})
    date_range = st.date_input("Dates", value=(dates[0], dates[-1]) if dates else None, min_value=dates[0] if dates else None, max_value=dates[-1] if dates else None)
    start_date, end_date = (date_range if isinstance(date_range, tuple) else (date_range, date_range)) if date_range else (None, None)
    time_options = sorted({t.strftime("%I:%M %p") for t in timestamps})
    selected_times = st.multiselect("Times", time_options, default=time_options)
    district_options = sorted(set(reservoirs.get("district", pd.Series(dtype=str)).dropna()).union(set(rivers.get("district", pd.Series(dtype=str)).dropna())))
    districts = st.multiselect("Districts", district_options)
    basins = st.multiselect("Basins / Rivers", sorted(rivers.get("basin", pd.Series(dtype=str)).dropna().unique()))
    res_filter = st.multiselect("Reservoirs", sorted(reservoir_names))
    gauge_filter = st.multiselect("Gauge stations", sorted(rivers.get("gauge_station", pd.Series(dtype=str)).dropna().unique()))


def time_filter(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "observed_at" not in df:
        return df
    out = df.copy()
    out = out[out["observed_at"].notna()]
    if start_date:
        out = out[out["observed_at"].dt.date >= start_date]
    if end_date:
        out = out[out["observed_at"].dt.date <= end_date]
    if selected_times:
        out = out[out["observed_at"].dt.strftime("%I:%M %p").isin(selected_times)]
    return out

reservoir_view = time_filter(reservoirs)
river_view = time_filter(rivers)
if districts:
    reservoir_view = reservoir_view[reservoir_view["district"].isin(districts)]
    river_view = river_view[river_view["district"].isin(districts)]
if basins and "basin" in river_view:
    river_view = river_view[river_view["basin"].isin(basins)]
if res_filter:
    reservoir_view = reservoir_view[reservoir_view["reservoir_name"].isin(res_filter)]
if gauge_filter:
    river_view = river_view[river_view["gauge_station"].isin(gauge_filter)]

gate_view = gates.copy()
if not gate_view.empty and res_filter:
    gate_view = gate_view[gate_view["reservoir_name"].isin(res_filter)]

latest_res = reservoir_view.sort_values("observed_at").groupby(["reservoir_name", "district"], as_index=False).tail(1) if not reservoir_view.empty else pd.DataFrame()
latest_riv = river_view.sort_values("observed_at").groupby(["river_name", "gauge_station", "district"], as_index=False).tail(1) if not river_view.empty else pd.DataFrame()

latest_at = meta_df["report_at"].max() if not meta_df.empty else pd.NaT
st.markdown(f"""
<div class="masthead"><div style="display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;flex-wrap:wrap">
<div><div class="title">MP WRD Flood Season 2026 Dashboard</div><div class="subtitle">Time-series reservoir, river gauge, gate and dam alert monitoring.</div></div>
<div class="badges"><div class="badge">Reports {len(meta_df)}</div><div class="badge">Latest {latest_at.strftime('%d %b %Y %I:%M %p') if pd.notna(latest_at) else '-'}</div><div class="badge">API {'configured' if API_BASE_URL else 'local/off'}</div></div>
</div></div>
""", unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Reservoirs", f"{latest_res['reservoir_name'].nunique() if not latest_res.empty else 0}")
c2.metric("Avg Filling", fnum(latest_res.get("filling_percent", pd.Series(dtype=float)).mean(), "%"))
c3.metric("Storage", fnum(latest_res.get("current_live_capacity_mcm", pd.Series(dtype=float)).sum(), " MCM"))
c4.metric("River Gauges", f"{latest_riv['gauge_station'].nunique() if not latest_riv.empty else 0}")
c5.metric("Open Gate Sites", f"{int((gate_view.get('gate_opened_count', pd.Series(dtype=float)).fillna(0).astype(float) > 0).sum()) if not gate_view.empty else 0}")

st.subheader("Dam Locations and FRL Alerts")
map_status = pd.DataFrame()
if not dams.empty:
    map_status = dams.copy()
    if not latest_res.empty:
        map_status = map_status.merge(latest_res, on="reservoir_name", how="left", suffixes=("", "_report"))
    if districts and "map_district" in map_status:
        map_status = map_status[map_status["map_district"].isin(districts) | map_status.get("district", pd.Series(dtype=str)).isin(districts)]
    map_status["display_filling"] = pd.to_numeric(map_status.get("filling_percent", map_status.get("map_filled_percent", 0)), errors="coerce").fillna(pd.to_numeric(map_status.get("map_filled_percent", 0), errors="coerce")).fillna(0)
    map_status["frl_gap_m"] = pd.to_numeric(map_status.get("frl_gap_m"), errors="coerce")
    map_status["alert_level"] = map_status.apply(alert_level, axis=1)
    map_status["fill_color"] = map_status["alert_level"].map(color)
    map_status["radius"] = (map_status["display_filling"].clip(0,100) * 18 + 850).astype(float)
    map_status["pulse_radius"] = map_status["radius"] * 2.35
    blink = pd.Timestamp.utcnow().second % 2 == 0
    map_status["pulse_color"] = map_status["alert_level"].map({"Critical":[239,68,68,70],"Warning":[245,158,11,56],"Watch":[250,204,21,0],"Normal":[37,99,235,0]})
    if not blink:
        map_status.loc[map_status["alert_level"].isin(["Critical","Warning"]), "pulse_color"] = [[255,255,255,0]] * len(map_status[map_status["alert_level"].isin(["Critical","Warning"])])

if map_status.empty:
    st.info("Dam locations are not available for the current filters.")
else:
    district_counts = map_status.assign(district_label=map_status.get("map_district", "")).groupby("district_label", as_index=False).agg(dams=("dam_name", "nunique"), avg_filling=("display_filling", "mean"), alerts=("alert_level", lambda s: s.isin(["Critical", "Warning"]).sum())).sort_values(["alerts", "dams"], ascending=False)
    html = '<div class="district-strip">'
    for row in district_counts.head(8).itertuples(index=False):
        html += f'<div class="district-pill"><b>{int(row.dams)}</b><span>{row.district_label} dams | avg {row.avg_filling:,.1f}% | alerts {int(row.alerts)}</span></div>'
    st.markdown(html + '</div>', unsafe_allow_html=True)
    left, right = st.columns([1.35, .65])
    with left:
        background = st.radio("Map background", ["Dam points only", "ArcGIS Online"], horizontal=True)
        alerts = map_status[map_status["alert_level"].isin(["Critical", "Warning"])]
        layers = [
            pdk.Layer("ScatterplotLayer", data=alerts, get_position="[longitude, latitude]", get_radius="pulse_radius", get_fill_color="pulse_color", line_width_min_pixels=2, radius_min_pixels=10, radius_max_pixels=28),
            pdk.Layer("ScatterplotLayer", data=map_status, get_position="[longitude, latitude]", get_radius="radius", get_fill_color="fill_color", get_line_color=[255,255,255,230], line_width_min_pixels=1, radius_min_pixels=4, radius_max_pixels=13, pickable=True, auto_highlight=True),
        ]
        style = "https://basemaps.arcgis.com/arcgis/rest/services/World_Basemap_v2/VectorTileServer/resources/styles/root.json" if background == "ArcGIS Online" else None
        deck = pdk.Deck(map_style=style, initial_view_state=pdk.ViewState(latitude=float(map_status["latitude"].mean()), longitude=float(map_status["longitude"].mean()), zoom=5.7), layers=layers, tooltip={"html":"<b>{dam_name}</b><br/>Alert: {alert_level}<br/>Reservoir: {reservoir_name}<br/>District: {map_district}<br/>Filling: {display_filling}%<br/>FRL gap: {frl_gap_m} m", "style":{"backgroundColor":"#111827","color":"white"}})
        st.pydeck_chart(deck, height=520)
        counts = map_status["alert_level"].value_counts().to_dict()
        st.caption(f"Critical {counts.get('Critical',0)} | Warning {counts.get('Warning',0)} | Watch {counts.get('Watch',0)} | Normal {counts.get('Normal',0)}")
    with right:
        gauge_district = st.selectbox("Dam filling gauges by district", ["Top filled dams"] + sorted(map_status.get("map_district", pd.Series(dtype=str)).dropna().unique()))
        gauge = map_status.copy()
        if gauge_district != "Top filled dams":
            gauge = gauge[gauge["map_district"] == gauge_district]
        gauge = gauge.sort_values("display_filling", ascending=False).head(16)
        chart = alt.Chart(gauge).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(x=alt.X("display_filling:Q", title="Filling %", scale=alt.Scale(domain=[0,100])), y=alt.Y("dam_name:N", sort="-x", title="Dam"), color=alt.Color("display_filling:Q", scale=alt.Scale(domain=[0,45,75,100], range=["#2563eb","#06b6d4","#f59e0b","#ef4444"]), legend=None), tooltip=["dam_name","reservoir_name","map_district","display_filling","frl_gap_m","alert_level"]).properties(height=360)
        st.altair_chart(chart, use_container_width=True)

api_tab, time_tab, reservoir_tab, river_tab, gates_tab, data_tab = st.tabs(["API", "Time Series", "Reservoir Trends", "River Trends", "Gate Timeline", "Data Explorer"])
with api_tab:
    st.subheader("External Data Services")
    status = "online" if api_ok(API_BASE_URL or "http://127.0.0.1:8600") else "configure FLOOD_API_URL after API deployment"
    st.markdown(f"<div class='small'>API status: {status}</div>", unsafe_allow_html=True)
    base = API_BASE_URL or "https://YOUR-RENDER-API.onrender.com"
    cards = [("Reservoir GeoJSON", "/api/geojson/reservoir-status"), ("Alert GeoJSON", "/api/geojson/alerts"), ("Reservoir observations", "/api/reservoir-observations"), ("River gauges", "/api/river-gauges"), ("District summary", "/api/district-summary"), ("Basin summary", "/api/basin-summary")]
    html = '<div class="api-grid">' + ''.join([f'<div class="api-card"><b>{name}</b><code>{base}{path}</code></div>' for name, path in cards]) + '</div>'
    st.markdown(html, unsafe_allow_html=True)

with time_tab:
    st.subheader("Observation Timeline")
    if reservoir_view.empty:
        st.info("No reservoir observations match the filters.")
    else:
        timeline = reservoir_view.groupby("observed_at", as_index=False).agg(reservoirs=("reservoir_name","nunique"), avg_filling_percent=("filling_percent","mean"), total_storage_mcm=("current_live_capacity_mcm","sum"), rainfall_daily_mm=("rainfall_daily_mm","sum")).sort_values("observed_at")
        a, b = st.columns([1.2,.8])
        a.altair_chart(alt.Chart(timeline).mark_line(point=True).encode(x="observed_at:T", y=alt.Y("avg_filling_percent:Q", title="Average filling (%)"), tooltip=list(timeline.columns)).properties(height=350), use_container_width=True)
        b.altair_chart(alt.Chart(timeline).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(x="observed_at:T", y=alt.Y("rainfall_daily_mm:Q", title="Daily rainfall (mm)"), tooltip=list(timeline.columns)).properties(height=350), use_container_width=True)
        st.dataframe(timeline, use_container_width=True, hide_index=True)

with reservoir_tab:
    st.subheader("Reservoir Trends")
    if reservoir_view.empty:
        st.info("No reservoir data.")
    else:
        metric = st.selectbox("Metric", ["filling_percent", "water_level_m", "current_live_capacity_mcm", "rainfall_daily_mm", "frl_gap_m"])
        options = sorted(reservoir_view["reservoir_name"].dropna().unique())
        chosen = st.multiselect("Reservoirs", options, default=options[:min(8, len(options))])
        df = reservoir_view[reservoir_view["reservoir_name"].isin(chosen)].dropna(subset=[metric])
        st.altair_chart(alt.Chart(df).mark_line(point=True).encode(x="observed_at:T", y=f"{metric}:Q", color="reservoir_name:N", tooltip=["reservoir_name","district","observed_at",metric]).properties(height=430), use_container_width=True)

with river_tab:
    st.subheader("River Gauge Trends")
    if river_view.empty:
        st.info("No river gauge data.")
    else:
        metric = st.selectbox("River metric", ["water_level_m", "danger_gap_m"])
        options = sorted(river_view["gauge_station"].dropna().unique())
        chosen = st.multiselect("Gauge stations", options, default=options[:min(8, len(options))])
        df = river_view[river_view["gauge_station"].isin(chosen)].dropna(subset=[metric])
        st.altair_chart(alt.Chart(df).mark_line(point=True).encode(x="observed_at:T", y=f"{metric}:Q", color="gauge_station:N", tooltip=["river_name","gauge_station","district","observed_at",metric]).properties(height=430), use_container_width=True)
        st.dataframe(latest_riv.sort_values("danger_gap_m", na_position="last"), use_container_width=True, hide_index=True)

with gates_tab:
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
