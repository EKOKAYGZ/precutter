@echo off
rem ---------------------------------------------------------------
rem  PreCutter - one-click launcher (Windows)
rem  Just double-click this file. The browser opens by itself.
rem ---------------------------------------------------------------
setlocal EnableExtensions
cd /d "%~dp0"

rem --- 1) Which Python? Prefer a project virtualenv, else PATH ---
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist "env\Scripts\python.exe" set "PY=env\Scripts\python.exe"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  echo.
  echo  [PreCutter] Python was not found.
  echo  Install Python 3.11+ from https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

rem --- 2) Are the requirements installed? ---
%PY% -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  [PreCutter] Missing Python packages. Install them once with:
  echo.
  echo      %PY% -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

rem --- 3) Launch the server in its own window (/k keeps errors visible).
rem       Ctrl+C stops it; the browser tab opens automatically.
start "PreCutter" cmd /k "%PY% -m precutter.app"

exit /b 0
