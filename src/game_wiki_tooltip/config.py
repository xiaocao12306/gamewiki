"""
Configuration management – settings and game configs.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional

from src.game_wiki_tooltip.utils import APPDATA_DIR, package_file


# ---------- LLM Configuration ----------

@dataclass
class LLMConfig:
    """LLM配置类"""
    model: str = "gemini-1.5-flash"
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
class AppSettings:
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    popup: PopupConfig = field(default_factory=PopupConfig)


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
        # 更新热键设置
        if 'hotkey' in new_settings:
            self._settings.hotkey = HotkeyConfig(**new_settings['hotkey'])
            # 更新弹窗设置
        if 'popup' in new_settings:
            self._settings.popup = PopupConfig(**new_settings['popup'])
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
            return AppSettings(hotkey=hotkey, popup=popup)
        except Exception as e:
            print(f"加载设置文件失败: {e}")
            return AppSettings()


# ---------- Game-configs ----------

@dataclass
class GameConfig:
    BaseUrl: str
    NeedsSearch: bool = True


class GameConfigManager:
    def __init__(self, path: pathlib.Path):
        # 获取默认游戏配置文件路径
        default_games_path = package_file("games.json")
        
        # 如果目标文件不存在，或者默认文件比目标文件新，则复制默认文件
        if not path.exists() or default_games_path.stat().st_mtime > path.stat().st_mtime:
            # 先创建目标目录
            path.parent.mkdir(parents=True, exist_ok=True)
            # 复制默认游戏配置文件
            shutil.copyfile(default_games_path, path)
            print(f"已更新游戏配置文件: {path}")
            
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._configs: Dict[str, GameConfig] = {}
        for k, v in raw.items():
            if isinstance(v, str):
                self._configs[k.lower()] = GameConfig(
                    BaseUrl=v
                )
            else:
                # 只保留 GameConfig 支持的字段
                filtered_v = {
                    'BaseUrl': v.get('BaseUrl'),
                    'NeedsSearch': v.get('NeedsSearch', True)
                }
                self._configs[k.lower()] = GameConfig(**filtered_v)

    def for_title(self, window_title: str) -> Optional[GameConfig]:
        """根据窗口标题获取游戏配置"""
        lower = window_title.lower()
        for name, cfg in self._configs.items():
            if name in lower:
                return cfg
        return None
