@echo off
setlocal

cd /d "%~dp0"
if not exist "logs" mkdir "logs"

set "PY_CMD="
if exist "%~dp0.venv\Scripts\python.exe" set "PY_CMD="%~dp0.venv\Scripts\python.exe""
if not defined PY_CMD if exist "D:\01 Project\Development\flood_dashboard\.venv\Scripts\python.exe" set "PY_CMD="D:\01 Project\Development\flood_dashboard\.venv\Scripts\python.exe""
if not defined PY_CMD set "PY_CMD=py -3"

set "LOG_FILE=%~dp0logs\gd_site_forecast_refresh.log"

:refresh_loop
echo [%date% %time%] Starting GD site forecast refresh.>> "%LOG_FILE%"

%PY_CMD% "%~dp0refresh_gd_site_online_forecasts_node.py" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] GD online linkage refresh failed.>> "%LOG_FILE%"
) else (
  echo [%date% %time%] GD online linkage refresh completed.>> "%LOG_FILE%"
)

%PY_CMD% "%~dp0refresh_gd_site_forecasts.py" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] GD SQLite database refresh failed.>> "%LOG_FILE%"
) else (
  echo [%date% %time%] GD SQLite database refresh completed.>> "%LOG_FILE%"
)

echo [%date% %time%] GD refresh cycle finished.>> "%LOG_FILE%"

if /I "%~1"=="--once" goto finished

echo Waiting 3 hours before next GD refresh cycle...
timeout /t 10800 /nobreak
goto refresh_loop

:finished
echo One-time GD refresh completed. Log: "%LOG_FILE%"
endlocal
