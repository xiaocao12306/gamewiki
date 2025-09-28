"""付费墙弹窗组件，展示远程配置的文案与 CTA"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QScrollArea,
    QFrame,
)


class PaywallDialog(QDialog):
    """简单的积分墙弹窗，用于展示升级提示与 CTA"""

    cta_clicked = pyqtSignal(dict)
    dismissed = pyqtSignal()

    def __init__(
        self,
        *,
        copy_config: Optional[Dict[str, Any]] = None,
        ctas: Optional[List[Dict[str, Any]]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(360)
        self._copy = copy_config or {}
        self._ctas = ctas or []

        self._init_ui()

    def _init_ui(self) -> None:
        title = self._copy.get("title") or "AI usage limit reached"
        self.setWindowTitle(title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # 标题
        title_label = QLabel(title, self)
        title_label.setObjectName("paywallTitle")
        font = title_label.font()
        font.setPointSizeF(font.pointSizeF() + 2)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # 高亮文案
        highlight = self._copy.get("highlight")
        if highlight:
            highlight_label = QLabel(highlight, self)
            highlight_label.setObjectName("paywallHighlight")
            highlight_label.setWordWrap(True)
            highlight_label.setStyleSheet("color: #FF6B00; font-weight: 600;")
            layout.addWidget(highlight_label)

        # 主体文案，支持换行
        body_text = self._copy.get("body") or ""
        if body_text:
            body_container = QScrollArea(self)
            body_container.setWidgetResizable(True)
            body_container.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            body_container.setFrameShape(QFrame.Shape.NoFrame)

            body_widget = QWidget(body_container)
            body_layout = QVBoxLayout(body_widget)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(0)

            body_label = QLabel(body_text.replace("\n", "<br/>"), body_widget)
            body_label.setWordWrap(True)
            body_label.setTextFormat(Qt.TextFormat.RichText)
            body_label.setObjectName("paywallBody")
            body_layout.addWidget(body_label)
            body_layout.addStretch()

            body_container.setWidget(body_widget)
            body_container.setMaximumHeight(160)
            layout.addWidget(body_container)

        # CTA 区域
        if self._ctas:
            buttons_container = QVBoxLayout()
            buttons_container.setSpacing(10)

            for item in self._ctas:
                label = item.get("label") or "Learn more"
                button = QPushButton(label, self)
                button.setObjectName("paywallCTAButton")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setMinimumHeight(36)
                button.clicked.connect(lambda _, data=item: self.cta_clicked.emit(data))  # type: ignore[arg-type]
                buttons_container.addWidget(button)

            layout.addLayout(buttons_container)

        layout.addStretch()

        # 简单样式
        self.setStyleSheet(
            """
            QDialog {
                background-color: #ffffff;
                border-radius: 12px;
            }
            QLabel#paywallTitle {
                color: #1D2331;
            }
            QLabel#paywallBody {
                color: #4A5161;
                line-height: 1.5em;
            }
            QPushButton#paywallCTAButton {
                background-color: #4C6EF5;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                padding: 8px 16px;
            }
            QPushButton#paywallCTAButton:hover {
                background-color: #3B5BDB;
            }
            QPushButton#paywallCTAButton:pressed {
                background-color: #364FC7;
            }
            QLabel#paywallHighlight {
                color: #FF6B00;
            }
        """
        )

    def closeEvent(self, event):
        super().closeEvent(event)
        self.dismissed.emit()

