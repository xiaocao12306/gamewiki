from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal
)
from PyQt6.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy, QMenu
)

import logging
import time

from src.game_wiki_tooltip.window_component import (
    convert_markdown_to_html,
    MessageType,
    ChatMessage,
)
from .markdown_converter import detect_markdown_content

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
            # Use duck typing instead of isinstance to avoid circular import
            if hasattr(parent, 'show_wiki') and hasattr(parent, 'wiki_requested'):
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
        self.render_interval = 50  # Render markdown every 50 characters (reduce frequency to avoid flickering)
        self.last_render_time = 0  # Last render time
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
        print(
            f"🔧 [STREAMING] New StreamingMessageWidget initialization completed, timer status: {'Active' if self.typing_timer.isActive() else 'Inactive'}")

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

    def _is_non_streaming_content(self, content: str) -> bool:
        """
        检测是否是非流式内容（如来自FallbackGuideHandler的内容）
        非流式内容的特征：
        1. 以NOTICE开头的fallback内容
        2. 包含完整结构的长内容（>1000字符且包含多个段落）
        """
        if not content:
            return False
        
        # 检测NOTICE标记（FallbackGuideHandler的标志）
        if content.strip().startswith("NOTICE:"):
            return True
            
        # 检测长内容且结构完整（可能是非流式API返回的完整内容）
        if len(content) > 1000 and content.count('\n\n') >= 3:
            return True
            
        return False

    def _display_complete_content(self, content: str):
        """直接显示完整内容，不使用打字机效果"""
        print(f"📋 [NON-STREAMING] Displaying complete content directly, length: {len(content)}")
        
        # 停止所有动画
        self.typing_timer.stop()
        self.dots_timer.stop()
        
        # 检测格式并直接显示
        if detect_markdown_content(content):
            html_content = convert_markdown_to_html(content)
            self.content_label.setTextFormat(Qt.TextFormat.RichText)
            self.content_label.setText(html_content)
            self.current_format = Qt.TextFormat.RichText
            
            # 确保链接处理正确配置
            if not self.link_signal_connected:
                self.content_label.linkActivated.connect(self.on_link_clicked)
                self.link_signal_connected = True
            self.content_label.setOpenExternalLinks(False)
        else:
            self.content_label.setTextFormat(Qt.TextFormat.PlainText)
            self.content_label.setText(content)
            self.current_format = Qt.TextFormat.PlainText
        
        # 标记为完成
        self.display_index = len(content)
        self.message.type = MessageType.AI_RESPONSE
        self.streaming_finished.emit()
        
        # 恢复灵活宽度
        self._restore_flexible_width()

    def _optimize_for_streaming(self):
        """Optimize streaming message layout to prevent flickering"""
        # Find message bubble
        bubble = self.findChild(QFrame, "messageBubble")
        if bubble:
            # Use Minimum policy to only take required height
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        # Optimize content_label settings
        if hasattr(self, 'content_label'):
            # Use Minimum policy to only take required height
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
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
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        if hasattr(self, 'content_label'):
            self.content_label.setMaximumWidth(content_width)
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

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
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            print(f"🔓 [STREAMING] Restored bubble flexible width, max: {self._calculated_bubble_width}px")

        if hasattr(self, 'content_label') and hasattr(self, '_calculated_content_width'):
            # Remove fixed width, restore maximum width limit
            self.content_label.setMinimumWidth(0)
            self.content_label.setMaximumWidth(self._calculated_content_width)
            self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            print(f"🔓 [STREAMING] Restored content flexible width, max: {self._calculated_content_width}px")

        # Mark flexible width as restored
        self._width_fixed = False

    def get_chat_view(self):
        """Get parent ChatView (if exists)"""
        try:
            parent = self.parent()
            # Check if parent is ChatView (by checking specific methods)
            if parent and hasattr(parent, 'verticalScrollBar'):
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
        
        # 检测是否是非流式内容（如来自FallbackGuideHandler的内容）
        if self._is_non_streaming_content(self.full_text):
            print(f"📋 [NON-STREAMING] Detected non-streaming content, skipping typewriter effect")
            self._display_complete_content(self.full_text)
            return

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
            # Faster typewriter effect: 2ms per character (previously 5ms)
            self.typing_timer.start(2)
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
            new_interval = 1
        elif remaining_chars > 50:
            # Small amount of remaining content, normal speed
            new_interval = 2
        else:
            # Very little remaining content, normal speed to maintain typewriter effect
            new_interval = 2

        # Check if timer interval needs adjustment
        if self.typing_timer.isActive():
            current_interval = self.typing_timer.interval()
            if current_interval != new_interval:
                print(
                    f"🚀 [TYPING] Adjusted typing speed: {current_interval}ms -> {new_interval}ms, Remaining: {remaining_chars}characters")
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
            # Show multiple characters at once for faster display
            batch_size = 3  # Show 3 characters at a time
            self.display_index = min(self.display_index + batch_size, len(self.full_text))
            display_text = self.full_text[:self.display_index]
            current_time = time.time()

            # Early markdown detection (start detecting at the first 20 characters)
            if self.display_index <= 20 and not self.is_markdown_detected and len(self.full_text) > 5:
                if detect_markdown_content(self.full_text):
                    self.is_markdown_detected = True
                    self.current_format = Qt.TextFormat.RichText
                    self.content_label.setTextFormat(Qt.TextFormat.RichText)
                    print(
                        f"🚀 [STREAMING] Early detected markdown format（{self.display_index}characters），Full text length: {len(self.full_text)}")

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
                    print(
                        f"🔄 [STREAMING] Force detected format content, triggering render, position: {self.display_index}")

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
                    print(
                        f"🔗 [STREAMING] Content label config - OpenExternalLinks: {self.content_label.openExternalLinks()}")
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
                print(
                    f"🎬 [STREAMING] Streaming message completed, length: {len(self.full_text)} characters，Contains video sources: {has_video_sources}")

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

                print(
                    f"🔄 [STREAMING] Final format detection: markdown={final_has_format}, video={final_has_video_sources}, Cache status={self.is_markdown_detected}")

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
        
        # Force update message width and height after content is fully displayed
        chat_view = self.get_chat_view()
        if chat_view:
            # Delay call to ensure content is fully displayed
            QTimer.singleShot(200, lambda: chat_view._update_message_width(self))
