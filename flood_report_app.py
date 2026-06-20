from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
BUNDLED_SITE_PACKAGES = Path(
    r"C:\Users\Welcome\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages"
)
if BUNDLED_SITE_PACKAGES.exists() and str(BUNDLED_SITE_PACKAGES) not in sys.path:
    sys.path.append(str(BUNDLED_SITE_PACKAGES))

from flood_report_parser import parse_pdf  # noqa: E402


st.set_page_config(page_title="MP WRD Flood Report Capture", layout="wide")

st.markdown(
    """
    <style>
    :root {
        --bg: #f3f6f9;
        --panel: #ffffff;
        --panel-soft: #f8fafc;
        --line: #d8e0ea;
        --line-strong: #b9c7d6;
        --text: #111827;
        --muted: #637083;
        --blue: #1f5fbf;
        --green: #0f766e;
        --amber: #b7791f;
        --red: #b42318;
    }
    html, body, [data-testid="stAppViewContainer"] {
        background: var(--bg);
    }
    .block-container {
        max-width: 1540px;
        padding-top: 1rem;
        padding-bottom: 2rem;
    }
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid var(--line);
    }
    h1, h2, h3, p, label {
        color: var(--text);
        letter-spacing: 0 !important;
    }
    h2 {
        font-size: 1.05rem !important;
    }
    .masthead {
        border: 1px solid var(--line);
        background: var(--panel);
        border-radius: 8px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.85rem;
        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
    }
    .masthead-top {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        align-items: flex-start;
    }
    .title {
        font-size: 1.45rem;
        line-height: 1.15;
        font-weight: 800;
    }
    .subtitle {
        color: var(--muted);
        font-size: 0.86rem;
        margin-top: 0.24rem;
    }
    .meta-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
        justify-content: flex-end;
    }
    .meta {
        border: 1px solid var(--line);
        background: var(--panel-soft);
        border-radius: 6px;
        padding: 0.35rem 0.48rem;
        color: #334155;
        font-size: 0.74rem;
        white-space: nowrap;
    }
    div[data-testid="stMetric"] {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 0.72rem 0.78rem;
        min-height: 80px;
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
    </style>
    """,
    unsafe_allow_html=True,
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
    selected_name = st.selectbox("Captured report", [path.name for path in dirs], index=len(dirs) - 1)
    selected_dir = APP_DIR / selected_name


meta, river_master, reservoir_master, rivers, reservoirs, gates = load_dataset(selected_dir)
latest_rivers = latest_by_asset(rivers, "gauge_station")
latest_reservoirs = latest_by_asset(reservoirs, "reservoir_name")
open_gates = gates[gates["gate_opened_count"].fillna(0).astype(float) > 0] if not gates.empty else gates

report_label = f"{meta.get('report_date', '-')} {meta.get('report_time', '-')}"
st.markdown(
    f"""
    <div class="masthead">
      <div class="masthead-top">
        <div>
          <div class="title">MP WRD Flood Report Capture</div>
          <div class="subtitle">Daily river, reservoir, rainfall, and gate-position data extracted from government PDF reports.</div>
        </div>
        <div class="meta-row">
          <div class="meta">Report {report_label}</div>
          <div class="meta">{meta.get('extraction_method', 'embedded_text')}</div>
          <div class="meta">{meta.get('source_filename', selected_name)}</div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.info(
    "Asset names repeat in the observation-history tables because each PDF row contains multiple time columns. "
    "The master lists below keep one unique river gauge or reservoir record; the observation tables keep one row per asset per observed time."
)

kpi_cols = st.columns(6)
kpi_cols[0].metric("River Stations", fmt_number(latest_rivers["gauge_station"].nunique() if not latest_rivers.empty else 0))
kpi_cols[1].metric("Reservoirs", fmt_number(latest_reservoirs["reservoir_name"].nunique() if not latest_reservoirs.empty else 0))
kpi_cols[2].metric("Avg Filling", fmt_number(latest_reservoirs["filling_percent"].mean() if not latest_reservoirs.empty else None, "%"))
kpi_cols[3].metric("Max Filling", fmt_number(latest_reservoirs["filling_percent"].max() if not latest_reservoirs.empty else None, "%"))
kpi_cols[4].metric("Open Gate Sites", fmt_number(open_gates["reservoir_name"].nunique() if not open_gates.empty else 0))
kpi_cols[5].metric("Rows Captured", fmt_number(len(rivers) + len(reservoirs) + len(gates)))

tab_overview, tab_rivers, tab_reservoirs, tab_graphs, tab_gates, tab_exports = st.tabs(
    ["Overview", "Rivers", "Reservoirs", "Reservoir Graphs", "Gates", "Exports"]
)

with tab_overview:
    left, right = st.columns([1.15, 0.85])
    with left:
        st.subheader("Reservoir Filling")
        if latest_reservoirs.empty:
            st.info("No reservoir rows captured for this report.")
        else:
            top_fill = latest_reservoirs.nlargest(15, "filling_percent")[
                ["reservoir_name", "district", "filling_percent", "water_level_m", "rainfall_daily_mm"]
            ]
            chart = (
                alt.Chart(top_fill)
                .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
                .encode(
                    x=alt.X("filling_percent:Q", title="Filling %"),
                    y=alt.Y("reservoir_name:N", sort="-x", title="Reservoir"),
                    color=alt.Color("district:N", legend=None),
                    tooltip=["reservoir_name", "district", "filling_percent", "water_level_m", "rainfall_daily_mm"],
                )
                .properties(height=420)
            )
            st.altair_chart(chart, use_container_width=True)
    with right:
        st.subheader("Open Gate Operations")
        if open_gates.empty:
            st.markdown('<div class="panel-note">No reservoir gate openings are recorded in the selected report.</div>', unsafe_allow_html=True)
        else:
            st.dataframe(
                open_gates[
                    [
                        "reservoir_name",
                        "district",
                        "gate_opened_count",
                        "opening_m",
                        "gate_opening_date",
                        "gate_opening_time",
                        "discharge_cumecs",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

    st.subheader("District Summary")
    if not latest_reservoirs.empty:
        district_summary = (
            latest_reservoirs.groupby("district", as_index=False)
            .agg(
                reservoirs=("reservoir_name", "nunique"),
                avg_filling_percent=("filling_percent", "mean"),
                max_filling_percent=("filling_percent", "max"),
                daily_rainfall_mm=("rainfall_daily_mm", "sum"),
            )
            .sort_values("avg_filling_percent", ascending=False)
        )
        st.dataframe(district_summary, use_container_width=True, hide_index=True)

with tab_rivers:
    st.subheader("River Gauge Data")
    st.markdown(
        '<div class="panel-note">Use Latest snapshot for one row per river gauge. Observation history intentionally repeats the same gauge once per time reading.</div>',
        unsafe_allow_html=True,
    )
    river_mode = st.radio(
        "River view",
        ["Latest snapshot", "Master list", "Observation history"],
        horizontal=True,
    )
    river_filter = st.multiselect(
        "District",
        sorted(rivers["district"].dropna().unique()) if not rivers.empty else [],
        key="river_district",
    )
    if river_mode == "Latest snapshot":
        river_view = latest_rivers.copy()
    elif river_mode == "Master list":
        river_view = river_master.copy()
    else:
        river_view = rivers.copy()
    if river_filter:
        river_view = river_view[river_view["district"].isin(river_filter)]
    st.dataframe(river_view, use_container_width=True, hide_index=True)

    if not rivers.empty:
        station = st.selectbox("Trend station", sorted(rivers["gauge_station"].dropna().unique()))
        trend = rivers[rivers["gauge_station"] == station].sort_values("observed_at")
        st.line_chart(trend.set_index("observed_at")["water_level_m"])

with tab_reservoirs:
    st.subheader("Reservoir Data")
    st.markdown(
        '<div class="panel-note">Use Latest snapshot for one row per reservoir. Observation history intentionally repeats each reservoir once per observed time.</div>',
        unsafe_allow_html=True,
    )
    reservoir_mode = st.radio(
        "Reservoir view",
        ["Latest snapshot", "Master list", "Observation history"],
        horizontal=True,
    )
    reservoir_filter = st.multiselect(
        "Reservoir district",
        sorted(reservoirs["district"].dropna().unique()) if not reservoirs.empty else [],
        key="reservoir_district",
    )
    if reservoir_mode == "Latest snapshot":
        reservoir_view = latest_reservoirs.copy()
    elif reservoir_mode == "Master list":
        reservoir_view = reservoir_master.copy()
    else:
        reservoir_view = reservoirs.copy()
    if reservoir_filter:
        reservoir_view = reservoir_view[reservoir_view["district"].isin(reservoir_filter)]
    st.dataframe(reservoir_view, use_container_width=True, hide_index=True)

    if not reservoirs.empty:
        reservoir = st.selectbox("Reservoir trend", sorted(reservoirs["reservoir_name"].dropna().unique()))
        trend = reservoirs[reservoirs["reservoir_name"] == reservoir].sort_values("observed_at")
        st.line_chart(trend.set_index("observed_at")["water_level_m"])

with tab_graphs:
    st.subheader("Reservoir Graphs")
    st.markdown(
        '<div class="panel-note">Switch graph mode, metric, time slot, district, or reservoir selection to inspect all reservoir readings captured from the PDF.</div>',
        unsafe_allow_html=True,
    )

    if reservoirs.empty:
        st.info("No reservoir observations are available for graphing.")
    else:
        graph_data = reservoirs.copy()
        graph_data["frl_gap_m"] = graph_data["frl_m"] - graph_data["water_level_m"]
        metric_labels = {
            "Water Level": "water_level_m",
            "Filling %": "filling_percent",
            "Current Storage": "current_live_capacity_mcm",
            "Rainfall": "rainfall_daily_mm",
            "FRL Gap": "frl_gap_m",
        }
        metric_units = {
            "water_level_m": "m",
            "filling_percent": "%",
            "current_live_capacity_mcm": "MCM",
            "rainfall_daily_mm": "mm",
            "frl_gap_m": "m",
        }
        graph_mode = st.radio(
            "Graph mode",
            ["All Reservoirs", "Top / Bottom", "District View", "Compare Selected", "Single Trend", "Rainfall vs Filling"],
            horizontal=True,
            key="reservoir_graph_mode",
        )
        control_cols = st.columns([1.05, 1.05, 1.2, 1.1])
        metric_label = control_cols[0].selectbox("Metric", list(metric_labels), index=1)
        metric_col = metric_labels[metric_label]
        chart_type = control_cols[1].radio("Chart type", ["Bar", "Line", "Scatter"], horizontal=True, key="reservoir_chart_type")
        district_options = ["All districts"] + sorted(graph_data["district"].dropna().unique())
        selected_district = control_cols[2].selectbox("District", district_options, key="reservoir_graph_district")
        observed_options = sorted(graph_data["observed_at"].dropna().unique())
        observed_labels = [pd.Timestamp(value).strftime("%d %b %Y %I:%M %p") for value in observed_options]
        selected_observed_label = control_cols[3].selectbox(
            "Time slot",
            observed_labels,
            index=max(0, len(observed_labels) - 1),
            key="reservoir_graph_time",
        )
        selected_observed = observed_options[observed_labels.index(selected_observed_label)]

        snapshot = graph_data[graph_data["observed_at"] == selected_observed].copy()
        if selected_district != "All districts":
            snapshot = snapshot[snapshot["district"] == selected_district]

        if graph_mode == "All Reservoirs":
            plot_df = snapshot.dropna(subset=[metric_col]).sort_values(metric_col, ascending=False)
            st.caption(f"{len(plot_df)} reservoirs at {selected_observed_label}, sorted by {metric_label}.")
            chart = reservoir_snapshot_chart(
                plot_df,
                metric_col,
                metric_label,
                metric_units[metric_col],
                chart_type,
                max(420, min(1200, len(plot_df) * 22)),
            )
            st.altair_chart(chart, use_container_width=True)

        elif graph_mode == "Top / Bottom":
            rank_cols = st.columns([1, 1])
            rank_view = rank_cols[0].radio("Ranking", ["Top", "Bottom"], horizontal=True, key="reservoir_rank_view")
            rank_count = rank_cols[1].slider("Number of reservoirs", min_value=5, max_value=25, value=10, step=5)
            plot_df = snapshot.dropna(subset=[metric_col])
            plot_df = plot_df.nlargest(rank_count, metric_col) if rank_view == "Top" else plot_df.nsmallest(rank_count, metric_col)
            st.caption(f"{rank_view} {len(plot_df)} reservoirs by {metric_label}.")
            chart = reservoir_snapshot_chart(
                plot_df,
                metric_col,
                metric_label,
                metric_units[metric_col],
                chart_type,
                430,
                "-x" if rank_view == "Top" else "x",
            )
            st.altair_chart(chart, use_container_width=True)

        elif graph_mode == "District View":
            if selected_district == "All districts":
                st.warning("Select a district to view all reservoirs in that district.")
            else:
                plot_df = snapshot.dropna(subset=[metric_col]).sort_values(metric_col, ascending=False)
                st.caption(f"{selected_district}: {len(plot_df)} reservoirs.")
                chart = reservoir_snapshot_chart(
                    plot_df,
                    metric_col,
                    metric_label,
                    metric_units[metric_col],
                    chart_type,
                    max(320, len(plot_df) * 34),
                )
                st.altair_chart(chart, use_container_width=True)

        elif graph_mode == "Compare Selected":
            reservoir_options = sorted(graph_data["reservoir_name"].dropna().unique())
            default_selection = [name for name in ["Bansagar", "Gandhisagar", "Kolar", "Tawa"] if name in reservoir_options]
            selected_reservoirs = st.multiselect(
                "Reservoirs to compare",
                reservoir_options,
                default=default_selection or reservoir_options[: min(4, len(reservoir_options))],
            )
            plot_df = graph_data[graph_data["reservoir_name"].isin(selected_reservoirs)].dropna(subset=[metric_col])
            if selected_district != "All districts":
                plot_df = plot_df[plot_df["district"] == selected_district]
            st.caption(f"{len(selected_reservoirs)} selected reservoirs across available PDF time slots.")
            chart = (
                alt.Chart(plot_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("observed_at:T", title="Observed time"),
                    y=alt.Y(f"{metric_col}:Q", title=f"{metric_label} ({metric_units[metric_col]})"),
                    color=alt.Color("reservoir_name:N", title="Reservoir"),
                    tooltip=["reservoir_name", "district", "observed_at", metric_col],
                )
                .properties(height=430)
            )
            st.altair_chart(chart, use_container_width=True)

        elif graph_mode == "Single Trend":
            reservoir_options = sorted(graph_data["reservoir_name"].dropna().unique())
            selected_reservoir = st.selectbox("Reservoir", reservoir_options, key="reservoir_single_trend")
            plot_df = graph_data[graph_data["reservoir_name"] == selected_reservoir].dropna(subset=[metric_col])
            chart = (
                alt.Chart(plot_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("observed_at:T", title="Observed time"),
                    y=alt.Y(f"{metric_col}:Q", title=f"{metric_label} ({metric_units[metric_col]})"),
                    tooltip=["reservoir_name", "district", "observed_at", metric_col],
                )
                .properties(height=430)
            )
            st.altair_chart(chart, use_container_width=True)
            st.dataframe(plot_df.sort_values("observed_at"), use_container_width=True, hide_index=True)

        else:
            plot_df = snapshot.dropna(subset=["rainfall_daily_mm", "filling_percent"])
            st.caption("Daily rainfall against filling percentage for the selected time slot.")
            chart = (
                alt.Chart(plot_df)
                .mark_circle(size=86, opacity=0.78)
                .encode(
                    x=alt.X("rainfall_daily_mm:Q", title="Daily rainfall (mm)"),
                    y=alt.Y("filling_percent:Q", title="Filling %"),
                    color=alt.Color("district:N", title="District"),
                    tooltip=["reservoir_name", "district", "rainfall_daily_mm", "filling_percent", "water_level_m"],
                )
                .properties(height=470)
            )
            st.altair_chart(chart, use_container_width=True)

with tab_gates:
    st.subheader("Reservoir Gate Positions")
    show_open_only = st.toggle("Show only open gates", value=False)
    gate_view = open_gates if show_open_only else gates
    st.dataframe(gate_view, use_container_width=True, hide_index=True)

with tab_exports:
    st.subheader("Captured Data Files")
    st.markdown(f'<div class="panel-note">Selected parsed folder: {selected_dir}</div>', unsafe_allow_html=True)
    export_cols = st.columns(3)
    export_cols[0].download_button(
        "Download river CSV",
        data=(selected_dir / "river_water_level_observations.csv").read_bytes(),
        file_name="river_water_level_observations.csv",
        mime="text/csv",
    )
    export_cols[1].download_button(
        "Download reservoir CSV",
        data=(selected_dir / "reservoir_status_observations.csv").read_bytes(),
        file_name="reservoir_status_observations.csv",
        mime="text/csv",
    )
    export_cols[2].download_button(
        "Download gates CSV",
        data=(selected_dir / "reservoir_gate_observations.csv").read_bytes(),
        file_name="reservoir_gate_observations.csv",
        mime="text/csv",
    )
    master_cols = st.columns(2)
    if (selected_dir / "river_gauge_stations.csv").exists():
        master_cols[0].download_button(
            "Download river master CSV",
            data=(selected_dir / "river_gauge_stations.csv").read_bytes(),
            file_name="river_gauge_stations.csv",
            mime="text/csv",
        )
    if (selected_dir / "reservoirs.csv").exists():
        master_cols[1].download_button(
            "Download reservoir master CSV",
            data=(selected_dir / "reservoirs.csv").read_bytes(),
            file_name="reservoirs.csv",
            mime="text/csv",
        )
