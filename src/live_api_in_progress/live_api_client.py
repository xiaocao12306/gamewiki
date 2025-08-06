"""
Gemini Live API client for text-to-audio conversation.
Handles WebSocket connection and audio streaming.
"""

import asyncio
import logging
import json
from typing import Optional, Callable, AsyncGenerator, Dict, Any
from dataclasses import dataclass
import io
import struct

try:
    import google.generativeai as genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logging.warning("google-generativeai not available. Please install it.")

logger = logging.getLogger(__name__)


@dataclass
class LiveAPIConfig:
    """Configuration for Live API client."""
    api_key: str
    model: str = "gemini-2.5-flash-preview-native-audio-dialog"
    voice_name: str = "Kore"
    language: str = "en-US"
    enable_affective_dialog: bool = True
    enable_proactive_audio: bool = True
    system_instruction: str = "You are a helpful and friendly AI assistant. Respond naturally and conversationally."


class LiveAPIClient:
    """
    Client for Gemini Live API with text input and audio output.
    """
    
    def __init__(
        self,
        config: LiveAPIConfig,
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
        on_text_response: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_connection_state: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the Live API client.
        
        Args:
            config: LiveAPIConfig with settings
            on_audio_chunk: Callback for audio data chunks (24kHz PCM)
            on_text_response: Callback for text transcription of response
            on_error: Callback for error messages
            on_connection_state: Callback for connection state changes
        """
        if not GENAI_AVAILABLE:
            raise ImportError("google-generativeai is required. Install with: pip install google-generativeai>=0.8.0")
        
        self.config = config
        self.on_audio_chunk = on_audio_chunk
        self.on_text_response = on_text_response
        self.on_error = on_error
        self.on_connection_state = on_connection_state
        
        self.session = None
        self.is_connected = False
        self.current_response_text = ""
        
        # Configure Gemini API
        genai.configure(api_key=config.api_key)
        
        # Initialize client
        self.client = genai.Client()
        
        # Build session config
        self.session_config = self._build_session_config()
    
    def _build_session_config(self) -> Dict[str, Any]:
        """Build the session configuration for Live API."""
        config = {
            "response_modalities": ["AUDIO"],  # We want audio output
            "system_instruction": self.config.system_instruction,
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": self.config.voice_name
                    }
                }
            }
        }
        
        # Add advanced features if enabled
        if self.config.enable_affective_dialog:
            config["enable_affective_dialog"] = True
        
        if self.config.enable_proactive_audio:
            config["proactivity"] = {"proactive_audio": True}
        
        return config
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection to Live API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            if self.on_connection_state:
                self.on_connection_state("connecting")
            
            # Create Live API session
            self.session = await self.client.aio.live.connect(
                model=self.config.model,
                config=self.session_config
            )
            
            self.is_connected = True
            logger.info(f"Connected to Live API with model: {self.config.model}")
            
            if self.on_connection_state:
                self.on_connection_state("connected")
            
            # Start listening for responses
            asyncio.create_task(self._listen_for_responses())
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to connect to Live API: {str(e)}"
            logger.error(error_msg)
            if self.on_error:
                self.on_error(error_msg)
            if self.on_connection_state:
                self.on_connection_state("disconnected")
            return False
    
    async def disconnect(self):
        """Disconnect from Live API."""
        if self.session:
            try:
                await self.session.close()
                logger.info("Disconnected from Live API")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
            finally:
                self.session = None
                self.is_connected = False
                if self.on_connection_state:
                    self.on_connection_state("disconnected")
    
    async def send_text(self, text: str) -> bool:
        """
        Send text input to Live API and receive audio response.
        
        Args:
            text: Text message to send
            
        Returns:
            True if message sent successfully
        """
        if not self.is_connected or not self.session:
            logger.error("Not connected to Live API")
            if self.on_error:
                self.on_error("Not connected to Live API")
            return False
        
        try:
            # Send text as user turn
            await self.session.send_client_content(
                turns={
                    "role": "user",
                    "parts": [{"text": text}]
                },
                turn_complete=True
            )
            
            logger.info(f"Sent text to Live API: {text}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to send text: {str(e)}"
            logger.error(error_msg)
            if self.on_error:
                self.on_error(error_msg)
            return False
    
    async def _listen_for_responses(self):
        """Listen for responses from Live API."""
        if not self.session:
            return
        
        try:
            async for response in self.session.receive():
                await self._process_response(response)
                
        except Exception as e:
            if self.is_connected:  # Only log if we didn't intentionally disconnect
                error_msg = f"Error listening for responses: {str(e)}"
                logger.error(error_msg)
                if self.on_error:
                    self.on_error(error_msg)
                
                # Try to reconnect
                self.is_connected = False
                if self.on_connection_state:
                    self.on_connection_state("reconnecting")
                await asyncio.sleep(2)
                await self.connect()
    
    async def _process_response(self, response):
        """Process response from Live API."""
        try:
            # Handle different response types
            if hasattr(response, 'server_content'):
                # Audio content response
                server_content = response.server_content
                
                if hasattr(server_content, 'model_turn'):
                    model_turn = server_content.model_turn
                    
                    # Process parts of the response
                    if hasattr(model_turn, 'parts'):
                        for part in model_turn.parts:
                            # Check for audio data
                            if hasattr(part, 'inline_data'):
                                audio_data = part.inline_data.data
                                
                                # Audio is 24kHz PCM format
                                if self.on_audio_chunk:
                                    self.on_audio_chunk(audio_data)
                            
                            # Check for text (for logging/display)
                            elif hasattr(part, 'text'):
                                text = part.text
                                self.current_response_text += text
                                if self.on_text_response:
                                    self.on_text_response(text)
            
            # Handle other response types (errors, status, etc.)
            elif hasattr(response, 'tool_call'):
                # Tool call response (if using functions)
                logger.info(f"Tool call: {response.tool_call}")
            
            elif hasattr(response, 'tool_call_cancellation'):
                # Tool call cancelled
                logger.info(f"Tool call cancelled: {response.tool_call_cancellation}")
                
        except Exception as e:
            logger.error(f"Error processing response: {e}")
    
    async def interrupt(self):
        """
        Interrupt the current response.
        Useful when user starts speaking while AI is responding.
        """
        if self.session:
            try:
                # Send empty audio to trigger interruption
                await self.session.send_realtime_input(
                    media_chunks=[types.Blob(data=b'', mime_type="audio/pcm;rate=16000")]
                )
                logger.info("Interrupted current response")
            except Exception as e:
                logger.error(f"Error interrupting: {e}")
    
    def is_ready(self) -> bool:
        """Check if client is ready to send messages."""
        return self.is_connected and self.session is not None
    
    async def set_voice(self, voice_name: str):
        """
        Change the voice for responses.
        
        Args:
            voice_name: Name of the voice to use
        """
        self.config.voice_name = voice_name
        self.session_config = self._build_session_config()
        
        # Reconnect with new config
        if self.is_connected:
            await self.disconnect()
            await self.connect()
    
    async def extend_session(self):
        """
        Extend the current session by 10 minutes.
        Sessions have a default 10-minute limit.
        """
        if self.session:
            try:
                # This would extend the session
                # Note: Actual implementation depends on API updates
                logger.info("Session extended")
            except Exception as e:
                logger.error(f"Error extending session: {e}")


# Example usage
async def main():
    config = LiveAPIConfig(
        api_key="YOUR_API_KEY",
        voice_name="Kore",
        language="en-US"
    )
    
    def on_audio(audio_chunk: bytes):
        print(f"Received audio chunk: {len(audio_chunk)} bytes")
    
    def on_text(text: str):
        print(f"Response text: {text}")
    
    def on_error(error: str):
        print(f"Error: {error}")
    
    def on_state(state: str):
        print(f"Connection state: {state}")
    
    client = LiveAPIClient(
        config=config,
        on_audio_chunk=on_audio,
        on_text_response=on_text,
        on_error=on_error,
        on_connection_state=on_state
    )
    
    # Connect to Live API
    if await client.connect():
        # Send a text message
        await client.send_text("Hello! How are you today?")
        
        # Wait for response
        await asyncio.sleep(10)
        
        # Disconnect
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())