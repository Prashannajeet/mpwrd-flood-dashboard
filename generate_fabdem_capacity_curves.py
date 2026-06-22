from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask

from generate_reservoir_capacity_curves import build_curve


APP_DIR = Path(__file__).resolve().parent
CAPACITY_ESTIMATES_CSV = APP_DIR / "data" / "reservoir_capacity_estimates.csv"
STAGE2A_CURVES_CSV = APP_DIR / "data" / "reservoir_capacity_curves.csv"
WATERBODIES_GEOJSON = (
    Path(r"D:\01 Project\Development")
    / "Altimetry"
    / "Shapefile"
    / "waterbodies_analysis_revised"
    / "waterbodies_top100_wgs84.geojson"
)
DEM_ZIP = Path(r"D:\01 Project\03 MPWRD\14 Digitial Atlas\01 Data\03 DEM\FABDEM\DEM_MP.zip")
DEM_MEMBER = "DEM_MP.tif"
DEM_RASTER = f"zip://{DEM_ZIP.as_posix()}!{DEM_MEMBER}"
OUTPUT_CSV = APP_DIR / "data" / "reservoir_capacity_curves_fabdem.csv"
OUTPUT_JSON = APP_DIR / "data" / "reservoir_capacity_curves_fabdem.json"


def to_float(value: object, default: float | None = None) -> float | None:
    try:
        if value in (None, "") or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\([^)]*\)", " ", text.lower())
    text = re.sub(r"\b(dam|reservoir|sagar|tank|project|barrage)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_waterbody(row: pd.Series, waterbodies: gpd.GeoDataFrame) -> pd.Series | None:
    if waterbodies.empty:
        return None
    lookup = {normalize_name(name): index for index, name in waterbodies["Name"].items()}
    candidates = [
        row.get("matched_waterbody_name"),
        row.get("reservoir_name"),
        row.get("dam_name"),
    ]
    for candidate in candidates:
        key = normalize_name(candidate)
        if key in lookup:
            return waterbodies.loc[lookup[key]]

    reservoir_key = normalize_name(row.get("reservoir_name"))
    if not reservoir_key:
        return None
    scored = [
        (SequenceMatcher(None, reservoir_key, normalize_name(name)).ratio(), index)
        for index, name in waterbodies["Name"].items()
    ]
    score, index = max(scored, key=lambda item: item[0])
    if score >= 0.72:
        return waterbodies.loc[index]
    return None


def build_fallback_rows(row: pd.Series, reason: str) -> list[dict[str, object]]:
    rows = build_curve(row)
    for item in rows:
        item["segmental_live_capacity_mcm"] = 0.0
        item["fabdem_sample_count"] = 0
        item["fabdem_min_m"] = None
        item["fabdem_max_m"] = None
        item["fabdem_p05_m"] = None
        item["fabdem_p95_m"] = None
        item["matched_waterbody_name"] = row.get("matched_waterbody_name")
        item["curve_method"] = f"stage2a_fallback_{reason}"
    for index in range(1, len(rows)):
        rows[index]["segmental_live_capacity_mcm"] = round(
            float(rows[index]["cumulative_storage_mcm"]) - float(rows[index - 1]["cumulative_storage_mcm"]),
            5,
        )
    return rows


def sample_polygon_dem(src: rasterio.DatasetReader, geometry: object) -> np.ndarray:
    data, _ = mask(src, [geometry], crop=True, filled=False, indexes=1)
    values = np.asarray(data.compressed() if np.ma.isMaskedArray(data) else data.ravel(), dtype="float64")
    nodata = src.nodata
    values = values[np.isfinite(values)]
    if nodata is not None and np.isfinite(nodata):
        values = values[np.abs(values - nodata) > 1e-6]
    values = values[(values > -100) & (values < 2000)]
    return values


def build_fabdem_curve(row: pd.Series, waterbody_row: pd.Series, values: np.ndarray, steps: int = 25) -> list[dict[str, object]]:
    lsl = to_float(row.get("lsl_m"))
    frl = to_float(row.get("frl_m"))
    official_capacity = to_float(row.get("calibrated_capacity_mcm")) or to_float(row.get("official_live_capacity_mcm"))
    top_area = to_float(row.get("waterbody_area_sqkm")) or to_float(waterbody_row.get("area_sqkm_calc"))
    if lsl is None or frl is None or official_capacity is None or official_capacity <= 0 or frl <= lsl:
        return build_fallback_rows(row, "missing_official_levels")
    if top_area is None or top_area <= 0:
        return build_fallback_rows(row, "missing_waterbody_area")
    if values.size < 50:
        return build_fallback_rows(row, "insufficient_dem_samples")

    p05, p95 = np.nanpercentile(values, [5, 95])
    if not np.isfinite(p05) or not np.isfinite(p95) or p95 <= p05:
        return build_fallback_rows(row, "flat_or_invalid_dem")

    normalized = np.clip((values - p05) / (p95 - p05), 0, 1)
    depth = frl - lsl
    raw_rows: list[dict[str, object]] = []
    cumulative = 0.0
    previous_area = 0.0
    previous_elevation = lsl
    for index in range(steps + 1):
        fraction = index / steps
        elevation = lsl + depth * fraction
        if index == 0:
            area_sqkm = 0.0
        elif index == steps:
            area_sqkm = top_area
        else:
            area_sqkm = float(np.count_nonzero(normalized <= fraction) / normalized.size) * top_area
        segment = 0.0 if index == 0 else ((previous_area + area_sqkm) / 2.0) * (elevation - previous_elevation)
        cumulative += segment
        raw_rows.append(
            {
                "index": index,
                "fraction": fraction,
                "elevation": elevation,
                "area_sqkm": area_sqkm,
                "segment": segment,
                "cumulative": cumulative,
            }
        )
        previous_area = area_sqkm
        previous_elevation = elevation

    scale = official_capacity / cumulative if cumulative > 0 else 1.0
    rows: list[dict[str, object]] = []
    previous_scaled = 0.0
    for item in raw_rows:
        storage = item["cumulative"] * scale
        segment_scaled = storage - previous_scaled if item["index"] else 0.0
        previous_scaled = storage
        rows.append(
            {
                "reservoir_name": row.get("reservoir_name"),
                "dam_name": row.get("dam_name"),
                "district": row.get("district"),
                "sub_basin": row.get("sub_basin"),
                "major_basin": row.get("major_basin"),
                "elevation_m": round(float(item["elevation"]), 3),
                "relative_depth_fraction": round(float(item["fraction"]), 4),
                "water_spread_area_sqkm": round(float(item["area_sqkm"]), 5),
                "segmental_live_capacity_mcm": round(float(segment_scaled), 5),
                "cumulative_storage_mcm": round(float(storage), 5),
                "storage_percent": round(float(storage / official_capacity * 100), 3),
                "curve_beta": None,
                "curve_method": "stage2b_fabdem_hypsometry_official_capacity_calibrated",
                "capacity_confidence": row.get("capacity_confidence"),
                "matched_waterbody_name": waterbody_row.get("Name"),
                "fabdem_sample_count": int(values.size),
                "fabdem_min_m": round(float(np.nanmin(values)), 3),
                "fabdem_max_m": round(float(np.nanmax(values)), 3),
                "fabdem_p05_m": round(float(p05), 3),
                "fabdem_p95_m": round(float(p95), 3),
            }
        )
    return rows


def main() -> None:
    if not CAPACITY_ESTIMATES_CSV.exists():
        raise FileNotFoundError(f"Run generate_reservoir_capacity_estimates.py first: {CAPACITY_ESTIMATES_CSV}")
    if not WATERBODIES_GEOJSON.exists():
        raise FileNotFoundError(f"Waterbody polygons not found: {WATERBODIES_GEOJSON}")
    if not DEM_ZIP.exists():
        raise FileNotFoundError(f"FABDEM zip not found: {DEM_ZIP}")

    estimates = pd.read_csv(CAPACITY_ESTIMATES_CSV)
    waterbodies = gpd.read_file(WATERBODIES_GEOJSON).to_crs("EPSG:4326")
    curve_rows: list[dict[str, object]] = []
    matched = 0
    dem_derived = 0

    with rasterio.open(DEM_RASTER) as src:
        for _, row in estimates.iterrows():
            waterbody_row = match_waterbody(row, waterbodies)
            if waterbody_row is None:
                curve_rows.extend(build_fallback_rows(row, "unmatched_waterbody"))
                print(f"fallback unmatched: {row.get('reservoir_name')}")
                continue
            matched += 1
            try:
                values = sample_polygon_dem(src, waterbody_row.geometry)
                rows = build_fabdem_curve(row, waterbody_row, values)
                if rows and str(rows[0].get("curve_method", "")).startswith("stage2b_fabdem"):
                    dem_derived += 1
                    print(f"FABDEM curve: {row.get('reservoir_name')} samples={len(values):,}")
                else:
                    print(f"fallback DEM: {row.get('reservoir_name')}")
                curve_rows.extend(rows)
            except Exception as exc:
                print(f"fallback error: {row.get('reservoir_name')} ({exc})")
                curve_rows.extend(build_fallback_rows(row, "dem_read_error"))

    curves = pd.DataFrame(curve_rows)
    OUTPUT_CSV.parent.mkdir(exist_ok=True)
    curves.to_csv(OUTPUT_CSV, index=False)
    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "metadata": {
                    "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                    "record_count": len(curves),
                    "reservoir_count": int(curves["reservoir_name"].nunique()) if not curves.empty else 0,
                    "matched_waterbody_count": matched,
                    "fabdem_derived_count": dem_derived,
                    "dem_source": str(DEM_ZIP),
                    "note": "Stage 2B FABDEM hypsometric curves calibrated to official LSL/FRL/live capacity. Fallback rows use Stage 2A where DEM sampling is unavailable.",
                },
                "records": curves.where(pd.notna(curves), None).to_dict("records"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_CSV}")
    print(f"curve_rows={len(curves)} reservoirs={curves['reservoir_name'].nunique() if not curves.empty else 0}")
    print(f"matched_waterbodies={matched} fabdem_derived={dem_derived}")


if __name__ == "__main__":
    main()
