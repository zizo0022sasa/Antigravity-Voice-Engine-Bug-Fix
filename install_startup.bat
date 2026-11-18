@echo off
title Install Antigravity Voice Engine to Startup
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_FILE=%STARTUP_DIR%\AntigravityVoiceEngine.vbs"
set "OLD_CMD_FILE=%STARTUP_DIR%\AntigravityVoiceEngine.cmd"
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"

echo Resolving Python 3.10+ interpreter with required audio libraries...
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command ^
  "$cands = @(); " ^
  "Get-ChildItem \"$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe\" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object { $cands += $_.FullName }; " ^
  "Get-Command python.exe -All -ErrorAction SilentlyContinue | ForEach-Object { $cands += $_.Source }; " ^
  "foreach ($py in ($cands | Select-Object -Unique)) { " ^
  "  $pyw = Join-Path (Split-Path $py) 'pythonw.exe'; " ^
  "  if (Test-Path $pyw) { & $py -c 'import sounddevice, numpy' 2>$null; if ($LASTEXITCODE -eq 0) { Write-Output $pyw; break } } " ^
  "}"`) do set "PYTHONW_EXE=%%P"

if "%PYTHONW_EXE%"=="" set "PYTHONW_EXE=pythonw.exe"

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
echo  Runner: %PYTHONW_EXE%
echo ========================================================
timeout /t 3 >nul
