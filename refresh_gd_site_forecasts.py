from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import geopandas as gpd
import pandas as pd


APP_DIR = Path(__file__).resolve().parent
GD_SITES = APP_DIR / "data" / "gd_sites_swedes.geojson"
OBSERVED = APP_DIR / "data" / "narmada_observed.csv"
SERVICE_CACHE = APP_DIR / "data" / "river_forecast_service_status.json"
ONLINE_FORECAST_CSV = APP_DIR / "data" / "gd_site_online_forecasts.csv"
DB = APP_DIR / "data" / "gd_site_forecasts.sqlite"
SERVICE_URL = "https://livefeeds3.arcgis.com/arcgis/rest/services/GEOGLOWS/GlobalWaterModel_Medium/MapServer"


def slot(timestamp: pd.Timestamp | None = None) -> tuple[str, str, pd.Timestamp]:
    ts = pd.Timestamp(timestamp if timestamp is not None else pd.Timestamp.now(tz="Asia/Kolkata"))
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Kolkata")
    else:
        ts = ts.tz_convert("Asia/Kolkata")
    slot_hour = max([hour for hour in [8, 12, 16, 20] if hour <= ts.hour], default=20)
    slot_date = ts.normalize()
    if ts.hour < 8:
        slot_date = (ts - pd.Timedelta(days=1)).normalize()
    return slot_date.strftime("%Y-%m-%d"), f"{slot_hour:02d}:00", slot_date + pd.Timedelta(hours=slot_hour)


def service_time() -> pd.Timestamp:
    payload = None
    url = f"{SERVICE_URL}/0?f=json"
    try:
        result = subprocess.run(["curl.exe", "-s", "--max-time", "10", url], capture_output=True, text=True, timeout=12)
        if result.returncode == 0 and result.stdout.strip():
            payload = json.loads(result.stdout)
            SERVICE_CACHE.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        payload = None
    if payload is None and SERVICE_CACHE.exists():
        payload = json.loads(SERVICE_CACHE.read_text(encoding="utf-8"))
    extent = (payload or {}).get("timeInfo", {}).get("timeExtent") or []
    if not extent:
        return pd.Timestamp.now(tz="Asia/Kolkata")
    now_ms = pd.Timestamp.now(tz="UTC").timestamp() * 1000
    selected = min(extent, key=lambda value: abs(float(value) - now_ms))
    return pd.to_datetime(selected, unit="ms", utc=True).tz_convert("Asia/Kolkata")


def latest_observed() -> pd.DataFrame:
    if not OBSERVED.exists():
        return pd.DataFrame(columns=["station_code", "observed_at", "water_level_m", "water_level_change_m"])
    observed = pd.read_csv(OBSERVED)
    observed["observed_at"] = pd.to_datetime(observed.get("Reading Date Time"), errors="coerce")
    observed["water_level_m"] = pd.to_numeric(observed.get("WL"), errors="coerce")
    observed["station_code"] = observed.get("Station Code", "").astype(str).str.strip()
    observed = observed.dropna(subset=["station_code", "observed_at", "water_level_m"]).sort_values(["station_code", "observed_at"])
    observed["water_level_change_m"] = observed.groupby("station_code")["water_level_m"].diff()
    return observed.groupby("station_code").tail(1)[["station_code", "observed_at", "water_level_m", "water_level_change_m"]]


def init_db() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as conn:
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


def main() -> None:
    forecast_time = service_time()
    slot_date, slot_time, _ = slot()
    sites = gpd.read_file(GD_SITES).to_crs(4326)
    sites["station_code"] = sites.get("Station Co", pd.Series(dtype=str)).astype(str).str.strip()
    sites["station_name"] = sites.get("Station Na", pd.Series(dtype=str)).astype(str).str.strip()
    sites["district"] = sites.get("District", pd.Series(dtype=str)).astype(str).str.strip()
    sites["river"] = sites.get("River", pd.Series(dtype=str)).astype(str).str.strip()
    sites["tributary"] = sites.get("Tributary", pd.Series(dtype=str)).astype(str).str.strip()
    sites["latitude"] = sites.geometry.y
    sites["longitude"] = sites.geometry.x
    latest = latest_observed()
    merged = pd.DataFrame(sites).merge(latest, on="station_code", how="left")
    generated_at = pd.Timestamp.now(tz="Asia/Kolkata").isoformat()
    rows = []
    if ONLINE_FORECAST_CSV.exists():
        online = pd.read_csv(ONLINE_FORECAST_CSV)
        online["station_code"] = online.get("station_code", "").astype(str).str.strip()
        online["forecast_time"] = pd.to_datetime(online.get("forecast_time"), errors="coerce")
        online["meanflow_cms"] = pd.to_numeric(online.get("meanflow_cms"), errors="coerce")
        online["lead_day"] = pd.to_numeric(online.get("lead_day"), errors="coerce").fillna(0).astype(int)
        online = online.merge(latest, on="station_code", how="left")
        for record in online.to_dict("records"):
            observed_at = record.get("observed_at")
            observed_age = None
            if pd.notna(observed_at):
                observed_age = (forecast_time.tz_convert("UTC") - pd.Timestamp(observed_at).tz_convert("UTC")).days
            ft = record.get("forecast_time")
            data_period = "Now Data" if int(record.get("lead_day") or 0) == 0 else "Forecasted Data"
            flow = pd.to_numeric(pd.Series([record.get("meanflow_cms")]), errors="coerce").iloc[0]
            fid = hashlib.sha256(f"{slot_date}|{slot_time}|{record.get('station_code')}|{ft}|{data_period}".encode()).hexdigest()[:32]
            rows.append(
                (
                    fid, slot_date, slot_time, generated_at,
                    record.get("station_code"), record.get("station_name"), record.get("district"), record.get("river"), record.get("tributary"),
                    record.get("latitude"), record.get("longitude"),
                    pd.Timestamp(observed_at).isoformat() if pd.notna(observed_at) else None,
                    observed_age,
                    pd.Timestamp(ft).isoformat() if pd.notna(ft) else None,
                    data_period,
                    float(flow) if data_period == "Now Data" and pd.notna(flow) else None,
                    record.get("water_level_m"), record.get("water_level_change_m"),
                    float(flow) if pd.notna(flow) else None,
                    None,
                    float(flow) if pd.notna(flow) else None,
                    str(record.get("comid") or ""),
                    record.get("streamorder"),
                    record.get("returnperiod"),
                    record.get("linkage_status") or "Linked drainage reach",
                )
            )
    else:
        for record in merged.to_dict("records"):
            observed_at = record.get("observed_at")
            observed_age = None
            if pd.notna(observed_at):
                observed_age = (forecast_time.tz_convert("UTC") - pd.Timestamp(observed_at).tz_convert("UTC")).days
            ft = forecast_time
            fid = hashlib.sha256(f"{slot_date}|{slot_time}|{record.get('station_code')}|{ft}|Now Data".encode()).hexdigest()[:32]
            rows.append(
                (
                    fid, slot_date, slot_time, generated_at,
                    record.get("station_code"), record.get("station_name"), record.get("district"), record.get("river"), record.get("tributary"),
                    record.get("latitude"), record.get("longitude"),
                    pd.Timestamp(observed_at).isoformat() if pd.notna(observed_at) else None,
                    observed_age,
                    pd.Timestamp(ft).isoformat(),
                    "Now Data",
                    None,
                    record.get("water_level_m"), record.get("water_level_change_m"),
                    None, None, None,
                    None, None, None,
                    "Not linked",
                )
            )
    init_db()
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
    with sqlite3.connect(DB) as conn:
        conn.execute("DELETE FROM gd_site_forecasts WHERE slot_date = ? AND slot_time = ?", (slot_date, slot_time))
        conn.executemany(
            f"INSERT OR REPLACE INTO gd_site_forecasts ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
            rows,
        )
    print(f"Saved {len(rows)} GD site forecast rows for {slot_date} {slot_time} to {DB}")


if __name__ == "__main__":
    main()
