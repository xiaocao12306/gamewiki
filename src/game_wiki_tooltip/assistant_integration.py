"""
Integration layer between the new unified UI and existing RAG/Wiki systems.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread

from src.game_wiki_tooltip.unified_window import (
    AssistantController, MessageType, TransitionMessages
)
from src.game_wiki_tooltip.config import SettingsManager, LLMConfig
from src.game_wiki_tooltip.utils import get_foreground_title

# 添加缺失的导入
try:
    from src.game_wiki_tooltip.ai.game_aware_query_processor import GameAwareQueryProcessor
    from src.game_wiki_tooltip.ai.rag_config import get_default_config
    from src.game_wiki_tooltip.ai.rag_query import EnhancedRagQuery
    logger = logging.getLogger(__name__)
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to import AI components: {e}")
    GameAwareQueryProcessor = None
    get_default_config = None
    EnhancedRagQuery = None

def get_selected_game_title():
    """Get current game title from active window"""
    return get_foreground_title()

@dataclass
class QueryIntent:
    """Query intent detection result"""
    intent_type: str  # "wiki" or "guide"
    confidence: float
    rewritten_query: Optional[str] = None


class QueryWorker(QThread):
    """Worker thread for processing queries asynchronously"""
    
    # Signals
    intent_detected = pyqtSignal(object)  # QueryIntent
    wiki_result = pyqtSignal(str, str)  # url, title
    guide_chunk = pyqtSignal(str)  # streaming chunk
    error_occurred = pyqtSignal(str)  # error message
    
    def __init__(self, rag_integration, query: str, parent=None):
        super().__init__(parent)
        self.rag_integration = rag_integration
        self.query = query
        self._stop_requested = False
        
    def run(self):
        """Run the query processing in thread"""
        try:
            # Create event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Process query asynchronously
                loop.run_until_complete(self._process_query())
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Query worker error: {e}")
            self.error_occurred.emit(str(e))
            
    async def _process_query(self):
        """Process the query asynchronously"""
        try:
            # Detect intent
            intent = await self.rag_integration.process_query_async(self.query)
            self.intent_detected.emit(intent)
            
            if intent.intent_type == "wiki":
                # Search wiki
                url, title = await self.rag_integration.search_wiki_async(
                    intent.rewritten_query or self.query
                )
                self.wiki_result.emit(url, title)
            else:
                # Generate guide - this will emit chunks via signals
                await self.rag_integration.generate_guide_async(
                    intent.rewritten_query or self.query
                )
                
        except Exception as e:
            logger.error(f"Query processing error: {e}")
            self.error_occurred.emit(str(e))
            
    def stop(self):
        """Request to stop the worker"""
        self._stop_requested = True


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
            
            # Get API keys from settings
            google_api_key = api_settings.get('google_api_key', '')
            jina_api_key = api_settings.get('jina_api_key', '')
            
            # Create LLMConfig with API key from settings
            # This makes the new UI system compatible with existing AI modules
            llm_config = LLMConfig(
                api_key=google_api_key,  # Explicitly pass API key
                model='gemini-2.5-flash-lite-preview-06-17'
            )
            
            if not llm_config.is_valid():
                logger.warning("Google API key not configured or invalid")
                return
                
            # Initialize query processor
            if GameAwareQueryProcessor:
                self.query_processor = GameAwareQueryProcessor(llm_config=llm_config)
            
            # Initialize RAG engine for current game
            game_title = get_selected_game_title()
            if game_title:
                self._init_rag_for_game(game_title, llm_config, jina_api_key)
                
        except Exception as e:
            logger.error(f"Failed to initialize AI components: {e}")
            
    def _init_rag_for_game(self, game_name: str, llm_config: LLMConfig, jina_api_key: str):
        """Initialize RAG engine for specific game"""
        try:
            if not (get_default_config and EnhancedRagQuery):
                logger.warning("RAG components not available")
                return
                
            # Get RAG config
            rag_config = get_default_config()
            
            # Create RAG engine
            self.rag_engine = EnhancedRagQuery(
                vector_store_path=None,  # Will be auto-detected
                enable_hybrid_search=rag_config.hybrid_search.enabled,
                hybrid_config=rag_config.hybrid_search.to_dict(),
                llm_config=llm_config,
                enable_query_rewrite=rag_config.query_processing.enable_query_rewrite,
                enable_summarization=rag_config.summarization.enabled,
                summarization_config=rag_config.summarization.to_dict(),
                enable_intent_reranking=rag_config.intent_reranking.enabled,
                reranking_config=rag_config.intent_reranking.to_dict()
            )
            
            # Initialize the engine in thread
            def init_rag():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.rag_engine.initialize(game_name))
                    logger.info(f"RAG engine initialized for game: {game_name}")
                except Exception as e:
                    logger.error(f"Failed to initialize RAG for {game_name}: {e}")
                finally:
                    loop.close()
            
            # Run initialization in a separate thread
            import threading
            init_thread = threading.Thread(target=init_rag)
            init_thread.daemon = True
            init_thread.start()
            
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
            # Query RAG engine (it's already async)
            result = await self.rag_engine.query(query)
            
            if not result or not result.get("answer"):
                self.error_occurred.emit("未找到相关信息")
                return
                
            # Get the answer from the result
            answer = result["answer"]
            
            # Emit the answer in chunks to simulate streaming
            # Split the answer into lines for better streaming experience
            lines = answer.split('\n')
            for line in lines:
                if line.strip():  # Only emit non-empty lines
                    self.streaming_chunk_ready.emit(line + '\n')
                    # Small delay to simulate streaming
                    await asyncio.sleep(0.05)
                    
        except Exception as e:
            logger.error(f"Guide generation failed: {e}")
            self.error_occurred.emit(f"生成攻略失败：{str(e)}")


class IntegratedAssistantController(AssistantController):
    """Enhanced assistant controller with RAG integration"""
    
    def __init__(self, settings_manager: SettingsManager):
        super().__init__(settings_manager)
        self.rag_integration = RAGIntegration(settings_manager)
        self._setup_connections()
        self._current_worker = None
        
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
        
        # Stop any existing worker
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.stop()
            self._current_worker.wait()
        
        # Create and start new worker
        self._current_worker = QueryWorker(self.rag_integration, query)
        self._current_worker.intent_detected.connect(self._on_intent_detected)
        self._current_worker.wiki_result.connect(self._on_wiki_result_from_worker)
        self._current_worker.guide_chunk.connect(self._on_guide_chunk)
        self._current_worker.error_occurred.connect(self._on_error)
        
        # Connect RAG integration signals to worker
        self.rag_integration.streaming_chunk_ready.connect(
            self._current_worker.guide_chunk
        )
        
        self._current_worker.start()
        
    def _on_intent_detected(self, intent: QueryIntent):
        """Handle intent detection result"""
        try:
            if intent.intent_type == "wiki":
                # Show wiki search transition
                self._current_transition_msg = self.main_window.chat_view.add_message(
                    MessageType.TRANSITION,
                    TransitionMessages.WIKI_SEARCHING
                )
            else:
                # Show guide search transition
                self._current_transition_msg = self.main_window.chat_view.add_message(
                    MessageType.TRANSITION,
                    TransitionMessages.GUIDE_SEARCHING
                )
                
                # Hide transition after delay and create streaming message
                QTimer.singleShot(500, self._setup_streaming_message)
                
        except Exception as e:
            logger.error(f"Intent detection handling error: {e}")
            self._on_error(str(e))
            
    def _setup_streaming_message(self):
        """Setup streaming message for guide responses"""
        if hasattr(self, '_current_transition_msg'):
            self._current_transition_msg.hide()
        self._current_streaming_msg = self.main_window.chat_view.add_streaming_message()
        
    def _on_wiki_result_from_worker(self, url: str, title: str):
        """Handle wiki result from worker"""
        try:
            if url:
                # Update transition message
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.WIKI_FOUND)
                
                # Add wiki link
                self.main_window.chat_view.add_message(
                    MessageType.WIKI_LINK,
                    title,
                    {"url": url}
                )
                
                # Open wiki page
                self.main_window.show_wiki_page(url, title)
            else:
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.ERROR_NOT_FOUND)
                    
        except Exception as e:
            logger.error(f"Wiki result handling error: {e}")
            self._on_error(str(e))
            
    def _on_guide_chunk(self, chunk: str):
        """Handle guide chunk from worker"""
        if hasattr(self, '_current_streaming_msg'):
            self._current_streaming_msg.append_chunk(chunk)
            
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
        """Switch to a different game"""
        # Stop current worker
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.stop()
            self._current_worker.wait()
            
        # Reinitialize RAG for new game
        settings = self.settings_manager.get()
        api_settings = settings.get('api', {})
        google_api_key = api_settings.get('google_api_key', '')
        jina_api_key = api_settings.get('jina_api_key', '')
        
        if google_api_key:
            llm_config = LLMConfig(
                api_key=google_api_key,
                model='gemini-2.5-flash-lite-preview-06-17'
            )
            self.rag_integration._init_rag_for_game(game_name, llm_config, jina_api_key)