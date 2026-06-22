from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
WATERBODY_AREA_CSV = (
    APP_DIR.parent
    / "Altimetry"
    / "Shapefile"
    / "waterbodies_analysis_revised"
    / "waterbodies_centroid_area_list.csv"
)
OUTPUT_CSV = APP_DIR / "data" / "reservoir_capacity_estimates.csv"
OUTPUT_JSON = APP_DIR / "data" / "reservoir_capacity_estimates.json"


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\b(major|minor|medium|project|dam|sagar|reservoir|barrage|tank)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def to_float(value: object, default: float | None = None) -> float | None:
    try:
        if value in (None, "") or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def haversine_km(lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None) -> float | None:
    if None in (lat1, lon1, lat2, lon2):
        return None
    values = [lat1, lon1, lat2, lon2]
    if not all(math.isfinite(float(value)) for value in values):
        return None
    radius_km = 6371.0088
    a_lat, a_lon, b_lat, b_lon = map(math.radians, map(float, values))
    d_lat = b_lat - a_lat
    d_lon = b_lon - a_lon
    a = math.sin(d_lat / 2) ** 2 + math.cos(a_lat) * math.cos(b_lat) * math.sin(d_lon / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def latest_parsed_report_dir() -> Path:
    parsed_dirs = [path for path in APP_DIR.iterdir() if path.is_dir() and path.name.startswith("parsed_")]
    if not parsed_dirs:
        raise FileNotFoundError("No parsed_* report folders found.")
    return sorted(parsed_dirs, key=lambda path: path.stat().st_mtime)[-1]


def best_waterbody_match(reservoir: dict[str, object], waterbodies: list[dict[str, object]]) -> dict[str, object]:
    reservoir_name = str(reservoir.get("reservoir_name") or reservoir.get("dam_name") or "")
    dam_name = str(reservoir.get("dam_name") or reservoir_name)
    target_names = [normalize_name(reservoir_name), normalize_name(dam_name)]
    dam_lat = to_float(reservoir.get("latitude"))
    dam_lon = to_float(reservoir.get("longitude"))
    best: dict[str, object] = {}
    best_score = -1.0
    for waterbody in waterbodies:
        wb_name = str(waterbody.get("Name") or "")
        wb_norm = normalize_name(wb_name)
        name_score = max((SequenceMatcher(None, target, wb_norm).ratio() for target in target_names if target and wb_norm), default=0.0)
        if any(target and (target in wb_norm or wb_norm in target) for target in target_names):
            name_score = max(name_score, 0.92)
        distance = haversine_km(
            dam_lat,
            dam_lon,
            to_float(waterbody.get("centroid_lat")),
            to_float(waterbody.get("centroid_lon")),
        )
        distance_score = 0.0 if distance is None else max(0.0, 1.0 - min(distance, 80.0) / 80.0)
        score = name_score * 0.72 + distance_score * 0.28
        if name_score >= 0.88:
            score += 0.18
        if distance is not None and distance <= 15:
            score += 0.08
        if score > best_score:
            best_score = score
            best = dict(waterbody)
            best["match_score"] = round(score, 4)
            best["name_score"] = round(name_score, 4)
            best["distance_km"] = round(distance, 3) if distance is not None else None
    if best_score < 0.48:
        return {}
    return best


def confidence_label(match: dict[str, object], official_capacity: float | None, shape_factor: float | None) -> str:
    if not match:
        return "Low - no remote-sensing waterbody match"
    score = to_float(match.get("match_score"), 0.0) or 0.0
    distance = to_float(match.get("distance_km"), 999.0) or 999.0
    if official_capacity and score >= 0.78 and distance <= 25 and shape_factor and 0.05 <= shape_factor <= 2.5:
        return "High - official capacity calibrated"
    if official_capacity and score >= 0.58:
        return "Medium - official capacity calibrated"
    return "Screening - RS geometry only"


def main() -> None:
    latest_dir = latest_parsed_report_dir()
    reservoirs = pd.read_csv(latest_dir / "reservoirs.csv")
    latest_status = pd.read_csv(latest_dir / "reservoir_status_observations.csv")
    dam_locations = pd.read_csv(DAM_LOCATIONS_CSV)
    waterbodies = pd.read_csv(WATERBODY_AREA_CSV).to_dict("records") if WATERBODY_AREA_CSV.exists() else []

    latest_status["observed_at"] = pd.to_datetime(latest_status["observed_at"], errors="coerce")
    latest_status = latest_status.sort_values("observed_at").drop_duplicates("reservoir_name", keep="last")
    locations_by_norm = {normalize_name(row["dam_name"]): row for row in dam_locations.to_dict("records")}

    rows: list[dict[str, object]] = []
    for reservoir in reservoirs.to_dict("records"):
        reservoir_name = str(reservoir.get("reservoir_name") or "")
        reservoir_norm = normalize_name(reservoir_name)
        dam_row = locations_by_norm.get(reservoir_norm)
        if dam_row is None:
            dam_row = max(
                dam_locations.to_dict("records"),
                key=lambda row: SequenceMatcher(None, reservoir_norm, normalize_name(row.get("dam_name"))).ratio(),
            )
        status_match = latest_status[latest_status["reservoir_name"] == reservoir_name]
        status = status_match.iloc[0].to_dict() if not status_match.empty else {}
        merged = {**reservoir, **dam_row, **status}
        match = best_waterbody_match(merged, waterbodies)

        lsl = to_float(reservoir.get("lsl_m"))
        frl = to_float(reservoir.get("frl_m"))
        active_depth = (frl - lsl) if lsl is not None and frl is not None else None
        official_capacity = to_float(reservoir.get("live_capacity_frl_mcm"))
        current_wl = to_float(status.get("water_level_m"))
        reported_current_storage = to_float(status.get("current_live_capacity_mcm"))
        waterbody_area = to_float(match.get("area_sqkm_calc")) if match else None
        rs_geometry_capacity = (
            waterbody_area * active_depth * 0.42
            if waterbody_area is not None and active_depth is not None and active_depth > 0
            else None
        )
        shape_factor = (
            official_capacity / (waterbody_area * active_depth)
            if official_capacity and waterbody_area and active_depth and active_depth > 0
            else None
        )
        calibrated_capacity = official_capacity or rs_geometry_capacity
        level_fraction = None
        model_current_storage = None
        if current_wl is not None and lsl is not None and frl is not None and frl > lsl and calibrated_capacity:
            level_fraction = max(0.0, min(1.0, (current_wl - lsl) / (frl - lsl)))
            model_current_storage = calibrated_capacity * (level_fraction**1.35)
        variance_pct = (
            ((model_current_storage - reported_current_storage) / official_capacity * 100)
            if model_current_storage is not None and reported_current_storage is not None and official_capacity
            else None
        )

        rows.append(
            {
                "reservoir_name": reservoir_name,
                "dam_name": dam_row.get("dam_name"),
                "district": reservoir.get("district") or dam_row.get("map_district"),
                "sub_basin": dam_row.get("sub_basin"),
                "major_basin": dam_row.get("major_basin"),
                "latitude": to_float(dam_row.get("latitude")),
                "longitude": to_float(dam_row.get("longitude")),
                "lsl_m": round(lsl, 3) if lsl is not None else None,
                "frl_m": round(frl, 3) if frl is not None else None,
                "active_depth_m": round(active_depth, 3) if active_depth is not None else None,
                "official_live_capacity_mcm": round(official_capacity, 3) if official_capacity is not None else None,
                "matched_waterbody_name": match.get("Name") if match else None,
                "waterbody_area_sqkm": round(waterbody_area, 4) if waterbody_area is not None else None,
                "waterbody_match_score": match.get("match_score") if match else None,
                "waterbody_distance_km": match.get("distance_km") if match else None,
                "rs_geometry_capacity_mcm": round(rs_geometry_capacity, 3) if rs_geometry_capacity is not None else None,
                "calibrated_capacity_mcm": round(calibrated_capacity, 3) if calibrated_capacity is not None else None,
                "hypsometric_shape_factor": round(shape_factor, 4) if shape_factor is not None else None,
                "latest_water_level_m": round(current_wl, 3) if current_wl is not None else None,
                "latest_reported_storage_mcm": round(reported_current_storage, 3) if reported_current_storage is not None else None,
                "model_storage_from_level_mcm": round(model_current_storage, 3) if model_current_storage is not None else None,
                "model_vs_reported_storage_pct_of_capacity": round(variance_pct, 3) if variance_pct is not None else None,
                "capacity_confidence": confidence_label(match, official_capacity, shape_factor),
                "method": "Official FRL capacity calibrated with RS waterbody area; RS geometry capacity is screening until FABDEM/altimetry curve is connected.",
            }
        )

    output = pd.DataFrame(rows).sort_values(["capacity_confidence", "district", "reservoir_name"])
    OUTPUT_CSV.parent.mkdir(exist_ok=True)
    output.to_csv(OUTPUT_CSV, index=False)
    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "metadata": {
                    "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                    "source_report_folder": latest_dir.name,
                    "waterbody_source": str(WATERBODY_AREA_CSV),
                    "record_count": len(output),
                },
                "records": output.where(pd.notna(output), None).to_dict("records"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_CSV}")
    print(f"records={len(output)} matched_waterbodies={output['matched_waterbody_name'].notna().sum()}")


if __name__ == "__main__":
    main()
