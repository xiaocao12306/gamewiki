import ctypes, shutil, sys, os
from pathlib import Path
from importlib import resources

def package_file(relative_path: str) -> Path:
    """
    Returns the path to files packaged in game_wiki_tooltip/assets.
    Supports both development environment and PyInstaller packaged environment.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller packaged environment
        base_path = Path(sys._MEIPASS) / "assets"
        return base_path / relative_path
    else:
        # Development environment, use importlib.resources
        try:
            return resources.files("src.game_wiki_tooltip.assets").joinpath(relative_path)
        except (ImportError, ModuleNotFoundError):
            # Fallback: relative path based on current file
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
