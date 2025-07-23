"""
Integration layer between the new unified UI and existing RAG/Wiki systems.
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
import os # Added for os.getenv

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread, Qt

from src.game_wiki_tooltip.unified_window import (
    AssistantController, MessageType, TransitionMessages
)
from src.game_wiki_tooltip.config import SettingsManager, LLMConfig
from src.game_wiki_tooltip.utils import get_foreground_title

# Lazy load AI modules - import only when needed to speed up startup
logger = logging.getLogger(__name__)
process_query_unified = None
get_default_config = None
EnhancedRagQuery = None
_ai_modules_loaded = False
_ai_modules_loading = False  # Prevent duplicate loading
_ai_load_lock = threading.Lock()  # Thread lock to protect loading state

class AIModuleLoader(QThread):
    """Background thread for loading AI modules"""
    load_completed = pyqtSignal(bool)  # Load completed signal, parameter is success or not
    
    def run(self):
        """Load AI modules in background thread"""
        success = _lazy_load_ai_modules()
        self.load_completed.emit(success)

def _lazy_load_ai_modules():
    """Lazy load AI modules, only import when first used"""
    global process_query_unified, get_default_config, EnhancedRagQuery, _ai_modules_loaded, _ai_modules_loading
    
    with _ai_load_lock:
        if _ai_modules_loaded:
            return True
            
        if _ai_modules_loading:
            # Another thread is loading, wait for completion
            logger.info("⏳ AI module is being loaded by another thread, waiting...")
            while _ai_modules_loading and not _ai_modules_loaded:
                time.sleep(0.1)
            return _ai_modules_loaded
            
        _ai_modules_loading = True
        
    try:
        logger.info("🔄 Starting AI module loading...")
        start_time = time.time()
        
        from src.game_wiki_tooltip.ai.unified_query_processor import process_query_unified as _process_query_unified
        from src.game_wiki_tooltip.ai.rag_config import get_default_config as _get_default_config
        from src.game_wiki_tooltip.ai.rag_query import EnhancedRagQuery as _EnhancedRagQuery
        
        process_query_unified = _process_query_unified
        get_default_config = _get_default_config
        EnhancedRagQuery = _EnhancedRagQuery
        
        with _ai_load_lock:
            _ai_modules_loaded = True
            _ai_modules_loading = False
            
        elapsed = time.time() - start_time
        logger.info(f"✅ AI module loading completed, time taken: {elapsed:.2f} seconds")
        return True
    except ImportError as e:
        logger.error(f"Failed to import AI components: {e}")
        with _ai_load_lock:
            _ai_modules_loading = False
        return False

def get_selected_game_title():
    """Get current game title from active window"""
    return get_foreground_title()

@dataclass
class QueryIntent:
    """Query intent detection result"""
    intent_type: str  # "wiki" or "guide"
    confidence: float
    rewritten_query: Optional[str] = None
    translated_query: Optional[str] = None  # Add translated query field
    unified_query_result: Optional[object] = None  # Complete unified query result


class QueryWorker(QThread):
    """Worker thread for processing queries asynchronously"""
    
    # Signals
    intent_detected = pyqtSignal(object)  # QueryIntent
    wiki_result = pyqtSignal(str, str)  # url, title
    guide_chunk = pyqtSignal(str)  # streaming chunk
    error_occurred = pyqtSignal(str)  # error message
    
    def __init__(self, rag_integration, query: str, game_context: str = None, parent=None):
        super().__init__(parent)
        self.rag_integration = rag_integration
        self.query = query
        self.game_context = game_context
        self._stop_requested = False
        self._current_task = None  # Current running async task
        
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
            # Check if stop has been requested
            if self._stop_requested:
                return
                
            # Use unified query processor for intent detection and query optimization
            intent = await self.rag_integration.process_query_async(
                self.query, 
                game_context=self.game_context
            )
            
            # Check again if stop has been requested
            if self._stop_requested:
                return
                
            self.intent_detected.emit(intent)
            
            if intent.intent_type == "unsupported":
                # For unsupported windows, emit error signal directly
                error_msg = f"The current window '{self.game_context}' is not in the list of supported games.\n\nPlease check the settings page for supported games, or try using this tool in a supported game window."
                self.error_occurred.emit(error_msg)
                return
            elif intent.intent_type == "wiki":
                # Check if stop has been requested
                if self._stop_requested:
                    return
                    
                # For wiki search, use original query (because wiki search does not need optimized query)
                search_url, search_title = await self.rag_integration.prepare_wiki_search_async(
                    self.query,  # Use original query for wiki search
                    game_context=self.game_context
                )
                
                if not self._stop_requested:
                    self.wiki_result.emit(search_url, search_title)
            else:
                # Check if stop has been requested
                if self._stop_requested:
                    return
                    
                # For guide query, pass both original query and processed query
                processed_query = intent.rewritten_query or intent.translated_query or self.query
                
                # Set current task and pass stop flag
                self._current_task = self.rag_integration.generate_guide_async(
                    processed_query,  # Query used for retrieval
                    game_context=self.game_context,
                    original_query=self.query,  # Original query, used for answer generation
                    skip_query_processing=True,  # Skip query processing inside RAG
                    unified_query_result=intent.unified_query_result,  # Pass complete unified query result
                    stop_flag=lambda: self._stop_requested  # Pass stop flag check function
                )
                await self._current_task
                
        except asyncio.CancelledError:
            logger.info("Query processing cancelled")
        except Exception as e:
            if not self._stop_requested:  # Only report error if not stopped
                logger.error(f"Query processing error: {e}")
                self.error_occurred.emit(str(e))
            
    def stop(self):
        """Request to stop the worker"""
        try:
            self._stop_requested = True
            logger.info("🛑 QueryWorker stop request issued")
            
            # If there's a current task, try to cancel it
            if self._current_task and not self._current_task.done():
                try:
                    self._current_task.cancel()
                    logger.info("🛑 Current async task cancelled")
                except Exception as e:
                    logger.error(f"Error cancelling async task: {e}")
                    
        except Exception as e:
            logger.error(f"Error during QueryWorker stop process: {e}")


class RAGIntegration(QObject):
    """Integrates RAG engine with the UI"""
    
    # Signals for UI updates
    streaming_chunk_ready = pyqtSignal(str)
    wiki_result_ready = pyqtSignal(str, str)  # url, title
    wiki_link_updated = pyqtSignal(str, str)  # 新信号：用于更新聊天窗口中的wiki链接
    error_occurred = pyqtSignal(str)
    
    def __init__(self, settings_manager: SettingsManager, limited_mode: bool = False):
        super().__init__()
        self.settings_manager = settings_manager
        self.limited_mode = limited_mode
        self.rag_engine = None
        self.query_processor = None
        self._pending_wiki_update = None  # Store wiki link information to be updated
        self._llm_config = None  # Store configured LLM configuration
        
        # Initialize game configuration manager
        from src.game_wiki_tooltip.utils import APPDATA_DIR
        from src.game_wiki_tooltip.config import GameConfigManager
        
        # Select game configuration file based on language settings
        self._init_game_config_manager()
        
        # Initialize AI components based on mode
        if limited_mode:
            logger.info("🚨 RAG Integration running in limited mode, skipping AI component initialization")
        else:
            self._init_ai_components()
            
    def _init_game_config_manager(self):
        """Initialize game configuration manager based on language settings"""
        from src.game_wiki_tooltip.utils import APPDATA_DIR
        from src.game_wiki_tooltip.config import GameConfigManager
        
        # Get current language settings
        settings = self.settings_manager.get()
        current_language = settings.get('language', 'zh')  # Default to Chinese
        
        # Select configuration file based on language
        if current_language == 'en':
            games_config_path = APPDATA_DIR / "games_en.json"
            logger.info(f"🌐 Using English game configuration: {games_config_path}")
        else:
            # Default to Chinese configuration (zh or other)
            games_config_path = APPDATA_DIR / "games_zh.json"
            logger.info(f"🌐 Using Chinese game configuration: {games_config_path}")
            
        # Check if configuration file exists, fallback to default games.json if not
        if not games_config_path.exists():
            logger.warning(f"⚠️ Language configuration file not found: {games_config_path}")
            fallback_path = APPDATA_DIR / "games.json"
            if fallback_path.exists():
                games_config_path = fallback_path
                logger.info(f"📄 Falling back to default configuration file: {games_config_path}")
            else:
                logger.error(f"❌ Even default configuration file doesn't exist: {fallback_path}")
        
        self.game_cfg_mgr = GameConfigManager(games_config_path)
        self._current_language = current_language
        logger.info(f"✅ Game configuration manager initialized, current language: {current_language}")
        
    def reload_for_language_change(self):
        """Reload game configuration when language settings change"""
        logger.info("🔄 Language setting change detected, reloading game configuration")
        self._init_game_config_manager()
        
    def _init_ai_components(self):
        """Initialize AI components with settings"""
        # Skip AI component initialization if in limited mode
        if self.limited_mode:
            logger.info("🚨 Skipping AI component initialization in limited mode")
            return
            
        # Defer AI component initialization until actually needed
        logger.info("📌 AI components will be initialized on first use (lazy loading)")
        
    def _ensure_ai_components_loaded(self):
        """Ensure AI components are loaded (called before actual use)"""
        if self.limited_mode:
            return False
            
        # If AI modules are loading, wait for completion
        if _ai_modules_loading:
            logger.info("⏳ AI modules are loading in background, waiting for completion...")
            max_wait = 10  # Wait up to 10 seconds
            start_time = time.time()
            while _ai_modules_loading and (time.time() - start_time) < max_wait:
                time.sleep(0.1)
            
            if not _ai_modules_loaded:
                logger.error("❌ AI module loading timeout")
                return False
        
        # Try to load AI modules
        if not _lazy_load_ai_modules():
            logger.error("❌ AI module loading failed")
            return False
            
        # Initialize only when first called
        if hasattr(self, '_ai_initialized') and self._ai_initialized:
            return True
            
        try:
            # Get API settings
            settings = self.settings_manager.get()
            api_settings = settings.get('api', {})
            gemini_api_key = api_settings.get('gemini_api_key', '')
            jina_api_key = api_settings.get('jina_api_key', '')
            
            # Check environment variables
            if not gemini_api_key:
                gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
            if not jina_api_key:
                jina_api_key = os.getenv('JINA_API_KEY')
            
            # Check if there are two API keys
            has_both_keys = bool(gemini_api_key and jina_api_key)
            
            if has_both_keys:
                logger.info("✅ Complete API key configuration detected, initializing AI components")
                
                llm_config = LLMConfig(
                    api_key=gemini_api_key,
                    model='gemini-2.5-flash-lite-preview-06-17'
                )
                
                # Store LLM configuration for other methods
                self._llm_config = llm_config
                
                # Initialize query processor - remove, we will directly use process_query_unified function
                # if process_query_unified:
                #     self.query_processor = process_query_unified(llm_config=llm_config)
                
                # Smart initialization of RAG engine
                game_title = get_selected_game_title()
                if game_title:
                    # Use window title to map to vector library name
                    from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name
                    vector_game_name = map_window_title_to_game_name(game_title)
                    
                    if vector_game_name:
                        logger.info(f"Detected game window '{game_title}' -> Vector library: {vector_game_name}")
                        self._init_rag_for_game(vector_game_name, llm_config, jina_api_key)
                    else:
                        logger.info(f"Current window '{game_title}' is not a supported game, skipping RAG initialization")
                        logger.info("RAG engine will be dynamically initialized based on game window when user first queries")
                        # Don't initialize RAG engine, wait for dynamic detection when user queries
                else:
                    logger.info("No foreground window detected, skipping RAG initialization")
            else:
                missing_keys = []
                if not gemini_api_key:
                    missing_keys.append("Gemini API Key")
                if not jina_api_key:
                    missing_keys.append("Jina API Key")
                
                logger.warning(f"❌ Missing required API keys: {', '.join(missing_keys)}")
                logger.warning("Cannot initialize AI components, need to configure both Gemini API Key and Jina API Key")
                return False
                    
        except Exception as e:
            logger.error(f"Failed to initialize AI components: {e}")
            return False
            
        self._ai_initialized = True
        return True
            
    def _init_rag_for_game(self, game_name: str, llm_config: LLMConfig, jina_api_key: str, wait_for_init: bool = False):
        """Initialize RAG engine for specific game"""
        try:
            if not (get_default_config and EnhancedRagQuery):
                logger.warning("RAG components not available")
                return
                
            logger.info(f"🔄 Initializing new RAG engine for game '{game_name}'")
            
            # Clear old RAG engine
            if hasattr(self, 'rag_engine') and self.rag_engine:
                logger.info("🗑️ Clearing old RAG engine instance")
                self.rag_engine = None
                
            # Get RAG config
            rag_config = get_default_config()
            
            # Custom hybrid search configuration, disable unified query processing
            custom_hybrid_config = rag_config.hybrid_search.to_dict()
            custom_hybrid_config["enable_unified_processing"] = False  # Disable unified query processing
            custom_hybrid_config["enable_query_rewrite"] = False      # Disable query rewrite
            custom_hybrid_config["enable_query_translation"] = False  # Disable query translation
            
            # Create RAG engine
            self.rag_engine = EnhancedRagQuery(
                vector_store_path=None,  # Will be auto-detected
                enable_hybrid_search=rag_config.hybrid_search.enabled,
                hybrid_config=custom_hybrid_config,  # Use custom configuration
                llm_config=llm_config,
                jina_api_key=jina_api_key,  # Pass Jina API key
                enable_query_rewrite=False,  # Disable query rewrite, avoid duplicate LLM calls
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
                    logger.info(f"🚀 Starting async RAG engine initialization (game: {game_name})")
                    loop.run_until_complete(self.rag_engine.initialize(game_name))
                    logger.info(f"✅ RAG engine initialization completed (game: {game_name})")
                    self._rag_init_complete = True
                    self._current_rag_game = game_name  # Record current RAG engine game
                    # Clear error information
                    if hasattr(self, '_rag_init_error'):
                        delattr(self, '_rag_init_error')
                except Exception as e:
                    logger.error(f"❌ RAG engine initialization failed (game: {game_name}): {e}")
                    self.rag_engine = None
                    self._rag_init_complete = False
                    self._rag_init_error = str(e)  # Record initialization error
                    self._current_rag_game = None
                finally:
                    loop.close()
            
            # Reset initialization status
            self._rag_init_complete = False
            
            # Run initialization in a separate thread
            import threading
            init_thread = threading.Thread(target=init_rag)
            init_thread.daemon = True
            init_thread.start()
            
            # If waiting for initialization to complete
            if wait_for_init:
                # Wait for initialization to complete, up to 5 seconds
                import time
                start_time = time.time()
                while not hasattr(self, '_rag_init_complete') or not self._rag_init_complete:
                    if time.time() - start_time > 5:  # Timeout
                        logger.warning("RAG initialization timeout")
                        break
                    time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Failed to initialize RAG for {game_name}: {e}")
            
    async def process_query_async(self, query: str, game_context: str = None) -> QueryIntent:
        """Process query using unified query processor for intent detection"""
        logger.info(f"Start unified query processing: '{query}' (game context: {game_context}, limited mode: {self.limited_mode})")
        
        # If in limited mode, always return wiki intent
        if self.limited_mode:
            logger.info("🚨 In limited mode, all queries will be treated as wiki queries")
            return QueryIntent(
                intent_type='wiki',
                confidence=0.9,
                rewritten_query=query,
                translated_query=query
            )
            
        # Ensure AI components are loaded (lazy loading)
        if not self._ensure_ai_components_loaded():
            logger.error("❌ AI component loading failed, switch to wiki mode")
            return QueryIntent(
                intent_type='wiki',
                confidence=0.9,
                rewritten_query=query,
                translated_query=query
            )
        
        # ✅ New: Before calling LLM, check if the game window supports RAG guide query (has vector library)
        if game_context:
            # 1. Check if RAG guide query is supported (has vector library)
            from .ai.rag_query import map_window_title_to_game_name
            game_name = map_window_title_to_game_name(game_context)
            
            # 2. Check if it is supported in games.json configuration (supports wiki query)
            is_wiki_supported = self._is_game_supported_for_wiki(game_context)
            
            # If neither RAG guide query nor wiki query is supported, return unsupported
            if not game_name and not is_wiki_supported:
                logger.info(f"📋 Window '{game_context}' does not support guide query")
                return QueryIntent(
                    intent_type='unsupported',
                    confidence=1.0,
                    rewritten_query=query,
                    translated_query=query
                )
        else:
            # If there is no game context (no recorded game window), skip unified query processing, use simple intent detection
            logger.info("📋 No recorded game window, skip unified query processing, use simple intent detection")
            return self._simple_intent_detection(query)
        
        if not process_query_unified:
            # Fallback to simple detection
            logger.warning("Unified query processor is not available, use simple intent detection")
            return self._simple_intent_detection(query)
            
        try:
            # Use stored LLM configuration, if not create temporary configuration
            llm_config = self._llm_config
            if not llm_config:
                # If there is no stored configuration, create temporary configuration and check API key
                llm_config = LLMConfig(
                    model='gemini-2.5-flash-lite-preview-06-17'
                )
                
                # Use LLMConfig's get_api_key method to get API key (supports GEMINI_API_KEY environment variable)
                api_key = llm_config.get_api_key()
                if not api_key:
                    logger.warning("GEMINI_API_KEY not configured, use simple intent detection")
                    return self._simple_intent_detection(query)
                    
                # Update API key in configuration
                llm_config.api_key = api_key
            else:
                # Use stored configuration, verify API key
                api_key = llm_config.get_api_key()
                if not api_key:
                    logger.warning("Stored LLM configuration does not have a valid API key, use simple intent detection")
                    return self._simple_intent_detection(query)
            
            # Use unified query processor for processing (merged translation, rewrite, intent detection)
            result = await asyncio.to_thread(
                process_query_unified,
                query,
                llm_config=llm_config
            )
            
            logger.info(f"Unified processing successful: '{query}' -> intent: {result.intent} (confidence: {result.confidence:.3f})")
            logger.info(f"  Translated result: '{result.translated_query}'")
            logger.info(f"  Rewritten result: '{result.rewritten_query}'")
            logger.info(f"  BM25 optimized: '{result.bm25_optimized_query}'")
            
            return QueryIntent(
                intent_type=result.intent,
                confidence=result.confidence,
                rewritten_query=result.rewritten_query,
                translated_query=result.translated_query,  # Add translated query
                unified_query_result=result  # Pass complete unified query result
            )
            
        except Exception as e:
            logger.error(f"Unified query processing failed: {e}")
            return self._simple_intent_detection(query)
            
    def _is_game_supported_for_wiki(self, window_title: str) -> bool:
        """Check if the game window supports wiki query (based on games.json configuration)"""
        try:
            # Get game configuration
            if hasattr(self, 'game_cfg_mgr') and self.game_cfg_mgr:
                game_config = self.game_cfg_mgr.for_title(window_title)
                if game_config:
                    logger.info(f"🎮 Window '{window_title}' found in games.json, supports wiki query")
                    return True
            
            logger.info(f"📋 Window '{window_title}' not found in games.json")
            return False
        except Exception as e:
            logger.error(f"Error checking game configuration: {e}")
            return False
            
    def _simple_intent_detection(self, query: str) -> QueryIntent:
        """Simple keyword-based intent detection"""
        # If in limited mode, always return wiki intent
        if self.limited_mode:
            return QueryIntent(
                intent_type='wiki',
                confidence=0.9,
                rewritten_query=query,
                translated_query=query
            )
            
        query_lower = query.lower()
        
        # Wiki intent keywords
        wiki_keywords = ['是什么', 'what is', 'wiki', '介绍', 'info']
        # Guide intent keywords  
        guide_keywords = ['怎么', '如何', 'how to', 'guide', '推荐', 'best']
        
        wiki_score = sum(1 for kw in wiki_keywords if kw in query_lower)
        guide_score = sum(1 for kw in guide_keywords if kw in query_lower)
        
        if wiki_score > guide_score:
            return QueryIntent(
                intent_type='wiki', 
                confidence=0.7, 
                rewritten_query=query,
                translated_query=query
            )
        else:
            return QueryIntent(
                intent_type='guide', 
                confidence=0.7,
                rewritten_query=query,
                translated_query=query
            )
            
    async def prepare_wiki_search_async(self, query: str, game_context: str = None) -> tuple[str, str]:
        """Prepare wiki search, return search URL and initial title, real URL will be obtained through JavaScript callback"""
        try:
            from urllib.parse import quote, urlparse
            
            # Use the incoming game context, if not get the current game window title
            game_title = game_context or get_selected_game_title()
            logger.info(f"🎮 Current game window title: {game_title}")
            
            # Find game configuration - use instance variable
            game_config = self.game_cfg_mgr.for_title(game_title)
            
            if not game_config:
                logger.warning(f"Game configuration not found: {game_title}")
                # Fallback to general search
                search_query = f"{game_title} {query} wiki"
                ddg_url = f"https://duckduckgo.com/?q=!ducky+{quote(search_query)}"
                # Store wiki information to be updated (marked as DuckDuckGo search)
                self._pending_wiki_update = {
                    "initial_url": ddg_url,
                    "query": query,
                    "title": f"Search: {query}",
                    "status": "searching"
                }
            else:
                logger.info(f"Game configuration found: {game_config}")
                
                # Get base URL
                base_url = game_config.BaseUrl
                logger.info(f"Game base URL: {base_url}")
                
                # Extract domain
                if base_url.startswith(('http://', 'https://')):
                    domain = urlparse(base_url).hostname or ''
                else:
                    # If there is no protocol prefix, use base_url as domain
                    domain = base_url.split('/')[0]  # Remove path part
                
                logger.info(f"Extracted domain: {domain}")
                
                # Build correct search query: site:domain user query
                search_query = f"site:{domain} {query}"
                ddg_url = f"https://duckduckgo.com/?q=!ducky+{quote(search_query)}"
                
                logger.info(f"Built search query: {search_query}")
                logger.info(f"DuckDuckGo URL: {ddg_url}")
                
                # Store wiki information to be updated
                self._pending_wiki_update = {
                    "initial_url": ddg_url,
                    "query": query,
                    "title": f"Search: {query}",
                    "domain": domain,
                    "status": "searching"
                }
            
            # Return search URL and temporary title, real URL will be updated through JavaScript callback
            return ddg_url, f"Search: {query}"
                    
        except Exception as e:
            logger.error(f"Wiki search preparation failed: {e}")
            return "", query
            
    async def search_wiki_async(self, query: str, game_context: str = None) -> tuple[str, str]:
        """Search for wiki page"""
        # Use existing wiki search logic from overlay.py
        try:
            import aiohttp
            from urllib.parse import quote, urlparse
            
            # Use the incoming game context, if not get the current game window title
            game_title = game_context or get_selected_game_title()
            logger.info(f"🎮 Current game window title: {game_title}")
            
            # Find game configuration - use instance variable
            game_config = self.game_cfg_mgr.for_title(game_title)
            
            if not game_config:
                logger.warning(f"Game configuration not found: {game_title}")
                # Fallback to general search
                search_query = f"{game_title} {query} wiki"
                ddg_url = f"https://duckduckgo.com/?q=!ducky+{quote(search_query)}"
            else:
                logger.info(f"Game configuration found: {game_config}")
                
                # Get base URL
                base_url = game_config.BaseUrl
                logger.info(f"Game base URL: {base_url}")
                
                # Extract domain
                if base_url.startswith(('http://', 'https://')):
                    domain = urlparse(base_url).hostname or ''
                else:
                    # If there is no protocol prefix, use base_url as domain
                    domain = base_url.split('/')[0]  # Remove path part
                
                logger.info(f"Extracted domain: {domain}")
                
                # Build correct search query: site:domain user query
                search_query = f"site:{domain} {query}"
                ddg_url = f"https://duckduckgo.com/?q=!ducky+{quote(search_query)}"
                
                logger.info(f"Built search query: {search_query}")
                logger.info(f"DuckDuckGo URL: {ddg_url}")
            
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
            
    def on_wiki_found(self, real_url: str, real_title: str = None):
        """When JavaScript finds the real wiki page, call this method"""
        if self._pending_wiki_update:
            logger.info(f"📄 JavaScript found the real wiki page: {real_url}")
            
            # Extract page title (if not provided)
            if not real_title:
                # Extract title from URL
                try:
                    from urllib.parse import unquote
                    parts = real_url.split('/')
                    if parts:
                        real_title = unquote(parts[-1]).replace('_', ' ')
                    else:
                        real_title = self._pending_wiki_update.get("query", "Wiki page")
                except:
                    real_title = self._pending_wiki_update.get("query", "Wiki page")
            
            # Update pending wiki information
            self._pending_wiki_update.update({
                "real_url": real_url,
                "real_title": real_title,
                "status": "found"
            })
            
            # Emit signal to update link in chat window
            self.wiki_link_updated.emit(real_url, real_title)
            logger.info(f"✅ Emitted wiki link update signal: {real_title} -> {real_url}")
            
            # Clear pending update information
            self._pending_wiki_update = None
        else:
            logger.warning("⚠️ Received wiki page callback, but no pending wiki information")
            
    async def generate_guide_async(self, query: str, game_context: str = None, original_query: str = None, skip_query_processing: bool = False, unified_query_result = None, stop_flag = None):
        """Generate guide response with streaming
        
        Args:
            query: 处理后的查询文本
            game_context: 游戏上下文
            original_query: 原始查询（用于答案生成）
            skip_query_processing: 是否跳过RAG内部的查询处理
            unified_query_result: 预处理的统一查询结果（来自process_query_unified）
        """
        # If in limited mode, display corresponding prompt information
        if self.limited_mode:
            logger.info("🚨 In limited mode, AI guide features are unavailable")
            self.error_occurred.emit(
                "🚨 AI Guide Features Unavailable\n\n"
                "Currently running in limited mode with Wiki search only.\n\n"
                "To use AI guide features, please configure both API keys (both required):\n"
                "• Google/Gemini API Key (required) - for AI reasoning\n"
                "• Jina API Key (required) - for vector search\n\n"
                "⚠️ Note: Gemini API alone cannot provide high-quality RAG functionality.\n"
                "Jina vector search is essential for complete AI guide features.\n\n"
                "Restart the program after configuration to enable full functionality."
            )
            return
            
        if not self.rag_engine:
            # Try to initialize RAG engine for specified game
            if game_context:
                from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name
                vector_game_name = map_window_title_to_game_name(game_context)
                
                if vector_game_name:
                    logger.info(f"RAG engine not initialized, attempting to initialize for game '{vector_game_name}'")
                    
                    # Get API settings
                    settings = self.settings_manager.get()
                    api_settings = settings.get('api', {})
                    gemini_api_key = api_settings.get('gemini_api_key', '')
                    jina_api_key = api_settings.get('jina_api_key', '')
                    
                    # Check environment variables
                    if not gemini_api_key:
                        gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
                    if not jina_api_key:
                        jina_api_key = os.getenv('JINA_API_KEY')
                    
                    # Check if there are two API keys
                    has_both_keys = bool(gemini_api_key and jina_api_key)
                    
                    if has_both_keys:
                        llm_config = LLMConfig(
                            api_key=gemini_api_key,
                            model='gemini-2.5-flash-lite-preview-06-17'
                        )
                        self._init_rag_for_game(vector_game_name, llm_config, jina_api_key, wait_for_init=True)
                        
                        if not self.rag_engine:
                            # Check if the vector library does not exist
                            logger.info(f"📋 The vector library for game '{vector_game_name}' does not exist, provide fallback solution")
                            
                            # Use internationalized error information
                            from src.game_wiki_tooltip.i18n import t, get_current_language
                            current_lang = get_current_language()
                            
                            if current_lang == 'zh':
                                error_msg = (
                                    f"🎮 Game '{game_context}' does not have a guide database yet\n\n"
                                    "💡 Suggestion: You can try using the Wiki search function to find related information\n\n"
                                    "📚 Games currently supporting guide queries:\n"
                                    "• 地狱潜兵2 (HELLDIVERS 2) - 武器配装、敌人攻略等\n"
                                    "• 艾尔登法环 (Elden Ring) - Boss攻略、装备推荐等\n"
                                    "• 饥荒联机版 (Don't Starve Together) - 生存技巧、角色攻略等\n"
                                    "• 文明6 (Civilization VI) - 文明特色、胜利策略等\n"
                                    "• 七日杀 (7 Days to Die) - 建筑、武器制作等"
                                )
                            else:
                                error_msg = (
                                    f"🎮 Game '{game_context}' doesn't have a guide database yet\n\n"
                                    "💡 Suggestion: You can try using the Wiki search function to find related information\n\n"
                                    "📚 Games currently supporting guide queries:\n"
                                    "• HELLDIVERS 2 - Weapon builds, enemy guides, etc.\n"
                                    "• Elden Ring - Boss guides, equipment recommendations, etc.\n"
                                    "• Don't Starve Together - Survival tips, character guides, etc.\n"
                                    "• Civilization VI - Civilization features, victory strategies, etc.\n"
                                    "• 7 Days to Die - Construction, weapon crafting, etc."
                                )
                            
                            self.error_occurred.emit(error_msg)
                            return
                    else:
                        missing_keys = []
                        if not gemini_api_key:
                            missing_keys.append("Gemini API Key")
                        if not jina_api_key:
                            missing_keys.append("Jina API Key")
                        
                        # Use internationalized error information
                        from src.game_wiki_tooltip.i18n import get_current_language
                        current_lang = get_current_language()
                        
                        if current_lang == 'zh':
                            error_msg = (
                                f"❌ 缺少必需的API密钥: {', '.join(missing_keys)}\n\n"
                                "AI攻略功能需要同时配置两个API密钥：\n"
                                "• Google/Gemini API Key - 用于AI推理\n"
                                "• Jina API Key - 用于向量搜索\n\n"
                                "⚠️ 注意：仅有Gemini API无法提供高质量的RAG功能。\n"
                                "Jina向量搜索对完整的AI攻略功能至关重要。\n\n"
                                "请在设置中配置完整的API密钥并重试。"
                            )
                        else:
                            error_msg = (
                                f"❌ Missing required API keys: {', '.join(missing_keys)}\n\n"
                                "AI guide features require both API keys to be configured:\n"
                                "• Google/Gemini API Key - for AI reasoning\n"
                                "• Jina API Key - for vector search\n\n"
                                "⚠️ Note: Gemini API alone cannot provide high-quality RAG functionality.\n"
                                "Jina vector search is essential for complete AI guide features.\n\n"
                                "Please configure complete API keys in settings and try again."
                            )
                        
                        self.error_occurred.emit(error_msg)
                        return
                else:
                    logger.info(f"📋 Window '{game_context}' does not support guide queries")
                    
                    # Use internationalized error information
                    from src.game_wiki_tooltip.i18n import get_current_language
                    current_lang = get_current_language()
                    
                    if current_lang == 'zh':
                        error_msg = (
                            f"🎮 窗口 '{game_context}' 暂时不支持攻略查询\n\n"
                            "💡 建议：您可以尝试使用Wiki搜索功能查找相关信息\n\n"
                            "📚 目前支持攻略查询的游戏：\n"
                            "• 地狱潜兵2 (HELLDIVERS 2) - 武器配装、敌人攻略等\n"
                            "• 艾尔登法环 (Elden Ring) - Boss攻略、装备推荐等\n"
                            "• 饥荒联机版 (Don't Starve Together) - 生存技巧、角色攻略等\n"
                            "• 文明6 (Civilization VI) - 文明特色、胜利策略等\n"
                            "• 七日杀 (7 Days to Die) - 建筑、武器制作等"
                        )
                    else:
                        error_msg = (
                            f"🎮 Window '{game_context}' doesn't support guide queries yet\n\n"
                            "💡 Suggestion: You can try using the Wiki search function to find related information\n\n"
                            "📚 Games currently supporting guide queries:\n"
                            "• HELLDIVERS 2 - Weapon builds, enemy guides, etc.\n"
                            "• Elden Ring - Boss guides, equipment recommendations, etc.\n"
                            "• Don't Starve Together - Survival tips, character guides, etc.\n"
                            "• Civilization VI - Civilization features, victory strategies, etc.\n"
                            "• 7 Days to Die - Construction, weapon crafting, etc."
                        )
                    
                    self.error_occurred.emit(error_msg)
                    return
            else:
                self.error_occurred.emit("RAG engine not initialized and no game context provided")
                return
            
        try:
            # Query RAG engine (it's already async)
            logger.info(f"🔍 Directly use processed query for RAG search: '{query}'")
            if original_query:
                logger.info(f"📝 Use original query for answer generation: '{original_query}'")
            if skip_query_processing:
                logger.info("⚡ Skip RAG internal query processing, use optimized query")
            if unified_query_result:
                logger.info(f"🔄 Pass preprocessed unified query result, avoid duplicate processing")
                logger.info(f"   - BM25 optimized query: '{unified_query_result.bm25_optimized_query}'")
            
            # Directly use streaming RAG query, process all logic during streaming
            logger.info("🌊 Use streaming RAG query")
            stream_generator = None
            try:
                has_output = False
                # Get streaming generator
                stream_generator = self.rag_engine.query_stream(
                    question=query, 
                    top_k=3, 
                    original_query=original_query,
                    unified_query_result=unified_query_result
                )
                
                # Use real streaming API
                async for chunk in stream_generator:
                    # Check if stop is requested
                    if stop_flag and stop_flag():
                        logger.info("🛑 Stop requested, interrupt streaming")
                        break
                        
                    # Ensure chunk is string type
                    if isinstance(chunk, dict):
                        logger.warning(f"Received dictionary type chunk, skip: {chunk}")
                        continue
                    
                    chunk_str = str(chunk) if chunk is not None else ""
                    if chunk_str.strip():  # Only send non-empty content
                        has_output = True
                        self.streaming_chunk_ready.emit(chunk_str)
                        await asyncio.sleep(0.01)  # Very short delay to keep UI responsive
                
                # If there is no output, it may need to switch to wiki mode
                if not has_output:
                    logger.info(f"🔄 RAG query has no output, may need to switch to wiki mode: '{query}'")
                    
                    from src.game_wiki_tooltip.i18n import get_current_language
                    current_lang = get_current_language()
                    
                    if current_lang == 'zh':
                        self.streaming_chunk_ready.emit("💡 该游戏暂无攻略数据库，为您自动切换到Wiki搜索模式...\n\n")
                    else:
                        self.streaming_chunk_ready.emit("💡 No guide database for this game, automatically switching to Wiki search mode...\n\n")
                    
                    # 自动切换到wiki搜索
                    try:
                        search_url, search_title = await self.prepare_wiki_search_async(query, game_context)
                        self.wiki_result_ready.emit(search_url, search_title)
                        
                        if current_lang == 'zh':
                            self.streaming_chunk_ready.emit(f"🔗 已为您打开Wiki搜索: {search_title}\n")
                        else:
                            self.streaming_chunk_ready.emit(f"🔗 Wiki search opened: {search_title}\n")
                    except Exception as wiki_error:
                        logger.error(f"Auto Wiki search failed: {wiki_error}")
                        if current_lang == 'zh':
                            self.streaming_chunk_ready.emit("❌ Auto Wiki search failed, please click Wiki search button manually\n")
                        else:
                            self.streaming_chunk_ready.emit("❌ Auto Wiki search failed, please click Wiki search button manually\n")
                    return
                
                logger.info("✅ Streaming RAG query completed")
                return
                    
            except Exception as e:
                # Handle specific RAG error types
                from src.game_wiki_tooltip.ai.rag_query import VectorStoreUnavailableError
                from src.game_wiki_tooltip.ai.enhanced_bm25_indexer import BM25UnavailableError
                from src.game_wiki_tooltip.i18n import t, get_current_language
                
                current_lang = get_current_language()
                
                if isinstance(e, VectorStoreUnavailableError):
                    if current_lang == 'zh':
                        error_msg = f"❌ {t('rag_vector_store_error')}: {str(e)}"
                    else:
                        error_msg = f"❌ {t('rag_vector_store_error')}: {str(e)}"
                elif isinstance(e, BM25UnavailableError):
                    if current_lang == 'zh':
                        error_msg = f"❌ {t('rag_bm25_error')}: {str(e)}"
                    else:
                        error_msg = f"❌ {t('rag_bm25_error')}: {str(e)}"
                else:
                    # General error - try to switch to wiki mode automatically
                    logger.error(f"Streaming RAG query failed: {e}")
                    logger.info("Trying to switch to Wiki search mode...")
                    
                    try:
                        # 如果流式查询失败，自动切换到wiki搜索
                        if current_lang == 'zh':
                            self.streaming_chunk_ready.emit("❌ AI攻略查询遇到问题，为您自动切换到Wiki搜索...\n\n")
                        else:
                            self.streaming_chunk_ready.emit("❌ AI guide query encountered an issue, automatically switching to Wiki search...\n\n")
                        
                        search_url, search_title = await self.prepare_wiki_search_async(query, game_context)
                        self.wiki_result_ready.emit(search_url, search_title)
                        
                        if current_lang == 'zh':
                            self.streaming_chunk_ready.emit(f"🔗 已为您打开Wiki搜索: {search_title}\n")
                        else:
                            self.streaming_chunk_ready.emit(f"🔗 Wiki search opened: {search_title}\n")
                        return
                    except Exception as wiki_error:
                        logger.error(f"Auto Wiki search also failed: {wiki_error}")
                        if current_lang == 'zh':
                            error_msg = f"❌ AI guide query failed, and Wiki search also failed. Please try again later.\nError details: {str(e)}"
                        else:
                            error_msg = f"❌ AI guide query failed, and Wiki search also failed. Please try again later.\nError details: {str(e)}"
                    
                # Send error information (for specific error types or wiki search failure)
                if 'error_msg' in locals():
                    logger.error(f"Send error information to chat window: {error_msg}")
                    self.streaming_chunk_ready.emit(error_msg)
                return
            finally:
                # Ensure asynchronous generator is properly closed
                if stream_generator is not None:
                    try:
                        await stream_generator.aclose()
                        logger.debug("Asynchronous generator properly closed")
                    except Exception as close_error:
                        logger.warning(f"Error closing asynchronous generator: {close_error}")
                    
        except Exception as e:
            logger.error(f"Guide generation failed: {e}")
            self.error_occurred.emit(f"Guide generation failed: {str(e)}")


class IntegratedAssistantController(AssistantController):
    """Enhanced assistant controller with RAG integration"""
    
    # Class-level global instance reference
    _global_instance = None
    
    def __init__(self, settings_manager: SettingsManager, limited_mode: bool = False):
        super().__init__(settings_manager)
        self.limited_mode = limited_mode
        self.rag_integration = RAGIntegration(settings_manager, limited_mode=limited_mode)
        self._setup_connections()
        self._current_worker = None
        self._current_wiki_message = None  # Store current wiki link message component
        self._rag_initializing = False  # Mark RAG as initializing
        self._target_vector_game = None  # Target vector game name
        
        # Register as global instance
        IntegratedAssistantController._global_instance = self
        logger.info(f"🌐 Registered as global assistant controller instance (limited_mode={limited_mode})")
        
        # If in limited mode, display prompt information
        if limited_mode:
            logger.info("🚨 Running in limited mode: only Wiki search functionality is supported")
        else:
            logger.info("✅ Running in full mode: supports Wiki search and AI guide functionality")
            # Preload AI modules when idle
            self._schedule_ai_preload()
        
    def _schedule_ai_preload(self):
        """Preload AI modules when idle"""
        # Store loader reference to prevent garbage collection
        self._ai_loader = None
        
        def start_background_loading():
            """Start background loading thread"""
            logger.info("🚀 Start AI module background loading thread...")
            
            # Create and start loader thread
            self._ai_loader = AIModuleLoader()
            self._ai_loader.load_completed.connect(self._on_ai_modules_loaded)
            self._ai_loader.start()
        
        # Use QTimer to delay 3 seconds before starting background loading (give UI enough time to initialize)
        QTimer.singleShot(3000, start_background_loading)
        logger.info("📅 AI modules scheduled for background loading in 3 seconds")
        
    def _on_ai_modules_loaded(self, success: bool):
        """Callback when AI modules are loaded"""
        if success:
            logger.info("✅ AI module background loading completed")
            # Record loading success status
            self._ai_modules_ready = True
            
            # Try to preinitialize RAG components
            try:
                self.rag_integration._ensure_ai_components_loaded()
                logger.info("✅ RAG components preinitialized")
            except Exception as e:
                logger.warning(f"⚠️ RAG components preinitialization failed: {e}")
        else:
            logger.warning("⚠️ AI module background loading failed")
            self._ai_modules_ready = False
            
        # Clean up loader reference
        self._ai_loader = None
        
    def __del__(self):
        """Destructor, clean up global instance reference"""
        if IntegratedAssistantController._global_instance is self:
            IntegratedAssistantController._global_instance = None
            logger.info("🌐 Global assistant controller instance reference cleaned up")
        
    def set_current_game_window(self, game_window_title: str):
        """Override parent class method, set current game window and handle RAG engine initialization"""
        super().set_current_game_window(game_window_title)
        
        # Check if RAG engine needs to be initialized or switched
        from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name
        vector_game_name = map_window_title_to_game_name(game_window_title)
        
        if vector_game_name:
            logger.info(f"🎮 Detected game window, preparing to initialize RAG engine: {vector_game_name}")
            # Check if game needs to be switched
            if not hasattr(self, '_current_vector_game') or self._current_vector_game != vector_game_name:
                logger.info(f"🔄 Switch RAG engine: {getattr(self, '_current_vector_game', 'None')} -> {vector_game_name}")
                self._current_vector_game = vector_game_name
                # Asynchronously initialize RAG engine, do not block UI
                self._reinitialize_rag_for_game(vector_game_name)
            else:
                logger.info(f"✓ Game not switched, continue using current RAG engine: {vector_game_name}")
        else:
            logger.info(f"⚠️ Window '{game_window_title}' is not a supported game")
        
    def _setup_connections(self):
        """Setup signal connections"""
        self.rag_integration.streaming_chunk_ready.connect(
            self._on_streaming_chunk
        )
        self.rag_integration.wiki_result_ready.connect(
            self._on_wiki_result
        )
        self.rag_integration.wiki_link_updated.connect(
            self._on_wiki_link_updated
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
        
        # Check RAG engine initialization status
        if getattr(self, '_rag_initializing', False):
            # RAG engine is initializing, display waiting status
            from src.game_wiki_tooltip.i18n import t
            logger.info("🔄 RAG engine is initializing, display waiting status")
            self.main_window.chat_view.show_status(t("rag_initializing"))
            
            # Delay processing query, check initialization status periodically
            self._pending_query = query
            self._check_rag_init_status()
            return
        
        # RAG engine is ready, process query normally
        self._process_query_immediately(query)
        
    def _check_rag_init_status(self):
        """Check RAG initialization status periodically"""
        from src.game_wiki_tooltip.i18n import t
        
        if hasattr(self.rag_integration, '_rag_init_complete') and self.rag_integration._rag_init_complete:
            # Initialization completed
            logger.info("✅ RAG engine initialization completed, start processing query")
            self._rag_initializing = False
            self.main_window.chat_view.hide_status()
            
            # Process waiting query
            if hasattr(self, '_pending_query'):
                self._process_query_immediately(self._pending_query)
                delattr(self, '_pending_query')
        elif hasattr(self.rag_integration, '_rag_init_complete') and self.rag_integration._rag_init_complete is False:
            # Initialization failed
            logger.error("❌ RAG engine initialization failed")
            self._rag_initializing = False
            self.main_window.chat_view.hide_status()
            
            # Display error information
            if hasattr(self.rag_integration, '_rag_init_error'):
                error_msg = self.rag_integration._rag_init_error
                logger.error(f"RAG initialization error details: {error_msg}")
                # Send error to chat window
                self.main_window.chat_view.add_message(
                    MessageType.AI_RESPONSE,
                    f"{t('rag_init_failed')}: {error_msg}"
                )
            else:
                # General error information
                self.main_window.chat_view.add_message(
                    MessageType.AI_RESPONSE,
                    t("rag_init_failed")
                )
            
            # Clean up waiting query
            if hasattr(self, '_pending_query'):
                delattr(self, '_pending_query')
        else:
            # Continue waiting, check every 500ms, up to 10 seconds
            if not hasattr(self, '_rag_init_start_time'):
                import time
                self._rag_init_start_time = time.time()
            
            import time
            if time.time() - self._rag_init_start_time > 10:  # Timeout 10 seconds
                logger.warning("RAG initialization timeout")
                self._rag_initializing = False
                self.main_window.chat_view.hide_status()
                
                # Display timeout error
                self.main_window.chat_view.add_message(
                    MessageType.ERROR,
                    f"{t('rag_init_failed')}: Initialization timeout"
                )
                
                # Clean up
                if hasattr(self, '_pending_query'):
                    delattr(self, '_pending_query')
                if hasattr(self, '_rag_init_start_time'):
                    delattr(self, '_rag_init_start_time')
            else:
                # Continue waiting
                QTimer.singleShot(500, self._check_rag_init_status)
            
    def _process_query_immediately(self, query: str):
        """Immediately process query (RAG engine is ready)"""
        # Stop any existing worker and reset UI state
        if self._current_worker and self._current_worker.isRunning():
            logger.info("🛑 New query started, stop previous generation")
            self._current_worker.stop()
            self._current_worker.wait()
            
            # If there is current streaming message, mark as stopped
            if hasattr(self, '_current_streaming_msg') and self._current_streaming_msg:
                self._current_streaming_msg.mark_as_stopped()
                
            # Reset UI state
            if self.main_window:
                self.main_window.set_generating_state(False)
                logger.info("🛑 UI state reset to non-generating state")
            
        # Disconnect all signals from RAG integration to prevent duplicates
        try:
            self.rag_integration.streaming_chunk_ready.disconnect()
            print(f"🔌 [SIGNAL-DEBUG] Disconnected previous streaming_chunk_ready signal")
        except:
            print(f"🔌 [SIGNAL-DEBUG] No previous streaming_chunk_ready signal connection to disconnect")
            pass  # If no connection, ignore error
            
        # Use recorded game window title (recorded when hotkey is triggered)
        if hasattr(self, 'current_game_window') and self.current_game_window:
            logger.info(f"🎮 Using recorded game window: '{self.current_game_window}'")
        else:
            logger.warning("⚠️ No recorded game window, possibly abnormal program state")
        
        # Create and start new worker with game context
        self._current_worker = QueryWorker(
            self.rag_integration, 
            query, 
            game_context=self.current_game_window
        )
        self._current_worker.intent_detected.connect(self._on_intent_detected)
        self._current_worker.wiki_result.connect(self._on_wiki_result_from_worker)
        self._current_worker.guide_chunk.connect(self._on_guide_chunk)
        self._current_worker.error_occurred.connect(self._on_error)
        
        # Reconnect RAG integration signals to current worker
        self.rag_integration.streaming_chunk_ready.connect(
            self._on_streaming_chunk  # Directly connect to processing method, not worker's signal
        )
        print(f"🔌 [SIGNAL-DEBUG] Reconnected streaming_chunk_ready signal to _on_streaming_chunk")
        
        # Add RAG status update timer to display processing progress
        if not hasattr(self, '_rag_status_timer'):
            self._rag_status_timer = QTimer()
            self._rag_status_timer.timeout.connect(self._update_rag_status)
            
        # Start status update timer
        self._rag_status_step = 0
        self._last_status_message = None  # Reset status message cache
        self._rag_status_timer.start(1500)  # Update every 1.5 seconds
        
        # Set generating state before starting worker, ensure user sees stop button
        if self.main_window:
            self.main_window.set_generating_state(True)
            logger.info("🔄 UI set to generating state (query started)")
        
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
                # Show guide search transition - Display status message instead of creating streaming message immediately
                self._current_status_widget = self.main_window.chat_view.show_status(
                    TransitionMessages.DB_SEARCHING
                )
                
                # Mark as waiting for RAG output, do not create streaming message immediately
                self._waiting_for_rag_output = True
                self._current_streaming_msg = None
                
        except Exception as e:
            logger.error(f"Intent detection handling error: {e}")
            self._on_error(str(e))
            
    def _setup_streaming_message(self):
        """Setup streaming message for guide responses"""
        print(f"🎯 [STREAMING-DEBUG] Start setting streaming message component")
        
        # If streaming message component already exists, do not create it again
        if hasattr(self, '_current_streaming_msg') and self._current_streaming_msg:
            logger.info("🔄 Streaming message component already exists, skip creating")
            print(f"🔄 [STREAMING-DEBUG] Streaming message component already exists, skip creating")
            return
            
        # Hide possible existing transition message
        if hasattr(self, '_current_transition_msg') and self._current_transition_msg:
            self._current_transition_msg.hide()
            print(f"🫥 [STREAMING-DEBUG] Transition message hidden")
            
        # Create streaming message component
        print(f"🏗️ [STREAMING-DEBUG] Call add_streaming_message()")
        try:
            self._current_streaming_msg = self.main_window.chat_view.add_streaming_message()
            logger.info("✅ Streaming message component created")
            print(f"✅ [STREAMING-DEBUG] Streaming message component created: {self._current_streaming_msg}")
            print(f"✅ [STREAMING-DEBUG] Streaming message component type: {type(self._current_streaming_msg)}")
            
            # Connect completion signal
            self._current_streaming_msg.streaming_finished.connect(self._on_streaming_finished)
            print(f"🔗 [STREAMING-DEBUG] Streaming finished signal connected")
            
            # Update UI generating state, associate streaming message component
            if self.main_window:
                self.main_window.set_generating_state(True, self._current_streaming_msg)
                logger.info("🔄 UI generating state associated with streaming message component")
                print(f"🔄 [STREAMING-DEBUG] UI generating state associated with streaming message component")
                
        except Exception as e:
            print(f"❌ [STREAMING-DEBUG] Create streaming message component failed: {e}")
            logger.error(f"Create streaming message component failed: {e}")
            # Ensure component is None, avoid subsequent operation exceptions
            self._current_streaming_msg = None
        
    def _on_wiki_result_from_worker(self, url: str, title: str):
        """Handle wiki result from worker"""
        try:
            # Wiki query completed, reset generating state
            if self.main_window:
                self.main_window.set_generating_state(False)
                logger.info("🔗 Wiki query completed, UI state reset to non-generating state")
            
            if url:
                # Update transition message
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.WIKI_FOUND)
                
                # Add wiki link message (initial display search URL)
                self._current_wiki_message = self.main_window.chat_view.add_message(
                    MessageType.WIKI_LINK,
                    title,
                    {"url": url}
                )
                
                # Show wiki page in the unified window (triggers JavaScript search for real URL)
                self.main_window.show_wiki_page(url, title)
            else:
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.ERROR_NOT_FOUND)
                    
        except Exception as e:
            logger.error(f"Wiki result handling error: {e}")
            self._on_error(str(e))
            
    def _on_wiki_link_updated(self, real_url: str, real_title: str):
        """Handle wiki link update signal"""
        try:
            if self._current_wiki_message:
                logger.info(f"🔗 Update wiki link in chat window: {real_title} -> {real_url}")
                
                # Update message content and metadata
                self._current_wiki_message.message.content = real_title
                self._current_wiki_message.message.metadata["url"] = real_url
                
                # Reset content to refresh display - fix: use real title instead of old content
                html_content = (
                    f'[LINK] <a href="{real_url}" style="color: #4096ff;">{real_url}</a><br/>'
                    f'<span style="color: #666; margin-left: 20px;">{real_title}</span>'
                )
                self._current_wiki_message.content_label.setText(html_content)
                self._current_wiki_message.content_label.setTextFormat(Qt.TextFormat.RichText)
                
                # Adjust component size to fit new content
                self._current_wiki_message.content_label.adjustSize()
                self._current_wiki_message.adjustSize()
                
                # Force redraw
                self._current_wiki_message.update()
                
                logger.info(f"✅ Wiki link in chat window updated to real URL and title")
                
                # Only clear reference when title contains meaningful content (avoid premature clearing causing subsequent updates)
                # Check if title is a temporary loading state
                temporary_titles = ["请稍候…", "Loading...", "Redirecting...", ""]
                if real_title and real_title not in temporary_titles:
                    # Delay clearing reference, allow possible subsequent updates
                    QTimer.singleShot(2000, lambda: setattr(self, '_current_wiki_message', None))
                    logger.info(f"📋 Delay clearing wiki message reference, title: '{real_title}'")
                else:
                    logger.info(f"📋 Keep wiki message reference, waiting for more complete title (current: '{real_title}')")
                    
            else:
                logger.warning("⚠️ No wiki message component found to update")
                
        except Exception as e:
            logger.error(f"❌ Update wiki link failed: {e}")
            
    def _on_streaming_chunk(self, chunk: str):
        """Handle streaming chunk from RAG"""
        print(f"🌊 [STREAMING-DEBUG] Received content chunk: '{chunk[:100]}...' (length: {len(chunk)})")
        print(f"🌊 [STREAMING-DEBUG] Waiting for RAG output status: {getattr(self, '_waiting_for_rag_output', 'undefined')}")
        print(f"🌊 [STREAMING-DEBUG] Current streaming message component: {hasattr(self, '_current_streaming_msg') and self._current_streaming_msg is not None}")
        
        # If waiting for RAG output and this is the first content chunk, create streaming message component
        if getattr(self, '_waiting_for_rag_output', False) and chunk.strip():
            logger.info("🔄 Received first RAG output chunk, create streaming message component")
            print(f"🔄 [STREAMING-DEBUG] Create streaming message component, content chunk: '{chunk.strip()[:50]}...'")
            
            # Hide status message
            if hasattr(self, '_current_status_widget') and self._current_status_widget:
                self.main_window.chat_view.hide_status()
                self._current_status_widget = None
                print(f"✅ [STREAMING-DEBUG] Status message hidden")
            
            # Create streaming message component
            self._setup_streaming_message()
            self._waiting_for_rag_output = False
            print(f"✅ [STREAMING-DEBUG] _waiting_for_rag_output set to False")
        
        # If there is streaming message component, add content chunk
        if hasattr(self, '_current_streaming_msg') and self._current_streaming_msg:
            print(f"📝 [STREAMING-DEBUG] Add content chunk to streaming message component")
            self._current_streaming_msg.append_chunk(chunk)
        else:
            print(f"⚠️ [STREAMING-DEBUG] No streaming message component, cannot add content chunk")
            # Try to create streaming message component immediately (fallback mechanism)
            if not getattr(self, '_waiting_for_rag_output', False):
                print(f"🚨 [STREAMING-DEBUG] Try to create streaming message component immediately (fallback mechanism)")
                self._setup_streaming_message()
                if hasattr(self, '_current_streaming_msg') and self._current_streaming_msg:
                    self._current_streaming_msg.append_chunk(chunk)
    
    def _update_rag_status(self):
        """Update RAG processing status message"""
        # If streaming output has started or not in waiting state, stop status update
        if (not getattr(self, '_waiting_for_rag_output', False) or 
            (hasattr(self, '_current_streaming_msg') and self._current_streaming_msg)):
            if hasattr(self, '_rag_status_timer'):
                self._rag_status_timer.stop()
            return
            
        # If there is no status component, do not update
        if not (hasattr(self, '_current_status_widget') and self._current_status_widget):
            return
            
        # In retrieval phase, keep displaying retrieval message, do not switch frequently
        # Only switch to AI processing message after long waiting
        if self._rag_status_step < 2:  # First 4.5 seconds (3 times * 1.5 seconds) keep displaying retrieval message
            current_message = TransitionMessages.DB_SEARCHING  # 📚 Retrieving related knowledge base...
        else:
            current_message = TransitionMessages.AI_SUMMARIZING  # 📝 AI summarizing in progress...
            
        # Only update when message actually changes, avoid setting same message repeatedly
        if not hasattr(self, '_last_status_message') or self._last_status_message != current_message:
            self.main_window.chat_view.update_status(current_message)
            self._last_status_message = current_message
            logger.info(f"🔄 RAG status updated: {current_message}")
        
        self._rag_status_step += 1
    
    def _on_guide_chunk(self, chunk: str):
        """Handle guide chunk from worker"""
        if hasattr(self, '_current_streaming_msg'):
            self._current_streaming_msg.append_chunk(chunk)
            
    def _on_streaming_finished(self):
        """Handle streaming output completed"""
        logger.info("✅ Streaming output completed")
        
        # Stop status update timer
        if hasattr(self, '_rag_status_timer'):
            self._rag_status_timer.stop()
            
        # Reset waiting state and status cache
        self._waiting_for_rag_output = False
        self._last_status_message = None
        
        # Notify streaming message component to quickly display remaining content
        if hasattr(self, '_current_streaming_msg') and self._current_streaming_msg:
            self._current_streaming_msg.mark_as_completed()
        
        # Reset UI state
        if self.main_window:
            self.main_window.set_generating_state(False)
            logger.info("✅ UI state reset to non-generating state")
        
    def _on_error(self, error_msg: str):
        """Handle error"""
        # Stop status update timer
        if hasattr(self, '_rag_status_timer'):
            self._rag_status_timer.stop()
            
        # Reset waiting state and status cache
        self._waiting_for_rag_output = False
        self._last_status_message = None
        
        # Reset UI generating state
        if self.main_window:
            self.main_window.set_generating_state(False)
            logger.info("❌ UI state reset to non-generating state when error occurred")
        
        # Hide status message
        if hasattr(self, '_current_status_widget') and self._current_status_widget:
            self.main_window.chat_view.hide_status()
            self._current_status_widget = None
            
        self.main_window.chat_view.add_message(
            MessageType.AI_RESPONSE,
            f"❌ {error_msg}"
        )
        
    def _on_wiki_result(self, url: str, title: str):
        """Handle wiki search result from RAG integration"""
        try:
            if url:
                # Update transition message
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.WIKI_FOUND)
                
                # Add wiki link message (initial display search URL)
                self._current_wiki_message = self.main_window.chat_view.add_message(
                    MessageType.WIKI_LINK,
                    title,
                    {"url": url}
                )
                
                # Show wiki page in the unified window (triggers JavaScript search for real URL)
                self.main_window.show_wiki_page(url, title)
            else:
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.ERROR_NOT_FOUND)
                    
        except Exception as e:
            logger.error(f"Wiki result handling error: {e}")
            self._on_error(str(e))
            
    def _reinitialize_rag_for_game(self, vector_game_name: str):
        """Reinitialize RAG engine for specific vector library (asynchronous, not blocking UI)"""
        try:
            logger.info(f"🚀 Start reinitializing RAG engine for vector library '{vector_game_name}' (asynchronous mode)")
            
            # Get API settings
            settings = self.settings_manager.get()
            api_settings = settings.get('api', {})
            gemini_api_key = api_settings.get('gemini_api_key', '')
            jina_api_key = api_settings.get('jina_api_key', '')
            
            # Check environment variables
            if not gemini_api_key:
                gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
            if not jina_api_key:
                jina_api_key = os.getenv('JINA_API_KEY')
            
            # Check if there are two API keys
            has_both_keys = bool(gemini_api_key and jina_api_key)
            
            if has_both_keys:
                llm_config = LLMConfig(
                    api_key=gemini_api_key,
                    model='gemini-2.5-flash-lite-preview-06-17'
                )
                
                # Update stored LLM configuration
                self._llm_config = llm_config
                
                # Asynchronously initialize RAG engine (do not wait for completion)
                self.rag_integration._init_rag_for_game(vector_game_name, llm_config, jina_api_key, wait_for_init=False)
                logger.info(f"🔄 RAG engine initialization started (asynchronous): {vector_game_name}")
                
                # Mark RAG engine as initializing
                self._rag_initializing = True
                self._target_vector_game = vector_game_name
            else:
                logger.warning(f"⚠️ API keys are incomplete, cannot initialize RAG engine (Gemini: {bool(gemini_api_key)}, Jina: {bool(jina_api_key)})")
                
        except Exception as e:
            logger.error(f"RAG engine reinitialization failed: {e}")
            self._rag_initializing = False
            
    def on_wiki_page_found(self, real_url: str, real_title: str = None):
        """Called when JavaScript in webview finds real wiki page"""
        logger.info(f"🌐 Received webview wiki page callback: {real_url}")
        self.rag_integration.on_wiki_found(real_url, real_title)
        
    def handle_wiki_page_found(self, url: str, title: str):
        """Override parent class method: handle WikiView signal when real wiki page is found"""
        logger.info(f"🔗 IntegratedAssistantController received WikiView signal: {title} -> {url}")
        
        # Filter out obvious temporary state titles, only process meaningful updates
        if title and title not in ["请稍候…", "Loading...", "Redirecting...", ""]:
            logger.info(f"✅ Accept wiki page update: {title}")
            # Directly call RAG integration method to handle wiki page discovery
            self.rag_integration.on_wiki_found(url, title)
        else:
            logger.info(f"⏳ Skip temporary state wiki page update: {title}")
            # For temporary state, still call, but do not trigger final update in chat window
            
    def expand_to_chat(self):
        """Override expand_to_chat method to connect stop signal"""
        # Call parent class expand_to_chat method
        super().expand_to_chat()
        
            # Connect stop generation signal
        if self.main_window and hasattr(self.main_window, 'stop_generation_requested'):
            self.main_window.stop_generation_requested.connect(self.stop_current_generation)
            logger.info("✅ Stop generation signal connected")
    
    def stop_current_generation(self):
        """Stop current generation process"""
        logger.info("🛑 Received stop generation request")
        
        try:
            # First restore UI state
            if self.main_window:
                try:
                    self.main_window.set_generating_state(False)
                    logger.info("🛑 UI state restored to non-generating state")
                except Exception as e:
                    logger.error(f"Error restoring UI state: {e}")
            
            # Stop current worker
            if self._current_worker and self._current_worker.isRunning():
                logger.info("🛑 Stop current QueryWorker")
                try:
                    self._current_worker.stop()
                    logger.info("🛑 QueryWorker stop request sent")
                    # Do not wait for worker to finish, let it finish asynchronously
                except Exception as e:
                    logger.error(f"Error stopping QueryWorker: {e}")
                    
        except Exception as e:
            logger.error(f"Error during generation: {e}")
            # Even if there is an error, try to restore UI state
            if self.main_window:
                try:
                    self.main_window.set_generating_state(False)
                except:
                    pass
    
    def switch_game(self, game_name: str):
        """Switch to a different game (game_name should be window title)"""
        # Stop current worker
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.stop()
            self._current_worker.wait()
            
        # First map window title to vector library name
        from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name
        vector_game_name = map_window_title_to_game_name(game_name)
        
        if vector_game_name:
            logger.info(f"🔄 Manually switch game: '{game_name}' -> vector library: {vector_game_name}")
            # Reinitialize with mapped vector library name
            self._reinitialize_rag_for_game(vector_game_name)
        else:
            logger.warning(f"⚠️ Game '{game_name}' not supported, cannot switch RAG engine")