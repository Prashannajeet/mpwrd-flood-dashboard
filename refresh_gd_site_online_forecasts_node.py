from __future__ import annotations

import csv
import json
import subprocess
import urllib.parse
from pathlib import Path

import geopandas as gpd
import pandas as pd


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
SITES = DATA_DIR / "gd_sites_swedes.geojson"
OUT = DATA_DIR / "gd_site_online_forecasts.csv"
LOCAL_REACHES = DATA_DIR / "geoglows_mp_reaches.geojson"
SERVICE = "https://livefeeds3.arcgis.com/arcgis/rest/services/GEOGLOWS/GlobalWaterModel_Medium/MapServer/0/query"
SERVICE_LAYER = "https://livefeeds3.arcgis.com/arcgis/rest/services/GEOGLOWS/GlobalWaterModel_Medium/MapServer/0"
FORECAST_HOURS = 7 * 24
FORECAST_STEP_HOURS = 3
COMID_CHUNK_SIZE = 45


def curl_json(params: dict[str, str]) -> dict:
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    # Use cmd.exe so the call behaves like the interactive curl command that works on this Windows host.
    command = f'curl.exe -s --max-time 25 "{url}"'
    result = subprocess.run(["cmd.exe", "/d", "/s", "/c", command], capture_output=True, text=True, timeout=35)
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def curl_json_url(url: str) -> dict:
    command = f'curl.exe -s --max-time 25 "{url}"'
    result = subprocess.run(["cmd.exe", "/d", "/s", "/c", command], capture_output=True, text=True, timeout=35)
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def forecast_time_values() -> list[int]:
    payload = curl_json_url(SERVICE_LAYER + "?f=json")
    extent = (payload or {}).get("timeInfo", {}).get("timeExtent") or []
    if not extent:
        return []
    start_ms, end_ms = int(extent[0]), int(extent[1])
    max_end_ms = min(end_ms, start_ms + FORECAST_HOURS * 60 * 60 * 1000)
    step_ms = FORECAST_STEP_HOURS * 60 * 60 * 1000
    return list(range(start_ms, max_end_ms + 1, step_ms))


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def fetch_forecast_series(comids: list[str]) -> pd.DataFrame:
    if not comids:
        return pd.DataFrame()
    time_values = forecast_time_values()
    if not time_values:
        return pd.DataFrame()
    rows: list[dict] = []
    for time_value in time_values:
        for group in chunks(comids, COMID_CHUNK_SIZE):
            where = "comid IN (" + ",".join(group) + ")"
            payload = curl_json(
                {
                    "f": "json",
                    "where": where,
                    "outFields": "comid,streamorder,timevalue,meanflow,returnperiod,upstreamarea",
                    "returnGeometry": "false",
                    "time": str(time_value),
                    "resultRecordCount": "2000",
                }
            )
            for feature in payload.get("features") or []:
                attrs = feature.get("attributes") or {}
                rows.append(attrs)
    if not rows:
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
    if LOCAL_REACHES.exists():
        reaches = gpd.read_file(LOCAL_REACHES).to_crs(4326)
        sites = gdf.dropna(subset=["geometry"]).copy()
        sites["station_code"] = sites.get("Station Co", "").astype(str).str.strip()
        sites = sites[sites["station_code"].str.len() > 0]
        sites_m = sites.to_crs(3857)
        reaches_m = reaches.dropna(subset=["geometry"]).to_crs(3857)
        linked = gpd.sjoin_nearest(
            sites_m,
            reaches_m[["comid", "streamorder", "timevalue", "meanflow", "returnperiod", "upstreamarea", "geometry"]],
            how="left",
            max_distance=150000,
            distance_col="distance_m",
        )
        linked = (
            linked.sort_values(["station_code", "distance_m", "streamorder", "upstreamarea"], ascending=[True, True, False, False])
            .drop_duplicates("station_code")
        )
        linked = linked.copy()
        linked["linked_comid"] = linked["comid"].apply(lambda value: "" if pd.isna(value) else str(int(value)))
        forecast_series = fetch_forecast_series(sorted([value for value in linked["linked_comid"].unique().tolist() if value]))
        for _, row in linked.to_crs(4326).iterrows():
            comid = str(row.get("linked_comid") or "")
            station_rows = forecast_series[forecast_series["comid"] == comid] if not forecast_series.empty and comid else pd.DataFrame()
            if station_rows.empty:
                fallback_time = row.get("timevalue") if "timevalue" in row else ""
                if pd.isna(fallback_time):
                    fallback_time = reaches.get("timevalue").iloc[0] if "timevalue" in reaches and len(reaches) else ""
                station_rows = pd.DataFrame(
                    [
                        {
                            "comid": comid,
                            "streamorder": row.get("streamorder"),
                            "forecast_time": pd.to_datetime(fallback_time, unit="ms", utc=True) if fallback_time != "" else "",
                            "meanflow": row.get("meanflow"),
                            "returnperiod": row.get("returnperiod"),
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
                        "linkage_status": "Linked live river forecast reach" if not pd.isna(flow) else "Not linked",
                        "distance_m": row.get("distance_m") if not pd.isna(row.get("distance_m")) else "",
                    }
                )
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
            writer.writeheader()
            writer.writerows(rows)
        linked_count = sum(1 for row in rows if str(row.get("linkage_status", "")).startswith("Linked"))
        print(f"Saved {len(rows)} GD site online forecast rows ({linked_count} linked) to {OUT}")
        return

    for _, feature in gdf.dropna(subset=["geometry"]).iterrows():
        lon = float(feature.geometry.x)
        lat = float(feature.geometry.y)
        station_code = str(feature.get("Station Co") or "").strip()
        if not station_code:
            continue
        near = curl_json(
            {
                "f": "json",
                "where": "1=1",
                "geometry": f"{lon:.8f},{lat:.8f}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "distance": "150000",
                "units": "esriSRUnit_Meter",
                "outFields": "comid,streamorder,rivercountry,timevalue,meanflow,returnperiod,upstreamarea",
                "returnGeometry": "false",
                "orderByFields": "streamorder DESC,upstreamarea DESC",
                "resultRecordCount": "1",
            }
        )
        features = near.get("features") or []
        if not features:
            rows.append(
                {
                    "station_code": station_code,
                    "station_name": str(feature.get("Station Na") or ""),
                    "district": str(feature.get("District") or ""),
                    "river": str(feature.get("River") or ""),
                    "tributary": str(feature.get("Tributary") or ""),
                    "latitude": lat,
                    "longitude": lon,
                    "comid": "",
                    "streamorder": "",
                    "forecast_time": "",
                    "lead_day": 0,
                    "meanflow_cms": "",
                    "returnperiod": "",
                    "linkage_status": "Not linked",
                }
            )
            continue
        attrs = features[0].get("attributes", {})
        rows.append(
            {
                "station_code": station_code,
                "station_name": str(feature.get("Station Na") or ""),
                "district": str(feature.get("District") or ""),
                "river": str(feature.get("River") or ""),
                "tributary": str(feature.get("Tributary") or ""),
                "latitude": lat,
                "longitude": lon,
                "comid": attrs.get("comid"),
                "streamorder": attrs.get("streamorder"),
                "forecast_time": attrs.get("timevalue"),
                "lead_day": 0,
                "meanflow_cms": attrs.get("meanflow"),
                "returnperiod": attrs.get("returnperiod"),
                "linkage_status": "Linked drainage reach",
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    linked = sum(1 for row in rows if row.get("linkage_status") == "Linked drainage reach")
    print(f"Saved {len(rows)} GD site online forecast rows ({linked} linked) to {OUT}")


if __name__ == "__main__":
    main()
