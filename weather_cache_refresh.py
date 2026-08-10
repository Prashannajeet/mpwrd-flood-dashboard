from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
MP_TOWNS_CSV = APP_DIR / "data" / "mp_towns.csv"
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
WEATHER_CACHE_DB = APP_DIR / "data" / "weather_cache.sqlite"
REFRESH_HOURS = 6


def now_utc() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def location_key(latitude: float, longitude: float) -> str:
    return f"{float(latitude):.5f},{float(longitude):.5f}"


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
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude:.5f}&longitude={longitude:.5f}"
        f"&current={current_vars}"
        "&timezone=Asia%2FKolkata"
        "&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm"
    )


def open_meteo_forecast_url(latitude: float, longitude: float, forecast_days: int = 7, past_days: int = 92) -> str:
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


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "mpwrd-vbsr-weather-refresh/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def init_database() -> None:
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_refresh_log (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                point_group TEXT NOT NULL,
                point_count INTEGER NOT NULL DEFAULT 0,
                current_count INTEGER NOT NULL DEFAULT 0,
                forecast_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                message TEXT
            )
            """
        )
        conn.commit()


def dataframe_payload(data: dict | pd.DataFrame) -> str:
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data or {})
    payload = {
        "columns": list(frame.columns),
        "records": json.loads(frame.to_json(orient="records", date_format="iso")),
    }
    return json.dumps(payload)


def refresh_current(towns: pd.DataFrame) -> int:
    refreshed = 0
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        for row in towns.itertuples(index=False):
            url = open_meteo_current_url(float(row.latitude), float(row.longitude))
            payload = fetch_json(url)
            current = payload.get("current") or {}
            conn.execute(
                """
                INSERT OR REPLACE INTO weather_current_cache
                (location_key, town_name, district, latitude, longitude, current_json, status, fetched_at, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    location_key(float(row.latitude), float(row.longitude)),
                    str(row.town_name),
                    str(row.district),
                    float(row.latitude),
                    float(row.longitude),
                    json.dumps(current, default=str),
                    "Fetched",
                    now_utc(),
                    url,
                ),
            )
            refreshed += 1
        conn.commit()
    return refreshed


def refresh_forecast(towns: pd.DataFrame) -> tuple[int, int]:
    current_refreshed = 0
    forecast_refreshed = 0
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        for row in towns.itertuples(index=False):
            url = open_meteo_forecast_url(float(row.latitude), float(row.longitude))
            payload = fetch_json(url)
            current = payload.get("current") or {}
            fetched_at = now_utc()
            key = location_key(float(row.latitude), float(row.longitude))
            conn.execute(
                """
                INSERT OR REPLACE INTO weather_forecast_cache
                (location_key, latitude, longitude, daily_json, hourly_json, current_json, fetched_at, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    float(row.latitude),
                    float(row.longitude),
                    dataframe_payload(payload.get("daily") or {}),
                    dataframe_payload(payload.get("hourly") or {}),
                    dataframe_payload(pd.DataFrame([current])),
                    fetched_at,
                    url,
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO weather_current_cache
                (location_key, town_name, district, latitude, longitude, current_json, status, fetched_at, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    str(row.town_name),
                    str(row.district),
                    float(row.latitude),
                    float(row.longitude),
                    json.dumps(current, default=str),
                    "Fetched",
                    fetched_at,
                    url,
                ),
            )
            forecast_refreshed += 1
            current_refreshed += 1
        conn.commit()
    return current_refreshed, forecast_refreshed


def load_towns() -> pd.DataFrame:
    towns = pd.read_csv(MP_TOWNS_CSV)
    towns["latitude"] = pd.to_numeric(towns["latitude"], errors="coerce")
    towns["longitude"] = pd.to_numeric(towns["longitude"], errors="coerce")
    return towns.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)


def load_dams() -> pd.DataFrame:
    if not DAM_LOCATIONS_CSV.exists():
        return pd.DataFrame(columns=["town_name", "district", "latitude", "longitude"])
    dams = pd.read_csv(DAM_LOCATIONS_CSV)
    dams["latitude"] = pd.to_numeric(dams.get("latitude"), errors="coerce")
    dams["longitude"] = pd.to_numeric(dams.get("longitude"), errors="coerce")
    dams["town_name"] = dams.get("dam_name", pd.Series("Dam", index=dams.index)).fillna("Dam")
    dams["district"] = dams.get("map_district", pd.Series("Unassigned", index=dams.index)).fillna("Unassigned")
    return dams[["town_name", "district", "latitude", "longitude"]].dropna(subset=["latitude", "longitude"]).drop_duplicates("town_name").reset_index(drop=True)


def load_points(include_dams: bool) -> tuple[pd.DataFrame, str]:
    towns = load_towns()
    if not include_dams:
        return towns, "towns"
    dams = load_dams()
    points = pd.concat([towns, dams], ignore_index=True)
    points = points.drop_duplicates(["town_name", "district", "latitude", "longitude"]).reset_index(drop=True)
    return points, "towns+dams"


def log_refresh(run_id: str, started_at: str, point_group: str, point_count: int, current_count: int, forecast_count: int, status: str, message: str = "") -> None:
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO weather_refresh_log
            (run_id, started_at, finished_at, point_group, point_count, current_count, forecast_count, status, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, started_at, now_utc(), point_group, point_count, current_count, forecast_count, status, message),
        )
        conn.commit()


def seconds_until_daily_time(daily_at: str) -> float:
    hour_text, minute_text = daily_at.split(":", 1)
    now = pd.Timestamp.now(tz="Asia/Kolkata")
    target = now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
    if target <= now:
        target = target + pd.Timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def seconds_until_next_cycle(interval_hours: int = REFRESH_HOURS) -> float:
    now = pd.Timestamp.now(tz="Asia/Kolkata")
    next_hour = ((now.hour // interval_hours) + 1) * interval_hours
    target = now.normalize() + pd.Timedelta(hours=next_hour)
    return max(1.0, (target - now).total_seconds())


def run_once(include_forecast: bool, include_dams: bool, max_points: int = 0) -> None:
    init_database()
    started_at = now_utc()
    points, point_group = load_points(include_dams)
    if max_points and max_points > 0:
        points = points.head(max_points).reset_index(drop=True)
        point_group = f"{point_group}-sample"
    run_id = f"{point_group.replace('+', '_')}_{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%SZ')}"
    try:
        if include_forecast:
            current_count, forecast_count = refresh_forecast(points)
        else:
            current_count = refresh_current(points)
            forecast_count = 0
        log_refresh(run_id, started_at, point_group, len(points), current_count, forecast_count, "Fetched")
        print(
            f"{now_utc()} refreshed current weather for {current_count} {point_group} points"
            + (f" and forecast/hindcast for {forecast_count} points." if include_forecast else ".")
        )
    except Exception as exc:
        log_refresh(run_id, started_at, point_group, len(points), 0, 0, "Failed", str(exc))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh MPWRD weather cache database.")
    parser.add_argument("--loop", action="store_true", help="Keep running at 00:00, 06:00, 12:00 and 18:00 IST.")
    parser.add_argument("--daily-at", default="", help="Run once daily at HH:MM in Asia/Kolkata, for example 00:30.")
    parser.add_argument("--forecast-all", action="store_true", help="Also refresh 7-day forecast and 92-day hindcast for all towns.")
    parser.add_argument("--include-dams", action="store_true", help="Also refresh dam weather points.")
    parser.add_argument("--max-points", type=int, default=0, help="Optional cap for test or emergency refresh runs. Default refreshes all points.")
    args = parser.parse_args()

    while True:
        if args.daily_at:
            sleep_seconds = seconds_until_daily_time(args.daily_at)
            print(f"{now_utc()} next scheduled weather refresh at {args.daily_at} IST in {sleep_seconds / 3600:.2f} hours.")
            time.sleep(sleep_seconds)
        run_once(args.forecast_all, args.include_dams, args.max_points)
        if not args.loop and not args.daily_at:
            break
        if args.loop and not args.daily_at:
            sleep_seconds = seconds_until_next_cycle()
            print(f"{now_utc()} next scheduled weather refresh in {sleep_seconds / 3600:.2f} hours.")
            time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
