@echo off
setlocal
title Downline - Choose Brave Beta
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -ChooseBrowser
if errorlevel 1 (
  echo.
  echo Downline could not start. The error above explains what happened.
  pause
)
endlocal
