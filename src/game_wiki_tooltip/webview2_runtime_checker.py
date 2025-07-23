"""
WebView2 Runtime检测和安装提示模块
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Tuple, Optional

def check_webview2_runtime() -> Tuple[bool, Optional[str]]:
    """
    检查WebView2 Runtime是否已安装
    
    Returns:
        Tuple[bool, Optional[str]]: (是否已安装, 版本号或None)
    """
    try:
        import winreg
        
        # 检查64位系统的注册表项
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            version = winreg.QueryValueEx(key, "pv")[0]
            winreg.CloseKey(key)
            return True, version
        except:
            pass
        
        # 检查32位系统的注册表项
        key_path = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            version = winreg.QueryValueEx(key, "pv")[0]
            winreg.CloseKey(key)
            return True, version
        except:
            pass
        
        # 检查Edge浏览器是否安装（Edge 83+包含WebView2）
        edge_path = r"SOFTWARE\WOW6432Node\Microsoft\Edge\BLBeacon"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, edge_path)
            version = winreg.QueryValueEx(key, "version")[0]
            winreg.CloseKey(key)
            # Edge 83+包含WebView2支持
            if int(version.split('.')[0]) >= 83:
                return True, f"Edge {version}"
        except:
            pass
            
    except ImportError:
        pass
    
    return False, None

def get_windows_version() -> str:
    """获取Windows版本"""
    try:
        import platform
        version = platform.version()
        # Windows 11的内部版本号是22000+
        if version and int(version.split('.')[2]) >= 22000:
            return "Windows 11"
        else:
            return "Windows 10"
    except:
        return "Windows"

def show_webview2_installation_dialog():
    """显示WebView2安装对话框"""
    try:
        from PyQt6.QtWidgets import QMessageBox, QPushButton
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QIcon, QPixmap
        
        windows_version = get_windows_version()
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("需要WebView2 Runtime")
        
        if windows_version == "Windows 11":
            msg.setText("""
检测到您使用的是Windows 11系统。

通常Windows 11已预装WebView2 Runtime，但当前检测未找到。
请尝试以下解决方案：

1. 更新Windows系统到最新版本
2. 手动下载安装WebView2 Runtime
3. 检查是否有Edge浏览器更新

点击"下载安装"获取最新的WebView2 Runtime。
            """)
        else:
            msg.setText("""
检测到您使用的是Windows 10系统。

应用需要Microsoft Edge WebView2 Runtime才能正常运行。
这是一个轻量级组件，大小约100MB，只需安装一次。

安装完成后，您将享受：
• 更好的网页渲染性能
• 完整的视频播放支持

点击"下载安装"获取WebView2 Runtime。
            """)
        
        # 添加自定义按钮
        download_btn = msg.addButton("下载安装", QMessageBox.ButtonRole.ActionRole)
        open_folder_btn = msg.addButton("打开安装目录", QMessageBox.ButtonRole.ActionRole)
        later_btn = msg.addButton("稍后安装", QMessageBox.ButtonRole.RejectRole)
        
        # 设置默认按钮
        msg.setDefaultButton(download_btn)
        
        result = msg.exec()
        
        if msg.clickedButton() == download_btn:
            open_webview2_download_page()
        elif msg.clickedButton() == open_folder_btn:
            open_runtime_folder()
        
        return result
        
    except ImportError:
        # 如果PyQt6不可用，使用系统消息框
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, 
            "应用需要Microsoft Edge WebView2 Runtime。\n请访问 https://go.microsoft.com/fwlink/p/?LinkId=2124703 下载安装。",
            "需要WebView2 Runtime",
            0x40  # MB_ICONINFORMATION
        )

def open_webview2_download_page():
    """打开WebView2下载页面"""
    import webbrowser
    webbrowser.open("https://go.microsoft.com/fwlink/p/?LinkId=2124703")

def open_runtime_folder():
    """打开runtime文件夹（如果存在）"""
    try:
        # 查找runtime文件夹
        runtime_paths = [
            Path("runtime"),  # 便携版
            Path("../runtime"),  # 上级目录
            Path("GameWikiAssistant_Portable/runtime"),  # 完整路径
        ]
        
        for path in runtime_paths:
            if path.exists():
                if sys.platform == "win32":
                    os.startfile(path)
                else:
                    subprocess.run(["explorer", str(path)])
                return
        
        # 如果没找到runtime文件夹，尝试下载到当前目录
        current_dir = Path.cwd()
        if sys.platform == "win32":
            os.startfile(current_dir)
        
    except Exception as e:
        print(f"无法打开文件夹: {e}")

def check_and_prompt_webview2() -> bool:
    """
    检查WebView2 Runtime并在需要时提示用户安装
    
    Returns:
        bool: True表示WebView2可用或用户选择继续，False表示用户取消
    """
    installed, version = check_webview2_runtime()
    
    if installed:
        print(f"✅ WebView2 Runtime已安装: {version}")
        return True
    
    print("⚠️ WebView2 Runtime未安装")
    
    # 在GUI环境中显示对话框
    try:
        from PyQt6.QtWidgets import QApplication
        if QApplication.instance() is not None:
            show_webview2_installation_dialog()
            return False  # 需要用户安装后重启应用
    except:
        pass
    
    # 在控制台环境中显示提示
    windows_version = get_windows_version()
    print(f"\n检测到系统版本: {windows_version}")
    print("应用需要Microsoft Edge WebView2 Runtime才能正常运行。")
    print("\n安装方法:")
    print("1. 访问: https://go.microsoft.com/fwlink/p/?LinkId=2124703")
    print("2. 下载并安装WebView2 Runtime")
    print("3. 重新启动应用程序")
    print("\n或者运行 runtime/install_webview2.bat（如果文件存在）")
    
    return False

if __name__ == "__main__":
    # 测试函数
    installed, version = check_webview2_runtime()
    print(f"WebView2 Runtime安装状态: {installed}")
    if installed:
        print(f"版本: {version}")
    else:
        print("未安装")
    
    print(f"Windows版本: {get_windows_version()}") 