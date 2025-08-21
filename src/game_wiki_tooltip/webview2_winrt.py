"""
WebView2 widget for PyQt6 using PyWinRT (WinRT projection).
This replaces the pythonnet-based implementation with pure Python + WinRT.
"""

import os
import sys
import logging
import asyncio
import ctypes
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import (
    QUrl, QTimer, pyqtSignal, QSize, Qt, QThread, QObject
)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtGui import QPalette

import win32gui
import win32con

logger = logging.getLogger(__name__)

# Initialize COM for WebView2
ole32 = ctypes.windll.ole32
ole32.CoInitialize(None)

# Lazy imports to avoid circular dependency
WINRT_AVAILABLE = False
CoreWebView2Environment = None
CoreWebView2ControllerWindowReference = None
CoreWebView2EnvironmentOptions = None
CoreWebView2PermissionKind = None
CoreWebView2PermissionState = None
Rect = None
Size = None
Point = None

def _lazy_import_webview2():
    """Lazily import WebView2 components to avoid circular imports"""
    global WINRT_AVAILABLE, CoreWebView2Environment, CoreWebView2ControllerWindowReference
    global CoreWebView2EnvironmentOptions, CoreWebView2PermissionKind, CoreWebView2PermissionState
    global Rect, Size, Point
    
    if WINRT_AVAILABLE:
        return True
    
    try:
        # Import base winrt first
        import winrt
        
        # Then import WebView2 components
        from webview2.microsoft.web.webview2.core import (
            CoreWebView2Environment as _Env,
            CoreWebView2ControllerWindowReference as _Ref,
            CoreWebView2EnvironmentOptions as _Opts,
            CoreWebView2PermissionKind as _Kind,
            CoreWebView2PermissionState as _State
        )
        
        CoreWebView2Environment = _Env
        CoreWebView2ControllerWindowReference = _Ref
        CoreWebView2EnvironmentOptions = _Opts
        CoreWebView2PermissionKind = _Kind
        CoreWebView2PermissionState = _State
        
        # Try to import Windows Foundation types
        try:
            from winrt.windows.foundation import Rect as _Rect, Size as _Size, Point as _Point
            Rect = _Rect
            Size = _Size
            Point = _Point
        except ImportError:
            # Will use fallback classes defined below
            pass
        
        WINRT_AVAILABLE = True
        logger.info("PyWinRT WebView2 packages loaded successfully")
        return True
        
    except ImportError as e:
        logger.warning(f"PyWinRT WebView2 packages not available: {e}")
        logger.warning("Install with: pip install webview2-Microsoft.Web.WebView2.Core winrt-runtime winrt-Windows.Foundation")
        return False

# Define simple replacement for Windows Foundation types
# These are used for setting bounds/size of the WebView2 control
class FallbackRect:
    """Simple rectangle class for WebView2 bounds"""
    def __init__(self, x: float = 0, y: float = 0, width: float = 0, height: float = 0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

class FallbackSize:
    """Simple size class"""
    def __init__(self, width: float = 0, height: float = 0):
        self.width = width
        self.height = height

class FallbackPoint:
    """Simple point class"""
    def __init__(self, x: float = 0, y: float = 0):
        self.x = x
        self.y = y

# We'll run everything in Qt main thread to avoid threading issues


# Removed AsyncRunner - we'll run in Qt main thread instead


class WebView2WinRTWidget(QWidget):
    """
    WebView2 widget using PyWinRT for pure Python implementation.
    Compatible with the original SimpleWebView2Widget interface.
    """
    
    # Signals matching original interface
    urlChanged = pyqtSignal(QUrl)
    loadFinished = pyqtSignal(bool)
    loadStarted = pyqtSignal()
    titleChanged = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # WebView2 objects
        self.environment = None
        self.controller = None
        self.webview = None
        self.hwnd = None
        
        # State
        self.current_url = ""
        self.current_title = ""
        self._is_initialized = False
        self._webview_initializing = False
        self._pending_navigations = []
        
        # Initialize async_runner as None (legacy compatibility)
        self.async_runner = None
        
        # Event tokens for cleanup
        self._event_tokens = {}
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Initialize UI
        self._init_ui()
        
        # Don't automatically initialize - wait for explicit call
        self._auto_initialize = False
    
    def _init_ui(self):
        """Initialize the UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Placeholder label
        self.placeholder = QLabel("WebView2 not initialized")
        self.placeholder.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #666;
                font-size: 14px;
                padding: 20px;
            }
        """)
        self.placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.placeholder)
    
    def initialize(self):
        """Start WebView2 initialization - call this after widget is created"""
        if self._is_initialized or self._webview_initializing:
            return
        
        self._webview_initializing = True
        self.placeholder.setText("Initializing WebView2...")
        
        # Try lazy import and initialize if successful
        if _lazy_import_webview2():
            # Start initialization after a short delay
            QTimer.singleShot(10, self._initialize_webview)
        else:
            self._show_error("PyWinRT WebView2 packages not installed")
            self._webview_initializing = False
    
    def _initialize_webview(self):
        """Initialize WebView2 - deferred to ensure proper context"""
        # Ensure imports are loaded
        if not _lazy_import_webview2():
            return
        
        # Force widget to create a native window
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        
        # Get HWND from Qt widget - this will create it if needed
        self.hwnd = int(self.winId())
        
        # Ensure window is native
        if not win32gui.IsWindow(self.hwnd):
            logger.error("Failed to get valid HWND")
            self._show_error("Failed to get window handle")
            self._webview_initializing = False
            return
        
        logger.info(f"Initializing WebView2 with HWND: {self.hwnd}")
        
        # Check visibility
        is_visible = win32gui.IsWindowVisible(self.hwnd)
        logger.info(f"Window visible: {is_visible}")
        
        # Defer the actual async initialization to next event loop iteration
        # This ensures we're in the Qt main thread's event loop
        QTimer.singleShot(0, self._do_async_init)
    
    def _do_async_init(self):
        """Run async initialization without blocking Qt's event loop"""
        async def init_task():
            try:
                await asyncio.wait_for(self._async_initialize(), timeout=30.0)
                # Call _on_initialized in Qt main thread
                QTimer.singleShot(0, self._on_initialized)
            except asyncio.TimeoutError:
                logger.error("WebView2 initialization timed out")
                QTimer.singleShot(0, lambda: self._show_error("WebView2 initialization timed out"))
                self._webview_initializing = False
            except Exception as e:
                logger.error(f"WebView2 initialization failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                QTimer.singleShot(0, lambda: self._show_error(f"WebView2 initialization failed: {e}"))
                self._webview_initializing = False
        
        # Run in qasync event loop - non-blocking
        asyncio.create_task(init_task())
    
    async def _async_initialize(self):
        """Async initialization of WebView2 components"""
        # Ensure Rect class is available
        global Rect
        if Rect is None:
            Rect = FallbackRect
        
        try:
            # 1. Prepare user data folder
            user_data_folder = os.path.join(
                os.environ.get('LOCALAPPDATA', ''),
                'GameWikiTooltip',
                'WebView2'
            )
            os.makedirs(user_data_folder, exist_ok=True)
            logger.info(f"User data folder: {user_data_folder}")
            
            # 2. Create CoreWebView2Environment using create_async()
            logger.info("Creating CoreWebView2Environment...")
            try:
                # Create environment with default settings
                self.environment = await CoreWebView2Environment.create_async()
                logger.info("Environment created successfully")
            except Exception as e:
                # If that fails, try alternative approaches
                logger.warning(f"Default environment creation failed: {e}")
                try:
                    # Try with just user data folder
                    self.environment = await CoreWebView2Environment.create_async(user_data_folder)
                    logger.info("Environment created with user data folder")
                except Exception as e2:
                    logger.warning(f"Failed with user data folder: {e2}")
                    # Last attempt: try with empty string for browser path and user data folder
                    try:
                        self.environment = await CoreWebView2Environment.create_async("", user_data_folder)
                        logger.info("Environment created with empty browser path and user data folder")
                    except Exception as e3:
                        logger.error(f"All environment creation attempts failed: {e3}")
                        raise
            
            # 3. Verify window handle is valid
            logger.info(f"Creating window reference for HWND: {self.hwnd}")
            
            # Check if window is valid using Win32 API
            if not win32gui.IsWindow(self.hwnd):
                raise Exception(f"Invalid window handle: {self.hwnd}")
            
            # Get window info for debugging
            try:
                window_rect = win32gui.GetWindowRect(self.hwnd)
                logger.info(f"Window rect: {window_rect}")
                is_visible = win32gui.IsWindowVisible(self.hwnd)
                logger.info(f"Window visible: {is_visible}")
                
                # Just log if not visible, don't try to force it
                # WebView2 can work with invisible windows
                if not is_visible:
                    logger.warning("Window not visible, but continuing with initialization")
                
            except Exception as e:
                logger.warning(f"Could not get window info: {e}")
            
            # Create window reference
            window_ref = CoreWebView2ControllerWindowReference.create_from_window_handle(self.hwnd)
            logger.info(f"Window reference created: {window_ref}")
            
            # Log window_ref properties for debugging
            try:
                if hasattr(window_ref, 'window_handle'):
                    logger.info(f"Window ref handle: {window_ref.window_handle}")
                if hasattr(window_ref, 'core_window'):
                    logger.info(f"Window ref core_window: {window_ref.core_window}")
                
                # Log all attributes of window_ref
                attrs = [attr for attr in dir(window_ref) if not attr.startswith('_')]
                logger.info(f"Window ref attributes: {attrs}")
            except Exception as e:
                logger.warning(f"Could not inspect window_ref: {e}")
            
            # 4. Create controller using the environment and window reference
            logger.info("Creating CoreWebView2Controller...")
            logger.info(f"Environment: {self.environment}")
            logger.info(f"Window reference type: {type(window_ref)}")
            
            # Pass window_ref directly - this is the correct way
            logger.info("Calling create_core_webview2_controller_async with window_ref")
            
            # Create controller - the timeout is handled in the caller
            self.controller = await self.environment.create_core_webview2_controller_async(window_ref)
            
            logger.info("Controller created successfully")
            
            # 5. Get CoreWebView2 from controller
            if hasattr(self.controller, 'CoreWebView2'):
                self.webview = self.controller.CoreWebView2
            elif hasattr(self.controller, 'core_web_view2'):
                self.webview = self.controller.core_web_view2
            else:
                # Try to find the webview property
                webview_attrs = [x for x in dir(self.controller) if 'webview' in x.lower() or 'web_view' in x.lower()]
                if webview_attrs:
                    self.webview = getattr(self.controller, webview_attrs[0])
                else:
                    raise AttributeError("Cannot find CoreWebView2 property on controller")
            
            logger.info("CoreWebView2 obtained from controller")
            
            # 6. Configure controller
            if hasattr(self.controller, 'IsVisible'):
                self.controller.IsVisible = True
            elif hasattr(self.controller, 'is_visible'):
                self.controller.is_visible = True
            
            self._update_bounds()
            
            # 7. Configure settings
            self._configure_settings()
            
            # 8. Setup event handlers
            self._setup_events()
            
            # Mark as initialized
            self._is_initialized = True
            
            # Hide placeholder
            QTimer.singleShot(0, self.placeholder.hide)
            
            # Process any pending navigations
            if self._pending_navigations:
                url = self._pending_navigations.pop(0)
                self.navigate(url)
            
            logger.info("WebView2 initialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"WebView2 initialization failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _configure_settings(self):
        """Configure WebView2 settings"""
        if not self.webview:
            return
        
        try:
            # Try both naming conventions
            if hasattr(self.webview, 'Settings'):
                settings = self.webview.Settings
            elif hasattr(self.webview, 'settings'):
                settings = self.webview.settings
            else:
                logger.warning("No settings property found on webview")
                return
            
            # Enable useful features (try both naming conventions)
            setting_mappings = [
                ('IsScriptEnabled', 'is_script_enabled', True),
                ('AreDefaultScriptDialogsEnabled', 'are_default_script_dialogs_enabled', True),
                ('IsWebMessageEnabled', 'is_web_message_enabled', True),
                ('AreDevToolsEnabled', 'are_dev_tools_enabled', True),
                ('IsZoomControlEnabled', 'is_zoom_control_enabled', True),
                ('IsGeneralAutofillEnabled', 'is_general_autofill_enabled', True),
                ('AreDefaultContextMenusEnabled', 'are_default_context_menus_enabled', True),
            ]
            
            for pascal_name, snake_name, value in setting_mappings:
                if hasattr(settings, pascal_name):
                    setattr(settings, pascal_name, value)
                elif hasattr(settings, snake_name):
                    setattr(settings, snake_name, value)
            
            logger.info("WebView2 settings configured")
            
        except Exception as e:
            logger.error(f"Failed to configure settings: {e}")
    
    def _setup_events(self):
        """Setup WebView2 event handlers"""
        if not self.webview:
            return
        
        try:
            # Navigation events
            token = self.webview.add_NavigationStarting(self._on_navigation_starting)
            self._event_tokens['NavigationStarting'] = token
            
            token = self.webview.add_NavigationCompleted(self._on_navigation_completed)
            self._event_tokens['NavigationCompleted'] = token
            
            token = self.webview.add_SourceChanged(self._on_source_changed)
            self._event_tokens['SourceChanged'] = token
            
            token = self.webview.add_DocumentTitleChanged(self._on_title_changed)
            self._event_tokens['DocumentTitleChanged'] = token
            
            # New window handling
            token = self.webview.add_NewWindowRequested(self._on_new_window_requested)
            self._event_tokens['NewWindowRequested'] = token
            
            logger.info("WebView2 event handlers configured")
            
        except Exception as e:
            logger.error(f"Failed to setup events: {e}")
    
    def _on_initialized(self):
        """Called when initialization is complete"""
        self.placeholder.hide()
        self._webview_initializing = False
        
        # Process pending navigations
        if self._pending_navigations:
            url = self._pending_navigations.pop(0)
            self.navigate(url)
    
    # Event handlers
    def _on_navigation_starting(self, sender, args):
        """Handle navigation starting event"""
        QTimer.singleShot(0, self.loadStarted.emit)
    
    def _on_navigation_completed(self, sender, args):
        """Handle navigation completed event"""
        success = args.IsSuccess if hasattr(args, 'IsSuccess') else True
        QTimer.singleShot(0, lambda: self.loadFinished.emit(success))
    
    def _on_source_changed(self, sender, args):
        """Handle source (URL) changed event"""
        try:
            if self.webview:
                # Get current URI
                uri = self.webview.Source
                if uri:
                    self.current_url = str(uri)
                    QTimer.singleShot(0, lambda: self.urlChanged.emit(QUrl(self.current_url)))
        except Exception as e:
            logger.error(f"Error in source changed handler: {e}")
    
    def _on_title_changed(self, sender, args):
        """Handle document title changed event"""
        try:
            if self.webview:
                title = self.webview.DocumentTitle
                if title:
                    self.current_title = str(title)
                    QTimer.singleShot(0, lambda: self.titleChanged.emit(self.current_title))
        except Exception as e:
            logger.error(f"Error in title changed handler: {e}")
    
    def _on_new_window_requested(self, sender, args):
        """Handle new window request - open in current window instead"""
        try:
            # Prevent new window
            args.Handled = True
            
            # Navigate in current window
            if args.Uri:
                self.navigate(str(args.Uri))
            
            logger.info(f"Intercepted new window request, navigating to: {args.Uri}")
            
        except Exception as e:
            logger.error(f"Error handling new window request: {e}")
    
    def _update_bounds(self):
        """Update WebView2 bounds to match widget size"""
        if not self.controller:
            return
        
        try:
            rect = self.rect()
            # Create Rect with position and size (use fallback if needed)
            rect_class = Rect if Rect is not None else FallbackRect
            bounds = rect_class(0, 0, rect.width(), rect.height())
            
            # Try both naming conventions for setting bounds
            if hasattr(self.controller, 'Bounds'):
                self.controller.Bounds = bounds
            elif hasattr(self.controller, 'bounds'):
                self.controller.bounds = bounds
            elif hasattr(self.controller, 'put_Bounds'):
                self.controller.put_Bounds(bounds)
            elif hasattr(self.controller, 'put_bounds'):
                self.controller.put_bounds(bounds)
            elif hasattr(self.controller, 'set_bounds'):
                self.controller.set_bounds(bounds)
            else:
                logger.warning("No bounds property/method found on controller")
                
            logger.debug(f"Updated bounds to {rect.width()}x{rect.height()}")
            
        except Exception as e:
            logger.error(f"Failed to update bounds: {e}")
    
    def _show_error(self, message: str):
        """Show error message in placeholder"""
        self.placeholder.setText(f"Error: {message}")
        self.placeholder.show()
    
    # Public API matching original interface
    
    def navigate(self, url: str):
        """Navigate to URL"""
        if not self._is_initialized:
            # Queue navigation for later
            self._pending_navigations.append(url)
            logger.info(f"Queued navigation to: {url}")
            return
        
        if self.webview:
            try:
                # Try both naming conventions
                if hasattr(self.webview, 'Navigate'):
                    self.webview.Navigate(url)
                elif hasattr(self.webview, 'navigate'):
                    self.webview.navigate(url)
                else:
                    logger.error("No navigate method found on webview")
                    return
                    
                self.current_url = url
                logger.info(f"Navigating to: {url}")
            except Exception as e:
                logger.error(f"Failed to navigate: {e}")
    
    def setUrl(self, url: QUrl):
        """Load URL (Qt API compatibility)"""
        self.navigate(url.toString())
    
    def load(self, url: QUrl):
        """Load URL (alias for setUrl)"""
        self.setUrl(url)
    
    def url(self) -> QUrl:
        """Get current URL"""
        return QUrl(self.current_url)
    
    def reload(self):
        """Reload current page"""
        if self.webview:
            try:
                if hasattr(self.webview, 'Reload'):
                    self.webview.Reload()
                elif hasattr(self.webview, 'reload'):
                    self.webview.reload()
                else:
                    logger.warning("No reload method found")
            except Exception as e:
                logger.error(f"Failed to reload: {e}")
    
    def back(self):
        """Go back in history"""
        if self.webview:
            try:
                # Check if can go back
                can_go_back = False
                if hasattr(self.webview, 'CanGoBack'):
                    can_go_back = self.webview.CanGoBack
                elif hasattr(self.webview, 'can_go_back'):
                    can_go_back = self.webview.can_go_back
                
                if can_go_back:
                    if hasattr(self.webview, 'GoBack'):
                        self.webview.GoBack()
                    elif hasattr(self.webview, 'go_back'):
                        self.webview.go_back()
            except Exception as e:
                logger.error(f"Failed to go back: {e}")
    
    def forward(self):
        """Go forward in history"""
        if self.webview:
            try:
                # Check if can go forward
                can_go_forward = False
                if hasattr(self.webview, 'CanGoForward'):
                    can_go_forward = self.webview.CanGoForward
                elif hasattr(self.webview, 'can_go_forward'):
                    can_go_forward = self.webview.can_go_forward
                
                if can_go_forward:
                    if hasattr(self.webview, 'GoForward'):
                        self.webview.GoForward()
                    elif hasattr(self.webview, 'go_forward'):
                        self.webview.go_forward()
            except Exception as e:
                logger.error(f"Failed to go forward: {e}")
    
    def stop(self):
        """Stop loading"""
        if self.webview:
            try:
                if hasattr(self.webview, 'Stop'):
                    self.webview.Stop()
                elif hasattr(self.webview, 'stop'):
                    self.webview.stop()
                else:
                    logger.warning("No stop method found")
            except Exception as e:
                logger.error(f"Failed to stop: {e}")
    
    def page(self):
        """Return self for API compatibility"""
        return self
    
    def history(self):
        """Return history object for compatibility"""
        widget = self
        
        class History:
            def canGoBack(self):
                return widget.webview.CanGoBack if widget.webview else False
            
            def canGoForward(self):
                return widget.webview.CanGoForward if widget.webview else False
        
        return History()
    
    def settings(self):
        """Return mock settings for compatibility"""
        class MockSettings:
            def setAttribute(self, attr, value):
                pass
        return MockSettings()
    
    def runJavaScript(self, script: str, callback: Callable = None):
        """Execute JavaScript code"""
        if not self.webview:
            logger.warning("WebView2 not initialized, cannot execute JavaScript")
            if callback:
                callback(None)
            return
        
        # Execute script asynchronously
        async def execute():
            try:
                result = await self.webview.ExecuteScriptAsync(script)
                return result
            except Exception as e:
                logger.error(f"Failed to execute JavaScript: {e}")
                return None
        
        if self.async_runner:
            # Use threading approach
            def handle_result(result):
                if callback:
                    callback(result)
            
            # Temporarily connect handler
            self.async_runner.result_ready.connect(handle_result)
            self.async_runner.run_async(execute())
        else:
            # Use qasync or direct execution
            try:
                future = asyncio.run_coroutine_threadsafe(execute(), asyncio.get_event_loop())
                if callback:
                    future.add_done_callback(lambda f: callback(f.result()))
            except Exception as e:
                logger.error(f"Failed to execute JavaScript: {e}")
                if callback:
                    callback(None)
    
    # Qt event handlers
    
    def resizeEvent(self, event):
        """Handle widget resize"""
        super().resizeEvent(event)
        self._update_bounds()
    
    def showEvent(self, event):
        """Handle widget show"""
        super().showEvent(event)
        
        # Only initialize if not already done and not in progress
        if not self._is_initialized and not self._webview_initializing and hasattr(self, '_auto_init_on_show'):
            logger.info("Widget shown, starting deferred WebView2 initialization")
            self._auto_init_on_show = False  # Prevent re-triggering
            QTimer.singleShot(100, self.initialize)
        
        QTimer.singleShot(0, self._update_bounds)
        QTimer.singleShot(100, self._update_bounds)
    
    def sizeHint(self) -> QSize:
        """Provide size hint"""
        return QSize(800, 600)
    
    def minimumSizeHint(self) -> QSize:
        """Provide minimum size hint"""
        return QSize(400, 300)
    
    def closeEvent(self, event):
        """Clean up on close"""
        # Remove event handlers
        if self.webview:
            for event_name, token in self._event_tokens.items():
                try:
                    remove_method = getattr(self.webview, f'remove_{event_name}')
                    remove_method(token)
                except:
                    pass
        
        # Close controller
        if self.controller:
            try:
                if hasattr(self.controller, 'Close'):
                    self.controller.Close()
                elif hasattr(self.controller, 'close'):
                    self.controller.close()
            except:
                pass
        
        # Stop async runner
        if self.async_runner:
            self.async_runner.stop()
        
        super().closeEvent(event)


def check_webview2_runtime() -> bool:
    """Check if WebView2 Runtime is installed"""
    import winreg
    
    try:
        # Check for WebView2 Runtime in registry
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        winreg.CloseKey(key)
        return True
    except:
        pass
    
    # Also check for Edge installation
    try:
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\Edge\BLBeacon"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        version = winreg.QueryValueEx(key, "version")[0]
        winreg.CloseKey(key)
        # Edge version 83+ includes WebView2
        return int(version.split('.')[0]) >= 83
    except:
        return False


def install_webview2_runtime(silent: bool = True) -> bool:
    """Download and install WebView2 Runtime"""
    import urllib.request
    import subprocess
    import tempfile
    
    if check_webview2_runtime():
        return True
    
    try:
        # Download WebView2 Runtime installer
        url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
        logger.info(f"Downloading WebView2 Runtime from {url}")
        
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
            urllib.request.urlretrieve(url, tmp.name)
            
            # Run installer
            args = [tmp.name]
            if silent:
                args.extend(["/silent", "/install"])
            
            logger.info(f"Installing WebView2 Runtime...")
            result = subprocess.run(args, capture_output=True)
            
            # Clean up
            os.unlink(tmp.name)
            
            if result.returncode == 0:
                logger.info("WebView2 Runtime installed successfully")
                return True
            else:
                logger.error(f"WebView2 Runtime installation failed: {result.stderr}")
                return False
            
    except Exception as e:
        logger.error(f"Failed to install WebView2 Runtime: {e}")
        return False