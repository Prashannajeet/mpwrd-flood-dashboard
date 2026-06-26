$ErrorActionPreference = "Stop"

$python = "D:\01 Project\Development\flood_dashboard\.venv\Scripts\python.exe"
$script = "D:\01 Project\Development\Flood Reports\hourly_alert_dispatcher.py"

& $python $script --loop
