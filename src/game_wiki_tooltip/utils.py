import ctypes, shutil, sys, os
from pathlib import Path
from importlib import resources

def package_file(relative_path: str) -> Path:
    """
    返回打包在 game_wiki_tooltip/assets 里的文件的路径。
    支持开发环境和PyInstaller打包环境。
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller打包环境
        base_path = Path(sys._MEIPASS) / "assets"
        return base_path / relative_path
    else:
        # 开发环境，使用importlib.resources
        try:
            return resources.files("src.game_wiki_tooltip.assets").joinpath(relative_path)
        except (ImportError, ModuleNotFoundError):
            # 备用方案：基于当前文件的相对路径
            current_dir = Path(__file__).parent
            assets_dir = current_dir / "assets"
            return assets_dir / relative_path

# ---- constants ----
APPDATA_DIR = Path.home() / "AppData" / "Roaming" / "GameWikiTooltip"

# ---- Win32 helpers ----
user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def get_foreground_title(max_len: int = 512) -> str:
    hwnd = user32.GetForegroundWindow()
    buf  = ctypes.create_unicode_buffer(max_len)
    user32.GetWindowTextW(hwnd, buf, max_len)
    return buf.value

def show_cursor_until_visible() -> None:
    while user32.ShowCursor(True) < 0:  # keep increasing internal count
        pass
