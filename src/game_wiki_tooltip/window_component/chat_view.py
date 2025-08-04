from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame,
    QScrollArea, QSizePolicy, QMenu
)
from PyQt6.QtGui import QTextDocument

from src.game_wiki_tooltip.window_component import (
    convert_markdown_to_html,
    detect_markdown_content,
    MessageType,
    ChatMessage,
    StatusMessageWidget,
    MessageWidget,
    StreamingMessageWidget,
)

import logging
from typing import Optional, Dict, Any, List

from src.game_wiki_tooltip.core.i18n import t

class ChatView(QScrollArea):
    """Chat message list view"""

    wiki_requested = pyqtSignal(str, str)  # url, title

    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages: List[MessageWidget] = []
        self.current_status_widget: Optional[StatusMessageWidget] = None

        # Resize anti-shake mechanism
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._performDelayedResize)

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

        # Connect scrollbar signals
        scrollbar = self.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll_changed)

        # Don't add welcome message anymore

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

        # Only set minimum height if we have existing messages (to prevent shrinking)
        if self.messages:
            current_height = self.height()
            self.setMinimumHeight(current_height)

        self.layout.insertWidget(self.layout.count() - 1, widget)
        self.messages.append(widget)

        # Dynamically set message maximum width to 75% of ChatView width
        self._update_message_width(widget)

        # Gentle layout update, avoid forced resizing
        widget.updateGeometry()
        self.container.updateGeometry()

        # Reset minimum height after layout stabilizes (only if we set it)
        if self.messages and len(self.messages) > 1:  # We set minimum height if there were existing messages
            QTimer.singleShot(10, lambda: self.setMinimumHeight(0))

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

        # Store current height to prevent shrinking
        current_height = self.height()

        # Temporarily disable updates to prevent visual glitches
        self.setUpdatesEnabled(False)

        try:
            # If there is already a status message, replace it atomically
            if self.current_status_widget:
                # Create new status message first
                new_status_widget = StatusMessageWidget(message, self)

                # Get the index of the old widget
                old_index = self.layout.indexOf(self.current_status_widget)

                # Remove old widget and insert new one at the same position
                self.layout.removeWidget(self.current_status_widget)
                self.layout.insertWidget(old_index, new_status_widget)

                # Clean up old widget
                self.current_status_widget.hide()
                self.current_status_widget.deleteLater()

                # Update reference
                self.current_status_widget = new_status_widget
            else:
                # No existing status, just add new one
                self.current_status_widget = StatusMessageWidget(message, self)
                self.layout.insertWidget(self.layout.count() - 1, self.current_status_widget)

            # Set minimum height to prevent shrinking
            self.setMinimumHeight(current_height)

            # Dynamically set message maximum width
            self._update_status_width(self.current_status_widget)

            # Gentle layout update
            self.current_status_widget.updateGeometry()
            self.container.updateGeometry()

        finally:
            # Re-enable updates
            self.setUpdatesEnabled(True)

            # Check if input field should have focus
            parent_window = self.parent()
            if (parent_window and hasattr(parent_window, 'input_field') and
                    hasattr(parent_window, 'isActiveWindow') and parent_window.isActiveWindow()):
                # Restore focus to input field if window is active
                parent_window.input_field.setFocus(Qt.FocusReason.OtherFocusReason)

            # Reset minimum height after a short delay
            QTimer.singleShot(10, lambda: self.setMinimumHeight(0))

        return self.current_status_widget

    def update_status(self, message: str):
        """Update current status information"""
        if self.current_status_widget:
            self.current_status_widget.update_status(message)
        else:
            self.show_status(message)

    def hide_status(self):
        """Hide current status information"""
        if self.current_status_widget:
            # Store current height to prevent shrinking
            current_height = self.height()

            # Temporarily set minimum height
            self.setMinimumHeight(current_height)

            # Hide and remove widget
            self.current_status_widget.hide_with_fadeout()
            self.layout.removeWidget(self.current_status_widget)
            self.current_status_widget.deleteLater()
            self.current_status_widget = None

            # Reset minimum height after a short delay
            QTimer.singleShot(10, lambda: self.setMinimumHeight(0))

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

            # Set the maximum width of the status message to 85% of the width of the chat view, minimum 300px, maximum 800px
            max_width = min(max(int(chat_width * 0.85), 300), 800)
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

    def _check_content_stability(self):
        """Check if the content is stable"""
        current_height = self.container.sizeHint().height()
        if current_height != self._last_content_height:
            # Content is still changing, continue waiting
            self._last_content_height = current_height
            self._content_stable_timer.start(50)

    def _on_scroll_changed(self, value):
        """Callback when scroll position changes"""
        # Currently no action needed on scroll change
        pass

    def wheelEvent(self, event):
        """Mouse wheel event"""
        # Call the original wheel event processing
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click event"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Scroll to bottom on double-click
            self.scroll_to_bottom()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """Keyboard event"""
        if event.key() == Qt.Key.Key_End:
            # End key: scroll to the bottom
            self.scroll_to_bottom()
        elif event.key() == Qt.Key.Key_Home:
            # Home key: scroll to the top
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
                    bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

                # Update the width of content_label at the same time
                if hasattr(widget, 'content_label'):
                    content_width = max_width - 24  # Subtract margin
                    widget.content_label.setMaximumWidth(content_width)
                    widget.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

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
                        content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

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
                            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

                            # Improved: use a more reliable way to calculate the required height
                            # Wait a little bit to let the content render
                            QTimer.singleShot(10,
                                              lambda w=widget, b=bubble, cl=content_label: self._updateBubbleHeight(w,
                                                                                                                    b,
                                                                                                                    cl))

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

        # Additional content refresh to fix incomplete display issues
        QTimer.singleShot(150, self._performDelayedResize)
        QTimer.singleShot(200, self._ensureContentComplete)





