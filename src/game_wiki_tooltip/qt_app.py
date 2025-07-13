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
from PyQt6.QtCore import QTimer, pyqtSignal, QObject, pyqtSlot
from PyQt6.QtGui import QIcon

from src.game_wiki_tooltip.config import SettingsManager, GameConfigManager
from src.game_wiki_tooltip.qt_tray_icon import QtTrayIcon
from src.game_wiki_tooltip.qt_settings_window import QtSettingsWindow
from src.game_wiki_tooltip.qt_hotkey_manager import QtHotkeyManager, HotkeyError
from src.game_wiki_tooltip.assistant_integration import IntegratedAssistantController
from src.game_wiki_tooltip.utils import APPDATA_DIR, package_file

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
        self.message_timer = None  # 用于主线程消息监听
        
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
            
            # Initialize hotkey manager
            self.hotkey_mgr = QtHotkeyManager(self.settings_mgr)
            self.hotkey_mgr.hotkey_triggered.connect(self._on_hotkey_triggered)
            logger.info("Hotkey manager signal connected")
            
            # Try to register hotkey
            try:
                self.hotkey_mgr.register()
                # Show notification
                self.tray_icon.show_notification(
                    "GameWiki Assistant",
                    f"已启动，按 {self.hotkey_mgr.get_hotkey_string()} 呼出助手"
                )
            except HotkeyError as e:
                logger.error(f"Failed to register hotkey: {e}")
                QMessageBox.warning(
                    None,
                    "热键注册失败",
                    f"无法注册热键：{e}\n\n请在设置中更换热键组合。"
                )
                
            # Start Windows message listener
            logger.info("Starting Windows message listener in main thread...")
            self.message_timer = QTimer()
            self.message_timer.timeout.connect(self._check_windows_messages)
            self.message_timer.start(10)  # Check every 10ms
            logger.info("Windows message timer started")
            
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
        """Check for Windows messages in the main thread"""
        try:
            msg = win32gui.PeekMessage(None, 0, 0, win32con.PM_REMOVE)
            if msg and msg[0]:
                if msg[1][1] == win32con.WM_HOTKEY:
                    logger.info(f"Hotkey message detected in main thread: wParam={msg[1][2]}, lParam={msg[1][3]}")
                    self.hotkey_mgr.handle_hotkey_message(msg[1])
                win32gui.TranslateMessage(msg[1])
                win32gui.DispatchMessage(msg[1])
        except Exception as e:
            logger.error(f"Error in _check_windows_messages: {e}")
            
    def _on_hotkey_triggered(self):
        """Handle hotkey trigger"""
        logger.info("Hotkey triggered! Expanding to chat window...")
        if self.assistant_ctrl:
            logger.info("Calling assistant_ctrl.expand_to_chat()")
            self.assistant_ctrl.expand_to_chat()
        else:
            logger.warning("assistant_ctrl is None, cannot expand to chat")
            
    def _quit_application(self):
        """Quit application"""
        logger.info("Quitting application...")
        
        # Stop message listener
        if self.message_timer:
            self.message_timer.stop()
            
        # Unregister hotkey
        if self.hotkey_mgr:
            self.hotkey_mgr.unregister()
            
        # Clean up tray icon
        if self.tray_icon:
            self.tray_icon.cleanup()
            
        # Quit
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