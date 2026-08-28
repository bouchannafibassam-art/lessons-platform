@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
    set "PY=py"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python is not installed.
        pause
        exit /b 1
    )
    set "PY=python"
)

echo Installing/checking required packages...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Could not install the required packages.
    pause
    exit /b 1
)

echo.
echo Starting the platform...
echo Open: http://127.0.0.1:5000
%PY% app.py
pause
