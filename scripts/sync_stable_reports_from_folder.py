from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_SOURCE = Path(r"D:\01 Project\Development\Flood Reports")
MANIFEST_CSV = APP_DIR / "data" / "stable_report_sync_manifest.csv"
MANIFEST_JSON = APP_DIR / "data" / "stable_report_sync_manifest.json"

sys.path.insert(0, str(APP_DIR))
from flood_report_parser import parse_pdf  # noqa: E402


def parsed_folder_name(pdf_path: Path) -> str:
    return f"parsed_{pdf_path.stem.replace(' ', '_')}"


def read_count(csv_path: Path) -> int:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return 0
    try:
        return len(pd.read_csv(csv_path))
    except Exception:
        return 0


def read_meta(parsed_dir: Path) -> dict:
    meta_path = parsed_dir / "report_meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parsed_status(parsed_dir: Path) -> dict:
    meta = read_meta(parsed_dir)
    river_rows = read_count(parsed_dir / "river_water_level_observations.csv")
    reservoir_rows = read_count(parsed_dir / "reservoir_status_observations.csv")
    gate_rows = read_count(parsed_dir / "reservoir_gate_observations.csv")
    valid = bool(meta) and river_rows > 0 and reservoir_rows > 0
    reason = "valid" if valid else "zero/missing usable reservoir or river rows"
    return {
        "report_date": meta.get("report_date", ""),
        "report_time": meta.get("report_time", ""),
        "river_rows": river_rows,
        "reservoir_rows": reservoir_rows,
        "gate_rows": gate_rows,
        "valid": valid,
        "reason": reason,
    }


def status_quality(status: dict, parsed_dir: Path) -> tuple[int, int, float]:
    return (
        int(status.get("reservoir_rows") or 0),
        int(status.get("river_rows") or 0),
        float(parsed_dir.stat().st_mtime) if parsed_dir.exists() else 0.0,
    )


def status_row_quality(status: dict) -> tuple[int, int]:
    return (int(status.get("reservoir_rows") or 0), int(status.get("river_rows") or 0))


def source_pdfs(source_dir: Path) -> list[Path]:
    return sorted(
        [path for path in source_dir.glob("*.pdf") if path.is_file()],
        key=lambda path: (path.stat().st_mtime, path.name.lower()),
    )


def sync_reports(source_dir: Path, keep_invalid: bool = False, force: bool = False) -> list[dict]:
    source_dir = source_dir.resolve()
    if not source_dir.exists():
        raise FileNotFoundError(f"Report source folder not found: {source_dir}")

    valid_slots: dict[tuple[str, str], Path] = {}
    for parsed_dir in APP_DIR.glob("parsed_*"):
        if not parsed_dir.is_dir():
            continue
        status = parsed_status(parsed_dir)
        if status["valid"]:
            slot_key = (str(status["report_date"]), str(status["report_time"]))
            existing = valid_slots.get(slot_key)
            if existing is None or status_quality(status, parsed_dir) >= status_quality(parsed_status(existing), existing):
                valid_slots[slot_key] = parsed_dir

    manifest_rows: list[dict] = []
    for pdf_path in source_pdfs(source_dir):
        out_dir = APP_DIR / parsed_folder_name(pdf_path)
        action = "existing"
        if force and out_dir.exists():
            shutil.rmtree(out_dir)
        if not (out_dir / "report_meta.json").exists():
            out_dir.mkdir(exist_ok=True)
            action = "parsed"
            try:
                parse_pdf(pdf_path, out_dir)
            except Exception as exc:
                shutil.rmtree(out_dir, ignore_errors=True)
                manifest_rows.append(
                    {
                        "pdf_name": pdf_path.name,
                        "parsed_folder": out_dir.name,
                        "action": "failed",
                        "valid": False,
                        "reason": str(exc),
                        "report_date": "",
                        "report_time": "",
                        "river_rows": 0,
                        "reservoir_rows": 0,
                        "gate_rows": 0,
                    }
                )
                continue

        status = parsed_status(out_dir)
        slot_key = (str(status.get("report_date")), str(status.get("report_time")))
        existing_slot_dir = valid_slots.get(slot_key)
        if status["valid"] and existing_slot_dir is not None and existing_slot_dir != out_dir and not force:
            existing_status = parsed_status(existing_slot_dir)
            if status_row_quality(status) > status_row_quality(existing_status):
                valid_slots[slot_key] = out_dir
            else:
                if action == "parsed":
                    shutil.rmtree(out_dir, ignore_errors=True)
                status = {
                    **existing_status,
                    "valid": True,
                    "reason": f"date/time slot already covered by {existing_slot_dir.name}",
                }
                action = "covered_existing_slot"
                out_dir = existing_slot_dir
        elif status["valid"]:
            valid_slots[slot_key] = out_dir

        if not status["valid"] and not keep_invalid:
            if action == "parsed":
                shutil.rmtree(out_dir, ignore_errors=True)
            action = "rejected"

        manifest_rows.append(
            {
                "pdf_name": pdf_path.name,
                "parsed_folder": out_dir.name,
                "action": action,
                **status,
            }
        )

    return sorted(manifest_rows, key=lambda row: (str(row.get("report_date")), str(row.get("report_time")), str(row.get("pdf_name"))))


def expected_daily_dates(rows: list[dict]) -> list[str]:
    valid_dates = sorted({row["report_date"] for row in rows if row.get("valid") and row.get("report_date")})
    if len(valid_dates) < 2:
        return []
    start = pd.to_datetime(valid_dates[0]).date()
    end = pd.to_datetime(valid_dates[-1]).date()
    return [date.strftime("%Y-%m-%d") for date in pd.date_range(start, end, freq="D")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync official report PDFs into stable parsed-report folders.")
    parser.add_argument("--source", type=Path, default=DEFAULT_REPORT_SOURCE, help="Folder containing official report PDFs.")
    parser.add_argument("--keep-invalid", action="store_true", help="Keep zero-row parses for debugging. Default rejects them.")
    parser.add_argument("--force", action="store_true", help="Re-parse existing folders from source PDFs.")
    args = parser.parse_args()

    rows = sync_reports(args.source, keep_invalid=args.keep_invalid, force=args.force)
    MANIFEST_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(MANIFEST_CSV, index=False)
    MANIFEST_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    valid_rows = [row for row in rows if row.get("valid")]
    valid_dates = sorted({row["report_date"] for row in valid_rows if row.get("report_date")})
    expected_dates = expected_daily_dates(rows)
    missing_dates = [value for value in expected_dates if value not in valid_dates]

    print(f"Source folder: {args.source}")
    print(f"PDF files reviewed: {len(rows)}")
    print(f"Valid parsed reports: {len(valid_rows)}")
    print(f"Latest valid report: {valid_dates[-1] if valid_dates else 'none'}")
    if missing_dates:
        print("Missing valid daily dates: " + ", ".join(missing_dates))
    rejected = [row for row in rows if not row.get("valid")]
    if rejected:
        print("Rejected/failed reports:")
        for row in rejected:
            print(f" - {row['pdf_name']}: {row['reason']}")
    print(f"Manifest written: {MANIFEST_CSV}")
    return 0 if valid_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
