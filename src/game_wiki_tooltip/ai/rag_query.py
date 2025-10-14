"""
增强的RAG查询接口 - 集成批量嵌入和向量存储检索
============================================

功能特性:
1. 加载预构建的向量存储
2. 执行语义检索
3. 支持LLM查询重写
4. 混合搜索（向量 + BM25）
5. 返回相关游戏策略信息
"""

import logging
import asyncio
import json
import numpy as np
from typing import Optional, Dict, Any, List, AsyncGenerator
from pathlib import Path
import time
import sys
import os

class VectorStoreUnavailableError(Exception):
    """向量存储不可用错误"""
    pass

def get_resource_path(relative_path: str) -> Path:
    """
    获取资源文件的绝对路径，兼容开发和PyInstaller打包环境
    
    Args:
        relative_path: 相对于项目根目录的路径
        
    Returns:
        资源文件的绝对路径
    """
    try:
        # PyInstaller打包环境
        base_path = Path(sys._MEIPASS)
        # 在PyInstaller环境中，资源文件打包在src/game_wiki_tooltip/路径下
        resource_path = base_path / "src" / "game_wiki_tooltip" / relative_path
        print(f"🔧 [RAG-DEBUG] 使用PyInstaller环境: {base_path}")
        print(f"🔧 [RAG-DEBUG] 构建资源路径: {resource_path}")
    except AttributeError:
        # 开发环境：从当前文件位置查找项目根目录
        current_file = Path(__file__).parent  # .../ai/
        project_root = current_file.parent.parent.parent  # 向上到项目根目录
        resource_path = project_root / "src" / "game_wiki_tooltip" / relative_path
        print(f"🔧 [RAG-DEBUG] 使用开发环境")
        print(f"🔧 [RAG-DEBUG] 项目根目录: {project_root}")
        print(f"🔧 [RAG-DEBUG] 构建资源路径: {resource_path}")
    
    return resource_path

# 导入批量嵌入处理器
try:
    from .batch_embedding import BatchEmbeddingProcessor
    BATCH_EMBEDDING_AVAILABLE = True
except ImportError:
    BATCH_EMBEDDING_AVAILABLE = False
    logging.warning("批量嵌入模块不可用")

# 向量存储支持 - 延迟导入以避免启动崩溃
FAISS_AVAILABLE = None

def _check_faiss_available():
    """检查并延迟导入faiss"""
    global FAISS_AVAILABLE
    if FAISS_AVAILABLE is None:
        try:
            import faiss
            FAISS_AVAILABLE = True
        except ImportError:
            FAISS_AVAILABLE = False
            logging.warning("FAISS不可用")
    return FAISS_AVAILABLE

try:
    import qdrant_client
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logging.warning("Qdrant不可用")

# 导入Gemini摘要器
try:
    from .gemini_summarizer import create_gemini_summarizer, GeminiSummarizer
    from .rag_config import SummarizationConfig
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

# 导入混合检索器和BM25错误类
try:
    from .hybrid_retriever import HybridSearchRetriever, VectorRetrieverAdapter
    from .enhanced_bm25_indexer import BM25UnavailableError
    HYBRID_RETRIEVER_AVAILABLE = True
except ImportError as e:
    HybridSearchRetriever = None
    VectorRetrieverAdapter = None
    BM25UnavailableError = Exception  # 回退到基础异常类
    HYBRID_RETRIEVER_AVAILABLE = False
    logging.warning(f"混合检索器模块不可用: {e}")

# 导入配置和查询重写
from .rag_config import LLMSettings
from .rag_config import RAGConfig, get_default_config

logger = logging.getLogger(__name__)

# 向量存储映射配置的全局缓存
_vector_mappings_cache = None
_vector_mappings_last_modified = None

def load_vector_mappings() -> Dict[str, str]:
    """
    加载向量存储映射配置
    
    Returns:
        从窗口标题到向量存储名称的映射字典
    """
    global _vector_mappings_cache, _vector_mappings_last_modified
    
    try:
        # 使用get_resource_path正确处理打包环境
        mapping_file = get_resource_path("assets/vector_mappings.json")
        
        # 检查文件是否存在
        if not mapping_file.exists():
            logger.warning(f"向量存储映射配置文件不存在: {mapping_file}")
            return {}  # 返回空字典而不是None
        
        # 检查文件修改时间，实现缓存机制
        current_modified = mapping_file.stat().st_mtime
        if (_vector_mappings_cache is not None and 
            _vector_mappings_last_modified == current_modified):
            return _vector_mappings_cache
        
        # 读取配置文件
        with open(mapping_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 构建映射字典
        mappings = {}
        for mapping in config.get("mappings", []):
            vector_db_name = mapping.get("vector_db_name")
            window_titles = mapping.get("window_titles", [])
            
            for title in window_titles:
                mappings[title.lower()] = vector_db_name
        
        # 更新缓存
        _vector_mappings_cache = mappings
        _vector_mappings_last_modified = current_modified
        
        logger.info(f"成功加载向量存储映射配置，包含{len(mappings)}个映射")
        return mappings
    except Exception as e:
        logger.error(f"加载向量存储映射配置失败: {e}")
        return {}  # 返回空字典而不是None

def map_window_title_to_game_name(window_title: str) -> Optional[str]:
    """
    将窗口标题映射到向量存储文件名
    
    Args:
        window_title: 窗口标题
        
    Returns:
        对应的向量存储文件名（不含.json扩展名），如果未找到则返回None
    """
    # 转换为小写进行匹配
    title_lower = window_title.lower()
    
    # 加载向量存储映射配置
    title_to_vectordb_mapping = load_vector_mappings()
    
    # 额外的安全检查 - 虽然load_vector_mappings()现在应该永远不会返回None
    if not title_to_vectordb_mapping:
        logger.warning(f"向量映射配置为空或无效")
        return None
    
    # 尝试精确匹配
    for title_key, vectordb_name in title_to_vectordb_mapping.items():
        if title_key in title_lower:
            logger.info(f"窗口标题'{window_title}'映射到向量存储'{vectordb_name}'")
            return vectordb_name
    
    # 如果未找到映射，记录警告并返回None
    logger.warning(f"未找到窗口标题'{window_title}'的映射")
    return None

class EnhancedRagQuery:
    """增强的RAG查询接口，支持向量存储检索和LLM查询重写"""
    
    def __init__(self, vector_store_path: Optional[str] = None,
                 enable_hybrid_search: bool = True,
                 hybrid_config: Optional[Dict] = None,
                 llm_config: Optional[LLMSettings] = None,
                 google_api_key: Optional[str] = None,
                 enable_query_rewrite: bool = True,
                 enable_summarization: bool = True,
                 summarization_config: Optional[Dict] = None,
                 enable_intent_reranking: bool = True,
                 reranking_config: Optional[Dict] = None,
                 rag_config: Optional[RAGConfig] = None):
        """
        初始化RAG查询
        
        Args:
            vector_store_path: 向量存储路径，如果为None则使用默认路径
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
            "vector_weight": 0.5,
            "bm25_weight": 0.5,
            "rrf_k": 60
        }
        # 如果提供了RAGConfig则使用，否则从单独参数创建
        if rag_config:
            self.rag_config = rag_config
            # 从RAGConfig覆盖单独设置
            self.llm_config = rag_config.llm_settings
            self.enable_hybrid_search = rag_config.hybrid_search.enabled
            self.hybrid_config = rag_config.hybrid_search.to_dict()
            self.enable_summarization = rag_config.summarization.enabled
            self.summarization_config = rag_config.summarization
            self.enable_intent_reranking = rag_config.intent_reranking.enabled
            self.reranking_config = rag_config.intent_reranking.to_dict()
            self.enable_query_rewrite = rag_config.query_processing.enable_query_rewrite
        else:
            # 使用单独参数以保持向后兼容性
            self.rag_config = None
            self.llm_config = llm_config
        
        self.google_api_key = google_api_key or (self.llm_config.get_api_key() if self.llm_config else None)
        self.enable_query_rewrite = enable_query_rewrite
        self.hybrid_retriever = None
        
        # 摘要配置
        self.enable_summarization = enable_summarization and GEMINI_AVAILABLE
        self.summarization_config = summarization_config or SummarizationConfig()
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
            game_name: 游戏名称，用于自动查找向量存储
        """
        try:
            print(f"🔧 [RAG-DEBUG] 开始初始化RAG系统 - 游戏: {game_name}")
            logger.info("正在初始化增强RAG系统...")
            
            if not BATCH_EMBEDDING_AVAILABLE:
                if not self.google_api_key:
                    logger.warning(
                        "批量嵌入不可用且未配置API密钥，尝试离线加载向量索引"
                    )
                else:
                    error_msg = (
                        "Vector search feature unavailable: batch embedding module import failed. "
                        "Please check if the following dependencies are correctly installed:\n"
                        "1. numpy\n2. faiss-cpu\n3. other embedding related dependencies"
                    )
                    print(f"❌ [RAG-DEBUG] {error_msg}")
                    logger.error(error_msg)
                    raise VectorStoreUnavailableError(error_msg)
            
            # 确定向量存储路径
            if self.vector_store_path is None and game_name:
                # 自动查找向量存储 - 使用资源路径函数
                vector_dir = get_resource_path("ai/vectorstore")
                
                print(f"🔍 [RAG-DEBUG] 查找向量存储目录: {vector_dir}")
                logger.info(f"查找向量存储目录: {vector_dir}")
                config_files = list(vector_dir.glob(f"{game_name}_vectors_config.json"))
                
                if config_files:
                    self.vector_store_path = str(config_files[0])
                    print(f"✅ [RAG-DEBUG] 找到向量存储配置: {self.vector_store_path}")
                    logger.info(f"找到向量存储配置: {self.vector_store_path}")
                else:
                    error_msg = f"未找到向量存储: 未找到游戏'{game_name}'的向量存储配置文件\n搜索路径: {vector_dir}\n搜索模式: {game_name}_vectors_config.json"
                    
                    # 列出现有文件用于调试
                    try:
                        existing_files = list(vector_dir.glob("*_vectors_config.json"))
                        if existing_files:
                            available_games = [f.stem.replace("_vectors_config", "") for f in existing_files]
                            error_msg += f"\n可用的向量存储: {', '.join(available_games)}"
                        else:
                            error_msg += "\n未找到向量存储配置文件"
                    except Exception as e:
                        error_msg += f"\n列出现有文件失败: {e}"
                    
                    print(f"❌ [RAG-DEBUG] {error_msg}")
                    logger.error(error_msg)
                    raise VectorStoreUnavailableError(error_msg)
            
            if not self.vector_store_path or not Path(self.vector_store_path).exists():
                error_msg = f"向量存储配置文件未找到: {self.vector_store_path}"
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            # 加载向量存储
            try:
                if self.google_api_key:
                    self.processor = BatchEmbeddingProcessor(api_key=self.google_api_key)
                    self.vector_store = self.processor.load_vector_store(self.vector_store_path)
                else:
                    logger.info("以离线模式加载向量存储（未提供API密钥）")
                    self.processor = None
                    self.vector_store = {"metadata": None, "index_path": None}

                # 加载配置和元数据
                with open(self.vector_store_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                if isinstance(self.vector_store, dict):
                    self.vector_store["index_path"] = self.config.get("index_path")

                if self.config["vector_store_type"] == "faiss":
                    if isinstance(self.vector_store, dict):
                        self.metadata = self.vector_store.get("metadata")
                        if not self.metadata:
                            index_dir = Path(self.vector_store_path).parent / Path(self.config["index_path"]).name
                            metadata_path = index_dir / "metadata.json"
                            if metadata_path.exists():
                                with open(metadata_path, 'r', encoding='utf-8') as meta_file:
                                    self.metadata = json.load(meta_file)
                                self.vector_store["metadata"] = self.metadata
                    else:
                        self.metadata = self.vector_store["metadata"]
                
                logger.info(f"Vector store loaded: {self.config['chunk_count']} chunks")
                
                # 存储来自初始参数的游戏名称
                self.game_name = game_name
                
                # 初始化混合检索器
                if self.enable_hybrid_search:
                    self._initialize_hybrid_retriever()
                    
            except Exception as e:
                error_msg = f"Failed to load vector store: {e}"
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            self.is_initialized = True
            logger.info("Enhanced RAG system initialized")
            
        except VectorStoreUnavailableError:
            # 重新抛出向量存储特定错误
            self.is_initialized = False
            raise
        except Exception as e:
            error_msg = f"RAG system initialization failed: {e}"
            logger.error(error_msg)
            self.is_initialized = False
            raise VectorStoreUnavailableError(error_msg)
    
    def _initialize_hybrid_retriever(self):
        """
        Initialize hybrid retriever
        
        Raises:
            VectorStoreUnavailableError: When hybrid search initialization fails
        """
        if not self.enable_hybrid_search:
            logger.warning("Hybrid search is not enabled, only vector search will be used")
            return
        
        if not HYBRID_RETRIEVER_AVAILABLE:
            error_msg = "Hybrid search initialization failed: hybrid retriever module is not available"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
        
        try:
            # 检查BM25索引文件是否存在 - 修复路径解析问题
            from pathlib import Path
            bm25_index_path = self.config.get("bm25_index_path")
            if not bm25_index_path:
                error_msg = "Hybrid search initialization failed: BM25 index path not found in configuration"
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            # 如果是相对路径，基于资源路径构建绝对路径
            bm25_path = Path(bm25_index_path)
            if not bm25_path.is_absolute():
                # 使用资源路径函数构建路径
                vectorstore_dir = get_resource_path("ai/vectorstore")
                # 尝试基于向量存储目录构建路径
                bm25_path = vectorstore_dir / bm25_index_path
            
            # 创建向量检索器适配器
            vector_retriever = VectorRetrieverAdapter(self)
            
            # 创建混合检索器 - 从配置中读取统一处理设置
            enable_unified_processing = self.hybrid_config.get("enable_unified_processing", True)
            enable_query_rewrite = self.hybrid_config.get("enable_query_rewrite", self.enable_query_rewrite)
            
            self.hybrid_retriever = HybridSearchRetriever(
                vector_retriever=vector_retriever,
                bm25_index_path=str(bm25_path),
                fusion_method=self.hybrid_config.get("fusion_method", "rrf"),
                vector_weight=self.hybrid_config.get("vector_weight", 0.5),
                bm25_weight=self.hybrid_config.get("bm25_weight", 0.5),
                rrf_k=self.hybrid_config.get("rrf_k", 60),
                llm_config=self.llm_config,
                enable_unified_processing=enable_unified_processing,  # 从配置中读取
                enable_query_rewrite=enable_query_rewrite
            )
            
            if enable_unified_processing:
                logger.info("Hybrid retriever initialized successfully (unified processing mode)")
            else:
                logger.info("Hybrid retriever initialized successfully (independent processing mode, unified processing disabled)")
            
        except BM25UnavailableError as e:
            # BM25特定错误，重新包装为向量存储错误
            error_msg = f"Hybrid search initialization failed: {e}"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
        except (FileNotFoundError, RuntimeError) as e:
            # 文件未找到或其他运行时错误
            error_msg = f"Hybrid search initialization failed: {e}"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
        except Exception as e:
            error_msg = f"Hybrid retriever initialization failed: {e}"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
    
    def _initialize_summarizer(self):
        """初始化Gemini摘要器"""
        try:
            import os
            
            # 从集中配置获取API密钥
            api_key = self.google_api_key
            
            if not api_key:
                logger.warning("Gemini API key not found, summary feature will be disabled")
                self.enable_summarization = False
                return
            
            # Use RAGConfig if available, otherwise use individual config
            if self.rag_config:
                # Use RAGConfig to get language settings from LLM config
                self.summarizer = GeminiSummarizer(rag_config=self.rag_config)
            else:
                # Use the config object directly or create from dict for backward compatibility
                if isinstance(self.summarization_config, SummarizationConfig):
                    # Direct config object from RAGConfig
                    config = self.summarization_config
                    config.api_key = api_key  # Override with actual API key
                else:
                    # Legacy dict format
                    config = SummarizationConfig(
                        api_key=api_key,
                        model_name=self.summarization_config.get("model_name"),
                        temperature=self.summarization_config.get("temperature"),
                        include_sources=self.summarization_config.get("include_sources"),
                        language=self.summarization_config.get("language"),
                        enable_google_search=self.summarization_config.get("enable_google_search"),
                        thinking_budget=self.summarization_config.get("thinking_budget")
                    )
                
                # Create summarizer using the config
                self.summarizer = GeminiSummarizer(config=config)
            
            # Log successful initialization
            if self.rag_config:
                logger.info(f"Gemini summarizer initialized successfully: {self.rag_config.summarization.model_name}")
            else:
                logger.info(f"Gemini summarizer initialized successfully: {config.model_name}")
            
        except Exception as e:
            logger.error(f"Gemini summarizer initialization failed: {e}")
            self.enable_summarization = False
    
    def _initialize_reranker(self):
        """初始化意图感知重排序器"""
        try:
            self.reranker = IntentAwareReranker()
            logger.info("Intent-aware reranker initialized successfully")
        except Exception as e:
            logger.error(f"Intent-aware reranker initialization failed: {e}")
            self.enable_intent_reranking = False
    
    def _search_faiss(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Use FAISS for vector search
        
        Args:
            query: Query text
            top_k: Number of results to return
            
        Returns:
            List of search results
        """
        print(f"🔍 [VECTOR-DEBUG] Starting FAISS vector search: query='{query}', top_k={top_k}")
        
        if not self.vector_store or not self.metadata:
            print(f"⚠️ [VECTOR-DEBUG] Vector store or metadata not initialized")
            logger.warning("Vector store or metadata not initialized")
            return []
        if not self.processor:
            print("⚠️ [VECTOR-DEBUG] Embedding processor not initialized, skip FAISS search")
            logger.warning("Embedding processor not initialized, skip FAISS search")
            return []
        
        try:
            # Get query vector - use query directly without duplication
            query_text = query
            print(f"📄 [VECTOR-DEBUG] Query text for embedding: '{query_text[:100]}...'")
            
            # Use Gemini embeddings with QUESTION_ANSWERING task type for queries
            try:
                if hasattr(self.processor, 'embedding_client'):
                    query_vectors = [self.processor.embedding_client.embed_query(query_text)]
                else:
                    query_vectors = self.processor.embed_batch([query_text])
                query_vector = np.array(query_vectors[0], dtype=np.float32).reshape(1, -1)
            except RuntimeError as e:
                if "EMBEDDING_OVERLOAD" in str(e):
                    # Return a special result to notify user about overload
                    logger.warning(f"Embedding service overloaded: {e}")
                    return [{
                        "chunk": {
                            "topic": "System Notice",
                            "summary": "⚠️ The AI service is currently busy. This happens when you hit a free-tier limit per minute or per day. Please try again in one minute. If this continues to happen, try again tomorrow.",
                            "keywords": [],
                            "chunk_id": "system_overload_notice"
                        },
                        "score": 0.0,
                        "error": "model_overload"
                    }]
                raise
            print(f"🔢 [VECTOR-DEBUG] Query vector dimension: {query_vector.shape}, first 5 values: {query_vector[0][:5]}")
            
            # Build correct index file path
            # Use the same path logic as BatchEmbeddingProcessor._load_faiss_store
            index_path_str = self.config["index_path"]
            if not Path(index_path_str).is_absolute():
                # Use resource path function to build absolute path
                vectorstore_dir = get_resource_path("ai/vectorstore")
                index_path = vectorstore_dir / Path(index_path_str).name
            else:
                index_path = Path(index_path_str)
            
            index_file_path = index_path / "index.faiss"
            print(f"📂 [VECTOR-DEBUG] FAISS index file path: {index_file_path}")
            logger.info(f"Attempting to load FAISS index file: {index_file_path}")
            
            if not index_file_path.exists():
                print(f"❌ [VECTOR-DEBUG] FAISS index file does not exist: {index_file_path}")
                logger.error(f"FAISS index file does not exist: {index_file_path}")
                return []
            
            # Load FAISS index
            try:
                import faiss
            except ImportError:
                logger.error("Failed to import faiss library")
                print(f"❌ [VECTOR-DEBUG] Failed to import faiss library, please ensure faiss-cpu is installed")
                return []
            
            index = faiss.read_index(str(index_file_path))
            print(f"📊 [VECTOR-DEBUG] FAISS index information: total vectors={index.ntotal}, dimension={index.d}")
            
            # Execute search
            scores, indices = index.search(query_vector, top_k)
            print(f"🔍 [VECTOR-DEBUG] FAISS search raw results:")
            print(f"   - Retrieved indices: {indices[0]}")
            print(f"   - Similarity scores: {scores[0]}")
            
            # Return results
            results = []
            for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                if idx < len(self.metadata):
                    chunk = self.metadata[idx]
                    chunk_info = {
                        "chunk": chunk,
                        "score": float(score),
                        "rank": i + 1
                    }
                    results.append(chunk_info)
                    
                    # Detailed result debugging information
                    print(f"   📋 [VECTOR-DEBUG] Result {i+1}:")
                    print(f"      - Similarity score: {score:.4f}")
                    print(f"      - Index ID: {idx}")
                    print(f"      - Topic: {chunk.get('topic', 'Unknown')}")
                    print(f"      - Summary: {chunk.get('summary', '')[:100]}...")
                    print(f"      - Keywords: {chunk.get('keywords', [])}")
                    
                    # If it's structured data, display enemy information
                    if "structured_data" in chunk:
                        structured = chunk["structured_data"]
                        if "enemy_name" in structured:
                            print(f"      - Enemy name: {structured['enemy_name']}")
                        if "weak_points" in structured:
                            weak_points = [wp.get("name", "Unknown") for wp in structured["weak_points"]]
                            print(f"      - Weak points: {weak_points}")
            
            print(f"✅ [VECTOR-DEBUG] FAISS search completed, found {len(results)} results")
            logger.info(f"FAISS search completed, found {len(results)} results")
            return results
            
        except Exception as e:
            print(f"❌ [VECTOR-DEBUG] FAISS search failed: {e}")
            logger.error(f"FAISS search failed: {e}")
            return []
    
    def _search_qdrant(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Use Qdrant for vector search
        
        Args:
            query: Query text
            top_k: Number of results to return
            
        Returns:
            List of search results
        """
        print(f"🔍 [VECTOR-DEBUG] Starting Qdrant vector search: query='{query}', top_k={top_k}")
        
        if not self.vector_store or not QDRANT_AVAILABLE:
            print(f"⚠️ [VECTOR-DEBUG] Qdrant vector store not initialized or not available")
            logger.warning("Qdrant vector store not initialized or not available")
            return []
        if not self.processor:
            print("⚠️ [VECTOR-DEBUG] Embedding processor not initialized, skip Qdrant search")
            logger.warning("Embedding processor not initialized, skip Qdrant search")
            return []
        
        try:
            # Get query vector - use query directly without duplication
            query_text = query
            print(f"📄 [VECTOR-DEBUG] Query text for embedding: '{query_text[:100]}...'")
            
            # Use Gemini embeddings with QUESTION_ANSWERING task type for queries
            if hasattr(self.processor, 'embedding_client'):
                query_vectors = [self.processor.embedding_client.embed_query(query_text)]
            else:
                query_vectors = self.processor.embed_batch([query_text])
            query_vector = query_vectors[0]
            print(f"🔢 [VECTOR-DEBUG] Query vector dimension: {len(query_vector)}, first 5 values: {query_vector[:5]}")
            
            # Execute search
            print(f"🔍 [VECTOR-DEBUG] Calling Qdrant search: collection={self.config['collection_name']}")
            results = self.vector_store.search(
                collection_name=self.config["collection_name"],
                query_vector=query_vector,
                limit=top_k
            )
            
            print(f"📊 [VECTOR-DEBUG] Qdrant search raw results count: {len(results)}")
            
            # Format results
            formatted_results = []
            for i, result in enumerate(results):
                chunk_info = {
                    "chunk": result.payload,
                    "score": result.score,
                    "rank": i + 1
                }
                formatted_results.append(chunk_info)
                
                # Detailed result debugging information
                print(f"   📋 [VECTOR-DEBUG] Result {i+1}:")
                print(f"      - Similarity score: {result.score:.4f}")
                print(f"      - Topic: {result.payload.get('topic', 'Unknown')}")
                print(f"      - Summary: {result.payload.get('summary', '')[:100]}...")
                print(f"      - Keywords: {result.payload.get('keywords', [])}")
                
                # If it's structured data, display enemy information
                if "structured_data" in result.payload:
                    structured = result.payload["structured_data"]
                    if "enemy_name" in structured:
                        print(f"      - Enemy name: {structured['enemy_name']}")
                    if "weak_points" in structured:
                        weak_points = [wp.get("name", "Unknown") for wp in structured["weak_points"]]
                        print(f"      - Weak points: {weak_points}")
            
            print(f"✅ [VECTOR-DEBUG] Qdrant search completed, found {len(formatted_results)} results")
            logger.info(f"Qdrant search completed, found {len(formatted_results)} results")
            return formatted_results
            
        except Exception as e:
            print(f"❌ [VECTOR-DEBUG] Qdrant search failed: {e}")
            logger.error(f"Qdrant search failed: {e}")
            return []

    def _search_hybrid_with_processed_query(self, unified_query_result, top_k: int = 3) -> Dict[str, Any]:
        """
        Use preprocessed unified query results for hybrid search
        
        Args:
            unified_query_result: Unified query processing result object
            top_k: Number of results to return
            
        Returns:
            Hybrid search results (including metadata)
        """
        print(f"🔍 [RAG-DEBUG] Starting hybrid search (preprocessed mode): top_k={top_k}")
        
        if not self.hybrid_retriever:
            print(f"⚠️ [RAG-DEBUG] Hybrid retriever not initialized, falling back to vector search")
            logger.warning("Hybrid retriever not initialized, falling back to vector search")
            # Use rewritten query for vector search
            semantic_query = unified_query_result.rewritten_query
            results = self._search_faiss(semantic_query, top_k) if self.config["vector_store_type"] == "faiss" else self._search_qdrant(semantic_query, top_k)
            return {
                "results": results,
                "query": {
                    "original": unified_query_result.original_query,
                    "processed_query": semantic_query,
                    "bm25_optimized_query": unified_query_result.bm25_optimized_query,
                    "translation_applied": unified_query_result.translation_applied,
                    "rewrite_applied": unified_query_result.rewrite_applied,
                    "intent": unified_query_result.intent,
                    "confidence": unified_query_result.confidence
                },
                "metadata": {
                    "total_results": len(results),
                    "search_type": "vector_fallback", 
                    "fusion_method": "none",
                    "rewrite_info": {
                        "intent": unified_query_result.intent,
                        "confidence": unified_query_result.confidence,
                        "reasoning": unified_query_result.reasoning
                    }
                }
            }
        
        # Directly call hybrid retriever, disable internal unified processing (avoid duplicate processing)
        try:
            print(f"🚀 [RAG-DEBUG] Starting hybrid search (using preprocessed results)")
            print(f"   - Semantic query: '{unified_query_result.rewritten_query}'")
            print(f"   - BM25 query: '{unified_query_result.bm25_optimized_query}'")
            
            # Manually execute hybrid search process, using preprocessed query
            # Vector search uses rewritten query
            vector_search_count = 10
            bm25_search_count = 10
            
            print(f"🔍 [HYBRID-DEBUG] Starting vector search: query='{unified_query_result.rewritten_query}', top_k={vector_search_count}")
            vector_results = self.hybrid_retriever.vector_retriever.search(unified_query_result.rewritten_query, vector_search_count)
            print(f"📊 [HYBRID-DEBUG] Vector search results count: {len(vector_results)}")
            
            # BM25 search uses optimized query
            bm25_results = []
            if self.hybrid_retriever.bm25_indexer:
                print(f"🔍 [HYBRID-DEBUG] Starting BM25 search:")
                print(f"   - Original query: '{unified_query_result.original_query}'")
                print(f"   - Semantic query: '{unified_query_result.rewritten_query}'")
                print(f"   - BM25 optimized: '{unified_query_result.bm25_optimized_query}'")
                print(f"   - Search count: {bm25_search_count}")
                
                bm25_results = self.hybrid_retriever.bm25_indexer.search(unified_query_result.bm25_optimized_query, bm25_search_count)
                print(f"📊 [HYBRID-DEBUG] BM25 search results count: {len(bm25_results)}")
            else:
                print(f"⚠️ [HYBRID-DEBUG] BM25 indexer not initialized, skipping BM25 search")
            
            # Score fusion
            final_result_count = 5
            print(f"🔄 [HYBRID-DEBUG] Starting score fusion: method={self.hybrid_retriever.fusion_method}")
            
            final_results = self.hybrid_retriever._fuse_results(vector_results, bm25_results, final_result_count)
            
            print(f"✅ [HYBRID-DEBUG] Score fusion completed, final results count: {len(final_results)}")
            
            # Build return results
            return {
                "results": final_results,
                "query": {
                    "original": unified_query_result.original_query,
                    "processed_query": unified_query_result.rewritten_query,
                    "bm25_optimized_query": unified_query_result.bm25_optimized_query,
                    "translation_applied": unified_query_result.translation_applied,
                    "rewrite_applied": unified_query_result.rewrite_applied,
                    "intent": unified_query_result.intent,
                    "confidence": unified_query_result.confidence,
                    "detected_language": unified_query_result.detected_language,
                    "processing_method": "preprocessed",
                    "reasoning": unified_query_result.reasoning
                },
                "metadata": {
                    "fusion_method": self.hybrid_retriever.fusion_method,
                    "vector_results_count": len(vector_results),
                    "bm25_results_count": len(bm25_results),
                    "final_results_count": len(final_results),
                    "vector_search_count": vector_search_count,
                    "bm25_search_count": bm25_search_count,
                    "target_final_count": final_result_count,
                    "processing_stats": {
                        "preprocessed_mode": True,
                        "avoided_duplicate_processing": True
                    }
                }
            }
            
        except Exception as e:
            print(f"❌ [RAG-DEBUG] Hybrid search failed: {e}")
            logger.error(f"Hybrid search failed: {e}")
            # Fall back to vector search
            semantic_query = unified_query_result.rewritten_query
            results = self._search_faiss(semantic_query, top_k) if self.config["vector_store_type"] == "faiss" else self._search_qdrant(semantic_query, top_k)
            return {
                "results": results,
                "query": {
                    "original": unified_query_result.original_query,
                    "processed_query": semantic_query,
                    "bm25_optimized_query": unified_query_result.bm25_optimized_query,
                    "translation_applied": unified_query_result.translation_applied,
                    "rewrite_applied": unified_query_result.rewrite_applied
                },
                "metadata": {
                    "total_results": len(results),
                    "search_type": "vector_fallback",
                    "fusion_method": "none",
                    "rewrite_info": {
                        "intent": unified_query_result.intent,
                        "confidence": unified_query_result.confidence,
                        "reasoning": f"Hybrid search failed: {str(e)}"
                    }
                }
            }
    
    def _format_answer(self, search_response: Dict[str, Any], question: str) -> str:
        """
        Format search results as an answer
        
        Args:
            search_response: Search response (contains results and metadata)
            question: Original question
            
        Returns:
            Formatted answer
        """
        results = search_response.get("results", [])
        metadata = search_response.get("metadata", {})
        query_info = search_response.get("query", {})
        
        if not results:
            return f"Sorry, I couldn't find any information about '{question}'."
        
        # Build answer
        answer_parts = [f"About '{question}' information:\n"]
        
        # If query is translated, display translation information
        if query_info.get("translation_applied", False):
            translation_info = metadata.get("translation_info", {})
            translated_query = translation_info.get("translated_query", "")
            if translated_query:
                answer_parts.append(f"Translation: '{question}' -> '{translated_query}'")
        
        # If query is rewritten, display related information
        if query_info.get("rewrite_applied", False):
            rewrite_info = metadata.get("rewrite_info", {})
            answer_parts.append(f"Intent analysis: {rewrite_info.get('intent', 'unknown')}")
            answer_parts.append(f"Query optimization: {rewrite_info.get('reasoning', 'Unknown')}")
        
        # If there is translation or rewrite information, add an empty line
        if query_info.get("translation_applied", False) or query_info.get("rewrite_applied", False):
            answer_parts.append("")
        
        for result in results:
            chunk = result["chunk"]
            score = result["score"]
            
            # Extract key information
            topic = chunk.get("topic", "Unknown topic")
            summary = chunk.get("summary", "")
            
            answer_parts.append(f"\n【{topic}】")
            
            # Display score information (distinguish between hybrid search and single search)
            if "fusion_method" in result:
                # Hybrid search results
                fusion_method = result.get("fusion_method", "unknown")
                vector_score = result.get("vector_score", 0)
                bm25_score = result.get("bm25_score", 0)
                answer_parts.append(f"Relevance: {score:.3f}")
                if vector_score > 0 and bm25_score > 0:
                    answer_parts.append(f"(Semantic match: {vector_score:.3f} | Keyword match: {bm25_score:.3f})")
            else:
                # Single search results
                answer_parts.append(f"Relevance: {score:.3f}")
            
            answer_parts.append(f"{summary}")
            
            # If there is build information, add build suggestions
            if "build" in chunk:
                build = chunk["build"]
                if "name" in build:
                    answer_parts.append(f"\nRecommended build: {build['name']}")
                if "focus" in build:
                    answer_parts.append(f"Build focus: {build['focus']}")
                
                # Add key equipment information
                if "stratagems" in build:
                    stratagems = [s["name"] for s in build["stratagems"]]
                    answer_parts.append(f"Core equipment: {', '.join(stratagems[:3])}")
        
        return "\n".join(answer_parts)

    async def _format_answer_with_summary_stream(self, search_response: Dict[str, Any], question: str, original_query: str = None) -> AsyncGenerator[str, None]:
        """
        Use Gemini summarizer to format search results in streaming mode
        
        Args:
            search_response: Search response (contains results and metadata)
            question: Original question
            original_query: Original query
            
        Yields:
            Streaming summary content
        """
        results = search_response.get("results", [])
        
        if not results:
            yield "Sorry, I couldn't find any information. Please try asking with different keywords."
            return
            
        try:
            print(f"🌊 [RAG-STREAM-DEBUG] Starting streaming summary formatting")
            print(f"   - Number of search results: {len(results)}")
            
            # Build summary data
            chunks = []
            for result in results:
                chunk = result.get("chunk", result)
                chunks.append(chunk)
            
            # Extract game context
            game_context = None
            # Try multiple ways to get game context
            if chunks:
                first_chunk = chunks[0]
                # Way 1: Get game field directly from chunk
                if "game" in first_chunk:
                    game_context = first_chunk["game"]
                # Way 2: Get game field from video_info
                elif "video_info" in first_chunk and isinstance(first_chunk["video_info"], dict):
                    game_context = first_chunk["video_info"].get("game")
            
            # Way 3: Get game field from config or initialization parameters
            if not game_context and hasattr(self, 'config') and self.config:
                game_context = self.config.get("game_name", None)
            
            # Way 4: Use stored game_name
            if not game_context and hasattr(self, 'game_name'):
                game_context = self.game_name
            
            print(f"🎮 [RAG-STREAM-DEBUG] Game context: {game_context}")
            
            # Set game name to summarizer for video source extraction
            if game_context and hasattr(self.summarizer, 'current_game_name'):
                self.summarizer.current_game_name = game_context
            
            # Call summarizer to generate structured reply
            print(f"🚀 [RAG-STREAM-DEBUG] Calling summarizer")
            async for chunk in self.summarizer.summarize_chunks_stream(
                chunks=chunks,
                query=question,
                original_query=original_query,
                context=game_context
            ):
                print(f"📦 [RAG-STREAM-DEBUG] Received summary chunk: {len(chunk)} characters")
                yield chunk
            
            print(f"✅ [RAG-STREAM-DEBUG] Streaming summary formatting completed")
            
        except Exception as e:
            logger.error(f"Streaming summary generation failed: {e}")
            print(f"❌ [RAG-STREAM-DEBUG] Streaming summary generation failed: {e}")
            # Fall back to friendly error message
            yield "😅 Sorry, I encountered a problem while organizing information. Let me answer you in a simple way:\n\n"
            yield self._format_simple_answer(results)

    def _format_simple_answer(self, results: List[Dict[str, Any]]) -> str:
        """简单格式化答案（摘要失败时的回退方案）"""
        if not results:
            return "No related information found."
        
        # Only take the most relevant result
        top_result = results[0]
        chunk = top_result.get("chunk", top_result)
        
        topic = chunk.get("topic", "")
        summary = chunk.get("summary", "")
        
        return f"About {topic}:\n{summary}"

    async def query_stream(self, question: str, top_k: int = 3, original_query: str = None, unified_query_result = None) -> AsyncGenerator[str, None]:
        """
        Execute streaming RAG query
        
        Args:
            question: User question
            top_k: Number of search results
            original_query: Original query
            unified_query_result: Preprocessed unified query result (from assistant_integration)
            
        Yields:
            Streaming answer content
        """
        if not self.is_initialized:
            await self.initialize()
            
        # If initialization fails, return fallback information
        if not self.is_initialized or not self.vector_store:
            print(f"❌ [RAG-STREAM-DEBUG] RAG system not initialized correctly, switch to wiki mode")
            yield "Sorry, the guide query system encountered an issue, please try again later."
            return
            
        start_time = time.time()
        
        try:
            print(f"🌊 [RAG-STREAM-DEBUG] Starting streaming RAG query: '{question}'")
            if unified_query_result:
                print(f"📝 [RAG-STREAM-DEBUG] Using preprocessed unified query result:")
                print(f"   - Original query: '{unified_query_result.original_query}'")
                print(f"   - Translated query: '{unified_query_result.translated_query}'") 
                print(f"   - Rewritten query: '{unified_query_result.rewritten_query}'")
                print(f"   - BM25 optimization: '{unified_query_result.bm25_optimized_query}'")
                print(f"   - Intent: {unified_query_result.intent} (Confidence: {unified_query_result.confidence:.3f})")
            
            if hasattr(self, 'vector_store') and self.vector_store:
                # Execute search (same logic as query method)
                if self.enable_hybrid_search and self.hybrid_retriever:
                    print(f"🔍 [RAG-STREAM-DEBUG] Using hybrid search")
                    # If there is a preprocessed result, pass it to hybrid search
                    if unified_query_result:
                        search_response = self._search_hybrid_with_processed_query(unified_query_result, top_k)
                    
                    results = search_response.get("results", [])
                    
                    # Apply intent-aware reranking
                    if self.enable_intent_reranking and self.reranker and results:
                        print(f"🔄 [RAG-STREAM-DEBUG] Applying intent-aware reranking")
                        results = self.reranker.rerank_results(
                            results, 
                            question,
                            intent_weight=self.reranking_config.get("intent_weight", 0.4),
                            semantic_weight=self.reranking_config.get("semantic_weight", 0.6)
                        )
                        search_response["results"] = results
                        # Record reranking information in metadata
                        search_response.setdefault("metadata", {})["reranking_applied"] = True
                    
                    # Format answer (using streaming summary)
                    print(f"🔍 [SUMMARY-STREAM-DEBUG] Checking streaming summary conditions:")
                    print(f"   - enable_summarization: {self.enable_summarization}")
                    print(f"   - summarizer exists: {self.summarizer is not None}")
                    print(f"   - number of results: {len(results)}")
                    
                    if self.enable_summarization and self.summarizer and len(results) > 0:
                        print(f"💬 [RAG-STREAM-DEBUG] Using Gemini streaming summary to format answer")
                        async for chunk in self._format_answer_with_summary_stream(search_response, question, original_query=original_query):
                            yield chunk
                    else:
                        print(f"💬 [RAG-STREAM-DEBUG] Using original format to format answer")
                        if not self.enable_summarization:
                            print(f"   Reason: Summary function not enabled")
                        elif not self.summarizer:
                            print(f"   Reason: Summarizer not initialized")
                        elif len(results) == 0:
                            print(f"   Reason: No search results")
                        answer = self._format_answer(search_response, question)
                        yield answer
                        
                else:
                    # Single vector search
                    print(f"🔍 [RAG-STREAM-DEBUG] Using single vector search")
                    if self.config["vector_store_type"] == "faiss":
                        results = self._search_faiss(question, top_k)
                    else:
                        results = self._search_qdrant(question, top_k)
                    
                    # Apply intent-aware reranking
                    if self.enable_intent_reranking and self.reranker and results:
                        print(f"🔄 [RAG-STREAM-DEBUG] Applying intent-aware reranking (single vector search mode)")
                        results = self.reranker.rerank_results(
                            results, 
                            question,
                            intent_weight=self.reranking_config.get("intent_weight", 0.4),
                            semantic_weight=self.reranking_config.get("semantic_weight", 0.6)
                        )
                    
                    # Build compatible search_response format
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
                                "reasoning": "Query rewrite not used"
                            },
                            "reranking_applied": self.enable_intent_reranking and self.reranker is not None
                        }
                    }
                    
                    # Format answer (using streaming summary)
                    print(f"🔍 [SUMMARY-STREAM-DEBUG] Checking streaming summary conditions (single vector search):")
                    print(f"   - enable_summarization: {self.enable_summarization}")
                    print(f"   - summarizer exists: {self.summarizer is not None}")
                    print(f"   - number of results: {len(results)}")
                    
                    if self.enable_summarization and self.summarizer and len(results) > 0:
                        print(f"💬 [RAG-STREAM-DEBUG] Using Gemini streaming summary to format answer")
                        async for chunk in self._format_answer_with_summary_stream(search_response, question, original_query=original_query):
                            yield chunk
                    else:
                        print(f"💬 [RAG-STREAM-DEBUG] Using original format to format answer")
                        if not self.enable_summarization:
                            print(f"   Reason: Summary function not enabled")
                        elif not self.summarizer:
                            print(f"   Reason: Summarizer not initialized")
                        elif len(results) == 0:
                            print(f"   Reason: No search results")
                        answer = self._format_answer(search_response, question)
                        yield answer
            else:
                # Vector store query failed
                print(f"❌ [RAG-STREAM-DEBUG] Vector store query failed")
                yield "Sorry, the guide query system encountered an issue, please try again later."
                
        except Exception as e:
            print(f"❌ [RAG-STREAM-DEBUG] Streaming query exception: {e}")
            logger.error(f"Streaming query error: {str(e)}")
            yield f"Sorry, an error occurred during the query, please try again later."

# Global instance
_enhanced_rag_query = None
