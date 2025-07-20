#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GameWiki Assistant 兼容性部署脚本
=================================

此脚本专门解决不同Windows版本间的兼容性问题，特别是：
- Visual C++ Redistributables缺失
- PyQt6 DLL依赖问题
- Win10/Win11兼容性
"""

import os
import sys
import shutil
import subprocess
import requests
import zipfile
from pathlib import Path
from urllib.parse import urlparse

def print_status(message):
    """打印状态信息"""
    print(f"🔧 {message}")

def print_error(message):
    """打印错误信息"""
    print(f"❌ 错误: {message}")

def print_success(message):
    """打印成功信息"""
    print(f"✅ {message}")

def print_warning(message):
    """打印警告信息"""
    print(f"⚠️  警告: {message}")

def download_file(url, local_path):
    """下载文件"""
    try:
        print_status(f"正在下载: {os.path.basename(local_path)}")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print_success(f"下载完成: {local_path}")
        return True
    except Exception as e:
        print_error(f"下载失败: {e}")
        return False

def create_vcredist_bundle():
    """创建包含VC++ Redistributables的部署包"""
    print_status("创建VC++ Redistributables兼容性包...")
    
    # 创建部署目录
    deploy_dir = Path("GameWikiAssistant_Deploy")
    if deploy_dir.exists():
        shutil.rmtree(deploy_dir)
    deploy_dir.mkdir()
    
    # VC++ Redistributables下载信息
    vcredist_info = {
        "x64": {
            "url": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
            "filename": "vc_redist.x64.exe"
        }
    }
    
    # 下载VC++ Redistributables
    vcredist_dir = deploy_dir / "vcredist"
    vcredist_dir.mkdir()
    
    for arch, info in vcredist_info.items():
        local_path = vcredist_dir / info["filename"]
        if download_file(info["url"], local_path):
            print_success(f"VC++ Redistributable ({arch}) 下载成功")
        else:
            print_warning(f"VC++ Redistributable ({arch}) 下载失败，可能需要手动安装")
    
    return deploy_dir, vcredist_dir

def copy_application_files(deploy_dir):
    """复制应用程序文件"""
    print_status("复制应用程序文件...")
    
    # 检查dist目录是否存在
    dist_dir = Path("dist")
    if not dist_dir.exists():
        print_error("dist目录不存在，请先运行构建脚本")
        return False
    
    # 复制exe文件
    exe_file = dist_dir / "GameWikiAssistant.exe"
    if exe_file.exists():
        shutil.copy2(exe_file, deploy_dir)
        print_success("应用程序文件复制完成")
        return True
    else:
        print_error("找不到GameWikiAssistant.exe文件")
        return False

def create_installation_script(deploy_dir, vcredist_dir):
    """创建自动安装脚本"""
    print_status("创建安装脚本...")
    
    # PowerShell安装脚本
    ps_script_content = '''# GameWiki Assistant 兼容性安装脚本
Write-Host "🚀 GameWiki Assistant 兼容性安装程序" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green

# 检查管理员权限
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "⚠️  警告: 建议以管理员身份运行以确保完整安装" -ForegroundColor Yellow
    Write-Host "按任意键继续..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# 安装VC++ Redistributables
Write-Host "`n📦 正在安装 Visual C++ Redistributables..." -ForegroundColor Cyan

$vcredistPath = Join-Path $PSScriptRoot "vcredist\\vc_redist.x64.exe"
if (Test-Path $vcredistPath) {
    Write-Host "正在安装 VC++ 2015-2022 x64..." -ForegroundColor Yellow
    try {
        Start-Process -FilePath $vcredistPath -ArgumentList "/install", "/quiet", "/norestart" -Wait
        Write-Host "✅ VC++ Redistributables 安装完成" -ForegroundColor Green
    } catch {
        Write-Host "❌ VC++ 安装失败，请手动运行: $vcredistPath" -ForegroundColor Red
    }
} else {
    Write-Host "❌ 找不到 VC++ 安装包" -ForegroundColor Red
}

# 启动应用程序
Write-Host "`n🎯 启动 GameWiki Assistant..." -ForegroundColor Cyan
$exePath = Join-Path $PSScriptRoot "GameWikiAssistant.exe"
if (Test-Path $exePath) {
    Write-Host "✅ 正在启动应用程序..." -ForegroundColor Green
    Start-Process -FilePath $exePath
} else {
    Write-Host "❌ 找不到应用程序文件" -ForegroundColor Red
}

Write-Host "`n✅ 安装完成！" -ForegroundColor Green
Write-Host "如有问题，请查看 README.txt 获取帮助" -ForegroundColor Cyan
'''
    
    # 批处理安装脚本（备用）
    bat_script_content = '''@echo off
chcp 65001 >nul 2>&1
echo 🚀 GameWiki Assistant 兼容性安装程序
echo ===============================================

echo.
echo 📦 正在安装 Visual C++ Redistributables...
if exist "vcredist\\vc_redist.x64.exe" (
    echo 正在安装 VC++ 2015-2022 x64...
    "vcredist\\vc_redist.x64.exe" /install /quiet /norestart
    if %errorlevel% equ 0 (
        echo ✅ VC++ Redistributables 安装完成
    ) else (
        echo ❌ VC++ 安装失败，请手动运行 vcredist\\vc_redist.x64.exe
    )
) else (
    echo ❌ 找不到 VC++ 安装包
)

echo.
echo 🎯 启动 GameWiki Assistant...
if exist "GameWikiAssistant.exe" (
    echo ✅ 正在启动应用程序...
    start "" "GameWikiAssistant.exe"
) else (
    echo ❌ 找不到应用程序文件
)

echo.
echo ✅ 安装完成！
echo 如有问题，请查看 README.txt 获取帮助
pause
'''
    
    # 写入脚本文件
    ps_script_path = deploy_dir / "Install.ps1"
    bat_script_path = deploy_dir / "Install.bat"
    
    with open(ps_script_path, 'w', encoding='utf-8') as f:
        f.write(ps_script_content)
    
    with open(bat_script_path, 'w', encoding='utf-8') as f:
        f.write(bat_script_content)
    
    print_success("安装脚本创建完成")
    return True

def create_readme(deploy_dir):
    """创建详细的README文档"""
    print_status("创建README文档...")
    
    readme_content = '''# GameWiki Assistant - 兼容性部署版

## 🎯 关于此版本

这是专门为解决Windows 10/11兼容性问题而创建的部署版本，包含了所有必要的运行时库。

## 💻 系统要求

- **操作系统**: Windows 10 1809 或更高版本
- **架构**: 64位 (x64)
- **内存**: 至少 4GB RAM
- **存储**: 至少 500MB 可用空间

## 🚀 安装说明

### 方法一：自动安装（推荐）

1. **以管理员身份运行 `Install.ps1`**（推荐）
   - 右键点击 `Install.ps1`
   - 选择 "使用PowerShell运行"
   - 如果提示执行策略，输入 `Y` 确认

2. **或者运行 `Install.bat`**
   - 双击 `Install.bat` 文件
   - 按照屏幕提示操作

### 方法二：手动安装

如果自动安装脚本失败，请按以下步骤手动安装：

1. **安装 Visual C++ Redistributables**
   - 进入 `vcredist` 文件夹
   - 双击运行 `vc_redist.x64.exe`
   - 按照安装向导完成安装

2. **运行应用程序**
   - 双击 `GameWikiAssistant.exe` 启动程序

## 🐛 故障排除

### 常见问题

1. **"找不到指定的程序" 错误**
   - 确保已安装 Visual C++ Redistributables
   - 手动运行 `vcredist\\vc_redist.x64.exe`

2. **应用程序无法启动**
   - 检查是否有杀毒软件阻止
   - 尝试以管理员身份运行
   - 检查 Windows 更新

3. **PyQt6 相关错误**
   - 重新安装 Visual C++ Redistributables
   - 确保系统是64位版本
   - 更新 Windows 到最新版本

### 详细诊断

如果问题持续存在，请尝试以下诊断步骤：

1. **检查依赖库**
   ```cmd
   # 在命令提示符中运行
   dumpbin /dependents GameWikiAssistant.exe
   ```

2. **查看错误日志**
   - 应用程序日志位置: `%APPDATA%\\game_wiki_tooltip\\`
   - Windows 事件查看器: 应用程序日志

3. **系统信息检查**
   ```cmd
   # 检查系统版本
   winver
   
   # 检查已安装的VC++版本
   wmic product where "name like '%Visual C++%'" get name,version
   ```

## 📞 技术支持

如果以上方法都无法解决问题，请：

1. 收集以下信息：
   - Windows 版本 (运行 `winver` 查看)
   - 错误信息截图
   - 应用程序日志文件

2. 在项目页面提交 Issue 或联系技术支持

## 📝 更新日志

### v1.0 兼容性版本
- 添加完整的Visual C++ Redistributables支持
- 增强Windows 10/11兼容性
- 包含自动安装脚本
- 改进错误诊断信息

---

**注意**: 此版本专为解决跨Windows版本兼容性问题而设计。如果在同一台电脑上开发和运行，建议使用标准版本。
'''
    
    readme_path = deploy_dir / "README.txt"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    print_success("README文档创建完成")
    return True

def main():
    """主函数"""
    print("🚀 GameWiki Assistant 兼容性部署工具")
    print("=" * 50)
    print("此工具专门解决Windows 10/11兼容性问题")
    print()
    
    try:
        # 创建VC++部署包
        deploy_dir, vcredist_dir = create_vcredist_bundle()
        
        # 复制应用程序文件
        if not copy_application_files(deploy_dir):
            return 1
        
        # 创建安装脚本
        create_installation_script(deploy_dir, vcredist_dir)
        
        # 创建README
        create_readme(deploy_dir)
        
        print("\n" + "=" * 50)
        print_success("🎉 兼容性部署包创建完成!")
        print(f"\n📦 部署包位置: {deploy_dir.absolute()}")
        print("\n📋 包含内容:")
        print("  - GameWikiAssistant.exe (应用程序)")
        print("  - vcredist/ (Visual C++ Redistributables)")
        print("  - Install.ps1 (PowerShell安装脚本)")
        print("  - Install.bat (批处理安装脚本)")
        print("  - README.txt (详细说明)")
        print("\n💡 使用说明:")
        print("  1. 将整个文件夹复制到目标电脑")
        print("  2. 以管理员身份运行 Install.ps1 或 Install.bat")
        print("  3. 按照屏幕提示完成安装")
        
        return 0
        
    except KeyboardInterrupt:
        print_error("用户中断了部署过程")
        return 1
    except Exception as e:
        print_error(f"部署过程中发生错误: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    input("\n按Enter键退出...")
    sys.exit(exit_code) 