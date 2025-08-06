"""
Conversation manager for Live API sessions.
Handles conversation state, context, and coordination between components.
"""

import asyncio
import logging
import time
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path

from .voice_listener import ContinuousVoiceListener
from .live_api_client import LiveAPIClient, LiveAPIConfig
from .audio_player import StreamingAudioPlayer

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """Represents a single turn in the conversation."""
    role: str  # 'user' or 'assistant'
    text: str
    timestamp: datetime = field(default_factory=datetime.now)
    audio_duration: Optional[float] = None


@dataclass
class ConversationState:
    """Current state of the conversation."""
    is_active: bool = False
    is_listening: bool = False
    is_ai_speaking: bool = False
    current_user_text: str = ""
    current_ai_text: str = ""
    turns: List[ConversationTurn] = field(default_factory=list)
    session_start: Optional[datetime] = None
    session_id: Optional[str] = None


class ConversationManager:
    """
    Manages the complete conversation flow between user and AI.
    Coordinates voice input, Live API, and audio output.
    """
    
    def __init__(
        self,
        api_key: str,
        model_path: Optional[str] = None,
        language: str = "en",
        voice_name: str = "Kore",
        on_state_change: Optional[Callable[[ConversationState], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the conversation manager.
        
        Args:
            api_key: Gemini API key
            model_path: Path to Vosk model
            language: Language code ('en' or 'zh')
            voice_name: Live API voice name
            on_state_change: Callback for state changes
            on_error: Callback for errors
        """
        self.api_key = api_key
        self.model_path = model_path
        self.language = language
        self.voice_name = voice_name
        self.on_state_change = on_state_change
        self.on_error = on_error
        
        # Conversation state
        self.state = ConversationState()
        
        # Components
        self.voice_listener = None
        self.live_api_client = None
        self.audio_player = None
        
        # Async event loop for Live API
        self.loop = None
        self.loop_thread = None
        
        # Control flags
        self.auto_interrupt = True  # Interrupt AI when user speaks
        self.save_history = True
        self.history_path = Path("conversation_history.json")
        
        # Initialize components
        self._init_components()
    
    def _init_components(self):
        """Initialize all components."""
        # Initialize voice listener
        self.voice_listener = ContinuousVoiceListener(
            model_path=self.model_path,
            language=self.language,
            on_partial_text=self._on_partial_text,
            on_final_text=self._on_final_text,
            on_error=self._on_voice_error
        )
        
        # Initialize audio player
        self.audio_player = StreamingAudioPlayer(
            sample_rate=24000,  # Live API output rate
            channels=1,
            chunk_size=1024
        )
        
        # Live API config
        self.live_api_config = LiveAPIConfig(
            api_key=self.api_key,
            voice_name=self.voice_name,
            language=f"{self.language}-US" if self.language == "en" else f"{self.language}-CN",
            enable_affective_dialog=True,
            enable_proactive_audio=True,
            system_instruction=(
                "You are a helpful and friendly AI assistant. "
                "Respond naturally and conversationally. "
                "Keep your responses concise and engaging."
            )
        )
        
        # Initialize Live API client (will be connected when starting)
        self.live_api_client = LiveAPIClient(
            config=self.live_api_config,
            on_audio_chunk=self._on_audio_chunk,
            on_text_response=self._on_ai_text,
            on_error=self._on_api_error,
            on_connection_state=self._on_connection_state
        )
    
    def start(self):
        """Start the conversation session."""
        if self.state.is_active:
            logger.warning("Conversation already active")
            return
        
        try:
            # Start audio player
            self.audio_player.start()
            
            # Start async event loop for Live API
            self.loop = asyncio.new_event_loop()
            self.loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self.loop_thread.start()
            
            # Connect to Live API
            future = asyncio.run_coroutine_threadsafe(
                self.live_api_client.connect(),
                self.loop
            )
            
            # Wait for connection (with timeout)
            connected = future.result(timeout=10)
            
            if not connected:
                raise Exception("Failed to connect to Live API")
            
            # Start voice listener (continuous listening)
            self.voice_listener.start_listening()
            
            # Update state
            self.state.is_active = True
            self.state.is_listening = True
            self.state.session_start = datetime.now()
            self.state.session_id = f"session_{int(time.time())}"
            
            self._notify_state_change()
            
            logger.info("Conversation session started")
            
        except Exception as e:
            error_msg = f"Failed to start conversation: {str(e)}"
            logger.error(error_msg)
            if self.on_error:
                self.on_error(error_msg)
            self.stop()
    
    def stop(self):
        """Stop the conversation session."""
        if not self.state.is_active:
            return
        
        logger.info("Stopping conversation session")
        
        # Stop voice listener
        if self.voice_listener:
            self.voice_listener.stop_listening()
        
        # Disconnect from Live API
        if self.live_api_client and self.loop:
            future = asyncio.run_coroutine_threadsafe(
                self.live_api_client.disconnect(),
                self.loop
            )
            try:
                future.result(timeout=5)
            except:
                pass
        
        # Stop audio player
        if self.audio_player:
            self.audio_player.stop()
        
        # Stop event loop
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
            if self.loop_thread:
                self.loop_thread.join(timeout=2)
        
        # Save conversation history
        if self.save_history and self.state.turns:
            self._save_history()
        
        # Reset state
        self.state = ConversationState()
        self._notify_state_change()
        
        logger.info("Conversation session stopped")
    
    def _run_event_loop(self):
        """Run the async event loop in a separate thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    
    def _on_partial_text(self, text: str):
        """Handle partial text from voice recognition."""
        self.state.current_user_text = text
        self._notify_state_change()
    
    def _on_final_text(self, text: str):
        """Handle final text from voice recognition."""
        if not text.strip():
            return
        
        logger.info(f"User said: {text}")
        
        # Add to conversation history
        turn = ConversationTurn(role="user", text=text)
        self.state.turns.append(turn)
        self.state.current_user_text = ""
        
        # Interrupt AI if it's speaking
        if self.auto_interrupt and self.state.is_ai_speaking:
            self._interrupt_ai()
        
        # Send to Live API
        if self.live_api_client and self.live_api_client.is_ready():
            asyncio.run_coroutine_threadsafe(
                self.live_api_client.send_text(text),
                self.loop
            )
            self.state.is_ai_speaking = True
        
        self._notify_state_change()
    
    def _on_voice_error(self, error: str):
        """Handle voice recognition errors."""
        logger.error(f"Voice error: {error}")
        if self.on_error:
            self.on_error(f"Voice recognition error: {error}")
    
    def _on_audio_chunk(self, audio_chunk: bytes):
        """Handle audio chunk from Live API."""
        # Add to audio player buffer
        if self.audio_player:
            self.audio_player.add_audio_chunk(audio_chunk)
    
    def _on_ai_text(self, text: str):
        """Handle text response from Live API (for display)."""
        self.state.current_ai_text += text
        self._notify_state_change()
        
        # When response is complete, add to history
        # (This is simplified - in practice, you'd detect end of response)
        if text.endswith(('.', '!', '?')):
            turn = ConversationTurn(
                role="assistant",
                text=self.state.current_ai_text
            )
            self.state.turns.append(turn)
            self.state.current_ai_text = ""
            self.state.is_ai_speaking = False
            self._notify_state_change()
    
    def _on_api_error(self, error: str):
        """Handle Live API errors."""
        logger.error(f"API error: {error}")
        if self.on_error:
            self.on_error(f"Live API error: {error}")
        self.state.is_ai_speaking = False
        self._notify_state_change()
    
    def _on_connection_state(self, state: str):
        """Handle Live API connection state changes."""
        logger.info(f"Live API connection state: {state}")
        
        if state == "disconnected" and self.state.is_active:
            # Try to reconnect
            asyncio.run_coroutine_threadsafe(
                self._reconnect(),
                self.loop
            )
    
    async def _reconnect(self):
        """Attempt to reconnect to Live API."""
        logger.info("Attempting to reconnect to Live API")
        
        for attempt in range(3):
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
            if await self.live_api_client.connect():
                logger.info("Reconnected to Live API")
                return
        
        logger.error("Failed to reconnect to Live API after 3 attempts")
        if self.on_error:
            self.on_error("Lost connection to Live API")
    
    def _interrupt_ai(self):
        """Interrupt the current AI response."""
        logger.info("Interrupting AI response")
        
        # Clear audio buffer
        if self.audio_player:
            self.audio_player.clear_buffer()
        
        # Send interrupt signal to Live API
        if self.live_api_client:
            asyncio.run_coroutine_threadsafe(
                self.live_api_client.interrupt(),
                self.loop
            )
        
        self.state.is_ai_speaking = False
        self.state.current_ai_text = ""
        self._notify_state_change()
    
    def _notify_state_change(self):
        """Notify about state changes."""
        if self.on_state_change:
            self.on_state_change(self.state)
    
    def pause_listening(self):
        """Temporarily pause voice listening."""
        if self.voice_listener:
            self.voice_listener.pause()
            self.state.is_listening = False
            self._notify_state_change()
    
    def resume_listening(self):
        """Resume voice listening."""
        if self.voice_listener:
            self.voice_listener.resume()
            self.state.is_listening = True
            self._notify_state_change()
    
    def set_language(self, language: str):
        """Change the conversation language."""
        self.language = language
        
        # Update voice listener
        if self.voice_listener:
            self.voice_listener.set_language(language)
        
        # Update Live API config and reconnect
        self.live_api_config.language = f"{language}-US" if language == "en" else f"{language}-CN"
        
        if self.state.is_active and self.live_api_client:
            asyncio.run_coroutine_threadsafe(
                self._reconnect_with_new_config(),
                self.loop
            )
    
    async def _reconnect_with_new_config(self):
        """Reconnect with updated configuration."""
        await self.live_api_client.disconnect()
        await self.live_api_client.connect()
    
    def set_voice(self, voice_name: str):
        """Change the AI voice."""
        self.voice_name = voice_name
        
        if self.live_api_client:
            asyncio.run_coroutine_threadsafe(
                self.live_api_client.set_voice(voice_name),
                self.loop
            )
    
    def _save_history(self):
        """Save conversation history to file."""
        try:
            history = {
                "session_id": self.state.session_id,
                "session_start": self.state.session_start.isoformat() if self.state.session_start else None,
                "language": self.language,
                "turns": [
                    {
                        "role": turn.role,
                        "text": turn.text,
                        "timestamp": turn.timestamp.isoformat(),
                        "audio_duration": turn.audio_duration
                    }
                    for turn in self.state.turns
                ]
            }
            
            with open(self.history_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved conversation history to {self.history_path}")
            
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    def get_conversation_text(self) -> str:
        """Get the conversation history as formatted text."""
        lines = []
        for turn in self.state.turns:
            prefix = "User: " if turn.role == "user" else "AI: "
            lines.append(f"{prefix}{turn.text}")
        return "\n\n".join(lines)


# Import for thread management
import threading


# Example usage
if __name__ == "__main__":
    import os
    
    def on_state_change(state: ConversationState):
        if state.current_user_text:
            print(f"User (partial): {state.current_user_text}")
        if state.current_ai_text:
            print(f"AI (partial): {state.current_ai_text}")
    
    def on_error(error: str):
        print(f"Error: {error}")
    
    # Get API key from environment
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Please set GEMINI_API_KEY environment variable")
        exit(1)
    
    # Create conversation manager
    manager = ConversationManager(
        api_key=api_key,
        language="en",
        voice_name="Kore",
        on_state_change=on_state_change,
        on_error=on_error
    )
    
    try:
        # Start conversation
        manager.start()
        
        print("Conversation started. Speak to interact. Press Ctrl+C to stop.")
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping conversation...")
        manager.stop()
        print("Conversation ended")