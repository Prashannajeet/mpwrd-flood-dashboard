@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=C:\Users\Welcome\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%~dp0scripts\run_v02_bias_pipeline.py" --app-dir "%~dp0" --python "%PYTHON_EXE%"
endlocal
