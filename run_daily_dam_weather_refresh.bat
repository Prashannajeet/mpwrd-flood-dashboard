@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

echo Starting daily 12:30 AM IST dam weather forecast cache refresh...
"%PYTHON%" weather_cache_refresh.py --daily-at 00:30 --forecast-all --include-dams
