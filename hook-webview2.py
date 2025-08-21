"""
PyInstaller hook for webview2-Microsoft.Web.WebView2.Core package
This hook ensures the WebView2 Core DLL is properly packaged and accessible
"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
from pathlib import Path
import site

# Collect all data files from webview2 package
datas = collect_data_files('webview2')

# Also ensure the DLL is included as a binary
binaries = []

# Find the WebView2 Core DLL
for site_dir in site.getsitepackages():
    dll_path = Path(site_dir) / "webview2" / "microsoft" / "web" / "webview2" / "core" / "Microsoft.Web.WebView2.Core.dll"
    if dll_path.exists():
        # Add as binary to ensure it's accessible at runtime
        binaries.append((str(dll_path), "webview2/microsoft/web/webview2/core"))
        break

# Also collect the .pyd file (Python extension module)
binaries += collect_dynamic_libs('webview2')

# Hidden imports needed for webview2
hiddenimports = [
    'webview2',
    'webview2.microsoft',
    'webview2.microsoft.web',
    'webview2.microsoft.web.webview2',
    'webview2.microsoft.web.webview2.core',
    'webview2._webview2_microsoft_web_webview2_core',
    'winrt',
    'winrt.runtime',
    'winrt.runtime._internals',
    'winrt.system',
    'winrt.windows.foundation',
]