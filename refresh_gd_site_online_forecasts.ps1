$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "D:\01 Project\Development\flood_dashboard\.venv\Scripts\python.exe"
}
if (-not (Test-Path $Python)) {
    throw "Python environment not found. Run refresh_gd_site_online_forecasts_node.py with the app environment."
}

& $Python (Join-Path $AppDir "refresh_gd_site_online_forecasts_node.py")
if ($LASTEXITCODE -ne 0) {
    throw "GD site forecast refresh failed. Existing operational data was preserved."
}

& $Python (Join-Path $AppDir "scripts\check_gd_forecast_quality.py")
if ($LASTEXITCODE -ne 0) {
    throw "GD site forecast quality checks failed. Do not publish the refreshed feed."
}
