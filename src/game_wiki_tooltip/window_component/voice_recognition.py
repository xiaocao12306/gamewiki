"""Voice recognition module for speech-to-text input."""

import json
import os
import sys
import logging
import threading
import time
from pathlib import Path
from typing import Optional
from threading import Lock

try:
    import pyaudio
    from vosk import Model, KaldiRecognizer, SetLogLevel
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logging.warning("Vosk or PyAudio not available. Voice input will be disabled.")

from PyQt6.QtCore import QThread, pyqtSignal, QObject

from src.game_wiki_tooltip.core.utils import package_file
from src.game_wiki_tooltip.core.i18n import get_current_language

logger = logging.getLogger(__name__)

# Suppress Vosk logging
if VOSK_AVAILABLE:
    SetLogLevel(-1)

# Global cache variables for audio devices
_audio_devices_cache = None
_cache_timestamp = 0
_last_refresh_time = 0
_refresh_lock = Lock()
CACHE_DURATION = 3600  # Cache for 1 hour
REFRESH_COOLDOWN = 2  # Refresh cooldown time in seconds


class VoiceRecognitionThread(QThread):
    """Thread for handling voice recognition without blocking UI."""
    
    # Signals
    partial_result = pyqtSignal(str)  # Real-time partial text
    final_result = pyqtSignal(str)    # Complete sentence
    error_occurred = pyqtSignal(str)  # Error messages
    silence_detected = pyqtSignal()   # Emitted when silence is detected
    
    def __init__(self, device_index: Optional[int] = None, silence_threshold: float = 2.0):
        super().__init__()
        self.is_recording = False
        self.model = None
        self.recognizer = None
        self.audio_stream = None
        self.pyaudio_instance = None
        self.device_index = device_index  # Allow specifying audio device
        self.silence_threshold = silence_threshold  # Seconds of silence before auto-stop
        self.last_activity_time = time.time()
        self._last_text = ""  # Track text changes for activity detection
        
        # Model paths - use package_file for consistency
        try:
            # Try to use package_file first (works in both dev and packaged)
            self.models_dir = package_file("vosk_models")
        except Exception:
            # Fallback for edge cases
            base_path = Path(__file__).parent.parent.parent
            self.models_dir = base_path / "assets" / "vosk_models"
        
    def initialize_model(self):
        """Initialize Vosk model based on current language."""
        if not VOSK_AVAILABLE:
            self.error_occurred.emit("Voice recognition not available. Please install vosk and pyaudio.")
            return False
            
        current_lang = get_current_language()
        
        # Model mapping
        model_names = {
            'zh': 'vosk-model-small-cn-0.22',
            'en': 'vosk-model-small-en-us-0.15'
        }
        
        model_name = model_names.get(current_lang, model_names['en'])
        model_path = self.models_dir / model_name
        
        try:
            if not model_path.exists():
                error_msg = (
                    f"Voice model not found: {model_name}\n"
                    f"Please run 'python download_vosk_models.py' from project root\n"
                    f"or download from https://alphacephei.com/vosk/models\n"
                    f"and extract to: {self.models_dir}"
                )
                self.error_occurred.emit(error_msg)
                return False
                
            logger.info(f"Loading voice model: {model_name}")
            self.model = Model(str(model_path))
            # Note: recognizer sample rate will be set when opening audio stream
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"Failed to load model: {str(e)}")
            logger.error(f"Model loading error: {e}")
            return False
    
    def run(self):
        """Main voice recognition loop."""
        if not self.initialize_model():
            return
            
        try:
            # Initialize PyAudio
            self.pyaudio_instance = pyaudio.PyAudio()
            
            # Use specified device or find a working input device
            if self.device_index is not None:
                # Validate specified device
                try:
                    device_info = self.pyaudio_instance.get_device_info_by_index(self.device_index)
                    if device_info['maxInputChannels'] > 0:
                        device_index = self.device_index
                        logger.info(f"Using specified audio input device: {device_info['name']}")
                    else:
                        self.error_occurred.emit(f"Specified device {self.device_index} is not an input device.")
                        return
                except Exception as e:
                    self.error_occurred.emit(f"Invalid device index {self.device_index}: {str(e)}")
                    return
            else:
                # Try to find a working input device
                device_index = None
                for i in range(self.pyaudio_instance.get_device_count()):
                    device_info = self.pyaudio_instance.get_device_info_by_index(i)
                    if device_info['maxInputChannels'] > 0:
                        device_index = i
                        logger.info(f"Using audio input device: {device_info['name']}")
                        break
                        
                if device_index is None:
                    self.error_occurred.emit("No microphone found. Please check your audio input devices.")
                    return
            
            # Try multiple sample rates for better compatibility
            SAMPLE_RATES = [16000, 44100, 48000, 22050, 8000]
            audio_opened = False
            used_sample_rate = None
            
            for sample_rate in SAMPLE_RATES:
                try:
                    self.audio_stream = self.pyaudio_instance.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=sample_rate,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=4000
                    )
                    # Successfully opened stream, create recognizer with this sample rate
                    self.recognizer = KaldiRecognizer(self.model, sample_rate)
                    self.recognizer.SetWords(True)
                    used_sample_rate = sample_rate
                    audio_opened = True
                    logger.info(f"Audio stream opened successfully with sample rate: {sample_rate} Hz")
                    break
                except Exception as e:
                    logger.debug(f"Failed to open audio stream with {sample_rate} Hz: {e}")
                    if sample_rate == SAMPLE_RATES[-1]:
                        # Last sample rate failed
                        self.error_occurred.emit(f"Could not open audio stream. Tried sample rates: {SAMPLE_RATES}")
                        return
                    continue
            
            if not audio_opened:
                self.error_occurred.emit("Failed to open audio stream with any supported sample rate.")
                return
            
            self.is_recording = True
            logger.info("Voice recording started")
            self.last_activity_time = time.time()  # Reset activity timer
            
            while self.is_recording:
                try:
                    data = self.audio_stream.read(4000, exception_on_overflow=False)
                    
                    if self.recognizer.AcceptWaveform(data):
                        # Complete result
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip()
                        if text:
                            self.final_result.emit(text)
                            # Update activity time when we get actual speech
                            self.last_activity_time = time.time()
                            self._last_text = text
                    else:
                        # Partial result
                        partial = json.loads(self.recognizer.PartialResult())
                        text = partial.get('partial', '').strip()
                        if text:
                            self.partial_result.emit(text)
                            # Update activity time if text has changed (indicating speech)
                            if text != self._last_text:
                                self.last_activity_time = time.time()
                                self._last_text = text
                    
                    # Check for silence timeout
                    current_time = time.time()
                    if current_time - self.last_activity_time > self.silence_threshold:
                        logger.info(f"Silence detected for {self.silence_threshold} seconds, auto-stopping recording")
                        self.silence_detected.emit()
                        self.is_recording = False
                        break
                            
                except Exception as e:
                    if self.is_recording:  # Only log if we're still supposed to be recording
                        logger.error(f"Audio processing error: {e}")
                        
        except Exception as e:
            self.error_occurred.emit(f"Recording error: {str(e)}")
            logger.error(f"Voice recording error: {e}")
        finally:
            self.cleanup()
    
    def stop_recording(self):
        """Stop the recording."""
        if not self.is_recording:
            logger.debug("Recording already stopped")
            return
            
        self.is_recording = False
        logger.info("Voice recording stopped")
        
    def cleanup(self):
        """Clean up audio resources."""
        if self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
                
        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")


def check_voice_models():
    """Check if voice models are installed."""
    try:
        # Use package_file for consistency
        models_dir = package_file("vosk_models")
    except Exception:
        # Fallback
        base_path = Path(__file__).parent.parent.parent
        models_dir = base_path / "assets" / "vosk_models"
    
    model_info = {
        'zh': {
            'name': 'vosk-model-small-cn-0.22',
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip',
            'size': '42 MB'
        },
        'en': {
            'name': 'vosk-model-small-en-us-0.15',
            'url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip',
            'size': '40 MB'
        }
    }
    
    current_lang = get_current_language()
    model_name = model_info[current_lang]['name']
    model_path = models_dir / model_name
    
    if not model_path.exists():
        return False, model_info[current_lang]
    
    return True, None


def is_voice_recognition_available():
    """Check if voice recognition is available."""
    return VOSK_AVAILABLE


def get_audio_input_devices(force_refresh=False, settings_manager=None):
    """Get list of available audio input devices, filtering duplicates and invalid devices.
    
    Args:
        force_refresh: Force re-enumeration of devices, bypassing cache
        settings_manager: Optional SettingsManager instance to save cache to settings
        
    Returns:
        List of audio device dictionaries
    """
    global _audio_devices_cache, _cache_timestamp, _last_refresh_time
    
    if not VOSK_AVAILABLE:
        return []
    
    current_time = time.time()
    
    # Try to load from settings cache first (if not forcing refresh)
    if not force_refresh and settings_manager:
        settings = settings_manager.get()
        cache_time = settings.get('audio_devices_cache_time', 0)
        cache_data = settings.get('audio_devices_cache', [])
        
        # Use settings cache if it's less than 7 days old
        if cache_data and cache_time and (current_time - cache_time < 7 * 24 * 3600):
            logger.info(f"Using audio devices from settings cache (age: {(current_time - cache_time) / 3600:.1f} hours)")
            _audio_devices_cache = cache_data
            _cache_timestamp = cache_time
            return cache_data
    
    # Check for refresh cooldown if force_refresh is requested
    if force_refresh:
        with _refresh_lock:
            if current_time - _last_refresh_time < REFRESH_COOLDOWN:
                logger.info(f"Refresh cooldown active ({REFRESH_COOLDOWN}s), using cached devices")
                if _audio_devices_cache is not None:
                    return _audio_devices_cache
                force_refresh = False  # Downgrade to normal request
            else:
                _last_refresh_time = current_time
    
    # Return memory cache if available and not forcing refresh
    if not force_refresh and _audio_devices_cache is not None:
        if current_time - _cache_timestamp < CACHE_DURATION:
            logger.info("Using memory cached audio devices")
            return _audio_devices_cache
    
    logger.info("Enumerating audio devices...")
    
    import re
    devices = []
    seen_base_names = {}  # Track unique device base names
    test_streams = []  # Keep track of test streams to ensure they're closed
    
    # System/virtual devices to filter out
    SYSTEM_DEVICES = [
        "Microsoft Sound Mapper",
        "Microsoft 声音映射器", 
        "主声音捕获驱动程序",
        "Primary Sound Capture Driver",
        "Microphone Array (Intel® Smart Sound Technology",  # Often problematic
    ]
    
    # API type indicators in device names
    API_PATTERNS = r'\s*\((MME|DirectSound|WASAPI|WDM-KS|Windows DirectSound|Windows WASAPI|Windows WDM-KS)\)'
    
    p = None
    try:
        p = pyaudio.PyAudio()
        
        for i in range(p.get_device_count()):
            try:
                device_info = p.get_device_info_by_index(i)
                
                # Only process input devices
                if device_info['maxInputChannels'] <= 0:
                    continue
                
                name = device_info['name']
                
                # Skip system/mapper devices
                if any(sys_dev in name for sys_dev in SYSTEM_DEVICES):
                    continue
                
                # Test if device is actually available
                # Try to open a stream briefly to check if device works
                test_stream = None
                try:
                    test_stream = p.open(
                        format=pyaudio.paInt16,
                        channels=min(1, device_info['maxInputChannels']),
                        rate=int(device_info['defaultSampleRate']),
                        input=True,
                        input_device_index=i,
                        frames_per_buffer=1024,
                        start=False  # Don't actually start the stream
                    )
                    # Add to list for cleanup
                    test_streams.append(test_stream)
                except Exception as e:
                    # Device not actually available, skip it
                    logger.debug(f"Skipping unavailable device: {name} (index {i}): {e}")
                    if test_stream:
                        try:
                            test_stream.close()
                        except:
                            pass
                    continue
                
                # Extract base name (remove API type suffix)
                clean_name = re.sub(API_PATTERNS, '', name).strip()
                
                # Remove index numbers that Windows sometimes adds
                clean_name = re.sub(r'\s*\(\d+\)$', '', clean_name)
                clean_name = re.sub(r'\s*\[\d+\]$', '', clean_name)
                
                # Check if we've seen this base device name
                if clean_name in seen_base_names:
                    # Keep the one with better properties (higher sample rate or more channels)
                    existing = seen_base_names[clean_name]
                    if (device_info['defaultSampleRate'] > existing['default_sample_rate'] or
                        device_info['maxInputChannels'] > existing['channels']):
                        # This version is better, replace
                        seen_base_names[clean_name] = {
                            'index': i,
                            'name': clean_name,
                            'channels': device_info['maxInputChannels'],
                            'default_sample_rate': device_info['defaultSampleRate'],
                            'original_name': name  # Keep original for debugging
                        }
                else:
                    # First time seeing this device
                    seen_base_names[clean_name] = {
                        'index': i,
                        'name': clean_name,
                        'channels': device_info['maxInputChannels'],
                        'default_sample_rate': device_info['defaultSampleRate'],
                        'original_name': name
                    }
                    
            except Exception as e:
                logger.debug(f"Error processing device {i}: {e}")
                continue
        
        # Convert to list, removing debug info
        for device_data in seen_base_names.values():
            devices.append({
                'index': device_data['index'],
                'name': device_data['name'],
                'channels': device_data['channels'],
                'default_sample_rate': device_data['default_sample_rate']
            })
        
        # Sort by name for consistent display
        devices.sort(key=lambda d: d['name'])
        
        logger.info(f"Found {len(devices)} unique audio input devices")
        
        # Update memory cache
        _audio_devices_cache = devices
        _cache_timestamp = current_time
        
        # Save to settings if manager provided
        if settings_manager:
            try:
                settings_manager.update({
                    'audio_devices_cache': devices,
                    'audio_devices_cache_time': current_time
                })
                logger.info("Audio devices cache saved to settings")
            except Exception as e:
                logger.warning(f"Failed to save audio devices cache to settings: {e}")
        
    except Exception as e:
        logger.error(f"Error getting audio devices: {e}")
        # Return cached devices if available on error
        if _audio_devices_cache is not None:
            logger.info("Returning cached devices due to enumeration error")
            return _audio_devices_cache
    finally:
        # Ensure all test streams are closed
        for stream in test_streams:
            try:
                if stream and not stream.is_stopped():
                    stream.stop_stream()
                if stream:
                    stream.close()
            except Exception as e:
                logger.debug(f"Error closing test stream: {e}")
        
        # Safely terminate PyAudio
        if p:
            try:
                # Small delay to ensure all streams are fully closed
                time.sleep(0.1)
                p.terminate()
                logger.debug("PyAudio terminated successfully")
            except Exception as e:
                logger.warning(f"Error terminating PyAudio (non-critical): {e}")
    
    return devices


def initialize_audio_devices(settings_manager=None):
    """Initialize audio device cache on program startup.
    
    This function checks if audio devices are cached in settings.
    If cache exists and is recent (< 7 days), skip enumeration.
    Otherwise, enumerate devices and save to cache.
    
    Args:
        settings_manager: Optional SettingsManager instance to load/save cache
    """
    if not VOSK_AVAILABLE:
        logger.info("Voice recognition not available, skipping audio device initialization")
        return
    
    # Check if we have a recent cache in settings
    if settings_manager:
        settings = settings_manager.get()
        cache_time = settings.get('audio_devices_cache_time', 0)
        cache_data = settings.get('audio_devices_cache', [])
        
        if cache_data and cache_time:
            age_days = (time.time() - cache_time) / (24 * 3600)
            if age_days < 7:
                logger.info(f"Audio devices cache found in settings (age: {age_days:.1f} days), skipping enumeration")
                # Load cache into memory
                global _audio_devices_cache, _cache_timestamp
                _audio_devices_cache = cache_data
                _cache_timestamp = cache_time
                return
            else:
                logger.info(f"Audio devices cache is stale (age: {age_days:.1f} days), will enumerate")
    
    # Add a small delay to ensure Qt/system is ready
    time.sleep(0.5)
    
    logger.info("Initializing audio devices (first run or stale cache)...")
    try:
        # Enumerate devices and save to cache
        devices = get_audio_input_devices(force_refresh=True, settings_manager=settings_manager)
        logger.info(f"Audio device initialization complete. Found {len(devices)} devices.")
    except Exception as e:
        logger.error(f"Failed to initialize audio devices: {e}")
        # Don't let audio initialization failure crash the app
        import traceback
        logger.debug(f"Audio initialization traceback: {traceback.format_exc()}")