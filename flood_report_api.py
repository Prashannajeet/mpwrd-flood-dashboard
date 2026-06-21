from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


APP_DIR = Path(__file__).resolve().parent
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
DAM_SHAPEFILE = APP_DIR / "dam_shapefile" / "Dams_EinC_54_R2.shp"


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def parsed_directories() -> list[Path]:
    return sorted(
        [
            path
            for path in APP_DIR.iterdir()
            if path.is_dir()
            and path.name.startswith("parsed_")
            and (path / "report_meta.json").exists()
        ],
        key=lambda path: path.name,
    )


def normalize_name(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    for word in ["project", "major", "medium", "dam", "tank", "sagar", "reservoir"]:
        text = re.sub(rf"\b{word}\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def best_match_name(source_name: str, candidates: list[str]) -> tuple[str | None, float]:
    source_norm = normalize_name(source_name)
    if not source_norm:
        return None, 0.0
    candidate_lookup = {candidate: normalize_name(candidate) for candidate in candidates}
    for candidate, candidate_norm in candidate_lookup.items():
        if source_norm == candidate_norm:
            return candidate, 1.0
        if source_norm and candidate_norm and (source_norm in candidate_norm or candidate_norm in source_norm):
            return candidate, 0.92
    scored = [
        (candidate, SequenceMatcher(None, source_norm, candidate_norm).ratio())
        for candidate, candidate_norm in candidate_lookup.items()
    ]
    if not scored:
        return None, 0.0
    return max(scored, key=lambda item: item[1])


def report_datetime(meta: dict[str, Any]) -> pd.Timestamp:
    return pd.to_datetime(
        f"{meta.get('report_date', '')} {meta.get('report_time', '')}",
        errors="coerce",
    )


def add_report_context(frame: pd.DataFrame, meta: dict[str, Any], report_id: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["report_id"] = report_id
    frame["report_at"] = report_datetime(meta)
    frame["report_date"] = meta.get("report_date")
    frame["report_time"] = meta.get("report_time")
    frame["source_filename"] = meta.get("source_filename", report_id)
    return frame


def load_dataset(parsed_dir: Path) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = json.loads((parsed_dir / "report_meta.json").read_text(encoding="utf-8"))
    river_master = read_csv(parsed_dir / "river_gauge_stations.csv")
    reservoir_master = read_csv(parsed_dir / "reservoirs.csv")
    rivers = read_csv(parsed_dir / "river_water_level_observations.csv")
    reservoirs = read_csv(parsed_dir / "reservoir_status_observations.csv")
    gates = read_csv(parsed_dir / "reservoir_gate_observations.csv")
    for frame in [rivers, reservoirs, gates]:
        if "observed_at" in frame:
            frame["observed_at"] = pd.to_datetime(frame["observed_at"], errors="coerce")
    return meta, river_master, reservoir_master, rivers, reservoirs, gates


@lru_cache(maxsize=1)
def load_all_data() -> dict[str, pd.DataFrame]:
    report_rows: list[dict[str, Any]] = []
    river_master_rows: list[pd.DataFrame] = []
    reservoir_master_rows: list[pd.DataFrame] = []
    river_rows: list[pd.DataFrame] = []
    reservoir_rows: list[pd.DataFrame] = []
    gate_rows: list[pd.DataFrame] = []

    for parsed_dir in parsed_directories():
        meta, river_master, reservoir_master, rivers, reservoirs, gates = load_dataset(parsed_dir)
        report_id = parsed_dir.name
        report_rows.append(
            {
                "report_id": report_id,
                "report_at": report_datetime(meta),
                "report_date": meta.get("report_date"),
                "report_time": meta.get("report_time"),
                "source_filename": meta.get("source_filename", report_id),
                "extraction_method": meta.get("extraction_method", "-"),
            }
        )
        river_master_rows.append(add_report_context(river_master, meta, report_id))
        reservoir_master_rows.append(add_report_context(reservoir_master, meta, report_id))
        river_rows.append(add_report_context(rivers, meta, report_id))
        reservoir_rows.append(add_report_context(reservoirs, meta, report_id))
        gate_rows.append(add_report_context(gates, meta, report_id))

    reports = pd.DataFrame(report_rows).sort_values("report_at") if report_rows else pd.DataFrame()
    rivers = pd.concat(river_rows, ignore_index=True) if river_rows else pd.DataFrame()
    reservoirs = pd.concat(reservoir_rows, ignore_index=True) if reservoir_rows else pd.DataFrame()
    gates = pd.concat(gate_rows, ignore_index=True) if gate_rows else pd.DataFrame()
    river_master = pd.concat(river_master_rows, ignore_index=True) if river_master_rows else pd.DataFrame()
    reservoir_master = pd.concat(reservoir_master_rows, ignore_index=True) if reservoir_master_rows else pd.DataFrame()

    if not reservoirs.empty:
        reservoirs["frl_gap_m"] = reservoirs["frl_m"] - reservoirs["water_level_m"]
    if not rivers.empty:
        rivers["danger_gap_m"] = rivers["danger_or_max_water_level_m"] - rivers["water_level_m"]

    if not river_master.empty:
        river_master = river_master.drop_duplicates(["river_name", "gauge_station", "district"])
    if not reservoir_master.empty:
        reservoir_master = reservoir_master.drop_duplicates(["reservoir_name", "district"])

    return {
        "reports": reports,
        "river_master": river_master,
        "reservoir_master": reservoir_master,
        "rivers": rivers,
        "reservoirs": reservoirs,
        "gates": gates,
    }


@lru_cache(maxsize=1)
def load_dam_locations() -> pd.DataFrame:
    if DAM_LOCATIONS_CSV.exists():
        return pd.read_csv(DAM_LOCATIONS_CSV)

    if not DAM_SHAPEFILE.exists():
        return pd.DataFrame()
    import geopandas as gpd

    gdf = gpd.read_file(DAM_SHAPEFILE)
    if "Lat" in gdf.columns and "Long" in gdf.columns:
        gdf["latitude"] = pd.to_numeric(gdf["Lat"], errors="coerce")
        gdf["longitude"] = pd.to_numeric(gdf["Long"], errors="coerce")
    else:
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)
        points = gdf.to_crs(epsg=4326).geometry.centroid
        gdf["latitude"] = points.y
        gdf["longitude"] = points.x

    columns = [
        column
        for column in ["DamName", "SUB_NAME", "MAJ_NAME", "dist_nm_e", "latitude", "longitude", "Water_Leve", "Filled"]
        if column in gdf.columns
    ]
    dams = pd.DataFrame(gdf[columns]).dropna(subset=["latitude", "longitude"])
    dams = dams.rename(
        columns={
            "DamName": "dam_name",
            "SUB_NAME": "sub_basin",
            "MAJ_NAME": "major_basin",
            "dist_nm_e": "map_district",
            "Water_Leve": "map_water_level_m",
            "Filled": "map_filled_percent",
        }
    )
    for column in ["dam_name", "sub_basin", "major_basin", "map_district"]:
        if column in dams:
            dams[column] = dams[column].fillna("").astype(str)
    return dams


def latest_by_asset(frame: pd.DataFrame, asset_col: str) -> pd.DataFrame:
    if frame.empty or "observed_at" not in frame:
        return frame
    return frame.sort_values("observed_at").groupby([asset_col, "district"], as_index=False).tail(1)


def with_dam_status() -> pd.DataFrame:
    data = load_all_data()
    dams = load_dam_locations().copy()
    reservoirs = data["reservoirs"]
    if dams.empty:
        return dams
    reservoir_names = sorted(reservoirs["reservoir_name"].dropna().unique()) if not reservoirs.empty else []
    if reservoir_names:
        matched_rows = []
        for row in dams.to_dict("records"):
            matched, score = best_match_name(row.get("dam_name", ""), reservoir_names)
            row["reservoir_name"] = matched
            row["match_score"] = score
            matched_rows.append(row)
        dams = pd.DataFrame(matched_rows)
    else:
        dams["reservoir_name"] = None
        dams["match_score"] = 0.0

    latest = (
        reservoirs.sort_values("observed_at").groupby("reservoir_name", as_index=False).tail(1)
        if not reservoirs.empty and "observed_at" in reservoirs
        else reservoirs
    )
    if not latest.empty:
        dams = dams.merge(
            latest[
                [
                    "reservoir_name",
                    "district",
                    "observed_at",
                    "water_level_m",
                    "frl_m",
                    "frl_gap_m",
                    "filling_percent",
                    "current_live_capacity_mcm",
                    "rainfall_daily_mm",
                    "report_id",
                ]
            ],
            on="reservoir_name",
            how="left",
        )
    dams["display_filling"] = pd.to_numeric(
        dams.get("filling_percent", dams.get("map_filled_percent")), errors="coerce"
    ).fillna(pd.to_numeric(dams.get("map_filled_percent"), errors="coerce"))
    dams["alert_level"] = dams.apply(alert_level, axis=1)
    return dams


def alert_level(row: pd.Series) -> str:
    filling = row.get("display_filling", 0)
    gap = row.get("frl_gap_m")
    if pd.notna(gap) and gap <= 0.5:
        return "Critical"
    if pd.notna(gap) and gap <= 1.5:
        return "Warning"
    if pd.notna(filling) and filling >= 90:
        return "Watch"
    return "Normal"


def serializable_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    clean = frame.copy()
    for column in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[column]):
            clean[column] = clean[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    rows = []
    for row in clean.to_dict("records"):
        cleaned = {}
        for key, value in row.items():
            if value is None or value is pd.NA:
                cleaned[key] = None
            elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                cleaned[key] = None
            elif pd.isna(value):
                cleaned[key] = None
            else:
                cleaned[key] = value
        rows.append(cleaned)
    return rows


def filtered(frame: pd.DataFrame, query: dict[str, str]) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return result
    if query.get("date_from") and "observed_at" in result:
        result = result[result["observed_at"] >= pd.to_datetime(query["date_from"])]
    if query.get("date_to") and "observed_at" in result:
        result = result[result["observed_at"] <= pd.to_datetime(query["date_to"])]
    if query.get("district") and "district" in result:
        districts = {value.strip() for value in query["district"].split(",")}
        result = result[result["district"].isin(districts)]
    if query.get("reservoir") and "reservoir_name" in result:
        reservoirs = {value.strip() for value in query["reservoir"].split(",")}
        result = result[result["reservoir_name"].isin(reservoirs)]
    if query.get("river") and "river_name" in result:
        rivers = {value.strip() for value in query["river"].split(",")}
        result = result[result["river_name"].isin(rivers)]
    if query.get("gauge") and "gauge_station" in result:
        gauges = {value.strip() for value in query["gauge"].split(",")}
        result = result[result["gauge_station"].isin(gauges)]
    if query.get("basin"):
        basins = {value.strip() for value in query["basin"].split(",")}
        basin_mask = pd.Series([False] * len(result), index=result.index)
        for column in ["sub_basin", "major_basin", "basin"]:
            if column in result:
                basin_mask = basin_mask | result[column].isin(basins)
        result = result[basin_mask]
    if query.get("alert_level") and "alert_level" in result:
        levels = {value.strip() for value in query["alert_level"].split(",")}
        result = result[result["alert_level"].isin(levels)]
    return result


def to_geojson(frame: pd.DataFrame) -> dict[str, Any]:
    features = []
    for row in serializable_rows(frame):
        lon = row.pop("longitude", None)
        lat = row.pop("latitude", None)
        if lon is None or lat is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": row,
            }
        )
    return {"type": "FeatureCollection", "features": features}


async def index(_request):
    return JSONResponse(
        {
            "service": "MP WRD Flood Dashboard API",
            "rest": [
                "/api/reports",
                "/api/reservoirs",
                "/api/reservoir-observations",
                "/api/river-gauges",
                "/api/river-observations",
                "/api/gates",
                "/api/district-summary",
                "/api/basin-summary",
            ],
            "geojson": [
                "/api/geojson/dams",
                "/api/geojson/reservoir-status",
                "/api/geojson/alerts",
            ],
            "filters": "Optional query filters: date_from, date_to, district, reservoir, river, gauge, alert_level",
        }
    )


async def reports(_request):
    return JSONResponse(serializable_rows(load_all_data()["reports"]))


async def reservoirs(request):
    return JSONResponse(serializable_rows(filtered(load_all_data()["reservoir_master"], dict(request.query_params))))


async def reservoir_observations(request):
    return JSONResponse(serializable_rows(filtered(load_all_data()["reservoirs"], dict(request.query_params))))


async def river_gauges(request):
    return JSONResponse(serializable_rows(filtered(load_all_data()["river_master"], dict(request.query_params))))


async def river_observations(request):
    return JSONResponse(serializable_rows(filtered(load_all_data()["rivers"], dict(request.query_params))))


async def gates(request):
    return JSONResponse(serializable_rows(filtered(load_all_data()["gates"], dict(request.query_params))))


async def district_summary(request):
    reservoirs = filtered(load_all_data()["reservoirs"], dict(request.query_params))
    if reservoirs.empty:
        return JSONResponse([])
    latest = latest_by_asset(reservoirs, "reservoir_name")
    summary = (
        latest.groupby("district", as_index=False)
        .agg(
            reservoirs=("reservoir_name", "nunique"),
            avg_filling_percent=("filling_percent", "mean"),
            max_filling_percent=("filling_percent", "max"),
            avg_frl_gap_m=("frl_gap_m", "mean"),
            daily_rainfall_mm=("rainfall_daily_mm", "sum"),
        )
        .sort_values("avg_filling_percent", ascending=False)
    )
    return JSONResponse(serializable_rows(summary))


async def basin_summary(request):
    dams = filtered(with_dam_status(), dict(request.query_params))
    if dams.empty:
        return JSONResponse([])
    summary = (
        dams.groupby(["major_basin", "sub_basin"], as_index=False)
        .agg(
            dams=("dam_name", "nunique"),
            matched_reservoirs=("reservoir_name", "nunique"),
            avg_filling_percent=("display_filling", "mean"),
            critical_alerts=("alert_level", lambda values: (values == "Critical").sum()),
            warning_alerts=("alert_level", lambda values: (values == "Warning").sum()),
        )
        .sort_values(["critical_alerts", "warning_alerts", "avg_filling_percent"], ascending=False)
    )
    return JSONResponse(serializable_rows(summary))


async def geojson_dams(request):
    return JSONResponse(to_geojson(filtered(with_dam_status(), dict(request.query_params))))


async def geojson_reservoir_status(request):
    dams = with_dam_status()
    dams = dams[dams["reservoir_name"].notna()] if not dams.empty and "reservoir_name" in dams else dams
    return JSONResponse(to_geojson(filtered(dams, dict(request.query_params))))


async def geojson_alerts(request):
    dams = with_dam_status()
    if not dams.empty:
        dams = dams[dams["alert_level"].isin(["Critical", "Warning", "Watch"])]
    return JSONResponse(to_geojson(filtered(dams, dict(request.query_params))))


async def refresh(_request):
    load_all_data.cache_clear()
    load_dam_locations.cache_clear()
    return JSONResponse({"status": "cache refreshed", "refreshed_at": datetime.now().isoformat(timespec="seconds")})


routes = [
    Route("/", index),
    Route("/api/reports", reports),
    Route("/api/reservoirs", reservoirs),
    Route("/api/reservoir-observations", reservoir_observations),
    Route("/api/river-gauges", river_gauges),
    Route("/api/river-observations", river_observations),
    Route("/api/gates", gates),
    Route("/api/district-summary", district_summary),
    Route("/api/basin-summary", basin_summary),
    Route("/api/geojson/dams", geojson_dams),
    Route("/api/geojson/reservoir-status", geojson_reservoir_status),
    Route("/api/geojson/alerts", geojson_alerts),
    Route("/api/refresh", refresh, methods=["POST", "GET"]),
]

app = Starlette(debug=False, routes=routes)
