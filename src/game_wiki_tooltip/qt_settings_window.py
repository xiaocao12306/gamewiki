"""
PyQt6-based settings window with hotkey and API configuration.
"""

import logging
import os
from typing import Dict, Optional, Callable, List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QCheckBox, QComboBox, QLineEdit,
    QGridLayout, QFrame, QMessageBox, QGroupBox, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

from src.game_wiki_tooltip.config import SettingsManager
from src.game_wiki_tooltip.utils import package_file
from src.game_wiki_tooltip.i18n import init_translations, get_translation_manager, t

logger = logging.getLogger(__name__)


class ApiKeyMissingDialog(QDialog):
    """自定义对话框，用于处理API key缺失的通知"""
    
    def __init__(self, missing_keys, parent=None):
        super().__init__(parent)
        self.missing_keys = missing_keys
        self.dont_remind = False
        self.open_settings = False
        self._init_ui()
        
    def _init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("GameWiki Assistant")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.setFixedSize(400, 220)
        
        # 主布局
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("AI Features Unavailable")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #d32f2f;")
        layout.addWidget(title_label)
        
        # 消息内容
        message = (
            "AI guide features require both API keys to function properly:\n\n"
            f"Missing: {', '.join(self.missing_keys)}\n\n"
            "⚠️ Note: Gemini API alone cannot provide high-quality RAG functionality.\n"
            "Jina vector search is essential for complete AI guide features.\n\n"
            "You can still use Wiki search without API keys."
        )
        
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("font-size: 11px; line-height: 1.4;")
        layout.addWidget(message_label)
        
        # "不再提醒" 复选框
        self.dont_remind_checkbox = QCheckBox("Don't remind me again (Wiki search only)")
        self.dont_remind_checkbox.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.dont_remind_checkbox)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # 配置按钮
        config_button = QPushButton("Configure API Keys")
        config_button.setStyleSheet("""
            QPushButton {
                background-color: #1976d2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
        """)
        config_button.clicked.connect(self._on_configure_clicked)
        button_layout.addWidget(config_button)
        
        # 稍后按钮
        later_button = QPushButton("Maybe Later")
        later_button.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        later_button.clicked.connect(self._on_later_clicked)
        button_layout.addWidget(later_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
    def _on_configure_clicked(self):
        """用户点击配置按钮"""
        self.dont_remind = self.dont_remind_checkbox.isChecked()
        self.open_settings = True
        self.accept()
        
    def _on_later_clicked(self):
        """用户点击稍后按钮"""
        self.dont_remind = self.dont_remind_checkbox.isChecked()
        self.open_settings = False
        self.accept()


class QtSettingsWindow(QMainWindow):
    """Settings window with hotkey and API configuration"""
    
    # Signals
    settings_applied = pyqtSignal()
    
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        
        # Initialize translation manager based on current settings
        settings = self.settings_manager.get()
        current_language = settings.get('language', 'en')
        init_translations(current_language)
        
        self._init_ui()
        self._load_settings()
        
    def _init_ui(self):
        """Initialize UI"""
        self.setWindowTitle(t("settings_title"))
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
        
        # Create tabs - hotkey first, language last
        self._create_hotkey_tab()
        self._create_api_tab()
        self._create_language_tab()
        
        # Set default tab to hotkey (first tab)
        self.tab_widget.setCurrentIndex(0)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Apply button
        self.apply_button = QPushButton(t("apply_button"))
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
        self.cancel_button = QPushButton(t("cancel_button"))
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
        
    def _create_language_tab(self):
        """Create language configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel(t("language_title"))
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Language group
        group = QGroupBox()
        group_layout = QVBoxLayout(group)
        
        # Language selection
        lang_layout = QHBoxLayout()
        lang_label = QLabel(t("language_label"))
        lang_layout.addWidget(lang_label)
        
        self.language_combo = QComboBox()
        self.language_combo.setFixedWidth(200)
        
        # Populate language options
        from src.game_wiki_tooltip.i18n import get_supported_languages
        supported_languages = get_supported_languages()
        for lang_code, lang_name in supported_languages.items():
            self.language_combo.addItem(lang_name, lang_code)
        
        # Connect language change signal
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        
        lang_layout.addWidget(self.language_combo)
        lang_layout.addStretch()
        group_layout.addLayout(lang_layout)
        
        layout.addWidget(group)
        
        # Tips
        tips_label = QLabel(t("language_tips"))
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; padding: 10px; background-color: #f8f9fa; border-radius: 6px;")
        layout.addWidget(tips_label)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, t("language_tab"))
        
    def switch_to_api_tab(self):
        """切换到API配置标签页"""
        # API配置标签页是第二个，索引为1
        self.tab_widget.setCurrentIndex(1)
        
    def _create_hotkey_tab(self):
        """Create hotkey configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel(t("hotkey_title"))
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Hotkey group
        group = QGroupBox()
        group_layout = QVBoxLayout(group)
        
        # Modifiers
        mod_label = QLabel(t("modifiers_label"))
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
        key_label = QLabel(t("main_key_label"))
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
        tips_label = QLabel(t("hotkey_tips"))
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; padding: 10px; background-color: #f8f9fa; border-radius: 6px;")
        layout.addWidget(tips_label)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, t("hotkey_tab"))
        
    def _create_api_tab(self):
        """Create API configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel(t("api_title"))
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # API keys group
        group = QGroupBox()
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(15)
        
        # Google API key
        google_layout = QVBoxLayout()
        google_label = QLabel(t("google_api_label"))
        google_layout.addWidget(google_label)
        
        self.google_api_input = QLineEdit()
        self.google_api_input.setPlaceholderText(t("google_api_placeholder"))
        self.google_api_input.setEchoMode(QLineEdit.EchoMode.Password)
        google_layout.addWidget(self.google_api_input)
        
        google_help = QLabel(f'<a href="https://makersuite.google.com/app/apikey">{t("google_api_help")}</a>')
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
        jina_label = QLabel(t("jina_api_label"))
        jina_layout.addWidget(jina_label)
        
        self.jina_api_input = QLineEdit()
        self.jina_api_input.setPlaceholderText(t("jina_api_placeholder"))
        self.jina_api_input.setEchoMode(QLineEdit.EchoMode.Password)
        jina_layout.addWidget(self.jina_api_input)
        
        jina_help = QLabel(f'<a href="https://jina.ai/">{t("jina_api_help")}</a>')
        jina_help.setOpenExternalLinks(True)
        jina_help.setStyleSheet("color: #1668dc;")
        jina_layout.addWidget(jina_help)
        
        group_layout.addLayout(jina_layout)
        
        layout.addWidget(group)
        
        # Tips
        tips_label = QLabel(t("api_tips"))
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("color: #666; padding: 10px; background-color: #f8f9fa; border-radius: 6px;")
        layout.addWidget(tips_label)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, t("api_tab"))
        
    def _on_language_changed(self):
        """Handle language selection change"""
        current_index = self.language_combo.currentIndex()
        if current_index >= 0:
            selected_language = self.language_combo.itemData(current_index)
            
            # Update translation manager
            from src.game_wiki_tooltip.i18n import set_language
            set_language(selected_language)
            
            # Update all UI text
            self._update_ui_text()
    
    def _update_ui_text(self):
        """Update all UI text with current language"""
        # Window title
        self.setWindowTitle(t("settings_title"))
        
        # Tab titles
        self.tab_widget.setTabText(0, t("language_tab"))
        self.tab_widget.setTabText(1, t("hotkey_tab"))
        self.tab_widget.setTabText(2, t("api_tab"))
        
        # Buttons
        self.apply_button.setText(t("apply_button"))
        self.cancel_button.setText(t("cancel_button"))
        
        # Language tab
        # We need to access the widgets in the language tab
        language_tab = self.tab_widget.widget(0)
        language_widgets = language_tab.findChildren(QLabel)
        if len(language_widgets) >= 2:
            language_widgets[0].setText(t("language_title"))  # Title
            language_widgets[1].setText(t("language_label"))  # Language label
            language_widgets[2].setText(t("language_tips"))   # Tips
        
        # Hotkey tab
        hotkey_tab = self.tab_widget.widget(1)
        hotkey_widgets = hotkey_tab.findChildren(QLabel)
        if len(hotkey_widgets) >= 3:
            hotkey_widgets[0].setText(t("hotkey_title"))      # Title
            hotkey_widgets[1].setText(t("modifiers_label"))   # Modifiers
            hotkey_widgets[2].setText(t("main_key_label"))    # Main key
            hotkey_widgets[3].setText(t("hotkey_tips"))       # Tips
        
        # API tab
        api_tab = self.tab_widget.widget(2)
        api_widgets = api_tab.findChildren(QLabel)
        if len(api_widgets) >= 5:
            api_widgets[0].setText(t("api_title"))            # Title
            api_widgets[1].setText(t("google_api_label"))     # Google API
            api_widgets[2].setText(f'<a href="https://makersuite.google.com/app/apikey">{t("google_api_help")}</a>')
            api_widgets[3].setText(t("jina_api_label"))       # Jina API
            api_widgets[4].setText(f'<a href="https://jina.ai/">{t("jina_api_help")}</a>')
            api_widgets[5].setText(t("api_tips"))             # Tips
        
        # Update placeholders
        self.google_api_input.setPlaceholderText(t("google_api_placeholder"))
        self.jina_api_input.setPlaceholderText(t("jina_api_placeholder"))
        
    def _load_settings(self):
        """Load current settings"""
        settings = self.settings_manager.get()
        
        # Load language settings
        current_language = settings.get('language', 'en')
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == current_language:
                self.language_combo.setCurrentIndex(i)
                break
        
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
        # Get selected language
        selected_language = self.language_combo.itemData(self.language_combo.currentIndex())
        
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
            QMessageBox.warning(self, t("warning"), t("validation_modifier_required"))
            return
            
        # Validate API keys (check both input and environment variables)
        google_api_key_input = self.google_api_input.text().strip()
        google_api_key_env = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
        google_api_key = google_api_key_input or google_api_key_env
        
        jina_api_key_input = self.jina_api_input.text().strip()
        jina_api_key_env = os.getenv('JINA_API_KEY')
        jina_api_key = jina_api_key_input or jina_api_key_env
        
        # Check if both API keys are available
        missing_keys = []
        if not google_api_key:
            missing_keys.append("Google/Gemini API Key")
        if not jina_api_key:
            missing_keys.append("Jina API Key")
        
        if missing_keys:
            # Check if user previously chose "don't remind me again"
            current_settings = self.settings_manager.get()
            dont_remind = current_settings.get('dont_remind_api_missing', False)
            
            if not dont_remind:
                # 显示友好的对话框
                dialog = ApiKeyMissingDialog(missing_keys, parent=self)
                dialog.exec()
                
                # 处理用户的选择
                if dialog.dont_remind:
                    logger.info("User selected 'Don't remind me again' in settings")
                    self.settings_manager.update({'dont_remind_api_missing': True})
                
                if dialog.open_settings:
                    # 用户选择配置API keys，直接切换到API配置标签页
                    logger.info("User chose to configure API keys, switching to API tab")
                    self.switch_to_api_tab()
                    return
                else:
                    # 用户选择稍后配置，继续保存设置但显示受限模式信息
                    logger.info("User chose to continue without API keys")
                    # 继续执行保存设置的逻辑
            else:
                # 用户之前选择了"不再提醒"，静默继续
                logger.info("User previously chose 'Don't remind me again', proceeding without API key validation")
                # 继续执行保存设置的逻辑
            
        # Update settings (only save what user explicitly entered)
        self.settings_manager.update({
            'language': selected_language,
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
        
        # Show success message (different based on API key status)
        if missing_keys:
            success_msg = (
                f"Settings saved successfully!\n\n"
                f"⚠️ Running in limited mode (Wiki search only)\n"
                f"Missing API keys: {', '.join(missing_keys)}\n\n"
                f"Configure complete API keys to enable AI guide features."
            )
        else:
            success_msg = t("validation_settings_saved")
        
        QMessageBox.information(self, t("success"), success_msg)
        
        # Close window
        self.close() 