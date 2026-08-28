@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Python is not installed or not available as "py".
  pause
  exit /b 1
)
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install requirements.
  pause
  exit /b 1
)
echo.
echo Starting the lessons platform...
echo Open http://127.0.0.1:5000 in your browser.
echo.
py app.py
pause
