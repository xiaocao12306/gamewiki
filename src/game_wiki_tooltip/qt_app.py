"""
Main PyQt6 application entry point.
"""

import sys
import logging
import os
import argparse
import asyncio

import win32con
import win32gui

from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox
from PyQt6.QtCore import QTimer, QObject, QAbstractNativeEventFilter, Qt
from PyQt6.QtGui import QIcon

# Import qasync for event loop integration
import qasync

from src.game_wiki_tooltip.core.config import SettingsManager, GameConfigManager
from src.game_wiki_tooltip.core.backend_client import BackendClient
from src.game_wiki_tooltip.core.analytics import AnalyticsManager
from src.game_wiki_tooltip.qt_tray_icon import QtTrayIcon
from src.game_wiki_tooltip.qt_settings_window import QtSettingsWindow
from src.game_wiki_tooltip.qt_hotkey_manager import QtHotkeyManager
from src.game_wiki_tooltip.assistant_integration import IntegratedAssistantController
from src.game_wiki_tooltip.core.utils import APPDATA_DIR, package_file
from src.game_wiki_tooltip.core.i18n import init_translations, t

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

    def __init__(self, splash_screen=None, force_settings=False):
        super().__init__()

        # Store splash screen reference
        self.splash_screen = splash_screen
        self.force_settings = force_settings
        
        # Get existing QApplication instance
        self.app = QApplication.instance()
        if self.app is None:
            # This should not happen as QApplication is created in main()
            logger.error("QApplication instance not found!")
            self.app = QApplication(sys.argv)
            
        # Set application properties
        self.app.setQuitOnLastWindowClosed(False)
        # Application name already set in main()
        
        # Try to set app icon
        try:
            icon_path = package_file("app.ico")
            self.app.setWindowIcon(QIcon(str(icon_path)))
        except:
            pass
            
        # Initialize managers
        self.settings_mgr = SettingsManager(SETTINGS_PATH)
        self.backend_client = BackendClient(self.settings_mgr)
        self.remote_config = {}
        self._sync_remote_config()

        self.analytics_mgr = AnalyticsManager(self.settings_mgr)
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
        
        # Preload icon resources
        self._preload_icons()
        
        # Check command line arguments
        self.force_settings = '--settings' in sys.argv or '--config' in sys.argv
        
        # Check if first run
        self._check_first_run()

    def _sync_remote_config(self):
        """Fetch remote configuration from backend and cache locally"""
        config = self.backend_client.fetch_remote_config()
        current = self.settings_mgr.settings.remote_config or {}

        if not config:
            if current:
                logger.info("Using cached remote configuration (backend fetch unavailable)")
                self.remote_config = current
            else:
                logger.info("Remote configuration unavailable; proceeding with local defaults")
                self.remote_config = {}
            return

        if config != current:
            logger.info("Remote configuration updated from backend")
            self.settings_mgr.update({'remote_config': config})
            try:
                self.settings_mgr.save()
            except Exception as exc:
                logger.warning(f"Failed to persist remote configuration: {exc}")
        else:
            logger.info("Remote configuration matches cached version")

        self.remote_config = config

    def _preload_icons(self):
        """Preload icon resources to avoid runtime errors"""
        try:
            # Preload main app icon
            app_icon_path = package_file("app.ico")
            logger.info(f"Preloaded app icon: {app_icon_path}")
            
            # Preload other common icons from assets/icons directory
            icon_files = [
                "google.ico",
                "youtube.png", 
                "bilibili.ico",
                "reddit.ico",
                "nexusmods.ico",
                "instagram.png"
            ]
            
            for icon_file in icon_files:
                try:
                    icon_path = package_file(f"icons/{icon_file}")
                    if icon_path.exists():
                        logger.debug(f"Preloaded icon: {icon_path}")
                    else:
                        logger.warning(f"Icon not found: {icon_path}")
                except Exception as e:
                    logger.warning(f"Failed to preload icon {icon_file}: {e}")
                    
            logger.info("Icon preloading completed")
            
        except Exception as e:
            logger.error(f"Failed to preload icons: {e}")
            # Don't fail the app initialization if icon preloading fails
        
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
            # 延迟到启动流程完成并关闭启动页后再弹出设置窗口
            self.need_show_settings_after_splash = True
            self._initialize_components(limited_mode=not has_api_key)
            return

        # 没有 Gemini Key 时默认运行在“云端代理模式”，不再弹出提示
        if not has_api_key:
            logger.info("Gemini API Key 未配置，将使用云端模型代理模式启动")
            self.need_show_settings_after_splash = False
            self._initialize_components(limited_mode=True)
            return

        logger.info("Detected Gemini API Key, enabling本地 RAG 功能")
        self.need_show_settings_after_splash = False
        self._initialize_components(limited_mode=False)
            
    def _initialize_components(self, limited_mode=False):
        """Initialize all components"""
        try:
            # Initialize audio devices on startup (non-blocking)
            try:
                from src.game_wiki_tooltip.window_component.voice_recognition import initialize_audio_devices
                import threading
                
                # Pass settings manager to audio init
                settings_mgr = self.settings_mgr
                
                def safe_audio_init():
                    """Wrapper to ensure audio init doesn't crash the thread"""
                    try:
                        initialize_audio_devices(settings_manager=settings_mgr)
                    except Exception as e:
                        logger.error(f"Audio device initialization failed in thread: {e}")
                        import traceback
                        logger.debug(f"Audio init thread traceback: {traceback.format_exc()}")
                
                # Run audio device initialization in background thread to avoid blocking
                audio_init_thread = threading.Thread(target=safe_audio_init, daemon=True, name="AudioInit")
                audio_init_thread.start()
                logger.info("Started audio device initialization in background")
            except Exception as e:
                logger.warning(f"Failed to start audio device initialization: {e}")
                # Continue without audio device initialization
            
            # Ensure cleanup of existing assistant controller before initializing new one
            if hasattr(self, 'assistant_ctrl') and self.assistant_ctrl:
                logger.info("Detected existing assistant controller, cleaning up first...")
                
                
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
            self.assistant_ctrl = IntegratedAssistantController(
                self.settings_mgr,
                self.backend_client,
                analytics_mgr=self.analytics_mgr,
                limited_mode=limited_mode,
            )
            
            # Set callback for settings window request from chat window
            self.assistant_ctrl.set_settings_window_callback(self._show_settings)
            
            # Initialize tray icon
            self.tray_icon = QtTrayIcon()
            self.tray_icon.settings_requested.connect(self._show_settings)
            self.tray_icon.exit_requested.connect(self._quit_application)
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
                    
                    if limited_mode:
                        # 云端代理模式提示
                        notification_msg = (
                            f"{t('hotkey_registered', hotkey=hotkey_string)}\n"
                            f"Running in cloud proxy mode — Wiki search + remote chat via backend."
                        )
                    else:
                        # 完整功能模式的通知
                        notification_msg = f"{t('hotkey_registered', hotkey=hotkey_string)}"
                    
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
            
            # Connect AI loading completion signal
            if hasattr(self.assistant_ctrl, '_on_ai_modules_loaded'):
                # Find the AI loader if it exists
                if hasattr(self.assistant_ctrl, '_ai_loader') and self.assistant_ctrl._ai_loader:
                    # Disconnect any existing connections to prevent duplicates
                    try:
                        self.assistant_ctrl._ai_loader.load_completed.disconnect()
                    except:
                        pass  # No existing connection, which is fine
                    
                    self.assistant_ctrl._ai_loader.load_completed.connect(
                        lambda success: self._on_ai_ready(success)
                    )
                    logger.info("Connected to existing AI loader signal")
                else:
                    # If AI loader hasn't started yet, wait for it
                    def check_ai_loader():
                        if hasattr(self.assistant_ctrl, '_ai_loader') and self.assistant_ctrl._ai_loader:
                            # Disconnect any existing connections to prevent duplicates
                            try:
                                self.assistant_ctrl._ai_loader.load_completed.disconnect()
                            except:
                                pass  # No existing connection, which is fine
                                
                            self.assistant_ctrl._ai_loader.load_completed.connect(
                                lambda success: self._on_ai_ready(success)
                            )
                            logger.info("Connected to AI loader signal after delay")
                        else:
                            # If still no loader, show UI anyway after timeout
                            QTimer.singleShot(1000, self._show_ui_fallback)
                    QTimer.singleShot(200, check_ai_loader)
            else:
                # No AI loading support, show UI immediately
                QTimer.singleShot(100, self._precreate_chat_window)
            
            logger.info(f"Component initialization completed successfully (limited_mode={limited_mode})")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            QMessageBox.critical(
                None,
                t("error"),
                f"程序初始化失败：{e}\n\n程序将退出。"
            )
            sys.exit(1)
            
    def _precreate_chat_window(self):
        """Pre-create chat window"""
        try:
            logger.info("Starting chat window pre-creation...")
            
            # Check if assistant controller supports pre-creation
            if hasattr(self.assistant_ctrl, 'precreate_chat_window'):
                self.assistant_ctrl.precreate_chat_window()
                logger.info("✅ f")
            else:
                # Fallback: Try to create and immediately hide the window
                logger.info("Using fallback pre-creation method")
                if hasattr(self.assistant_ctrl, 'main_window') and not self.assistant_ctrl.main_window:
                    # Temporarily create and hide the window
                    from src.game_wiki_tooltip.window_component.unified_window import UnifiedAssistantWindow
                    self.assistant_ctrl.main_window = UnifiedAssistantWindow(self.settings_mgr)
                    
                    # Connect signals
                    self.assistant_ctrl.main_window.query_submitted.connect(self.assistant_ctrl.handle_query)
                    self.assistant_ctrl.main_window.wiki_page_found.connect(self.assistant_ctrl.handle_wiki_page_found)
                    
                    # Connect stop generation signal if handler exists
                    if hasattr(self.assistant_ctrl, 'handle_stop_generation'):
                        self.assistant_ctrl.main_window.stop_generation_requested.connect(
                            self.assistant_ctrl.handle_stop_generation
                        )
                        logger.info("✅ Connected stop_generation_requested signal in fallback method")
                    
                    self.assistant_ctrl.main_window.hide()
                    logger.info("✅ Chat window pre-created via fallback method")
                    
        except Exception as e:
            logger.warning(f"Failed to pre-create chat window: {e}")
            # Not critical, just means first hotkey will be slower
        
        # Close splash screen after pre-creation
        if self.splash_screen:
            logger.info("Scheduling splash screen closure")
            QTimer.singleShot(100, self._close_splash_screen)
            
    def _close_splash_screen(self):
        """Close splash screen"""
        if self.splash_screen:
            logger.info("Closing splash screen after mini window displayed")
            self.splash_screen.close_and_cleanup()
            self.splash_screen = None
            
        # Now that splash is closed, show settings if needed
        if hasattr(self, 'need_show_settings_after_splash') and self.need_show_settings_after_splash:
            logger.info("Auto-opening settings window after splash screen closed")
            self.need_show_settings_after_splash = False
            QTimer.singleShot(200, lambda: self._show_settings(initial_setup=True))
            
    def _on_ai_ready(self, success: bool):
        """Called when AI modules are loaded"""
        if success:
            logger.info("✅ AI modules loaded successfully, showing UI")
        else:
            logger.warning("⚠️ AI modules loading failed, showing UI anyway")
        
        # Pre-create chat window and show mini assistant
        self._precreate_chat_window()
        
    def _show_ui_fallback(self):
        """Fallback to show UI if AI loading signal wasn't connected"""
        logger.info("⏱️ AI loading timeout, showing UI as fallback")
        self._precreate_chat_window()
            
    def _show_settings(self, initial_setup=False):
        """Show settings window"""
        if self.settings_window is None:
            self.settings_window = QtSettingsWindow(self.settings_mgr)
            self.settings_window.settings_applied.connect(self._on_settings_applied)
            
            # 移除initial_setup处理逻辑，因为现在不会因为没有API key而强制退出
        
        # Ensure window has correct size before showing
        self.settings_window.resize(600, 500)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
        
        # Force proper size after showing
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        if self.settings_window.size().width() < 600 or self.settings_window.size().height() < 500:
            self.settings_window.resize(600, 500)
            
    def _on_settings_applied(self):
        """Handle settings applied"""
        try:
            logger.info("Settings applied, checking component initialization status")
            settings = self.settings_mgr.get()
            api_config = settings.get('api', {})
            gemini_api_key = (
                api_config.get('gemini_api_key') or 
                os.getenv('GEMINI_API_KEY') or 
                os.getenv('GOOGLE_API_KEY')
            )
            has_api_key = bool(gemini_api_key)
            
            # Check if components are already initialized
            if not hasattr(self, 'assistant_ctrl') or self.assistant_ctrl is None:
                logger.info("Components not initialized yet, initializing now...")
                self._initialize_components(limited_mode=not has_api_key)
                return
            
            logger.info("Components already initialized, updating settings...")
            
            # Update RAG system language settings when settings are applied
            if hasattr(self.assistant_ctrl, 'rag_integration') and self.assistant_ctrl.rag_integration:
                logger.info("🌐 Updating RAG system language settings...")
                self.assistant_ctrl.rag_integration.reload_for_language_change()
            
            # 检查当前API key配置，决定是否需要切换模式
            dont_remind = settings.get('dont_remind_api_missing', False)
            
            # 检查是否需要切换模式
            current_limited_mode = getattr(self.assistant_ctrl, 'limited_mode', True)
            new_limited_mode = not has_api_key
            
            logger.info(f"Mode check: current limited mode={current_limited_mode}, new limited mode={new_limited_mode}")
            logger.info(f"API key status: Gemini={'✓' if gemini_api_key else '✗'}")
            
            # Check if API key missing dialog should be shown (only when switching from full to limited mode)
            show_api_dialog = False
                    
            if current_limited_mode != new_limited_mode:
                # Mode switch required, reinitialize components
                logger.info(f"Mode switch: {current_limited_mode} -> {new_limited_mode}")
                
                # Clean up existing components (add proper cleanup logic)
                if hasattr(self, 'assistant_ctrl') and self.assistant_ctrl:
                    logger.info("Cleaning up old assistant controller...")
                    
                    # Clean up mini window
                    
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
                
                # Reinitialize components (slight delay to ensure old window_component are fully cleaned)
                QTimer.singleShot(100, lambda: self._initialize_components(limited_mode=new_limited_mode))
                
                # Show mode switch notification (but don't repeat hotkey notification)
                mode_switched = True  # Mark that mode switch has occurred
                if self.tray_icon:
                    if new_limited_mode:
                        self.tray_icon.show_notification(
                            "GameWiki Assistant",
                            "Switched to cloud proxy mode\n\nWiki search + remote chat via backend are available."
                        )
                    else:
                        self.tray_icon.show_notification(
                            "GameWiki Assistant",
                            "Switched to full functionality mode\n\nLocal RAG enhancements re-enabled."
                        )
                
                logger.info("Mode switch completed")
                return
            
            # If no mode switch needed, continue with original settings update logic
            mode_switched = False  # No mode switch occurred
            
            # Update translation manager with new language
            current_language = settings.get('language', 'en')
            from src.game_wiki_tooltip.core.i18n import set_language
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
        """Handle hotkey trigger using SmartInteractionManager"""
        logger.info("=== HOTKEY TRIGGERED ===")
        
        if not self.assistant_ctrl:
            logger.warning("assistant_ctrl is None, cannot process hotkey")
            return
        
        try:
            # Use smart interaction manager to handle hotkey
            is_visible = self.assistant_ctrl.main_window and self.assistant_ctrl.main_window.isVisible()
            self.assistant_ctrl.handle_smart_hotkey(is_visible)
            logger.info("=== Hotkey processing completed ===")
        except Exception as e:
            logger.error(f"Error in hotkey handler: {e}")
            import traceback
            traceback.print_exc()
    
            
    def _quit_application(self):
        """Quit application"""
        logger.info("Quitting application...")
        
        # Clean up assistant controller and its window_component first
        if hasattr(self, 'assistant_ctrl') and self.assistant_ctrl:
            logger.info("Cleaning up assistant controller and related window_component...")
            
            
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
            
        # 停止埋点
        if hasattr(self, 'analytics_mgr') and self.analytics_mgr:
            try:
                self.analytics_mgr.shutdown()
            except Exception as exc:
                logger.warning(f"AnalyticsManager shutdown failed: {exc}")

        if hasattr(self, 'backend_client') and self.backend_client:
            try:
                self.backend_client.close()
            except Exception as exc:
                logger.warning(f"BackendClient shutdown failed: {exc}")

        # Quit
        logger.info("Application exiting...")
        self.app.quit()
        
    def run(self):
        """Run the application"""
        return self.app.exec()


def run_main_app(qapp, splash_screen=None):
    """Run the main application with provided QApplication and splash screen"""
    # Step 3: Continue with other initialization (while splash is visible)
    # Suppress warnings
    try:
        from src.game_wiki_tooltip.preloader import suppress_warnings
        suppress_warnings()
    except:
        pass
    
    # Initialize logging

    # Apply graphics fixes
    logger.info("Applying PyQt6 Windows graphics compatibility fixes...")
    from src.game_wiki_tooltip.core.graphics_compatibility import (
        apply_windows_10_fixes, get_graphics_debug_info,
        set_qt_attributes_before_app_creation, GraphicsMode
    )
    apply_windows_10_fixes()
    
    # Log debug info
    debug_info = get_graphics_debug_info()
    logger.info(f"Graphics configuration: {debug_info}")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='GameWiki Assistant')
    parser.add_argument('--settings', '--config', action='store_true', 
                       help='Force show settings window even if API keys are configured')
    args = parser.parse_args()
    
    if args.settings:
        logger.info("Settings window will be forced to show")
    
    # Set remaining Qt attributes
    try:
        set_qt_attributes_before_app_creation(GraphicsMode.AUTO)
        logger.info("Qt application attributes set successfully")
    except Exception as e:
        logger.error(f"Failed to set Qt application attributes: {e}")
    
    # Set up qasync event loop integration
    loop = qasync.QEventLoop(qapp)
    asyncio.set_event_loop(loop)
    
    # Create main application (pass splash screen reference)
    app = GameWikiApp(splash_screen=splash_screen, force_settings=args.settings)
    
    # Run application with qasync loop
    with loop:
        sys.exit(app.run())

def main():
    import sys
    """Main entry point"""
    if sys.platform != "win32":
        raise RuntimeError("This tool only works on Windows.")
    
    # Step 1: Minimal Qt setup for splash screen
    # Set critical Qt attributes before QApplication
    try:
        from PyQt6.QtCore import Qt
    except:
        pass
    
    # Create QApplication instance immediately
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("GameWiki Assistant")
    
    # Configure tooltip behavior - remove delays
    try:
        from PyQt6.QtWidgets import QStyle
        # Remove tooltip delays - show immediately on hover
        qapp.setStyleSheet(qapp.styleSheet() + """
            QToolTip {
                padding: 5px;
                border: 1px solid #333;
                background-color: #2b2b2b;
                color: white;
                border-radius: 3px;
            }
        """)
        # Note: Style hints for tooltip delays are not directly settable in Qt6
        # The WA_AlwaysShowToolTips attribute on widgets is the primary solution
    except Exception as e:
        pass  # Non-critical, continue without tooltip configuration
    
    # Step 2: Show splash screen IMMEDIATELY
    splash = None
    try:
        from src.game_wiki_tooltip.splash_screen import SplashScreen
        
        # Show normal splash screen for all cases (OneDir mode doesn't need special first-run handling)
        splash = SplashScreen()
        splash.show()
        qapp.processEvents()
            
    except Exception as e:
        print(f"Failed to show splash screen: {e}")
    
    # Run the main app
    run_main_app(qapp, splash)


if __name__ == "__main__":
    main() 
