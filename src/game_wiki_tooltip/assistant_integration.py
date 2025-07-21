"""
Integration layer between the new unified UI and existing RAG/Wiki systems.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
import os # Added for os.getenv

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread, Qt

from src.game_wiki_tooltip.unified_window import (
    AssistantController, MessageType, TransitionMessages
)
from src.game_wiki_tooltip.config import SettingsManager, LLMConfig
from src.game_wiki_tooltip.utils import get_foreground_title

# 添加缺失的导入
try:
    from src.game_wiki_tooltip.ai.unified_query_processor import process_query_unified
    from src.game_wiki_tooltip.ai.rag_config import get_default_config
    from src.game_wiki_tooltip.ai.rag_query import EnhancedRagQuery
    logger = logging.getLogger(__name__)
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to import AI components: {e}")
    process_query_unified = None
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
    translated_query: Optional[str] = None  # 添加翻译后的查询字段
    unified_query_result: Optional[object] = None  # 完整的统一查询结果


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
        self._current_task = None  # 当前运行的异步任务
        
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
            # 检查是否已请求停止
            if self._stop_requested:
                return
                
            # 使用统一查询处理器进行意图检测和查询优化
            intent = await self.rag_integration.process_query_async(
                self.query, 
                game_context=self.game_context
            )
            
            # 再次检查是否已请求停止
            if self._stop_requested:
                return
                
            self.intent_detected.emit(intent)
            
            if intent.intent_type == "unsupported":
                # 对于不支持的窗口，直接发出错误信号
                error_msg = f"当前窗口 '{self.game_context}' 不在支持的游戏列表中。\n\n支持的游戏请查看设置页面，或者尝试在支持的游戏窗口中使用本工具。"
                self.error_occurred.emit(error_msg)
                return
            elif intent.intent_type == "wiki":
                # 检查是否已请求停止
                if self._stop_requested:
                    return
                    
                # 对于wiki搜索，使用原始查询（因为wiki搜索不需要优化的查询）
                search_url, search_title = await self.rag_integration.prepare_wiki_search_async(
                    self.query,  # 使用原始查询进行wiki搜索
                    game_context=self.game_context
                )
                
                if not self._stop_requested:
                    self.wiki_result.emit(search_url, search_title)
            else:
                # 检查是否已请求停止
                if self._stop_requested:
                    return
                    
                # 对于攻略查询，同时传递原始查询和处理后的查询
                processed_query = intent.rewritten_query or intent.translated_query or self.query
                
                # 设置当前任务并传递停止标志
                self._current_task = self.rag_integration.generate_guide_async(
                    processed_query,  # 用于检索的查询
                    game_context=self.game_context,
                    original_query=self.query,  # 原始查询，用于答案生成
                    skip_query_processing=True,  # 跳过RAG内部的查询处理
                    unified_query_result=intent.unified_query_result,  # 传递完整的统一查询结果
                    stop_flag=lambda: self._stop_requested  # 传递停止标志检查函数
                )
                await self._current_task
                
        except asyncio.CancelledError:
            logger.info("查询处理被取消")
        except Exception as e:
            if not self._stop_requested:  # 只有在非停止状态下才报告错误
                logger.error(f"Query processing error: {e}")
                self.error_occurred.emit(str(e))
            
    def stop(self):
        """Request to stop the worker"""
        self._stop_requested = True
        logger.info("🛑 QueryWorker停止请求已发出")
        
        # 如果有当前任务，尝试取消
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            logger.info("🛑 当前异步任务已取消")


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
        self._pending_wiki_update = None  # 存储待更新的wiki链接信息
        self._llm_config = None  # 存储已配置的LLM配置
        
        # 初始化游戏配置管理器
        from src.game_wiki_tooltip.utils import APPDATA_DIR
        from src.game_wiki_tooltip.config import GameConfigManager
        
        # 根据语言设置选择游戏配置文件
        self._init_game_config_manager()
        
        # 根据模式初始化AI组件
        if limited_mode:
            logger.info("🚨 RAG Integration 运行在受限模式下，跳过AI组件初始化")
        else:
            self._init_ai_components()
            
    def _init_game_config_manager(self):
        """根据语言设置初始化游戏配置管理器"""
        from src.game_wiki_tooltip.utils import APPDATA_DIR
        from src.game_wiki_tooltip.config import GameConfigManager
        
        # 获取当前语言设置
        settings = self.settings_manager.get()
        current_language = settings.get('language', 'zh')  # 默认中文
        
        # 根据语言选择配置文件
        if current_language == 'en':
            games_config_path = APPDATA_DIR / "games_en.json"
            logger.info(f"🌐 使用英文游戏配置: {games_config_path}")
        else:
            # 默认使用中文配置 (zh 或其他)
            games_config_path = APPDATA_DIR / "games_zh.json"
            logger.info(f"🌐 使用中文游戏配置: {games_config_path}")
            
        # 检查配置文件是否存在，如果不存在则回退到默认的games.json
        if not games_config_path.exists():
            logger.warning(f"⚠️ 语言配置文件不存在: {games_config_path}")
            fallback_path = APPDATA_DIR / "games.json"
            if fallback_path.exists():
                games_config_path = fallback_path
                logger.info(f"📄 回退到默认配置文件: {games_config_path}")
            else:
                logger.error(f"❌ 连默认配置文件都不存在: {fallback_path}")
        
        self.game_cfg_mgr = GameConfigManager(games_config_path)
        self._current_language = current_language
        logger.info(f"✅ 游戏配置管理器已初始化，当前语言: {current_language}")
        
    def reload_for_language_change(self):
        """当语言设置改变时重新加载游戏配置"""
        logger.info("🔄 检测到语言设置变化，重新加载游戏配置")
        self._init_game_config_manager()
        
    def _init_ai_components(self):
        """Initialize AI components with settings"""
        # 如果在受限模式下，跳过AI组件初始化
        if self.limited_mode:
            logger.info("🚨 受限模式下跳过AI组件初始化")
            return
            
        try:
            # 获取API设置
            settings = self.settings_manager.get()
            api_settings = settings.get('api', {})
            gemini_api_key = api_settings.get('gemini_api_key', '')
            jina_api_key = api_settings.get('jina_api_key', '')
            
            # 检查环境变量
            if not gemini_api_key:
                gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
            if not jina_api_key:
                jina_api_key = os.getenv('JINA_API_KEY')
            
            # 检查是否同时有两个API key
            has_both_keys = bool(gemini_api_key and jina_api_key)
            
            if has_both_keys:
                logger.info("✅ 检测到完整的API密钥配置，初始化AI组件")
                
                llm_config = LLMConfig(
                    api_key=gemini_api_key,
                    model='gemini-2.5-flash-lite-preview-06-17'
                )
                
                # 存储LLM配置供其他方法使用
                self._llm_config = llm_config
                
                # Initialize query processor - 移除，我们将直接使用process_query_unified函数
                # if process_query_unified:
                #     self.query_processor = process_query_unified(llm_config=llm_config)
                
                # 智能初始化RAG引擎
                game_title = get_selected_game_title()
                if game_title:
                    # 使用窗口标题映射到向量库名称
                    from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name
                    vector_game_name = map_window_title_to_game_name(game_title)
                    
                    if vector_game_name:
                        logger.info(f"检测到游戏窗口 '{game_title}' -> 向量库: {vector_game_name}")
                        self._init_rag_for_game(vector_game_name, llm_config, jina_api_key)
                    else:
                        logger.info(f"当前窗口 '{game_title}' 不是支持的游戏，跳过RAG初始化")
                        logger.info("RAG引擎将在用户首次查询时根据游戏窗口动态初始化")
                        # 不初始化RAG引擎，等待用户查询时动态检测
                else:
                    logger.info("未检测到前台窗口，跳过RAG初始化")
            else:
                missing_keys = []
                if not gemini_api_key:
                    missing_keys.append("Gemini API Key")
                if not jina_api_key:
                    missing_keys.append("Jina API Key")
                
                logger.warning(f"❌ 缺少必需的API密钥: {', '.join(missing_keys)}")
                logger.warning("无法初始化AI组件，需要同时配置Gemini API Key和Jina API Key")
                    
        except Exception as e:
            logger.error(f"Failed to initialize AI components: {e}")
            
    def _init_rag_for_game(self, game_name: str, llm_config: LLMConfig, jina_api_key: str, wait_for_init: bool = False):
        """Initialize RAG engine for specific game"""
        try:
            if not (get_default_config and EnhancedRagQuery):
                logger.warning("RAG components not available")
                return
                
            logger.info(f"🔄 正在为游戏 '{game_name}' 初始化新的RAG引擎")
            
            # 清除旧的RAG引擎
            if hasattr(self, 'rag_engine') and self.rag_engine:
                logger.info("🗑️ 清除旧的RAG引擎实例")
                self.rag_engine = None
                
            # Get RAG config
            rag_config = get_default_config()
            
            # 自定义混合搜索配置，禁用统一查询处理
            custom_hybrid_config = rag_config.hybrid_search.to_dict()
            custom_hybrid_config["enable_unified_processing"] = False  # 禁用统一查询处理
            custom_hybrid_config["enable_query_rewrite"] = False      # 禁用查询重写
            custom_hybrid_config["enable_query_translation"] = False  # 禁用查询翻译
            
            # Create RAG engine
            self.rag_engine = EnhancedRagQuery(
                vector_store_path=None,  # Will be auto-detected
                enable_hybrid_search=rag_config.hybrid_search.enabled,
                hybrid_config=custom_hybrid_config,  # 使用自定义配置
                llm_config=llm_config,
                jina_api_key=jina_api_key,  # 传入Jina API密钥
                enable_query_rewrite=False,  # 禁用查询重写，避免重复LLM调用
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
                    logger.info(f"🚀 开始异步初始化RAG引擎 (游戏: {game_name})")
                    loop.run_until_complete(self.rag_engine.initialize(game_name))
                    logger.info(f"✅ RAG引擎初始化完成 (游戏: {game_name})")
                    self._rag_init_complete = True
                    self._current_rag_game = game_name  # 记录当前RAG引擎对应的游戏
                    # 清除错误信息
                    if hasattr(self, '_rag_init_error'):
                        delattr(self, '_rag_init_error')
                except Exception as e:
                    logger.error(f"❌ RAG引擎初始化失败 (游戏: {game_name}): {e}")
                    self.rag_engine = None
                    self._rag_init_complete = False
                    self._rag_init_error = str(e)  # 记录初始化错误
                    self._current_rag_game = None
                finally:
                    loop.close()
            
            # 重置初始化状态
            self._rag_init_complete = False
            
            # Run initialization in a separate thread
            import threading
            init_thread = threading.Thread(target=init_rag)
            init_thread.daemon = True
            init_thread.start()
            
            # 如果需要等待初始化完成
            if wait_for_init:
                # 等待初始化完成，最多等待5秒
                import time
                start_time = time.time()
                while not hasattr(self, '_rag_init_complete') or not self._rag_init_complete:
                    if time.time() - start_time > 5:  # 超时
                        logger.warning("RAG初始化超时")
                        break
                    time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Failed to initialize RAG for {game_name}: {e}")
            
    async def process_query_async(self, query: str, game_context: str = None) -> QueryIntent:
        """Process query using unified query processor for intent detection"""
        logger.info(f"开始统一查询处理: '{query}' (游戏上下文: {game_context}, 受限模式: {self.limited_mode})")
        
        # 如果在受限模式下，始终返回wiki意图
        if self.limited_mode:
            logger.info("🚨 受限模式下，所有查询都将被视为wiki查询")
            return QueryIntent(
                intent_type='wiki',
                confidence=0.9,
                rewritten_query=query,
                translated_query=query
            )
        
        # ✅ 新增：在调用LLM之前，先检查游戏窗口是否支持
        if game_context:
            # 1. 检查是否支持RAG攻略查询（有向量库）
            from .ai.rag_query import map_window_title_to_game_name
            game_name = map_window_title_to_game_name(game_context)
            
            # 2. 检查是否在games.json配置中（支持wiki查询）
            is_wiki_supported = self._is_game_supported_for_wiki(game_context)
            
            # 如果既不支持RAG攻略查询，也不支持wiki查询，直接返回不支持
            if not game_name and not is_wiki_supported:
                logger.info(f"📋 窗口 '{game_context}' 不支持攻略查询")
                return QueryIntent(
                    intent_type='unsupported',
                    confidence=1.0,
                    rewritten_query=query,
                    translated_query=query
                )
        else:
            # 如果没有游戏上下文（未记录游戏窗口），跳过统一查询处理
            logger.info("📋 未记录游戏窗口，跳过统一查询处理，使用简单意图检测")
            return self._simple_intent_detection(query)
        
        if not process_query_unified:
            # Fallback to simple detection
            logger.warning("统一查询处理器不可用，使用简单意图检测")
            return self._simple_intent_detection(query)
            
        try:
            # 使用存储的LLM配置，如果没有则创建临时配置
            llm_config = self._llm_config
            if not llm_config:
                # 如果没有存储的配置，创建临时配置并检查API密钥
                llm_config = LLMConfig(
                    model='gemini-2.5-flash-lite-preview-06-17'
                )
                
                # 使用LLMConfig的get_api_key方法获取API密钥（支持GEMINI_API_KEY环境变量）
                api_key = llm_config.get_api_key()
                if not api_key:
                    logger.warning("GEMINI_API_KEY未配置，使用简单意图检测")
                    return self._simple_intent_detection(query)
                    
                # 更新配置中的API密钥
                llm_config.api_key = api_key
            else:
                # 使用存储的配置，验证API密钥
                api_key = llm_config.get_api_key()
                if not api_key:
                    logger.warning("存储的LLM配置中没有有效的API密钥，使用简单意图检测")
                    return self._simple_intent_detection(query)
            
            # 使用统一查询处理器进行处理（合并了翻译、重写、意图判断）
            result = await asyncio.to_thread(
                process_query_unified,
                query,
                llm_config=llm_config
            )
            
            logger.info(f"统一处理成功: '{query}' -> 意图: {result.intent} (置信度: {result.confidence:.3f})")
            logger.info(f"  翻译结果: '{result.translated_query}'")
            logger.info(f"  重写结果: '{result.rewritten_query}'")
            logger.info(f"  BM25优化: '{result.bm25_optimized_query}'")
            
            return QueryIntent(
                intent_type=result.intent,
                confidence=result.confidence,
                rewritten_query=result.rewritten_query,
                translated_query=result.translated_query,  # 添加翻译后的查询
                unified_query_result=result  # 传递完整的统一查询结果
            )
            
        except Exception as e:
            logger.error(f"统一查询处理失败: {e}")
            return self._simple_intent_detection(query)
            
    def _is_game_supported_for_wiki(self, window_title: str) -> bool:
        """检查游戏窗口是否支持wiki查询（基于games.json配置）"""
        try:
            # 获取游戏配置
            if hasattr(self, 'game_cfg_mgr') and self.game_cfg_mgr:
                game_config = self.game_cfg_mgr.for_title(window_title)
                if game_config:
                    logger.info(f"🎮 窗口 '{window_title}' 在games.json中找到配置，支持wiki查询")
                    return True
            
            logger.info(f"📋 窗口 '{window_title}' 未在games.json中找到配置")
            return False
        except Exception as e:
            logger.error(f"检查游戏配置时出错: {e}")
            return False
            
    def _simple_intent_detection(self, query: str) -> QueryIntent:
        """Simple keyword-based intent detection"""
        # 如果在受限模式下，始终返回wiki意图
        if self.limited_mode:
            return QueryIntent(
                intent_type='wiki',
                confidence=0.9,
                rewritten_query=query,
                translated_query=query
            )
            
        query_lower = query.lower()
        
        # Wiki intent keywords
        wiki_keywords = ['是什么', '什么是', 'what is', 'wiki', '介绍', 'info']
        # Guide intent keywords  
        guide_keywords = ['怎么', '如何', 'how to', '攻略', 'guide', '推荐', 'best']
        
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
        """准备wiki搜索，返回搜索URL和初始标题，真实URL将通过JavaScript回调获取"""
        try:
            from urllib.parse import quote, urlparse
            
            # 使用传入的游戏上下文，如果没有则获取当前游戏窗口标题
            game_title = game_context or get_selected_game_title()
            logger.info(f"🎮 当前游戏窗口标题: {game_title}")
            
            # 查找游戏配置 - 使用实例变量
            game_config = self.game_cfg_mgr.for_title(game_title)
            
            if not game_config:
                logger.warning(f"未找到游戏配置: {game_title}")
                # 回退到通用搜索
                search_query = f"{game_title} {query} wiki"
                ddg_url = f"https://duckduckgo.com/?q=!ducky+{quote(search_query)}"
                # 存储待更新的wiki信息（标记为DuckDuckGo搜索）
                self._pending_wiki_update = {
                    "initial_url": ddg_url,
                    "query": query,
                    "title": f"搜索: {query}",
                    "status": "searching"
                }
            else:
                logger.info(f"找到游戏配置: {game_config}")
                
                # 获取基础URL
                base_url = game_config.BaseUrl
                logger.info(f"游戏基础URL: {base_url}")
                
                # 提取域名
                if base_url.startswith(('http://', 'https://')):
                    domain = urlparse(base_url).hostname or ''
                else:
                    # 如果没有协议前缀，直接使用base_url作为域名
                    domain = base_url.split('/')[0]  # 移除路径部分
                
                logger.info(f"提取的域名: {domain}")
                
                # 构建正确的搜索查询：site:域名 用户查询
                search_query = f"site:{domain} {query}"
                ddg_url = f"https://duckduckgo.com/?q=!ducky+{quote(search_query)}"
                
                logger.info(f"构建的搜索查询: {search_query}")
                logger.info(f"DuckDuckGo URL: {ddg_url}")
                
                # 存储待更新的wiki信息
                self._pending_wiki_update = {
                    "initial_url": ddg_url,
                    "query": query,
                    "title": f"搜索: {query}",
                    "domain": domain,
                    "status": "searching"
                }
            
            # 返回搜索URL和临时标题，真实URL将通过JavaScript回调更新
            return ddg_url, f"搜索: {query}"
                    
        except Exception as e:
            logger.error(f"Wiki search preparation failed: {e}")
            return "", query
            
    async def search_wiki_async(self, query: str, game_context: str = None) -> tuple[str, str]:
        """Search for wiki page"""
        # Use existing wiki search logic from overlay.py
        try:
            import aiohttp
            from urllib.parse import quote, urlparse
            
            # 使用传入的游戏上下文，如果没有则获取当前游戏窗口标题
            game_title = game_context or get_selected_game_title()
            logger.info(f"🎮 当前游戏窗口标题: {game_title}")
            
            # 查找游戏配置 - 使用实例变量
            game_config = self.game_cfg_mgr.for_title(game_title)
            
            if not game_config:
                logger.warning(f"未找到游戏配置: {game_title}")
                # 回退到通用搜索
                search_query = f"{game_title} {query} wiki"
                ddg_url = f"https://duckduckgo.com/?q=!ducky+{quote(search_query)}"
            else:
                logger.info(f"找到游戏配置: {game_config}")
                
                # 获取基础URL
                base_url = game_config.BaseUrl
                logger.info(f"游戏基础URL: {base_url}")
                
                # 提取域名
                if base_url.startswith(('http://', 'https://')):
                    domain = urlparse(base_url).hostname or ''
                else:
                    # 如果没有协议前缀，直接使用base_url作为域名
                    domain = base_url.split('/')[0]  # 移除路径部分
                
                logger.info(f"提取的域名: {domain}")
                
                # 构建正确的搜索查询：site:域名 用户查询
                search_query = f"site:{domain} {query}"
                ddg_url = f"https://duckduckgo.com/?q=!ducky+{quote(search_query)}"
                
                logger.info(f"构建的搜索查询: {search_query}")
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
        """当JavaScript找到真实wiki页面时调用此方法"""
        if self._pending_wiki_update:
            logger.info(f"📄 JavaScript找到真实wiki页面: {real_url}")
            
            # 提取页面标题（如果没有提供）
            if not real_title:
                # 从URL提取标题
                try:
                    from urllib.parse import unquote
                    parts = real_url.split('/')
                    if parts:
                        real_title = unquote(parts[-1]).replace('_', ' ')
                    else:
                        real_title = self._pending_wiki_update.get("query", "Wiki页面")
                except:
                    real_title = self._pending_wiki_update.get("query", "Wiki页面")
            
            # 更新待处理的wiki信息
            self._pending_wiki_update.update({
                "real_url": real_url,
                "real_title": real_title,
                "status": "found"
            })
            
            # 发出信号更新聊天窗口中的链接
            self.wiki_link_updated.emit(real_url, real_title)
            logger.info(f"✅ 已发出wiki链接更新信号: {real_title} -> {real_url}")
            
            # 清除待更新信息
            self._pending_wiki_update = None
        else:
            logger.warning("⚠️ 收到wiki页面回调，但没有待更新的wiki信息")
            
    async def generate_guide_async(self, query: str, game_context: str = None, original_query: str = None, skip_query_processing: bool = False, unified_query_result = None, stop_flag = None):
        """Generate guide response with streaming
        
        Args:
            query: 处理后的查询文本
            game_context: 游戏上下文
            original_query: 原始查询（用于答案生成）
            skip_query_processing: 是否跳过RAG内部的查询处理
            unified_query_result: 预处理的统一查询结果（来自process_query_unified）
        """
        # 如果在受限模式下，显示相应的提示信息
        if self.limited_mode:
            logger.info("🚨 受限模式下，AI攻略功能不可用")
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
            # 尝试为指定游戏初始化RAG引擎
            if game_context:
                from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name
                vector_game_name = map_window_title_to_game_name(game_context)
                
                if vector_game_name:
                    logger.info(f"RAG engine not initialized, attempting to initialize for game '{vector_game_name}'")
                    
                    # 获取API设置
                    settings = self.settings_manager.get()
                    api_settings = settings.get('api', {})
                    gemini_api_key = api_settings.get('gemini_api_key', '')
                    jina_api_key = api_settings.get('jina_api_key', '')
                    
                    # 检查环境变量
                    if not gemini_api_key:
                        gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
                    if not jina_api_key:
                        jina_api_key = os.getenv('JINA_API_KEY')
                    
                    # 检查是否同时有两个API key
                    has_both_keys = bool(gemini_api_key and jina_api_key)
                    
                    if has_both_keys:
                        llm_config = LLMConfig(
                            api_key=gemini_api_key,
                            model='gemini-2.5-flash-lite-preview-06-17'
                        )
                        self._init_rag_for_game(vector_game_name, llm_config, jina_api_key, wait_for_init=True)
                        
                        if not self.rag_engine:
                            # 检查是否是向量库不存在的问题
                            logger.info(f"📋 游戏 '{vector_game_name}' 的向量库不存在，提供降级方案")
                            
                            # 使用国际化的错误信息
                            from src.game_wiki_tooltip.i18n import t, get_current_language
                            current_lang = get_current_language()
                            
                            if current_lang == 'zh':
                                error_msg = (
                                    f"🎮 游戏 '{game_context}' 暂时没有攻略数据库\n\n"
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
                        
                        # 使用国际化的错误信息
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
                    logger.info(f"📋 窗口 '{game_context}' 不支持攻略查询")
                    
                    # 使用国际化的错误信息
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
            logger.info(f"🔍 直接使用处理后的查询进行RAG搜索: '{query}'")
            if original_query:
                logger.info(f"📝 同时使用原始查询进行答案生成: '{original_query}'")
            if skip_query_processing:
                logger.info("⚡ 跳过RAG内部查询处理，使用已优化的查询")
            if unified_query_result:
                logger.info(f"🔄 传递预处理的统一查询结果，避免重复处理")
                logger.info(f"   - BM25优化查询: '{unified_query_result.bm25_optimized_query}'")
            
            # 直接使用流式RAG查询，在流式过程中处理所有逻辑
            logger.info("🌊 使用流式RAG查询")
            stream_generator = None
            try:
                has_output = False
                # 获取流式生成器
                stream_generator = self.rag_engine.query_stream(
                    question=query, 
                    top_k=3, 
                    original_query=original_query,
                    unified_query_result=unified_query_result
                )
                
                # 使用真正的流式API
                async for chunk in stream_generator:
                    # 检查是否被请求停止
                    if stop_flag and stop_flag():
                        logger.info("🛑 检测到停止请求，中断流式生成")
                        break
                        
                    # 确保chunk是字符串类型
                    if isinstance(chunk, dict):
                        logger.warning(f"收到字典类型的chunk，跳过: {chunk}")
                        continue
                    
                    chunk_str = str(chunk) if chunk is not None else ""
                    if chunk_str.strip():  # 只发送非空内容
                        has_output = True
                        self.streaming_chunk_ready.emit(chunk_str)
                        await asyncio.sleep(0.01)  # 很短的延迟以保持UI响应性
                
                # 如果没有任何输出，可能需要切换到wiki模式
                if not has_output:
                    logger.info(f"🔄 RAG查询无输出，可能需要切换到wiki模式: '{query}'")
                    
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
                        logger.error(f"自动Wiki搜索失败: {wiki_error}")
                        if current_lang == 'zh':
                            self.streaming_chunk_ready.emit("❌ 自动Wiki搜索失败，请手动点击Wiki搜索按钮\n")
                        else:
                            self.streaming_chunk_ready.emit("❌ Auto Wiki search failed, please click Wiki search button manually\n")
                    return
                
                logger.info("✅ 流式RAG查询完成")
                return
                    
            except Exception as e:
                # 处理特定的RAG错误类型
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
                    # 通用错误 - 尝试自动切换到wiki模式
                    logger.error(f"流式RAG查询失败: {e}")
                    logger.info("尝试自动切换到Wiki搜索模式...")
                    
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
                        logger.error(f"自动Wiki搜索也失败: {wiki_error}")
                        if current_lang == 'zh':
                            error_msg = f"❌ AI攻略查询失败，Wiki搜索也失败了。请稍后重试。\n错误详情: {str(e)}"
                        else:
                            error_msg = f"❌ AI guide query failed, and Wiki search also failed. Please try again later.\nError details: {str(e)}"
                    
                # 发送错误信息（对于特定错误类型或wiki搜索失败的情况）
                if 'error_msg' in locals():
                    logger.error(f"发送错误信息到聊天窗口: {error_msg}")
                    self.streaming_chunk_ready.emit(error_msg)
                return
            finally:
                # 确保异步生成器正确关闭
                if stream_generator is not None:
                    try:
                        await stream_generator.aclose()
                        logger.debug("异步生成器已正确关闭")
                    except Exception as close_error:
                        logger.warning(f"关闭异步生成器时出错: {close_error}")
                    
        except Exception as e:
            logger.error(f"Guide generation failed: {e}")
            self.error_occurred.emit(f"Guide generation failed: {str(e)}")


class IntegratedAssistantController(AssistantController):
    """Enhanced assistant controller with RAG integration"""
    
    # 类级别的全局实例引用
    _global_instance = None
    
    def __init__(self, settings_manager: SettingsManager, limited_mode: bool = False):
        super().__init__(settings_manager)
        self.limited_mode = limited_mode
        self.rag_integration = RAGIntegration(settings_manager, limited_mode=limited_mode)
        self._setup_connections()
        self._current_worker = None
        self._current_wiki_message = None  # 存储当前的wiki链接消息组件
        
        # 注册为全局实例
        IntegratedAssistantController._global_instance = self
        logger.info(f"🌐 已注册为全局assistant controller实例 (limited_mode={limited_mode})")
        
        # 如果是受限模式，显示提示信息
        if limited_mode:
            logger.info("🚨 运行在受限模式下：仅支持Wiki搜索功能")
        else:
            logger.info("✅ 运行在完整模式下：支持Wiki搜索和AI攻略功能")
        
    def __del__(self):
        """析构函数，清理全局实例引用"""
        if IntegratedAssistantController._global_instance is self:
            IntegratedAssistantController._global_instance = None
            logger.info("🌐 已清理全局assistant controller实例引用")
        
    def set_current_game_window(self, game_window_title: str):
        """重写父类方法，设置当前游戏窗口并处理RAG引擎初始化"""
        super().set_current_game_window(game_window_title)
        
        # 检查是否需要初始化或切换RAG引擎
        from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name
        vector_game_name = map_window_title_to_game_name(game_window_title)
        
        if vector_game_name:
            logger.info(f"🎮 检测到游戏窗口，准备初始化RAG引擎: {vector_game_name}")
            # 检查是否需要切换游戏
            if not hasattr(self, '_current_vector_game') or self._current_vector_game != vector_game_name:
                logger.info(f"🔄 切换RAG引擎: {getattr(self, '_current_vector_game', 'None')} -> {vector_game_name}")
                self._current_vector_game = vector_game_name
                self._reinitialize_rag_for_game(vector_game_name)
            else:
                logger.info(f"✓ 游戏未切换，继续使用当前RAG引擎: {vector_game_name}")
        else:
            logger.info(f"⚠️ 窗口 '{game_window_title}' 不是支持的游戏")
        
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
        
        # 检查RAG引擎初始化状态
        if getattr(self, '_rag_initializing', False):
            # RAG引擎正在初始化中，显示等待状态
            from src.game_wiki_tooltip.i18n import t
            logger.info("🔄 RAG引擎正在初始化中，显示等待提示")
            self.main_window.chat_view.show_status(t("rag_initializing"))
            
            # 延迟处理查询，定期检查初始化状态
            self._pending_query = query
            self._check_rag_init_status()
            return
        
        # RAG引擎已准备好，正常处理查询
        self._process_query_immediately(query)
        
    def _check_rag_init_status(self):
        """定期检查RAG初始化状态"""
        from src.game_wiki_tooltip.i18n import t
        
        if hasattr(self.rag_integration, '_rag_init_complete') and self.rag_integration._rag_init_complete:
            # 初始化完成
            logger.info("✅ RAG引擎初始化完成，开始处理查询")
            self._rag_initializing = False
            self.main_window.chat_view.hide_status()
            
            # 处理等待中的查询
            if hasattr(self, '_pending_query'):
                self._process_query_immediately(self._pending_query)
                delattr(self, '_pending_query')
        elif hasattr(self.rag_integration, '_rag_init_complete') and self.rag_integration._rag_init_complete is False:
            # 初始化失败
            logger.error("❌ RAG引擎初始化失败")
            self._rag_initializing = False
            self.main_window.chat_view.hide_status()
            
            # 显示错误信息
            if hasattr(self.rag_integration, '_rag_init_error'):
                error_msg = self.rag_integration._rag_init_error
                logger.error(f"RAG初始化错误详情: {error_msg}")
                # 将错误发送到聊天窗口
                self.main_window.chat_view.add_message(
                    MessageType.AI_RESPONSE,
                    f"{t('rag_init_failed')}: {error_msg}"
                )
            else:
                # 通用错误信息
                self.main_window.chat_view.add_message(
                    MessageType.AI_RESPONSE,
                    t("rag_init_failed")
                )
            
            # 清理等待中的查询
            if hasattr(self, '_pending_query'):
                delattr(self, '_pending_query')
        else:
            # 继续等待，每500ms检查一次，最多等待10秒
            if not hasattr(self, '_rag_init_start_time'):
                import time
                self._rag_init_start_time = time.time()
            
            import time
            if time.time() - self._rag_init_start_time > 10:  # 超时10秒
                logger.warning("RAG初始化超时")
                self._rag_initializing = False
                self.main_window.chat_view.hide_status()
                
                # 显示超时错误
                self.main_window.chat_view.add_message(
                    MessageType.ERROR,
                    f"{t('rag_init_failed')}: 初始化超时"
                )
                
                # 清理
                if hasattr(self, '_pending_query'):
                    delattr(self, '_pending_query')
                if hasattr(self, '_rag_init_start_time'):
                    delattr(self, '_rag_init_start_time')
            else:
                # 继续等待
                QTimer.singleShot(500, self._check_rag_init_status)
            
    def _process_query_immediately(self, query: str):
        """立即处理查询（RAG引擎已准备好）"""
        # Stop any existing worker and reset UI state
        if self._current_worker and self._current_worker.isRunning():
            logger.info("🛑 新查询开始，停止上一次的生成")
            self._current_worker.stop()
            self._current_worker.wait()
            
            # 如果有当前的流式消息，标记为已停止
            if hasattr(self, '_current_streaming_msg') and self._current_streaming_msg:
                self._current_streaming_msg.mark_as_stopped()
                
            # 重置UI状态
            if self.main_window:
                self.main_window.set_generating_state(False)
                logger.info("🛑 UI状态已重置为非生成状态")
            
        # 断开RAG integration的所有信号连接，防止重复
        try:
            self.rag_integration.streaming_chunk_ready.disconnect()
        except:
            pass  # 如果没有连接，忽略错误
            
        # 使用已记录的游戏窗口标题（在热键触发时记录）
        if hasattr(self, 'current_game_window') and self.current_game_window:
            logger.info(f"🎮 使用已记录的游戏窗口: '{self.current_game_window}'")
        else:
            logger.warning("⚠️ 未记录游戏窗口，可能是程序异常状态")
        
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
        
        # 重新连接RAG integration的信号到当前worker
        self.rag_integration.streaming_chunk_ready.connect(
            self._on_streaming_chunk  # 直接连接到处理方法，而不是worker的信号
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
        
        # 连接完成信号
        self._current_streaming_msg.streaming_finished.connect(self._on_streaming_finished)
        
        # 设置UI为生成状态
        if self.main_window:
            self.main_window.set_generating_state(True, self._current_streaming_msg)
            logger.info("🔄 UI已设置为生成状态")
        
    def _on_wiki_result_from_worker(self, url: str, title: str):
        """Handle wiki result from worker"""
        try:
            if url:
                # Update transition message
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.WIKI_FOUND)
                
                # Add wiki link message (初始显示搜索URL)
                self._current_wiki_message = self.main_window.chat_view.add_message(
                    MessageType.WIKI_LINK,
                    title,
                    {"url": url}
                )
                
                # Show wiki page in the unified window (会触发JavaScript搜索真实URL)
                self.main_window.show_wiki_page(url, title)
            else:
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.ERROR_NOT_FOUND)
                    
        except Exception as e:
            logger.error(f"Wiki result handling error: {e}")
            self._on_error(str(e))
            
    def _on_wiki_link_updated(self, real_url: str, real_title: str):
        """处理wiki链接更新信号"""
        try:
            if self._current_wiki_message:
                logger.info(f"🔗 更新聊天窗口中的wiki链接: {real_title} -> {real_url}")
                
                # 更新消息内容和元数据
                self._current_wiki_message.message.content = real_title
                self._current_wiki_message.message.metadata["url"] = real_url
                
                # 重新设置内容以刷新显示 - 修复：使用真实标题而不是旧内容
                html_content = (
                    f'[LINK] <a href="{real_url}" style="color: #4096ff;">{real_url}</a><br/>'
                    f'<span style="color: #666; margin-left: 20px;">{real_title}</span>'
                )
                self._current_wiki_message.content_label.setText(html_content)
                self._current_wiki_message.content_label.setTextFormat(Qt.TextFormat.RichText)
                
                # 调整组件大小以适应新内容
                self._current_wiki_message.content_label.adjustSize()
                self._current_wiki_message.adjustSize()
                
                # 强制重绘
                self._current_wiki_message.update()
                
                logger.info(f"✅ 聊天窗口wiki链接已更新为真实URL和标题")
                
                # 只有当标题包含有意义的内容时才清除引用（避免过早清除导致后续更新失效）
                # 检查标题是否是临时的加载状态
                temporary_titles = ["请稍候…", "Loading...", "Redirecting...", ""]
                if real_title and real_title not in temporary_titles:
                    # 延迟清除引用，允许可能的后续更新
                    QTimer.singleShot(2000, lambda: setattr(self, '_current_wiki_message', None))
                    logger.info(f"📋 延迟清除wiki消息引用，标题: '{real_title}'")
                else:
                    logger.info(f"📋 保持wiki消息引用，等待更完整的标题（当前: '{real_title}'）")
                    
            else:
                logger.warning("⚠️ 没有找到要更新的wiki消息组件")
                
        except Exception as e:
            logger.error(f"❌ 更新wiki链接失败: {e}")
            
    def _on_guide_chunk(self, chunk: str):
        """Handle guide chunk from worker"""
        if hasattr(self, '_current_streaming_msg'):
            self._current_streaming_msg.append_chunk(chunk)
            
    def _on_streaming_chunk(self, chunk: str):
        """Handle streaming chunk from RAG"""
        if hasattr(self, '_current_streaming_msg'):
            self._current_streaming_msg.append_chunk(chunk)
    
    def _on_streaming_finished(self):
        """处理流式输出完成"""
        logger.info("✅ 流式输出已完成")
        
        # 重置UI状态
        if self.main_window:
            self.main_window.set_generating_state(False)
            logger.info("✅ UI状态已重置为非生成状态")
            
    def _on_wiki_result(self, url: str, title: str):
        """Handle wiki search result from RAG integration"""
        try:
            if url:
                # Update transition message
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.WIKI_FOUND)
                
                # Add wiki link message (初始显示搜索URL)
                self._current_wiki_message = self.main_window.chat_view.add_message(
                    MessageType.WIKI_LINK,
                    title,
                    {"url": url}
                )
                
                # Show wiki page in the unified window (会触发JavaScript搜索真实URL)
                self.main_window.show_wiki_page(url, title)
            else:
                if hasattr(self, '_current_transition_msg'):
                    self._current_transition_msg.update_content(TransitionMessages.ERROR_NOT_FOUND)
                    
        except Exception as e:
            logger.error(f"Wiki result handling error: {e}")
            self._on_error(str(e))
        
    def _on_error(self, error_msg: str):
        """Handle error"""
        self.main_window.chat_view.add_message(
            MessageType.AI_RESPONSE,
            f"❌ {error_msg}"
        )
        
    def _reinitialize_rag_for_game(self, vector_game_name: str):
        """重新初始化RAG引擎为特定向量库（异步，不阻塞UI）"""
        try:
            logger.info(f"🚀 开始为向量库 '{vector_game_name}' 重新初始化RAG引擎（异步模式）")
            
            # 获取API设置
            settings = self.settings_manager.get()
            api_settings = settings.get('api', {})
            gemini_api_key = api_settings.get('gemini_api_key', '')
            jina_api_key = api_settings.get('jina_api_key', '')
            
            # 检查环境变量
            if not gemini_api_key:
                gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
            if not jina_api_key:
                jina_api_key = os.getenv('JINA_API_KEY')
            
            # 检查是否同时有两个API key
            has_both_keys = bool(gemini_api_key and jina_api_key)
            
            if has_both_keys:
                llm_config = LLMConfig(
                    api_key=gemini_api_key,
                    model='gemini-2.5-flash-lite-preview-06-17'
                )
                
                # 更新存储的LLM配置
                self._llm_config = llm_config
                
                # 异步初始化RAG引擎（不等待完成）
                self.rag_integration._init_rag_for_game(vector_game_name, llm_config, jina_api_key, wait_for_init=False)
                logger.info(f"🔄 RAG引擎初始化已启动（异步）: {vector_game_name}")
                
                # 标记RAG引擎正在初始化
                self._rag_initializing = True
                self._target_vector_game = vector_game_name
            else:
                logger.warning(f"⚠️ API密钥不完整，无法初始化RAG引擎 (Gemini: {bool(gemini_api_key)}, Jina: {bool(jina_api_key)})")
                
        except Exception as e:
            logger.error(f"RAG引擎重新初始化失败: {e}")
            self._rag_initializing = False
            
    def on_wiki_page_found(self, real_url: str, real_title: str = None):
        """当webview中的JavaScript找到真实wiki页面时调用"""
        logger.info(f"🌐 收到webview的wiki页面回调: {real_url}")
        self.rag_integration.on_wiki_found(real_url, real_title)
        
    def handle_wiki_page_found(self, url: str, title: str):
        """重写父类方法：处理WikiView发现真实wiki页面的信号"""
        logger.info(f"🔗 IntegratedAssistantController收到WikiView信号: {title} -> {url}")
        
        # 过滤掉明显的临时状态标题，只处理有意义的更新
        if title and title not in ["请稍候…", "Loading...", "Redirecting...", ""]:
            logger.info(f"✅ 接受wiki页面更新：{title}")
            # 直接调用RAG integration的方法来处理wiki页面发现
            self.rag_integration.on_wiki_found(url, title)
        else:
            logger.info(f"⏳ 跳过临时状态的wiki页面更新：{title}")
            # 对于临时状态，仍然调用，但不会触发聊天窗口的最终更新
            
    def expand_to_chat(self):
        """重写expand_to_chat方法以连接停止信号"""
        # 调用父类的expand_to_chat方法
        super().expand_to_chat()
        
        # 连接停止生成信号
        if self.main_window and hasattr(self.main_window, 'stop_generation_requested'):
            self.main_window.stop_generation_requested.connect(self.stop_current_generation)
            logger.info("✅ 已连接停止生成信号")
    
    def stop_current_generation(self):
        """停止当前的生成过程"""
        logger.info("🛑 收到停止生成请求")
        
        # 停止当前的worker
        if self._current_worker and self._current_worker.isRunning():
            logger.info("🛑 停止当前QueryWorker")
            self._current_worker.stop()
            # 不等待worker结束，让它异步结束
            
        # 恢复UI状态
        if self.main_window:
            self.main_window.set_generating_state(False)
            logger.info("🛑 UI状态已恢复为非生成状态")
    
    def switch_game(self, game_name: str):
        """Switch to a different game (game_name应该是窗口标题)"""
        # Stop current worker
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.stop()
            self._current_worker.wait()
            
        # 先映射窗口标题到向量库名称
        from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name
        vector_game_name = map_window_title_to_game_name(game_name)
        
        if vector_game_name:
            logger.info(f"🔄 手动切换游戏: '{game_name}' -> 向量库: {vector_game_name}")
            # 使用映射后的向量库名称重新初始化
            self._reinitialize_rag_for_game(vector_game_name)
        else:
            logger.warning(f"⚠️ 游戏 '{game_name}' 不支持，无法切换RAG引擎")