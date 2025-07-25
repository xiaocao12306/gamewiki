@echo off
echo ========================================
echo GameWiki Assistant OneDir Build Script
echo ========================================
echo.
echo This script will build GameWiki Assistant in OneDir mode for faster startup.
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher and add it to PATH
    pause
    exit /b 1
)

REM Ask user if they want to create installer
set /p create_installer="Do you want to create an Inno Setup installer script? (y/n): "

echo.
echo Starting build process...
echo.

REM Run build script with appropriate options
if /i "%create_installer%"=="y" (
    echo Building with installer script generation...
    python build_exe.py --mode onedir --create-installer
) else (
    echo Building without installer script...
    python build_exe.py --mode onedir
)

REM Check if build was successful
if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build completed successfully!
echo ========================================
echo.
echo Output files:
echo - dist\GameWikiAssistant\         (Application directory)
echo - GameWikiAssistant_Portable_onedir\  (Portable package)

if /i "%create_installer%"=="y" (
    echo - GameWikiAssistant_onedir.iss    (Inno Setup script)
    echo.
    echo Next steps to create installer:
    echo 1. Install Inno Setup from https://jrsoftware.org/isdl.php
    echo 2. Open GameWikiAssistant_onedir.iss in Inno Setup
    echo 3. Press F9 to compile the installer
)

echo.
pause