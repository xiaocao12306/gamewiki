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
    width: int = 800
    height: int = 600
    left: int = 100
    top: int = 100


@dataclass
class ApiConfig:
    google_api_key: str = ""
    jina_api_key: str = ""


@dataclass
class AppSettings:
    """应用程序设置"""
    language: str = "en"
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    popup: PopupConfig = field(default_factory=PopupConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    dont_remind_api_missing: bool = False  # 用户是否选择了"不再提醒"API缺失


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

    def get(self) -> Dict[str, Any]:
        """获取当前设置"""
        return asdict(self._settings)

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
        self.save()

    # ---- internal ----
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
            
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # 关键改动！
            hotkey = HotkeyConfig(**data.get('hotkey', {}))
            popup = PopupConfig(**data.get('popup', {}))
            api = ApiConfig(**data.get('api', {}))
            language = data.get('language', 'en')
            dont_remind_api_missing = data.get('dont_remind_api_missing', False)
            return AppSettings(
                language=language,
                hotkey=hotkey, 
                popup=popup, 
                api=api,
                dont_remind_api_missing=dont_remind_api_missing
            )
        except Exception as e:
            print(f"加载设置文件失败: {e}")
            return AppSettings()


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
