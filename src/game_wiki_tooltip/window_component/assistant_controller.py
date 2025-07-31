"""
Assistant controller for managing chat window and game context.
"""

import logging
from enum import Enum
from typing import Optional


from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import QApplication


class WindowMode(Enum):
    """Window display modes"""
    CHAT = "chat"
    WIKI = "wiki"


class MessageType(Enum):
    """Chat message types"""
    USER_QUERY = "user_query"
    AI_RESPONSE = "ai_response"
    SYSTEM_MESSAGE = "system_message"
    STATUS = "status"
    ERROR = "error"


class TransitionMessages:
    """Transition state messages"""
    QUERY_RECEIVED = "Processing your query..."


class WindowState(Enum):
    """Window state enumeration"""
    CHAT_ONLY = "chat_only"      # Only show input box
    FULL_CONTENT = "full_content" # Show all content
    WEBVIEW = "webview"          # WebView2 form


class AssistantController:
    """Controller for the assistant system"""
    
    def __init__(self, settings_manager=None):
        self.settings_manager = settings_manager
        self.main_window = None
        self.current_mode = WindowMode.CHAT
        self.current_game_window = None  # Record current game window title
        self._precreated = False  # Track if window has been pre-created
        self.previous_window_state = None  # Track previous window state for restoration
        
    def set_current_game_window(self, game_window_title: str):
        """Set current game window title"""
        self.current_game_window = game_window_title
        
        # Pass game window information to main window
        if self.main_window:
            self.main_window.set_current_game_window(game_window_title)
        
        logger = logging.getLogger(__name__)
        logger.info(f"🎮 Recording game window: '{game_window_title}'")

    def precreate_chat_window(self):
        """Pre-create chat window for faster first-time response"""
        logger = logging.getLogger(__name__)
        
        if self._precreated or self.main_window:
            logger.info("Chat window already created or pre-created")
            return
            
        try:
            logger.info("Pre-creating chat window...")
            
            # Import here to avoid circular import
            from ..unified_window import UnifiedAssistantWindow
            
            # Create window but keep it hidden
            self.main_window = UnifiedAssistantWindow(self.settings_manager)
            
            # Set precreating mode to prevent geometry saving during initialization
            self.main_window.set_precreating_mode(True)
            
            self.main_window.query_submitted.connect(self.handle_query)
            self.main_window.wiki_page_found.connect(self.handle_wiki_page_found)
            
            # CRITICAL FIX: Ensure task buttons are created during pre-creation
            logger.info(f"🔍 [DEBUG] Force loading shortcuts for pre-created window...")
            try:
                # Call _load_deferred_content directly since showEvent won't be triggered
                self.main_window._load_deferred_content()
                self.main_window.shortcuts_loaded = True  # Mark as loaded
                button_count = len(getattr(self.main_window, 'game_task_buttons', {}))
                logger.info(f"✅ [DEBUG] Shortcuts loaded for pre-created window, task buttons: {button_count}")
            except Exception as e:
                logger.error(f"❌ [DEBUG] Failed to load shortcuts for pre-created window: {e}")
                import traceback
                traceback.print_exc()
            
            # If we already have a game context, set it AFTER shortcuts are loaded
            try:
                if self.current_game_window:
                    self.main_window.set_current_game_window(self.current_game_window)
                    logger.info(f"✅ [DEBUG] Set game context for pre-created window: {self.current_game_window}")
            except Exception as e:
                logger.error(f"❌ [DEBUG] Failed to set game context for pre-created window: {e}")
            
            # Important: Keep window hidden
            self.main_window.hide()
            
            # Mark as pre-created
            self._precreated = True
            logger.info("✅ Chat window pre-created and hidden")
            
        except Exception as e:
            logger.error(f"Failed to pre-create chat window: {e}")
            import traceback
            traceback.print_exc()
            self.main_window = None
            self._precreated = False

    def expand_to_chat(self):
        """Show pre-created chat window"""
        logger = logging.getLogger(__name__)
        logger.info("expand_to_chat() called")
        
        # Check if window is pre-created
        if not self.main_window:
            logger.error("Main window not pre-created! Creating now...")
            # Fallback: create window now if not pre-created
            self.precreate_chat_window()
            
        if not self.main_window:
            logger.error("Failed to create main window!")
            return
            
        # Clear precreating mode before showing window
        if hasattr(self.main_window, '_is_precreating') and self.main_window._is_precreating:
            self.main_window.set_precreating_mode(False)
            logger.info("Cleared precreating mode for main window")
            
        # Update game context if needed
        if self.current_game_window:
            logger.info(f"🎮 [DEBUG] Updating game window: '{self.current_game_window}'")
            self.main_window.set_current_game_window(self.current_game_window)

        # Set window initial opacity to 0 (prepare fade-in animation)
        self.main_window.setWindowOpacity(0.0)

        # Show window
        logger.info("Showing main window with fade-in animation")
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

        # Apply window layout based on current state
        if not self.main_window.has_switched_state:
            logger.info("Applying CHAT_ONLY layout for window with no state switch")
            self.main_window.switch_to_chat_only()
        elif self.previous_window_state == WindowState.WEBVIEW:
            # Restore to webview state if that was the previous state
            logger.info("Restoring to previous WEBVIEW state")
            self.main_window.switch_to_webview()
        
        # Create fade-in animation
        self._fade_in_animation = QPropertyAnimation(self.main_window, b"windowOpacity")
        self._fade_in_animation.setDuration(100)  # 100ms fade-in animation
        self._fade_in_animation.setStartValue(0.0)
        self._fade_in_animation.setEndValue(1.0)
        self._fade_in_animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_in_animation.start()
        
        # Restore geometry
        self.main_window.restore_geometry()

        # Ensure window is within screen range
        screen = QApplication.primaryScreen().geometry()
        window_rect = self.main_window.geometry()

        # Adjust position to ensure window is visible
        x = max(10, min(window_rect.x(), screen.width() - window_rect.width() - 10))
        y = max(30, min(window_rect.y(), screen.height() - window_rect.height() - 40))

        if x != window_rect.x() or y != window_rect.y():
            self.main_window.move(x, y)
            logger.info(f"Adjusted window position to ensure visibility: ({x}, {y})")

        self.current_mode = WindowMode.CHAT
        logger.info("expand_to_chat() completed")
        
    def handle_wiki_page_found(self, url: str, title: str):
        """Handle signal when real wiki page is found (basic implementation, subclasses can override)"""
        logger = logging.getLogger(__name__)
        logger.info(f"🔗 AssistantController received wiki page signal: {title} -> {url}")
        # Basic implementation: do nothing, subclasses (IntegratedAssistantController) will override this method
    
    def refresh_shortcuts(self):
        """Refresh shortcut buttons"""
        if self.main_window:
            self.main_window.load_shortcuts()
        
    def handle_query(self, query: str, mode: str = "auto"):
        """Handle user query"""
        # Add user message to chat
        self.main_window.chat_view.add_message(
            MessageType.USER_QUERY,
            query
        )
        
        # Reset auto scroll state, ensure auto scroll is enabled when new query
        self.main_window.chat_view.reset_auto_scroll()
        
        # Show initial processing status
        self.main_window.chat_view.show_status(TransitionMessages.QUERY_RECEIVED)
            
    def hide_all(self):
        """Hide all window_component"""
        if self.main_window:
            try:
                # Save current window state before hiding
                self.previous_window_state = self.main_window.current_state
                self.main_window.save_geometry()
                self.main_window._persist_geometry_if_needed()
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to save geometry when hiding all window_component: {e}")
            self.main_window.hide()
        self.current_mode = None
        
    def is_visible(self):
        """Check if any window is visible"""
        return self.main_window and self.main_window.isVisible()
