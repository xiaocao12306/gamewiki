"""
Main application entry point for Gemini Live API Assistant.
PyQt6-based UI with continuous voice recognition and AI audio responses.
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional
import asyncio
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QComboBox, QGroupBox,
    QSplitter, QStatusBar, QMenuBar, QMenu, QMessageBox,
    QInputDialog, QFileDialog, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QFont, QTextCursor, QIcon, QPalette, QColor

from conversation_manager import ConversationManager, ConversationState
from config import AppConfig, get_config, set_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConversationThread(QThread):
    """Thread for running the conversation manager."""
    
    state_changed = pyqtSignal(object)  # ConversationState
    error_occurred = pyqtSignal(str)
    
    def __init__(self, api_key: str, config: AppConfig):
        super().__init__()
        self.api_key = api_key
        self.config = config
        self.manager = None
    
    def run(self):
        """Run the conversation manager in this thread."""
        try:
            self.manager = ConversationManager(
                api_key=self.api_key,
                model_path=str(self.config.get_vosk_model_path(self.config.default_language)),
                language=self.config.default_language,
                voice_name=self.config.live_api.default_voice,
                on_state_change=self._on_state_change,
                on_error=self._on_error
            )
            
            # Start the conversation
            self.manager.start()
            
            # Keep thread alive
            while self.manager and self.manager.state.is_active:
                self.msleep(100)
                
        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def stop_conversation(self):
        """Stop the conversation manager."""
        if self.manager:
            self.manager.stop()
            self.manager = None
    
    def _on_state_change(self, state: ConversationState):
        """Handle state changes from conversation manager."""
        self.state_changed.emit(state)
    
    def _on_error(self, error: str):
        """Handle errors from conversation manager."""
        self.error_occurred.emit(error)


class LiveAPIAssistant(QMainWindow):
    """Main application window for Live API Assistant."""
    
    def __init__(self):
        super().__init__()
        self.config = get_config()
        self.conversation_thread = None
        self.init_ui()
        self.check_api_key()
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle(self.config.ui.window_title)
        self.setGeometry(100, 100, self.config.ui.window_width, self.config.ui.window_height)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create menu bar
        self.create_menu_bar()
        
        # Control panel
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)
        
        # Main content area
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Conversation display
        self.conversation_display = self.create_conversation_display()
        content_splitter.addWidget(self.conversation_display)
        
        # Status panel
        self.status_panel = self.create_status_panel()
        content_splitter.addWidget(self.status_panel)
        
        content_splitter.setSizes([600, 200])
        main_layout.addWidget(content_splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Apply theme
        if self.config.ui.dark_mode:
            self.apply_dark_theme()
    
    def create_menu_bar(self):
        """Create the menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        save_action = QAction("Save Conversation", self)
        save_action.triggered.connect(self.save_conversation)
        file_menu.addAction(save_action)
        
        load_action = QAction("Load Conversation", self)
        load_action.triggered.connect(self.load_conversation)
        file_menu.addAction(load_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Settings menu
        settings_menu = menubar.addMenu("Settings")
        
        api_key_action = QAction("Set API Key", self)
        api_key_action.triggered.connect(self.set_api_key)
        settings_menu.addAction(api_key_action)
        
        config_action = QAction("Edit Configuration", self)
        config_action.triggered.connect(self.edit_configuration)
        settings_menu.addAction(config_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def create_control_panel(self) -> QWidget:
        """Create the control panel."""
        panel = QGroupBox("Controls")
        layout = QHBoxLayout()
        
        # Start/Stop button
        self.start_stop_btn = QPushButton("Start Conversation")
        self.start_stop_btn.clicked.connect(self.toggle_conversation)
        layout.addWidget(self.start_stop_btn)
        
        # Pause/Resume button
        self.pause_resume_btn = QPushButton("Pause Listening")
        self.pause_resume_btn.clicked.connect(self.toggle_listening)
        self.pause_resume_btn.setEnabled(False)
        layout.addWidget(self.pause_resume_btn)
        
        # Language selector
        layout.addWidget(QLabel("Language:"))
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "中文"])
        self.language_combo.currentTextChanged.connect(self.change_language)
        layout.addWidget(self.language_combo)
        
        # Voice selector
        layout.addWidget(QLabel("Voice:"))
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(self.config.live_api.available_voices)
        self.voice_combo.setCurrentText(self.config.live_api.default_voice)
        self.voice_combo.currentTextChanged.connect(self.change_voice)
        layout.addWidget(self.voice_combo)
        
        # Mode selector
        layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(list(self.config.live_api.system_instructions.keys()))
        self.mode_combo.setCurrentText(self.config.live_api.default_mode)
        self.mode_combo.currentTextChanged.connect(self.change_mode)
        layout.addWidget(self.mode_combo)
        
        layout.addStretch()
        
        # Clear button
        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.clicked.connect(self.clear_history)
        layout.addWidget(self.clear_btn)
        
        panel.setLayout(layout)
        return panel
    
    def create_conversation_display(self) -> QWidget:
        """Create the conversation display area."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Conversation")
        title.setFont(QFont(self.config.ui.font_family, self.config.ui.font_size + 2, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Conversation text area
        self.conversation_text = QTextEdit()
        self.conversation_text.setReadOnly(True)
        self.conversation_text.setFont(QFont(self.config.ui.font_family, self.config.ui.font_size))
        layout.addWidget(self.conversation_text)
        
        # Current input display
        self.current_input_label = QLabel("Current Input:")
        layout.addWidget(self.current_input_label)
        
        self.current_input_text = QTextEdit()
        self.current_input_text.setMaximumHeight(60)
        self.current_input_text.setReadOnly(True)
        self.current_input_text.setFont(QFont(self.config.ui.font_family, self.config.ui.font_size))
        layout.addWidget(self.current_input_text)
        
        widget.setLayout(layout)
        return widget
    
    def create_status_panel(self) -> QWidget:
        """Create the status panel."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Status")
        title.setFont(QFont(self.config.ui.font_family, self.config.ui.font_size + 2, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Connection status
        self.connection_label = QLabel("🔴 Disconnected")
        layout.addWidget(self.connection_label)
        
        # Listening status
        self.listening_label = QLabel("🔇 Not Listening")
        layout.addWidget(self.listening_label)
        
        # AI status
        self.ai_status_label = QLabel("💤 Idle")
        layout.addWidget(self.ai_status_label)
        
        # Audio buffer level
        self.buffer_label = QLabel("Buffer: Empty")
        layout.addWidget(self.buffer_label)
        
        # Session info
        self.session_label = QLabel("Session: Not Started")
        layout.addWidget(self.session_label)
        
        layout.addStretch()
        
        # Statistics
        self.stats_label = QLabel("Turns: 0")
        layout.addWidget(self.stats_label)
        
        widget.setLayout(layout)
        return widget
    
    def apply_dark_theme(self):
        """Apply dark theme to the application."""
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        self.setPalette(dark_palette)
    
    def check_api_key(self):
        """Check if API key is available."""
        api_key = self.config.get_api_key()
        if not api_key:
            QMessageBox.warning(
                self,
                "API Key Required",
                "Please set your Gemini API key in Settings > Set API Key"
            )
    
    def toggle_conversation(self):
        """Start or stop the conversation."""
        if self.conversation_thread and self.conversation_thread.isRunning():
            # Stop conversation
            self.stop_conversation()
        else:
            # Start conversation
            self.start_conversation()
    
    def start_conversation(self):
        """Start the conversation."""
        api_key = self.config.get_api_key()
        if not api_key:
            QMessageBox.warning(self, "Error", "API key not set")
            return
        
        # Update UI
        self.start_stop_btn.setText("Stop Conversation")
        self.pause_resume_btn.setEnabled(True)
        self.status_bar.showMessage("Starting conversation...")
        
        # Create and start conversation thread
        self.conversation_thread = ConversationThread(api_key, self.config)
        self.conversation_thread.state_changed.connect(self.on_state_changed)
        self.conversation_thread.error_occurred.connect(self.on_error)
        self.conversation_thread.start()
    
    def stop_conversation(self):
        """Stop the conversation."""
        if self.conversation_thread:
            self.conversation_thread.stop_conversation()
            self.conversation_thread.quit()
            self.conversation_thread.wait()
            self.conversation_thread = None
        
        # Update UI
        self.start_stop_btn.setText("Start Conversation")
        self.pause_resume_btn.setText("Pause Listening")
        self.pause_resume_btn.setEnabled(False)
        self.status_bar.showMessage("Conversation stopped")
        
        # Update status indicators
        self.connection_label.setText("🔴 Disconnected")
        self.listening_label.setText("🔇 Not Listening")
        self.ai_status_label.setText("💤 Idle")
    
    def toggle_listening(self):
        """Pause or resume listening."""
        if not self.conversation_thread or not self.conversation_thread.manager:
            return
        
        manager = self.conversation_thread.manager
        if manager.state.is_listening:
            manager.pause_listening()
            self.pause_resume_btn.setText("Resume Listening")
        else:
            manager.resume_listening()
            self.pause_resume_btn.setText("Pause Listening")
    
    @pyqtSlot(object)
    def on_state_changed(self, state: ConversationState):
        """Handle conversation state changes."""
        # Update connection status
        if state.is_active:
            self.connection_label.setText("🟢 Connected")
        else:
            self.connection_label.setText("🔴 Disconnected")
        
        # Update listening status
        if state.is_listening:
            self.listening_label.setText("🎤 Listening")
        else:
            self.listening_label.setText("🔇 Not Listening")
        
        # Update AI status
        if state.is_ai_speaking:
            self.ai_status_label.setText("🗣️ Speaking")
        else:
            self.ai_status_label.setText("💭 Thinking")
        
        # Update current input
        if state.current_user_text:
            self.current_input_text.setText(state.current_user_text)
        else:
            self.current_input_text.clear()
        
        # Update conversation display
        if state.turns:
            self.update_conversation_display(state.turns)
        
        # Update statistics
        self.stats_label.setText(f"Turns: {len(state.turns)}")
        
        # Update session info
        if state.session_start:
            duration = datetime.now() - state.session_start
            self.session_label.setText(f"Session: {duration.seconds // 60}m {duration.seconds % 60}s")
    
    def update_conversation_display(self, turns):
        """Update the conversation display with turns."""
        html = ""
        for turn in turns[-self.config.ui.max_history_display:]:
            if turn.role == "user":
                color = self.config.ui.user_text_color
                prefix = "👤 You"
            else:
                color = self.config.ui.ai_text_color
                prefix = "🤖 AI"
            
            html += f'<p><span style="color: {color};"><b>{prefix}:</b></span> {turn.text}</p>'
        
        self.conversation_text.setHtml(html)
        
        # Auto-scroll to bottom
        if self.config.ui.auto_scroll:
            cursor = self.conversation_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.conversation_text.setTextCursor(cursor)
    
    @pyqtSlot(str)
    def on_error(self, error: str):
        """Handle errors."""
        QMessageBox.critical(self, "Error", error)
        self.status_bar.showMessage(f"Error: {error}")
    
    def change_language(self, language: str):
        """Change the conversation language."""
        lang_code = "zh" if "中" in language else "en"
        
        if self.conversation_thread and self.conversation_thread.manager:
            self.conversation_thread.manager.set_language(lang_code)
            self.status_bar.showMessage(f"Language changed to {language}")
    
    def change_voice(self, voice: str):
        """Change the AI voice."""
        if self.conversation_thread and self.conversation_thread.manager:
            self.conversation_thread.manager.set_voice(voice)
            self.status_bar.showMessage(f"Voice changed to {voice}")
    
    def change_mode(self, mode: str):
        """Change the conversation mode."""
        # This would require reconnecting with new system instruction
        self.config.live_api.default_mode = mode
        self.status_bar.showMessage(f"Mode changed to {mode} (will apply on next conversation)")
    
    def clear_history(self):
        """Clear the conversation history."""
        self.conversation_text.clear()
        self.current_input_text.clear()
        self.status_bar.showMessage("History cleared")
    
    def save_conversation(self):
        """Save the current conversation."""
        if not self.conversation_thread or not self.conversation_thread.manager:
            QMessageBox.warning(self, "Warning", "No active conversation to save")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Conversation",
            f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt)"
        )
        
        if file_path:
            text = self.conversation_thread.manager.get_conversation_text()
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(text)
            self.status_bar.showMessage(f"Conversation saved to {file_path}")
    
    def load_conversation(self):
        """Load a conversation (for display only)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Conversation",
            "",
            "Text Files (*.txt)"
        )
        
        if file_path:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            self.conversation_text.setPlainText(text)
            self.status_bar.showMessage(f"Conversation loaded from {file_path}")
    
    def set_api_key(self):
        """Set the API key."""
        api_key, ok = QInputDialog.getText(
            self,
            "Set API Key",
            "Enter your Gemini API Key:",
            echo=QInputDialog.EchoMode.Password
        )
        
        if ok and api_key:
            self.config.api_key = api_key
            # Save to environment for this session
            os.environ["GEMINI_API_KEY"] = api_key
            self.status_bar.showMessage("API key set successfully")
    
    def edit_configuration(self):
        """Edit configuration (simplified)."""
        QMessageBox.information(
            self,
            "Configuration",
            "Configuration editing not implemented in this demo.\n"
            "Edit config.json manually and restart the application."
        )
    
    def show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Live API Assistant",
            "Gemini Live API Assistant\n\n"
            "A hybrid voice assistant using:\n"
            "- Local Vosk for speech recognition\n"
            "- Gemini Live API for intelligent responses\n"
            "- Continuous listening for natural conversation\n\n"
            "Version 0.1.0"
        )
    
    def closeEvent(self, event):
        """Handle window close event."""
        if self.conversation_thread and self.conversation_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Conversation is active. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_conversation()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Live API Assistant")
    
    # Create and show main window
    window = LiveAPIAssistant()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()