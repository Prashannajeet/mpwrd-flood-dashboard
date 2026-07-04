@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

echo Starting 3-hour MP satellite rainfall station refresh...
"%PYTHON%" satellite_rainfall_refresh.py --loop --include-dams --include-gd-sites
