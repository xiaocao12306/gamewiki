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

from src.game_wiki_tooltip.core.utils import package_file

# Configure logging
logger = logging.getLogger(__name__)


# ---------- LLM Configuration ----------

@dataclass
class LLMConfig:
    def get_api_key(self) -> Optional[str]:
        """Get API key, prioritize environment variable"""
        if getattr(self, "api_key", None):
            return self.api_key
        
        # Get API key from environment variable based on model type
        model_name = getattr(self, "model", "")
        if "deepseek" in model_name.lower():
            return os.getenv("DEEPSEEK_API_KEY")
        elif "gemini" in model_name.lower():
            return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        elif "gpt" in model_name.lower() or "openai" in model_name.lower():
            return os.getenv("OPENAI_API_KEY")

        return None

    def resolved_base_url(self) -> Optional[str]:
        base_url = getattr(self, "base_url", None)
        if base_url:
            return base_url

        model_name = getattr(self, "model", "")
        if "deepseek" in model_name.lower():
            return os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        return None


# ---------- App-settings ----------

@dataclass
class HotkeyConfig:
    modifiers: List[str] = field(default_factory=lambda: ["Ctrl"])
    key: str = "X"


@dataclass
class ChatOnlyGeometry:
    """Geometry configuration for chat_only window state"""
    left_percent: float = 0.65
    top_percent: float = 0.85
    width_percent: float = 0.22
    height_percent: float = 0.108


@dataclass
class FullContentGeometry:
    """Geometry configuration for full_content window state"""
    width_percent: float = 0.25
    height_percent: float = 0.5


@dataclass
class WebViewGeometry:
    """Geometry configuration for webview window state"""
    width_percent: float = 0.5
    height_percent: float = 0.5


@dataclass
class WindowGeometryConfig:
    """Container for all window state geometries"""
    chat_only: ChatOnlyGeometry = field(default_factory=ChatOnlyGeometry)
    full_content: FullContentGeometry = field(default_factory=FullContentGeometry)
    webview: WebViewGeometry = field(default_factory=WebViewGeometry)

@dataclass
class ApiConfig:
    gemini_api_key: str = ""


@dataclass
class BackendConfig:
    base_url: str = ""
    api_key: str = ""
    config_endpoint: str = "/api/v1/config"
    events_endpoint: str = "/api/v1/events"
    chat_endpoint: str = "/api/v1/chat"
    timeout: float = 10.0

    def resolved_base_url(self) -> str:
        return self.base_url or os.getenv("GW_BACKEND_BASE_URL", "")

    def resolved_api_key(self) -> str:
        return self.api_key or os.getenv("GW_BACKEND_API_KEY", "")


@dataclass
class AnalyticsConfig:
    flush_interval_seconds: float = 5.0
    max_queue_size: int = 50
    max_retry: int = 3
    enabled: bool = True


@dataclass
class AppSettings:
    """Application settings"""
    language: str = "en"
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    window_geometry: WindowGeometryConfig = field(default_factory=WindowGeometryConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)
    remote_config: Dict[str, Any] = field(default_factory=dict)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    dont_remind_api_missing: bool = False  # User has selected "Don't remind me again" API missing
    shortcuts: List[Dict[str, Any]] = field(default_factory=list)
    audio_device_index: Optional[int] = None  # Audio device index for voice recognition
    auto_voice_on_hotkey: bool = False  # Auto-start voice input when hotkey triggers window
    auto_send_voice_input: bool = False  # Auto-send voice input when recording stops
    audio_devices_cache: List[Dict[str, Any]] = field(default_factory=list)  # Cached audio device list
    audio_devices_cache_time: Optional[float] = None  # Timestamp when cache was last updated


class SettingsManager:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self._settings = self._load()

    # ---- public API ----
    @property
    def settings(self) -> AppSettings:  # read-only snapshot
        return self._settings

    def save(self) -> None:
        """Save settings to file"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(asdict(self._settings), f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save settings file: {e}")

    def get(self, key: Optional[str] = None, default: Any = None) -> Any:
        """Get current settings or value of specified key"""
        settings_dict = asdict(self._settings)
        if key is None:
            return settings_dict
        return settings_dict.get(key, default)

    def update(self, new_settings: Dict[str, Any]):
        """Update settings"""
        # Update language settings
        if 'language' in new_settings:
            self._settings.language = new_settings['language']
        # Update hotkey settings
        if 'hotkey' in new_settings:
            self._settings.hotkey = HotkeyConfig(**new_settings['hotkey'])
        # Update window geometry settings
        if 'window_geometry' in new_settings:
            geom = new_settings['window_geometry']
            if 'chat_only' in geom:
                self._settings.window_geometry.chat_only = ChatOnlyGeometry(**geom['chat_only'])
            if 'full_content' in geom:
                self._settings.window_geometry.full_content = FullContentGeometry(**geom['full_content'])
            if 'webview' in geom:
                self._settings.window_geometry.webview = WebViewGeometry(**geom['webview'])
        # Update API settings
        if 'api' in new_settings:
            self._settings.api = ApiConfig(**new_settings['api'])
        # Update backend settings
        if 'backend' in new_settings:
            self._settings.backend = BackendConfig(**new_settings['backend'])
        if 'remote_config' in new_settings:
            self._settings.remote_config = new_settings['remote_config']
        # Update analytics settings
        if 'analytics' in new_settings:
            self._settings.analytics = AnalyticsConfig(**new_settings['analytics'])
        # Update "Don't remind me again" settings
        if 'dont_remind_api_missing' in new_settings:
            self._settings.dont_remind_api_missing = new_settings['dont_remind_api_missing']
        # Update shortcuts settings
        if 'shortcuts' in new_settings:
            self._settings.shortcuts = new_settings['shortcuts']
        # Update audio device index
        if 'audio_device_index' in new_settings:
            self._settings.audio_device_index = new_settings['audio_device_index']
        # Update auto voice on hotkey setting
        if 'auto_voice_on_hotkey' in new_settings:
            self._settings.auto_voice_on_hotkey = new_settings['auto_voice_on_hotkey']
        # Update auto send voice input setting
        if 'auto_send_voice_input' in new_settings:
            self._settings.auto_send_voice_input = new_settings['auto_send_voice_input']
        # Update audio devices cache
        if 'audio_devices_cache' in new_settings:
            self._settings.audio_devices_cache = new_settings['audio_devices_cache']
        # Update audio devices cache time
        if 'audio_devices_cache_time' in new_settings:
            self._settings.audio_devices_cache_time = new_settings['audio_devices_cache_time']
        self.save()

    # ---- internal ----
    def _merge_settings(self, default_data: dict, existing_data: dict) -> dict:
        """Merge default settings with existing settings, preserving user modifications"""
        merged = existing_data.copy()
        
        # Recursively merge dictionaries
        for key, default_value in default_data.items():
            if key not in merged:
                # If key does not exist, use default value
                merged[key] = default_value
            elif isinstance(default_value, dict) and isinstance(merged.get(key), dict):
                # If both are dictionaries, recursively merge
                merged[key] = self._merge_settings(default_value, merged[key])
            # Otherwise, keep existing value (user's modifications)
            
        return merged
    def _load(self) -> AppSettings:
        """Load settings file"""
        # Get default settings file path
        default_settings_path = package_file("settings.json")
        
        # If target file does not exist, copy default file (remove time-based check to prevent overwriting user settings in exe)
        if not self.path.exists():
            # First create target directory
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Copy default settings file
            shutil.copyfile(default_settings_path, self.path)
            print(f"Settings file created: {self.path}")
            
        # Ensure roaming settings contains all necessary fields
        try:
            # Read default settings from project
            default_data = json.loads(default_settings_path.read_text(encoding="utf-8"))
            # Read existing settings from roaming
            existing_data = json.loads(self.path.read_text(encoding="utf-8"))
            
            # Merge settings, preserve user modifications but ensure all fields exist
            merged_data = self._merge_settings(default_data, existing_data)
            
            # If merged data is different from existing data, save update
            if merged_data != existing_data:
                self.path.write_text(json.dumps(merged_data, indent=4, ensure_ascii=False), encoding="utf-8")
                print(f"Settings file fields synchronized: {self.path}")
            
            # Create AppSettings instance from merged data
            window_geometry_data = merged_data.get('window_geometry', {})
            window_geometry = WindowGeometryConfig()
            if 'chat_only' in window_geometry_data:
                window_geometry.chat_only = ChatOnlyGeometry(**window_geometry_data['chat_only'])
            if 'full_content' in window_geometry_data:
                window_geometry.full_content = FullContentGeometry(**window_geometry_data['full_content'])
            if 'webview' in window_geometry_data:
                window_geometry.webview = WebViewGeometry(**window_geometry_data['webview'])
                
            return AppSettings(
                language=merged_data.get('language', 'en'),
                hotkey=HotkeyConfig(**merged_data.get('hotkey', {})),
                window_geometry=window_geometry,
                api=ApiConfig(**merged_data.get('api', {})),
                dont_remind_api_missing=merged_data.get('dont_remind_api_missing', False),
                backend=BackendConfig(**merged_data.get('backend', {})),
                analytics=AnalyticsConfig(**merged_data.get('analytics', {})),
                shortcuts=merged_data.get('shortcuts', []),
                audio_device_index=merged_data.get('audio_device_index', None),
                auto_voice_on_hotkey=merged_data.get('auto_voice_on_hotkey', False),
                auto_send_voice_input=merged_data.get('auto_send_voice_input', False),
                audio_devices_cache=merged_data.get('audio_devices_cache', []),
                audio_devices_cache_time=merged_data.get('audio_devices_cache_time', None)
            )
        except Exception as e:
            print(f"Error processing settings file: {e}")
            # Use default settings on error
            default_data = json.loads(default_settings_path.read_text(encoding="utf-8"))
            
            window_geometry_data = default_data.get('window_geometry', {})
            window_geometry = WindowGeometryConfig()
            if 'chat_only' in window_geometry_data:
                window_geometry.chat_only = ChatOnlyGeometry(**window_geometry_data['chat_only'])
            if 'full_content' in window_geometry_data:
                window_geometry.full_content = FullContentGeometry(**window_geometry_data['full_content'])
            if 'webview' in window_geometry_data:
                window_geometry.webview = WebViewGeometry(**window_geometry_data['webview'])
                
            return AppSettings(
                language=default_data.get('language', 'en'),
                hotkey=HotkeyConfig(**default_data.get('hotkey', {})),
                window_geometry=window_geometry,
                api=ApiConfig(**default_data.get('api', {})),
                dont_remind_api_missing=default_data.get('dont_remind_api_missing', False),
                backend=BackendConfig(**default_data.get('backend', {})),
                analytics=AnalyticsConfig(**default_data.get('analytics', {})),
                shortcuts=default_data.get('shortcuts', []),
                audio_device_index=default_data.get('audio_device_index', None),
                auto_voice_on_hotkey=default_data.get('auto_voice_on_hotkey', False),
                auto_send_voice_input=default_data.get('auto_send_voice_input', False),
                audio_devices_cache=default_data.get('audio_devices_cache', []),
                audio_devices_cache_time=default_data.get('audio_devices_cache_time', None)
            )

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
        except Exception as e:
            logger.error(f"Failed to load games config: {e}")
            
    def _ensure_language_configs_copied(self):
        """Ensure language-specific configuration files are copied to appdata directory"""
        try:
            # Language configuration files to copy
            language_files = ['games_en.json', 'games_zh.json', 'games.json']
            
            for filename in language_files:
                try:
                    # Get source file path (assets directory)
                    source_path = package_file(filename)
                    if not source_path.exists():
                        logger.warning(f"Language config file not found in assets: {filename}")
                        continue
                    
                    # Target file path (appdata directory)
                    target_path = self.path.parent / filename
                    
                    # If target file does not exist, or source file is updated, copy
                    if not target_path.exists() or source_path.stat().st_mtime > target_path.stat().st_mtime:
                        # Ensure target directory exists
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        # Copy file
                        shutil.copyfile(source_path, target_path)
                        logger.info(f"Language configuration file copied: {filename} -> {target_path}")
                    else:
                        logger.debug(f"Language configuration file already up to date: {filename}")
                        
                except Exception as e:
                    logger.error(f"Failed to copy language configuration file {filename}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to ensure language configuration file copy: {e}")
    
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
                
                # Save the config to the language-specific file
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(self._games, f, indent=2, ensure_ascii=False)
                logger.info(f"Created games config for language '{language}' at {config_path}")
                
        except Exception as e:
            logger.error(f"Failed to reload games config for language '{language}': {e}")
    
    def for_title(self, window_title: str) -> Optional[GameConfig]:
        """Get game configuration based on window title (backward compatibility)"""
        lower = window_title.lower()
        for name, cfg in self._games.items():
            if name.lower() in lower:
                # Convert dict to GameConfig for backward compatibility
                return GameConfig(
                    BaseUrl=cfg.get('BaseUrl', ''),
                    NeedsSearch=cfg.get('NeedsSearch', True)
                )
        return None
