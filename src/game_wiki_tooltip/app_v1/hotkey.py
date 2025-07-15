"""
Hotkey management – registers and handles global hotkeys.
"""

import logging
import asyncio
import ctypes
from typing import Callable, Dict, Final
from ctypes import wintypes

import win32con
import win32gui
import win32api

from src.game_wiki_tooltip.config import SettingsManager

MOD_MAP: Final[Dict[str, int]] = {
    "Alt": win32con.MOD_ALT,
    "Ctrl": win32con.MOD_CONTROL,
    "Shift": win32con.MOD_SHIFT,
    "Win": win32con.MOD_WIN,
}

logger = logging.getLogger(__name__)

user32 = ctypes.WinDLL('user32', use_last_error=True)

# 定义Windows API函数
RegisterHotKey = user32.RegisterHotKey
RegisterHotKey.argtypes = [wintypes.HWND, wintypes.INT, wintypes.UINT, wintypes.UINT]
RegisterHotKey.restype = wintypes.BOOL

UnregisterHotKey = user32.UnregisterHotKey
UnregisterHotKey.argtypes = [wintypes.HWND, wintypes.INT]
UnregisterHotKey.restype = wintypes.BOOL

class HotkeyError(Exception):
    """热键相关的错误"""
    pass

class HotkeyManager:
    def __init__(self, settings_mgr: SettingsManager, on_trigger: Callable):
        self.settings_mgr = settings_mgr
        self.on_trigger = on_trigger
        self._registered = False
        self._hotkey_id = 1  # 使用固定的热键ID
        self._loop = asyncio.get_event_loop()
        logger.info("HotkeyManager初始化完成")

    def _get_virtual_key(self, key: str) -> int:
        """将按键名称转换为虚拟键码"""
        # 处理功能键
        if key.startswith('F') and key[1:].isdigit():
            return win32con.VK_F1 + int(key[1:]) - 1
            
        # 处理字母键
        if len(key) == 1 and key.isalpha():
            return ord(key.upper())
            
        # 处理数字键
        if key.isdigit():
            return ord(key)
            
        # 处理特殊键
        special_keys = {
            'Space': win32con.VK_SPACE,
            'Enter': win32con.VK_RETURN,
            'Tab': win32con.VK_TAB,
            'Escape': win32con.VK_ESCAPE,
            'Backspace': win32con.VK_BACK,
            'Delete': win32con.VK_DELETE,
            'Insert': win32con.VK_INSERT,
            'Home': win32con.VK_HOME,
            'End': win32con.VK_END,
            'PageUp': win32con.VK_PRIOR,
            'PageDown': win32con.VK_NEXT,
            'Up': win32con.VK_UP,
            'Down': win32con.VK_DOWN,
            'Left': win32con.VK_LEFT,
            'Right': win32con.VK_RIGHT,
        }
        
        if key in special_keys:
            return special_keys[key]
            
        logger.error(f"未知的键: {key}")
        raise HotkeyError(f"未知的键: {key}")

    def register(self):
        """注册全局热键"""
        if self._registered:
            logger.info("热键已经注册，先注销")
            self.unregister()

        try:
            # 获取热键设置
            settings = self.settings_mgr.get()
            hotkey_settings = settings.get('hotkey', {})
            
            # 计算修饰键
            mod_flags = 0
            modifiers = hotkey_settings.get('modifiers', [])
            if not modifiers:
                raise HotkeyError("请至少选择一个修饰键（Ctrl/Alt/Shift/Win）")
                
            for modifier in modifiers:
                if modifier in MOD_MAP:
                    mod_flags |= MOD_MAP[modifier]

            # 获取虚拟键码
            key = hotkey_settings.get('key', 'X')
            if not key:
                raise HotkeyError("请选择一个主键")
                
            vk = self._get_virtual_key(key)

            logger.info(f"尝试注册热键: modifiers={modifiers}, key={key}, mod_flags={mod_flags}, vk={vk}")

            # 注册热键
            if not RegisterHotKey(None, self._hotkey_id, mod_flags, vk):
                error = ctypes.get_last_error()
                if error == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
                    logger.warning("热键已被注册，将直接使用")
                    self._registered = True
                    return
                else:
                    logger.error(f"注册热键失败，错误码: {error}")
                    raise HotkeyError(f"注册热键失败，错误码: {error}")

            self._registered = True
            logger.info("热键注册成功")

        except HotkeyError:
            raise
        except Exception as e:
            logger.error(f"注册热键时发生错误: {e}")
            raise HotkeyError(f"注册热键时发生未知错误: {str(e)}")

    def unregister(self):
        """注销全局热键"""
        if not self._registered:
            return

        try:
            if not UnregisterHotKey(None, self._hotkey_id):
                error = ctypes.get_last_error()
                logger.error(f"注销热键失败，错误码: {error}")
            self._registered = False
            logger.info("成功注销热键")
        except Exception as e:
            print(f"注销热键失败: {e}")

    def handle_wm_hotkey(self):
        """处理热键消息"""
        logger.info("处理热键消息")
        if self.on_trigger:
            try:
                # 使用 asyncio.run_coroutine_threadsafe 来在事件循环中运行协程
                future = asyncio.run_coroutine_threadsafe(self.on_trigger(), self._loop)
                # 等待协程完成，然后启动webview
                future.add_done_callback(lambda f: self._handle_callback_result(f))
            except Exception as e:
                logger.error(f"热键回调执行失败: {e}", exc_info=True)

    def _handle_callback_result(self, future):
        """处理回调结果"""
        try:
            future.result()  # 检查是否有异常
            # 在主线程中启动webview
            import webview
            import threading
            
            def start_webview():
                try:
                    print("=== 开始启动webview ===")
                    webview.start()
                    print("=== webview启动完成 ===")
                except Exception as e:
                    logger.error(f"启动webview失败: {e}", exc_info=True)
                    print(f"启动webview失败: {e}")
            
            # 在主线程中启动webview
            if threading.current_thread() is threading.main_thread():
                start_webview()
            else:
                # 如果不在主线程，使用Tk的after方法在主线程中执行
                import tkinter as tk
                if tk._default_root:
                    tk._default_root.after(100, start_webview)  # 延迟100ms确保窗口已创建
                    
        except Exception as e:
            logger.error(f"热键回调执行失败: {e}", exc_info=True)
