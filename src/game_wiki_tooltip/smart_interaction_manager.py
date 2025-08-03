"""
Smart Interaction Manager - Handles UI interaction logic in gaming scenarios
Solves mouse click conflicts and hotkey repeat issues when mouse is hidden
"""

import ctypes
import logging
import time
from ctypes import wintypes
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# Windows API constants
CURSOR_SHOWING = 0x00000001
CURSOR_SUPPRESSED = 0x00000002
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

# Windows API function definitions
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD), 
        ("hCursor", wintypes.HANDLE),  # Use HANDLE instead of HCURSOR
        ("ptScreenPos", POINT)
    ]

# Windows API functions
GetCursorInfo = user32.GetCursorInfo
GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
GetCursorInfo.restype = wintypes.BOOL

GetForegroundWindow = user32.GetForegroundWindow
GetForegroundWindow.restype = wintypes.HWND

GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int

GetWindowLongW = user32.GetWindowLongW
GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
GetWindowLongW.restype = wintypes.LONG

SetWindowLongW = user32.SetWindowLongW
SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
SetWindowLongW.restype = wintypes.LONG

class InteractionMode(Enum):
    """Interaction mode enumeration"""
    NORMAL = "normal"           # Normal mode: mouse visible, normal interaction
    GAME_HIDDEN = "game_hidden" # Game mode: mouse hidden, requires passthrough
    GAME_VISIBLE = "game_visible" # Game mode: mouse visible, normal interaction

@dataclass
class MouseState:
    """Mouse state information"""
    is_visible: bool
    is_suppressed: bool
    position: Tuple[int, int]
    cursor_handle: int

@dataclass
class WindowState:
    """Window state information"""
    foreground_window: int
    window_title: str
    is_game_window: bool

class SmartInteractionManager(QObject):
    """
    Smart Interaction Manager
    
    Main features:
    1. Detect mouse show/hide status
    2. Detect current focus window and game state
    3. Manage window mouse passthrough state
    4. Optimize hotkey response logic
    """
    
    # Signal definitions
    interaction_mode_changed = pyqtSignal(object)  # InteractionMode
    mouse_state_changed = pyqtSignal(object)       # MouseState
    # 移除 window_state_changed 信号，改为按需检测
    
    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        
        # Store reference to the assistant controller (not necessarily a QObject)
        self.controller = controller
        
        # State variables
        self.current_mode = InteractionMode.NORMAL
        self.last_mouse_state: Optional[MouseState] = None
        # 移除 last_window_state，改为按需检测
        self.last_hotkey_time = 0
        self.hotkey_double_press_threshold = 0.5  # Double-click hotkey time threshold (seconds)
        
        # Window display protection
        self._window_just_shown = False
        self._window_shown_time = 0
        self.window_protection_duration = 1.0  # Protection duration after window shown (seconds)
        
        # User interaction tracking
        self._user_requested_mouse_visible = False  # Track if user explicitly requested mouse visibility
        
        # Monitor timer
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._monitor_system_state)
        self.monitor_timer.start(100)  # Check every 100ms
        
        # Game window title keywords (can be loaded from config)
        self.game_keywords = [
            'unity', 'unreal', 'steam', 'epic', 'origin',
            'helldivers', 'elden ring', 'civilization', 'dst', 'don\'t starve',
            '游戏', '全屏', 'fullscreen', 'gamemode', 'gaming'
        ]
        
        logger.info("SmartInteractionManager initialized successfully")
    
    def get_mouse_state(self) -> Optional[MouseState]:
        """Get current mouse state"""
        try:
            cursor_info = CURSORINFO()
            cursor_info.cbSize = ctypes.sizeof(CURSORINFO)
            
            if GetCursorInfo(ctypes.byref(cursor_info)):
                is_visible = bool(cursor_info.flags & CURSOR_SHOWING)
                is_suppressed = bool(cursor_info.flags & CURSOR_SUPPRESSED)
                position = (cursor_info.ptScreenPos.x, cursor_info.ptScreenPos.y)
                
                # Safely handle cursor handle - it may be None when mouse is hidden
                cursor_handle = 0  # Default value
                if cursor_info.hCursor is not None:
                    try:
                        cursor_handle = int(cursor_info.hCursor)
                    except (ValueError, TypeError):
                        cursor_handle = 0  # Fallback to 0 if conversion fails
                
                return MouseState(
                    is_visible=is_visible,
                    is_suppressed=is_suppressed,
                    position=position,
                    cursor_handle=cursor_handle
                )
            else:
                logger.warning("GetCursorInfo call failed")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get mouse state: {e}")
            return None
    
    def get_window_state(self) -> Optional[WindowState]:
        """Get current window state"""
        try:
            hwnd = GetForegroundWindow()
            if not hwnd:
                return None
                
            # Get window title
            buffer = ctypes.create_unicode_buffer(512)
            GetWindowTextW(hwnd, buffer, 512)
            window_title = buffer.value or ""
            
            # Check if it's a game window
            is_game_window = self._is_game_window(window_title)
            
            return WindowState(
                foreground_window=hwnd,
                window_title=window_title,
                is_game_window=is_game_window
            )
            
        except Exception as e:
            logger.error(f"Failed to get window state: {e}")
            return None
    
    def _is_game_window(self, window_title: str) -> bool:
        """Check if it's a game window"""
        if not window_title:
            return False
            
        title_lower = window_title.lower()
        
        # 排除应用程序自身的窗口
        app_window_keywords = [
            'gamewiki assistant',
            'gamewiki',
            'game wiki assistant',
            'game wiki'
        ]
        
        # 如果是应用程序自身的窗口，不视为游戏窗口（不记录日志）
        if any(app_keyword in title_lower for app_keyword in app_window_keywords):
            return False
        
        return any(keyword in title_lower for keyword in self.game_keywords)
    
    def _monitor_system_state(self):
        """Monitor system state changes - 监控鼠标状态和游戏窗口焦点"""
        try:
            # Get current states
            mouse_state = self.get_mouse_state()
            window_state = self.get_window_state()
            
            # Check if game window just got focus (and chat window is visible)
            if window_state and window_state.is_game_window:
                # If game window is in focus and user hasn't explicitly requested mouse
                # we should clear the flag to ensure proper passthrough
                if hasattr(self.controller, 'main_window') and self.controller.main_window and self.controller.main_window.isVisible():
                    if self._user_requested_mouse_visible:
                        # Game regained focus, clear user request
                        logger.info("🎮 Game window regained focus, clearing user mouse request")
                        self._user_requested_mouse_visible = False
                        # Force update to re-enable passthrough
                        self.force_update_interaction_mode()
            
            # Check mouse state changes
            if mouse_state and (not self.last_mouse_state or 
                              mouse_state.is_visible != self.last_mouse_state.is_visible or
                              mouse_state.is_suppressed != self.last_mouse_state.is_suppressed):
                self.last_mouse_state = mouse_state
                self.mouse_state_changed.emit(mouse_state)
                logger.debug(f"Mouse state changed: visible={mouse_state.is_visible}, suppressed={mouse_state.is_suppressed}")
                
                # 只在鼠标状态变化时才重新计算交互模式
                # 如果窗口在保护期内，延迟模式更新以避免误判
                if not self.is_window_protected():
                    new_mode = self._calculate_interaction_mode(mouse_state, window_state)
                    if new_mode != self.current_mode:
                        old_mode = self.current_mode
                        self.current_mode = new_mode
                        self.interaction_mode_changed.emit(new_mode)
                        logger.info(f"Interaction mode changed: {old_mode.value} -> {new_mode.value}")
                else:
                    logger.debug("🛡️ Delaying interaction mode update during window protection period")
                
        except Exception as e:
            logger.error(f"Error monitoring system state: {e}")
    
    def _calculate_interaction_mode(self, mouse_state: Optional[MouseState], 
                                  window_state: Optional[WindowState]) -> InteractionMode:
        """Calculate current interaction mode"""
        if not mouse_state or not window_state:
            return InteractionMode.NORMAL
        
        # If current focus is a game window
        if window_state.is_game_window:
            # Mouse is hidden or suppressed
            if not mouse_state.is_visible or mouse_state.is_suppressed:
                return InteractionMode.GAME_HIDDEN
            else:
                return InteractionMode.GAME_VISIBLE
        
        return InteractionMode.NORMAL
    
    def should_enable_mouse_passthrough(self) -> bool:
        """Check if mouse passthrough should be enabled
        
        Mouse passthrough should be enabled when:
        1. In a game environment AND user hasn't explicitly requested mouse visibility
        2. OR in GAME_HIDDEN mode AND mouse is actually hidden
        """
        # Get current window state to check if we're in a game
        window_state = self.get_window_state()
        
        # If in a game window and user hasn't explicitly requested mouse visibility, always enable passthrough
        if window_state and window_state.is_game_window and not self._user_requested_mouse_visible:
            logger.debug("🎮 Game window active and user hasn't requested mouse - enabling passthrough")
            return True
        
        # Otherwise, use the original logic
        if self.current_mode != InteractionMode.GAME_HIDDEN:
            return False
        
        # Check actual mouse state
        mouse_state = self.get_mouse_state()
        if mouse_state and mouse_state.is_visible and self._user_requested_mouse_visible:
            # Mouse is visible because user requested it
            logger.debug("🖱️ Mouse is visible by user request, disabling passthrough")
            return False
        
        return True
    
    def handle_hotkey_press(self, current_chat_visible: bool) -> str:
        """
        Handle hotkey press event
        
        Args:
            current_chat_visible: Whether the chat window (main_window) is currently visible
            
        Returns:
            Suggested action: 'show_chat', 'hide_chat', 'ignore', 'show_mouse'
        """
        current_time = time.time()
        time_since_last = current_time - self.last_hotkey_time
        self.last_hotkey_time = current_time
        
        # 获取当前状态用于调试
        mouse_state = self.get_mouse_state()
        window_state = self.get_window_state()
        
        logger.info(f"Hotkey triggered - mode: {self.current_mode.value}, chat visible: {current_chat_visible}, interval: {time_since_last:.2f}s")
        logger.debug(f"🖱️ Mouse state: visible={mouse_state.is_visible if mouse_state else 'None'}, suppressed={mouse_state.is_suppressed if mouse_state else 'None'}")
        logger.debug(f"🪟 Window state: title='{window_state.window_title if window_state else 'None'}', is_game={window_state.is_game_window if window_state else 'None'}")
        
        # 场景1：聊天窗口不可见 -> 显示聊天窗口
        if not current_chat_visible:
            logger.info("💬 Chat window not visible: Showing chat window")
            return 'show_chat'
        
        # 场景2&3：聊天窗口可见的情况
        
        # 检查窗口是否在保护期内
        if self.is_window_protected():
            logger.info("🛡️ Window is in protection period")
            # 如果在游戏模式且鼠标隐藏，仍然需要显示鼠标
            mouse_state = self.get_mouse_state()
            if self.current_mode == InteractionMode.GAME_HIDDEN or (mouse_state and not mouse_state.is_visible):
                logger.info("🎮 Game mode (mouse hidden) + protection: Still showing mouse for interaction")
                return 'show_mouse'
            else:
                # 保护期内但鼠标已经可见，忽略操作避免误关闭
                logger.info("🛡️ Ignoring hotkey during protection period (mouse already visible)")
                return 'ignore'
        
        # 检查鼠标实际状态，不仅依赖于交互模式
        mouse_state = self.get_mouse_state()
        if self.current_mode == InteractionMode.GAME_HIDDEN or (mouse_state and not mouse_state.is_visible):
            # 游戏模式 + 鼠标隐藏 或 鼠标实际隐藏 -> 显示鼠标，让用户与聊天窗口互动
            logger.info("🎮 Mouse is hidden (mode or actual state): Showing mouse for interaction")
            return 'show_mouse'
            
        elif time_since_last < self.hotkey_double_press_threshold:
            # 双击热键 -> 隐藏聊天窗口
            logger.info(f"⚡ Double-press detected ({time_since_last:.2f}s < {self.hotkey_double_press_threshold}s): Hiding chat window")
            return 'hide_chat'
            
        else:
            # 单击热键 + 聊天窗口可见 + 鼠标可见 -> 隐藏聊天窗口，根据设置处理悬浮窗
            if self.current_mode == InteractionMode.GAME_VISIBLE:
                logger.info("🎮 Game mode (mouse visible): Single press, hiding chat window")
            else:
                logger.info("🖥️ Normal mode: Single press, hiding chat window")
            return 'hide_chat'
    
    def apply_mouse_passthrough(self, widget: QWidget, enable: bool):
        """
        Apply or cancel mouse passthrough for the specified window
        
        Args:
            widget: Target window widget
            enable: Whether to enable mouse passthrough
        """
        try:
            # First set Qt attribute
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enable)
            
            # Then use Windows API for true transparency
            try:
                # Get window handle
                hwnd = widget.winId().__int__()
                
                # Get current extended style
                current_exstyle = GetWindowLongW(hwnd, GWL_EXSTYLE)
                
                if enable:
                    # Add WS_EX_TRANSPARENT to make window truly transparent to mouse
                    new_exstyle = current_exstyle | WS_EX_TRANSPARENT
                    SetWindowLongW(hwnd, GWL_EXSTYLE, new_exstyle)
                    logger.info(f"✅ Enabled TRUE mouse passthrough for window {widget} (hwnd: {hwnd})")
                else:
                    # Remove WS_EX_TRANSPARENT to restore normal mouse interaction
                    new_exstyle = current_exstyle & ~WS_EX_TRANSPARENT
                    SetWindowLongW(hwnd, GWL_EXSTYLE, new_exstyle)
                    logger.info(f"❌ Disabled mouse passthrough for window {widget} (hwnd: {hwnd})")
                    
            except Exception as win_err:
                logger.error(f"Windows API error: {win_err}")
                # Fall back to Qt-only implementation
                
        except Exception as e:
            logger.error(f"Error applying mouse passthrough settings: {e}")
    
    def set_hotkey_double_press_threshold(self, threshold: float):
        """Set hotkey double-click time threshold"""
        self.hotkey_double_press_threshold = max(0.1, min(2.0, threshold))
        logger.info(f"Set hotkey double-click threshold: {self.hotkey_double_press_threshold} seconds") 

    def get_current_game_window(self) -> Optional[str]:
        """获取当前前台窗口的游戏名称（用于热键触发时检测）"""
        try:
            window_state = self.get_window_state()
            if window_state and window_state.is_game_window:
                logger.info(f"🎮 Current game window detected: '{window_state.window_title}'")
                return window_state.window_title
            else:
                # 检查是否是应用自身窗口，如果是则不记录日志
                if window_state and window_state.window_title:
                    title_lower = window_state.window_title.lower()
                    app_window_keywords = [
                        'gamewiki assistant', 'gamewiki', 'game wiki assistant', 'game wiki'
                    ]
                    if not any(app_keyword in title_lower for app_keyword in app_window_keywords):
                        logger.debug(f"🪟 Current window is not a game: '{window_state.window_title}'")
                return None
        except Exception as e:
            logger.error(f"Failed to get current game window: {e}")
            return None
    
    def mark_window_just_shown(self):
        """Mark that the chat window has just been shown"""
        self._window_just_shown = True
        self._window_shown_time = time.time()
        logger.info(f"🛡️ Window display protection activated for {self.window_protection_duration}s")
    
    def set_user_requested_mouse_visible(self, visible: bool):
        """Set whether the user has explicitly requested mouse visibility"""
        self._user_requested_mouse_visible = visible
        logger.info(f"👤 User requested mouse visible: {visible}")
        
        # Force update interaction mode to apply the new passthrough state
        self.force_update_interaction_mode()
    
    def is_window_protected(self) -> bool:
        """Check if the window is still in protection period"""
        if not self._window_just_shown:
            return False
        
        current_time = time.time()
        elapsed = current_time - self._window_shown_time
        
        if elapsed > self.window_protection_duration:
            self._window_just_shown = False
            logger.debug("🛡️ Window display protection expired")
            return False
        
        return True
    
    def force_update_interaction_mode(self):
        """Force update interaction mode and window passthrough state
        
        This is useful after showing mouse cursor to ensure window state is correct
        """
        logger.info("🔄 Force updating interaction mode and window passthrough state")
        
        # Get current states
        mouse_state = self.get_mouse_state()
        window_state = self.get_window_state()
        
        if not mouse_state or not window_state:
            logger.warning("Cannot update interaction mode: missing state information")
            return
        
        # Recalculate interaction mode
        new_mode = self._calculate_interaction_mode(mouse_state, window_state)
        old_mode = self.current_mode
        
        # Always emit the signal to ensure passthrough state is updated
        # even if mode hasn't changed (mouse state might have changed)
        self.current_mode = new_mode
        self.interaction_mode_changed.emit(new_mode)
        
        if new_mode != old_mode:
            logger.info(f"🎮 Interaction mode force updated: {old_mode.value} -> {new_mode.value}")
        else:
            logger.info(f"🎮 Interaction mode unchanged but passthrough state may have updated: {new_mode.value}") 