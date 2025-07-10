"""
增强的RAG查询接口 - 集成批量嵌入和向量库检索
============================================

功能：
1. 加载预构建的向量库
2. 执行语义检索
3. 支持LLM查询重写
4. 混合搜索（向量+BM25）
5. 返回相关游戏攻略信息
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

# 导入Gemini摘要器
try:
    from .gemini_summarizer import create_gemini_summarizer, SummarizationConfig
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Gemini摘要模块不可用")

# 导入意图感知重排序器
try:
    from .intent_aware_reranker import IntentAwareReranker
    RERANKER_AVAILABLE = True
except ImportError:
    RERANKER_AVAILABLE = False
    logging.warning("意图重排序模块不可用")

# 导入配置和查询重写
from ..config import LLMConfig

logger = logging.getLogger(__name__)

def map_window_title_to_game_name(window_title: str) -> Optional[str]:
    """
    将窗口标题映射到向量库文件名
    
    Args:
        window_title: 窗口标题
        
    Returns:
        对应的向量库文件名（不包含.json扩展名），如果未找到则返回None
    """
    # 转换为小写进行匹配
    title_lower = window_title.lower()
    
    # 窗口标题到向量库文件名的映射（基于实际存在的向量库文件）
    title_to_vectordb_mapping = {
        "don't starve together": "dst",
        "don't starve": "dst",
        "饥荒": "dst",
        "helldivers 2": "helldiver2",
        "地狱潜兵2": "helldiver2",
        "地狱潜兵": "helldiver2",
        "elden ring": "eldenring",
        "艾尔登法环": "eldenring",
        "老头环": "eldenring",
        "civilization vi": "civilization6",
        "civilization 6": "civilization6",
        "文明6": "civilization6",
        "7 days to die": "7daystodie",
        "七日杀": "7daystodie",
    }
    
    # 尝试精确匹配
    for title_key, vectordb_name in title_to_vectordb_mapping.items():
        if title_key in title_lower:
            logger.info(f"窗口标题 '{window_title}' 映射到向量库 '{vectordb_name}'")
            return vectordb_name
    
    # 如果没有找到映射，记录警告并返回None
    logger.warning(f"未找到窗口标题 '{window_title}' 对应的向量库映射")
    return None

class EnhancedRagQuery:
    """增强的RAG查询接口，支持向量库检索和LLM查询重写"""
    
    def __init__(self, vector_store_path: Optional[str] = None,
                 enable_hybrid_search: bool = True,
                 hybrid_config: Optional[Dict] = None,
                 llm_config: Optional[LLMConfig] = None,
                 enable_query_rewrite: bool = True,
                 enable_summarization: bool = False,
                 summarization_config: Optional[Dict] = None,
                 enable_intent_reranking: bool = True,
                 reranking_config: Optional[Dict] = None):
        """
        初始化RAG查询器
        
        Args:
            vector_store_path: 向量库路径，如果为None则使用默认路径
            enable_hybrid_search: 是否启用混合搜索
            hybrid_config: 混合搜索配置
            llm_config: LLM配置
            enable_query_rewrite: 是否启用查询重写
            enable_summarization: 是否启用Gemini摘要
            summarization_config: 摘要配置
            enable_intent_reranking: 是否启用意图感知重排序
            reranking_config: 重排序配置
        """
        self.is_initialized = False
        self.vector_store_path = vector_store_path
        self.vector_store = None
        self.metadata = None
        self.config = None
        self.processor = None
        self.enable_hybrid_search = enable_hybrid_search
        self.hybrid_config = hybrid_config or {
            "fusion_method": "rrf",
            "vector_weight": 0.3,
            "bm25_weight": 0.7,
            "rrf_k": 60
        }
        self.llm_config = llm_config
        self.enable_query_rewrite = enable_query_rewrite
        self.hybrid_retriever = None
        
        # 摘要配置
        self.enable_summarization = enable_summarization and GEMINI_AVAILABLE
        self.summarization_config = summarization_config or {}
        self.summarizer = None
        
        # 意图重排序配置
        self.enable_intent_reranking = enable_intent_reranking and RERANKER_AVAILABLE
        self.reranking_config = reranking_config or {
            "intent_weight": 0.4,
            "semantic_weight": 0.6
        }
        self.reranker = None
        
        # 初始化摘要器
        if self.enable_summarization:
            self._initialize_summarizer()
            
        # 初始化重排序器
        if self.enable_intent_reranking:
            self._initialize_reranker()
        
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
                # 自动查找向量库 - 使用绝对路径
                import os
                current_dir = Path(__file__).parent
                vector_dir = current_dir / "vectorstore"
                
                logger.info(f"查找向量库目录: {vector_dir}")
                config_files = list(vector_dir.glob(f"{game_name}_vectors_config.json"))
                
                if config_files:
                    self.vector_store_path = str(config_files[0])
                    logger.info(f"找到向量库配置: {self.vector_store_path}")
                else:
                    logger.warning(f"未找到游戏 {game_name} 的向量库，搜索路径: {vector_dir}")
                    logger.warning(f"查找模式: {game_name}_vectors_config.json")
                    # 列出现有的文件用于调试
                    try:
                        existing_files = list(vector_dir.glob("*_vectors_config.json"))
                        logger.info(f"现有的向量库配置文件: {[f.name for f in existing_files]}")
                    except Exception as e:
                        logger.error(f"列出现有文件失败: {e}")
                    # 不立即返回，让后续代码处理这种情况
                    self.vector_store_path = None
            
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
                
                # 初始化混合检索器
                if self.enable_hybrid_search:
                    self._initialize_hybrid_retriever()
                    
            else:
                logger.warning("向量库不可用，使用模拟模式")
            
            self.is_initialized = True
            logger.info("增强RAG系统初始化完成")
            
        except Exception as e:
            logger.error(f"RAG系统初始化失败: {e}")
            self.is_initialized = False
    
    def _initialize_hybrid_retriever(self):
        """初始化混合检索器"""
        if not self.config or not self.config.get("hybrid_search_enabled", False):
            logger.warning("混合搜索未启用，将仅使用向量搜索")
            return
        
        try:
            from .hybrid_retriever import HybridSearchRetriever, VectorRetrieverAdapter
            
            bm25_index_path = self.config.get("bm25_index_path")
            if not bm25_index_path:
                logger.warning("BM25索引路径未找到，将仅使用向量搜索")
                return
            
            # 检查BM25索引文件是否存在
            from pathlib import Path
            if not Path(bm25_index_path).exists():
                logger.warning(f"BM25索引文件不存在: {bm25_index_path}，将仅使用向量搜索")
                return
            
            # 创建向量检索器适配器
            vector_retriever = VectorRetrieverAdapter(self)
            
            # 创建混合检索器 - 默认启用统一处理以提高性能
            self.hybrid_retriever = HybridSearchRetriever(
                vector_retriever=vector_retriever,
                bm25_index_path=bm25_index_path,
                fusion_method=self.hybrid_config.get("fusion_method", "rrf"),
                vector_weight=self.hybrid_config.get("vector_weight", 0.3),
                bm25_weight=self.hybrid_config.get("bm25_weight", 0.7),
                rrf_k=self.hybrid_config.get("rrf_k", 60),
                llm_config=self.llm_config,
                enable_unified_processing=True,  # 启用统一处理以提高性能
                enable_query_rewrite=self.enable_query_rewrite,
                enable_query_translation=self.enable_summarization and self.enable_query_rewrite  # 仅在统一处理禁用时使用
            )
            
            logger.info("混合检索器初始化成功（统一处理模式）")
            
        except Exception as e:
            logger.error(f"混合检索器初始化失败: {e}")
            logger.info("将回退到仅使用向量搜索模式")
    
    def _initialize_summarizer(self):
        """初始化Gemini摘要器"""
        try:
            import os
            
            # 获取API密钥
            api_key = self.summarization_config.get("api_key") or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                logger.warning("未找到Gemini API密钥，摘要功能将被禁用")
                self.enable_summarization = False
                return
            
            # 创建摘要配置
            config = SummarizationConfig(
                api_key=api_key,
                model_name=self.summarization_config.get("model_name", "gemini-2.5-flash-lite-preview-06-17"),
                max_summary_length=self.summarization_config.get("max_summary_length", 300),
                temperature=self.summarization_config.get("temperature", 0.3),
                include_sources=self.summarization_config.get("include_sources", True),
                language=self.summarization_config.get("language", "auto")
            )
            
            # 创建摘要器
            self.summarizer = create_gemini_summarizer(
                api_key=api_key,
                model_name=config.model_name,
                max_summary_length=config.max_summary_length,
                temperature=config.temperature,
                include_sources=config.include_sources,
                language=config.language
            )
            
            logger.info(f"Gemini摘要器初始化成功: {config.model_name}")
            
        except Exception as e:
            logger.error(f"Gemini摘要器初始化失败: {e}")
            self.enable_summarization = False
    
    def _initialize_reranker(self):
        """初始化意图感知重排序器"""
        try:
            self.reranker = IntentAwareReranker()
            logger.info("意图感知重排序器初始化成功")
        except Exception as e:
            logger.error(f"意图重排序器初始化失败: {e}")
            self.enable_intent_reranking = False
    
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
            
            # 构建正确的索引文件路径
            # 使用与BatchEmbeddingProcessor._load_faiss_store相同的路径逻辑
            index_path_str = self.config["index_path"]
            if not Path(index_path_str).is_absolute():
                # 使用向量库存储路径来构建绝对路径
                current_dir = Path(__file__).parent
                index_path = current_dir / "vectorstore" / Path(index_path_str).name
            else:
                index_path = Path(index_path_str)
            
            index_file_path = index_path / "index.faiss"
            logger.info(f"尝试加载FAISS索引文件: {index_file_path}")
            
            if not index_file_path.exists():
                logger.error(f"FAISS索引文件不存在: {index_file_path}")
                return []
            
            # 加载FAISS索引
            index = faiss.read_index(str(index_file_path))
            
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
            
            logger.info(f"FAISS检索完成，找到 {len(results)} 个结果")
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
    
    def _search_hybrid(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        """
        使用混合搜索进行检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            混合搜索结果（包含元数据）
        """
        if not self.hybrid_retriever:
            logger.warning("混合检索器未初始化，回退到向量搜索")
            results = self._search_faiss(query, top_k) if self.config["vector_store_type"] == "faiss" else self._search_qdrant(query, top_k)
            return {
                "results": results,
                "query": {"original": query, "rewritten": query, "rewrite_applied": False},
                "metadata": {
                    "total_results": len(results),
                    "search_type": "vector_fallback",
                    "fusion_method": "none",
                    "rewrite_info": {
                        "intent": "unknown",
                        "confidence": 0.0,
                        "reasoning": "混合检索器未初始化"
                    }
                }
            }
        
        # 执行混合搜索
        try:
            search_response = self.hybrid_retriever.search(query, top_k)
            logger.info(f"混合搜索完成，找到 {len(search_response.get('results', []))} 个结果")
            return search_response
        except Exception as e:
            logger.error(f"混合搜索失败: {e}")
            # 回退到向量搜索
            results = self._search_faiss(query, top_k) if self.config["vector_store_type"] == "faiss" else self._search_qdrant(query, top_k)
            return {
                "results": results,
                "query": {"original": query, "rewritten": query, "rewrite_applied": False},
                "metadata": {
                    "total_results": len(results),
                    "search_type": "vector_fallback",
                    "fusion_method": "none",
                    "rewrite_info": {
                        "intent": "unknown",
                        "confidence": 0.0,
                        "reasoning": f"混合搜索失败: {str(e)}"
                    }
                }
            }
    
    def _format_answer(self, search_response: Dict[str, Any], question: str) -> str:
        """
        格式化检索结果为答案
        
        Args:
            search_response: 搜索响应（包含results和metadata）
            question: 原始问题
            
        Returns:
            格式化的答案
        """
        results = search_response.get("results", [])
        metadata = search_response.get("metadata", {})
        query_info = search_response.get("query", {})
        
        if not results:
            return f"抱歉，没有找到关于'{question}'的相关信息。"
        
        # 构建答案
        answer_parts = [f"关于'{question}'的攻略信息：\n"]
        
        # 如果查询被翻译，显示翻译信息
        if query_info.get("translation_applied", False):
            translation_info = metadata.get("translation_info", {})
            translated_query = translation_info.get("translated_query", "")
            if translated_query:
                answer_parts.append(f"查询翻译: '{question}' -> '{translated_query}'")
        
        # 如果查询被重写，显示相关信息
        if query_info.get("rewrite_applied", False):
            rewrite_info = metadata.get("rewrite_info", {})
            answer_parts.append(f"意图分析: {rewrite_info.get('intent', 'unknown')}")
            answer_parts.append(f"查询优化: {rewrite_info.get('reasoning', '未知')}")
        
        # 如果有翻译或重写信息，添加空行
        if query_info.get("translation_applied", False) or query_info.get("rewrite_applied", False):
            answer_parts.append("")
        
        for result in results:
            chunk = result["chunk"]
            score = result["score"]
            
            # 提取关键信息
            topic = chunk.get("topic", "未知主题")
            summary = chunk.get("summary", "")
            
            answer_parts.append(f"\n【{topic}】")
            
            # 显示分数信息（区分混合搜索和单一搜索）
            if "fusion_method" in result:
                # 混合搜索结果
                fusion_method = result.get("fusion_method", "unknown")
                vector_score = result.get("vector_score", 0)
                bm25_score = result.get("bm25_score", 0)
                answer_parts.append(f"相关度: {score:.3f}")
                if vector_score > 0 and bm25_score > 0:
                    answer_parts.append(f"(语义匹配: {vector_score:.3f} | 关键词匹配: {bm25_score:.3f})")
            else:
                # 单一搜索结果
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
    
    async def _format_answer_with_summary(self, search_response: Dict[str, Any], question: str) -> str:
        """
        使用Gemini摘要器格式化检索结果
        
        Args:
            search_response: 搜索响应（包含results和metadata）
            question: 原始问题
            
        Returns:
            摘要后的答案
        """
        results = search_response.get("results", [])
        
        if not results:
            return "😔 抱歉，我没有找到相关的游戏攻略信息。可以试试换个关键词问我哦！"
        
        try:
            # 准备知识块数据
            chunks = []
            for result in results:
                chunk_data = result["chunk"]
                chunks.append({
                    "topic": chunk_data.get("topic", "未知主题"),
                    "summary": chunk_data.get("summary", ""),
                    "keywords": chunk_data.get("keywords", []),
                    "score": result.get("score", 0),
                    "content": chunk_data.get("summary", "")
                })
            
            # 获取游戏上下文
            game_context = None
            if hasattr(self, 'config') and self.config:
                game_context = self.config.get("game_name", None)
            
            # 调用摘要器生成对话式回复
            summary_result = self.summarizer.summarize_chunks(
                chunks=chunks,
                query=question,
                context=game_context
            )
            
            # 直接返回摘要内容（对话式格式）
            return summary_result["summary"]
            
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")
            # 回退到友好的错误消息
            return "😅 抱歉，我在整理信息时遇到了一点问题。让我用简单的方式回答你：\n\n" + self._format_simple_answer(results)
    
    def _format_simple_answer(self, results: List[Dict[str, Any]]) -> str:
        """简单格式化答案（用于摘要失败时的降级）"""
        if not results:
            return "没有找到相关信息。"
        
        # 只取最相关的结果
        top_result = results[0]
        chunk = top_result.get("chunk", top_result)
        
        topic = chunk.get("topic", "")
        summary = chunk.get("summary", "")
        
        return f"根据{topic}：\n{summary}"
    
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
            
            # 执行检索
            if self.vector_store and self.config:
                # 选择搜索方式
                if self.enable_hybrid_search and self.hybrid_retriever:
                    search_response = self._search_hybrid(question, top_k)
                    results = search_response.get("results", [])
                    
                    # 应用意图感知重排序
                    if self.enable_intent_reranking and self.reranker and results:
                        logger.info("应用意图感知重排序")
                        results = self.reranker.rerank_results(
                            results, 
                            question,
                            intent_weight=self.reranking_config.get("intent_weight", 0.4),
                            semantic_weight=self.reranking_config.get("semantic_weight", 0.6)
                        )
                        search_response["results"] = results
                        # 在元数据中记录重排序信息
                        search_response.setdefault("metadata", {})["reranking_applied"] = True
                    
                    # 格式化答案（使用摘要或原始格式）
                    if self.enable_summarization and self.summarizer and len(results) > 1:
                        answer = await self._format_answer_with_summary(search_response, question)
                    else:
                        answer = self._format_answer(search_response, question)
                    
                    confidence = max([r["score"] for r in results]) if results else 0.0
                    sources = [r["chunk"].get("topic", "未知") for r in results]
                    
                    # 添加搜索元数据
                    search_metadata = search_response.get("metadata", {})
                    
                else:
                    # 单一搜索
                    if self.config["vector_store_type"] == "faiss":
                        results = self._search_faiss(question, top_k)
                    else:
                        results = self._search_qdrant(question, top_k)
                    
                    # 应用意图感知重排序
                    if self.enable_intent_reranking and self.reranker and results:
                        logger.info("应用意图感知重排序（单一搜索模式）")
                        results = self.reranker.rerank_results(
                            results, 
                            question,
                            intent_weight=self.reranking_config.get("intent_weight", 0.4),
                            semantic_weight=self.reranking_config.get("semantic_weight", 0.6)
                        )
                    
                    # 构建兼容的search_response格式
                    search_response = {
                        "results": results,
                        "query": {"original": question, "rewritten": question, "rewrite_applied": False},
                        "metadata": {
                            "total_results": len(results),
                            "search_type": "vector_only",
                            "fusion_method": "none",
                            "rewrite_info": {
                                "intent": "unknown",
                                "confidence": 0.0,
                                "reasoning": "未使用查询重写"
                            },
                            "reranking_applied": self.enable_intent_reranking and self.reranker is not None
                        }
                    }
                    
                    # 格式化答案（使用摘要或原始格式）
                    if self.enable_summarization and self.summarizer and len(results) > 1:
                        answer = await self._format_answer_with_summary(search_response, question)
                    else:
                        answer = self._format_answer(search_response, question)
                    
                    confidence = max([r["score"] for r in results]) if results else 0.0
                    sources = [r["chunk"].get("topic", "未知") for r in results]
                    search_metadata = search_response.get("metadata", {})
                
            else:
                # 检查是否是因为向量库不存在
                if hasattr(self, 'vector_store_path') and self.vector_store_path is None:
                    # 没有找到对应的向量库
                    return {
                        "answer": "抱歉，暂时没有找到该游戏的攻略数据库。\n\n目前支持攻略查询的游戏：\n• 地狱潜兵2 - 可以询问武器配装、敌人攻略等\n• 艾尔登法环 - 可以询问Boss攻略、装备推荐等\n• 饥荒联机版 - 可以询问生存技巧、角色攻略等\n• 文明6 - 可以询问文明特色、胜利策略等\n• 七日杀 - 可以询问建筑、武器制作等",
                        "sources": [],
                        "confidence": 0.0,
                        "query_time": 0.0,
                        "results_count": 0,
                        "error": "VECTOR_STORE_NOT_FOUND"
                    }
                else:
                    # 其他情况，回退到模拟模式
                    await asyncio.sleep(0.5)
                    answer = self._get_mock_answer(question)
                    confidence = 0.8
                    sources = ["模拟知识库"]
                    search_metadata = {"search_type": "mock"}
            
            query_time = asyncio.get_event_loop().time() - start_time
            
            response = {
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
                "query_time": query_time,
                "results_count": len(results) if 'results' in locals() else 0
            }
            
            # 添加搜索元数据
            if 'search_metadata' in locals():
                response["search_metadata"] = search_metadata
            
            return response
            
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

def get_enhanced_rag_query(vector_store_path: Optional[str] = None,
                          llm_config: Optional[LLMConfig] = None) -> EnhancedRagQuery:
    """获取增强RAG查询器的单例实例"""
    global _enhanced_rag_query
    if _enhanced_rag_query is None:
        _enhanced_rag_query = EnhancedRagQuery(
            vector_store_path=vector_store_path,
            llm_config=llm_config
        )
    return _enhanced_rag_query

async def query_enhanced_rag(question: str, 
                           game_name: Optional[str] = None,
                           top_k: int = 3,
                           enable_hybrid_search: bool = True,
                           hybrid_config: Optional[Dict] = None,
                           llm_config: Optional[LLMConfig] = None,
                           enable_summarization: bool = False,
                           summarization_config: Optional[Dict] = None,
                           enable_intent_reranking: bool = None,
                           reranking_config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    执行增强RAG查询的便捷函数
    
    Args:
        question: 用户问题
        game_name: 游戏名称（可选）
        top_k: 检索结果数量
        enable_hybrid_search: 是否启用混合搜索
        hybrid_config: 混合搜索配置
        llm_config: LLM配置
        enable_summarization: 是否启用Gemini摘要
        summarization_config: 摘要配置
        enable_intent_reranking: 是否启用意图感知重排序
        reranking_config: 重排序配置
        
    Returns:
        查询结果字典
    """
    # 从配置文件加载设置
    import os
    from pathlib import Path
    config_path = Path(__file__).parent.parent / "assets" / "settings.json"
    if config_path.exists():
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            
            # 加载混合搜索设置
            if hybrid_config is None:
                hybrid_search_settings = settings.get("hybrid_search", {})
                enable_hybrid_search = hybrid_search_settings.get("enabled", True)
                hybrid_config = {
                    "fusion_method": hybrid_search_settings.get("fusion_method", "rrf"),
                    "vector_weight": hybrid_search_settings.get("vector_weight", 0.3),
                    "bm25_weight": hybrid_search_settings.get("bm25_weight", 0.7),
                    "rrf_k": hybrid_search_settings.get("rrf_k", 60)
                }
            
            # 加载摘要设置
            if summarization_config is None:
                summarization_settings = settings.get("summarization", {})
                enable_summarization = summarization_settings.get("enabled", False)
                summarization_config = {
                    "api_key": summarization_settings.get("api_key") or os.environ.get("GEMINI_API_KEY"),
                    "model_name": summarization_settings.get("model_name", "gemini-2.5-flash-lite-preview-06-17"),
                    "max_summary_length": summarization_settings.get("max_summary_length", 300),
                    "temperature": summarization_settings.get("temperature", 0.3),
                    "include_sources": summarization_settings.get("include_sources", True),
                    "language": summarization_settings.get("language", "auto")
                }
            
            # 加载重排序设置
            if enable_intent_reranking is None:
                reranking_settings = settings.get("intent_reranking", {})
                enable_intent_reranking = reranking_settings.get("enabled", True)
            
            if reranking_config is None:
                reranking_settings = settings.get("intent_reranking", {})
                reranking_config = {
                    "intent_weight": reranking_settings.get("intent_weight", 0.4),
                    "semantic_weight": reranking_settings.get("semantic_weight", 0.6)
                }
    
    rag_query = EnhancedRagQuery(
        enable_hybrid_search=enable_hybrid_search,
        hybrid_config=hybrid_config,
        llm_config=llm_config,
        enable_summarization=enable_summarization,
        summarization_config=summarization_config,
        enable_intent_reranking=enable_intent_reranking,
        reranking_config=reranking_config
    )
    
    await rag_query.initialize(game_name)
    return await rag_query.query(question, top_k)


class SimpleRagQuery(EnhancedRagQuery):
    """简化的RAG查询器，保持向后兼容"""
    pass

def get_rag_query() -> SimpleRagQuery:
    """获取简化RAG查询器的单例实例（向后兼容）"""
    return SimpleRagQuery()

async def query_rag(question: str, game_name: Optional[str] = None) -> Dict[str, Any]:
    """执行简化RAG查询的便捷函数（向后兼容）"""
    return await query_enhanced_rag(question, game_name) 