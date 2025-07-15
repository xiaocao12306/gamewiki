"""
Hotkey configuration UI.
"""

import tkinter as tk
import ctypes
from tkinter import ttk, messagebox
import logging
from typing import Callable, Optional

from src.game_wiki_tooltip.config import SettingsManager  # noqa: WPS433

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

def ask_hotkey_setting(default=None, on_close=None, on_apply=None):
    """
    弹出热键设置窗口，返回用户选择的配置(dict)：
    {
        'ctrl': True/False,
        'shift': True/False,
        'alt': True/False,
        'win': True/False,
        'key': 'F1'/'A'/...
    }
    用户关闭窗口或未选择key时返回None
    """
    result = {}

    def on_save():
        # 读取设置
        if not cmb_key.get():
            messagebox.showwarning("提示", "请选择一个主键")
            return
        result['ctrl'] = var_ctrl.get()
        result['shift'] = var_shift.get()
        result['alt'] = var_alt.get()
        result['win'] = var_win.get()
        result['key'] = cmb_key.get()
        if on_apply:
            on_apply(result)  # 传递结果给回调函数
        window.destroy()

    def _on_close():
        if on_close:
            on_close()
        window.destroy()

    window = tk.Toplevel()
    window.title("Game Wiki Tooltip 设置")
    window.geometry("530x650")
    window.resizable(False, False)
    window.configure(bg="#f8fafc")
    window.protocol("WM_DELETE_WINDOW", _on_close)
    if on_close:
        window.bind("<Destroy>", lambda e: on_close())

    # 设置图标（需要 app.ico 放到同级目录）
    try:
        window.iconbitmap("app.ico")
    except Exception:
        pass

    # 配置网格权重，让内容能够自适应宽度
    window.grid_columnconfigure(0, weight=1)
    window.grid_columnconfigure(1, weight=1)

    # --------- 标题 ---------
    title = tk.Label(window, text="全局热键设置", font=("微软雅黑", 16, "bold"),
                     bg="#f8fafc", fg="#24292f", pady=14)
    title.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20)

    # --------- 组合键选择 ---------
    hotkey_label = tk.Label(window, text="请选择组合键：", font=("微软雅黑", 11),
                            bg="#f8fafc")
    hotkey_label.grid(row=1, column=0, sticky="w", padx=20, pady=(4,0), columnspan=2)

    var_ctrl = tk.BooleanVar(value=(default.get('ctrl') if default else True))
    var_shift = tk.BooleanVar(value=(default.get('shift') if default else False))
    var_alt = tk.BooleanVar(value=(default.get('alt') if default else False))
    var_win = tk.BooleanVar(value=(default.get('win') if default else False))

    check_frame = tk.Frame(window, bg="#f8fafc")
    check_frame.grid(row=2, column=0, sticky="w", padx=20, columnspan=2)
    tk.Checkbutton(check_frame, text="Ctrl", variable=var_ctrl, bg="#f8fafc", font=("微软雅黑", 10)).pack(side="left", padx=(0, 14))
    tk.Checkbutton(check_frame, text="Shift", variable=var_shift, bg="#f8fafc", font=("微软雅黑", 10)).pack(side="left", padx=(0, 14))
    tk.Checkbutton(check_frame, text="Alt", variable=var_alt, bg="#f8fafc", font=("微软雅黑", 10)).pack(side="left", padx=(0, 14))
    tk.Checkbutton(check_frame, text="Win", variable=var_win, bg="#f8fafc", font=("微软雅黑", 10)).pack(side="left")

    # --------- 主键选择 ---------
    key_label = tk.Label(window, text="主键：", font=("微软雅黑", 11), bg="#f8fafc")
    key_label.grid(row=3, column=0, sticky="w", padx=20, pady=(14, 2))

    key_list = [chr(x) for x in range(ord('A'), ord('Z')+1)] + [f"F{i}" for i in range(1, 12)]
    cmb_key = ttk.Combobox(window, values=key_list, width=8, font=("微软雅黑", 11))
    cmb_key.grid(row=3, column=1, sticky="w", padx=0, pady=(14,2))
    cmb_key.set(default['key'] if default and default.get('key') else "")

    # --------- 保存按钮 ---------
    btn_save = tk.Button(window, text="保存并应用", font=("微软雅黑", 11, "bold"),
                         bg="#1668dc", fg="white", activebackground="#4096ff",
                         relief="raised", bd=2, height=1, width=16, command=on_save, cursor="hand2")
    btn_save.grid(row=4, column=0, columnspan=2, pady=(24, 6), sticky="ew", padx=20)

    # --------- 多段提示 ---------
    tip_frame = tk.Frame(window, bg="#f8fafc")
    tip_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=20, pady=12)
    
    # 创建一个内部容器来居中放置tips内容
    inner_tip_frame = tk.Frame(tip_frame, bg="#f8fafc")
    inner_tip_frame.pack(expand=True, fill="x")

    # 主要提示
    tips = [
        ("在游戏中按下热键后，即可打开游戏对应网页，再次按下热键即可呼出鼠标光标。在游戏中尝试一下吧！", "#24292f"),
        ("注意！！", "#b91c1c"),
        ("部分游戏(如cs2等)可能不支持只勾选Shift，建议勾选Ctrl", "#b45309"),
        ("注册的热键会与其他应用的热键冲突，请尽量设置平常用不到的热键组合", "#b45309"),
        ("需要在游戏中将显示模式切换为窗口全屏或无边框全屏，浮窗才会显示", "#2563eb"),
        ("第一次运行应用时，打开网页速度可能较慢，请耐心等待。", "#475569"),
    ]
    for idx, (text, color) in enumerate(tips):
        lab = tk.Label(inner_tip_frame, text=text, font=("微软雅黑", 9, "bold" if idx == 1 else "normal"),
                       bg="#f8fafc", fg=color, anchor="w", justify="left", wraplength=480)
        lab.pack(anchor="w", pady=(0, 4) if idx else (0,8))

    # 立即返回 window 实例
    return window

# --- 用法示例 ---
if __name__ == "__main__":
    config = ask_hotkey_setting()
    print("用户选择：", config)

# ---------------------------------------------------------------------------
# 公共工具：在任意位置调用以让用户配置热键并写回 settings.json。
# ---------------------------------------------------------------------------

def configure_hotkey(settings_mgr, on_close=None, on_apply=None):
    """弹出热键设置窗口，保存用户选择，并返回窗口实例（或None）。"""
    if not isinstance(settings_mgr, SettingsManager):
        raise TypeError("settings_mgr must be an instance of SettingsManager")

    # 获取当前设置
    current_settings = settings_mgr.get()
    hotkey_settings = current_settings.get('hotkey', {})
    default = {
        'ctrl': 'Ctrl' in hotkey_settings.get('modifiers', []),
        'shift': 'Shift' in hotkey_settings.get('modifiers', []),
        'alt': 'Alt' in hotkey_settings.get('modifiers', []),
        'win': 'Win' in hotkey_settings.get('modifiers', []),
        'key': hotkey_settings.get('key', 'X'),
    }

    def _on_apply(new_settings):
        # 构建新的热键设置
        modifiers = []
        if new_settings.get('ctrl'):
            modifiers.append('Ctrl')
        if new_settings.get('shift'):
            modifiers.append('Shift')
        if new_settings.get('alt'):
            modifiers.append('Alt')
        if new_settings.get('win'):
            modifiers.append('Win')
            
        hotkey_config = {
            'hotkey': {
                'modifiers': modifiers,
                'key': new_settings['key']
            }
        }
        
        # 更新设置
        settings_mgr.update(hotkey_config)
        # 调用外部回调
        if on_apply:
            on_apply()

    # 直接调用 ask_hotkey_setting，返回窗口实例
    return ask_hotkey_setting(default, on_close=on_close, on_apply=_on_apply)
