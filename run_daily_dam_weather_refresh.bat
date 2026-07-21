@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

echo Starting 3-hour dam and town weather cache refresh loop...
"%PYTHON%" weather_cache_refresh.py --loop --forecast-all --include-dams
