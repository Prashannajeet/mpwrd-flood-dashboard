@echo off
setlocal
set APP_DIR=%~dp0
set PYTHON_EXE=D:\01 Project\Development\flood_dashboard\.venv\Scripts\python.exe
set REPORT_SOURCE=D:\01 Project\Development\Flood Reports

"%PYTHON_EXE%" "%APP_DIR%scripts\sync_stable_reports_from_folder.py" --source "%REPORT_SOURCE%"
if errorlevel 1 (
  echo.
  echo Stable report sync failed. Review data\stable_report_sync_manifest.csv.
  exit /b 1
)

echo.
echo Stable report sync completed. Review data\stable_report_sync_manifest.csv before pushing.
endlocal
