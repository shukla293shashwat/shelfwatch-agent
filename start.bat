@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating a Python 3.12 environment...
    py -3.12 -m venv .venv
    if errorlevel 1 goto failed
)

echo Checking project dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.lock
if errorlevel 1 goto failed

echo.
echo Open http://127.0.0.1:8000 after the server starts.
echo Keep this window open. Press Ctrl+C to stop ShelfWatch.
echo.
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo ShelfWatch could not start. Check that Python 3.12 is installed.
echo The message above shows the step that failed.
pause
exit /b 1
