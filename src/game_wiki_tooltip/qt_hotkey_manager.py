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


class HotkeyConflictStrategy:
    """热键冲突处理策略"""
    FAIL = "fail"                    # 失败退出
    FORCE_REGISTER = "force"         # 强制注册
    TRY_ALTERNATIVES = "alternatives" # 尝试备选方案
    USER_CHOICE = "user_choice"      # 让用户选择


class QtHotkeyManager(QObject):
    """PyQt6-based global hotkey manager with conflict resolution and ultra-compatible mode
    
    This class provides global hotkey management with multiple compatibility modes:
    
    1. Standard mode (legacy_mode=False): 
       - Uses normal hotkey registration with conflict resolution
       - Supports alternative hotkey suggestions when conflicts occur
       
    2. Legacy mode (legacy_mode=True, ultra_compatible_mode=False):
       - Uses original legacy hotkey registration logic
       - Handles ERROR_HOTKEY_ALREADY_REGISTERED by assuming hotkey is available
       - Other errors still cause registration failure
       
    3. Ultra-compatible mode (legacy_mode=True, ultra_compatible_mode=True):
       - Uses enhanced ultra-compatible registration logic
       - ALL errors and exceptions are handled by assuming hotkey is available
       - Ensures the application can start in ANY environment
       - Provides maximum compatibility with existing systems
    
    Ultra-compatible mode is designed to ensure the application never fails to start
    due to hotkey registration issues, which is critical for user experience.
    """
    
    # Signals
    hotkey_triggered = pyqtSignal()
    
    def __init__(self, settings_mgr: SettingsManager, parent=None, 
                 conflict_strategy: str = HotkeyConflictStrategy.FORCE_REGISTER,
                 legacy_mode: bool = True,
                 ultra_compatible_mode: bool = True):
        super().__init__(parent)
        self.settings_mgr = settings_mgr
        self._registered = False
        self._hotkey_id = 1
        self._conflict_strategy = conflict_strategy
        self._backup_hotkey_id = None  # 备用热键ID
        self._legacy_mode = legacy_mode  # 向后兼容模式
        self._ultra_compatible_mode = ultra_compatible_mode  # 超级兼容模式
        logger.info(f"QtHotkeyManager initialized (legacy_mode={legacy_mode}, ultra_compatible_mode={ultra_compatible_mode})")
        
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
    
    def _get_alternative_hotkeys(self, base_modifiers: list, base_key: str) -> list:
        """获取备选热键组合"""
        alternatives = []
        
        # 添加额外修饰键的组合
        if "Shift" not in base_modifiers:
            alternatives.append((base_modifiers + ["Shift"], base_key))
        if "Alt" not in base_modifiers:
            alternatives.append((base_modifiers + ["Alt"], base_key))
        if len(base_modifiers) >= 2:  # 如果已经有多个修饰键，尝试减少
            for mod in base_modifiers:
                reduced_mods = [m for m in base_modifiers if m != mod]
                if reduced_mods:
                    alternatives.append((reduced_mods, base_key))
        
        # 尝试不同的主键
        alternative_keys = ['F1', 'F2', 'F3', 'F4', 'F12', 'Insert', 'Home', 'End']
        for alt_key in alternative_keys:
            if alt_key != base_key:
                alternatives.append((base_modifiers, alt_key))
        
        return alternatives[:5]  # 限制备选数量
    
    def _try_register_hotkey(self, modifiers: list, key: str, hotkey_id: int) -> tuple[bool, Optional[str]]:
        """尝试注册单个热键组合"""
        try:
            # Calculate modifier flags
            mod_flags = 0
            for modifier in modifiers:
                if modifier in MOD_MAP:
                    mod_flags |= MOD_MAP[modifier]
            
            # Get virtual key code
            vk = self._get_virtual_key(key)
            
            logger.info(f"尝试注册热键: {'+'.join(modifiers + [key])}, mod_flags={mod_flags}, vk={vk}, id={hotkey_id}")
            
            # Register hotkey
            result = RegisterHotKey(None, hotkey_id, mod_flags, vk)
            
            if result:
                logger.info(f"热键注册成功: {'+'.join(modifiers + [key])}")
                return True, None
            else:
                error = ctypes.get_last_error()
                error_msg = f"错误代码: {error}"
                
                if error == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
                    error_msg = "热键已被其他程序占用"
                elif error == 1401:  # ERROR_HOTKEY_NOT_REGISTERED
                    error_msg = "热键未注册"
                elif error == 0:
                    error_msg = "无效的热键组合或权限不足"
                
                logger.warning(f"热键注册失败: {'+'.join(modifiers + [key])}, {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = f"注册异常: {str(e)}"
            logger.error(f"热键注册异常: {error_msg}")
            return False, error_msg
    
    def _try_register_hotkey_legacy_old(self, modifiers: list, key: str, hotkey_id: int) -> tuple[bool, Optional[str]]:
        """原始的旧版本兼容热键注册逻辑（备份）"""
        try:
            # Calculate modifier flags
            mod_flags = 0
            for modifier in modifiers:
                if modifier in MOD_MAP:
                    mod_flags |= MOD_MAP[modifier]
            
            # Get virtual key code
            vk = self._get_virtual_key(key)
            
            logger.info(f"尝试注册热键(旧版兼容): {'+'.join(modifiers + [key])}, mod_flags={mod_flags}, vk={vk}, id={hotkey_id}")
            
            # Register hotkey
            result = RegisterHotKey(None, hotkey_id, mod_flags, vk)
            
            if result:
                logger.info(f"热键注册成功: {'+'.join(modifiers + [key])}")
                return True, None
            else:
                error = ctypes.get_last_error()
                
                if error == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
                    # 旧版本行为：假设热键已经被自己注册，直接成功
                    logger.warning(f"热键已被注册，假设为已注册状态: {'+'.join(modifiers + [key])}")
                    return True, "already_registered"
                elif error == 1401:  # ERROR_HOTKEY_NOT_REGISTERED
                    error_msg = "热键未注册"
                elif error == 0:
                    error_msg = "无效的热键组合或权限不足"
                else:
                    error_msg = f"未知错误代码: {error}"
                
                logger.error(f"热键注册失败: {'+'.join(modifiers + [key])}, {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = f"注册异常: {str(e)}"
            logger.error(f"热键注册异常: {error_msg}")
            return False, error_msg

    def _try_register_hotkey_legacy(self, modifiers: list, key: str, hotkey_id: int) -> tuple[bool, Optional[str]]:
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
    
    def _handle_hotkey_conflict(self, modifiers: list, key: str) -> bool:
        """处理热键冲突"""
        logger.info(f"处理热键冲突: {'+'.join(modifiers + [key])}")
        
        if self._conflict_strategy == HotkeyConflictStrategy.FORCE_REGISTER:
            logger.info("使用强制注册策略")
            
            # 尝试多个热键ID（可能其他程序使用了相同ID）
            for attempt_id in range(1, 10):
                success, error = self._try_register_hotkey(modifiers, key, attempt_id)
                if success:
                    logger.info(f"强制注册成功，使用热键ID: {attempt_id}")
                    self._hotkey_id = attempt_id
                    return True
            
            logger.warning("强制注册失败，尝试备选方案")
            
        if self._conflict_strategy in [HotkeyConflictStrategy.FORCE_REGISTER, 
                                       HotkeyConflictStrategy.TRY_ALTERNATIVES]:
            logger.info("尝试备选热键组合")
            
            alternatives = self._get_alternative_hotkeys(modifiers, key)
            for alt_modifiers, alt_key in alternatives:
                success, error = self._try_register_hotkey(alt_modifiers, alt_key, self._hotkey_id + 10)
                if success:
                    logger.info(f"备选热键注册成功: {'+'.join(alt_modifiers + [alt_key])}")
                    self._backup_hotkey_id = self._hotkey_id + 10
                    
                    # 更新设置（可选）
                    # self._update_settings_with_alternative(alt_modifiers, alt_key)
                    
                    return True
        
        return False
    
    def register(self):
        """Register global hotkey with conflict resolution"""
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
            
            if self._legacy_mode:
                # 使用旧版本兼容逻辑
                if self._ultra_compatible_mode:
                    logger.info("使用超级兼容的热键注册逻辑")
                    success, error = self._try_register_hotkey_legacy(modifiers, key, self._hotkey_id)
                else:
                    logger.info("使用原始旧版本兼容的热键注册逻辑")
                    success, error = self._try_register_hotkey_legacy_old(modifiers, key, self._hotkey_id)
                
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
                    # 即使在旧版模式下，如果失败也不抛异常，而是警告
                    logger.error(f"热键注册失败: {error}")
                    logger.info("程序将继续运行，但热键功能不可用")
                    logger.info("建议:")
                    logger.info("1. 以管理员身份运行程序")
                    logger.info("2. 关闭可能占用热键的其他程序")
                    logger.info("3. 在设置中更换热键组合")
                    
                    # 不抛出异常，让程序继续运行
                    self._registered = False
                    return
            else:
                # 使用新版本冲突处理逻辑
                logger.info("使用新版本冲突处理的热键注册逻辑")
                # 首先尝试正常注册
                success, error = self._try_register_hotkey(modifiers, key, self._hotkey_id)
                
                if success:
                    self._registered = True
                    logger.info("热键注册成功")
                    return
                
                # 处理冲突
                logger.warning(f"热键注册失败: {error}")
                
                if self._handle_hotkey_conflict(modifiers, key):
                    self._registered = True
                    logger.info("通过冲突处理成功注册热键")
                    return
                else:
                    # 最后的尝试：警告用户但继续运行
                    logger.error("所有热键注册尝试都失败了")
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
            # 取消注册主热键
            if not UnregisterHotKey(None, self._hotkey_id):
                error = ctypes.get_last_error()
                logger.error(f"Failed to unregister hotkey, error code: {error}")
            else:
                logger.info("Main hotkey unregistered successfully")
            
            # 取消注册备用热键
            if self._backup_hotkey_id:
                if not UnregisterHotKey(None, self._backup_hotkey_id):
                    error = ctypes.get_last_error()
                    logger.error(f"Failed to unregister backup hotkey, error code: {error}")
                else:
                    logger.info("Backup hotkey unregistered successfully")
                self._backup_hotkey_id = None
            
            self._registered = False
            
        except Exception as e:
            logger.error(f"Failed to unregister hotkey: {e}")
            
    def handle_hotkey_message(self, msg):
        """Handle WM_HOTKEY message"""
        logger.info(f"=== HOTKEY MESSAGE RECEIVED ===")
        logger.info(f"Message wParam: {msg.wParam}, expected_ids: {self._hotkey_id}, {self._backup_hotkey_id}")
        logger.info(f"Message lParam: {msg.lParam}")
        
        # 检查主热键或备用热键
        if msg.wParam == self._hotkey_id or msg.wParam == self._backup_hotkey_id:
            logger.info("Hotkey ID matches! Emitting hotkey_triggered signal")
            self.hotkey_triggered.emit()
            logger.info("hotkey_triggered signal emitted")
        else:
            logger.warning(f"Hotkey ID mismatch: received={msg.wParam}, expected={self._hotkey_id} or {self._backup_hotkey_id}")
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
    
    def get_conflict_strategy(self) -> str:
        """Get current conflict resolution strategy"""
        return self._conflict_strategy
    
    def set_conflict_strategy(self, strategy: str):
        """Set conflict resolution strategy"""
        if strategy in [HotkeyConflictStrategy.FAIL, 
                       HotkeyConflictStrategy.FORCE_REGISTER,
                       HotkeyConflictStrategy.TRY_ALTERNATIVES,
                       HotkeyConflictStrategy.USER_CHOICE]:
            self._conflict_strategy = strategy
            logger.info(f"Conflict strategy set to: {strategy}")
        else:
            logger.error(f"Invalid conflict strategy: {strategy}")
    
    def is_legacy_mode(self) -> bool:
        """Check if legacy mode is enabled"""
        return self._legacy_mode
    
    def set_legacy_mode(self, enabled: bool):
        """Enable or disable legacy mode"""
        self._legacy_mode = enabled
        logger.info(f"Legacy mode set to: {enabled}")
    
    def is_ultra_compatible_mode(self) -> bool:
        """Check if ultra compatible mode is enabled"""
        return self._ultra_compatible_mode
    
    def set_ultra_compatible_mode(self, enabled: bool):
        """Set ultra compatible mode (affects hotkey registration strategy in legacy mode)"""
        if self._ultra_compatible_mode != enabled:
            self._ultra_compatible_mode = enabled
            logger.info(f"Ultra compatible mode {'enabled' if enabled else 'disabled'}")
            # If currently registered and in legacy mode, re-register with new strategy
            if self._registered and self._legacy_mode:
                self.register()
    
    def get_registration_info(self) -> dict:
        """Get detailed registration information"""
        return {
            "registered": self._registered,
            "hotkey_id": self._hotkey_id,
            "backup_hotkey_id": self._backup_hotkey_id,
            "legacy_mode": self._legacy_mode,
            "ultra_compatible_mode": self._ultra_compatible_mode,
            "conflict_strategy": self._conflict_strategy,
            "hotkey_string": self.get_hotkey_string() if self._registered else None
        } 