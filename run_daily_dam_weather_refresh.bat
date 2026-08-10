@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

echo Starting fixed 6-hour dam and town weather cache refresh loop at 00:00, 06:00, 12:00 and 18:00 IST...
"%PYTHON%" weather_cache_refresh.py --loop --forecast-all --include-dams
