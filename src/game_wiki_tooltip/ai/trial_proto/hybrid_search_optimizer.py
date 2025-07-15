"""
Hybrid Search 性能优化工具
==========================

功能：
1. 查询结果缓存
2. 并行搜索执行
3. 查询优化和预处理
4. 性能监控和统计
"""

import asyncio
import time
import hashlib
import logging
import threading
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SearchMetrics:
    """搜索性能指标"""
    query_time: float
    vector_search_time: float
    bm25_search_time: float
    fusion_time: float
    cache_hit: bool
    result_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "query_time": self.query_time,
            "vector_search_time": self.vector_search_time,
            "bm25_search_time": self.bm25_search_time,
            "fusion_time": self.fusion_time,
            "cache_hit": self.cache_hit,
            "result_count": self.result_count
        }


class QueryCache:
    """查询结果缓存"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.ttl = ttl
        self.cache = {}
        self.access_times = {}
        self.lock = threading.RLock()
    
    def _generate_key(self, query: str, config: Dict[str, Any]) -> str:
        """生成缓存key"""
        # 使用查询和配置生成唯一key
        key_data = {
            "query": query.strip().lower(),
            "config": config
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, query: str, config: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """获取缓存结果"""
        key = self._generate_key(query, config)
        
        with self.lock:
            if key in self.cache:
                cached_time, result = self.cache[key]
                
                # 检查是否过期
                if time.time() - cached_time < self.ttl:
                    self.access_times[key] = time.time()
                    logger.debug(f"缓存命中: {query}")
                    return result
                else:
                    # 删除过期缓存
                    del self.cache[key]
                    if key in self.access_times:
                        del self.access_times[key]
        
        return None
    
    def set(self, query: str, config: Dict[str, Any], result: List[Dict[str, Any]]) -> None:
        """设置缓存结果"""
        key = self._generate_key(query, config)
        
        with self.lock:
            # 如果缓存已满，删除最旧的条目
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.access_times, key=self.access_times.get)
                del self.cache[oldest_key]
                del self.access_times[oldest_key]
            
            self.cache[key] = (time.time(), result)
            self.access_times[key] = time.time()
            logger.debug(f"缓存设置: {query}")
    
    def clear(self) -> None:
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.access_times.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self.lock:
            return {
                "cache_size": len(self.cache),
                "max_size": self.max_size,
                "ttl": self.ttl,
                "hit_rate": 0.0  # 需要额外的统计来计算命中率
            }


class ParallelSearchExecutor:
    """并行搜索执行器"""
    
    def __init__(self, max_workers: int = 2):
        """
        初始化并行执行器
        
        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def execute_parallel_search(self, 
                               vector_retriever,
                               bm25_indexer,
                               query: str,
                               top_k: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float, float]:
        """
        并行执行向量搜索和BM25搜索
        
        Args:
            vector_retriever: 向量检索器
            bm25_indexer: BM25索引器
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            (向量搜索结果, BM25搜索结果, 向量搜索时间, BM25搜索时间)
        """
        # 提交并行任务
        vector_future = self.executor.submit(self._vector_search_wrapper, vector_retriever, query, top_k)
        bm25_future = self.executor.submit(self._bm25_search_wrapper, bm25_indexer, query, top_k)
        
        # 等待结果
        vector_result, vector_time = vector_future.result()
        bm25_result, bm25_time = bm25_future.result()
        
        return vector_result, bm25_result, vector_time, bm25_time
    
    def _vector_search_wrapper(self, vector_retriever, query: str, top_k: int) -> Tuple[List[Dict[str, Any]], float]:
        """向量搜索包装器"""
        start_time = time.time()
        try:
            result = vector_retriever.search(query, top_k)
            return result, time.time() - start_time
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return [], time.time() - start_time
    
    def _bm25_search_wrapper(self, bm25_indexer, query: str, top_k: int) -> Tuple[List[Dict[str, Any]], float]:
        """BM25搜索包装器"""
        start_time = time.time()
        try:
            result = bm25_indexer.search(query, top_k)
            return result, time.time() - start_time
        except Exception as e:
            logger.error(f"BM25搜索失败: {e}")
            return [], time.time() - start_time
    
    def shutdown(self):
        """关闭执行器"""
        self.executor.shutdown(wait=True)


class QueryOptimizer:
    """查询优化器"""
    
    def __init__(self):
        """初始化查询优化器"""
        self.stop_words = {
            # 中文停用词
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这',
            # 英文停用词
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must', 'shall'
        }
    
    def optimize_query(self, query: str) -> str:
        """
        优化查询
        
        Args:
            query: 原始查询
            
        Returns:
            优化后的查询
        """
        # 去除多余空格
        query = query.strip()
        
        # 转换为小写
        query = query.lower()
        
        # 移除特殊字符
        import re
        query = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', query)
        
        # 分词并去除停用词
        words = query.split()
        filtered_words = [word for word in words if word not in self.stop_words and len(word) > 1]
        
        return ' '.join(filtered_words)
    
    def extract_keywords(self, query: str) -> List[str]:
        """
        提取关键词
        
        Args:
            query: 查询文本
            
        Returns:
            关键词列表
        """
        optimized_query = self.optimize_query(query)
        keywords = optimized_query.split()
        
        # 按长度排序，长词优先
        keywords.sort(key=len, reverse=True)
        
        return keywords[:5]  # 返回前5个关键词
    
    def suggest_alternatives(self, query: str) -> List[str]:
        """
        建议替代查询
        
        Args:
            query: 原始查询
            
        Returns:
            建议的替代查询列表
        """
        alternatives = []
        
        # 关键词扩展
        keywords = self.extract_keywords(query)
        if len(keywords) > 1:
            # 尝试单个关键词
            alternatives.extend(keywords[:3])
            
            # 尝试关键词组合
            for i in range(len(keywords) - 1):
                combo = f"{keywords[i]} {keywords[i+1]}"
                alternatives.append(combo)
        
        return alternatives[:5]


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        """初始化性能监控器"""
        self.metrics = []
        self.total_queries = 0
        self.cache_hits = 0
        self.lock = threading.RLock()
    
    def record_search(self, metrics: SearchMetrics) -> None:
        """记录搜索指标"""
        with self.lock:
            self.metrics.append(metrics)
            self.total_queries += 1
            if metrics.cache_hit:
                self.cache_hits += 1
            
            # 保持最近1000条记录
            if len(self.metrics) > 1000:
                self.metrics = self.metrics[-1000:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            if not self.metrics:
                return {"message": "没有搜索记录"}
            
            # 计算平均值
            avg_query_time = sum(m.query_time for m in self.metrics) / len(self.metrics)
            avg_vector_time = sum(m.vector_search_time for m in self.metrics) / len(self.metrics)
            avg_bm25_time = sum(m.bm25_search_time for m in self.metrics) / len(self.metrics)
            avg_fusion_time = sum(m.fusion_time for m in self.metrics) / len(self.metrics)
            
            # 计算缓存命中率
            cache_hit_rate = self.cache_hits / self.total_queries if self.total_queries > 0 else 0
            
            return {
                "total_queries": self.total_queries,
                "cache_hit_rate": cache_hit_rate,
                "avg_query_time": avg_query_time,
                "avg_vector_search_time": avg_vector_time,
                "avg_bm25_search_time": avg_bm25_time,
                "avg_fusion_time": avg_fusion_time,
                "recent_metrics_count": len(self.metrics)
            }
    
    def export_metrics(self, filepath: str) -> None:
        """导出指标到文件"""
        with self.lock:
            data = {
                "total_queries": self.total_queries,
                "cache_hits": self.cache_hits,
                "metrics": [m.to_dict() for m in self.metrics]
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"性能指标已导出到: {filepath}")


class OptimizedHybridSearchRetriever:
    """优化的混合搜索检索器"""
    
    def __init__(self, 
                 base_retriever,
                 enable_cache: bool = True,
                 enable_parallel: bool = True,
                 enable_optimization: bool = True,
                 cache_size: int = 1000,
                 cache_ttl: int = 3600):
        """
        初始化优化的混合搜索检索器
        
        Args:
            base_retriever: 基础混合搜索检索器
            enable_cache: 是否启用缓存
            enable_parallel: 是否启用并行搜索
            enable_optimization: 是否启用查询优化
            cache_size: 缓存大小
            cache_ttl: 缓存过期时间
        """
        self.base_retriever = base_retriever
        self.enable_cache = enable_cache
        self.enable_parallel = enable_parallel
        self.enable_optimization = enable_optimization
        
        # 初始化组件
        self.cache = QueryCache(cache_size, cache_ttl) if enable_cache else None
        self.parallel_executor = ParallelSearchExecutor() if enable_parallel else None
        self.query_optimizer = QueryOptimizer() if enable_optimization else None
        self.performance_monitor = PerformanceMonitor()
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        执行优化的混合搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        start_time = time.time()
        
        # 查询优化
        optimized_query = query
        if self.enable_optimization:
            optimized_query = self.query_optimizer.optimize_query(query)
            logger.debug(f"查询优化: '{query}' -> '{optimized_query}'")
        
        # 生成缓存配置
        cache_config = {
            "fusion_method": self.base_retriever.fusion_method,
            "vector_weight": self.base_retriever.vector_weight,
            "bm25_weight": self.base_retriever.bm25_weight,
            "top_k": top_k
        }
        
        # 检查缓存
        cached_result = None
        if self.enable_cache:
            cached_result = self.cache.get(optimized_query, cache_config)
            if cached_result:
                # 记录缓存命中
                metrics = SearchMetrics(
                    query_time=time.time() - start_time,
                    vector_search_time=0,
                    bm25_search_time=0,
                    fusion_time=0,
                    cache_hit=True,
                    result_count=len(cached_result)
                )
                self.performance_monitor.record_search(metrics)
                return cached_result
        
        # 执行搜索
        vector_time = 0
        bm25_time = 0
        fusion_start_time = time.time()
        
        if self.enable_parallel:
            # 并行搜索
            vector_results, bm25_results, vector_time, bm25_time = self.parallel_executor.execute_parallel_search(
                self.base_retriever.vector_retriever,
                self.base_retriever.bm25_indexer,
                optimized_query,
                min(top_k * 3, 20)
            )
        else:
            # 串行搜索
            vector_start = time.time()
            vector_results = self.base_retriever.vector_retriever.search(optimized_query, min(top_k * 3, 20))
            vector_time = time.time() - vector_start
            
            bm25_start = time.time()
            bm25_results = self.base_retriever.bm25_indexer.search(optimized_query, min(top_k * 3, 20))
            bm25_time = time.time() - bm25_start
        
        # 分数融合
        if self.base_retriever.fusion_method == "rrf":
            results = self.base_retriever._reciprocal_rank_fusion(vector_results, bm25_results, top_k)
        elif self.base_retriever.fusion_method == "weighted":
            results = self.base_retriever._weighted_fusion(vector_results, bm25_results, top_k)
        else:
            results = self.base_retriever._normalized_fusion(vector_results, bm25_results, top_k)
        
        fusion_time = time.time() - fusion_start_time
        
        # 缓存结果
        if self.enable_cache:
            self.cache.set(optimized_query, cache_config, results)
        
        # 记录性能指标
        metrics = SearchMetrics(
            query_time=time.time() - start_time,
            vector_search_time=vector_time,
            bm25_search_time=bm25_time,
            fusion_time=fusion_time,
            cache_hit=False,
            result_count=len(results)
        )
        self.performance_monitor.record_search(metrics)
        
        return results
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        stats = {
            "performance": self.performance_monitor.get_statistics(),
            "cache": self.cache.get_stats() if self.cache else {"enabled": False},
            "parallel": {"enabled": self.enable_parallel},
            "optimization": {"enabled": self.enable_optimization}
        }
        return stats
    
    def clear_cache(self) -> None:
        """清空缓存"""
        if self.cache:
            self.cache.clear()
    
    def shutdown(self) -> None:
        """关闭资源"""
        if self.parallel_executor:
            self.parallel_executor.shutdown()


def create_optimized_retriever(base_retriever, 
                             performance_config: Optional[Dict[str, Any]] = None) -> OptimizedHybridSearchRetriever:
    """
    创建优化的混合搜索检索器
    
    Args:
        base_retriever: 基础混合搜索检索器
        performance_config: 性能配置
        
    Returns:
        优化的混合搜索检索器
    """
    config = performance_config or {}
    
    return OptimizedHybridSearchRetriever(
        base_retriever=base_retriever,
        enable_cache=config.get("enable_cache", True),
        enable_parallel=config.get("enable_parallel", True),
        enable_optimization=config.get("enable_optimization", True),
        cache_size=config.get("cache_size", 1000),
        cache_ttl=config.get("cache_ttl", 3600)
    )


# 示例使用
if __name__ == "__main__":
    print("混合搜索性能优化工具")
    print("此模块提供缓存、并行搜索和查询优化功能")
    print("请在实际应用中使用create_optimized_retriever函数") 