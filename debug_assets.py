#!/usr/bin/env python3
"""
调试脚本：检查PyInstaller打包后的资源文件结构
"""
import sys
import os
from pathlib import Path

def debug_assets():
    print("=== PyInstaller 资源文件调试 ===")
    
    # 检查是否在打包环境中运行
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        print(f"✅ 运行在PyInstaller打包环境中")
        print(f"📁 sys._MEIPASS = {sys._MEIPASS}")
        
        # 检查assets目录
        assets_path = Path(sys._MEIPASS) / "assets"
        print(f"📁 assets路径: {assets_path}")
        print(f"📁 assets存在: {assets_path.exists()}")
        
        if assets_path.exists():
            print("📂 assets目录内容:")
            for item in assets_path.iterdir():
                if item.is_file():
                    print(f"   📄 {item.name} ({item.stat().st_size} bytes)")
                elif item.is_dir():
                    print(f"   📁 {item.name}/")
                    # 检查子目录内容
                    for subitem in item.iterdir():
                        print(f"      📄 {subitem.name} ({subitem.stat().st_size} bytes)")
        
        # 检查icons目录
        icons_path = Path(sys._MEIPASS) / "assets" / "icons"
        print(f"\n📁 icons路径: {icons_path}")
        print(f"📁 icons存在: {icons_path.exists()}")
        
        if icons_path.exists():
            print("📂 icons目录内容:")
            for item in icons_path.iterdir():
                print(f"   📄 {item.name} ({item.stat().st_size} bytes)")
        
        # 测试package_file函数
        print(f"\n🔧 测试package_file函数:")
        try:
            # 添加当前目录到路径以导入utils
            sys.path.insert(0, str(Path(sys._MEIPASS)))
            from src.game_wiki_tooltip.utils import package_file
            
            # 测试加载app.ico
            app_ico = package_file("app.ico")
            print(f"   app.ico路径: {app_ico}")
            print(f"   app.ico存在: {app_ico.exists()}")
            
            # 测试加载default.png
            try:
                default_png = package_file("icons/default.png")
                print(f"   default.png路径: {default_png}")
                print(f"   default.png存在: {default_png.exists()}")
            except Exception as e:
                print(f"   default.png加载失败: {e}")
                
        except Exception as e:
            print(f"   package_file函数测试失败: {e}")
            
    else:
        print(f"❌ 运行在开发环境中")
        print(f"📁 当前工作目录: {os.getcwd()}")
        print(f"📁 __file__: {__file__}")
        
        # 检查开发环境的assets
        current_dir = Path(__file__).parent
        assets_path = current_dir / "src" / "game_wiki_tooltip" / "assets"
        print(f"📁 开发环境assets路径: {assets_path}")
        print(f"📁 assets存在: {assets_path.exists()}")

if __name__ == "__main__":
    debug_assets()
    input("按回车键退出...") 