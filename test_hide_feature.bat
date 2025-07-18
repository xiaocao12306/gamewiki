@echo off
echo Testing Hide/Show Feature...
echo.

REM Activate virtual environment if exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
) else (
    echo Warning: Virtual environment not found. Using system Python.
)

REM Run the test script
python test_hide_feature_complete.py

pause