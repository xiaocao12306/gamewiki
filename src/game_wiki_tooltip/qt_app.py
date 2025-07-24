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
from src.game_wiki_tooltip.graphics_compatibility import apply_windows_10_fixes, set_application_attributes, get_graphics_debug_info, set_qt_attributes_before_app_creation

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
    """Custom dialog for handling API key missing notifications"""
    
    def __init__(self, missing_keys, parent=None):
        super().__init__(parent)
        self.missing_keys = missing_keys
        self.dont_remind = False
        self.open_settings = False
        self._init_ui()
        
    def _init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("GameWiki Assistant")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.setFixedSize(400, 220)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Title
        title_label = QLabel("AI Features Unavailable")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #d32f2f;")
        layout.addWidget(title_label)
        
        # Message content
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
        
        # "Don't remind me again" checkbox
        self.dont_remind_checkbox = QCheckBox("Don't remind me again (Wiki search only)")
        self.dont_remind_checkbox.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.dont_remind_checkbox)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Configure button
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
        
        # Later button
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
        logger.info("WindowsHotkeyFilter initialization completed")
    
    def nativeEventFilter(self, eventType, message):
        """Filter Windows native messages"""
        try:
            # Check if it's a Windows message
            if eventType == b"windows_generic_MSG":
                # Convert message to readable format
                msg_ptr = int(message)
                import ctypes
                from ctypes import wintypes
                
                # Define MSG structure
                class MSG(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", wintypes.HWND),
                        ("message", wintypes.UINT),
                        ("wParam", wintypes.WPARAM),
                        ("lParam", wintypes.LPARAM),
                        ("time", wintypes.DWORD),
                        ("pt", wintypes.POINT)
                    ]
                
                # Get message content
                msg = MSG.from_address(msg_ptr)
                
                # Check if it's a hotkey message
                if msg.message == win32con.WM_HOTKEY:
                    logger.info(f"📨 Native event filter received hotkey message: wParam={msg.wParam}, lParam={msg.lParam}")
                    
                    # Call hotkey handler function
                    if self.hotkey_handler:
                        self.hotkey_handler(msg.wParam, msg.lParam, "Native Event Filter")
                    
                    # Return True to indicate message was handled
                    return True, 0
                    
        except Exception as e:
            logger.error(f"Native event filter error: {e}")
        
        # Return False to indicate message was not handled, continue passing
        return False, 0


class GameWikiApp(QObject):
    """Main application controller"""
    
    def __init__(self):
        super().__init__()
        
        # Create QApplication first
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication(sys.argv)
            logger.info("QApplication created successfully with graphics compatibility attributes")
            
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
        self.message_timer = None  # For main thread message monitoring (backup)
        self.hotkey_triggered_count = 0  # Hotkey trigger counter
        self.native_filter = None  # Windows native event filter
        
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
        
        # No longer need separate Jina API key, Gemini is used for both LLM and embeddings
        
        # Debug information
        logger.info(f"API Key Detection:")
        logger.info(f"  - settings.json Gemini API key: {'***found***' if api_config.get('gemini_api_key') else 'not found'}")
        logger.info(f"  - Environment GEMINI_API_KEY: {'***found***' if os.getenv('GEMINI_API_KEY') else 'not found'}")
        logger.info(f"  - Environment GOOGLE_API_KEY: {'***found***' if os.getenv('GOOGLE_API_KEY') else 'not found'}")
        logger.info(f"  - Final Gemini API key: {'***found***' if gemini_api_key else 'not found'}")
        
        # 检查API key是否可用
        has_api_key = bool(gemini_api_key)
        dont_remind = settings.get('dont_remind_api_missing', False)
        logger.info(f"  - API key available: {has_api_key}")
        logger.info(f"  - Don't remind API missing: {dont_remind}")
        
        # 修改逻辑：强制显示设置窗口的情况
        if self.force_settings:
            logger.info("Settings window forced by command line argument")
            self._show_settings(initial_setup=False)
        elif not has_api_key:
            # 没有API key时，显示信息但不强制退出
            logger.info("Missing Gemini API Key, starting in limited mode")
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
            # Ensure cleanup of existing assistant controller before initializing new one
            if hasattr(self, 'assistant_ctrl') and self.assistant_ctrl:
                logger.info("Detected existing assistant controller, cleaning up first...")
                
                # Clean up mini window
                if hasattr(self.assistant_ctrl, 'mini_window') and self.assistant_ctrl.mini_window:
                    try:
                        logger.info("Cleaning up existing mini window...")
                        self.assistant_ctrl.mini_window.hide()
                        self.assistant_ctrl.mini_window.close()
                        self.assistant_ctrl.mini_window.deleteLater()
                        self.assistant_ctrl.mini_window = None
                    except Exception as e:
                        logger.warning(f"Error cleaning up existing mini window: {e}")
                        self.assistant_ctrl.mini_window = None
                
                # Clean up main window
                if hasattr(self.assistant_ctrl, 'main_window') and self.assistant_ctrl.main_window:
                    try:
                        logger.info("Cleaning up existing main window...")
                        self.assistant_ctrl.main_window.hide()
                        self.assistant_ctrl.main_window.close()
                        self.assistant_ctrl.main_window.deleteLater()
                        self.assistant_ctrl.main_window = None
                    except Exception as e:
                        logger.warning(f"Error cleaning up existing main window: {e}")
                        self.assistant_ctrl.main_window = None
                
                # Disconnect signal connections
                try:
                    if hasattr(self.assistant_ctrl, 'rag_integration'):
                        self.assistant_ctrl.rag_integration.disconnect()
                except Exception as e:
                    logger.warning(f"Error disconnecting old RAG integration signals: {e}")
                
                self.assistant_ctrl = None
                logger.info("Existing assistant controller cleanup completed")
            
            # Initialize assistant controller with limited mode flag
            self.assistant_ctrl = IntegratedAssistantController(self.settings_mgr, limited_mode=limited_mode)
            
            # Connect visibility change handler
            self.assistant_ctrl.visibility_changed = self._on_assistant_visibility_changed
            
            # Initialize tray icon
            self.tray_icon = QtTrayIcon()
            self.tray_icon.settings_requested.connect(self._show_settings)
            self.tray_icon.exit_requested.connect(self._quit_application)
            self.tray_icon.toggle_visibility_requested.connect(self._toggle_assistant_visibility)
            self.tray_icon.show()
            
            # Initialize hotkey manager with ultra-compatible mode
            self.hotkey_mgr = QtHotkeyManager(self.settings_mgr)
            self.hotkey_mgr.hotkey_triggered.connect(self._on_hotkey_triggered)
            logger.info("Hotkey manager signal connected")
            
            # Try to register hotkey with enhanced conflict resolution
            try:
                self.hotkey_mgr.register()
                
                if self.hotkey_mgr.is_registered():
                    # Show success notification
                    hotkey_string = self.hotkey_mgr.get_hotkey_string()
                    registration_info = self.hotkey_mgr.get_registration_info()
                    
                    mode_text = "Ultra Compatible Mode"
                    
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
                    logger.info(f"Hotkey registration successful: {hotkey_string} (mode=ultra_compatible, limited_mode={limited_mode})")
                else:
                    # Show warning but continue
                    self.tray_icon.show_notification(
                        "GameWiki Assistant",
                        t("hotkey_failed")
                    )
                    logger.warning("Hotkey registration failed, but application continues running")
                    
            except Exception as e:
                logger.error(f"Failed to register hotkey: {e}")
                # Don't show error dialog, just log and continue
                self.tray_icon.show_notification(
                    "GameWiki Assistant",
                    t("hotkey_failed")
                )
                
            # Install Windows native event filter (primary solution)
            logger.info("Installing Windows native event filter...")
            self.native_filter = WindowsHotkeyFilter(self._handle_hotkey_message_direct)
            self.app.installNativeEventFilter(self.native_filter)
            logger.info("Windows native event filter installation completed")
            
            # Start Windows message listener as backup
            logger.info("Starting Windows message listener (backup solution)...")
            self.message_timer = QTimer()
            self.message_timer.timeout.connect(self._check_windows_messages)
            self.message_timer.start(50)  # Check every 50ms as backup
            logger.info("Windows message listener started (backup)")
            
            # Show mini assistant (delayed display to ensure cleanup operations complete)
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
        
    def _toggle_assistant_visibility(self):
        """Toggle assistant window visibility"""
        if self.assistant_ctrl:
            self.assistant_ctrl.toggle_visibility()
            # Update tray icon menu text
            is_visible = self.assistant_ctrl.is_visible()
            self.tray_icon.update_toggle_text(is_visible)
        
    def _on_initial_setup_closed(self):
        """Handle initial setup window closed - deprecated, kept for compatibility"""
        # 这个方法现在不再使用，因为我们不再强制要求API key
        # 保留是为了兼容性，但实际上不会被调用
        pass
        
    def _on_assistant_visibility_changed(self, is_visible):
        """Handle assistant visibility change to update tray icon"""
        if self.tray_icon:
            self.tray_icon.update_toggle_text(is_visible)
            
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
            
            # No longer need separate Jina API key
            
            # 检查是否有API key
            has_api_key = bool(gemini_api_key)
            dont_remind = settings.get('dont_remind_api_missing', False)
            
            # 检查是否需要切换模式
            current_limited_mode = getattr(self.assistant_ctrl, 'limited_mode', True)
            new_limited_mode = not has_api_key
            
            logger.info(f"Mode check: current limited mode={current_limited_mode}, new limited mode={new_limited_mode}")
            logger.info(f"API key status: Gemini={'✓' if gemini_api_key else '✗'}")
            
            # Check if API key missing dialog should be shown (only when switching from full to limited mode)
            show_api_dialog = (new_limited_mode and not current_limited_mode and not dont_remind)
            
            if show_api_dialog:
                missing_keys = []
                if not gemini_api_key:
                    missing_keys.append("Gemini API Key")
                # Only need Gemini API key now
                
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
                # Mode switch required, reinitialize components
                logger.info(f"Mode switch: {current_limited_mode} -> {new_limited_mode}")
                
                # Clean up existing components (add proper cleanup logic)
                if hasattr(self, 'assistant_ctrl') and self.assistant_ctrl:
                    logger.info("Cleaning up old assistant controller...")
                    
                    # Clean up mini window
                    if hasattr(self.assistant_ctrl, 'mini_window') and self.assistant_ctrl.mini_window:
                        try:
                            logger.info("Cleaning up old mini window...")
                            self.assistant_ctrl.mini_window.hide()
                            self.assistant_ctrl.mini_window.close()
                            self.assistant_ctrl.mini_window.deleteLater()
                            self.assistant_ctrl.mini_window = None
                            logger.info("Old mini window cleaned up")
                        except Exception as e:
                            logger.warning(f"Error cleaning up old mini window: {e}")
                            self.assistant_ctrl.mini_window = None
                    
                    # Clean up main window
                    if hasattr(self.assistant_ctrl, 'main_window') and self.assistant_ctrl.main_window:
                        try:
                            logger.info("Cleaning up old main window...")
                            self.assistant_ctrl.main_window.hide()
                            self.assistant_ctrl.main_window.close()
                            self.assistant_ctrl.main_window.deleteLater()
                            self.assistant_ctrl.main_window = None
                            logger.info("Old main window cleaned up")
                        except Exception as e:
                            logger.warning(f"Error cleaning up old main window: {e}")
                            self.assistant_ctrl.main_window = None
                    
                    # Disconnect signal connections to avoid memory leaks
                    try:
                        if hasattr(self.assistant_ctrl, 'rag_integration'):
                            self.assistant_ctrl.rag_integration.disconnect()
                    except Exception as e:
                        logger.warning(f"Error disconnecting RAG integration signals: {e}")
                    
                    # Clean up assistant_ctrl reference
                    self.assistant_ctrl = None
                    logger.info("Old assistant controller cleaned up")
                
                # Reinitialize components (slight delay to ensure old windows are fully cleaned)
                QTimer.singleShot(100, lambda: self._initialize_components(limited_mode=new_limited_mode))
                
                # Show mode switch notification (but don't repeat hotkey notification)
                mode_switched = True  # Mark that mode switch has occurred
                if self.tray_icon:
                    if new_limited_mode:
                        missing_keys = []
                        if not gemini_api_key:
                            missing_keys.append("Gemini API Key")
                        # Only need Gemini API key now
                        
                        self.tray_icon.show_notification(
                            "GameWiki Assistant",
                            f"Switched to limited mode\n\nOnly Wiki search is available\n\nMissing API keys: {', '.join(missing_keys)}\nConfigure complete API keys for full functionality"
                        )
                    else:
                        self.tray_icon.show_notification(
                            "GameWiki Assistant",
                            "Switched to full functionality mode\n\nWiki search and AI guide features are now available\n\nComplete API key configuration detected"
                        )
                
                logger.info("Mode switch completed")
                return
            
            # If no mode switch needed, continue with original settings update logic
            mode_switched = False  # No mode switch occurred
            
            # Update translation manager with new language
            current_language = settings.get('language', 'en')
            from src.game_wiki_tooltip.i18n import set_language
            set_language(current_language)
            
            # Reload games configuration (for language change or wiki URL updates)
            if self.game_cfg_mgr:
                logger.info(f"Reloading games configuration for language: {current_language}")
                self.game_cfg_mgr.reload_for_language(current_language)
                
            # Reload RAG integration game config (when language changes or wiki URL updates)
            if self.assistant_ctrl and hasattr(self.assistant_ctrl, 'rag_integration'):
                # Always reload game config to pick up any wiki URL changes
                logger.info(f"Reloading RAG game config (language: {current_language})")
                self.assistant_ctrl.rag_integration.reload_for_language_change()
            
            # Update tray icon text
            if self.tray_icon:
                self.tray_icon.update_text()
            
            # Re-register hotkey
            if self.hotkey_mgr:
                logger.info("Re-registering hotkey...")
                self.hotkey_mgr.unregister()
                self.hotkey_mgr.register()
                
                # Only show hotkey update notification if no mode switch occurred, to avoid duplicate notifications
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
        """Check for Windows messages in the main thread - backup solution (using test_hotkey_only.py's successful logic)"""
        try:
            # Use the same message checking logic as test_hotkey_only.py
            msg = win32gui.PeekMessage(None, 0, 0, win32con.PM_REMOVE)
            
            if msg and msg[0]:
                # Check if it's a hotkey message - exactly the same as test_hotkey_only.py
                if msg[1][1] == win32con.WM_HOTKEY:
                    wParam = msg[1][2]
                    lParam = msg[1][3]
                    
                    logger.info(f"📨 [Backup] Received hotkey message: wParam={wParam}, lParam={lParam}")
                    logger.info(f"   Message details: {msg[1]}")
                    
                    # Use test_hotkey_only.py's hotkey handling logic
                    self._handle_hotkey_message_direct(wParam, lParam, "Backup")
                
                # Process message
                win32gui.TranslateMessage(msg[1])
                win32gui.DispatchMessage(msg[1])
        except Exception as e:
            logger.error(f"Error in _check_windows_messages: {e}")
    
    def _handle_hotkey_message_direct(self, wParam, lParam, source="Unknown"):
        """Directly handle hotkey messages - dynamically match configured hotkey"""
        logger.info(f"🎯 Processing hotkey message [{source}]: wParam={wParam}, lParam={lParam}")
        
        if wParam == HOTKEY_ID:
            # Parse lParam
            modifiers = lParam & 0xFFFF
            vk = (lParam >> 16) & 0xFFFF
            
            # Get expected hotkey configuration from settings
            settings = self.settings_mgr.get()
            hotkey_settings = settings.get('hotkey', {})
            expected_modifiers_list = hotkey_settings.get('modifiers', ['Ctrl'])
            expected_key = hotkey_settings.get('key', 'X')
            
            # Calculate expected modifier values
            expected_modifiers = 0
            mod_map = {
                "Alt": 0x0001,    # MOD_ALT
                "Ctrl": 0x0002,   # MOD_CONTROL
                "Shift": 0x0004,  # MOD_SHIFT
                "Win": 0x0008     # MOD_WIN
            }
            for mod in expected_modifiers_list:
                if mod in mod_map:
                    expected_modifiers |= mod_map[mod]
            
            # Calculate expected virtual key value
            expected_vk = ord(expected_key.upper()) if len(expected_key) == 1 and expected_key.isalpha() else VK_X
            
            logger.info(f"   Modifiers: {modifiers:#x} (expected: {expected_modifiers:#x})")
            logger.info(f"   Virtual key: {vk:#x} (expected: {expected_vk:#x})")
            logger.info(f"   Configured hotkey: {'+'.join(expected_modifiers_list + [expected_key])}")
            
            # Check if it matches the configured hotkey
            if modifiers == expected_modifiers and vk == expected_vk:
                self.hotkey_triggered_count += 1
                logger.info(f"✅ Hotkey match correct! {self.hotkey_triggered_count}th trigger, triggering hotkey event...")
                self._on_hotkey_triggered()
                return True
            else:
                logger.warning("⚠️ Hotkey match incorrect")
                return False
        else:
            logger.warning(f"⚠️ Hotkey ID mismatch: received={wParam}, expected={HOTKEY_ID}")
            return False
            
    def _on_hotkey_triggered(self):
        """Handle hotkey trigger"""
        logger.info("=== HOTKEY TRIGGERED ===")
        logger.info(f"Hotkey triggered! {self.hotkey_triggered_count}th time, preparing to expand chat window...")
        
        # Get current foreground window (game window) before showing chat window
        from src.game_wiki_tooltip.utils import get_foreground_title
        game_window_title = get_foreground_title()
        logger.info(f"🎮 Foreground window when hotkey triggered: '{game_window_title}'")
        
        if self.assistant_ctrl:
            logger.info("assistant_ctrl exists, checking window status...")
            
            # Check if chat window is already visible
            if (self.assistant_ctrl.main_window and 
                self.assistant_ctrl.main_window.isVisible()):
                logger.info("Chat window already visible, hiding window")
                # Window is visible, hide it
                self.assistant_ctrl.main_window.hide()
                self.assistant_ctrl.show_mini()
                # Update tray icon menu text
                self.tray_icon.update_toggle_text(False)
                return
            
            try:
                # Optimized flow: show window quickly first, then initialize RAG engine asynchronously
                # 1. Record game window first but don't initialize RAG immediately
                self.assistant_ctrl.current_game_window = game_window_title
                logger.info(f"🎮 Recording game window: '{game_window_title}'")
                
                # 2. Show chat window immediately (no need to wait for RAG initialization)
                self.assistant_ctrl.expand_to_chat()
                logger.info("expand_to_chat() executed successfully")
                
                # Update tray icon menu text
                self.tray_icon.update_toggle_text(True)
                
                # 3. After window is shown, initialize RAG engine asynchronously
                QTimer.singleShot(100, lambda: self.assistant_ctrl.set_current_game_window(game_window_title))
                logger.info("RAG engine initialization scheduled as async task")
                
            except Exception as e:
                logger.error(f"expand_to_chat() execution failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            logger.warning("assistant_ctrl is None, cannot expand chat window")
            
        logger.info("=== Hotkey processing completed ===")
            
    def _quit_application(self):
        """Quit application"""
        logger.info("Quitting application...")
        
        # Clean up assistant controller and its windows first
        if hasattr(self, 'assistant_ctrl') and self.assistant_ctrl:
            logger.info("Cleaning up assistant controller and related windows...")
            
            # Clean up mini window
            if hasattr(self.assistant_ctrl, 'mini_window') and self.assistant_ctrl.mini_window:
                try:
                    logger.info("Closing mini window...")
                    self.assistant_ctrl.mini_window.hide()
                    self.assistant_ctrl.mini_window.close()
                    self.assistant_ctrl.mini_window.deleteLater()
                    self.assistant_ctrl.mini_window = None
                    logger.info("Mini window closed")
                except Exception as e:
                    logger.warning(f"Error closing mini window: {e}")
                    self.assistant_ctrl.mini_window = None
            
            # Clean up main window
            if hasattr(self.assistant_ctrl, 'main_window') and self.assistant_ctrl.main_window:
                try:
                    logger.info("Closing main window...")
                    self.assistant_ctrl.main_window.hide()
                    self.assistant_ctrl.main_window.close()
                    self.assistant_ctrl.main_window.deleteLater()
                    self.assistant_ctrl.main_window = None
                    logger.info("Main window closed")
                except Exception as e:
                    logger.warning(f"Error closing main window: {e}")
                    self.assistant_ctrl.main_window = None
            
            # Stop any running workers
            if hasattr(self.assistant_ctrl, '_current_worker') and self.assistant_ctrl._current_worker:
                try:
                    logger.info("Stopping current worker thread...")
                    if self.assistant_ctrl._current_worker.isRunning():
                        self.assistant_ctrl._current_worker.stop()
                        self.assistant_ctrl._current_worker.wait()
                    logger.info("Worker thread stopped")
                except Exception as e:
                    logger.warning(f"Error stopping worker thread: {e}")
            
            # Disconnect RAG integration signals
            try:
                if hasattr(self.assistant_ctrl, 'rag_integration') and self.assistant_ctrl.rag_integration:
                    logger.info("Disconnecting RAG integration signals...")
                    self.assistant_ctrl.rag_integration.disconnect()
                    logger.info("RAG integration signals disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting RAG integration signals: {e}")
            
            self.assistant_ctrl = None
            logger.info("Assistant controller cleanup completed")
        
        # Remove native event filter
        if self.native_filter:
            logger.info("Removing Windows native event filter...")
            self.app.removeNativeEventFilter(self.native_filter)
            self.native_filter = None
            logger.info("Windows native event filter removed")
        
        # Stop message listener
        if self.message_timer:
            self.message_timer.stop()
            logger.info("Windows message listener stopped")
            
        # Unregister hotkey
        if self.hotkey_mgr:
            self.hotkey_mgr.unregister()
            logger.info("Hotkey registration cancelled")
            
        # Clean up tray icon
        if self.tray_icon:
            self.tray_icon.cleanup()
            logger.info("System tray icon cleaned up")
            
        # Quit
        logger.info("Application exiting...")
        self.app.quit()
        
    def run(self):
        """Run the application"""
        return self.app.exec()


def main():
    """Main entry point"""
    if sys.platform != "win32":
        raise RuntimeError("This tool only works on Windows.")
    
    # Apply Windows 10 PyQt6 graphics compatibility fixes BEFORE any Qt initialization
    logger.info("Applying PyQt6 Windows graphics compatibility fixes...")
    apply_windows_10_fixes()  # Auto-detects Windows version and applies appropriate fixes
    
    # Log graphics configuration for debugging
    debug_info = get_graphics_debug_info()
    logger.info(f"Graphics configuration: {debug_info}")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='GameWiki Assistant')
    parser.add_argument('--settings', '--config', action='store_true', 
                       help='Force show settings window even if API keys are configured')
    args = parser.parse_args()
    
    if args.settings:
        logger.info("Settings window will be forced to show")
    
    # Set Qt application attributes and DPI policy BEFORE creating QApplication
    # This prevents attribute and DPI policy errors
    try:
        from src.game_wiki_tooltip.graphics_compatibility import GraphicsMode
        set_qt_attributes_before_app_creation(GraphicsMode.AUTO)  # Auto-detect Windows version
        logger.info("Qt application attributes and DPI policy set successfully")
    except Exception as e:
        logger.error(f"Failed to set Qt application attributes: {e}")
        # Continue anyway, but the app might have graphics issues
        
    # Create and run app
    app = GameWikiApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main() 