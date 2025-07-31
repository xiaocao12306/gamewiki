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

from src.game_wiki_tooltip.windows import AssistantController
from src.game_wiki_tooltip.unified_window import MessageType, TransitionMessages
from src.game_wiki_tooltip.config import SettingsManager, LLMConfig
from src.game_wiki_tooltip.utils import get_foreground_title
from src.game_wiki_tooltip.i18n import t, get_current_language
from src.game_wiki_tooltip.smart_interaction_manager import SmartInteractionManager, InteractionMode

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
        # Set low priority to avoid affecting UI responsiveness
        try:
            import os
            if hasattr(os, 'nice'):
                os.nice(10)  # Unix/Linux
            else:
                # Windows: set thread priority
                import ctypes
                import sys
                if sys.platform == 'win32':
                    thread_handle = ctypes.windll.kernel32.GetCurrentThread()
                    ctypes.windll.kernel32.SetThreadPriority(thread_handle, -1)  # THREAD_PRIORITY_BELOW_NORMAL
        except Exception as e:
            logger.warning(f"Failed to set thread priority: {e}")
        
        success = _lazy_load_ai_modules()
        self.load_completed.emit(success)

def _lazy_load_ai_modules():
    """Lazy load AI modules, only import when first used"""
    global process_query_unified, get_default_config, EnhancedRagQuery, _ai_modules_loaded, _ai_modules_loading
    
    with _ai_load_lock:
        if _ai_modules_loaded:
            logger.info("✅ AI modules already loaded (probably during splash screen)")
            return True
            
        if _ai_modules_loading:
            # Another thread is loading, wait for completion
            logger.info("⏳ AI module is being loaded by another thread, waiting...")
            while _ai_modules_loading and not _ai_modules_loaded:
                time.sleep(0.1)
            return _ai_modules_loaded
            
        _ai_modules_loading = True
        
    try:
        logger.info("🔄 Starting AI module loading (fallback - should have been loaded during splash)...")
        start_time = time.time()
        
        # Check if modules were already loaded by splash screen
        if process_query_unified and get_default_config and EnhancedRagQuery:
            logger.info("✅ AI modules were already loaded by splash screen")
            with _ai_load_lock:
                _ai_modules_loaded = True
                _ai_modules_loading = False
            return True
        
        # Fallback: load modules if not already loaded
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
        logger.info(f"✅ AI module loading completed (fallback), time taken: {elapsed:.2f} seconds")
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
    
    def __init__(self, rag_integration, query: str, game_context: str = None, search_mode: str = "auto", parent=None):
        super().__init__(parent)
        self.rag_integration = rag_integration
        self.query = query
        self.game_context = game_context
        self.search_mode = search_mode
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
            
            # Wait for AI modules to load if needed (with timeout)
            if not await self._wait_for_ai_modules():
                self.error_occurred.emit("AI modules are still loading. Please try again in a moment.")
                return
                
            # Use unified query processor for intent detection and query optimization
            intent = await self.rag_integration.process_query_async(
                self.query, 
                game_context=self.game_context,
                search_mode=self.search_mode
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
    
    async def _wait_for_ai_modules(self) -> bool:
        """Wait for AI modules to load with timeout"""
        max_wait = 5.0  # Maximum 5 seconds
        check_interval = 0.1
        elapsed = 0.0
        
        while elapsed < max_wait:
            # Check if modules are loaded
            if _ai_modules_loaded:
                return True
            
            # Check if stop requested
            if self._stop_requested:
                return False
                
            # Wait a bit
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
        # Timeout
        return _ai_modules_loaded
            
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
        
        # RAG initialization state tracking
        self._rag_initializing = False  # Flag to prevent duplicate initializations
        self._rag_init_game = None      # Track which game is being initialized
        self._current_rag_game = None   # Track current initialized game
        
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
            
        # Just log that we'll initialize on demand - don't actually initialize anything
        logger.info("📌 AI components will be initialized on first use (lazy loading)")
        
    def _ensure_ai_components_loaded(self):
        """Ensure AI components are loaded (called before actual use)"""
        if self.limited_mode:
            return False
            
        # If AI modules are loading, wait but don't block UI
        if _ai_modules_loading:
            logger.info("⏳ AI modules are loading in background...")
            # For UI operations, return immediately
            # The actual query processing will handle waiting
            if not _ai_modules_loaded:
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
            # No longer need separate Jina API key, use Gemini API key for embeddings
            
            # Check environment variables
            if not gemini_api_key:
                gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
            # Gemini API key is used for both LLM and embeddings
            
            # Check if API key is available
            has_api_key = bool(gemini_api_key)
            
            if has_api_key:
                logger.info("✅ Complete API key configuration detected, initializing AI components")
                
                llm_config = LLMConfig(
                    api_key=gemini_api_key,
                    model='gemini-2.5-flash-lite'
                )
                
                # Store LLM configuration for other methods
                self._llm_config = llm_config
                
                # Initialize query processor - remove, we will directly use process_query_unified function
                # if process_query_unified:
                #     self.query_processor = process_query_unified(llm_config=llm_config)
                
                # Don't read game window at startup - wait for user interaction
                logger.info("✅ AI components configuration ready, RAG will be initialized on demand")
                self._last_game_window = None
                self._last_vector_game_name = None
            else:
                missing_keys = []
                if not gemini_api_key:
                    missing_keys.append("Gemini API Key")
                if not has_api_key:
                    missing_keys.append("Jina API Key")
                
                logger.warning(f"❌ Missing required API keys: {', '.join(missing_keys)}")
                logger.warning("Cannot initialize AI components, need to configure both Gemini API Key and Jina API Key")
                return False
                    
        except Exception as e:
            logger.error(f"Failed to initialize AI components: {e}")
            return False
            
        self._ai_initialized = True
        return True
            
    def _init_rag_for_game(self, game_name: str, llm_config: LLMConfig, google_api_key: str, wait_for_init: bool = False):
        """Initialize RAG engine for specific game"""
        try:
            # Check if already initializing or initialized for this game
            if self._rag_initializing and self._rag_init_game == game_name:
                logger.info(f"⚠️ RAG initialization already in progress for game '{game_name}', skipping duplicate")
                return
                
            if self._current_rag_game == game_name and self.rag_engine:
                logger.info(f"✓ RAG engine already initialized for game '{game_name}', no need to reinitialize")
                return
            
            # Mark as initializing
            self._rag_initializing = True
            self._rag_init_game = game_name
            
            # Ensure AI components are loaded first
            if not _ai_modules_loaded:
                logger.info("AI modules not yet loaded, ensuring they are loaded first...")
                if not self._ensure_ai_components_loaded():
                    logger.error("Failed to load AI components, cannot initialize RAG")
                    self._rag_initializing = False
                    self._rag_init_game = None
                    return
            
            if not (get_default_config and EnhancedRagQuery):
                logger.warning("RAG components not available after loading attempt")
                self._rag_initializing = False
                self._rag_init_game = None
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
                google_api_key=google_api_key,  # Pass Google API key
                enable_query_rewrite=False,  # Disable query rewrite, avoid duplicate LLM calls
                enable_summarization=rag_config.summarization.enabled,
                summarization_config=rag_config.summarization.to_dict(),
                enable_intent_reranking=rag_config.intent_reranking.enabled,
                reranking_config=rag_config.intent_reranking.to_dict()
            )
            
            # Initialize the engine in thread
            def init_rag():
                # Set low priority to avoid affecting UI responsiveness
                try:
                    import os
                    if hasattr(os, 'nice'):
                        os.nice(10)  # Unix/Linux
                    else:
                        # Windows: set thread priority
                        import ctypes
                        import sys
                        if sys.platform == 'win32':
                            thread_handle = ctypes.windll.kernel32.GetCurrentThread()
                            ctypes.windll.kernel32.SetThreadPriority(thread_handle, -2)  # THREAD_PRIORITY_LOWEST
                except Exception as e:
                    logger.warning(f"Failed to set thread priority: {e}")
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    logger.info(f"🚀 Starting async RAG engine initialization (game: {game_name})")
                    loop.run_until_complete(self.rag_engine.initialize(game_name))
                    logger.info(f"✅ RAG engine initialization completed (game: {game_name})")
                    self._rag_init_complete = True
                    self._current_rag_game = game_name  # Record current RAG engine game
                    # Clear initialization flags on success
                    self._rag_initializing = False
                    self._rag_init_game = None
                    # Clear error information
                    if hasattr(self, '_rag_init_error'):
                        delattr(self, '_rag_init_error')
                except Exception as e:
                    logger.error(f"❌ RAG engine initialization failed (game: {game_name}): {e}")
                    self.rag_engine = None
                    self._rag_init_complete = False
                    self._rag_init_error = str(e)  # Record initialization error
                    self._current_rag_game = None
                    # Clear initialization flags on failure
                    self._rag_initializing = False
                    self._rag_init_game = None
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
            # Ensure initialization flags are cleared on any error
            self._rag_initializing = False
            self._rag_init_game = None
            
    async def process_query_async(self, query: str, game_context: str = None, search_mode: str = "auto") -> QueryIntent:
        """Process query using unified query processor for intent detection"""
        logger.info(f"Start unified query processing: '{query}' (game context: {game_context}, search mode: {search_mode}, limited mode: {self.limited_mode})")
        
        # Handle manual search mode selection
        if search_mode == "wiki":
            logger.info("📚 Manual wiki search mode selected")
            return QueryIntent(
                intent_type='wiki',
                confidence=1.0,
                rewritten_query=query,
                translated_query=query
            )
        elif search_mode == "ai":
            logger.info("🤖 Manual AI search mode selected")
            return QueryIntent(
                intent_type='guide',
                confidence=1.0,
                rewritten_query=query,
                translated_query=query
            )
        
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
                    model='gemini-2.5-flash-lite'
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
                    # No longer need separate Jina API key, use Gemini API key for embeddings
                    
                    # Check environment variables
                    if not gemini_api_key:
                        gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
                    
                    # Check if API key is available
                    has_api_key = bool(gemini_api_key)
                    
                    if has_api_key:
                        llm_config = LLMConfig(
                            api_key=gemini_api_key,
                            model='gemini-2.5-flash-lite'
                        )
                        
                        # Check if RAG is already initializing
                        if self._rag_initializing and self._rag_init_game == vector_game_name:
                            logger.info(f"RAG already initializing for {vector_game_name}, showing status and queueing query")
                            # Show initialization status
                            self.streaming_chunk_ready.emit("🚀 AI guide system is initializing, please wait a moment...")
                            
                            # Queue the query to be processed after initialization
                            self._pending_query = {
                                'query': query,
                                'game_context': game_context,
                                'original_query': original_query,
                                'skip_query_processing': skip_query_processing,
                                'unified_query_result': unified_query_result,
                                'stop_flag': stop_flag
                            }
                            
                            # Start checking initialization status
                            if not hasattr(self, '_init_check_timer') or not self._init_check_timer:
                                from PyQt6.QtCore import QTimer
                                self._init_check_timer = QTimer()
                                self._init_check_timer.timeout.connect(self._check_rag_init_and_process_query)
                                self._init_check_timer.start(100)  # Check every 100ms
                            return
                        
                        # Use asynchronous initialization to avoid blocking UI
                        self._init_rag_for_game(vector_game_name, llm_config, gemini_api_key, wait_for_init=False)
                        
                        # Show initialization status
                        self.streaming_chunk_ready.emit("🚀 AI guide system is initializing for the first time, please wait...")
                        
                        # Queue the query
                        self._pending_query = {
                            'query': query,
                            'game_context': game_context,
                            'original_query': original_query,
                            'skip_query_processing': skip_query_processing,
                            'unified_query_result': unified_query_result,
                            'stop_flag': stop_flag
                        }
                        
                        # Start checking initialization status
                        if not hasattr(self, '_init_check_timer') or not self._init_check_timer:
                            from PyQt6.QtCore import QTimer
                            self._init_check_timer = QTimer()
                            self._init_check_timer.timeout.connect(self._check_rag_init_and_process_query)
                            self._init_check_timer.start(100)  # Check every 100ms
                        
                        return
                    else:
                        missing_keys = []
                        if not gemini_api_key:
                            missing_keys.append("Gemini API Key")
                        if not has_api_key:
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
                error_str = str(e)
                
                # Check for rate limit errors
                if "API_RATE_LIMIT" in error_str or "quota" in error_str.lower() or "rate limit" in error_str.lower() or "429" in error_str:
                    logger.warning("⏱️ API rate limit detected")
                    if current_lang == 'zh':
                        error_msg = (
                            "⏱️ **API 使用限制**\n\n"
                            "您已达到 Google Gemini API 的使用限制。免费账户限制：\n"
                            "• 每分钟最多 15 次请求\n"
                            "• 每天最多 1500 次请求\n\n"
                            "请稍等片刻后再试，或考虑升级到付费账户以获得更高的配额。"
                        )
                    else:
                        error_msg = (
                            "⏱️ **API Rate Limit**\n\n"
                            "You've reached the Google Gemini API usage limit. Free tier limits:\n"
                            "• Maximum 15 requests per minute\n"
                            "• Maximum 1500 requests per day\n\n"
                            "Please wait a moment and try again, or consider upgrading to a paid account for higher quotas."
                        )
                    self.streaming_chunk_ready.emit(error_msg)
                    return
                elif isinstance(e, VectorStoreUnavailableError):
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
        
        # Initialize smart interaction manager (pass None as parent, but pass self as controller reference)
        self.smart_interaction = SmartInteractionManager(parent=None, controller=self)
        self._setup_smart_interaction()
        
        # Register as global instance
        IntegratedAssistantController._global_instance = self
        logger.info(f"🌐 Registered as global assistant controller instance (limited_mode={limited_mode})")
        
        # If in limited mode, display prompt information
        if limited_mode:
            logger.info("🚨 Running in limited mode: only Wiki search functionality is supported")
        else:
            logger.info("✅ Running in full mode: supports Wiki search and AI guide functionality")
            # Don't preload AI modules immediately, wait for first window display
            self._ai_preload_scheduled = False
            
            # Schedule AI preload immediately after initialization (with a small delay to avoid blocking)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self._schedule_ai_preload_on_startup)
        
    def _schedule_ai_preload_on_startup(self):
        """Schedule AI preload on startup if not already scheduled"""
        if not hasattr(self, '_ai_preload_scheduled') or not self._ai_preload_scheduled:
            self._ai_preload_scheduled = True
            logger.info("🚀 Scheduling AI module preload on startup")
            self._schedule_ai_preload()
    
    def _schedule_ai_preload(self):
        """Preload AI modules when idle"""
        # Check if already loading
        if hasattr(self, '_ai_loader') and self._ai_loader:
            logger.info("⏭️ AI modules already loading, skipping duplicate request")
            return
            
        # First ensure basic modules are preloaded via preloader
        try:
            from src.game_wiki_tooltip.preloader import ensure_preloaded
            ensure_preloaded(timeout=0.1)  # Quick check, don't block
        except:
            pass
            
        logger.info("🚀 Starting AI module background loading immediately...")
        
        # Create and start loader thread with low priority
        self._ai_loader = AIModuleLoader()
        self._ai_loader.load_completed.connect(self._on_ai_modules_loaded)
        self._ai_loader.start()
        
        logger.info("📋 AI modules loading started in background thread")
        
    def _on_ai_modules_loaded(self, success: bool):
        """Callback when AI modules are loaded"""
        if success:
            logger.info("✅ AI module background loading completed")
            # Record loading success status
            self._ai_modules_ready = True
            
            # Now initialize RAG if we have cached game window
            if hasattr(self.rag_integration, '_last_vector_game_name') and self.rag_integration._last_vector_game_name:
                try:
                    logger.info(f"🎮 Initializing RAG for cached game: {self.rag_integration._last_vector_game_name}")
                    self.rag_integration._init_rag_for_game(
                        self.rag_integration._last_vector_game_name,
                        self.rag_integration._llm_config,
                        self.rag_integration._llm_config.api_key if hasattr(self.rag_integration, '_llm_config') else None
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to initialize RAG for cached game: {e}")
        else:
            logger.warning("⚠️ AI module background loading failed")
            
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
        
        # 排除应用程序自身的窗口
        title_lower = game_window_title.lower()
        app_window_keywords = [
            'gamewiki assistant',
            'gamewiki',
            'game wiki assistant',
            'game wiki'
        ]
        
        # 如果是应用程序自身的窗口，不处理
        if any(app_keyword in title_lower for app_keyword in app_window_keywords):
            logger.debug(f"🚫 Ignoring self window: '{game_window_title}'")
            return
        
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
        
    def _setup_smart_interaction(self):
        """Setup smart interaction manager"""
        # Connect interaction mode change signal
        self.smart_interaction.interaction_mode_changed.connect(
            self._on_interaction_mode_changed
        )
        
        # Connect mouse state change signal
        self.smart_interaction.mouse_state_changed.connect(
            self._on_mouse_state_changed
        )
        
        # 移除窗口状态变化的信号连接 - 改为热键触发时按需检测
    
    def handle_query(self, query: str, mode: str = "auto"):
        """Override to handle query with RAG integration"""
        # Store search mode
        self._search_mode = mode
        
        # Add user message
        self.main_window.chat_view.add_message(
            MessageType.USER_QUERY,
            query
        )
        
        # Check if user requested web search
        query_lower = query.lower()
        web_search_keywords = [
            'search web', 'web search', 'search online', 'online search',
            '搜索网络', '网络搜索', '在线搜索', '搜索在线'
        ]
        
        if getattr(self, '_web_search_suggested', False) and any(kw in query_lower for kw in web_search_keywords):
            logger.info("🔍 User requested web search")
            self._web_search_suggested = False
            self._perform_web_search()
            return
        
        # Check RAG engine initialization status (check the RAGIntegration's status)
        if hasattr(self.rag_integration, '_rag_initializing') and self.rag_integration._rag_initializing:
            # RAG engine is initializing, display waiting status
            from src.game_wiki_tooltip.i18n import t
            logger.info(f"🔄 RAG engine is initializing for game '{self.rag_integration._rag_init_game}', display waiting status")
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
        
        # Check if initialization is complete (check if _rag_initializing is False)
        if not self.rag_integration._rag_initializing:
            # Initialization completed (either success or failure)
            if self.rag_integration.rag_engine and self.rag_integration._current_rag_game:
                logger.info("✅ RAG engine initialization completed, start processing query")
            else:
                logger.warning("⚠️ RAG engine initialization finished but engine not available")
            
            self.main_window.chat_view.hide_status()
            
            # Process waiting query
            if hasattr(self, '_pending_query'):
                self._process_query_immediately(self._pending_query)
                delattr(self, '_pending_query')
        elif hasattr(self.rag_integration, '_rag_init_error'):
            # Initialization failed
            logger.error(f"❌ RAG engine initialization failed: {self.rag_integration._rag_init_error}")
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
        # Save query for potential web search
        self._last_user_query = query
        self._last_game_context = getattr(self, 'current_game_window', None)
        
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
            game_context=self.current_game_window,
            search_mode=getattr(self, '_search_mode', 'auto')
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
            # Save rewritten query for potential web search
            if intent.rewritten_query:
                self._last_rewritten_query = intent.rewritten_query
            
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
        
        # Check if knowledge was insufficient and add web search option
        if getattr(self, '_knowledge_insufficient', False):
            self._add_web_search_option()
            self._knowledge_insufficient = False
        
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
        
    def _check_rag_init_and_process_query(self):
        """Check if RAG initialization is complete and process pending query"""
        # Check if RAG is still initializing
        if self.rag_integration._rag_initializing:
            # Still initializing, continue waiting
            logger.debug("RAG still initializing, waiting...")
            return
            
        # Stop the timer
        if hasattr(self, '_init_check_timer') and self._init_check_timer:
            self._init_check_timer.stop()
            self._init_check_timer = None
            
        # Check if we have a pending query
        if not hasattr(self, '_pending_query') or not self._pending_query:
            logger.warning("No pending query found after RAG initialization")
            return
            
        # Extract pending query details
        pending = self._pending_query
        self._pending_query = None  # Clear pending query
        
        # Check if RAG engine is now available
        if self.rag_integration.rag_engine:
            logger.info("✅ RAG initialization complete, processing pending query")
            # Clear initialization message
            if self.main_window:
                self.main_window.chat_view.hide_status()
            
            # Process the query using asyncio
            import asyncio
            task = asyncio.create_task(
                self.rag_integration.generate_guide_async(
                    query=pending['query'],
                    game_context=pending['game_context'],
                    original_query=pending['original_query'],
                    skip_query_processing=pending['skip_query_processing'],
                    unified_query_result=pending['unified_query_result'],
                    stop_flag=pending.get('stop_flag')
                )
            )
            # Store task reference for potential cancellation
            self._current_task = task
        else:
            logger.error("RAG initialization failed, unable to process query")
            self.rag_integration.error_occurred.emit(
                "Failed to initialize AI guide system. Please check your API keys and try again."
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
            
            # Check if RAG is already initializing or initialized for this game
            if self.rag_integration._rag_initializing:
                logger.info(f"⚠️ RAG already initializing for game '{self.rag_integration._rag_init_game}', skipping")
                return
                
            if self.rag_integration._current_rag_game == vector_game_name and self.rag_integration.rag_engine:
                logger.info(f"✓ RAG already initialized for game '{vector_game_name}', no need to reinitialize")
                return
            
            # Ensure AI modules are loaded before attempting RAG initialization
            if not self.rag_integration._ensure_ai_components_loaded():
                logger.warning("AI components not yet loaded, deferring RAG initialization")
                # Schedule another attempt after a delay
                QTimer.singleShot(1000, lambda: self._reinitialize_rag_for_game(vector_game_name))
                return
            
            # Get API settings
            settings = self.settings_manager.get()
            api_settings = settings.get('api', {})
            gemini_api_key = api_settings.get('gemini_api_key', '')
            # No longer need separate Jina API key, use Gemini API key for embeddings
            
            # Check environment variables
            if not gemini_api_key:
                gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
            # Gemini API key is used for both LLM and embeddings
            
            # Check if API key is available
            has_api_key = bool(gemini_api_key)
            
            if has_api_key:
                llm_config = LLMConfig(
                    api_key=gemini_api_key,
                    model='gemini-2.5-flash-lite'
                )
                
                # Update stored LLM configuration
                self._llm_config = llm_config
                
                # Asynchronously initialize RAG engine (do not wait for completion)
                self.rag_integration._init_rag_for_game(vector_game_name, llm_config, gemini_api_key, wait_for_init=False)
                logger.info(f"🔄 RAG engine initialization started (asynchronous): {vector_game_name}")
            else:
                logger.warning(f"⚠️ API key is missing, cannot initialize RAG engine (Gemini: {bool(gemini_api_key)})")
                
        except Exception as e:
            logger.error(f"RAG engine reinitialization failed: {e}")
            
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
            
        # Schedule AI preload after first window display (only if not already scheduled)
        if not self.limited_mode and (not hasattr(self, '_ai_preload_scheduled') or not self._ai_preload_scheduled):
            # Check if AI modules are already loaded
            if _ai_modules_loaded:
                logger.info("✅ AI modules already loaded, skipping preload schedule")
            else:
                self._ai_preload_scheduled = True
                # Start AI loading immediately but with low priority
                QTimer.singleShot(0, self._schedule_ai_preload)
                logger.info("📅 AI modules loading started with low priority from expand_to_chat")
    
    def _add_web_search_option(self):
        """Add web search option when knowledge is insufficient"""
        logger.info("🔍 Adding web search option for insufficient knowledge")
        
        current_lang = get_current_language()
        
        # Create web search prompt message
        if current_lang == 'zh':
            message = "\n\n💡 知识库中的信息可能不够全面。您可以点击下方按钮进行网络搜索以获取更详细的信息。"
            button_text = "🔍 搜索网络"
        else:
            message = "\n\n💡 The knowledge base might not have sufficient information. You can click the button below to search the web for more details."
            button_text = "🔍 Search Web"
        
        # Add message to chat
        if self.main_window and hasattr(self.main_window, 'chat_view'):
            self.main_window.chat_view.add_message(MessageType.ASSISTANT, message)
            
            # Add interactive button
            self.main_window.chat_view.add_interactive_button(
                button_text,
                self._perform_web_search
            )
    
    def _perform_web_search(self):
        """Perform web search using Google Search grounding"""
        logger.info("🌐 Starting web search with Google grounding")
        
        # Get the last user query
        if not hasattr(self, '_last_user_query'):
            logger.error("No user query available for web search")
            return
        
        # Start web search in a new worker
        self._start_web_search_worker(
            self._last_user_query,
            getattr(self, '_last_rewritten_query', None),
            getattr(self, '_last_game_context', None)
        )
    
    def _start_web_search_worker(self, query: str, rewritten_query: str = None, game_context: str = None):
        """Start web search worker"""
        from PyQt6.QtCore import QThread
        
        # Create web search worker
        class WebSearchWorker(QThread):
            chunk_ready = pyqtSignal(str)
            finished_signal = pyqtSignal()
            error_signal = pyqtSignal(str)
            
            def __init__(self, query, rewritten_query, game_context, api_key):
                super().__init__()
                self.query = query
                self.rewritten_query = rewritten_query
                self.game_context = game_context
                self.api_key = api_key
                
            def run(self):
                try:
                    # Import and use Google Search grounding
                    from src.game_wiki_tooltip.ai.google_search_grounding import create_google_search_grounding
                    
                    grounding = create_google_search_grounding(api_key=self.api_key)
                    
                    # Run async in sync context
                    import asyncio
                    
                    async def search_and_stream():
                        async for chunk in grounding.search_and_generate_stream(
                            self.query,
                            self.rewritten_query,
                            self.game_context
                        ):
                            self.chunk_ready.emit(chunk)
                    
                    # Run the async function
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(search_and_stream())
                    
                    self.finished_signal.emit()
                    
                except Exception as e:
                    logger.error(f"Web search error: {e}")
                    self.error_signal.emit(str(e))
        
        # Get API key
        settings = self.settings_manager.get()
        api_settings = settings.get('api', {})
        api_key = api_settings.get('gemini_api_key', '') or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        
        if not api_key:
            logger.error("No API key available for web search")
            return
        
        # Create and start worker
        self._web_search_worker = WebSearchWorker(query, rewritten_query, game_context, api_key)
        
        # Setup streaming message for web search
        current_lang = get_current_language()
        if current_lang == 'zh':
            self.main_window.chat_view.add_message("🌐 正在搜索网络信息...\n\n", MessageType.ASSISTANT)
        else:
            self.main_window.chat_view.add_message("🌐 Searching the web...\n\n", MessageType.ASSISTANT)
        
        self._setup_streaming_message()
        
        # Connect signals
        self._web_search_worker.chunk_ready.connect(self._on_streaming_chunk)
        self._web_search_worker.finished_signal.connect(self._on_streaming_finished)
        self._web_search_worker.error_signal.connect(self._on_error)
        
        # Start worker
        self._web_search_worker.start()
        self.main_window.set_generating_state(True)
    
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
    
    # Smart interaction manager signal handling methods
    def _on_interaction_mode_changed(self, mode: InteractionMode):
        """Handle interaction mode changes"""
        logger.info(f"🎮 Interaction mode changed: {mode.value}")
        
        # Adjust window mouse passthrough state based on interaction mode
        if hasattr(self, 'main_window') and self.main_window:
            should_passthrough = self.smart_interaction.should_enable_mouse_passthrough()
            self.smart_interaction.apply_mouse_passthrough(self.main_window, should_passthrough)
            
            # Show status message for different modes
            if mode == InteractionMode.GAME_HIDDEN:
                logger.info("🎮 Game mouse hidden mode: enabled mouse passthrough to prevent accidental clicks")
            elif mode == InteractionMode.GAME_VISIBLE:
                logger.info("🎮 Game mouse visible mode: normal interaction")
            else:
                logger.info("🖥️ Normal mode: normal interaction")
        
    def _on_mouse_state_changed(self, mouse_state):
        """Handle mouse state changes"""
        logger.debug(f"🖱️ Mouse state changed: visible={mouse_state.is_visible}, position={mouse_state.position}")
    
    def handle_smart_hotkey(self, current_visible: bool) -> bool:
        """
        Handle hotkey events using smart interaction manager
        
        Args:
            current_visible: Whether the chat window (main_window) is visible
            
        Returns:
            Whether the hotkey event was handled
        """
        # Debug: Log smart hotkey processing start
        logger.info(f"🎯 [DEBUG] Smart hotkey processing started")
        
        # 检测当前游戏窗口但先不设置，避免阻塞窗口显示
        current_game_window = self.smart_interaction.get_current_game_window()
        logger.info(f"🔍 [DEBUG] Detected current game window: '{current_game_window}'")
        
        # 强制更新交互模式，确保正确识别当前游戏状态
        mouse_state = self.smart_interaction.get_mouse_state()
        window_state = self.smart_interaction.get_window_state()
        if mouse_state and window_state:
            new_mode = self.smart_interaction._calculate_interaction_mode(mouse_state, window_state)
            if new_mode != self.smart_interaction.current_mode:
                old_mode = self.smart_interaction.current_mode
                self.smart_interaction.current_mode = new_mode
                logger.info(f"🎮 Interaction mode updated for hotkey: {old_mode.value} -> {new_mode.value}")
        
        # 只检查聊天窗口的可见性，而不是所有窗口
        chat_visible = (self.main_window and self.main_window.isVisible())
        action = self.smart_interaction.handle_hotkey_press(chat_visible)
        logger.info(f"🔥 Smart hotkey handling result: {action}")
        
        if action == 'show_chat':
            # 先显示聊天窗口
            self.show_chat_window()
            logger.info("💬 Show chat window requested - executed before game window setting")
            
            # 然后异步设置游戏窗口（避免阻塞UI）
            if current_game_window:
                logger.info(f"🎮 Setting current game window after chat display: '{current_game_window}'")
                # 使用QTimer异步设置游戏窗口，避免阻塞UI
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(50, lambda: self._delayed_set_game_window(current_game_window))
                
            return True
        elif action == 'hide_chat':
            self.hide_chat_window()
            # Clear the flag after handling to allow future updates
            self._game_window_already_set = False
            return True
        elif action == 'show_mouse':
            self.show_mouse_for_interaction()
            # Clear the flag after handling to allow future updates
            self._game_window_already_set = False
            return True
        elif action == 'ignore':
            logger.info("🎮 Ignoring hotkey event")
            # Clear the flag after handling to allow future updates
            self._game_window_already_set = False
            return True
        
        # Clear the flag if no action was taken
        self._game_window_already_set = False
        return False
    
    def _delayed_set_game_window(self, game_window_title: str):
        """延迟设置游戏窗口，避免阻塞UI"""
        try:
            logger.info(f"🎮 [DEBUG] About to set current game window (delayed): '{game_window_title}'")
            logger.info(f"📋 [DEBUG] Main window exists: {self.main_window is not None}")
            if self.main_window:
                logger.info(f"📋 [DEBUG] Main window task buttons count before: {len(getattr(self.main_window, 'game_task_buttons', {}))}")
            
            # 设置游戏窗口并确保task flow按钮正确显示
            self.set_current_game_window(game_window_title)
            
            # Debug: Log after setting game window
            if self.main_window:
                logger.info(f"📋 [DEBUG] Main window task buttons count after: {len(getattr(self.main_window, 'game_task_buttons', {}))}")
                # Log visibility of each button
                for game_name, button in getattr(self.main_window, 'game_task_buttons', {}).items():
                    if button:
                        is_visible = button.isVisible()
                        logger.info(f"    📋 [DEBUG] {game_name} task button visible: {is_visible}")
            
            # 标记游戏窗口已经设置
            self._game_window_already_set = True
            logger.info(f"🏁 [DEBUG] Game window already set flag: True (delayed)")
            
        except Exception as e:
            logger.error(f"Error in delayed game window setting: {e}")
            import traceback
            traceback.print_exc()
    
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
    
    def show_chat_window(self):
        """显示聊天窗口，隐藏悬浮窗"""
        logger.info("💬 Show chat window requested")
        
        
        # 显示聊天窗口
        if not self.main_window:
            self.expand_to_chat()  # 创建并显示聊天窗口
        else:
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
            
            # 决定显示哪种形态
            if not self.main_window.has_user_input:
                # 如果用户没有输入过，显示CHAT_ONLY形态
                logger.info("🎯 Switching to CHAT_ONLY mode (no user input yet)")
                self.main_window.switch_to_chat_only()
                
        logger.info("💬 Chat window shown")
    
    def hide_chat_window(self):
        """隐藏聊天窗口，根据用户设置决定是否显示悬浮窗"""
        logger.info("💬 Hide chat window requested")
        
        # 隐藏聊天窗口
        if self.main_window:
            self.main_window.hide()
            logger.info("💬 Chat window hidden")
        
        # 检查用户设置的悬浮窗隐藏状态
        if hasattr(self, '_is_manually_hidden') and self._is_manually_hidden:
            logger.info("🔹 Mini window stays hidden (user setting)")
        else:
            # 显示聊天窗口
            self.expand_to_chat()
            logger.info("🔹 Chat window shown")
    
    def show_mouse_for_interaction(self):
        """显示鼠标以便与聊天窗口互动"""
        logger.info("🖱️ Show mouse for interaction requested")
        try:
            # 调用Windows API显示鼠标
            from .utils import show_cursor_until_visible
            show_cursor_until_visible()
            logger.info("🖱️ Mouse cursor shown")
        except Exception as e:
            logger.error(f"Failed to show mouse cursor: {e}")
    
    def show_assistant(self):
        """显示助手窗口"""
        logger.info("🔍 Show assistant requested")
        self.expand_to_chat()
    
    def hide_assistant(self):
        """隐藏助手窗口"""
        logger.info("🚫 Hide assistant requested")
        if hasattr(self, '_is_manually_hidden'):
            self._is_manually_hidden = True
        
        # 隐藏所有窗口
        if self.main_window:
            self.main_window.hide()
    
    def toggle_assistant(self):
        """切换助手窗口显示状态"""
        logger.info("🔄 Toggle assistant requested")
        
        # 使用统一的可见性检查方法
        if self.is_assistant_visible():
            self.hide_assistant()
        else:
            self.show_assistant()

    def is_assistant_visible(self) -> bool:
        """检查助手窗口是否可见（检查所有窗口）"""
        if self.main_window and self.main_window.isVisible():
            return True
        return False