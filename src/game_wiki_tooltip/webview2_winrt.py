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

# COM will be initialized on-demand by WebView2 runtime
# Removed automatic COM initialization to avoid conflicts with Qt event loop

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
        """Initialize WebView2 asynchronously using asyncio.create_task (like test_webview2.py)"""
        logger.info("Starting async initialization using asyncio...")
        
        # Start timeout watchdog
        self._init_timeout_timer = QTimer(self)
        self._init_timeout_timer.setSingleShot(True)
        self._init_timeout_timer.timeout.connect(self._on_init_timeout)
        self._init_timeout_timer.start(30000)  # 30 second timeout
        
        async def init_task():
            """Async initialization task"""
            try:
                logger.info("Beginning async initialization task...")
                # Call the async initialization method
                result = await self._async_initialize()
                
                if result:
                    logger.info("✅ WebView2 initialization successful!")
                    # Ensure _on_initialized is called in the main thread
                    loop.call_soon_threadsafe(self._on_initialized)
                else:
                    logger.error("WebView2 initialization returned False")
                    QTimer.singleShot(0, self._fallback_sync_init)
                    
            except Exception as e:
                logger.error(f"Async initialization failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self._cancel_init_timeout()
                QTimer.singleShot(0, self._fallback_sync_init)
        
        # Schedule the async task on the event loop
        # Use loop.call_soon_threadsafe to avoid "no running event loop" error
        # when called from Qt callback context
        try:
            loop = asyncio.get_event_loop()  # qasync has already set this as default loop
            # Schedule task creation in the loop's context
            loop.call_soon_threadsafe(lambda: loop.create_task(init_task()))
            logger.info("Async initialization task scheduled on event loop")
        except Exception as e:
            logger.error(f"Failed to schedule async init: {e}")
            self._cancel_init_timeout()
            QTimer.singleShot(0, self._fallback_sync_init)
    
    def _fallback_sync_init(self):
        """Fallback synchronous initialization if async fails"""
        logger.warning("All initialization attempts failed")
        try:
            # Show error but don't block the UI
            self._show_error("WebView2 initialization failed. Web features will be unavailable.")
            self._webview_initializing = False
        except Exception as e:
            logger.error(f"Error showing fallback message: {e}")
            self._webview_initializing = False
    
    # Removed callback-based methods - now using async/await in _async_initialize
    
    def _setup_controller(self):
        """Setup controller properties"""
        try:
            # Set initial bounds
            self._update_bounds()
            
            # Set visibility
            if hasattr(self.controller, 'IsVisible'):
                self.controller.IsVisible = True
            elif hasattr(self.controller, 'is_visible'):
                self.controller.is_visible = True
            elif hasattr(self.controller, 'put_IsVisible'):
                self.controller.put_IsVisible(True)
            
            # Set zoom factor
            if hasattr(self.controller, 'ZoomFactor'):
                self.controller.ZoomFactor = 1.0
            elif hasattr(self.controller, 'zoom_factor'):
                self.controller.zoom_factor = 1.0
            elif hasattr(self.controller, 'put_ZoomFactor'):
                self.controller.put_ZoomFactor(1.0)
                
            logger.info("Controller properties configured")
            
        except Exception as e:
            logger.error(f"Failed to setup controller properties: {e}")
    
    def _on_init_timeout(self):
        """Handle initialization timeout"""
        logger.error("WebView2 initialization timed out after 30 seconds")
        self._webview_initializing = False
        self._show_error("WebView2 initialization timed out")
        self._fallback_sync_init()
    
    def _cancel_init_timeout(self):
        """Cancel the initialization timeout timer"""
        if hasattr(self, '_init_timeout_timer') and self._init_timeout_timer:
            self._init_timeout_timer.stop()
            self._init_timeout_timer = None
            logger.debug("Initialization timeout timer cancelled")
    
    async def _await_winrt(self, op, timeout=30.0):
        """
        Wait for WinRT IAsyncOperation to complete:
        - Primary: Use Completed property (if projection supports Python callback to delegate conversion)
        - Fallback: Use Status polling (avoids delegate conversion errors)
        """
        from winrt.windows.foundation import AsyncStatus
        
        loop = asyncio.get_event_loop()

        # Try to use Completed callback (may throw NotImplementedError if projection doesn't support delegate conversion)
        try:
            fut = loop.create_future()

            # Keep reference to prevent GC
            if not hasattr(self, "_pending_ops"):
                self._pending_ops = []
            self._pending_ops.append(op)

            def _done(o, status):
                try:
                    if status == AsyncStatus.Completed:
                        res = o.get_results()
                        loop.call_soon_threadsafe(fut.set_result, res)
                    else:
                        try:
                            o.get_results()  # Trigger specific exception
                        except Exception as e:
                            loop.call_soon_threadsafe(fut.set_exception, e)
                finally:
                    try:
                        self._pending_ops.remove(o)
                    except Exception:
                        pass

            if hasattr(op, "Completed"):
                op.Completed = _done
            elif hasattr(op, "completed"):
                op.completed = _done
            else:
                raise NotImplementedError("No Completed/completed on this IAsyncOperation")

            return await asyncio.wait_for(fut, timeout=timeout)

        except (NotImplementedError, TypeError) as e:
            # Fallback to QTimer-based polling (avoids asyncio.sleep and get_running_loop issues)
            logger.debug(f"Callback approach failed ({e}), falling back to QTimer polling")
            
            from PyQt6.QtCore import QTimer
            from time import monotonic
            
            # Create future for result
            fut = loop.create_future()
            
            status_attr = "Status" if hasattr(op, "Status") else ("status" if hasattr(op, "status") else None)
            if not status_attr:
                raise RuntimeError("IAsyncOperation has neither Status nor status attribute")

            # Get enum constants, compatible with different naming (uppercase/camelCase)
            # Windows.Foundation.AsyncStatus: Started=0, Completed=1, Canceled=2, Error=3
            COMPLETED = getattr(AsyncStatus, "COMPLETED", getattr(AsyncStatus, "Completed", 1))
            CANCELED = getattr(AsyncStatus, "CANCELED", getattr(AsyncStatus, "Canceled", 2))
            ERROR = getattr(AsyncStatus, "ERROR", getattr(AsyncStatus, "Error", 3))

            # Use Qt timer for polling instead of asyncio.sleep
            timer = QTimer(self)
            timer.setInterval(10)  # 10ms polling interval
            
            start = monotonic()
            
            def tick():
                try:
                    status = getattr(op, status_attr)
                    try:
                        code = int(status)
                    except Exception:
                        code = getattr(status, "value", status)
                    
                    if code == int(COMPLETED):
                        try:
                            res = op.get_results()
                            loop.call_soon_threadsafe(fut.set_result, res)
                        except Exception as ex:
                            loop.call_soon_threadsafe(fut.set_exception, ex)
                        finally:
                            timer.stop()
                        return
                    
                    if code in (int(ERROR), int(CANCELED)):
                        try:
                            op.get_results()  # Trigger specific exception
                        except Exception as ex:
                            loop.call_soon_threadsafe(fut.set_exception, ex)
                        else:
                            loop.call_soon_threadsafe(
                                fut.set_exception, RuntimeError(f"Operation finished with status code: {code}")
                            )
                        timer.stop()
                        return
                    
                    if monotonic() - start > timeout:
                        timer.stop()
                        loop.call_soon_threadsafe(
                            fut.set_exception, TimeoutError(f"IAsyncOperation timed out after {timeout} seconds")
                        )
                        return
                        
                except Exception as ex:
                    timer.stop()
                    loop.call_soon_threadsafe(fut.set_exception, ex)
            
            # Keep references to prevent GC
            if not hasattr(self, "_pending_ops"):
                self._pending_ops = []
            self._pending_ops.append(op)
            if not hasattr(self, "_await_timers"):
                self._await_timers = []
            self._await_timers.append(timer)
            
            # Start polling
            timer.timeout.connect(tick)
            timer.start()
            
            # Return the future (await will work correctly)
            return await fut
    
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
            
            # 2. Create CoreWebView2Environment using bridge to avoid get_running_loop() issues
            logger.info("Creating CoreWebView2Environment...")
            try:
                # Only use zero-parameter version - current projection doesn't support parameter overloads
                env_op = CoreWebView2Environment.create_async()
                self.environment = await self._await_winrt(env_op)
                logger.info("✓ Environment created successfully")
            except Exception as e:
                logger.error(f"Environment creation failed: {e}")
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
            
            try:
                # Create controller with bridge (timeout handled by _await_winrt itself)
                logger.info("About to call create_core_webview2_controller_async...")
                ctrl_op = self.environment.create_core_webview2_controller_async(window_ref)
                # Let _await_winrt handle the timeout directly
                self.controller = await self._await_winrt(ctrl_op, timeout=20.0)
                logger.info("✓ Controller created successfully!")
            except TimeoutError:
                logger.error("✗ Controller creation timed out after 20 seconds")
                raise Exception("Controller creation timed out")
            except Exception as e:
                logger.error(f"✗ Controller creation failed: {e}")
                # List environment methods for debugging
                try:
                    env_methods = [m for m in dir(self.environment) if not m.startswith('_')]
                    logger.info(f"Available environment methods: {env_methods}")
                except:
                    pass
                raise
            
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
            
            logger.info("WebView2 async initialization completed successfully")
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
            # Navigation events (使用正确的下划线命名法)
            if hasattr(self.webview, 'add_navigation_starting'):
                token = self.webview.add_navigation_starting(self._on_navigation_starting)
                self._event_tokens['navigation_starting'] = token
                logger.info("✓ navigation_starting event configured")
            else:
                logger.warning("⚠ navigation_starting event not available")
            
            if hasattr(self.webview, 'add_navigation_completed'):
                token = self.webview.add_navigation_completed(self._on_navigation_completed)
                self._event_tokens['navigation_completed'] = token
                logger.info("✓ navigation_completed event configured")
            else:
                logger.warning("⚠ navigation_completed event not available")
            
            if hasattr(self.webview, 'add_source_changed'):
                token = self.webview.add_source_changed(self._on_source_changed)
                self._event_tokens['source_changed'] = token
                logger.info("✓ source_changed event configured")
            else:
                logger.warning("⚠ source_changed event not available")
            
            if hasattr(self.webview, 'add_document_title_changed'):
                token = self.webview.add_document_title_changed(self._on_title_changed)
                self._event_tokens['document_title_changed'] = token
                logger.info("✓ document_title_changed event configured")
            else:
                logger.warning("⚠ document_title_changed event not available")
            
            # New window handling
            if hasattr(self.webview, 'add_new_window_requested'):
                token = self.webview.add_new_window_requested(self._on_new_window_requested)
                self._event_tokens['new_window_requested'] = token
                logger.info("✓ new_window_requested event configured")
            else:
                logger.warning("⚠ new_window_requested event not available")
            
            # 列出所有可用的事件方法以供调试
            event_methods = [m for m in dir(self.webview) if m.startswith('add_')]
            logger.info(f"Available event methods: {event_methods}")
            
            logger.info("WebView2 event handlers setup completed")
            
        except Exception as e:
            logger.error(f"Failed to setup events: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _on_initialized(self):
        """Called when initialization is complete"""
        logger.info(">>> _on_initialized called <<<")
        self._is_initialized = True  # ★ 必须有！
        self.placeholder.hide()
        self._webview_initializing = False
        
        # Cancel the timeout timer since initialization succeeded
        self._cancel_init_timeout()
        
        logger.info("✅ WebView2 initialization complete, ready for navigation")
        
        # Process all pending navigations
        while self._pending_navigations:
            url = self._pending_navigations.pop(0)
            logger.info(f"Processing pending navigation: {url}")
            self.navigate(url)
    
    # Event handlers
    def _on_navigation_starting(self, sender, args):
        """Handle navigation starting event"""
        QTimer.singleShot(0, self.loadStarted.emit)
    
    def _on_navigation_completed(self, sender, args):
        """Handle navigation completed event"""
        try:
            # 尝试不同的属性名
            success = True
            if hasattr(args, 'IsSuccess'):
                success = args.IsSuccess
            elif hasattr(args, 'is_success'):
                success = args.is_success
            
            logger.info(f"Navigation completed: {'success' if success else 'failed'}")
            QTimer.singleShot(0, lambda: self.loadFinished.emit(success))
        except Exception as e:
            logger.error(f"Error in navigation completed handler: {e}")
            QTimer.singleShot(0, lambda: self.loadFinished.emit(True))
    
    def _on_source_changed(self, sender, args):
        """Handle source (URL) changed event"""
        try:
            if self.webview:
                # Get current URI - try different property names
                uri = None
                if hasattr(self.webview, 'Source'):
                    uri = self.webview.Source
                elif hasattr(self.webview, 'source'):
                    uri = self.webview.source
                
                if uri:
                    self.current_url = str(uri)
                    logger.info(f"URL changed to: {self.current_url}")
                    QTimer.singleShot(0, lambda: self.urlChanged.emit(QUrl(self.current_url)))
        except Exception as e:
            logger.error(f"Error in source changed handler: {e}")
    
    def _on_title_changed(self, sender, args):
        """Handle document title changed event"""
        try:
            if self.webview:
                # Try different property names
                title = None
                if hasattr(self.webview, 'DocumentTitle'):
                    title = self.webview.DocumentTitle
                elif hasattr(self.webview, 'document_title'):
                    title = self.webview.document_title
                
                if title:
                    self.current_title = str(title)
                    logger.info(f"Title changed to: {self.current_title}")
                    QTimer.singleShot(0, lambda: self.titleChanged.emit(self.current_title))
        except Exception as e:
            logger.error(f"Error in title changed handler: {e}")
    
    def _on_new_window_requested(self, sender, args):
        """Handle new window request - open in current window instead"""
        try:
            # Prevent new window - try different property names
            if hasattr(args, 'Handled'):
                args.Handled = True
            elif hasattr(args, 'handled'):
                args.handled = True
            
            # Navigate in current window - try different property names
            uri = None
            if hasattr(args, 'Uri'):
                uri = args.Uri
            elif hasattr(args, 'uri'):
                uri = args.uri
            
            if uri:
                self.navigate(str(uri))
                logger.info(f"Intercepted new window request, navigating to: {uri}")
            
        except Exception as e:
            logger.error(f"Error handling new window request: {e}")
    
    def _update_bounds(self):
        """Update WebView2 bounds to match widget size"""
        if not self.controller:
            return
        
        try:
            rect = self.rect()
            logger.info(f"Updating bounds to {rect.width()}x{rect.height()}")
            
            # Create Rect with position and size (prefer WinRT Rect if available)
            if Rect is not None and hasattr(Rect, '__call__'):
                try:
                    # Use WinRT Rect constructor
                    bounds = Rect(0, 0, rect.width(), rect.height())
                    logger.info(f"✓ Created WinRT Rect: {bounds}")
                except Exception as e:
                    logger.warning(f"WinRT Rect creation failed: {e}, using fallback")
                    bounds = FallbackRect(0, 0, rect.width(), rect.height())
            else:
                bounds = FallbackRect(0, 0, rect.width(), rect.height())
            
            # Try both naming conventions for setting bounds
            success = False
            if hasattr(self.controller, 'bounds'):
                self.controller.bounds = bounds
                logger.info("✓ Set bounds using 'bounds' property")
                success = True
            elif hasattr(self.controller, 'Bounds'):
                self.controller.Bounds = bounds
                logger.info("✓ Set bounds using 'Bounds' property")
                success = True
            elif hasattr(self.controller, 'put_bounds'):
                self.controller.put_bounds(bounds)
                logger.info("✓ Set bounds using 'put_bounds' method")
                success = True
            elif hasattr(self.controller, 'put_Bounds'):
                self.controller.put_Bounds(bounds)
                logger.info("✓ Set bounds using 'put_Bounds' method")
                success = True
            elif hasattr(self.controller, 'set_bounds'):
                self.controller.set_bounds(bounds)
                logger.info("✓ Set bounds using 'set_bounds' method")
                success = True
            
            if not success:
                logger.warning("⚠ No bounds property/method found on controller")
                # List available methods for debugging
                attrs = [attr for attr in dir(self.controller) if not attr.startswith('_') and 'bound' in attr.lower()]
                logger.info(f"Available bounds-related methods: {attrs}")
            
        except Exception as e:
            logger.error(f"✗ Failed to update bounds: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
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
        
        # 使用正确的事件循环调度方式
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(execute())
            if callback:
                def handle_done(future):
                    try:
                        result = future.result()
                        callback(result)
                    except Exception as e:
                        logger.error(f"JavaScript execution error: {e}")
                        callback(None)
                task.add_done_callback(handle_done)
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