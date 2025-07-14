"""
PyQt6-based settings window with hotkey and API configuration.
"""

import logging
import os
from typing import Dict, Optional, Callable, List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QCheckBox, QComboBox, QLineEdit,
    QGridLayout, QFrame, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

from src.game_wiki_tooltip.config import SettingsManager
from src.game_wiki_tooltip.utils import package_file

logger = logging.getLogger(__name__)


class QtSettingsWindow(QMainWindow):
    """Settings window with hotkey and API configuration"""
    
    # Signals
    settings_applied = pyqtSignal()
    
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self._init_ui()
        self._load_settings()
        
    def _init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("GameWiki Assistant 设置")
        self.setFixedSize(600, 500)
        
        # Set window icon
        try:
            icon_path = package_file("app.ico")
            self.setWindowIcon(QIcon(str(icon_path)))
        except:
            pass
            
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create tabs
        self._create_hotkey_tab()
        self._create_api_tab()
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Apply button
        self.apply_button = QPushButton("保存并应用")
        self.apply_button.setFixedHeight(35)
        self.apply_button.setStyleSheet("""
            QPushButton {
                background-color: #1668dc;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #4096ff;
            }
        """)
        self.apply_button.clicked.connect(self._on_apply)
        button_layout.addWidget(self.apply_button)
        
        # Cancel button
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setFixedHeight(35)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                color: #333;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 14px;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.cancel_button.clicked.connect(self.close)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
    def _create_hotkey_tab(self):
        """Create hotkey configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("全局热键设置")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Hotkey group
        group = QGroupBox()
        group_layout = QVBoxLayout(group)
        
        # Modifiers
        mod_label = QLabel("修饰键：")
        group_layout.addWidget(mod_label)
        
        mod_layout = QHBoxLayout()
        self.ctrl_check = QCheckBox("Ctrl")
        self.shift_check = QCheckBox("Shift")
        self.alt_check = QCheckBox("Alt")
        self.win_check = QCheckBox("Win")
        
        mod_layout.addWidget(self.ctrl_check)
        mod_layout.addWidget(self.shift_check)
        mod_layout.addWidget(self.alt_check)
        mod_layout.addWidget(self.win_check)
        mod_layout.addStretch()
        group_layout.addLayout(mod_layout)
        
        # Main key
        key_layout = QHBoxLayout()
        key_label = QLabel("主键：")
        key_layout.addWidget(key_label)
        
        self.key_combo = QComboBox()
        self.key_combo.setFixedWidth(100)
        # Add A-Z
        for i in range(26):
            self.key_combo.addItem(chr(ord('A') + i))
        # Add F1-F12
        for i in range(1, 13):
            self.key_combo.addItem(f"F{i}")
        key_layout.addWidget(self.key_combo)
        key_layout.addStretch()
        group_layout.addLayout(key_layout)
        
        layout.addWidget(group)
        
        # Tips
        tips_label = QLabel(
            "提示：\n"
            "• 在游戏中按下热键即可呼出AI助手\n"
            "• 部分游戏可能不支持某些热键组合，请选择合适的组合\n"
            "• 建议使用 Ctrl + 字母键 的组合"
        )
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; padding: 10px; background-color: #f8f9fa; border-radius: 6px;")
        layout.addWidget(tips_label)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, "热键设置")
        
    def _create_api_tab(self):
        """Create API configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("API 密钥配置")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # API keys group
        group = QGroupBox()
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(15)
        
        # Google API key
        google_layout = QVBoxLayout()
        google_label = QLabel("Google (Gemini) API Key:")
        google_layout.addWidget(google_label)
        
        self.google_api_input = QLineEdit()
        self.google_api_input.setPlaceholderText("输入您的 Google API 密钥")
        self.google_api_input.setEchoMode(QLineEdit.EchoMode.Password)
        google_layout.addWidget(self.google_api_input)
        
        google_help = QLabel('<a href="https://makersuite.google.com/app/apikey">获取 Google API Key</a>')
        google_help.setOpenExternalLinks(True)
        google_help.setStyleSheet("color: #1668dc;")
        google_layout.addWidget(google_help)
        
        group_layout.addLayout(google_layout)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        group_layout.addWidget(separator)
        
        # Jina API key
        jina_layout = QVBoxLayout()
        jina_label = QLabel("Jina API Key (可选):")
        jina_layout.addWidget(jina_label)
        
        self.jina_api_input = QLineEdit()
        self.jina_api_input.setPlaceholderText("输入您的 Jina API 密钥")
        self.jina_api_input.setEchoMode(QLineEdit.EchoMode.Password)
        jina_layout.addWidget(self.jina_api_input)
        
        jina_help = QLabel('<a href="https://jina.ai/">获取 Jina API Key</a>')
        jina_help.setOpenExternalLinks(True)
        jina_help.setStyleSheet("color: #1668dc;")
        jina_layout.addWidget(jina_help)
        
        group_layout.addLayout(jina_layout)
        
        layout.addWidget(group)
        
        # Tips
        tips_label = QLabel(
            "说明：\n"
            "• Google API Key 用于AI对话和内容生成\n"
            "• Jina API Key 用于高级语义搜索（可选）\n"
            "• API密钥将安全保存在本地配置文件中"
        )
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; padding: 10px; background-color: #f8f9fa; border-radius: 6px;")
        layout.addWidget(tips_label)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, "API配置")
        
    def _load_settings(self):
        """Load current settings"""
        settings = self.settings_manager.get()
        
        # Load hotkey settings
        hotkey = settings.get('hotkey', {})
        modifiers = hotkey.get('modifiers', [])
        self.ctrl_check.setChecked('Ctrl' in modifiers)
        self.shift_check.setChecked('Shift' in modifiers)
        self.alt_check.setChecked('Alt' in modifiers)
        self.win_check.setChecked('Win' in modifiers)
        
        key = hotkey.get('key', 'X')
        index = self.key_combo.findText(key)
        if index >= 0:
            self.key_combo.setCurrentIndex(index)
            
        # Load API settings (check both settings.json and environment variables)
        api = settings.get('api', {})
        
        # Google API key: settings.json -> environment variables
        google_api_key = (
            api.get('google_api_key') or 
            os.getenv('GOOGLE_API_KEY') or 
            os.getenv('GEMINI_API_KEY') or 
            ''
        )
        self.google_api_input.setText(google_api_key)
        
        # Jina API key: settings.json -> environment variables
        jina_api_key = (
            api.get('jina_api_key') or 
            os.getenv('JINA_API_KEY') or 
            ''
        )
        self.jina_api_input.setText(jina_api_key)
        
    def _on_apply(self):
        """Apply settings"""
        # Validate hotkey
        modifiers = []
        if self.ctrl_check.isChecked():
            modifiers.append('Ctrl')
        if self.shift_check.isChecked():
            modifiers.append('Shift')
        if self.alt_check.isChecked():
            modifiers.append('Alt')
        if self.win_check.isChecked():
            modifiers.append('Win')
            
        if not modifiers:
            QMessageBox.warning(self, "提示", "请至少选择一个修饰键")
            return
            
        # Validate API key (check both input and environment variables)
        google_api_key_input = self.google_api_input.text().strip()
        google_api_key_env = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
        
        if not google_api_key_input and not google_api_key_env:
            QMessageBox.warning(
                self, 
                "提示", 
                "请输入 Google API Key，或在环境变量中设置 GOOGLE_API_KEY"
            )
            return
            
        # Update settings (only save what user explicitly entered)
        self.settings_manager.update({
            'hotkey': {
                'modifiers': modifiers,
                'key': self.key_combo.currentText()
            },
            'api': {
                'google_api_key': google_api_key_input,  # Only save user input
                'jina_api_key': self.jina_api_input.text().strip()
            }
        })
        
        # Emit signal
        self.settings_applied.emit()
        
        # Show success message
        QMessageBox.information(self, "成功", "设置已保存并应用")
        
        # Close window
        self.close() 