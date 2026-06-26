from __future__ import annotations

import argparse
import json
import math
import os
import re
import smtplib
import sqlite3
import time
from email.message import EmailMessage
from html import escape
from pathlib import Path

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
ALERT_DB = APP_DIR / "data" / "alert_dispatch.sqlite"
DEFAULT_INTERVAL_SECONDS = 60 * 60


def load_simple_toml(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


SECRETS = load_simple_toml(APP_DIR / ".streamlit" / "secrets.toml")


def secret(name: str, env_name: str, default: str = "") -> str:
    return os.getenv(env_name) or SECRETS.get(name, default)


def smtp_config() -> dict:
    return {
        "host": secret("smtp_host", "SMTP_HOST"),
        "port": int(secret("smtp_port", "SMTP_PORT", "587") or "587"),
        "username": secret("smtp_username", "SMTP_USERNAME"),
        "password": secret("smtp_password", "SMTP_PASSWORD"),
        "sender": secret("smtp_from", "SMTP_FROM", secret("smtp_username", "SMTP_USERNAME")),
        "use_tls": secret("smtp_use_tls", "SMTP_USE_TLS", "true").lower() not in {"0", "false", "no", "off"},
        "use_ssl": secret("smtp_use_ssl", "SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"},
    }


def parse_recipients(text: str) -> list[str]:
    emails = re.findall(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}", text or "")
    return sorted(set(emails))


def configured_recipients() -> list[str]:
    text = secret("alert_email_recipients", "ALERT_EMAIL_RECIPIENTS", "")
    if not text:
        text = secret("alert_recipients", "ALERT_RECIPIENTS", "info@nitageoai.com")
    return parse_recipients(text)


def fmt_number(value: object, suffix: str = "") -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
    except Exception:
        if value is None:
            return "-"
    try:
        number = float(value)
        if math.isnan(number):
            return "-"
        return f"{number:.2f}{suffix}"
    except Exception:
        return f"{value}{suffix}"


def parsed_directories() -> list[Path]:
    return sorted(
        [
            path
            for path in APP_DIR.iterdir()
            if path.is_dir()
            and (path / "report_meta.json").exists()
            and (path / "reservoir_status_observations.csv").exists()
        ],
        key=lambda path: path.name,
    )


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def load_latest_reservoirs() -> pd.DataFrame:
    frames = []
    for folder in parsed_directories():
        frame = read_csv(folder / "reservoir_status_observations.csv")
        if frame.empty:
            continue
        meta = json.loads((folder / "report_meta.json").read_text(encoding="utf-8"))
        report_at = pd.to_datetime(f"{meta.get('report_date')} {meta.get('report_time')}", errors="coerce")
        frame["observed_at"] = report_at
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    reservoirs = pd.concat(frames, ignore_index=True)
    reservoirs["observed_at"] = pd.to_datetime(reservoirs["observed_at"], errors="coerce")
    reservoirs["water_level_m"] = pd.to_numeric(reservoirs.get("water_level_m"), errors="coerce")
    reservoirs = reservoirs.sort_values(["reservoir_name", "observed_at"])
    reservoirs["wl_delta_m"] = reservoirs.groupby("reservoir_name")["water_level_m"].diff()
    return reservoirs.groupby("reservoir_name", as_index=False).tail(1).reset_index(drop=True)


def load_alert_rows() -> pd.DataFrame:
    latest = load_latest_reservoirs()
    dams = read_csv(DAM_LOCATIONS_CSV)
    if latest.empty or dams.empty:
        return pd.DataFrame()
    if "reservoir_name" not in dams.columns and "dam_name" in dams.columns:
        dams["reservoir_name"] = dams["dam_name"]
    merged = dams.merge(
        latest,
        on="reservoir_name",
        how="left",
        suffixes=("_map", ""),
    )
    merged["display_filling"] = pd.to_numeric(merged.get("filling_percent"), errors="coerce").fillna(
        pd.to_numeric(merged.get("map_filled_percent"), errors="coerce")
    )
    merged["frl_gap_m"] = pd.to_numeric(merged.get("frl_gap_m"), errors="coerce")
    merged["water_level_m"] = pd.to_numeric(merged.get("water_level_m"), errors="coerce")
    merged["frl_m"] = pd.to_numeric(merged.get("frl_m"), errors="coerce")
    merged["wl_delta_m"] = pd.to_numeric(merged.get("wl_delta_m"), errors="coerce")

    critical_gap = float(secret("dam_critical_gap", "DAM_CRITICAL_GAP", "0.5") or "0.5")
    warning_gap = float(secret("dam_warning_gap", "DAM_WARNING_GAP", "1.5") or "1.5")
    watch_filling = float(secret("dam_watch_filling", "DAM_WATCH_FILLING", "90") or "90")
    rapid_rise = float(secret("rapid_rise_threshold", "RAPID_RISE_THRESHOLD", "0.30") or "0.30")

    def classify(row: pd.Series) -> str:
        gap = row.get("frl_gap_m")
        filling = row.get("display_filling")
        if pd.notna(gap) and gap <= critical_gap:
            return "Critical"
        if pd.notna(gap) and gap <= warning_gap:
            return "Warning"
        if pd.notna(filling) and filling >= watch_filling:
            return "Watch"
        return "Normal"

    merged["configured_alert"] = merged.apply(classify, axis=1)
    merged["rapid_rise_alert"] = merged["wl_delta_m"].fillna(0) >= rapid_rise
    alerts = merged[(merged["configured_alert"] != "Normal") | merged["rapid_rise_alert"]].copy()
    if alerts.empty:
        return alerts
    alerts["alert_reason"] = alerts.apply(
        lambda row: "Rapid rise"
        if bool(row.get("rapid_rise_alert")) and row.get("configured_alert") == "Normal"
        else f"FRL gap {fmt_number(row.get('frl_gap_m'), ' m')}",
        axis=1,
    )
    return alerts.sort_values(["configured_alert", "frl_gap_m", "display_filling"], ascending=[True, True, False])


def plain_message(row: pd.Series) -> str:
    return (
        "MPWRD Dam Alert\n"
        f"Reservoir: {row.get('reservoir_name') or row.get('dam_name')}\n"
        f"District: {row.get('district') or row.get('map_district') or '-'}\n"
        f"Basin: {row.get('sub_basin') or row.get('major_basin') or '-'}\n"
        f"Current WL: {fmt_number(row.get('water_level_m'), ' m')}\n"
        f"FRL Gap: {fmt_number(row.get('frl_gap_m'), ' m')}\n"
        f"Filling: {fmt_number(row.get('display_filling'), '%')}\n"
        f"Alert Level: {row.get('configured_alert')}\n"
        "Action: Monitor inflow, gates, and downstream warning protocol."
    )


def html_message(row: pd.Series, text: str) -> str:
    alert = str(row.get("configured_alert") or "Alert")
    accent = {"Critical": "#dc2626", "Warning": "#f59e0b", "Watch": "#eab308"}.get(alert, "#2563eb")
    reservoir = row.get("reservoir_name") or row.get("dam_name") or "Reservoir"
    observed_at = pd.to_datetime(row.get("observed_at"), errors="coerce")
    observed_label = observed_at.strftime("%d %b %Y, %I:%M %p") if pd.notna(observed_at) else "Latest observation"
    metrics = [
        ("Reservoir", reservoir),
        ("District", row.get("district") or row.get("map_district") or "-"),
        ("Basin", row.get("sub_basin") or row.get("major_basin") or "-"),
        ("Observed At", observed_label),
        ("Current Water Level", fmt_number(row.get("water_level_m"), " m")),
        ("FRL", fmt_number(row.get("frl_m"), " m")),
        ("FRL Gap", fmt_number(row.get("frl_gap_m"), " m")),
        ("Filling", fmt_number(row.get("display_filling"), "%")),
        ("Latest WL Change", fmt_number(row.get("wl_delta_m"), " m")),
        ("Alert Reason", row.get("alert_reason") or "-"),
    ]
    metric_rows = "".join(
        f"<tr><td style='padding:10px;border-bottom:1px solid #e5edf7;color:#64748b'>{escape(str(k))}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #e5edf7;font-weight:700;color:#0f172a'>{escape(str(v))}</td></tr>"
        for k, v in metrics
    )
    plain_lines = "".join(f"<li>{escape(line)}</li>" for line in text.splitlines() if line.strip())
    generated_at = pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y, %I:%M %p IST")
    return f"""<!doctype html>
<html><body style="margin:0;background:#eef3f8;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
<div style="max-width:720px;margin:0 auto;padding:24px;">
<div style="background:#0f172a;border-radius:14px 14px 0 0;padding:20px 24px;color:#fff;">
<div style="font-size:12px;letter-spacing:1.8px;text-transform:uppercase;color:#93c5fd;font-weight:700;">NITA AI & Geo-Analytics | MPWRD DSS</div>
<h1 style="margin:8px 0 4px;font-size:24px;">Automated Hourly Dam Alert</h1>
<div style="font-size:13px;color:#cbd5e1;">Generated: {escape(generated_at)}</div></div>
<div style="background:#fff;border:1px solid #dbe6f4;border-top:0;border-radius:0 0 14px 14px;overflow:hidden;">
<div style="padding:22px 24px;border-left:8px solid {accent};background:#fbfdff;">
<div style="display:inline-block;background:{accent};color:#fff;border-radius:999px;padding:7px 12px;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.8px;">{escape(alert)} Alert</div>
<h2 style="margin:12px 0 4px;font-size:22px;">{escape(str(reservoir))}</h2>
<p style="margin:0;color:#64748b;font-size:14px;">Private recipient delivery: addresses are not disclosed to other officials.</p></div>
<div style="padding:20px 24px;"><table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;border:1px solid #e5edf7;">{metric_rows}</table>
<div style="margin-top:18px;padding:16px;border-radius:10px;background:#f8fafc;border:1px solid #e5edf7;">
<b style="font-size:13px;color:#334155;text-transform:uppercase;letter-spacing:.9px;">Recommended DSS Actions</b>
<ol style="margin:8px 0 0;padding-left:20px;color:#334155;font-size:14px;line-height:1.55;">
<li>Verify current reservoir level, inflow, gate status and downstream gauge trend.</li>
<li>Keep district control room and dam safety officer on watch for rapid rise or FRL approach.</li>
<li>Escalate warning protocol if the next observation confirms rising level or reduced FRL gap.</li></ol></div>
<div style="margin-top:18px;padding:16px;border-radius:10px;background:#fff7ed;border:1px solid #fed7aa;">
<b style="font-size:13px;color:#9a3412;text-transform:uppercase;letter-spacing:.9px;">Operational Message</b>
<ul style="margin:8px 0 0;padding-left:18px;color:#431407;font-size:14px;line-height:1.55;">{plain_lines}</ul></div></div>
<div style="padding:14px 24px;background:#f1f5f9;color:#64748b;font-size:12px;border-top:1px solid #e5edf7;">Automated DSS email from MPWRD flood report observations and NITA GeoAI analytics. Validate with official field communication before public warning release.</div>
</div></div></body></html>"""


def init_database() -> None:
    ALERT_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ALERT_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_dispatch_log (
                dispatch_key TEXT PRIMARY KEY,
                sent_at TEXT NOT NULL,
                reservoir_name TEXT,
                alert_level TEXT,
                observed_at TEXT,
                recipients INTEGER,
                status TEXT
            )
            """
        )
        conn.commit()


def already_sent(dispatch_key: str) -> bool:
    init_database()
    with sqlite3.connect(ALERT_DB) as conn:
        row = conn.execute("SELECT 1 FROM alert_dispatch_log WHERE dispatch_key = ?", (dispatch_key,)).fetchone()
    return bool(row)


def record_dispatch(dispatch_key: str, row: pd.Series, recipients: int, status: str) -> None:
    init_database()
    with sqlite3.connect(ALERT_DB) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO alert_dispatch_log
            (dispatch_key, sent_at, reservoir_name, alert_level, observed_at, recipients, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dispatch_key,
                pd.Timestamp.now(tz="Asia/Kolkata").isoformat(),
                str(row.get("reservoir_name") or row.get("dam_name") or ""),
                str(row.get("configured_alert") or ""),
                str(row.get("observed_at") or ""),
                recipients,
                status,
            ),
        )
        conn.commit()


def send_email_private(subject: str, text: str, html: str, recipients: list[str]) -> tuple[bool, str]:
    config = smtp_config()
    missing = [key for key in ["host", "username", "password", "sender"] if not str(config.get(key) or "").strip()]
    if missing:
        return False, f"Missing SMTP settings: {', '.join(missing)}"
    if not recipients:
        return False, "No recipients configured."
    try:
        smtp_class = smtplib.SMTP_SSL if config["use_ssl"] else smtplib.SMTP
        with smtp_class(config["host"], config["port"], timeout=30) as smtp:
            if config["use_tls"] and not config["use_ssl"]:
                smtp.starttls()
            smtp.login(config["username"], config["password"])
            for recipient in recipients:
                message = EmailMessage()
                message["Subject"] = subject
                message["From"] = config["sender"]
                message["To"] = recipient
                message.set_content(text)
                message.add_alternative(html, subtype="html")
                smtp.send_message(message)
        return True, f"Sent privately to {len(recipients)} recipient(s)."
    except Exception as exc:
        return False, f"Email failed: {exc}"


def dispatch_once(force: bool = False, dry_run: bool = False) -> None:
    recipients = configured_recipients()
    alerts = load_alert_rows()
    if alerts.empty:
        print("No active dam alerts.")
        return
    sent = 0
    skipped = 0
    for _, row in alerts.iterrows():
        observed_key = str(row.get("observed_at") or "")
        dispatch_key = "|".join(
            [
                str(row.get("reservoir_name") or row.get("dam_name") or ""),
                str(row.get("configured_alert") or ""),
                observed_key,
                pd.Timestamp.now(tz="Asia/Kolkata").strftime("%Y%m%d%H"),
            ]
        )
        if not force and already_sent(dispatch_key):
            skipped += 1
            continue
        subject = f"MPWRD {row.get('configured_alert')} Dam Alert: {row.get('reservoir_name') or row.get('dam_name')}"
        text = plain_message(row)
        html = html_message(row, text)
        if dry_run:
            ok, status = True, f"DRY RUN: would send privately to {len(recipients)} recipient(s)."
        else:
            ok, status = send_email_private(subject, text, html, recipients)
            record_dispatch(dispatch_key, row, len(recipients), status)
        print(f"{row.get('reservoir_name')}: {status}")
        if ok:
            sent += 1
    print(f"Alert dispatch complete. Sent: {sent}; skipped duplicate-hour alerts: {skipped}; active alerts: {len(alerts)}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send automated hourly MPWRD dam alert emails.")
    parser.add_argument("--loop", action="store_true", help="Run continuously every hour.")
    parser.add_argument("--force", action="store_true", help="Send even if this alert was already sent this hour.")
    parser.add_argument("--dry-run", action="store_true", help="List alerts without sending email or writing dispatch history.")
    args = parser.parse_args()
    while True:
        dispatch_once(force=args.force, dry_run=args.dry_run)
        if not args.loop:
            break
        time.sleep(DEFAULT_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
