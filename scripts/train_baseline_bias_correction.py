from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd


TRAINING_COLUMNS = [
    "station_code",
    "linked_cwc_station",
    "linked_comid",
    "forecast_issue_time",
    "forecast_valid_time",
    "lead_hours",
    "raw_forecast_discharge_cms",
    "observed_discharge_cms",
    "basin",
    "river",
    "district",
]

FACTOR_COLUMNS = [
    "station_code",
    "linked_cwc_station",
    "month",
    "lead_bucket_hours",
    "training_rows",
    "median_ratio",
    "mean_ratio",
    "median_bias_cms",
    "mean_bias_cms",
    "mae_cms",
    "rmse_cms",
    "model_status",
]


def safe_ratio(observed: pd.Series, forecast: pd.Series) -> pd.Series:
    forecast = pd.to_numeric(forecast, errors="coerce")
    observed = pd.to_numeric(observed, errors="coerce")
    return observed.where(forecast.abs() > 0.001) / forecast.where(forecast.abs() > 0.001)


def ensure_training_template(db_path: Path, training_csv: Path) -> None:
    if training_csv.exists():
        return
    with sqlite3.connect(db_path) as con:
        linkages = pd.read_sql_query(
            """
            SELECT station_code, effective_cwc_station_name AS linked_cwc_station,
                   linked_comid, cwc_basin AS basin, cwc_river AS river, forecast_district AS district
            FROM gd_cwc_station_linkage
            WHERE manual_approved = 1
            ORDER BY linkage_score DESC
            """,
            con,
        )
    if linkages.empty:
        pd.DataFrame(columns=TRAINING_COLUMNS).to_csv(training_csv, index=False)
        return
    template = linkages.copy()
    for col in TRAINING_COLUMNS:
        if col not in template:
            template[col] = pd.NA
    template[TRAINING_COLUMNS].head(200).to_csv(training_csv, index=False)


def train_factors(training: pd.DataFrame) -> pd.DataFrame:
    if training.empty:
        return pd.DataFrame()
    frame = training.copy()
    frame["forecast_valid_time"] = pd.to_datetime(frame["forecast_valid_time"], errors="coerce")
    frame["lead_hours"] = pd.to_numeric(frame["lead_hours"], errors="coerce")
    frame["raw_forecast_discharge_cms"] = pd.to_numeric(frame["raw_forecast_discharge_cms"], errors="coerce")
    frame["observed_discharge_cms"] = pd.to_numeric(frame["observed_discharge_cms"], errors="coerce")
    frame = frame.dropna(subset=["station_code", "forecast_valid_time", "raw_forecast_discharge_cms", "observed_discharge_cms"])
    frame = frame[frame["raw_forecast_discharge_cms"].abs() > 0.001].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["month"] = frame["forecast_valid_time"].dt.month
    frame["lead_bucket_hours"] = frame["lead_hours"].fillna(0).clip(lower=0)
    frame["lead_bucket_hours"] = (frame["lead_bucket_hours"] / 24).round().astype(int) * 24
    frame["bias_cms"] = frame["observed_discharge_cms"] - frame["raw_forecast_discharge_cms"]
    frame["ratio"] = safe_ratio(frame["observed_discharge_cms"], frame["raw_forecast_discharge_cms"]).clip(0.05, 20)

    factors = (
        frame.groupby(["station_code", "linked_cwc_station", "month", "lead_bucket_hours"], dropna=False, as_index=False)
        .agg(
            training_rows=("ratio", "size"),
            median_ratio=("ratio", "median"),
            mean_ratio=("ratio", "mean"),
            median_bias_cms=("bias_cms", "median"),
            mean_bias_cms=("bias_cms", "mean"),
            mae_cms=("bias_cms", lambda s: s.abs().mean()),
            rmse_cms=("bias_cms", lambda s: float((s.pow(2).mean()) ** 0.5)),
        )
    )
    numeric_cols = ["median_ratio", "mean_ratio", "median_bias_cms", "mean_bias_cms", "mae_cms", "rmse_cms"]
    factors[numeric_cols] = factors[numeric_cols].round(4)
    factors["model_status"] = factors["training_rows"].map(lambda rows: "Trained" if rows >= 30 else "Low sample")
    return factors.sort_values(["station_code", "month", "lead_bucket_hours"])


def apply_factors(db_path: Path, factors: pd.DataFrame) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        current = pd.read_sql_query(
            """
            SELECT station_code, station_name, district, river, forecast_time, lead_day, meanflow_cms,
                   linked_cwc_station, historical_median_cms, historical_p75_cms,
                   historical_p90_cms, historical_p95_cms, historical_p99_cms, historical_max_cms,
                   flow_percentile_status, linkage_score, linkage_confidence, manual_approved
            FROM current_forecast_cwc_context
            """,
            con,
            parse_dates=["forecast_time"],
        )
    if current.empty:
        return current
    current["month"] = current["forecast_time"].dt.month
    current["lead_bucket_hours"] = pd.to_numeric(current.get("lead_day", 0), errors="coerce").fillna(0).astype(int) * 24
    current["raw_forecast_discharge_cms"] = pd.to_numeric(current["meanflow_cms"], errors="coerce")
    if not factors.empty:
        current = current.merge(
            factors[
                [
                    "station_code",
                    "month",
                    "lead_bucket_hours",
                    "median_ratio",
                    "median_bias_cms",
                    "training_rows",
                    "mae_cms",
                    "rmse_cms",
                    "model_status",
                ]
            ],
            on=["station_code", "month", "lead_bucket_hours"],
            how="left",
        )
    else:
        current["median_ratio"] = pd.NA
        current["median_bias_cms"] = pd.NA
        current["training_rows"] = 0
        current["mae_cms"] = pd.NA
        current["rmse_cms"] = pd.NA
        current["model_status"] = "Awaiting hindcast training"

    current["correction_factor"] = pd.to_numeric(current["median_ratio"], errors="coerce").fillna(1.0).clip(0.1, 10)
    current["additive_bias_cms"] = pd.to_numeric(current["median_bias_cms"], errors="coerce").fillna(0.0)
    current["corrected_forecast_discharge_cms"] = (
        current["raw_forecast_discharge_cms"] * current["correction_factor"] + current["additive_bias_cms"]
    ).clip(lower=0)
    current["correction_mode"] = current["model_status"].fillna("Awaiting hindcast training")
    current.loc[current["training_rows"].fillna(0).eq(0), "correction_mode"] = "Readiness mode - raw forecast retained"
    return current


def write_outputs(db_path: Path, training_csv: Path) -> dict:
    ensure_training_template(db_path, training_csv)
    training = pd.read_csv(training_csv) if training_csv.exists() else pd.DataFrame(columns=TRAINING_COLUMNS)
    has_training = {
        "raw_forecast_discharge_cms",
        "observed_discharge_cms",
        "forecast_valid_time",
    }.issubset(training.columns) and training["observed_discharge_cms"].notna().any()
    factors = train_factors(training) if has_training else pd.DataFrame(columns=FACTOR_COLUMNS)
    calibrated = apply_factors(db_path, factors)
    with sqlite3.connect(db_path) as con:
        factors.to_sql("forecast_bias_correction_factors", con, index=False, if_exists="replace")
        calibrated.to_sql("calibrated_gd_forecasts", con, index=False, if_exists="replace")
        con.execute("CREATE INDEX IF NOT EXISTS idx_calibrated_station ON calibrated_gd_forecasts(station_code)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_bias_factor_station ON forecast_bias_correction_factors(station_code, month, lead_bucket_hours)")
    return {
        "training_csv": str(training_csv),
        "training_rows": int(len(training.dropna(subset=["observed_discharge_cms"])) if "observed_discharge_cms" in training else 0),
        "factor_rows": int(len(factors)),
        "calibrated_rows": int(len(calibrated)),
        "trained": bool(not factors.empty),
        "mode": "trained baseline correction" if not factors.empty else "readiness mode - raw forecast retained until hindcast/observed overlap is supplied",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train/apply V02 baseline GD forecast bias correction.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--training-csv", required=True, type=Path)
    args = parser.parse_args()
    args.training_csv.parent.mkdir(parents=True, exist_ok=True)
    summary = write_outputs(args.db, args.training_csv)
    summary_path = args.training_csv.parent / "baseline_bias_correction_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
