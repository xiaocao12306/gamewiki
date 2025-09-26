"""
Integration layer between the new unified UI and existing RAG/Wiki systems.
"""

import asyncio
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import os

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread, Qt, QPoint

from src.game_wiki_tooltip.window_component import AssistantController, TransitionMessages, MessageType, WindowState
from src.game_wiki_tooltip.core.backend_client import BackendClient
from src.game_wiki_tooltip.core.config import SettingsManager
from src.game_wiki_tooltip.core import events as analytics_events
from src.game_wiki_tooltip.ai.rag_config import LLMSettings
from src.game_wiki_tooltip.ai.unified_query_processor import UnifiedQueryResult
from src.game_wiki_tooltip.core.utils import get_foreground_title
from src.game_wiki_tooltip.core.smart_interaction_manager import SmartInteractionManager, InteractionMode

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
                # For unsupported window_component, emit error signal directly
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
                # Check for specific errors and provide user-friendly messages
                if "_check_rag_init_and_process_query" in str(e):
                    # This error occurs when vector store is not found
                    self.error_occurred.emit(self.rag_integration._get_localized_message("game_not_supported"))
                else:
                    self.error_occurred.emit(str(e))
    
    async def _wait_for_ai_modules(self) -> bool:
        """Wait for AI modules to load with timeout"""
        # In limited mode, skip AI module check
        if self.rag_integration.limited_mode:
            return True  # Skip AI module loading in limited mode
            
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
    error_occurred = pyqtSignal(str)
    
    def __init__(
        self,
        settings_manager: SettingsManager,
        backend_client: BackendClient,
        analytics_mgr=None,
        limited_mode: bool = False,
    ):
        super().__init__()
        self.settings_manager = settings_manager
        self.backend_client = backend_client
        self.analytics_mgr = analytics_mgr
        self.limited_mode = limited_mode
        self.rag_engine = None
        self.query_processor = None
        self._pending_wiki_update = None  # Store wiki link information to be updated
        self._llm_config = None  # Store configured LLM configuration
        self._lightweight_rag_cache = {}
        
        # RAG initialization state tracking
        self._rag_initializing = False  # Flag to prevent duplicate initializations
        self._rag_init_game = None      # Track which game is being initialized
        self._current_rag_game = None   # Track current initialized game
        
        # Initialize game configuration manager

        # Select game configuration file based on language settings
        self._init_game_config_manager()
        
        # Initialize AI components based on mode
        if limited_mode:
            logger.info("🚨 RAG Integration running in limited mode, skipping AI component initialization")
        else:
            self._init_ai_components()

    # ----- telemetry helpers -----
    def _telemetry_base(self) -> Dict[str, Any]:
        """构建默认埋点上下文，确保后端能够识别设备与模式"""

        base: Dict[str, Any] = {"app_mode": "cloud" if self.limited_mode else "local"}

        # 尝试补充来自客户端的设备信息，便于排查问题
        if self.backend_client:
            try:
                base.update(self.backend_client.telemetry_context())
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"telemetry_context 生成失败: {exc}")

        # 标记当前窗口信息 & 映射游戏识别
        current_window = getattr(self, "current_game_window", None)
        base["game_window"] = current_window

        detected_game = None
        try:
            detected_game = getattr(self.rag_integration, "_current_rag_game", None)
        except Exception:  # noqa: BLE001
            detected_game = None

        if not detected_game and current_window:
            try:
                from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name

                detected_game = map_window_title_to_game_name(current_window)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"game mapping failed: {exc}")

        if detected_game:
            base["game_detected"] = detected_game

        # 确保基础字段存在，避免后端解析报错
        base.setdefault("ip", "127.0.0.1")
        base.setdefault("device_id", None)
        return base

    def _track_event(self, name: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """统一封装埋点上报，避免在调用处散落 try/except"""

        if not self.analytics_mgr:
            return

        try:
            payload = self._telemetry_base()
            if properties:
                payload.update(properties)
            self.analytics_mgr.track(name, payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Analytics track failed: {exc}")

    def _track_model_event(
        self,
        provider: Optional[str],
        success: bool,
        model: Optional[str] = None,
        fallback_used: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        """记录模型调用结果，区分不同厂商与回退场景"""

        if not provider:
            provider = "unknown"

        event_name = None
        provider_lower = provider.lower()
        if provider_lower == "deepseek":
            event_name = (
                analytics_events.DEEPSEEK_CALL_SUCCESS
                if success
                else analytics_events.DEEPSEEK_CALL_FAILED
            )
        elif provider_lower == "gemini":
            event_name = (
                analytics_events.GEMINI_CALL_SUCCESS
                if success
                else analytics_events.GEMINI_CALL_FAILED
            )

        properties = {
            "provider": provider,
            "model": model,
            "limited_mode": self.limited_mode,
            "fallback_used": fallback_used,
        }
        if reason:
            properties["reason"] = reason

        if event_name:
            self._track_event(event_name, properties)
        else:
            # 未知厂商统一归入 fallback 埋点，便于后端聚合分析
            self._track_event(
                analytics_events.MODEL_FALLBACK_TRIGGERED,
                {
                    "provider": provider,
                    "model": model,
                    "limited_mode": self.limited_mode,
                    "reason": reason or ("success" if success else "failure"),
                },
            )
            
    def _get_localized_message(self, message_key: str) -> str:
        """Get localized message based on current language setting"""
        # Get current language from settings
        settings = self.settings_manager.get()
        current_language = settings.get('language', 'zh')
        
        # Define localized messages
        messages = {
            "game_not_supported": {
                "zh": "我们目前尚未支持该游戏的AI问答",
                "en": "AI Q&A is not currently supported for this game"
            }
        }
        
        # Return localized message, fallback to Chinese if not found
        if message_key in messages:
            return messages[message_key].get(current_language, messages[message_key].get('zh', ''))
        
        # Return key itself if message not defined
        return message_key
            
    def _init_game_config_manager(self):
        """Initialize game configuration manager based on language settings"""
        from src.game_wiki_tooltip.core.utils import APPDATA_DIR
        from src.game_wiki_tooltip.core.config import GameConfigManager
        
        # Get current language settings
        settings = self.settings_manager.get()
        current_language = settings.get('language', 'en')
        
        # Select configuration file based on language
        if current_language == 'zh':
            games_config_path = APPDATA_DIR / "games_zh.json"
            logger.info(f"🌐 Using Chinese game configuration: {games_config_path}")
        else:
            # Default to English configuration (other)
            games_config_path = APPDATA_DIR / "games_en.json"
            logger.info(f"🌐 Using English game configuration: {games_config_path}")
            
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
        
        # Update AI components language setting
        self._update_ai_language_setting()
        
    def _init_ai_components(self):
        """Initialize AI components with settings"""
        # Skip AI component initialization if in limited mode
        if self.limited_mode:
            logger.info("🚨 Skipping AI component initialization in limited mode")
            return
            
        # Just log that we'll initialize on demand - don't actually initialize anything
        logger.info("📌 AI components will be initialized on first use (lazy loading)")
        
    def _ensure_ai_components_loaded(self, allow_partial: bool = False):
        """Ensure AI components are loaded (called before actual use)"""
        if self.limited_mode and not allow_partial:
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
            
            # Check environment variables
            if not gemini_api_key:
                gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
            # Gemini API key is used for both LLM and embeddings
            
            # Check if API key is available
            has_api_key = bool(gemini_api_key)
            
            if has_api_key:
                logger.info("✅ Complete API key configuration detected, initializing AI components")
                
                # Get current language setting for AI response
                current_language = settings.get('language', 'en')
                response_language = current_language if current_language in ['zh', 'en'] else 'en'
                logger.info(f"🌐 AI language setting: interface={current_language}, response={response_language}")
                
                llm_config = LLMSettings(
                    api_key=gemini_api_key,
                    model='gemini-2.5-flash-lite',
                    response_language=response_language
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
            elif allow_partial:
                logger.info("🧩 Partial AI initialization：使用检索功能但跳过 Gemini 依赖")

                current_language = settings.get('language', 'en')
                response_language = current_language if current_language in ['zh', 'en'] else 'en'

                llm_config = LLMSettings(
                    api_key=gemini_api_key or None,
                    model='gemini-2.5-flash-lite',
                    response_language=response_language
                )

                self._llm_config = llm_config
                self._last_game_window = None
                self._last_vector_game_name = None
            else:
                missing_keys = []
                if not gemini_api_key:
                    missing_keys.append("Gemini API Key")
                
                logger.warning(f"❌ Missing required API keys: {', '.join(missing_keys)}")
                return False
                    
        except Exception as e:
            logger.error(f"Failed to initialize AI components: {e}")
            return False
            
        self._ai_initialized = True
        return True
    
    def _update_ai_language_setting(self):
        """Update AI components language setting when interface language changes"""
        try:
            if not hasattr(self, '_llm_config') or not self._llm_config:
                logger.info("🌐 No LLM config available, skipping language update")
                return
                
            # Get current language setting
            settings = self.settings_manager.get()
            current_language = settings.get('language', 'en')
            response_language = current_language if current_language in ['zh', 'en'] else 'en'
            
            # Update LLM config language setting
            old_language = self._llm_config.response_language
            self._llm_config.response_language = response_language
            
            logger.info(f"🌐 Updated AI response language: {old_language} -> {response_language}")
            
            # If RAG engine is initialized, update its summarizer language setting
            if hasattr(self, 'rag_engine') and self.rag_engine and hasattr(self.rag_engine, 'summarizer'):
                if self.rag_engine.summarizer:
                    # Update config language setting
                    if hasattr(self.rag_engine.summarizer, 'config'):
                        self.rag_engine.summarizer.config.language = response_language
                        logger.info(f"🌐 Updated RAG summarizer config language setting to: {response_language}")
                    
                    # Update LLM config language setting (priority)
                    if hasattr(self.rag_engine.summarizer, 'llm_config') and self.rag_engine.summarizer.llm_config:
                        self.rag_engine.summarizer.llm_config.response_language = response_language
                        logger.info(f"🌐 Updated RAG summarizer LLM config language setting to: {response_language}")
                    
        except Exception as e:
            logger.error(f"Failed to update AI language setting: {e}")
            
    def _init_rag_for_game(self, game_name: str, llm_config: LLMSettings, google_api_key: str, wait_for_init: bool = False):
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
            
    def _check_vector_store_exists(self, game_name: str) -> bool:
        """Check if vector store exists for the given game"""
        try:
            from .ai.rag_query import find_vector_store_directory
            from pathlib import Path
            
            vector_dir = find_vector_store_directory()
            config_path = vector_dir / f"{game_name}_vectors_config.json"
            return config_path.exists()
        except Exception as e:
            logger.error(f"Error checking vector store existence: {e}")
            return False
            
    def _check_rag_init_and_process_query(self):
        """Check RAG initialization status and process pending query"""
        try:
            # Check if initialization is complete
            if not self._rag_initializing:
                # Stop the timer
                if hasattr(self, '_init_check_timer') and self._init_check_timer:
                    self._init_check_timer.stop()
                    self._init_check_timer = None
                
                # Check if initialization was successful
                if self.rag_engine and self._pending_query:
                    # Process the pending query
                    query_data = self._pending_query
                    self._pending_query = None
                    
                    # Continue with query processing
                    asyncio.create_task(self.generate_guide_async(
                        query_data['query'],
                        query_data['game_context'],
                        query_data['original_query'],
                        query_data['skip_query_processing'],
                        query_data['unified_query_result'],
                        query_data['stop_flag']
                    ))
                elif not self.rag_engine and self._pending_query:
                    # Initialization failed, show appropriate message
                    self._pending_query = None
                    self.streaming_chunk_ready.emit(self._get_localized_message("game_not_supported"))
                    
        except Exception as e:
            logger.error(f"Error checking RAG initialization: {e}")
            if hasattr(self, '_init_check_timer') and self._init_check_timer:
                self._init_check_timer.stop()
                self._init_check_timer = None
            
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
        
        # In cloud proxy模式下使用简化意图识别，允许继续调用后端模型
        if self.limited_mode:
            logger.info("🌐 Limited mode active，trying cloud preprocessing pipeline")
            backend_intent = await self._process_query_via_backend(query, game_context)
            if backend_intent:
                return backend_intent
            logger.warning("Cloud preprocessing unavailable, falling back to lightweight detection")
            return self._simple_intent_detection(query)
            
        # Ensure AI components are loaded (lazy loading)
        if not self._ensure_ai_components_loaded():
            logger.error("❌ AI component loading failed, attempting cloud preprocessing fallback")
            backend_intent = await self._process_query_via_backend(query, game_context)
            if backend_intent:
                return backend_intent
            return QueryIntent(
                intent_type='wiki',
                confidence=0.9,
                rewritten_query=query,
                translated_query=query
            )
        
        # Check if we have game context, if not use simple intent detection
        if not game_context:
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
                llm_config = LLMSettings(
                    model='gemini-2.5-flash-lite'
                )
                
                # Use LLMSettings's get_api_key method to get API key (supports GEMINI_API_KEY environment variable)
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
    
    async def _process_query_via_backend(self, query: str, game_context: Optional[str]) -> Optional[QueryIntent]:
        """Use backend proxy model to perform translation/intent/rewriting"""

        if not self.backend_client:
            logger.debug("Backend client unavailable, cannot run cloud preprocessing")
            return None

        system_prompt = (
            "You are a preprocessing helper for a game wiki assistant. "
            "Analyze the incoming player query and respond with STRICT JSON (no extra text) containing:\n"
            "{\n"
            "  \"detected_language\": string (iso code like zh/en/other),\n"
            "  \"translated_query\": string (English translation or original),\n"
            "  \"rewritten_query\": string (optimized for semantic search),\n"
            "  \"bm25_optimized_query\": string (keywords for BM25),\n"
            "  \"intent\": string (wiki or guide),\n"
            "  \"confidence\": number between 0 and 1,\n"
            "  \"search_type\": string (semantic, keyword, or hybrid),\n"
            "  \"reasoning\": short explanation\n"
            "}\n"
            "The JSON must be parsable and contain all keys."
        )

        user_prompt = (
            f"User query: {query}\n"
            f"Game context: {game_context or 'unknown'}\n"
            "Return JSON ONLY."
        )

        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.backend_client.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Cloud preprocessing request failed: {exc}")
            return None

        if not response or not response.get("content"):
            logger.warning("Cloud preprocessing returned empty content")
            return None

        content = response.get("content", "").strip()
        data = self._parse_backend_json(content)
        if not data:
            logger.warning("Cloud preprocessing JSON parse failed")
            return None

        intent_value = (data.get("intent") or "").lower()
        if intent_value not in {"wiki", "guide"}:
            logger.debug(f"Unsupported intent value from backend: {intent_value}")
            return None

        translated_query = data.get("translated_query") or query
        rewritten_query = data.get("rewritten_query") or translated_query
        bm25_query = data.get("bm25_optimized_query") or translated_query
        confidence = data.get("confidence")
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.6
        confidence = max(0.0, min(1.0, confidence))

        search_type = data.get("search_type") or "semantic"
        reasoning = data.get("reasoning") or ""
        detected_language = data.get("detected_language") or "unknown"

        unified_result = UnifiedQueryResult(
            original_query=query,
            detected_language=detected_language,
            translated_query=translated_query,
            rewritten_query=rewritten_query,
            bm25_optimized_query=bm25_query,
            intent=intent_value,
            confidence=confidence,
            search_type=search_type,
            reasoning=reasoning,
            translation_applied=translated_query != query,
            rewrite_applied=rewritten_query != translated_query,
            processing_time=0.0,
        )

        logger.info(
            "Cloud preprocessing success: intent=%s confidence=%.2f translation_applied=%s",
            intent_value,
            confidence,
            unified_result.translation_applied,
        )

        return QueryIntent(
            intent_type=intent_value,
            confidence=confidence,
            rewritten_query=rewritten_query,
            translated_query=translated_query,
            unified_query_result=unified_result,
        )

    @staticmethod
    def _parse_backend_json(content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON content returned by backend preprocessing"""

        if not content:
            return None

        text = content.strip()
        if text.startswith("```"):
            # Remove code fences if present
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            if lines and lines[0].lower().startswith("json"):
                lines = lines[1:]
            text = "\n".join(lines).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                logger.debug("Primary JSON block parsing failed")

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.debug("Fallback JSON parsing failed")
            return None
            
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
            
            # Note: wiki_link_updated signal removed - now using direct update mechanism
            logger.info(f"✅ Wiki link information processed: {real_title} -> {real_url}")
            
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
        # Limited mode 下使用后端模型代理
        if self.limited_mode:
            context_snippets = await self._collect_context_snippets(
                query=query,
                game_context=game_context,
                unified_query_result=unified_query_result,
            )
            await self._generate_via_backend(
                query,
                original_query,
                game_context,
                stop_flag,
                context_snippets=context_snippets,
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
                    
                    # Check environment variables
                    if not gemini_api_key:
                        gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
                    
                    # Check if API key is available
                    has_api_key = bool(gemini_api_key)
                    
                    if has_api_key:
                        llm_config = LLMSettings(
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
                        
                        # Check if vector store exists before attempting initialization
                        if not self._check_vector_store_exists(vector_game_name):
                            logger.info(f"No vector store found for game '{vector_game_name}', checking intent for fallback")
                            
                            # Check if intent is guide and use fallback handler
                            if unified_query_result and unified_query_result.intent == "guide":
                                logger.info("🌐 Using fallback guide handler for game without vector store")
                                
                                try:
                                    # Import fallback handler
                                    from .ai.fallback_guide_handler import create_fallback_guide_handler
                                    
                                    # Get current language setting for AI response
                                    current_language = settings.get('language', 'en')
                                    response_language = current_language if current_language in ['zh', 'en'] else 'en'
                                    
                                    # Create LLM config for fallback handler
                                    fallback_llm_config = LLMSettings(
                                        api_key=gemini_api_key,
                                        model='gemini-2.5-flash-lite',
                                        response_language=response_language
                                    )
                                    
                                    # Create fallback handler with LLM config
                                    fallback_handler = create_fallback_guide_handler(
                                        api_key=gemini_api_key,
                                        llm_config=fallback_llm_config
                                    )
                                    
                                    # Determine language
                                    from src.game_wiki_tooltip.core.i18n import get_current_language
                                    current_lang = get_current_language()
                                    
                                    # Use fallback handler for streaming guide generation
                                    async for chunk in fallback_handler.generate_guide_stream(
                                        query=query,
                                        game_context=game_context,
                                        language=current_lang,
                                        original_query=original_query
                                    ):
                                        # Check stop flag if provided
                                        if stop_flag and stop_flag():
                                            logger.info("🛑 Fallback guide generation stopped by user")
                                            return
                                        
                                        self.streaming_chunk_ready.emit(chunk)
                                    
                                    self._track_model_event(
                                        provider="gemini",
                                        success=True,
                                        model=fallback_llm_config.model,
                                        fallback_used=False,
                                    )
                                    return
                                    
                                except Exception as e:
                                    logger.error(f"Fallback guide handler failed: {e}")
                                    # Fall through to error message below
                            
                            # If not guide intent or fallback failed, show error
                            self.streaming_chunk_ready.emit(self._get_localized_message("game_not_supported"))
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
                        # No API key available, switch to wiki search
                        logger.info("No API key configured, switching to wiki search")
                        self._track_model_event(
                            provider="gemini",
                            success=False,
                            model=getattr(self._llm_config, "model", "gemini"),
                            fallback_used=True,
                            reason="api_key_missing",
                        )
                        from src.game_wiki_tooltip.core.i18n import get_current_language
                        current_lang = get_current_language()
                        
                        # 发送提示消息
                        if current_lang == 'zh':
                            self.streaming_chunk_ready.emit("💡 正在为您切换到Wiki搜索模式...\n\n")
                        else:
                            self.streaming_chunk_ready.emit("💡 Switching to Wiki search mode...\n\n")
                        
                        # 准备wiki搜索
                        search_url, search_title = await self.prepare_wiki_search_async(query, game_context)
                        self.wiki_result_ready.emit(search_url, search_title)
                        
                        if current_lang == 'zh':
                            self.streaming_chunk_ready.emit(f"🔗 已为您打开Wiki搜索: {search_title}\n")
                        else:
                            self.streaming_chunk_ready.emit(f"🔗 Wiki search opened: {search_title}\n")
                        return
                else:
                    logger.info(f"📋 Window '{game_context}' does not have vector store for guide queries")
                    
                    # Check if we have unified_query_result to determine intent
                    if unified_query_result and unified_query_result.intent == "guide":
                        logger.info("🌐 Using fallback guide handler for unsupported game")
                        
                        # Get API settings for fallback handler
                        settings = self.settings_manager.get()
                        api_settings = settings.get('api', {})
                        gemini_api_key = api_settings.get('gemini_api_key', '') or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
                        
                        if gemini_api_key:
                            try:
                                # Import fallback handler
                                from .ai.fallback_guide_handler import create_fallback_guide_handler
                                
                                # Get current language setting for AI response
                                current_language = settings.get('language', 'en')
                                response_language = current_language if current_language in ['zh', 'en'] else 'en'
                                
                                # Create LLM config for fallback handler
                                fallback_llm_config = LLMSettings(
                                    api_key=gemini_api_key,
                                    model='gemini-2.5-flash-lite',
                                    response_language=response_language
                                )
                                
                                # Create fallback handler with LLM config
                                fallback_handler = create_fallback_guide_handler(
                                    api_key=gemini_api_key,
                                    llm_config=fallback_llm_config
                                )
                                
                                # Determine language
                                from src.game_wiki_tooltip.core.i18n import get_current_language
                                current_lang = get_current_language()
                                
                                # Use fallback handler for streaming guide generation
                                async for chunk in fallback_handler.generate_guide_stream(
                                    query=query,
                                    game_context=game_context,
                                    language=current_lang,
                                    original_query=original_query
                                ):
                                    # Check stop flag if provided
                                    if stop_flag and stop_flag():
                                        logger.info("🛑 Fallback guide generation stopped by user")
                                        return
                                    
                                    self.streaming_chunk_ready.emit(chunk)
                                
                                self._track_model_event(
                                    provider="gemini",
                                    success=True,
                                    model=fallback_llm_config.model,
                                    fallback_used=False,
                                )
                                return
                                
                            except Exception as e:
                                logger.error(f"Fallback guide handler failed: {e}")
                                # Fall through to error handling below
                    
                    # If not guide intent or fallback failed, show error
                    from src.game_wiki_tooltip.core.i18n import t
                    error_msg = t("game_not_supported", window=game_context)
                    self.error_occurred.emit(error_msg)
                    self._track_model_event(
                        provider="gemini",
                        success=False,
                        model=getattr(self._llm_config, "model", "gemini"),
                        fallback_used=False,
                        reason="game_not_supported",
                    )
                    return
            else:
                from src.game_wiki_tooltip.core.i18n import t
                self.error_occurred.emit(t("game_not_detected"))
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
                    # Check if stop was requested before switching to wiki
                    if stop_flag and stop_flag():
                        logger.info("🛑 Stop requested, not switching to wiki mode")
                        return
                        
                    logger.info(f"🔄 RAG query has no output, may need to switch to wiki mode: '{query}'")
                    self._track_model_event(
                        provider="gemini",
                        success=False,
                        model=getattr(self._llm_config, "model", "gemini"),
                        fallback_used=True,
                        reason="no_output",
                    )
                    
                    from src.game_wiki_tooltip.core.i18n import get_current_language
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
                
                # 成功完成本地 RAG 结果，记录成功埋点
                self._track_model_event(
                    provider="gemini",
                    success=True,
                    model=getattr(self._llm_config, "model", "gemini"),
                    fallback_used=False,
                )
                logger.info("✅ Streaming RAG query completed")
                return
                    
            except Exception as e:
                # Handle specific RAG error types
                from src.game_wiki_tooltip.ai.rag_query import VectorStoreUnavailableError
                from src.game_wiki_tooltip.ai.enhanced_bm25_indexer import BM25UnavailableError
                from src.game_wiki_tooltip.core.i18n import t, get_current_language
                
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
                    self._track_model_event(
                        provider="gemini",
                        success=False,
                        model=getattr(self._llm_config, "model", "gemini"),
                        fallback_used=False,
                        reason="rate_limit",
                    )
                    return
                elif isinstance(e, VectorStoreUnavailableError):
                    if current_lang == 'zh':
                        error_msg = f"❌ {t('rag_vector_store_error')}: {str(e)}"
                    else:
                        error_msg = f"❌ {t('rag_vector_store_error')}: {str(e)}"
                    self._track_model_event(
                        provider="gemini",
                        success=False,
                        model=getattr(self._llm_config, "model", "gemini"),
                        fallback_used=True,
                        reason="vector_store_unavailable",
                    )
                elif isinstance(e, BM25UnavailableError):
                    if current_lang == 'zh':
                        error_msg = f"❌ {t('rag_bm25_error')}: {str(e)}"
                    else:
                        error_msg = f"❌ {t('rag_bm25_error')}: {str(e)}"
                    self._track_model_event(
                        provider="gemini",
                        success=False,
                        model=getattr(self._llm_config, "model", "gemini"),
                        fallback_used=True,
                        reason="bm25_unavailable",
                    )
                else:
                    # General error - try to switch to wiki mode automatically
                    logger.error(f"Streaming RAG query failed: {e}")
                    
                    # Check if stop was requested before switching to wiki
                    if stop_flag and stop_flag():
                        logger.info("🛑 Stop requested, not switching to wiki mode after error")
                        return
                        
                    logger.info("Trying to switch to Wiki search mode...")
                    self._track_model_event(
                        provider="gemini",
                        success=False,
                        model=getattr(self._llm_config, "model", "gemini"),
                        fallback_used=True,
                        reason=str(e),
                    )
                    
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
                    self._track_model_event(
                        provider="gemini",
                        success=False,
                        model=getattr(self._llm_config, "model", "gemini"),
                        fallback_used=False,
                        reason=str(e),
                    )
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


    def _is_stop_requested(self, stop_flag) -> bool:
        if not stop_flag:
            return False
        try:
            if callable(stop_flag):
                return bool(stop_flag())
        except Exception:
            return False

        if hasattr(stop_flag, "is_set"):
            try:
                return bool(stop_flag.is_set())
            except Exception:
                return False
        return False

    async def _generate_via_backend(
        self,
        query: str,
        original_query: Optional[str],
        game_context: Optional[str],
        stop_flag,
        *,
        context_snippets: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Use backend chat proxy to generate responses in limited mode"""
        # 云端代理流程：请求前后都要判断停止标记，并记录埋点
        if self._is_stop_requested(stop_flag):
            logger.info("Cloud chat aborted before request (stop flag set)")
            return

        messages = self._build_chat_messages(query, original_query, game_context)
        if context_snippets:
            logger.info(
                "🔁 Limited mode context prepared: game=%s snippets=%s",
                game_context or "unknown",
                len(context_snippets),
            )
            context_message = self._format_context_message(context_snippets, game_context)
            if context_message:
                messages.insert(
                    1,
                    {
                        "role": "system",
                        "content": context_message,
                    },
                )
        preferred_model, provider = self._resolve_model_preferences()
        provider_hint = provider or "unknown"

        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.backend_client.chat_completion(
                    messages=messages,
                    model=preferred_model,
                    provider=provider,
                ),
            )
        except Exception as exc:
            logger.error(f"Cloud chat request failed: {exc}")
            self._track_model_event(provider_hint, False, preferred_model, fallback_used=True, reason="request_error")
            await self._fallback_to_wiki(query, game_context)
            return

        if self._is_stop_requested(stop_flag):
            logger.info("Cloud chat aborted after request (stop flag set)")
            return

        if not response or not response.get("content"):
            logger.warning("Cloud chat returned empty payload, fallback to wiki")
            self._track_model_event(provider_hint, False, preferred_model, fallback_used=True, reason="empty_response")
            await self._fallback_to_wiki(query, game_context)
            return

        content = response.get("content", "").strip()
        if not content:
            logger.warning("Cloud chat content empty, fallback to wiki")
            self._track_model_event(provider_hint, False, preferred_model, fallback_used=True, reason="empty_content")
            await self._fallback_to_wiki(query, game_context)
            return

        logger.info(
            "Cloud chat success provider=%s model=%s fallback=%s",
            response.get("provider"),
            response.get("model"),
            response.get("fallback_used"),
        )

        resolved_provider = response.get("provider") or provider_hint
        self._track_model_event(
            resolved_provider,
            True,
            response.get("model") or preferred_model,
            fallback_used=response.get("fallback_used", False),
        )

        if self._is_stop_requested(stop_flag):
            logger.info("Cloud chat aborted before streaming output")
            return

        self.streaming_chunk_ready.emit(content if content.endswith("\n") else f"{content}\n")

    async def _collect_context_snippets(
        self,
        *,
        query: str,
        game_context: Optional[str],
        unified_query_result: Optional[Any],
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """检索本地向量库，返回用于云端代理的上下文片段"""

        if not query or not _lazy_load_ai_modules():
            return []

        try:
            self._ensure_ai_components_loaded(allow_partial=True)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Partial AI init failed, skip local context: {exc}")
            return []

        from src.game_wiki_tooltip.ai.rag_query import (  # Local import to avoid circular cost
            EnhancedRagQuery,
            VectorStoreUnavailableError,
            map_window_title_to_game_name,
        )

        vector_game_name = None
        try:
            vector_game_name = map_window_title_to_game_name(game_context) if game_context else None
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Map window title to game failed: {exc}")

        if not vector_game_name:
            logger.debug("No vector game mapping available, skip context")
            return []

        rag_instance = self._lightweight_rag_cache.get(vector_game_name)

        if not rag_instance:
            try:
                rag_config = get_default_config() if callable(get_default_config) else None
            except Exception:  # noqa: BLE001
                rag_config = None

            if rag_config:
                rag_config.summarization.enabled = False
                rag_config.intent_reranking.enabled = False
                rag_config.query_processing.enable_query_rewrite = False

            rag_instance = EnhancedRagQuery(
                rag_config=rag_config,
                enable_hybrid_search=True,
                enable_summarization=False,
                enable_intent_reranking=False,
                enable_query_rewrite=False,
            )
            try:
                await rag_instance.initialize(vector_game_name)
            except VectorStoreUnavailableError as exc:
                logger.warning(f"Vector store unavailable for game {vector_game_name}: {exc}")
                return []
            self._lightweight_rag_cache[vector_game_name] = rag_instance
        elif not rag_instance.is_initialized:
            try:
                await rag_instance.initialize(vector_game_name)
            except VectorStoreUnavailableError as exc:
                logger.warning(f"Vector store init failed for game {vector_game_name}: {exc}")
                return []

        search_response: Dict[str, Any] = {"results": []}

        try:
            if unified_query_result:
                search_response = await asyncio.to_thread(
                    rag_instance._search_hybrid_with_processed_query,  # noqa: SLF001
                    unified_query_result,
                    top_k,
                )
            elif getattr(rag_instance, "hybrid_retriever", None):
                if getattr(rag_instance, "google_api_key", None):
                    search_response = await asyncio.to_thread(
                        rag_instance.hybrid_retriever.search,
                        query,
                        top_k,
                    )
                else:
                    bm25_indexer = getattr(rag_instance.hybrid_retriever, "bm25_indexer", None)
                    if not bm25_indexer:
                        logger.debug("BM25 indexer unavailable, skip context")
                        return []
                    bm25_results = await asyncio.to_thread(
                        bm25_indexer.search,
                        query,
                        max(top_k, 5),
                    )
                    search_response = {"results": bm25_results}
            else:
                base_results = await asyncio.to_thread(
                    rag_instance._search_faiss if rag_instance.config and rag_instance.config.get("vector_store_type") == "faiss" else rag_instance._search_qdrant,  # noqa: SLF001
                    query,
                    top_k,
                )
                search_response = {"results": base_results}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Collecting context snippets failed: {exc}")
            return []

        results = search_response.get("results", [])
        if not results:
            return []

        snippets: List[Dict[str, Any]] = []
        for idx, item in enumerate(results):
            chunk = item.get("chunk", item)
            summary = chunk.get("summary") or chunk.get("text")
            if not summary:
                continue
            logger.debug(
                "Snippet #%s score=%s title=%s",
                idx + 1,
                item.get("score"),
                chunk.get("topic") or chunk.get("title"),
            )
            snippet = {
                "title": chunk.get("topic") or chunk.get("title") or f"Snippet {idx + 1}",
                "summary": summary,
                "source": chunk.get("video_title") or chunk.get("source"),
                "url": chunk.get("video_url") or chunk.get("source_url"),
            }
            score = item.get("score")
            if score is not None:
                snippet["score"] = float(score)
            snippets.append(snippet)
            if len(snippets) >= top_k:
                break

        return snippets

    def _format_context_message(
        self,
        snippets: List[Dict[str, Any]],
        game_context: Optional[str],
    ) -> str:
        if not snippets:
            return ""

        header = "以下是根据当前游戏检索到的参考资料，请结合这些内容回答用户问题："
        if game_context:
            header = f"以下是关于 {game_context} 的参考资料，请结合这些内容回答用户问题："

        lines: List[str] = [header]
        for idx, snippet in enumerate(snippets, 1):
            title = snippet.get("title") or f"片段 {idx}"
            lines.append(f"{idx}. {title}")
            lines.append(snippet.get("summary", "").strip())
            if snippet.get("source"):
                lines.append(f"来源：{snippet['source']}")
            if snippet.get("url"):
                lines.append(f"链接：{snippet['url']}")
            lines.append("")

        return "\n".join(lines).strip()

    async def _fallback_to_wiki(self, query: str, game_context: Optional[str]) -> None:
        from src.game_wiki_tooltip.core.i18n import get_current_language

        # 当云端代理失败时，一方面告知用户转回 Wiki，另一方面发送回退埋点
        current_lang = get_current_language()
        if current_lang == 'zh':
            self.streaming_chunk_ready.emit("💡 云端模型暂不可用，已为您切换到 Wiki 搜索模式...\n\n")
        else:
            self.streaming_chunk_ready.emit("💡 Cloud model is unavailable, switching to Wiki search...\n\n")

        self._track_event(
            analytics_events.MODEL_FALLBACK_TRIGGERED,
            {
                "provider": "deepseek",
                "limited_mode": self.limited_mode,
                "reason": "cloud_fallback",
            },
        )

        search_url, search_title = await self.prepare_wiki_search_async(query, game_context)
        self.wiki_result_ready.emit(search_url, search_title)

        if current_lang == 'zh':
            self.streaming_chunk_ready.emit(f"🔗 已为您打开Wiki搜索: {search_title}\n")
        else:
            self.streaming_chunk_ready.emit(f"🔗 Wiki search opened: {search_title}\n")

    def _resolve_model_preferences(self) -> Tuple[Optional[str], Optional[str]]:
        remote_config = getattr(self.settings_manager.settings, 'remote_config', {}) or {}
        strategy = remote_config.get("model_strategy", {}) or {}
        preferred_model = strategy.get("preferred_model")
        preferred_provider = strategy.get("preferred_provider")

        if preferred_provider:
            return preferred_model, preferred_provider

        for endpoint in remote_config.get("models", []):
            metadata = endpoint.get("metadata", {}) or {}
            if preferred_model and metadata.get("model") == preferred_model:
                return preferred_model, endpoint.get("provider")

        return preferred_model, None

    def _build_chat_messages(
        self,
        query: str,
        original_query: Optional[str],
        game_context: Optional[str],
    ) -> List[Dict[str, str]]:
        settings_snapshot = self.settings_manager.get()
        language = settings_snapshot.get('language', 'zh')
        remote_config = getattr(self.settings_manager.settings, 'remote_config', {}) or {}
        strategy = remote_config.get("model_strategy", {}) or {}

        system_prompt = strategy.get(
            "system_prompt",
            "You are GameWiki Assistant. Provide concise, helpful answers for gamers.",
        )
        if language == 'zh' and "中文" not in system_prompt:
            system_prompt += "\n请使用简体中文回答用户的问题。"

        user_content = original_query or query
        if game_context:
            user_content = f"当前窗口/游戏: {game_context}\n\n{user_content}"

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        return messages


class IntegratedAssistantController(AssistantController):
    """Enhanced assistant controller with RAG integration"""
    
    # Class-level global instance reference
    _global_instance = None
    
    def __init__(self, settings_manager: SettingsManager, backend_client, analytics_mgr=None, limited_mode: bool = False):
        super().__init__(settings_manager)
        self.limited_mode = limited_mode
        self.backend_client = backend_client
        self.analytics_mgr = analytics_mgr
        self.rag_integration = RAGIntegration(
            settings_manager,
            backend_client,
            analytics_mgr,
            limited_mode=limited_mode,
        )
        self._setup_connections()
        self._current_worker = None
        self._current_wiki_message = None  # Store current wiki link message component
        self._settings_window_callback = None  # Callback to show settings window from main app
        
        # Initialize smart interaction manager (pass None as parent, but pass self as controller reference)
        self.smart_interaction = SmartInteractionManager(parent=None, controller=self, game_config_manager=self.rag_integration.game_cfg_mgr)
        self._setup_smart_interaction()
        
        # Register as global instance
        IntegratedAssistantController._global_instance = self
        logger.info(f"🌐 Registered as global assistant controller instance (limited_mode={limited_mode})")
        
        # If in limited mode, display prompt information
        if limited_mode:
            logger.info("🚨 运行在云端代理模式：Wiki 搜索 + 远端聊天")
        else:
            logger.info("✅ 运行在本地增强模式：支持 Wiki 搜索与本地 RAG 功能")
            # Don't preload AI modules immediately, wait for first window display
            self._ai_preload_scheduled = False
            
            # Schedule AI preload immediately after initialization (with a small delay to avoid blocking)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self._schedule_ai_preload_on_startup)

    # ----- analytics helpers -----
    def _telemetry_base(self) -> Dict[str, Any]:
        """构建所有埋点默认需要包含的上下文"""

        base: Dict[str, Any] = {
            "game_window": getattr(self, "current_game_window", None),
            "app_mode": "cloud" if self.limited_mode else "local",
        }

        if self.backend_client:
            base.update(self.backend_client.telemetry_context())

        # 若 backend_client 无法推断 IP，会返回 127.0.0.1，后端可再次校验
        base.setdefault("ip", "127.0.0.1")
        return base

    def _track_event(self, name: str, properties: Optional[Dict[str, Any]] = None) -> None:
        if not self.analytics_mgr:
            return
        try:
            payload = self._telemetry_base()
            if properties:
                payload.update(properties)
            self.analytics_mgr.track(name, payload)
        except Exception as exc:
            logger.debug(f"Analytics track failed: {exc}")

    def _track_model_event(
        self,
        provider: Optional[str],
        success: bool,
        model: Optional[str] = None,
        fallback_used: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        """统一埋点模型调用结果，区分成功/失败/回退"""

        if not provider:
            provider = "unknown"

        event_name = None
        provider_lower = provider.lower()
        if provider_lower == "deepseek":
            event_name = (
                analytics_events.DEEPSEEK_CALL_SUCCESS
                if success
                else analytics_events.DEEPSEEK_CALL_FAILED
            )
        elif provider_lower == "gemini":
            event_name = (
                analytics_events.GEMINI_CALL_SUCCESS
                if success
                else analytics_events.GEMINI_CALL_FAILED
            )

        properties = {
            "provider": provider,
            "model": model,
            "limited_mode": self.limited_mode,
            "fallback_used": fallback_used,
        }
        if reason:
            properties["reason"] = reason

        if event_name:
            self._track_event(event_name, properties)
        else:
            # Unknown provider，统一记录到 fallback 事件中
            self._track_event(
                analytics_events.MODEL_FALLBACK_TRIGGERED,
                {
                    "provider": provider,
                    "model": model,
                    "limited_mode": self.limited_mode,
                    "reason": reason or ("success" if success else "failure"),
                },
            )
        
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
        
        # Verify thread started successfully
        if not self._ai_loader.isRunning():
            logger.warning("⚠️ AI loader thread failed to start, trying direct loading")
            # Fallback to direct loading if thread fails
            success = _lazy_load_ai_modules()
            self._on_ai_modules_loaded(success)
        else:
            logger.info("📋 AI modules loading started in background thread")
        
    def handle_stop_generation(self):
        """Handle stop generation request from UI"""
        logger.info("🛑 Received stop generation request from UI")
        
        # Stop current worker thread
        if self._current_worker and self._current_worker.isRunning():
            logger.info("🛑 Stopping current worker...")
            self._current_worker.stop()
            
        # Reset UI state
        if self.main_window:
            self.main_window.set_generating_state(False)
            # Hide any status messages when generation is stopped
            self.main_window.chat_view.hide_status()
        
    def _on_ai_modules_loaded(self, success: bool):
        """Callback when AI modules are loaded"""
        # Add thread safety check
        if not hasattr(self, '_ai_loader') or not self._ai_loader:
            logger.warning("AI loader already cleaned up, ignoring signal")
            return
            
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
            
        # Safely clean up loader thread
        if self._ai_loader:
            try:
                if self._ai_loader.isRunning():
                    logger.debug("Waiting for AI loader thread to finish...")
                    self._ai_loader.quit()
                    if not self._ai_loader.wait(1000):  # Wait max 1 second
                        logger.warning("AI loader thread did not finish in time")
                self._ai_loader.deleteLater()  # Use Qt's deferred deletion mechanism
                logger.debug("AI loader thread cleanup scheduled")
            except Exception as e:
                logger.error(f"Error during AI loader cleanup: {e}")
            finally:
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
            # Clear current game context if window changed to unsupported game
            if hasattr(self, '_current_vector_game'):
                logger.info(f"🔄 Clearing game context due to unsupported window")
                self._current_vector_game = None
    
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
    
    def handle_settings_requested(self):
        """Handle settings window request from chat window"""
        logger.info("Settings window requested from chat window")
        # Call the callback if it's set
        if self._settings_window_callback:
            self._settings_window_callback()
        else:
            logger.warning("No settings window callback set")
    
    def set_settings_window_callback(self, callback):
        """Set the callback function to show settings window"""
        self._settings_window_callback = callback
    
    def handle_query(self, query: str, mode: str = "auto"):
        """Override to handle query with RAG integration"""
        # Store search mode
        self._search_mode = mode
        
        # Check if the last message in chat view is already this user query
        # to avoid duplication (since it may have been added in the UI already)
        should_add_message = True
        if self.main_window and self.main_window.chat_view.messages:
            last_message = self.main_window.chat_view.messages[-1]
            if (hasattr(last_message, 'message') and 
                last_message.message.type == MessageType.USER_QUERY and 
                last_message.message.content == query):
                should_add_message = False
        
        # Add user message only if not already added
        if should_add_message:
            self.main_window.chat_view.add_message(
                MessageType.USER_QUERY,
                query
            )
        
        # Check RAG engine initialization status (check the RAGIntegration's status)
        if hasattr(self.rag_integration, '_rag_initializing') and self.rag_integration._rag_initializing:
            # RAG engine is initializing, display waiting status
            from src.game_wiki_tooltip.core.i18n import t
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
        from src.game_wiki_tooltip.core.i18n import t
        
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
            
    # Note: _on_wiki_link_updated method removed - functionality replaced by _update_wiki_message_directly
    
    def _update_wiki_message_directly(self, url: str, title: str):
        """Directly update wiki message in chat view, similar to history record mechanism"""
        try:
            import logging
            logger = logging.getLogger(__name__)
            
            # Validate URL and title
            if not url or not title:
                logger.warning(f"Invalid URL or title for wiki update: url='{url}', title='{title}'")
                return
                
            # Filter out temporary states
            if title in ["请稍候…", "Loading...", "Redirecting...", "", "Search:"]:
                logger.info(f"Skip temporary title: '{title}'")
                return
            
            # Ensure we have a wiki message to update
            if not hasattr(self, '_current_wiki_message') or not self._current_wiki_message:
                logger.warning("No current wiki message to update")
                return
                
            logger.info(f"🔗 Directly updating wiki message: '{title}' -> {url}")
            
            # Update message content and metadata directly
            self._current_wiki_message.message.content = title
            self._current_wiki_message.message.metadata["url"] = url
            
            # Update display with clean HTML - show title as clickable link
            html_content = f'[LINK] <a href="{url}" style="color: #4096ff;">{title}</a>'
            self._current_wiki_message.content_label.setText(html_content)
            self._current_wiki_message.content_label.setTextFormat(Qt.TextFormat.RichText)
            
            # Adjust component size to fit new content
            self._current_wiki_message.content_label.adjustSize()
            self._current_wiki_message.adjustSize()
            
            # Force redraw
            self._current_wiki_message.update()
            
            logger.info(f"✅ Wiki message directly updated to show real title: '{title}'")
            
        except Exception as e:
            logger.error(f"❌ Failed to directly update wiki message: {e}")
            
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
            
    def _reinitialize_rag_for_game(self, vector_game_name: str, retry_count: int = 0):
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
            
            # Check if we should stop retrying
            MAX_RETRIES = 3
            if retry_count >= MAX_RETRIES:
                logger.info(f"⏹️ Max retries ({MAX_RETRIES}) reached for RAG initialization, stopping")
                return
            
            # Ensure AI modules are loaded before attempting RAG initialization
            if not self.rag_integration._ensure_ai_components_loaded():
                # Check if this is a permanent failure (missing API key) or temporary (loading)
                settings = self.settings_manager.get()
                api_settings = settings.get('api', {})
                gemini_api_key = api_settings.get('gemini_api_key', '') or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
                
                if not gemini_api_key:
                    # Permanent failure - no API key configured
                    logger.info("⏹️ No API key configured, RAG initialization disabled")
                    return
                else:
                    # Temporary failure - modules still loading
                    if retry_count == 0:
                        logger.info(f"AI components loading, deferring RAG initialization...")
                    else:
                        logger.info(f"AI components not ready, retrying RAG initialization (attempt {retry_count + 1}/{MAX_RETRIES})")
                    # Schedule another attempt with exponential backoff
                    delay = min(1000 * (2 ** retry_count), 10000)  # 1s, 2s, 4s, 8s, max 10s
                    QTimer.singleShot(delay, lambda: self._reinitialize_rag_for_game(vector_game_name, retry_count + 1))
                    return
            
            # Get API settings
            settings = self.settings_manager.get()
            api_settings = settings.get('api', {})
            gemini_api_key = api_settings.get('gemini_api_key', '')
            
            # Check environment variables
            if not gemini_api_key:
                gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
            # Gemini API key is used for both LLM and embeddings
            
            # Check if API key is available
            has_api_key = bool(gemini_api_key)
            
            if has_api_key:
                llm_config = LLMSettings(
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
        
    def reset_rag_retry_state(self):
        """Reset RAG retry state, useful when settings change or new API keys are added."""
        # This method can be called when settings are updated to allow retrying RAG initialization
        # The retry counter is passed as a parameter, so no persistent state to reset
        logger.info("RAG retry state reset - will retry initialization on next game window change")
        
        # If there's a current game, try to reinitialize
        if hasattr(self, 'current_game_window') and self.current_game_window:
            # Try to get vector name for current game
            settings = self.settings_manager.get()
            current_language = settings.get('language', 'zh')
            if current_language == 'en':
                games_config = self._games_config_en
            else:
                games_config = self._games_config_zh
            
            vector_game_name = self._get_vector_library_name(self.current_game_window, games_config)
            if vector_game_name:
                # Reset retry count to 0 for new attempt
                self._reinitialize_rag_for_game(vector_game_name, retry_count=0)
        
    def handle_wiki_page_found(self, url: str, title: str):
        """Override parent class method: handle WikiView signal when real wiki page is found"""
        logger.info(f"🔗 IntegratedAssistantController received WikiView signal: {title} -> {url}")
        
        # Filter out obvious temporary state titles, only process meaningful updates
        if title and title not in ["请稍候…", "Loading...", "Redirecting...", ""]:
            logger.info(f"✅ Accept wiki page update: {title}")
            
            # Use direct update approach - reliable like the history record mechanism
            self._update_wiki_message_directly(url, title)
        else:
            logger.info(f"⏳ Skip temporary state wiki page update: {title}")
            # For temporary state, still call, but do not trigger final update in chat window
    
    # Smart interaction manager signal handling methods
    def _on_interaction_mode_changed(self, mode: InteractionMode):
        """Handle interaction mode changes"""
        logger.info(f"🎮 Interaction mode changed: {mode.value}")
        
        # Adjust window mouse passthrough state based on interaction mode
        if hasattr(self, 'main_window') and self.main_window:
            should_passthrough = self.smart_interaction.should_enable_mouse_passthrough()
            logger.info(f"🔧 Should enable passthrough: {should_passthrough}")
            
            # Get current mouse state for debugging
            mouse_state = self.smart_interaction.get_mouse_state()
            if mouse_state:
                logger.info(f"🖱️ Current mouse state: visible={mouse_state.is_visible}, suppressed={mouse_state.is_suppressed}")
            
            self.smart_interaction.apply_mouse_passthrough(self.main_window, should_passthrough)
            
            # Show status message for different modes
            if mode == InteractionMode.GAME_HIDDEN:
                logger.info("🎮 Game mouse hidden mode: checking if passthrough needed")
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
            # 立即设置游戏窗口信息到assistant（只更新UI，不初始化RAG）
            if current_game_window:
                logger.info(f"🎮 Pre-setting game window for UI: '{current_game_window}'")
                self.current_game_window = current_game_window
                # 立即更新main_window的按钮（如果窗口已存在）
                if self.main_window:
                    self.main_window.current_game_window = current_game_window
                    self.main_window._update_task_flow_button()
            
            # 先显示聊天窗口（按钮已经更新）
            self.show_chat_window()
            logger.info("💬 Show chat window requested - executed with button pre-configured")
            
            # 检查是否需要自动开启语音输入
            if (self.settings_manager.settings.auto_voice_on_hotkey and 
                self.main_window and 
                self.main_window.current_state in [WindowState.CHAT_ONLY, WindowState.FULL_CONTENT]):
                # 延迟启动语音输入，确保窗口完全显示且输入框获得焦点
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(150, lambda: self._auto_start_voice_input())
                logger.info("🎤 Auto voice input scheduled after hotkey trigger")
            
            # 然后异步初始化RAG（分离按钮显示和RAG初始化）
            if current_game_window:
                logger.info(f"🎮 Async RAG initialization for: '{current_game_window}'")
                # 使用QTimer异步初始化RAG，避免阻塞UI
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(50, lambda: self._delayed_set_game_window(current_game_window))
            else:
                # 清除之前的游戏窗口设置
                logger.info(f"🎮 No game window detected, clearing previous game context")
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(50, lambda: self._clear_game_context())
                
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
    
    def _clear_game_context(self):
        """清除游戏上下文（当检测到非游戏窗口时）"""
        logger.info("🧹 Clearing game context due to non-game window")
        
        # 清除记录的游戏窗口
        self.current_game_window = None
        
        # 清除 RAG 引擎的当前游戏
        if hasattr(self, '_current_vector_game'):
            self._current_vector_game = None
            logger.info("🧹 Cleared RAG engine game context")
        
        # 更新主窗口的游戏上下文
        if self.main_window:
            self.main_window.set_current_game_window(None)
            logger.info("🧹 Cleared main window game context")
    
    def _delayed_set_game_window(self, game_window_title: str):
        """延迟设置游戏窗口，避免阻塞UI"""
        try:
            logger.info(f"🎮 [DEBUG] About to set current game window (delayed): '{game_window_title}'")
            logger.info(f"📋 [DEBUG] Main window exists: {self.main_window is not None}")

            # 设置游戏窗口并确保task flow按钮正确显示
            self.set_current_game_window(game_window_title)

            # 标记游戏窗口已经设置
            self._game_window_already_set = True
            logger.info(f"🏁 [DEBUG] Game window already set flag: True (delayed)")
            
        except Exception as e:
            logger.error(f"Error in delayed game window setting: {e}")
            import traceback
            traceback.print_exc()
    
    def _auto_start_voice_input(self):
        """Auto start voice input after hotkey trigger"""
        try:
            if self.main_window and hasattr(self.main_window, 'toggle_voice_input'):
                logger.info("🎤 Auto-starting voice input")
                self.main_window.toggle_voice_input()
            else:
                logger.warning("⚠️ Cannot auto-start voice input: main_window or toggle_voice_input not available")
        except Exception as e:
            logger.error(f"Error auto-starting voice input: {e}")
            import traceback
            traceback.print_exc()
    
    def show_chat_window(self):
        """显示聊天窗口，隐藏悬浮窗"""
        logger.info("💬 Show chat window requested")
        
        # 标记窗口刚刚显示，激活保护期
        if hasattr(self, 'smart_interaction') and self.smart_interaction:
            self.smart_interaction.mark_window_just_shown()
        
        # 如果已知游戏窗口，立即更新task flow按钮（不等待延迟）
        if hasattr(self, 'current_game_window') and self.current_game_window and self.main_window:
            logger.info(f"🎮 Pre-setting game window for immediate button display: {self.current_game_window}")
            self.main_window.current_game_window = self.current_game_window
            self.main_window._update_task_flow_button()
            # 强制UI更新
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

        # 先决定显示哪种形态
        if not self.main_window.has_switched_state:
            # 如果用户没有切换过形态，显示CHAT_ONLY形态
            logger.info("🎯 Switching to CHAT_ONLY mode (no state switch yet)")
            self.main_window.switch_to_chat_only()
            self.main_window.set_precreating_mode(False)

        # 然后恢复对应状态的几何位置
        self.main_window.restore_geometry()

        # 最后显示窗口
        self.main_window.show()
        self.main_window.raise_()
        
        # 仅在未启用自动语音输入时激活窗口
        if not self.settings_manager.settings.auto_voice_on_hotkey:
            self.main_window.activateWindow()
        else:
            # 语音输入模式：窗口显示但不抢夺焦点
            logger.info("🎤 Voice input mode: showing window without stealing focus")
        
        # 关键：确保窗口显示时是可交互的
        # 使用小延迟确保窗口完全显示后再设置
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, self._ensure_window_interactable)

        # 设置输入框焦点（仅在未启用自动语音输入时）
        if not self.settings_manager.settings.auto_voice_on_hotkey:
            QTimer.singleShot(100, self.main_window._set_chat_input_focus)

        logger.info("💬 Chat window shown")
    
    def _ensure_window_interactable(self):
        """确保窗口在显示后是可交互的"""
        if self.main_window and self.main_window.isVisible():
            logger.info("🔧 Ensuring window is interactable after showing")
            # 强制设置窗口为非穿透状态
            self.smart_interaction.apply_mouse_passthrough(self.main_window, False)
    
    def hide_chat_window(self):
        """隐藏聊天窗口，根据用户设置决定是否显示悬浮窗"""
        logger.info("💬 Hide chat window requested")
        
        # 清除用户主动显示鼠标的标记
        if hasattr(self, 'smart_interaction') and self.smart_interaction:
            self.smart_interaction.set_user_requested_mouse_visible(False)
        
        # 隐藏聊天窗口
        if self.main_window:
            self.main_window.hide()
            logger.info("💬 Chat window hidden")
    
    def show_mouse_for_interaction(self):
        """显示鼠标以便与聊天窗口互动"""
        logger.info("🖱️ Show mouse for interaction requested")
        try:
            # 1. 先激活聊天窗口，确保它获得焦点
            if self.main_window and self.main_window.isVisible():
                logger.info("🎯 Activating chat window first")
                if not self.settings_manager.settings.auto_voice_on_hotkey:
                    self.main_window.activateWindow()
                self.main_window.raise_()
            
            # 2. 在显示鼠标之前，先设置鼠标位置到窗口中心
            if self.main_window and self.main_window.isVisible():
                import ctypes
                
                # 使用mapToGlobal获取窗口中心的屏幕坐标
                center_point = self.main_window.mapToGlobal(
                    QPoint(self.main_window.width() // 2, self.main_window.height() // 2)
                )
                center_x = center_point.x()
                center_y = center_point.y()
                
                # 使用Windows API移动鼠标到窗口中心（在显示之前）
                ctypes.windll.user32.SetCursorPos(center_x, center_y)
                logger.info(f"🎯 Pre-positioned cursor to window center: ({center_x}, {center_y})")
            
            # 3. 标记用户主动请求显示鼠标
            if hasattr(self, 'smart_interaction') and self.smart_interaction:
                self.smart_interaction.set_user_requested_mouse_visible(True)
            
            # 4. 最后调用Windows API显示鼠标
            from src.game_wiki_tooltip.core.utils import show_cursor_until_visible
            show_cursor_until_visible()
            logger.info("🖱️ Mouse cursor shown (after positioning)")
            
            # 5. 微移鼠标以强制Windows立即渲染（移动1像素再移回）
            if self.main_window and self.main_window.isVisible():
                import ctypes
                # 重新获取坐标以防窗口移动
                center_point = self.main_window.mapToGlobal(
                    QPoint(self.main_window.width() // 2, self.main_window.height() // 2)
                )
                center_x = center_point.x()
                center_y = center_point.y()
                
                # 微移动：右移1像素再移回，触发鼠标渲染
                ctypes.windll.user32.SetCursorPos(center_x + 1, center_y)
                ctypes.windll.user32.SetCursorPos(center_x, center_y)
                logger.info("🎯 Micro-moved cursor to ensure rendering")
            
            # 延迟一点时间让鼠标状态更新，然后强制更新交互模式
            # 这会重新评估窗口的鼠标穿透状态
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self._update_window_after_mouse_shown)
            
        except Exception as e:
            logger.error(f"Failed to show mouse cursor: {e}")
    
    def _update_window_after_mouse_shown(self):
        """在鼠标显示后更新窗口状态"""
        logger.info("🔄 Updating window state after mouse shown")
        
        # 强制更新交互模式，这会触发窗口穿透状态的重新评估
        if hasattr(self, 'smart_interaction') and self.smart_interaction:
            # 先检查当前的穿透状态
            current_passthrough = self.smart_interaction.should_enable_mouse_passthrough()
            logger.info(f"🔍 Current passthrough state check: {current_passthrough}")
            
            # 强制更新交互模式
            self.smart_interaction.force_update_interaction_mode()
            
            # 再次检查更新后的穿透状态
            new_passthrough = self.smart_interaction.should_enable_mouse_passthrough()
            logger.info(f"🔍 New passthrough state after update: {new_passthrough}")
