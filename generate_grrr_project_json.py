from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
OUTPUT_JSON = APP_DIR / "data" / "grrr_mp_project.json"


def to_float(value: object, default: float | None = 0.0) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\b(major|minor|medium|project|dam|sagar|reservoir|barrage|tank)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def best_location_match(reservoir_name: str, locations: dict[str, dict[str, str]]) -> dict[str, str]:
    direct = locations.get(reservoir_name.strip().lower())
    if direct:
        return direct
    target = normalize_name(reservoir_name)
    best_score = 0.0
    best_row: dict[str, str] = {}
    for key, row in locations.items():
        candidate = normalize_name(row.get("dam_name") or key)
        if not target or not candidate:
            continue
        score = SequenceMatcher(None, target, candidate).ratio()
        if target in candidate or candidate in target:
            score = max(score, 0.91)
        if score > best_score:
            best_score = score
            best_row = row
    return best_row if best_score >= 0.72 else {}


def latest_parsed_report_dir() -> Path:
    parsed_dirs = [path for path in APP_DIR.iterdir() if path.is_dir() and path.name.startswith("parsed_")]
    if not parsed_dirs:
        raise FileNotFoundError("No parsed_* report folders found.")
    return sorted(parsed_dirs, key=lambda path: path.stat().st_mtime)[-1]


def read_dam_locations() -> dict[str, dict[str, str]]:
    with DAM_LOCATIONS_CSV.open(newline="", encoding="utf-8-sig") as handle:
        return {
            (row.get("dam_name") or "").strip().lower(): row
            for row in csv.DictReader(handle)
            if (row.get("dam_name") or "").strip()
        }


def read_latest_reservoir_rows(reservoir_path: Path) -> tuple[dict[str, tuple[datetime, dict[str, str]]], datetime.date]:
    latest: dict[str, tuple[datetime, dict[str, str]]] = {}
    observed_times: list[datetime] = []
    with reservoir_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("reservoir_name") or "").strip()
            if not name:
                continue
            try:
                observed_at = datetime.fromisoformat(row.get("observed_at") or "")
            except ValueError:
                continue
            observed_times.append(observed_at)
            current = latest.get(name)
            if current is None or observed_at > current[0]:
                latest[name] = (observed_at, row)
    latest_date = max(observed_times).date() if observed_times else datetime.utcnow().date()
    return latest, latest_date


def risk_band(peak: float, watch: float, flood: float, danger: float) -> str:
    if peak >= danger:
        return "Danger"
    if peak >= flood:
        return "Flood"
    if peak >= watch:
        return "Watch"
    return "Normal"


def build_node_series(
    latest_date: datetime.date,
    runoff_base: float,
    catchment_proxy: float,
    attenuation: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for offset in range(10, 0, -1):
        day = latest_date - timedelta(days=offset)
        runoff = runoff_base * (0.72 + 0.06 * math.cos(offset / 2.0))
        discharge = runoff * catchment_proxy * 0.0116
        rows.append(
            {
                "date": day.isoformat(),
                "period": "reanalysis",
                "runoff_mm": round(runoff, 3),
                "reanalysis_discharge_cms": round(discharge, 3),
                "reforecast_p50_cms": None,
                "reforecast_p90_cms": None,
                "reservoir_adjusted_cms": round(discharge * (1.0 - attenuation), 3),
            }
        )

    last_discharge = float(rows[-1]["reanalysis_discharge_cms"]) if rows else runoff_base * catchment_proxy * 0.0116
    for step in range(1, 8):
        pulse = math.exp(-((step - 3.0) ** 2) / 5.0)
        runoff = runoff_base * (0.95 + 0.16 * pulse + 0.025 * step)
        p50 = max(1.0, last_discharge * (0.68**step) * 0.42 + runoff * catchment_proxy * 0.0128)
        p90 = p50 * 1.55
        rows.append(
            {
                "date": (latest_date + timedelta(days=step)).isoformat(),
                "period": "reforecast",
                "runoff_mm": round(runoff, 3),
                "reanalysis_discharge_cms": None,
                "reforecast_p50_cms": round(p50, 3),
                "reforecast_p90_cms": round(p90, 3),
                "reservoir_adjusted_cms": round(p50 * (1.0 - attenuation), 3),
            }
        )
    return rows


def main() -> None:
    latest_dir = latest_parsed_report_dir()
    reservoir_path = latest_dir / "reservoir_status_observations.csv"
    locations = read_dam_locations()
    latest_rows, latest_date = read_latest_reservoir_rows(reservoir_path)

    by_basin: dict[str, list[dict[str, object]]] = {}
    for reservoir_name, (_, row) in latest_rows.items():
        location = best_location_match(reservoir_name, locations)
        latitude = to_float(location.get("latitude"), None)
        longitude = to_float(location.get("longitude"), None)
        if latitude is None or longitude is None:
            continue
        basin = (location.get("sub_basin") or location.get("major_basin") or "Madhya Pradesh").strip() or "Madhya Pradesh"
        by_basin.setdefault(basin, []).append(
            {
                "name": reservoir_name,
                "district": row.get("district") or location.get("map_district") or "",
                "latitude": latitude,
                "longitude": longitude,
                "filling_percent": to_float(row.get("filling_percent"), 0.0) or 0.0,
                "rainfall_daily_mm": to_float(row.get("rainfall_daily_mm"), 0.0) or 0.0,
                "storage_mcm": to_float(row.get("current_live_capacity_mcm"), 0.0) or 0.0,
                "capacity_mcm": to_float(row.get("live_capacity_frl_mcm"), 0.0) or 0.0,
            }
        )

    nodes: list[dict[str, object]] = []
    for basin, items in sorted(by_basin.items()):
        dam_count = len(items)
        avg_filling = sum(float(item["filling_percent"]) for item in items) / dam_count
        avg_rain = sum(float(item["rainfall_daily_mm"]) for item in items) / dam_count
        storage = sum(float(item["storage_mcm"]) for item in items)
        capacity = sum(float(item["capacity_mcm"]) for item in items)
        representative = sorted(items, key=lambda item: (float(item["rainfall_daily_mm"]), float(item["filling_percent"])), reverse=True)[0]

        catchment_proxy = max(80.0, dam_count * 125.0 + storage * 0.18 + capacity * 0.025)
        runoff_base = max(0.4, avg_rain * 0.38 + avg_filling / 130.0)
        attenuation = min(0.35, storage / 8500.0)
        watch = max(18.0, runoff_base * 2.1 + dam_count * 0.55)
        flood = watch * 1.45
        danger = flood * 1.35
        rows = build_node_series(latest_date, runoff_base, catchment_proxy, attenuation)
        peak = max(float(row.get("reforecast_p90_cms") or row.get("reanalysis_discharge_cms") or 0.0) for row in rows)

        nodes.append(
            {
                "name": f"{basin} GRRR project runoff node",
                "basin": basin,
                "latitude": round(float(representative["latitude"]), 6),
                "longitude": round(float(representative["longitude"]), 6),
                "dam_count": dam_count,
                "avg_filling": round(avg_filling, 2),
                "avg_rainfall_mm": round(avg_rain, 2),
                "storage_mcm": round(storage, 2),
                "catchment_proxy_sq_km": round(catchment_proxy, 2),
                "forecast_days": 7,
                "risk_band": risk_band(peak, watch, flood, danger),
                "source_status": "project_preprocessed_grrr_json_pending_google_runoff_export",
                "thresholds": {
                    "watch_cms": round(watch, 3),
                    "flood_cms": round(flood, 3),
                    "danger_cms": round(danger, 3),
                },
                "linked_dams": sorted(str(item["name"]) for item in items),
                "series": rows,
            }
        )

    OUTPUT_JSON.parent.mkdir(exist_ok=True)
    payload = {
        "metadata": {
            "title": "MPWRD VBSR project-area Google Runoff Reanalysis/Reforecast-compatible JSON",
            "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "source_report_folder": latest_dir.name,
            "latest_observation_date": latest_date.isoformat(),
            "note": "Project preprocessed dynamic JSON. Replace series with Google Runoff Reanalysis/Reforecast notebook or API export when the live pipeline is configured.",
        },
        "nodes": nodes,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_JSON}")
    print(f"nodes={len(nodes)} dams={sum(int(node['dam_count']) for node in nodes)}")


if __name__ == "__main__":
    main()
