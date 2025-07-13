"""
PyQt6-compatible global hotkey management.
"""

import logging
import ctypes
from typing import Callable, Dict, Final
from ctypes import wintypes

import win32con
import win32api

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from src.game_wiki_tooltip.config import SettingsManager

MOD_MAP: Final[Dict[str, int]] = {
    "Alt": win32con.MOD_ALT,
    "Ctrl": win32con.MOD_CONTROL,
    "Shift": win32con.MOD_SHIFT,
    "Win": win32con.MOD_WIN,
}

logger = logging.getLogger(__name__)

user32 = ctypes.WinDLL('user32', use_last_error=True)

# Windows API functions
RegisterHotKey = user32.RegisterHotKey
RegisterHotKey.argtypes = [wintypes.HWND, wintypes.INT, wintypes.UINT, wintypes.UINT]
RegisterHotKey.restype = wintypes.BOOL

UnregisterHotKey = user32.UnregisterHotKey
UnregisterHotKey.argtypes = [wintypes.HWND, wintypes.INT]
UnregisterHotKey.restype = wintypes.BOOL


class HotkeyError(Exception):
    """Hotkey related errors"""
    pass


class QtHotkeyManager(QObject):
    """PyQt6-based global hotkey manager"""
    
    # Signals
    hotkey_triggered = pyqtSignal()
    
    def __init__(self, settings_mgr: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_mgr = settings_mgr
        self._registered = False
        self._hotkey_id = 1
        logger.info("QtHotkeyManager initialized")
        
    def _get_virtual_key(self, key: str) -> int:
        """Convert key name to virtual key code"""
        # Handle function keys
        if key.startswith('F') and key[1:].isdigit():
            return win32con.VK_F1 + int(key[1:]) - 1
            
        # Handle letter keys
        if len(key) == 1 and key.isalpha():
            return ord(key.upper())
            
        # Handle number keys
        if key.isdigit():
            return ord(key)
            
        # Handle special keys
        special_keys = {
            'Space': win32con.VK_SPACE,
            'Enter': win32con.VK_RETURN,
            'Tab': win32con.VK_TAB,
            'Escape': win32con.VK_ESCAPE,
            'Backspace': win32con.VK_BACK,
            'Delete': win32con.VK_DELETE,
            'Insert': win32con.VK_INSERT,
            'Home': win32con.VK_HOME,
            'End': win32con.VK_END,
            'PageUp': win32con.VK_PRIOR,
            'PageDown': win32con.VK_NEXT,
            'Up': win32con.VK_UP,
            'Down': win32con.VK_DOWN,
            'Left': win32con.VK_LEFT,
            'Right': win32con.VK_RIGHT,
        }
        
        if key in special_keys:
            return special_keys[key]
            
        logger.error(f"Unknown key: {key}")
        raise HotkeyError(f"Unknown key: {key}")
        
    def register(self):
        """Register global hotkey"""
        if self._registered:
            logger.info("Hotkey already registered, unregistering first")
            self.unregister()
            
        try:
            # Get hotkey settings
            settings = self.settings_mgr.get()
            hotkey_settings = settings.get('hotkey', {})
            
            # Calculate modifier flags
            mod_flags = 0
            modifiers = hotkey_settings.get('modifiers', [])
            if not modifiers:
                raise HotkeyError("Please select at least one modifier key (Ctrl/Alt/Shift/Win)")
                
            for modifier in modifiers:
                if modifier in MOD_MAP:
                    mod_flags |= MOD_MAP[modifier]
                    
            # Get virtual key code
            key = hotkey_settings.get('key', 'X')
            if not key:
                raise HotkeyError("Please select a main key")
                
            vk = self._get_virtual_key(key)
            
            logger.info(f"Registering hotkey: modifiers={modifiers}, key={key}, mod_flags={mod_flags}, vk={vk}")
            
            # Register hotkey
            if not RegisterHotKey(None, self._hotkey_id, mod_flags, vk):
                error = ctypes.get_last_error()
                if error == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
                    logger.warning("Hotkey already registered")
                    self._registered = True
                    return
                else:
                    logger.error(f"Failed to register hotkey, error code: {error}")
                    raise HotkeyError(f"Failed to register hotkey, error code: {error}")
                    
            self._registered = True
            logger.info("Hotkey registered successfully")
            
        except HotkeyError:
            raise
        except Exception as e:
            logger.error(f"Error registering hotkey: {e}")
            raise HotkeyError(f"Unknown error registering hotkey: {str(e)}")
            
    def unregister(self):
        """Unregister global hotkey"""
        if not self._registered:
            return
            
        try:
            if not UnregisterHotKey(None, self._hotkey_id):
                error = ctypes.get_last_error()
                logger.error(f"Failed to unregister hotkey, error code: {error}")
            self._registered = False
            logger.info("Hotkey unregistered successfully")
        except Exception as e:
            logger.error(f"Failed to unregister hotkey: {e}")
            
    def handle_hotkey_message(self, msg):
        """Handle WM_HOTKEY message"""
        logger.debug(f"Received hotkey message: wParam={msg.wParam}, expected_id={self._hotkey_id}")
        if msg.wParam == self._hotkey_id:
            logger.info("Hotkey triggered")
            self.hotkey_triggered.emit()
        else:
            logger.debug(f"Hotkey ID mismatch: received={msg.wParam}, expected={self._hotkey_id}")
            
    def get_hotkey_string(self) -> str:
        """Get hotkey string representation"""
        settings = self.settings_mgr.get()
        hotkey_settings = settings.get('hotkey', {})
        modifiers = hotkey_settings.get('modifiers', [])
        key = hotkey_settings.get('key', 'X')
        return ' + '.join(modifiers + [key]) 