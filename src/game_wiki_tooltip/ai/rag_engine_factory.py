"""
RAG引擎工厂
============

提供统一的RAG引擎创建和管理，确保相同配置产生相同的引擎实例
"""

import asyncio
import logging
from typing import Dict, Optional
from threading import Lock

from .rag_query import EnhancedRagQuery
from .rag_config import RAGConfig, get_global_rag_config
from ..config import LLMConfig

logger = logging.getLogger(__name__)


class RAGEngineFactory:
    """RAG引擎工厂，管理引擎实例的创建和缓存"""
    
    # 引擎缓存：{game_name: engine_instance}
    _engine_cache: Dict[str, EnhancedRagQuery] = {}
    _cache_lock = Lock()
    
    @classmethod
    async def get_engine(
        cls,
        game_name: str,
        config: Optional[RAGConfig] = None,
        llm_config: Optional[LLMConfig] = None,
        force_new: bool = False
    ) -> EnhancedRagQuery:
        """
        获取或创建RAG引擎实例
        
        Args:
            game_name: 游戏名称
            config: RAG配置，如果为None则使用全局默认配置
            llm_config: LLM配置，如果为None则创建新实例
            force_new: 是否强制创建新实例
            
        Returns:
            初始化好的RAG引擎实例
        """
        # 使用默认配置
        if config is None:
            config = get_global_rag_config()
        
        if llm_config is None:
            llm_config = LLMConfig()
        
        # 生成缓存键
        cache_key = f"{game_name}"
        
        # 如果不强制创建新实例，尝试从缓存获取
        if not force_new:
            with cls._cache_lock:
                if cache_key in cls._engine_cache:
                    logger.info(f"从缓存返回RAG引擎: {game_name}")
                    return cls._engine_cache[cache_key]
        
        # 创建新引擎
        logger.info(f"创建新的RAG引擎: {game_name}")
        engine = await cls._create_engine(game_name, config, llm_config)
        
        # 缓存引擎实例
        with cls._cache_lock:
            cls._engine_cache[cache_key] = engine
        
        return engine
    
    @classmethod
    async def _create_engine(
        cls,
        game_name: str,
        config: RAGConfig,
        llm_config: LLMConfig
    ) -> EnhancedRagQuery:
        """
        创建并初始化RAG引擎
        
        Args:
            game_name: 游戏名称
            config: RAG配置
            llm_config: LLM配置
            
        Returns:
            初始化好的RAG引擎实例
        """
        # 创建引擎实例
        engine = EnhancedRagQuery(
            enable_summarization=config.enable_summarization,
            enable_hybrid_search=config.enable_hybrid_search,
            enable_intent_reranking=config.enable_intent_reranking,
            enable_query_rewrite=config.enable_query_rewrite,
            hybrid_config=config.hybrid_config,
            summarization_config=config.summarization_config,
            reranking_config=config.reranking_config,
            llm_config=llm_config
        )
        
        # 初始化引擎
        await engine.initialize(game_name=game_name)
        
        return engine
    
    @classmethod
    def clear_cache(cls, game_name: Optional[str] = None) -> None:
        """
        清除引擎缓存
        
        Args:
            game_name: 要清除的游戏名称，如果为None则清除所有缓存
        """
        with cls._cache_lock:
            if game_name:
                cache_key = f"{game_name}"
                if cache_key in cls._engine_cache:
                    logger.info(f"清除RAG引擎缓存: {game_name}")
                    del cls._engine_cache[cache_key]
            else:
                logger.info("清除所有RAG引擎缓存")
                cls._engine_cache.clear()
    
    @classmethod
    async def create_for_evaluation(
        cls,
        game_name: str,
        llm_config: Optional[LLMConfig] = None
    ) -> EnhancedRagQuery:
        """
        为评估创建RAG引擎（使用evaluation配置）
        
        Args:
            game_name: 游戏名称
            llm_config: LLM配置
            
        Returns:
            配置好的RAG引擎实例
        """
        config = RAGConfig.get_evaluation_config()
        return await cls.get_engine(
            game_name=game_name,
            config=config,
            llm_config=llm_config,
            force_new=True  # 评估时总是创建新实例
        )
    
    @classmethod
    async def create_for_searchbar(
        cls,
        game_name: str,
        llm_config: Optional[LLMConfig] = None
    ) -> EnhancedRagQuery:
        """
        为searchbar创建RAG引擎（使用searchbar配置）
        
        Args:
            game_name: 游戏名称
            llm_config: LLM配置
            
        Returns:
            配置好的RAG引擎实例
        """
        config = RAGConfig.get_searchbar_config()
        return await cls.get_engine(
            game_name=game_name,
            config=config,
            llm_config=llm_config,
            force_new=False  # searchbar可以复用缓存的实例
        )


# 便捷函数
async def get_rag_engine(
    game_name: str,
    use_case: str = "searchbar",
    llm_config: Optional[LLMConfig] = None
) -> EnhancedRagQuery:
    """
    获取RAG引擎的便捷函数
    
    Args:
        game_name: 游戏名称
        use_case: 使用场景 ("searchbar" 或 "evaluation")
        llm_config: LLM配置
        
    Returns:
        配置好的RAG引擎实例
    """
    if use_case == "evaluation":
        return await RAGEngineFactory.create_for_evaluation(game_name, llm_config)
    else:
        return await RAGEngineFactory.create_for_searchbar(game_name, llm_config)