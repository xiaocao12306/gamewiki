"""
RAG configuration management module - unified management of RAG system configurations
=========================================

Provide unified configuration management for high-quality RAG systems, ensuring that evaluator and searchbar use the same configuration.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class HybridSearchConfig:
    """Hybrid search configuration"""
    enabled: bool = True
    fusion_method: str = "rrf"  # rrf, weighted, normalized
    vector_weight: float = 0.5  # Same as evaluator
    bm25_weight: float = 0.5    # Same as evaluator
    rrf_k: int = 60            # RRF algorithm parameters
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "fusion_method": self.fusion_method,
            "vector_weight": self.vector_weight,
            "bm25_weight": self.bm25_weight,
            "rrf_k": self.rrf_k
        }


@dataclass
class SummarizationConfig:
    """Summary generation configuration"""
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
    """Intent-aware reranking configuration"""
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
    """Query processing configuration"""
    enable_query_rewrite: bool = True
    enable_intent_classification: bool = True
    unified_processing: bool = True  # Use unified processing to improve performance
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enable_query_rewrite": self.enable_query_rewrite,
            "enable_intent_classification": self.enable_intent_classification,
            "unified_processing": self.unified_processing
        }


@dataclass
class RAGConfig:
    """
    Full RAG system configuration
    
    This is the high-quality RAG configuration used by evaluator, now provided to all components for use.
    """
    # Hybrid search configuration
    hybrid_search: HybridSearchConfig = field(default_factory=HybridSearchConfig)
    
    # Summary generation configuration
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)
    
    # Intent reranking configuration
    intent_reranking: IntentRerankingConfig = field(default_factory=IntentRerankingConfig)
    
    # Query processing configuration
    query_processing: QueryProcessingConfig = field(default_factory=QueryProcessingConfig)
    
    # Basic configuration
    top_k: int = 5
    enable_cache: bool = True
    cache_ttl: int = 3600  # Cache time (seconds)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "RAGConfig":
        """Create configuration from dictionary"""
        config = cls()
        
        # Hybrid search configuration
        if "hybrid_search" in config_dict:
            hs_dict = config_dict["hybrid_search"]
            config.hybrid_search = HybridSearchConfig(
                enabled=hs_dict.get("enabled", True),
                fusion_method=hs_dict.get("fusion_method", "rrf"),
                vector_weight=hs_dict.get("vector_weight", 0.5),
                bm25_weight=hs_dict.get("bm25_weight", 0.5),
                rrf_k=hs_dict.get("rrf_k", 60)
            )
        
        # Summary generation configuration
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
        
        # Intent reranking configuration
        if "intent_reranking" in config_dict:
            ir_dict = config_dict["intent_reranking"]
            config.intent_reranking = IntentRerankingConfig(
                enabled=ir_dict.get("enabled", True),
                intent_weight=ir_dict.get("intent_weight", 0.4),
                semantic_weight=ir_dict.get("semantic_weight", 0.6),
                confidence_threshold=ir_dict.get("confidence_threshold", 0.7)
            )
        
        # Query processing configuration
        if "query_processing" in config_dict:
            qp_dict = config_dict["query_processing"]
            config.query_processing = QueryProcessingConfig(
                enable_query_rewrite=qp_dict.get("enable_query_rewrite", True),
                enable_intent_classification=qp_dict.get("enable_intent_classification", True),
                unified_processing=qp_dict.get("unified_processing", True)
            )
        
        # Basic configuration
        config.top_k = config_dict.get("top_k", 5)
        config.enable_cache = config_dict.get("enable_cache", True)
        config.cache_ttl = config_dict.get("cache_ttl", 3600)
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
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
        """Load configuration from file"""
        if config_path is None:
            # Default from settings.json
            config_path = Path(__file__).parent.parent / "assets" / "settings.json"
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    rag_settings = settings.get("rag", {})
                    return cls.from_dict(rag_settings)
            except Exception as e:
                logger.warning(f"Failed to load RAG configuration: {e}, using default configuration")
        
        # Return default configuration
        return cls()
    
    def save_to_file(self, config_path: Optional[Path] = None):
        """Save configuration to file"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "assets" / "settings.json"
        
        # Read existing settings
        settings = {}
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read settings file: {e}")
        
        # Update RAG settings
        settings["rag"] = self.to_dict()
        
        # Save
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            logger.info(f"RAG configuration saved to: {config_path}")
        except Exception as e:
            logger.error(f"Failed to save RAG configuration: {e}")


def get_default_config() -> RAGConfig:
    """Get default high-quality RAG configuration (same as evaluator)"""
    return RAGConfig(
        hybrid_search=HybridSearchConfig(
            enabled=True,
            fusion_method="rrf",
            vector_weight=0.5,  # Same as evaluator
            bm25_weight=0.5,    # Same as evaluator
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
            enable_intent_classification=True,
            unified_processing=True
        ),
        top_k=5,
        enable_cache=True,
        cache_ttl=3600
    )


def get_evaluation_config() -> RAGConfig:
    """Get RAG configuration for evaluation (ensure it's exactly the same as evaluator)"""
    config = get_default_config()
    # Special configuration needed for evaluation
    config.enable_cache = False  # Disable cache for evaluation
    return config