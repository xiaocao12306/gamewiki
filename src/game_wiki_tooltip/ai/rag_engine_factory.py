"""
RAG引擎工厂类 - 统一创建和管理RAG引擎实例
==========================================

提供统一的接口创建高质量的RAG引擎，确保所有组件使用相同的配置和流程。
"""

import logging
from typing import Optional, Dict, Any, Union
from pathlib import Path
import asyncio

from .rag_config import RAGConfig, get_default_config, get_evaluation_config
from .rag_query import EnhancedRagQuery, query_enhanced_rag
from ..config import LLMConfig

logger = logging.getLogger(__name__)


class RAGEngineFactory:
    """
    RAG引擎工厂类
    
    统一创建和管理RAG引擎实例，确保evaluator和searchbar使用相同的高质量RAG系统。
    """
    
    _instances: Dict[str, EnhancedRagQuery] = {}  # 缓存引擎实例
    
    @classmethod
    def create_engine(
        cls,
        game_name: Optional[str] = None,
        config: Optional[RAGConfig] = None,
        llm_config: Optional[LLMConfig] = None,
        use_cache: bool = True
    ) -> EnhancedRagQuery:
        """
        创建RAG引擎实例
        
        Args:
            game_name: 游戏名称，用于查找对应的向量库
            config: RAG配置，如果为None则使用默认配置
            llm_config: LLM配置
            use_cache: 是否使用缓存的引擎实例
            
        Returns:
            配置好的RAG引擎实例
        """
        # 使用默认配置
        if config is None:
            config = get_default_config()
        
        # 创建缓存键
        cache_key = f"{game_name or 'default'}_{hash(str(config.to_dict()))}"
        
        # 检查缓存
        if use_cache and cache_key in cls._instances:
            logger.info(f"使用缓存的RAG引擎实例: {cache_key}")
            return cls._instances[cache_key]
        
        # 创建新的引擎实例
        logger.info(f"创建新的RAG引擎实例: 游戏={game_name}")
        
        engine = EnhancedRagQuery(
            vector_store_path=None,  # 将在初始化时自动查找
            enable_hybrid_search=config.hybrid_search.enabled,
            hybrid_config=config.hybrid_search.to_dict(),
            llm_config=llm_config or LLMConfig(),
            enable_query_rewrite=config.query_processing.enable_query_rewrite,
            enable_summarization=config.summarization.enabled,
            summarization_config=config.summarization.to_dict(),
            enable_intent_reranking=config.intent_reranking.enabled,
            reranking_config=config.intent_reranking.to_dict()
        )
        
        # 缓存实例
        if use_cache:
            cls._instances[cache_key] = engine
        
        return engine
    
    @classmethod
    async def create_and_initialize_engine(
        cls,
        game_name: Optional[str] = None,
        config: Optional[RAGConfig] = None,
        llm_config: Optional[LLMConfig] = None,
        use_cache: bool = True
    ) -> EnhancedRagQuery:
        """
        创建并初始化RAG引擎（异步版本）
        
        Args:
            game_name: 游戏名称
            config: RAG配置
            llm_config: LLM配置
            use_cache: 是否使用缓存
            
        Returns:
            初始化完成的RAG引擎实例
        """
        engine = cls.create_engine(game_name, config, llm_config, use_cache)
        
        # 初始化引擎
        await engine.initialize(game_name)
        
        return engine
    
    @classmethod
    def create_evaluation_engine(
        cls,
        game_name: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None
    ) -> EnhancedRagQuery:
        """
        创建用于评估的RAG引擎（不使用缓存）
        
        Args:
            game_name: 游戏名称
            llm_config: LLM配置
            
        Returns:
            配置用于评估的RAG引擎实例
        """
        config = get_evaluation_config()
        return cls.create_engine(game_name, config, llm_config, use_cache=False)
    
    @classmethod
    async def query_with_engine(
        cls,
        question: str,
        game_name: Optional[str] = None,
        config: Optional[RAGConfig] = None,
        llm_config: Optional[LLMConfig] = None,
        use_cached_engine: bool = True
    ) -> Dict[str, Any]:
        """
        使用工厂创建的引擎执行查询
        
        Args:
            question: 用户问题
            game_name: 游戏名称
            config: RAG配置
            llm_config: LLM配置
            use_cached_engine: 是否使用缓存的引擎
            
        Returns:
            查询结果
        """
        # 创建并初始化引擎
        engine = await cls.create_and_initialize_engine(
            game_name, config, llm_config, use_cached_engine
        )
        
        # 使用配置执行查询
        if config is None:
            config = get_default_config()
        
        # 执行查询
        if not engine.is_initialized:
            logger.warning("引擎未初始化，使用降级查询")
            # 使用query_enhanced_rag作为降级方案
            return await query_enhanced_rag(
                question=question,
                game_name=game_name,
                top_k=config.top_k,
                enable_hybrid_search=config.hybrid_search.enabled,
                hybrid_config=config.hybrid_search.to_dict(),
                llm_config=llm_config,
                enable_summarization=config.summarization.enabled,
                summarization_config=config.summarization.to_dict(),
                enable_intent_reranking=config.intent_reranking.enabled,
                reranking_config=config.intent_reranking.to_dict()
            )
        
        # 使用引擎查询
        return await engine.query(
            question,
            top_k=config.top_k
        )
    
    @classmethod
    def clear_cache(cls, game_name: Optional[str] = None):
        """
        清除缓存的引擎实例
        
        Args:
            game_name: 指定游戏名称，如果为None则清除所有缓存
        """
        if game_name is None:
            cls._instances.clear()
            logger.info("已清除所有RAG引擎缓存")
        else:
            # 清除特定游戏的缓存
            keys_to_remove = [k for k in cls._instances.keys() if k.startswith(f"{game_name}_")]
            for key in keys_to_remove:
                del cls._instances[key]
            logger.info(f"已清除游戏 {game_name} 的RAG引擎缓存")
    
    @classmethod
    def get_cached_engines_info(cls) -> Dict[str, int]:
        """
        获取缓存的引擎信息
        
        Returns:
            缓存信息字典
        """
        info = {}
        for key in cls._instances.keys():
            game_part = key.split('_')[0]
            info[game_part] = info.get(game_part, 0) + 1
        return info


# 便捷函数
async def create_rag_engine(
    game_name: Optional[str] = None,
    use_default_config: bool = True,
    custom_config: Optional[Dict[str, Any]] = None
) -> EnhancedRagQuery:
    """
    便捷函数：创建RAG引擎
    
    Args:
        game_name: 游戏名称
        use_default_config: 是否使用默认高质量配置
        custom_config: 自定义配置（字典格式）
        
    Returns:
        初始化完成的RAG引擎
    """
    config = None
    if use_default_config:
        config = get_default_config()
    elif custom_config:
        config = RAGConfig.from_dict(custom_config)
    
    return await RAGEngineFactory.create_and_initialize_engine(
        game_name=game_name,
        config=config
    )


async def query_rag_unified(
    question: str,
    game_name: Optional[str] = None,
    use_default_config: bool = True,
    custom_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    便捷函数：使用统一的RAG系统执行查询
    
    Args:
        question: 用户问题
        game_name: 游戏名称
        use_default_config: 是否使用默认高质量配置
        custom_config: 自定义配置
        
    Returns:
        查询结果
    """
    config = None
    if use_default_config:
        config = get_default_config()
    elif custom_config:
        config = RAGConfig.from_dict(custom_config)
    
    return await RAGEngineFactory.query_with_engine(
        question=question,
        game_name=game_name,
        config=config
    )