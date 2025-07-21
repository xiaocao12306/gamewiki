"""
Configuration management – settings and game configs.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import os
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional

from src.game_wiki_tooltip.utils import APPDATA_DIR, package_file

# Configure logging
logger = logging.getLogger(__name__)


# ---------- LLM Configuration ----------

@dataclass
class LLMConfig:
    """LLM配置类"""
    model: str = "gemini-2.5-flash-lite-preview-06-17"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 1000
    temperature: float = 0.7
    timeout: int = 30
    enable_cache: bool = True
    cache_ttl: int = 3600  # 缓存TTL，秒
    max_retries: int = 3
    retry_delay: float = 1.0
    
    def is_valid(self) -> bool:
        """检查配置是否有效"""
        api_key = self.get_api_key()
        return bool(api_key and self.model)
    
    def get_api_key(self) -> Optional[str]:
        """获取API密钥，优先从环境变量获取"""
        if self.api_key:
            return self.api_key
        
        # 根据模型类型从环境变量获取
        if "gemini" in self.model.lower():
            return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        elif "gpt" in self.model.lower() or "openai" in self.model.lower():
            return os.getenv("OPENAI_API_KEY")
        
        return None


# ---------- App-settings ----------

@dataclass
class HotkeyConfig:
    modifiers: List[str] = field(default_factory=lambda: ["Ctrl"])
    key: str = "X"


@dataclass
class PopupConfig:
    width: int = 600
    height: int = 500
    left: int = 100
    top: int = 50
    # 统一使用相对坐标作为默认配置
    use_relative_position: bool = True
    left_percent: float = 0.55  # 屏幕宽度的55%位置（右侧偏中）
    top_percent: float = 0.1    # 屏幕高度的10%位置（顶部留白）
    width_percent: float = 0.35 # 屏幕宽度的35%（适中大小）
    height_percent: float = 0.65 # 屏幕高度的65%（足够内容显示）
    use_relative_size: bool = True
    
    def get_absolute_geometry(self, screen_geometry=None):
        """
        获取绝对坐标几何信息
        
        Args:
            screen_geometry: 屏幕几何信息，如果为None则自动获取
            
        Returns:
            tuple: (x, y, width, height) 绝对像素坐标
        """
        if screen_geometry is None:
            try:
                from PyQt6.QtWidgets import QApplication
                screen_geometry = QApplication.primaryScreen().availableGeometry()
            except ImportError:
                try:
                    from PyQt5.QtWidgets import QApplication
                    screen_geometry = QApplication.primaryScreen().availableGeometry()
                except ImportError:
                    # 如果PyQt不可用，使用默认值
                    return self.left, self.top, self.width, self.height
        
        # 兼容不同类型的screen_geometry对象
        def get_screen_value(obj, attr_name):
            """获取屏幕几何属性值，兼容方法调用和属性访问"""
            try:
                # 首先尝试方法调用（PyQt对象）
                attr = getattr(obj, attr_name)
                if callable(attr):
                    return attr()
                else:
                    return attr
            except (AttributeError, TypeError):
                # 如果失败，尝试直接属性访问（测试对象）
                return getattr(obj, attr_name, 0)
        
        screen_x = get_screen_value(screen_geometry, 'x')
        screen_y = get_screen_value(screen_geometry, 'y') 
        screen_width = get_screen_value(screen_geometry, 'width')
        screen_height = get_screen_value(screen_geometry, 'height')
        
        # 计算尺寸
        if self.use_relative_size:
            calc_width = int(screen_width * self.width_percent)
            calc_height = int(screen_height * self.height_percent)
            # 确保最小尺寸
            calc_width = max(300, min(calc_width, 1200))
            calc_height = max(200, min(calc_height, 900))
        else:
            calc_width = self.width
            calc_height = self.height
        
        # 计算位置
        if self.use_relative_position:
            calc_x = int(screen_x + screen_width * self.left_percent)
            calc_y = int(screen_y + screen_height * self.top_percent)
        else:
            calc_x = self.left
            calc_y = self.top
        
        # 确保窗口在屏幕可见区域内
        return self._ensure_window_visible(
            calc_x, calc_y, calc_width, calc_height, 
            screen_x, screen_y, screen_width, screen_height
        )
    
    def _ensure_window_visible(self, x, y, width, height, screen_x, screen_y, screen_width, screen_height):
        """
        确保窗口在屏幕可见区域内
        
        Args:
            x, y, width, height: 窗口几何参数
            screen_x, screen_y, screen_width, screen_height: 屏幕几何参数
            
        Returns:
            tuple: 调整后的(x, y, width, height)
        """
        # 最小可见区域（确保用户能看到并操作窗口）
        min_visible_width = min(200, width // 2)
        min_visible_height = min(100, height // 4)
        
        # 右边界检查
        if x > screen_x + screen_width - min_visible_width:
            x = screen_x + screen_width - width - 10
        
        # 下边界检查  
        if y > screen_y + screen_height - min_visible_height:
            y = screen_y + screen_height - height - 10
        
        # 左边界检查
        if x < screen_x - width + min_visible_width:
            x = screen_x + 10
        
        # 上边界检查
        if y < screen_y:
            y = screen_y + 10
        
        # 尺寸检查 - 如果窗口比屏幕大，调整尺寸
        max_width = screen_width - 20
        max_height = screen_height - 40  # 留出任务栏空间
        
        if width > max_width:
            width = max_width
            x = screen_x + 10
        
        if height > max_height:
            height = max_height
            y = screen_y + 10
        
        return x, y, width, height
    
    @classmethod
    def create_smart_default(cls, screen_geometry=None):
        """
        创建智能默认配置
        统一使用相对坐标系统，根据屏幕尺寸优化百分比参数
        
        Args:
            screen_geometry: 屏幕几何信息
            
        Returns:
            PopupConfig: 智能默认配置实例
        """
        if screen_geometry is None:
            try:
                from PyQt6.QtWidgets import QApplication
                screen_geometry = QApplication.primaryScreen().availableGeometry()
            except ImportError:
                try:
                    from PyQt5.QtWidgets import QApplication  
                    screen_geometry = QApplication.primaryScreen().availableGeometry()
                except ImportError:
                    # 回退到传统固定值
                    return cls()
        
        # 兼容不同类型的screen_geometry对象
        def get_screen_value(obj, attr_name):
            """获取屏幕几何属性值，兼容方法调用和属性访问"""
            try:
                # 首先尝试方法调用（PyQt对象）
                attr = getattr(obj, attr_name)
                if callable(attr):
                    return attr()
                else:
                    return attr
            except (AttributeError, TypeError):
                # 如果失败，尝试直接属性访问（测试对象）
                return getattr(obj, attr_name, 0)
        
        # 根据屏幕尺寸智能选择配置策略
        screen_width = get_screen_value(screen_geometry, 'width')
        screen_height = get_screen_value(screen_geometry, 'height')
        
        if screen_width >= 1920 and screen_height >= 1080:
            # 大屏幕：可以使用更大的窗口和更靠右的位置
            return cls(
                use_relative_position=True,
                use_relative_size=True,
                left_percent=0.58,    # 更靠右侧，充分利用大屏幕
                top_percent=0.08,     # 稍微靠上
                width_percent=0.38,   # 稍大一些的宽度
                height_percent=0.75,  # 更高的窗口
            )
        elif screen_width >= 1366 and screen_height >= 768:
            # 中等屏幕：平衡的配置
            return cls(
                use_relative_position=True,
                use_relative_size=True,
                left_percent=0.55,    # 标准右侧位置
                top_percent=0.1,      # 标准顶部位置
                width_percent=0.35,   # 标准宽度
                height_percent=0.65,  # 标准高度
            )
        else:
            # 小屏幕：更紧凑的配置，确保内容可见
            return cls(
                use_relative_position=True,
                use_relative_size=True,
                left_percent=0.52,    # 稍微居中一些，避免过于靠边
                top_percent=0.05,     # 更靠上，节省垂直空间
                width_percent=0.42,   # 相对更宽，确保内容可读
                height_percent=0.7,   # 相对更高，充分利用屏幕
            )


@dataclass
class ApiConfig:
    gemini_api_key: str = ""
    jina_api_key: str = ""


@dataclass
class AppSettings:
    """应用程序设置"""
    language: str = "en"
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    popup: PopupConfig = field(default_factory=PopupConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    dont_remind_api_missing: bool = False  # 用户是否选择了"不再提醒"API缺失
    shortcuts: List[Dict[str, Any]] = field(default_factory=list)


class SettingsManager:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self._settings = self._load()

    # ---- public API ----
    @property
    def settings(self) -> AppSettings:  # read-only snapshot
        return self._settings

    def save(self) -> None:
        """保存设置到文件"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(asdict(self._settings), f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"保存设置文件失败: {e}")

    def get(self, key: Optional[str] = None, default: Any = None) -> Any:
        """获取当前设置或指定键的值"""
        settings_dict = asdict(self._settings)
        if key is None:
            return settings_dict
        return settings_dict.get(key, default)

    def update(self, new_settings: Dict[str, Any]):
        """更新设置"""
        # 更新语言设置
        if 'language' in new_settings:
            self._settings.language = new_settings['language']
        # 更新热键设置
        if 'hotkey' in new_settings:
            self._settings.hotkey = HotkeyConfig(**new_settings['hotkey'])
        # 更新弹窗设置
        if 'popup' in new_settings:
            self._settings.popup = PopupConfig(**new_settings['popup'])
        # 更新API设置
        if 'api' in new_settings:
            self._settings.api = ApiConfig(**new_settings['api'])
        # 更新"不再提醒"设置
        if 'dont_remind_api_missing' in new_settings:
            self._settings.dont_remind_api_missing = new_settings['dont_remind_api_missing']
        # 更新快捷网站设置
        if 'shortcuts' in new_settings:
            self._settings.shortcuts = new_settings['shortcuts']
        self.save()

    # ---- internal ----
    def _merge_settings(self, default_data: dict, existing_data: dict) -> dict:
        """合并默认设置和现有设置，保留用户的修改"""
        merged = existing_data.copy()
        
        # 递归合并字典
        for key, default_value in default_data.items():
            if key not in merged:
                # 如果键不存在，使用默认值
                merged[key] = default_value
            elif isinstance(default_value, dict) and isinstance(merged.get(key), dict):
                # 如果都是字典，递归合并
                merged[key] = self._merge_settings(default_value, merged[key])
            # 否则保留现有值（用户的修改）
            
        return merged
    def _load(self) -> AppSettings:
        """加载设置文件"""
        # 获取默认设置文件路径
        default_settings_path = package_file("settings.json")
        
        # 如果目标文件不存在，或者默认文件比目标文件新，则复制默认文件
        if not self.path.exists() or default_settings_path.stat().st_mtime > self.path.stat().st_mtime:
            # 先创建目标目录
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # 复制默认设置文件
            shutil.copyfile(default_settings_path, self.path)
            print(f"已更新设置文件: {self.path}")
            
        # 同步确保roaming中的settings包含所有必要字段
        try:
            # 读取项目中的默认settings
            default_data = json.loads(default_settings_path.read_text(encoding="utf-8"))
            # 读取roaming中的现有settings
            existing_data = json.loads(self.path.read_text(encoding="utf-8"))
            
            # 合并设置，保留用户的修改但确保所有字段都存在
            merged_data = self._merge_settings(default_data, existing_data)
            
            # 特殊处理：升级旧的popup配置到新格式
            merged_data = self._upgrade_popup_config(merged_data)
            
            # 如果合并后的数据与现有数据不同，保存更新
            if merged_data != existing_data:
                self.path.write_text(json.dumps(merged_data, indent=4, ensure_ascii=False), encoding="utf-8")
                print(f"已同步设置文件字段: {self.path}")
            
            # 从合并后的数据创建AppSettings实例
            return AppSettings(
                language=merged_data.get('language', 'en'),
                hotkey=HotkeyConfig(**merged_data.get('hotkey', {})),
                popup=PopupConfig(**merged_data.get('popup', {})),
                api=ApiConfig(**merged_data.get('api', {})),
                dont_remind_api_missing=merged_data.get('dont_remind_api_missing', False),
                shortcuts=merged_data.get('shortcuts', [])
            )
        except Exception as e:
            print(f"处理设置文件时出错: {e}")
            # 出错时使用默认设置
            default_data = json.loads(default_settings_path.read_text(encoding="utf-8"))
            return AppSettings(
                language=default_data.get('language', 'en'),
                hotkey=HotkeyConfig(**default_data.get('hotkey', {})),
                popup=PopupConfig(**default_data.get('popup', {})),
                api=ApiConfig(**default_data.get('api', {})),
                shortcuts=default_data.get('shortcuts', [])
            )
    
    def _upgrade_popup_config(self, data: dict) -> dict:
        """
        升级旧的popup配置到新格式
        统一使用智能相对坐标系统
        
        Args:
            data: 设置数据字典
            
        Returns:
            dict: 升级后的设置数据
        """
        popup = data.get('popup', {})
        
        # 检查是否需要升级（缺少新字段）
        new_fields = ['use_relative_position', 'left_percent', 'top_percent', 
                     'width_percent', 'height_percent', 'use_relative_size']
        needs_upgrade = not all(field in popup for field in new_fields)
        
        if needs_upgrade:
            print("🔄 检测到旧版popup配置，升级为智能相对坐标系统...")
            
            # 检查是否有基本的坐标信息
            has_basic_coords = all(field in popup for field in ['left', 'top', 'width', 'height'])
            
            if has_basic_coords:
                # 保留原有坐标作为兜底，但统一使用相对坐标
                left = popup.get('left', 100)
                top = popup.get('top', 50)
                width = popup.get('width', 600)
                height = popup.get('height', 500)
                
                # 检查是否是极端不合理的坐标（例如超大值或负值）
                is_extreme_coords = (left > 3000 or top > 2000 or 
                                   left < 0 or top < 0 or 
                                   width > 2000 or height > 1500 or
                                   width < 100 or height < 100)
                
                if is_extreme_coords:
                    print(f"⚠️  检测到极端坐标值，使用标准智能配置")
                    # 使用标准智能相对坐标
                    popup.update({
                        'left': 100,
                        'top': 50,
                        'width': 600,
                        'height': 500,
                        'use_relative_position': True,
                        'left_percent': 0.55,
                        'top_percent': 0.1,
                        'width_percent': 0.35,
                        'height_percent': 0.65,
                        'use_relative_size': True
                    })
                else:
                    # 普通坐标，统一升级为智能相对坐标
                    popup.update({
                        'use_relative_position': True,
                        'left_percent': 0.55,
                        'top_percent': 0.1,
                        'width_percent': 0.35,
                        'height_percent': 0.65,
                        'use_relative_size': True
                    })
                    
                print(f"✅ 已升级为智能相对坐标配置（原坐标: {left},{top},{width}x{height}）")
            else:
                # 没有基本坐标，创建标准智能配置
                popup.update({
                    'left': 100,
                    'top': 50,
                    'width': 600,
                    'height': 500,
                    'use_relative_position': True,
                    'left_percent': 0.55,
                    'top_percent': 0.1,
                    'width_percent': 0.35,
                    'height_percent': 0.65,
                    'use_relative_size': True
                })
                print(f"✅ 已创建标准智能相对坐标配置")
            
            data['popup'] = popup
        else:
            # 已有新字段，检查是否需要从固定坐标迁移到相对坐标
            if not popup.get('use_relative_position', True):
                print("🔄 检测到固定坐标配置，建议升级为相对坐标...")
                popup['use_relative_position'] = True
                popup['use_relative_size'] = True
                popup['left_percent'] = 0.55
                popup['top_percent'] = 0.1
                popup['width_percent'] = 0.35
                popup['height_percent'] = 0.65
                print(f"✅ 已从固定坐标升级为智能相对坐标")
                data['popup'] = popup
        
        return data


# ---------- Game-configs ----------

@dataclass
class GameConfig:
    BaseUrl: str
    NeedsSearch: bool = True


class GameConfigManager:
    """Game configuration manager"""
    
    def __init__(self, path: pathlib.Path):
        self.path = path
        self._games = {}
        self._load()
    
    def _get_language_specific_path(self, language: str = None) -> pathlib.Path:
        """Get language-specific games.json path"""
        if language is None:
            # Try to get current language from settings
            settings_path = self.path.parent / "settings.json"
            if settings_path.exists():
                try:
                    settings_mgr = SettingsManager(settings_path)
                    settings = settings_mgr.get()
                    language = settings.get('language', 'en')
                except:
                    language = 'en'
            else:
                language = 'en'
        
        # Get the directory where games.json is located
        games_dir = self.path.parent
        
        # Try language-specific file first
        lang_file = games_dir / f"games_{language}.json"
        if lang_file.exists():
            return lang_file
        
        # Fallback to default games.json
        return self.path
    
    def _load(self):
        """Load games configuration"""
        try:
            # Ensure language-specific config files are copied to appdata
            self._ensure_language_configs_copied()
            
            config_path = self._get_language_specific_path()
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._games = json.load(f)
                logger.info(f"Loaded games config from {config_path}")
            else:
                # Create default config if it doesn't exist
                self._games = self._create_default_config()
                self._save()
                logger.info(f"Created default games config at {config_path}")
        except Exception as e:
            logger.error(f"Failed to load games config: {e}")
            self._games = self._create_default_config()
            
    def _ensure_language_configs_copied(self):
        """确保语言特定的配置文件被复制到appdata目录"""
        try:
            # 需要复制的语言配置文件
            language_files = ['games_en.json', 'games_zh.json', 'games.json']
            
            for filename in language_files:
                try:
                    # 获取源文件路径（assets目录）
                    source_path = package_file(filename)
                    if not source_path.exists():
                        logger.warning(f"Language config file not found in assets: {filename}")
                        continue
                    
                    # 目标文件路径（appdata目录）
                    target_path = self.path.parent / filename
                    
                    # 如果目标文件不存在，或源文件更新，则复制
                    if not target_path.exists() or source_path.stat().st_mtime > target_path.stat().st_mtime:
                        # 确保目标目录存在
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        # 复制文件
                        shutil.copyfile(source_path, target_path)
                        logger.info(f"已复制语言配置文件: {filename} -> {target_path}")
                    else:
                        logger.debug(f"语言配置文件已是最新: {filename}")
                        
                except Exception as e:
                    logger.error(f"复制语言配置文件失败 {filename}: {e}")
                    
        except Exception as e:
            logger.error(f"确保语言配置文件复制失败: {e}")
    
    def _create_default_config(self) -> dict:
        """Create default games configuration"""
        # Default to English games config
        return {
            "VALORANT": {
                "BaseUrl": "https://valorant.fandom.com/wiki/",
                "NeedsSearch": False
            },
            "Counter-Strike 2": {
                "BaseUrl": "https://counterstrike.fandom.com/wiki/",
                "NeedsSearch": False
            },
            "Stardew Valley": {
                "BaseUrl": "https://stardewvalleywiki.com/",
                "NeedsSearch": True
            },
            "Don't Starve Together": {
                "BaseUrl": "https://dontstarve.fandom.com/wiki/",
                "NeedsSearch": True
            },
            "Elden Ring": {
                "BaseUrl": "https://eldenring.wiki.fextralife.com/",
                "NeedsSearch": True
            },
            "HELLDIVERS 2": {
                "BaseUrl": "https://helldivers.fandom.com/wiki/",
                "NeedsSearch": True
            }
        }
    
    def _save(self):
        """Save games configuration"""
        try:
            config_path = self._get_language_specific_path()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self._games, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save games config: {e}")
    
    def get(self) -> dict:
        """Get games configuration"""
        return self._games.copy()
    
    def get_game_config(self, game_name: str) -> Optional[dict]:
        """Get configuration for a specific game"""
        return self._games.get(game_name)
    
    def update_game_config(self, game_name: str, config: dict):
        """Update configuration for a specific game"""
        self._games[game_name] = config
        self._save()
    
    def reload_for_language(self, language: str):
        """Reload games configuration for a specific language"""
        self._games = {}
        config_path = self._get_language_specific_path(language)
        
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._games = json.load(f)
                logger.info(f"Reloaded games config for language '{language}' from {config_path}")
            else:
                # If language-specific file doesn't exist, create it with default config
                self._games = self._create_default_config()
                
                # Save the config to the language-specific file
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(self._games, f, indent=2, ensure_ascii=False)
                logger.info(f"Created games config for language '{language}' at {config_path}")
                
        except Exception as e:
            logger.error(f"Failed to reload games config for language '{language}': {e}")
            self._games = self._create_default_config()
    
    def for_title(self, window_title: str) -> Optional[GameConfig]:
        """根据窗口标题获取游戏配置 (向后兼容)"""
        lower = window_title.lower()
        for name, cfg in self._games.items():
            if name.lower() in lower:
                # Convert dict to GameConfig for backward compatibility
                return GameConfig(
                    BaseUrl=cfg.get('BaseUrl', ''),
                    NeedsSearch=cfg.get('NeedsSearch', True)
                )
        return None
