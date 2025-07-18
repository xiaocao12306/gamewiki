@echo off
echo Testing Internationalization and State Synchronization...
echo.

REM Activate virtual environment if exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
) else (
    echo Warning: Virtual environment not found. Using system Python.
)

REM Run the test script
python test_i18n_sync.py

pause