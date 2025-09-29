"""付费墙弹窗组件，展示远程配置的文案与 CTA"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QScrollArea,
    QFrame,
    QSizePolicy,
)


class PaywallDialog(QDialog):
    """积分墙弹窗：支持标题、高亮、正文与多 CTA 的完整布局"""

    cta_clicked = pyqtSignal(dict)
    dismissed = pyqtSignal(str)

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
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(420)

        self._copy = copy_config or {}
        self._ctas = ctas or []
        self._close_reason = "close"

        self._init_ui()
        self._populate_content()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(20)

        # Header（标题 + 关闭按钮）
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)

        self.title_label = QLabel("", self)
        self.title_label.setObjectName("paywallTitle")
        title_font = self.title_label.font()
        title_font.setPointSizeF(title_font.pointSizeF() + 2)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header.addWidget(self.title_label)

        self.close_button = QPushButton("✕", self)
        self.close_button.setObjectName("paywallCloseButton")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFixedSize(28, 28)
        self.close_button.clicked.connect(self._on_close_clicked)
        header.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header)

        # 高亮标签
        self.highlight_label = QLabel("", self)
        self.highlight_label.setObjectName("paywallHighlight")
        self.highlight_label.setWordWrap(True)
        self.highlight_label.hide()
        layout.addWidget(self.highlight_label)

        # 正文区域（滚动容器，避免长文撑破）
        self.body_area = QScrollArea(self)
        self.body_area.setWidgetResizable(True)
        self.body_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body_area.setFrameShape(QFrame.Shape.NoFrame)
        self.body_area.setMaximumHeight(220)

        body_widget = QWidget(self.body_area)
        self.body_layout = QVBoxLayout(body_widget)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)

        self.body_label = QLabel("", body_widget)
        self.body_label.setObjectName("paywallBody")
        self.body_label.setWordWrap(True)
        self.body_label.setTextFormat(Qt.TextFormat.PlainText)
        self.body_layout.addWidget(self.body_label)
        self.body_layout.addStretch()

        self.body_area.setWidget(body_widget)
        layout.addWidget(self.body_area)

        # CTA 容器
        self.cta_container = QWidget(self)
        self.cta_container.setObjectName("paywallCTAContainer")
        self.cta_layout = QVBoxLayout(self.cta_container)
        self.cta_layout.setContentsMargins(0, 0, 0, 0)
        self.cta_layout.setSpacing(12)
        layout.addWidget(self.cta_container)

        # 次要提示（如“可在横幅再次查看”）
        self.secondary_hint = QLabel("", self)
        self.secondary_hint.setObjectName("paywallSecondaryHint")
        self.secondary_hint.setWordWrap(True)
        self.secondary_hint.hide()
        layout.addWidget(self.secondary_hint)

        # 页脚按钮（稍后再说）
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addStretch(1)

        self.dismiss_button = QPushButton("稍后再说", self)
        self.dismiss_button.setObjectName("paywallDismissButton")
        self.dismiss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dismiss_button.setMinimumHeight(32)
        self.dismiss_button.clicked.connect(self._on_dismiss_clicked)
        footer.addWidget(self.dismiss_button)

        layout.addLayout(footer)

        # 样式
        self.setStyleSheet(
            """
            QDialog {
                background-color: #FFFFFF;
                border-radius: 16px;
            }
            QLabel#paywallTitle {
                color: #111528;
            }
            QLabel#paywallHighlight {
                color: #4C6EF5;
                background-color: rgba(76, 110, 245, 0.12);
                border-radius: 8px;
                padding: 6px 10px;
                font-weight: 600;
            }
            QLabel#paywallBody {
                color: #424B63;
                line-height: 1.65em;
            }
            QLabel#paywallSecondaryHint {
                color: #6A738A;
                font-size: 12px;
            }
            QPushButton#paywallCTAButtonPrimary {
                background-color: #4C6EF5;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-weight: 600;
                padding: 12px 16px;
            }
            QPushButton#paywallCTAButtonPrimary:hover {
                background-color: #3B5BDB;
            }
            QPushButton#paywallCTAButtonPrimary:pressed {
                background-color: #364FC7;
            }
            QPushButton#paywallCTAButtonSecondary {
                background-color: rgba(76, 110, 245, 0.12);
                color: #334173;
                border: none;
                border-radius: 10px;
                font-weight: 600;
                padding: 12px 16px;
            }
            QPushButton#paywallCTAButtonSecondary:hover {
                background-color: rgba(76, 110, 245, 0.18);
            }
            QPushButton#paywallCTAButtonSecondary:pressed {
                background-color: rgba(76, 110, 245, 0.24);
            }
            QPushButton#paywallDismissButton {
                background: transparent;
                color: #5A6579;
                border: none;
                font-weight: 500;
                padding: 6px 12px;
            }
            QPushButton#paywallDismissButton:hover {
                color: #2C3C57;
            }
            QPushButton#paywallCloseButton {
                background: rgba(17, 21, 40, 0.06);
                color: #111528;
                border: none;
                border-radius: 6px;
            }
            QPushButton#paywallCloseButton:hover {
                background: rgba(17, 21, 40, 0.12);
            }
        """
        )

    def _populate_content(self) -> None:
        title = self._copy.get("title") or "AI 算力不足"
        self.setWindowTitle(title)
        self.title_label.setText(title)

        highlight = (self._copy.get("highlight") or "").strip()
        if highlight:
            self.highlight_label.setText(highlight)
            self.highlight_label.show()
        else:
            self.highlight_label.hide()

        body_text = (self._copy.get("body") or "").strip()
        self.body_label.setText(body_text)
        self.body_area.setVisible(bool(body_text))

        # 重建 CTA
        while self.cta_layout.count():
            child = self.cta_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

        if not self._ctas:
            self.cta_container.hide()
        else:
            self.cta_container.show()
            for idx, item in enumerate(self._ctas):
                button = self._create_cta_button(item, primary=(idx == 0))
                self.cta_layout.addWidget(button)

        hint = (self._copy.get("reminder") or "").strip()
        if hint:
            self.secondary_hint.setText(hint)
            self.secondary_hint.show()
        else:
            self.secondary_hint.hide()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        super().closeEvent(event)
        self.dismissed.emit(self._close_reason)
        self._close_reason = "close"

    def _create_cta_button(self, cta_item: Dict[str, Any], *, primary: bool) -> QPushButton:
        label = cta_item.get("label") or "了解更多"
        button = QPushButton(label, self)
        button.setObjectName("paywallCTAButtonPrimary" if primary else "paywallCTAButtonSecondary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(44 if primary else 40)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _, data=cta_item: self.cta_clicked.emit(data))  # type: ignore[arg-type]
        return button

    def _on_close_clicked(self) -> None:
        self._close_reason = "close"
        self.reject()

    def _on_dismiss_clicked(self) -> None:
        self._close_reason = "later"
        self.reject()
