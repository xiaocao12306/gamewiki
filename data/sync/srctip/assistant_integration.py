"""
Integration layer between the new unified UI and existing RAG/Wiki systems.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from src.game_wiki_tooltip.unified_window import (
    AssistantController, MessageType, TransitionMessages
)
from src.game_wiki_tooltip.config import SettingsManager
from src.game_wiki_tooltip.overlay import get_selected_game_title
from src.game_wiki_tooltip.ai.rag_query import (
    GameRAGQueryEngine, QueryResult
)
from src.game_wiki_tooltip.ai.game_aware_query_processor import (
    GameAwareQueryProcessor
)
from src.game_wiki_tooltip.ai.rag_config import get_rag_config

logger = logging.getLogger(__name__)


@dataclass
class QueryIntent:
    """Query intent detection result"""
    intent_type: str  # "wiki" or "guide"
    confidence: float
    rewritten_query: Optional[str] = None


class RAGIntegration(QObject):
    """Integrates RAG engine with the UI"""
    
    # Signals for UI updates
    streaming_chunk_ready = pyqtSignal(str)
    wiki_result_ready = pyqtSignal(str, str)  # url, title
    error_occurred = pyqtSignal(str)
    
    def __init__(self, settings_manager: SettingsManager):
        super().__init__()
        self.settings_manager = settings_manager
        self.rag_engine = None
        self.query_processor = None
        self._init_ai_components()
        
    def _init_ai_components(self):
        """Initialize AI components with settings"""
        try:
            settings = self.settings_manager.get()
            api_settings = settings.get('api', {})
            
            # Get API keys
            google_api_key = api_settings.get('google_api_key', '')
            jina_api_key = api_settings.get('jina_api_key', '')
            
            if not google_api_key:
                logger.warning("Google API key not configured")
                return
                
            # Initialize query processor
            self.query_processor = GameAwareQueryProcessor(
                llm_config={
                    'api_key': google_api_key,
                    'model': 'gemini-2.5-flash-lite-preview-06-17'
                }
            )
            
            # Initialize RAG engine for current game
            game_title = get_selected_game_title()
            if game_title:
                self._init_rag_for_game(game_title, google_api_key, jina_api_key)
                
        except Exception as e:
            logger.error(f"Failed to initialize AI components: {e}")
            
    def _init_rag_for_game(self, game_name: str, google_api_key: str, jina_api_key: str):
        """Initialize RAG engine for specific game"""
        try:
            # Get RAG config
            rag_config = get_rag_config(game_name)
            
            # Override with user's API keys
            if hasattr(rag_config, 'summarizer_config'):
                rag_config.summarizer_config.api_key = google_api_key
            if hasattr(rag_config, 'embedder_config'):
                rag_config.embedder_config.api_key = jina_api_key
                
            # Create RAG engine
            self.rag_engine = GameRAGQueryEngine(rag_config)
            logger.info(f"RAG engine initialized for game: {game_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize RAG for {game_name}: {e}")
            
    async def process_query_async(self, query: str) -> QueryIntent:
        """Process query to detect intent"""
        if not self.query_processor:
            # Fallback to simple detection
            return self._simple_intent_detection(query)
            
        try:
            # Use game-aware processor
            result = await asyncio.to_thread(
                self.query_processor.process_query,
                query,
                game_context=get_selected_game_title()
            )
            
            return QueryIntent(
                intent_type=result.intent,
                confidence=result.confidence,
                rewritten_query=result.rewritten_query
            )
            
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return self._simple_intent_detection(query)
            
    def _simple_intent_detection(self, query: str) -> QueryIntent:
        """Simple keyword-based intent detection"""
        query_lower = query.lower()
        
        # Wiki intent keywords
        wiki_keywords = ['是什么', '什么是', 'what is', 'wiki', '介绍', 'info']
        # Guide intent keywords  
        guide_keywords = ['怎么', '如何', 'how to', '攻略', 'guide', '推荐', 'best']
        
        wiki_score = sum(1 for kw in wiki_keywords if kw in query_lower)
        guide_score = sum(1 for kw in guide_keywords if kw in query_lower)
        
        if wiki_score > guide_score:
            return QueryIntent('wiki', confidence=0.7)
        else:
            return QueryIntent('guide', confidence=0.7)
            
    async def search_wiki_async(self, query: str) -> tuple[str, str]:
        """Search for wiki page"""
        # Use existing wiki search logic from overlay.py
        try:
            import aiohttp
            from urllib.parse import quote
            
            game_title = get_selected_game_title()
            search_query = f"{game_title} {query} wiki"
            
            # Try DuckDuckGo first
            ddg_url = f"https://duckduckgo.com/?q=!ducky+{quote(search_query)}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(ddg_url, allow_redirects=True) as response:
                    final_url = str(response.url)
                    
                    # Extract title from URL or use query
                    title = query
                    if 'wiki' in final_url:
                        parts = final_url.split('/')
                        if parts:
                            title = parts[-1].replace('_', ' ')
                            
                    return final_url, title
                    
        except Exception as e:
            logger.error(f"Wiki search failed: {e}")
            return "", query
            
    async def generate_guide_async(self, query: str):
        """Generate guide response with streaming"""
        if not self.rag_engine:
            self.error_occurred.emit("RAG引擎未初始化，请检查API配置")
            return
            
        try:
            # Query RAG engine
            result = await asyncio.to_thread(
                self.rag_engine.query,
                query
            )
            
            if not result or not result.chunks:
                self.error_occurred.emit("未找到相关信息")
                return
                
            # Get summarizer
            summarizer = self.rag_engine.summarizer
            if not summarizer:
                self.error_occurred.emit("摘要生成器未配置")
                return
                
            # Stream the summary
            async for chunk in summarizer.summarize_chunks_stream(
                result.chunks,
                query
            ):
                self.streaming_chunk_ready.emit(chunk)
                
        except Exception as e:
            logger.error(f"Guide generation failed: {e}")
            self.error_occurred.emit(f"生成攻略失败：{str(e)}")


class IntegratedAssistantController(AssistantController):
    """Enhanced assistant controller with RAG integration"""
    
    def __init__(self, settings_manager: SettingsManager):
        super().__init__(settings_manager)
        self.rag_integration = RAGIntegration(settings_manager)
        self._setup_connections()
        self._async_tasks = []
        
    def _setup_connections(self):
        """Setup signal connections"""
        self.rag_integration.streaming_chunk_ready.connect(
            self._on_streaming_chunk
        )
        self.rag_integration.wiki_result_ready.connect(
            self._on_wiki_result
        )
        self.rag_integration.error_occurred.connect(
            self._on_error
        )
        
    def handle_query(self, query: str):
        """Override to handle query with RAG integration"""
        # Add user message
        self.main_window.chat_view.add_message(
            MessageType.USER_QUERY,
            query
        )
        
        # Process query asynchronously
        asyncio.create_task(self._process_query_async(query))
        
    async def _process_query_async(self, query: str):
        """Async query processing"""
        try:
            # Detect intent
            intent = await self.rag_integration.process_query_async(query)
            
            if intent.intent_type == "wiki":
                # Show wiki search transition
                transition_msg = self.main_window.chat_view.add_message(
                    MessageType.TRANSITION,
                    TransitionMessages.WIKI_SEARCHING
                )
                
                # Search wiki
                url, title = await self.rag_integration.search_wiki_async(
                    intent.rewritten_query or query
                )
                
                if url:
                    # Update transition message
                    transition_msg.update_content(TransitionMessages.WIKI_FOUND)
                    
                    # Add wiki link
                    self.main_window.chat_view.add_message(
                        MessageType.WIKI_LINK,
                        title,
                        {"url": url}
                    )
                    
                    # Open wiki page
                    self.main_window.show_wiki_page(url, title)
                else:
                    transition_msg.update_content(TransitionMessages.ERROR_NOT_FOUND)
                    
            else:  # guide intent
                # Show guide search transition
                transition_msg = self.main_window.chat_view.add_message(
                    MessageType.TRANSITION,
                    TransitionMessages.GUIDE_SEARCHING
                )
                
                # Hide transition and create streaming message
                QTimer.singleShot(500, transition_msg.hide)
                self._current_streaming_msg = self.main_window.chat_view.add_streaming_message()
                
                # Generate guide
                await self.rag_integration.generate_guide_async(
                    intent.rewritten_query or query
                )
                
        except Exception as e:
            logger.error(f"Query processing error: {e}")
            self._on_error(str(e))
            
    def _on_streaming_chunk(self, chunk: str):
        """Handle streaming chunk from RAG"""
        if hasattr(self, '_current_streaming_msg'):
            self._current_streaming_msg.append_chunk(chunk)
            
    def _on_wiki_result(self, url: str, title: str):
        """Handle wiki search result"""
        self.main_window.chat_view.add_message(
            MessageType.WIKI_LINK,
            title,
            {"url": url}
        )
        
    def _on_error(self, error_msg: str):
        """Handle error"""
        self.main_window.chat_view.add_message(
            MessageType.AI_RESPONSE,
            f"❌ {error_msg}"
        )
        
    def switch_game(self, game_name: str):
        """Switch to different game context"""
        settings = self.settings_manager.get()
        api_settings = settings.get('api', {})
        
        self.rag_integration._init_rag_for_game(
            game_name,
            api_settings.get('google_api_key', ''),
            api_settings.get('jina_api_key', '')
        )