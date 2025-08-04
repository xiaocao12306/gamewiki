"""Voice recognition module for speech-to-text input."""

import json
import os
import sys
import logging
import threading
from pathlib import Path
from typing import Optional

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


class VoiceRecognitionThread(QThread):
    """Thread for handling voice recognition without blocking UI."""
    
    # Signals
    partial_result = pyqtSignal(str)  # Real-time partial text
    final_result = pyqtSignal(str)    # Complete sentence
    error_occurred = pyqtSignal(str)  # Error messages
    
    def __init__(self, device_index: Optional[int] = None):
        super().__init__()
        self.is_recording = False
        self.model = None
        self.recognizer = None
        self.audio_stream = None
        self.pyaudio_instance = None
        self.device_index = device_index  # Allow specifying audio device
        
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
            self.recognizer = KaldiRecognizer(self.model, 16000)
            self.recognizer.SetWords(True)
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
            
            self.audio_stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=4000
            )
            
            self.is_recording = True
            logger.info("Voice recording started")
            
            while self.is_recording:
                try:
                    data = self.audio_stream.read(4000, exception_on_overflow=False)
                    
                    if self.recognizer.AcceptWaveform(data):
                        # Complete result
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip()
                        if text:
                            self.final_result.emit(text)
                    else:
                        # Partial result
                        partial = json.loads(self.recognizer.PartialResult())
                        text = partial.get('partial', '').strip()
                        if text:
                            self.partial_result.emit(text)
                            
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


def get_audio_input_devices():
    """Get list of available audio input devices."""
    if not VOSK_AVAILABLE:
        return []
    
    devices = []
    try:
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': device_info['name'],
                    'channels': device_info['maxInputChannels'],
                    'default_sample_rate': device_info['defaultSampleRate']
                })
        p.terminate()
    except Exception as e:
        logger.error(f"Error getting audio devices: {e}")
    
    return devices