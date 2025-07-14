"""
Main PyQt6 application entry point.
"""

import sys
import logging
import ctypes
import os
import argparse
from typing import Optional

import win32con
import win32gui
import win32api

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QTimer, pyqtSignal, QObject, pyqtSlot, QAbstractNativeEventFilter
from PyQt6.QtGui import QIcon

from src.game_wiki_tooltip.config import SettingsManager, GameConfigManager
from src.game_wiki_tooltip.qt_tray_icon import QtTrayIcon
from src.game_wiki_tooltip.qt_settings_window import QtSettingsWindow
from src.game_wiki_tooltip.qt_hotkey_manager import QtHotkeyManager, HotkeyError
from src.game_wiki_tooltip.assistant_integration import IntegratedAssistantController
from src.game_wiki_tooltip.utils import APPDATA_DIR, package_file

# 热键常量 - 与test_hotkey_only.py保持一致
MOD_CONTROL = 0x0002
VK_X = 0x58
HOTKEY_ID = 1

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded .env file")
except ImportError:
    logger.info("python-dotenv not available, skipping .env file loading")
except Exception as e:
    logger.warning(f"Failed to load .env file: {e}")

SETTINGS_PATH = APPDATA_DIR / "settings.json"
GAMES_CONFIG_PATH = APPDATA_DIR / "games.json"


class WindowsHotkeyFilter(QAbstractNativeEventFilter):
    """Windows消息过滤器 - 直接处理热键消息，避免Qt事件循环阻塞"""
    
    def __init__(self, hotkey_handler):
        super().__init__()
        self.hotkey_handler = hotkey_handler
        logger.info("WindowsHotkeyFilter初始化完成")
    
    def nativeEventFilter(self, eventType, message):
        """过滤Windows原生消息"""
        try:
            # 检查是否是Windows消息
            if eventType == b"windows_generic_MSG":
                # 将消息转换为可读格式
                msg_ptr = int(message)
                import ctypes
                from ctypes import wintypes
                
                # 定义MSG结构
                class MSG(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", wintypes.HWND),
                        ("message", wintypes.UINT),
                        ("wParam", wintypes.WPARAM),
                        ("lParam", wintypes.LPARAM),
                        ("time", wintypes.DWORD),
                        ("pt", wintypes.POINT)
                    ]
                
                # 获取消息内容
                msg = MSG.from_address(msg_ptr)
                
                # 检查是否是热键消息
                if msg.message == win32con.WM_HOTKEY:
                    logger.info(f"📨 原生事件过滤器收到热键消息: wParam={msg.wParam}, lParam={msg.lParam}")
                    
                    # 调用热键处理函数
                    if self.hotkey_handler:
                        self.hotkey_handler(msg.wParam, msg.lParam, "原生事件过滤器")
                    
                    # 返回True表示消息已处理
                    return True, 0
                    
        except Exception as e:
            logger.error(f"原生事件过滤器错误: {e}")
        
        # 返回False表示消息未处理，继续传递
        return False, 0


class GameWikiApp(QObject):
    """Main application controller"""
    
    def __init__(self):
        super().__init__()
        
        # Create QApplication first
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication(sys.argv)
            
        # Set application properties
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("GameWiki Assistant")
        
        # Try to set app icon
        try:
            icon_path = package_file("app.ico")
            self.app.setWindowIcon(QIcon(str(icon_path)))
        except:
            pass
            
        # Initialize managers
        self.settings_mgr = SettingsManager(SETTINGS_PATH)
        self.game_cfg_mgr = GameConfigManager(GAMES_CONFIG_PATH)
        
        # Initialize components
        self.tray_icon = None
        self.settings_window = None
        self.assistant_ctrl = None
        self.hotkey_mgr = None
        self.message_timer = None  # 用于主线程消息监听（备用）
        self.hotkey_triggered_count = 0  # 热键触发计数器
        self.native_filter = None  # Windows原生事件过滤器
        
        # Check command line arguments
        self.force_settings = '--settings' in sys.argv or '--config' in sys.argv
        
        # Check if first run
        self._check_first_run()
        
    def _check_first_run(self):
        """Check if this is first run and show settings"""
        settings = self.settings_mgr.get()
        
        # Check if API keys are configured (both settings.json and environment variables)
        api_config = settings.get('api', {})
        
        # Check Google API key
        google_api_key = (
            api_config.get('google_api_key') or 
            os.getenv('GOOGLE_API_KEY') or 
            os.getenv('GEMINI_API_KEY')
        )
        
        # Check Jina API key (optional but recommended)
        jina_api_key = (
            api_config.get('jina_api_key') or 
            os.getenv('JINA_API_KEY')
        )
        
        # Debug information
        logger.info(f"API Key Detection:")
        logger.info(f"  - settings.json Google API key: {'***found***' if api_config.get('google_api_key') else 'not found'}")
        logger.info(f"  - Environment GOOGLE_API_KEY: {'***found***' if os.getenv('GOOGLE_API_KEY') else 'not found'}")
        logger.info(f"  - Environment GEMINI_API_KEY: {'***found***' if os.getenv('GEMINI_API_KEY') else 'not found'}")
        logger.info(f"  - Final Google API key: {'***found***' if google_api_key else 'not found'}")
        logger.info(f"  - settings.json Jina API key: {'***found***' if api_config.get('jina_api_key') else 'not found'}")
        logger.info(f"  - Environment JINA_API_KEY: {'***found***' if os.getenv('JINA_API_KEY') else 'not found'}")
        logger.info(f"  - Final Jina API key: {'***found***' if jina_api_key else 'not found'}")
        
        if not google_api_key or self.force_settings:
            # No Google API key found OR user forced settings, show settings for initial setup
            if self.force_settings:
                logger.info("Settings window forced by command line argument")
            else:
                logger.info("No Google API key found in settings or environment variables")
            logger.info("Showing settings window for initial setup")
            self._show_settings(initial_setup=not self.force_settings)
        else:
            # API key found, initialize components
            logger.info("Google API key found, initializing components directly")
            if jina_api_key:
                logger.info("Found both Google and Jina API keys")
            else:
                logger.info("Found Google API key, Jina API key not configured (optional)")
            self._initialize_components()
            
    def _initialize_components(self):
        """Initialize all components"""
        try:
            # Initialize assistant controller
            self.assistant_ctrl = IntegratedAssistantController(self.settings_mgr)
            
            # Initialize tray icon
            self.tray_icon = QtTrayIcon()
            self.tray_icon.settings_requested.connect(self._show_settings)
            self.tray_icon.exit_requested.connect(self._quit_application)
            self.tray_icon.show()
            
            # Initialize hotkey manager with conflict resolution
            from src.game_wiki_tooltip.qt_hotkey_manager import HotkeyConflictStrategy
            self.hotkey_mgr = QtHotkeyManager(
                self.settings_mgr, 
                conflict_strategy=HotkeyConflictStrategy.FORCE_REGISTER,
                legacy_mode=True,  # 使用旧版兼容模式
                ultra_compatible_mode=True  # 使用超级兼容逻辑，确保任何情况下都能启动
            )
            self.hotkey_mgr.hotkey_triggered.connect(self._on_hotkey_triggered)
            logger.info("Hotkey manager signal connected")
            
            # Try to register hotkey with enhanced conflict resolution
            try:
                self.hotkey_mgr.register()
                
                if self.hotkey_mgr.is_registered():
                    # Show success notification
                    hotkey_string = self.hotkey_mgr.get_hotkey_string()
                    registration_info = self.hotkey_mgr.get_registration_info()
                    
                    if registration_info["legacy_mode"]:
                        if registration_info.get("ultra_compatible_mode", False):
                            mode_text = "超级兼容模式"
                        else:
                            mode_text = "旧版兼容模式"
                    else:
                        mode_text = "新版冲突处理模式"
                    
                    self.tray_icon.show_notification(
                        "GameWiki Assistant",
                        f"已启动，按 {hotkey_string} 呼出助手\n({mode_text})"
                    )
                    logger.info(f"热键注册成功: {hotkey_string} (legacy_mode={registration_info['legacy_mode']}, ultra_compatible_mode={registration_info.get('ultra_compatible_mode', False)})")
                else:
                    # Show warning but continue
                    self.tray_icon.show_notification(
                        "GameWiki Assistant",
                        "已启动，但热键注册失败。请在设置中配置热键或以管理员身份运行。"
                    )
                    logger.warning("热键注册失败，但程序继续运行")
                    
            except Exception as e:
                logger.error(f"Failed to register hotkey: {e}")
                # Don't show error dialog, just log and continue
                self.tray_icon.show_notification(
                    "GameWiki Assistant",
                    "已启动，但热键功能不可用。请检查设置或以管理员身份运行。"
                )
                
            # 安装Windows原生事件过滤器（主要方案）
            logger.info("安装Windows原生事件过滤器...")
            self.native_filter = WindowsHotkeyFilter(self._handle_hotkey_message_direct)
            self.app.installNativeEventFilter(self.native_filter)
            logger.info("Windows原生事件过滤器安装完成")
            
            # Start Windows message listener as backup
            logger.info("启动Windows消息监听器（备用方案）...")
            self.message_timer = QTimer()
            self.message_timer.timeout.connect(self._check_windows_messages)
            self.message_timer.start(50)  # Check every 50ms as backup
            logger.info("Windows消息监听器启动完成（备用）")
            
            # Show mini assistant
            logger.info("Showing mini assistant...")
            self.assistant_ctrl.show_mini()
            logger.info("Component initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            QMessageBox.critical(
                None,
                "初始化失败",
                f"程序初始化失败：{e}\n\n程序将退出。"
            )
            sys.exit(1)
            
    def _show_settings(self, initial_setup=False):
        """Show settings window"""
        if self.settings_window is None:
            self.settings_window = QtSettingsWindow(self.settings_mgr)
            self.settings_window.settings_applied.connect(self._on_settings_applied)
            
            if initial_setup:
                # Connect close event for initial setup
                self.settings_window.destroyed.connect(self._on_initial_setup_closed)
                
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
        
    def _on_initial_setup_closed(self):
        """Handle initial setup window closed"""
        # Check if API keys are available (settings or environment variables)
        settings = self.settings_mgr.get()
        api_config = settings.get('api', {})
        
        # Check Google API key from both sources
        google_api_key = (
            api_config.get('google_api_key') or 
            os.getenv('GOOGLE_API_KEY') or 
            os.getenv('GEMINI_API_KEY')
        )
        
        if google_api_key:
            # API key available, initialize components
            logger.info("API key available after settings window closed")
            self._initialize_components()
        else:
            # No API key available, exit
            QMessageBox.information(
                None,
                "设置未完成",
                "需要配置Google API密钥才能使用本程序。\n\n"
                "请在设置窗口中配置API密钥，或设置环境变量 GOOGLE_API_KEY。"
            )
            sys.exit(0)
            
    def _on_settings_applied(self):
        """Handle settings applied"""
        try:
            logger.info("Settings applied, checking component initialization status")
            
            # Check if components are already initialized
            if not hasattr(self, 'assistant_ctrl') or self.assistant_ctrl is None:
                logger.info("Components not initialized yet, initializing now...")
                self._initialize_components()
                return
            
            logger.info("Components already initialized, updating settings...")
            
            # Re-register hotkey
            if self.hotkey_mgr:
                logger.info("Re-registering hotkey...")
                self.hotkey_mgr.unregister()
                self.hotkey_mgr.register()
                
                # Show notification
                if self.tray_icon:
                    self.tray_icon.show_notification(
                        "设置已应用",
                        f"热键已更新为 {self.hotkey_mgr.get_hotkey_string()}"
                    )
                    
            # Reinitialize RAG components with new API keys
            if self.assistant_ctrl:
                logger.info("Reinitializing RAG components with new API keys...")
                settings = self.settings_mgr.get()
                api_settings = settings.get('api', {})
                
                # Reinitialize RAG integration
                self.assistant_ctrl.rag_integration._init_ai_components()
                
        except Exception as e:
            logger.error(f"Failed to apply settings: {e}")
            QMessageBox.warning(
                None,
                "应用设置失败",
                f"部分设置应用失败：{e}"
            )
            
    def _check_windows_messages(self):
        """Check for Windows messages in the main thread - 备用方案（使用test_hotkey_only.py的成功逻辑）"""
        try:
            # 使用与test_hotkey_only.py相同的消息检查逻辑
            msg = win32gui.PeekMessage(None, 0, 0, win32con.PM_REMOVE)
            
            if msg and msg[0]:
                # 检查是否是热键消息 - 与test_hotkey_only.py完全一致
                if msg[1][1] == win32con.WM_HOTKEY:
                    wParam = msg[1][2]
                    lParam = msg[1][3]
                    
                    logger.info(f"📨 [备用方案] 收到热键消息: wParam={wParam}, lParam={lParam}")
                    logger.info(f"   消息详情: {msg[1]}")
                    
                    # 使用test_hotkey_only.py的热键处理逻辑
                    self._handle_hotkey_message_direct(wParam, lParam, "备用方案")
                
                # 处理消息
                win32gui.TranslateMessage(msg[1])
                win32gui.DispatchMessage(msg[1])
        except Exception as e:
            logger.error(f"Error in _check_windows_messages: {e}")
    
    def _handle_hotkey_message_direct(self, wParam, lParam, source="未知"):
        """直接处理热键消息 - 使用test_hotkey_only.py的成功逻辑"""
        logger.info(f"🎯 处理热键消息[{source}]: wParam={wParam}, lParam={lParam}")
        
        # 与test_hotkey_only.py完全相同的处理逻辑
        if wParam == HOTKEY_ID:
            # 解析lParam - 与test_hotkey_only.py完全一致
            modifiers = lParam & 0xFFFF
            vk = (lParam >> 16) & 0xFFFF
            
            logger.info(f"   修饰键: {modifiers:#x} (期望: {MOD_CONTROL:#x})")
            logger.info(f"   虚拟键: {vk:#x} (期望: {VK_X:#x})")
            
            # 检查是否匹配 Ctrl+X - 与test_hotkey_only.py完全一致
            if modifiers == MOD_CONTROL and vk == VK_X:
                self.hotkey_triggered_count += 1
                logger.info(f"✅ 热键匹配正确! 第{self.hotkey_triggered_count}次触发，触发热键事件...")
                self._on_hotkey_triggered()
                return True
            else:
                logger.warning("⚠️ 热键匹配不正确")
                return False
        else:
            logger.warning(f"⚠️ 热键ID不匹配: 收到={wParam}, 期望={HOTKEY_ID}")
            return False
            
    def _on_hotkey_triggered(self):
        """Handle hotkey trigger"""
        logger.info("=== HOTKEY TRIGGERED ===")
        logger.info(f"热键触发! 第{self.hotkey_triggered_count}次，准备展开聊天窗口...")
        
        # 在显示聊天窗口前，立即获取当前前台窗口（游戏窗口）
        from src.game_wiki_tooltip.utils import get_foreground_title
        game_window_title = get_foreground_title()
        logger.info(f"🎮 热键触发时的前台窗口: '{game_window_title}'")
        
        if self.assistant_ctrl:
            logger.info("assistant_ctrl存在，调用expand_to_chat()...")
            try:
                # 将游戏窗口标题传递给assistant controller
                self.assistant_ctrl.set_current_game_window(game_window_title)
                self.assistant_ctrl.expand_to_chat()
                logger.info("expand_to_chat()执行成功")
            except Exception as e:
                logger.error(f"expand_to_chat()执行失败: {e}")
                import traceback
                traceback.print_exc()
        else:
            logger.warning("assistant_ctrl为None，无法展开聊天窗口")
            
        logger.info("=== 热键处理完成 ===")
            
    def _quit_application(self):
        """Quit application"""
        logger.info("Quitting application...")
        
        # Remove native event filter
        if self.native_filter:
            logger.info("移除Windows原生事件过滤器...")
            self.app.removeNativeEventFilter(self.native_filter)
            self.native_filter = None
            logger.info("Windows原生事件过滤器已移除")
        
        # Stop message listener
        if self.message_timer:
            self.message_timer.stop()
            logger.info("Windows消息监听器已停止")
            
        # Unregister hotkey
        if self.hotkey_mgr:
            self.hotkey_mgr.unregister()
            logger.info("热键注册已取消")
            
        # Clean up tray icon
        if self.tray_icon:
            self.tray_icon.cleanup()
            logger.info("系统托盘图标已清理")
            
        # Quit
        logger.info("应用程序退出中...")
        self.app.quit()
        
    def run(self):
        """Run the application"""
        return self.app.exec()


def main():
    """Main entry point"""
    if sys.platform != "win32":
        raise RuntimeError("This tool only works on Windows.")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='GameWiki Assistant')
    parser.add_argument('--settings', '--config', action='store_true', 
                       help='Force show settings window even if API keys are configured')
    args = parser.parse_args()
    
    if args.settings:
        logger.info("Settings window will be forced to show")
        
    # Enable DPI awareness
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass
            
    # Create and run app
    app = GameWikiApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main() 