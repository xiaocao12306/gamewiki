"""
Continuous voice listener using Vosk for local speech recognition.
Provides real-time speech-to-text with automatic sentence detection.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Callable
from queue import Queue, Empty

try:
    import pyaudio
    from vosk import Model, KaldiRecognizer, SetLogLevel
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logging.warning("Vosk or PyAudio not available. Voice input will be disabled.")

logger = logging.getLogger(__name__)

# Suppress Vosk logging
if VOSK_AVAILABLE:
    SetLogLevel(-1)


class ContinuousVoiceListener:
    """
    Continuous voice listener that automatically detects speech
    and converts it to text using Vosk.
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        language: str = "en",
        on_partial_text: Optional[Callable[[str], None]] = None,
        on_final_text: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        device_index: Optional[int] = None
    ):
        """
        Initialize the continuous voice listener.
        
        Args:
            model_path: Path to Vosk model directory
            language: Language code ('en' or 'zh')
            on_partial_text: Callback for partial recognition results
            on_final_text: Callback for complete sentences
            on_error: Callback for error messages
            device_index: Audio device index (None for default)
        """
        self.model_path = model_path
        self.language = language
        self.on_partial_text = on_partial_text
        self.on_final_text = on_final_text
        self.on_error = on_error
        self.device_index = device_index
        
        self.model = None
        self.recognizer = None
        self.audio_stream = None
        self.pyaudio_instance = None
        self.is_listening = False
        self.listener_thread = None
        self.silence_threshold = 1.5  # seconds of silence to trigger sentence end
        self.last_speech_time = time.time()
        self.accumulated_text = ""
        
        # Audio parameters
        self.sample_rate = 16000
        self.chunk_size = 4096
        self.format = pyaudio.paInt16
        self.channels = 1
        
        # Initialize model on creation
        self._initialize_model()
    
    def _initialize_model(self) -> bool:
        """Initialize Vosk model based on language setting."""
        if not VOSK_AVAILABLE:
            if self.on_error:
                self.on_error("Voice recognition not available. Please install vosk and pyaudio.")
            return False
        
        # Default model paths if not specified
        if not self.model_path:
            base_path = Path(__file__).parent.parent / "game_wiki_tooltip" / "assets" / "vosk_models"
            model_names = {
                'zh': 'vosk-model-small-cn-0.22',
                'en': 'vosk-model-small-en-us-0.15'
            }
            model_name = model_names.get(self.language, model_names['en'])
            self.model_path = base_path / model_name
        else:
            self.model_path = Path(self.model_path)
        
        try:
            if not self.model_path.exists():
                error_msg = f"Voice model not found at: {self.model_path}"
                if self.on_error:
                    self.on_error(error_msg)
                logger.error(error_msg)
                return False
            
            logger.info(f"Loading voice model from: {self.model_path}")
            self.model = Model(str(self.model_path))
            self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
            self.recognizer.SetWords(True)
            return True
            
        except Exception as e:
            error_msg = f"Failed to load model: {str(e)}"
            if self.on_error:
                self.on_error(error_msg)
            logger.error(error_msg)
            return False
    
    def start_listening(self):
        """Start continuous listening in a separate thread."""
        if self.is_listening:
            logger.warning("Already listening")
            return
        
        if not self.model:
            if not self._initialize_model():
                return
        
        self.is_listening = True
        self.listener_thread = threading.Thread(target=self._listening_loop, daemon=True)
        self.listener_thread.start()
        logger.info("Started continuous voice listening")
    
    def stop_listening(self):
        """Stop the continuous listening."""
        if not self.is_listening:
            return
        
        self.is_listening = False
        
        # Close audio stream
        if self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
        
        # Terminate PyAudio
        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")
        
        # Wait for thread to finish
        if self.listener_thread:
            self.listener_thread.join(timeout=2.0)
        
        logger.info("Stopped continuous voice listening")
    
    def _listening_loop(self):
        """Main listening loop running in separate thread."""
        try:
            # Initialize PyAudio
            self.pyaudio_instance = pyaudio.PyAudio()
            
            # Open audio stream
            self.audio_stream = self.pyaudio_instance.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=self.device_index
            )
            
            logger.info("Audio stream opened, starting recognition loop")
            
            while self.is_listening:
                try:
                    # Read audio chunk
                    data = self.audio_stream.read(self.chunk_size, exception_on_overflow=False)
                    
                    # Process with Vosk
                    if self.recognizer.AcceptWaveform(data):
                        # Final result for this segment
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip()
                        
                        if text:
                            self.accumulated_text += " " + text if self.accumulated_text else text
                            self.last_speech_time = time.time()
                            
                            # Send final text
                            if self.on_final_text and self.accumulated_text:
                                self.on_final_text(self.accumulated_text.strip())
                                self.accumulated_text = ""
                    else:
                        # Partial result
                        partial = json.loads(self.recognizer.PartialResult())
                        partial_text = partial.get('partial', '').strip()
                        
                        if partial_text:
                            self.last_speech_time = time.time()
                            
                            # Send partial text for real-time feedback
                            if self.on_partial_text:
                                display_text = self.accumulated_text + " " + partial_text if self.accumulated_text else partial_text
                                self.on_partial_text(display_text.strip())
                        else:
                            # Check for silence timeout
                            if self.accumulated_text and (time.time() - self.last_speech_time > self.silence_threshold):
                                # Silence detected, send accumulated text as final
                                if self.on_final_text:
                                    self.on_final_text(self.accumulated_text.strip())
                                self.accumulated_text = ""
                    
                except Exception as e:
                    if self.is_listening:  # Only log if we're still supposed to be listening
                        logger.error(f"Error in recognition loop: {e}")
                        if self.on_error:
                            self.on_error(f"Recognition error: {str(e)}")
            
        except Exception as e:
            error_msg = f"Failed to initialize audio: {str(e)}"
            logger.error(error_msg)
            if self.on_error:
                self.on_error(error_msg)
        
        finally:
            # Cleanup
            if self.audio_stream:
                try:
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except:
                    pass
            
            if self.pyaudio_instance:
                try:
                    self.pyaudio_instance.terminate()
                except:
                    pass
    
    def pause(self):
        """Temporarily pause listening without closing the stream."""
        self.is_listening = False
        logger.info("Paused voice listening")
    
    def resume(self):
        """Resume listening after pause."""
        if not self.listener_thread or not self.listener_thread.is_alive():
            self.start_listening()
        else:
            self.is_listening = True
            logger.info("Resumed voice listening")
    
    def set_language(self, language: str):
        """
        Change the recognition language.
        
        Args:
            language: Language code ('en' or 'zh')
        """
        if language != self.language:
            self.language = language
            was_listening = self.is_listening
            
            if was_listening:
                self.stop_listening()
            
            # Reinitialize model with new language
            self.model = None
            self.model_path = None
            self._initialize_model()
            
            if was_listening:
                self.start_listening()
    
    def __del__(self):
        """Cleanup on deletion."""
        self.stop_listening()


# Example usage
if __name__ == "__main__":
    def on_partial(text):
        print(f"Partial: {text}")
    
    def on_final(text):
        print(f"Final: {text}")
    
    def on_error(error):
        print(f"Error: {error}")
    
    listener = ContinuousVoiceListener(
        language="en",
        on_partial_text=on_partial,
        on_final_text=on_final,
        on_error=on_error
    )
    
    listener.start_listening()
    
    try:
        # Keep listening
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        listener.stop_listening()
        print("Stopped listening")