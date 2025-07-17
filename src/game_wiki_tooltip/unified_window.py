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
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from dataclasses import dataclass, field

from src.game_wiki_tooltip.i18n import t

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
        QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QLineEdit
    )
    from PyQt6.QtGui import (
        QPainter, QColor, QBrush, QPen, QFont, QLinearGradient,
        QPalette, QIcon, QPixmap, QPainterPath
    )
    # Try to import WebEngine, but handle gracefully if it fails
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        WEBENGINE_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: PyQt6 WebEngine not available: {e}")
        print("Wiki view functionality will be disabled. Using fallback text view.")
        WEBENGINE_AVAILABLE = False
        QWebEngineView = None
except ImportError:
    from PyQt5.QtCore import (
        Qt, QTimer, QPropertyAnimation, QRect, QSize, QPoint,
        QEasingCurve, QParallelAnimationGroup, pyqtSignal, QUrl,
        QThread, pyqtSlot
    )
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QFrame, QStackedWidget,
        QScrollArea, QSizePolicy, QGraphicsOpacityEffect, QLineEdit
    )
    from PyQt5.QtGui import (
        QPainter, QColor, QBrush, QPen, QFont, QLinearGradient,
        QPalette, QIcon, QPixmap, QPainterPath
    )
    # Try to import WebEngine for PyQt5, but handle gracefully if it fails
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        WEBENGINE_AVAILABLE = True
    except ImportError as e:
        print(f"Warning: PyQt5 WebEngine not available: {e}")
        print("Wiki view functionality will be disabled. Using fallback text view.")
        WEBENGINE_AVAILABLE = False
        QWebEngineView = None


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
    
    # 简化的状态提示信息
    QUERY_RECEIVED = "🔍 正在分析您的问题..."
    DB_SEARCHING = "📚 检索相关知识库..."
    AI_SUMMARIZING = "📝 智能总结生成中..."
    COMPLETED = "✨ 回答生成完成"


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
        r'📺\s*\*\*信息来源：\*\*',  # 视频源标题
        r'---\s*\n\s*<small>',  # markdown分隔符 + HTML
        r'\n\n<small>.*?来源.*?</small>',  # 通用来源模式
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
                r'📺\s*\*\*信息来源：\*\*',  # 视频源标题模式  
                r'\n\n<small>.*?来源.*?</small>',  # 通用来源模式
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
        
        # 向上查找ChatView实例
        chat_view = self._find_chat_view()
        if chat_view:
            logger.info(f"找到ChatView实例，调用显示Wiki页面")
            chat_view.show_wiki(url, title)
        else:
            logger.warning(f"未找到ChatView实例")
            
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
    
    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(message, parent)
        self.full_text = ""
        self.display_index = 0
        
        # Markdown渲染控制
        self.last_render_index = 0  # 上次渲染时的字符位置
        self.render_interval = 80   # 每80个字符进行一次markdown渲染（减少频率，避免闪烁）
        self.last_render_time = 0   # 上次渲染时间
        self.render_time_interval = 1.5  # 最长1.5秒进行一次渲染
        self.is_markdown_detected = False  # 缓存markdown检测结果
        self.current_format = Qt.TextFormat.PlainText  # 当前文本格式
        self.link_signal_connected = False  # 跟踪是否已连接linkActivated信号
        self.has_video_source = False  # 跟踪是否已检测到视频源
        
        # 优化流式消息的布局，防止闪烁
        self._optimize_for_streaming()
        
        # Typing animation timer
        self.typing_timer = QTimer()
        self.typing_timer.timeout.connect(self.show_next_char)
        
        # Loading dots animation
        self.dots_timer = QTimer()
        self.dots_count = 0
        self.dots_timer.timeout.connect(self.update_dots)
        self.dots_timer.start(500)
    
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
    
    def _update_bubble_width(self):
        """根据聊天窗口宽度动态设置对话框宽度"""
        # 获取聊天视图的宽度，考虑滚动条宽度
        chat_view = self.parent()
        if chat_view and hasattr(chat_view, 'viewport'):
            viewport_width = chat_view.viewport().width()
            # 减去滚动条可能占用的宽度（通常约20px）
            scrollbar = chat_view.verticalScrollBar()
            if scrollbar and scrollbar.isVisible():
                viewport_width -= scrollbar.width()
        else:
            # 如果无法获取聊天视图宽度，尝试从父容器获取
            parent_widget = self.parent()
            viewport_width = parent_widget.width() if parent_widget else 500
        
        # 确保有效宽度
        viewport_width = max(300, viewport_width)
        
        # 计算对话框宽度（聊天视图宽度的75%，减少比例避免过宽，但不超过600px，不少于300px）
        bubble_width = max(300, min(600, int(viewport_width * 0.75)))
        content_width = bubble_width - 24  # 减去边距
        
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
    
    def set_render_params(self, char_interval: int = 80, time_interval: float = 1.5):
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
        self.full_text += chunk
        if not self.typing_timer.isActive():
            self.dots_timer.stop()
            # 初始化渲染时间戳和markdown检测
            self.last_render_time = time.time()
            # 提前检测是否可能包含markdown（基于首个chunk）
            if len(self.full_text) > 10:  # 有一定长度时再检测
                self.is_markdown_detected = detect_markdown_content(self.full_text)
            self.typing_timer.start(20)  # 20ms per character
            
    def show_next_char(self):
        """Show next character in typing animation"""
        if self.display_index < len(self.full_text):
            self.display_index += 1
            display_text = self.full_text[:self.display_index]
            current_time = time.time()
            
            # 检查是否需要进行阶段性markdown渲染
            should_render = False
            
            # 条件1: 达到字符间隔
            if self.display_index - self.last_render_index >= self.render_interval:
                should_render = True
            
            # 条件2: 达到时间间隔
            elif current_time - self.last_render_time >= self.render_time_interval:
                should_render = True
            
            # 条件3: 检测到关键内容边界（如video sources开始）
            elif not self.has_video_source and ('📺' in display_text[-10:] or 
                  '---\n<small>' in display_text[-20:] or
                  '<small>' in display_text[-10:]):
                should_render = True
                self.has_video_source = True  # 标记已检测到视频源，避免重复打印
                print(f"🎬 [STREAMING] 检测到视频源内容，触发渲染")
            
            if should_render and self.message.type == MessageType.AI_STREAMING:
                # 重新检测内容格式（支持动态变化，如添加HTML视频源）
                current_has_format = detect_markdown_content(display_text)
                
                # 如果检测到格式变化，更新检测状态
                if current_has_format and not self.is_markdown_detected:
                    self.is_markdown_detected = True
                    print(f"🔄 [STREAMING] 检测到格式内容，切换到HTML渲染模式，当前长度: {len(display_text)}")
                
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
                else:
                    # 只在格式实际变化时才设置格式，避免闪烁
                    if self.current_format != Qt.TextFormat.PlainText:
                        self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                        self.current_format = Qt.TextFormat.PlainText
                        print(f"📝 [STREAMING] 切换到PlainText格式，内容长度: {len(display_text)}")
                    self.content_label.setText(display_text)
                
                # 更新渲染状态
                self.last_render_index = self.display_index
                self.last_render_time = current_time
            else:
                # 不需要渲染时，保持当前格式但更新文本
                if self.is_markdown_detected:
                    # 如果已检测到markdown/HTML，继续使用HTML格式
                    html_content = convert_markdown_to_html(display_text)
                    self.content_label.setText(html_content)
                else:
                    # 否则使用纯文本
                    self.content_label.setText(display_text)
                
            # 不要频繁调用adjustSize，这是闪烁的主要原因
            # self.content_label.adjustSize()
            # self.adjustSize()
            
            # Auto-scroll to bottom
            if hasattr(self.parent(), 'smart_scroll_to_bottom'):
                self.parent().smart_scroll_to_bottom()
        else:
            self.typing_timer.stop()
            
            # 最终完成时，转换消息类型并进行最终渲染
            if self.message.type == MessageType.AI_STREAMING and self.full_text:
                # 将消息类型改为AI_RESPONSE，表示流式输出已完成
                self.message.type = MessageType.AI_RESPONSE
                
                # 输出完成信息
                has_video_sources = any(pattern in self.full_text for pattern in [
                    '📺 **信息来源：**', 
                    '---\n<small>', 
                    '<small>.*?来源.*?</small>'
                ])
                print(f"🎬 [STREAMING] 流式消息完成，长度: {len(self.full_text)} 字符，包含视频源: {has_video_sources}")
                
                # 进行最终的格式检测和转换
                # 如果包含视频源，强制使用RichText格式
                if detect_markdown_content(self.full_text) or has_video_sources:
                    html_content = convert_markdown_to_html(self.full_text)
                    self.content_label.setText(html_content)
                    self.content_label.setTextFormat(Qt.TextFormat.RichText)
                    
                    # 流式输出完成后，确保linkActivated信号已连接（避免重复连接）
                    if not self.link_signal_connected:
                        self.content_label.linkActivated.connect(self.on_link_clicked)
                        self.link_signal_connected = True
                        print(f"🔗 [STREAMING] 最终渲染时连接linkActivated信号")
                    
                    print(f"✅ [STREAMING] 最终渲染完成，使用RichText格式")
                else:
                    self.content_label.setText(self.full_text)
                    self.content_label.setTextFormat(Qt.TextFormat.PlainText)
                    print(f"✅ [STREAMING] 最终渲染完成，使用PlainText格式")
                
                # 更新几何而不是强制调整大小，避免内容被截断
                self.content_label.updateGeometry()
                self.updateGeometry()
                
                # 确保父容器也更新布局
                if self.parent() and hasattr(self.parent(), 'container'):
                    self.parent().container.updateGeometry()
                
                # 移除不必要的调试输出
                
                # 延迟滚动到底部，确保布局完成后内容可见
                if hasattr(self.parent(), 'scroll_to_bottom'):
                    QTimer.singleShot(200, self.parent().scroll_to_bottom)
            
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
        self.current_status_widget: Optional[StatusMessageWidget] = None
        
        # 自动滚动控制
        self.auto_scroll_enabled = True  # 是否启用自动滚动
        self.user_scrolled_manually = False  # 用户是否手动滚动过
        self.last_scroll_position = 0  # 上次滚动位置
        
        # resize防抖动机制
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._performDelayedResize)
        
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
        
        # 稍微延长滚动延迟，确保布局完成
        QTimer.singleShot(150, self.smart_scroll_to_bottom)
        
        return widget
        
    def add_streaming_message(self) -> StreamingMessageWidget:
        """Add a new streaming message"""
        # 创建流式消息，完成后会转换为AI_RESPONSE类型
        streaming_widget = self.add_message(MessageType.AI_STREAMING, "")
        return streaming_widget
        
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
        QTimer.singleShot(150, self.smart_scroll_to_bottom)
        
        return self.current_status_widget
        
    def update_status(self, message: str):
        """更新当前状态信息"""
        if self.current_status_widget:
            self.current_status_widget.update_status(message)
            # 确保滚动到底部显示新状态
            QTimer.singleShot(50, self.smart_scroll_to_bottom)
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
            print("📍 滚轮操作后接近底部，重新启用自动滚动")
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
        
        # 强制ChatView保持正确的宽度（立即执行，避免显示异常）
        parent_width = self.parent().width() if self.parent() else 0
        current_width = self.width()
        if parent_width > 0 and abs(current_width - parent_width) > 5:  # 超过5px差异
            self.resize(parent_width, self.height())
        
        # 使用防抖动机制延迟更新消息宽度
        self.resize_timer.stop()  # 停止之前的计时器
        self.resize_timer.start(200)  # 0.2秒后执行更新
        
    def _performDelayedResize(self):
        """延迟执行的resize更新操作"""
        # 调试：只在防抖动完成后输出一次信息
        print(f"📏 ChatView尺寸稳定，执行布局更新: {self.size()}")
        
        # 更新所有现有消息的宽度
        for widget in self.messages:
            self._update_message_width(widget)
        # 更新状态消息的宽度
        if self.current_status_widget:
            self._update_status_width(self.current_status_widget)
            
        # 强制更新所有消息的高度，确保内容完整显示
        self._ensureContentComplete()
        
        # 确保滚动到正确位置
        QTimer.singleShot(50, self.smart_scroll_to_bottom)
        
    def _ensureContentComplete(self):
        """确保所有消息内容完整显示"""
        for widget in self.messages:
            if hasattr(widget, 'content_label'):
                # 强制内容标签重新计算高度
                widget.content_label.updateGeometry()
                widget.updateGeometry()
                
                # 对于流式消息，特别处理
                if isinstance(widget, StreamingMessageWidget):
                    # 如果是已完成的流式消息，确保所有内容都可见
                    if widget.message.type == MessageType.AI_RESPONSE and widget.full_text:
                        # 重新设置文本以触发高度重新计算
                        current_text = widget.content_label.text()
                        if current_text:
                            widget.content_label.setText("")
                            widget.content_label.setText(current_text)
                            widget.content_label.updateGeometry()
                            widget.updateGeometry()
        
        # 强制整个容器重新布局
        self.container.updateGeometry()
        self.updateGeometry()
            
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


class WikiView(QWidget):
    """Wiki page viewer"""
    
    back_requested = pyqtSignal()
    wiki_page_loaded = pyqtSignal(str, str)  # 新信号：url, title
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_search_url = ""  # 存储搜索URL
        self.current_search_title = ""  # 存储搜索标题
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
        
        # Open in browser button (when WebEngine not available)
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
        
        toolbar_layout.addWidget(self.back_button)
        toolbar_layout.addWidget(self.title_label)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.open_browser_button)
        
        # Content area
        if WEBENGINE_AVAILABLE and QWebEngineView:
            # Use WebEngine view
            self.web_view = QWebEngineView()
            # 修复尺寸问题：设置更小的最小尺寸，避免影响整体布局
            self.web_view.setMinimumSize(100, 100)  # 减小最小尺寸
            self.web_view.setMaximumSize(16777215, 16777215)  # 移除最大尺寸限制
            # 设置尺寸策略为可扩展，允许自由调整
            self.web_view.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding
            )
            
            # 连接页面加载完成信号
            self.web_view.loadFinished.connect(self._on_page_load_finished)
            
            self.content_widget = self.web_view
        else:
            # Fallback to text view
            self.content_widget = QTextEdit()
            self.content_widget.setReadOnly(True)
            self.content_widget.setMinimumSize(100, 100)  # 减小最小尺寸，避免影响布局
            self.content_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding
            )
            self.content_widget.setStyleSheet("""
                QTextEdit {
                    background-color: white;
                    border: none;
                    font-family: "Microsoft YaHei", "Segoe UI", Arial;
                    font-size: 14px;
                    line-height: 1.6;
                }
            """)
            self.web_view = None
        
        layout.addWidget(toolbar)
        layout.addWidget(self.content_widget)
        
        # Store current URL and title
        self.current_url = ""
        self.current_title = ""
        
    def _on_page_load_finished(self, ok):
        """页面加载完成时的回调"""
        if not ok or not self.web_view:
            return
            
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
            self.title_label.setText(title)
            
            # 发出信号，通知找到了真实的wiki页面
            print(f"📄 WikiView找到真实wiki页面: {title} -> {current_url}")
            self.wiki_page_loaded.emit(current_url, title)
            
        except Exception as e:
            print(f"处理页面标题失败: {e}")
        
    def load_wiki(self, url: str, title: str):
        """Load a wiki page"""
        self.current_search_url = url  # 保存搜索URL
        self.current_search_title = title  # 保存搜索标题
        self.current_url = url
        self.current_title = title
        self.title_label.setText(title)
        
        if self.web_view:
            # Use WebEngine
            self.web_view.load(QUrl(url))
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


class UnifiedAssistantWindow(QMainWindow):
    """Main unified window with all modes"""
    
    query_submitted = pyqtSignal(str)
    window_closing = pyqtSignal()  # Signal when window is closing
    wiki_page_found = pyqtSignal(str, str)  # 新信号：传递真实wiki页面信息到controller
    
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self.current_mode = WindowMode.MINI
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
        self.wiki_view.back_requested.connect(self.show_chat_view)
        self.wiki_view.wiki_page_loaded.connect(self.handle_wiki_page_loaded)
        # 确保Wiki视图有合理的最小尺寸但不强制固定尺寸
        self.wiki_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
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
        
        # Add to main layout with stretch factor
        main_layout.addWidget(self.content_stack, 1)  # 拉伸因子1，占据所有可用空间
        main_layout.addWidget(input_container, 0)     # 拉伸因子0，保持固定高度
        
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
        """Restore window geometry from settings with DPI scaling support"""
        if self.settings_manager:
            try:
                scale = _get_scale()  # 获取DPI缩放因子
                settings = self.settings_manager.get()
                popup = settings.get('popup', {})
                
                # 从逻辑像素转换为物理像素
                phys_x = int(popup.get('left', 100) * scale)
                phys_y = int(popup.get('top', 100) * scale)
                phys_w = int(popup.get('width', 500) * scale)
                phys_h = int(popup.get('height', 700) * scale)
                
                # 确保窗口在屏幕范围内
                screen = QApplication.primaryScreen().geometry()
                
                # 调整位置确保窗口可见
                if phys_x + phys_w > screen.width():
                    phys_x = screen.width() - phys_w - 10
                if phys_y + phys_h > screen.height():
                    phys_y = screen.height() - phys_h - 40
                if phys_x < 0:
                    phys_x = 10
                if phys_y < 0:
                    phys_y = 30
                
                self.setGeometry(phys_x, phys_y, phys_w, phys_h)
                logging.info(f"恢复窗口几何: x={phys_x}, y={phys_y}, w={phys_w}, h={phys_h}, scale={scale}")
                
                # 恢复几何后重置尺寸约束，确保可以自由调整大小
                self.reset_size_constraints()
                
            except Exception as e:
                logging.error(f"恢复窗口几何信息失败: {e}")
                # 失败时使用默认值
                self.setGeometry(617, 20, 514, 32)
                self.reset_size_constraints()
        else:
            self.setGeometry(617, 20, 514, 32)
            self.reset_size_constraints()
            
    def save_geometry(self):
        """Save window geometry to settings with DPI scaling support"""
        if self.settings_manager:
            try:
                scale = _get_scale()  # 获取DPI缩放因子
                geo = self.geometry()
                
                # 将物理像素转换为逻辑像素
                css_x = int(geo.x() / scale)
                css_y = int(geo.y() / scale)
                css_w = int(geo.width() / scale)
                css_h = int(geo.height() / scale)
                
                # 更新配置
                self.settings_manager.update({
                    'popup': {
                        'left': css_x,
                        'top': css_y,
                        'width': css_w,
                        'height': css_h
                    }
                })
                
                logging.info(f"保存窗口几何: x={css_x}, y={css_y}, w={css_w}, h={css_h}, scale={scale}")
            except Exception as e:
                logging.error(f"保存窗口几何信息失败: {e}")
            
    def show_chat_view(self):
        """Switch to chat view"""
        self.content_stack.setCurrentWidget(self.chat_view)
        # 切换到聊天视图时重置尺寸约束
        self.reset_size_constraints()
        # 确保消息宽度正确
        QTimer.singleShot(50, self.chat_view.update_all_message_widths)
        
    def show_wiki_page(self, url: str, title: str):
        """Switch to wiki view and load page"""
        logger = logging.getLogger(__name__)
        logger.info(f"🌐 UnifiedAssistantWindow.show_wiki_page 被调用: URL={url}, Title={title}")
        self.wiki_view.load_wiki(url, title)
        self.content_stack.setCurrentWidget(self.wiki_view)
        # 切换到Wiki视图时也重置尺寸约束
        self.reset_size_constraints()
        logger.info(f"✅ 已切换到Wiki视图并加载页面")
        
    def handle_wiki_page_loaded(self, url: str, title: str):
        """处理Wiki页面加载完成信号，将信号转发给controller"""
        print(f"🌐 UnifiedAssistantWindow: Wiki页面加载完成 - {title}: {url}")
        # 发出信号给controller处理
        self.wiki_page_found.emit(url, title)
        
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
        self.current_game_window = None  # 记录当前游戏窗口标题
        
    def show_mini(self):
        """Show mini assistant"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("show_mini() called")
        
        if not self.mini_window:
            logger.info("Creating new MiniAssistant window")
            self.mini_window = MiniAssistant()
            self.mini_window.clicked.connect(self.expand_to_chat)
            logger.info("MiniAssistant created and signal connected")
        
        # 确保窗口显示在屏幕上
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
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🎮 记录游戏窗口: '{game_window_title}'")
        
    def expand_to_chat(self):
        """Expand from mini to chat window with animation"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("expand_to_chat() called")
        
        if not self.main_window:
            logger.info("Creating new UnifiedAssistantWindow")
            self.main_window = UnifiedAssistantWindow(self.settings_manager)
            self.main_window.query_submitted.connect(self.handle_query)
            self.main_window.window_closing.connect(self.show_mini)
            self.main_window.wiki_page_found.connect(self.handle_wiki_page_found)
            logger.info("UnifiedAssistantWindow created and signals connected")
        
        # 确保窗口显示
        logger.info("Showing main window")
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        
        if self.mini_window:
            logger.info("Mini window exists, starting animation")
            
            # Get screen geometry
            screen = QApplication.primaryScreen().geometry()
            
            # Get mini window position and settings
            mini_pos = self.mini_window.pos()
            
            # 从设置中获取保存的窗口位置和大小
            settings = self.settings_manager.get() if self.settings_manager else {}
            popup = settings.get('popup', {})
            scale = _get_scale()
            
            # 从逻辑像素转换为物理像素
            target_width = int(popup.get('width', 514) * scale)
            target_height = int(popup.get('height', 32) * scale)
            
            # 使用保存的位置而不是根据mini window计算
            saved_x = int(popup.get('left', 617) * scale)
            saved_y = int(popup.get('top', 20) * scale)
            
            # 确保窗口在屏幕范围内（使用保存的位置）
            target_x = max(10, min(saved_x, screen.width() - target_width - 10))
            target_y = max(30, min(saved_y, screen.height() - target_height - 40))
            
            logger.info(f"Using saved position: saved=({saved_x}, {saved_y}), adjusted=({target_x}, {target_y})")
            logger.info(f"Animation: from ({mini_pos.x()}, {mini_pos.y()}, 60, 60) to ({target_x}, {target_y}, {target_width}, {target_height})")
            
            # Set initial position and size
            self.main_window.setGeometry(
                mini_pos.x(), mini_pos.y(), 60, 60
            )
            
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
            
            # 添加动画完成回调，自动设置输入框焦点
            def on_animation_finished():
                logger.info("Animation finished, setting focus to input field")
                if self.main_window and self.main_window.input_field:
                    self.main_window.input_field.setFocus()
                    self.main_window.input_field.activateWindow()
                    
            self.expand_animation.finished.connect(on_animation_finished)
            self.expand_animation.start()
            
            logger.info("Animation started")
        else:
            logger.info("No mini window, directly showing main window")
            # 使用restore_geometry恢复上次的窗口位置和大小
            self.main_window.restore_geometry()
            
        self.current_mode = WindowMode.CHAT
        
        # 确保消息宽度在窗口显示后正确设置
        QTimer.singleShot(200, self.main_window.chat_view.update_all_message_widths)
        
        logger.info("expand_to_chat() completed")
        
    def handle_wiki_page_found(self, url: str, title: str):
        """处理找到真实wiki页面的信号（基础实现，子类可重写）"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔗 AssistantController收到wiki页面信号: {title} -> {url}")
        # 基础实现：什么都不做，子类（IntegratedAssistantController）会重写此方法
        
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


# Demo/Testing
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Create controller
    controller = AssistantController()
    controller.show_mini()
    
    sys.exit(app.exec())