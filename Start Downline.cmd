@echo off
setlocal
title Downline
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 (
  echo.
  echo Downline could not start. The error above explains what happened.
  echo Please keep the app extracted in a folder you can write to.
  pause
)
endlocal
