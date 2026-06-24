from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.request
from pathlib import Path

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
MP_TOWNS_CSV = APP_DIR / "data" / "mp_towns.csv"
WEATHER_CACHE_DB = APP_DIR / "data" / "weather_cache.sqlite"
REFRESH_SECONDS = 3 * 60 * 60


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


def refresh_forecast(towns: pd.DataFrame) -> int:
    refreshed = 0
    with sqlite3.connect(WEATHER_CACHE_DB) as conn:
        for row in towns.itertuples(index=False):
            url = open_meteo_forecast_url(float(row.latitude), float(row.longitude))
            payload = fetch_json(url)
            conn.execute(
                """
                INSERT OR REPLACE INTO weather_forecast_cache
                (location_key, latitude, longitude, daily_json, hourly_json, current_json, fetched_at, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    location_key(float(row.latitude), float(row.longitude)),
                    float(row.latitude),
                    float(row.longitude),
                    dataframe_payload(payload.get("daily") or {}),
                    dataframe_payload(payload.get("hourly") or {}),
                    dataframe_payload(pd.DataFrame([payload.get("current") or {}])),
                    now_utc(),
                    url,
                ),
            )
            refreshed += 1
        conn.commit()
    return refreshed


def load_towns() -> pd.DataFrame:
    towns = pd.read_csv(MP_TOWNS_CSV)
    towns["latitude"] = pd.to_numeric(towns["latitude"], errors="coerce")
    towns["longitude"] = pd.to_numeric(towns["longitude"], errors="coerce")
    return towns.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)


def run_once(include_forecast: bool) -> None:
    init_database()
    towns = load_towns()
    current_count = refresh_current(towns)
    forecast_count = refresh_forecast(towns) if include_forecast else 0
    print(
        f"{now_utc()} refreshed current weather for {current_count} towns"
        + (f" and forecast/hindcast for {forecast_count} towns." if include_forecast else ".")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh MPWRD weather cache database.")
    parser.add_argument("--loop", action="store_true", help="Keep running and refresh every 3 hours.")
    parser.add_argument("--forecast-all", action="store_true", help="Also refresh 7-day forecast and 92-day hindcast for all towns.")
    args = parser.parse_args()

    while True:
        run_once(args.forecast_all)
        if not args.loop:
            break
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
