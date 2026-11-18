@echo off
title Stop Antigravity Voice Engine
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"

echo Sending graceful shutdown signal to Antigravity Voice Engine...
powershell -NoProfile -Command ^
  "$signaled = $false; " ^
  "try { $ev = [System.Threading.EventWaitHandle]::OpenExisting('Local\AntigravityVoiceEngine_Shutdown'); $null = $ev.Set(); $ev.Close(); $signaled = $true } catch {}; " ^
  "if ($signaled) { Start-Sleep -Milliseconds 900 }; " ^
  "$target = [System.IO.Path]::Combine('%ENGINE_DIR%', 'main.py'); " ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine.IndexOf($target, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo Antigravity Voice Engine stopped.
timeout /t 2 >nul
