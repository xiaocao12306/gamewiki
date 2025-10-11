"""
GameWikiTooltip 卸载程序
移除所有应用程序文件和用户数据
"""

import os
import sys
import shutil
import winreg
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import ctypes

def is_admin():
    """检查脚本是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """以管理员权限重新运行脚本"""
    if is_admin():
        return True
    else:
        # 以管理员权限重新运行程序
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        return False

class GameWikiUninstaller:
    def __init__(self):
        self.app_name = "GuidorTooltip"
        self.display_name = "Guidor Assistant"
        self.appdata_dir = Path.home() / "AppData" / "Roaming" / self.app_name
        self.install_dir = None
        self.is_portable = False
        self.removed_items = []
        self.failed_items = []
        
    def detect_install_directory(self):
        """尝试检测安装目录"""
        # 首先检查是否从安装目录运行
        current_dir = Path(sys.executable).parent
        
        # 便携版 - 检查父目录是否存在GuidorAssistant文件夹
        if (current_dir / "GuidorAssistant").exists() and (current_dir / "GuidorAssistant" / "GuidorAssistant.exe").exists():
            # 便携版单目录版本
            self.install_dir = current_dir / "GuidorAssistant"
            self.is_portable = True
            return True
        elif (current_dir / "GuidorAssistant.exe").exists():
            # 与卸载程序同一目录（单文件或已安装版本）
            self.install_dir = current_dir
            self.is_portable = True
            return True
            
        # 检查常见安装位置（Inno Setup安装版本）
        common_paths = [
            Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / "Guidor Assistant",
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')) / "Guidor Assistant",
            Path(os.environ.get('LOCALAPPDATA', '')) / "Programs" / "Guidor Assistant",
        ]
        
        for path in common_paths:
            if path.exists() and (path / "GuidorAssistant.exe").exists():
                self.install_dir = path
                self.is_portable = False
                return True
                
        return False
    
    def remove_directory(self, path: Path, description: str):
        """删除目录及其内容"""
        if not path.exists():
            return True
            
        try:
            shutil.rmtree(path, ignore_errors=False)
            self.removed_items.append(f"✓ {description}: {path}")
            return True
        except PermissionError:
            self.failed_items.append(f"✗ {description}: {path} (权限被拒绝)")
            return False
        except Exception as e:
            self.failed_items.append(f"✗ {description}: {path} ({str(e)})")
            return False
    
    def remove_file(self, path: Path, description: str):
        """删除单个文件"""
        if not path.exists():
            return True
            
        try:
            path.unlink()
            self.removed_items.append(f"✓ {description}: {path}")
            return True
        except Exception as e:
            self.failed_items.append(f"✗ {description}: {path} ({str(e)})")
            return False
    
    def remove_shortcuts(self):
        """删除桌面和开始菜单快捷方式"""
        shortcuts_removed = []
        
        # 桌面快捷方式
        desktop = Path.home() / "Desktop" / f"{self.display_name}.lnk"
        if desktop.exists():
            if self.remove_file(desktop, "桌面快捷方式"):
                shortcuts_removed.append("桌面")
        
        # 开始菜单快捷方式
        start_menu_paths = [
            Path(os.environ.get('APPDATA', '')) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / self.display_name,
            Path(os.environ.get('PROGRAMDATA', '')) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / self.display_name,
        ]
        
        for start_menu in start_menu_paths:
            if start_menu.exists():
                if self.remove_directory(start_menu, "开始菜单文件夹"):
                    shortcuts_removed.append("开始菜单")
        
        # 快速启动快捷方式
        quick_launch = Path(os.environ.get('APPDATA', '')) / "Microsoft" / "Internet Explorer" / "Quick Launch" / f"{self.display_name}.lnk"
        if quick_launch.exists():
            if self.remove_file(quick_launch, "快速启动快捷方式"):
                shortcuts_removed.append("快速启动")
                
        return shortcuts_removed
    
    def remove_registry_entries(self):
        """删除注册表项（仅限已安装版本）"""
        try:
            # 删除卸载项
            uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8F7A9E2C-4B3D-4E6A-9C1F-2A3B4C5D6E7F}_is1"
            
            try:
                winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, uninstall_key)
                self.removed_items.append(f"✓ 注册表卸载项")
            except:
                # 如果HKLM失败，尝试HKEY_CURRENT_USER
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, uninstall_key)
                    self.removed_items.append(f"✓ 注册表卸载项（用户）")
                except:
                    pass
                    
        except Exception as e:
            # 便携版可能不存在注册表项
            pass
    
    def remove_temp_files(self):
        """删除PyInstaller创建的临时文件"""
        temp_dir = Path(os.environ.get('TEMP', ''))
        removed_count = 0
        
        # 删除_MEI*目录（PyInstaller临时文件）
        for item in temp_dir.glob("_MEI*"):
            if item.is_dir():
                try:
                    shutil.rmtree(item, ignore_errors=True)
                    removed_count += 1
                except:
                    pass
                    
        if removed_count > 0:
            self.removed_items.append(f"✓ 临时文件: {removed_count} 个PyInstaller临时文件夹")
            
        return removed_count > 0
    
    def uninstall(self, remove_install_dir=True):
        """执行卸载"""
        success = True
        
        # 1. 删除AppData文件夹
        if self.appdata_dir.exists():
            self.remove_directory(self.appdata_dir, "用户数据文件夹")
        
        # 2. 删除快捷方式
        self.remove_shortcuts()
        
        # 3. 删除注册表项（仅限已安装版本）
        if not self.is_portable:
            self.remove_registry_entries()
        
        # 4. 删除临时文件
        self.remove_temp_files()
        
        # 5. 删除安装目录（如果指定且检测到）
        if remove_install_dir and self.install_dir:
            # 对于便携版，检查是否在父目录中
            uninstaller_parent = Path(sys.executable).parent
            
            # 检查是否需要清理整个便携版目录
            if self.is_portable and uninstaller_parent.name.startswith("GuidorAssistant_Portable"):
                # 我们在便携版目录中，需要清理整个目录
                self.removed_items.append(f"⚠ 便携版文件夹将在重启后删除: {uninstaller_parent}")
                self.create_cleanup_batch(uninstaller_parent)
            elif Path(sys.executable).parent == self.install_dir:
                # 无法删除正在运行的目录
                self.removed_items.append(f"⚠ 安装文件夹将在重启后删除: {self.install_dir}")
                self.create_cleanup_batch(self.install_dir)
            else:
                self.remove_directory(self.install_dir, "安装文件夹")
        
        return len(self.failed_items) == 0
    
    def create_cleanup_batch(self, target_dir=None):
        """创建批处理文件，在卸载程序退出后删除安装文件夹"""
        if not target_dir:
            target_dir = self.install_dir
        if not target_dir:
            return
            
        batch_content = f"""@echo off
echo 等待卸载程序关闭...
timeout /t 3 /nobreak > nul
echo 正在删除安装文件夹...
rmdir /s /q "{target_dir}"
echo 清理完成。
del "%~f0"
"""
        
        batch_file = Path(os.environ.get('TEMP', '')) / "guidor_cleanup.bat"
        try:
            batch_file.write_text(batch_content)
            # 启动批处理文件
            os.startfile(str(batch_file))
        except:
            pass

class UninstallerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Guidor Assistant 卸载程序")
        self.root.geometry("500x400")
        self.root.resizable(False, False)
        
        # 设置窗口图标（如果可用）
        try:
            if getattr(sys, 'frozen', False):
                # 作为编译的exe运行
                icon_path = Path(sys._MEIPASS) / "app.ico"
            else:
                # 作为脚本运行
                icon_path = Path(__file__).parent / "src" / "game_wiki_tooltip" / "assets" / "app.ico"
            
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except:
            pass
        
        self.uninstaller = GameWikiUninstaller()
        self.create_widgets()
        
    def create_widgets(self):
        # 标题
        title_frame = tk.Frame(self.root, bg="#2196F3", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="Guidor Assistant 卸载程序",
            font=("Arial", 16, "bold"),
            bg="#2196F3",
            fg="white"
        )
        title_label.pack(pady=15)
        
        # 信息框架
        info_frame = tk.Frame(self.root, padx=20, pady=20)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        info_text = (
            "这将从您的计算机中移除 Guidor Assistant。\n\n"
            "以下内容将被删除：\n"
            "• 应用程序文件\n"
            "• 用户设置和数据\n"
            "• 桌面和开始菜单快捷方式\n"
            "• 临时文件\n"
        )
        
        info_label = tk.Label(info_frame, text=info_text, justify=tk.LEFT, font=("Arial", 10))
        info_label.pack(anchor=tk.W)
        
        # 选项
        self.remove_userdata_var = tk.BooleanVar(value=True)
        userdata_check = tk.Checkbutton(
            info_frame,
            text="删除用户设置和数据",
            variable=self.remove_userdata_var,
            font=("Arial", 10)
        )
        userdata_check.pack(anchor=tk.W, pady=(20, 5))
        
        # 检测到的安装
        if self.uninstaller.detect_install_directory():
            install_type = "便携版" if self.uninstaller.is_portable else "已安装"
            detected_label = tk.Label(
                info_frame,
                text=f"找到安装 ({install_type}): {self.uninstaller.install_dir}",
                font=("Arial", 9),
                fg="green"
            )
            detected_label.pack(anchor=tk.W, pady=(10, 0))
        
        # 按钮
        button_frame = tk.Frame(self.root, padx=20, pady=20)
        button_frame.pack(fill=tk.X)
        
        uninstall_btn = tk.Button(
            button_frame,
            text="卸载",
            command=self.perform_uninstall,
            bg="#f44336",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        )
        uninstall_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        cancel_btn = tk.Button(
            button_frame,
            text="取消",
            command=self.root.quit,
            font=("Arial", 10),
            padx=20,
            pady=5
        )
        cancel_btn.pack(side=tk.RIGHT)
        
    def perform_uninstall(self):
        # 确认
        if not messagebox.askyesno(
            "确认卸载",
            "您确定要卸载 Guidor Assistant 吗？\n\n此操作无法撤销。",
            icon='warning'
        ):
            return
        
        # 执行卸载
        success = self.uninstaller.uninstall(remove_install_dir=True)
        
        # 显示结果
        result_window = tk.Toplevel(self.root)
        result_window.title("卸载完成")
        result_window.geometry("500x400")
        result_window.resizable(False, False)
        
        # 标题
        title_frame = tk.Frame(result_window, bg="#4CAF50" if success else "#f44336", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="卸载完成" if success else "卸载完成（有错误）",
            font=("Arial", 16, "bold"),
            bg="#4CAF50" if success else "#f44336",
            fg="white"
        )
        title_label.pack(pady=15)
        
        # 结果
        results_frame = tk.Frame(result_window, padx=20, pady=20)
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建带滚动条的文本组件
        text_frame = tk.Frame(results_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        results_text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 9),
            height=15
        )
        results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=results_text.yview)
        
        # 添加结果
        results_text.insert(tk.END, "已删除的项目：\n")
        results_text.insert(tk.END, "-" * 50 + "\n")
        for item in self.uninstaller.removed_items:
            results_text.insert(tk.END, item + "\n")
        
        if self.uninstaller.failed_items:
            results_text.insert(tk.END, "\n失败的项目：\n")
            results_text.insert(tk.END, "-" * 50 + "\n")
            for item in self.uninstaller.failed_items:
                results_text.insert(tk.END, item + "\n")
        
        results_text.config(state=tk.DISABLED)
        
        # 关闭按钮
        close_btn = tk.Button(
            result_window,
            text="关闭",
            command=self.root.quit,
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        )
        close_btn.pack(pady=10)
        
        # 隐藏主窗口
        self.root.withdraw()
        
    def run(self):
        self.root.mainloop()

def main():
    # 检查管理员权限（可选，但建议用于完全删除）
    if not is_admin():
        response = messagebox.askyesno(
            "管理员权限",
            "没有管理员权限可能无法完全删除。\n\n"
            "您是否要以管理员权限重新启动？",
            icon='warning'
        )
        if response:
            if not run_as_admin():
                sys.exit(0)
    
    # 运行GUI
    app = UninstallerGUI()
    app.run()

if __name__ == "__main__":
    main()