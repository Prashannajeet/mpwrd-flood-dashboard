from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_step(name: str, command: list[str], cwd: Path) -> dict:
    started = datetime.now(timezone.utc)
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    ended = datetime.now(timezone.utc)
    return {
        "name": name,
        "command": command,
        "return_code": result.returncode,
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "status": "success" if result.returncode == 0 else "failed",
    }


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_markdown_report(path: Path, summary: dict) -> None:
    lines = [
        "# V02 Bias-Correction Pipeline Status",
        "",
        f"- Run status: {summary.get('status')}",
        f"- Generated at: {summary.get('generated_at')}",
        f"- Database: `{summary.get('database')}`",
        f"- Input directory: `{summary.get('input_dir')}`",
        "",
        "## Metrics",
        "",
    ]
    metrics = summary.get("metrics", {})
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Steps", ""])
    for step in summary.get("steps", []):
        lines.append(f"- {step.get('name')}: {step.get('status')} ({step.get('return_code')})")
    if summary.get("failed_steps"):
        lines.extend(["", "## Failed Steps", ""])
        for step in summary["failed_steps"]:
            lines.append(f"### {step.get('name')}")
            if step.get("stderr"):
                lines.append("```")
                lines.append(step["stderr"][-4000:])
                lines.append("```")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the V02 CWC/GD bias-correction refresh pipeline.")
    parser.add_argument("--app-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()

    app_dir = args.app_dir.resolve()
    data_dir = app_dir / "data" / "bias_correction"
    db_path = data_dir / "cwc_bias_correction.sqlite"
    hindcast_csv = data_dir / "historical_model_hindcast_template.csv"
    training_csv = data_dir / "historical_forecast_observation_training.csv"

    steps = [
        (
            "Build CWC bias database",
            [
                str(args.python),
                str(app_dir / "scripts" / "build_cwc_bias_database.py"),
                "--input-dir",
                str(data_dir),
                "--output-db",
                str(db_path),
            ],
        ),
        (
            "Build hindcast/CWC training overlap",
            [
                str(args.python),
                str(app_dir / "scripts" / "build_hindcast_training_overlap.py"),
                "--db",
                str(db_path),
                "--hindcast-csv",
                str(hindcast_csv),
                "--training-output-csv",
                str(training_csv),
            ],
        ),
        (
            "Train/apply baseline bias correction",
            [
                str(args.python),
                str(app_dir / "scripts" / "train_baseline_bias_correction.py"),
                "--db",
                str(db_path),
                "--training-csv",
                str(training_csv),
            ],
        ),
    ]

    run_results = []
    for name, command in steps:
        result = run_step(name, command, app_dir)
        run_results.append(result)
        if result["return_code"] != 0:
            break

    db_summary = read_json(data_dir / "cwc_bias_database_summary.json")
    overlap_summary = read_json(data_dir / "hindcast_training_overlap_summary.json")
    correction_summary = read_json(data_dir / "baseline_bias_correction_summary.json")
    metrics = {
        "cwc_daily_rows": db_summary.get("cwc_daily_rows", 0),
        "cwc_stations": db_summary.get("cwc_stations", 0),
        "training_ready_stations": db_summary.get("training_ready_stations", 0),
        "review_approved_links": db_summary.get("review_approved_links", 0),
        "gauge_travel_links": db_summary.get("gauge_travel_links", 0),
        "hindcast_rows": overlap_summary.get("hindcast_rows", 0),
        "training_overlap_rows": overlap_summary.get("training_overlap_rows", 0),
        "bias_factor_rows": correction_summary.get("factor_rows", 0),
        "calibrated_rows": correction_summary.get("calibrated_rows", 0),
        "bias_mode": correction_summary.get("mode", "unknown"),
    }
    failed_steps = [step for step in run_results if step["return_code"] != 0]
    summary = {
        "status": "failed" if failed_steps else "success",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_dir": str(app_dir),
        "input_dir": str(data_dir),
        "database": str(db_path),
        "metrics": metrics,
        "steps": run_results,
        "failed_steps": failed_steps,
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "v02_pipeline_status.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown_report(data_dir / "v02_pipeline_status.md", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"steps", "failed_steps"}}, indent=2))
    sys.exit(1 if failed_steps else 0)


if __name__ == "__main__":
    main()
