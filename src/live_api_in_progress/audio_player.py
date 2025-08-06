"""
Audio player for streaming PCM audio from Live API.
Handles 24kHz PCM audio playback with buffering.
"""

import logging
import threading
import queue
import struct
from typing import Optional
import numpy as np

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    logging.warning("PyAudio not available. Audio playback will be disabled.")

logger = logging.getLogger(__name__)


class StreamingAudioPlayer:
    """
    Streaming audio player for real-time PCM audio playback.
    Optimized for Live API's 24kHz output.
    """
    
    def __init__(
        self,
        sample_rate: int = 24000,
        channels: int = 1,
        chunk_size: int = 1024,
        buffer_size: int = 10
    ):
        """
        Initialize the streaming audio player.
        
        Args:
            sample_rate: Sample rate in Hz (24000 for Live API)
            channels: Number of audio channels (1 for mono)
            chunk_size: Size of audio chunks for playback
            buffer_size: Size of the audio buffer queue
        """
        if not PYAUDIO_AVAILABLE:
            raise ImportError("PyAudio is required for audio playback")
        
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.format = pyaudio.paInt16
        
        # Audio queue for buffering
        self.audio_queue = queue.Queue(maxsize=buffer_size)
        
        # PyAudio instances
        self.pyaudio_instance = None
        self.audio_stream = None
        
        # Playback control
        self.is_playing = False
        self.playback_thread = None
        self.stop_requested = False
        
        # Statistics
        self.total_bytes_played = 0
        self.underrun_count = 0
    
    def start(self):
        """Start the audio player."""
        if self.is_playing:
            logger.warning("Audio player already started")
            return
        
        try:
            # Initialize PyAudio
            self.pyaudio_instance = pyaudio.PyAudio()
            
            # Open audio stream
            self.audio_stream = self.pyaudio_instance.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=None  # We'll use blocking mode
            )
            
            # Start playback thread
            self.is_playing = True
            self.stop_requested = False
            self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self.playback_thread.start()
            
            logger.info(f"Audio player started: {self.sample_rate}Hz, {self.channels} channel(s)")
            
        except Exception as e:
            error_msg = f"Failed to start audio player: {str(e)}"
            logger.error(error_msg)
            self.cleanup()
            raise
    
    def stop(self):
        """Stop the audio player."""
        if not self.is_playing:
            return
        
        logger.info("Stopping audio player")
        
        # Signal stop
        self.stop_requested = True
        
        # Clear the queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        
        # Put sentinel value to unblock the playback thread
        try:
            self.audio_queue.put(None, block=False)
        except queue.Full:
            pass
        
        # Wait for playback thread to finish
        if self.playback_thread:
            self.playback_thread.join(timeout=2.0)
        
        # Cleanup audio resources
        self.cleanup()
        
        self.is_playing = False
        logger.info(f"Audio player stopped. Total played: {self.total_bytes_played} bytes")
    
    def cleanup(self):
        """Clean up audio resources."""
        if self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
            self.audio_stream = None
        
        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")
            self.pyaudio_instance = None
    
    def add_audio_chunk(self, audio_data: bytes) -> bool:
        """
        Add audio chunk to playback queue.
        
        Args:
            audio_data: PCM audio data (24kHz, 16-bit, mono)
            
        Returns:
            True if chunk was added, False if queue is full
        """
        if not self.is_playing:
            logger.warning("Cannot add audio chunk: player not started")
            return False
        
        try:
            # Add to queue without blocking
            self.audio_queue.put(audio_data, block=False)
            return True
        except queue.Full:
            logger.warning("Audio buffer full, dropping chunk")
            return False
    
    def _playback_loop(self):
        """Main playback loop running in separate thread."""
        logger.info("Playback loop started")
        
        try:
            while not self.stop_requested:
                try:
                    # Get audio chunk from queue (blocking with timeout)
                    audio_chunk = self.audio_queue.get(timeout=0.1)
                    
                    # Check for sentinel value
                    if audio_chunk is None:
                        break
                    
                    # Play the audio chunk
                    if self.audio_stream and len(audio_chunk) > 0:
                        self.audio_stream.write(audio_chunk)
                        self.total_bytes_played += len(audio_chunk)
                    
                except queue.Empty:
                    # No audio available, continue waiting
                    if not self.stop_requested:
                        self.underrun_count += 1
                        if self.underrun_count % 10 == 0:
                            logger.debug(f"Audio buffer underrun count: {self.underrun_count}")
                    continue
                    
                except Exception as e:
                    if not self.stop_requested:
                        logger.error(f"Error in playback loop: {e}")
                    
        except Exception as e:
            logger.error(f"Fatal error in playback loop: {e}")
        
        finally:
            logger.info("Playback loop ended")
    
    def clear_buffer(self):
        """Clear the audio buffer (useful for interruptions)."""
        cleared = 0
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                cleared += 1
            except queue.Empty:
                break
        
        if cleared > 0:
            logger.info(f"Cleared {cleared} audio chunks from buffer")
    
    def get_buffer_level(self) -> float:
        """
        Get current buffer level as percentage.
        
        Returns:
            Buffer level from 0.0 (empty) to 1.0 (full)
        """
        return self.audio_queue.qsize() / self.audio_queue.maxsize
    
    def is_buffer_empty(self) -> bool:
        """Check if the audio buffer is empty."""
        return self.audio_queue.empty()
    
    def wait_until_done(self, timeout: Optional[float] = None):
        """
        Wait until all queued audio has been played.
        
        Args:
            timeout: Maximum time to wait in seconds
        """
        import time
        start_time = time.time()
        
        while not self.audio_queue.empty():
            if timeout and (time.time() - start_time) > timeout:
                logger.warning("Timeout waiting for audio playback to complete")
                break
            time.sleep(0.1)
    
    def __del__(self):
        """Cleanup on deletion."""
        self.stop()


class AudioFormatConverter:
    """Utility class for audio format conversion."""
    
    @staticmethod
    def resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """
        Resample audio data from one sample rate to another.
        
        Args:
            audio_data: PCM audio data (16-bit)
            from_rate: Original sample rate
            to_rate: Target sample rate
            
        Returns:
            Resampled audio data
        """
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # Simple linear interpolation resampling
        # For production, consider using scipy.signal.resample
        ratio = to_rate / from_rate
        new_length = int(len(audio_array) * ratio)
        
        # Create indices for interpolation
        old_indices = np.arange(len(audio_array))
        new_indices = np.linspace(0, len(audio_array) - 1, new_length)
        
        # Interpolate
        resampled = np.interp(new_indices, old_indices, audio_array)
        
        # Convert back to int16
        resampled = resampled.astype(np.int16)
        
        return resampled.tobytes()
    
    @staticmethod
    def normalize_audio(audio_data: bytes, target_level: float = 0.8) -> bytes:
        """
        Normalize audio volume to target level.
        
        Args:
            audio_data: PCM audio data (16-bit)
            target_level: Target volume level (0.0 to 1.0)
            
        Returns:
            Normalized audio data
        """
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        
        # Find peak
        peak = np.max(np.abs(audio_array))
        
        if peak > 0:
            # Calculate scaling factor
            scale = (target_level * 32767) / peak
            
            # Apply scaling
            audio_array *= scale
            
            # Clip to valid range
            audio_array = np.clip(audio_array, -32768, 32767)
        
        # Convert back to int16
        return audio_array.astype(np.int16).tobytes()


# Example usage
if __name__ == "__main__":
    import time
    
    # Create player
    player = StreamingAudioPlayer(sample_rate=24000)
    
    try:
        # Start player
        player.start()
        
        # Generate test tone (1 second of 440Hz sine wave)
        sample_rate = 24000
        duration = 1.0
        frequency = 440.0
        
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio = (32767 * 0.5 * np.sin(2 * np.pi * frequency * t)).astype(np.int16)
        
        # Add audio in chunks
        chunk_size = 1024
        audio_bytes = audio.tobytes()
        
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            player.add_audio_chunk(chunk)
            time.sleep(0.01)  # Simulate streaming
        
        # Wait for playback to complete
        player.wait_until_done(timeout=5.0)
        
    finally:
        # Stop player
        player.stop()
        print("Test completed")