"""
Unified window system for GameWikiTooltip.
Provides mini assistant and expandable chat window functionality.
"""

import sys
import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from dataclasses import dataclass, field

# Try PyQt6 first, fall back to PyQt5
try:
    from PyQt6.QtCore import (
        Qt, QTimer, QPropertyAnimation, QRect, QSize, QPoint,
        QEasingCurve, QParallelAnimationGroup, pyqtSignal, QUrl,
        QThread, pyqtSlot
    )
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QFrame, QStackedWidget,
        QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QLineEdit
    )
    from PyQt6.QtGui import (
        QPainter, QColor, QBrush, QPen, QFont, QLinearGradient,
        QPalette, QIcon, QPixmap, QPainterPath
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    from PyQt5.QtCore import (
        Qt, QTimer, QPropertyAnimation, QRect, QSize, QPoint,
        QEasingCurve, QParallelAnimationGroup, pyqtSignal, QUrl,
        QThread, pyqtSlot
    )
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QFrame, QStackedWidget,
        QScrollArea, QSizePolicy, QGraphicsOpacityEffect
    )
    from PyQt5.QtGui import (
        QPainter, QColor, QBrush, QPen, QFont, QLinearGradient,
        QPalette, QIcon, QPixmap, QPainterPath
    )
    from PyQt5.QtWebEngineWidgets import QWebEngineView


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


class TransitionMessages:
    """Predefined transition messages"""
    WIKI_SEARCHING = "Searching Wiki page..."
    WIKI_FOUND = "Found Wiki page:"
    GUIDE_SEARCHING = "Searching for information..."
    GUIDE_GENERATING = "Generating guide content..."
    ERROR_NOT_FOUND = "Sorry, no relevant information found"
    ERROR_TIMEOUT = "Request timeout, please try again later"


class MiniAssistant(QWidget):
    """Circular mini assistant window"""
    
    clicked = pyqtSignal()
    
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
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.click_time = event.timestamp()
            
    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if it was a click (not drag)
            if event.timestamp() - self.click_time < 200:  # 200ms threshold
                drag_distance = (event.globalPosition().toPoint() - 
                               (self.frameGeometry().topLeft() + self.drag_position)).manhattanLength()
                if drag_distance < 5:  # 5 pixel threshold
                    self.clicked.emit()
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


class MessageWidget(QFrame):
    """Individual chat message widget"""
    
    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(parent)
        self.message = message
        self.init_ui()
        
    def init_ui(self):
        """Initialize the message UI"""
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Create message bubble
        bubble = QFrame()
        bubble.setObjectName("messageBubble")
        bubble.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum
        )
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
            QSizePolicy.Policy.Minimum
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
        else:
            self.content_label.setText(self.message.content)
            self.content_label.setTextFormat(Qt.TextFormat.PlainText)
            
        # Style the label based on message type
        if self.message.type == MessageType.USER_QUERY:
            self.content_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    line-height: 1.5;
                    font-family: "Microsoft YaHei", "Segoe UI", Arial;
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
                    font-family: "Microsoft YaHei", "Segoe UI", Arial;
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
                    background-color: #4096ff;
                    border-radius: 18px;
                    color: white;
                    padding: 4px;
                }
            """)
            # Style is already set above for QTextEdit
        else:
            # Left-aligned AI/system message
            # Wiki link handling is done above in content setting
            
            bubble.setStyleSheet("""
                QFrame#messageBubble {
                    background-color: #f5f5f5;
                    border-radius: 18px;
                    padding: 4px;
                }
            """)
            layout.addWidget(bubble)
            layout.addStretch()
            
        bubble_layout.addWidget(self.content_label)
        
        if self.message.type == MessageType.USER_QUERY:
            layout.addWidget(bubble)
            
        # Handle link clicks for wiki messages
        if self.message.type == MessageType.WIKI_LINK:
            self.content_label.linkActivated.connect(self.on_link_clicked)
            
    def on_link_clicked(self, url):
        """Handle wiki link clicks"""
        # Emit signal to parent to handle wiki navigation
        if hasattr(self.parent(), 'show_wiki'):
            self.parent().show_wiki(url, self.message.content)
            
    def update_content(self, new_content: str):
        """Update message content"""
        self.message.content = new_content
        self.content_label.setText(new_content)
        self.content_label.adjustSize()
        self.adjustSize()


class StreamingMessageWidget(MessageWidget):
    """Message widget with streaming/typing animation support"""
    
    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(message, parent)
        self.full_text = ""
        self.display_index = 0
        
        # Typing animation timer
        self.typing_timer = QTimer()
        self.typing_timer.timeout.connect(self.show_next_char)
        
        # Loading dots animation
        self.dots_timer = QTimer()
        self.dots_count = 0
        self.dots_timer.timeout.connect(self.update_dots)
        self.dots_timer.start(500)
        
    def append_chunk(self, chunk: str):
        """Append text chunk for streaming display"""
        self.full_text += chunk
        if not self.typing_timer.isActive():
            self.dots_timer.stop()
            self.typing_timer.start(20)  # 20ms per character
            
    def show_next_char(self):
        """Show next character in typing animation"""
        if self.display_index < len(self.full_text):
            self.display_index += 1
            display_text = self.full_text[:self.display_index]
            self.content_label.setText(display_text)
            self.content_label.adjustSize()
            self.adjustSize()
            
            # Auto-scroll to bottom
            if hasattr(self.parent(), 'scroll_to_bottom'):
                self.parent().scroll_to_bottom()
        else:
            self.typing_timer.stop()
            
    def update_dots(self):
        """Update loading dots animation"""
        self.dots_count = (self.dots_count + 1) % 4
        dots = "." * self.dots_count
        self.content_label.setText(f"{self.message.content}{dots}")


class ChatView(QScrollArea):
    """Chat message list view"""
    
    wiki_requested = pyqtSignal(str, str)  # url, title
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages: List[MessageWidget] = []
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
        self.layout.addStretch()
        
        self.setWidget(self.container)
        
        # Styling
        self.setStyleSheet("""
            QScrollArea {
                background-color: white;
                border: none;
            }
        """)
        
    def add_message(self, msg_type: MessageType, content: str, 
                   metadata: Dict[str, Any] = None) -> MessageWidget:
        """Add a new message to the chat"""
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
        
        # Force layout update
        widget.adjustSize()
        self.container.adjustSize()
        
        # Auto-scroll to bottom
        QTimer.singleShot(100, self.scroll_to_bottom)
        
        return widget
        
    def add_streaming_message(self) -> StreamingMessageWidget:
        """Add a new streaming message"""
        return self.add_message(MessageType.AI_STREAMING, "")
        
    def scroll_to_bottom(self):
        """Scroll to the bottom of the chat"""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def show_wiki(self, url: str, title: str):
        """Emit signal to show wiki page"""
        self.wiki_requested.emit(url, title)


class WikiView(QWidget):
    """Wiki page viewer"""
    
    back_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
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
        
        # Back button
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
        
        # URL/Title label
        self.title_label = QLabel()
        self.title_label.setStyleSheet("color: #5f6368; margin-left: 10px;")
        
        toolbar_layout.addWidget(self.back_button)
        toolbar_layout.addWidget(self.title_label)
        toolbar_layout.addStretch()
        
        # Web view
        self.web_view = QWebEngineView()
        
        layout.addWidget(toolbar)
        layout.addWidget(self.web_view)
        
    def load_wiki(self, url: str, title: str):
        """Load a wiki page"""
        self.title_label.setText(title)
        self.web_view.load(QUrl(url))


class UnifiedAssistantWindow(QMainWindow):
    """Main unified window with all modes"""
    
    query_submitted = pyqtSignal(str)
    window_closing = pyqtSignal()  # Signal when window is closing
    
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.current_mode = WindowMode.MINI
        self.init_ui()
        self.restore_geometry()
        
    def init_ui(self):
        """Initialize the main window UI"""
        self.setWindowTitle("GameWiki Assistant")
        # Use standard window frame with always-on-top
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
        )
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Content area (chat/wiki switcher)
        self.content_stack = QStackedWidget()
        
        # Chat view
        self.chat_view = ChatView()
        self.chat_view.wiki_requested.connect(self.show_wiki_page)
        
        # Wiki view
        self.wiki_view = WikiView()
        self.wiki_view.back_requested.connect(self.show_chat_view)
        
        self.content_stack.addWidget(self.chat_view)
        self.content_stack.addWidget(self.wiki_view)
        
        # Input area
        input_container = QFrame()
        input_container.setFixedHeight(60)
        input_container.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-top: 1px solid #e0e0e0;
            }
        """)
        
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(10, 10, 10, 10)
        
        # Input field - use QLineEdit for single line input
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter message...")
        self.input_field.setFixedHeight(45)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 22px;
                padding: 10px 20px;
                font-size: 16px;
                font-family: "Microsoft YaHei", "Segoe UI", Arial;
            }
            QLineEdit:focus {
                border-color: #4096ff;
                outline: none;
            }
        """)
        # Connect Enter key to send
        self.input_field.returnPressed.connect(self.on_send_clicked)
        
        # Send button
        self.send_button = QPushButton("Send")
        self.send_button.setFixedSize(80, 45)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #4096ff;
                color: white;
                border: none;
                border-radius: 22px;
                font-weight: bold;
                font-size: 16px;
                font-family: "Microsoft YaHei", "Segoe UI", Arial;
            }
            QPushButton:hover {
                background-color: #2d7ff9;
            }
            QPushButton:pressed {
                background-color: #1668dc;
            }
        """)
        self.send_button.clicked.connect(self.on_send_clicked)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        
        # Add to main layout
        main_layout.addWidget(self.content_stack)
        main_layout.addWidget(input_container)
        
        # Window styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: white;
                border-radius: 16px;
            }
            QWidget {
                font-size: 14px;
                font-family: "Microsoft YaHei", "Segoe UI", Arial;
            }
        """)
        
        # Apply shadow effect
        self.apply_shadow()
        
    def apply_shadow(self):
        """Apply shadow effect to window"""
        # This would require platform-specific implementation
        # For now, using basic window flags
        pass
        
    def restore_geometry(self):
        """Restore window geometry from settings"""
        if self.settings_manager:
            settings = self.settings_manager.get()
            popup = settings.get('popup', {})
            self.setGeometry(
                popup.get('left', 100),
                popup.get('top', 100),
                popup.get('width', 500),
                popup.get('height', 700)
            )
        else:
            self.setGeometry(100, 100, 500, 700)
            
    def save_geometry(self):
        """Save window geometry to settings"""
        if self.settings_manager:
            geo = self.geometry()
            self.settings_manager.update({
                'popup': {
                    'left': geo.x(),
                    'top': geo.y(),
                    'width': geo.width(),
                    'height': geo.height()
                }
            })
            
    def show_chat_view(self):
        """Switch to chat view"""
        self.content_stack.setCurrentWidget(self.chat_view)
        
    def show_wiki_page(self, url: str, title: str):
        """Switch to wiki view and load page"""
        self.wiki_view.load_wiki(url, title)
        self.content_stack.setCurrentWidget(self.wiki_view)
        
    def on_send_clicked(self):
        """Handle send button click"""
        text = self.input_field.text().strip()
        if text:
            self.input_field.clear()
            self.query_submitted.emit(text)
            
    def closeEvent(self, event):
        """Handle close event - emit signal to return to mini mode"""
        self.save_geometry()
        event.ignore()  # Don't actually close
        self.hide()  # Just hide the window
        self.window_closing.emit()  # Emit signal to show mini window
        
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()  # Hide instead of close
            self.window_closing.emit()  # Show mini window
        elif event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.on_send_clicked()
            
    def changeEvent(self, event):
        """Handle window state changes"""
        if event.type() == event.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                # Window is minimized, hide it and show mini window
                QTimer.singleShot(100, lambda: (
                    self.hide(),
                    self.setWindowState(Qt.WindowState.WindowNoState),
                    self.window_closing.emit()
                ))
        super().changeEvent(event)


class AssistantController:
    """Controller for the assistant system"""
    
    def __init__(self, settings_manager=None):
        self.settings_manager = settings_manager
        self.mini_window = None
        self.main_window = None
        self.current_mode = WindowMode.MINI
        
    def show_mini(self):
        """Show mini assistant"""
        if not self.mini_window:
            self.mini_window = MiniAssistant()
            self.mini_window.clicked.connect(self.expand_to_chat)
        self.mini_window.show()
        self.current_mode = WindowMode.MINI
        
    def expand_to_chat(self):
        """Expand from mini to chat window with animation"""
        if not self.main_window:
            self.main_window = UnifiedAssistantWindow(self.settings_manager)
            self.main_window.query_submitted.connect(self.handle_query)
            self.main_window.window_closing.connect(self.show_mini)
        
        if self.mini_window:
            # Get screen geometry
            screen = QApplication.primaryScreen().geometry()
            
            # Get mini window position and target window size
            mini_pos = self.mini_window.pos()
            target_width = 500
            target_height = 700
            
            # Calculate target position to ensure window stays on screen
            # If mini window is on the right side, open to the left
            if mini_pos.x() > screen.width() // 2:
                target_x = mini_pos.x() - target_width + 60  # Open to left
            else:
                target_x = mini_pos.x()  # Open to right
                
            # Ensure target position is within screen bounds
            target_x = max(10, min(target_x, screen.width() - target_width - 10))
            target_y = max(30, min(mini_pos.y() - (target_height - 60) // 2, 
                                  screen.height() - target_height - 40))
            
            # Set initial position and size
            self.main_window.setGeometry(
                mini_pos.x(), mini_pos.y(), 60, 60
            )
            self.main_window.show()
            
            # Hide mini window
            self.mini_window.hide()
            
            # Animate to target size and position
            self.expand_animation = QPropertyAnimation(
                self.main_window, b"geometry"
            )
            self.expand_animation.setDuration(300)
            self.expand_animation.setStartValue(
                QRect(mini_pos.x(), mini_pos.y(), 60, 60)
            )
            self.expand_animation.setEndValue(
                QRect(target_x, target_y, target_width, target_height)
            )
            self.expand_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.expand_animation.start()
        else:
            self.main_window.show()
            
        self.current_mode = WindowMode.CHAT
        
    def handle_query(self, query: str):
        """Handle user query"""
        # Add user message to chat
        self.main_window.chat_view.add_message(
            MessageType.USER_QUERY,
            query
        )
        
        # TODO: Implement actual query processing
        # For now, just show a demo response
        QTimer.singleShot(500, lambda: self.demo_response(query))
        
    def demo_response(self, query: str):
        """Demo response for testing"""
        if "wiki" in query.lower():
            # Simulate wiki response
            transition = self.main_window.chat_view.add_message(
                MessageType.TRANSITION,
                TransitionMessages.WIKI_SEARCHING
            )
            
            QTimer.singleShot(1000, lambda: self.show_wiki_result(transition))
        else:
            # Simulate guide response
            transition = self.main_window.chat_view.add_message(
                MessageType.TRANSITION,
                TransitionMessages.GUIDE_SEARCHING
            )
            
            QTimer.singleShot(1000, lambda: self.show_guide_result(transition))
            
    def show_wiki_result(self, transition_widget):
        """Show wiki search result"""
        transition_widget.update_content(TransitionMessages.WIKI_FOUND)
        
        self.main_window.chat_view.add_message(
            MessageType.WIKI_LINK,
            "Helldivers 2 - 武器指南",
            {"url": "https://helldivers.wiki.gg/wiki/Weapons"}
        )
        
    def show_guide_result(self, transition_widget):
        """Show guide result with streaming"""
        transition_widget.hide()
        
        streaming_msg = self.main_window.chat_view.add_streaming_message()
        
        # Simulate streaming response
        demo_text = "根据您的问题，我为您整理了以下攻略内容：\n\n1. 首先，您需要了解基础机制\n2. 其次，掌握核心技巧\n3. 最后，通过实践提升水平"
        
        chunks = [demo_text[i:i+5] for i in range(0, len(demo_text), 5)]
        
        def send_chunk(index=0):
            if index < len(chunks):
                streaming_msg.append_chunk(chunks[index])
                QTimer.singleShot(100, lambda: send_chunk(index + 1))
                
        send_chunk()


# Demo/Testing
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Create controller
    controller = AssistantController()
    controller.show_mini()
    
    sys.exit(app.exec())