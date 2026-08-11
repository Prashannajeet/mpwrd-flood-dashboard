from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import smtplib
import sqlite3
import time
import tomllib
import urllib.error
import urllib.request
from email.message import EmailMessage
from html import escape
from pathlib import Path

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
DAM_LOCATIONS_CSV = APP_DIR / "dam_locations.csv"
GD_FORECAST_CSV = APP_DIR / "data" / "gd_site_online_forecasts.csv"
ALERT_DB = APP_DIR / "data" / "alert_dispatch.sqlite"
DEFAULT_INTERVAL_SECONDS = 60 * 60


def load_toml_secrets(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as secrets_file:
            values = tomllib.load(secrets_file)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return {str(key): value if isinstance(value, str) else str(value) for key, value in values.items()}


SECRETS = load_toml_secrets(APP_DIR / ".streamlit" / "secrets.toml")


def secret(name: str, env_name: str, default: str = "") -> str:
    return os.getenv(env_name) or SECRETS.get(name, default)


def smtp_config() -> dict:
    return {
        "provider": secret("email_provider", "EMAIL_PROVIDER", "auto").strip().lower(),
        "resend_api_key": secret("resend_api_key", "RESEND_API_KEY"),
        "brevo_api_key": secret("brevo_api_key", "BREVO_API_KEY"),
        "sendgrid_api_key": secret("sendgrid_api_key", "SENDGRID_API_KEY"),
        "host": secret("smtp_host", "SMTP_HOST"),
        "port": int(secret("smtp_port", "SMTP_PORT", "587") or "587"),
        "username": secret("smtp_username", "SMTP_USERNAME"),
        "password": secret("smtp_password", "SMTP_PASSWORD"),
        "sender": secret("smtp_from", "SMTP_FROM", secret("smtp_username", "SMTP_USERNAME")),
        "use_tls": secret("smtp_use_tls", "SMTP_USE_TLS", "true").lower() not in {"0", "false", "no", "off"},
        "use_ssl": secret("smtp_use_ssl", "SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"},
    }


def email_api_provider(config: dict) -> str:
    provider = str(config.get("provider") or "auto").strip().lower()
    if provider in {"resend", "brevo", "sendgrid"}:
        return provider
    if config.get("resend_api_key"):
        return "resend"
    if config.get("brevo_api_key"):
        return "brevo"
    if config.get("sendgrid_api_key"):
        return "sendgrid"
    return ""


def post_json(url: str, payload: dict, headers: dict) -> tuple[bool, str]:
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return 200 <= response.status < 300, body or f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return False, body or f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)


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
    alerts.loc[alerts["rapid_rise_alert"] & alerts["configured_alert"].eq("Normal"), "configured_alert"] = "Watch"
    return alerts.sort_values(["configured_alert", "frl_gap_m", "display_filling"], ascending=[True, True, False])


def alert_rank(level: object) -> int:
    return {"Critical": 4, "Warning": 3, "Watch": 2, "Normal": 1}.get(str(level or ""), 0)


def google_flood_rank(severity: object) -> int:
    text = str(severity or "").upper()
    if any(token in text for token in ["EXTREME", "SEVERE", "DANGER"]):
        return 4
    if any(token in text for token in ["HIGH", "FLOODING"]) and "NO_FLOODING" not in text:
        return 3
    if any(token in text for token in ["WARNING", "MODERATE"]):
        return 2
    if any(token in text for token in ["WATCH", "LOW", "ABOVE_NORMAL"]):
        return 1
    return 0


def flood_rank_level(rank: object) -> str:
    value = int(pd.to_numeric(pd.Series([rank]), errors="coerce").fillna(0).iloc[0])
    if value >= 3:
        return "Critical"
    if value >= 2:
        return "Warning"
    if value >= 1:
        return "Watch"
    return "Normal"


def haversine_km(lat1: object, lon1: object, lat2: object, lon2: object) -> float:
    values = pd.to_numeric(pd.Series([lat1, lon1, lat2, lon2]), errors="coerce")
    if values.isna().any():
        return math.nan
    lat1, lon1, lat2, lon2 = [math.radians(float(value)) for value in values]
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def fetch_google_flood_status() -> pd.DataFrame:
    api_key = secret("google_flood_api_key", "GOOGLE_FLOOD_API_KEY", "").strip()
    if not api_key:
        return pd.DataFrame()
    endpoint = f"https://floodforecasting.googleapis.com/v1/floodStatus:searchLatestFloodStatusByArea?key={api_key}"
    base_payload = {
        "pageSize": 20000,
        "loop": {
            "vertices": [
                {"latitude": 21.0, "longitude": 74.0},
                {"latitude": 21.0, "longitude": 83.0},
                {"latitude": 26.9, "longitude": 83.0},
                {"latitude": 26.9, "longitude": 74.0},
            ]
        },
        "includeNonQualityVerified": True,
    }
    statuses: list[dict] = []
    page_token = ""
    for _ in range(10):
        payload = dict(base_payload)
        if page_token:
            payload["pageToken"] = page_token
        try:
            request = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception:
            return pd.DataFrame()
        statuses.extend(item for item in result.get("floodStatuses", []) if isinstance(item, dict))
        page_token = str(result.get("nextPageToken") or "")
        if not page_token:
            break
    rows = []
    for item in statuses:
        location = item.get("gaugeLocation") if isinstance(item.get("gaugeLocation"), dict) else {}
        severity = item.get("severity") or item.get("floodStatus") or item.get("status") or "UNKNOWN"
        rank = google_flood_rank(severity)
        if rank <= 0:
            continue
        rows.append(
            {
                "google_gauge_id": item.get("gaugeId") or "",
                "flood_status": str(severity).replace("_", " ").title(),
                "flood_rank": rank,
                "latitude": pd.to_numeric(pd.Series([location.get("latitude")]), errors="coerce").iloc[0],
                "longitude": pd.to_numeric(pd.Series([location.get("longitude")]), errors="coerce").iloc[0],
                "issued_at": pd.to_datetime(item.get("issuedTime") or item.get("updateTime"), errors="coerce", utc=True),
            }
        )
    return pd.DataFrame(rows).dropna(subset=["latitude", "longitude"]) if rows else pd.DataFrame()


def load_gd_alert_rows() -> pd.DataFrame:
    forecasts = read_csv(GD_FORECAST_CSV)
    if forecasts.empty or not {"station_code", "forecast_time", "meanflow_cms"}.issubset(forecasts.columns):
        return pd.DataFrame()
    forecasts = forecasts.copy()
    forecasts["station_code"] = forecasts["station_code"].astype(str).str.strip()
    forecasts["forecast_time"] = pd.to_datetime(forecasts["forecast_time"], errors="coerce", utc=True)
    forecasts["meanflow_cms"] = pd.to_numeric(forecasts["meanflow_cms"], errors="coerce")
    forecasts["returnperiod"] = pd.to_numeric(forecasts.get("returnperiod"), errors="coerce").fillna(0)
    forecasts = forecasts.dropna(subset=["station_code", "forecast_time", "meanflow_cms"])
    if forecasts.empty:
        return pd.DataFrame()
    now_utc = pd.Timestamp.now(tz="UTC")
    latest_available = forecasts["forecast_time"].max()
    if pd.isna(latest_available) or abs((now_utc - latest_available).total_seconds()) > 10 * 24 * 3600:
        return pd.DataFrame()
    forecasts["time_distance"] = (forecasts["forecast_time"] - now_utc).abs()
    current = forecasts.loc[forecasts.groupby("station_code")["time_distance"].idxmin()].copy()
    future = forecasts[
        forecasts["forecast_time"].between(now_utc - pd.Timedelta(hours=6), now_utc + pd.Timedelta(days=7))
    ].copy()
    if future.empty:
        future = forecasts.copy()
    peak_indexes = future.groupby("station_code")["meanflow_cms"].idxmax()
    peaks = future.loc[peak_indexes, ["station_code", "forecast_time", "meanflow_cms", "returnperiod"]].rename(
        columns={
            "forecast_time": "peak_time",
            "meanflow_cms": "peak_flow_cms",
            "returnperiod": "peak_return_period",
        }
    )
    current = current.merge(peaks, on="station_code", how="left")
    current["return_period"] = current[["returnperiod", "peak_return_period"]].max(axis=1).fillna(0)
    current["alert_level"] = current["return_period"].apply(
        lambda value: "Critical" if value >= 25 else "Warning" if value >= 10 else "Watch" if value >= 2 else "Normal"
    )
    current["flood_status"] = ""
    flood_status = fetch_google_flood_status()
    if not flood_status.empty and {"latitude", "longitude"}.issubset(current.columns):
        for flood in flood_status.sort_values("flood_rank", ascending=False).to_dict("records"):
            distances = current.apply(
                lambda row: haversine_km(row.get("latitude"), row.get("longitude"), flood.get("latitude"), flood.get("longitude")),
                axis=1,
            )
            if distances.dropna().empty:
                continue
            nearest_index = distances.idxmin()
            if float(distances.loc[nearest_index]) > 30.0:
                continue
            flood_level = flood_rank_level(flood.get("flood_rank"))
            if alert_rank(flood_level) > alert_rank(current.at[nearest_index, "alert_level"]):
                current.at[nearest_index, "alert_level"] = flood_level
            current.at[nearest_index, "flood_status"] = flood.get("flood_status") or "Active flood status"
            current.at[nearest_index, "google_gauge_id"] = flood.get("google_gauge_id") or ""
    active = current[current["alert_level"] != "Normal"].copy()
    if active.empty:
        return active
    active["alert_rank"] = active["alert_level"].map({"Critical": 4, "Warning": 3, "Watch": 2}).fillna(0)
    return active.sort_values(["alert_rank", "return_period", "peak_flow_cms"], ascending=[False, False, False])


def plain_message(row: pd.Series) -> str:
    return (
        "Nita AI WaterWatch Dam Alert\n"
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
<div style="font-size:12px;letter-spacing:1.8px;text-transform:uppercase;color:#93c5fd;font-weight:700;">NITA AI & GeoAnalytics | WaterWatch DSS</div>
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
<div style="padding:14px 24px;background:#f1f5f9;color:#64748b;font-size:12px;border-top:1px solid #e5edf7;">Automated DSS email from WaterWatch observations and Nita AI GeoAnalytics. Validate with official field communication before public warning release.</div>
</div></div></body></html>"""


def consolidated_plain_message(dam_alerts: pd.DataFrame, gd_alerts: pd.DataFrame) -> str:
    generated_at = pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y, %I:%M %p IST")
    lines = [
        "Nita AI WaterWatch Consolidated Operational Alert Bulletin",
        f"Generated: {generated_at}",
        "",
        f"Active dam alerts: {len(dam_alerts)}",
        f"Active GD-site alerts: {len(gd_alerts)}",
        "",
        "DAM ALERTS",
    ]
    if dam_alerts.empty:
        lines.append("No active dam alert in the latest report observations.")
    else:
        for _, row in dam_alerts.iterrows():
            lines.append(
                " | ".join(
                    [
                        str(row.get("configured_alert") or "Alert").upper(),
                        str(row.get("reservoir_name") or row.get("dam_name") or "Reservoir"),
                        f"District: {row.get('district') or row.get('map_district') or '-'}",
                        f"WL: {fmt_number(row.get('water_level_m'), ' m')}",
                        f"FRL gap: {fmt_number(row.get('frl_gap_m'), ' m')}",
                        f"Filling: {fmt_number(row.get('display_filling'), '%')}",
                    ]
                )
            )
    lines.extend(["", "GD-SITE ALERTS"])
    if gd_alerts.empty:
        lines.append("No verified GD-site return-period or flood-status alert in the current forecast window.")
    else:
        for _, row in gd_alerts.iterrows():
            lines.append(
                " | ".join(
                    [
                        str(row.get("alert_level") or "Alert").upper(),
                        str(row.get("station_name") or row.get("station_code") or "GD Site"),
                        f"District: {row.get('district') or '-'}",
                        f"River: {row.get('river') or '-'}",
                        f"Current flow: {fmt_number(row.get('meanflow_cms'), ' cumecs')}",
                        f"Peak flow: {fmt_number(row.get('peak_flow_cms'), ' cumecs')}",
                        f"Return period: {fmt_number(row.get('return_period'), ' years')}",
                        f"Flood status: {row.get('flood_status') or '-'}",
                    ]
                )
            )
    lines.extend(
        [
            "",
            "Operational action: Verify levels and discharge with field/control-room communication, review inflow and gate operation, and activate downstream warning protocols where required.",
            "This is a DSS screening bulletin; official field observations remain authoritative for public warning decisions.",
        ]
    )
    return "\n".join(lines)


def consolidated_html_message(dam_alerts: pd.DataFrame, gd_alerts: pd.DataFrame) -> str:
    colors = {"Critical": "#dc2626", "Warning": "#f59e0b", "Watch": "#eab308"}
    combined_levels = list(dam_alerts.get("configured_alert", pd.Series(dtype=str)).astype(str)) + list(
        gd_alerts.get("alert_level", pd.Series(dtype=str)).astype(str)
    )
    counts = {level: combined_levels.count(level) for level in ["Critical", "Warning", "Watch"]}
    generated_at = pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y, %I:%M %p IST")

    def badge(level: object) -> str:
        label = str(level or "Alert")
        color = colors.get(label, "#2563eb")
        return f"<span style='display:inline-block;background:{color};color:#fff;border-radius:999px;padding:4px 9px;font-size:11px;font-weight:800'>{escape(label.upper())}</span>"

    dam_rows = ""
    for _, row in dam_alerts.iterrows():
        observed = pd.to_datetime(row.get("observed_at"), errors="coerce")
        observed_label = observed.strftime("%d %b, %I:%M %p") if pd.notna(observed) else "-"
        dam_rows += (
            "<tr>"
            f"<td>{badge(row.get('configured_alert'))}</td>"
            f"<td><b>{escape(str(row.get('reservoir_name') or row.get('dam_name') or '-'))}</b><br><span>{escape(str(row.get('district') or row.get('map_district') or '-'))}</span></td>"
            f"<td>{escape(fmt_number(row.get('water_level_m'), ' m'))}</td>"
            f"<td>{escape(fmt_number(row.get('frl_gap_m'), ' m'))}</td>"
            f"<td>{escape(fmt_number(row.get('display_filling'), '%'))}</td>"
            f"<td>{escape(observed_label)}</td>"
            "</tr>"
        )
    if not dam_rows:
        dam_rows = "<tr><td colspan='6'>No active dam alert in the latest report observations.</td></tr>"

    gd_rows = ""
    for _, row in gd_alerts.iterrows():
        peak_time = pd.to_datetime(row.get("peak_time"), errors="coerce", utc=True)
        peak_label = peak_time.tz_convert("Asia/Kolkata").strftime("%d %b, %I:%M %p") if pd.notna(peak_time) else "-"
        forecast_basis = str(row.get("flood_status") or "").strip()
        if not forecast_basis:
            forecast_basis = f"RP {fmt_number(row.get('return_period'))}"
        gd_rows += (
            "<tr>"
            f"<td>{badge(row.get('alert_level'))}</td>"
            f"<td><b>{escape(str(row.get('station_name') or row.get('station_code') or '-'))}</b><br><span>{escape(str(row.get('district') or '-'))} | {escape(str(row.get('river') or '-'))}</span></td>"
            f"<td>{escape(fmt_number(row.get('meanflow_cms'), ' cumecs'))}</td>"
            f"<td>{escape(fmt_number(row.get('peak_flow_cms'), ' cumecs'))}</td>"
            f"<td>{escape(forecast_basis)}</td>"
            f"<td>{escape(peak_label)}</td>"
            "</tr>"
        )
    if not gd_rows:
        gd_rows = "<tr><td colspan='6'>No verified GD-site return-period or flood-status alert in the current forecast window.</td></tr>"

    summary_cards = "".join(
        f"<td style='width:33.33%;padding:8px'><div style='border:1px solid #dbe6f4;border-top:4px solid {colors[level]};border-radius:8px;padding:12px;text-align:center'><div style='font-size:24px;font-weight:800'>{counts[level]}</div><div style='font-size:11px;color:#64748b;text-transform:uppercase'>{level}</div></div></td>"
        for level in ["Critical", "Warning", "Watch"]
    )
    table_style = "width:100%;border-collapse:collapse;font-size:12px"
    return f"""<!doctype html>
<html><body style="margin:0;background:#eef3f8;font-family:Arial,Helvetica,sans-serif;color:#0f172a">
<div style="max-width:920px;margin:0 auto;padding:20px">
<div style="background:#073b63;color:#fff;border-radius:12px 12px 0 0;padding:20px 24px">
<div style="font-size:11px;letter-spacing:1.5px;color:#8ed8ff;font-weight:800">NITA AI & GEOANALYTICS | WATERWATCH LIVE</div>
<h1 style="margin:7px 0 3px;font-size:24px">Consolidated Dam and GD-Site Alert Bulletin</h1>
<div style="color:#d7e9f7;font-size:12px">Generated {escape(generated_at)} | Private individual delivery</div></div>
<div style="background:#fff;border:1px solid #dbe6f4;border-top:0;border-radius:0 0 12px 12px;padding:20px 24px">
<table role="presentation" style="width:100%;border-collapse:collapse;margin-bottom:16px"><tr>{summary_cards}</tr></table>
<h2 style="font-size:16px;margin:16px 0 8px;color:#073b63">Reservoir and Dam Alerts</h2>
<table class="alert-table" style="{table_style}"><thead><tr><th>Level</th><th>Reservoir / District</th><th>Water Level</th><th>FRL Gap</th><th>Filling</th><th>Observed</th></tr></thead><tbody>{dam_rows}</tbody></table>
<h2 style="font-size:16px;margin:22px 0 8px;color:#073b63">GD-Site River Alerts</h2>
<table class="alert-table" style="{table_style}"><thead><tr><th>Level</th><th>GD Site / River</th><th>Current Flow</th><th>Forecast Peak</th><th>Alert Basis</th><th>Peak Time</th></tr></thead><tbody>{gd_rows}</tbody></table>
<div style="margin-top:18px;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:14px;color:#7c2d12;font-size:13px;line-height:1.5"><b>Operational action:</b> Verify levels and discharge with field/control-room communication, review inflow and gate operation, and activate downstream warning protocols where required.</div>
<div style="margin-top:14px;color:#64748b;font-size:11px;line-height:1.5">This is an automated DSS screening bulletin. Official field observations and control-room communication remain authoritative for public warning decisions.</div>
</div></div>
<style>.alert-table th{{background:#eaf3fb;color:#334155;padding:9px;text-align:left;border:1px solid #dbe6f4}}.alert-table td{{padding:9px;border:1px solid #dbe6f4;vertical-align:top}}.alert-table span{{color:#64748b;font-size:11px}}@media(max-width:680px){{.alert-table{{font-size:10px}}.alert-table th,.alert-table td{{padding:5px}}}}</style>
</body></html>"""


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
    if not recipients:
        return False, "No recipients configured."
    provider = email_api_provider(config)
    if provider:
        key_name = f"{provider}_api_key"
        missing = [key for key in [key_name, "sender"] if not str(config.get(key) or "").strip()]
        if missing:
            return False, f"Missing {provider} email API settings: {', '.join(missing)}"
        failures = []
        for recipient in recipients:
            if provider == "resend":
                ok, detail = post_json(
                    "https://api.resend.com/emails",
                    {"from": config["sender"], "to": [recipient], "subject": subject, "text": text, "html": html},
                    {"Authorization": f"Bearer {config['resend_api_key']}", "Content-Type": "application/json"},
                )
            elif provider == "brevo":
                ok, detail = post_json(
                    "https://api.brevo.com/v3/smtp/email",
                    {
                        "sender": {"email": config["sender"], "name": "NITA GeoAI Alerts"},
                        "to": [{"email": recipient}],
                        "subject": subject,
                        "textContent": text,
                        "htmlContent": html,
                    },
                    {"api-key": config["brevo_api_key"], "Content-Type": "application/json"},
                )
            else:
                ok, detail = post_json(
                    "https://api.sendgrid.com/v3/mail/send",
                    {
                        "personalizations": [{"to": [{"email": recipient}]}],
                        "from": {"email": config["sender"]},
                        "subject": subject,
                        "content": [
                            {"type": "text/plain", "value": text},
                            {"type": "text/html", "value": html},
                        ],
                    },
                    {"Authorization": f"Bearer {config['sendgrid_api_key']}", "Content-Type": "application/json"},
                )
            if not ok:
                failures.append(f"{recipient}: {detail[:180]}")
        if failures:
            return False, f"{provider.title()} email API failed for {len(failures)} recipient(s): {' | '.join(failures[:2])}"
        return True, f"Sent privately to {len(recipients)} recipient(s) using {provider.title()} API."

    missing = [key for key in ["host", "username", "password", "sender"] if not str(config.get(key) or "").strip()]
    if missing:
        return False, f"Missing SMTP settings: {', '.join(missing)}"
    def send_with_config(active_config: dict) -> None:
        smtp_class = smtplib.SMTP_SSL if active_config["use_ssl"] else smtplib.SMTP
        with smtp_class(active_config["host"], active_config["port"], timeout=35) as smtp:
            if active_config["use_tls"] and not active_config["use_ssl"]:
                smtp.starttls()
            smtp.login(active_config["username"], active_config["password"])
            for recipient in recipients:
                message = EmailMessage()
                message["Subject"] = subject
                message["From"] = active_config["sender"]
                message["To"] = recipient
                message.set_content(text)
                message.add_alternative(html, subtype="html")
                smtp.send_message(message)

    try:
        send_with_config(config)
        return True, f"Sent privately to {len(recipients)} recipient(s)."
    except Exception as exc:
        if str(config.get("host", "")).endswith("secureserver.net") and not config.get("use_ssl"):
            fallback = {**config, "port": 465, "use_tls": False, "use_ssl": True}
            try:
                send_with_config(fallback)
                return True, f"Sent privately to {len(recipients)} recipient(s) using SSL fallback."
            except Exception as fallback_exc:
                return False, f"Email failed: {exc}; SSL fallback also failed: {fallback_exc}"
        return False, f"Email failed: {exc}"


def dispatch_once(force: bool = False, dry_run: bool = False) -> None:
    recipients = configured_recipients()
    dam_alerts = load_alert_rows()
    gd_alerts = load_gd_alert_rows()
    if dam_alerts.empty and gd_alerts.empty:
        print("No active dam or GD-site alerts.")
        return
    if not dam_alerts.empty:
        dam_alerts = dam_alerts.assign(
            alert_rank=dam_alerts["configured_alert"].map({"Critical": 4, "Warning": 3, "Watch": 2}).fillna(1)
        ).sort_values(["alert_rank", "frl_gap_m", "display_filling"], ascending=[False, True, False])
    signature_rows = []
    for _, row in dam_alerts.iterrows():
        signature_rows.append(
            f"DAM|{row.get('reservoir_name')}|{row.get('configured_alert')}|{row.get('observed_at')}|{fmt_number(row.get('water_level_m'))}"
        )
    for _, row in gd_alerts.iterrows():
        signature_rows.append(
            f"GD|{row.get('station_code')}|{row.get('alert_level')}|{row.get('forecast_time')}|{fmt_number(row.get('meanflow_cms'))}"
        )
    signature = hashlib.sha256("\n".join(sorted(signature_rows)).encode("utf-8")).hexdigest()[:20]
    hour_key = pd.Timestamp.now(tz="Asia/Kolkata").strftime("%Y%m%d%H")
    dispatch_key = f"consolidated|{hour_key}|{signature}"
    if not force and already_sent(dispatch_key):
        print("Consolidated alert bulletin already sent for this hourly data state.")
        return

    levels = list(dam_alerts.get("configured_alert", pd.Series(dtype=str)).astype(str)) + list(
        gd_alerts.get("alert_level", pd.Series(dtype=str)).astype(str)
    )
    critical_count = levels.count("Critical")
    warning_count = levels.count("Warning")
    watch_count = levels.count("Watch")
    subject = (
        f"Nita AI WaterWatch Consolidated Alert: {critical_count} Critical | "
        f"{warning_count} Warning | {watch_count} Watch"
    )
    text = consolidated_plain_message(dam_alerts, gd_alerts)
    html = consolidated_html_message(dam_alerts, gd_alerts)
    summary_row = pd.Series(
        {
            "reservoir_name": f"Consolidated: {len(dam_alerts)} dam(s), {len(gd_alerts)} GD site(s)",
            "configured_alert": "Critical" if critical_count else "Warning" if warning_count else "Watch",
            "observed_at": pd.Timestamp.now(tz="Asia/Kolkata").isoformat(),
        }
    )
    if dry_run:
        status = f"DRY RUN: one consolidated bulletin would be sent privately to {len(recipients)} recipient(s)."
        ok = True
    else:
        ok, status = send_email_private(subject, text, html, recipients)
        record_dispatch(dispatch_key, summary_row, len(recipients), status)
    print(status)
    print(
        f"Alert dispatch complete. Bulletins {'prepared' if dry_run else 'sent'}: {1 if ok else 0}; "
        f"active dam alerts: {len(dam_alerts)}; active GD-site alerts: {len(gd_alerts)}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Send an automated consolidated WaterWatch dam and GD-site alert email.")
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
