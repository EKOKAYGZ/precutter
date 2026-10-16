@echo off
rem Double-click once: puts a "PreCutter" shortcut on your Desktop.
setlocal EnableExtensions
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\create-shortcut.ps1"
if errorlevel 1 (
  echo.
  echo  [PreCutter] Kisayol olusturulamadi.
) 
echo.
pause
exit /b 0
