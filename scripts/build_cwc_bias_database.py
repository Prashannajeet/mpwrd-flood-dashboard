from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path

import pandas as pd


def load_inputs(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = pd.read_csv(input_dir / "cwc_daily_discharge_clean.csv", parse_dates=["date"])
    station_summary = pd.read_csv(input_dir / "cwc_station_summary.csv")
    linkage = pd.read_csv(input_dir / "cwc_station_forecast_linkage_candidates.csv")
    forecast_inventory = pd.read_csv(input_dir / "forecast_station_inventory.csv")
    return daily, station_summary, linkage, forecast_inventory


def build_station_thresholds(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    daily["month"] = daily["date"].dt.month
    base_aggs = {
        "records": ("discharge_cms_mean", "size"),
        "mean_flow_cms": ("discharge_cms_mean", "mean"),
        "median_flow_cms": ("discharge_cms_mean", "median"),
        "max_flow_cms": ("discharge_cms_mean", "max"),
        "p75_flow_cms": ("discharge_cms_mean", lambda s: s.quantile(0.75)),
        "p90_flow_cms": ("discharge_cms_mean", lambda s: s.quantile(0.90)),
        "p95_flow_cms": ("discharge_cms_mean", lambda s: s.quantile(0.95)),
        "p99_flow_cms": ("discharge_cms_mean", lambda s: s.quantile(0.99)),
    }
    all_season = (
        daily.groupby(["station_name", "district", "river", "basin"], as_index=False)
        .agg(**base_aggs)
        .assign(period_type="All season", month=0)
    )
    monthly = (
        daily.groupby(["station_name", "district", "river", "basin", "month"], as_index=False)
        .agg(**base_aggs)
        .assign(period_type="Monthly")
    )
    thresholds = pd.concat([all_season, monthly], ignore_index=True)
    number_cols = [col for col in thresholds.columns if col.endswith("_cms")]
    thresholds[number_cols] = thresholds[number_cols].round(3)
    return thresholds[
        [
            "station_name",
            "district",
            "river",
            "basin",
            "period_type",
            "month",
            "records",
            "mean_flow_cms",
            "median_flow_cms",
            "max_flow_cms",
            "p75_flow_cms",
            "p90_flow_cms",
            "p95_flow_cms",
            "p99_flow_cms",
        ]
    ]


def build_training_station_flags(station_summary: pd.DataFrame) -> pd.DataFrame:
    station_summary = station_summary.copy()
    station_summary["training_ready"] = (
        (pd.to_numeric(station_summary["daily_rows"], errors="coerce") >= 365 * 3)
        & (pd.to_numeric(station_summary["nonzero_pct"], errors="coerce") >= 10)
        & (pd.to_numeric(station_summary["missing_pct"], errors="coerce") <= 35)
    )
    station_summary["data_quality_class"] = "Needs Review"
    station_summary.loc[
        (station_summary["training_ready"])
        & (pd.to_numeric(station_summary["missing_pct"], errors="coerce") <= 5)
        & (pd.to_numeric(station_summary["nonzero_pct"], errors="coerce") >= 70),
        "data_quality_class",
    ] = "High"
    station_summary.loc[
        (station_summary["training_ready"])
        & (station_summary["data_quality_class"].eq("Needs Review")),
        "data_quality_class",
    ] = "Moderate"
    return station_summary


def normalize_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "approved"}


def build_linkage_review_template(linkage: pd.DataFrame, review_path: Path) -> pd.DataFrame:
    top = linkage[linkage["candidate_rank"].eq(1)].copy()
    top["auto_approved"] = pd.to_numeric(top["linkage_score"], errors="coerce").ge(0.65)
    top["linkage_confidence"] = "Needs Review"
    top.loc[top["linkage_score"].ge(0.80), "linkage_confidence"] = "High"
    top.loc[top["linkage_score"].between(0.65, 0.80, inclusive="left"), "linkage_confidence"] = "Moderate"
    review = top[
        [
            "station_code",
            "forecast_station_name",
            "forecast_district",
            "forecast_river",
            "cwc_station_name",
            "cwc_district",
            "cwc_river",
            "cwc_basin",
            "cwc_to_forecast_distance_km",
            "name_similarity_score",
            "linkage_score",
            "linkage_confidence",
            "auto_approved",
            "linked_comid",
            "streamorder",
        ]
    ].copy()
    review["manual_approved"] = review["auto_approved"]
    review["manual_cwc_station_name"] = review["cwc_station_name"]
    review["review_status"] = review["linkage_confidence"].where(review["auto_approved"], "Needs Review")
    review["review_notes"] = ""
    review = review.sort_values(["manual_approved", "linkage_score"], ascending=[False, False])
    if not review_path.exists():
        review.to_csv(review_path, index=False)
    return review


def build_approved_linkage(linkage: pd.DataFrame, review_path: Path) -> pd.DataFrame:
    template = build_linkage_review_template(linkage, review_path)
    if review_path.exists():
        review = pd.read_csv(review_path)
    else:
        review = template
    if "manual_approved" not in review:
        review["manual_approved"] = review.get("auto_approved", False)
    if "manual_cwc_station_name" not in review:
        review["manual_cwc_station_name"] = review.get("cwc_station_name", "")
    if "review_status" not in review:
        review["review_status"] = review.get("linkage_confidence", "Needs Review")
    if "review_notes" not in review:
        review["review_notes"] = ""
    review["manual_approved"] = review["manual_approved"].map(normalize_bool)
    review["effective_cwc_station_name"] = review["manual_cwc_station_name"].fillna("").astype(str).str.strip()
    review.loc[review["effective_cwc_station_name"].eq(""), "effective_cwc_station_name"] = review["cwc_station_name"]
    review["linkage_source"] = review["manual_approved"].map(lambda value: "Manual/auto approved" if value else "Pending review")
    return review.sort_values(["manual_approved", "linkage_score"], ascending=[False, False])


def build_current_forecast_context(input_dir: Path, approved_linkage: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    forecast_path = input_dir.parent / "gd_site_online_forecasts.csv"
    if not forecast_path.exists():
        return pd.DataFrame()
    forecast = pd.read_csv(forecast_path, parse_dates=["forecast_time"])
    now_rows = forecast.sort_values("forecast_time").drop_duplicates("station_code", keep="first").copy()
    linked = approved_linkage[
        [
            "station_code",
            "effective_cwc_station_name",
            "cwc_river",
            "cwc_basin",
            "cwc_to_forecast_distance_km",
            "linkage_score",
            "linkage_confidence",
            "review_status",
            "manual_approved",
            "auto_approved",
            "linkage_source",
        ]
    ].rename(columns={"effective_cwc_station_name": "linked_cwc_station"})
    context = now_rows.merge(linked, on="station_code", how="left")
    threshold_cols = thresholds[thresholds["period_type"].eq("All season")].rename(
        columns={
            "station_name": "linked_cwc_station",
            "p75_flow_cms": "historical_p75_cms",
            "p90_flow_cms": "historical_p90_cms",
            "p95_flow_cms": "historical_p95_cms",
            "p99_flow_cms": "historical_p99_cms",
            "median_flow_cms": "historical_median_cms",
            "max_flow_cms": "historical_max_cms",
        }
    )
    context = context.merge(
        threshold_cols[
            [
                "linked_cwc_station",
                "historical_median_cms",
                "historical_p75_cms",
                "historical_p90_cms",
                "historical_p95_cms",
                "historical_p99_cms",
                "historical_max_cms",
            ]
        ],
        on="linked_cwc_station",
        how="left",
    )
    context["flow_percentile_status"] = "Unlinked"
    flow = pd.to_numeric(context["meanflow_cms"], errors="coerce")
    context.loc[flow.notna() & context["historical_p75_cms"].notna(), "flow_percentile_status"] = "Normal"
    context.loc[flow.ge(context["historical_p75_cms"]), "flow_percentile_status"] = "Watch"
    context.loc[flow.ge(context["historical_p90_cms"]), "flow_percentile_status"] = "Warning"
    context.loc[flow.ge(context["historical_p95_cms"]), "flow_percentile_status"] = "Critical"
    return context


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if any(pd.isna(v) for v in [lat1, lon1, lat2, lon2]):
        return math.nan
    radius_km = 6371.0088
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def confidence_from_correlation(correlation: float, overlap_days: int) -> str:
    if pd.isna(correlation):
        return "Needs Review"
    if correlation >= 0.85 and overlap_days >= 365 * 3:
        return "High"
    if correlation >= 0.70 and overlap_days >= 365 * 2:
        return "Moderate"
    if correlation >= 0.55 and overlap_days >= 365:
        return "Screening"
    return "Needs Review"


def build_gauge_travel_time_correlations(
    daily: pd.DataFrame,
    station_summary: pd.DataFrame,
    max_lag_days: int = 7,
    min_overlap_days: int = 365,
    min_correlation: float = 0.55,
) -> pd.DataFrame:
    required_cols = {"station_name", "date", "discharge_cms_mean", "river", "basin"}
    if daily.empty or not required_cols.issubset(daily.columns):
        return pd.DataFrame()

    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily["discharge_cms_mean"] = pd.to_numeric(daily["discharge_cms_mean"], errors="coerce")
    daily = daily.dropna(subset=["date", "station_name", "discharge_cms_mean"])
    station_lookup = station_summary.set_index("station_name").to_dict("index")
    rows = []

    for (basin, river), group in daily.groupby(["basin", "river"], dropna=False):
        stations = sorted(group["station_name"].dropna().astype(str).unique())
        if len(stations) < 2:
            continue
        pivot = (
            group.pivot_table(index="date", columns="station_name", values="discharge_cms_mean", aggfunc="mean")
            .sort_index()
        )
        flow_change = pivot.diff()
        for source_station in stations:
            source_flow = pivot.get(source_station)
            source_change = flow_change.get(source_station)
            if source_flow is None or source_flow.dropna().shape[0] < min_overlap_days:
                continue
            for target_station in stations:
                if source_station == target_station:
                    continue
                target_flow = pivot.get(target_station)
                target_change = flow_change.get(target_station)
                if target_flow is None or target_flow.dropna().shape[0] < min_overlap_days:
                    continue

                best = None
                for lag_days in range(1, max_lag_days + 1):
                    comparison = pd.concat(
                        [
                            source_flow.shift(lag_days).rename("source_flow_lagged"),
                            target_flow.rename("target_flow"),
                            source_change.shift(lag_days).rename("source_change_lagged"),
                            target_change.rename("target_change"),
                        ],
                        axis=1,
                    ).dropna()
                    if len(comparison) < min_overlap_days:
                        continue
                    flow_corr = comparison["source_flow_lagged"].corr(comparison["target_flow"])
                    change_corr = comparison["source_change_lagged"].corr(comparison["target_change"])
                    if pd.isna(flow_corr):
                        continue
                    combined_score = (0.75 * flow_corr) + (0.25 * change_corr if not pd.isna(change_corr) else 0.0)
                    candidate = {
                        "source_station": source_station,
                        "target_station": target_station,
                        "basin": basin,
                        "river": river,
                        "best_lag_days": lag_days,
                        "lead_time_hours": lag_days * 24,
                        "overlap_days": int(len(comparison)),
                        "flow_correlation": round(float(flow_corr), 4),
                        "change_correlation": round(float(change_corr), 4) if not pd.isna(change_corr) else math.nan,
                        "combined_correlation_score": round(float(combined_score), 4),
                    }
                    if best is None or candidate["combined_correlation_score"] > best["combined_correlation_score"]:
                        best = candidate

                if not best or best["flow_correlation"] < min_correlation:
                    continue
                source_meta = station_lookup.get(source_station, {})
                target_meta = station_lookup.get(target_station, {})
                distance_km = haversine_km(
                    source_meta.get("latitude"),
                    source_meta.get("longitude"),
                    target_meta.get("latitude"),
                    target_meta.get("longitude"),
                )
                best["source_district"] = source_meta.get("district", "")
                best["target_district"] = target_meta.get("district", "")
                best["source_latitude"] = source_meta.get("latitude", math.nan)
                best["source_longitude"] = source_meta.get("longitude", math.nan)
                best["target_latitude"] = target_meta.get("latitude", math.nan)
                best["target_longitude"] = target_meta.get("longitude", math.nan)
                best["straight_distance_km"] = round(distance_km, 3) if not pd.isna(distance_km) else math.nan
                best["travel_confidence"] = confidence_from_correlation(best["flow_correlation"], best["overlap_days"])
                best["method_note"] = "Daily CWC discharge cross-correlation; refine with 3-hour data and drainage chainage when available."
                rows.append(best)

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    result = result.sort_values(
        ["travel_confidence", "combined_correlation_score", "overlap_days"],
        ascending=[True, False, False],
    )
    confidence_order = {"High": 0, "Moderate": 1, "Screening": 2, "Needs Review": 3}
    result["_confidence_order"] = result["travel_confidence"].map(confidence_order).fillna(9)
    result = result.sort_values(["_confidence_order", "combined_correlation_score"], ascending=[True, False]).drop(columns=["_confidence_order"])
    return result


def write_database(output_db: Path, tables: dict[str, pd.DataFrame]) -> None:
    output_db.parent.mkdir(parents=True, exist_ok=True)
    if output_db.exists():
        output_db.unlink()
    with sqlite3.connect(output_db) as con:
        for name, frame in tables.items():
            frame.to_sql(name, con, index=False, if_exists="replace")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cwc_daily_station_date ON cwc_daily_discharge(station_name, date)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cwc_threshold_station ON cwc_flow_thresholds(station_name, period_type, month)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_linkage_station_code ON gd_cwc_station_linkage(station_code)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_current_context_station_code ON current_forecast_cwc_context(station_code)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_gauge_travel_source ON gauge_travel_time_correlations(source_station)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_gauge_travel_target ON gauge_travel_time_correlations(target_station)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build V02 CWC bias-correction SQLite database.")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-db", required=True, type=Path)
    args = parser.parse_args()

    daily, station_summary, linkage, forecast_inventory = load_inputs(args.input_dir)
    station_summary = build_training_station_flags(station_summary)
    thresholds = build_station_thresholds(daily)
    review_path = args.input_dir / "gd_cwc_station_linkage_review.csv"
    approved_linkage = build_approved_linkage(linkage, review_path)
    current_context = build_current_forecast_context(args.input_dir, approved_linkage, thresholds)
    gauge_travel = build_gauge_travel_time_correlations(daily, station_summary)

    tables = {
        "cwc_daily_discharge": daily,
        "cwc_station_summary": station_summary,
        "gd_cwc_station_linkage_candidates": linkage,
        "gd_cwc_station_linkage": approved_linkage,
        "forecast_station_inventory": forecast_inventory,
        "cwc_flow_thresholds": thresholds,
        "current_forecast_cwc_context": current_context,
        "gauge_travel_time_correlations": gauge_travel,
    }
    write_database(args.output_db, tables)

    summary = {
        "output_db": str(args.output_db),
        "cwc_daily_rows": int(len(daily)),
        "cwc_stations": int(station_summary["station_name"].nunique()),
        "training_ready_stations": int(station_summary["training_ready"].sum()),
        "linkage_rows": int(len(approved_linkage)),
        "auto_approved_links": int(approved_linkage["auto_approved"].sum()),
        "current_context_rows": int(len(current_context)),
        "gauge_travel_links": int(len(gauge_travel)),
        "high_confidence_travel_links": int(gauge_travel["travel_confidence"].eq("High").sum()) if not gauge_travel.empty else 0,
        "linkage_review_csv": str(review_path),
        "review_approved_links": int(approved_linkage["manual_approved"].sum()) if "manual_approved" in approved_linkage else 0,
    }
    (args.output_db.parent / "cwc_bias_database_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
