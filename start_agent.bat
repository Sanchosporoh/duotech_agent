@echo off
setlocal
title Production monitoring agent
cd /d "%~dp0"
set "AGENT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%AGENT_PYTHON%" set "AGENT_PYTHON=C:\work-scripts\venv\Scripts\python.exe"
if not exist "%AGENT_PYTHON%" set "AGENT_PYTHON=python"
rem Demo: one simulated hour of measurements per minute until 23:00.
rem Real time: replace the arguments with --loop --clock wall --interval 300
echo Agent runs in this window. The dashboard shows its results. Press Ctrl+C to stop.
"%AGENT_PYTHON%" "%~dp0tools\run_agent.py" --loop --interval 60 %*
echo.
echo Agent stopped. Any error message is shown above.
pause
