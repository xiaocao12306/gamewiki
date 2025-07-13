import ctypes, shutil, asyncio, tkinter as tk
from pathlib import Path
from importlib import resources
import queue

def package_file(relative_path: str) -> Path:
    """
    返回打包在 game_wiki_tooltip/assets 里的文件的临时拷贝路径。
    （importlib.resources 会在需要时解压到临时文件夹）
    """
    return resources.files("src.game_wiki_tooltip.assets").joinpath(relative_path)

# ---- constants ----
APPDATA_DIR = Path.home() / "AppData" / "Roaming" / "GameWikiTooltip"

# ---- Win32 helpers ----
user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ---- cross-thread call queue for Tk operations ----
_tk_call_queue: "queue.Queue[callable]" = queue.Queue()

def invoke_in_tk_thread(func):
    """在线程安全队列中加入回调，让主线程 Tk 更新循环执行。"""
    _tk_call_queue.put(func)

def get_foreground_title(max_len: int = 512) -> str:
    hwnd = user32.GetForegroundWindow()
    buf  = ctypes.create_unicode_buffer(max_len)
    user32.GetWindowTextW(hwnd, buf, max_len)
    return buf.value

def show_cursor_until_visible() -> None:
    while user32.ShowCursor(True) < 0:  # keep increasing internal count
        pass

# ---- asyncio-friendly Tk loop (for prompt + pywebview) ----
async def run_tk_event_loop() -> None:
    while True:
        try:
            await asyncio.sleep(0.01)
            tk._default_root.update()

            # 处理其他线程提交到 Tk 线程的调用
            while True:
                try:
                    cb = _tk_call_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    cb()
                except Exception as e:  # noqa: WPS424
                    import traceback, sys
                    print("Error in Tk callback from queue", file=sys.stderr)
                    traceback.print_exception(e)

        except tk.TclError:  # app closed
            break
