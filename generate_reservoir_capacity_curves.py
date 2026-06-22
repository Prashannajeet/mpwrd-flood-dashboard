from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
CAPACITY_ESTIMATES_CSV = APP_DIR / "data" / "reservoir_capacity_estimates.csv"
OUTPUT_CSV = APP_DIR / "data" / "reservoir_capacity_curves.csv"
OUTPUT_JSON = APP_DIR / "data" / "reservoir_capacity_curves.json"


def to_float(value: object, default: float | None = None) -> float | None:
    try:
        if value in (None, "") or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_curve(row: pd.Series, steps: int = 25) -> list[dict[str, object]]:
    lsl = to_float(row.get("lsl_m"))
    frl = to_float(row.get("frl_m"))
    capacity = to_float(row.get("calibrated_capacity_mcm")) or to_float(row.get("official_live_capacity_mcm"))
    top_area = to_float(row.get("waterbody_area_sqkm"))
    if lsl is None or frl is None or capacity is None or capacity <= 0 or frl <= lsl:
        return []

    depth = frl - lsl
    curve_method = "official_capacity_power_curve"
    beta = 1.35
    if top_area and top_area > 0:
        raw_beta = (top_area * depth / capacity) - 1
        if raw_beta >= 0.08:
            beta = min(raw_beta, 5.0)
            curve_method = "rs_top_area_official_capacity_calibrated"
        else:
            beta = 0.08
            curve_method = "rs_top_area_inconsistent_screening_clamped"
    else:
        top_area = capacity * (beta + 1) / depth
        curve_method = "official_capacity_default_shape_no_rs_area"

    rows: list[dict[str, object]] = []
    for index in range(steps + 1):
        fraction = index / steps
        elevation = lsl + depth * fraction
        area_sqkm = 0.0 if fraction == 0 else top_area * (fraction**beta)
        storage_mcm = capacity * (fraction ** (beta + 1))
        rows.append(
            {
                "reservoir_name": row.get("reservoir_name"),
                "dam_name": row.get("dam_name"),
                "district": row.get("district"),
                "sub_basin": row.get("sub_basin"),
                "major_basin": row.get("major_basin"),
                "elevation_m": round(elevation, 3),
                "relative_depth_fraction": round(fraction, 4),
                "water_spread_area_sqkm": round(area_sqkm, 5),
                "cumulative_storage_mcm": round(storage_mcm, 5),
                "storage_percent": round(fraction ** (beta + 1) * 100, 3),
                "curve_beta": round(beta, 5),
                "curve_method": curve_method,
                "capacity_confidence": row.get("capacity_confidence"),
            }
        )
    return rows


def main() -> None:
    if not CAPACITY_ESTIMATES_CSV.exists():
        raise FileNotFoundError(f"Run generate_reservoir_capacity_estimates.py first: {CAPACITY_ESTIMATES_CSV}")
    estimates = pd.read_csv(CAPACITY_ESTIMATES_CSV)
    curve_rows: list[dict[str, object]] = []
    for _, row in estimates.iterrows():
        curve_rows.extend(build_curve(row))

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
                    "note": "Stage 2A calibrated hypsometric curves. Replace/augment with FABDEM sampled curves when DEM tiles are connected.",
                },
                "records": curves.where(pd.notna(curves), None).to_dict("records"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_CSV}")
    print(f"curve_rows={len(curves)} reservoirs={curves['reservoir_name'].nunique() if not curves.empty else 0}")


if __name__ == "__main__":
    main()
