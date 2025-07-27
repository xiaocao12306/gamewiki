#!/usr/bin/env python3
"""
BlurWindow安装脚本
"""

import subprocess
import sys
import os

def install_blurwindow():
    """安装BlurWindow"""
    print("正在安装BlurWindow...")
    
    try:
        # 尝试安装BlurWindow
        subprocess.check_call([sys.executable, "-m", "pip", "install", "BlurWindow"])
        print("✅ BlurWindow安装成功！")
        return True
    except subprocess.CalledProcessError:
        print("❌ BlurWindow安装失败")
        print("请尝试手动安装：")
        print("pip install BlurWindow")
        return False

def check_blurwindow():
    """检查BlurWindow是否可用"""
    try:
        from BlurWindow.blurWindow import GlobalBlur
        print("✅ BlurWindow已可用")
        return True
    except ImportError:
        print("❌ BlurWindow未安装或不可用")
        return False

def main():
    """主函数"""
    print("BlurWindow安装检查工具")
    print("=" * 30)
    
    if check_blurwindow():
        print("BlurWindow已准备就绪！")
    else:
        print("需要安装BlurWindow...")
        install = input("是否现在安装？(y/n): ").lower().strip()
        if install == 'y':
            if install_blurwindow():
                if check_blurwindow():
                    print("🎉 安装完成！现在可以运行半透明窗口了。")
                else:
                    print("⚠️ 安装后仍然无法导入，请检查Python环境。")
            else:
                print("💡 您可以稍后手动安装：pip install BlurWindow")
        else:
            print("💡 您可以稍后手动安装：pip install BlurWindow")

if __name__ == "__main__":
    main() 