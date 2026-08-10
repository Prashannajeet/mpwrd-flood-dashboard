from __future__ import annotations

import csv
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SITES = DATA_DIR / "gd_sites_swedes.geojson"
OUT = DATA_DIR / "gd_site_online_forecasts.csv"
LOCAL_REACHES = DATA_DIR / "geoglows_mp_reaches.geojson"
SERVICE_CACHE = DATA_DIR / "river_forecast_service_status.json"
SERVICE = "https://livefeeds3.arcgis.com/arcgis/rest/services/GEOGLOWS/GlobalWaterModel_Medium/MapServer/0/query"
SERVICE_LAYER = "https://livefeeds3.arcgis.com/arcgis/rest/services/GEOGLOWS/GlobalWaterModel_Medium/MapServer/0"
FORECAST_HOURS = 7 * 24
FORECAST_STEP_HOURS = 3
COMID_CHUNK_SIZE = 20
MAX_LINK_DISTANCE_M = 25_000
LINK_SEARCH_RADII_M = (1_000, 5_000, MAX_LINK_DISTANCE_M)


def curl_json(params: dict[str, str]) -> dict:
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    return fetch_json_url(url)


def fetch_json_url(url: str) -> dict:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "MPWRD-GD-Forecast-Refresh/1.0"})
        with urllib.request.urlopen(request, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        pass
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"(Invoke-WebRequest -UseBasicParsing -TimeoutSec 35 -Uri {json.dumps(url)}).Content",
            ],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    result = subprocess.run(["curl.exe", "-s", "--max-time", "35", url], capture_output=True, text=True, timeout=45)
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def curl_json_url(url: str) -> dict:
    return fetch_json_url(url)


def forecast_time_values() -> list[int]:
    payload = curl_json_url(SERVICE_LAYER + "?f=json")
    if payload:
        try:
            SERVICE_CACHE.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass
    elif SERVICE_CACHE.exists():
        try:
            payload = json.loads(SERVICE_CACHE.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    extent = (payload or {}).get("timeInfo", {}).get("timeExtent") or []
    if not extent:
        return []
    extent_start_ms, end_ms = int(extent[0]), int(extent[1])
    now_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    start_ms = min(
        range(extent_start_ms, end_ms + 1, FORECAST_STEP_HOURS * 60 * 60 * 1000),
        key=lambda value: abs(value - now_ms),
    )
    max_end_ms = min(end_ms, start_ms + FORECAST_HOURS * 60 * 60 * 1000)
    step_ms = FORECAST_STEP_HOURS * 60 * 60 * 1000
    return list(range(start_ms, max_end_ms + 1, step_ms))


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def nearest_live_reach(lon: float, lat: float, time_value: int) -> tuple[dict, float]:
    point = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(3857).iloc[0]
    for radius_m in LINK_SEARCH_RADII_M:
        payload = curl_json(
            {
                "f": "geojson",
                "where": "1=1",
                "geometry": f"{lon:.8f},{lat:.8f}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "distance": str(radius_m),
                "units": "esriSRUnit_Meter",
                "time": str(time_value),
                "outFields": "comid,streamorder,timevalue,meanflow,returnperiod,upstreamarea",
                "returnGeometry": "true",
                "outSR": "4326",
                "resultRecordCount": "500",
            }
        )
        features = payload.get("features") or []
        if not features:
            continue
        candidates = gpd.GeoDataFrame.from_features(features, crs=4326)
        if candidates.empty or "geometry" not in candidates:
            continue
        candidates = candidates.dropna(subset=["geometry"]).to_crs(3857)
        if candidates.empty:
            continue
        candidates["distance_m"] = candidates.geometry.distance(point)
        candidates["streamorder"] = pd.to_numeric(candidates.get("streamorder"), errors="coerce")
        candidates["upstreamarea"] = pd.to_numeric(candidates.get("upstreamarea"), errors="coerce")
        nearest = candidates.sort_values(
            ["distance_m", "streamorder", "upstreamarea"],
            ascending=[True, False, False],
        ).iloc[0]
        distance_m = float(nearest.get("distance_m"))
        if distance_m <= MAX_LINK_DISTANCE_M:
            return nearest.drop(labels=["geometry"], errors="ignore").to_dict(), distance_m
    return {}, float("nan")


def fetch_forecast_series(comids: list[str]) -> pd.DataFrame:
    if not comids:
        return pd.DataFrame()
    time_values = forecast_time_values()
    if not time_values:
        return pd.DataFrame()
    rows: list[dict] = []
    time_window = f"{min(time_values)},{max(time_values)}"
    for group in chunks(comids, COMID_CHUNK_SIZE):
        where = "comid IN (" + ",".join(group) + ")"
        payload = curl_json(
            {
                "f": "json",
                "where": where,
                "outFields": "comid,streamorder,timevalue,meanflow,returnperiod,upstreamarea",
                "returnGeometry": "false",
                "time": time_window,
                "orderByFields": "comid ASC,timevalue ASC",
                "resultRecordCount": "2000",
            }
        )
        if not payload or payload.get("error"):
            features = []
        else:
            features = payload.get("features") or []
        if payload and not payload.get("error") and not features:
            for time_value in time_values:
                fallback_payload = curl_json(
                    {
                        "f": "json",
                        "where": where,
                        "outFields": "comid,streamorder,timevalue,meanflow,returnperiod,upstreamarea",
                        "returnGeometry": "false",
                        "time": str(time_value),
                        "resultRecordCount": "2000",
                    }
                )
                features.extend(fallback_payload.get("features") or [])
        for feature in features:
            attrs = feature.get("attributes") or {}
            rows.append(attrs)
    if not rows:
        print("Warning: live river forecast series could not be fetched; using cached reach snapshot only.")
        return pd.DataFrame()
    series = pd.DataFrame(rows)
    series["comid"] = series["comid"].astype(str)
    series["forecast_time"] = pd.to_datetime(series["timevalue"], unit="ms", utc=True)
    for column in ["meanflow", "returnperiod", "streamorder", "upstreamarea"]:
        series[column] = pd.to_numeric(series[column], errors="coerce")
    return series.drop_duplicates(["comid", "forecast_time"]).sort_values(["comid", "forecast_time"])


def main() -> None:
    gdf = gpd.read_file(SITES).to_crs(4326)
    rows: list[dict] = []
    time_values = forecast_time_values()
    if not time_values:
        raise RuntimeError("The river forecast service did not provide a current forecast window; the existing file was preserved.")
    current_time_value = time_values[0]
    sites = gdf.dropna(subset=["geometry"]).copy()
    sites["station_code"] = sites.get("Station Co", "").astype(str).str.strip()
    sites = sites[sites["station_code"].str.len() > 0]
    linked_records = []
    for _, site in sites.iterrows():
        lon = float(site.geometry.x)
        lat = float(site.geometry.y)
        reach, distance_m = nearest_live_reach(lon, lat, current_time_value)
        record = site.to_dict()
        record.update(reach)
        record["distance_m"] = distance_m
        record["linked_comid"] = "" if not reach or pd.isna(reach.get("comid")) else str(int(reach.get("comid")))
        linked_records.append(record)
    linked = gpd.GeoDataFrame(linked_records, geometry="geometry", crs=4326)
    forecast_series = fetch_forecast_series(sorted([value for value in linked["linked_comid"].unique().tolist() if value]))
    for _, row in linked.iterrows():
            comid = str(row.get("linked_comid") or "")
            station_rows = forecast_series[forecast_series["comid"] == comid] if not forecast_series.empty and comid else pd.DataFrame()
            if station_rows.empty:
                station_rows = pd.DataFrame(
                    [
                        {
                            "comid": comid,
                            "streamorder": row.get("streamorder"),
                            "forecast_time": pd.to_datetime(current_time_value, unit="ms", utc=True),
                            "meanflow": None,
                            "returnperiod": None,
                        }
                    ]
                )
            first_time = pd.to_datetime(station_rows["forecast_time"], errors="coerce").min()
            for _, forecast in station_rows.iterrows():
                ft = pd.to_datetime(forecast.get("forecast_time"), errors="coerce")
                lead_day = 0
                if pd.notna(ft) and pd.notna(first_time):
                    lead_day = int(max(0, (ft - first_time).total_seconds()) // 86400)
                flow = forecast.get("meanflow")
                rows.append(
                    {
                        "station_code": str(row.get("Station Co") or "").strip(),
                        "station_name": str(row.get("Station Na") or ""),
                        "district": str(row.get("District") or ""),
                        "river": str(row.get("River") or ""),
                        "tributary": str(row.get("Tributary") or ""),
                        "latitude": float(row.geometry.y),
                        "longitude": float(row.geometry.x),
                        "comid": comid,
                        "streamorder": forecast.get("streamorder") if not pd.isna(forecast.get("streamorder")) else row.get("streamorder"),
                        "forecast_time": ft.isoformat() if pd.notna(ft) else "",
                        "lead_day": lead_day,
                        "meanflow_cms": flow if not pd.isna(flow) else "",
                        "returnperiod": forecast.get("returnperiod") if not pd.isna(forecast.get("returnperiod")) else "",
                        "linkage_status": "Linked live river forecast reach" if comid and not pd.isna(flow) else "No verified river forecast link",
                        "distance_m": row.get("distance_m") if not pd.isna(row.get("distance_m")) else "",
                    }
                )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError("No valid GD forecast rows were produced; the existing file was preserved.")
    temp_out = OUT.with_suffix(".csv.tmp")
    with temp_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    temp_out.replace(OUT)
    linked_count = len({row["station_code"] for row in rows if str(row.get("linkage_status", "")).startswith("Linked")})
    print(f"Saved {len(rows)} GD site online forecast rows ({linked_count} verified station links) to {OUT}")


if __name__ == "__main__":
    main()
