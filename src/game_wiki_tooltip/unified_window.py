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
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from dataclasses import dataclass, field

from src.game_wiki_tooltip.i18n import t
from src.game_wiki_tooltip.config import PopupConfig

# 导入 markdown 支持
try:
    import markdown
    MARKDOWN_AVAILABLE = True
    
    # 禁用markdown库的调试日志输出，避免大量debug信息
    markdown_logger = logging.getLogger('markdown')
    markdown_logger.setLevel(logging.WARNING)
    
except ImportError:
    print("Warning: markdown library not available. Markdown content will be displayed as plain text.")
    MARKDOWN_AVAILABLE = False

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
        QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QLineEdit,
        QToolButton, QMenu
    )
    from PyQt6.QtGui import (
        QPainter, QColor, QBrush, QPen, QFont, QLinearGradient,
        QPalette, QIcon, QPixmap, QPainterPath, QTextDocument
    )
    # Try to import WebEngine, but handle gracefully if it fails
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage
        WEBENGINE_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: PyQt6 WebEngine not available: {e}")
        print("Wiki view functionality will be disabled. Using fallback text view.")
        WEBENGINE_AVAILABLE = False
        QWebEngineView = None
        QWebEngineProfile = None
        QWebEngineSettings = None
        QWebEnginePage = None
except ImportError:
    print("Error: PyQt6 is required. PyQt5 is no longer supported.")
    sys.exit(1)

# Configuration option to use WebView2 instead of WebEngine
USE_WEBVIEW2 = True  # Set to True to use lightweight WebView2

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
        USE_WEBVIEW2 = False  # Fall back to WebEngine
else:
    WEBVIEW2_AVAILABLE = False


def _get_scale() -> float:
    """获取显示器缩放因子（仅 Windows）"""
    try:
        shcore = ctypes.windll.shcore
        hMonitor = ctypes.windll.user32.MonitorFromWindow(
            None,   # 传 None 拿到主显示器
            1       # MONITOR_DEFAULTTOPRIMARY
        )
        factor = ctypes.c_uint()
        if shcore.GetScaleFactorForMonitor(hMonitor, ctypes.byref(factor)) == 0:
            return factor.value / 100.0
    except Exception:
        pass
    return 1.0


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


# 为了让类属性能动态返回翻译，我们使用元类
class TransitionMessagesMeta(type):
    """元类，用于动态处理TransitionMessages的属性访问"""
    
    def __getattribute__(cls, name):
        # 映射旧的属性名到新的翻译key
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
        
        # 对于其他属性，使用默认行为
        return super().__getattribute__(name)

class TransitionMessages(metaclass=TransitionMessagesMeta):
    """Predefined transition messages with i18n support"""
    
    def __new__(cls):
        # 防止实例化，这个类应该只用作静态访问
        raise TypeError(f"{cls.__name__} should not be instantiated")
    
    # 静态方法版本，供需要时使用
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
    检测文本是否包含markdown格式或HTML格式
    
    Args:
        text: 要检测的文本
        
    Returns:
        True如果文本包含markdown或HTML格式，否则False
    """
    if not text:
        return False
        
    # 检测常见的markdown模式
    markdown_patterns = [
        r'\*\*.*?\*\*',  # 粗体 **text**
        r'\*.*?\*',      # 斜体 *text*
        r'#{1,6}\s',     # 标题 # ## ### 等
        r'^\s*[-\*\+]\s', # 无序列表
        r'^\s*\d+\.\s',  # 有序列表
        r'`.*?`',        # 行内代码
        r'```.*?```',    # 代码块
        r'\[.*?\]\(.*?\)', # 链接 [text](url)
    ]
    
    # 检测HTML标签（特别是视频源中使用的标签）
    html_patterns = [
        r'<small.*?>.*?</small>',  # <small>标签
        r'<a\s+.*?href.*?>.*?</a>', # <a>链接标签
        r'<[^>]+>',  # 其他HTML标签
        r'📺\s*\*\*info source：\*\*',  # 视频源标题
        r'---\s*\n\s*<small>',  # markdown分隔符 + HTML
        r'\n\n<small>.*?来源.*?</small>',  # 通用来源模式
        r'<br\s*/?>',  # <br>标签
        r'<strong>.*?</strong>',  # <strong>标签
        r'<em>.*?</em>',  # <em>标签
        r'<code>.*?</code>',  # <code>标签
        r'<pre>.*?</pre>',  # <pre>标签
    ]
    
    # 检查markdown模式
    for pattern in markdown_patterns:
        if re.search(pattern, text, re.MULTILINE | re.DOTALL):
            return True
    
    # 检查HTML模式        
    for pattern in html_patterns:
        if re.search(pattern, text, re.MULTILINE | re.DOTALL):
            return True
            
    return False


def convert_markdown_to_html(text: str) -> str:
    """
    将markdown文本转换为HTML，同时保持已有的HTML标签
    
    Args:
        text: markdown文本或混合HTML内容
        
    Returns:
        转换后的HTML文本
    """
    if not text:
        return text
        
    try:
        # 检查是否包含HTML标签（特别是视频源部分）
        has_html_tags = bool(re.search(r'<[^>]+>', text, re.MULTILINE | re.DOTALL))
        
        if has_html_tags:
            # 检查是否是混合内容（Markdown + HTML视频源）
            # 改进：使用更灵活的视频源识别方式
            video_source_patterns = [
                r'---\s*\n\s*<small>',  # 原有模式
                r'📺\s*\*\*info source：\*\*',  # 视频源标题模式  
                r'\n\n<small>.*?来源.*?</small>',  # 通用来源模式
                r'\n\n---\n\s*<small>',  # 添加更灵活的分隔符模式
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
                # 分离Markdown和HTML部分
                markdown_content = text[:video_source_start].strip()
                html_content = text[video_source_start:].strip()
                
                # 处理Markdown部分
                processed_markdown = ""
                if markdown_content:
                    if MARKDOWN_AVAILABLE:
                        # 使用markdown库处理
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
                        # 没有markdown库时，处理基本格式
                        processed_markdown = markdown_content.replace('\n', '<br/>')
                        processed_markdown = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', processed_markdown)
                        processed_markdown = re.sub(r'\*(.*?)\*', r'<em>\1</em>', processed_markdown)
                        processed_markdown = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', processed_markdown)
                
                # 处理HTML部分，确保格式正确
                processed_html = html_content
                if html_content:
                    # 清理可能的markdown分隔符
                    processed_html = re.sub(r'^---\s*\n\s*', '', processed_html, flags=re.MULTILINE)
                    processed_html = processed_html.strip()
                    
                    # 处理视频源中的markdown链接
                    processed_html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', processed_html)
                
                # 合并处理后的内容
                combined_content = processed_markdown
                if processed_html:
                    # 添加适当的间距
                    if combined_content and not combined_content.endswith('<br/>'):
                        combined_content += '<br/><br/>'
                    combined_content += processed_html
                
                # 应用样式包装
                styled_html = f"""
                <div style="
                    font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif;
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
                # 纯HTML内容，但仍需要处理其中的markdown链接
                processed_text = text
                # 处理markdown链接
                processed_text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', processed_text)
                
                styled_html = f"""
                <div style="
                    font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 100%;
                    word-wrap: break-word;
                ">
                    {processed_text}
                </div>
                """
                return styled_html
        
        # 如果没有HTML标签，进行常规markdown处理
        if not MARKDOWN_AVAILABLE:
            # 没有markdown库时，至少处理一些基本格式
            html = text.replace('\n', '<br/>')
            # 处理粗体
            html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
            # 处理斜体
            html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
            # 处理链接
            html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
        else:
            # 使用markdown库处理
            # 配置markdown转换器，使用基础扩展（避免依赖可能不存在的扩展）
            available_extensions = []
            
            # 尝试添加可用的扩展
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
                
            # 如果没有可用的扩展，使用基础配置
            if available_extensions:
                md = markdown.Markdown(extensions=available_extensions)
            else:
                md = markdown.Markdown()
            
            # 转换markdown到HTML
            html = md.convert(text)
        
        # 添加一些基础样式，让HTML显示更好看
        styled_html = f"""
        <div style="
            font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif;
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
        # 只在转换失败时输出错误信息
        print(f"❌ [RENDER-ERROR] Markdown转换失败: {e}")
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
        """处理右键菜单事件"""
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
    """专门用于显示状态信息的消息组件"""
    
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.current_message = message
        
        # 初始化动画属性（必须在init_ui之前，因为init_ui中会调用update_display）
        self.animation_dots = 0
        
        self.init_ui()
        
        # 动画定时器
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_timer.start(500)  # 每500ms更新一次动画
        
    def init_ui(self):
        """初始化状态消息UI"""
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # 创建状态气泡
        bubble = QFrame()
        bubble.setObjectName("statusBubble")
        bubble.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        
        # 状态文本标签
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum
        )
        
        # 设置状态样式
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                line-height: 1.5;
                font-family: "Microsoft YaHei", "Segoe UI", Arial;
                background-color: transparent;
                border: none;
                padding: 0;
                color: #666;
                font-style: italic;
            }
        """)
        
        # 设置气泡样式
        bubble.setStyleSheet("""
            QFrame#statusBubble {
                background-color: #f0f8ff;
                border: 1px solid #e0e8f0;
                border-radius: 18px;
                padding: 4px;
            }
        """)
        
        bubble_layout.addWidget(self.status_label)
        layout.addWidget(bubble)
        layout.addStretch()
        
        self.update_display()
        
    def update_status(self, new_message: str):
        """更新状态信息"""
        self.current_message = new_message
        self.animation_dots = 0  # 重置动画
        self.update_display()
        # 确保动画继续运行
        if not self.animation_timer.isActive():
            self.animation_timer.start(500)
        
    def update_animation(self):
        """更新动画效果"""
        self.animation_dots = (self.animation_dots + 1) % 4
        self.update_display()
        
    def update_display(self):
        """更新显示内容"""
        dots = "." * self.animation_dots
        display_text = f"{self.current_message}{dots}"
        self.status_label.setText(display_text)
        self.status_label.adjustSize()
        self.adjustSize()
        
        # 确保父容器也更新布局
        if self.parent():
            self.parent().adjustSize()
        
    def stop_animation(self):
        """停止动画"""
        if self.animation_timer.isActive():
            self.animation_timer.stop()
            
    def hide_with_fadeout(self):
        """淡出隐藏"""
        self.stop_animation()
        # 简单的隐藏，可以后续添加淡出动画
        self.hide()


class MessageWidget(QFrame):
    """Individual chat message widget"""
    
    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(parent)
        self.message = message
        self.init_ui()
        
    def init_ui(self):
        """Initialize the message UI"""
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,  # 改为Expanding以占满可用宽度
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
        # 设置最大宽度为父容器的80%，留出边距
        bubble.setMaximumWidth(9999)  # 先设置一个大值，后续会动态调整
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
            # AI回复可能包含markdown格式，需要检测和转换
            if detect_markdown_content(self.message.content):
                # 转换markdown到HTML
                html_content = convert_markdown_to_html(self.message.content)
                self.content_label.setText(html_content)
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
                # AI回复中可能包含链接，需要连接linkActivated信号
                self.content_label.setOpenExternalLinks(False)  # 确保使用信号处理
                self.content_label.linkActivated.connect(self.on_link_clicked)
            else:
                # 普通文本
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
            
        # 设置初始宽度
        self._set_initial_width()
            
    def _set_initial_width(self):
        """设置消息的初始宽度，基于父容器"""
        # 这个方法会在添加到聊天视图后被_update_message_width方法覆盖
        # 但是可以提供一个合理的初始值
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            bubble.setMaximumWidth(500)  # 设置一个合理的初始最大宽度
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            
    def on_link_clicked(self, url):
        """Handle wiki link clicks"""
        logger = logging.getLogger(__name__)
        print(f"🔗 [LINK-DEBUG] 链接被点击: {url}")
        print(f"🔗 [LINK-DEBUG] 消息类型: {self.message.type}")
        print(f"🔗 [LINK-DEBUG] 是否为流式消息: {isinstance(self, StreamingMessageWidget)}")
        print(f"🔗 [LINK-DEBUG] content_label格式: {self.content_label.textFormat()}")
        print(f"🔗 [LINK-DEBUG] openExternalLinks: {self.content_label.openExternalLinks()}")
        
        logger.info(f"🔗 Wiki链接被点击: {url}")
        logger.info(f"消息内容: {self.message.content}")
        logger.info(f"消息元数据: {self.message.metadata}")
        
        # 优化标题传递：优先使用消息内容，如果内容为空则从URL提取
        title = self.message.content
        if not title or title.strip() == "":
            # 如果没有标题，从URL中提取
            try:
                from urllib.parse import unquote
                title = unquote(url.split('/')[-1]).replace('_', ' ')
            except:
                title = "Wiki页面"
        
        logger.info(f"使用标题: {title}")
        print(f"🔗 [LINK-DEBUG] 使用标题: {title}")
        
        # 向上查找ChatView实例
        chat_view = self._find_chat_view()
        if chat_view:
            logger.info(f"找到ChatView实例，调用显示Wiki页面")
            print(f"🔗 [LINK-DEBUG] 找到ChatView实例，调用显示Wiki页面")
            chat_view.show_wiki(url, title)
        else:
            logger.warning(f"未找到ChatView实例")
            print(f"🔗 [LINK-DEBUG] ❌ 未找到ChatView实例")
            
    def _find_chat_view(self):
        """向上查找ChatView实例"""
        parent = self.parent()
        while parent:
            if isinstance(parent, ChatView):
                return parent
            parent = parent.parent()
        return None
        
    def update_content(self, new_content: str):
        """Update message content"""
        self.message.content = new_content
        
        # 如果是AI回复，检测并转换markdown
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


class StreamingMessageWidget(MessageWidget):
    """Message widget with streaming/typing animation support"""
    
    # 添加信号
    streaming_finished = pyqtSignal()  # 流式输出完成信号
    
    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(message, parent)
        self.full_text = ""
        self.display_index = 0
        self.is_stopped = False  # 标记是否被用户停止
        
        # Markdown渲染控制 - 确保每次都重新初始化
        self.last_render_index = 0  # 上次渲染时的字符位置
        self.render_interval = 50   # 每50个字符进行一次markdown渲染（减少频率，避免闪烁）
        self.last_render_time = 0   # 上次渲染时间
        self.render_time_interval = 1.0  # 最长1.0秒进行一次渲染
        self.is_markdown_detected = False  # 缓存markdown检测结果 - 强制重置
        self.current_format = Qt.TextFormat.PlainText  # 当前文本格式 - 强制重置
        self.link_signal_connected = False  # 跟踪是否已连接linkActivated信号 - 强制重置
        self.has_video_source = False  # 跟踪是否已检测到视频源 - 强制重置
        self.force_render_count = 0  # 强制渲染计数器
        
        # 优化流式消息的布局，防止闪烁
        self._optimize_for_streaming()
        
        # 设置默认的渲染参数（更敏感的检测）
        self.set_render_params(char_interval=50, time_interval=1.0)
        
        # Typing animation timer
        self.typing_timer = QTimer()
        self.typing_timer.timeout.connect(self.show_next_char)
        # 确保timer在初始化时是停止状态
        self.typing_timer.stop()
        
        # Loading dots animation
        self.dots_timer = QTimer()
        self.dots_count = 0
        self.dots_timer.timeout.connect(self.update_dots)
        self.dots_timer.start(500)
        
        # 添加调试日志
        print(f"🔧 [STREAMING] 新StreamingMessageWidget初始化完成，timer状态: {'激活' if self.typing_timer.isActive() else '未激活'}")
        
        # 初始化时就配置链接处理
        if hasattr(self, 'content_label'):
            self.content_label.setOpenExternalLinks(False)  # 确保使用信号处理而不是直接打开
            # 预先连接linkActivated信号，避免在流式过程中的连接问题
            try:
                self.content_label.linkActivated.connect(self.on_link_clicked)
                self.link_signal_connected = True
                print(f"🔗 [STREAMING] 初始化时已连接linkActivated信号")
            except Exception as e:
                print(f"⚠️ [STREAMING] 初始化连接linkActivated信号失败: {e}")
                self.link_signal_connected = False
    
    def _optimize_for_streaming(self):
        """优化流式消息的布局，防止闪烁"""
        # 找到消息气泡
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            # 使用MinimumExpanding策略，允许内容自由扩展
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        
        # 优化content_label设置
        if hasattr(self, 'content_label'):
            # 使用MinimumExpanding策略，允许内容自由扩展
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            # 设置文本换行
            self.content_label.setWordWrap(True)
            self.content_label.setScaledContents(False)
            
        # 初始设置宽度（基于父容器）
        self._update_bubble_width()
        
        # 为流式消息固定初始宽度，避免排版跳动
        self._fix_width_for_streaming()
    
    def _update_bubble_width(self):
        """根据聊天窗口宽度动态设置对话框宽度"""
        # 获取聊天视图的宽度，考虑滚动条宽度
        parent_widget = self.parent()
        
        # 尝试使用get_chat_view，但在初始化时可能还不可用
        if hasattr(self, 'get_chat_view'):
            chat_view = self.get_chat_view()
        else:
            chat_view = parent_widget if parent_widget and hasattr(parent_widget, 'viewport') else None
            
        if chat_view and hasattr(chat_view, 'viewport'):
            viewport_width = chat_view.viewport().width()
            # 减去滚动条可能占用的宽度（通常约20px）
            if hasattr(chat_view, 'verticalScrollBar'):
                scrollbar = chat_view.verticalScrollBar()
                if scrollbar and scrollbar.isVisible():
                    viewport_width -= scrollbar.width()
        else:
            # 如果无法获取聊天视图宽度，尝试从父容器获取
            viewport_width = parent_widget.width() if parent_widget else 500
        
        # 确保有效宽度
        viewport_width = max(300, viewport_width)
        
        # 计算对话框宽度（聊天视图宽度的75%，减少比例避免过宽，但不超过600px，不少于300px）
        bubble_width = max(300, min(600, int(viewport_width * 0.75)))
        content_width = bubble_width - 24  # 减去边距
        
        # 保存计算的宽度供后续使用
        self._calculated_bubble_width = bubble_width
        self._calculated_content_width = content_width
        
        # 更新气泡和内容宽度 - 使用最大宽度而不是固定宽度
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            bubble.setMaximumWidth(bubble_width)
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            
        if hasattr(self, 'content_label'):
            self.content_label.setMaximumWidth(content_width)
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            
        # 只在异常情况下输出调试信息
        if chat_view and hasattr(chat_view, 'viewport'):
            original_viewport_width = chat_view.viewport().width()
            # 只有在宽度异常小时才输出警告
            if original_viewport_width < 400:
                print(f"⚠️ 流式消息视图宽度异常: viewport={original_viewport_width}px")
    
    def _fix_width_for_streaming(self):
        """为流式消息固定宽度，避免排版跳动"""
        if not hasattr(self, '_calculated_bubble_width'):
            return
            
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            # 使用固定宽度而不是最大宽度
            bubble.setFixedWidth(self._calculated_bubble_width)
            print(f"🔒 [STREAMING] 固定bubble宽度: {self._calculated_bubble_width}px")
            
        if hasattr(self, 'content_label'):
            # 内容标签也使用固定宽度
            self.content_label.setFixedWidth(self._calculated_content_width)
            # 设置最小高度，避免垂直跳动
            self.content_label.setMinimumHeight(30)
            print(f"🔒 [STREAMING] 固定content宽度: {self._calculated_content_width}px")
            
        # 标记已固定宽度
        self._width_fixed = True
    
    def _restore_flexible_width(self):
        """恢复灵活宽度设置（流式结束后调用）"""
        if not hasattr(self, '_width_fixed') or not self._width_fixed:
            return
            
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble and hasattr(self, '_calculated_bubble_width'):
            # 移除固定宽度，恢复最大宽度限制
            bubble.setMinimumWidth(0)
            bubble.setMaximumWidth(self._calculated_bubble_width)
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            print(f"🔓 [STREAMING] 恢复bubble灵活宽度，最大: {self._calculated_bubble_width}px")
            
        if hasattr(self, 'content_label') and hasattr(self, '_calculated_content_width'):
            # 移除固定宽度，恢复最大宽度限制
            self.content_label.setMinimumWidth(0)
            self.content_label.setMaximumWidth(self._calculated_content_width)
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
            print(f"🔓 [STREAMING] 恢复content灵活宽度，最大: {self._calculated_content_width}px")
            
        # 标记已恢复灵活宽度
        self._width_fixed = False
        
    def get_chat_view(self):
        """获取父级ChatView（如果存在）"""
        try:
            parent = self.parent()
            # 检查parent是否是ChatView（通过检查特有方法）
            if parent and hasattr(parent, 'request_auto_scroll') and hasattr(parent, 'verticalScrollBar'):
                return parent
        except:
            pass
        return None
    
    def set_render_params(self, char_interval: int = 50, time_interval: float = 1.0):
        """
        设置markdown渲染参数
        
        Args:
            char_interval: 字符间隔，每多少个字符进行一次渲染
            time_interval: 时间间隔，最长多少秒进行一次渲染
        """
        self.render_interval = max(20, char_interval)  # 最少20个字符
        self.render_time_interval = max(0.5, time_interval)  # 最少0.5秒
        
    def append_chunk(self, chunk: str):
        """Append text chunk for streaming display"""
        # 更严格的停止检查，直接返回不处理
        if self.is_stopped:
            print(f"🛑 流式消息已停止，拒绝新内容块: '{chunk[:50]}...'")
            return
        
        # 记录timer状态用于调试
        timer_was_active = self.typing_timer.isActive()
        
        self.full_text += chunk
        print(f"✅ [STREAMING-WIDGET] 全文已更新，新长度: {len(self.full_text)}")
        
        # 改进的初始检测逻辑：
        # 1. 移除timer检查限制，确保每个新消息都能进行初始检测
        # 2. 降低长度限制，尽早检测markdown
        if not timer_was_active:
            self.dots_timer.stop()
            # 初始化渲染时间戳
            self.last_render_time = time.time()
            
        # 对每个新chunk都进行markdown检测（不仅仅是第一个）
        # 使用缓存避免重复检测相同内容
        if not self.is_markdown_detected and len(self.full_text) > 5:  # 降低长度限制
            self.is_markdown_detected = detect_markdown_content(self.full_text)
            # 如果检测到markdown，立即进行初始渲染
            if self.is_markdown_detected:
                print(f"🔍 [STREAMING] 初始检测到markdown格式，长度: {len(self.full_text)}")
                print(f"📋 [STREAMING] Timer状态: {'激活' if timer_was_active else '未激活'}")
                print(f"📝 [STREAMING] 前50字符: {self.full_text[:50]}...")
                # 立即设置正确的格式
                self.current_format = Qt.TextFormat.RichText
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
                
        # 确保timer启动
        if not self.typing_timer.isActive():
            print(f"⏰ [STREAMING-WIDGET] 启动打字机定时器")
            # 更快的打字机效果：5ms per character（之前是20ms）
            self.typing_timer.start(5)
        else:
            print(f"⏰ [STREAMING-WIDGET] 打字机定时器已在运行")
    
    def _adjust_typing_speed(self):
        """动态调整打字机速度"""
        remaining_chars = len(self.full_text) - self.display_index
        
        # 如果剩余字符很多，加速显示
        if remaining_chars > 500:
            # 大量剩余内容，极快速度
            new_interval = 1
        elif remaining_chars > 200:
            # 中等剩余内容，快速度
            new_interval = 2
        elif remaining_chars > 50:
            # 少量剩余内容，正常速度
            new_interval = 3
        else:
            # 很少剩余内容，慢速度保持打字效果
            new_interval = 5
            
        # 检查是否需要调整定时器间隔
        if self.typing_timer.isActive():
            current_interval = self.typing_timer.interval()
            if current_interval != new_interval:
                print(f"🚀 [TYPING] 调整打字速度: {current_interval}ms -> {new_interval}ms, 剩余: {remaining_chars}字符")
                self.typing_timer.setInterval(new_interval)
    
    def mark_as_stopped(self):
        """标记为已停止"""
        self.is_stopped = True
        self.typing_timer.stop()
        self.dots_timer.stop()
        
        # 在当前位置添加停止标记
        if self.display_index < len(self.full_text):
            stopped_text = self.full_text[:self.display_index] + "\n\n*[Generation stopped by user]*"
        else:
            stopped_text = self.full_text + "\n\n*[Generation stopped by user]*"
            
        # 立即显示所有已生成的文本加上停止标记
        self.content_label.setText(stopped_text)
        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
        
        # 转换消息类型为AI_RESPONSE
        self.message.type = MessageType.AI_RESPONSE
        
        print(f"🛑 流式消息已停止，显示位置: {self.display_index}/{len(self.full_text)}")
            
    def show_next_char(self):
        """Show next character in typing animation"""
        
        # 首先检查是否已被停止
        if self.is_stopped:
            self.typing_timer.stop()
            print(f"🛑 打字机效果检测到停止状态，立即终止")
            return
            
        # 动态调整打字速度（根据剩余字符数量）
        self._adjust_typing_speed()
            
        if self.display_index < len(self.full_text):
            self.display_index += 1
            display_text = self.full_text[:self.display_index]
            current_time = time.time()
            
            # 早期markdown检测（在前20个字符时就开始检测）
            if self.display_index <= 20 and not self.is_markdown_detected and len(self.full_text) > 5:
                if detect_markdown_content(self.full_text):
                    self.is_markdown_detected = True
                    self.current_format = Qt.TextFormat.RichText
                    self.content_label.setTextFormat(Qt.TextFormat.RichText)
                    print(f"🚀 [STREAMING] 早期检测到markdown格式（{self.display_index}字符），全文长度: {len(self.full_text)}")
            
            # 检查是否需要进行阶段性markdown渲染
            should_render = False
            
            # 添加更新缓冲检查 - 减少频繁的DOM操作
            should_update_display = False
            
            # 缓冲条件1: 每5个字符更新一次显示（减少更新频率）
            # 但前10个字符立即显示，确保用户看到内容开始
            if self.display_index <= 10 or self.display_index % 5 == 0:
                should_update_display = True
            
            # 缓冲条件2: 遇到换行符或段落结束
            elif display_text and display_text[-1] in ['\n', '.', '。', '!', '！', '?', '？']:
                should_update_display = True
            
            # 缓冲条件3: 达到字符间隔时必须更新
            if self.display_index - self.last_render_index >= self.render_interval:
                should_render = True
                should_update_display = True
            
            # 条件2: 达到时间间隔
            elif current_time - self.last_render_time >= self.render_time_interval:
                should_render = True
                should_update_display = True
            
            # 条件3: 检测到关键内容边界（如video sources开始）
            elif not self.has_video_source and ('📺' in display_text[-10:] or 
                  '---\n<small>' in display_text[-20:] or
                  '<small>' in display_text[-10:]):
                should_render = True
                should_update_display = True
                self.has_video_source = True  # 标记已检测到视频源，避免重复打印
                print(f"🎬 [STREAMING] 检测到视频源内容，触发渲染")
            
            # 条件4: 检测到markdown格式内容（新增条件，确保格式内容能被渲染）
            elif not self.is_markdown_detected and len(display_text) > 5 and detect_markdown_content(display_text):
                should_render = True
                should_update_display = True
                self.is_markdown_detected = True
                print(f"🔄 [STREAMING] 检测到格式内容，触发渲染，当前长度: {len(display_text)}")
                print(f"📝 [STREAMING] 前50字符: {display_text[:50]}...")
                # 立即设置正确的格式
                self.current_format = Qt.TextFormat.RichText
                self.content_label.setTextFormat(Qt.TextFormat.RichText)
            
            # 条件5: 如果已检测到markdown，但当前文本没有格式，重新检测（处理格式变化）
            elif self.is_markdown_detected and not detect_markdown_content(display_text):
                # 重新检测整个文本，避免误判
                if detect_markdown_content(self.full_text):
                    should_render = True
                    print(f"🔄 [STREAMING] 重新检测到格式内容，触发渲染")
                else:
                    # 如果确实没有格式，重置状态
                    self.is_markdown_detected = False
                    self.current_format = Qt.TextFormat.PlainText
                    print(f"🔄 [STREAMING] 重置为纯文本格式")
            
            # 条件6: 每100个字符强制检测一次格式（新增，确保不会遗漏格式内容）
            elif self.display_index % 100 == 0 and self.display_index > 0:
                if detect_markdown_content(display_text) and not self.is_markdown_detected:
                    should_render = True
                    self.is_markdown_detected = True
                    print(f"🔄 [STREAMING] 强制检测到格式内容，触发渲染，位置: {self.display_index}")
            
            # 条件7: 如果已经检测到markdown但还没有渲染过，强制渲染（新增）
            elif self.is_markdown_detected and self.current_format == Qt.TextFormat.PlainText:
                should_render = True
                print(f"🔄 [STREAMING] 强制渲染已检测的markdown内容，位置: {self.display_index}")
            
            # 进行渲染处理
            if should_render and self.message.type == MessageType.AI_STREAMING:
                # 重新检测内容格式（支持动态变化，如添加HTML视频源）
                current_has_format = detect_markdown_content(display_text)
                
                # 进行阶段性渲染
                if self.is_markdown_detected or current_has_format:
                    html_content = convert_markdown_to_html(display_text)
                    # 只在格式实际变化时才设置格式，避免闪烁
                    if self.current_format != Qt.TextFormat.RichText:
                        self.content_label.setTextFormat(Qt.TextFormat.RichText)
                        self.current_format = Qt.TextFormat.RichText
                        print(f"📝 [STREAMING] 切换到RichText格式，内容长度: {len(display_text)}")
                    self.content_label.setText(html_content)
                    
                    # 如果还未连接linkActivated信号，现在连接
                    if not self.link_signal_connected:
                        self.content_label.linkActivated.connect(self.on_link_clicked)
                        self.link_signal_connected = True
                        print(f"🔗 [STREAMING] 已连接linkActivated信号")
                        print(f"🔗 [STREAMING] 当前内容包含链接: {'<a href' in html_content}")
                        
                    # 确保内容标签启用了链接打开
                    self.content_label.setOpenExternalLinks(False)  # 确保信号处理而不是直接打开
                    print(f"🔗 [STREAMING] 内容标签配置 - OpenExternalLinks: {self.content_label.openExternalLinks()}")
                    print(f"🔗 [STREAMING] 内容标签格式: {self.content_label.textFormat()}")
                    
                    # 确保状态一致
                    self.is_markdown_detected = True
                else:
                    # 只在格式实际变化时才设置格式，避免闪烁
                    if self.current_format != Qt.TextFormat.PlainText:
                        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                        self.current_format = Qt.TextFormat.PlainText
                        print(f"📝 [STREAMING] 切换到PlainText格式，内容长度: {len(display_text)}")
                    self.content_label.setText(display_text)
                    
                    # 确保状态一致
                    self.is_markdown_detected = False
                
                # 更新渲染状态
                self.last_render_index = self.display_index
                self.last_render_time = current_time
            elif should_update_display:
                # 只更新显示，不进行完整渲染
                # 使用setUpdatesEnabled减少闪烁
                self.content_label.setUpdatesEnabled(False)
                
                if self.is_markdown_detected:
                    # 如果已检测到markdown/HTML，继续使用HTML格式
                    html_content = convert_markdown_to_html(display_text)
                    self.content_label.setText(html_content)
                    # 确保格式设置正确
                    if self.current_format != Qt.TextFormat.RichText:
                        self.content_label.setTextFormat(Qt.TextFormat.RichText)
                        self.current_format = Qt.TextFormat.RichText
                else:
                    # 否则使用纯文本
                    self.content_label.setText(display_text)
                    # 确保格式设置正确
                    if self.current_format != Qt.TextFormat.PlainText:
                        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                        self.current_format = Qt.TextFormat.PlainText
                
                # 恢复更新
                self.content_label.setUpdatesEnabled(True)
            # 如果既不需要渲染也不需要更新显示，但这是前5个字符，强制至少显示一次
            elif self.display_index <= 5:
                print(f"🚀 [DISPLAY] 强制显示前5个字符: display_index={self.display_index}")
                should_update_display = True
                if self.is_markdown_detected:
                    html_content = convert_markdown_to_html(display_text)
                    self.content_label.setText(html_content)
                else:
                    self.content_label.setText(display_text)
                
            # 只在需要滚动时才滚动（减少滚动调用）
            if should_update_display:
                chat_view = self.get_chat_view()
                if chat_view:
                    # 使用统一的滚动请求机制
                    chat_view.request_auto_scroll()
        else:
            self.typing_timer.stop()
            
            # 最终完成时，转换消息类型并进行最终渲染
            if self.message.type == MessageType.AI_STREAMING and self.full_text and not self.is_stopped:
                # 将消息类型改为AI_RESPONSE，表示流式输出已完成
                self.message.type = MessageType.AI_RESPONSE
                
                # 输出完成信息
                has_video_sources = any(pattern in self.full_text for pattern in [
                    '📺 **info source：**', 
                    '---\n<small>', 
                    '<small>.*?来源.*?</small>'
                ])
                print(f"🎬 [STREAMING] 流式消息完成，长度: {len(self.full_text)} 字符，包含视频源: {has_video_sources}")
                
                # 发出完成信号
                self.streaming_finished.emit()
                
                # 进行最终的格式检测和转换 - 强制重新检测，忽略缓存状态
                final_has_format = detect_markdown_content(self.full_text)
                final_has_video_sources = has_video_sources
                
                # 如果之前没有检测到markdown，但最终检测到了，立即更新
                if not self.is_markdown_detected and final_has_format:
                    self.is_markdown_detected = True
                    self.current_format = Qt.TextFormat.RichText
                    print(f"⚡ [STREAMING] 最终检测到markdown格式，强制更新渲染")
                
                print(f"🔄 [STREAMING] 最终格式检测: markdown={final_has_format}, video={final_has_video_sources}, 缓存状态={self.is_markdown_detected}")
                
                # 确保最终渲染使用正确的格式 - 基于实际检测结果而不是缓存状态
                if final_has_format or final_has_video_sources:
                    html_content = convert_markdown_to_html(self.full_text)
                    self.content_label.setText(html_content)
                    self.content_label.setTextFormat(Qt.TextFormat.RichText)
                    self.current_format = Qt.TextFormat.RichText
                    self.is_markdown_detected = True  # 更新状态与检测结果一致
                    
                    # 流式输出完成后，确保linkActivated信号已连接（避免重复连接）
                    if not self.link_signal_connected:
                        self.content_label.linkActivated.connect(self.on_link_clicked)
                        self.link_signal_connected = True
                        print(f"🔗 [STREAMING] 最终渲染时连接linkActivated信号")
                        
                    # 确保内容标签配置正确
                    self.content_label.setOpenExternalLinks(False)  # 确保信号处理而不是直接打开
                    print(f"🔗 [STREAMING] 最终渲染 - 内容包含链接: {'<a href' in html_content}")
                    print(f"🔗 [STREAMING] 最终渲染 - OpenExternalLinks: {self.content_label.openExternalLinks()}")
                    print(f"🔗 [STREAMING] 最终渲染 - 文本格式: {self.content_label.textFormat()}")
                    
                    print(f"✅ [STREAMING] 最终渲染完成，使用RichText格式")
                else:
                    self.content_label.setText(self.full_text)
                    self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                    self.current_format = Qt.TextFormat.PlainText
                    self.is_markdown_detected = False  # 更新状态与检测结果一致
                    print(f"✅ [STREAMING] 最终渲染完成，使用PlainText格式")
                
                # 流式结束后恢复灵活宽度
                self._restore_flexible_width()
                
                # 只在流式结束后进行一次完整的布局更新
                self.content_label.updateGeometry()
                self.updateGeometry()
                
                # 确保父容器也更新布局（延迟执行，避免阻塞）
                chat_view = self.get_chat_view()
                if chat_view and hasattr(chat_view, 'container'):
                    QTimer.singleShot(50, chat_view.container.updateGeometry)
                
                # 请求滚动到底部，使用统一的滚动管理
                if chat_view:
                    # 稍微延迟，确保布局完成
                    QTimer.singleShot(100, chat_view.request_auto_scroll)
            
    def update_dots(self):
        """Update loading dots animation"""
        self.dots_count = (self.dots_count + 1) % 4
        dots = "." * self.dots_count
        self.content_label.setText(f"{self.message.content}{dots}")
    
    def mark_as_completed(self):
        """标记流式输出已完成，快速显示剩余内容"""
        print(f"🏁 [STREAMING] 流式输出完成，快速显示剩余内容")
        print(f"🏁 [STREAMING] 当前显示: {self.display_index}/{len(self.full_text)} 字符")
        
        # 如果还有很多未显示的内容，直接快速显示
        remaining_chars = len(self.full_text) - self.display_index
        if remaining_chars > 50:
            print(f"⚡ [STREAMING] 剩余 {remaining_chars} 字符，切换到极速显示模式")
            # 停止当前定时器
            self.typing_timer.stop()
            # 使用极快的定时器快速显示剩余内容
            self.typing_timer.start(1)  # 1ms per character，极快速度
        else:
            print(f"✅ [STREAMING] 剩余 {remaining_chars} 字符不多，保持当前速度")


class ChatView(QScrollArea):
    """Chat message list view"""
    
    wiki_requested = pyqtSignal(str, str)  # url, title
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages: List[MessageWidget] = []
        self.current_status_widget: Optional[StatusMessageWidget] = None
        
        # 自动滚动控制
        self.auto_scroll_enabled = True  # 是否启用自动滚动
        self.user_scrolled_manually = False  # 用户是否手动滚动过
        self.last_scroll_position = 0  # 上次滚动位置
        
        # resize防抖动机制
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._performDelayedResize)
        
        # 统一的滚动管理器
        self._scroll_request_timer = QTimer()
        self._scroll_request_timer.setSingleShot(True)
        self._scroll_request_timer.timeout.connect(self._perform_auto_scroll)
        self._scroll_request_pending = False
        
        # 内容稳定检测
        self._last_content_height = 0
        self._content_stable_timer = QTimer()
        self._content_stable_timer.setSingleShot(True)
        self._content_stable_timer.timeout.connect(self._check_content_stability)
        
        # 动画状态标志
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
        self.layout.addStretch()  # 保持底部对齐
        
        # 确保容器填充ScrollArea
        self.container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        self.setWidget(self.container)
        
        # Styling
        self.setStyleSheet("""
            QScrollArea {
                background-color: white;
                border: none;
            }
        """)
        
        # 连接滚动条信号，监测用户手动滚动
        scrollbar = self.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll_changed)
        scrollbar.sliderPressed.connect(self._on_user_scroll_start)
        scrollbar.sliderReleased.connect(self._on_user_scroll_end)
        
        # 添加欢迎信息
        self._add_welcome_message()
        
    def _check_and_fix_width(self):
        """检查并修复ChatView宽度异常"""
        if not self.parent():
            return
            
        parent_width = self.parent().width()
        current_width = self.width()
        viewport_width = self.viewport().width()
        
        # 如果父容器宽度正常但ChatView宽度异常
        if parent_width > 600 and current_width < 600:
            print(f"🔧 检测到ChatView宽度异常，开始修复:")
            print(f"  父容器宽度: {parent_width}px")
            print(f"  ChatView宽度: {current_width}px") 
            print(f"  viewport宽度: {viewport_width}px")
            
            # 显示完整的父容器链
            print(f"  完整父容器链:")
            parent = self.parent()
            level = 0
            while parent and level < 5:
                parent_width_info = parent.width() if hasattr(parent, 'width') else "N/A"
                parent_type = type(parent).__name__
                parent_geometry = parent.geometry() if hasattr(parent, 'geometry') else "N/A"
                print(f"    └─ [{level}] {parent_type}: 宽度={parent_width_info}px, 几何={parent_geometry}")
                parent = parent.parent() if hasattr(parent, 'parent') else None
                level += 1
            
            # 强制设置为父容器宽度
            self.setFixedWidth(parent_width)
            QTimer.singleShot(50, lambda: self.setMaximumWidth(16777215))  # 延迟移除固定宽度限制
            QTimer.singleShot(100, lambda: self.setMinimumWidth(0))
            
            print(f"🔧 已修复ChatView宽度为: {parent_width}px")
            
        # 如果viewport宽度异常，强制刷新
        elif viewport_width < 600 and parent_width > 600:
            print(f"🔧 检测到viewport宽度异常，强制刷新layout")
            print(f"  当前尺寸策略: {self.sizePolicy().horizontalPolicy()}")
            print(f"  最小尺寸: {self.minimumSize()}")
            print(f"  最大尺寸: {self.maximumSize()}")
            
            self.updateGeometry()
            self.container.updateGeometry()
            if self.parent():
                self.parent().updateGeometry()
        
    def _add_welcome_message(self):
        """添加欢迎信息和推荐查询"""
        # 构建多语言欢迎消息
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
        
        # 创建欢迎消息
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
        # 检查并修复ChatView宽度异常
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
        
        # 动态设置消息最大宽度为聊天视图宽度的75%
        self._update_message_width(widget)
        
        # 温和的布局更新，避免强制调整大小
        widget.updateGeometry()
        self.container.updateGeometry()
        
        # 使用统一的滚动请求机制
        self.request_auto_scroll()
        
        return widget
        
    def add_streaming_message(self) -> StreamingMessageWidget:
        """Add a new streaming message"""
        print(f"🎬 [UI-DEBUG] 开始创建流式消息组件")
        try:
            # 创建流式消息，完成后会转换为AI_RESPONSE类型
            streaming_widget = self.add_message(MessageType.AI_STREAMING, "")
            print(f"✅ [UI-DEBUG] 流式消息组件创建成功: {streaming_widget}")
            print(f"✅ [UI-DEBUG] 流式消息组件类型: {type(streaming_widget)}")
            return streaming_widget
        except Exception as e:
            print(f"❌ [UI-DEBUG] 创建流式消息组件失败: {e}")
            raise
        
    def show_status(self, message: str) -> StatusMessageWidget:
        """显示状态信息"""
        # 检查并修复ChatView宽度异常
        self._check_and_fix_width()
        
        # 如果已有状态消息，先隐藏
        if self.current_status_widget:
            self.hide_status()
            
        # 创建新的状态消息
        self.current_status_widget = StatusMessageWidget(message, self)
        self.layout.insertWidget(self.layout.count() - 1, self.current_status_widget)
        
        # 动态设置消息最大宽度
        self._update_status_width(self.current_status_widget)
        
        # 温和的布局更新
        self.current_status_widget.updateGeometry()
        self.container.updateGeometry()
        # 使用统一的滚动请求机制
        self.request_auto_scroll()
        
        return self.current_status_widget
        
    def update_status(self, message: str):
        """更新当前状态信息"""
        if self.current_status_widget:
            self.current_status_widget.update_status(message)
            # 确保滚动到底部显示新状态
            self.request_auto_scroll()
        else:
            self.show_status(message)
            
    def hide_status(self):
        """隐藏当前状态信息"""
        if self.current_status_widget:
            self.current_status_widget.hide_with_fadeout()
            self.layout.removeWidget(self.current_status_widget)
            self.current_status_widget.deleteLater()
            self.current_status_widget = None
            
    def _update_status_width(self, widget: StatusMessageWidget):
        """更新状态消息控件的最大宽度"""
        # 获取聊天视图的实际宽度，考虑滚动条宽度
        chat_width = self.viewport().width()
        
        # 减去滚动条可能占用的宽度
        scrollbar = self.verticalScrollBar()
        if scrollbar and scrollbar.isVisible():
            chat_width -= scrollbar.width()
            
        if chat_width > 0:
            # 确保有效宽度
            chat_width = max(300, chat_width)
            
            # 设置状态消息最大宽度为聊天视图宽度的75%，最小300px，最大600px
            max_width = min(max(int(chat_width * 0.75), 300), 600)
            # 找到状态气泡并设置其最大宽度
            bubble = widget.findChild(QFrame, "statusBubble")
            if bubble:
                bubble.setMaximumWidth(max_width)
                # 使用首选尺寸策略，避免固定宽度造成布局问题
                bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        
    def scroll_to_bottom(self):
        """Scroll to the bottom of the chat"""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def smart_scroll_to_bottom(self):
        """智能滚动到底部 - 只在启用自动滚动时执行"""
        if self.auto_scroll_enabled and not self.user_scrolled_manually:
            self.scroll_to_bottom()
            
    def request_auto_scroll(self):
        """请求自动滚动（防抖动）"""
        if not self.auto_scroll_enabled or self.user_scrolled_manually:
            print(f"🚫 [SCROLL] 滚动请求被拒绝 - auto_enabled: {self.auto_scroll_enabled}, manual: {self.user_scrolled_manually}")
            return
            
        # 标记有滚动请求
        self._scroll_request_pending = True
        print(f"📋 [SCROLL] 收到滚动请求，启动防抖定时器")
        
        # 使用防抖动定时器，避免频繁滚动
        self._scroll_request_timer.stop()
        self._scroll_request_timer.start(100)  # 100ms防抖
        
    def _perform_auto_scroll(self):
        """实际执行自动滚动"""
        print(f"🔄 [SCROLL] _perform_auto_scroll 被调用，pending: {self._scroll_request_pending}")
        if not self._scroll_request_pending:
            return
            
        # 检查内容高度是否变化
        current_height = self.container.sizeHint().height()
        if current_height != self._last_content_height:
            # 内容还在变化，等待稳定
            print(f"📏 [SCROLL] 内容高度变化: {self._last_content_height} -> {current_height}，等待稳定")
            self._last_content_height = current_height
            self._content_stable_timer.stop()
            self._content_stable_timer.start(50)  # 50ms后再次检查
            return
            
        # 内容稳定，执行滚动
        if self.auto_scroll_enabled and not self.user_scrolled_manually:
            # 检查是否在底部附近（容差50px）
            scrollbar = self.verticalScrollBar()
            at_bottom = (scrollbar.maximum() - scrollbar.value()) <= 50
            
            print(f"📊 [SCROLL] 滚动检查 - max: {scrollbar.maximum()}, value: {scrollbar.value()}, at_bottom: {at_bottom}")
            
            if at_bottom or self._scroll_request_pending:
                # 平滑滚动到底部
                self.scroll_to_bottom()
                print(f"📍 [SCROLL] 执行自动滚动，高度: {current_height}px")
        else:
            print(f"🚫 [SCROLL] 滚动被禁用或用户手动滚动")
                
        self._scroll_request_pending = False
        
    def _check_content_stability(self):
        """检查内容是否稳定"""
        current_height = self.container.sizeHint().height()
        if current_height == self._last_content_height:
            # 内容稳定，执行挂起的滚动
            if self._scroll_request_pending:
                self._perform_auto_scroll()
        else:
            # 内容仍在变化，继续等待
            self._last_content_height = current_height
            self._content_stable_timer.start(50)
            
    def _on_scroll_changed(self, value):
        """滚动位置改变时的回调"""
        scrollbar = self.verticalScrollBar()
        
        # 检查是否接近底部（距离底部少于50像素）
        near_bottom = (scrollbar.maximum() - value) <= 50
        
        # 如果用户滚动到接近底部，重新启用自动滚动
        if near_bottom and self.user_scrolled_manually:
            print("📍 用户滚动到底部附近，重新启用自动滚动")
            self.user_scrolled_manually = False
            self.auto_scroll_enabled = True
            
    def _on_user_scroll_start(self):
        """用户开始手动滚动"""
        self.user_scrolled_manually = True
        
    def _on_user_scroll_end(self):
        """用户结束手动滚动"""
        # 检查当前是否在底部附近
        scrollbar = self.verticalScrollBar()
        near_bottom = (scrollbar.maximum() - scrollbar.value()) <= 50
        
        if not near_bottom:
            # 如果不在底部，禁用自动滚动
            self.auto_scroll_enabled = False
            print("📍 用户手动滚动离开底部，禁用自动滚动")
        else:
            # 如果在底部，保持自动滚动
            self.auto_scroll_enabled = True
            self.user_scrolled_manually = False
            print("📍 用户在底部附近，保持自动滚动")
            
    def wheelEvent(self, event):
        """鼠标滚轮事件 - 检测用户滚轮操作"""
        # 标记用户进行了手动滚动
        self.user_scrolled_manually = True
        
        # 调用原始的滚轮事件处理
        super().wheelEvent(event)
        
        # 延迟检查是否在底部附近
        QTimer.singleShot(100, self._check_if_near_bottom)
        
    def _check_if_near_bottom(self):
        """检查是否接近底部"""
        scrollbar = self.verticalScrollBar()
        near_bottom = (scrollbar.maximum() - scrollbar.value()) <= 50
        
        if near_bottom:
            # 如果接近底部，重新启用自动滚动
            self.auto_scroll_enabled = True
            self.user_scrolled_manually = False
        else:
            # 否则禁用自动滚动
            self.auto_scroll_enabled = False
            print("📍 滚轮操作离开底部，禁用自动滚动")
            
    def mouseDoubleClickEvent(self, event):
        """双击事件 - 手动重新启用自动滚动并滚动到底部"""
        if event.button() == Qt.MouseButton.LeftButton:
            print("📍 双击聊天区域，重新启用自动滚动")
            self.auto_scroll_enabled = True
            self.user_scrolled_manually = False
            self.scroll_to_bottom()
        super().mouseDoubleClickEvent(event)
        
    def reset_auto_scroll(self):
        """重置自动滚动状态（供外部调用）"""
        self.auto_scroll_enabled = True
        self.user_scrolled_manually = False
        print("📍 重置自动滚动状态")
        
    def disable_auto_scroll(self):
        """禁用自动滚动（供外部调用）"""
        self.auto_scroll_enabled = False
        self.user_scrolled_manually = True
        print("📍 禁用自动滚动")
        
    def keyPressEvent(self, event):
        """键盘事件 - 支持快捷键控制自动滚动"""
        if event.key() == Qt.Key.Key_End:
            # End键：重新启用自动滚动并滚动到底部
            print("📍 按下End键，重新启用自动滚动")
            self.auto_scroll_enabled = True
            self.user_scrolled_manually = False
            self.scroll_to_bottom()
        elif event.key() == Qt.Key.Key_Home:
            # Home键：滚动到顶部并禁用自动滚动
            print("📍 按下Home键，滚动到顶部并禁用自动滚动")
            self.auto_scroll_enabled = False
            self.user_scrolled_manually = True
            scrollbar = self.verticalScrollBar()
            scrollbar.setValue(0)
        else:
            super().keyPressEvent(event)
        
    def show_wiki(self, url: str, title: str):
        """Emit signal to show wiki page"""
        logger = logging.getLogger(__name__)
        logger.info(f"📄 ChatView.show_wiki 被调用: URL={url}, Title={title}")
        self.wiki_requested.emit(url, title)
        logger.info(f"📤 已发出wiki_requested信号")
        
    def _update_message_width(self, widget: MessageWidget):
        """更新消息控件的最大宽度"""
        # 如果正在动画中，跳过更新
        if self._is_animating:
            return
            
        # 获取多层容器的宽度信息，用于调试
        viewport_width = self.viewport().width()
        scroll_area_width = self.width()
        parent_window_width = self.parent().width() if self.parent() else "N/A"
        
        # 获取聊天视图的实际宽度，考虑滚动条宽度
        chat_width = viewport_width
        
        # 减去滚动条可能占用的宽度
        scrollbar = self.verticalScrollBar()
        scrollbar_width = 0
        if scrollbar and scrollbar.isVisible():
            scrollbar_width = scrollbar.width()
            chat_width -= scrollbar_width
            
        if chat_width > 0:
            # 确保有效宽度
            chat_width = max(300, chat_width)
            
            # 设置消息最大宽度为聊天视图宽度的75%，最小300px，最大600px
            max_width = min(max(int(chat_width * 0.75), 300), 600)
            
            # 如果是StreamingMessageWidget，调用其专门的更新方法
            if isinstance(widget, StreamingMessageWidget):
                widget._update_bubble_width()
            else:
                # 对于普通消息，使用最大宽度而不是固定宽度
                bubble = widget.findChild(QFrame, "messageBubble")
                if bubble:
                    # 使用最大宽度，让布局系统自由决定实际宽度
                    bubble.setMaximumWidth(max_width)
                    bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
                
                # 同时更新content_label的宽度
                if hasattr(widget, 'content_label'):
                    content_width = max_width - 24  # 减去边距
                    widget.content_label.setMaximumWidth(content_width)
                    widget.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
                
                # 只在异常情况下输出调试信息
                if viewport_width < 400:  # 当视图宽度异常小时输出警告
                    print(f"⚠️ 视图宽度异常: viewport={viewport_width}px")
                
    def resizeEvent(self, event):
        """窗口大小改变时触发防抖动更新"""
        super().resizeEvent(event)
        
        # 如果正在动画中，跳过更新，避免卡顿
        if self._is_animating:
            return
        
        # 强制ChatView保持正确的宽度（立即执行，避免显示异常）
        parent_width = self.parent().width() if self.parent() else 0
        current_width = self.width()
        if parent_width > 0 and abs(current_width - parent_width) > 5:  # 超过5px差异
            self.resize(parent_width, self.height())
        
        # 使用防抖动机制延迟更新消息宽度（恢复原有逻辑）
        self.resize_timer.stop()  # 停止之前的计时器
        self.resize_timer.start(200)  # 0.2秒后执行更新
        
    def _performDelayedResize(self):
        """延迟执行的resize更新操作"""
        print(f"📏 ChatView布局更新: {self.size()}")
        
        # 更新所有现有消息的宽度
        for widget in self.messages:
            self._update_message_width(widget)
        # 更新状态消息的宽度
        if self.current_status_widget:
            self._update_status_width(self.current_status_widget)
            
        # 强制更新所有消息的高度，确保内容完整显示
        self._ensureContentComplete()
        
        # 延迟一点时间再次检查，确保所有内容都已渲染
        QTimer.singleShot(50, self._finalizeContentDisplay)
        
        # 确保滚动到正确位置
        QTimer.singleShot(100, self.smart_scroll_to_bottom)
        
    def _ensureContentComplete(self):
        """确保所有消息内容完整显示"""
        try:
            # 更新所有消息的显示
            for widget in self.messages:
                if hasattr(widget, 'content_label'):
                    try:
                        # 1. 更新消息宽度
                        self._update_message_width(widget)
                        
                        # 2. 强制内容标签重新计算尺寸
                        content_label = widget.content_label
                        
                        # 确保内容不被截断
                        content_label.setWordWrap(True)
                        content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
                        
                        # 对于 StreamingMessageWidget，确保格式正确
                        if isinstance(widget, StreamingMessageWidget):
                            # 如果有完整文本，重新检测并渲染
                            if hasattr(widget, 'full_text') and widget.full_text:
                                if detect_markdown_content(widget.full_text):
                                    html_content = convert_markdown_to_html(widget.full_text)
                                    content_label.setText(html_content)
                                    content_label.setTextFormat(Qt.TextFormat.RichText)
                                else:
                                    content_label.setText(widget.full_text)
                                    content_label.setTextFormat(Qt.TextFormat.PlainText)
                        
                        # 3. 强制更新内容大小
                        content_label.adjustSize()
                        
                        # 4. 确保气泡容器正确扩展
                        bubble = widget.findChild(QFrame, "messageBubble")
                        if bubble:
                            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
                            
                            # 改进：使用更可靠的方式计算所需高度
                            # 等待一小段时间让内容渲染完成
                            QTimer.singleShot(10, lambda w=widget, b=bubble, cl=content_label: self._updateBubbleHeight(w, b, cl))
                        
                        # 5. 对于流式消息的特别处理
                        if isinstance(widget, StreamingMessageWidget):
                            if hasattr(widget, 'full_text') and widget.full_text:
                                widget._update_bubble_width()
                                widget.updateGeometry()
                        
                    except Exception as e:
                        # 记录错误而不是静默处理
                        print(f"更新消息显示时出错: {e}")
            
            # 更新状态消息
            if self.current_status_widget:
                try:
                    self._update_status_width(self.current_status_widget)
                except Exception:
                    pass
            
            # 强制整个容器重新布局
            self.container.updateGeometry()
            self.updateGeometry()
            self.verticalScrollBar().update()
            
        except Exception as e:
            # 记录全局错误
            print(f"_ensureContentComplete 出错: {e}")
    
    def _updateBubbleHeight(self, widget, bubble, content_label):
        """延迟更新气泡高度，确保内容渲染完成"""
        try:
            # 获取内容的实际高度
            # 使用多种方法来获取最准确的高度
            height1 = content_label.sizeHint().height()
            height2 = content_label.heightForWidth(content_label.width())
            
            # 对于富文本内容，需要额外的高度计算
            if content_label.textFormat() == Qt.TextFormat.RichText:
                # 创建临时文档来准确计算HTML内容高度
                doc = QTextDocument()
                doc.setDefaultFont(content_label.font())
                doc.setHtml(content_label.text())
                doc.setTextWidth(content_label.width())
                height3 = int(doc.size().height())
            else:
                height3 = height1
            
            # 取最大值确保内容完整显示
            actual_height = max(height1, height2, height3)
            
            # 加上内边距
            min_height = actual_height + 20  # 增加边距
            
            # 设置最小高度
            bubble.setMinimumHeight(min_height)
            
            # 强制更新整个消息widget
            widget.updateGeometry()
            widget.update()
            
        except Exception as e:
            print(f"更新气泡高度时出错: {e}")
    
    def _finalizeContentDisplay(self):
        """最终确认内容显示完整"""
        # 再次检查所有消息的高度
        for widget in self.messages:
            if hasattr(widget, 'content_label'):
                bubble = widget.findChild(QFrame, "messageBubble")
                if bubble and widget.content_label:
                    self._updateBubbleHeight(widget, bubble, widget.content_label)
    
    def _force_content_refresh(self):
        """强制刷新所有内容显示（简化版本）"""
        try:
            # 简单的内容刷新，确保滚动位置正确
            if hasattr(self, 'near_bottom_before_resize') and self.near_bottom_before_resize:
                self.scroll_to_bottom()
        except Exception:
            pass
            
    def update_all_message_widths(self):
        """更新所有消息的宽度（用于窗口显示后的初始化）"""
        for widget in self.messages:
            self._update_message_width(widget)
        if self.current_status_widget:
            self._update_status_width(self.current_status_widget)
        
    def showEvent(self, event):
        """窗口显示时更新消息宽度"""
        super().showEvent(event)
        # 延迟更新，确保窗口已完全显示
        QTimer.singleShot(100, self.update_all_message_widths)


# Only define CustomWebEnginePage if WebEngine is available
if WEBENGINE_AVAILABLE and QWebEnginePage:
    class CustomWebEnginePage(QWebEnginePage):
        """Custom page to handle all navigation in current window"""
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Connect the newWindowRequested signal to handle new window requests
            self.newWindowRequested.connect(self._handle_new_window_request)
        
        def createWindow(self, window_type):
            """Override to prevent new windows/tabs from opening
            Return None to trigger newWindowRequested signal"""
            # Don't create a new window, let the signal handler deal with it
            return None
        
        def _handle_new_window_request(self, request):
            """Handle new window request by navigating in current window"""
            # Get the requested URL from the request
            url = request.requestedUrl()
            print(f"🔗 新窗口请求被拦截，在当前窗口打开: {url.toString()}")
            # Navigate to the URL in the current page
            self.setUrl(url)
            # The browser history will automatically be updated
        
        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            """Handle navigation requests"""
            # Always accept navigation in the main frame
            if is_main_frame:
                return True
            
            # For subframes (iframes), check the navigation type
            if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                # If a link in an iframe tries to navigate, load it in the main frame
                self.setUrl(url)
                return False
                
            # Allow other types of navigation in subframes
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
else:
    CustomWebEnginePage = None


class WikiView(QWidget):
    """Wiki page viewer - 简化版本以避免崩溃"""
    
    back_requested = pyqtSignal()
    wiki_page_loaded = pyqtSignal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_search_url = ""  # 存储搜索URL
        self.current_search_title = ""  # 存储搜索标题
        self.web_view = None
        self.content_widget = None
        self._webview_ready = False
        self._is_paused = False  # 添加暂停状态标记
        self._pause_lock = False  # 添加暂停锁，防止重复调用
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
        self.nav_back_button.setToolTip("返回上一页")
        self.nav_back_button.setEnabled(False)
        
        self.nav_forward_button = QPushButton("▶")
        self.nav_forward_button.setStyleSheet(nav_button_style)
        self.nav_forward_button.setToolTip("前进到下一页")
        self.nav_forward_button.setEnabled(False)
        
        self.refresh_button = QPushButton("🔄")
        self.refresh_button.setStyleSheet(nav_button_style)
        self.refresh_button.setToolTip("刷新页面")
        
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
        self.url_bar.setPlaceholderText("输入URL并按Enter键导航...")
        
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
        
        # Content area - 简化WebView创建逻辑
        self.web_view = None
        self.content_widget = None
        
        # 尝试创建WebView，优先使用WebView2
        webview_created = False
        
        # Try WebView2 first if enabled and available
        if USE_WEBVIEW2 and WEBVIEW2_AVAILABLE:
            try:
                print("🔧 尝试创建WebView2...")
                self.web_view = WebView2Widget()
                self.content_widget = self.web_view
                self._webview_ready = True
                webview_created = True
                print("✅ WebView2创建成功 - 支持完整视频播放")
                
                # 连接导航信号
                self._connect_navigation_signals()
                
            except Exception as e:
                print(f"❌ WebView2创建失败: {e}")
                webview_created = False
        
        # Fall back to WebEngine if WebView2 failed or not available
        if not webview_created and WEBENGINE_AVAILABLE and QWebEngineView:
            try:
                print("🔧 尝试创建WebEngine...")
                self.web_view = QWebEngineView()
                
                # 使用自定义页面来处理导航
                if CustomWebEnginePage:
                    custom_page = CustomWebEnginePage(self.web_view)
                    self.web_view.setPage(custom_page)
                
                # 配置WebEngine设置以允许加载外部内容
                try:
                    if hasattr(self.web_view, 'settings'):
                        settings = self.web_view.settings()
                        if QWebEngineSettings:
                            # 允许JavaScript
                            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                            # 允许本地内容访问远程资源（重要！）
                            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                            # 允许本地内容访问文件
                            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
                            # 允许JavaScript打开窗口（重要！这样createWindow才会被调用）
                            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
                            print("✅ WebEngine设置已配置")
                except Exception as settings_error:
                    print(f"⚠️ WebEngine设置配置失败: {settings_error}")
                
                # 连接导航信号
                self._connect_navigation_signals()
                
                self.content_widget = self.web_view
                self._webview_ready = True
                webview_created = True
                print("✅ WebEngine创建成功")
            except Exception as e:
                print(f"❌ WebEngine创建失败: {e}")
                webview_created = False
        
        # Final fallback to text view
        if not webview_created:
            print("⚠️ WebView不可用，使用文本视图")
            self.web_view = None
            self.content_widget = self._create_fallback_text_view()
        
        layout.addWidget(toolbar)
        layout.addWidget(self.content_widget)
        
        # Store current URL and title
        self.current_url = ""
        self.current_title = ""
        
    def load_url(self, url: str):
        """Load a URL in the web view"""
        if self.web_view:
            self.web_view.setUrl(QUrl(url))
            self.current_url = url
    
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
        
        # For WebEngine, connect page signals
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
            
        self.load_url(url)
        
    def _on_url_changed(self, url):
        """Update URL bar when URL changes"""
        url_str = url.toString()
        self.url_bar.setText(url_str)
        self.current_url = url_str
        
    def _on_load_started(self):
        """Called when page loading starts"""
        # You could add a loading indicator here if desired
        pass
        
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
        """页面加载完成时的回调"""
        if not ok or not self.web_view:
            return
            
        # Update navigation state
        self._update_navigation_state()
            
        try:
            # 获取当前页面的URL和标题
            current_url = self.web_view.url().toString()
            
            # 检查是否是真实的wiki页面（不是搜索页面）
            if self._is_real_wiki_page(current_url):
                # 获取页面标题
                self.web_view.page().runJavaScript(
                    "document.title",
                    self._on_title_received
                )
            else:
                # 如果还是搜索页面，等待一段时间后再次检查
                QTimer.singleShot(2000, self._check_for_redirect)
                
        except Exception as e:
            print(f"页面加载完成处理失败: {e}")
            
    def _check_for_redirect(self):
        """检查页面是否已重定向到真实wiki页面"""
        if not self.web_view:
            return
            
        try:
            current_url = self.web_view.url().toString()
            if self._is_real_wiki_page(current_url):
                self.web_view.page().runJavaScript(
                    "document.title",
                    self._on_title_received
                )
        except Exception as e:
            print(f"重定向检查失败: {e}")
            
    def _is_real_wiki_page(self, url: str) -> bool:
        """判断是否是真实的wiki页面（而不是搜索页面）"""
        if not url:
            return False
            
        # 检查URL是否包含常见的搜索引擎域名
        search_engines = [
            'duckduckgo.com',
            'bing.com',
            'google.com',
            'search.yahoo.com'
        ]
        
        for engine in search_engines:
            if engine in url.lower():
                return False
                
        # 检查是否包含wiki相关域名或路径
        wiki_indicators = [
            'wiki',
            'fandom.com',
            'wikia.com',
            'gamepedia.com',
            'huijiwiki.com',  # 添加灰机wiki支持
            'mcmod.cn',       # MC百科
            'terraria.wiki.gg',
            'helldiversgamepedia.com'
        ]
        
        url_lower = url.lower()
        for indicator in wiki_indicators:
            if indicator in url_lower:
                return True
                
        # 如果URL与初始搜索URL不同，且不是搜索引擎，认为是真实页面
        return url != self.current_search_url
        
    def _on_title_received(self, title):
        """收到页面标题时的回调"""
        if not title or not self.web_view:
            return
            
        try:
            current_url = self.web_view.url().toString()
            
            # 更新显示的标题
            self.current_url = current_url
            self.current_title = title
            
            # 发出信号，通知找到了真实的wiki页面
            print(f"📄 WikiView找到真实wiki页面: {title} -> {current_url}")
            self.wiki_page_loaded.emit(current_url, title)
            
        except Exception as e:
            print(f"处理页面标题失败: {e}")
    
    def _create_persistent_webview(self):
        """创建带有持久化Cookie配置的QWebEngineView - 简化版本避免崩溃"""
        if not WEBENGINE_AVAILABLE or not QWebEngineView or not QWebEngineProfile:
            return None
            
        print("🔧 开始创建持久化WebView...")
        
        try:
            # 先创建基本WebView
            web_view = QWebEngineView()
            print("✅ 基本WebView创建成功")
            
            # 尝试配置持久化Profile（如果失败不影响WebView使用）
            try:
                # 导入路径工具
                from src.game_wiki_tooltip.utils import APPDATA_DIR
                
                # 使用较短的存储名称，避免路径问题
                storage_name = "GameWiki"
                
                # 创建持久化Profile
                profile = QWebEngineProfile(storage_name)
                print(f"✅ 创建Profile成功: {storage_name}")
                
                # 设置存储路径（如果失败不中断）
                try:
                    profile_path = APPDATA_DIR / "webengine_profile"
                    cache_path = APPDATA_DIR / "webengine_cache"
                    profile_path.mkdir(parents=True, exist_ok=True)
                    cache_path.mkdir(parents=True, exist_ok=True)
                    
                    profile.setPersistentStoragePath(str(profile_path))
                    profile.setCachePath(str(cache_path))
                    print("✅ 存储路径配置成功")
                except Exception as path_error:
                    print(f"⚠️ 存储路径配置失败（使用默认）: {path_error}")
                
                # 设置Cookie策略（如果失败不中断）
                try:
                    # 尝试PyQt6风格
                    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
                    print("✅ Cookie策略配置成功 (PyQt6)")
                except AttributeError:
                    try:
                        # 尝试PyQt5风格
                        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
                        print("✅ Cookie策略配置成功 (PyQt5)")
                    except Exception as cookie_error:
                        print(f"⚠️ Cookie策略配置失败: {cookie_error}")
                
                # 配置本地文件访问权限（用于DST任务流程等本地HTML文件）
                try:
                    # 允许访问本地文件
                    if hasattr(profile, 'settings'):
                        settings = profile.settings()
                        if hasattr(settings, 'setAttribute'):
                            # 启用本地文件访问
                            try:
                                from PyQt6.QtWebEngineCore import QWebEngineSettings
                                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
                                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                                print("✅ 本地文件访问权限配置成功 (PyQt6)")
                            except ImportError:
                                try:
                                    from PyQt5.QtWebEngineWidgets import QWebEngineSettings
                                    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
                                    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
                                    print("✅ 本地文件访问权限配置成功 (PyQt5)")
                                except Exception as settings_error:
                                    print(f"⚠️ 本地文件访问权限配置失败: {settings_error}")
                except Exception as access_error:
                    print(f"⚠️ 无法配置本地文件访问权限: {access_error}")
                
                # 尝试设置WebView使用自定义Profile（关键步骤）
                try:
                    try:
                        from PyQt6.QtWebEngineCore import QWebEnginePage
                    except ImportError:
                        from PyQt5.QtWebEngineCore import QWebEnginePage
                    
                    if CustomWebEnginePage:
                        page = CustomWebEnginePage(profile, web_view)
                        web_view.setPage(page)
                    else:
                        page = QWebEnginePage(profile, web_view)
                        web_view.setPage(page)
                    print("✅ Profile与WebView关联成功")
                    
                    # 验证Profile状态
                    if hasattr(profile, 'isOffTheRecord') and not profile.isOffTheRecord():
                        print("✅ Profile支持持久化Cookie")
                    else:
                        print("⚠️ Profile可能不支持持久化")
                        
                except Exception as page_error:
                    print(f"⚠️ Profile关联失败，使用默认Profile: {page_error}")
                    
            except Exception as profile_error:
                print(f"⚠️ Profile配置失败，使用默认配置: {profile_error}")
            
            print("✅ WebView创建完成")
            return web_view
                
        except Exception as e:
            print(f"❌ WebView创建完全失败: {e}")
            return None
    
    def _create_fallback_text_view(self):
        """创建降级的文本视图"""
        text_view = QTextEdit()
        text_view.setReadOnly(True)
        text_view.setMinimumSize(100, 100)  # 减小最小尺寸，避免影响布局
        text_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        text_view.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: none;
                font-family: "Microsoft YaHei", "Segoe UI", Arial;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        return text_view
    
    def _check_webengine_ready(self):
        """检查WebEngine是否已准备就绪"""
        try:
            # 检查基本可用性
            if not WEBENGINE_AVAILABLE or not QWebEngineView:
                return False, "WebEngine不可用"
            
            # 检查是否可以访问Profile
            try:
                test_profile = QWebEngineProfile.defaultProfile()
                if test_profile is None:
                    return False, "无法访问默认Profile"
            except Exception as e:
                return False, f"Profile访问失败: {e}"
            
            # 尝试创建一个临时的WebView进行测试
            try:
                temp_view = QWebEngineView()
                temp_view.deleteLater()
                return True, "WebEngine就绪"
            except Exception as e:
                return False, f"WebView创建测试失败: {e}"
                
        except Exception as e:
            return False, f"WebEngine检查失败: {e}"
    
    def _delayed_webview_creation(self):
        """延迟创建WebView，在Qt应用完全初始化后执行"""
        try:
            print("🔧 开始延迟WebView创建...")
            
            # 首先检查WebEngine是否准备就绪
            ready, message = self._check_webengine_ready()
            if not ready:
                print(f"❌ WebEngine未就绪: {message}")
                print("继续使用文本视图")
                return
            
            print(f"✅ WebEngine状态检查通过: {message}")
            
            # 尝试创建WebView
            new_web_view = self._create_persistent_webview_safe()
            
            if new_web_view is not None:
                print("✅ WebView延迟创建成功")
                
                # 配置WebView属性
                try:
                    new_web_view.setMinimumSize(100, 100)
                    new_web_view.setMaximumSize(16777215, 16777215)
                    new_web_view.setSizePolicy(
                        QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Expanding
                    )
                    
                    # 连接信号
                    new_web_view.loadFinished.connect(self._on_page_load_finished)
                    print("✅ WebView配置完成")
                except Exception as config_error:
                    print(f"⚠️ WebView配置失败: {config_error}")
                
                # 替换内容组件
                try:
                    old_widget = self.content_widget
                    self.content_widget = new_web_view
                    self.web_view = new_web_view
                    self._webview_ready = True  # 标记WebView已准备好
                    
                    # 更新布局
                    layout = self.layout()
                    if layout:
                        # 查找旧的content_widget并替换
                        for i in range(layout.count()):
                            item = layout.itemAt(i)
                            if item and item.widget() == old_widget:
                                layout.removeWidget(old_widget)
                                layout.addWidget(new_web_view)
                                # 延迟删除旧组件，避免立即删除引起问题
                                QTimer.singleShot(100, old_widget.deleteLater)
                                break
                    
                    print("✅ WebView已成功替换文本视图")
                except Exception as replace_error:
                    print(f"⚠️ WebView替换失败: {replace_error}")
                    # 如果替换失败，清理新创建的WebView
                    new_web_view.deleteLater()
            else:
                print("⚠️ WebView创建失败，继续使用文本视图")
                
        except Exception as e:
            print(f"❌ 延迟WebView创建过程失败: {e}")
            print("继续使用文本视图作为降级方案")
    
    def _create_persistent_webview_safe(self):
        """安全创建WebView的方法，包含更多错误处理"""
        try:
            print("🔧 开始安全创建WebView...")
            
            # 分步骤创建，每步都检查
            
            # 步骤1：测试基本WebView创建
            try:
                test_view = QWebEngineView()
                test_view.deleteLater()  # 立即清理
                print("✅ 基本WebView创建能力确认")
            except Exception as test_error:
                print(f"❌ 基本WebView创建测试失败: {test_error}")
                return None
            
            # 步骤2：短暂等待，确保清理完成
            import time
            time.sleep(0.1)
            
            # 步骤3：尝试创建实际的WebView
            web_view = self._create_persistent_webview()
            
            if web_view is not None:
                print("✅ 持久化WebView创建成功")
                return web_view
            else:
                print("⚠️ 持久化WebView创建失败，尝试基本WebView")
                # 最后尝试：创建最基本的WebView
                try:
                    basic_view = QWebEngineView()
                    print("✅ 降级到基本WebView成功")
                    return basic_view
                except Exception as basic_error:
                    print(f"❌ 基本WebView创建也失败: {basic_error}")
                    return None
            
        except Exception as e:
            print(f"❌ 安全WebView创建完全失败: {e}")
            return None
        
    def load_wiki(self, url: str, title: str):
        """Load a wiki page"""
        self.current_search_url = url  # 保存搜索URL
        self.current_search_title = title  # 保存搜索标题
        self.current_url = url
        self.current_title = title
        self.url_bar.setText(url)  # Update URL bar instead of title label
        
        if self.web_view:
            try:
                # 对于本地文件，直接使用load方法以保留外部资源加载能力
                if url.startswith('file:///'):
                    # 创建QUrl对象
                    qurl = QUrl(url)
                    print(f"📄 加载本地文件: {url}")
                    
                    # 直接加载文件URL，让WebEngine处理外部资源
                    self.web_view.load(qurl)
                    print(f"✅ 使用load方法加载本地HTML，保留外部资源加载")
                else:
                    # 非本地文件，正常加载
                    self.web_view.load(QUrl(url))
            except Exception as e:
                print(f"❌ 加载wiki页面失败: {e}")
                import traceback
                traceback.print_exc()
                # 显示错误信息
                self.web_view.setHtml(f"<h2>Error</h2><p>Failed to load page: {str(e)}</p>")
        else:
            # Show fallback message
            fallback_text = f"""
            <h2>{title}</h2>
            <p><strong>URL:</strong> <a href="{url}">{url}</a></p>
            <hr>
            <p>WebEngine is not available. Please click "Open in Browser" to view this page in your default browser.</p>
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
        """停止页面中所有正在播放的媒体内容"""
        if self.web_view:
            try:
                # 执行更全面的JavaScript停止所有媒体播放
                javascript_code = """
                (function() {
                    // 停止所有视频和音频
                    var videos = document.querySelectorAll('video');
                    var audios = document.querySelectorAll('audio');
                    
                    videos.forEach(function(video) {
                        video.pause();
                        video.currentTime = 0;
                        video.muted = true;
                        video.volume = 0;
                        // 移除所有事件监听器
                        video.onplay = null;
                        video.onloadeddata = null;
                        video.oncanplay = null;
                    });
                    
                    audios.forEach(function(audio) {
                        audio.pause();
                        audio.currentTime = 0;
                        audio.muted = true;
                        audio.volume = 0;
                        // 移除所有事件监听器
                        audio.onplay = null;
                        audio.onloadeddata = null;
                        audio.oncanplay = null;
                    });
                    
                    // 停止所有iframe中的媒体
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
                            // 跨域iframe无法访问，忽略错误
                        }
                    });
                    
                    // 阻止新的媒体播放
                    if (!window._originalPlay) {
                        window._originalPlay = HTMLMediaElement.prototype.play;
                    }
                    HTMLMediaElement.prototype.play = function() {
                        console.log('🚫 阻止媒体播放:', this);
                        return Promise.reject(new Error('Media playback blocked'));
                    };
                    
                    console.log('🔇 媒体播放已停止并阻止新的播放');
                })();
                """
                
                self.web_view.page().runJavaScript(javascript_code)
                print("🔇 WikiView: 已执行增强媒体停止脚本")
                
            except Exception as e:
                print(f"⚠️ WikiView: 停止媒体播放失败: {e}")
                
    def pause_page(self):
        """暂停页面活动（包括媒体播放）"""
        # 防止重复调用
        if self._pause_lock:
            print("🔄 WikiView: 暂停操作正在进行中，跳过重复调用")
            return
            
        if self.web_view and not self._is_paused:
            try:
                self._pause_lock = True
                print("🔄 正在暂停WikiView页面...")
                
                # 1. 停止当前网络请求
                try:
                    self.web_view.stop()
                    print("✅ WebView网络请求已停止")
                except Exception as stop_error:
                    print(f"⚠️ WebView停止失败: {stop_error}")
                
                # 2. 停止媒体播放
                try:
                    self.stop_media_playback()
                    print("✅ 媒体播放已停止")
                except Exception as media_error:
                    print(f"⚠️ 媒体停止失败: {media_error}")
                
                # 3. 设置页面为不可见状态，某些网站会自动暂停媒体
                try:
                    self.web_view.page().runJavaScript("""
                    (function() {
                        // 设置页面为不可见状态
                        Object.defineProperty(document, 'hidden', {value: true, writable: false});
                        Object.defineProperty(document, 'visibilityState', {value: 'hidden', writable: false});
                        
                        // 触发可见性变化事件
                        var event = new Event('visibilitychange');
                        document.dispatchEvent(event);
                        
                        // 阻止页面焦点
                        if (document.hasFocus) {
                            document.hasFocus = function() { return false; };
                        }
                        
                        // 设置页面为不可交互状态
                        document.body.style.pointerEvents = 'none';
                        
                        console.log('🔇 页面已设置为不可见状态');
                    })();
                    """)
                    print("✅ 页面可见性状态已设置")
                except Exception as js_error:
                    print(f"⚠️ JavaScript执行失败: {js_error}")
                
                self._is_paused = True
                print("✅ WikiView页面暂停完成")
                
            except Exception as e:
                print(f"⚠️ WikiView: 暂停页面失败: {e}")
            finally:
                self._pause_lock = False
        else:
            print("🔄 WikiView: 页面已经暂停或WebView不可用，跳过暂停操作")
    
    def safe_cleanup(self):
        """安全清理WikiView资源，用于窗口关闭时"""
        try:
            print("🔄 开始WikiView简化清理...")
            
            if self.web_view:
                # 只执行最基本的清理操作，避免复杂的JavaScript或信号操作
                try:
                    # 停止网络活动
                    self.web_view.stop()
                    print("✅ WebView已停止")
                except Exception:
                    # 如果停止失败，继续处理
                    pass
                
                # 不执行复杂的媒体停止、JavaScript执行或信号断开操作
                # 这些可能导致崩溃
            
            print("✅ WikiView简化清理完成")
            
        except Exception as e:
            print(f"❌ WikiView清理失败: {e}")
                
    def resume_page(self):
        """恢复页面活动"""
        if self.web_view and self._is_paused:
            try:
                # 恢复页面可见性状态和交互性
                self.web_view.page().runJavaScript("""
                (function() {
                    // 恢复页面可见性状态
                    Object.defineProperty(document, 'hidden', {value: false, writable: false});
                    Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: false});
                    
                    // 触发可见性变化事件
                    var event = new Event('visibilitychange');
                    document.dispatchEvent(event);
                    
                    // 恢复页面交互性
                    document.body.style.pointerEvents = '';
                    
                    // 恢复媒体播放功能
                    if (window._originalPlay) {
                        HTMLMediaElement.prototype.play = window._originalPlay;
                        delete window._originalPlay;
                    }
                    
                    console.log('▶️ 页面已恢复可见和交互状态');
                })();
                """)
                
                self._is_paused = False
                print("▶️ WikiView: 页面已恢复")
                
            except Exception as e:
                 print(f"⚠️ WikiView: 恢复页面失败: {e}")
        else:
            print("▶️ WikiView: 页面未处于暂停状态，跳过恢复操作")
                 
    def hideEvent(self, event):
        """当WikiView被隐藏时自动暂停媒体播放"""
        # 只有在当前显示Wiki视图时才暂停
        if hasattr(self, 'parent') and self.parent():
            parent = self.parent()
            if hasattr(parent, 'content_stack'):
                current_widget = parent.content_stack.currentWidget()
                if current_widget == self:
                    self.pause_page()
        super().hideEvent(event)
        
    def showEvent(self, event):
        """当WikiView被显示时恢复页面活动"""
        super().showEvent(event)
        # 延迟恢复，确保页面已完全显示
        QTimer.singleShot(100, self.resume_page)


class UnifiedAssistantWindow(QMainWindow):
    """Main unified window with all modes"""
    
    query_submitted = pyqtSignal(str)
    window_closing = pyqtSignal()  # Signal when window is closing
    wiki_page_found = pyqtSignal(str, str)  # 新信号：传递真实wiki页面信息到controller
    visibility_changed = pyqtSignal(bool)  # Signal for visibility state changes
    stop_generation_requested = pyqtSignal()  # 新信号：停止生成请求

    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.current_mode = "wiki"
        self.is_generating = False
        self.streaming_widget = None
        self.current_game_window = None  # 记录当前游戏窗口标题
        self.game_task_buttons = {}  # 存储所有游戏的任务流程按钮
        
        # 初始化历史记录管理器
        from src.game_wiki_tooltip.history_manager import WebHistoryManager
        self.history_manager = WebHistoryManager()
        
        self.init_ui()
        self.restore_geometry()
        
        # 调试：初始化后打印尺寸
        print(f"🏠 UnifiedAssistantWindow初始化完成，尺寸: {self.size()}")
        
    def init_ui(self):
        """Initialize the main window UI"""
        self.setWindowTitle("GameWiki Assistant")
        # Use standard window frame with always-on-top
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
        )
        
        # 确保窗口可以自由调整大小，移除任何尺寸限制
        self.setMinimumSize(300, 200)  # 设置一个合理的最小尺寸
        self.setMaximumSize(16777215, 16777215)  # 移除最大尺寸限制
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Content area (chat/wiki switcher)
        self.content_stack = QStackedWidget()
        # 确保QStackedWidget不会强制改变尺寸
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Chat view
        self.chat_view = ChatView()
        self.chat_view.wiki_requested.connect(self.show_wiki_page)
        # 确保聊天视图保持其尺寸
        self.chat_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # Wiki view
        self.wiki_view = WikiView()
        self.wiki_view.back_requested.connect(self.show_chat_view)  # This will restore input/shortcuts
        self.wiki_view.wiki_page_loaded.connect(self.handle_wiki_page_loaded)
        # 确保Wiki视图有合理的最小尺寸但不强制固定尺寸
        self.wiki_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        self.content_stack.addWidget(self.chat_view)
        self.content_stack.addWidget(self.wiki_view)
        
        # Shortcuts container (above input area)
        self.shortcut_container = QFrame()
        self.shortcut_container.setFixedHeight(35)
        self.shortcut_container.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-bottom: 1px solid #e0e0e0;
            }
        """)
        
        self.shortcut_layout = QHBoxLayout(self.shortcut_container)
        self.shortcut_layout.setContentsMargins(10, 4, 10, 4)
        self.shortcut_layout.setSpacing(8)
        
        # Load shortcuts
        self.load_shortcuts()
        
        # Input area
        self.input_container = QFrame()
        self.input_container.setFixedHeight(60)
        self.input_container.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-top: 1px solid #e0e0e0;
            }
        """)
        
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(10, 10, 10, 10)
        
        # Mode selection button
        self.mode_button = QToolButton()
        self.mode_button.setText("Search info")
        self.mode_button.setFixedSize(160, 45)
        self.mode_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.mode_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.mode_button.setArrowType(Qt.ArrowType.NoArrow)  # We'll use custom arrow
        self.mode_button.setStyleSheet("""
            QToolButton {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 22px;
                padding: 0 15px;
                font-size: 14px;
                font-family: "Microsoft YaHei", "Segoe UI", Arial;
            }
            QToolButton:hover {
                border-color: #4096ff;
            }
            QToolButton::menu-indicator {
                image: none;
                subcontrol-position: right center;
                subcontrol-origin: padding;
                width: 16px;
            }
        """)
        
        # Create menu for mode selection
        mode_menu = QMenu(self.mode_button)
        mode_menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:hover {
                background-color: #f0f0f0;
            }
        """)
        
        # Add mode options
        wiki_action = mode_menu.addAction("Search wiki / guide")
        wiki_action.triggered.connect(lambda: self.set_mode("wiki"))
        
        url_action = mode_menu.addAction("Go to URL")
        url_action.triggered.connect(lambda: self.set_mode("url"))
        
        self.mode_button.setMenu(mode_menu)
        
        # Update button text to include arrow
        self.mode_button.setText("Search info ▼")
        
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
        # Connect Enter key - will be handled based on mode
        self.input_field.returnPressed.connect(self.on_input_return_pressed)
        
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
            QPushButton[stop_mode="true"] {
                background-color: #ff4d4f;
            }
            QPushButton[stop_mode="true"]:hover {
                background-color: #ff7875;
            }
            QPushButton[stop_mode="true"]:pressed {
                background-color: #d32f2f;
            }
        """)
        self.send_button.clicked.connect(self.on_send_clicked)
        
        # History button
        self.history_button = QToolButton()
        self.history_button.setFixedSize(45, 45)
        self.history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_button.setToolTip("View browsing history")
        self.history_button.setStyleSheet("""
            QToolButton {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 22px;
                font-size: 20px;
            }
            QToolButton:hover {
                background-color: #f0f0f0;
                border-color: #4096ff;
            }
            QToolButton:pressed {
                background-color: #e0e0e0;
            }
        """)
        self.history_button.setText("📜")  # History icon
        self.history_button.clicked.connect(self.show_history_menu)
        
        # Current mode
        self.current_mode = "wiki"
        
        input_layout.addWidget(self.mode_button)
        input_layout.addWidget(self.history_button)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        
        # Add to main layout with stretch factor
        main_layout.addWidget(self.content_stack, 1)  # 拉伸因子1，占据所有可用空间
        main_layout.addWidget(self.shortcut_container, 0)  # 快捷按钮栏
        main_layout.addWidget(self.input_container, 0)     # 拉伸因子0，保持固定高度
        
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
        
    def reset_size_constraints(self):
        """重置窗口尺寸约束，确保可以自由调整大小"""
        self.setMinimumSize(300, 200)  # 保持合理的最小尺寸
        self.setMaximumSize(16777215, 16777215)  # 移除最大尺寸限制
        
    def apply_shadow(self):
        """Apply shadow effect to window"""
        # This would require platform-specific implementation
        # For now, using basic window flags
        pass
        
    def restore_geometry(self):
        """Restore window geometry from settings with enhanced screen compatibility"""
        if self.settings_manager:
            try:
                scale = _get_scale()  # 获取DPI缩放因子
                settings = self.settings_manager.get()
                popup_dict = settings.get('popup', {})
                
                # 使用availableGeometry获取可用屏幕区域（排除任务栏等）
                screen = QApplication.primaryScreen().availableGeometry()
                
                # 检查是否为首次使用或配置不完整
                is_first_use = not popup_dict or len(popup_dict) < 4
                
                if is_first_use:
                    # 首次使用，创建智能默认配置
                    popup_config = PopupConfig.create_smart_default(screen)
                    print(f"📍 首次使用，创建智能默认窗口配置")
                else:
                    # 从设置创建PopupConfig实例
                    popup_config = PopupConfig(**popup_dict)
                
                # 获取绝对坐标（已包含屏幕适配和边界检查）
                phys_x, phys_y, phys_w, phys_h = popup_config.get_absolute_geometry(screen)
                
                # 应用DPI缩放
                if scale != 1.0:
                    # 如果使用相对坐标，不需要额外的DPI缩放（已在get_absolute_geometry中处理）
                    if not popup_config.use_relative_position:
                        phys_x = int(phys_x * scale)
                        phys_y = int(phys_y * scale)
                    if not popup_config.use_relative_size:
                        phys_w = int(phys_w * scale)
                        phys_h = int(phys_h * scale)
                
                # 最终边界检查（考虑DPI缩放后的值）
                phys_x, phys_y, phys_w, phys_h = self._final_geometry_check(
                    phys_x, phys_y, phys_w, phys_h, screen
                )
                
                self.setGeometry(phys_x, phys_y, phys_w, phys_h)
                
                # 记录详细的窗口恢复信息
                screen_info = f"{screen.width()}x{screen.height()}"
                position_type = "相对坐标" if popup_config.use_relative_position else "绝对坐标"
                size_type = "相对尺寸" if popup_config.use_relative_size else "固定尺寸"
                
                logging.info(f"恢复窗口几何: 位置({phys_x},{phys_y}) 尺寸({phys_w}x{phys_h}) "
                           f"屏幕({screen_info}) DPI缩放({scale:.2f}) "
                           f"配置({position_type}+{size_type})")
                
                # 恢复几何后重置尺寸约束，确保可以自由调整大小
                self.reset_size_constraints()
                
                # 如果是首次使用且创建了智能默认配置，保存到设置中
                if is_first_use:
                    self._save_initial_geometry_config(popup_config)
                
            except Exception as e:
                logging.error(f"恢复窗口几何信息失败: {e}")
                # 失败时使用安全的默认值
                self._apply_safe_default_geometry()
        else:
            self._apply_safe_default_geometry()
    
    def _final_geometry_check(self, x, y, width, height, screen):
        """
        最终的几何检查，确保窗口完全可见且可操作
        
        Args:
            x, y, width, height: 窗口几何参数
            screen: 屏幕可用区域
            
        Returns:
            tuple: 调整后的(x, y, width, height)
        """
        # 确保最小尺寸
        min_width, min_height = 300, 200
        width = max(min_width, width)
        height = max(min_height, height)
        
        # 确保最大尺寸不超过屏幕
        max_width = screen.width() - 20
        max_height = screen.height() - 40
        width = min(width, max_width)
        height = min(height, max_height)
        
        # 确保位置在可见范围内
        margin = 10
        max_x = screen.x() + screen.width() - width - margin
        max_y = screen.y() + screen.height() - height - margin
        min_x = screen.x() + margin
        min_y = screen.y() + margin
        
        x = max(min_x, min(x, max_x))
        y = max(min_y, min(y, max_y))
        
        return x, y, width, height
    
    def _apply_safe_default_geometry(self):
        """应用安全的默认几何配置"""
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            # 使用屏幕中心偏右的安全位置
            safe_width = min(600, screen.width() - 100)
            safe_height = min(500, screen.height() - 100)
            safe_x = screen.x() + (screen.width() - safe_width) // 2 + 50
            safe_y = screen.y() + (screen.height() - safe_height) // 4
            
            self.setGeometry(safe_x, safe_y, safe_width, safe_height)
            logging.info(f"应用安全默认几何: ({safe_x},{safe_y},{safe_width},{safe_height})")
        except Exception as e:
            # 最后的兜底方案
            logging.error(f"应用安全默认几何失败: {e}")
            self.setGeometry(100, 100, 600, 500)
        
        self.reset_size_constraints()
    
    def _save_initial_geometry_config(self, popup_config):
        """
        保存初始几何配置到设置文件
        
        Args:
            popup_config: PopupConfig实例
        """
        try:
            from dataclasses import asdict
            popup_dict = asdict(popup_config)
            self.settings_manager.update({'popup': popup_dict})
            logging.info("已保存智能默认窗口配置到设置文件")
        except Exception as e:
            logging.warning(f"保存初始几何配置失败: {e}")
    
    def save_geometry(self):
        """Save window geometry to settings with enhanced format support"""
        if self.settings_manager:
            try:
                scale = _get_scale()  # 获取DPI缩放因子
                geo = self.geometry()
                screen = QApplication.primaryScreen().availableGeometry()
                
                # 获取当前设置以保持配置一致性
                current_settings = self.settings_manager.get()
                current_popup = current_settings.get('popup', {})
                
                # 检查当前配置是否使用相对坐标
                use_relative_position = current_popup.get('use_relative_position', False)
                use_relative_size = current_popup.get('use_relative_size', False)
                
                if use_relative_position:
                    # 保存为相对坐标（0.0-1.0）
                    left_percent = (geo.x() - screen.x()) / screen.width() if screen.width() > 0 else 0.5
                    top_percent = (geo.y() - screen.y()) / screen.height() if screen.height() > 0 else 0.1
                    
                    # 确保相对坐标在合理范围内
                    left_percent = max(0.0, min(1.0, left_percent))
                    top_percent = max(0.0, min(1.0, top_percent))
                else:
                    # 保存为绝对坐标（逻辑像素）
                    left_percent = current_popup.get('left_percent', 0.6)
                    top_percent = current_popup.get('top_percent', 0.1)
                
                if use_relative_size:
                    # 保存为相对尺寸
                    width_percent = geo.width() / screen.width() if screen.width() > 0 else 0.4
                    height_percent = geo.height() / screen.height() if screen.height() > 0 else 0.7
                    
                    # 确保相对尺寸在合理范围内
                    width_percent = max(0.2, min(0.9, width_percent))
                    height_percent = max(0.3, min(0.9, height_percent))
                else:
                    # 保存为固定尺寸
                    width_percent = current_popup.get('width_percent', 0.4)
                    height_percent = current_popup.get('height_percent', 0.7)
                
                # 转换为逻辑像素坐标（用于向后兼容）
                css_x = int(geo.x() / scale) if scale != 1.0 else geo.x()
                css_y = int(geo.y() / scale) if scale != 1.0 else geo.y()
                css_w = int(geo.width() / scale) if scale != 1.0 else geo.width()
                css_h = int(geo.height() / scale) if scale != 1.0 else geo.height()
                
                # 构建完整的popup配置
                popup_config = {
                    # 传统固定坐标（向后兼容）
                    'left': css_x,
                    'top': css_y,
                    'width': css_w,
                    'height': css_h,
                    # 新的相对坐标系统
                    'use_relative_position': use_relative_position,
                    'left_percent': left_percent,
                    'top_percent': top_percent,
                    'width_percent': width_percent,
                    'height_percent': height_percent,
                    'use_relative_size': use_relative_size,
                }
                
                # 更新配置
                self.settings_manager.update({'popup': popup_config})
                
                # 记录保存信息
                pos_type = "相对" if use_relative_position else "绝对"
                size_type = "相对" if use_relative_size else "固定"
                logging.info(f"保存窗口几何: {pos_type}位置({css_x},{css_y}|{left_percent:.2f},{top_percent:.2f}) "
                           f"{size_type}尺寸({css_w}x{css_h}|{width_percent:.2f}x{height_percent:.2f}) "
                           f"DPI缩放({scale:.2f})")
                
            except Exception as e:
                logging.error(f"保存窗口几何信息失败: {e}")
                # 兜底保存基本信息
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
                    logging.warning("使用基本格式保存窗口几何信息")
                except Exception as fallback_error:
                    logging.error(f"基本格式保存也失败: {fallback_error}")
    
    def show_chat_view(self):
        """Switch to chat view"""
        # 首先停止WikiView中的媒体播放（只有在当前显示Wiki视图时才暂停）
        if hasattr(self, 'wiki_view') and self.wiki_view:
            current_widget = self.content_stack.currentWidget()
            if current_widget == self.wiki_view:
                self.wiki_view.pause_page()
            
        self.content_stack.setCurrentWidget(self.chat_view)
        # Show input area and shortcuts in chat mode
        if hasattr(self, 'input_container'):
            self.input_container.show()
        if hasattr(self, 'shortcut_container'):
            self.shortcut_container.show()
        # 切换到聊天视图时重置尺寸约束
        self.reset_size_constraints()
        # 确保消息宽度正确并触发完整的布局更新
        QTimer.singleShot(50, self.chat_view.update_all_message_widths)
        # 延迟执行完整的布局更新，确保内容完整显示
        QTimer.singleShot(100, self.chat_view._performDelayedResize)
        
    def show_wiki_page(self, url: str, title: str):
        """Switch to wiki view and load page"""
        logger = logging.getLogger(__name__)
        logger.info(f"🌐 UnifiedAssistantWindow.show_wiki_page 被调用: URL={url}, Title={title}")
        
        # Add to history (skip local files and if already added from open_url)
        if hasattr(self, 'history_manager') and not url.startswith('file://'):
            # Determine source type
            if "wiki" in url.lower() or "wiki" in title.lower():
                source = "wiki"
            else:
                source = "web"
            self.history_manager.add_entry(url, title, source=source)
        
        self.wiki_view.load_wiki(url, title)
        self.content_stack.setCurrentWidget(self.wiki_view)
        
        # 恢复WikiView的页面活动（如果之前被暂停）
        self.wiki_view.resume_page()
        
        # Hide input area and shortcuts in wiki mode
        if hasattr(self, 'input_container'):
            self.input_container.hide()
        if hasattr(self, 'shortcut_container'):
            self.shortcut_container.hide()
        # 切换到Wiki视图时也重置尺寸约束
        self.reset_size_constraints()
        logger.info(f"✅ 已切换到Wiki视图并加载页面")
        
    def handle_wiki_page_loaded(self, url: str, title: str):
        """处理Wiki页面加载完成信号，将信号转发给controller"""
        print(f"🌐 UnifiedAssistantWindow: Wiki页面加载完成 - {title}: {url}")
        # 发出信号给controller处理
        self.wiki_page_found.emit(url, title)
        
    def set_mode(self, mode: str):
        """Set the input mode (wiki or url)"""
        self.current_mode = mode
        if mode == "url":
            self.mode_button.setText("Go to URL ▼")
            self.input_field.setPlaceholderText("Enter URL...")
            self.send_button.setText("Open")
            # Disconnect and reconnect send button
            try:
                self.send_button.clicked.disconnect()
            except:
                pass
            self.send_button.clicked.connect(self.on_open_url_clicked)
        else:
            self.mode_button.setText("Search info ▼")
            self.input_field.setPlaceholderText("Enter message...")
            self.send_button.setText("Send")
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
        # Extract domain as title
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            title = parsed.netloc or url
        except:
            title = url
            
        # Add to history
        if hasattr(self, 'history_manager'):
            self.history_manager.add_entry(url, title, source="web")
            
        # Switch to wiki view and load URL
        self.show_wiki_page(url, title)
    
    def load_shortcuts(self):
        """Load shortcut buttons from settings"""
        try:
            # Clear existing buttons
            while self.shortcut_layout.count() > 0:
                item = self.shortcut_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            # Get shortcuts from settings
            shortcuts = []
            if self.settings_manager:
                try:
                    shortcuts = self.settings_manager.get('shortcuts', [])
                except Exception as e:
                    print(f"Failed to get shortcuts from settings: {e}")
                    
            
            # Filter out hidden shortcuts
            visible_shortcuts = [s for s in shortcuts if s.get('visible', True)]
            
            # Hide container if no visible shortcuts
            if not visible_shortcuts:
                self.shortcut_container.hide()
                return
            
            self.shortcut_container.show()
            
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
                    self.shortcut_layout.addWidget(btn)
                except Exception as e:
                    print(f"Failed to create shortcut button: {e}")
            
            # Add DST task flow button (conditionally visible)
            self._create_dst_task_button()
            
            # Add stretch at the end
            self.shortcut_layout.addStretch()
        except Exception as e:
            print(f"Error in load_shortcuts: {e}")
            # Hide the container if there's an error
            self.shortcut_container.hide()
    
    def _create_dst_task_button(self):
        """创建游戏任务流程按钮（兼容旧代码）"""
        self._create_game_task_buttons()
    
    def _create_game_task_buttons(self):
        """创建所有游戏的任务流程按钮"""
        # 定义支持任务流程的游戏
        game_configs = [
            {
                'game_name': 'dst',
                'display_name': t('dst_task_button'),
                'window_titles': ["don't starve together", "dst"],
                'html_files': {'en': 'dst_en.html', 'zh': 'dst_zh.html'},
                'button_color': '#4CAF50'
            },
            {
                'game_name': 'civilization6',
                'display_name': t('civ6_task_button') if hasattr(self, '_t') and callable(getattr(self, '_t', None)) else 'Civilization VI Guide',
                'window_titles': ["sid meier's civilization vi", "civilization vi", "civ6", "civ 6"],
                'html_files': {'en': 'civilization6_en.html', 'zh': 'civilization6_zh.html'},
                'button_color': '#FFB300'
            }
        ]
        
        # 清除现有按钮
        for btn in self.game_task_buttons.values():
            if btn:
                self.shortcut_layout.removeWidget(btn)
                btn.deleteLater()
        self.game_task_buttons.clear()
        
        # 创建新按钮
        for config in game_configs:
            try:
                button = self._create_single_game_button(config)
                if button:
                    self.game_task_buttons[config['game_name']] = button
                    self.shortcut_layout.addWidget(button)
                    button.hide()  # 初始时隐藏
            except Exception as e:
                print(f"Failed to create task button for {config['game_name']}: {e}")
    
    def _create_single_game_button(self, config):
        """创建单个游戏的任务流程按钮"""
        button = QPushButton(config['display_name'])
        button.setFixedHeight(27)
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {config['button_color']};
                color: white;
                border: none;
                border-radius: 13px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: bold;
                font-family: "Microsoft YaHei", "Segoe UI", Arial;
            }}
            QPushButton:hover {{
                background-color: {self._darken_color(config['button_color'], 0.1)};
            }}
            QPushButton:pressed {{
                background-color: {self._darken_color(config['button_color'], 0.2)};
            }}
        """)
        
        # 连接点击事件
        button.clicked.connect(lambda: self._open_game_task_flow(config))
        return button
    
    def _darken_color(self, hex_color, factor):
        """使颜色变暗的辅助函数"""
        # 移除 # 号
        hex_color = hex_color.lstrip('#')
        # 转换为 RGB
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # 变暗
        r = int(r * (1 - factor))
        g = int(g * (1 - factor))
        b = int(b * (1 - factor))
        # 转换回十六进制
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def _open_game_task_flow(self, config):
        """打开游戏任务流程HTML文件"""
        try:
            # 获取当前语言设置
            current_language = 'en'
            if self.settings_manager:
                settings = self.settings_manager.get()
                current_language = settings.get('language', 'en')
            
            # 根据语言选择对应的HTML文件
            html_filename = config['html_files'].get(current_language, config['html_files']['en'])
            
            # 获取HTML文件路径
            import pathlib
            base_path = pathlib.Path(__file__).parent
            html_path = base_path / "assets" / "html" / html_filename
            
            if html_path.exists():
                print(f"Loading DST task flow from: {html_path}")
                
                # 直接在应用内显示，与wiki链接逻辑一致
                try:
                    title = t("dst_task_flow_title")
                    
                    # 使用与其他wiki链接相同的显示逻辑
                    self._load_local_html_in_wiki_view(html_path, title)
                    
                except Exception as html_error:
                    print(f"Failed to load HTML content: {html_error}")
                    self._show_simple_dst_info(current_language)
            else:
                print(f"DST task flow file not found: {html_path}")
                self._show_simple_dst_info(current_language)
                
        except Exception as e:
            print(f"Failed to open DST task flow: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_local_html_in_wiki_view(self, html_path: pathlib.Path, title: str):
        """使用与其他wiki链接相同的逻辑加载本地HTML文件"""
        try:
            # 创建file:// URL，这与正常wiki链接的处理方式一致
            file_url = html_path.as_uri()
            print(f"Loading local HTML with file URL: {file_url}")
            
            # 使用标准的show_wiki_page方法，确保与其他wiki链接的行为一致
            self.show_wiki_page(file_url, title)
            
        except Exception as e:
            print(f"Failed to load local HTML in wiki view: {e}")
            # 降级到简化显示
            self._show_simple_dst_info('zh' if '任务流程' in title else 'en')
    
    def _show_simple_dst_info(self, language: str):
        """显示简化的DST信息作为降级方案"""
        try:
            title = t("dst_task_flow_title")
            # 根据当前语言决定Wiki链接
            wiki_url = "https://dontstarve.fandom.com/zh/wiki/" if language == 'zh' else "https://dontstarve.fandom.com/wiki/"
            
            content = f"""
            <h1>{t("dst_survival_guide_title")}</h1>
            <p>{t("dst_technical_error")}</p>
            <p>{t("dst_recommended_resources")}</p>
            <ul>
                <li><a href="{wiki_url}">{t("dst_official_wiki")}</a></li>
                <li>{t("dst_basic_survival")}</li>
                <li>{t("dst_food_gathering")}</li>
                <li>{t("dst_base_building")}</li>
                <li>{t("dst_winter_preparation")}</li>
            </ul>
            """
            
            # 直接使用简单的HTML显示
            self._show_simple_content(content, title)
            
        except Exception as e:
            print(f"Failed to show simple DST info: {e}")
    
    def _show_simple_content(self, content: str, title: str):
        """显示简单内容的安全方法"""
        try:
            # 切换到Wiki视图
            self.content_stack.setCurrentWidget(self.wiki_view)
            self.shortcut_container.hide()
            self.input_container.hide()
            
            # 设置标题
            self.wiki_view.title_label.setText(title)
            self.wiki_view.current_title = title
            self.wiki_view.current_url = "local://simple_content.html"
            
            # 创建完整的HTML
            full_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{title}</title>
                <style>
                    body {{
                        font-family: "Microsoft YaHei", "Segoe UI", Arial;
                        margin: 20px;
                        line-height: 1.6;
                        background-color: #f5f5f5;
                    }}
                    .container {{
                        background-color: white;
                        padding: 30px;
                        border-radius: 8px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        max-width: 800px;
                        margin: 0 auto;
                    }}
                    h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                    a {{ color: #3498db; text-decoration: none; }}
                    a:hover {{ text-decoration: underline; }}
                    ul {{ padding-left: 20px; }}
                    li {{ margin: 8px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    {content}
                </div>
            </body>
            </html>
            """
            
            # 只使用文本视图显示，避免WebEngine的问题
            if hasattr(self.wiki_view, 'content_widget') and self.wiki_view.content_widget:
                self.wiki_view.content_widget.setHtml(full_html)
                print("✅ Simple content loaded in text view")
            else:
                print("❌ No content widget available for simple content")
                
        except Exception as e:
            print(f"Failed to show simple content: {e}")
            # 最终降级：只更新标题
            try:
                self.wiki_view.title_label.setText(f"错误: 无法显示内容")
            except:
                pass
    
    def _show_html_content(self, html_content: str, title: str):
        """直接显示HTML内容到WikiView"""
        try:
            # 切换到Wiki视图
            self.content_stack.setCurrentWidget(self.wiki_view)
            self.shortcut_container.hide()
            self.input_container.hide()
            
            # 设置标题
            self.wiki_view.title_label.setText(title)
            self.wiki_view.current_title = title
            self.wiki_view.current_url = "local://dst_task_flow.html"
            
            # 先检查WebEngine是否可用并已创建
            if (WEBENGINE_AVAILABLE and 
                hasattr(self.wiki_view, 'web_view') and 
                self.wiki_view.web_view is not None):
                try:
                    # 使用QWebEngineView的setHtml方法来显示HTML内容
                    base_url = QUrl.fromLocalFile(str(pathlib.Path(__file__).parent / "assets" / "html" / ""))
                    self.wiki_view.web_view.setHtml(html_content, base_url)
                    print("✅ HTML content loaded in WebEngine")
                    return
                except Exception as web_error:
                    print(f"⚠️ WebEngine loading failed: {web_error}")
                    # 继续到降级方案
            
            # 降级到文本视图 - 这个应该总是可用的
            if hasattr(self.wiki_view, 'content_widget') and self.wiki_view.content_widget:
                try:
                    self.wiki_view.content_widget.setHtml(html_content)
                    print("✅ HTML content loaded in text view")
                    return
                except Exception as text_error:
                    print(f"⚠️ Text view loading failed: {text_error}")
            
            # 如果都失败了，显示错误信息
            print("❌ No content widget available")
            self._show_error_message(title, "无法找到可用的显示组件")
                    
        except Exception as e:
            print(f"Failed to show HTML content: {e}")
            import traceback
            traceback.print_exc()
            self._show_error_message(title, str(e))
    
    def _show_error_message(self, title: str, error_msg: str):
        """显示错误信息的安全方法"""
        try:
            error_html = f"""
            <html>
            <head>
                <title>Error</title>
                <style>
                    body {{ 
                        font-family: "Microsoft YaHei", "Segoe UI", Arial; 
                        margin: 20px; 
                        background-color: #f5f5f5;
                    }}
                    .error-container {{ 
                        background-color: white; 
                        padding: 20px; 
                        border-radius: 8px; 
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    h2 {{ color: #d32f2f; }}
                    .error-msg {{ 
                        background-color: #ffebee; 
                        padding: 10px; 
                        border-left: 4px solid #d32f2f; 
                        margin: 10px 0;
                    }}
                </style>
            </head>
            <body>
                <div class="error-container">
                    <h2>无法显示 {title}</h2>
                    <div class="error-msg">
                        <strong>错误信息:</strong> {error_msg}
                    </div>
                    <p>建议解决方案：</p>
                    <ul>
                        <li>确保HTML文件存在且格式正确</li>
                        <li>重新启动应用程序</li>
                        <li>检查WebEngine组件是否正常安装</li>
                    </ul>
                </div>
            </body>
            </html>
            """
            
            # 尝试在任何可用的组件中显示错误信息
            if (hasattr(self.wiki_view, 'web_view') and 
                self.wiki_view.web_view is not None):
                self.wiki_view.web_view.setHtml(error_html)
            elif (hasattr(self.wiki_view, 'content_widget') and 
                  self.wiki_view.content_widget):
                self.wiki_view.content_widget.setHtml(error_html)
            else:
                # 最后的降级方案：在标题中显示错误
                self.wiki_view.title_label.setText(f"错误: {error_msg}")
                
        except Exception as final_error:
            print(f"连错误信息都无法显示: {final_error}")
            # 最终降级：只更新标题
            try:
                self.wiki_view.title_label.setText("加载失败")
            except:
                pass
    
    def show_history_menu(self):
        """Show history menu"""
        if not hasattr(self, 'history_manager'):
            return
            
        history_menu = QMenu(self)
        history_menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 4px;
                min-width: 350px;
            }
            QMenu::item {
                padding: 8px 12px;
                border-radius: 4px;
            }
            QMenu::item:hover {
                background-color: #f0f0f0;
            }
            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 4px 0;
            }
        """)
        
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
        
        # Show menu below the button
        history_menu.exec(self.history_button.mapToGlobal(QPoint(0, self.history_button.height())))
    
    def clear_history(self):
        """Clear browsing history"""
        if hasattr(self, 'history_manager'):
            self.history_manager.clear_history()
            # Show notification
            QTimer.singleShot(100, lambda: self.history_button.setToolTip("History cleared"))
            QTimer.singleShot(2000, lambda: self.history_button.setToolTip("View browsing history"))
    
    def set_current_game_window(self, game_window_title: str):
        """设置当前游戏窗口标题并更新DST按钮可见性"""
        self.current_game_window = game_window_title
        self._update_dst_button_visibility()
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🎮 记录游戏窗口: '{game_window_title}'")
    
    def _update_dst_button_visibility(self):
        """更新游戏任务按钮的可见性"""
        self._update_game_task_buttons_visibility()
    
    def _update_game_task_buttons_visibility(self):
        """根据当前游戏窗口更新所有游戏任务按钮的可见性"""
        try:
            if not self.current_game_window:
                # 隐藏所有按钮
                for button in self.game_task_buttons.values():
                    if button:
                        button.hide()
                return
            
            game_title_lower = self.current_game_window.lower()
            
            # 定义游戏配置（与创建按钮时一致）
            game_configs = [
                {
                    'game_name': 'dst',
                    'window_titles': ["don't starve together", "dst"]
                },
                {
                    'game_name': 'civilization6',
                    'window_titles': ["sid meier's civilization vi", "civilization vi", "civ6", "civ 6"]
                }
            ]
            
            # 检查每个游戏
            for config in game_configs:
                button = self.game_task_buttons.get(config['game_name'])
                if button:
                    # 检查当前窗口是否匹配该游戏
                    is_matched = any(title in game_title_lower for title in config['window_titles'])
                    
                    if is_matched:
                        button.show()
                        print(f"{config['game_name']} task button shown for game: {self.current_game_window}")
                    else:
                        button.hide()
                    
        except Exception as e:
            print(f"Failed to update game task buttons visibility: {e}")

    def on_send_clicked(self):
        """Handle send button click"""
        if self.is_generating:
            # 如果正在生成，停止生成
            self.stop_generation()
        else:
            # 正常发送
            text = self.input_field.text().strip()
            if text:
                # 检查是否需要停止当前的生成（如果有的话）
                if self.is_generating:
                    self.stop_generation()
                    
                self.input_field.clear()
                self.query_submitted.emit(text)
    
    def set_generating_state(self, is_generating: bool, streaming_msg=None):
        """设置生成状态"""
        self.is_generating = is_generating
        self.streaming_widget = streaming_msg
        
        if is_generating:
            # 切换到停止模式
            self.send_button.setText("Stop")
            self.send_button.setProperty("stop_mode", "true")
            self.input_field.setPlaceholderText("Click Stop to cancel generation...")
            self.input_field.setEnabled(False)  # 禁用输入框
        else:
            # 切换回发送模式
            if self.current_mode == "url":
                self.send_button.setText("Open")
            else:
                self.send_button.setText("Send")
            self.send_button.setProperty("stop_mode", "false")
            self.input_field.setPlaceholderText("Enter message..." if self.current_mode != "url" else "Enter URL...")
            self.input_field.setEnabled(True)  # 启用输入框
            
        # 刷新样式
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)
        self.send_button.update()
    
    def stop_generation(self):
        """停止当前的生成"""
        print("🛑 用户请求停止生成")
        
        try:
            # 首先恢复UI状态，避免用户看到卡死的状态
            self.set_generating_state(False)
            print("✅ UI状态已恢复")
            
            # 隐藏状态信息
            try:
                self.chat_view.hide_status()
                print("✅ 状态信息已隐藏")
            except Exception as e:
                print(f"⚠️ 隐藏状态信息时出错: {e}")
            
            # 如果有当前的流式消息，标记为已停止
            if self.streaming_widget:
                try:
                    self.streaming_widget.mark_as_stopped()
                    print("✅ 流式消息已标记为停止")
                except Exception as e:
                    print(f"⚠️ 标记流式消息停止时出错: {e}")
            
            # 最后发出停止信号，使用QTimer.singleShot来避免直接信号可能的死锁
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._emit_stop_signal_safe())
            print("✅ 停止信号已安排发送")
            
        except Exception as e:
            print(f"❌ 停止生成过程中出错: {e}")
            # 即使出错也要尝试恢复UI状态
            try:
                self.set_generating_state(False)
            except:
                pass
                
    def _emit_stop_signal_safe(self):
        """安全地发出停止信号"""
        try:
            self.stop_generation_requested.emit()
            print("✅ 停止信号已发送")
        except Exception as e:
            print(f"⚠️ 发送停止信号时出错: {e}")
    
    def contextMenuEvent(self, event):
        """处理右键菜单事件"""
        menu = QMenu(self)
        
        # 最小化到迷你窗口
        minimize_action = menu.addAction(t("menu_minimize_to_mini"))
        minimize_action.triggered.connect(lambda: self.window_closing.emit())
        
        # 隐藏到托盘
        hide_action = menu.addAction(t("menu_hide_to_tray"))
        hide_action.triggered.connect(self._on_hide_to_tray)
        
        menu.exec(event.globalPos())
        
    def _on_hide_to_tray(self):
        """Handle hide to tray request"""
        self.hide()
        self.visibility_changed.emit(False)
        
    def closeEvent(self, event):
        """Handle close event - just hide the window"""
        event.ignore()  # Don't actually close the window
        self.hide()  # Just hide it
        
        # 保存几何信息
        try:
            self.save_geometry()
        except Exception:
            pass
            
        # 通知控制器窗口已关闭
        self.window_closing.emit()
        
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
        self.current_game_window = None  # 记录当前游戏窗口标题
        self._is_manually_hidden = False  # 记录用户是否主动隐藏了悬浮窗
        self._was_hidden_before_hotkey = False  # 记录热键触发前的隐藏状态
        
    def show_mini(self):
        """Show mini assistant"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("show_mini() called")
        
        # 检查是否需要恢复之前的隐藏状态
        if hasattr(self, '_was_hidden_before_hotkey') and self._was_hidden_before_hotkey:
            logger.info("Restoring hidden state from before hotkey")
            self._is_manually_hidden = True
            self._was_hidden_before_hotkey = False  # 重置标志
        
        # 如果用户主动隐藏了悬浮窗，则不显示
        if self._is_manually_hidden:
            logger.info("Mini window was manually hidden, skipping show")
            # 如果有主窗口，也要隐藏它
            if self.main_window:
                logger.info("Hiding main window")
                self.main_window.hide()
            return
        
        if not self.mini_window:
            logger.info("Creating new MiniAssistant window")
            self.mini_window = MiniAssistant()
            self.mini_window.clicked.connect(self.expand_to_chat)
            self.mini_window.visibility_changed.connect(self._on_mini_window_visibility_changed)
            logger.info("MiniAssistant created and signal connected")
        
        # 显示mini窗口
        logger.info("Showing mini window")
        self.mini_window.show()
        self.mini_window.raise_()
        self.mini_window.activateWindow()
        
        # 如果有主窗口，隐藏它
        if self.main_window:
            logger.info("Hiding main window")
            self.main_window.hide()
        
        self.current_mode = WindowMode.MINI
        logger.info("show_mini() completed")
        
    def set_current_game_window(self, game_window_title: str):
        """设置当前游戏窗口标题"""
        self.current_game_window = game_window_title
        
        # 将游戏窗口信息传递给主窗口
        if self.main_window:
            self.main_window.set_current_game_window(game_window_title)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🎮 记录游戏窗口: '{game_window_title}'")
        
    def expand_to_chat(self):
        """Expand from mini to chat window with animation"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("expand_to_chat() called")
        
        # 记录热键触发前的隐藏状态
        self._was_hidden_before_hotkey = self._is_manually_hidden
        logger.info(f"Recording hidden state before hotkey: {self._was_hidden_before_hotkey}")
        
        # 用户主动展开窗口，清除手动隐藏标志
        self._is_manually_hidden = False
        
        # 检查窗口是否已创建但被隐藏
        if not self.main_window:
            logger.info("Creating new UnifiedAssistantWindow")
            self.main_window = UnifiedAssistantWindow(self.settings_manager)
            self.main_window.query_submitted.connect(self.handle_query)
            # 窗口关闭时回到mini模式
            self.main_window.window_closing.connect(self.show_mini)
            self.main_window.wiki_page_found.connect(self.handle_wiki_page_found)
            self.main_window.visibility_changed.connect(self._on_main_window_visibility_changed)
            
            # 如果有当前游戏窗口信息，传递给新窗口
            if self.current_game_window:
                self.main_window.set_current_game_window(self.current_game_window)
            
            logger.info("UnifiedAssistantWindow created and signals connected")
        else:
            logger.info("Reusing existing UnifiedAssistantWindow")
            # 如果游戏窗口改变了，更新它
            if self.current_game_window:
                self.main_window.set_current_game_window(self.current_game_window)
        
        # 设置窗口初始透明度为0（准备渐显动画）
        self.main_window.setWindowOpacity(0.0)
        
        # 确保窗口显示并获得焦点
        logger.info("Showing main window with fade-in animation")
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        
        # 创建渐显动画
        self._fade_in_animation = QPropertyAnimation(self.main_window, b"windowOpacity")
        self._fade_in_animation.setDuration(200)  # 200ms的渐显动画
        self._fade_in_animation.setStartValue(0.0)
        self._fade_in_animation.setEndValue(1.0)
        self._fade_in_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # 动画完成后聚焦到输入框并更新消息宽度
        def on_fade_in_finished():
            logger.info("Fade-in animation completed")
            # 更新所有消息宽度
            if hasattr(self.main_window, 'chat_view'):
                self.main_window.chat_view.update_all_message_widths()
            # 聚焦输入框
            if hasattr(self.main_window, 'query_input'):
                self.main_window.query_input.setFocus()
                
        self._fade_in_animation.finished.connect(on_fade_in_finished)
        self._fade_in_animation.start()
        
        if self.mini_window:
            logger.info("Mini window exists, hiding it")
            # 隐藏mini窗口
            self.mini_window.hide()
            
            # 直接恢复主窗口到之前保存的位置和大小
            self.main_window.restore_geometry()
            
            # 确保窗口在屏幕范围内
            screen = QApplication.primaryScreen().geometry()
            window_rect = self.main_window.geometry()
            
            # 调整位置确保窗口可见
            x = max(10, min(window_rect.x(), screen.width() - window_rect.width() - 10))
            y = max(30, min(window_rect.y(), screen.height() - window_rect.height() - 40))
            
            if x != window_rect.x() or y != window_rect.y():
                self.main_window.move(x, y)
                logger.info(f"Adjusted window position to ensure visibility: ({x}, {y})")
            
            # 消息宽度更新和输入框焦点设置将在动画完成后进行
            
            logger.info("Window position adjusted, fade-in animation in progress")
        else:
            logger.info("No mini window, showing main window with fade-in animation")
            # 使用restore_geometry恢复上次的窗口位置和大小
            self.main_window.restore_geometry()
            
            # 窗口动画效果播放期间不需要更新消息宽度（动画结束后会更新）
            
        self.current_mode = WindowMode.CHAT
        
        # 动画结束后会自动聚焦输入框，这里不需要额外处理
        
        logger.info("expand_to_chat() completed")
        
    def handle_wiki_page_found(self, url: str, title: str):
        """处理找到真实wiki页面的信号（基础实现，子类可重写）"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔗 AssistantController收到wiki页面信号: {title} -> {url}")
        # 基础实现：什么都不做，子类（IntegratedAssistantController）会重写此方法
    
    def refresh_shortcuts(self):
        """刷新快捷按钮栏"""
        if self.main_window:
            self.main_window.load_shortcuts()
        
    def handle_query(self, query: str):
        """Handle user query"""
        # Add user message to chat
        self.main_window.chat_view.add_message(
            MessageType.USER_QUERY,
            query
        )
        
        # 重置自动滚动状态，确保新查询时启用自动滚动
        self.main_window.chat_view.reset_auto_scroll()
        
        # Show initial processing status
        self.main_window.chat_view.show_status(TransitionMessages.QUERY_RECEIVED)
        
        # TODO: Implement actual query processing
        # For now, just show a trial_proto response with shorter delay
        QTimer.singleShot(500, lambda: self.demo_response(query))
        
    def demo_response(self, query: str):
        """Demo response for testing"""
        if "wiki" in query.lower():
            # Simulate wiki response with status updates
            self.simulate_wiki_process()
        else:
            # Simulate guide response with detailed status flow
            self.simulate_guide_process(query)
            
    def simulate_wiki_process(self):
        """模拟Wiki搜索流程"""
        chat_view = self.main_window.chat_view
        
        # Wiki搜索流程简化，总时间1.5秒
        QTimer.singleShot(300, lambda: chat_view.update_status(TransitionMessages.WIKI_SEARCHING))
        QTimer.singleShot(1500, lambda: self.show_wiki_result())
        
    def simulate_guide_process(self, query: str):
        """模拟完整的攻略查询流程"""
        chat_view = self.main_window.chat_view
        
        # 简化状态切换序列（只保留2-3个关键状态）
        status_updates = [
            (0, TransitionMessages.DB_SEARCHING),      # 检索阶段
            (1500, TransitionMessages.AI_SUMMARIZING), # AI处理阶段
        ]
        
        # 依次设置状态更新
        def create_status_updater(status_msg):
            def updater():
                print(f"[STATUS] 更新状态: {status_msg}")
                chat_view.update_status(status_msg)
            return updater
        
        for delay, status in status_updates:
            QTimer.singleShot(delay, create_status_updater(status))
        
        # 缩短总时间到3秒
        QTimer.singleShot(3000, lambda: self.show_guide_result())
            
    def show_wiki_result(self):
        """Show wiki search result"""
        # 隐藏状态信息
        self.main_window.chat_view.hide_status()
        
        # 显示找到的Wiki页面
        self.main_window.chat_view.add_message(
            MessageType.TRANSITION,
            TransitionMessages.WIKI_FOUND
        )
        
        self.main_window.chat_view.add_message(
            MessageType.WIKI_LINK,
            "Helldivers 2 - 武器指南",
            {"url": "https://duckduckgo.com/?q=!ducky+Helldivers+2+weapons+site:helldivers.wiki.gg"}
        )
        
        # Show wiki page in the unified window (这将触发页面加载和URL更新)
        self.main_window.show_wiki_page(
            "https://duckduckgo.com/?q=!ducky+Helldivers+2+weapons+site:helldivers.wiki.gg", 
            "Helldivers 2 - 武器指南"
        )
        
    def show_guide_result(self):
        """Show guide result with streaming"""
        # 隐藏状态信息
        self.main_window.chat_view.hide_status()
        
        # 显示完成状态
        completion_msg = self.main_window.chat_view.add_message(
            MessageType.TRANSITION,
            TransitionMessages.COMPLETED
        )
        
        # 短暂显示完成状态后开始流式输出
        QTimer.singleShot(500, lambda: self.start_streaming_response(completion_msg))
        
    def start_streaming_response(self, completion_widget):
        """开始流式输出回答"""
        # 隐藏完成状态
        completion_widget.hide()
        
        streaming_msg = self.main_window.chat_view.add_streaming_message()
        
        # Simulate streaming response with markdown formatting
        demo_text = """## 🎮 游戏攻略指南

根据您的问题，我为您整理了以下攻略内容：

### 📋 基础要点
1. **首先**，您需要了解基础机制
2. **其次**，掌握核心技巧  
3. **最后**，通过实践提升水平

### 🛠️ 推荐配装
- 主武器：*高伤害输出*
- 副武器：`快速清兵`
- 装备：**防护为主**

### 💡 高级技巧
> 记住：*熟能生巧*是提升的关键！

希望这些信息对您有帮助！ 😊"""
        
        # 调整chunk大小和速度，便于观察markdown渲染效果
        chunks = [demo_text[i:i+15] for i in range(0, len(demo_text), 15)]
        
        def send_chunk(index=0):
            if index < len(chunks):
                streaming_msg.append_chunk(chunks[index])
                QTimer.singleShot(120, lambda: send_chunk(index + 1))
                
        send_chunk()
        
    def show_processing_status(self, status_message: str, delay_ms: int = 0):
        """
        显示处理状态信息
        
        Args:
            status_message: 状态信息
            delay_ms: 延迟显示的毫秒数
        """
        if self.main_window and self.main_window.chat_view:
            if delay_ms > 0:
                QTimer.singleShot(delay_ms, lambda: self.main_window.chat_view.update_status(status_message))
            else:
                self.main_window.chat_view.update_status(status_message)
                
    def hide_processing_status(self):
        """隐藏处理状态信息"""
        if self.main_window and self.main_window.chat_view:
            self.main_window.chat_view.hide_status()
            
    def hide_all(self):
        """隐藏所有窗口"""
        if self.mini_window:
            self.mini_window.hide()
        if self.main_window:
            self.main_window.hide()
        self.current_mode = None
        
    def toggle_visibility(self):
        """切换显示/隐藏状态"""
        if self.is_visible():
            # 记录当前显示的窗口模式
            self._last_visible_mode = self.current_mode
            self._is_manually_hidden = True  # 用户主动隐藏
            self.hide_all()
        else:
            self._is_manually_hidden = False  # 用户主动显示
            self.restore_last_window()
            
    def is_visible(self):
        """检查是否有窗口在显示"""
        mini_visible = self.mini_window and self.mini_window.isVisible()
        main_visible = self.main_window and self.main_window.isVisible()
        return mini_visible or main_visible
        
    def restore_last_window(self):
        """恢复上次显示的窗口状态"""
        # 如果有记录的模式，恢复到该模式
        if hasattr(self, '_last_visible_mode') and self._last_visible_mode:
            if self._last_visible_mode == WindowMode.MINI:
                self.show_mini()
            elif self._last_visible_mode == WindowMode.CHAT:
                self.expand_to_chat()
        else:
            # 默认显示迷你窗口
            self.show_mini()
            
    def _on_mini_window_visibility_changed(self, is_visible: bool):
        """Handle mini window visibility change"""
        # This is called when mini window is hidden via context menu
        # We need to notify any external listeners (like tray icon)
        if not is_visible:
            # 如果是隐藏操作，设置手动隐藏标志
            self._is_manually_hidden = True
        if hasattr(self, 'visibility_changed') and callable(self.visibility_changed):
            self.visibility_changed(is_visible)
        
    def _on_main_window_visibility_changed(self, is_visible: bool):
        """Handle main window visibility change"""
        # This is called when main window is hidden via context menu
        # We need to notify any external listeners (like tray icon)
        if not is_visible:
            # 如果是隐藏操作，设置手动隐藏标志
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