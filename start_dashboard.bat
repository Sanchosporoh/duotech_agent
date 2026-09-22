@echo off
setlocal
title Production monitoring dashboard
cd /d "%~dp0"
set "AGENT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%AGENT_PYTHON%" set "AGENT_PYTHON=C:\work-scripts\venv\Scripts\python.exe"
if not exist "%AGENT_PYTHON%" set "AGENT_PYTHON=python"
if not exist "%~dp0dashboard.py" (
    echo dashboard.py not found in %~dp0
    pause
    exit /b 1
)
echo Dashboard: http://127.0.0.1:8503/
echo Keep this window open. To stop the dashboard, press Ctrl+C.
powershell.exe -NoProfile -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8503/_stcore/health' -UseBasicParsing -TimeoutSec 3; if ($response.Content.Trim() -eq 'ok') { exit 0 }; exit 1 } catch { exit 1 }"
if not errorlevel 1 (
    echo Dashboard is already running.
    start "" "http://127.0.0.1:8503/"
    exit /b 0
)
"%AGENT_PYTHON%" -m streamlit run "%~dp0dashboard.py" --server.port 8503 --server.address 127.0.0.1 --server.headless false --browser.gatherUsageStats false
echo.
echo Dashboard stopped. Any error message is shown above.
pause
