"""
RAG配置管理模块 - 统一管理RAG系统的配置
=========================================

提供高质量RAG系统的统一配置管理，确保evaluator和searchbar使用相同的配置。
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class HybridSearchConfig:
    """混合搜索配置"""
    enabled: bool = True
    fusion_method: str = "rrf"  # rrf, weighted, normalized
    vector_weight: float = 0.5  # 与evaluator保持一致
    bm25_weight: float = 0.5    # 与evaluator保持一致
    rrf_k: int = 60            # RRF算法参数
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "fusion_method": self.fusion_method,
            "vector_weight": self.vector_weight,
            "bm25_weight": self.bm25_weight,
            "rrf_k": self.rrf_k
        }


@dataclass
class SummarizationConfig:
    """摘要生成配置"""
    enabled: bool = True
    model_name: str = "gemini-2.0-flash-exp"
    max_summary_length: int = 300
    temperature: float = 0.3
    include_sources: bool = True
    language: str = "auto"  # auto, zh, en
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "max_summary_length": self.max_summary_length,
            "temperature": self.temperature,
            "include_sources": self.include_sources,
            "language": self.language
        }


@dataclass
class IntentRerankingConfig:
    """意图感知重排序配置"""
    enabled: bool = True
    intent_weight: float = 0.4
    semantic_weight: float = 0.6
    confidence_threshold: float = 0.7
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_weight": self.intent_weight,
            "semantic_weight": self.semantic_weight
        }


@dataclass
class QueryProcessingConfig:
    """查询处理配置"""
    enable_query_rewrite: bool = True
    enable_query_translation: bool = True
    enable_intent_classification: bool = True
    unified_processing: bool = True  # 使用统一处理提高性能
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enable_query_rewrite": self.enable_query_rewrite,
            "enable_query_translation": self.enable_query_translation,
            "enable_intent_classification": self.enable_intent_classification,
            "unified_processing": self.unified_processing
        }


@dataclass
class RAGConfig:
    """
    RAG系统完整配置
    
    这是evaluator使用的高质量RAG配置，现在统一提供给所有组件使用。
    """
    # 混合搜索配置
    hybrid_search: HybridSearchConfig = field(default_factory=HybridSearchConfig)
    
    # 摘要生成配置
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)
    
    # 意图重排序配置
    intent_reranking: IntentRerankingConfig = field(default_factory=IntentRerankingConfig)
    
    # 查询处理配置
    query_processing: QueryProcessingConfig = field(default_factory=QueryProcessingConfig)
    
    # 基础配置
    top_k: int = 5
    enable_cache: bool = True
    cache_ttl: int = 3600  # 缓存时间（秒）
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "RAGConfig":
        """从字典创建配置"""
        config = cls()
        
        # 混合搜索配置
        if "hybrid_search" in config_dict:
            hs_dict = config_dict["hybrid_search"]
            config.hybrid_search = HybridSearchConfig(
                enabled=hs_dict.get("enabled", True),
                fusion_method=hs_dict.get("fusion_method", "rrf"),
                vector_weight=hs_dict.get("vector_weight", 0.5),
                bm25_weight=hs_dict.get("bm25_weight", 0.5),
                rrf_k=hs_dict.get("rrf_k", 60)
            )
        
        # 摘要生成配置
        if "summarization" in config_dict:
            sum_dict = config_dict["summarization"]
            config.summarization = SummarizationConfig(
                enabled=sum_dict.get("enabled", True),
                model_name=sum_dict.get("model_name", "gemini-2.0-flash-exp"),
                max_summary_length=sum_dict.get("max_summary_length", 300),
                temperature=sum_dict.get("temperature", 0.3),
                include_sources=sum_dict.get("include_sources", True),
                language=sum_dict.get("language", "auto")
            )
        
        # 意图重排序配置
        if "intent_reranking" in config_dict:
            ir_dict = config_dict["intent_reranking"]
            config.intent_reranking = IntentRerankingConfig(
                enabled=ir_dict.get("enabled", True),
                intent_weight=ir_dict.get("intent_weight", 0.4),
                semantic_weight=ir_dict.get("semantic_weight", 0.6),
                confidence_threshold=ir_dict.get("confidence_threshold", 0.7)
            )
        
        # 查询处理配置
        if "query_processing" in config_dict:
            qp_dict = config_dict["query_processing"]
            config.query_processing = QueryProcessingConfig(
                enable_query_rewrite=qp_dict.get("enable_query_rewrite", True),
                enable_query_translation=qp_dict.get("enable_query_translation", True),
                enable_intent_classification=qp_dict.get("enable_intent_classification", True),
                unified_processing=qp_dict.get("unified_processing", True)
            )
        
        # 基础配置
        config.top_k = config_dict.get("top_k", 5)
        config.enable_cache = config_dict.get("enable_cache", True)
        config.cache_ttl = config_dict.get("cache_ttl", 3600)
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "hybrid_search": {
                "enabled": self.hybrid_search.enabled,
                **self.hybrid_search.to_dict()
            },
            "summarization": {
                "enabled": self.summarization.enabled,
                **self.summarization.to_dict()
            },
            "intent_reranking": {
                "enabled": self.intent_reranking.enabled,
                **self.intent_reranking.to_dict()
            },
            "query_processing": self.query_processing.to_dict(),
            "top_k": self.top_k,
            "enable_cache": self.enable_cache,
            "cache_ttl": self.cache_ttl
        }
    
    @classmethod
    def load_from_file(cls, config_path: Optional[Path] = None) -> "RAGConfig":
        """从文件加载配置"""
        if config_path is None:
            # 默认从settings.json加载
            config_path = Path(__file__).parent.parent / "assets" / "settings.json"
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    rag_settings = settings.get("rag", {})
                    return cls.from_dict(rag_settings)
            except Exception as e:
                logger.warning(f"加载RAG配置失败: {e}，使用默认配置")
        
        # 返回默认配置
        return cls()
    
    def save_to_file(self, config_path: Optional[Path] = None):
        """保存配置到文件"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "assets" / "settings.json"
        
        # 读取现有设置
        settings = {}
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            except Exception as e:
                logger.warning(f"读取设置文件失败: {e}")
        
        # 更新RAG设置
        settings["rag"] = self.to_dict()
        
        # 保存
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            logger.info(f"RAG配置已保存到: {config_path}")
        except Exception as e:
            logger.error(f"保存RAG配置失败: {e}")


def get_default_config() -> RAGConfig:
    """获取默认的高质量RAG配置（与evaluator使用的相同）"""
    return RAGConfig(
        hybrid_search=HybridSearchConfig(
            enabled=True,
            fusion_method="rrf",
            vector_weight=0.5,  # evaluator使用的权重
            bm25_weight=0.5,    # evaluator使用的权重
            rrf_k=60
        ),
        summarization=SummarizationConfig(
            enabled=True,
            model_name="gemini-2.0-flash-exp",
            max_summary_length=300,
            temperature=0.3,
            include_sources=True,
            language="auto"
        ),
        intent_reranking=IntentRerankingConfig(
            enabled=True,
            intent_weight=0.4,
            semantic_weight=0.6,
            confidence_threshold=0.7
        ),
        query_processing=QueryProcessingConfig(
            enable_query_rewrite=True,
            enable_query_translation=True,
            enable_intent_classification=True,
            unified_processing=True
        ),
        top_k=5,
        enable_cache=True,
        cache_ttl=3600
    )


def get_evaluation_config() -> RAGConfig:
    """获取用于评估的RAG配置（确保与evaluator完全一致）"""
    config = get_default_config()
    # 评估时可能需要的特殊配置
    config.enable_cache = False  # 评估时禁用缓存
    return config