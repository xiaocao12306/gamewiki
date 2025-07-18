#!/usr/bin/env python3
"""
简单调试脚本：测试package_file函数在打包后的表现
"""
import sys
import os
from pathlib import Path

def main():
    print("=== package_file 函数测试 ===")
    
    # 导入utils模块
    try:
        if getattr(sys, 'frozen', False):
            print("✅ 运行在打包环境中")
        else:
            print("❌ 运行在开发环境中")
            
        from src.game_wiki_tooltip.utils import package_file
        
        # 测试各种文件路径
        test_files = [
            "app.ico",
            "settings.json", 
            "icons/youtube.png",
            "icons/reddit.ico",
            "icons/instagram.png",
            "icons/default.png"  # 这个不存在，测试错误处理
        ]
        
        print(f"\n📁 sys._MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
        
        for file_path in test_files:
            try:
                resolved_path = package_file(file_path)
                exists = resolved_path.exists() if resolved_path else False
                print(f"📄 {file_path}: {resolved_path} (存在: {exists})")
            except Exception as e:
                print(f"❌ {file_path}: 错误 - {e}")
                
    except Exception as e:
        print(f"导入失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
    input("按回车键退出...") 