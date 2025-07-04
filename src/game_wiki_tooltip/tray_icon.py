"""
System tray icon management.
"""

import logging
import threading
import tkinter as tk
from tkinter import messagebox
import pystray
from PIL import Image
import pathlib
import sys
import time
import os

from src.game_wiki_tooltip.utils import package_file, invoke_in_tk_thread
from src.game_wiki_tooltip.hotkey import HotkeyManager


class TrayIcon:
    def __init__(self, settings_mgr, overlay_mgr):
        self.settings_mgr = settings_mgr
        self.overlay_mgr = overlay_mgr
        self._settings_window = None   # 保存设置窗口实例
        self.icon = None  # 注意：初始化时不创建icon
        self.should_exit = False  # 添加退出标志
        self.hk_mgr = HotkeyManager(settings_mgr, on_trigger=overlay_mgr.on_hotkey)

    def _show_settings(self, icon, item=None):
        """弹出热键设置窗口。既用于菜单点击，也用于托盘图标激活（单/双击）。"""

        from src.game_wiki_tooltip.hotkey_setup import configure_hotkey
        from src.game_wiki_tooltip.utils import invoke_in_tk_thread
        def show():
            if self._settings_window is not None:
                try:
                    self._settings_window.lift()
                    self._settings_window.focus_force()
                except Exception:
                    pass
                return

            def on_close(*args):
                self._settings_window = None

            def after_apply():
                try:
                    # 重新注册热键
                    self.hk_mgr.register()
                    # 获取当前热键设置
                    settings = self.settings_mgr.get()
                    hotkey_settings = settings.get('hotkey', {})
                    modifiers = hotkey_settings.get('modifiers', [])
                    key = hotkey_settings.get('key', 'X')
                    hotkey_str = ' + '.join(modifiers + [key])
                    
                    # 预创建搜索窗口以减少用户等待时间
                    logging.info("开始预创建搜索窗口...")
                    try:
                        self.overlay_mgr.precreate_search_window()
                        logging.info("预创建搜索窗口完成")
                    except Exception as e:
                        logging.warning(f"预创建搜索窗口失败: {e}")
                    
                    # 系统托盘气泡通知
                    if self.icon:
                        self.icon.notify(f"热键设置成功：{hotkey_str}\n搜索窗口已预创建，响应更快！", "GameWikiTooltip")
                except Exception as e:
                    logging.error(f"热键注册失败: {e}")
                    messagebox.showerror("错误", f"热键注册失败：{str(e)}\n\n请尝试使用其他热键组合。")
                    # 不要重新打开设置窗口，避免死循环
                    # 让用户手动重新打开设置

            win = configure_hotkey(self.settings_mgr, on_close=on_close, on_apply=after_apply)
            self._settings_window = win

        invoke_in_tk_thread(show)

    def show_trayicon(self):
        image = Image.open(package_file("app.ico"))
        self.icon = pystray.Icon(
            "GameWikiTooltip", image, "Game Wiki Tooltip",
            menu=pystray.Menu(
                pystray.MenuItem("设置", self._show_settings, default=True),
                pystray.MenuItem("退出", self._quit)
            )
        )
        threading.Thread(target=self.icon.run, daemon=True).start()

    def _quit(self, icon, item):
        """退出整个应用程序"""
        try:
            logging.info("用户请求退出程序")
            # 设置退出标志
            self.should_exit = True
            
            # 停止托盘图标
            if self.icon:
                self.icon.stop()
            
            logging.info("退出标志已设置，等待主事件循环退出")
            
        except Exception as e:
            logging.error(f"退出时发生错误: {e}")
            # 如果出错，强制退出
            sys.exit(1)

    def shutdown(self):
        """优雅关闭托盘图标"""
        if self.icon:
            try:
                self.icon.stop()
            except Exception as e:
                logging.error(f"关闭托盘图标时发生错误: {e}")
