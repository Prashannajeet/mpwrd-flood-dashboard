from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
FORECAST_CSV = DATA_DIR / "gd_site_online_forecasts.csv"
SITES_GEOJSON = DATA_DIR / "gd_sites_swedes.geojson"
MAX_AGE_HOURS = 12.0
MAX_LINK_DISTANCE_M = 25_000.0
MIN_SITE_COVERAGE = 0.95


def parse_time(value: str) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []
    if not FORECAST_CSV.exists():
        print(f"FAIL: missing forecast file: {FORECAST_CSV}")
        return 1
    if not SITES_GEOJSON.exists():
        print(f"FAIL: missing GD site master: {SITES_GEOJSON}")
        return 1

    with FORECAST_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    site_master = json.loads(SITES_GEOJSON.read_text(encoding="utf-8"))
    expected_sites = {
        str((feature.get("properties") or {}).get("Station Co") or "").strip()
        for feature in site_master.get("features", [])
        if feature.get("geometry")
    }
    expected_sites.discard("")
    forecast_sites = {str(row.get("station_code") or "").strip() for row in rows}
    forecast_sites.discard("")

    if not rows:
        failures.append("forecast CSV has no records")
    coverage = len(forecast_sites & expected_sites) / max(1, len(expected_sites))
    if coverage < MIN_SITE_COVERAGE:
        failures.append(f"station coverage is {coverage:.1%}; expected at least {MIN_SITE_COVERAGE:.0%}")

    now = datetime.now(timezone.utc)
    nearest_ages: list[float] = []
    link_distances: list[float] = []
    return_periods: list[float] = []
    for station_code in forecast_sites:
        station_rows = [row for row in rows if str(row.get("station_code") or "").strip() == station_code]
        timestamps = [parse_time(row.get("forecast_time", "")) for row in station_rows]
        valid_times = [value for value in timestamps if value is not None]
        if not valid_times:
            failures.append(f"{station_code}: no valid forecast timestamps")
            continue
        nearest_ages.append(min(abs((value - now).total_seconds()) for value in valid_times) / 3600.0)
        distances = [number(row.get("distance_m", "")) for row in station_rows]
        link_distances.extend(value for value in distances if math.isfinite(value))
        periods = [number(row.get("returnperiod", "")) for row in station_rows]
        return_periods.extend(value for value in periods if math.isfinite(value))

    median_age = statistics.median(nearest_ages) if nearest_ages else math.inf
    if median_age > MAX_AGE_HOURS:
        failures.append(f"median current-signal age is {median_age:.1f} h; maximum is {MAX_AGE_HOURS:.0f} h")
    max_distance = max(link_distances, default=math.inf)
    if max_distance > MAX_LINK_DISTANCE_M:
        failures.append(f"maximum reach-link distance is {max_distance / 1000:.2f} km; maximum is 25 km")
    if return_periods and max(return_periods) <= 0:
        warnings.append("all model return-period values are zero; do not interpret this as verified absence of flooding")

    print(
        "GD forecast quality: "
        f"rows={len(rows):,}, sites={len(forecast_sites)}/{len(expected_sites)}, "
        f"coverage={coverage:.1%}, median_age={median_age:.2f} h, "
        f"max_link={max_distance / 1000:.2f} km"
    )
    for warning in warnings:
        print(f"WARN: {warning}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: GD forecast feed meets freshness, coverage, and linkage-distance requirements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
