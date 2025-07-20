#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GameWiki Assistant 兼容性检查工具
================================

用于诊断Win10/Win11系统兼容性问题，特别是PyQt6相关的依赖。
"""

import sys
import os
import subprocess
from pathlib import Path
import platform

def print_header(title):
    """打印标题"""
    print(f"\n{'=' * 50}")
    print(f"🔍 {title}")
    print(f"{'=' * 50}")

def print_check(name, result, details=""):
    """打印检查结果"""
    status = "✅" if result else "❌"
    print(f"{status} {name}")
    if details:
        print(f"   {details}")

def check_python_version():
    """检查Python版本"""
    version = sys.version_info
    is_compatible = version >= (3, 8)
    details = f"当前版本: {version.major}.{version.minor}.{version.micro}"
    if not is_compatible:
        details += " (需要Python 3.8+)"
    return is_compatible, details

def check_windows_version():
    """检查Windows版本"""
    try:
        version = sys.getwindowsversion()
        is_win10_plus = version.major >= 10
        details = f"Windows {version.major}.{version.minor} Build {version.build}"
        
        if not is_win10_plus:
            details += " (需要Windows 10+)"
        elif version.build < 17763:  # Windows 10 1809
            details += " (建议更新到1809或更高版本)"
            
        return is_win10_plus, details
    except:
        return False, "无法检测Windows版本"

def check_architecture():
    """检查系统架构"""
    arch = platform.machine().lower()
    is_x64 = arch in ['amd64', 'x86_64']
    details = f"系统架构: {arch}"
    if not is_x64:
        details += " (需要64位系统)"
    return is_x64, details

def check_vcredist():
    """检查VC++ Redistributables"""
    system32 = Path(os.environ.get('SYSTEMROOT', 'C:\\Windows')) / 'System32'
    
    required_dlls = {
        'msvcp140.dll': 'Visual C++ 2015-2022 runtime',
        'vcruntime140.dll': 'Visual C++ 2015-2022 runtime',
        'vcruntime140_1.dll': 'Visual C++ 2015-2022 runtime (x64)',
    }
    
    missing = []
    found = []
    
    for dll, desc in required_dlls.items():
        dll_path = system32 / dll
        if dll_path.exists():
            try:
                # 尝试获取文件版本信息
                size = dll_path.stat().st_size
                found.append(f"{dll} ({size} bytes)")
            except:
                found.append(dll)
        else:
            missing.append(f"{dll} ({desc})")
    
    is_complete = len(missing) == 0
    
    if is_complete:
        details = f"已安装: {', '.join(found)}"
    else:
        details = f"缺失: {', '.join(missing)}"
        if found:
            details += f"; 已安装: {', '.join(found)}"
    
    return is_complete, details

def check_pyqt6_dependencies():
    """检查PyQt6相关的系统依赖"""
    system32 = Path(os.environ.get('SYSTEMROOT', 'C:\\Windows')) / 'System32'
    
    # PyQt6常用的系统DLL
    pyqt_dlls = {
        'shcore.dll': 'Shell Core (DPI支持)',
        'dwmapi.dll': 'Desktop Window Manager',
        'uxtheme.dll': 'Visual Styles',
        'comctl32.dll': 'Common Controls',
        'gdi32.dll': 'Graphics Device Interface',
        'user32.dll': 'User Interface',
        'opengl32.dll': 'OpenGL',
    }
    
    missing = []
    found = []
    
    for dll, desc in pyqt_dlls.items():
        dll_path = system32 / dll
        if dll_path.exists():
            found.append(dll)
        else:
            missing.append(f"{dll} ({desc})")
    
    is_complete = len(missing) == 0
    
    if is_complete:
        details = f"系统DLL完整 ({len(found)}/{len(pyqt_dlls)})"
    else:
        details = f"缺失系统DLL: {', '.join(missing)}"
    
    return is_complete, details

def check_installed_vcredist_packages():
    """检查已安装的VC++ Redistributable包"""
    try:
        # 使用wmic查询已安装的VC++包
        cmd = ['wmic', 'product', 'where', "name like '%Visual C++%'", 'get', 'name,version', '/format:csv']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            packages = []
            for line in lines[1:]:  # 跳过标题行
                if line.strip() and ',' in line:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        name = parts[1].strip()
                        version = parts[2].strip()
                        if name and version:
                            packages.append(f"{name} v{version}")
            
            if packages:
                return True, f"已安装: {'; '.join(packages)}"
            else:
                return False, "未找到已安装的VC++ Redistributable包"
        else:
            return False, "无法查询已安装的VC++包"
    except:
        return False, "查询VC++包时出错"

def check_pyinstaller_environment():
    """检查PyInstaller打包环境"""
    checks = []
    
    # 检查是否在PyInstaller环境中
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        checks.append("✅ 运行在PyInstaller打包环境中")
        checks.append(f"   临时目录: {sys._MEIPASS}")
        
        # 检查关键DLL是否存在
        temp_dir = Path(sys._MEIPASS)
        key_dlls = ['msvcp140.dll', 'vcruntime140.dll', 'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll']
        
        found_dlls = []
        missing_dlls = []
        
        for dll in key_dlls:
            if (temp_dir / dll).exists():
                found_dlls.append(dll)
            else:
                missing_dlls.append(dll)
        
        if found_dlls:
            checks.append(f"   打包的DLL: {', '.join(found_dlls)}")
        if missing_dlls:
            checks.append(f"   缺失的DLL: {', '.join(missing_dlls)}")
            
        return len(missing_dlls) == 0, '\n'.join(checks)
    else:
        return True, "运行在开发环境中 (非打包版本)"

def run_comprehensive_check():
    """运行综合兼容性检查"""
    print_header("GameWiki Assistant 兼容性检查")
    print("此工具将检查系统是否满足运行要求")
    
    # 基础系统检查
    print_header("基础系统检查")
    
    checks = [
        ("Python版本", check_python_version),
        ("Windows版本", check_windows_version),
        ("系统架构", check_architecture),
    ]
    
    basic_passed = 0
    for name, check_func in checks:
        try:
            result, details = check_func()
            print_check(name, result, details)
            if result:
                basic_passed += 1
        except Exception as e:
            print_check(name, False, f"检查失败: {e}")
    
    # 运行时依赖检查
    print_header("运行时依赖检查")
    
    runtime_checks = [
        ("Visual C++ Runtime DLL", check_vcredist),
        ("PyQt6系统依赖", check_pyqt6_dependencies),
        ("已安装VC++包", check_installed_vcredist_packages),
    ]
    
    runtime_passed = 0
    for name, check_func in runtime_checks:
        try:
            result, details = check_func()
            print_check(name, result, details)
            if result:
                runtime_passed += 1
        except Exception as e:
            print_check(name, False, f"检查失败: {e}")
    
    # 打包环境检查
    print_header("应用程序环境检查")
    
    try:
        result, details = check_pyinstaller_environment()
        print_check("PyInstaller环境", result, details)
    except Exception as e:
        print_check("PyInstaller环境", False, f"检查失败: {e}")
    
    # 总结
    print_header("检查总结")
    
    total_basic = len(checks)
    total_runtime = len(runtime_checks)
    
    print(f"基础系统检查: {basic_passed}/{total_basic} 通过")
    print(f"运行时依赖检查: {runtime_passed}/{total_runtime} 通过")
    
    if basic_passed == total_basic and runtime_passed == total_runtime:
        print("\n🎉 系统兼容性检查全部通过！")
        print("应用程序应该能够正常运行。")
    else:
        print("\n⚠️  发现兼容性问题，建议解决方案：")
        
        if basic_passed < total_basic:
            print("\n📋 基础系统问题：")
            print("  - 升级到Windows 10 1809或更高版本")
            print("  - 确保使用64位系统")
            print("  - 升级Python到3.8或更高版本")
        
        if runtime_passed < total_runtime:
            print("\n📋 运行时依赖问题：")
            print("  - 下载并安装: https://aka.ms/vs/17/release/vc_redist.x64.exe")
            print("  - 运行 deploy_with_vcredist.py 创建兼容性部署包")
            print("  - 使用改进的PyInstaller配置重新打包")
    
    return basic_passed == total_basic and runtime_passed == total_runtime

def main():
    """主函数"""
    try:
        success = run_comprehensive_check()
        
        print_header("建议操作")
        if success:
            print("✅ 无需额外操作，系统兼容性良好")
        else:
            print("📝 建议按以下顺序解决问题：")
            print("  1. 运行兼容性部署脚本: python deploy_with_vcredist.py")
            print("  2. 或重新打包应用: pyinstaller game_wiki_tooltip.spec --clean")
            print("  3. 或手动安装VC++ Redistributable")
            print("  4. 查看详细指南: deploy_instructions.md")
        
        print(f"\n检查完成 - 退出代码: {0 if success else 1}")
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n用户中断了检查过程")
        return 1
    except Exception as e:
        print(f"\n检查过程中发生错误: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    input("\n按Enter键退出...")
    sys.exit(exit_code) 