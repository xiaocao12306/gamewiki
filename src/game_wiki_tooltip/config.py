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
    """LLM configuration class"""
    model: str = "gemini-2.5-flash-lite-preview-06-17"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 1000
    temperature: float = 0.7
    timeout: int = 30
    enable_cache: bool = True
    cache_ttl: int = 3600  # Cache TTL, seconds
    max_retries: int = 3
    retry_delay: float = 1.0
    
    def is_valid(self) -> bool:
        """Check if configuration is valid"""
        api_key = self.get_api_key()
        return bool(api_key and self.model)
    
    def get_api_key(self) -> Optional[str]:
        """Get API key, prioritize environment variable"""
        if self.api_key:
            return self.api_key
        
        # Get API key from environment variable based on model type
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
    # Use relative coordinates as default configuration
    use_relative_position: bool = True
    left_percent: float = 0.55  # 55% of screen width (right-center)
    top_percent: float = 0.1    # 10% of screen height (top margin)
    width_percent: float = 0.35 # 35% of screen width (medium size)
    height_percent: float = 0.65 # 65% of screen height (enough content display)
    use_relative_size: bool = True
    
    def get_absolute_geometry(self, screen_geometry=None):
        """
        Get absolute geometry information

        Args:
            screen_geometry: Screen geometry info. If None, will be auto-detected.

        Returns:
            tuple: (x, y, width, height) in absolute pixel coordinates
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
                    # If PyQt is not available, use default values
                    return self.left, self.top, self.width, self.height
        
        # Compatible with different types of screen_geometry objects
        def get_screen_value(obj, attr_name):
            """Get screen geometry attribute value, compatible with method calls and attribute access"""
            try:
                # First try method call (PyQt object)
                attr = getattr(obj, attr_name)
                if callable(attr):
                    return attr()
                else:
                    return attr
            except (AttributeError, TypeError):
                # If failed, try direct attribute access (test object)
                return getattr(obj, attr_name, 0)
        
        screen_x = get_screen_value(screen_geometry, 'x')
        screen_y = get_screen_value(screen_geometry, 'y') 
        screen_width = get_screen_value(screen_geometry, 'width')
        screen_height = get_screen_value(screen_geometry, 'height')
        
        # Calculate size (relative size)
        if self.use_relative_size:
            calc_width = int(screen_width * self.width_percent)
            calc_height = int(screen_height * self.height_percent)
            # Ensure minimum size (minimum width: 300px, maximum width: 1200px)
            calc_width = max(300, min(calc_width, 1200))
            calc_height = max(200, min(calc_height, 900))
        else:
            calc_width = self.width
            calc_height = self.height
        
        # Calculate position (relative position)    
        if self.use_relative_position:
            calc_x = int(screen_x + screen_width * self.left_percent)
            calc_y = int(screen_y + screen_height * self.top_percent)
        else:
            calc_x = self.left
            calc_y = self.top
        
        # Ensure window is visible on screen
        return self._ensure_window_visible(
            calc_x, calc_y, calc_width, calc_height, 
            screen_x, screen_y, screen_width, screen_height
        )
    
    def _ensure_window_visible(self, x, y, width, height, screen_x, screen_y, screen_width, screen_height):
        """
        Ensure window is visible on screen
        
        Args:
            x, y, width, height: Window geometry parameters
            screen_x, screen_y, screen_width, screen_height: Screen geometry parameters
            
        Returns:
            tuple: Adjusted (x, y, width, height)
        """
        # Minimum visible area (ensure user can see and operate window)
        min_visible_width = min(200, width // 2)
        min_visible_height = min(100, height // 4)
        
        # Right boundary check
        if x > screen_x + screen_width - min_visible_width:
            x = screen_x + screen_width - width - 10
        
        # Bottom boundary check  
        if y > screen_y + screen_height - min_visible_height:
            y = screen_y + screen_height - height - 10
        
        # Left boundary check
        if x < screen_x - width + min_visible_width:
            x = screen_x + 10
        
        # Top boundary check
        if y < screen_y:
            y = screen_y + 10
        
        # Size check - if window is larger than screen, adjust size
        max_width = screen_width - 20
        max_height = screen_height - 40  # Leave space for taskbar
        
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
        Create smart default configuration
        Use relative coordinate system, optimize percentage parameters based on screen size
        
        Args:
            screen_geometry: Screen geometry info
            
        Returns:
            PopupConfig: Smart default configuration instance
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
                    # Fall back to traditional fixed values
                    return cls()
        
        # Compatible with different types of screen_geometry objects
        def get_screen_value(obj, attr_name):
            """Get screen geometry attribute value, compatible with method calls and attribute access"""
            try:
                # First try method call (PyQt object)
                attr = getattr(obj, attr_name)
                if callable(attr):
                    return attr()
                else:
                    return attr
            except (AttributeError, TypeError):
                # If failed, try direct attribute access (test object)
                return getattr(obj, attr_name, 0)
        
        # Select configuration strategy based on screen size
        screen_width = get_screen_value(screen_geometry, 'width')
        screen_height = get_screen_value(screen_geometry, 'height')
        
        if screen_width >= 1920 and screen_height >= 1080:
            # Large screen: can use larger window and more right position
            return cls(
                use_relative_position=True,
                use_relative_size=True,
                left_percent=0.58,    # More to the right,充分利用大屏幕
                top_percent=0.08,     # Slightly up
                width_percent=0.38,   # Slightly larger width
                height_percent=0.75,  # Higher window
            )
        elif screen_width >= 1366 and screen_height >= 768:
            # Medium screen: balanced configuration
            return cls(
                use_relative_position=True,
                use_relative_size=True,
                left_percent=0.55,    # Standard right position
                top_percent=0.1,      # Standard top position
                width_percent=0.35,   # Standard width
                height_percent=0.65,  # Standard height
            )
        else:
            # Small screen: more compact configuration, ensure content visible
            return cls(
                use_relative_position=True,
                use_relative_size=True,
                left_percent=0.52,    # Slightly centered, avoid too close to edge
                top_percent=0.05,     # More up, save vertical space
                width_percent=0.42,   # More wide, ensure content readable
                height_percent=0.7,   # More high,充分利用屏幕
            )


@dataclass
class ApiConfig:
    gemini_api_key: str = ""
    jina_api_key: str = ""


@dataclass
class AppSettings:
    """Application settings"""
    language: str = "en"
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    popup: PopupConfig = field(default_factory=PopupConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    dont_remind_api_missing: bool = False  # User has selected "Don't remind me again" API missing
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
        # Update popup settings
        if 'popup' in new_settings:
            self._settings.popup = PopupConfig(**new_settings['popup'])
        # Update API settings
        if 'api' in new_settings:
            self._settings.api = ApiConfig(**new_settings['api'])
        # Update "Don't remind me again" settings
        if 'dont_remind_api_missing' in new_settings:
            self._settings.dont_remind_api_missing = new_settings['dont_remind_api_missing']
        # Update shortcuts settings
        if 'shortcuts' in new_settings:
            self._settings.shortcuts = new_settings['shortcuts']
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
        
        # If target file does not exist, or default file is newer than target file, copy default file
        if not self.path.exists() or default_settings_path.stat().st_mtime > self.path.stat().st_mtime:
            # First create target directory
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Copy default settings file
            shutil.copyfile(default_settings_path, self.path)
            print(f"Settings file updated: {self.path}")
            
        # Ensure roaming settings contains all necessary fields
        try:
            # Read default settings from project
            default_data = json.loads(default_settings_path.read_text(encoding="utf-8"))
            # Read existing settings from roaming
            existing_data = json.loads(self.path.read_text(encoding="utf-8"))
            
            # Merge settings, preserve user modifications but ensure all fields exist
            merged_data = self._merge_settings(default_data, existing_data)
            
            # Special handling: upgrade old popup configuration to new format
            merged_data = self._upgrade_popup_config(merged_data)
            
            # If merged data is different from existing data, save update
            if merged_data != existing_data:
                self.path.write_text(json.dumps(merged_data, indent=4, ensure_ascii=False), encoding="utf-8")
                print(f"Settings file fields synchronized: {self.path}")
            
            # Create AppSettings instance from merged data
            return AppSettings(
                language=merged_data.get('language', 'en'),
                hotkey=HotkeyConfig(**merged_data.get('hotkey', {})),
                popup=PopupConfig(**merged_data.get('popup', {})),
                api=ApiConfig(**merged_data.get('api', {})),
                dont_remind_api_missing=merged_data.get('dont_remind_api_missing', False),
                shortcuts=merged_data.get('shortcuts', [])
            )
        except Exception as e:
            print(f"Error processing settings file: {e}")
            # Use default settings on error
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
        Upgrade old popup configuration to new format
        Use smart relative coordinate system
        
        Args:
            data: settings data dictionary
            
        Returns:
            dict: upgraded settings data
        """
        popup = data.get('popup', {})
        
        # Check if upgrade is needed (missing new fields)
        new_fields = ['use_relative_position', 'left_percent', 'top_percent', 
                     'width_percent', 'height_percent', 'use_relative_size']
        needs_upgrade = not all(field in popup for field in new_fields)
        
        if needs_upgrade:
            print("🔄 Detected old popup configuration, upgrading to smart relative coordinate system...")
            
            # Check if there are basic coordinate information
            has_basic_coords = all(field in popup for field in ['left', 'top', 'width', 'height'])
            
            if has_basic_coords:
                # Keep original coordinates as fallback, but use relative coordinates
                left = popup.get('left', 100)
                top = popup.get('top', 50)
                width = popup.get('width', 600)
                height = popup.get('height', 500)
                
                # Check if the coordinates are extreme (e.g. too large or negative)
                is_extreme_coords = (left > 3000 or top > 2000 or 
                                   left < 0 or top < 0 or 
                                   width > 2000 or height > 1500 or
                                   width < 100 or height < 100)
                
                if is_extreme_coords:
                    print(f"⚠️  Detected extreme coordinate values, using standard smart configuration")
                    # Use standard smart relative coordinates
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
                    # Normal coordinates, upgrade to smart relative coordinates
                    popup.update({
                        'use_relative_position': True,
                        'left_percent': 0.55,
                        'top_percent': 0.1,
                        'width_percent': 0.35,
                        'height_percent': 0.65,
                        'use_relative_size': True
                    })
                    
                print(f"✅ Upgraded to smart relative coordinate configuration (original coordinates: {left},{top},{width}x{height})")
            else:
                # No basic coordinates, create standard smart configuration
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
                print(f"✅ Created standard smart relative coordinate configuration")
            
            data['popup'] = popup
        else:
            # New fields exist, check if fixed coordinates need to be migrated to relative coordinates
            if not popup.get('use_relative_position', True):
                print("🔄 Detected fixed coordinate configuration, suggesting upgrade to relative coordinates...")
                popup['use_relative_position'] = True
                popup['use_relative_size'] = True
                popup['left_percent'] = 0.55
                popup['top_percent'] = 0.1
                popup['width_percent'] = 0.35
                popup['height_percent'] = 0.65
                print(f"✅ Upgraded from fixed coordinates to smart relative coordinates")
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
