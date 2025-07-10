"""
自适应混合检索器 - 智能融合向量和BM25搜索
==========================================

功能：
1. 自适应权重调整（基于查询类型）
2. 智能结果融合（RRF + 分数标准化）
3. 敌人特定权重提升
4. 查询处理集成
5. 性能优化和缓存
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json

# 导入自定义组件
from .enhanced_bm25_indexer import EnhancedBM25Indexer
from .enhanced_query_processor import EnhancedQueryProcessor, QueryIntent

logger = logging.getLogger(__name__)

class AdaptiveHybridRetriever:
    """自适应混合检索器"""
    
    # 查询类型权重配置
    QUERY_TYPE_WEIGHTS = {
        QueryIntent.WEAKNESS: {"vector": 0.6, "bm25": 0.4},      # 弱点查询：语义为主
        QueryIntent.KILL_METHOD: {"vector": 0.5, "bm25": 0.5},   # 击杀方法：平衡
        QueryIntent.STRATEGY: {"vector": 0.5, "bm25": 0.5},      # 策略查询：平衡
        QueryIntent.WEAPON_LOADOUT: {"vector": 0.3, "bm25": 0.7}, # 武器配装：关键词为主
        QueryIntent.BUILD_GUIDE: {"vector": 0.3, "bm25": 0.7},   # 配装指南：关键词为主
        QueryIntent.GENERAL_INFO: {"vector": 0.4, "bm25": 0.6},  # 通用信息：稍微偏向关键词
        QueryIntent.UNKNOWN: {"vector": 0.4, "bm25": 0.6}        # 未知意图：默认配置
    }
    
    # 敌人特定提升因子
    ENEMY_BOOST_FACTORS = {
        'bile titan': 1.8,      # 高优先级敌人
        'hulk': 1.6,
        'charger': 1.4,
        'factory strider': 1.5,
        'tank': 1.3,
        'impaler': 1.2,
        'devastator': 1.1,
        'brood commander': 1.1,
        'stalker': 1.1,
        'berserker': 1.0,
        'gunship': 1.0,
        'dropship': 1.0
    }
    
    def __init__(self, 
                 vector_retriever: Any,
                 bm25_index_path: str,
                 fusion_method: str = "rrf",
                 rrf_k: int = 60,
                 enable_query_rewrite: bool = True,
                 enable_enemy_boost: bool = True):
        """
        初始化自适应混合检索器
        
        Args:
            vector_retriever: 向量检索器
            bm25_index_path: BM25索引路径
            fusion_method: 融合方法 ("rrf", "weighted_sum", "max")
            rrf_k: RRF参数
            enable_query_rewrite: 是否启用查询重写
            enable_enemy_boost: 是否启用敌人特定提升
        """
        self.vector_retriever = vector_retriever
        self.fusion_method = fusion_method
        self.rrf_k = rrf_k
        self.enable_query_rewrite = enable_query_rewrite
        self.enable_enemy_boost = enable_enemy_boost
        
        # 初始化BM25索引器
        self.bm25_indexer = EnhancedBM25Indexer()
        self._load_bm25_index(bm25_index_path)
        
        # 初始化查询处理器
        if self.enable_query_rewrite:
            self.query_processor = EnhancedQueryProcessor()
        else:
            self.query_processor = None
            
        # 结果缓存
        self._result_cache = {}
        self._cache_size_limit = 100
        
    def _load_bm25_index(self, index_path: str) -> None:
        """加载BM25索引"""
        try:
            if Path(index_path).exists():
                self.bm25_indexer.load_index(index_path)
                logger.info(f"BM25索引加载成功: {index_path}")
            else:
                logger.warning(f"BM25索引文件不存在: {index_path}")
                self.bm25_indexer = None
        except Exception as e:
            logger.error(f"BM25索引加载失败: {e}")
            self.bm25_indexer = None
    
    def _get_cache_key(self, query: str, top_k: int, **kwargs) -> str:
        """生成缓存键"""
        return f"{query}_{top_k}_{hash(str(sorted(kwargs.items())))}"
    
    def search(self, query: str, top_k: int = 10, **kwargs) -> Dict[str, Any]:
        """
        执行自适应混合搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            **kwargs: 其他参数
            
        Returns:
            搜索结果字典
        """
        # 检查缓存
        cache_key = self._get_cache_key(query, top_k, **kwargs)
        if cache_key in self._result_cache:
            logger.info(f"使用缓存结果: {query}")
            return self._result_cache[cache_key]
        
        start_time = self._get_time()
        
        # 1. 查询预处理
        processed_query = self._preprocess_query(query)
        
        # 2. 执行向量搜索
        vector_results = self._vector_search(processed_query["rewritten"], top_k * 2)  # 获取更多候选
        
        # 3. 执行BM25搜索
        bm25_results = self._bm25_search(processed_query["rewritten"], top_k * 2)
        
        # 4. 自适应融合结果
        fused_results = self._adaptive_fusion(
            vector_results, bm25_results, processed_query, top_k
        )
        
        # 5. 应用敌人特定提升
        if self.enable_enemy_boost:
            fused_results = self._apply_enemy_boost(fused_results, processed_query)
        
        # 6. 最终排序和截断
        final_results = self._finalize_results(fused_results, top_k)
        
        # 7. 构建响应
        processing_time = self._get_time() - start_time
        response = self._build_response(
            query, processed_query, final_results, vector_results, bm25_results, processing_time
        )
        
        # 8. 缓存结果
        self._cache_result(cache_key, response)
        
        return response
    
    def _preprocess_query(self, query: str) -> Dict[str, Any]:
        """预处理查询"""
        if self.query_processor:
            return self.query_processor.rewrite_query(query)
        else:
            return {
                "original": query,
                "rewritten": query,
                "intent": "unknown",
                "confidence": 0.0,
                "detected_enemies": [],
                "rewrite_applied": False,
                "reasoning": "查询重写被禁用"
            }
    
    def _vector_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """执行向量搜索"""
        try:
            if hasattr(self.vector_retriever, 'search'):
                # 假设vector_retriever有search方法
                return self.vector_retriever.search(query, top_k)
            else:
                # 使用现有的RAG查询接口
                results = []
                if hasattr(self.vector_retriever, '_search_faiss'):
                    faiss_results = self.vector_retriever._search_faiss(query, top_k)
                    for result in faiss_results:
                        results.append({
                            "chunk": result["chunk"],
                            "score": result["score"],
                            "rank": result["rank"],
                            "source": "vector"
                        })
                return results
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []
    
    def _bm25_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """执行BM25搜索"""
        try:
            if self.bm25_indexer:
                bm25_results = self.bm25_indexer.search(query, top_k)
                for result in bm25_results:
                    result["source"] = "bm25"
                return bm25_results
            else:
                logger.warning("BM25索引器不可用")
                return []
        except Exception as e:
            logger.error(f"BM25搜索失败: {e}")
            return []
    
    def _adaptive_fusion(self, 
                        vector_results: List[Dict[str, Any]], 
                        bm25_results: List[Dict[str, Any]], 
                        processed_query: Dict[str, Any],
                        top_k: int) -> List[Dict[str, Any]]:
        """自适应融合搜索结果"""
        
        # 确定权重
        intent = QueryIntent(processed_query.get("intent", "unknown"))
        weights = self.QUERY_TYPE_WEIGHTS.get(intent, self.QUERY_TYPE_WEIGHTS[QueryIntent.UNKNOWN])
        
        logger.info(f"使用权重配置: 向量={weights['vector']}, BM25={weights['bm25']} (意图: {intent.value})")
        
        if self.fusion_method == "rrf":
            return self._reciprocal_rank_fusion(vector_results, bm25_results, weights)
        elif self.fusion_method == "weighted_sum":
            return self._weighted_sum_fusion(vector_results, bm25_results, weights)
        elif self.fusion_method == "max":
            return self._max_score_fusion(vector_results, bm25_results, weights)
        else:
            # 默认使用RRF
            return self._reciprocal_rank_fusion(vector_results, bm25_results, weights)
    
    def _reciprocal_rank_fusion(self, 
                               vector_results: List[Dict[str, Any]], 
                               bm25_results: List[Dict[str, Any]], 
                               weights: Dict[str, float]) -> List[Dict[str, Any]]:
        """倒数排名融合 (RRF)"""
        
        # 构建文档ID到结果的映射
        doc_scores = {}
        doc_chunks = {}
        
        # 处理向量搜索结果
        for rank, result in enumerate(vector_results):
            chunk_id = result["chunk"].get("chunk_id", f"unknown_{rank}")
            doc_chunks[chunk_id] = result["chunk"]
            
            rrf_score = weights["vector"] / (self.rrf_k + rank + 1)
            if chunk_id not in doc_scores:
                doc_scores[chunk_id] = {"vector": 0, "bm25": 0, "sources": []}
            doc_scores[chunk_id]["vector"] = rrf_score
            doc_scores[chunk_id]["sources"].append("vector")
        
        # 处理BM25搜索结果
        for rank, result in enumerate(bm25_results):
            chunk_id = result["chunk"].get("chunk_id", f"unknown_bm25_{rank}")
            doc_chunks[chunk_id] = result["chunk"]
            
            rrf_score = weights["bm25"] / (self.rrf_k + rank + 1)
            if chunk_id not in doc_scores:
                doc_scores[chunk_id] = {"vector": 0, "bm25": 0, "sources": []}
            doc_scores[chunk_id]["bm25"] = rrf_score
            doc_scores[chunk_id]["sources"].append("bm25")
        
        # 计算总分并排序
        fused_results = []
        for chunk_id, scores in doc_scores.items():
            total_score = scores["vector"] + scores["bm25"]
            fused_results.append({
                "chunk": doc_chunks[chunk_id],
                "score": total_score,
                "vector_score": scores["vector"],
                "bm25_score": scores["bm25"],
                "sources": scores["sources"],
                "fusion_method": "rrf"
            })
        
        # 按分数降序排序
        fused_results.sort(key=lambda x: x["score"], reverse=True)
        return fused_results
    
    def _weighted_sum_fusion(self, 
                            vector_results: List[Dict[str, Any]], 
                            bm25_results: List[Dict[str, Any]], 
                            weights: Dict[str, float]) -> List[Dict[str, Any]]:
        """加权求和融合"""
        
        # 标准化分数
        vector_scores = self._normalize_scores([r["score"] for r in vector_results])
        bm25_scores = self._normalize_scores([r["score"] for r in bm25_results])
        
        # 构建文档映射
        doc_scores = {}
        doc_chunks = {}
        
        # 处理向量结果
        for i, result in enumerate(vector_results):
            chunk_id = result["chunk"].get("chunk_id", f"unknown_{i}")
            doc_chunks[chunk_id] = result["chunk"]
            
            if chunk_id not in doc_scores:
                doc_scores[chunk_id] = {"vector": 0, "bm25": 0, "sources": []}
            doc_scores[chunk_id]["vector"] = vector_scores[i] * weights["vector"]
            doc_scores[chunk_id]["sources"].append("vector")
        
        # 处理BM25结果
        for i, result in enumerate(bm25_results):
            chunk_id = result["chunk"].get("chunk_id", f"unknown_bm25_{i}")
            doc_chunks[chunk_id] = result["chunk"]
            
            if chunk_id not in doc_scores:
                doc_scores[chunk_id] = {"vector": 0, "bm25": 0, "sources": []}
            doc_scores[chunk_id]["bm25"] = bm25_scores[i] * weights["bm25"]
            doc_scores[chunk_id]["sources"].append("bm25")
        
        # 计算总分
        fused_results = []
        for chunk_id, scores in doc_scores.items():
            total_score = scores["vector"] + scores["bm25"]
            fused_results.append({
                "chunk": doc_chunks[chunk_id],
                "score": total_score,
                "vector_score": scores["vector"],
                "bm25_score": scores["bm25"],
                "sources": scores["sources"],
                "fusion_method": "weighted_sum"
            })
        
        fused_results.sort(key=lambda x: x["score"], reverse=True)
        return fused_results
    
    def _max_score_fusion(self, 
                         vector_results: List[Dict[str, Any]], 
                         bm25_results: List[Dict[str, Any]], 
                         weights: Dict[str, float]) -> List[Dict[str, Any]]:
        """最大分数融合"""
        
        # 标准化分数
        vector_scores = self._normalize_scores([r["score"] for r in vector_results])
        bm25_scores = self._normalize_scores([r["score"] for r in bm25_results])
        
        doc_scores = {}
        doc_chunks = {}
        
        # 处理向量结果
        for i, result in enumerate(vector_results):
            chunk_id = result["chunk"].get("chunk_id", f"unknown_{i}")
            doc_chunks[chunk_id] = result["chunk"]
            
            weighted_score = vector_scores[i] * weights["vector"]
            if chunk_id not in doc_scores:
                doc_scores[chunk_id] = {"max_score": weighted_score, "sources": ["vector"]}
            else:
                doc_scores[chunk_id]["max_score"] = max(doc_scores[chunk_id]["max_score"], weighted_score)
                doc_scores[chunk_id]["sources"].append("vector")
        
        # 处理BM25结果
        for i, result in enumerate(bm25_results):
            chunk_id = result["chunk"].get("chunk_id", f"unknown_bm25_{i}")
            doc_chunks[chunk_id] = result["chunk"]
            
            weighted_score = bm25_scores[i] * weights["bm25"]
            if chunk_id not in doc_scores:
                doc_scores[chunk_id] = {"max_score": weighted_score, "sources": ["bm25"]}
            else:
                doc_scores[chunk_id]["max_score"] = max(doc_scores[chunk_id]["max_score"], weighted_score)
                doc_scores[chunk_id]["sources"].append("bm25")
        
        # 构建结果
        fused_results = []
        for chunk_id, score_info in doc_scores.items():
            fused_results.append({
                "chunk": doc_chunks[chunk_id],
                "score": score_info["max_score"],
                "sources": score_info["sources"],
                "fusion_method": "max"
            })
        
        fused_results.sort(key=lambda x: x["score"], reverse=True)
        return fused_results
    
    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """标准化分数到0-1范围"""
        if not scores:
            return []
        
        scores = np.array(scores)
        min_score = scores.min()
        max_score = scores.max()
        
        if max_score == min_score:
            return [1.0] * len(scores)
        
        normalized = (scores - min_score) / (max_score - min_score)
        return normalized.tolist()
    
    def _apply_enemy_boost(self, 
                          results: List[Dict[str, Any]], 
                          processed_query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """应用敌人特定的分数提升"""
        
        detected_enemies = processed_query.get("detected_enemies", [])
        if not detected_enemies:
            return results
        
        # 计算最大提升因子
        max_boost = max(self.ENEMY_BOOST_FACTORS.get(enemy, 1.0) for enemy in detected_enemies)
        
        logger.info(f"应用敌人提升: {detected_enemies}, 最大提升因子: {max_boost}")
        
        boosted_results = []
        for result in results:
            chunk = result["chunk"]
            topic = chunk.get("topic", "").lower()
            
            # 检查是否匹配任何检测到的敌人
            boost_factor = 1.0
            for enemy in detected_enemies:
                if enemy in topic:
                    boost_factor = max(boost_factor, self.ENEMY_BOOST_FACTORS.get(enemy, 1.0))
            
            # 应用提升
            boosted_result = result.copy()
            boosted_result["score"] = result["score"] * boost_factor
            boosted_result["enemy_boost"] = boost_factor
            boosted_results.append(boosted_result)
        
        # 重新排序
        boosted_results.sort(key=lambda x: x["score"], reverse=True)
        return boosted_results
    
    def _finalize_results(self, results: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """最终化结果"""
        
        # 截断到top_k
        final_results = results[:top_k]
        
        # 添加排名信息
        for i, result in enumerate(final_results):
            result["rank"] = i + 1
        
        return final_results
    
    def _build_response(self, 
                       original_query: str,
                       processed_query: Dict[str, Any],
                       final_results: List[Dict[str, Any]],
                       vector_results: List[Dict[str, Any]],
                       bm25_results: List[Dict[str, Any]],
                       processing_time: float) -> Dict[str, Any]:
        """构建响应"""
        
        return {
            "results": final_results,
            "query": processed_query,
            "metadata": {
                "total_results": len(final_results),
                "vector_results": len(vector_results),
                "bm25_results": len(bm25_results),
                "processing_time": processing_time,
                "fusion_method": self.fusion_method,
                "query_rewrite_enabled": self.enable_query_rewrite,
                "enemy_boost_enabled": self.enable_enemy_boost,
                "detected_enemies": processed_query.get("detected_enemies", []),
                "query_intent": processed_query.get("intent", "unknown"),
                "intent_confidence": processed_query.get("confidence", 0.0)
            }
        }
    
    def _cache_result(self, cache_key: str, response: Dict[str, Any]) -> None:
        """缓存结果"""
        if len(self._result_cache) >= self._cache_size_limit:
            # 移除最老的缓存项
            oldest_key = next(iter(self._result_cache))
            del self._result_cache[oldest_key]
        
        self._result_cache[cache_key] = response
    
    def _get_time(self) -> float:
        """获取当前时间戳"""
        import time
        return time.time()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取检索器统计信息"""
        stats = {
            "fusion_method": self.fusion_method,
            "rrf_k": self.rrf_k,
            "query_rewrite_enabled": self.enable_query_rewrite,
            "enemy_boost_enabled": self.enable_enemy_boost,
            "cache_size": len(self._result_cache),
            "cache_limit": self._cache_size_limit
        }
        
        # 添加BM25统计
        if self.bm25_indexer:
            stats["bm25_stats"] = self.bm25_indexer.get_stats()
        else:
            stats["bm25_stats"] = {"status": "不可用"}
        
        return stats


class VectorRetrieverAdapter:
    """向量检索器适配器，用于适配现有的RAG查询接口"""
    
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
        try:
            if hasattr(self.rag_query, '_search_faiss'):
                return self.rag_query._search_faiss(query, top_k)
            elif hasattr(self.rag_query, '_search_qdrant'):
                return self.rag_query._search_qdrant(query, top_k)
            else:
                logger.error("向量检索器不支持搜索方法")
                return []
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []


def test_adaptive_retriever():
    """测试自适应混合检索器"""
    
    # 创建模拟的向量检索器
    class MockVectorRetriever:
        def search(self, query: str, top_k: int = 10):
            return [
                {
                    "chunk": {"chunk_id": "test_1", "topic": "Test Topic 1", "summary": "Test summary"},
                    "score": 0.8,
                    "rank": 1
                },
                {
                    "chunk": {"chunk_id": "test_2", "topic": "Test Topic 2", "summary": "Test summary 2"},
                    "score": 0.6,
                    "rank": 2
                }
            ]
    
    # 创建模拟的BM25索引文件（实际使用中应该是真实的索引）
    mock_vector_retriever = MockVectorRetriever()
    
    print("=== 自适应混合检索器测试 ===")
    print("注意：这是一个简化的测试，实际使用需要真实的BM25索引")
    
    # 显示配置信息
    retriever = AdaptiveHybridRetriever(
        vector_retriever=mock_vector_retriever,
        bm25_index_path="nonexistent.pkl",  # 模拟不存在的索引
        fusion_method="rrf"
    )
    
    print(f"检索器统计: {retriever.get_stats()}")
    
    # 测试查询处理
    if retriever.query_processor:
        test_query = "how to kill bile titan"
        processed = retriever.query_processor.rewrite_query(test_query)
        print(f"\n查询处理示例:")
        print(f"  原始: {processed['original']}")
        print(f"  重写: {processed['rewritten']}")
        print(f"  意图: {processed['intent']} (置信度: {processed['confidence']:.2f})")


if __name__ == "__main__":
    test_adaptive_retriever() 