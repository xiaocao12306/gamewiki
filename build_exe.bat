@echo off
chcp 65001 >nul
title GameWiki Assistant 打包工具

echo.
echo ======================================
echo     GameWiki Assistant 打包工具
echo ======================================
echo.

:: 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到Python，请先安装Python 3.8或更高版本
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查是否在正确的目录
if not exist "src\game_wiki_tooltip\qt_app.py" (
    echo ❌ 错误: 请在项目根目录运行此脚本
    echo 当前目录: %CD%
    pause
    exit /b 1
)

echo 🔧 开始打包流程...
echo.

:: 运行Python打包脚本
python build_exe.py

:: 检查打包是否成功
if exist "dist\GameWikiAssistant.exe" (
    echo.
    echo ✅ 打包成功！
    echo 📁 exe文件位置: %CD%\dist\GameWikiAssistant.exe
    echo.
    
    :: 询问是否打开文件夹
    set /p choice="是否打开包含exe文件的文件夹？(y/n): "
    if /i "%choice%"=="y" (
        explorer "%CD%\dist"
    )
) else (
    echo.
    echo ❌ 打包失败，请检查错误信息
)

echo.
pause 