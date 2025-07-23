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
        Tuple[bool, Optional[str]]: (is_installed, version_or_none)
    """
    try:
        import winreg
        
        # Check 64-bit system registry key
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            version = winreg.QueryValueEx(key, "pv")[0]
            winreg.CloseKey(key)
            return True, version
        except:
            pass
        
        # Check 32-bit system registry key
        key_path = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            version = winreg.QueryValueEx(key, "pv")[0]
            winreg.CloseKey(key)
            return True, version
        except:
            pass
        
        # Check if Edge browser is installed (Edge 83+ includes WebView2)
        edge_path = r"SOFTWARE\WOW6432Node\Microsoft\Edge\BLBeacon"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, edge_path)
            version = winreg.QueryValueEx(key, "version")[0]
            winreg.CloseKey(key)
            # Edge 83+ includes WebView2 support
            if int(version.split('.')[0]) >= 83:
                return True, f"Edge {version}"
        except:
            pass
            
    except ImportError:
        pass
    
    return False, None

def get_windows_version() -> str:
    """Get Windows version"""
    try:
        import platform
        version = platform.version()
        # Windows 11 internal build number is 22000+
        if version and int(version.split('.')[2]) >= 22000:
            return "Windows 11"
        else:
            return "Windows 10"
    except:
        return "Windows"

def show_webview2_installation_dialog():
    """Show WebView2 installation dialog"""
    try:
        from PyQt6.QtWidgets import QMessageBox, QPushButton
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QIcon, QPixmap
        
        windows_version = get_windows_version()
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("WebView2 Runtime Required")
        
        if windows_version == "Windows 11":
            msg.setText("""
Detected that you are using Windows 11.

Usually Windows 11 comes with WebView2 Runtime pre-installed, but it was not found in the current detection.
Please try the following solutions:

1. Update Windows to the latest version
2. Manually download and install WebView2 Runtime
3. Check for Edge browser updates

Click "Download & Install" to get the latest WebView2 Runtime.
            """)
        else:
            msg.setText("""
Detected that you are using Windows 10.

The application requires Microsoft Edge WebView2 Runtime to run properly.
This is a lightweight component, about 100MB, and only needs to be installed once.

After installation, you will enjoy:
• Better web rendering performance
• Complete video playback support

Click "Download & Install" to get WebView2 Runtime.
            """)
        
        # Add custom buttons
        download_btn = msg.addButton("Download & Install", QMessageBox.ButtonRole.ActionRole)
        open_folder_btn = msg.addButton("Open Install Directory", QMessageBox.ButtonRole.ActionRole)
        later_btn = msg.addButton("Install Later", QMessageBox.ButtonRole.RejectRole)
        
        # Set default button
        msg.setDefaultButton(download_btn)
        
        result = msg.exec()
        
        if msg.clickedButton() == download_btn:
            open_webview2_download_page()
        elif msg.clickedButton() == open_folder_btn:
            open_runtime_folder()
        
        return result
        
    except ImportError:
        # If PyQt6 is not available, use system message box
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, 
            "The application requires Microsoft Edge WebView2 Runtime.\nPlease visit https://go.microsoft.com/fwlink/p/?LinkId=2124703 to download and install.",
            "WebView2 Runtime Required",
            0x40  # MB_ICONINFORMATION
        )

def open_webview2_download_page():
    """Open WebView2 download page"""
    import webbrowser
    webbrowser.open("https://go.microsoft.com/fwlink/p/?LinkId=2124703")

def open_runtime_folder():
    """Open runtime folder (if exists)"""
    try:
        # Find runtime folder
        runtime_paths = [
            Path("runtime"),  # Portable version
            Path("../runtime"),  # Parent directory
            Path("GameWikiAssistant_Portable/runtime"),  # Full path
        ]
        
        for path in runtime_paths:
            if path.exists():
                if sys.platform == "win32":
                    os.startfile(path)
                else:
                    subprocess.run(["explorer", str(path)])
                return
        
        # If runtime folder not found, try to open current directory
        current_dir = Path.cwd()
        if sys.platform == "win32":
            os.startfile(current_dir)
        
    except Exception as e:
        print(f"Cannot open folder: {e}")

def check_and_prompt_webview2() -> bool:
    """
    Check WebView2 Runtime and prompt user to install if needed
    
    Returns:
        bool: True means WebView2 is available or user chose to continue, False means user cancelled
    """
    installed, version = check_webview2_runtime()
    
    if installed:
        print(f"✅ WebView2 Runtime installed: {version}")
        return True
    
    print("⚠️ WebView2 Runtime not installed")
    
    # Show dialog in GUI environment
    try:
        from PyQt6.QtWidgets import QApplication
        if QApplication.instance() is not None:
            show_webview2_installation_dialog()
            return False  # User needs to install and restart application
    except:
        pass
    
    # Show prompt in console environment
    windows_version = get_windows_version()
    print(f"\nDetected system version: {windows_version}")
    print("The application requires Microsoft Edge WebView2 Runtime to run properly.")
    print("\nInstallation method:")
    print("1. Visit: https://go.microsoft.com/fwlink/p/?LinkId=2124703")
    print("2. Download and install WebView2 Runtime")
    print("3. Restart the application")
    print("\nOr run runtime/install_webview2.bat (if file exists)")
    
    return False

if __name__ == "__main__":
    # Test function
    installed, version = check_webview2_runtime()
    print(f"WebView2 Runtime installation status: {installed}")
    if installed:
        print(f"Version: {version}")
    else:
        print("Not installed")
    
    print(f"Windows version: {get_windows_version()}") 