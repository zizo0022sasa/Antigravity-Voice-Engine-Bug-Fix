@echo off
title Uninstall Antigravity Voice Engine from Startup
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"

echo Stopping running background instance gracefully...
powershell -NoProfile -Command ^
  "$signaled = $false; " ^
  "try { $ev = [System.Threading.EventWaitHandle]::OpenExisting('Local\AntigravityVoiceEngine_Shutdown'); $null = $ev.Set(); $ev.Close(); $signaled = $true } catch {}; " ^
  "if ($signaled) { Start-Sleep -Milliseconds 900 }; " ^
  "$target = [System.IO.Path]::Combine('%ENGINE_DIR%', 'main.py'); " ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine.IndexOf($target, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo Removing from Windows Startup...
if exist "%STARTUP_DIR%\AntigravityVoiceEngine.cmd" del /f /q "%STARTUP_DIR%\AntigravityVoiceEngine.cmd"
if exist "%STARTUP_DIR%\AntigravityVoiceEngine.vbs" del /f /q "%STARTUP_DIR%\AntigravityVoiceEngine.vbs"

echo.
echo ========================================================
echo  Antigravity Voice Engine removed from Startup.
echo ========================================================
timeout /t 3 >nul
