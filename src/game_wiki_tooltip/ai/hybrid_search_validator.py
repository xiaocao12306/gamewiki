"""
混合搜索验证工具
================

功能：
1. 验证BM25索引是否存在和可用
2. 测试向量搜索和BM25搜索的性能
3. 验证结果融合算法的正确性
4. 提供混合搜索的健康检查
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import json

logger = logging.getLogger(__name__)

class HybridSearchValidator:
    """混合搜索验证器"""
    
    def __init__(self, config_path: str):
        """
        初始化验证器
        
        Args:
            config_path: 向量库配置文件路径
        """
        self.config_path = config_path
        self.config = None
        self.validation_results = {}
        
        # 加载配置
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
                logger.info(f"配置加载成功: {self.config_path}")
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            self.config = None
    
    def validate_bm25_index(self) -> Dict[str, Any]:
        """验证BM25索引"""
        validation_result = {
            "status": "unknown",
            "exists": False,
            "loadable": False,
            "document_count": 0,
            "index_size": 0,
            "error": None
        }
        
        try:
            if not self.config:
                validation_result["status"] = "failed"
                validation_result["error"] = "配置未加载"
                return validation_result
            
            bm25_index_path = self.config.get("bm25_index_path")
            if not bm25_index_path:
                validation_result["status"] = "failed"
                validation_result["error"] = "配置中未找到BM25索引路径"
                return validation_result
            
            # 检查文件是否存在
            bm25_path = Path(bm25_index_path)
            if not bm25_path.exists():
                validation_result["status"] = "failed"
                validation_result["error"] = f"BM25索引文件不存在: {bm25_index_path}"
                return validation_result
            
            validation_result["exists"] = True
            validation_result["index_size"] = bm25_path.stat().st_size
            
            # 尝试加载BM25索引
            try:
                from .bm25_indexer import BM25Indexer
                
                bm25_indexer = BM25Indexer()
                bm25_indexer.load_index(str(bm25_path))
                
                validation_result["loadable"] = True
                validation_result["document_count"] = len(bm25_indexer.documents)
                validation_result["status"] = "success"
                
                logger.info(f"BM25索引验证成功: {bm25_indexer.get_stats()}")
                
            except Exception as e:
                validation_result["status"] = "failed"
                validation_result["error"] = f"BM25索引加载失败: {str(e)}"
                
        except Exception as e:
            validation_result["status"] = "failed"
            validation_result["error"] = f"BM25索引验证异常: {str(e)}"
        
        return validation_result
    
    def validate_vector_search(self) -> Dict[str, Any]:
        """验证向量搜索"""
        validation_result = {
            "status": "unknown",
            "index_exists": False,
            "metadata_exists": False,
            "loadable": False,
            "vector_count": 0,
            "error": None
        }
        
        try:
            if not self.config:
                validation_result["status"] = "failed"
                validation_result["error"] = "配置未加载"
                return validation_result
            
            index_path = self.config.get("index_path")
            if not index_path:
                validation_result["status"] = "failed"
                validation_result["error"] = "配置中未找到索引路径"
                return validation_result
            
            # 检查索引文件
            index_dir = Path(index_path)
            faiss_index = index_dir / "index.faiss"
            metadata_file = index_dir / "metadata.json"
            
            validation_result["index_exists"] = faiss_index.exists()
            validation_result["metadata_exists"] = metadata_file.exists()
            
            if not validation_result["index_exists"]:
                validation_result["status"] = "failed"
                validation_result["error"] = f"FAISS索引文件不存在: {faiss_index}"
                return validation_result
            
            if not validation_result["metadata_exists"]:
                validation_result["status"] = "failed"
                validation_result["error"] = f"元数据文件不存在: {metadata_file}"
                return validation_result
            
            # 尝试加载元数据
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                validation_result["vector_count"] = len(metadata)
                validation_result["loadable"] = True
                validation_result["status"] = "success"
                
                logger.info(f"向量搜索验证成功: {len(metadata)} 个向量")
                
            except Exception as e:
                validation_result["status"] = "failed"
                validation_result["error"] = f"元数据加载失败: {str(e)}"
                
        except Exception as e:
            validation_result["status"] = "failed"
            validation_result["error"] = f"向量搜索验证异常: {str(e)}"
        
        return validation_result
    
    def test_hybrid_search_performance(self, test_queries: List[str] = None) -> Dict[str, Any]:
        """测试混合搜索性能"""
        if test_queries is None:
            test_queries = [
                "地狱潜兵配装推荐",
                "虫族敌人攻略",
                "武器选择建议",
                "角色技能",
                "游戏攻略"
            ]
        
        performance_result = {
            "total_queries": len(test_queries),
            "successful_queries": 0,
            "failed_queries": 0,
            "average_response_time": 0.0,
            "query_results": [],
            "error": None
        }
        
        try:
            # 初始化RAG查询器
            from .rag_query import EnhancedRagQuery
            from ..config import LLMConfig
            
            rag_query = EnhancedRagQuery(
                vector_store_path=self.config_path,
                enable_hybrid_search=True,
                llm_config=LLMConfig()
            )
            
            # 异步初始化
            import asyncio
            async def run_tests():
                await rag_query.initialize()
                
                total_time = 0.0
                for query in test_queries:
                    start_time = time.time()
                    
                    try:
                        result = await rag_query.query(query, top_k=3)
                        query_time = time.time() - start_time
                        total_time += query_time
                        
                        performance_result["successful_queries"] += 1
                        performance_result["query_results"].append({
                            "query": query,
                            "success": True,
                            "response_time": query_time,
                            "result_count": result.get("results_count", 0),
                            "confidence": result.get("confidence", 0.0)
                        })
                        
                    except Exception as e:
                        query_time = time.time() - start_time
                        total_time += query_time
                        
                        performance_result["failed_queries"] += 1
                        performance_result["query_results"].append({
                            "query": query,
                            "success": False,
                            "response_time": query_time,
                            "error": str(e)
                        })
                
                if performance_result["successful_queries"] > 0:
                    performance_result["average_response_time"] = total_time / len(test_queries)
            
            # 运行异步测试
            asyncio.run(run_tests())
            
        except Exception as e:
            performance_result["error"] = f"性能测试失败: {str(e)}"
        
        return performance_result
    
    def validate_fusion_algorithms(self) -> Dict[str, Any]:
        """验证融合算法"""
        fusion_result = {
            "rrf_available": False,
            "weighted_available": False,
            "normalized_available": False,
            "error": None
        }
        
        try:
            from .hybrid_retriever import HybridSearchRetriever
            
            # 创建测试数据
            test_vector_results = [
                {"chunk_id": "test1", "score": 0.9, "chunk": {"topic": "测试1"}},
                {"chunk_id": "test2", "score": 0.8, "chunk": {"topic": "测试2"}},
                {"chunk_id": "test3", "score": 0.7, "chunk": {"topic": "测试3"}},
            ]
            
            test_bm25_results = [
                {"chunk_id": "test1", "score": 2.1, "chunk": {"topic": "测试1"}},
                {"chunk_id": "test4", "score": 1.8, "chunk": {"topic": "测试4"}},
                {"chunk_id": "test2", "score": 1.5, "chunk": {"topic": "测试2"}},
            ]
            
            # 创建虚拟的混合检索器来测试融合算法
            class TestHybridRetriever(HybridSearchRetriever):
                def __init__(self):
                    self.fusion_method = "rrf"
                    self.vector_weight = 0.6
                    self.bm25_weight = 0.4
                    self.rrf_k = 60
            
            test_retriever = TestHybridRetriever()
            
            # 测试RRF
            try:
                rrf_results = test_retriever._reciprocal_rank_fusion(
                    test_vector_results, test_bm25_results, 3
                )
                fusion_result["rrf_available"] = len(rrf_results) > 0
            except Exception as e:
                logger.error(f"RRF测试失败: {e}")
            
            # 测试加权融合
            try:
                weighted_results = test_retriever._weighted_fusion(
                    test_vector_results, test_bm25_results, 3
                )
                fusion_result["weighted_available"] = len(weighted_results) > 0
            except Exception as e:
                logger.error(f"加权融合测试失败: {e}")
            
            # 测试归一化融合
            try:
                normalized_results = test_retriever._normalized_fusion(
                    test_vector_results, test_bm25_results, 3
                )
                fusion_result["normalized_available"] = len(normalized_results) > 0
            except Exception as e:
                logger.error(f"归一化融合测试失败: {e}")
                
        except Exception as e:
            fusion_result["error"] = f"融合算法验证失败: {str(e)}"
        
        return fusion_result
    
    def run_full_validation(self) -> Dict[str, Any]:
        """运行完整验证"""
        logger.info("开始混合搜索完整验证...")
        
        validation_results = {
            "timestamp": time.time(),
            "config_path": self.config_path,
            "bm25_validation": self.validate_bm25_index(),
            "vector_validation": self.validate_vector_search(),
            "fusion_validation": self.validate_fusion_algorithms(),
            "performance_test": None,
            "overall_status": "unknown",
            "recommendations": []
        }
        
        # 如果基础验证通过，进行性能测试
        if (validation_results["bm25_validation"]["status"] == "success" and 
            validation_results["vector_validation"]["status"] == "success"):
            
            validation_results["performance_test"] = self.test_hybrid_search_performance()
            
            # 判断整体状态
            if validation_results["performance_test"]["successful_queries"] > 0:
                validation_results["overall_status"] = "success"
            else:
                validation_results["overall_status"] = "partial"
                validation_results["recommendations"].append("性能测试失败，建议检查RAG查询器配置")
        else:
            validation_results["overall_status"] = "failed"
            
            # 添加建议
            if validation_results["bm25_validation"]["status"] != "success":
                validation_results["recommendations"].append("BM25索引不可用，建议重新构建索引")
            
            if validation_results["vector_validation"]["status"] != "success":
                validation_results["recommendations"].append("向量搜索不可用，建议检查FAISS索引")
        
        logger.info(f"混合搜索验证完成，整体状态: {validation_results['overall_status']}")
        return validation_results
    
    def generate_report(self, validation_results: Dict[str, Any]) -> str:
        """生成验证报告"""
        report_lines = [
            "=" * 60,
            "混合搜索验证报告",
            "=" * 60,
            f"配置文件: {validation_results['config_path']}",
            f"验证时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(validation_results['timestamp']))}",
            f"整体状态: {validation_results['overall_status']}",
            "",
            "BM25索引验证:",
            f"  状态: {validation_results['bm25_validation']['status']}",
            f"  文件存在: {validation_results['bm25_validation']['exists']}",
            f"  可加载: {validation_results['bm25_validation']['loadable']}",
            f"  文档数量: {validation_results['bm25_validation']['document_count']}",
            "",
            "向量搜索验证:",
            f"  状态: {validation_results['vector_validation']['status']}",
            f"  索引存在: {validation_results['vector_validation']['index_exists']}",
            f"  元数据存在: {validation_results['vector_validation']['metadata_exists']}",
            f"  向量数量: {validation_results['vector_validation']['vector_count']}",
            "",
            "融合算法验证:",
            f"  RRF可用: {validation_results['fusion_validation']['rrf_available']}",
            f"  加权融合可用: {validation_results['fusion_validation']['weighted_available']}",
            f"  归一化融合可用: {validation_results['fusion_validation']['normalized_available']}",
            ""
        ]
        
        # 性能测试结果
        if validation_results.get("performance_test"):
            perf = validation_results["performance_test"]
            report_lines.extend([
                "性能测试结果:",
                f"  总查询数: {perf['total_queries']}",
                f"  成功查询数: {perf['successful_queries']}",
                f"  失败查询数: {perf['failed_queries']}",
                f"  平均响应时间: {perf['average_response_time']:.3f}秒",
                ""
            ])
        
        # 建议
        if validation_results.get("recommendations"):
            report_lines.extend([
                "建议:",
                *[f"  - {rec}" for rec in validation_results["recommendations"]],
                ""
            ])
        
        report_lines.append("=" * 60)
        
        return "\n".join(report_lines)


def validate_hybrid_search(config_path: str) -> Dict[str, Any]:
    """
    验证混合搜索的便捷函数
    
    Args:
        config_path: 向量库配置文件路径
        
    Returns:
        验证结果字典
    """
    validator = HybridSearchValidator(config_path)
    return validator.run_full_validation()


if __name__ == "__main__":
    # 示例使用
    import sys
    
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        validator = HybridSearchValidator(config_path)
        results = validator.run_full_validation()
        print(validator.generate_report(results))
    else:
        print("使用方法: python hybrid_search_validator.py <config_path>") 