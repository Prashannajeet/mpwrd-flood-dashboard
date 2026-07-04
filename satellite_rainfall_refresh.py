from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
RAINGAUGE_STATIONS_CSV = DATA_DIR / "mp_raingauge_stations.csv"
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
GD_SITES_GEOJSON = DATA_DIR / "gd_sites_swedes.geojson"
RAINFALL_DB = DATA_DIR / "satellite_rainfall_timeseries.sqlite"
REFRESH_SECONDS = 3 * 60 * 60
NASA_PPS_BASE_URL = os.getenv("NASA_PPS_BASE_URL", "https://arthurhouhttps.pps.eosdis.nasa.gov").rstrip("/")


@dataclass(frozen=True)
class RainfallStation:
    station_id: str
    station_name: str
    station_type: str
    district: str
    basin: str
    latitude: float
    longitude: float
    source: str


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def previous_three_hour_slot(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    current = current.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return current.replace(hour=(current.hour // 3) * 3)


def station_id(prefix: str, name: str, district: str, latitude: float, longitude: float) -> str:
    raw = f"{prefix}|{name}|{district}|{latitude:.5f}|{longitude:.5f}".lower()
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    slug = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")[:24]
    return f"{prefix}_{slug}_{digest}"


def init_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(RAINFALL_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rainfall_station_master (
                station_id TEXT PRIMARY KEY,
                station_name TEXT NOT NULL,
                station_type TEXT NOT NULL,
                district TEXT,
                basin TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                source TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rainfall_3hour_observations (
                station_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                rainfall_3h_mm REAL,
                rainfall_24h_mm REAL,
                source_product TEXT NOT NULL,
                source_latency_hours REAL,
                quality_flag TEXT NOT NULL DEFAULT 'unchecked',
                fetched_at TEXT NOT NULL,
                raw_payload TEXT,
                PRIMARY KEY (station_id, observed_at, source_product),
                FOREIGN KEY (station_id) REFERENCES rainfall_station_master(station_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rainfall_refresh_log (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                source_product TEXT NOT NULL,
                requested_slot TEXT NOT NULL,
                station_count INTEGER NOT NULL DEFAULT 0,
                observation_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                message TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rainfall_observed_at ON rainfall_3hour_observations(observed_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rainfall_station_time ON rainfall_3hour_observations(station_id, observed_at)")
        conn.commit()


def clean_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text and text.lower() != "nan" else default


def numeric(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def load_raingauge_stations() -> list[RainfallStation]:
    if not RAINGAUGE_STATIONS_CSV.exists():
        return []
    frame = pd.read_csv(RAINGAUGE_STATIONS_CSV)
    stations: list[RainfallStation] = []
    for row in frame.to_dict(orient="records"):
        lat = numeric(row.get("latitude") or row.get("lat"))
        lon = numeric(row.get("longitude") or row.get("lon") or row.get("long"))
        name = clean_text(row.get("station_name") or row.get("name") or row.get("raingauge_name"))
        if lat is None or lon is None or not name:
            continue
        district = clean_text(row.get("district"))
        basin = clean_text(row.get("basin") or row.get("river_basin"))
        stations.append(
            RainfallStation(
                station_id=clean_text(row.get("station_id") or row.get("station_code"))
                or station_id("rg", name, district, lat, lon),
                station_name=name,
                station_type="Rain Gauge",
                district=district,
                basin=basin,
                latitude=lat,
                longitude=lon,
                source="mp_raingauge_stations.csv",
            )
        )
    return stations


def load_dam_stations() -> list[RainfallStation]:
    if not DAM_LOCATIONS_CSV.exists():
        return []
    frame = pd.read_csv(DAM_LOCATIONS_CSV)
    stations: list[RainfallStation] = []
    for row in frame.to_dict(orient="records"):
        lat = numeric(row.get("latitude"))
        lon = numeric(row.get("longitude"))
        name = clean_text(row.get("dam_name"))
        if lat is None or lon is None or not name:
            continue
        district = clean_text(row.get("map_district"))
        basin = clean_text(row.get("major_basin") or row.get("sub_basin"))
        stations.append(
            RainfallStation(
                station_id=station_id("dam", name, district, lat, lon),
                station_name=name,
                station_type="Dam",
                district=district,
                basin=basin,
                latitude=lat,
                longitude=lon,
                source="dam_locations.csv",
            )
        )
    return stations


def load_gd_stations() -> list[RainfallStation]:
    if not GD_SITES_GEOJSON.exists():
        return []
    payload = json.loads(GD_SITES_GEOJSON.read_text(encoding="utf-8"))
    stations: list[RainfallStation] = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        coords = ((feature.get("geometry") or {}).get("coordinates") or [])
        if len(coords) < 2:
            continue
        lon = numeric(coords[0])
        lat = numeric(coords[1])
        name = clean_text(props.get("Station Na") or props.get("Station Name") or props.get("Station"))
        if lat is None or lon is None or not name:
            continue
        district = clean_text(props.get("District"))
        basin = clean_text(props.get("River") or props.get("Tributary") or props.get("Major Basi"))
        stations.append(
            RainfallStation(
                station_id=clean_text(props.get("Station Co")) or station_id("gd", name, district, lat, lon),
                station_name=name,
                station_type="GD Site",
                district=district,
                basin=basin,
                latitude=lat,
                longitude=lon,
                source="gd_sites_swedes.geojson",
            )
        )
    return stations


def load_all_stations(include_dams: bool, include_gd_sites: bool) -> list[RainfallStation]:
    stations = load_raingauge_stations()
    if include_dams:
        stations.extend(load_dam_stations())
    if include_gd_sites:
        stations.extend(load_gd_stations())

    deduped: dict[str, RainfallStation] = {}
    for station in stations:
        deduped[station.station_id] = station
    return list(deduped.values())


def upsert_stations(stations: Iterable[RainfallStation]) -> int:
    count = 0
    with sqlite3.connect(RAINFALL_DB) as conn:
        for station in stations:
            conn.execute(
                """
                INSERT INTO rainfall_station_master
                (station_id, station_name, station_type, district, basin, latitude, longitude, source, active, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(station_id) DO UPDATE SET
                    station_name=excluded.station_name,
                    station_type=excluded.station_type,
                    district=excluded.district,
                    basin=excluded.basin,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    source=excluded.source,
                    active=1,
                    updated_at=excluded.updated_at
                """,
                (
                    station.station_id,
                    station.station_name,
                    station.station_type,
                    station.district,
                    station.basin,
                    station.latitude,
                    station.longitude,
                    station.source,
                    now_utc(),
                ),
            )
            count += 1
        conn.commit()
    return count


def import_observation_csv(path: Path, source_product: str) -> int:
    required = {"station_id", "observed_at", "rainfall_3h_mm"}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    with sqlite3.connect(RAINFALL_DB) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO rainfall_3hour_observations
                (station_id, observed_at, rainfall_3h_mm, rainfall_24h_mm, source_product,
                 source_latency_hours, quality_flag, fetched_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_text(row.get("station_id")),
                    clean_text(row.get("observed_at")),
                    numeric(row.get("rainfall_3h_mm")),
                    numeric(row.get("rainfall_24h_mm")),
                    source_product,
                    numeric(row.get("source_latency_hours")),
                    clean_text(row.get("quality_flag"), "imported"),
                    now_utc(),
                    json.dumps(row, default=str),
                ),
            )
        conn.commit()
    return len(rows)


def log_run(run_id: str, source_product: str, requested_slot: str, station_count: int, status: str, message: str = "") -> None:
    with sqlite3.connect(RAINFALL_DB) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO rainfall_refresh_log
            (run_id, started_at, finished_at, source_product, requested_slot, station_count, observation_count, status, message)
            VALUES (?, COALESCE((SELECT started_at FROM rainfall_refresh_log WHERE run_id = ?), ?), ?, ?, ?, ?, 0, ?, ?)
            """,
            (run_id, run_id, now_utc(), now_utc(), source_product, requested_slot, station_count, status, message),
        )
        conn.commit()


def create_pending_imerg_run(stations: list[RainfallStation], requested_slot: datetime) -> None:
    source_product = os.getenv("NASA_IMERG_PRODUCT", "IMERG_EARLY_3H")
    run_id = f"{source_product}_{requested_slot.strftime('%Y%m%dT%H%MZ')}"
    message = (
        "Station master refreshed. Configure NASA PPS/GES DISC access or import an extracted "
        "station rainfall CSV to populate 3-hour IMERG observations."
    )
    log_run(run_id, source_product, requested_slot.isoformat(), len(stations), "station_master_ready", message)


def get_nasa_pps_credentials() -> tuple[str, str]:
    return os.getenv("NASA_PPS_USERNAME", "").strip(), os.getenv("NASA_PPS_PASSWORD", "").strip()


def check_nasa_pps_access() -> tuple[bool, str]:
    username, password = get_nasa_pps_credentials()
    if not username or not password:
        return False, "NASA_PPS_USERNAME and NASA_PPS_PASSWORD are not configured."
    password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_manager.add_password(None, NASA_PPS_BASE_URL, username, password)
    opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_manager))
    request = urllib.request.Request(NASA_PPS_BASE_URL + "/", headers={"User-Agent": "mpwrd-imerg-refresh/1.0"})
    try:
        with opener.open(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            return 200 <= int(status) < 400, f"NASA PPS access check returned HTTP {status}."
    except urllib.error.HTTPError as exc:
        return False, f"NASA PPS access check failed with HTTP {exc.code}."
    except Exception as exc:
        return False, f"NASA PPS access check failed: {exc}"


def run_once(include_dams: bool, include_gd_sites: bool, import_csv: Path | None, source_product: str) -> None:
    init_database()
    stations = load_all_stations(include_dams=include_dams, include_gd_sites=include_gd_sites)
    station_count = upsert_stations(stations)
    slot = previous_three_hour_slot()

    if import_csv:
        observation_count = import_observation_csv(import_csv, source_product)
        run_id = f"{source_product}_import_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        log_run(run_id, source_product, slot.isoformat(), station_count, "imported", f"Imported {observation_count} observation rows.")
        print(f"{now_utc()} imported {observation_count} rainfall rows for {station_count} stations.")
        return

    create_pending_imerg_run(stations, slot)
    print(
        f"{now_utc()} refreshed rainfall station master for {station_count} stations. "
        "No live IMERG extraction endpoint is configured yet."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh 3-hour satellite rainfall database for MP stations.")
    parser.add_argument("--loop", action="store_true", help="Keep running and refresh every 3 hours.")
    parser.add_argument("--include-dams", action="store_true", help="Include dam locations as rainfall sampling points.")
    parser.add_argument("--include-gd-sites", action="store_true", help="Include GD/gauge-discharge locations as rainfall sampling points.")
    parser.add_argument("--import-csv", type=Path, help="Import extracted 3-hour rainfall rows from CSV.")
    parser.add_argument("--check-nasa-access", action="store_true", help="Check NASA PPS login using NASA_PPS_USERNAME and NASA_PPS_PASSWORD.")
    parser.add_argument("--source-product", default=os.getenv("NASA_IMERG_PRODUCT", "IMERG_EARLY_3H"))
    args = parser.parse_args()

    if args.check_nasa_access:
        ok, message = check_nasa_pps_access()
        print(f"{'OK' if ok else 'FAILED'}: {message}")
        if not ok:
            raise SystemExit(1)

    while True:
        run_once(
            include_dams=args.include_dams,
            include_gd_sites=args.include_gd_sites,
            import_csv=args.import_csv,
            source_product=args.source_product,
        )
        if not args.loop:
            break
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
