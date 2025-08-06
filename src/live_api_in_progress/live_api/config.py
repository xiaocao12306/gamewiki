"""
Configuration settings for Live API application.
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass
class AudioConfig:
    """Audio configuration settings."""
    # Input (Vosk)
    input_sample_rate: int = 16000
    input_channels: int = 1
    input_chunk_size: int = 4096
    
    # Output (Live API)
    output_sample_rate: int = 24000
    output_channels: int = 1
    output_chunk_size: int = 1024
    
    # Voice Activity Detection
    silence_threshold: float = 1.5  # seconds
    
    # Buffer settings
    buffer_size: int = 10  # queue size for audio chunks
    
    # Device settings
    input_device_index: Optional[int] = None
    output_device_index: Optional[int] = None


@dataclass
class VoskConfig:
    """Vosk speech recognition configuration."""
    models_dir: str = str(Path(__file__).parent.parent / "game_wiki_tooltip" / "assets" / "vosk_models")
    model_names: Dict[str, str] = field(default_factory=lambda: {
        'en': 'vosk-model-small-en-us-0.15',
        'zh': 'vosk-model-small-cn-0.22'
    })
    default_language: str = 'en'


@dataclass
class LiveAPISettings:
    """Gemini Live API settings."""
    model: str = "gemini-2.5-flash-preview-native-audio-dialog"
    
    # Available voices for Live API
    available_voices: List[str] = field(default_factory=lambda: [
        "Kore",      # Default voice
        "Puck",      # Alternative voice
        "Charon",    # Deep voice
        "Fenrir",    # Another option
        "Aoede",     # Female voice
    ])
    
    default_voice: str = "Kore"
    
    # Response configuration
    enable_affective_dialog: bool = True  # Emotion-aware responses
    enable_proactive_audio: bool = True   # Selective response to background
    
    # System instructions for different modes
    system_instructions: Dict[str, str] = field(default_factory=lambda: {
        "default": (
            "You are a helpful and friendly AI assistant. "
            "Respond naturally and conversationally. "
            "Keep your responses concise and engaging."
        ),
        "casual": (
            "You are a casual, friendly companion. "
            "Chat naturally, use informal language, and be engaging. "
            "Feel free to ask questions and show interest."
        ),
        "professional": (
            "You are a professional assistant. "
            "Provide clear, accurate, and helpful responses. "
            "Maintain a professional but friendly tone."
        ),
        "creative": (
            "You are a creative and imaginative assistant. "
            "Be playful with language, use metaphors, and think outside the box. "
            "Make conversations interesting and thought-provoking."
        )
    })
    
    default_mode: str = "default"
    
    # Session settings
    session_timeout: int = 600  # 10 minutes in seconds
    auto_extend_session: bool = True
    
    # Connection settings
    max_reconnect_attempts: int = 3
    reconnect_delay: float = 2.0  # seconds


@dataclass
class UIConfig:
    """User interface configuration."""
    window_title: str = "Gemini Live API Assistant"
    window_width: int = 800
    window_height: int = 600
    
    # Theme settings
    dark_mode: bool = True
    
    # Display settings
    show_partial_text: bool = True
    show_connection_status: bool = True
    show_audio_visualizer: bool = True
    
    # History settings
    max_history_display: int = 50  # Maximum turns to display
    auto_scroll: bool = True
    
    # Font settings
    font_family: str = "Segoe UI"
    font_size: int = 10
    
    # Colors (hex)
    user_text_color: str = "#4A90E2"
    ai_text_color: str = "#7B68EE"
    system_text_color: str = "#95A5A6"


@dataclass
class AppConfig:
    """Main application configuration."""
    # API key (from environment or user input)
    api_key: Optional[str] = None
    
    # Sub-configurations
    audio: AudioConfig = field(default_factory=AudioConfig)
    vosk: VoskConfig = field(default_factory=VoskConfig)
    live_api: LiveAPISettings = field(default_factory=LiveAPISettings)
    ui: UIConfig = field(default_factory=UIConfig)
    
    # Application settings
    auto_start_listening: bool = True
    save_conversation_history: bool = True
    history_dir: str = "conversation_history"
    
    # Language settings
    default_language: str = "en"
    supported_languages: List[str] = field(default_factory=lambda: ["en", "zh"])
    
    # Debug settings
    debug_mode: bool = False
    log_level: str = "INFO"
    log_file: Optional[str] = "live_api.log"
    
    @classmethod
    def load_from_file(cls, config_path: str) -> 'AppConfig':
        """Load configuration from JSON file."""
        config_path = Path(config_path)
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Create nested dataclass instances
                if 'audio' in data:
                    data['audio'] = AudioConfig(**data['audio'])
                if 'vosk' in data:
                    data['vosk'] = VoskConfig(**data['vosk'])
                if 'live_api' in data:
                    data['live_api'] = LiveAPISettings(**data['live_api'])
                if 'ui' in data:
                    data['ui'] = UIConfig(**data['ui'])
                
                return cls(**data)
        
        return cls()
    
    def save_to_file(self, config_path: str):
        """Save configuration to JSON file."""
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict
        data = asdict(self)
        
        # Remove None API key from saved config for security
        if 'api_key' in data:
            data['api_key'] = None
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_api_key(self) -> Optional[str]:
        """Get API key from config or environment."""
        if self.api_key:
            return self.api_key
        
        # Try environment variables
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    
    def get_vosk_model_path(self, language: str) -> Path:
        """Get the path to Vosk model for given language."""
        model_name = self.vosk.model_names.get(language, self.vosk.model_names['en'])
        return Path(self.vosk.models_dir) / model_name
    
    def get_system_instruction(self, mode: Optional[str] = None) -> str:
        """Get system instruction for given mode."""
        if mode is None:
            mode = self.live_api.default_mode
        
        return self.live_api.system_instructions.get(
            mode,
            self.live_api.system_instructions['default']
        )


# Global config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        # Try to load from default location
        default_config_path = Path.home() / ".live_api" / "config.json"
        if default_config_path.exists():
            _config = AppConfig.load_from_file(str(default_config_path))
        else:
            _config = AppConfig()
    
    return _config


def set_config(config: AppConfig):
    """Set the global configuration instance."""
    global _config
    _config = config


def reset_config():
    """Reset configuration to defaults."""
    global _config
    _config = AppConfig()


# Example usage
if __name__ == "__main__":
    # Create default config
    config = AppConfig()
    
    # Save to file
    config.save_to_file("example_config.json")
    
    # Load from file
    loaded_config = AppConfig.load_from_file("example_config.json")
    
    # Get API key
    api_key = loaded_config.get_api_key()
    print(f"API Key available: {api_key is not None}")
    
    # Get Vosk model path
    model_path = loaded_config.get_vosk_model_path("en")
    print(f"Vosk model path: {model_path}")
    
    # Get system instruction
    instruction = loaded_config.get_system_instruction("casual")
    print(f"System instruction: {instruction}")