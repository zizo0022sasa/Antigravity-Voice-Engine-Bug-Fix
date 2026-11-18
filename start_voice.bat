@echo off
title Antigravity Smart Voice Engine
cd /d "%~dp0"
echo Starting Antigravity Voice Engine...

set "PY_CMD=python"
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

"%PY_CMD%" main.py
pause

