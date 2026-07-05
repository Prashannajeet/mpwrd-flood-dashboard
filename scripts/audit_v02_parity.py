from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


CORE_FEATURE_PATTERNS = {
    "Water Watch page": r'"Water Watch"',
    "Dam DSS & Analytics page": r'"Dam DSS & Analytics"',
    "GD Site Analytics page": r'"GD Site Analytics"',
    "Weather Forecast page": r'"Weather Forecast"',
    "3D Flood Scenarios page": r'"3D Flood Scenarios"',
    "Data & Timeseries page": r'"Data & Timeseries"',
    "Report Generation page": r'"Report Generation"',
    "Administration page": r'"Administration"',
    "Water Watch Leaflet map": r"render_infographic_leaflet_map",
    "Dam/GD Leaflet map": r"render_gd_site_leaflet_map",
    "ArcGIS/GEOGLOWS layer support": r"GEOGLOWS_MEDIUM_URL",
    "Weather DSS": r"render_weather_forecast_page|Weather Data",
    "AI DSS assistant": r"render_dashboard_assistant",
    "Admin operations": r"render_admin_operations",
    "Report builder": r"build_pdf_report",
    "Capacity DSS": r"reservoir_capacity|Capacity DSS",
    "Email alert framework": r"send_email|Messaging Alerts",
}

V02_FEATURE_PATTERNS = {
    "CWC bias correction database": r"CWC_BIAS_CORRECTION_DB",
    "CWC historical calibration": r"V02 CWC Historical Calibration",
    "GD-CWC linkage review": r"V02 GD-CWC Linkage Review",
    "Gauge travel-time correlations": r"gauge_travel_time_correlations|Gauge-to-gauge",
    "Downstream warning window": r"Downstream warning window",
    "Hindcast intake": r"historical_model_hindcast|hindcast",
    "Bias correction readiness": r"V02 Bias Correction Readiness",
    "V02 pipeline status": r"V02 Pipeline Status",
}


def git_executable() -> str:
    candidates = [
        Path(r"C:\Users\Welcome\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe"),
        Path(r"C:\Program Files\Git\cmd\git.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "git"


def read_text_at_commit(repo: Path, commit: str, file_path: str) -> str:
    result = subprocess.run(
        [git_executable(), "-c", f"safe.directory={repo.as_posix()}", "show", f"{commit}:{file_path}"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def read_current_text(repo: Path, file_path: str) -> str:
    return (repo / file_path).read_text(encoding="utf-8")


def extract_functions(source: str) -> set[str]:
    tree = ast.parse(source)
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def extract_nav_pages(source: str) -> list[str]:
    match = re.search(r"nav_pages\s*=\s*\[(.*?)\]", source, flags=re.S)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def pattern_status(source: str, patterns: dict[str, str]) -> dict[str, bool]:
    return {name: bool(re.search(pattern, source, flags=re.I | re.S)) for name, pattern in patterns.items()}


def build_report(repo: Path, v01_ref: str, v02_ref: str) -> dict:
    v01_source = read_text_at_commit(repo, v01_ref, "flood_report_app.py")
    v02_source = read_current_text(repo, "flood_report_app.py") if v02_ref == "working-tree" else read_text_at_commit(repo, v02_ref, "flood_report_app.py")

    v01_functions = extract_functions(v01_source)
    v02_functions = extract_functions(v02_source)
    v01_pages = extract_nav_pages(v01_source)
    v02_pages = extract_nav_pages(v02_source)
    missing_functions = sorted(v01_functions - v02_functions)
    added_functions = sorted(v02_functions - v01_functions)
    missing_pages = [page for page in v01_pages if page not in v02_pages]
    added_pages = [page for page in v02_pages if page not in v01_pages]
    core_features = pattern_status(v02_source, CORE_FEATURE_PATTERNS)
    v02_features = pattern_status(v02_source, V02_FEATURE_PATTERNS)
    failed_core_features = [name for name, present in core_features.items() if not present]
    failed_v02_features = [name for name, present in v02_features.items() if not present]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "v01_ref": v01_ref,
        "v02_ref": v02_ref,
        "status": "pass" if not missing_functions and not missing_pages and not failed_core_features and not failed_v02_features else "review",
        "v01_function_count": len(v01_functions),
        "v02_function_count": len(v02_functions),
        "missing_v01_functions_in_v02": missing_functions,
        "v02_added_functions": added_functions,
        "v01_nav_pages": v01_pages,
        "v02_nav_pages": v02_pages,
        "missing_v01_pages_in_v02": missing_pages,
        "v02_added_pages": added_pages,
        "core_feature_presence": core_features,
        "v02_feature_presence": v02_features,
        "failed_core_features": failed_core_features,
        "failed_v02_features": failed_v02_features,
    }


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# V02 Feature Parity Audit",
        "",
        f"- Status: {report['status']}",
        f"- Generated at: {report['generated_at']}",
        f"- V01 reference: `{report['v01_ref']}`",
        f"- V02 reference: `{report['v02_ref']}`",
        f"- V01 function count: {report['v01_function_count']}",
        f"- V02 function count: {report['v02_function_count']}",
        "",
        "## Navigation Pages",
        "",
        f"- Missing V01 pages in V02: {', '.join(report['missing_v01_pages_in_v02']) or 'None'}",
        f"- V02 added pages: {', '.join(report['v02_added_pages']) or 'None'}",
        "",
        "## Core V01 Feature Signals In V02",
        "",
    ]
    for name, present in report["core_feature_presence"].items():
        lines.append(f"- {'OK' if present else 'REVIEW'}: {name}")
    lines.extend(["", "## V02 Enhancement Signals", ""])
    for name, present in report["v02_feature_presence"].items():
        lines.append(f"- {'OK' if present else 'REVIEW'}: {name}")
    lines.extend(["", "## Function Parity", ""])
    lines.append(f"- Missing V01 functions in V02: {len(report['missing_v01_functions_in_v02'])}")
    if report["missing_v01_functions_in_v02"]:
        for name in report["missing_v01_functions_in_v02"]:
            lines.append(f"  - {name}")
    lines.append(f"- V02 added functions: {len(report['v02_added_functions'])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit whether V02 remains a feature superset of V01.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--v01-ref", default="v01")
    parser.add_argument("--v02-ref", default="working-tree")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    args = parser.parse_args()

    repo = args.repo.resolve()
    report = build_report(repo, args.v01_ref, args.v02_ref)
    output_json = args.output_json or repo / "data" / "bias_correction" / "v02_feature_parity_audit.json"
    output_md = args.output_md or repo / "data" / "bias_correction" / "v02_feature_parity_audit.md"
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(output_md, report)
    print(json.dumps({k: report[k] for k in ["status", "v01_function_count", "v02_function_count", "missing_v01_pages_in_v02", "failed_core_features", "failed_v02_features"]}, indent=2))


if __name__ == "__main__":
    main()
