#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GameWiki Assistant 打包脚本

这个脚本用于将 GameWiki Assistant 打包成独立的 exe 文件。
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def print_status(message):
    """打印状态信息"""
    print(f"🔧 {message}")

def print_error(message):
    """打印错误信息"""
    print(f"❌ 错误: {message}")

def print_success(message):
    """打印成功信息"""
    print(f"✅ {message}")

def run_command(command, cwd=None):
    """执行命令并返回结果"""
    import locale
    
    # 获取系统默认编码
    system_encoding = locale.getpreferredencoding()
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding=system_encoding,
            errors='replace'  # 遇到编码错误时用替换字符处理
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        # 确保错误信息也能正确解码
        error_msg = e.stderr if e.stderr else str(e)
        return False, error_msg
    except UnicodeDecodeError as e:
        print_error(f"编码错误，尝试使用UTF-8: {e}")
        # 如果系统编码失败，尝试UTF-8
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                check=True, 
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e2:
            error_msg = e2.stderr if e2.stderr else str(e2)
            return False, error_msg

def install_dependencies():
    """安装依赖包"""
    print_status("正在安装/更新依赖包...")
    
    success, output = run_command("pip install --upgrade pip")
    if not success:
        print_error(f"更新pip失败: {output}")
        return False
    
    success, output = run_command("pip install -r requirements.txt")
    if not success:
        print_error(f"安装依赖失败: {output}")
        return False
    
    print_success("依赖包安装完成")
    return True

def clean_build():
    """清理构建目录"""
    print_status("清理之前的构建文件...")
    
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"  已删除: {dir_name}")
            except Exception as e:
                print(f"  无法删除 {dir_name}: {e}")
                # 继续，不停止整个流程
    
    # 删除spec生成的缓存文件
    try:
        for file in Path('.').glob('*.spec~'):
            file.unlink()
            print(f"  已删除: {file}")
    except Exception as e:
        print(f"  清理spec缓存文件时出错: {e}")
    
    print_success("构建目录清理完成")
    return True  # 确保返回True

def check_assets():
    """检查必要的资源文件是否存在"""
    print_status("检查资源文件...")
    
    required_files = [
        "src/game_wiki_tooltip/assets/app.ico",
        "src/game_wiki_tooltip/assets/games.json",
        "src/game_wiki_tooltip/assets/settings.json",
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print_error("缺少必要的资源文件:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    print_success("资源文件检查完成")
    return True

def check_webview2_requirements():
    """检查WebView2相关要求"""
    print_status("检查WebView2要求...")
    
    # 检查pythonnet
    try:
        import clr
        print("  ✓ pythonnet已安装")
    except ImportError:
        print_error("pythonnet未安装，请运行: pip install pythonnet")
        return False
    
    # 检查WebView2 SDK文件
    webview2_lib_path = Path("src/game_wiki_tooltip/webview2/lib")
    required_dlls = [
        "Microsoft.Web.WebView2.Core.dll",
        "Microsoft.Web.WebView2.WinForms.dll", 
        "WebView2Loader.dll"
    ]
    
    missing_dlls = []
    for dll in required_dlls:
        if not (webview2_lib_path / dll).exists():
            missing_dlls.append(dll)
    
    if missing_dlls:
        print_error(f"缺少WebView2 SDK文件: {', '.join(missing_dlls)}")
        print("请运行: python src/game_wiki_tooltip/webview2_setup.py")
        return False
    
    print("  ✓ WebView2 SDK文件存在")
    
    # 检查WebView2 Runtime（可选检查，因为可能在目标机器上安装）
    try:
        import winreg
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        version = winreg.QueryValueEx(key, "pv")[0]
        winreg.CloseKey(key)
        print(f"  ✓ WebView2 Runtime已安装: {version}")
    except:
        print("  ⚠️  WebView2 Runtime未检测到，但用户可能需要在目标机器上安装")
    
    print_success("WebView2要求检查完成")
    return True

def update_spec_for_webview2():
    """更新spec文件以支持WebView2"""
    print_status("更新PyInstaller配置以支持WebView2...")
    
    spec_file = "game_wiki_tooltip.spec"
    if not os.path.exists(spec_file):
        print_error(f"找不到spec文件: {spec_file}")
        return False
    
    # 读取当前spec文件
    with open(spec_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否已经包含WebView2配置
    if "pythonnet" in content and "webview2" in content.lower():
        print("  ✓ spec文件已包含WebView2配置")
        return True
    
    # 添加WebView2相关的hiddenimports
    webview2_imports = """
    # WebView2 related imports
    'pythonnet',
    'clr',
    'System',
    'System.Windows.Forms',
    'System.Threading',
    'Microsoft.Web.WebView2.Core',
    'Microsoft.Web.WebView2.WinForms',"""
    
    # 替换PyQt6-WebEngine为WebView2
    updated_content = content.replace(
        "'PyQt6.QtWebEngineWidgets',\n    'PyQt6.QtWebEngineCore',",
        "'pywebview[edgechromium]'," + webview2_imports
    )
    
    # 添加WebView2 DLL文件到datas
    webview2_datas = '''
    # WebView2 SDK files
    ("src/game_wiki_tooltip/webview2/lib", "webview2/lib"),'''
    
    # 在datas部分后添加
    if "# Knowledge data" in updated_content:
        updated_content = updated_content.replace(
            '("data", "data"),',
            '("data", "data"),' + webview2_datas
        )
    
    # 写回文件
    with open(spec_file, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print_success("spec文件已更新以支持WebView2")
    return True

def build_exe():
    """使用PyInstaller构建exe文件"""
    print_status("开始构建exe文件...")
    print("这可能需要几分钟时间，请耐心等待...")
    
    # 使用spec文件构建
    success, output = run_command("pyinstaller game_wiki_tooltip.spec --clean --noconfirm")
    
    if not success:
        print_error(f"构建失败: {output}")
        return False
    
    # 检查生成的exe文件
    exe_path = Path("dist/GameWikiAssistant.exe")
    if exe_path.exists():
        print_success(f"构建成功! exe文件位置: {exe_path.absolute()}")
        print(f"文件大小: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
        return True
    else:
        print_error("构建完成但找不到exe文件")
        return False

def create_portable_package():
    """创建便携版打包"""
    print_status("创建便携版压缩包...")
    
    dist_dir = Path("dist")
    if not dist_dir.exists():
        print_error("dist目录不存在")
        return False
    
    # 创建便携版目录
    portable_dir = Path("GameWikiAssistant_Portable")
    if portable_dir.exists():
        shutil.rmtree(portable_dir)
    
    portable_dir.mkdir()
    
    # 复制exe文件
    exe_file = dist_dir / "GameWikiAssistant.exe"
    if exe_file.exists():
        shutil.copy2(exe_file, portable_dir)
    
    # 复制必要的文档
    readme_content = """# GameWiki Assistant 便携版

## 使用说明

1. **首次使用前必读**: 本应用使用WebView2技术，需要Microsoft Edge WebView2 Runtime
2. 双击 GameWikiAssistant.exe 启动程序
3. 如果程序无法启动或显示白屏，请安装WebView2 Runtime
4. 首次运行时需要配置API密钥（可选）
5. 使用快捷键 Ctrl+X 激活游戏助手功能

## 系统要求

- Windows 10 或更高版本（推荐Windows 11）
- 64位系统
- Microsoft Edge WebView2 Runtime

## WebView2 Runtime 安装

### Windows 11 用户
✅ 您的系统已预装WebView2 Runtime，可直接使用

### Windows 10 用户  
⚠️ 需要安装WebView2 Runtime：

**方法1（推荐）**: 运行自动安装脚本
1. 进入 runtime 文件夹
2. 双击运行 install_webview2.bat
3. 按提示完成安装

**方法2**: 手动下载安装
1. 访问：https://go.microsoft.com/fwlink/p/?LinkId=2124703
2. 下载并安装 WebView2 Runtime
3. 重新启动应用程序

## 优势特性

- 📦 更小的程序体积（仅50MB，比传统方案节省150MB）
- 🎥 完美支持视频播放（YouTube、Bilibili等）
- ⚡ 更好的性能表现
- 🔄 自动更新的WebView引擎

## 注意事项

- 本程序是独立的便携版，无需安装（除WebView2 Runtime外）
- 配置文件会保存在系统的AppData目录中
- 如需完整的AI功能，请配置Gemini和Jina API密钥
- 首次安装WebView2 Runtime约需下载100MB，但仅需安装一次

## 故障排除

### 问题：程序无法启动或显示白屏
**解决**: 安装WebView2 Runtime（见上方安装说明）

### 问题：视频无法播放
**解决**: 确认WebView2 Runtime已正确安装并重启程序

### 问题：程序运行缓慢
**解决**: WebView2使用系统Edge引擎，性能通常比传统方案更好

## 技术支持

如有问题，请访问项目页面获取帮助。
"""
    
    with open(portable_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print_success(f"便携版创建完成: {portable_dir.absolute()}")
    return True

def create_webview2_runtime_installer():
    """创建WebView2 Runtime安装包"""
    print_status("创建WebView2 Runtime安装包...")
    
    portable_dir = Path("GameWikiAssistant_Portable")
    if not portable_dir.exists():
        print_error("便携版目录不存在")
        return False
    
    # 创建runtime目录
    runtime_dir = portable_dir / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    
    # 下载WebView2 Runtime Bootstrapper
    try:
        import urllib.request
        bootstrapper_url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
        bootstrapper_path = runtime_dir / "MicrosoftEdgeWebView2Setup.exe"
        
        print("  正在下载WebView2 Runtime Bootstrapper...")
        urllib.request.urlretrieve(bootstrapper_url, bootstrapper_path)
        print(f"  ✓ 已下载到: {bootstrapper_path}")
        
        # 创建安装脚本
        install_script = runtime_dir / "install_webview2.bat"
        script_content = """@echo off
echo 正在检查WebView2 Runtime...
reg query "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" >nul 2>&1
if %errorlevel% equ 0 (
    echo WebView2 Runtime已安装，无需安装。
    pause
    exit /b 0
)

echo WebView2 Runtime未安装，正在安装...
echo 这可能需要几分钟时间，请稍候...
MicrosoftEdgeWebView2Setup.exe /silent /install
if %errorlevel% equ 0 (
    echo WebView2 Runtime安装完成！
) else (
    echo 安装失败，请手动运行MicrosoftEdgeWebView2Setup.exe
)
pause
"""
        with open(install_script, 'w', encoding='gbk') as f:
            f.write(script_content)
        
        print_success("WebView2 Runtime安装包创建完成")
        return True
        
    except Exception as e:
        print_error(f"创建WebView2 Runtime安装包失败: {e}")
        return False

def main():
    """主函数"""
    # 设置控制台编码，确保中文字符正确显示
    if sys.platform == "win32":
        import locale
        try:
            # 尝试设置控制台编码为UTF-8
            os.system("chcp 65001 >nul 2>&1")
        except:
            pass
    
    print("🚀 GameWiki Assistant 打包工具")
    print("=" * 50)
    
    # 检查Python版本
    if sys.version_info < (3, 8):
        print_error("需要Python 3.8或更高版本")
        return 1
    
    # 检查是否在项目根目录
    if not os.path.exists("src/game_wiki_tooltip/qt_app.py"):
        print_error("请在项目根目录运行此脚本")
        return 1
    
    try:
        # 执行构建步骤
        steps = [
            ("安装依赖", install_dependencies),
            ("清理构建", clean_build),
            ("检查资源", check_assets),
            ("检查WebView2要求", check_webview2_requirements),
            ("更新spec文件", update_spec_for_webview2),
            ("构建exe", build_exe),
            ("创建便携版", create_portable_package),
            ("创建WebView2 Runtime安装包", create_webview2_runtime_installer),
        ]
        
        for step_name, step_func in steps:
            print(f"\n📋 步骤: {step_name}")
            if not step_func():
                print_error(f"步骤 '{step_name}' 失败")
                return 1
        
        print("\n" + "=" * 50)
        print_success("🎉 打包完成!")
        print("\n📦 生成的文件:")
        print("  - dist/GameWikiAssistant.exe (单独的exe文件)")
        print("  - GameWikiAssistant_Portable/ (便携版目录)")
        print("\n💡 提示: 你可以将便携版目录压缩后分发给其他用户")
        
        return 0
        
    except KeyboardInterrupt:
        print_error("用户中断了构建过程")
        return 1
    except Exception as e:
        print_error(f"构建过程中发生未预期的错误: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    input("\n按Enter键退出...")
    sys.exit(exit_code) 