"""
增强的RAG查询接口 - 集成批量嵌入和向量库检索
============================================

功能：
1. 加载预构建的向量库
2. 执行语义检索
3. 返回相关游戏攻略信息
"""

import logging
import asyncio
import json
import numpy as np
from typing import Optional, Dict, Any, List
from pathlib import Path

# 导入批量嵌入处理器
try:
    from .batch_embedding import BatchEmbeddingProcessor
    BATCH_EMBEDDING_AVAILABLE = True
except ImportError:
    BATCH_EMBEDDING_AVAILABLE = False
    logging.warning("批量嵌入模块不可用")

# 向量库支持
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logging.warning("FAISS不可用")

try:
    import qdrant_client
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logging.warning("Qdrant不可用")

logger = logging.getLogger(__name__)

class EnhancedRagQuery:
    """增强的RAG查询接口，支持向量库检索"""
    
    def __init__(self, vector_store_path: Optional[str] = None):
        """
        初始化RAG查询器
        
        Args:
            vector_store_path: 向量库路径，如果为None则使用默认路径
        """
        self.is_initialized = False
        self.vector_store_path = vector_store_path
        self.vector_store = None
        self.metadata = None
        self.config = None
        self.processor = None
        
    async def initialize(self, game_name: Optional[str] = None):
        """
        初始化RAG系统
        
        Args:
            game_name: 游戏名称，用于自动查找向量库
        """
        try:
            logger.info("初始化增强RAG系统...")
            
            if not BATCH_EMBEDDING_AVAILABLE:
                logger.warning("批量嵌入模块不可用，使用模拟模式")
                self.is_initialized = True
                return
            
            # 确定向量库路径
            if self.vector_store_path is None and game_name:
                # 自动查找向量库
                vector_dir = Path("src/game_wiki_tooltip/ai/vectorstore")
                config_files = list(vector_dir.glob(f"{game_name}_vectors_config.json"))
                
                if config_files:
                    self.vector_store_path = str(config_files[0])
                    logger.info(f"找到向量库配置: {self.vector_store_path}")
                else:
                    logger.warning(f"未找到游戏 {game_name} 的向量库，使用模拟模式")
                    self.is_initialized = True
                    return
            
            if self.vector_store_path and Path(self.vector_store_path).exists():
                # 加载向量库
                self.processor = BatchEmbeddingProcessor()
                self.vector_store = self.processor.load_vector_store(self.vector_store_path)
                
                # 加载配置和元数据
                with open(self.vector_store_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                
                if self.config["vector_store_type"] == "faiss":
                    self.metadata = self.vector_store["metadata"]
                
                logger.info(f"向量库加载完成: {self.config['chunk_count']} 个知识块")
            else:
                logger.warning("向量库不可用，使用模拟模式")
            
            self.is_initialized = True
            logger.info("增强RAG系统初始化完成")
            
        except Exception as e:
            logger.error(f"RAG系统初始化失败: {e}")
            self.is_initialized = False
    
    def _search_faiss(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        使用FAISS进行向量检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            检索结果列表
        """
        if not self.vector_store or not self.metadata:
            return []
        
        try:
            # 获取查询向量
            query_text = self.processor.build_text({"topic": query, "summary": query, "keywords": []})
            query_vectors = self.processor.embed_batch([query_text])
            query_vector = np.array(query_vectors[0], dtype=np.float32).reshape(1, -1)
            
            # 加载FAISS索引
            index_path = Path(self.config["index_path"])
            index = faiss.read_index(str(index_path / "index.faiss"))
            
            # 执行检索
            scores, indices = index.search(query_vector, top_k)
            
            # 返回结果
            results = []
            for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                if idx < len(self.metadata):
                    chunk = self.metadata[idx]
                    results.append({
                        "chunk": chunk,
                        "score": float(score),
                        "rank": i + 1
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"FAISS检索失败: {e}")
            return []
    
    def _search_qdrant(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        使用Qdrant进行向量检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            检索结果列表
        """
        if not self.vector_store or not QDRANT_AVAILABLE:
            return []
        
        try:
            # 获取查询向量
            query_text = self.processor.build_text({"topic": query, "summary": query, "keywords": []})
            query_vectors = self.processor.embed_batch([query_text])
            
            # 执行检索
            results = self.vector_store.search(
                collection_name=self.config["collection_name"],
                query_vector=query_vectors[0],
                limit=top_k
            )
            
            # 格式化结果
            formatted_results = []
            for i, result in enumerate(results):
                formatted_results.append({
                    "chunk": result.payload,
                    "score": result.score,
                    "rank": i + 1
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Qdrant检索失败: {e}")
            return []
    
    def _format_answer(self, results: List[Dict[str, Any]], question: str) -> str:
        """
        格式化检索结果为答案
        
        Args:
            results: 检索结果
            question: 原始问题
            
        Returns:
            格式化的答案
        """
        if not results:
            return f"抱歉，没有找到关于'{question}'的相关信息。"
        
        answer_parts = [f"关于'{question}'的攻略信息：\n"]
        
        for result in results:
            chunk = result["chunk"]
            score = result["score"]
            
            # 提取关键信息
            topic = chunk.get("topic", "未知主题")
            summary = chunk.get("summary", "")
            
            answer_parts.append(f"\n【{topic}】")
            answer_parts.append(f"相关度: {score:.3f}")
            answer_parts.append(f"{summary}")
            
            # 如果有build信息，添加配装建议
            if "build" in chunk:
                build = chunk["build"]
                if "name" in build:
                    answer_parts.append(f"\n推荐配装: {build['name']}")
                if "focus" in build:
                    answer_parts.append(f"配装重点: {build['focus']}")
                
                # 添加关键装备信息
                if "stratagems" in build:
                    stratagems = [s["name"] for s in build["stratagems"]]
                    answer_parts.append(f"核心装备: {', '.join(stratagems[:3])}")
        
        return "\n".join(answer_parts)
    
    async def query(self, question: str, top_k: int = 3) -> Dict[str, Any]:
        """
        执行RAG查询
        
        Args:
            question: 用户问题
            top_k: 检索结果数量
            
        Returns:
            包含答案的字典
        """
        if not self.is_initialized:
            await self.initialize()
        
        try:
            logger.info(f"RAG查询: {question}")
            start_time = asyncio.get_event_loop().time()
            
            # 执行向量检索
            if self.vector_store and self.config:
                if self.config["vector_store_type"] == "faiss":
                    results = self._search_faiss(question, top_k)
                else:
                    results = self._search_qdrant(question, top_k)
                
                answer = self._format_answer(results, question)
                confidence = max([r["score"] for r in results]) if results else 0.0
                sources = [r["chunk"].get("topic", "未知") for r in results]
                
            else:
                # 回退到模拟模式
                await asyncio.sleep(0.5)
                answer = self._get_mock_answer(question)
                confidence = 0.8
                sources = ["模拟知识库"]
            
            query_time = asyncio.get_event_loop().time() - start_time
            
            return {
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
                "query_time": query_time,
                "results_count": len(results) if 'results' in locals() else 0
            }
            
        except Exception as e:
            logger.error(f"RAG查询失败: {e}")
            return {
                "answer": "抱歉，查询过程中出现错误，请稍后重试。",
                "sources": [],
                "confidence": 0.0,
                "query_time": 0.0,
                "error": str(e)
            }
    
    def _get_mock_answer(self, question: str) -> str:
        """获取模拟答案（用于测试）"""
        question_lower = question.lower()
        
        if "好感度" in question_lower or "关系" in question_lower:
            return """提升好感度的方法：
1. 送礼物：每个角色都有喜欢的礼物，送对礼物能快速提升好感度
2. 对话：每天与角色对话
3. 参加节日活动
4. 完成角色任务

建议：艾米丽喜欢羊毛、布料等手工制品；谢恩喜欢啤酒和披萨。"""
        
        elif "赚钱" in question_lower or "收入" in question_lower:
            return """赚钱攻略：
1. 种植高价值作物：草莓、蓝莓、蔓越莓
2. 养殖动物：鸡、牛、羊
3. 钓鱼：不同季节有不同鱼类
4. 挖矿：获得宝石和矿石
5. 制作手工艺品：果酱、奶酪等

最佳策略：春季种植草莓，夏季种植蓝莓，秋季种植蔓越莓。"""
        
        elif "新手" in question_lower or "入门" in question_lower:
            return """新手入门指南：
1. 第一周：清理农场，种植防风草
2. 第二周：建造鸡舍，开始养殖
3. 第三周：升级工具，扩大种植
4. 第四周：参加春季节日

重点：优先升级水壶和锄头，多与村民互动。"""
        
        else:
            return f"关于'{question}'的攻略：\n\n这是一个通用的游戏攻略建议。建议您尝试不同的游戏策略，探索游戏中的各种可能性。记住，每个玩家都有自己独特的游戏风格！"


# 全局实例
_enhanced_rag_query = None

def get_enhanced_rag_query(vector_store_path: Optional[str] = None) -> EnhancedRagQuery:
    """获取增强RAG查询器的单例实例"""
    global _enhanced_rag_query
    if _enhanced_rag_query is None:
        _enhanced_rag_query = EnhancedRagQuery(vector_store_path)
    return _enhanced_rag_query

async def query_enhanced_rag(question: str, 
                           game_name: Optional[str] = None,
                           top_k: int = 3) -> Dict[str, Any]:
    """
    执行增强RAG查询的便捷函数
    
    Args:
        question: 用户问题
        game_name: 游戏名称，用于自动加载对应向量库
        top_k: 检索结果数量
        
    Returns:
        查询结果
    """
    rag_query = get_enhanced_rag_query()
    if not rag_query.is_initialized:
        await rag_query.initialize(game_name)
    return await rag_query.query(question, top_k)

# 保持向后兼容
class SimpleRagQuery(EnhancedRagQuery):
    """保持向后兼容的简单RAG查询接口"""
    pass

def get_rag_query() -> SimpleRagQuery:
    """获取RAG查询器的单例实例（向后兼容）"""
    return get_enhanced_rag_query()

async def query_rag(question: str) -> Dict[str, Any]:
    """执行RAG查询的便捷函数（向后兼容）"""
    return await query_enhanced_rag(question) 