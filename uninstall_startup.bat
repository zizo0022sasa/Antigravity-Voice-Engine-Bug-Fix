@echo off
title Uninstall Antigravity Voice Engine from Startup
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo Stopping running background instances...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*antigravity_voice_engine*' -and $_.Name -match 'python' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo Removing from Windows Startup...
if exist "%STARTUP_DIR%\AntigravityVoiceEngine.cmd" del /f /q "%STARTUP_DIR%\AntigravityVoiceEngine.cmd"
if exist "%STARTUP_DIR%\AntigravityVoiceEngine.vbs" del /f /q "%STARTUP_DIR%\AntigravityVoiceEngine.vbs"

echo.
echo ========================================================
echo  Antigravity Voice Engine removed from Startup.
echo ========================================================
timeout /t 3 >nul
