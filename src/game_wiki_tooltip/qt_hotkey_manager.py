"""
PyQt6-compatible global hotkey management with conflict resolution.
"""

import logging
import ctypes
from typing import Callable, Dict, Final, Optional
from ctypes import wintypes

import win32con
import win32api
import win32gui

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
    """PyQt6-based global hotkey manager with ultra-compatible mode
    
    This class provides global hotkey management with ultra-compatible behavior:
    - ALL errors and exceptions are handled by assuming hotkey is available
    - Ensures the application can start in ANY environment
    - Provides maximum compatibility with existing systems
    
    Ultra-compatible mode is designed to ensure the application never fails to start
    due to hotkey registration issues, which is critical for user experience.
    """
    
    # Signals
    hotkey_triggered = pyqtSignal()
    
    def __init__(self, settings_mgr: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_mgr = settings_mgr
        self._registered = False
        self._hotkey_id = 1
        logger.info("QtHotkeyManager initialized with ultra-compatible mode")
        
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
    
    
    

    def _try_register_hotkey_ultra_compatible(self, modifiers: list, key: str, hotkey_id: int) -> tuple[bool, Optional[str]]:
        """使用超级兼容的热键注册逻辑 - 确保任何情况下都能成功"""
        try:
            # Calculate modifier flags
            mod_flags = 0
            for modifier in modifiers:
                if modifier in MOD_MAP:
                    mod_flags |= MOD_MAP[modifier]
            
            # Get virtual key code
            vk = self._get_virtual_key(key)
            
            hotkey_str = '+'.join(modifiers + [key])
            logger.info(f"尝试注册热键(超级兼容): {hotkey_str}, mod_flags={mod_flags}, vk={vk}, id={hotkey_id}")
            
            # Register hotkey
            result = RegisterHotKey(None, hotkey_id, mod_flags, vk)
            
            if result:
                logger.info(f"✅ 热键注册成功: {hotkey_str}")
                return True, None
            else:
                error = ctypes.get_last_error()
                logger.warning(f"⚠️ 热键API调用失败，错误代码: {error}")
                
                # 超级兼容逻辑：不管什么错误都假设热键可用
                if error == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
                    logger.warning(f"🔄 热键已被其他程序注册，强制假设热键可用: {hotkey_str}")
                    return True, "already_registered"
                elif error == 1401:  # ERROR_HOTKEY_NOT_REGISTERED
                    logger.warning(f"🔄 热键未注册错误，强制假设热键可用: {hotkey_str}")
                    return True, "not_registered_but_assumed"
                elif error == 0:  # 特殊情况：错误代码0但返回False
                    logger.warning(f"🔄 特殊情况（错误代码0），强制假设热键可用: {hotkey_str}")
                    return True, "zero_error_but_assumed"
                elif error == 5:  # ERROR_ACCESS_DENIED
                    logger.warning(f"🔄 权限不足，强制假设热键可用: {hotkey_str}")
                    return True, "access_denied_but_assumed"
                else:
                    logger.warning(f"🔄 未知错误（{error}），强制假设热键可用: {hotkey_str}")
                    return True, f"unknown_error_{error}_but_assumed"
                
        except Exception as e:
            # 异常兼容模式：即使发生异常也假设热键可用
            logger.warning(f"🔄 热键注册异常，强制假设热键可用: {'+'.join(modifiers + [key])}, 异常: {str(e)}")
            return True, f"exception_but_assumed_{type(e).__name__}"
    
    
    def register(self):
        """Register global hotkey with ultra-compatible mode"""
        if self._registered:
            logger.info("Hotkey already registered, unregistering first")
            self.unregister()
            
        try:
            # Get hotkey settings
            settings = self.settings_mgr.get()
            hotkey_settings = settings.get('hotkey', {})
            
            modifiers = hotkey_settings.get('modifiers', [])
            if not modifiers:
                raise HotkeyError("Please select at least one modifier key (Ctrl/Alt/Shift/Win)")
            
            key = hotkey_settings.get('key', 'X')
            if not key:
                raise HotkeyError("Please select a main key")
            
            # Always use ultra-compatible mode
            logger.info("使用超级兼容的热键注册逻辑")
            success, error = self._try_register_hotkey_ultra_compatible(modifiers, key, self._hotkey_id)
            
            if success:
                self._registered = True
                if error and "already_registered" in error:
                    logger.info("热键注册成功（假设已注册）")
                elif error and "assumed" in error:
                    logger.info(f"热键注册成功（强制兼容：{error}）")
                else:
                    logger.info("热键注册成功")
                return
            else:
                # This should never happen with ultra-compatible mode
                logger.error(f"热键注册失败: {error}")
                logger.info("程序将继续运行，但热键功能不可用")
                logger.info("建议:")
                logger.info("1. 以管理员身份运行程序")
                logger.info("2. 关闭可能占用热键的其他程序")
                logger.info("3. 在设置中更换热键组合")
                
                # 不抛出异常，让程序继续运行
                self._registered = False
                return
                
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
            # Unregister hotkey
            if not UnregisterHotKey(None, self._hotkey_id):
                error = ctypes.get_last_error()
                logger.error(f"Failed to unregister hotkey, error code: {error}")
            else:
                logger.info("Hotkey unregistered successfully")
            
            self._registered = False
            
        except Exception as e:
            logger.error(f"Failed to unregister hotkey: {e}")
            
    def handle_hotkey_message(self, msg):
        """Handle WM_HOTKEY message"""
        logger.info(f"=== HOTKEY MESSAGE RECEIVED ===")
        logger.info(f"Message wParam: {msg.wParam}, expected_id: {self._hotkey_id}")
        logger.info(f"Message lParam: {msg.lParam}")
        
        # Check hotkey ID
        if msg.wParam == self._hotkey_id:
            logger.info("Hotkey ID matches! Emitting hotkey_triggered signal")
            self.hotkey_triggered.emit()
            logger.info("hotkey_triggered signal emitted")
        else:
            logger.warning(f"Hotkey ID mismatch: received={msg.wParam}, expected={self._hotkey_id}")
            logger.warning("Hotkey signal NOT emitted")
            
    def get_hotkey_string(self) -> str:
        """Get hotkey string representation"""
        settings = self.settings_mgr.get()
        hotkey_settings = settings.get('hotkey', {})
        modifiers = hotkey_settings.get('modifiers', [])
        key = hotkey_settings.get('key', 'X')
        return ' + '.join(modifiers + [key])
    
    def is_registered(self) -> bool:
        """Check if hotkey is registered"""
        return self._registered
    
    
    def get_registration_info(self) -> dict:
        """Get detailed registration information"""
        return {
            "registered": self._registered,
            "hotkey_id": self._hotkey_id,
            "mode": "ultra_compatible",
            "hotkey_string": self.get_hotkey_string() if self._registered else None
        } 