"""
RAG系统配置管理器
==================

统一管理RAG系统的所有配置，确保evaluation和searchbar使用相同的配置
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class RAGConfig:
    """RAG系统的统一配置"""
    
    # 基础配置
    enable_hybrid_search: bool = True
    enable_query_rewrite: bool = True
    enable_summarization: bool = True
    enable_intent_reranking: bool = True
    
    # 混合搜索配置
    hybrid_config: Dict[str, Any] = field(default_factory=lambda: {
        "fusion_method": "rrf",
        "vector_weight": 0.5,  # 与evaluation相同的权重
        "bm25_weight": 0.5,    # 与evaluation相同的权重
        "rrf_k": 60
    })
    
    # 摘要配置
    summarization_config: Dict[str, Any] = field(default_factory=lambda: {
        "model_name": "gemini-2.0-flash-exp",
        "max_summary_length": 300,
        "temperature": 0.3,
        "include_sources": True,
        "language": "auto"
    })
    
    # 重排序配置
    reranking_config: Dict[str, Any] = field(default_factory=lambda: {
        "intent_weight": 0.4,
        "semantic_weight": 0.6
    })
    
    # 检索配置
    retrieval_config: Dict[str, Any] = field(default_factory=lambda: {
        "top_k": 3,
        "min_relevance_score": 0.5
    })
    
    @classmethod
    def get_default_config(cls) -> 'RAGConfig':
        """获取默认配置（与evaluation相同）"""
        return cls()
    
    @classmethod
    def get_searchbar_config(cls) -> 'RAGConfig':
        """获取searchbar专用配置（如果需要微调）"""
        config = cls.get_default_config()
        # 可以在这里调整searchbar专用的配置
        # 目前保持与evaluation完全一致
        return config
    
    @classmethod
    def get_evaluation_config(cls) -> 'RAGConfig':
        """获取evaluation专用配置"""
        return cls.get_default_config()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "enable_hybrid_search": self.enable_hybrid_search,
            "enable_query_rewrite": self.enable_query_rewrite,
            "enable_summarization": self.enable_summarization,
            "enable_intent_reranking": self.enable_intent_reranking,
            "hybrid_config": self.hybrid_config,
            "summarization_config": self.summarization_config,
            "reranking_config": self.reranking_config,
            "retrieval_config": self.retrieval_config
        }
    
    def update_from_dict(self, config_dict: Dict[str, Any]) -> None:
        """从字典更新配置"""
        for key, value in config_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)


# 全局配置实例
_global_rag_config: Optional[RAGConfig] = None


def get_global_rag_config() -> RAGConfig:
    """获取全局RAG配置"""
    global _global_rag_config
    if _global_rag_config is None:
        _global_rag_config = RAGConfig.get_default_config()
    return _global_rag_config


def set_global_rag_config(config: RAGConfig) -> None:
    """设置全局RAG配置"""
    global _global_rag_config
    _global_rag_config = config