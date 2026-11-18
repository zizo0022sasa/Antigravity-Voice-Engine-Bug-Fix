@echo off
title Install Antigravity Voice Engine to Startup
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_FILE=%STARTUP_DIR%\AntigravityVoiceEngine.vbs"
set "OLD_CMD_FILE=%STARTUP_DIR%\AntigravityVoiceEngine.cmd"
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"

set "PYTHONW_EXE=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PYTHONW_EXE%" (
    for /f "delims=" %%I in ('where pythonw.exe 2^>nul') do (
        set "PYTHONW_EXE=%%I"
        goto :found_pyw
    )
    set "PYTHONW_EXE=pythonw.exe"
)
:found_pyw

if exist "%OLD_CMD_FILE%" del /f /q "%OLD_CMD_FILE%"

echo [1/2] Installing silent VBS launcher to Windows Startup...
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.CurrentDirectory = "%ENGINE_DIR%"
echo WshShell.Run """%PYTHONW_EXE%"" ""%ENGINE_DIR%\main.py""", 0, False
) > "%VBS_FILE%"

echo [2/2] Launching background daemon now...
wscript.exe "%VBS_FILE%"

echo.
echo ========================================================
echo  SUCCESS: Antigravity Voice Engine is now installed!
echo  It will launch silently whenever Windows boots.
echo ========================================================
timeout /t 3 >nul
