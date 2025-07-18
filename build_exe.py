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
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

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

1. 双击 GameWikiAssistant.exe 启动程序
2. 首次运行时需要配置API密钥（可选）
3. 使用快捷键 Ctrl+X 激活游戏助手功能

## 系统要求

- Windows 10 或更高版本
- 64位系统

## 注意事项

- 本程序是独立的便携版，无需安装
- 配置文件会保存在系统的AppData目录中
- 如需完整的AI功能，请配置Gemini和Jina API密钥

## 技术支持

如有问题，请访问项目页面获取帮助。
"""
    
    with open(portable_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print_success(f"便携版创建完成: {portable_dir.absolute()}")
    return True

def main():
    """主函数"""
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
            ("构建exe", build_exe),
            ("创建便携版", create_portable_package),
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