"""
Enhanced unified window with blur effect and frameless design
基于unified_window.py的UnifiedAssistantWindow，整合frameless_blur_window.py的无边框半透明效果
"""

import sys
import ctypes
from typing import Optional, Dict, Any
from datetime import datetime
import pathlib

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QLineEdit, QStackedWidget, QToolButton,
    QMenu, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, pyqtSignal, QSize
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QLinearGradient,
    QPalette, QPixmap, QPainterPath, QRegion, QIcon
)

# Import existing components from unified_window
from src.game_wiki_tooltip.unified_window import (
    ChatView, WikiView, WindowMode, MessageType, ChatMessage,
    TransitionMessages, load_svg_icon, create_fallback_icon,
    StatusMessageWidget, MessageWidget, InteractiveButtonWidget,
    StreamingMessageWidget, detect_markdown_content, convert_markdown_to_html
)

# Import settings and history managers
from src.game_wiki_tooltip.config import SettingsManager
from src.game_wiki_tooltip.i18n import t

# Try to import BlurWindow
try:
    from BlurWindow.blurWindow import GlobalBlur
    BLUR_WINDOW_AVAILABLE = True
    print("✅ BlurWindow module loaded successfully")
except ImportError:
    print("Warning: BlurWindow module not found, will use default transparency effect")
    BLUR_WINDOW_AVAILABLE = False

# Windows version detection
def get_windows_version():
    """Get Windows version info"""
    try:
        import platform
        version = platform.version()
        if "10.0" in version:
            return "Windows 10"
        elif "11.0" in version:
            return "Windows 11"
        else:
            return f"Windows {version}"
    except:
        return "Unknown"


class UnifiedAssistantWindowBlur(QMainWindow):
    """Main unified window with blur effect and frameless design"""
    
    # Keep all existing signals
    query_submitted = pyqtSignal(str, str)  # query, mode
    window_closing = pyqtSignal()  # Signal when window is closing
    wiki_page_found = pyqtSignal(str, str)  # Pass real wiki page information to controller
    visibility_changed = pyqtSignal(bool)  # Signal for visibility state changes
    stop_generation_requested = pyqtSignal()  # Stop generation request

    def __init__(self, settings_manager=None):
        super().__init__()
        
        # Set frameless window flags
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        
        # Window properties for drag and resize
        self.dragging = False
        self.resizing = False
        self.resize_edge = None
        self.drag_position = QPoint()
        self.resize_start_pos = QPoint()
        self.resize_start_geometry = QRect()
        
        # Keep all existing properties
        self.settings_manager = settings_manager
        self.current_mode = "auto"
        self.is_generating = False
        self.streaming_widget = None
        self.current_game_window = None
        self.game_task_buttons = {}
        
        # History manager will be initialized lazily
        self.history_manager = None
        
        # Track current navigation
        self._pending_navigation = None
        self._last_recorded_url = None
        
        # Enable mouse tracking for resize
        self.setMouseTracking(True)
        
        # Initialize UI
        self.init_ui()
        
        # Apply BlurWindow effect
        self.apply_blur_effect()
        
        # Restore geometry
        self.restore_geometry()
        
        print(f"🏠 UnifiedAssistantWindowBlur initialized, size: {self.size()}")
        
    def apply_blur_effect(self):
        """Apply BlurWindow transparency effect"""
        if BLUR_WINDOW_AVAILABLE:
            try:
                windows_version = get_windows_version()
                print(f"Detected system version: {windows_version}")
                
                # Set window rounded corners
                self.set_window_rounded_corners()
                
                # Apply blur effect based on Windows version
                if "Windows 11" in windows_version:
                    GlobalBlur(
                        int(self.winId()), 
                        Acrylic=True,    # Win11 Acrylic effect
                        Dark=False,      # Light theme
                        QWidget=self
                    )
                    print("✅ Win11 Acrylic effect applied")
                elif "Windows 10" in windows_version:
                    GlobalBlur(
                        int(self.winId()), 
                        Acrylic=False,   # Win10 Aero effect
                        Dark=False,      # Light theme
                        QWidget=self
                    )
                    print("✅ Win10 Aero effect applied")
                else:
                    GlobalBlur(
                        int(self.winId()), 
                        Acrylic=False,   # Generic effect
                        Dark=False,      # Light theme
                        QWidget=self
                    )
                    print(f"✅ Generic transparency effect applied ({windows_version})")
                    
            except Exception as e:
                print(f"❌ BlurWindow application failed: {e}")
                print("Will use default transparency effect")
        else:
            print("⚠️ BlurWindow not available, using default transparency effect")
            
    def set_window_rounded_corners(self):
        """Set window rounded corners"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Windows API constants
            DWM_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            
            # Get window handle
            hwnd = int(self.winId())
            
            # Call DwmSetWindowAttribute to set rounded corners
            dwmapi = ctypes.windll.dwmapi
            corner_preference = wintypes.DWORD(DWMWCP_ROUND)
            result = dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWM_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(corner_preference),
                ctypes.sizeof(corner_preference)
            )
            
            if result == 0:
                print("✅ Window rounded corners set successfully")
            else:
                print(f"⚠️ Window rounded corners setting failed: {result}")
                
        except Exception as e:
            print(f"❌ Failed to set window rounded corners: {e}")
    
    def _ensure_history_manager(self):
        """Ensure history manager is initialized"""
        if self.history_manager is None:
            from src.game_wiki_tooltip.history_manager import WebHistoryManager
            self.history_manager = WebHistoryManager()
            print("📚 History manager initialized")
            
    def init_ui(self):
        """Initialize the main window UI with blur effect"""
        self.setWindowTitle("GameWiki Assistant")
        
        # Create central widget
        central_widget = QWidget()
        central_widget.setMouseTracking(True)
        self.setCentralWidget(central_widget)
        
        # Create main container frame (consistent with BlurWindow layer size)
        main_container = QFrame()
        main_container.setObjectName("mainContainer")
        main_container.setMouseTracking(True)
        
        # Save main_container reference for later adjustments
        self.main_container = main_container
        
        # Central widget layout (only contains main container)
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(main_container)
        
        # Main container layout
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create custom title bar
        self.title_bar = self.create_title_bar()
        main_layout.addWidget(self.title_bar)
        
        # Content area (chat/wiki switcher)
        self.content_stack = QStackedWidget()
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Chat view
        self.chat_view = ChatView()
        self.chat_view.wiki_requested.connect(self.show_wiki_page)
        self.chat_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Wiki view
        self.wiki_view = WikiView()
        self.wiki_view.back_requested.connect(self.show_chat_view)
        self.wiki_view.wiki_page_loaded.connect(self.handle_wiki_page_loaded)
        self.wiki_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        self.content_stack.addWidget(self.chat_view)
        self.content_stack.addWidget(self.wiki_view)
        
        # Shortcuts container (above input area)
        self.shortcut_container = self.create_shortcut_container()
        
        # Input area
        self.input_container = self.create_input_container()
        
        # Add to main layout
        main_layout.addWidget(self.content_stack, 1)
        main_layout.addWidget(self.shortcut_container, 0)
        main_layout.addWidget(self.input_container, 0)
        
        # Apply styles
        self.setup_styles()
        
        # Enable mouse tracking for all children
        self.enable_mouse_tracking_for_children()
        
        # Don't load shortcuts immediately - defer to after window is shown
        self.shortcuts_loaded = False
        
        # Ensure the window can be freely resized
        self.setMinimumSize(300, 200)
        self.setMaximumSize(16777215, 16777215)
        
    def create_title_bar(self):
        """Create custom title bar"""
        title_bar = QFrame()
        title_bar.setFixedHeight(40)
        title_bar.setObjectName("titleBar")
        title_bar.setMouseTracking(True)
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Title
        self.title_label = QLabel("GameWiki Assistant")
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # Minimize button
        min_btn = QPushButton("−")
        min_btn.setObjectName("minBtn")
        min_btn.setFixedSize(30, 25)
        min_btn.clicked.connect(self.showMinimized)
        
        # Close button
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(30, 25)
        close_btn.clicked.connect(self.close)
        
        layout.addWidget(min_btn)
        layout.addWidget(close_btn)
        
        return title_bar
        
    def create_shortcut_container(self):
        """Create shortcuts container with blur style"""
        container = QFrame()
        container.setObjectName("shortcutContainer")
        container.setFixedHeight(35)
        
        self.shortcut_layout = QHBoxLayout(container)
        self.shortcut_layout.setContentsMargins(10, 4, 10, 4)
        self.shortcut_layout.setSpacing(8)
        
        return container
        
    def create_input_container(self):
        """Create input container with blur style"""
        container = QFrame()
        container.setObjectName("inputContainer")
        container.setFixedHeight(60)
        
        input_layout = QHBoxLayout(container)
        input_layout.setContentsMargins(10, 10, 10, 10)
        
        # Mode selection button
        self.mode_button = QToolButton()
        self.mode_button.setText("Search info")
        self.mode_button.setFixedSize(160, 45)
        self.mode_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.mode_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.mode_button.setArrowType(Qt.ArrowType.NoArrow)
        self.mode_button.setObjectName("modeButton")
        
        # Create menu for mode selection
        mode_menu = QMenu(self.mode_button)
        mode_menu.setObjectName("modeMenu")
        
        # Add mode options
        auto_action = mode_menu.addAction(t("search_mode_auto"))
        auto_action.triggered.connect(lambda: self.set_mode("auto"))
        
        wiki_action = mode_menu.addAction(t("search_mode_wiki"))
        wiki_action.triggered.connect(lambda: self.set_mode("wiki"))
        
        ai_action = mode_menu.addAction(t("search_mode_ai"))
        ai_action.triggered.connect(lambda: self.set_mode("ai"))
        
        mode_menu.addSeparator()
        
        url_action = mode_menu.addAction(t("search_mode_url"))
        url_action.triggered.connect(lambda: self.set_mode("url"))
        
        self.mode_button.setMenu(mode_menu)
        self.mode_button.setText(t("search_mode_auto") + " ▼")
        
        # Input field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter message...")
        self.input_field.setFixedHeight(45)
        self.input_field.setObjectName("inputField")
        self.input_field.returnPressed.connect(self.on_input_return_pressed)
        
        # Send button
        self.send_button = QPushButton("Send")
        self.send_button.setFixedSize(80, 45)
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self.on_send_clicked)
        
        # History button
        self.history_button = QToolButton()
        self.history_button.setFixedSize(45, 45)
        self.history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_button.setToolTip("View browsing history")
        self.history_button.setObjectName("historyButton")
        self.history_button.setText("📜")
        self.history_button.clicked.connect(self.show_history_menu)
        
        input_layout.addWidget(self.mode_button)
        input_layout.addWidget(self.history_button)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        
        return container
        
    def setup_styles(self):
        """Set up styles with blur effect"""
        style_sheet = """
        QMainWindow {
            background: transparent;
        }
        
        #mainContainer {
            background: rgba(255, 255, 255, 115);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 40);
        }
        
        #titleBar {
            background: transparent;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            border-bottom: 1px solid rgba(200, 200, 200, 50);
        }
        
        #titleLabel {
            color: #111111;
            font-size: 14px;
            font-weight: bold;
            font-family: "Microsoft YaHei", "Segoe UI", Arial;
        }
        
        #minBtn, #closeBtn {
            background: rgba(255, 255, 255, 150);
            border: none;
            border-radius: 5px;
            color: #111111;
            font-weight: bold;
            font-family: "Segoe UI", Arial;
        }
        
        #minBtn:hover, #closeBtn:hover {
            background: rgba(220, 220, 220, 180);
        }
        
        #closeBtn:hover {
            background: rgba(220, 60, 60, 180);
            color: white;
        }
        
        #shortcutContainer {
            background: rgba(248, 249, 250, 180);
            border-bottom: 1px solid rgba(200, 200, 200, 100);
        }
        
        #inputContainer {
            background: rgba(248, 249, 250, 180);
            border-top: 1px solid rgba(200, 200, 200, 100);
            border-bottom-left-radius: 10px;
            border-bottom-right-radius: 10px;
        }
        
        #modeButton {
            background-color: rgba(255, 255, 255, 200);
            border: 1px solid rgba(224, 224, 224, 150);
            border-radius: 22px;
            padding: 0 15px;
            font-size: 14px;
            font-family: "Microsoft YaHei", "Segoe UI", Arial;
        }
        
        #modeButton:hover {
            border-color: rgba(64, 150, 255, 180);
        }
        
        #modeButton::menu-indicator {
            image: none;
            subcontrol-position: right center;
            subcontrol-origin: padding;
            width: 16px;
        }
        
        #modeMenu {
            background-color: rgba(255, 255, 255, 240);
            border: 1px solid rgba(224, 224, 224, 150);
            border-radius: 8px;
            padding: 4px;
        }
        
        #modeMenu::item {
            padding: 8px 20px;
            border-radius: 4px;
        }
        
        #modeMenu::item:hover {
            background-color: rgba(240, 240, 240, 180);
        }
        
        #inputField {
            background-color: rgba(255, 255, 255, 200);
            border: 1px solid rgba(224, 224, 224, 150);
            border-radius: 22px;
            padding: 10px 20px;
            font-size: 16px;
            font-family: "Microsoft YaHei", "Segoe UI", Arial;
        }
        
        #inputField:focus {
            border-color: rgba(64, 150, 255, 180);
            outline: none;
        }
        
        #sendButton {
            background-color: rgba(64, 150, 255, 200);
            color: white;
            border: none;
            border-radius: 22px;
            font-weight: bold;
            font-size: 16px;
            font-family: "Microsoft YaHei", "Segoe UI", Arial;
        }
        
        #sendButton:hover {
            background-color: rgba(45, 127, 249, 200);
        }
        
        #sendButton:pressed {
            background-color: rgba(22, 104, 220, 200);
        }
        
        #sendButton[stop_mode="true"] {
            background-color: rgba(255, 77, 79, 200);
        }
        
        #sendButton[stop_mode="true"]:hover {
            background-color: rgba(255, 120, 117, 200);
        }
        
        #sendButton[stop_mode="true"]:pressed {
            background-color: rgba(211, 47, 47, 200);
        }
        
        #historyButton {
            background-color: rgba(255, 255, 255, 200);
            border: 1px solid rgba(224, 224, 224, 150);
            border-radius: 22px;
            font-size: 20px;
        }
        
        #historyButton:hover {
            background-color: rgba(240, 240, 240, 200);
            border-color: rgba(64, 150, 255, 180);
        }
        
        #historyButton:pressed {
            background-color: rgba(224, 224, 224, 200);
        }
        
        /* Chat view styles with transparency */
        ChatView {
            background: transparent;
        }
        
        MessageWidget {
            background: transparent;
        }
        """
        self.setStyleSheet(style_sheet)
        
    def enable_mouse_tracking_for_children(self):
        """Enable mouse tracking for all child widgets recursively"""
        def enable_tracking(widget):
            widget.setMouseTracking(True)
            for child in widget.findChildren(QWidget):
                enable_tracking(child)
        
        enable_tracking(self)
        
    # Mouse event handlers for drag and resize
    def get_resize_edge(self, pos):
        """Check if mouse position is at window edge, return edge type"""
        margin = 10
        rect = self.rect()
        
        left = pos.x() <= margin
        right = pos.x() >= rect.width() - margin
        top = pos.y() <= margin
        bottom = pos.y() >= rect.height() - margin
        
        if top and left:
            return 'top-left'
        elif top and right:
            return 'top-right'
        elif bottom and left:
            return 'bottom-left'
        elif bottom and right:
            return 'bottom-right'
        elif top:
            return 'top'
        elif bottom:
            return 'bottom'
        elif left:
            return 'left'
        elif right:
            return 'right'
        else:
            return None
    
    def set_resize_cursor(self, edge):
        """Set mouse cursor based on edge type"""
        if edge == 'top' or edge == 'bottom':
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge == 'left' or edge == 'right':
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge == 'top-left' or edge == 'bottom-right':
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge == 'top-right' or edge == 'bottom-left':
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
    def mousePressEvent(self, event):
        """Mouse press event"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            edge = self.get_resize_edge(pos)
            
            if edge:
                # Start resizing
                self.resizing = True
                self.resize_edge = edge
                self.resize_start_pos = event.globalPosition().toPoint()
                self.resize_start_geometry = self.geometry()
            elif self.title_bar.geometry().contains(pos):
                # Start dragging only if clicked on title bar
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        """Mouse move event"""
        pos = event.position().toPoint()
        
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self.resizing and self.resize_edge:
                # Resize window
                self.resize_window(event.globalPosition().toPoint())
            elif self.dragging:
                # Move window
                self.move(event.globalPosition().toPoint() - self.drag_position)
        else:
            # Check if mouse is at edge, set cursor
            edge = self.get_resize_edge(pos)
            self.set_resize_cursor(edge)
        
        event.accept()
            
    def mouseReleaseEvent(self, event):
        """Mouse release event"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.resizing = False
            self.resize_edge = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
    
    def resize_window(self, global_pos):
        """Resize window"""
        if not self.resize_edge:
            return
            
        delta = global_pos - self.resize_start_pos
        geometry = QRect(self.resize_start_geometry)
        
        # Set minimum window size
        min_width = 400
        min_height = 300
        
        # Handle horizontal resize
        if 'left' in self.resize_edge:
            new_width = geometry.width() - delta.x()
            if new_width >= min_width:
                geometry.setLeft(geometry.left() + delta.x())
            else:
                geometry.setLeft(geometry.right() - min_width)
        elif 'right' in self.resize_edge:
            new_width = geometry.width() + delta.x()
            if new_width >= min_width:
                geometry.setWidth(new_width)
            else:
                geometry.setWidth(min_width)
                
        # Handle vertical resize
        if 'top' in self.resize_edge:
            new_height = geometry.height() - delta.y()
            if new_height >= min_height:
                geometry.setTop(geometry.top() + delta.y())
            else:
                geometry.setTop(geometry.bottom() - min_height)
        elif 'bottom' in self.resize_edge:
            new_height = geometry.height() + delta.y()
            if new_height >= min_height:
                geometry.setHeight(new_height)
            else:
                geometry.setHeight(min_height)
        
        self.setGeometry(geometry)
    
    # All existing methods from UnifiedAssistantWindow should be copied here
    # For now, I'll include the key methods that were referenced in the original init_ui
    
    def show_wiki_page(self, url: str, title: str):
        """Show wiki page"""
        self.wiki_view.load_url(url)
        self.content_stack.setCurrentWidget(self.wiki_view)
        
    def show_chat_view(self):
        """Show chat view"""
        self.content_stack.setCurrentWidget(self.chat_view)
        
    def handle_wiki_page_loaded(self, url: str, title: str):
        """Handle wiki page loaded event"""
        self.wiki_page_found.emit(url, title)
        
    def set_mode(self, mode: str):
        """Set current search mode"""
        self.current_mode = mode
        mode_text = t(f"search_mode_{mode}")
        self.mode_button.setText(mode_text + " ▼")
        
    def on_input_return_pressed(self):
        """Handle input field return pressed"""
        if self.current_mode == "url":
            self.on_open_url_clicked()
        else:
            self.on_send_clicked()
            
    def on_open_url_clicked(self):
        """Handle open URL"""
        url = self.input_field.text().strip()
        if url:
            self.open_url(url)
            self.input_field.clear()
            
    def open_url(self, url: str):
        """Open URL in wiki view"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        self.wiki_view.load_url(url)
        self.content_stack.setCurrentWidget(self.wiki_view)
        
    def on_send_clicked(self):
        """Handle send button click"""
        if self.is_generating and self.streaming_widget:
            self.stop_generation()
        else:
            query = self.input_field.text().strip()
            if query:
                self.query_submitted.emit(query, self.current_mode)
                self.input_field.clear()
                
    def stop_generation(self):
        """Stop current generation"""
        if self.streaming_widget:
            self.streaming_widget.mark_as_stopped()
        self.set_generating_state(False)
        self.stop_generation_requested.emit()
        
    def set_generating_state(self, is_generating: bool, streaming_msg=None):
        """Set generating state"""
        self.is_generating = is_generating
        self.streaming_widget = streaming_msg
        
        if is_generating:
            self.send_button.setText("Stop")
            self.send_button.setProperty("stop_mode", True)
        else:
            self.send_button.setText("Send")
            self.send_button.setProperty("stop_mode", False)
            
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)
        
    def show_history_menu(self):
        """Show history menu"""
        # Implementation should be copied from original UnifiedAssistantWindow
        pass
        
    def restore_geometry(self):
        """Restore window geometry from settings"""
        if self.settings_manager:
            settings = self.settings_manager.get()
            geometry = settings.get('window_geometry', {})
            if geometry:
                self.setGeometry(
                    geometry.get('x', 100),
                    geometry.get('y', 100),
                    geometry.get('width', 600),
                    geometry.get('height', 800)
                )
                
    def save_geometry(self):
        """Save window geometry to settings"""
        if self.settings_manager:
            geometry = {
                'x': self.x(),
                'y': self.y(),
                'width': self.width(),
                'height': self.height()
            }
            self.settings_manager.update({'window_geometry': geometry})
            
    def closeEvent(self, event):
        """Handle window close event"""
        self.save_geometry()
        self.window_closing.emit()
        event.accept()
        
    def showEvent(self, event):
        """Handle window show event"""
        super().showEvent(event)
        self.visibility_changed.emit(True)
        
        # Load shortcuts if not loaded yet
        if not self.shortcuts_loaded:
            QTimer.singleShot(100, self.load_shortcuts)
            
    def hideEvent(self, event):
        """Handle window hide event"""
        super().hideEvent(event)
        self.visibility_changed.emit(False)
        
    def load_shortcuts(self):
        """Load shortcut buttons - implementation should be copied from original"""
        self.shortcuts_loaded = True
        # TODO: Copy implementation from original UnifiedAssistantWindow 