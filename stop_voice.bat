@echo off
title Stop Antigravity Voice Engine
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"

echo Sending graceful shutdown signal to Antigravity Voice Engine...
powershell -NoProfile -Command ^
  "$target = [System.IO.Path]::Combine('%ENGINE_DIR%', 'main.py'); " ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine.IndexOf($target, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 }; " ^
  "if (-not $procs) { Write-Host 'No running Antigravity Voice Engine process found.'; exit 0 }; " ^
  "try { $ev = [System.Threading.EventWaitHandle]::OpenExisting('Local\AntigravityVoiceEngine_Shutdown'); $null = $ev.Set(); $ev.Close() } catch {}; " ^
  "foreach ($p in $procs) { " ^
  "  try { $procObj = Get-Process -Id $p.ProcessId -ErrorAction Stop; $null = $procObj.WaitForExit(10000) } catch {} " ^
  "}; " ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine.IndexOf($target, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo Antigravity Voice Engine stopped.
ping -n 3 127.0.0.1 >nul

