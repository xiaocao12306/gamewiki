"""
Main entry point – initialises tray icon, hot-key hook and Tk event-loop.
"""

import sys
import asyncio
import pathlib
import tkinter as tk
from tkinter import messagebox
import time
import win32gui
import win32con
import logging
import queue

from src.game_wiki_tooltip.config import SettingsManager, GameConfigManager
from src.game_wiki_tooltip.hotkey import HotkeyManager
from src.game_wiki_tooltip.overlay import OverlayManager
from src.game_wiki_tooltip.tray_icon import TrayIcon
from src.game_wiki_tooltip.utils import run_tk_event_loop, APPDATA_DIR, get_foreground_title, _tk_call_queue
from src.game_wiki_tooltip.hotkey_setup import configure_hotkey

# 配置日志
logging.basicConfig(level=logging.DEBUG,
                   format='%(asctime)s - %(levelname)s - %(message)s')

SETTINGS_PATH = APPDATA_DIR / "settings.json"
GAMES_CONFIG_PATH = APPDATA_DIR / "games.json"


def main():
    if tk._default_root is None:
        root = tk.Tk()
        root.withdraw()

    settings_mgr = SettingsManager(SETTINGS_PATH)

    # 先定义托盘和主功能，但不显示托盘
    game_cfg_mgr = GameConfigManager(GAMES_CONFIG_PATH)
    overlay_mgr = OverlayManager(settings_mgr, game_cfg_mgr)
    tray = TrayIcon(settings_mgr, overlay_mgr)
    hk_mgr = HotkeyManager(settings_mgr, on_trigger=overlay_mgr.on_hotkey)

    # 先让用户设置热键；若取消则直接退出
    def after_apply():
        try:
            # 重新注册热键
            hk_mgr.register()
            # 显示托盘图标
            tray.show_trayicon()
            # 获取当前热键设置
            settings = settings_mgr.get()
            hotkey_settings = settings.get('hotkey', {})
            modifiers = hotkey_settings.get('modifiers', [])
            key = hotkey_settings.get('key', 'X')
            hotkey_str = ' + '.join(modifiers + [key])
            
            # 预创建搜索窗口以减少用户等待时间
            logging.info("开始预创建搜索窗口...")
            try:
                overlay_mgr.precreate_search_window()
                logging.info("预创建搜索窗口完成")
            except Exception as e:
                logging.warning(f"预创建搜索窗口失败: {e}")
            
            # 系统托盘气泡通知
            # 等待托盘线程启动
            time.sleep(0.2)
            if tray.icon:
                tray.icon.notify(f"热键设置成功：{hotkey_str}\n托盘图标已显示。\n搜索窗口已预创建，响应更快！", "GameWikiTooltip")
        except Exception as e:
            # 如果热键注册失败，显示错误消息
            logging.error(f"热键注册失败: {e}")
            messagebox.showerror("错误", f"热键注册失败：{str(e)}\n\n请尝试使用其他热键组合。")
            # 不要重新打开设置窗口，避免死循环
            # 让用户手动重新打开设置

    win = configure_hotkey(settings_mgr, on_apply=after_apply)
    # 阻塞直到设置窗口关闭
    logging.info("等待设置窗口关闭...")
    win.wait_window()
    logging.info("设置窗口已关闭")

    try:
        # 运行主事件循环
        logging.info("开始运行主事件循环")
        loop = asyncio.get_event_loop()
        
        while not tray.should_exit:
            # 使用非阻塞方式处理Windows消息
            try:
                msg = win32gui.PeekMessage(None, 0, 0, win32con.PM_REMOVE)
                if msg:
                    if msg[1][1] == win32con.WM_HOTKEY:
                        # 热键被触发
                        logging.info("检测到热键触发")
                        hk_mgr.handle_wm_hotkey()
                    win32gui.TranslateMessage(msg[1])
                    win32gui.DispatchMessage(msg[1])
            except Exception as e:
                logging.error(f"处理Windows消息时发生错误: {e}")
            
            # 更新Tk窗口
            if tk._default_root:
                try:
                    tk._default_root.update()
                    
                    # 处理其他线程提交到 Tk 线程的调用
                    while True:
                        try:
                            cb = _tk_call_queue.get_nowait()
                        except queue.Empty:
                            break
                        try:
                            cb()
                        except Exception as e:
                            logging.error(f"Tk回调执行失败: {e}")
                            
                except tk.TclError:
                    # Tk窗口已关闭，退出循环
                    logging.info("Tk窗口已关闭")
                    break
            
            # 运行异步任务
            try:
                loop.run_until_complete(asyncio.sleep(0.01))
            except Exception:
                # 如果异步循环出错，继续主循环
                pass
            
            # 检查是否需要退出
            if tray.should_exit:
                logging.info("收到退出信号，准备关闭程序")
                break
                
    except Exception as e:
        logging.error(f"事件循环发生错误: {e}", exc_info=True)
    finally:
        # 清理资源
        logging.info("开始清理程序资源")
        try:
            hk_mgr.unregister()
        except Exception as e:
            logging.error(f"注销热键时发生错误: {e}")
        
        try:
            # 清理预创建的搜索窗口
            if overlay_mgr._precreated_search_window:
                try:
                    overlay_mgr._precreated_search_window.destroy()
                    logging.info("已清理预创建的搜索窗口")
                except Exception as e:
                    logging.warning(f"清理预创建搜索窗口失败: {e}")
        except Exception as e:
            logging.error(f"清理预创建窗口时发生错误: {e}")
        
        try:
            tray.shutdown()
        except Exception as e:
            logging.error(f"关闭托盘时发生错误: {e}")
        
        # 确保Tk窗口被销毁
        if tk._default_root:
            try:
                tk._default_root.destroy()
            except Exception:
                pass
        
        logging.info("程序资源清理完成，程序退出")


if __name__ == "__main__":
    if sys.platform != "win32":
        raise RuntimeError("This tool only works on Windows.")
    main()
