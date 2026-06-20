from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


TIME_FROM_FILENAME = [
    (re.compile(r"8\s*am|08\s*am", re.I), time(8, 0)),
    (re.compile(r"12\s*pm", re.I), time(12, 0)),
    (re.compile(r"4\s*pm|04\s*pm", re.I), time(16, 0)),
    (re.compile(r"8\s*pm|08\s*pm", re.I), time(20, 0)),
]


@dataclass
class ReportMeta:
    report_date: str
    report_time: str
    season_year: int
    source_filename: str
    source_file_hash: str
    extraction_method: str


@dataclass
class RiverObservation:
    source_row_no: int
    river_name: str
    gauge_station: str
    district: str
    danger_or_max_water_level_m: float | None
    observed_at: str
    water_level_m: float | None


@dataclass
class ReservoirObservation:
    source_row_no: int
    reservoir_name: str
    district: str
    lsl_m: float | None
    frl_m: float | None
    live_capacity_frl_mcm: float | None
    observed_at: str
    water_level_m: float | None
    current_live_capacity_mcm: float | None
    filling_percent: float | None
    rainfall_daily_mm: float | None
    rainfall_total_mm: float | None


@dataclass
class GateObservation:
    source_row_no: int
    reservoir_name: str
    district: str
    total_no_of_gates: int | None
    gate_opened_count: int | None
    opening_m: float | None
    gate_opening_date: str | None
    gate_opening_time: str | None
    discharge_cumecs: float | None
    discharge_cusec: float | None


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def to_float(value: str) -> float | None:
    value = value.strip()
    if value in {"", "-", "NA", "N/A"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def to_int(value: str) -> int | None:
    value = value.strip()
    if value in {"", "-", "NA", "N/A"}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = []
    for page_no, page in enumerate(reader.pages, start=1):
        pages.append(f"\n---PAGE {page_no}---\n{page.extract_text() or ''}")
    return "\n".join(pages)


def parse_report_date(text: str, fallback_name: str) -> date:
    match = re.search(r"Dated:\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", text, re.I)
    if match:
        day, month, year = map(int, match.groups())
        return date(year, month, day)
    match = re.search(r"(\d{1,2})-(\d{1,2})-(\d{2,4})", fallback_name)
    if not match:
        raise ValueError("Could not determine report date")
    day, month, year = map(int, match.groups())
    if year < 100:
        year += 2000
    return date(year, month, day)


def parse_report_time(filename: str) -> time:
    for pattern, parsed_time in TIME_FROM_FILENAME:
        if pattern.search(filename):
            return parsed_time
    return time(12, 0)


def observation_times(report_date: date, report_time: time) -> list[datetime]:
    previous_day = report_date - timedelta(days=1)
    schedule = [
        datetime.combine(previous_day, time(16, 0)),
        datetime.combine(previous_day, time(20, 0)),
        datetime.combine(report_date, time(8, 0)),
        datetime.combine(report_date, report_time),
    ]
    return sorted(set(schedule))


def latest_observation_times(report_date: date, report_time: time, count: int) -> list[datetime]:
    previous_day = report_date - timedelta(days=1)
    report_dt = datetime.combine(report_date, report_time)
    schedule = [
        datetime.combine(previous_day, time(16, 0)),
        datetime.combine(previous_day, time(20, 0)),
        datetime.combine(report_date, time(8, 0)),
        datetime.combine(report_date, time(12, 0)),
        datetime.combine(report_date, time(16, 0)),
        datetime.combine(report_date, time(20, 0)),
    ]
    available = [observed_at for observed_at in schedule if observed_at <= report_dt]
    return available[-count:]


def section(text: str, start: str, end: str | None = None) -> str:
    start_idx = text.find(start)
    if start_idx == -1:
        return ""
    end_idx = text.find(end, start_idx) if end else len(text)
    if end_idx == -1:
        end_idx = len(text)
    return text[start_idx:end_idx]


def parse_river_rows(text: str, report_date: date, report_time: time) -> list[RiverObservation]:
    rows = []
    for line in text.splitlines():
        line = clean_text(line)
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if not match:
            continue
        row_no = int(match.group(1))
        tokens = match.group(2).split()
        numeric_tail = []
        while tokens and re.fullmatch(r"[\d.]+|-", tokens[-1]):
            numeric_tail.insert(0, tokens.pop())
        if len(numeric_tail) < 4 or not tokens:
            continue
        river_name = tokens[0]
        district = tokens[-1]
        gauge_station = " ".join(tokens[1:-1])
        max_level = to_float(numeric_tail[0])
        levels = [to_float(value) for value in numeric_tail[1:]]
        obs_times = latest_observation_times(report_date, report_time, len(levels))
        for observed_at, level in zip(obs_times, levels):
            rows.append(
                RiverObservation(
                    row_no,
                    river_name,
                    gauge_station,
                    district,
                    max_level,
                    observed_at.isoformat(sep=" "),
                    level,
                )
            )
    return rows


def split_name_district(prefix: str) -> tuple[str, str]:
    parts = prefix.split()
    if len(parts) < 2:
        return prefix, ""
    return " ".join(parts[:-1]), parts[-1]


def parse_reservoir_rows(text: str, report_date: date, report_time: time) -> list[ReservoirObservation]:
    rows = []
    for line in text.splitlines():
        line = clean_text(line)
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if not match:
            continue
        row_no = int(match.group(1))
        if not 1 <= row_no <= 80:
            continue
        tokens = match.group(2).split()
        numeric_tail = []
        while tokens and re.fullmatch(r"[\d.]+|-", tokens[-1]):
            numeric_tail.insert(0, tokens.pop())
        if len(numeric_tail) not in {10, 11} or not tokens:
            continue
        name, district = split_name_district(" ".join(tokens))
        values = [to_float(value) for value in numeric_tail]
        lsl = values[0]
        frl = values[1]
        level_count = len(values) - 7
        levels = values[2 : 2 + level_count]
        live_cap, current_cap, filling, rain_daily, rain_total = values[-5:]
        # Some PDF text rows can include spacing artifacts; skip river rows by plausible LSL/FRL test.
        if lsl is None or frl is None or frl < 150:
            continue
        obs_times = latest_observation_times(report_date, report_time, len(levels))
        for observed_at, level in zip(obs_times, levels):
            rows.append(
                ReservoirObservation(
                    row_no,
                    name,
                    district,
                    lsl,
                    frl,
                    live_cap,
                    observed_at.isoformat(sep=" "),
                    level,
                    current_cap,
                    filling,
                    rain_daily,
                    rain_total,
                )
            )
    return rows


def parse_gate_date(value: str, report_year: int) -> str | None:
    if value in {"", "-", "NA"}:
        return None
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", value)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    if year < 100:
        year += 2000
    return date(year, month, day).isoformat()


def parse_gate_time(value: str) -> str | None:
    if value in {"", "-", "NA"}:
        return None
    match = re.match(r"(\d{1,2})(?::?(\d{2}))?\s*(am|pm)?", value, re.I)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return time(hour, minute).isoformat()


def parse_gate_rows(text: str, report_year: int) -> list[GateObservation]:
    rows = []
    pattern = re.compile(
        r"^(\d+)\s+(.+?)\s+([A-Za-z]+)\s+([A-Za-z0-9]+)\s+"
        r"([A-Za-z0-9-]+)\s+([A-Za-z0-9.-]+)\s+([0-9/-]+|-)\s+"
        r"([0-9:apmAPM]+|-)\s+([\d.]+|-)\s+([\d.]+|-)\s*$"
    )
    for line in text.splitlines():
        line = clean_text(line)
        match = pattern.match(line)
        if not match:
            continue
        row_no = int(match.group(1))
        rows.append(
            GateObservation(
                source_row_no=row_no,
                reservoir_name=match.group(2),
                district=match.group(3),
                total_no_of_gates=to_int(match.group(4)),
                gate_opened_count=to_int(match.group(5)),
                opening_m=to_float(match.group(6)),
                gate_opening_date=parse_gate_date(match.group(7), report_year),
                gate_opening_time=parse_gate_time(match.group(8)),
                discharge_cumecs=to_float(match.group(9)),
                discharge_cusec=to_float(match.group(10)),
            )
        )
    return rows


def write_csv(path: Path, rows: Iterable[object]) -> None:
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_dict_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def river_master_rows(rows: list[RiverObservation]) -> list[dict]:
    unique = {}
    for row in rows:
        key = (row.river_name, row.gauge_station, row.district)
        unique[key] = {
            "river_name": row.river_name,
            "gauge_station": row.gauge_station,
            "district": row.district,
            "danger_or_max_water_level_m": row.danger_or_max_water_level_m,
        }
    return list(unique.values())


def reservoir_master_rows(
    reservoir_rows: list[ReservoirObservation], gate_rows: list[GateObservation]
) -> list[dict]:
    gates_by_reservoir = {
        (row.reservoir_name, row.district): row.total_no_of_gates for row in gate_rows
    }
    unique = {}
    for row in reservoir_rows:
        key = (row.reservoir_name, row.district)
        unique[key] = {
            "reservoir_name": row.reservoir_name,
            "district": row.district,
            "lsl_m": row.lsl_m,
            "frl_m": row.frl_m,
            "live_capacity_frl_mcm": row.live_capacity_frl_mcm,
            "total_no_of_gates": gates_by_reservoir.get(key),
        }
    return list(unique.values())


def parse_pdf(pdf_path: Path, out_dir: Path) -> dict[str, int]:
    text = pdf_text(pdf_path)
    report_date = parse_report_date(text, pdf_path.name)
    report_time = parse_report_time(pdf_path.name)
    file_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    meta = ReportMeta(
        report_date=report_date.isoformat(),
        report_time=report_time.isoformat(),
        season_year=report_date.year,
        source_filename=pdf_path.name,
        source_file_hash=file_hash,
        extraction_method="embedded_text",
    )

    river_text = section(text, "(A) Water Level in Rivers", "(B) Water Level in Reservoirs")
    reservoir_text = section(text, "(B) Water Level in Reservoirs", "(C) Position of Reservoir Gates")
    gate_text = section(text, "(C) Position of Reservoir Gates")

    rivers = parse_river_rows(river_text, report_date, report_time)
    reservoirs = parse_reservoir_rows(reservoir_text, report_date, report_time)
    gates = parse_gate_rows(gate_text, report_date.year)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_meta.json").write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")
    write_dict_csv(out_dir / "river_gauge_stations.csv", river_master_rows(rivers))
    write_dict_csv(out_dir / "reservoirs.csv", reservoir_master_rows(reservoirs, gates))
    write_csv(out_dir / "river_water_level_observations.csv", rivers)
    write_csv(out_dir / "reservoir_status_observations.csv", reservoirs)
    write_csv(out_dir / "reservoir_gate_observations.csv", gates)

    return {
        "river_observation_rows": len(rivers),
        "reservoir_observation_rows": len(reservoirs),
        "gate_observation_rows": len(gates),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse MP WRD flood report PDF into normalized CSV files.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("parsed_flood_report"))
    args = parser.parse_args()
    counts = parse_pdf(args.pdf, args.out_dir)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
