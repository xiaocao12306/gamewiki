"""
Unified window system for GameWikiTooltip.
Provides mini assistant and expandable chat window functionality.
"""

import sys
import asyncio
import json
import ctypes
import logging
import re
import time
import os
import pathlib
from datetime import datetime
import threading
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from dataclasses import dataclass, field

from src.game_wiki_tooltip.i18n import t
from src.game_wiki_tooltip.config import PopupConfig

# Import markdown support
try:
    import markdown
    MARKDOWN_AVAILABLE = True
    
    # Disable markdown library debug log output to avoid excessive debug information
    markdown_logger = logging.getLogger('markdown')
    markdown_logger.setLevel(logging.WARNING)
    
except ImportError:
    print("Warning: markdown library not available. Markdown content will be displayed as plain text.")
    MARKDOWN_AVAILABLE = False

try:
    from PyQt6.QtCore import (
        Qt, QTimer, QPropertyAnimation, QRect, QSize, QPoint,
        QEasingCurve, QParallelAnimationGroup, pyqtSignal, QUrl,
        QThread, pyqtSlot
    )
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QFrame, QStackedWidget,
        QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QLineEdit,
        QToolButton, QMenu
    )
    from PyQt6.QtGui import (
        QPainter, QColor, QBrush, QPen, QFont, QLinearGradient,
        QPalette, QIcon, QPixmap, QPainterPath, QTextDocument
    )
    # Only WebView2 is supported
except ImportError:
    print("Error: PyQt6 is required. PyQt5 is no longer supported.")
    sys.exit(1)

# Always use WebView2 for web content
USE_WEBVIEW2 = True

# Import WebView2Widget if enabled
if USE_WEBVIEW2:
    try:
        # Try the simple implementation first
        from src.game_wiki_tooltip.webview2_simple import SimpleWebView2Widget as WebView2Widget
        from src.game_wiki_tooltip.webview_widget import check_webview2_runtime
        WEBVIEW2_AVAILABLE = True
        print("Using simplified WebView2 implementation")
        # Check if WebView2 Runtime is installed
        if not check_webview2_runtime():
            print("Warning: WebView2 Runtime not installed. Video playback may be limited.")
            print("Visit https://go.microsoft.com/fwlink/p/?LinkId=2124703 to install WebView2 Runtime.")
    except ImportError as e:
        print(f"Warning: WebView2Widget not available: {e}")
        WEBVIEW2_AVAILABLE = False
        USE_WEBVIEW2 = False  # WebView2 failed to initialize
else:
    WEBVIEW2_AVAILABLE = False

# Try to import BlurWindow
try:
    from BlurWindow.blurWindow import GlobalBlur
    BLUR_WINDOW_AVAILABLE = True
    print("✅ BlurWindow module loaded successfully")
except ImportError:
    print("Warning: BlurWindow module not found, will use default transparency effect")
    BLUR_WINDOW_AVAILABLE = False

# Import graphics compatibility for Windows version detection
from src.game_wiki_tooltip.graphics_compatibility import WindowsGraphicsCompatibility


def _get_scale() -> float:
    """Get display scaling factor (Windows only)"""
    try:
        shcore = ctypes.windll.shcore
        hMonitor = ctypes.windll.user32.MonitorFromWindow(
            None,   # Pass None to get primary monitor
            1       # MONITOR_DEFAULTTOPRIMARY
        )
        factor = ctypes.c_uint()
        if shcore.GetScaleFactorForMonitor(hMonitor, ctypes.byref(factor)) == 0:
            return factor.value / 100.0
    except Exception:
        pass
    return 1.0


def load_svg_icon(svg_path, color="#666666", size=16):
    """Load SVG icon and set color"""
    try:
        import os
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QByteArray
        
        # Check if file exists
        if not os.path.exists(svg_path):
            print(f"SVG file not found: {svg_path}")
            return QIcon()
        
        # Read SVG file
        with open(svg_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()
        
        # Replace color
        svg_content = svg_content.replace('stroke="#000000"', f'stroke="{color}"')
        svg_content = svg_content.replace('fill="#000000"', f'fill="{color}"')
        
        # Create icon
        icon = QIcon()
        renderer = QSvgRenderer(QByteArray(svg_content.encode()))
        
        # Create pixmaps for different sizes
        for s in [size, size*2]:  # Support high DPI
            pixmap = QPixmap(s, s)
            pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            icon.addPixmap(pixmap)
        
        return icon
    except Exception as e:
        print(f"Failed to load SVG icon: {e}")
        return QIcon()

class QuickAccessPopup(QWidget):
    """Horizontal popup widget for quick access shortcuts"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus |
            Qt.WindowType.Popup  # Add popup flag for auto-close behavior
        )

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("QuickAccessPopup")  # Set object name for the main widget
        self.setStyleSheet("""
                #QuickAccessPopup {
                    background-color: rgb( 0);
                    border-radius: 50px !important;
                    border: 1px ;
                    padding: 0;
                    margin: 0;
                }
            """)

        # Main container
        self.container = QFrame()
        self.container.setObjectName("quickAccessPopup")
        # Container should be transparent since parent has the background
        self.container.setStyleSheet("""
            #quickAccessPopup {
                background-color: rgb(255, 255, 255);
                border-radius: 10px;
                padding: 5px;
                border: none;
                margin: 0;
            }
        """)
        
        # Layout
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.container)
        
        # Shortcuts layout
        self.shortcuts_layout = QHBoxLayout(self.container)
        self.shortcuts_layout.setContentsMargins(10, 5, 10, 5)
        self.shortcuts_layout.setSpacing(0)
        
        # Hide timer
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)
        
        # Track if mouse is over popup
        self.mouse_over = False
        self.setMouseTracking(True)
        self.container.setMouseTracking(True)
        
    def add_shortcut(self, button: 'ExpandableIconButton'):
        """Add a shortcut button to the popup"""
        self.shortcuts_layout.addWidget(button)
        
    def clear_shortcuts(self):
        """Clear all shortcuts"""
        while self.shortcuts_layout.count() > 0:
            item = self.shortcuts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
    def show_at(self, parent_widget: QWidget):
        """Show popup above the parent widget"""
        # Calculate position
        parent_pos = parent_widget.mapToGlobal(QPoint(0, 0))
        
        # Show first to get correct size
        self.show()
        self.adjustSize()
        
        # Position above parent with left alignment
        x = parent_pos.x()  # Align left edge with parent button
        y = parent_pos.y() - self.height() - 5
        
        # Ensure popup stays within screen bounds
        screen = QApplication.primaryScreen().geometry()
        if x < 0:
            x = 0
        elif x + self.width() > screen.width():
            x = screen.width() - self.width()
            
        if y < 0:
            # Show below if no space above
            y = parent_pos.y() + parent_widget.height() + 5
            
        self.move(x, y)
        
        # Don't auto-hide on hover show
        self.hide_timer.stop()
        
    def enterEvent(self, event):
        """Mouse entered popup"""
        self.mouse_over = True
        self.hide_timer.stop()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        """Mouse left popup"""
        self.mouse_over = False
        self.hide_timer.start(500)  # Hide after 500ms
        super().leaveEvent(event)
    
    def eventFilter(self, obj, event):
        """Filter events to detect clicks outside popup"""
        from PyQt6.QtCore import QEvent
        
        # Handle mouse press events
        if event.type() == QEvent.Type.MouseButtonPress:
            # Check if click is outside the popup
            if self.isVisible() and not self.geometry().contains(event.globalPosition().toPoint()):
                # Get the widget at the click position
                click_pos = event.globalPosition().toPoint()
                widget_at_pos = QApplication.widgetAt(click_pos)
                
                # If clicking on a button (history, mode, etc), hide popup but don't consume event
                # This allows the button's click handler to execute
                if widget_at_pos and isinstance(widget_at_pos, QPushButton):
                    self.hide()
                    return False  # Don't consume event, let button handle it
                else:
                    self.hide()
                    return True  # Consume event for other clicks
        
        return super().eventFilter(obj, event)
    
    def showEvent(self, event):
        """Install event filter when showing"""
        super().showEvent(event)
        # Install event filter on application to detect clicks
        QApplication.instance().installEventFilter(self)
    
    def hideEvent(self, event):
        """Remove event filter when hiding"""
        super().hideEvent(event)
        # Remove event filter
        QApplication.instance().removeEventFilter(self)


class ExpandableIconButton(QPushButton):
    """Icon button that expands to show text on hover"""
    
    def __init__(self, icon_path: str, text: str, url: str, name: str = "", parent=None):
        super().__init__(parent)
        self.icon_path = icon_path
        self.full_text = text
        self.url = url
        self.name = name  # Store the website name
        self.expanded = False
        self._animation_callback = None
        self.has_icon = False
        
        # Try to set icon
        try:
            print(f"[ExpandableIconButton] Attempting to load icon from: {icon_path}")
            if icon_path and os.path.exists(icon_path):
                print(f"[ExpandableIconButton] File exists at {icon_path}")
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    print(f"[ExpandableIconButton] Pixmap loaded successfully, size: {pixmap.size()}")
                    self.setIcon(QIcon(pixmap))
                    self.has_icon = True
                    self.setText("")  # Initially show icon only
                else:
                    print(f"[ExpandableIconButton] Failed to load pixmap from {icon_path} - pixmap is null")
            else:
                print(f"[ExpandableIconButton] File does not exist at {icon_path}")
        except Exception as e:
            print(f"[ExpandableIconButton] Exception loading icon {icon_path}: {e}")
        
        # If no icon, show full name
        if not self.has_icon and self.name:
            # Show full name
            self.setText(self.name)
        
        self.setIconSize(QSize(20, 20))
        self.setFixedHeight(28)
        # Adjust minimum width based on content
        if self.has_icon:
            self.setMinimumWidth(28)
        else:
            # Calculate width based on text
            fm = self.fontMetrics()
            text_width = fm.horizontalAdvance(self.name) if hasattr(fm, 'horizontalAdvance') else fm.width(self.name)
            self.setMinimumWidth(text_width + 20)  # Add padding
        
        # Animation for width
        self.animation = QPropertyAnimation(self, b"minimumWidth")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Styling
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 14px;
                padding: 0 8px;
                font-size: 13px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                border-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        """)
        
    def enterEvent(self, event):
        """Expand to show text on hover"""
        if not self.expanded:
            self.expanded = True
            # Stop any ongoing animation
            self.animation.stop()
            # Disconnect any existing connections
            try:
                self.animation.finished.disconnect()
            except:
                pass
            
            # Show full text with or without icon
            if self.has_icon:
                self.setText(f"  {self.full_text}")
            else:
                self.setText(self.full_text)
            
            self.animation.setStartValue(self.minimumWidth())
            self.animation.setEndValue(140)
            self.animation.start()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        """Collapse to show icon only"""
        if self.expanded:
            self.expanded = False
            # Stop any ongoing animation
            self.animation.stop()
            # Disconnect any existing connections
            try:
                self.animation.finished.disconnect()
            except:
                pass
            
            # Create callback function
            def clear_text():
                if not self.expanded:  # Double check we're still collapsed
                    if self.has_icon:
                        self.setText("")
                    else:
                        # Show full name for non-icon buttons
                        self.setText(self.name)
            
            # Connect new callback
            self.animation.finished.connect(clear_text)
            self.animation.setStartValue(self.minimumWidth())
            self.animation.setEndValue(28)
            self.animation.start()
        super().leaveEvent(event)


class WindowMode(Enum):
    """Window display modes"""
    MINI = "mini"
    CHAT = "chat"
    WIKI = "wiki"


class MessageType(Enum):
    """Chat message types"""
    USER_QUERY = "user_query"
    AI_RESPONSE = "ai_response"
    AI_STREAMING = "ai_streaming"
    WIKI_LINK = "wiki_link"
    TRANSITION = "transition"


@dataclass
class ChatMessage:
    """Single chat message"""
    type: MessageType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# To allow class attributes to dynamically return translations, we use a metaclass
class TransitionMessagesMeta(type):
    """Metaclass for dynamically handling TransitionMessages attribute access"""
    
    def __getattribute__(cls, name):
        # Map old attribute names to new translation keys
        attribute_mapping = {
            'WIKI_SEARCHING': 'status_wiki_searching',
            'WIKI_FOUND': 'status_wiki_found', 
            'GUIDE_SEARCHING': 'status_guide_searching',
            'GUIDE_GENERATING': 'status_guide_generating',
            'ERROR_NOT_FOUND': 'status_error_not_found',
            'ERROR_TIMEOUT': 'status_error_timeout',
            'QUERY_RECEIVED': 'status_query_received',
            'DB_SEARCHING': 'status_db_searching',
            'AI_SUMMARIZING': 'status_ai_summarizing',
            'COMPLETED': 'status_completed'
        }
        
        if name in attribute_mapping:
            return t(attribute_mapping[name])
        
        # For other attributes, use default behavior
        return super().__getattribute__(name)

class TransitionMessages(metaclass=TransitionMessagesMeta):
    """Predefined transition messages with i18n support"""
    
    def __new__(cls):
        # Prevent instantiation, this class should only be used for static access
        raise TypeError(f"{cls.__name__} should not be instantiated")
    
    # Static method versions for use when needed
    @staticmethod
    def get_wiki_searching():
        return t("status_wiki_searching")
    
    @staticmethod 
    def get_wiki_found():
        return t("status_wiki_found")
    
    @staticmethod
    def get_guide_searching():
        return t("status_guide_searching")
    
    @staticmethod
    def get_guide_generating():
        return t("status_guide_generating")
    
    @staticmethod
    def get_error_not_found():
        return t("status_error_not_found")
    
    @staticmethod
    def get_error_timeout():
        return t("status_error_timeout")
    
    @staticmethod
    def get_query_received():
        return t("status_query_received")
    
    @staticmethod
    def get_db_searching():
        return t("status_db_searching")
    
    @staticmethod
    def get_ai_summarizing():
        return t("status_ai_summarizing")
    
    @staticmethod
    def get_completed():
        return t("status_completed")


def detect_markdown_content(text: str) -> bool:
    """
    Detect if text contains markdown format or HTML format
    
    Args:
        text: Text to detect
        
    Returns:
        True if text contains markdown or HTML format, False otherwise
    """
    if not text:
        return False
        
    # Detect common markdown patterns
    markdown_patterns = [
        r'\*\*.*?\*\*',  # Bold **text**
        r'\*.*?\*',      # Italic *text*
        r'#{1,6}\s',     # Headers # ## ### etc.
        r'^\s*[-\*\+]\s', # Unordered lists
        r'^\s*\d+\.\s',  # Ordered lists
        r'`.*?`',        # Inline code
        r'```.*?```',    # Code blocks
        r'\[.*?\]\(.*?\)', # Links [text](url)
    ]
    
    # Detect HTML tags (especially those used in video sources)
    html_patterns = [
        r'<small.*?>.*?</small>',  # <small> tags
        r'<a\s+.*?href.*?>.*?</a>', # <a> link tags
        r'<[^>]+>',  # Other HTML tags
        r'📺\s*\*\*info source：\*\*',  # Video source title
        r'---\s*\n\s*<small>',  # Markdown separator + HTML
        r'\n\n<small>.*?来源.*?</small>',  # Generic source pattern
        r'<br\s*/?>',  # <br> tags
        r'<strong>.*?</strong>',  # <strong> tags
        r'<em>.*?</em>',  # <em> tags
        r'<code>.*?</code>',  # <code> tags
        r'<pre>.*?</pre>',  # <pre> tags
    ]
    
    # Check markdown patterns
    for pattern in markdown_patterns:
        if re.search(pattern, text, re.MULTILINE | re.DOTALL):
            return True
    
    # Check HTML patterns        
    for pattern in html_patterns:
        if re.search(pattern, text, re.MULTILINE | re.DOTALL):
            return True
            
    return False


def convert_markdown_to_html(text: str) -> str:
    """
    Convert markdown text to HTML while preserving existing HTML tags
    
    Args:
        text: Markdown text or mixed HTML content
        
    Returns:
        Converted HTML text
    """
    if not text:
        return text
        
    try:
        # Check if HTML tags are present (especially in video source sections)
        has_html_tags = bool(re.search(r'<[^>]+>', text, re.MULTILINE | re.DOTALL))
        
        if has_html_tags:
            # Check if it's mixed content (Markdown + HTML video sources)
            # Improvement: Use more flexible video source recognition
            video_source_patterns = [
                r'---\s*\n\s*<small>',  # Original pattern
                r'📺\s*\*\*info source：\*\*',  # Video source title pattern  
                r'\n\n<small>.*?来源.*?</small>',  # Generic source pattern
                r'\n\n---\n\s*<small>',  # Add more flexible separator pattern
            ]
            
            video_source_start = -1
            used_pattern = None
            
            for pattern in video_source_patterns:
                match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
                if match:
                    video_source_start = match.start()
                    used_pattern = pattern
                    break
            
            if video_source_start != -1:
                # Separate Markdown and HTML parts
                markdown_content = text[:video_source_start].strip()
                html_content = text[video_source_start:].strip()
                
                # Process Markdown part
                processed_markdown = ""
                if markdown_content:
                    if MARKDOWN_AVAILABLE:
                        # Use markdown library
                        available_extensions = []
                        try:
                            import markdown.extensions.extra
                            available_extensions.append('extra')
                        except ImportError:
                            pass
                        try:
                            import markdown.extensions.nl2br
                            available_extensions.append('nl2br')
                        except ImportError:
                            pass
                        
                        if available_extensions:
                            md = markdown.Markdown(extensions=available_extensions)
                        else:
                            md = markdown.Markdown()
                        
                        processed_markdown = md.convert(markdown_content)
                    else:
                        # When markdown library is not available, process basic formats
                        processed_markdown = markdown_content.replace('\n', '<br/>')
                        processed_markdown = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', processed_markdown)
                        processed_markdown = re.sub(r'\*(.*?)\*', r'<em>\1</em>', processed_markdown)
                        processed_markdown = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', processed_markdown)
                
                # Process HTML part, ensure correct formatting
                processed_html = html_content
                if html_content:
                    # Clean up possible markdown separators
                    processed_html = re.sub(r'^---\s*\n\s*', '', processed_html, flags=re.MULTILINE)
                    processed_html = processed_html.strip()
                    
                    # Process markdown links in video sources
                    processed_html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', processed_html)
                
                # Combine processed content
                combined_content = processed_markdown
                if processed_html:
                    # Add appropriate spacing
                    if combined_content and not combined_content.endswith('<br/>'):
                        combined_content += '<br/><br/>'
                    combined_content += processed_html
                
                # Apply style wrapper
                styled_html = f"""
                <div style="
                    font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 100%;
                    word-wrap: break-word;
                ">
                    {combined_content}
                </div>
                """
                return styled_html
            else:
                # Pure HTML content, but still need to process markdown links
                processed_text = text
                # Process markdown links
                processed_text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', processed_text)
                
                styled_html = f"""
                <div style="
                    font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 100%;
                    word-wrap: break-word;
                ">
                    {processed_text}
                </div>
                """
                return styled_html
        
        # If no HTML tags, perform regular markdown processing
        if not MARKDOWN_AVAILABLE:
            # When markdown library is not available, at least process some basic formats
            html = text.replace('\n', '<br/>')
            # Process bold
            html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
            # Process italic
            html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
            # Process links
            html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
        else:
            # Use markdown library
            # Configure markdown converter, use basic extensions (avoid dependencies that may not exist)
            available_extensions = []
            
            # Try to add available extensions
            try:
                import markdown.extensions.extra
                available_extensions.append('extra')
            except ImportError:
                pass
                
            try:
                import markdown.extensions.nl2br
                available_extensions.append('nl2br')
            except ImportError:
                pass
                
            # If no extensions available, use basic configuration
            if available_extensions:
                md = markdown.Markdown(extensions=available_extensions)
            else:
                md = markdown.Markdown()
            
            # Convert markdown to HTML
            html = md.convert(text)
        
        # Add some basic styles to make HTML display better
        styled_html = f"""
        <div style="
            font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 100%;
            word-wrap: break-word;
        ">
            {html}
        </div>
        """
        
        return styled_html
        
    except Exception as e:
        # Only output error information when conversion fails
        print(f"❌ [RENDER-ERROR] Markdown conversion failed: {e}")
        return text


class MiniAssistant(QWidget):
    """Circular mini assistant window"""
    
    clicked = pyqtSignal()
    visibility_changed = pyqtSignal(bool)  # Signal for visibility state changes
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(60, 60)
        
        # Position at screen edge
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 80, screen.height() // 2 - 30)
        
        # Animation setup
        self.hover_animation = QPropertyAnimation(self, b"geometry")
        self.hover_animation.setDuration(150)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Drag support
        self.dragging = False
        self.drag_position = None
        
    def paintEvent(self, event):
        """Draw the circular assistant"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Shadow effect
        shadow_color = QColor(0, 0, 0, 30)
        for i in range(3):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow_color)
            painter.drawEllipse(2 + i, 2 + i, 56 - 2*i, 56 - 2*i)
        
        # Main circle with gradient
        gradient = QLinearGradient(0, 0, 60, 60)
        gradient.setColorAt(0, QColor(70, 130, 255, 200))
        gradient.setColorAt(1, QColor(100, 150, 255, 200))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(255, 255, 255, 100), 2))
        painter.drawEllipse(5, 5, 50, 50)
        
        # Icon text
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 16, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "AI")
        
    def contextMenuEvent(self, event):
        """Handle right-click menu event"""
        menu = QMenu(self)
        hide_action = menu.addAction(t("menu_hide_overlay"))
        hide_action.triggered.connect(self._on_hide_requested)
        menu.exec(event.globalPos())
        
    def _on_hide_requested(self):
        """Handle hide request from context menu"""
        self.hide()
        self.visibility_changed.emit(False)
        
    def mousePressEvent(self, event):
        import logging
        logger = logging.getLogger(__name__)
        logger.info("MiniAssistant: mousePressEvent triggered")
        
        if event.button() == Qt.MouseButton.LeftButton:
            logger.info("MiniAssistant: Left button pressed, starting drag")
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.click_time = event.timestamp()
            
    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            
    def mouseReleaseEvent(self, event):
        import logging
        logger = logging.getLogger(__name__)
        logger.info("MiniAssistant: mouseReleaseEvent triggered")
        
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if it was a click (not drag)
            time_diff = event.timestamp() - self.click_time
            logger.info(f"MiniAssistant: Time diff: {time_diff}ms")
            
            if time_diff < 200:  # 200ms threshold
                drag_distance = (event.globalPosition().toPoint() - 
                               (self.frameGeometry().topLeft() + self.drag_position)).manhattanLength()
                logger.info(f"MiniAssistant: Drag distance: {drag_distance}px")
                
                if drag_distance < 5:  # 5 pixel threshold
                    logger.info("MiniAssistant: Emitting clicked signal")
                    self.clicked.emit()
                else:
                    logger.info("MiniAssistant: Not a click - drag distance too large")
            else:
                logger.info("MiniAssistant: Not a click - time too long")
            
            self.dragging = False
            
    def enterEvent(self, event):
        """Hover effect - slight enlargement"""
        current = self.geometry()
        expanded = QRect(
            current.x() - 5,
            current.y() - 5,
            current.width() + 10,
            current.height() + 10
        )
        self.hover_animation.setStartValue(current)
        self.hover_animation.setEndValue(expanded)
        self.hover_animation.start()
        
    def leaveEvent(self, event):
        """Reset size on hover leave"""
        current = self.geometry()
        normal = QRect(
            current.x() + 5,
            current.y() + 5,
            60,
            60
        )
        self.hover_animation.setStartValue(current)
        self.hover_animation.setEndValue(normal)
        self.hover_animation.start()


class StatusMessageWidget(QFrame):
    """Message component specifically for displaying status information"""
    
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.current_message = message
        
        # Initialize animation properties (must be before init_ui as update_display is called in init_ui)
        self.animation_dots = 0
        
        self.init_ui()
        
        # Animation timer
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_timer.start(500)  # Update animation every 500ms
        
    def init_ui(self):
        """Initialize status message UI"""
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Create status bubble
        bubble = QFrame()
        bubble.setObjectName("statusBubble")
        bubble.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        
        # Status text label
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum
        )
        
        # Set status style
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                line-height: 1.5;
                font-family: "Segoe UI", "Microsoft YaHei", Arial;
                background-color: transparent;
                border: none;
                padding: 0;
                color: #666;
                font-style: italic;
            }
        """)
        
        # Set bubble style
        bubble.setStyleSheet("""
            QFrame#statusBubble {
                background-color: rgba(240, 248, 255, 200);
                border: 1px solid rgba(224, 232, 240, 150);
                border-radius: 18px;
                padding: 4px;
            }
        """)
        
        bubble_layout.addWidget(self.status_label)
        layout.addWidget(bubble)
        layout.addStretch()
        
        # Override context menu for proper styling
        self.status_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status_label.customContextMenuRequested.connect(self._show_context_menu)
        
        self.update_display()
        
    def update_status(self, new_message: str):
        """Update status information"""
        self.current_message = new_message
        self.animation_dots = 0  # Reset animation
        self.update_display()
        # Ensure animation continues running
        if not self.animation_timer.isActive():
            self.animation_timer.start(500)
        
    def update_animation(self):
        """Update animation effect"""
        self.animation_dots = (self.animation_dots + 1) % 4
        self.update_display()
        
    def update_display(self):
        """Update display content"""
        dots = "." * self.animation_dots
        display_text = f"{self.current_message}{dots}"
        self.status_label.setText(display_text)
        self.status_label.adjustSize()
        self.adjustSize()
        
        # Ensure parent container also updates layout
        if self.parent():
            self.parent().adjustSize()
        
    def stop_animation(self):
        """Stop animation"""
        if self.animation_timer.isActive():
            self.animation_timer.stop()
            
    def hide_with_fadeout(self):
        """Hide with fade out"""
        self.stop_animation()
        # Simple hide, can add fade out animation later
        self.hide()
    
    def _show_context_menu(self, pos):
        """Show custom context menu for the label"""
        # Create a new menu instead of using createStandardContextMenu
        menu = QMenu(self)
        
        # Add standard actions manually
        if self.status_label.selectedText():
            copy_action = menu.addAction("Copy")
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(self.status_label.selectedText())
            )
        
        # Show the menu
        global_pos = self.status_label.mapToGlobal(pos)
        menu.exec(global_pos)


class MessageWidget(QFrame):
    """Individual chat message widget"""
    
    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(parent)
        self.message = message
        self.init_ui()
        
    def init_ui(self):
        """Initialize the message UI"""
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,  # 改为Expanding以占满可用width
            QSizePolicy.Policy.Minimum
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Create message bubble
        bubble = QFrame()
        bubble.setObjectName("messageBubble")
        bubble.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        # Set the maximum width to 80% of the parent container to leave margins
        bubble.setMaximumWidth(9999)  # Set a large value initially, will be dynamically adjusted later
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        
        # Use QLabel for better auto-sizing
        self.content_label = QLabel()
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.content_label.setOpenExternalLinks(False)
        self.content_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.MinimumExpanding
        )
        
        # Set content based on message type
        if self.message.type == MessageType.WIKI_LINK:
            url = self.message.metadata.get('url', '')
            html_content = (
                f'[LINK] <a href="{url}" style="color: #4096ff;">{url}</a><br/>'
                f'<span style="color: #666; margin-left: 20px;">{self.message.content}</span>'
            )
            self.content_label.setText(html_content)
            self.content_label.setTextFormat(Qt.TextFormat.RichText)
        elif self.message.type == MessageType.AI_RESPONSE:
            # AI response may contain markdown format, need to detect and convert
            if detect_markdown_content(self.message.content):
                # Convert markdown to HTML
                html_content = convert_markdown_to_html(self.message.content)
                self.content_label.setText(html_content)
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
                # AI response may contain links, need to connect linkActivated signal
                self.content_label.setOpenExternalLinks(False)  # Ensure using signal processing
                self.content_label.linkActivated.connect(self.on_link_clicked)
            else:
                # Plain text
                self.content_label.setText(self.message.content)
                self.content_label.setTextFormat(Qt.TextFormat.PlainText)
        else:
            self.content_label.setText(self.message.content)
            self.content_label.setTextFormat(Qt.TextFormat.PlainText)
            
        # Style the label based on message type
        if self.message.type == MessageType.USER_QUERY:
            self.content_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    line-height: 1.5;
                    font-family: "Segoe UI", "Microsoft YaHei", Arial;
                    background-color: transparent;
                    border: none;
                    padding: 0;
                    color: white;
                }
            """)
        else:
            self.content_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    line-height: 1.5;
                    font-family: "Segoe UI", "Microsoft YaHei", Arial;
                    background-color: transparent;
                    border: none;
                    padding: 0;
                    color: #333;
                }
            """)
        
        # Style based on message type
        if self.message.type == MessageType.USER_QUERY:
            # Right-aligned user message
            layout.addStretch()
            bubble.setStyleSheet("""
                QFrame#messageBubble {
                    background-color: rgba(64, 150, 255, 220);
                    border-radius: 18px;
                    color: white;
                    padding: 4px;
                    border: 1px solid rgba(64, 150, 255, 100);
                }
            """)
            # Style is already set above for QTextEdit
        else:
            # Left-aligned AI/system message
            # Wiki link handling is done above in content setting
            
            bubble.setStyleSheet("""
                QFrame#messageBubble {
                    background-color: rgba(255, 255, 255, 200);
                    border-radius: 18px;
                    padding: 4px;
                    border: 1px solid rgba(224, 224, 224, 150);
                }
            """)
            layout.addWidget(bubble)
            layout.addStretch()
            
        bubble_layout.addWidget(self.content_label)
        
        # Override context menu for proper styling
        self.content_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.content_label.customContextMenuRequested.connect(self._show_context_menu)
        
        if self.message.type == MessageType.USER_QUERY:
            layout.addWidget(bubble)
            
        # Handle link clicks for wiki messages
        if self.message.type == MessageType.WIKI_LINK:
            self.content_label.linkActivated.connect(self.on_link_clicked)
            
        # Set initial width
        self._set_initial_width()
            
    def _set_initial_width(self):
        """Set initial width of message, based on parent container"""
        # This method will be overridden by _update_message_width method after adding to chat view
        # But can provide a reasonable initial value
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            bubble.setMaximumWidth(500)  # Set a reasonable initial maximum width
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            
    def on_link_clicked(self, url):
        """Handle wiki link clicks"""
        logger = logging.getLogger(__name__)
        print(f"🔗 [LINK-DEBUG] Link clicked: {url}")
        print(f"🔗 [LINK-DEBUG] Message type: {self.message.type}")
        print(f"🔗 [LINK-DEBUG] Is streaming message: {isinstance(self, StreamingMessageWidget)}")
        print(f"🔗 [LINK-DEBUG] content_label format: {self.content_label.textFormat()}")
        print(f"🔗 [LINK-DEBUG] openExternalLinks: {self.content_label.openExternalLinks()}")
        
        logger.info(f"🔗 WikiLink clicked: {url}")
        logger.info(f"Message content: {self.message.content}")
        logger.info(f"Message metadata: {self.message.metadata}")
        
        # Optimize title passing: use message content first, if empty then extract from URL
        title = self.message.content
        if not title or title.strip() == "":
            # If no title, extract from URL
            try:
                from urllib.parse import unquote
                title = unquote(url.split('/')[-1]).replace('_', ' ')
            except:
                title = "Wiki页面"
        
        logger.info(f"Using title: {title}")
        print(f"🔗 [LINK-DEBUG] Using title: {title}")
        
        # Find ChatView instance upwards
        chat_view = self._find_chat_view()
        if chat_view:
            logger.info(f"Found ChatView instance, calling show Wiki page")
            print(f"🔗 [LINK-DEBUG] Found ChatView instance, calling show Wiki page")
            chat_view.show_wiki(url, title)
        else:
            logger.warning(f"ChatView instance not found")
            print(f"🔗 [LINK-DEBUG] ❌ ChatView instance not found")
            
    def _find_chat_view(self):
        """Find ChatView instance upwards"""
        parent = self.parent()
        while parent:
            if isinstance(parent, ChatView):
                return parent
            parent = parent.parent()
        return None
        
    def update_content(self, new_content: str):
        """Update message content"""
        self.message.content = new_content
        
        # If AI response, detect and convert markdown
        if self.message.type == MessageType.AI_RESPONSE:
            if detect_markdown_content(new_content):
                html_content = convert_markdown_to_html(new_content)
                self.content_label.setText(html_content)
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
            else:
                self.content_label.setText(new_content)
                self.content_label.setTextFormat(Qt.TextFormat.PlainText)
        else:
            self.content_label.setText(new_content)
            
        self.content_label.adjustSize()
        self.adjustSize()
    
    def _show_context_menu(self, pos):
        """Show custom context menu for the label"""
        # Create a new menu instead of using createStandardContextMenu
        menu = QMenu(self)
        
        # Add standard actions manually
        if self.content_label.selectedText():
            copy_action = menu.addAction("Copy")
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(self.content_label.selectedText())
            )
        
        # Show the menu
        global_pos = self.content_label.mapToGlobal(pos)
        menu.exec(global_pos)

class StreamingMessageWidget(MessageWidget):
    """Message widget with streaming/typing animation support"""
    
    # Add signal
    streaming_finished = pyqtSignal()  # Signal for streaming completion
    
    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(message, parent)
        self.full_text = ""
        self.display_index = 0
        self.is_stopped = False  # Flag indicating if stopped by user
        
        # Markdown rendering control - ensure re-initialization each time
        self.last_render_index = 0  # Last render character position
        self.render_interval = 50   # Render markdown every 50 characters (reduce frequency to avoid flickering)
        self.last_render_time = 0   # Last render time
        self.render_time_interval = 1.0  # Maximum 1.0 second between renders
        self.is_markdown_detected = False  # Cache markdown detection result - force reset
        self.current_format = Qt.TextFormat.PlainText  # Current text format - force reset
        self.link_signal_connected = False  # Track if linkActivated signal is connected - force reset
        self.has_video_source = False  # Track if video source has been detected - force reset
        self.force_render_count = 0  # Force render counter
        
        # Optimize streaming message layout to prevent flickering
        self._optimize_for_streaming()
        
        # Set default render parameters (more sensitive detection)
        self.set_render_params(char_interval=50, time_interval=1.0)
        
        # Typing animation timer
        self.typing_timer = QTimer()
        self.typing_timer.timeout.connect(self.show_next_char)
        # Ensure timer is stopped during initialization
        self.typing_timer.stop()
        
        # Loading dots animation
        self.dots_timer = QTimer()
        self.dots_count = 0
        self.dots_timer.timeout.connect(self.update_dots)
        self.dots_timer.start(500)
        
        # Add debug logs
        print(f"🔧 [STREAMING] New StreamingMessageWidget initialization completed, timer status: {'Active' if self.typing_timer.isActive() else 'Inactive'}")
        
        # Configure link handling during initialization
        if hasattr(self, 'content_label'):
            self.content_label.setOpenExternalLinks(False)  # Ensure signal handling instead of direct opening
            # Pre-connect linkActivated signal to avoid connection issues during streaming
            try:
                self.content_label.linkActivated.connect(self.on_link_clicked)
                self.link_signal_connected = True
                print(f"🔗 [STREAMING] linkActivated signal already connected during initialization")
            except Exception as e:
                print(f"⚠️ [STREAMING] Failed to connect linkActivated signal during initialization: {e}")
                self.link_signal_connected = False
    
    def _optimize_for_streaming(self):
        """Optimize streaming message layout to prevent flickering"""
        # Find message bubble
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            # Use MinimumExpanding policy to allow content to expand freely
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        
        # Optimize content_label settings
        if hasattr(self, 'content_label'):
            # Use MinimumExpanding policy to allow content to expand freely
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            # Set text wrapping
            self.content_label.setWordWrap(True)
            self.content_label.setScaledContents(False)
            
        # Initial width setup (based on parent container)
        self._update_bubble_width()
        
        # Fix initial width for streaming messages to avoid layout jumping
        self._fix_width_for_streaming()
    
    def _update_bubble_width(self):
        """Dynamically set dialog width based on chat window width"""
        # Get chat view width, considering scrollbar width
        parent_widget = self.parent()
        
        # Try to use get_chat_view, but may not be available during initialization
        if hasattr(self, 'get_chat_view'):
            chat_view = self.get_chat_view()
        else:
            chat_view = parent_widget if parent_widget and hasattr(parent_widget, 'viewport') else None
            
        if chat_view and hasattr(chat_view, 'viewport'):
            viewport_width = chat_view.viewport().width()
            # Subtract scrollbar width (usually about 20px)
            if hasattr(chat_view, 'verticalScrollBar'):
                scrollbar = chat_view.verticalScrollBar()
                if scrollbar and scrollbar.isVisible():
                    viewport_width -= scrollbar.width()
        else:
            # If unable to get chat view width, try to get from parent container
            viewport_width = parent_widget.width() if parent_widget else 500
        
        # Ensure valid width
        viewport_width = max(300, viewport_width)
        
        # Calculate dialog width (75% of chat view width, reduce ratio to avoid too wide, but not exceed 600px, not less than 300px)
        bubble_width = max(300, min(600, int(viewport_width * 0.75)))
        content_width = bubble_width - 24  # Subtract margins
        
        # Save calculated width for later use
        self._calculated_bubble_width = bubble_width
        self._calculated_content_width = content_width
        
        # Update bubble and content width - use maximum width instead of fixed width
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            bubble.setMaximumWidth(bubble_width)
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            
        if hasattr(self, 'content_label'):
            self.content_label.setMaximumWidth(content_width)
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            
        # Only output debug information in abnormal cases
        if chat_view and hasattr(chat_view, 'viewport'):
            original_viewport_width = chat_view.viewport().width()
            # Only output warning when width is abnormally small
            if original_viewport_width < 400:
                print(f"⚠️ Streaming message view width abnormal: viewport={original_viewport_width}px")
    
    def _fix_width_for_streaming(self):
        """Fix width for streaming messages to avoid layout jumping"""
        if not hasattr(self, '_calculated_bubble_width'):
            return
            
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            # Use fixed width instead of maximum width
            bubble.setFixedWidth(self._calculated_bubble_width)
            print(f"🔒 [STREAMING] Fixed bubble width: {self._calculated_bubble_width}px")
            
        if hasattr(self, 'content_label'):
            # Content label also uses fixed width
            self.content_label.setFixedWidth(self._calculated_content_width)
            # Set minimum height to avoid vertical jumping
            self.content_label.setMinimumHeight(30)
            print(f"🔒 [STREAMING] Fixed content width: {self._calculated_content_width}px")
            
        # Mark width as fixed
        self._width_fixed = True
    
    def _restore_flexible_width(self):
        """Restore flexible width settings (called after streaming ends)"""
        if not hasattr(self, '_width_fixed') or not self._width_fixed:
            return
            
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble and hasattr(self, '_calculated_bubble_width'):
            # Remove fixed width, restore maximum width limit
            bubble.setMinimumWidth(0)
            bubble.setMaximumWidth(self._calculated_bubble_width)
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            print(f"🔓 [STREAMING] Restored bubble flexible width, max: {self._calculated_bubble_width}px")
            
        if hasattr(self, 'content_label') and hasattr(self, '_calculated_content_width'):
            # Remove fixed width, restore maximum width limit
            self.content_label.setMinimumWidth(0)
            self.content_label.setMaximumWidth(self._calculated_content_width)
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            print(f"🔓 [STREAMING] Restored content flexible width, max: {self._calculated_content_width}px")
            
        # Mark flexible width as restored
        self._width_fixed = False
        
    def get_chat_view(self):
        """Get parent ChatView (if exists)"""
        try:
            parent = self.parent()
            # Check if parent is ChatView (by checking specific methods)
            if parent and hasattr(parent, 'request_auto_scroll') and hasattr(parent, 'verticalScrollBar'):
                return parent
        except:
            pass
        return None
    
    def set_render_params(self, char_interval: int = 50, time_interval: float = 1.0):
        """
        Set markdown rendering parameters
        
        Args:
            char_interval: Character interval, how many characters between renders
            time_interval: Time interval, maximum seconds between renders
        """
        self.render_interval = max(20, char_interval)  # Minimum 20 characters
        self.render_time_interval = max(0.5, time_interval)  # Minimum 0.5 seconds
        
    def append_chunk(self, chunk: str):
        """Append text chunk for streaming display"""
        # Stricter stop check, return without processing
        if self.is_stopped:
            print(f"🛑 Streaming message stopped, rejecting new content chunk: '{chunk[:50]}...'")
            return
        
        # Record timer status for debugging
        timer_was_active = self.typing_timer.isActive()
        
        self.full_text += chunk
        print(f"✅ [STREAMING-WIDGET] Full text updated, new length: {len(self.full_text)}")
        
        # Improved initial detection logic:
        # 1. Remove timer check restriction, ensure each new message can perform initial detection
        # 2. Lower length limit, detect markdown early
        if not timer_was_active:
            self.dots_timer.stop()
            # Initialize render timestamp
            self.last_render_time = time.time()
            
        # Perform markdown detection for each new chunk (not just the first one)
        # Use cache to avoid repeated detection of same content
        if not self.is_markdown_detected and len(self.full_text) > 5:  # Lower length limit
            self.is_markdown_detected = detect_markdown_content(self.full_text)
            # If markdown is detected, perform initial render immediately
            if self.is_markdown_detected:
                print(f"🔍 [STREAMING] Initially detected markdown format, length: {len(self.full_text)}")
                print(f"📋 [STREAMING] Timer status: {'Active' if timer_was_active else 'Inactive'}")
                print(f"📝 [STREAMING] First 50 characters: {self.full_text[:50]}...")
                # Set correct format immediately
                self.current_format = Qt.TextFormat.RichText
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
                
        # Ensure timer starts
        if not self.typing_timer.isActive():
            print(f"⏰ [STREAMING-WIDGET] Started typewriter timer")
            # Faster typewriter effect: 5ms per character (previously 20ms)
            self.typing_timer.start(5)
        else:
            print(f"⏰ [STREAMING-WIDGET] Typewriter timer already running")
    
    def _adjust_typing_speed(self):
        """Dynamically adjust typewriter speed"""
        remaining_chars = len(self.full_text) - self.display_index
        
        # If many remaining characters, speed up display
        if remaining_chars > 500:
            # Large amount of remaining content, very fast speed
            new_interval = 1
        elif remaining_chars > 200:
            # Medium remaining content, fast speed
            new_interval = 2
        elif remaining_chars > 50:
            # Small amount of remaining content, normal speed
            new_interval = 3
        else:
            # Very little remaining content, slow speed to maintain typewriter effect
            new_interval = 5
            
        # Check if timer interval needs adjustment
        if self.typing_timer.isActive():
            current_interval = self.typing_timer.interval()
            if current_interval != new_interval:
                print(f"🚀 [TYPING] Adjusted typing speed: {current_interval}ms -> {new_interval}ms, Remaining: {remaining_chars}characters")
                self.typing_timer.setInterval(new_interval)
    
    def mark_as_stopped(self):
        """Mark as stopped"""
        self.is_stopped = True
        self.typing_timer.stop()
        self.dots_timer.stop()
        
        # Add stop marker at current position
        if self.display_index < len(self.full_text):
            stopped_text = self.full_text[:self.display_index] + "\n\n*[Generation stopped by user]*"
        else:
            stopped_text = self.full_text + "\n\n*[Generation stopped by user]*"
            
        # Immediately display all generated text plus stop marker
        self.content_label.setText(stopped_text)
        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
        
        # Convert Message type to AI_RESPONSE
        self.message.type = MessageType.AI_RESPONSE
        
        print(f"🛑 Streaming message stopped, display position: {self.display_index}/{len(self.full_text)}")
            
    def show_next_char(self):
        """Show next character in typing animation"""
        
        # First check if it has been stopped
        if self.is_stopped:
            self.typing_timer.stop()
            print(f"🛑 Typewriter effect detected stop state, immediately terminating")
            return
            
        # Dynamically adjusted typing speed (based on remaining characters)
        self._adjust_typing_speed()
            
        if self.display_index < len(self.full_text):
            self.display_index += 1
            display_text = self.full_text[:self.display_index]
            current_time = time.time()
            
            # Early markdown detection (start detecting at the first 20 characters)
            if self.display_index <= 20 and not self.is_markdown_detected and len(self.full_text) > 5:
                if detect_markdown_content(self.full_text):
                    self.is_markdown_detected = True
                    self.current_format = Qt.TextFormat.RichText
                    self.content_label.setTextFormat(Qt.TextFormat.RichText)
                    print(f"🚀 [STREAMING] Early detected markdown format（{self.display_index}characters），Full text length: {len(self.full_text)}")
            
            # Check if it needs to perform staged markdown rendering
            should_render = False
            
            # Add update buffer check - reduce frequent DOM operations
            should_update_display = False
            
            # Buffer condition 1: Update display every 5 characters (reduce update frequency)
            # But the first 10 characters are immediately displayed, ensuring the user sees the content start
            if self.display_index <= 10 or self.display_index % 5 == 0:
                should_update_display = True
            
            # Buffer condition 2: Encounter line breaks or paragraph ends
            elif display_text and display_text[-1] in ['\n', '.', '。', '!', '！', '?', '？']:
                should_update_display = True
            
            # Buffer condition 3: Must update when characters interval is reached
            if self.display_index - self.last_render_index >= self.render_interval:
                should_render = True
                should_update_display = True
            
            # Condition 2: Time interval reached
            elif current_time - self.last_render_time >= self.render_time_interval:
                should_render = True
                should_update_display = True
            
            # Condition 3: Detect key content boundaries (e.g., video sources start)
            elif not self.has_video_source and ('📺' in display_text[-10:] or 
                  '---\n<small>' in display_text[-20:] or
                  '<small>' in display_text[-10:]):
                should_render = True
                should_update_display = True
                self.has_video_source = True  # Mark as detected video source, avoid duplicate printing
                print(f"🎬 [STREAMING] Detected video source content, triggering render")
            
            # Condition 4: Detect markdown format content (new condition, ensure format content can be rendered)
            elif not self.is_markdown_detected and len(display_text) > 5 and detect_markdown_content(display_text):
                should_render = True
                should_update_display = True
                self.is_markdown_detected = True
                print(f"🔄 [STREAMING] Detected format content, triggering render, current length: {len(display_text)}")
                print(f"📝 [STREAMING] First 50 characters: {display_text[:50]}...")
                # Immediately set the correct format
                self.current_format = Qt.TextFormat.RichText
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
            
            # Condition 5: If markdown is detected, but the current text has no format, re-detect (handle format changes)
            elif self.is_markdown_detected and not detect_markdown_content(display_text):
                # Re-detect the entire text to avoid misjudgment
                if detect_markdown_content(self.full_text):
                    should_render = True
                    print(f"🔄 [STREAMING] Re-detected format content, triggering render")
                else:
                    # If there is no format, reset the state
                    self.is_markdown_detected = False
                    self.current_format = Qt.TextFormat.PlainText
                    print(f"🔄 [STREAMING] Reset to plain text format")
            
            # Condition 6: Force detect format every 100 characters (new, ensure no format content is missed)
            elif self.display_index % 100 == 0 and self.display_index > 0:
                if detect_markdown_content(display_text) and not self.is_markdown_detected:
                    should_render = True
                    self.is_markdown_detected = True
                    print(f"🔄 [STREAMING] Force detected format content, triggering render, position: {self.display_index}")
            
            # Condition 7: If markdown is detected but not yet rendered, force render (new)
            elif self.is_markdown_detected and self.current_format == Qt.TextFormat.PlainText:
                should_render = True
                print(f"🔄 [STREAMING] Force render detected markdown content, position: {self.display_index}")
            
            # Perform rendering processing
            if should_render and self.message.type == MessageType.AI_STREAMING:
                # Re-detect content format (supports dynamic changes, such as adding HTML video sources)
                current_has_format = detect_markdown_content(display_text)
                
                # Perform staged rendering
                if self.is_markdown_detected or current_has_format:
                    html_content = convert_markdown_to_html(display_text)
                    # Only set format when the format actually changes to avoid flickering
                    if self.current_format != Qt.TextFormat.RichText:
                        self.content_label.setTextFormat(Qt.TextFormat.RichText)
                        self.current_format = Qt.TextFormat.RichText
                        print(f"📝 [STREAMING] Switched to RichText format, content length: {len(display_text)}")
                    self.content_label.setText(html_content)
                    
                    # If the linkActivated signal is not yet connected, connect it now
                    if not self.link_signal_connected:
                        self.content_label.linkActivated.connect(self.on_link_clicked)
                        self.link_signal_connected = True
                        print(f"🔗 [STREAMING] linkActivated signal connected")
                        print(f"🔗 [STREAMING] Current content contains links: {'<a href' in html_content}")
                        
                    # Ensure the content label enables link opening
                    self.content_label.setOpenExternalLinks(False)  # Ensure signal processing instead of direct opening
                    print(f"🔗 [STREAMING] Content label config - OpenExternalLinks: {self.content_label.openExternalLinks()}")
                    print(f"🔗 [STREAMING] Content label format: {self.content_label.textFormat()}")
                    
                    # Ensure state consistency
                    self.is_markdown_detected = True
                else:
                    # Only set format when the format actually changes to avoid flickering
                    if self.current_format != Qt.TextFormat.PlainText:
                        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                        self.current_format = Qt.TextFormat.PlainText
                        print(f"📝 [STREAMING] Switched to PlainText format, content length: {len(display_text)}")
                    self.content_label.setText(display_text)
                    
                    # Ensure state consistency
                    self.is_markdown_detected = False
                
                # Update rendering state
                self.last_render_index = self.display_index
                self.last_render_time = current_time
            elif should_update_display:
                # Only update display, not perform full render
                # Use setUpdatesEnabled to reduce flickering
                self.content_label.setUpdatesEnabled(False)
                
                if self.is_markdown_detected:
                    # If markdown/HTML is detected, continue using HTML format
                    html_content = convert_markdown_to_html(display_text)
                    self.content_label.setText(html_content)
                    # Ensure format is set correctly
                    if self.current_format != Qt.TextFormat.RichText:
                        self.content_label.setTextFormat(Qt.TextFormat.RichText)
                        self.current_format = Qt.TextFormat.RichText
                else:
                    # Otherwise use plain text
                    self.content_label.setText(display_text)
                    # Ensure format is set correctly
                    if self.current_format != Qt.TextFormat.PlainText:
                        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                        self.current_format = Qt.TextFormat.PlainText
                
                # Restore updates
                self.content_label.setUpdatesEnabled(True)
            # If neither rendering nor display update is needed, but this is the first 5 characters, force at least one display
            elif self.display_index <= 5:
                print(f"🚀 [DISPLAY] 强制显示前5个characters: display_index={self.display_index}")
                should_update_display = True
                if self.is_markdown_detected:
                    html_content = convert_markdown_to_html(display_text)
                    self.content_label.setText(html_content)
                else:
                    self.content_label.setText(display_text)
                
            # Only scroll when needed (reduce scrolling calls)
            if should_update_display:
                chat_view = self.get_chat_view()
                if chat_view:
                    # Use unified scroll request mechanism
                    chat_view.request_auto_scroll()
        else:
            self.typing_timer.stop()
            
            # When finally completed, convert Message type and perform final render
            if self.message.type == MessageType.AI_STREAMING and self.full_text and not self.is_stopped:
                # Convert Message type to AI_RESPONSE, indicating streaming output is complete
                self.message.type = MessageType.AI_RESPONSE
                
                # Output completion information
                has_video_sources = any(pattern in self.full_text for pattern in [
                    '📺 **info source：**', 
                    '---\n<small>', 
                    '<small>.*?来源.*?</small>'
                ])
                print(f"🎬 [STREAMING] Streaming message completed, length: {len(self.full_text)} characters，Contains video sources: {has_video_sources}")
                
                # Emit completion signal
                self.streaming_finished.emit()
                
                # Perform final format detection and conversion - force re-detection, ignore Cache status
                final_has_format = detect_markdown_content(self.full_text)
                final_has_video_sources = has_video_sources
                
                # If markdown was not detected before, but detected finally, update immediately
                if not self.is_markdown_detected and final_has_format:
                    self.is_markdown_detected = True
                    self.current_format = Qt.TextFormat.RichText
                    print(f"⚡ [STREAMING] Finally detected markdown format, force update render")
                
                print(f"🔄 [STREAMING] Final format detection: markdown={final_has_format}, video={final_has_video_sources}, Cache status={self.is_markdown_detected}")
                
                # Ensure final render uses correct format - based on actual detection results, not Cache status
                if final_has_format or final_has_video_sources:
                    html_content = convert_markdown_to_html(self.full_text)
                    self.content_label.setText(html_content)
                    self.content_label.setTextFormat(Qt.TextFormat.RichText)
                    self.current_format = Qt.TextFormat.RichText
                    self.is_markdown_detected = True  # Update state to match detection result
                    
                    # After streaming output is complete, ensure linkActivated signal is connected (avoid duplicate connections)
                    if not self.link_signal_connected:
                        self.content_label.linkActivated.connect(self.on_link_clicked)
                        self.link_signal_connected = True
                        print(f"🔗 [STREAMING] Connect linkActivated signal during final render")
                        
                    # Ensure content label configuration is correct
                    self.content_label.setOpenExternalLinks(False)  # Ensure signal processing instead of direct opening
                    print(f"🔗 [STREAMING] Final render - content contains links: {'<a href' in html_content}")
                    print(f"🔗 [STREAMING] Final render - OpenExternalLinks: {self.content_label.openExternalLinks()}")
                    print(f"🔗 [STREAMING] Final render - text format: {self.content_label.textFormat()}")
                    
                    print(f"✅ [STREAMING] Final render completed, using RichText format")
                else:
                    self.content_label.setText(self.full_text)
                    self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                    self.current_format = Qt.TextFormat.PlainText
                    self.is_markdown_detected = False  # Update state to match detection result
                    print(f"✅ [STREAMING] Final render completed, using PlainText format")
                
                # After streaming ends, restore flexible width
                self._restore_flexible_width()
                
                # Only perform one full layout update after streaming ends
                self.content_label.updateGeometry()
                self.updateGeometry()
                
                # Ensure parent container also updates layout (delayed execution, avoid blocking)
                chat_view = self.get_chat_view()
                if chat_view and hasattr(chat_view, 'container'):
                    QTimer.singleShot(50, chat_view.container.updateGeometry)
                
                # Request scrolling to the bottom, using unified scroll management
                if chat_view:
                    # Slightly delay to ensure layout is complete
                    QTimer.singleShot(100, chat_view.request_auto_scroll)
            
    def update_dots(self):
        """Update loading dots animation"""
        self.dots_count = (self.dots_count + 1) % 4
        dots = "." * self.dots_count
        self.content_label.setText(f"{self.message.content}{dots}")
    
    def mark_as_completed(self):
        """Mark streaming output as completed, quickly display Remaining content"""
        print(f"🏁 [STREAMING] Streaming output completed, quickly display Remaining content")
        print(f"🏁 [STREAMING] Currently displaying: {self.display_index}/{len(self.full_text)} characters")
        
        # If there is still a lot of content that has not been displayed, display it directly
        remaining_chars = len(self.full_text) - self.display_index
        if remaining_chars > 50:
            print(f"⚡ [STREAMING] Remaining {remaining_chars} characters, switch to extremely fast display mode")
            # Stop current timer
            self.typing_timer.stop()
            # Use extremely fast timer to quickly display Remaining content
            self.typing_timer.start(1)  # 1ms per character, extremely fast speed
        else:
            print(f"✅ [STREAMING] Remaining {remaining_chars} characters, keep current speed")


class ChatView(QScrollArea):
    """Chat message list view"""
    
    wiki_requested = pyqtSignal(str, str)  # url, title
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages: List[MessageWidget] = []
        self.current_status_widget: Optional[StatusMessageWidget] = None
        
        # Automatic scroll control
        self.auto_scroll_enabled = True  # Whether to enable automatic scrolling
        self.user_scrolled_manually = False  # Whether the user has manually scrolled
        self.last_scroll_position = 0  # Last scroll position
        
        # Resize anti-shake mechanism
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._performDelayedResize)
        
        # Unified scroll manager
        self._scroll_request_timer = QTimer()
        self._scroll_request_timer.setSingleShot(True)
        self._scroll_request_timer.timeout.connect(self._perform_auto_scroll)
        self._scroll_request_pending = False
        
        # Content stability detection
        self._last_content_height = 0
        self._content_stable_timer = QTimer()
        self._content_stable_timer.setSingleShot(True)
        self._content_stable_timer.timeout.connect(self._check_content_stability)
        
        # Animation status flag
        self._is_animating = False
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the chat view UI"""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Container widget
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.addStretch()  # Keep bottom alignment
        
        # Ensure container fills ScrollArea
        self.container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        self.setWidget(self.container)
        
        # Styling - transparent background to blend with main window
        self.setStyleSheet("""
            QScrollArea {
                background: rgba(248, 249, 250, 120);
                border: none;
                border-radius: 0px;
            }
            QScrollArea::corner {
                background: transparent;
            }
        """)
        
        # Connect scrollbar signals, monitor user manual scrolling
        scrollbar = self.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll_changed)
        scrollbar.sliderPressed.connect(self._on_user_scroll_start)
        scrollbar.sliderReleased.connect(self._on_user_scroll_end)
        
        # Add welcome message
        self._add_welcome_message()
        
    def _check_and_fix_width(self):
        """Check and fix ChatView width exception"""
        if not self.parent():
            return
            
        parent_width = self.parent().width()
        current_width = self.width()
        viewport_width = self.viewport().width()
        
        # If Parent container width is normal but ChatView width is abnormal
        if parent_width > 600 and current_width < 600:
            print(f"🔧 Detected ChatView width abnormal, starting fix:")
            print(f"  Parent container width: {parent_width}px")
            print(f"  ChatView width: {current_width}px") 
            print(f"  viewport width: {viewport_width}px")
            
            # Display the complete parent container chain
            print(f"  Complete parent container chain:")
            parent = self.parent()
            level = 0
            while parent and level < 5:
                parent_width_info = parent.width() if hasattr(parent, 'width') else "N/A"
                parent_type = type(parent).__name__
                parent_geometry = parent.geometry() if hasattr(parent, 'geometry') else "N/A"
                print(f"    └─ [{level}] {parent_type}: width={parent_width_info}px, geometry={parent_geometry}")
                parent = parent.parent() if hasattr(parent, 'parent') else None
                level += 1
            
            # Force set to Parent container width
            self.setFixedWidth(parent_width)
            QTimer.singleShot(50, lambda: self.setMaximumWidth(16777215))  # Delay removal of fixed width limit
            QTimer.singleShot(100, lambda: self.setMinimumWidth(0))
            
            print(f"🔧 ChatView width fixed: {parent_width}px")
            
        # If viewport width is abnormal, force refresh
        elif viewport_width < 600 and parent_width > 600:
            print(f"🔧 Detected viewport width abnormal, force refresh layout")
            print(f"  Current size policy: {self.sizePolicy().horizontalPolicy()}")
            print(f"  Minimum size: {self.minimumSize()}")
            print(f"  Maximum size: {self.maximumSize()}")
            
            self.updateGeometry()
            self.container.updateGeometry()
            if self.parent():
                self.parent().updateGeometry()
        
    def _add_welcome_message(self):
        """Add welcome message and recommended queries"""
        # Build multi-language welcome message
        welcome_parts = [
            t('welcome_title'),
            "",
            t('welcome_features'),
            t('welcome_wiki_search'),
            t('welcome_ai_guide'),
            "",
            t('welcome_examples'),
            t('welcome_helldivers'),
            t('welcome_eldenring'),
            t('welcome_dst')
        ]
        
        welcome_content = "\n".join(welcome_parts)
        
        # Create welcome message
        welcome_message = ChatMessage(
            type=MessageType.AI_RESPONSE,
            content=welcome_content,
            metadata={"is_welcome": True}
        )
        
        widget = MessageWidget(welcome_message, self)
        self.layout.insertWidget(self.layout.count() - 1, widget)
        self.messages.append(widget)
        
    def add_message(self, msg_type: MessageType, content: str, 
                   metadata: Dict[str, Any] = None) -> MessageWidget:
        """Add a new message to the chat"""
        # Check and fix ChatView width exception
        self._check_and_fix_width()
        
        message = ChatMessage(
            type=msg_type,
            content=content,
            metadata=metadata or {}
        )
        
        if msg_type == MessageType.AI_STREAMING:
            widget = StreamingMessageWidget(message, self)
        else:
            widget = MessageWidget(message, self)
            
        self.layout.insertWidget(self.layout.count() - 1, widget)
        self.messages.append(widget)
        
        # Dynamically set message maximum width to 75% of ChatView width
        self._update_message_width(widget)
        
        # Gentle layout update, avoid forced resizing
        widget.updateGeometry()
        self.container.updateGeometry()
        
        # Use unified scroll request mechanism
        self.request_auto_scroll()
        
        return widget
        
    def add_streaming_message(self) -> StreamingMessageWidget:
        """Add a new streaming message"""
        print(f"🎬 [UI-DEBUG] Started creating streaming message component")
        try:
            # Create streaming message, which will be converted to AI_RESPONSE type after completion
            streaming_widget = self.add_message(MessageType.AI_STREAMING, "")
            print(f"✅ [UI-DEBUG] Streaming message component created successfully: {streaming_widget}")
            print(f"✅ [UI-DEBUG] Streaming message component type: {type(streaming_widget)}")
            return streaming_widget
        except Exception as e:
            print(f"❌ [UI-DEBUG] Failed to create streaming message component: {e}")
            raise

    def show_status(self, message: str) -> StatusMessageWidget:
        """Display status information"""
        # Check and fix ChatView width exception
        self._check_and_fix_width()
        
        # If there is already a status message, hide it first
        if self.current_status_widget:
            self.hide_status()
            
        # Create new status message
        self.current_status_widget = StatusMessageWidget(message, self)
        self.layout.insertWidget(self.layout.count() - 1, self.current_status_widget)
        
        # Dynamically set message maximum width
        self._update_status_width(self.current_status_widget)
        
        # Gentle layout update
        self.current_status_widget.updateGeometry()
        self.container.updateGeometry()
        # Use unified scroll request mechanism
        self.request_auto_scroll()
        
        return self.current_status_widget
        
    def update_status(self, message: str):
        """Update current status information"""
        if self.current_status_widget:
            self.current_status_widget.update_status(message)
            # Ensure scrolling to the bottom to display the new status
            self.request_auto_scroll()
        else:
            self.show_status(message)
            
    def hide_status(self):
        """Hide current status information"""
        if self.current_status_widget:
            self.current_status_widget.hide_with_fadeout()
            self.layout.removeWidget(self.current_status_widget)
            self.current_status_widget.deleteLater()
            self.current_status_widget = None
            
    def _update_status_width(self, widget: StatusMessageWidget):
        """Update status message widget maximum width"""
        # Get the actual width of the chat view, considering the width of the scrollbar
        chat_width = self.viewport().width()
        
        # Subtract the width that the scrollbar may occupy
        scrollbar = self.verticalScrollBar()
        if scrollbar and scrollbar.isVisible():
            chat_width -= scrollbar.width()
            
        if chat_width > 0:
            # Ensure valid width
            chat_width = max(300, chat_width)
            
            # Set the maximum width of the status message to 75% of the width of the chat view, minimum 300px, maximum 600px
            max_width = min(max(int(chat_width * 0.75), 300), 600)
            # Find the status bubble and set its maximum width
            bubble = widget.findChild(QFrame, "statusBubble")
            if bubble:
                bubble.setMaximumWidth(max_width)
                # Use preferred size policy, avoid fixed width causing layout problems
                bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        
    def scroll_to_bottom(self):
        """Scroll to the bottom of the chat"""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def smart_scroll_to_bottom(self):
        """Smart scroll to the bottom - only execute when automatic scrolling is enabled"""
        if self.auto_scroll_enabled and not self.user_scrolled_manually:
            self.scroll_to_bottom()
            
    def request_auto_scroll(self):
        """Request automatic scrolling (anti-shake)"""
        if not self.auto_scroll_enabled or self.user_scrolled_manually:
            print(f"🚫 [SCROLL] Scroll request rejected - auto_enabled: {self.auto_scroll_enabled}, manual: {self.user_scrolled_manually}")
            return
            
        # Mark that there is a scroll request
        self._scroll_request_pending = True
        print(f"📋 [SCROLL] Received scroll request, starting debounce timer")
        
        # Use anti-shake timer to avoid frequent scrolling
        self._scroll_request_timer.stop()
        self._scroll_request_timer.start(100)  # 100ms anti-shake
        
    def _perform_auto_scroll(self):
        """Perform actual automatic scrolling"""
        print(f"🔄 [SCROLL] _perform_auto_scroll called, pending: {self._scroll_request_pending}")
        if not self._scroll_request_pending:
            return
            
        # Check if the content height has changed
        current_height = self.container.sizeHint().height()
        if current_height != self._last_content_height:
            # Content is still changing, waiting for stability
            print(f"📏 [SCROLL] Content height changed: {self._last_content_height} -> {current_height}，Waiting for stability")
            self._last_content_height = current_height
            self._content_stable_timer.stop()
            self._content_stable_timer.start(50)  # Check again after 50ms
            return
            
        # Content stable, execute scrolling
        if self.auto_scroll_enabled and not self.user_scrolled_manually:
            # Check if it is near the bottom (tolerance 50px)
            scrollbar = self.verticalScrollBar()
            at_bottom = (scrollbar.maximum() - scrollbar.value()) <= 50
            
            print(f"📊 [SCROLL] Scroll check - max: {scrollbar.maximum()}, value: {scrollbar.value()}, at_bottom: {at_bottom}")
            
            if at_bottom or self._scroll_request_pending:
                # Smooth scroll to the bottom
                self.scroll_to_bottom()
                print(f"📍 [SCROLL] Executing auto scroll, height: {current_height}px")
        else:
            print(f"🚫 [SCROLL] Scroll disabled or user manually scrolled")
                
        self._scroll_request_pending = False
        
    def _check_content_stability(self):
        """Check if the content is stable"""
        current_height = self.container.sizeHint().height()
        if current_height == self._last_content_height:
            # Content stable, execute pending scrolling
            if self._scroll_request_pending:
                self._perform_auto_scroll()
        else:
            # Content is still changing, continue waiting
            self._last_content_height = current_height
            self._content_stable_timer.start(50)
            
    def _on_scroll_changed(self, value):
        """Callback when scroll position changes"""
        scrollbar = self.verticalScrollBar()
        
        # Check if it is near the bottom (less than 50 pixels from the bottom)
        near_bottom = (scrollbar.maximum() - value) <= 50
        
        # If the user scrolls to near the bottom, re-enable automatic scrolling
        if near_bottom and self.user_scrolled_manually:
            print("📍 User scrolled near bottom, re-enabling auto scroll")
            self.user_scrolled_manually = False
            self.auto_scroll_enabled = True
            
    def _on_user_scroll_start(self):
        """User starts manual scrolling"""
        self.user_scrolled_manually = True
        
    def _on_user_scroll_end(self):
        """User ends manual scrolling"""
        # Check if it is near the bottom
        scrollbar = self.verticalScrollBar()
        near_bottom = (scrollbar.maximum() - scrollbar.value()) <= 50
        
        if not near_bottom:
            # If not near the bottom, disable auto scroll
            self.auto_scroll_enabled = False
            print("📍 User manually scrolled away from bottom, disabling auto scroll")
        else:
            # If near the bottom, maintain auto scroll
            self.auto_scroll_enabled = True
            self.user_scrolled_manually = False
            print("📍 User near bottom, maintaining auto scroll")
            
    def wheelEvent(self, event):
        """Mouse wheel event - detect user wheel operation"""
        # Mark that the user has manually scrolled
        self.user_scrolled_manually = True
        
        # Call the original wheel event processing
        super().wheelEvent(event)
        
        # Delay checking if it is near the bottom
        QTimer.singleShot(100, self._check_if_near_bottom)
        
    def _check_if_near_bottom(self):
        """Check if it is near the bottom"""
        scrollbar = self.verticalScrollBar()
        near_bottom = (scrollbar.maximum() - scrollbar.value()) <= 50
        
        if near_bottom:
            # If near the bottom, re-enable auto scroll
            self.auto_scroll_enabled = True
            self.user_scrolled_manually = False
        else:
            # Otherwise disable auto scroll
            self.auto_scroll_enabled = False
            print("📍 Wheel operation left bottom, disabling auto scroll")
            
    def mouseDoubleClickEvent(self, event):
        """Double-click event - manually re-enable auto scroll and scroll to the bottom"""
        if event.button() == Qt.MouseButton.LeftButton:
            print("📍 Double-clicked chat area, re-enabling auto scroll")
            self.auto_scroll_enabled = True
            self.user_scrolled_manually = False
            self.scroll_to_bottom()
        super().mouseDoubleClickEvent(event)
        
    def reset_auto_scroll(self):
        """Reset auto scroll state (for external use)"""
        self.auto_scroll_enabled = True
        self.user_scrolled_manually = False
        print("📍 Reset auto scroll state")
        
    def disable_auto_scroll(self):
        """Disable auto scroll (for external use)"""
        self.auto_scroll_enabled = False
        self.user_scrolled_manually = True
        print("📍 Disable auto scroll")
        
    def keyPressEvent(self, event):
        """Keyboard event - support shortcut key control auto scroll"""
        if event.key() == Qt.Key.Key_End:
            # End key: re-enable auto scroll and scroll to the bottom
            print("📍 Pressed End key, re-enabling auto scroll")
            self.auto_scroll_enabled = True
            self.user_scrolled_manually = False
            self.scroll_to_bottom()
        elif event.key() == Qt.Key.Key_Home:
            # Home key: scroll to the top and disable auto scroll
            print("📍 Pressed Home key, scroll to the top and disable auto scroll")
            self.auto_scroll_enabled = False
            self.user_scrolled_manually = True
            scrollbar = self.verticalScrollBar()
            scrollbar.setValue(0)
        else:
            super().keyPressEvent(event)
    
    def contextMenuEvent(self, event):
        """Override context menu event to ensure proper styling"""
        # Create a custom context menu
        menu = QMenu(self)
        
        # The menu will inherit the global QMenu styling
        # No need to add any actions for scrollbar - just show empty menu
        # This prevents the default transparent context menu
        
        menu.exec(event.globalPos())
        
    def show_wiki(self, url: str, title: str):
        """Emit signal to show wiki page"""
        logger = logging.getLogger(__name__)
        logger.info(f"📄 ChatView.show_wiki called: URL={url}, Title={title}")
        self.wiki_requested.emit(url, title)
        logger.info(f"📤 wiki_requested signal emitted")
        
    def _update_message_width(self, widget: MessageWidget):
        """Update message widget maximum width"""
        # If it is animating, skip update
        if self._is_animating:
            return
            
        # Get multi-layer container width information for debugging
        viewport_width = self.viewport().width()
        scroll_area_width = self.width()
        parent_window_width = self.parent().width() if self.parent() else "N/A"
        
        # Get the actual width of the chat view, considering the width of the scrollbar
        chat_width = viewport_width
        
        # Subtract the width that the scrollbar may occupy
        scrollbar = self.verticalScrollBar()
        scrollbar_width = 0
        if scrollbar and scrollbar.isVisible():
            scrollbar_width = scrollbar.width()
            chat_width -= scrollbar_width
            
        if chat_width > 0:
            # Ensure valid width
            chat_width = max(300, chat_width)
            
            # Set the maximum width of the message to 75% of the width of the chat view, minimum 300px, maximum 600px
            max_width = min(max(int(chat_width * 0.75), 300), 600)
            
            # If it is StreamingMessageWidget, call its specialized update method
            if isinstance(widget, StreamingMessageWidget):
                widget._update_bubble_width()
            else:
                # For normal messages, use maximum width instead of fixed width
                bubble = widget.findChild(QFrame, "messageBubble")
                if bubble:
                    # Use maximum width, let the layout system decide the actual width
                    bubble.setMaximumWidth(max_width)
                    bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
                
                # Update the width of content_label at the same time
                if hasattr(widget, 'content_label'):
                    content_width = max_width - 24  # Subtract margin
                    widget.content_label.setMaximumWidth(content_width)
                    widget.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
                
                # Output debug information only in abnormal cases
                if viewport_width < 400:  # Output warning when the view width is abnormal
                    print(f"⚠️ View width abnormal: viewport={viewport_width}px")
                
    def resizeEvent(self, event):
        """Trigger anti-shake update when window size changes"""
        super().resizeEvent(event)
        
        # If it is animating, skip update to avoid stuttering
        if self._is_animating:
            return
        
        # Force ChatView to maintain the correct width (immediately executed to avoid display exceptions)
        parent_width = self.parent().width() if self.parent() else 0
        current_width = self.width()
        if parent_width > 0 and abs(current_width - parent_width) > 5:  # More than 5px difference
            self.resize(parent_width, self.height())
        
        # Use anti-shake mechanism to delay updating message width (restore original logic)
        self.resize_timer.stop()  # Stop the previous timer
        self.resize_timer.start(200)  # Update after 0.2 seconds
        
    def _performDelayedResize(self):
        """Delayed resize update operation"""
        print(f"📏 ChatView layout updated: {self.size()}")
        
        # Update the width of all existing messages
        for widget in self.messages:
            self._update_message_width(widget)
        # Update the width of the status message
        if self.current_status_widget:
            self._update_status_width(self.current_status_widget)
            
        # Force update the height of all messages to ensure complete display
        self._ensureContentComplete()
        
        # Delay a little bit to check again, ensure all content has been rendered
        QTimer.singleShot(50, self._finalizeContentDisplay)
        
        # Ensure scrolling to the correct position
        QTimer.singleShot(100, self.smart_scroll_to_bottom)
        
    def _ensureContentComplete(self):
        """Ensure all message content is displayed completely"""
        try:
            # Update the display of all messages
            for widget in self.messages:
                if hasattr(widget, 'content_label'):
                    try:
                        # 1. Update message width
                        self._update_message_width(widget)
                        
                        # 2. Force content label to recalculate size
                        content_label = widget.content_label
                        
                        # Ensure content is not truncated
                        content_label.setWordWrap(True)
                        content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
                        
                        # For StreamingMessageWidget, ensure the format is correct
                        if isinstance(widget, StreamingMessageWidget):
                            # If there is complete text, re-detect and render
                            if hasattr(widget, 'full_text') and widget.full_text:
                                if detect_markdown_content(widget.full_text):
                                    html_content = convert_markdown_to_html(widget.full_text)
                                    content_label.setText(html_content)
                                    content_label.setTextFormat(Qt.TextFormat.RichText)
                                else:
                                    content_label.setText(widget.full_text)
                                    content_label.setTextFormat(Qt.TextFormat.PlainText)
                        
                        # 3. Force update content size
                        content_label.adjustSize()
                        
                        # 4. Ensure bubble container is correctly expanded
                        bubble = widget.findChild(QFrame, "messageBubble")
                        if bubble:
                            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
                            
                            # Improved: use a more reliable way to calculate the required height
                            # Wait a little bit to let the content render
                            QTimer.singleShot(10, lambda w=widget, b=bubble, cl=content_label: self._updateBubbleHeight(w, b, cl))
                        
                        # 5. Special handling for streaming messages
                        if isinstance(widget, StreamingMessageWidget):
                            if hasattr(widget, 'full_text') and widget.full_text:
                                widget._update_bubble_width()
                                widget.updateGeometry()
                        
                    except Exception as e:
                        # Record errors instead of silent processing
                        print(f"Error updating message display: {e}")
            
            # Update status message
            if self.current_status_widget:
                try:
                    self._update_status_width(self.current_status_widget)
                except Exception:
                    pass
            
            # Force the entire container to re-layout
            self.container.updateGeometry()
            self.updateGeometry()
            self.verticalScrollBar().update()
            
        except Exception as e:
            # Record global error
            print(f"_ensureContentComplete error: {e}")
    
    def _updateBubbleHeight(self, widget, bubble, content_label):
        """Delay updating bubble height, ensure content rendering is complete"""
        try:
            # Get the actual height of the content
            # Use multiple methods to get the most accurate height
            height1 = content_label.sizeHint().height()
            height2 = content_label.heightForWidth(content_label.width())
            
            # For rich text content, additional height calculation is required
            if content_label.textFormat() == Qt.TextFormat.RichText:
                # Create a temporary document to accurately calculate the height of HTML content
                doc = QTextDocument()
                doc.setDefaultFont(content_label.font())
                doc.setHtml(content_label.text())
                doc.setTextWidth(content_label.width())
                height3 = int(doc.size().height())
            else:
                height3 = height1
            
            # Take the maximum value to ensure complete display
            actual_height = max(height1, height2, height3)
            
            # Add padding
            min_height = actual_height + 20  # Increase margin
            
            # Set minimum height
            bubble.setMinimumHeight(min_height)
            
            # Force update the entire message widget
            widget.updateGeometry()
            widget.update()
            
        except Exception as e:
            print(f"Error updating bubble height: {e}")
    
    def _finalizeContentDisplay(self):
        """Finalize content display"""
        # Check the height of all messages again
        for widget in self.messages:
            if hasattr(widget, 'content_label'):
                bubble = widget.findChild(QFrame, "messageBubble")
                if bubble and widget.content_label:
                    self._updateBubbleHeight(widget, bubble, widget.content_label)
    
    def _force_content_refresh(self):
        """Force refresh all content display (simplified version)"""
        try:
            # Simple content refresh, ensure the scroll position is correct
            if hasattr(self, 'near_bottom_before_resize') and self.near_bottom_before_resize:
                self.scroll_to_bottom()
        except Exception:
            pass
            
    def update_all_message_widths(self):
        """Update the width of all messages (for initialization after window display)"""
        for widget in self.messages:
            self._update_message_width(widget)
        if self.current_status_widget:
            self._update_status_width(self.current_status_widget)
        
    def showEvent(self, event):
        """Update message width when window is displayed"""
        super().showEvent(event)
        # Delay update, ensure the window is fully displayed
        QTimer.singleShot(100, self.update_all_message_widths)




class WikiView(QWidget):
    """Wiki page viewer - simplified version to avoid crashes"""
    
    back_requested = pyqtSignal()
    wiki_page_loaded = pyqtSignal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_search_url = ""  # Store search URL
        self.current_search_title = ""  # Store search title
        self.web_view = None
        self.content_widget = None
        self._webview_ready = False
        self._is_paused = False  # Add pause state flag
        self._pause_lock = False  # Add pause lock to prevent duplicate calls
        
        # URL monitoring for wiki detection
        self._url_monitor_timer = QTimer()
        self._url_monitor_timer.timeout.connect(self._monitor_wiki_navigation)
        self._monitoring_start_url = None
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the wiki view UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Top toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-bottom: 1px solid #e0e0e0;
            }
        """)
        
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 0, 10, 0)
        
        # Back to chat button
        self.back_button = QPushButton("< Back to Chat")
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #4096ff;
                font-size: 14px;
                padding: 8px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #e8f0fe;
                border-radius: 4px;
            }
        """)
        self.back_button.clicked.connect(self.back_requested.emit)
        
        # Navigation button style
        nav_button_style = """
            QPushButton {
                background-color: transparent;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                color: #5f6368;
                font-size: 16px;
                padding: 4px 4px;
                min-width: 28px;
                max-width: 28px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                border-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
            QPushButton:disabled {
                color: #c0c0c0;
                border-color: #f0f0f0;
            }
        """
        
        # Browser navigation buttons
        self.nav_back_button = QPushButton("◀")
        self.nav_back_button.setStyleSheet(nav_button_style)
        self.nav_back_button.setToolTip("Back to the previous page")
        self.nav_back_button.setEnabled(False)
        
        self.nav_forward_button = QPushButton("▶")
        self.nav_forward_button.setStyleSheet(nav_button_style)
        self.nav_forward_button.setToolTip("Forward to the next page")
        self.nav_forward_button.setEnabled(False)
        
        self.refresh_button = QPushButton("🔄")
        self.refresh_button.setStyleSheet(nav_button_style)
        self.refresh_button.setToolTip("Refresh page")
        
        # URL bar
        self.url_bar = QLineEdit()
        self.url_bar.setStyleSheet("""
            QLineEdit {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                background: white;
                color: #202124;
            }
            QLineEdit:focus {
                border-color: #4096ff;
                outline: none;
            }
        """)
        self.url_bar.setPlaceholderText("Enter URL and press Enter to navigate...")
        
        # Open in browser button
        self.open_browser_button = QPushButton("Open in Browser")
        self.open_browser_button.setStyleSheet("""
            QPushButton {
                background-color: #4096ff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2d7ff9;
            }
        """)
        self.open_browser_button.clicked.connect(self.open_in_browser)
        
        # Add all widgets to toolbar
        toolbar_layout.addWidget(self.back_button)
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(self.nav_back_button)
        toolbar_layout.addWidget(self.nav_forward_button)
        toolbar_layout.addWidget(self.refresh_button)
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(self.url_bar, 1)  # URL bar takes remaining space
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(self.open_browser_button)
        
        # Content area - delayed WebView creation
        self.web_view = None
        self.content_widget = None
        self._webview_initialized = False
        self._webview_initializing = False
        
        # Create placeholder widget first
        self.placeholder_widget = QFrame()
        self.placeholder_widget.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #e0e0e0;
            }
        """)
        placeholder_layout = QVBoxLayout(self.placeholder_widget)
        placeholder_label = QLabel("Loading...")
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_label.setStyleSheet("color: #666; font-size: 14px;")
        placeholder_layout.addWidget(placeholder_label)
        
        self.content_widget = self.placeholder_widget
        
        layout.addWidget(toolbar)
        layout.addWidget(self.content_widget)
        
        # Store current URL and title
        self.current_url = ""
        self.current_title = ""
        
        # Start WebView2 initialization immediately in background
        QTimer.singleShot(0, self._initialize_webview_async)
        
    def load_url(self, url: str):
        """Load a URL in the web view"""
        if self.web_view and self._webview_initialized:
            self.web_view.setUrl(QUrl(url))
            self.current_url = url
        else:
            # Store pending URL, will be loaded when WebView is ready
            self._pending_url = url
            # WebView should already be initializing, just wait
    
    def _connect_navigation_signals(self):
        """Connect navigation-related signals"""
        if not self.web_view:
            return
            
        # Connect navigation buttons
        self.nav_back_button.clicked.connect(self.web_view.back)
        self.nav_forward_button.clicked.connect(self.web_view.forward)
        self.refresh_button.clicked.connect(self.web_view.reload)
        
        # Connect URL bar
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        
        # Connect web view signals
        self.web_view.urlChanged.connect(self._on_url_changed)
        self.web_view.loadFinished.connect(self._update_navigation_state)
        self.web_view.titleChanged.connect(self._on_web_title_changed)
        
        # Connect page signals if available
        if hasattr(self.web_view, 'page') and callable(self.web_view.page):
            page = self.web_view.page()
            if page:
                page.loadStarted.connect(self._on_load_started)
        else:
            # For WebView2Widget, connect loadStarted directly
            if hasattr(self.web_view, 'loadStarted'):
                self.web_view.loadStarted.connect(self._on_load_started)
        
    def navigate_to_url(self):
        """Navigate to the URL entered in the URL bar"""
        url = self.url_bar.text().strip()
        if not url:
            return
            
        # Add protocol if missing
        if not url.startswith(('http://', 'https://', 'file://')):
            url = 'https://' + url
            
        # Mark as pending navigation
        self._pending_navigation = url
        self.load_url(url)
        
    def _on_url_changed(self, url):
        """Update URL bar when URL changes"""
        url_str = url.toString()
        self.url_bar.setText(url_str)
        self.current_url = url_str
        
        # If URL changed to a new page (not just hash change), mark as pending
        if hasattr(self, '_last_recorded_url') and url_str != self._last_recorded_url:
            # Check if it's a significant navigation (not just anchor/hash change)
            try:
                from urllib.parse import urlparse
                current_parsed = urlparse(url_str)
                last_parsed = urlparse(self._last_recorded_url) if self._last_recorded_url else None
                
                # Different domain or path = new navigation
                if not last_parsed or (current_parsed.netloc != last_parsed.netloc or 
                                     current_parsed.path != last_parsed.path):
                    self._pending_navigation = url_str
            except:
                self._pending_navigation = url_str
        
    def _on_load_started(self):
        """Called when page loading starts"""
        # You could add a loading indicator here if desired
        pass
        
    def _on_web_title_changed(self, title):
        """Handle title change from web view"""
        if not title or not self._pending_navigation:
            return
            
        # Get current URL from web view
        current_url = self.web_view.url().toString()
        
        # Check if this title change is for our pending navigation
        if current_url == self._pending_navigation:
            # Now we have the real title, record to history
            if hasattr(self, 'history_manager') and title.strip() != "":
                # Determine source type
                if "wiki" in current_url.lower() or "wiki" in title.lower():
                    source = "wiki"
                else:
                    source = "web"
                
                self._ensure_history_manager()
                self.history_manager.add_entry(current_url, title, source=source)
                self._last_recorded_url = current_url
                self._pending_navigation = None  # Clear pending state
                
                logger = logging.getLogger(__name__)
                logger.info(f"📝 Added to history with real title: {title}")
        
    def _update_navigation_state(self, ok=True):
        """Update navigation button states based on history"""
        if not self.web_view:
            return
            
        # Update back/forward button states
        try:
            history = self.web_view.history()
            self.nav_back_button.setEnabled(history.canGoBack())
            self.nav_forward_button.setEnabled(history.canGoForward())
        except:
            pass
        
    def _on_page_load_finished(self, ok):
        """Callback when page loading is complete"""
        if not ok or not self.web_view:
            return
            
        # Update navigation state
        self._update_navigation_state()
            
        try:
            # Get the URL and title of the current page
            current_url = self.web_view.url().toString()
            
            # Check if it is a real wiki page (not a search page)
            if self._is_real_wiki_page(current_url):
                # Delay to ensure page is fully rendered
                QTimer.singleShot(500, self._extract_page_info)
            else:
                # If it is still a search page, check again after a while
                QTimer.singleShot(2000, self._check_for_redirect)
                
        except Exception as e:
            print(f"Page load completion handling failed: {e}")
            
    def _check_for_redirect(self):
        """检查页面是否已重定向到真实wiki页面"""
        if not self.web_view:
            return
            
        try:
            current_url = self.web_view.url().toString()
            if self._is_real_wiki_page(current_url):
                # Delay to ensure page is fully rendered
                QTimer.singleShot(500, self._extract_page_info)
            else:
                # Still on search page, check one more time
                QTimer.singleShot(2000, self._final_check_for_redirect)
        except Exception as e:
            print(f"Redirect check failed: {e}")
            
    def _final_check_for_redirect(self):
        """Final check for redirect after additional delay"""
        if not self.web_view:
            return
            
        try:
            current_url = self.web_view.url().toString()
            if self._is_real_wiki_page(current_url):
                self._extract_page_info()
        except Exception as e:
            print(f"Final redirect check failed: {e}")
            
    def _extract_page_info(self):
        """Extract page title and URL"""
        if not self.web_view:
            return
            
        try:
            current_url = self.web_view.url().toString()
            self._try_get_page_title(current_url)
        except Exception as e:
            print(f"Failed to extract page info: {e}")
            
    def _process_page_info(self, url, title):
        """Process extracted page information"""
        if not title or not url:
            return
            
        # Clean up the title
        title = title.strip()
        
        # Skip if title looks like a search or redirect page
        if any(x in title.lower() for x in ['search', 'redirect', 'loading', '...', 'duckduckgo']):
            return
            
        # Save current info
        self.current_url = url
        self.current_title = title
            
        # Emit signal with real wiki page info
        self._emit_wiki_found(url, title)
        
    def _emit_wiki_found(self, url, title):
        """Emit wiki page found signal"""
        print(f"📄 WikiView found real wiki page: {title} -> {url}")
        self.wiki_page_loaded.emit(url, title)
        
    def _extract_page_info_for_url(self, expected_url):
        """Extract page info and verify it's for the expected URL"""
        if not self.web_view:
            return
            
        try:
            current_url = self.web_view.url().toString()
            
            # Verify we're still on the same page
            if current_url == expected_url:
                # Try multiple methods to get title
                self._try_get_page_title(current_url)
        except Exception as e:
            print(f"Failed to extract page info for URL: {e}")
            
    def _try_get_page_title(self, url):
        """Try to get page title using multiple methods"""
        print(f"🔍 Attempting to extract title for: {url}")
        
        # Method 1: Try JavaScript
        if hasattr(self.web_view, 'page') and callable(self.web_view.page):
            try:
                # More comprehensive title extraction script
                script = """
                (function() {
                    // First try document.title
                    var title = document.title;
                    if (title && title !== '' && title !== 'undefined') {
                        // Return title as-is without modification
                        return title;
                    }
                    // Fallback to h1
                    var h1 = document.querySelector('h1');
                    if (h1 && h1.innerText) {
                        return h1.innerText.trim();
                    }
                    // Fallback to first heading
                    var heading = document.querySelector('h1, h2, h3');
                    if (heading && heading.innerText) {
                        return heading.innerText.trim();
                    }
                    return '';
                })();
                """
                self.web_view.page().runJavaScript(
                    script,
                    lambda title: self._on_title_extracted(url, title)
                )
                return
            except Exception as e:
                print(f"❌ JavaScript title extraction failed: {e}")
        
        # Method 2: For WebView2Widget
        elif hasattr(self.web_view, 'runJavaScript'):
            try:
                script = """
                (function() {
                    var title = document.title;
                    if (title && title !== '' && title !== 'undefined') {
                        // Return title as-is without modification
                        return title;
                    }
                    var h1 = document.querySelector('h1');
                    if (h1 && h1.innerText) {
                        return h1.innerText.trim();
                    }
                    return '';
                })();
                """
                self.web_view.runJavaScript(script, lambda title: self._on_title_extracted(url, title))
                return
            except Exception as e:
                print(f"❌ WebView2 JavaScript title extraction failed: {e}")
            
    def _on_title_extracted(self, url, title):
        """Handle extracted title"""
        if title and title.strip() and title != "null" and title != "undefined":
            print(f"✅ Successfully extracted title: {title}")
            self._emit_wiki_found(url, title)
        else:
            print(f"⚠️ Empty or invalid title extracted, trying fallback")
            # Fallback: use the last part of the URL as title
            try:
                from urllib.parse import urlparse, unquote
                parsed = urlparse(url)
                path_parts = parsed.path.strip('/').split('/')
                if path_parts and path_parts[-1]:
                    fallback_title = unquote(path_parts[-1]).replace('_', ' ')
                    print(f"📝 Using URL-based fallback title: {fallback_title}")
                    self._emit_wiki_found(url, fallback_title)
                else:
                    # Last resort: emit with a generic title
                    self._emit_wiki_found(url, "Wiki Page")
            except Exception as e:
                print(f"❌ Fallback title extraction failed: {e}")
                # Still emit with a generic title
                self._emit_wiki_found(url, "Wiki Page")
            
    def _is_real_wiki_page(self, url: str) -> bool:
        """Determine if it is a real wiki page (not a search page)"""
        if not url:
            return False
            
        # Check if the URL contains common search engine domains
        search_engines = [
            'duckduckgo.com',
            'bing.com',
            'google.com',
            'search.yahoo.com'
        ]
        
        for engine in search_engines:
            if engine in url.lower():
                return False
                
        # Check if it contains wiki-related domains or paths
        wiki_indicators = [
            'wiki',
            'fandom.com',
            'wikia.com',
            'gamepedia.com',
            'huijiwiki.com',  # Add support for HuijiWiki
            'mcmod.cn',       # MC Encyclopedia
            'terraria.wiki.gg',
            'helldiversgamepedia.com'
        ]
        
        url_lower = url.lower()
        for indicator in wiki_indicators:
            if indicator in url_lower:
                return True
                
        # If the URL is different from the initial search URL and is not a search engine, it is considered a real page
        return url != self.current_search_url
    
    def _start_wiki_monitoring(self, search_url: str):
        """Start monitoring for wiki page navigation"""
        self._monitoring_start_url = search_url
        self._url_monitor_timer.start(1000)  # Check every second
        print(f"🔍 Started monitoring for wiki navigation from: {search_url}")
        
    def _stop_wiki_monitoring(self):
        """Stop monitoring for wiki page navigation"""
        self._url_monitor_timer.stop()
        self._monitoring_start_url = None
        print("🚫 Stopped wiki navigation monitoring")
        
    def _monitor_wiki_navigation(self):
        """Monitor WebView for navigation to actual wiki page"""
        if not self.web_view:
            return
            
        try:
            current_url = self.web_view.url().toString()
            
            # Check if we've navigated away from search engine
            if current_url != self._monitoring_start_url and self._is_real_wiki_page(current_url):
                print(f"🎆 Detected navigation to wiki page: {current_url}")
                self._stop_wiki_monitoring()
                
                # Extract title first, don't emit with URL as title
                # Wait a bit for page to load then extract proper title
                QTimer.singleShot(1000, lambda: self._extract_page_info_for_url(current_url))
        except Exception as e:
            print(f"Error in wiki navigation monitoring: {e}")
    
    def _initialize_webview_async(self):
        """Initialize WebView2 asynchronously"""
        if self._webview_initialized or self._webview_initializing:
            return
            
        self._webview_initializing = True
        
        # WebView2 must be created in main thread due to COM requirements
        # Use QTimer to defer creation to avoid blocking current event
        def create_webview():
            try:
                if USE_WEBVIEW2 and WEBVIEW2_AVAILABLE:
                    print("🔧 Creating WebView2...")
                    start_time = time.time()
                    web_view = WebView2Widget()
                    elapsed = time.time() - start_time
                    print(f"✅ WebView2 created in {elapsed:.2f}s")
                    self._apply_webview(web_view)
                else:
                    print("⚠️ WebView2 not available")
            except Exception as e:
                print(f"❌ WebView2 creation failed: {e}")
        
        # Defer to next event loop iteration to avoid blocking
        QTimer.singleShot(10, create_webview)
        
    def _apply_webview(self, web_view):
        """Apply WebView2 widget (must be called in main thread)"""
        if self._webview_initialized:
            return
            
        try:
            # Remove placeholder
            layout = self.layout()
            layout.removeWidget(self.placeholder_widget)
            self.placeholder_widget.deleteLater()
            
            # Apply WebView2
            self.web_view = web_view
            self.content_widget = self.web_view
            layout.addWidget(self.content_widget)
            
            # Connect signals
            self._connect_navigation_signals()
            
            self._webview_ready = True
            self._webview_initialized = True
            self._webview_initializing = False
            
            print("✅ WebView2 applied successfully")
            
            # If there's a pending URL to load
            if hasattr(self, '_pending_url'):
                self.load_url(self._pending_url)
                delattr(self, '_pending_url')
                
        except Exception as e:
            print(f"❌ Failed to apply WebView2: {e}")
    
    def _delayed_webview_creation(self):
        """Delayed WebView creation, executed after Qt application is fully initialized"""
        try:
            print("🔧 Starting delayed WebView creation...")
            
            
            # WebView2 is the only supported option - skip creation
            new_web_view = None
            
            if new_web_view is not None:
                print("✅ WebView delayed creation successful")
                
                # Configure WebView properties
                try:
                    new_web_view.setMinimumSize(100, 100)
                    new_web_view.setMaximumSize(16777215, 16777215)
                    new_web_view.setSizePolicy(
                        QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Expanding
                    )
                    
                    # Connect signals
                    new_web_view.loadFinished.connect(self._on_page_load_finished)
                    print("✅ WebView configuration completed")
                except Exception as config_error:
                    print(f"⚠️ WebView configuration failed: {config_error}")
                
                # Replace content component
                try:
                    old_widget = self.content_widget
                    self.content_widget = new_web_view
                    self.web_view = new_web_view
                    self._webview_ready = True  # Mark WebView as ready
                    
                    # Update layout
                    layout = self.layout()
                    if layout:
                        # Find old content_widget and replace it
                        for i in range(layout.count()):
                            item = layout.itemAt(i)
                            if item and item.widget() == old_widget:
                                layout.removeWidget(old_widget)
                                layout.addWidget(new_web_view)
                                # Delay deletion of old component to avoid issues from immediate deletion
                                QTimer.singleShot(100, old_widget.deleteLater)
                                break
                    
                    print("✅ WebView successfully replaced text view")
                except Exception as replace_error:
                    print(f"⚠️ WebView replacement failed: {replace_error}")
                    # If replacement fails, clean up newly created WebView
                    new_web_view.deleteLater()
            else:
                print("⚠️ WebView creation failed, continuing to use text view")
                
        except Exception as e:
            print(f"❌ Delayed WebView creation process failed: {e}")
    
        
    def load_wiki(self, url: str, title: str):
        """Load a wiki page"""
        self.current_search_url = url  # Save search URL
        self.current_search_title = title  # Save search title
        self.current_url = url
        self.current_title = title
        self.url_bar.setText(url)  # Update URL bar instead of title label
        
        # Start monitoring for wiki page navigation if loading from search engine
        if any(engine in url.lower() for engine in ['duckduckgo.com', 'google.com', 'bing.com']):
            self._start_wiki_monitoring(url)
        
        if self.web_view:
            try:
                # For local files, use load method directly to preserve external resource loading capability
                if url.startswith('file:///'):
                    # Create QUrl object
                    qurl = QUrl(url)
                    print(f"📄 Loading local file: {url}")
                    
                    # Load file URL
                    self.web_view.load(qurl)
                    print(f"✅ Using load method to load local HTML, preserving external resource loading")
                else:
                    # Non-local files, normal loading
                    self.web_view.load(QUrl(url))
            except Exception as e:
                print(f"❌ Failed to load wiki page: {e}")
                import traceback
                traceback.print_exc()
                # Display error message
                self.web_view.setHtml(f"<h2>Error</h2><p>Failed to load page: {str(e)}</p>")
        else:
            # Show fallback message
            fallback_text = f"""
            <h2>{title}</h2>
            <p><strong>URL:</strong> <a href="{url}">{url}</a></p>
            <hr>
            <p>WebView2 is not available. Please click "Open in Browser" to view this page in your default browser.</p>
            <p>Alternatively, you can copy and paste the URL above into your browser.</p>
            """
            self.content_widget.setHtml(fallback_text)
            
    def open_in_browser(self):
        """Open the current URL in default browser"""
        if self.current_url:
            import webbrowser
            try:
                webbrowser.open(self.current_url)
            except Exception as e:
                print(f"Failed to open browser: {e}")
    
    def stop_media_playback(self):
        """Stop all media playback in the page"""
        if self.web_view:
            try:
                # Execute more comprehensive JavaScript to stop all media playback
                javascript_code = """
                (function() {
                    // Stop all video and audio
                    var videos = document.querySelectorAll('video');
                    var audios = document.querySelectorAll('audio');
                    
                    videos.forEach(function(video) {
                        video.pause();
                        video.currentTime = 0;
                        video.muted = true;
                        video.volume = 0;
                        // Remove all event listeners
                        video.onplay = null;
                        video.onloadeddata = null;
                        video.oncanplay = null;
                    });
                    
                    audios.forEach(function(audio) {
                        audio.pause();
                        audio.currentTime = 0;
                        audio.muted = true;
                        audio.volume = 0;
                        // Remove all event listeners
                        audio.onplay = null;
                        audio.onloadeddata = null;
                        audio.oncanplay = null;
                    });
                    
                    // Stop all media in iframes
                    var iframes = document.querySelectorAll('iframe');
                    iframes.forEach(function(iframe) {
                        try {
                            var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                            var iframeVideos = iframeDoc.querySelectorAll('video');
                            var iframeAudios = iframeDoc.querySelectorAll('audio');
                            
                            iframeVideos.forEach(function(video) {
                                video.pause();
                                video.currentTime = 0;
                                video.muted = true;
                                video.volume = 0;
                                video.onplay = null;
                                video.onloadeddata = null;
                                video.oncanplay = null;
                            });
                            
                            iframeAudios.forEach(function(audio) {
                                audio.pause();
                                audio.currentTime = 0;
                                audio.muted = true;
                                audio.volume = 0;
                                audio.onplay = null;
                                audio.onloadeddata = null;
                                audio.oncanplay = null;
                            });
                        } catch(e) {
                            // Cross-domain iframe cannot be accessed, ignore error
                        }
                    });
                    
                    // Prevent new media playback
                    if (!window._originalPlay) {
                        window._originalPlay = HTMLMediaElement.prototype.play;
                    }
                    HTMLMediaElement.prototype.play = function() {
                        console.log('🚫 Prevent media playback:', this);
                        return Promise.reject(new Error('Media playback blocked'));
                    };
                    
                    console.log('🔇 Media playback has been stopped and new playback has been prevented');
                })();
                """
                
                self.web_view.page().runJavaScript(javascript_code)
                print("🔇 WikiView: Enhanced media stop script executed")
                
            except Exception as e:
                print(f"⚠️ WikiView: Failed to stop media playback: {e}")
                
    def pause_page(self):
        """Pause page activity (including media playback)"""
        # Prevent repeated calls
        if self._pause_lock:
            print("🔄 WikiView: Pause operation is in progress, skipping repeated call")
            return
            
        if self.web_view and not self._is_paused:
            try:
                self._pause_lock = True
                print("🔄 Pausing WikiView page...")
                
                # 1. Stop current network request
                try:
                    self.web_view.stop()
                    print("✅ WebView network request stopped")
                except Exception as stop_error:
                    print(f"⚠️ WebView stop failed: {stop_error}")
                
                # 2. Stop media playback
                try:
                    self.stop_media_playback()
                    print("✅ Media playback stopped")
                except Exception as media_error:
                    print(f"⚠️ Media stop failed: {media_error}")
                
                # 3. Set the page to an invisible state, some websites will automatically pause media
                try:
                    self.web_view.page().runJavaScript("""
                    (function() {
                        // Set the page to an invisible state
                        Object.defineProperty(document, 'hidden', {value: true, writable: false});
                        Object.defineProperty(document, 'visibilityState', {value: 'hidden', writable: false});
                        
                        // Trigger visibility change event
                        var event = new Event('visibilitychange');
                        document.dispatchEvent(event);
                        
                        // Prevent page focus
                        if (document.hasFocus) {
                            document.hasFocus = function() { return false; };
                        }
                        
                        // Set the page to an uninteractive state
                        document.body.style.pointerEvents = 'none';
                        
                        console.log('🔇 The page has been set to an invisible state');
                    })();
                    """)
                    print("✅ The page visibility state has been set")
                except Exception as js_error:
                    print(f"⚠️ JavaScript execution failed: {js_error}")
                
                self._is_paused = True
                print("✅ WikiView page pause completed")
                
            except Exception as e:
                print(f"⚠️ WikiView: Failed to pause page: {e}")
            finally:
                self._pause_lock = False
        else:
            print("🔄 WikiView: The page is already paused or WebView is not available, skipping pause operation")
    
    def safe_cleanup(self):
        """Safe cleanup of WikiView resources, used when window is closing"""
        try:
            print("🔄 Starting simplified WikiView cleanup...")
            
            if self.web_view:
                # Only perform the most basic cleanup, avoiding complex JavaScript or signal operations
                try:
                    # Stop network activity
                    self.web_view.stop()
                    print("✅ WebView stopped")
                except Exception:
                    # If stopping fails, continue processing
                    pass
                
                # Do not perform complex media stop, JavaScript execution, or signal disconnection operations
                # These may cause crashes
            
            print("✅ Simplified WikiView cleanup completed")
            
        except Exception as e:
            print(f"❌ WikiView cleanup failed: {e}")
                
    def resume_page(self):
        """Resume page activity"""
        if self.web_view and self._is_paused:
            try:
                # Restore page visibility and interactivity
                self.web_view.page().runJavaScript("""
                (function() {
                    // Restore page visibility state
                    Object.defineProperty(document, 'hidden', {value: false, writable: false});
                    Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: false});
                    
                    // Trigger visibility change event
                    var event = new Event('visibilitychange');
                    document.dispatchEvent(event);
                    
                    // Restore page interactivity
                    document.body.style.pointerEvents = '';
                    
                    // Restore media playback functionality
                    if (window._originalPlay) {
                        HTMLMediaElement.prototype.play = window._originalPlay;
                        delete window._originalPlay;
                    }
                    
                    console.log('▶️ The page has been restored to visible and interactive state');
                })();
                """)
                
                self._is_paused = False
                print("▶️ WikiView: The page has been restored")
                
            except Exception as e:
                 print(f"⚠️ WikiView: Failed to restore page: {e}")
        else:
            print("▶️ WikiView: The page is not in a paused state, skipping restore operation")
                 
    def hideEvent(self, event):
        """When WikiView is hidden, automatically pause media playback"""
        # Only pause when currently displaying WikiView
        if hasattr(self, 'parent') and self.parent():
            parent = self.parent()
            if hasattr(parent, 'content_stack'):
                current_widget = parent.content_stack.currentWidget()
                if current_widget == self:
                    self.pause_page()
        super().hideEvent(event)
        
    def showEvent(self, event):
        """When WikiView is displayed, restore page activity"""
        super().showEvent(event)
        
        # Ensure WebView2 is initialized when showing
        if not self._webview_initialized and not self._webview_initializing:
            self._initialize_webview_async()
            
        # Delay restore, ensure the page is fully displayed
        QTimer.singleShot(100, self.resume_page)


class UnifiedAssistantWindow(QMainWindow):
    """Main unified window with all modes"""
    
    query_submitted = pyqtSignal(str, str)  # query, mode
    window_closing = pyqtSignal()  # Signal when window is closing
    wiki_page_found = pyqtSignal(str, str)  # New signal: pass real wiki page information to controller
    visibility_changed = pyqtSignal(bool)  # Signal for visibility state changes
    stop_generation_requested = pyqtSignal()  # New signal: stop generation request

    def __init__(self, settings_manager=None):
        super().__init__()
        
        # Set frameless window flags and transparency
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)  # Enable tooltips without focus
        
        # Create quick access popup
        self.quick_access_popup = QuickAccessPopup()
        
        # Window properties for drag and resize
        self.dragging = False
        self.resizing = False
        self.resize_edge = None
        self.drag_position = QPoint()
        self.resize_start_pos = QPoint()
        self.resize_start_geometry = QRect()
        
        # Enable mouse tracking for resize
        self.setMouseTracking(True)
        
        # Keep all existing properties
        self.settings_manager = settings_manager
        self.current_mode = "auto"
        self.is_generating = False
        self.streaming_widget = None
        self.current_game_window = None  # Record current game window title
        
        # History manager will be initialized lazily
        self.history_manager = None
        
        # Track current navigation to avoid duplicate history entries
        self._pending_navigation = None  # URL being navigated to
        self._last_recorded_url = None  # Last URL added to history
        
        self.init_ui()
        
        # Apply BlurWindow effect
        self.apply_blur_effect()
        
        self.restore_geometry()
        
        # Debug: print size after initialization
        print(f"🏠 UnifiedAssistantWindow initialized, size: {self.size()}")
    
    def apply_blur_effect(self):
        """Apply BlurWindow transparency effect"""
        if BLUR_WINDOW_AVAILABLE:
            try:
                # Use the proper Windows version detection from graphics_compatibility
                graphics_compat = WindowsGraphicsCompatibility()
                windows_version = graphics_compat._get_windows_version()
                print(f"Detected system version: {windows_version}")
                
                # Set window rounded corners
                self.set_window_rounded_corners()
                
                # Always use Win10 Aero effect
                GlobalBlur(
                    int(self.winId()), 
                    Acrylic=False,   # Win10 Aero effect
                    Dark=False,      # Light theme
                    QWidget=self
                )
                print("✅ Win10 Aero effect applied")
                    
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
        """Initialize the main window UI"""
        self.setWindowTitle("GameWiki Assistant")
        
        # Ensure the window can be freely resized, remove any size restrictions
        self.setMinimumSize(300, 200)  # Set a reasonable Minimum size
        self.setMaximumSize(16777215, 16777215)  # Remove Maximum size restrictions
        
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
        # Ensure QStackedWidget does not force size changes
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Chat view
        self.chat_view = ChatView()
        self.chat_view.wiki_requested.connect(self.show_wiki_page)
        # Ensure the chat view maintains its size
        self.chat_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Wiki view
        self.wiki_view = WikiView()
        self.wiki_view.back_requested.connect(self.show_chat_view)  # This will restore input/shortcuts
        self.wiki_view.wiki_page_loaded.connect(self.handle_wiki_page_loaded)
        # Ensure WikiView has a reasonable Minimum size but does not force a fixed size
        self.wiki_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        self.content_stack.addWidget(self.chat_view)
        self.content_stack.addWidget(self.wiki_view)
        
        # Shortcuts container (above input area)
        self.shortcut_container = QFrame()
        self.shortcut_container.setObjectName("shortcutContainer")
        self.shortcut_container.setFixedHeight(35)
        
        self.shortcut_layout = QHBoxLayout(self.shortcut_container)
        self.shortcut_layout.setContentsMargins(10, 4, 10, 4)
        self.shortcut_layout.setSpacing(8)
        
        # Don't load shortcuts immediately - defer to after window is shown
        self.shortcuts_loaded = False
        
        # Input area - create integrated search bar following frameless_blur_window design
        self.input_container = QFrame()
        self.input_container.setObjectName("inputContainer")
        self.input_container.setFixedHeight(115)  # Adjusted height for two-row design
        
        input_layout = QVBoxLayout(self.input_container)
        input_layout.setContentsMargins(20, 10, 20, 10)
        input_layout.setSpacing(10)
        
        # Integrated search container (two rows)
        search_container = QFrame()
        search_container.setObjectName("searchContainer")
        search_container.setFixedHeight(90)
        
        # Search container internal layout
        container_layout = QVBoxLayout(search_container)
        container_layout.setContentsMargins(12, 8, 12, 8)
        container_layout.setSpacing(6)
        
        # Top row: Search input only
        search_input_row = QFrame()
        search_input_row.setObjectName("searchInputRow")
        
        input_row_layout = QHBoxLayout(search_input_row)
        input_row_layout.setContentsMargins(0, 0, 0, 0)
        input_row_layout.setSpacing(8)
        
        # Search input field
        self.input_field = QLineEdit()
        self.input_field.setObjectName("searchInput")
        self.input_field.setPlaceholderText("Recommend content / Search game content")
        self.input_field.returnPressed.connect(self.on_input_return_pressed)
        
        input_row_layout.addWidget(self.input_field)
        
        # Bottom row: Quick access buttons
        quick_access_row = QFrame()
        quick_access_row.setObjectName("quickAccessRow")
        
        access_layout = QHBoxLayout(quick_access_row)
        access_layout.setContentsMargins(0, 0, 0, 0)
        access_layout.setSpacing(0)
        
        # History button
        self.history_button = QPushButton()
        self.history_button.setObjectName("historyBtn")
        self.history_button.setFixedSize(32, 32)
        self.history_button.setToolTip("History")
        self.history_button.clicked.connect(self.show_history_menu)
        
        # Load history icon
        import pathlib
        base_path = pathlib.Path(__file__).parent.parent.parent  # Go up to project root
        history_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "refresh-ccw-clock-svgrepo-com.svg")
        history_icon = load_svg_icon(history_icon_path, color="#111111", size=20)
        self.history_button.setIcon(history_icon)
        self.history_button.setIconSize(QSize(20, 20))
        
        # Quick Access button (replaces external website button)
        self.quick_access_button = QPushButton()
        self.quick_access_button.setObjectName("externalBtn")
        self.quick_access_button.setFixedSize(32, 32)
        self.quick_access_button.setToolTip("Go to external website")
        # Connect click handler
        self.quick_access_button.clicked.connect(self.on_quick_access_clicked)
        
        # Load quick access icon
        external_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "globe-alt-1-svgrepo-com.svg")
        external_icon = load_svg_icon(external_icon_path, color="#111111", size=20)
        self.quick_access_button.setIcon(external_icon)
        self.quick_access_button.setIconSize(QSize(20, 20))
        
        # Search mode button
        self.mode_button = QPushButton()
        self.mode_button.setObjectName("searchBtn")
        self.mode_button.setFixedSize(32, 32)
        self.mode_button.setToolTip("Search Mode")
        self.mode_button.clicked.connect(self.show_mode_menu)
        
        # Load search icon
        search_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "search-alt-1-svgrepo-com.svg")
        search_icon = load_svg_icon(search_icon_path, color="#111111", size=20)
        self.mode_button.setIcon(search_icon)
        self.mode_button.setIconSize(QSize(20, 20))
        
        # Send button
        self.send_button = QPushButton()
        self.send_button.setObjectName("sendBtn")
        self.send_button.setFixedSize(32, 32)
        self.send_button.clicked.connect(self.on_send_clicked)
        
        # Load send icon
        send_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "arrow-circle-up-svgrepo-com.svg")
        send_icon = load_svg_icon(send_icon_path, color="#111111", size=20)
        self.send_button.setIcon(send_icon)
        self.send_button.setIconSize(QSize(20, 20))
        
        # Add buttons to bottom row
        access_layout.addWidget(self.history_button)
        access_layout.addWidget(self.quick_access_button)
        access_layout.addWidget(self.mode_button)
        
        # Single task flow button (will change based on current game)
        self.task_flow_button = QPushButton()
        self.task_flow_button.setObjectName("taskFlowBtn")
        # Dynamic sizing based on content
        self.task_flow_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.task_flow_button.setMinimumHeight(32)
        self.task_flow_button.setToolTip(t("task_flow"))
        self.task_flow_button.hide()  # Initially hidden
        
        # Load task flow icon
        task_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "layers-svgrepo-com.svg")
        task_icon = load_svg_icon(task_icon_path, color="#111111", size=20)
        self.task_flow_button.setIcon(task_icon)
        self.task_flow_button.setIconSize(QSize(20, 20))
        
        access_layout.addWidget(self.task_flow_button)
        
        # Initialize current task flow game
        self.current_task_flow_game = None
        
        access_layout.addStretch()  # Space in middle
        access_layout.addWidget(self.send_button)
        
        # Add rows to search container
        container_layout.addWidget(search_input_row)
        container_layout.addWidget(quick_access_row)
        
        # Add search container to input container
        input_layout.addWidget(search_container)
        
        # Current mode
        self.current_mode = "auto"
        
        # Add to main layout with stretch factor
        main_layout.addWidget(self.content_stack, 1)  # Stretch factor 1, occupy all available space
        # Removed shortcut_container - shortcuts now in popup
        main_layout.addWidget(self.input_container, 0)     # Stretch factor 0, keep fixed height
        
        # Apply transparent styles
        self.setup_transparent_styles()
        
        # Enable mouse tracking for all children
        self.enable_mouse_tracking_for_children()
    
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
    
    def enable_mouse_tracking_for_children(self):
        """Enable mouse tracking for all child widgets recursively"""
        def enable_tracking(widget):
            widget.setMouseTracking(True)
            for child in widget.findChildren(QWidget):
                enable_tracking(child)
        
        enable_tracking(self)
        
    def reset_size_constraints(self):
        """Reset window size constraints, ensure free resizing"""
        self.setMinimumSize(300, 200)  # Keep reasonable Minimum size
        self.setMaximumSize(16777215, 16777215)  # Remove Maximum size restrictions
        
    def setup_transparent_styles(self):
        """Set up styles with blur effect"""
        style_sheet = """
        QMainWindow {
            background: transparent;
        }
        
        /* Global menu styling for consistent appearance */
        QMenu {
            background-color: white;
            border: 1px solid #d0d0d0;
            border-radius: 8px;
            padding: 5px;
        }
        
        QMenu::item {
            padding: 5px 20px;
            background-color: transparent;
            border-radius: 4px;
        }
        
        QMenu::item:selected {
            background-color: #f0f0f0;
        }
        
        QMenu::separator {
            height: 1px;
            background-color: #e0e0e0;
            margin: 5px 10px;
        }
        
        #mainContainer {
            background: rgba(255, 255, 255, 115);
            border-radius: 10px;  /* Remove rounded corners from main container */
            border: none;
        }
        
        #titleBar {
            background: rgba(255, 255, 255, 115);
            border-top-left-radius: 0px;  /* Remove rounded corners */
            border-top-right-radius: 0px;  /* Remove rounded corners */
        }
        
        #titleLabel {
            color: #111111;
            font-size: 14px;
            font-weight: bold;
            font-family: "Segoe UI", "Microsoft YaHei", Arial;
        }
        
        #minBtn, #closeBtn {
            background: rgba(255, 255, 255, 150);
            border: none;
            border-radius: 5px;
            color: #111111;
            font-weight: bold;
            font-family: "Segoe UI", "Microsoft YaHei", Arial;
        }
        
        #minBtn:hover, #closeBtn:hover {
            background: rgba(220, 220, 220, 180);
        }
        
        #closeBtn:hover {
            background: rgba(220, 60, 60, 180);
            color: white;
        }
        
        /* Shortcut container - hidden by default */
        #shortcutContainer {
            background: rgba(255, 255, 255, 115);
        }
        
        /* Input container - updated background */
        #inputContainer {
            background: rgba(255, 255, 255, 115);
            border-bottom-left-radius: 0px;  /* Remove rounded corners */
            border-bottom-right-radius: 0px;  /* Remove rounded corners */
        }
        
        /* Search container - integrated two-row design */
        #searchContainer {
            background: rgba(0, 0, 0, 10);
            border: 1px solid rgba(200, 200, 200, 150);
            border-radius: 10px;  
        }
        
        #searchInputRow, #quickAccessRow {
            background: transparent;
            border: none;
        }
        
        /* Search input field */
        #searchInput {
            background: transparent;
            border: none;
            color: #111111;
            font-size: 14px;
            font-family: "Segoe UI", "Microsoft YaHei", Arial;
            padding: 0 5px;
        }
        
        #searchInput:focus {
            background: transparent;
            border: none;
            outline: none;
        }
        
        /* Button styles for the bottom row */
        #historyBtn, #externalBtn, #searchBtn, #sendBtn {
            background: transparent;
            border: none;
            color: #111111;
            font-size: 12px;
            font-weight: normal;
        }
        
        /* Task flow button with dynamic sizing */
        #taskFlowBtn {
            background: transparent;
            border: none;
            color: #111111;
            font-size: 12px;
            font-weight: normal;
            padding: 6px 12px;
            min-width: auto;
        }
        
        #historyBtn:hover, #externalBtn:hover, #searchBtn:hover, #taskFlowBtn:hover {
            background: rgba(220, 220, 220, 120);
            border-radius: 4px;
        }
        
        #sendBtn:hover {
            background: rgba(220, 220, 220, 120);
            border-radius: 4px;
        }
        
        /* Send button special states */
        #sendBtn[stop_mode="true"] {
            background-color: rgba(255, 77, 79, 200);
            border-radius: 4px;
        }
        
        #sendBtn[stop_mode="true"]:hover {
            background-color: rgba(255, 120, 117, 200);
        }
        
        /* Chat view styles - updated background */
        ChatView {
            background: rgba(255, 255, 255, 115);
            border: none;
            border-radius: 0px;  /* Remove rounded corners from chat content */
        }
        
        /* Chat container widget */
        ChatView QWidget {
            background: transparent;
        }
        
        /* Chat scrollbar */
        ChatView QScrollBar:vertical {
            background: rgba(240, 240, 240, 150);
            width: 12px;
            border-radius: 6px;
        }
        
        ChatView QScrollBar::handle:vertical {
            background: rgba(180, 180, 180, 200);
            border-radius: 6px;
            min-height: 20px;
        }
        
        ChatView QScrollBar::handle:vertical:hover {
            background: rgba(150, 150, 150, 220);
        }
        
        MessageWidget {
            background: transparent;
        }
        
        /* Message bubble enhanced styles */
        QFrame#messageBubble {
            border-radius: 18px;
            padding: 4px;
        }
        
        /* Welcome message styles */
        QLabel[messageType="welcome"] {
            background: rgba(255, 255, 255, 180);
            border: 1px solid rgba(224, 224, 224, 120);
            border-radius: 12px;
            padding: 15px;
            color: #666;
            font-size: 14px;
        }
        
        /* Status message styles */
        QFrame#statusBubble {
            background-color: rgba(240, 248, 255, 200);
            border: 1px solid rgba(224, 232, 240, 150);
            border-radius: 18px;
            padding: 4px;
        }
        """
        self.setStyleSheet(style_sheet)
        
    def restore_geometry(self):
        """Restore window geometry from settings with enhanced screen compatibility"""
        if self.settings_manager:
            try:
                scale = _get_scale()  # Get DPI scaling factor
                settings = self.settings_manager.get()
                popup_dict = settings.get('popup', {})
                
                # Use availableGeometry to get the available screen area (excluding taskbars, etc.)
                screen = QApplication.primaryScreen().availableGeometry()
                
                # Check if it is the first use or the configuration is incomplete
                is_first_use = not popup_dict or len(popup_dict) < 4
                
                if is_first_use:
                    # First use, create smart default configuration
                    popup_config = PopupConfig.create_smart_default(screen)
                    print(f"📍 First use, create smart default window configuration")
                else:
                    # Create PopupConfig instance from settings
                    popup_config = PopupConfig(**popup_dict)
                
                # Get absolute coordinates (already includes screen adaptation and boundary checks)
                phys_x, phys_y, phys_w, phys_h = popup_config.get_absolute_geometry(screen)
                
                # Apply DPI scaling
                if scale != 1.0:
                    # If using relative coordinates, no additional DPI scaling is needed (already handled in get_absolute_geometry)
                    if not popup_config.use_relative_position:
                        phys_x = int(phys_x * scale)
                        phys_y = int(phys_y * scale)
                    if not popup_config.use_relative_size:
                        phys_w = int(phys_w * scale)
                        phys_h = int(phys_h * scale)
                
                # Final boundary check (considering values after DPI scaling)
                phys_x, phys_y, phys_w, phys_h = self._final_geometry_check(
                    phys_x, phys_y, phys_w, phys_h, screen
                )
                
                self.setGeometry(phys_x, phys_y, phys_w, phys_h)
                
                # Record detailed window restoration information
                screen_info = f"{screen.width()}x{screen.height()}"
                position_type = "Relative coordinates" if popup_config.use_relative_position else "Absolute coordinates"
                size_type = "Relative size" if popup_config.use_relative_size else "Fixed size"
                
                logging.info(f"Restore window geometry: position({phys_x},{phys_y}) size({phys_w}x{phys_h}) "
                           f"screen({screen_info}) DPI scaling({scale:.2f}) "
                           f"configuration({position_type}+{size_type})")
                
                # After restoring geometry, reset size constraints to ensure free resizing
                self.reset_size_constraints()
                
                # If it is the first use and a smart default configuration is created, save to settings
                if is_first_use:
                    self._save_initial_geometry_config(popup_config)
                
            except Exception as e:
                logging.error(f"Failed to restore window geometry information: {e}")
                # Use safe default values when failed
                self._apply_safe_default_geometry()
        else:
            self._apply_safe_default_geometry()
    
    def _final_geometry_check(self, x, y, width, height, screen):
        """
        Final geometry check, ensure the window is fully visible and operable
        
        Args:
            x, y, width, height: Window geometry parameters
            screen: Screen available area
            
        Returns:
            tuple: Adjusted (x, y, width, height)
        """
        # Ensure Minimum size
        min_width, min_height = 300, 200
        width = max(min_width, width)
        height = max(min_height, height)
        
        # Ensure Maximum size does not exceed screen
        max_width = screen.width() - 20
        max_height = screen.height() - 40
        width = min(width, max_width)
        height = min(height, max_height)
        
        # Ensure position is within visible range
        margin = 10
        max_x = screen.x() + screen.width() - width - margin
        max_y = screen.y() + screen.height() - height - margin
        min_x = screen.x() + margin
        min_y = screen.y() + margin
        
        x = max(min_x, min(x, max_x))
        y = max(min_y, min(y, max_y))
        
        return x, y, width, height
    
    def _apply_safe_default_geometry(self):
        """Apply safe default geometry configuration"""
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            # Use the safe position on the right side of the screen
            safe_width = min(600, screen.width() - 100)
            safe_height = min(500, screen.height() - 100)
            safe_x = screen.x() + (screen.width() - safe_width) // 2 + 50
            safe_y = screen.y() + (screen.height() - safe_height) // 4
            
            self.setGeometry(safe_x, safe_y, safe_width, safe_height)
            logging.info(f"Apply safe default geometry: ({safe_x},{safe_y},{safe_width},{safe_height})")
        except Exception as e:
            # Last fallback solution
            logging.error(f"Apply safe default geometry failed: {e}")
            self.setGeometry(100, 100, 600, 500)
        
        self.reset_size_constraints()
    
    def _save_initial_geometry_config(self, popup_config):
        """
        Save initial geometry configuration to settings file
        
        Args:
            popup_config: PopupConfig instance
        """
        try:
            from dataclasses import asdict
            popup_dict = asdict(popup_config)
            self.settings_manager.update({'popup': popup_dict})
            logging.info("Saved smart default window configuration to settings file")
        except Exception as e:
            logging.warning(f"Failed to save initial geometry configuration: {e}")
    
    def save_geometry(self):
        """Save window geometry to settings with enhanced format support"""
        if self.settings_manager:
            try:
                scale = _get_scale()  # Get DPI scaling factor
                geo = self.geometry()
                screen = QApplication.primaryScreen().availableGeometry()
                
                # Get current settings to maintain consistency
                current_settings = self.settings_manager.get()
                current_popup = current_settings.get('popup', {})
                
                # Check if current configuration uses relative coordinates
                use_relative_position = current_popup.get('use_relative_position', False)
                use_relative_size = current_popup.get('use_relative_size', False)
                
                if use_relative_position:
                    # Save as relative coordinates (0.0-1.0)
                    left_percent = (geo.x() - screen.x()) / screen.width() if screen.width() > 0 else 0.5
                    top_percent = (geo.y() - screen.y()) / screen.height() if screen.height() > 0 else 0.1
                    
                    # Ensure relative coordinates are within reasonable range
                    left_percent = max(0.0, min(1.0, left_percent))
                    top_percent = max(0.0, min(1.0, top_percent))
                else:
                    # Save as absolute coordinates (logical pixels)
                    left_percent = current_popup.get('left_percent', 0.6)
                    top_percent = current_popup.get('top_percent', 0.1)
                
                if use_relative_size:
                    # Save as relative size
                    width_percent = geo.width() / screen.width() if screen.width() > 0 else 0.4
                    height_percent = geo.height() / screen.height() if screen.height() > 0 else 0.7
                    
                    # Ensure relative size is within reasonable range
                    width_percent = max(0.2, min(0.9, width_percent))
                    height_percent = max(0.3, min(0.9, height_percent))
                else:
                    # Save as fixed size
                    width_percent = current_popup.get('width_percent', 0.4)
                    height_percent = current_popup.get('height_percent', 0.7)
                
                # Convert to logical pixel coordinates (for backward compatibility)
                css_x = int(geo.x() / scale) if scale != 1.0 else geo.x()
                css_y = int(geo.y() / scale) if scale != 1.0 else geo.y()
                css_w = int(geo.width() / scale) if scale != 1.0 else geo.width()
                css_h = int(geo.height() / scale) if scale != 1.0 else geo.height()
                
                # Build complete popup configuration
                popup_config = {
                    # Traditional fixed coordinates (for backward compatibility)
                    'left': css_x,
                    'top': css_y,
                    'width': css_w,
                    'height': css_h,
                    # New relative coordinate system
                    'use_relative_position': use_relative_position,
                    'left_percent': left_percent,
                    'top_percent': top_percent,
                    'width_percent': width_percent,
                    'height_percent': height_percent,
                    'use_relative_size': use_relative_size,
                }
                
                # Update configuration
                self.settings_manager.update({'popup': popup_config})
                
                # Record saved information
                pos_type = "Relative" if use_relative_position else "Absolute"
                size_type = "Relative" if use_relative_size else "Fixed"
                logging.info(f"Save window geometry: {pos_type} position({css_x},{css_y}|{left_percent:.2f},{top_percent:.2f}) "
                           f"{size_type} size({css_w}x{css_h}|{width_percent:.2f}x{height_percent:.2f}) "
                           f"DPI scaling({scale:.2f})")
                
            except Exception as e:
                logging.error(f"Failed to save window geometry information: {e}")
                # Fallback to save basic information
                try:
                    geo = self.geometry()
                    self.settings_manager.update({
                        'popup': {
                            'left': geo.x(),
                            'top': geo.y(),
                            'width': geo.width(),
                            'height': geo.height()
                        }
                    })
                    logging.warning("Save window geometry information using basic format")
                except Exception as fallback_error:
                    logging.error(f"Failed to save window geometry information using basic format: {fallback_error}")
    
    def show_chat_view(self):
        """Switch to chat view"""
        # First stop media playback in WikiView (only pause when currently displaying WikiView)
        if hasattr(self, 'wiki_view') and self.wiki_view:
            current_widget = self.content_stack.currentWidget()
            if current_widget == self.wiki_view:
                self.wiki_view.pause_page()
            
        self.content_stack.setCurrentWidget(self.chat_view)
        # Show input area and shortcuts in chat mode
        if hasattr(self, 'input_container'):
            self.input_container.show()
        # Shortcut container is now hidden - shortcuts are in popup
        # Reset size constraints when switching to chat view
        self.reset_size_constraints()
        # Ensure message width is correct and trigger full layout update
        QTimer.singleShot(50, self.chat_view.update_all_message_widths)
        # Delay executing full layout update, ensure content is fully displayed
        QTimer.singleShot(100, self.chat_view._performDelayedResize)
        # Set focus to input field when returning to chat view
        QTimer.singleShot(150, self._set_chat_input_focus)
        
    def _set_chat_input_focus(self):
        """Set focus to input field in chat view with improved reliability"""
        if not hasattr(self, 'input_field') or not self.input_field:
            return
            
        logger = logging.getLogger(__name__)
        
        def try_set_focus():
            try:
                # 1. Ensure window is properly shown and active
                if not self.isVisible():
                    logger.warning("Window is not visible, cannot set focus")
                    return False
                    
                # 2. Bring window to front and activate
                self.raise_()
                self.activateWindow()
                
                # 3. Wait a bit for window manager to process
                QApplication.processEvents()
                
                # 4. Verify window is actually active
                if not self.isActiveWindow():
                    logger.warning("Window is not active after activation attempt")
                    # Try once more
                    self.activateWindow()
                    QApplication.processEvents()
                
                # 5. Set focus to input field
                self.input_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
                
                # 6. Verify focus was set
                if self.input_field.hasFocus():
                    logger.info("✅ Chat input focus set successfully")
                    return True
                else:
                    logger.warning("⚠️ Input field does not have focus after setting")
                    return False
                    
            except Exception as e:
                logger.warning(f"❌ Failed to set chat input focus: {e}")
                return False
        
        # Try immediately first
        if try_set_focus():
            return
            
        # If immediate attempt fails, try again after a longer delay
        logger.info("🔄 Retrying focus setting after delay...")
        QTimer.singleShot(300, lambda: try_set_focus())

    def show_wiki_page(self, url: str, title: str):
        """Switch to wiki view and load page"""
        logger = logging.getLogger(__name__)
        logger.info(f"🌐 UnifiedAssistantWindow.show_wiki_page called: URL={url}, Title={title}")
        
        # Only add to history if:
        # 1. Not a local file
        # 2. Not the same as last recorded URL
        # 3. Has a meaningful title (not just domain)
        if (hasattr(self, 'history_manager') and 
            not url.startswith('file://') and 
            url != self._last_recorded_url and
            title and title.strip() != ""):
            
            # Check if title is just a domain (indicates quick access)
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                is_just_domain = (title == parsed.netloc)
            except:
                is_just_domain = False
            
            # Only record if we have a real title, not just domain
            if not is_just_domain:
                # Determine source type
                if "wiki" in url.lower() or "wiki" in title.lower():
                    source = "wiki"
                else:
                    source = "web"
                self._ensure_history_manager()
                self.history_manager.add_entry(url, title, source=source)
                self._last_recorded_url = url
            else:
                # Mark as pending for when real title arrives
                self._pending_navigation = url
        
        self.wiki_view.load_wiki(url, title)
        self.content_stack.setCurrentWidget(self.wiki_view)
        
        # Restore page activity in WikiView (if previously paused)
        self.wiki_view.resume_page()
        
        # Hide input area and shortcuts in wiki mode
        if hasattr(self, 'input_container'):
            self.input_container.hide()
        # Shortcut container is now hidden - shortcuts are in popup
        # Reset size constraints when switching to Wiki view
        self.reset_size_constraints()
        logger.info(f"✅ Switched to Wiki view and loaded page")
        
    def handle_wiki_page_loaded(self, url: str, title: str):
        """Handle Wiki page loaded signal, forward signal to controller"""
        print(f"🌐 UnifiedAssistantWindow: Wiki page loaded - {title}: {url}")
        # Emit signal to controller for processing
        self.wiki_page_found.emit(url, title)
        
    def set_mode(self, mode: str):
        """Set the input mode (auto, wiki, ai or url)"""
        from src.game_wiki_tooltip.i18n import t
        
        self.current_mode = mode
        if mode == "url":
            self.input_field.setPlaceholderText("Enter URL...")
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_open_url_clicked)
        elif mode == "wiki":
            self.input_field.setPlaceholderText("Enter search query...")
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_send_clicked)
        elif mode == "ai":
            self.input_field.setPlaceholderText("Enter question...")
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_send_clicked)
        else:  # auto mode
            self.input_field.setPlaceholderText("Enter message...")
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_send_clicked)
    
    def on_input_return_pressed(self):
        """Handle return key press based on current mode"""
        if self.current_mode == "url":
            self.on_open_url_clicked()
        else:
            self.on_send_clicked()
    
    def on_open_url_clicked(self):
        """Handle URL open button click"""
        url = self.input_field.text().strip()
        if url:
            # Ensure URL has protocol
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            self.open_url(url)
            self.input_field.clear()
    
    def open_url(self, url: str):
        """Open a URL in the wiki view"""
        # Mark as pending navigation (don't record history yet)
        self._pending_navigation = url
        
        # Extract domain as temporary title
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            title = parsed.netloc or url
        except:
            title = url
            
        # Switch to wiki view and load URL (without recording history)
        self.wiki_view.load_wiki(url, title)
        self.content_stack.setCurrentWidget(self.wiki_view)
        self.wiki_view.resume_page()
        
        # Hide input area and shortcuts in wiki mode
        if hasattr(self, 'input_container'):
            self.input_container.hide()
        # Shortcut container is now hidden - shortcuts are in popup
        # Reset size constraints when switching to Wiki view
        self.reset_size_constraints()
        
        logger = logging.getLogger(__name__)
        logger.info("✅ Switched to Wiki view for URL navigation")
    
    def load_shortcuts(self):
        """Load shortcut buttons from settings"""
        try:
            # Clear existing buttons in popup
            self.quick_access_popup.clear_shortcuts()
            
            # Get shortcuts from settings
            shortcuts = []
            if self.settings_manager:
                try:
                    shortcuts = self.settings_manager.get('shortcuts', [])
                except Exception as e:
                    print(f"Failed to get shortcuts from settings: {e}")
                    
            
            # Filter out hidden shortcuts
            visible_shortcuts = [s for s in shortcuts if s.get('visible', True)]
            
            # Hide shortcut container - shortcuts are now in popup
            if hasattr(self, 'shortcut_container'):
                self.shortcut_container.hide()
            
            # Create buttons for visible shortcuts only
            for shortcut in visible_shortcuts:
                try:
                    # Use package_file to get correct path
                    from src.game_wiki_tooltip.utils import package_file
                    icon_path = ""
                    if shortcut.get('icon'):
                        try:
                            relative_path = shortcut.get('icon', '')
                            print(f"[load_shortcuts] Trying to load icon: {relative_path}")
                            
                            # Get the actual file path
                            import pathlib
                            # Try direct path first (for development)
                            base_path = pathlib.Path(__file__).parent
                            # relative_path already contains "assets/icons/..."
                            direct_path = base_path / relative_path
                            
                            if direct_path.exists():
                                icon_path = str(direct_path)
                                print(f"[load_shortcuts] Using direct path: {icon_path}")
                            else:
                                # Try package_file for packaged app
                                try:
                                    # Remove 'assets/' prefix for package_file call
                                    package_path = relative_path
                                    if relative_path.startswith('assets/'):
                                        package_path = relative_path[7:]  # Remove 'assets/'
                                    path_obj = package_file(package_path)
                                    # For resources, we might need to extract
                                    if hasattr(path_obj, 'read_bytes'):
                                        # It's a resource, we need to save it temporarily
                                        import tempfile
                                        data = path_obj.read_bytes()
                                        suffix = pathlib.Path(relative_path).suffix
                                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                                            tmp.write(data)
                                            icon_path = tmp.name
                                        print(f"[load_shortcuts] Extracted resource to: {icon_path}")
                                    else:
                                        icon_path = str(path_obj)
                                        print(f"[load_shortcuts] package_file path: {icon_path}")
                                except Exception as e:
                                    print(f"[load_shortcuts] Failed with package_file: {e}")
                                    icon_path = ""
                        except Exception as e:
                            print(f"[load_shortcuts] Failed to get icon path: {e}")
                            icon_path = ""
                    
                    name = shortcut.get('name', 'Website')
                    btn = ExpandableIconButton(
                        icon_path,
                        f"Go to {name}",
                        shortcut.get('url', 'https://google.com'),
                        name  # Pass the name for text display
                    )
                    btn.clicked.connect(lambda checked, url=shortcut.get('url', ''): self.open_url(url))
                    # Add to popup instead of shortcut_layout
                    self.quick_access_popup.add_shortcut(btn)
                except Exception as e:
                    print(f"Failed to create shortcut button: {e}")
            
            # Note: Task flow buttons are now in the main button row, not in popup
            
            # Mark shortcuts as loaded
            self.shortcuts_loaded = True
            
        except Exception as e:
            print(f"Error in load_shortcuts: {e}")

    def _open_game_task_flow(self, config):
        """Open game task flow HTML file"""
        try:
            # Prevent multiple clicks
            if hasattr(self, '_task_flow_loading') and self._task_flow_loading:
                return
            self._task_flow_loading = True
            
            # Get current language setting
            current_language = 'en'
            if self.settings_manager:
                settings = self.settings_manager.get()
                current_language = settings.get('language', 'en')
            
            # Select corresponding HTML file based on language
            html_filename = config['html_files'].get(current_language, config['html_files']['en'])
            
            # Get HTML file path
            import pathlib
            base_path = pathlib.Path(__file__).parent
            html_path = base_path / "assets" / "html" / html_filename
            
            if html_path.exists():
                print(f"Loading task flow from: {html_path}")
                
                # Display directly in the application, same as wiki link logic
                try:
                    title = t("dst_task_flow_title")

                    # Use the same display logic as wiki link
                    self._load_local_html_in_wiki_view(html_path, title)
                    
                except Exception as html_error:
                    print(f"Failed to load HTML content: {html_error}")
            else:
                print(f"DST task flow file not found: {html_path}")
                
        except Exception as e:
            print(f"Failed to open DST task flow: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Reset loading flag
            self._task_flow_loading = False
    
    def _load_local_html_in_wiki_view(self, html_path: pathlib.Path, title: str):
        """Load local HTML file with the same logic as wiki link"""
        try:
            # Create file:// URL, same as normal wiki link processing
            file_url = html_path.as_uri()
            print(f"Loading local HTML with file URL: {file_url}")
            
            # Use standard show_wiki_page method, ensure consistent behavior with other wiki links
            self.show_wiki_page(file_url, title)
            
        except Exception as e:
            print(f"Failed to load local HTML in wiki view: {e}")
    
    def show_history_menu(self):
        """Show history menu"""
        self._ensure_history_manager()
            
        history_menu = QMenu(self)  # Use standard QMenu with parent
        
        # Get history
        history_items = self.history_manager.get_history(limit=20)
        
        if not history_items:
            no_history_action = history_menu.addAction("No browsing history")
            no_history_action.setEnabled(False)
        else:
            # Add header
            header_action = history_menu.addAction("Recent Pages")
            header_action.setEnabled(False)
            header_font = header_action.font()
            header_font.setBold(True)
            header_action.setFont(header_font)
            history_menu.addSeparator()
            
            # Add history items
            for item in history_items[:10]:  # Show top 10
                title = item.get('title', 'Untitled')
                url = item.get('url', '')
                visit_count = item.get('visit_count', 1)
                
                # Truncate long titles
                if len(title) > 40:
                    title = title[:37] + "..."
                
                # Create action text with visit count if > 1
                if visit_count > 1:
                    action_text = f"{title} ({visit_count}x)"
                else:
                    action_text = title
                
                action = history_menu.addAction(action_text)
                action.setToolTip(url)
                
                # Connect to open the URL
                action.triggered.connect(lambda checked, u=url, t=item.get('title', 'Untitled'): self.show_wiki_page(u, t))
            
            if len(history_items) > 10:
                history_menu.addSeparator()
                more_action = history_menu.addAction(f"... and {len(history_items) - 10} more")
                more_action.setEnabled(False)
            
            # Add clear history option
            history_menu.addSeparator()
            clear_action = history_menu.addAction("Clear History")
            clear_action.triggered.connect(self.clear_history)
        
        # Show menu above the button (popup upward)
        # Calculate position to show menu above the button
        menu_height = history_menu.sizeHint().height()
        button_pos = self.history_button.mapToGlobal(QPoint(0, -menu_height))
        history_menu.exec(button_pos)
    
    def clear_history(self):
        """Clear browsing history"""
        self._ensure_history_manager()
        self.history_manager.clear_history()
        # Show notification
        QTimer.singleShot(100, lambda: self.history_button.setToolTip("History cleared"))
        QTimer.singleShot(2000, lambda: self.history_button.setToolTip("View browsing history"))

    def _show_task_flow_html(self, game_name):
        """Show task flow HTML for a specific game"""
        try:
            # Get current language setting
            current_language = 'en'
            if self.settings_manager:
                settings = self.settings_manager.get()
                current_language = settings.get('language', 'en')
            
            # Build config for the game
            config = {
                'game_name': game_name,
                'display_name': t(f'{game_name}_task_button'),
                'html_files': {
                    'en': f'{game_name}_en.html',
                    'zh': f'{game_name}_zh.html'
                }
            }
            
            # Call existing method
            self._open_game_task_flow(config)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to show task flow HTML for {game_name}: {e}")
            # Show error message
            self.chat_view.add_message(
                MessageType.STATUS,
                f"Unable to open {game_name} task flow"
            )

    def set_current_game_window(self, game_window_title: str):
        """Set current game window title and update task flow button visibility"""
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        
        # Debug: Log method call with stack trace to identify caller
        logger.info(f"🎮 [DEBUG] set_current_game_window called with: '{game_window_title}'")
        logger.debug(f"🔍 [DEBUG] Call stack (last 3 frames):")
        stack = traceback.extract_stack()
        for i, frame in enumerate(stack[-4:-1]):  # Skip current frame, show last 3
            logger.debug(f"    Frame {i+1}: {frame.filename}:{frame.lineno} in {frame.name}")
        
        # Debug: Log current state before change
        old_game_window = getattr(self, 'current_game_window', None)
        logger.info(f"🔄 [DEBUG] Game window change: '{old_game_window}' -> '{game_window_title}'")
        
        # Debug: Check if task buttons are initialized
        button_count = len(getattr(self, 'game_task_buttons', {}))
        logger.info(f"📋 [DEBUG] Current task buttons count: {button_count}")
        
        # Critical fix: Ensure task buttons are created before trying to update visibility
        if button_count == 0:
            logger.warning(f"⚠️ [DEBUG] Task buttons not created yet, creating them first")
            logger.warning(f"⚠️ [DEBUG] Game task layout not available, buttons will be created later")
        
        # Set the new game window
        self.current_game_window = game_window_title
        
        # Debug: Log before button visibility update
        logger.info(f"🎯 [DEBUG] About to update task button visibility for: '{game_window_title}'")
        
        # Update task flow button based on current game
        self._update_task_flow_button()
        
        # Debug: Log completion
        logger.info(f"✅ [DEBUG] set_current_game_window completed for: '{game_window_title}'")
    
    def _update_task_flow_button(self):
        """Update task flow button visibility and functionality based on current game"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Define games that support task flow
        game_configs = {
            'dst': {
                'display_name': t('dst_task_button'),
                'window_titles': ["don't starve together", "dst"],
                'handler': lambda: self._show_task_flow_html('dst')
            },
            'helldiver2': {
                'display_name': t('helldiver2_task_button'),
                'window_titles': ["helldivers™ 2", "helldivers 2"],
                'handler': lambda: self._show_task_flow_html('helldiver2')
            },
            'civilization6': {
                'display_name': t('civ6_task_button'),
                'window_titles': ["sid meier's civilization vi", "civilization vi", "civ6"],
                'handler': lambda: self._show_task_flow_html('civilization6')
            }
        }
        
        if not self.current_game_window:
            # No game window set, hide task flow button
            self.task_flow_button.hide()
            self.current_task_flow_game = None
            return
            
        # Get normalized window title for comparison
        current_window_lower = self.current_game_window.lower()
        
        # Find matching game
        matched_game = None
        for game_name, config in game_configs.items():
            if any(title in current_window_lower for title in config['window_titles']):
                matched_game = game_name
                break
                
        if matched_game:
            # Show and configure task flow button
            config = game_configs[matched_game]
            self.task_flow_button.setText(config['display_name'])
            self.task_flow_button.show()
            
            # Disconnect previous handler if any
            try:
                self.task_flow_button.clicked.disconnect()
            except:
                pass
                
            # Connect new handler
            self.task_flow_button.clicked.connect(config['handler'])
            self.current_task_flow_game = matched_game
            
            logger.info(f"✅ Task flow button shown for {matched_game}")
        else:
            # No matching game, hide button
            self.task_flow_button.hide()
            self.current_task_flow_game = None
            logger.info(f"⚠️ No task flow available for current window: {self.current_game_window}")
    
    def on_quick_access_clicked(self):
        """Show quick access popup"""
        # Load shortcuts if not loaded
        if not self.shortcuts_loaded:
            self.load_shortcuts()
            
        # Show popup above the button
        self.quick_access_popup.show_at(self.quick_access_button)
        
    def eventFilter(self, obj, event):
        """Event filter to handle events"""
        # Remove hover behavior for quick access button
        return super().eventFilter(obj, event)
        
    def show_mode_menu(self):
        """Show search mode menu"""
        mode_menu = QMenu(self)  # Use standard QMenu with parent
        from src.game_wiki_tooltip.i18n import t
        
        auto_action = mode_menu.addAction(t("search_mode_auto"))
        auto_action.triggered.connect(lambda: self.set_mode("auto"))
        
        wiki_action = mode_menu.addAction(t("search_mode_wiki"))
        wiki_action.triggered.connect(lambda: self.set_mode("wiki"))
        
        ai_action = mode_menu.addAction(t("search_mode_ai"))
        ai_action.triggered.connect(lambda: self.set_mode("ai"))
        
        mode_menu.addSeparator()
        
        url_action = mode_menu.addAction(t("search_mode_url"))
        url_action.triggered.connect(lambda: self.set_mode("url"))
        
        # Show menu above the button (popup upward)
        # Calculate position to show menu above the button
        menu_height = mode_menu.sizeHint().height()
        button_pos = self.mode_button.mapToGlobal(QPoint(0, -menu_height))
        mode_menu.exec(button_pos)

    def on_send_clicked(self):
        """Handle send button click"""
        if self.is_generating:
            # If generating, stop generation
            self.stop_generation()
        else:
            # Normal send
            text = self.input_field.text().strip()
            if text:
                # Check if need to stop current generation (if any)
                if self.is_generating:
                    self.stop_generation()
                    
                self.input_field.clear()
                self.query_submitted.emit(text, self.current_mode)
    
    def set_generating_state(self, is_generating: bool, streaming_msg=None):
        """Set generation state"""
        self.is_generating = is_generating
        self.streaming_widget = streaming_msg
        
        # Get icon paths
        import pathlib
        base_path = pathlib.Path(__file__).parent.parent.parent
        pause_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "pause-circle-svgrepo-com.svg")
        send_icon_path = str(base_path / "src" / "game_wiki_tooltip" / "assets" / "icons" / "arrow-circle-up-svgrepo-com.svg")
        
        if is_generating:
            # Switch to stop mode with pause icon
            pause_icon = load_svg_icon(pause_icon_path, color="#ffffff", size=20)
            self.send_button.setIcon(pause_icon)
            self.send_button.setProperty("stop_mode", "true")
            self.input_field.setPlaceholderText("Click Stop to cancel generation...")
            self.input_field.setEnabled(False)  # Disable input field
        else:
            # Switch back to send mode with arrow icon
            send_icon = load_svg_icon(send_icon_path, color="#111111", size=20)
            self.send_button.setIcon(send_icon)
            if self.current_mode == "url":
                self.send_button.setText("Open")
            else:
                self.send_button.setText("")  # No text, icon only
            self.send_button.setProperty("stop_mode", "false")
            self.input_field.setPlaceholderText("Enter message..." if self.current_mode != "url" else "Enter URL...")
            self.input_field.setEnabled(True)  # Enable input field
            
        # Refresh style
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)
        self.send_button.update()
    
    def stop_generation(self):
        """Stop current generation"""
        print("🛑 User requested to stop generation")
        
        try:
            # First restore UI state, avoid user seeing stuck state
            self.set_generating_state(False)
            print("✅ UI state restored")
            
            # Hide status information
            try:
                self.chat_view.hide_status()
                print("✅ Status information hidden")
            except Exception as e:
                print(f"⚠️ Error hiding status information: {e}")
            
            # If there is current streaming message, mark as stopped
            if self.streaming_widget:
                try:
                    self.streaming_widget.mark_as_stopped()
                    print("✅ Streaming message marked as stopped")
                except Exception as e:
                    print(f"⚠️ Error marking streaming message as stopped: {e}")
            
            # Finally emit stop signal, use QTimer.singleShot to avoid possible deadlock
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._emit_stop_signal_safe())
            print("✅ Stop signal scheduled to be sent")
            
        except Exception as e:
            print(f"❌ Error during stop generation: {e}")
            # Even if error occurs, try to restore UI state
            try:
                self.set_generating_state(False)
            except:
                pass
                
    def _emit_stop_signal_safe(self):
        """Safely emit stop signal"""
        try:
            self.stop_generation_requested.emit()
            print("✅ Stop signal sent")
        except Exception as e:
            print(f"⚠️ Error sending stop signal: {e}")
    
    def contextMenuEvent(self, event):
        """Handle right-click menu event"""
        menu = QMenu(self)
        
        # Minimize to mini window
        minimize_action = menu.addAction(t("menu_minimize_to_mini"))
        minimize_action.triggered.connect(lambda: self.window_closing.emit())
        
        # Hide to tray
        hide_action = menu.addAction(t("menu_hide_to_tray"))
        hide_action.triggered.connect(self._on_hide_to_tray)
        
        menu.exec(event.globalPos())
        
    def _on_hide_to_tray(self):
        """Handle hide to tray request"""
        self.hide()
        self.visibility_changed.emit(False)
        
    def showEvent(self, event):
        """Handle show event - defer loading non-critical content"""
        super().showEvent(event)
        
        # Load shortcuts and history after window is shown
        if not self.shortcuts_loaded:
            self.shortcuts_loaded = True
            # Use QTimer to defer loading to next event loop iteration
            QTimer.singleShot(0, self._load_deferred_content)
            
    def _load_deferred_content(self):
        """Load non-critical content after window is shown"""
        try:
            # Load shortcuts
            print("📌 Loading shortcuts...")
            start_time = time.time()
            self.load_shortcuts()
            print(f"✅ Shortcuts loaded in {time.time() - start_time:.2f}s")
            
            # Initialize history manager
            print("📌 Initializing history manager...")
            start_time = time.time()
            self._ensure_history_manager()
            print(f"✅ History manager initialized in {time.time() - start_time:.2f}s")
            
            # Load other deferred content
            # Add more deferred loading here if needed
            
        except Exception as e:
            print(f"❌ Error loading deferred content: {e}")
            import traceback
            traceback.print_exc()
        
    def closeEvent(self, event):
        """Handle close event - just hide the window"""
        event.ignore()  # Don't actually close the window
        self.hide()  # Just hide it
        
        # Save geometry information
        try:
            self.save_geometry()
        except Exception:
            pass
            
        # Notify controller that window is closing
        self.window_closing.emit()
        
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key.Key_Escape:
            # Save geometry before hiding
            try:
                self.save_geometry()
            except Exception:
                pass
            self.hide()  # Hide instead of close
            self.window_closing.emit()  # Show mini window
        elif event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.on_send_clicked()
            
    def changeEvent(self, event):
        """Handle window state changes"""
        if event.type() == event.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                # Window is minimized, save geometry and hide it
                try:
                    self.save_geometry()
                except Exception:
                    pass
                # Hide and show mini window
                QTimer.singleShot(100, lambda: (
                    self.hide(),
                    self.setWindowState(Qt.WindowState.WindowNoState),
                    self.window_closing.emit()
                ))
        super().changeEvent(event)
    
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
            elif hasattr(self, 'title_bar') and self.title_bar.geometry().contains(pos):
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


class AssistantController:
    """Controller for the assistant system"""
    
    def __init__(self, settings_manager=None):
        self.settings_manager = settings_manager
        self.mini_window = None
        self.main_window = None
        self.current_mode = WindowMode.MINI
        self.current_game_window = None  # Record current game window title
        self._is_manually_hidden = False  # Record if user manually hidden the floating window
        self._was_hidden_before_hotkey = False  # Record hidden state before hotkey
        self._precreated = False  # Track if window has been pre-created
        
    def show_mini(self):
        """Show mini assistant"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("show_mini() called")
        
        # Check if need to restore previous hidden state
        if hasattr(self, '_was_hidden_before_hotkey') and self._was_hidden_before_hotkey:
            logger.info("Restoring hidden state from before hotkey")
            self._is_manually_hidden = True
            self._was_hidden_before_hotkey = False  # Reset flag
        
        # If user manually hidden the floating window, skip showing
        if self._is_manually_hidden:
            logger.info("Mini window was manually hidden, skipping show")
            # If there is main window, save geometry and hide it
            if self.main_window:
                logger.info("Hiding main window")
                try:
                    self.main_window.save_geometry()
                except Exception as e:
                    logger.warning(f"Failed to save geometry when hiding main window: {e}")
                self.main_window.hide()
            return
        
        if not self.mini_window:
            logger.info("Creating new MiniAssistant window")
            self.mini_window = MiniAssistant()
            self.mini_window.clicked.connect(self.expand_to_chat)
            self.mini_window.visibility_changed.connect(self._on_mini_window_visibility_changed)
            logger.info("MiniAssistant created and signal connected")
        
        # Show mini window
        logger.info("Showing mini window")
        self.mini_window.show()
        self.mini_window.raise_()
        self.mini_window.activateWindow()
        
        # If there is main window, save geometry and hide it
        if self.main_window:
            logger.info("Hiding main window")
            try:
                self.main_window.save_geometry()
            except Exception as e:
                logger.warning(f"Failed to save geometry when hiding main window: {e}")
            self.main_window.hide()
        
        self.current_mode = WindowMode.MINI
        logger.info("show_mini() completed")
        
    def set_current_game_window(self, game_window_title: str):
        """Set current game window title"""
        self.current_game_window = game_window_title
        
        # Pass game window information to main window
        if self.main_window:
            self.main_window.set_current_game_window(game_window_title)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🎮 Recording game window: '{game_window_title}'\n ")

    def precreate_chat_window(self):
        """Pre-create chat window for faster first-time response"""
        import logging
        logger = logging.getLogger(__name__)
        
        if self._precreated or self.main_window:
            logger.info("Chat window already created or pre-created")
            return
            
        try:
            logger.info("Pre-creating chat window...")
            
            # Create window but keep it hidden
            self.main_window = UnifiedAssistantWindow(self.settings_manager)
            self.main_window.query_submitted.connect(self.handle_query)
            self.main_window.window_closing.connect(self.show_mini)
            self.main_window.wiki_page_found.connect(self.handle_wiki_page_found)
            
            # CRITICAL FIX: Ensure task buttons are created during pre-creation
            # The issue: load_shortcuts (which creates task buttons) is only called in showEvent,
            # but pre-created windows are kept hidden, so showEvent never fires.
            logger.info(f"🔍 [DEBUG] Force loading shortcuts for pre-created window...")
            try:
                # Call _load_deferred_content directly since showEvent won't be triggered
                self.main_window._load_deferred_content()
                self.main_window.shortcuts_loaded = True  # Mark as loaded
                button_count = len(getattr(self.main_window, 'game_task_buttons', {}))
                logger.info(f"✅ [DEBUG] Shortcuts loaded for pre-created window, task buttons: {button_count}")
            except Exception as e:
                logger.error(f"❌ [DEBUG] Failed to load shortcuts for pre-created window: {e}")
            
            # If we already have a game context, set it AFTER shortcuts are loaded
            if self.current_game_window:
                self.main_window.set_current_game_window(self.current_game_window)
                logger.info(f"✅ [DEBUG] Set game context for pre-created window: {self.current_game_window}")
            
            # Important: Keep window hidden
            self.main_window.hide()
            
            # Mark as pre-created
            self._precreated = True
            logger.info("✅ Chat window pre-created and hidden")
            
        except Exception as e:
            logger.error(f"Failed to pre-create chat window: {e}")
            self.main_window = None
            self._precreated = False

    def expand_to_chat(self):
        """Expand from mini to chat window with animation"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("expand_to_chat() called")

        # Record hidden state before hotkey
        self._was_hidden_before_hotkey = self._is_manually_hidden
        logger.info(f"Recording hidden state before hotkey: {self._was_hidden_before_hotkey}")

        # User manually expanded window, clear manually hidden flag
        self._is_manually_hidden = False

        # Check if window is created but hidden
        if not self.main_window:
            logger.info("Creating new UnifiedAssistantWindow")
            self.main_window = UnifiedAssistantWindow(self.settings_manager)
            self.main_window.query_submitted.connect(self.handle_query)
            # When window is closed, go back to mini mode
            self.main_window.window_closing.connect(self.show_mini)
            self.main_window.wiki_page_found.connect(self.handle_wiki_page_found)
            self.main_window.visibility_changed.connect(self._on_main_window_visibility_changed)

            # CRITICAL FIX: Always set current game window for new window (ignore the flag)
            if self.current_game_window:
                logger.info(f"🎮 [DEBUG] Setting game window on NEW main window: '{self.current_game_window}'")
                self.main_window.set_current_game_window(self.current_game_window)
                logger.info(f"✅ [DEBUG] Game window set and task buttons should be visible now")
            else:
                logger.info(f"⚠️ [DEBUG] No current game window to set on new window")

            logger.info("UnifiedAssistantWindow created and signals connected")
        else:
            logger.info("Reusing existing UnifiedAssistantWindow")
            # For existing windows, always update game context to ensure task buttons are visible
            if self.current_game_window:
                logger.info(f"🎮 [DEBUG] Updating game window on EXISTING main window: '{self.current_game_window}'")
                self.main_window.set_current_game_window(self.current_game_window)
                logger.info(f"✅ [DEBUG] Game window updated and task buttons should be visible now")
            else:
                logger.info(f"⚠️ [DEBUG] No current game window to set on existing window")

        # Set window initial opacity to 0 (prepare fade-in animation)
        self.main_window.setWindowOpacity(0.0)

        # Ensure window is visible and focused
        logger.info("Showing main window with fade-in animation")
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

        # Debug: Check if input field exists
        if hasattr(self.main_window, 'input_field'):
            logger.info(f"Input field found: {self.main_window.input_field}")
        else:
            logger.warning("Input field not found in main window!")

        # Create fade-in animation
        self._fade_in_animation = QPropertyAnimation(self.main_window, b"windowOpacity")
        self._fade_in_animation.setDuration(100)  # 100ms fade-in animation (faster)
        self._fade_in_animation.setStartValue(0.0)
        self._fade_in_animation.setEndValue(1.0)
        self._fade_in_animation.setEasingCurve(QEasingCurve.Type.OutQuad)  # Faster curve
        self._fade_in_animation.start()

        if self.mini_window:
            logger.info("Mini window exists, hiding it")
            # Hide mini window
            self.mini_window.hide()

            # Restore main window to previous saved position and size
            self.main_window.restore_geometry()

            # Ensure window is within screen range
            screen = QApplication.primaryScreen().geometry()
            window_rect = self.main_window.geometry()

            # Adjust position to ensure window is visible
            x = max(10, min(window_rect.x(), screen.width() - window_rect.width() - 10))
            y = max(30, min(window_rect.y(), screen.height() - window_rect.height() - 40))

            if x != window_rect.x() or y != window_rect.y():
                self.main_window.move(x, y)
                logger.info(f"Adjusted window position to ensure visibility: ({x}, {y})")

            # Message width update and input field focus setting will be done after animation

            logger.info("Window position adjusted, fade-in animation in progress")
        else:
            logger.info("No mini window, showing main window with fade-in animation")
            # Use restore_geometry to restore previous window position and size
            self.main_window.restore_geometry()

            # During window animation, message width does not need to be updated (will be updated after animation)

        self.current_mode = WindowMode.CHAT

        # After animation, input field will be automatically focused, no additional processing needed

        logger.info("expand_to_chat() completed")
        
    def handle_wiki_page_found(self, url: str, title: str):
        """Handle signal when real wiki page is found (basic implementation, subclasses can override)"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔗 AssistantController received wiki page signal: {title} -> {url}")
        # Basic implementation: do nothing, subclasses (IntegratedAssistantController) will override this method
    
    def refresh_shortcuts(self):
        """Refresh shortcut buttons"""
        if self.main_window:
            self.main_window.load_shortcuts()
        
    def handle_query(self, query: str, mode: str = "auto"):
        """Handle user query"""
        # Add user message to chat
        self.main_window.chat_view.add_message(
            MessageType.USER_QUERY,
            query
        )
        
        # Reset auto scroll state, ensure auto scroll is enabled when new query
        self.main_window.chat_view.reset_auto_scroll()
        
        # Show initial processing status
        self.main_window.chat_view.show_status(TransitionMessages.QUERY_RECEIVED)
            
    def hide_all(self):
        """Hide all windows"""
        if self.mini_window:
            self.mini_window.hide()
        if self.main_window:
            try:
                self.main_window.save_geometry()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to save geometry when hiding all windows: {e}")
            self.main_window.hide()
        self.current_mode = None
        
    def toggle_visibility(self):
        """Toggle display/hide state"""
        if self.is_visible():
            # Record currently displaying window mode
            self._last_visible_mode = self.current_mode
            self._is_manually_hidden = True  # User manually hidden
            self.hide_all()
        else:
            self._is_manually_hidden = False  # User manually displayed
            self.restore_last_window()
            
    def is_visible(self):
        """Check if any window is visible"""
        mini_visible = self.mini_window and self.mini_window.isVisible()
        main_visible = self.main_window and self.main_window.isVisible()
        return mini_visible or main_visible
        
    def restore_last_window(self):
        """Restore last displayed window state"""
        # If there is recorded mode, restore to that mode
        if hasattr(self, '_last_visible_mode') and self._last_visible_mode:
            if self._last_visible_mode == WindowMode.MINI:
                self.show_mini()
            elif self._last_visible_mode == WindowMode.CHAT:
                self.expand_to_chat()
        else:
            # Default show mini window
            self.show_mini()
            
    def _on_mini_window_visibility_changed(self, is_visible: bool):
        """Handle mini window visibility change"""
        # This is called when mini window is hidden via context menu
        # We need to notify any external listeners (like tray icon)
        if not is_visible:
            # If it is a hidden operation, set manually hidden flag
            self._is_manually_hidden = True
        if hasattr(self, 'visibility_changed') and callable(self.visibility_changed):
            self.visibility_changed(is_visible)
        
    def _on_main_window_visibility_changed(self, is_visible: bool):
        """Handle main window visibility change"""
        # This is called when main window is hidden via context menu
        # We need to notify any external listeners (like tray icon)
        if not is_visible:
            # If it is a hidden operation, set manually hidden flag
            self._is_manually_hidden = True
        if hasattr(self, 'visibility_changed') and callable(self.visibility_changed):
            self.visibility_changed(is_visible)

# Demo/Testing
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Create controller
    controller = AssistantController()
    controller.show_mini()
    
    sys.exit(app.exec())