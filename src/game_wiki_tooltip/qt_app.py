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

from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox
from PyQt6.QtCore import QTimer, pyqtSignal, QObject, pyqtSlot, QAbstractNativeEventFilter, Qt
from PyQt6.QtGui import QIcon

from src.game_wiki_tooltip.config import SettingsManager, GameConfigManager
from src.game_wiki_tooltip.qt_tray_icon import QtTrayIcon
from src.game_wiki_tooltip.qt_settings_window import QtSettingsWindow
from src.game_wiki_tooltip.qt_hotkey_manager import QtHotkeyManager, HotkeyError
from src.game_wiki_tooltip.assistant_integration import IntegratedAssistantController
from src.game_wiki_tooltip.utils import APPDATA_DIR, package_file
from src.game_wiki_tooltip.i18n import init_translations, t

# 热键常量 - 与test_hotkey_only.py保持一致
MOD_CONTROL = 0x0002
VK_X = 0x58
HOTKEY_ID = 1

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 抑制markdown库的重复调试信息
try:
    markdown_logger = logging.getLogger('MARKDOWN')
    markdown_logger.setLevel(logging.WARNING)
except:
    pass  # 如果没有markdown库，忽略

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


class ApiKeyMissingDialog(QDialog):
    """自定义对话框，用于处理API key缺失的通知"""
    
    def __init__(self, missing_keys, parent=None):
        super().__init__(parent)
        self.missing_keys = missing_keys
        self.dont_remind = False
        self.open_settings = False
        self._init_ui()
        
    def _init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("GameWiki Assistant")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.setFixedSize(400, 220)
        
        # 主布局
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("AI Features Unavailable")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #d32f2f;")
        layout.addWidget(title_label)
        
        # 消息内容
        message = (
            "AI guide features require both API keys to function properly:\n\n"
            f"Missing: {', '.join(self.missing_keys)}\n\n"
            "⚠️ Note: Gemini API alone cannot provide high-quality RAG functionality.\n"
            "Jina vector search is essential for complete AI guide features.\n\n"
            "You can still use Wiki search without API keys."
        )
        
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("font-size: 11px; line-height: 1.4;")
        layout.addWidget(message_label)
        
        # "不再提醒" 复选框
        self.dont_remind_checkbox = QCheckBox("Don't remind me again (Wiki search only)")
        self.dont_remind_checkbox.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.dont_remind_checkbox)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # 配置按钮
        config_button = QPushButton("Configure API Keys")
        config_button.setStyleSheet("""
            QPushButton {
                background-color: #1976d2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
        """)
        config_button.clicked.connect(self._on_configure_clicked)
        button_layout.addWidget(config_button)
        
        # 稍后按钮
        later_button = QPushButton("Maybe Later")
        later_button.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        later_button.clicked.connect(self._on_later_clicked)
        button_layout.addWidget(later_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
    def _on_configure_clicked(self):
        """用户点击配置按钮"""
        self.dont_remind = self.dont_remind_checkbox.isChecked()
        self.open_settings = True
        self.accept()
        
    def _on_later_clicked(self):
        """用户点击稍后按钮"""
        self.dont_remind = self.dont_remind_checkbox.isChecked()
        self.open_settings = False
        self.accept()


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
        
        # Initialize translation system based on settings
        settings = self.settings_mgr.get()
        current_language = settings.get('language', 'en')
        init_translations(current_language)
        
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
        
        # Check Gemini API key
        gemini_api_key = (
            api_config.get('gemini_api_key') or 
            os.getenv('GEMINI_API_KEY') or 
            os.getenv('GOOGLE_API_KEY')
        )
        
        # Check Jina API key (现在也是必需的，不再是可选的)
        jina_api_key = (
            api_config.get('jina_api_key') or 
            os.getenv('JINA_API_KEY')
        )
        
        # Debug information
        logger.info(f"API Key Detection:")
        logger.info(f"  - settings.json Gemini API key: {'***found***' if api_config.get('gemini_api_key') else 'not found'}")
        logger.info(f"  - Environment GEMINI_API_KEY: {'***found***' if os.getenv('GEMINI_API_KEY') else 'not found'}")
        logger.info(f"  - Environment GOOGLE_API_KEY: {'***found***' if os.getenv('GOOGLE_API_KEY') else 'not found'}")
        logger.info(f"  - Final Gemini API key: {'***found***' if gemini_api_key else 'not found'}")
        logger.info(f"  - settings.json Jina API key: {'***found***' if api_config.get('jina_api_key') else 'not found'}")
        logger.info(f"  - Environment JINA_API_KEY: {'***found***' if os.getenv('JINA_API_KEY') else 'not found'}")
        logger.info(f"  - Final Jina API key: {'***found***' if jina_api_key else 'not found'}")
        
        # 检查是否同时有两个API key
        has_both_keys = bool(gemini_api_key and jina_api_key)
        dont_remind = settings.get('dont_remind_api_missing', False)
        logger.info(f"  - Both API keys available: {has_both_keys}")
        logger.info(f"  - Don't remind API missing: {dont_remind}")
        
        # 修改逻辑：强制显示设置窗口的情况
        if self.force_settings:
            logger.info("Settings window forced by command line argument")
            self._show_settings(initial_setup=False)
        elif not has_both_keys:
            # 没有两个API key时，显示信息但不强制退出
            missing_keys = []
            if not gemini_api_key:
                missing_keys.append("Gemini API Key")
            if not jina_api_key:
                missing_keys.append("Jina API Key")
            
            logger.info(f"Missing API keys: {', '.join(missing_keys)}, starting in limited mode")
            logger.info("User will be able to use wiki search but not AI guide features")
            
            # 显示通知告知用户功能受限
            self._initialize_components(limited_mode=True)
            
            # 如果用户没有选择"不再提醒"，自动打开设置界面
            if not dont_remind:
                logger.info("Auto-opening settings window for API key configuration")
                self._show_settings(initial_setup=True)
        else:
            # 同时有两个API key，initialize components normally
            logger.info("Found both Google/Gemini and Jina API keys, initializing components with full functionality")
            self._initialize_components(limited_mode=False)
            
    def _initialize_components(self, limited_mode=False):
        """Initialize all components"""
        try:
            # 确保在初始化新的assistant controller之前，清理可能存在的旧实例
            if hasattr(self, 'assistant_ctrl') and self.assistant_ctrl:
                logger.info("检测到已存在的assistant controller，先进行清理...")
                
                # 清理悬浮窗
                if hasattr(self.assistant_ctrl, 'mini_window') and self.assistant_ctrl.mini_window:
                    try:
                        logger.info("清理已存在的悬浮窗...")
                        self.assistant_ctrl.mini_window.hide()
                        self.assistant_ctrl.mini_window.close()
                        self.assistant_ctrl.mini_window.deleteLater()
                        self.assistant_ctrl.mini_window = None
                    except Exception as e:
                        logger.warning(f"清理已存在悬浮窗时出错: {e}")
                        self.assistant_ctrl.mini_window = None
                
                # 清理主窗口
                if hasattr(self.assistant_ctrl, 'main_window') and self.assistant_ctrl.main_window:
                    try:
                        logger.info("清理已存在的主窗口...")
                        self.assistant_ctrl.main_window.hide()
                        self.assistant_ctrl.main_window.close()
                        self.assistant_ctrl.main_window.deleteLater()
                        self.assistant_ctrl.main_window = None
                    except Exception as e:
                        logger.warning(f"清理已存在主窗口时出错: {e}")
                        self.assistant_ctrl.main_window = None
                
                # 断开信号连接
                try:
                    if hasattr(self.assistant_ctrl, 'rag_integration'):
                        self.assistant_ctrl.rag_integration.disconnect()
                except Exception as e:
                    logger.warning(f"断开旧的RAG integration信号连接时出错: {e}")
                
                self.assistant_ctrl = None
                logger.info("已存在的assistant controller清理完成")
            
            # Initialize assistant controller with limited mode flag
            self.assistant_ctrl = IntegratedAssistantController(self.settings_mgr, limited_mode=limited_mode)
            
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
                    
                    if limited_mode:
                        # 合并启动通知：热键信息 + 受限模式信息
                        notification_msg = (
                            f"{t('hotkey_registered', hotkey=hotkey_string)}\n"
                            f"Started in limited mode (Wiki search only)\n"
                            f"Running in {mode_text}\n\n"
                            f"Missing API keys for AI guide features\n"
                            f"Configure complete API keys to enable full functionality"
                        )
                    else:
                        # 完整功能模式的通知
                        notification_msg = f"{t('hotkey_registered', hotkey=hotkey_string)}\nFull functionality enabled ({mode_text})"
                    
                    self.tray_icon.show_notification(
                        "GameWiki Assistant",
                        notification_msg
                    )
                    logger.info(f"热键注册成功: {hotkey_string} (legacy_mode={registration_info['legacy_mode']}, ultra_compatible_mode={registration_info.get('ultra_compatible_mode', False)}, limited_mode={limited_mode})")
                else:
                    # Show warning but continue
                    self.tray_icon.show_notification(
                        "GameWiki Assistant",
                        t("hotkey_failed")
                    )
                    logger.warning("热键注册失败，但程序继续运行")
                    
            except Exception as e:
                logger.error(f"Failed to register hotkey: {e}")
                # Don't show error dialog, just log and continue
                self.tray_icon.show_notification(
                    "GameWiki Assistant",
                    t("hotkey_failed")
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
            
            # Show mini assistant (延迟显示，确保之前的清理操作完成)
            logger.info("Showing mini assistant...")
            QTimer.singleShot(50, self.assistant_ctrl.show_mini)
            logger.info(f"Component initialization completed successfully (limited_mode={limited_mode})")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            QMessageBox.critical(
                None,
                t("error"),
                f"程序初始化失败：{e}\n\n程序将退出。"
            )
            sys.exit(1)
            
    def _show_settings(self, initial_setup=False):
        """Show settings window"""
        if self.settings_window is None:
            self.settings_window = QtSettingsWindow(self.settings_mgr)
            self.settings_window.settings_applied.connect(self._on_settings_applied)
            
            # 移除initial_setup处理逻辑，因为现在不会因为没有API key而强制退出
                
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
        
    def _on_initial_setup_closed(self):
        """Handle initial setup window closed - deprecated, kept for compatibility"""
        # 这个方法现在不再使用，因为我们不再强制要求API key
        # 保留是为了兼容性，但实际上不会被调用
        pass
            
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
            
            # 检查当前API key配置，决定是否需要切换模式
            settings = self.settings_mgr.get()
            api_config = settings.get('api', {})
            
            # Check Gemini API key from both sources
            gemini_api_key = (
                api_config.get('gemini_api_key') or 
                os.getenv('GEMINI_API_KEY') or 
                os.getenv('GOOGLE_API_KEY')
            )
            
            # Check Jina API key (现在也是必需的)
            jina_api_key = (
                api_config.get('jina_api_key') or 
                os.getenv('JINA_API_KEY')
            )
            
            # 检查是否同时有两个API key
            has_both_keys = bool(gemini_api_key and jina_api_key)
            dont_remind = settings.get('dont_remind_api_missing', False)
            
            # 检查是否需要切换模式
            current_limited_mode = getattr(self.assistant_ctrl, 'limited_mode', True)
            new_limited_mode = not has_both_keys
            
            logger.info(f"模式检查: 当前受限模式={current_limited_mode}, 新受限模式={new_limited_mode}")
            logger.info(f"API key状态: Gemini={'✓' if gemini_api_key else '✗'}, Jina={'✓' if jina_api_key else '✗'}")
            
            # 检查是否需要显示API key缺失对话框（只在从完整模式切换到受限模式时显示）
            show_api_dialog = (new_limited_mode and not current_limited_mode and not dont_remind)
            
            if show_api_dialog:
                missing_keys = []
                if not gemini_api_key:
                    missing_keys.append("Gemini API Key")
                if not jina_api_key:
                    missing_keys.append("Jina API Key")
                
                # 显示自定义对话框
                dialog = ApiKeyMissingDialog(missing_keys, parent=None)
                dialog.exec()
                
                # 处理用户的选择
                if dialog.dont_remind:
                    logger.info("User selected 'Don't remind me again'")
                    self.settings_mgr.update({'dont_remind_api_missing': True})
                
                if dialog.open_settings:
                    logger.info("User chose to configure API keys")
                    # 不需要在这里打开设置窗口，因为它应该已经打开了
                else:
                    logger.info("User chose to continue without API keys")
                    
            if current_limited_mode != new_limited_mode:
                # 需要切换模式，重新初始化组件
                logger.info(f"模式切换: {current_limited_mode} -> {new_limited_mode}")
                
                # 清理现有组件（添加正确的清理逻辑）
                if hasattr(self, 'assistant_ctrl') and self.assistant_ctrl:
                    logger.info("正在清理旧的assistant controller...")
                    
                    # 清理悬浮窗
                    if hasattr(self.assistant_ctrl, 'mini_window') and self.assistant_ctrl.mini_window:
                        try:
                            logger.info("清理旧的悬浮窗...")
                            self.assistant_ctrl.mini_window.hide()
                            self.assistant_ctrl.mini_window.close()
                            self.assistant_ctrl.mini_window.deleteLater()
                            self.assistant_ctrl.mini_window = None
                            logger.info("旧的悬浮窗已清理")
                        except Exception as e:
                            logger.warning(f"清理旧悬浮窗时出错: {e}")
                            self.assistant_ctrl.mini_window = None
                    
                    # 清理主窗口
                    if hasattr(self.assistant_ctrl, 'main_window') and self.assistant_ctrl.main_window:
                        try:
                            logger.info("清理旧的主窗口...")
                            self.assistant_ctrl.main_window.hide()
                            self.assistant_ctrl.main_window.close()
                            self.assistant_ctrl.main_window.deleteLater()
                            self.assistant_ctrl.main_window = None
                            logger.info("旧的主窗口已清理")
                        except Exception as e:
                            logger.warning(f"清理旧主窗口时出错: {e}")
                            self.assistant_ctrl.main_window = None
                    
                    # 断开信号连接，避免内存泄漏
                    try:
                        if hasattr(self.assistant_ctrl, 'rag_integration'):
                            self.assistant_ctrl.rag_integration.disconnect()
                    except Exception as e:
                        logger.warning(f"断开RAG integration信号连接时出错: {e}")
                    
                    # 清理assistant_ctrl引用
                    self.assistant_ctrl = None
                    logger.info("旧的assistant controller已清理")
                
                # 重新初始化组件（稍微延迟，确保旧窗口完全清理）
                QTimer.singleShot(100, lambda: self._initialize_components(limited_mode=new_limited_mode))
                
                # 显示模式切换通知（但不重复显示热键通知）
                mode_switched = True  # 标记已进行模式切换
                if self.tray_icon:
                    if new_limited_mode:
                        missing_keys = []
                        if not gemini_api_key:
                            missing_keys.append("Gemini API Key")
                        if not jina_api_key:
                            missing_keys.append("Jina API Key")
                        
                        self.tray_icon.show_notification(
                            "GameWiki Assistant",
                            f"Switched to limited mode\n\nOnly Wiki search is available\n\nMissing API keys: {', '.join(missing_keys)}\nConfigure complete API keys for full functionality"
                        )
                    else:
                        self.tray_icon.show_notification(
                            "GameWiki Assistant",
                            "Switched to full functionality mode\n\nWiki search and AI guide features are now available\n\nComplete API key configuration detected"
                        )
                
                logger.info("模式切换完成")
                return
            
            # 如果不需要切换模式，继续原有的设置更新逻辑
            mode_switched = False  # 未进行模式切换
            
            # Update translation manager with new language
            current_language = settings.get('language', 'en')
            from src.game_wiki_tooltip.i18n import set_language
            set_language(current_language)
            
            # Reload games configuration for the new language
            if self.game_cfg_mgr:
                logger.info(f"Reloading games configuration for language: {current_language}")
                self.game_cfg_mgr.reload_for_language(current_language)
                
            # 检测语言变化并重新加载RAG integration的游戏配置
            if self.assistant_ctrl and hasattr(self.assistant_ctrl, 'rag_integration'):
                if hasattr(self.assistant_ctrl.rag_integration, '_current_language'):
                    old_language = self.assistant_ctrl.rag_integration._current_language
                    if old_language != current_language:
                        logger.info(f"Language changed from {old_language} to {current_language}, reloading RAG game config")
                        self.assistant_ctrl.rag_integration.reload_for_language_change()
                else:
                    # 如果没有记录之前的语言，直接重新加载
                    logger.info(f"Reloading RAG game config for language: {current_language}")
                    self.assistant_ctrl.rag_integration.reload_for_language_change()
            
            # Update tray icon text
            if self.tray_icon:
                self.tray_icon.update_text()
            
            # Re-register hotkey
            if self.hotkey_mgr:
                logger.info("Re-registering hotkey...")
                self.hotkey_mgr.unregister()
                self.hotkey_mgr.register()
                
                # 只在没有进行模式切换时显示热键更新通知，避免重复通知
                if self.tray_icon and not mode_switched:
                    self.tray_icon.show_notification(
                        t("settings_applied"),
                        t("hotkey_updated", hotkey=self.hotkey_mgr.get_hotkey_string())
                    )
                    
            # Reinitialize RAG components with new API keys (only if not in limited mode)
            if self.assistant_ctrl and not new_limited_mode:
                logger.info("Reinitializing RAG components with new API keys...")
                # Reinitialize RAG integration
                self.assistant_ctrl.rag_integration._init_ai_components()
            
            # Refresh shortcuts in the main window
            if self.assistant_ctrl:
                logger.info("Refreshing shortcuts in main window...")
                self.assistant_ctrl.refresh_shortcuts()
                
        except Exception as e:
            logger.error(f"Failed to apply settings: {e}")
            QMessageBox.warning(
                None,
                t("warning"),
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
                # 优化流程：先快速显示窗口，再异步初始化RAG引擎
                # 1. 先记录游戏窗口但不立即初始化RAG
                self.assistant_ctrl.current_game_window = game_window_title
                logger.info(f"🎮 记录游戏窗口: '{game_window_title}'")
                
                # 2. 立即显示聊天窗口（无需等待RAG初始化）
                self.assistant_ctrl.expand_to_chat()
                logger.info("expand_to_chat()执行成功")
                
                # 3. 窗口显示后，异步初始化RAG引擎
                QTimer.singleShot(100, lambda: self.assistant_ctrl.set_current_game_window(game_window_title))
                logger.info("RAG引擎初始化已安排为异步任务")
                
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