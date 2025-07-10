"""
混合搜索检索器模块
==================

功能：
1. 整合向量搜索和BM25搜索
2. 实现多种分数融合算法
3. 提供统一的搜索接口
4. 支持统一查询处理（翻译+重写+意图分析）
5. 性能优化：一次LLM调用完成多项任务
"""

import numpy as np
import logging
from typing import List, Dict, Any, Optional, Tuple
from sklearn.preprocessing import MinMaxScaler
from pathlib import Path
from .bm25_indexer import BM25Indexer
from .unified_query_processor import process_query_unified, UnifiedQueryResult
from ..config import LLMConfig

logger = logging.getLogger(__name__)


class VectorRetrieverAdapter:
    """向量检索器适配器，用于包装现有的向量搜索功能"""
    
    def __init__(self, rag_query_instance):
        """
        初始化适配器
        
        Args:
            rag_query_instance: EnhancedRagQuery实例
        """
        self.rag_query = rag_query_instance
        
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        执行向量搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        if self.rag_query.config and self.rag_query.config["vector_store_type"] == "faiss":
            return self.rag_query._search_faiss(query, top_k)
        else:
            return self.rag_query._search_qdrant(query, top_k)


class HybridSearchRetriever:
    """混合搜索检索器"""
    
    def __init__(self, 
                 vector_retriever: VectorRetrieverAdapter,
                 bm25_index_path: str,
                 fusion_method: str = "rrf",
                 vector_weight: float = 0.6,
                 bm25_weight: float = 0.4,
                 rrf_k: int = 60,
                 llm_config: Optional[LLMConfig] = None,
                 enable_unified_processing: bool = True,
                 enable_query_rewrite: bool = True,
                 enable_query_translation: bool = True):
        """
        初始化混合搜索检索器
        
        Args:
            vector_retriever: 向量检索器适配器
            bm25_index_path: BM25索引路径
            fusion_method: 融合方法 ("rrf", "weighted", "normalized")
            vector_weight: 向量搜索权重
            bm25_weight: BM25搜索权重
            rrf_k: RRF算法的k参数
            llm_config: LLM配置
            enable_unified_processing: 是否启用统一查询处理（推荐）
            enable_query_rewrite: 是否启用查询重写（仅在统一处理禁用时生效）
            enable_query_translation: 是否启用查询翻译（仅在统一处理禁用时生效）
        """
        self.vector_retriever = vector_retriever
        self.fusion_method = fusion_method
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.rrf_k = rrf_k
        self.llm_config = llm_config or LLMConfig()
        
        # 性能优化：统一处理vs分离处理
        self.enable_unified_processing = enable_unified_processing
        self.enable_query_rewrite = enable_query_rewrite if not enable_unified_processing else False
        self.enable_query_translation = enable_query_translation if not enable_unified_processing else False
        
        # 初始化BM25索引器
        self.bm25_indexer = None
        bm25_path = Path(bm25_index_path)
        if bm25_path.exists():
            try:
                self.bm25_indexer = BM25Indexer()
                self.bm25_indexer.load_index(str(bm25_path))
                logger.info(f"BM25索引加载成功: {bm25_index_path}")
            except Exception as e:
                logger.error(f"BM25索引加载失败: {e}")
                self.bm25_indexer = None
        else:
            logger.warning(f"BM25索引文件不存在: {bm25_index_path}")
        
        # 统计信息
        self.unified_processing_stats = {
            "total_queries": 0,
            "unified_successful": 0,
            "unified_failed": 0,
            "cache_hits": 0,
            "average_processing_time": 0.0
        }
        
        # 降级处理的统计（仅在统一处理禁用时使用）
        self.query_rewrite_stats = {
            "total_queries": 0,
            "rewritten_queries": 0,
            "cache_hits": 0
        }
        
        self.query_translation_stats = {
            "total_queries": 0,
            "translated_queries": 0
        }
    
    def search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        执行混合搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            搜索结果字典，包含结果列表和元数据
        """
        logger.info(f"开始混合搜索: {query}")
        
        # 更新统计
        if self.enable_unified_processing:
            self.unified_processing_stats["total_queries"] += 1
        else:
            self.query_rewrite_stats["total_queries"] += 1
            self.query_translation_stats["total_queries"] += 1
        
        # 查询处理
        if self.enable_unified_processing:
            # 使用统一处理器（推荐方式）
            try:
                unified_result = process_query_unified(query, self.llm_config)
                
                # 提取处理结果
                final_query = unified_result.rewritten_query
                translation_applied = unified_result.translation_applied
                rewrite_applied = unified_result.rewrite_applied
                
                # 更新统计
                self.unified_processing_stats["unified_successful"] += 1
                if hasattr(unified_result, 'processing_time'):
                    avg_time = self.unified_processing_stats["average_processing_time"]
                    total_queries = self.unified_processing_stats["total_queries"]
                    self.unified_processing_stats["average_processing_time"] = (
                        (avg_time * (total_queries - 1) + unified_result.processing_time) / total_queries
                    )
                
                # 构建查询元数据
                query_metadata = {
                    "original_query": query,
                    "processed_query": final_query,
                    "translation_applied": translation_applied,
                    "rewrite_applied": rewrite_applied,
                    "intent": unified_result.intent,
                    "confidence": unified_result.confidence,
                    "detected_language": unified_result.detected_language,
                    "processing_method": "unified",
                    "reasoning": unified_result.reasoning
                }
                
                logger.info(f"统一处理成功: '{query}' -> '{final_query}' (翻译: {translation_applied}, 重写: {rewrite_applied})")
                
            except Exception as e:
                logger.error(f"统一处理失败: {e}")
                self.unified_processing_stats["unified_failed"] += 1
                
                # 降级到原始查询
                final_query = query
                translation_applied = False
                rewrite_applied = False
                query_metadata = {
                    "original_query": query,
                    "processed_query": final_query,
                    "translation_applied": False,
                    "rewrite_applied": False,
                    "processing_method": "fallback",
                    "error": str(e)
                }
        else:
            # 原有的分离处理方式（兼容性保留）
            final_query = query
            translation_applied = False
            rewrite_applied = False
            
            # 查询翻译（如果启用）
            if self.enable_query_translation:
                try:
                    from .query_translator import translate_query_if_needed
                    translated_query = translate_query_if_needed(query, self.llm_config)
                    if translated_query != query:
                        final_query = translated_query
                        translation_applied = True
                        self.query_translation_stats["translated_queries"] += 1
                        logger.info(f"查询翻译: '{query}' -> '{translated_query}'")
                except Exception as e:
                    logger.warning(f"查询翻译失败: {e}")
            
            # 查询重写（如果启用）
            if self.enable_query_rewrite:
                try:
                    from .intent.intent_classifier import rewrite_query_for_search
                    rewrite_result = rewrite_query_for_search(final_query, self.llm_config)
                    
                    if rewrite_result.rewritten_query != final_query:
                        final_query = rewrite_result.rewritten_query
                        rewrite_applied = True
                        self.query_rewrite_stats["rewritten_queries"] += 1
                        logger.info(f"查询重写: '{query}' -> '{final_query}'")
                        
                except Exception as e:
                    logger.warning(f"查询重写失败: {e}")
            
            query_metadata = {
                "original_query": query,
                "processed_query": final_query,
                "translation_applied": translation_applied,
                "rewrite_applied": rewrite_applied,
                "processing_method": "separate"
            }
        
        # 执行混合搜索
        try:
            # 向量搜索
            vector_results = self.vector_retriever.search(final_query, top_k * 2)
            
            # BM25搜索
            bm25_results = []
            if self.bm25_indexer:
                bm25_results = self.bm25_indexer.search(final_query, top_k * 2)
            
            # 分数融合
            final_results = self._fuse_results(vector_results, bm25_results, top_k)
            
            # 构建返回结果
            return {
                "results": final_results,
                "query": query_metadata,
                "metadata": {
                    "fusion_method": self.fusion_method,
                    "vector_results_count": len(vector_results),
                    "bm25_results_count": len(bm25_results),
                    "final_results_count": len(final_results),
                    "processing_stats": self._get_processing_stats()
                }
            }
            
        except Exception as e:
            logger.error(f"混合搜索执行失败: {e}")
            return {
                "results": [],
                "query": query_metadata,
                "metadata": {
                    "error": str(e),
                    "processing_stats": self._get_processing_stats()
                }
            }
    
    def _fuse_results(self, vector_results: List[Dict], bm25_results: List[Dict], top_k: int) -> List[Dict]:
        """
        融合向量搜索和BM25搜索的结果
        
        Args:
            vector_results: 向量搜索结果
            bm25_results: BM25搜索结果
            top_k: 返回的结果数量
            
        Returns:
            融合后的搜索结果
        """
        if self.fusion_method == "rrf":
            return self._reciprocal_rank_fusion(vector_results, bm25_results, top_k)
        elif self.fusion_method == "weighted":
            return self._weighted_fusion(vector_results, bm25_results, top_k)
        elif self.fusion_method == "normalized":
            return self._normalized_fusion(vector_results, bm25_results, top_k)
        else:
            logger.warning(f"未知的融合方法: {self.fusion_method}，使用RRF")
            return self._reciprocal_rank_fusion(vector_results, bm25_results, top_k)
    
    def _reciprocal_rank_fusion(self, vector_results: List[Dict], bm25_results: List[Dict], top_k: int) -> List[Dict]:
        """
        使用倒数排名融合(RRF)算法融合结果
        """
        # 创建文档ID到分数的映射
        doc_scores = {}
        
        # 处理向量搜索结果
        for rank, result in enumerate(vector_results, 1):
            doc_id = result.get("chunk_id", f"vector_{rank}")
            rrf_score = 1.0 / (self.rrf_k + rank)
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "result": result,
                    "vector_score": result.get("score", 0),
                    "bm25_score": 0,
                    "rrf_score": 0
                }
            doc_scores[doc_id]["rrf_score"] += rrf_score
        
        # 处理BM25搜索结果
        for rank, result in enumerate(bm25_results, 1):
            doc_id = result.get("chunk_id", f"bm25_{rank}")
            rrf_score = 1.0 / (self.rrf_k + rank)
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "result": result,
                    "vector_score": 0,
                    "bm25_score": result.get("score", 0),
                    "rrf_score": 0
                }
            else:
                doc_scores[doc_id]["bm25_score"] = result.get("score", 0)
            
            doc_scores[doc_id]["rrf_score"] += rrf_score
        
        # 按RRF分数排序并返回top_k结果
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1]["rrf_score"], reverse=True)
        
        final_results = []
        for doc_id, scores in sorted_docs[:top_k]:
            result = scores["result"].copy()
            result["fusion_score"] = scores["rrf_score"]
            result["vector_score"] = scores["vector_score"]
            result["bm25_score"] = scores["bm25_score"]
            result["fusion_method"] = "rrf"
            final_results.append(result)
        
        return final_results
    
    def _weighted_fusion(self, vector_results: List[Dict], bm25_results: List[Dict], top_k: int) -> List[Dict]:
        """
        使用加权平均融合结果
        """
        # 归一化分数
        vector_scores = [r.get("score", 0) for r in vector_results]
        bm25_scores = [r.get("score", 0) for r in bm25_results]
        
        if vector_scores:
            vector_scaler = MinMaxScaler()
            vector_scores_norm = vector_scaler.fit_transform([[s] for s in vector_scores]).flatten()
        else:
            vector_scores_norm = []
        
        if bm25_scores:
            bm25_scaler = MinMaxScaler()
            bm25_scores_norm = bm25_scaler.fit_transform([[s] for s in bm25_scores]).flatten()
        else:
            bm25_scores_norm = []
        
        # 创建文档分数映射
        doc_scores = {}
        
        # 处理向量结果
        for i, result in enumerate(vector_results):
            doc_id = result.get("chunk_id", f"vector_{i}")
            normalized_score = vector_scores_norm[i] if i < len(vector_scores_norm) else 0
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "result": result,
                    "vector_score": normalized_score,
                    "bm25_score": 0
                }
            else:
                doc_scores[doc_id]["vector_score"] = normalized_score
        
        # 处理BM25结果
        for i, result in enumerate(bm25_results):
            doc_id = result.get("chunk_id", f"bm25_{i}")
            normalized_score = bm25_scores_norm[i] if i < len(bm25_scores_norm) else 0
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "result": result,
                    "vector_score": 0,
                    "bm25_score": normalized_score
                }
            else:
                doc_scores[doc_id]["bm25_score"] = normalized_score
        
        # 计算加权分数
        for doc_id, scores in doc_scores.items():
            weighted_score = (
                scores["vector_score"] * self.vector_weight +
                scores["bm25_score"] * self.bm25_weight
            )
            scores["fusion_score"] = weighted_score
        
        # 排序并返回结果
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1]["fusion_score"], reverse=True)
        
        final_results = []
        for doc_id, scores in sorted_docs[:top_k]:
            result = scores["result"].copy()
            result["fusion_score"] = scores["fusion_score"]
            result["vector_score"] = scores["vector_score"]
            result["bm25_score"] = scores["bm25_score"]
            result["fusion_method"] = "weighted"
            final_results.append(result)
        
        return final_results
    
    def _normalized_fusion(self, vector_results: List[Dict], bm25_results: List[Dict], top_k: int) -> List[Dict]:
        """
        使用归一化融合结果
        """
        # 归一化处理逻辑类似加权融合，但权重相等
        temp_vector_weight = self.vector_weight
        temp_bm25_weight = self.bm25_weight
        
        # 临时设置相等权重
        self.vector_weight = 0.5
        self.bm25_weight = 0.5
        
        result = self._weighted_fusion(vector_results, bm25_results, top_k)
        
        # 恢复原权重
        self.vector_weight = temp_vector_weight
        self.bm25_weight = temp_bm25_weight
        
        # 更新融合方法标记
        for r in result:
            r["fusion_method"] = "normalized"
        
        return result
    
    def _get_processing_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        if self.enable_unified_processing:
            return {
                "method": "unified_processing",
                "stats": self.unified_processing_stats.copy()
            }
        else:
            return {
                "method": "separate_processing",
                "translation_stats": self.query_translation_stats.copy(),
                "rewrite_stats": self.query_rewrite_stats.copy()
            }
    
    def get_search_stats(self) -> Dict[str, Any]:
        """获取搜索统计信息"""
        vector_stats = {}
        bm25_stats = {}
        
        # 获取BM25统计
        if hasattr(self.bm25_indexer, 'get_stats'):
            bm25_stats = self.bm25_indexer.get_stats()
        
        base_stats = {
            "vector_stats": vector_stats,
            "bm25_stats": bm25_stats,
            "unified_processing_enabled": self.enable_unified_processing,
            "query_rewrite_enabled": self.enable_query_rewrite,
            "query_translation_enabled": self.enable_query_translation
        }
        
        if self.enable_unified_processing:
            base_stats["unified_processing_stats"] = self.unified_processing_stats.copy()
        else:
            base_stats["query_rewrite_stats"] = self.query_rewrite_stats.copy()
            base_stats["query_translation_stats"] = self.query_translation_stats.copy()
        
        return base_stats
    
    def reset_stats(self):
        """重置所有统计信息"""
        self.unified_processing_stats = {
            "total_queries": 0,
            "unified_successful": 0,
            "unified_failed": 0,
            "cache_hits": 0,
            "average_processing_time": 0.0
        }
        
        self.query_rewrite_stats = {
            "total_queries": 0,
            "rewritten_queries": 0,
            "cache_hits": 0
        }
        
        self.query_translation_stats = {
            "total_queries": 0,
            "translated_queries": 0
        }


def test_hybrid_retriever():
    """测试混合检索器"""
    # 这里需要实际的向量检索器实例
    print("混合检索器测试需要完整的RAG系统支持")
    print("请在完整系统中测试")


if __name__ == "__main__":
    test_hybrid_retriever() 