from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QSize, QPoint,
    QEasingCurve
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFrame
)
from PyQt6.QtGui import (
    QIcon, QPixmap
)
import os

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