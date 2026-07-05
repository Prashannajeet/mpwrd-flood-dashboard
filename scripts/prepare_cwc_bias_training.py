from __future__ import annotations

import argparse
import json
import math
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


DATE_COL = "Data Acquisition Time"
FLOW_COL = "Manual Daily River Water Discharge (m3/sec)"


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


def normalized_name_score(left: str, right: str) -> float:
    left_norm = "".join(ch.lower() for ch in str(left) if ch.isalnum() or ch.isspace()).strip()
    right_norm = "".join(ch.lower() for ch in str(right) if ch.isalnum() or ch.isspace()).strip()
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def read_cwc_daily(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raw = pd.read_csv(path)
    raw[DATE_COL] = pd.to_datetime(raw[DATE_COL], dayfirst=True, errors="coerce")
    raw[FLOW_COL] = pd.to_numeric(raw[FLOW_COL], errors="coerce")
    raw["date"] = raw[DATE_COL].dt.date
    raw["timestamp"] = raw[DATE_COL]

    metadata_cols = [
        "Station",
        "Agency",
        "State",
        "District",
        "River",
        "Basin",
        "Tributary",
        "Latitude",
        "Longitude",
    ]
    for col in metadata_cols:
        if col not in raw.columns:
            raw[col] = pd.NA

    daily = (
        raw.groupby(["Station", "date"], as_index=False)
        .agg(
            station_name=("Station", "first"),
            agency=("Agency", "first"),
            state=("State", "first"),
            district=("District", "first"),
            river=("River", "first"),
            basin=("Basin", "first"),
            tributary=("Tributary", "first"),
            latitude=("Latitude", "first"),
            longitude=("Longitude", "first"),
            discharge_cms_mean=(FLOW_COL, "mean"),
            discharge_cms_max=(FLOW_COL, "max"),
            discharge_cms_min=(FLOW_COL, "min"),
            observations_in_day=(FLOW_COL, "size"),
            first_timestamp=("timestamp", "min"),
            last_timestamp=("timestamp", "max"),
        )
        .sort_values(["station_name", "date"])
    )
    daily["date"] = pd.to_datetime(daily["date"])
    daily["is_duplicate_day_aggregate"] = daily["observations_in_day"] > 1
    daily["discharge_is_zero"] = daily["discharge_cms_mean"].fillna(0).eq(0)

    station_rows = []
    for station, group in daily.groupby("station_name", dropna=False):
        dates = pd.to_datetime(group["date"]).sort_values()
        full_dates = pd.date_range(dates.min(), dates.max(), freq="D")
        missing_days = len(set(full_dates.date) - set(dates.dt.date))
        station_rows.append(
            {
                "station_name": station,
                "district": group["district"].dropna().astype(str).iloc[0] if group["district"].notna().any() else "",
                "river": group["river"].dropna().astype(str).iloc[0] if group["river"].notna().any() else "",
                "basin": group["basin"].dropna().astype(str).iloc[0] if group["basin"].notna().any() else "",
                "latitude": group["latitude"].dropna().iloc[0] if group["latitude"].notna().any() else math.nan,
                "longitude": group["longitude"].dropna().iloc[0] if group["longitude"].notna().any() else math.nan,
                "start_date": dates.min().date(),
                "end_date": dates.max().date(),
                "daily_rows": int(len(group)),
                "missing_days": int(missing_days),
                "missing_pct": round((missing_days / len(full_dates)) * 100, 2) if len(full_dates) else math.nan,
                "nonzero_days": int(group["discharge_cms_mean"].fillna(0).gt(0).sum()),
                "nonzero_pct": round(group["discharge_cms_mean"].fillna(0).gt(0).mean() * 100, 2),
                "mean_discharge_cms": round(float(group["discharge_cms_mean"].mean()), 3),
                "max_discharge_cms": round(float(group["discharge_cms_max"].max()), 3),
                "duplicate_day_aggregates": int(group["is_duplicate_day_aggregate"].sum()),
            }
        )
    station_summary = pd.DataFrame(station_rows).sort_values(["basin", "river", "station_name"])

    audit = {
        "source_file": str(path),
        "raw_rows": int(len(raw)),
        "daily_rows": int(len(daily)),
        "stations": int(daily["station_name"].nunique()),
        "districts": int(daily["district"].nunique()),
        "rivers": int(daily["river"].nunique()),
        "basins": int(daily["basin"].nunique()),
        "date_min": str(daily["date"].min().date()),
        "date_max": str(daily["date"].max().date()),
        "bad_dates": int(raw[DATE_COL].isna().sum()),
        "missing_discharge": int(raw[FLOW_COL].isna().sum()),
        "negative_discharge_rows": int(raw[FLOW_COL].lt(0).sum()),
        "exact_duplicate_station_timestamp_rows": int(raw.duplicated(["Station", DATE_COL]).sum()),
        "duplicate_station_date_rows": int(raw.duplicated(["Station", "date"]).sum()),
        "zero_discharge_pct": round(float(raw[FLOW_COL].fillna(0).eq(0).mean() * 100), 2),
    }
    return daily, station_summary, audit


def read_forecast_stations(app_data_dir: Path) -> pd.DataFrame:
    forecast_csv = app_data_dir / "gd_site_online_forecasts.csv"
    if forecast_csv.exists():
        forecast = pd.read_csv(forecast_csv)
        return (
            forecast[
                [
                    "station_code",
                    "station_name",
                    "district",
                    "river",
                    "tributary",
                    "latitude",
                    "longitude",
                    "comid",
                    "streamorder",
                    "distance_m",
                ]
            ]
            .drop_duplicates("station_code")
            .rename(
                columns={
                    "station_name": "forecast_station_name",
                    "district": "forecast_district",
                    "river": "forecast_river",
                    "tributary": "forecast_tributary",
                    "latitude": "forecast_latitude",
                    "longitude": "forecast_longitude",
                    "comid": "linked_comid",
                    "distance_m": "reach_link_distance_m",
                }
            )
        )

    geojson_path = app_data_dir / "gd_sites_swedes.geojson"
    if not geojson_path.exists():
        return pd.DataFrame()
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    rows = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        rows.append(
            {
                "station_code": props.get("Station Co"),
                "forecast_station_name": props.get("Station Na"),
                "forecast_district": props.get("District"),
                "forecast_river": props.get("River"),
                "forecast_tributary": props.get("Tributary"),
                "forecast_latitude": props.get("Lat"),
                "forecast_longitude": props.get("Long"),
                "linked_comid": pd.NA,
                "streamorder": pd.NA,
                "reach_link_distance_m": pd.NA,
            }
        )
    return pd.DataFrame(rows).drop_duplicates("station_code")


def build_linkage_candidates(cwc_stations: pd.DataFrame, forecast_stations: pd.DataFrame) -> pd.DataFrame:
    if cwc_stations.empty or forecast_stations.empty:
        return pd.DataFrame()

    candidates = []
    for _, cwc in cwc_stations.iterrows():
        scored = []
        for _, fcst in forecast_stations.iterrows():
            distance_km = haversine_km(
                cwc.get("latitude"),
                cwc.get("longitude"),
                fcst.get("forecast_latitude"),
                fcst.get("forecast_longitude"),
            )
            name_score = normalized_name_score(cwc.get("station_name", ""), fcst.get("forecast_station_name", ""))
            basin_match = str(cwc.get("basin", "")).strip().lower() == str(fcst.get("forecast_river", "")).strip().lower()
            river_match = str(cwc.get("river", "")).strip().lower() == str(fcst.get("forecast_river", "")).strip().lower()
            distance_score = max(0.0, 1.0 - min(distance_km, 100.0) / 100.0) if not pd.isna(distance_km) else 0.0
            combined_score = round((0.55 * distance_score) + (0.35 * name_score) + (0.10 if river_match or basin_match else 0.0), 4)
            scored.append(
                {
                    "cwc_station_name": cwc.get("station_name"),
                    "cwc_district": cwc.get("district"),
                    "cwc_river": cwc.get("river"),
                    "cwc_basin": cwc.get("basin"),
                    "cwc_latitude": cwc.get("latitude"),
                    "cwc_longitude": cwc.get("longitude"),
                    "cwc_start_date": cwc.get("start_date"),
                    "cwc_end_date": cwc.get("end_date"),
                    "cwc_daily_rows": cwc.get("daily_rows"),
                    "cwc_missing_pct": cwc.get("missing_pct"),
                    "cwc_nonzero_pct": cwc.get("nonzero_pct"),
                    "station_code": fcst.get("station_code"),
                    "forecast_station_name": fcst.get("forecast_station_name"),
                    "forecast_district": fcst.get("forecast_district"),
                    "forecast_river": fcst.get("forecast_river"),
                    "forecast_tributary": fcst.get("forecast_tributary"),
                    "forecast_latitude": fcst.get("forecast_latitude"),
                    "forecast_longitude": fcst.get("forecast_longitude"),
                    "linked_comid": fcst.get("linked_comid"),
                    "streamorder": fcst.get("streamorder"),
                    "reach_link_distance_m": fcst.get("reach_link_distance_m"),
                    "cwc_to_forecast_distance_km": round(distance_km, 3) if not pd.isna(distance_km) else math.nan,
                    "name_similarity_score": round(name_score, 4),
                    "river_or_basin_match": bool(river_match or basin_match),
                    "linkage_score": combined_score,
                }
            )
        top = sorted(scored, key=lambda item: item["linkage_score"], reverse=True)[:5]
        for rank, row in enumerate(top, start=1):
            row["candidate_rank"] = rank
            candidates.append(row)

    return pd.DataFrame(candidates).sort_values(["cwc_station_name", "candidate_rank"])


def write_bias_schema(path: Path) -> None:
    columns = [
        "station_id",
        "station_name",
        "linked_comid",
        "date",
        "forecast_issue_time",
        "lead_hours",
        "observed_discharge_cms",
        "raw_forecast_discharge_cms",
        "bias_cms",
        "bias_ratio",
        "corrected_forecast_discharge_cms",
        "rainfall_mm_lag_1d",
        "rainfall_mm_lag_3d",
        "observed_discharge_lag_1d",
        "observed_discharge_lag_3d",
        "observed_discharge_lag_7d",
        "season_month",
        "basin",
        "river",
        "district",
        "model_source",
        "data_split",
    ]
    pd.DataFrame(columns=columns).to_csv(path, index=False)


def write_report(path: Path, audit: dict, station_summary: pd.DataFrame, linkage: pd.DataFrame, forecast_stations: pd.DataFrame) -> None:
    strong_station_count = int(
        ((station_summary["daily_rows"] >= 365 * 3) & (station_summary["nonzero_pct"] >= 10)).sum()
    )
    high_conf_links = int((linkage["candidate_rank"].eq(1) & linkage["linkage_score"].ge(0.65)).sum()) if not linkage.empty else 0
    report = f"""# MP CWC Discharge Bias-Correction Training Readiness

## Historical Observation Dataset

- Source rows: {audit['raw_rows']:,}
- Clean daily station rows: {audit['daily_rows']:,}
- Stations: {audit['stations']}
- Districts: {audit['districts']}
- Rivers: {audit['rivers']}
- Basins: {audit['basins']}
- Date range: {audit['date_min']} to {audit['date_max']}
- Missing discharge rows: {audit['missing_discharge']}
- Duplicate station-date rows aggregated: {audit['duplicate_station_date_rows']:,}
- Exact duplicate station-timestamp rows: {audit['exact_duplicate_station_timestamp_rows']:,}
- Negative discharge rows requiring review: {audit['negative_discharge_rows']}
- Zero discharge share: {audit['zero_discharge_pct']}%

## Training Suitability

The CWC daily discharge file is suitable as the observed target dataset for discharge modelling and forecast bias correction. {strong_station_count} stations have at least three years of data and at least 10% non-zero observations, which is adequate for station-wise or pooled basin-wise training.

## Linkage With Existing Forecast System

- Forecast/GD stations available in the app cache: {len(forecast_stations)}
- Candidate CWC-to-forecast station links generated: {len(linkage)}
- High-confidence top links with score >= 0.65: {high_conf_links}

The current app forecast cache is a recent operational forecast window, while the CWC file is historical through 2025. Therefore, true historical bias correction requires a matching historical hindcast/reforecast archive for the same CWC dates. The generated linkage table provides the station/reach mapping needed to pull or attach those hindcast values.

## Recommended Bias-Correction Workflow

1. Use `cwc_daily_discharge_clean.csv` as the observation target.
2. Use `cwc_station_forecast_linkage_candidates.csv` to approve station-to-forecast reach matches.
3. Fetch or attach historical hindcast/reforecast discharge for the approved linked reaches.
4. Join observations and model values by station/reach, date, forecast issue time, and lead hours.
5. Train correction models:
   - Baseline: monthly median ratio and additive bias by station.
   - Operational: gradient boosting or TensorFlow model using lead time, month, basin, rainfall, upstream lag, and raw forecast.
   - Safety layer: monotonic clipping and return-period alert class validation.
6. Save corrected forecasts into the app database for dashboard display.

## Suggested Model Targets

- `observed_discharge_cms`: direct discharge target.
- `bias_cms = observed - raw_forecast`.
- `bias_ratio = observed / raw_forecast` with safe handling for very low flow.
- Alert class target: Normal, Watch, Warning, Critical based on observed return period or station thresholds.

## Generated Files

- `cwc_daily_discharge_clean.csv`
- `cwc_station_summary.csv`
- `cwc_station_forecast_linkage_candidates.csv`
- `bias_correction_training_schema.csv`
- `training_readiness_audit.json`
"""
    path.write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare MP CWC discharge observations for forecast bias correction.")
    parser.add_argument("--cwc-csv", required=True, type=Path)
    parser.add_argument("--app-data-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    daily, station_summary, audit = read_cwc_daily(args.cwc_csv)
    forecast_stations = read_forecast_stations(args.app_data_dir)
    linkage = build_linkage_candidates(station_summary, forecast_stations)

    daily.to_csv(args.output_dir / "cwc_daily_discharge_clean.csv", index=False)
    station_summary.to_csv(args.output_dir / "cwc_station_summary.csv", index=False)
    forecast_stations.to_csv(args.output_dir / "forecast_station_inventory.csv", index=False)
    linkage.to_csv(args.output_dir / "cwc_station_forecast_linkage_candidates.csv", index=False)
    write_bias_schema(args.output_dir / "bias_correction_training_schema.csv")
    (args.output_dir / "training_readiness_audit.json").write_text(
        json.dumps(audit, indent=2),
        encoding="utf-8",
    )
    write_report(args.output_dir / "bias_correction_training_readiness.md", audit, station_summary, linkage, forecast_stations)

    print(json.dumps({**audit, "output_dir": str(args.output_dir)}, indent=2))


if __name__ == "__main__":
    main()
