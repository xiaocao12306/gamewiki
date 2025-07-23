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
from typing import Optional, Dict, Any, List, AsyncGenerator
from pathlib import Path
import time
import sys
import os

class VectorStoreUnavailableError(Exception):
    """向量库不可用错误"""
    pass

def get_resource_path(relative_path: str) -> Path:
    """
    获取资源文件的绝对路径，兼容开发环境和PyInstaller打包环境
    
    Args:
        relative_path: 相对于项目根目录或临时目录的路径
        
    Returns:
        资源文件的绝对路径
    """
    try:
        # PyInstaller打包后的临时目录
        base_path = Path(sys._MEIPASS)
        resource_path = base_path / relative_path
        print(f"🔧 [RAG-DEBUG] 使用PyInstaller临时目录: {base_path}")
        print(f"🔧 [RAG-DEBUG] 构建资源路径: {resource_path}")
    except AttributeError:
        # 开发环境：从当前文件位置向上找到项目根目录
        current_file = Path(__file__).parent  # .../ai/
        base_path = current_file  # 对于ai目录下的文件，直接使用当前目录
        # 如果relative_path以"ai/"开头，需要去掉这个前缀
        if relative_path.startswith("ai/"):
            relative_path = relative_path[3:]  # 去掉"ai/"前缀
        resource_path = base_path / relative_path
        print(f"🔧 [RAG-DEBUG] 使用开发环境路径: {base_path}")
        print(f"🔧 [RAG-DEBUG] 调整后的相对路径: {relative_path}")
        print(f"🔧 [RAG-DEBUG] 构建资源路径: {resource_path}")
    
    return resource_path

# 导入批量嵌入处理器
try:
    from .batch_embedding import BatchEmbeddingProcessor
    BATCH_EMBEDDING_AVAILABLE = True
except ImportError:
    BATCH_EMBEDDING_AVAILABLE = False
    logging.warning("批量嵌入模块不可用")

# 向量库支持 - 延迟导入以避免启动时崩溃
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
from ..config import LLMConfig

logger = logging.getLogger(__name__)

# 全局缓存向量库映射配置
_vector_mappings_cache = None
_vector_mappings_last_modified = None

def load_vector_mappings() -> Dict[str, str]:
    """
    加载向量库映射配置
    
    Returns:
        窗口标题到向量库名称的映射字典
    """
    global _vector_mappings_cache, _vector_mappings_last_modified
    
    try:
        # 获取配置文件路径 - 从ai目录向上找到assets目录
        current_dir = Path(__file__).parent  # .../ai/
        assets_dir = current_dir.parent / "assets"  # .../game_wiki_tooltip/assets/
        mapping_file = assets_dir / "vector_mappings.json"
        
        # 检查文件是否存在
        if not mapping_file.exists():
            logger.warning(f"向量库映射配置文件不存在: {mapping_file}")
            return
        
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
        
        logger.info(f"成功加载向量库映射配置，包含 {len(mappings)} 个映射")
        return mappings
    except Exception as e:
        return

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
    
    # 加载向量库映射配置
    title_to_vectordb_mapping = load_vector_mappings()
    
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
                 jina_api_key: Optional[str] = None,
                 enable_query_rewrite: bool = True,
                 enable_summarization: bool = True,
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
        self.jina_api_key = jina_api_key
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
            print(f"🔧 [RAG-DEBUG] 开始初始化RAG系统 - 游戏: {game_name}")
            logger.info("初始化增强RAG系统...")
            
            if not BATCH_EMBEDDING_AVAILABLE:
                error_msg = "向量搜索功能不可用: 批量嵌入模块导入失败。请检查以下依赖是否正确安装:\n1. numpy\n2. faiss-cpu\n3. 其他嵌入相关依赖"
                print(f"❌ [RAG-DEBUG] {error_msg}")
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            # 确定向量库路径
            if self.vector_store_path is None and game_name:
                # 自动查找向量库 - 使用资源路径函数
                vector_dir = get_resource_path("ai/vectorstore")
                
                print(f"🔍 [RAG-DEBUG] 查找向量库目录: {vector_dir}")
                logger.info(f"查找向量库目录: {vector_dir}")
                config_files = list(vector_dir.glob(f"{game_name}_vectors_config.json"))
                
                if config_files:
                    self.vector_store_path = str(config_files[0])
                    print(f"✅ [RAG-DEBUG] 找到向量库配置: {self.vector_store_path}")
                    logger.info(f"找到向量库配置: {self.vector_store_path}")
                else:
                    error_msg = f"向量库不存在: 未找到游戏 '{game_name}' 的向量库配置文件\n搜索路径: {vector_dir}\n查找模式: {game_name}_vectors_config.json"
                    
                    # 列出现有的文件用于调试
                    try:
                        existing_files = list(vector_dir.glob("*_vectors_config.json"))
                        if existing_files:
                            available_games = [f.stem.replace("_vectors_config", "") for f in existing_files]
                            error_msg += f"\n可用的游戏向量库: {', '.join(available_games)}"
                        else:
                            error_msg += "\n未找到任何向量库配置文件"
                    except Exception as e:
                        error_msg += f"\n无法列出现有文件: {e}"
                    
                    print(f"❌ [RAG-DEBUG] {error_msg}")
                    logger.error(error_msg)
                    raise VectorStoreUnavailableError(error_msg)
            
            if not self.vector_store_path or not Path(self.vector_store_path).exists():
                error_msg = f"向量库配置文件不存在: {self.vector_store_path}"
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            # 加载向量库
            try:
                self.processor = BatchEmbeddingProcessor(api_key=self.jina_api_key)
                self.vector_store = self.processor.load_vector_store(self.vector_store_path)
                
                # 加载配置和元数据
                with open(self.vector_store_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                
                if self.config["vector_store_type"] == "faiss":
                    self.metadata = self.vector_store["metadata"]
                
                logger.info(f"向量库加载完成: {self.config['chunk_count']} 个知识块")
                
                # Store game name from initial parameter
                self.game_name = game_name
                
                # 初始化混合检索器
                if self.enable_hybrid_search:
                    self._initialize_hybrid_retriever()
                    
            except Exception as e:
                error_msg = f"向量库加载失败: {e}"
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            self.is_initialized = True
            logger.info("增强RAG系统初始化完成")
            
        except VectorStoreUnavailableError:
            # 重新抛出向量库特定错误
            self.is_initialized = False
            raise
        except Exception as e:
            error_msg = f"RAG系统初始化失败: {e}"
            logger.error(error_msg)
            self.is_initialized = False
            raise VectorStoreUnavailableError(error_msg)
    
    def _initialize_hybrid_retriever(self):
        """
        初始化混合检索器
        
        Raises:
            VectorStoreUnavailableError: 当混合搜索初始化失败时
        """
        if not self.enable_hybrid_search:
            logger.warning("混合搜索未启用，将仅使用向量搜索")
            return
        
        if not HYBRID_RETRIEVER_AVAILABLE:
            error_msg = "混合搜索初始化失败: 混合检索器模块不可用"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
        
        try:
            # 检查BM25索引文件是否存在 - 修复路径解析问题
            from pathlib import Path
            bm25_index_path = self.config.get("bm25_index_path")
            if not bm25_index_path:
                error_msg = "混合搜索初始化失败: BM25索引路径未在配置中找到"
                logger.error(error_msg)
                raise VectorStoreUnavailableError(error_msg)
            
            # 如果是相对路径，基于资源路径构建绝对路径
            bm25_path = Path(bm25_index_path)
            if not bm25_path.is_absolute():
                # 使用资源路径函数构建路径
                vectorstore_dir = get_resource_path("ai/vectorstore")
                # 尝试基于vectorstore目录
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
                vector_weight=self.hybrid_config.get("vector_weight", 0.3),
                bm25_weight=self.hybrid_config.get("bm25_weight", 0.7),
                rrf_k=self.hybrid_config.get("rrf_k", 60),
                llm_config=self.llm_config,
                enable_unified_processing=enable_unified_processing,  # 从配置中读取
                enable_query_rewrite=enable_query_rewrite
            )
            
            if enable_unified_processing:
                logger.info("混合检索器初始化成功（统一处理模式）")
            else:
                logger.info("混合检索器初始化成功（独立处理模式，禁用统一处理）")
            
        except BM25UnavailableError as e:
            # BM25特定错误，重新包装为向量库错误
            error_msg = f"混合搜索初始化失败: {e}"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
        except (FileNotFoundError, RuntimeError) as e:
            # 文件不存在或其他运行时错误
            error_msg = f"混合搜索初始化失败: {e}"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
        except Exception as e:
            error_msg = f"混合检索器初始化失败: {e}"
            logger.error(error_msg)
            raise VectorStoreUnavailableError(error_msg)
    
    def _initialize_summarizer(self):
        """初始化Gemini摘要器"""
        try:
            import os
            
            # 获取API密钥，优先级：LLM配置 > 摘要配置 > 环境变量
            api_key = None
            if self.llm_config and hasattr(self.llm_config, 'get_api_key'):
                api_key = self.llm_config.get_api_key()
            
            if not api_key:
                api_key = self.summarization_config.get("api_key") or os.environ.get("GEMINI_API_KEY")
            
            if not api_key:
                logger.warning("未找到Gemini API密钥，摘要功能将被禁用")
                self.enable_summarization = False
                return
            
            # 创建摘要配置 (移除已废弃的max_summary_length参数)
            config = SummarizationConfig(
                api_key=api_key,
                model_name=self.summarization_config.get("model_name", "gemini-2.5-flash-lite-preview-06-17"),
                temperature=self.summarization_config.get("temperature", 0.3),
                include_sources=self.summarization_config.get("include_sources", True),
                language=self.summarization_config.get("language", "auto")
            )
            
            # 创建摘要器 (移除已废弃的max_summary_length参数)
            self.summarizer = create_gemini_summarizer(
                api_key=api_key,
                model_name=config.model_name,
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
        print(f"🔍 [VECTOR-DEBUG] 开始FAISS向量检索: query='{query}', top_k={top_k}")
        
        if not self.vector_store or not self.metadata:
            print(f"⚠️ [VECTOR-DEBUG] 向量库或元数据未初始化")
            logger.warning("向量库或元数据未初始化")
            return []
        
        try:
            # 获取查询向量
            query_text = self.processor.build_text({"topic": query, "summary": query, "keywords": []})
            print(f"📄 [VECTOR-DEBUG] 构建查询文本: '{query_text[:100]}...'")
            
            query_vectors = self.processor.embed_batch([query_text])
            query_vector = np.array(query_vectors[0], dtype=np.float32).reshape(1, -1)
            print(f"🔢 [VECTOR-DEBUG] 查询向量维度: {query_vector.shape}, 前5个值: {query_vector[0][:5]}")
            
            # 构建正确的索引文件路径
            # 使用与BatchEmbeddingProcessor._load_faiss_store相同的路径逻辑
            index_path_str = self.config["index_path"]
            if not Path(index_path_str).is_absolute():
                # 使用资源路径函数来构建绝对路径
                vectorstore_dir = get_resource_path("ai/vectorstore")
                index_path = vectorstore_dir / Path(index_path_str).name
            else:
                index_path = Path(index_path_str)
            
            index_file_path = index_path / "index.faiss"
            print(f"📂 [VECTOR-DEBUG] FAISS索引文件路径: {index_file_path}")
            logger.info(f"尝试加载FAISS索引文件: {index_file_path}")
            
            if not index_file_path.exists():
                print(f"❌ [VECTOR-DEBUG] FAISS索引文件不存在: {index_file_path}")
                logger.error(f"FAISS索引文件不存在: {index_file_path}")
                return []
            
            # 加载FAISS索引
            try:
                import faiss
            except ImportError:
                logger.error("无法导入faiss库")
                print(f"❌ [VECTOR-DEBUG] 无法导入faiss库，请确保已安装faiss-cpu")
                return []
            
            index = faiss.read_index(str(index_file_path))
            print(f"📊 [VECTOR-DEBUG] FAISS索引信息: 总向量数={index.ntotal}, 维度={index.d}")
            
            # 执行检索
            scores, indices = index.search(query_vector, top_k)
            print(f"🔍 [VECTOR-DEBUG] FAISS检索原始结果:")
            print(f"   - 检索到的索引: {indices[0]}")
            print(f"   - 相似度分数: {scores[0]}")
            
            # 返回结果
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
                    
                    # 详细的结果调试信息
                    print(f"   📋 [VECTOR-DEBUG] 结果 {i+1}:")
                    print(f"      - 相似度分数: {score:.4f}")
                    print(f"      - 索引ID: {idx}")
                    print(f"      - 主题: {chunk.get('topic', 'Unknown')}")
                    print(f"      - 摘要: {chunk.get('summary', '')[:100]}...")
                    print(f"      - 关键词: {chunk.get('keywords', [])}")
                    
                    # 如果是结构化数据，显示敌人信息
                    if "structured_data" in chunk:
                        structured = chunk["structured_data"]
                        if "enemy_name" in structured:
                            print(f"      - 敌人名称: {structured['enemy_name']}")
                        if "weak_points" in structured:
                            weak_points = [wp.get("name", "Unknown") for wp in structured["weak_points"]]
                            print(f"      - 弱点: {weak_points}")
            
            print(f"✅ [VECTOR-DEBUG] FAISS检索完成，找到 {len(results)} 个结果")
            logger.info(f"FAISS检索完成，找到 {len(results)} 个结果")
            return results
            
        except Exception as e:
            print(f"❌ [VECTOR-DEBUG] FAISS检索失败: {e}")
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
        print(f"🔍 [VECTOR-DEBUG] 开始Qdrant向量检索: query='{query}', top_k={top_k}")
        
        if not self.vector_store or not QDRANT_AVAILABLE:
            print(f"⚠️ [VECTOR-DEBUG] Qdrant向量库未初始化或不可用")
            logger.warning("Qdrant向量库未初始化或不可用")
            return []
        
        try:
            # 获取查询向量
            query_text = self.processor.build_text({"topic": query, "summary": query, "keywords": []})
            print(f"📄 [VECTOR-DEBUG] 构建查询文本: '{query_text[:100]}...'")
            
            query_vectors = self.processor.embed_batch([query_text])
            query_vector = query_vectors[0]
            print(f"🔢 [VECTOR-DEBUG] 查询向量维度: {len(query_vector)}, 前5个值: {query_vector[:5]}")
            
            # 执行检索
            print(f"🔍 [VECTOR-DEBUG] 调用Qdrant搜索: collection={self.config['collection_name']}")
            results = self.vector_store.search(
                collection_name=self.config["collection_name"],
                query_vector=query_vector,
                limit=top_k
            )
            
            print(f"📊 [VECTOR-DEBUG] Qdrant检索原始结果数量: {len(results)}")
            
            # 格式化结果
            formatted_results = []
            for i, result in enumerate(results):
                chunk_info = {
                    "chunk": result.payload,
                    "score": result.score,
                    "rank": i + 1
                }
                formatted_results.append(chunk_info)
                
                # 详细的结果调试信息
                print(f"   📋 [VECTOR-DEBUG] 结果 {i+1}:")
                print(f"      - 相似度分数: {result.score:.4f}")
                print(f"      - 主题: {result.payload.get('topic', 'Unknown')}")
                print(f"      - 摘要: {result.payload.get('summary', '')[:100]}...")
                print(f"      - 关键词: {result.payload.get('keywords', [])}")
                
                # 如果是结构化数据，显示敌人信息
                if "structured_data" in result.payload:
                    structured = result.payload["structured_data"]
                    if "enemy_name" in structured:
                        print(f"      - 敌人名称: {structured['enemy_name']}")
                    if "weak_points" in structured:
                        weak_points = [wp.get("name", "Unknown") for wp in structured["weak_points"]]
                        print(f"      - 弱点: {weak_points}")
            
            print(f"✅ [VECTOR-DEBUG] Qdrant检索完成，找到 {len(formatted_results)} 个结果")
            logger.info(f"Qdrant检索完成，找到 {len(formatted_results)} 个结果")
            return formatted_results
            
        except Exception as e:
            print(f"❌ [VECTOR-DEBUG] Qdrant检索失败: {e}")
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
        print(f"🔍 [RAG-DEBUG] 进入混合搜索: query='{query}', top_k={top_k}")
        
        if not self.hybrid_retriever:
            print(f"⚠️ [RAG-DEBUG] 混合检索器未初始化，回退到向量搜索")
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
            print(f"🚀 [RAG-DEBUG] 开始执行混合搜索")
            search_response = self.hybrid_retriever.search(query, top_k)
            result_count = len(search_response.get('results', []))
            print(f"✅ [RAG-DEBUG] 混合搜索完成，找到 {result_count} 个结果")
            logger.info(f"混合搜索完成，找到 {result_count} 个结果")
            return search_response
        except Exception as e:
            print(f"❌ [RAG-DEBUG] 混合搜索失败: {e}")
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
    
    def _search_hybrid_with_processed_query(self, unified_query_result, top_k: int = 3) -> Dict[str, Any]:
        """
        使用预处理的统一查询结果进行混合搜索
        
        Args:
            unified_query_result: 统一查询处理结果对象
            top_k: 返回结果数量
            
        Returns:
            混合搜索结果（包含元数据）
        """
        print(f"🔍 [RAG-DEBUG] 进入混合搜索（预处理模式）: top_k={top_k}")
        
        if not self.hybrid_retriever:
            print(f"⚠️ [RAG-DEBUG] 混合检索器未初始化，回退到向量搜索")
            logger.warning("混合检索器未初始化，回退到向量搜索")
            # 使用重写后的查询进行向量搜索
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
        
        # 直接调用混合检索器，禁用其内部的统一处理（避免重复处理）
        try:
            print(f"🚀 [RAG-DEBUG] 开始执行混合搜索（使用预处理结果）")
            print(f"   - 语义查询: '{unified_query_result.rewritten_query}'")
            print(f"   - BM25查询: '{unified_query_result.bm25_optimized_query}'")
            
            # 手动执行混合搜索流程，使用预处理的查询
            # 向量搜索使用重写查询
            vector_search_count = 10
            bm25_search_count = 10
            
            print(f"🔍 [HYBRID-DEBUG] 开始向量搜索: query='{unified_query_result.rewritten_query}', top_k={vector_search_count}")
            vector_results = self.hybrid_retriever.vector_retriever.search(unified_query_result.rewritten_query, vector_search_count)
            print(f"📊 [HYBRID-DEBUG] 向量搜索结果数量: {len(vector_results)}")
            
            # BM25搜索使用优化查询
            bm25_results = []
            if self.hybrid_retriever.bm25_indexer:
                print(f"🔍 [HYBRID-DEBUG] 开始BM25搜索:")
                print(f"   - 原始查询: '{unified_query_result.original_query}'")
                print(f"   - 语义查询: '{unified_query_result.rewritten_query}'")
                print(f"   - BM25优化: '{unified_query_result.bm25_optimized_query}'")
                print(f"   - 检索数量: {bm25_search_count}")
                
                bm25_results = self.hybrid_retriever.bm25_indexer.search(unified_query_result.bm25_optimized_query, bm25_search_count)
                print(f"📊 [HYBRID-DEBUG] BM25搜索结果数量: {len(bm25_results)}")
            else:
                print(f"⚠️ [HYBRID-DEBUG] BM25索引器未初始化，跳过BM25搜索")
            
            # 分数融合
            final_result_count = 5
            print(f"🔄 [HYBRID-DEBUG] 开始分数融合: 方法={self.hybrid_retriever.fusion_method}")
            
            final_results = self.hybrid_retriever._fuse_results(vector_results, bm25_results, final_result_count)
            
            print(f"✅ [HYBRID-DEBUG] 分数融合完成，最终结果数量: {len(final_results)}")
            
            # 构建返回结果
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
            print(f"❌ [RAG-DEBUG] 混合搜索失败: {e}")
            logger.error(f"混合搜索失败: {e}")
            # 回退到向量搜索
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
    
    async def _format_answer_with_summary(self, search_response: Dict[str, Any], question: str, original_query: str = None) -> str:
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
            # 准备知识块数据，包含完整的结构化信息
            chunks = []
            for result in results:
                chunk_data = result["chunk"]
                
                # 传递完整的 chunk 数据，包括 structured_data
                chunk_for_summary = {
                    "topic": chunk_data.get("topic", "未知主题"),
                    "summary": chunk_data.get("summary", ""),
                    "keywords": chunk_data.get("keywords", []),
                    "type": chunk_data.get("type", "General"),
                    "structured_data": chunk_data.get("structured_data", {}),
                    "score": result.get("score", 0),
                    "content": chunk_data.get("summary", "")
                }
                
                chunks.append(chunk_for_summary)
            
            # 获取游戏上下文
            game_context = None
            # 尝试多种方式获取游戏上下文
            if chunks:
                first_chunk = chunks[0]
                # 方式1: 直接从chunk获取game字段
                if "game" in first_chunk:
                    game_context = first_chunk["game"]
                # 方式2: 从video_info中获取
                elif "video_info" in first_chunk and isinstance(first_chunk["video_info"], dict):
                    game_context = first_chunk["video_info"].get("game")
            
            # 方式3: 从config获取
            if not game_context and hasattr(self, 'config') and self.config:
                game_context = self.config.get("game_name", None)
            
            # 方式4: 使用存储的game_name
            if not game_context and hasattr(self, 'game_name'):
                game_context = self.game_name
            
            # Set game name in summarizer for video source extraction
            if game_context and hasattr(self.summarizer, 'current_game_name'):
                self.summarizer.current_game_name = game_context
            
            # 调用摘要器生成结构化回复
            summary_result = self.summarizer.summarize_chunks(
                chunks=chunks,
                query=question,
                original_query=original_query,
                context=game_context
            )
            
            # 直接返回摘要内容（一句话总结+详细讲解格式）
            return summary_result["summary"]
            
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")
            # 回退到友好的错误消息
            return "😅 抱歉，我在整理信息时遇到了一点问题。让我用简单的方式回答你：\n\n" + self._format_simple_answer(results)
    
    async def _format_answer_with_summary_stream(self, search_response: Dict[str, Any], question: str, original_query: str = None) -> AsyncGenerator[str, None]:
        """
        使用Gemini摘要器流式格式化检索结果
        
        Args:
            search_response: 搜索响应（包含results和metadata）
            question: 原始问题
            original_query: 原始查询
            
        Yields:
            流式摘要内容
        """
        results = search_response.get("results", [])
        
        if not results:
            yield "抱歉，没有找到相关信息。请尝试其他关键词。"
            return
            
        try:
            print(f"🌊 [RAG-STREAM-DEBUG] 开始流式摘要格式化")
            print(f"   - 检索结果数量: {len(results)}")
            
            # 构建摘要数据
            chunks = []
            for result in results:
                chunk = result.get("chunk", result)
                chunks.append(chunk)
            
            # 提取游戏上下文
            game_context = None
            # 尝试多种方式获取游戏上下文
            if chunks:
                first_chunk = chunks[0]
                # 方式1: 直接从chunk获取game字段
                if "game" in first_chunk:
                    game_context = first_chunk["game"]
                # 方式2: 从video_info中获取
                elif "video_info" in first_chunk and isinstance(first_chunk["video_info"], dict):
                    game_context = first_chunk["video_info"].get("game")
            
            # 方式3: 从config或初始化参数获取
            if not game_context and hasattr(self, 'config') and self.config:
                game_context = self.config.get("game_name", None)
            
            # 方式4: 使用存储的game_name
            if not game_context and hasattr(self, 'game_name'):
                game_context = self.game_name
            
            print(f"🎮 [RAG-STREAM-DEBUG] 游戏上下文: {game_context}")
            
            # 设置游戏名称到摘要器中用于视频源提取
            if game_context and hasattr(self.summarizer, 'current_game_name'):
                self.summarizer.current_game_name = game_context
            
            # 调用流式摘要器生成结构化回复
            print(f"🚀 [RAG-STREAM-DEBUG] 调用流式摘要器")
            async for chunk in self.summarizer.summarize_chunks_stream(
                chunks=chunks,
                query=question,
                original_query=original_query,
                context=game_context
            ):
                print(f"📦 [RAG-STREAM-DEBUG] 收到摘要块: {len(chunk)} 字符")
                yield chunk
            
            print(f"✅ [RAG-STREAM-DEBUG] 流式摘要格式化完成")
            
        except Exception as e:
            logger.error(f"流式摘要生成失败: {e}")
            print(f"❌ [RAG-STREAM-DEBUG] 流式摘要生成失败: {e}")
            # 回退到友好的错误消息
            yield "😅 抱歉，我在整理信息时遇到了一点问题。让我用简单的方式回答你：\n\n"
            yield self._format_simple_answer(results)

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
    
    async def query(self, question: str, top_k: int = 3, original_query: str = None, unified_query_result = None) -> Dict[str, Any]:
        """
        执行RAG查询
        
        Args:
            question: 用户问题
            top_k: 检索结果数量
            original_query: 原始查询（用于摘要）
            unified_query_result: 预处理的统一查询结果（来自assistant_integration）
            
        Returns:
            包含答案的字典
        """
        if not self.is_initialized:
            await self.initialize()
            
        # 如果初始化后仍然没有向量库，返回fallback_to_wiki
        if not self.is_initialized or not self.vector_store:
            print(f"❌ [RAG-DEBUG] RAG系统未正确初始化，建议切换到wiki模式")
            return {
                "answer": "",
                "sources": [],
                "confidence": 0.0,
                "query_time": 0.0,
                "results_count": 0,
                "error": "RAG_NOT_INITIALIZED",
                "fallback_to_wiki": True
            }
        
        try:
            print(f"🔍 [RAG-DEBUG] 开始RAG查询: {question}")
            if unified_query_result:
                print(f"📝 [RAG-DEBUG] 使用预处理的统一查询结果:")
                print(f"   - 原始查询: '{unified_query_result.original_query}'")
                print(f"   - 翻译查询: '{unified_query_result.translated_query}'") 
                print(f"   - 重写查询: '{unified_query_result.rewritten_query}'")
                print(f"   - BM25优化: '{unified_query_result.bm25_optimized_query}'")
                print(f"   - 意图: {unified_query_result.intent} (置信度: {unified_query_result.confidence:.3f})")
            
            start_time = asyncio.get_event_loop().time()
            
            # 执行检索
            if self.vector_store and self.config:
                # 选择搜索方式
                if self.enable_hybrid_search and self.hybrid_retriever:
                    print(f"🔍 [RAG-DEBUG] 使用混合搜索")
                    # 如果有预处理结果，传递给混合搜索
                    if unified_query_result:
                        search_response = self._search_hybrid_with_processed_query(unified_query_result, top_k)
                    else:
                        search_response = self._search_hybrid(question, top_k)
                    
                    results = search_response.get("results", [])
                    
                    # 应用意图感知重排序
                    if self.enable_intent_reranking and self.reranker and results:
                        print(f"🔄 [RAG-DEBUG] 应用意图感知重排序")
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
                    print(f"🔍 [SUMMARY-DEBUG] 检查摘要条件 (混合搜索):")
                    print(f"   - enable_summarization: {self.enable_summarization}")
                    print(f"   - summarizer存在: {self.summarizer is not None}")
                    print(f"   - 结果数量: {len(results)}")
                    
                    if self.enable_summarization and self.summarizer and len(results) > 0:
                        print(f"💬 [RAG-DEBUG] 使用Gemini摘要格式化答案")
                        answer = await self._format_answer_with_summary(search_response, question, original_query=original_query)
                    else:
                        print(f"💬 [RAG-DEBUG] 使用原始格式化答案")
                        if not self.enable_summarization:
                            print(f"   原因: 摘要功能未启用")
                        elif not self.summarizer:
                            print(f"   原因: 摘要器未初始化")
                        elif len(results) == 0:
                            print(f"   原因: 没有检索结果")
                        answer = self._format_answer(search_response, question)
                    
                    confidence = max([r["score"] for r in results]) if results else 0.0
                    sources = [r["chunk"].get("topic", "未知") for r in results]
                    
                    # 添加搜索元数据
                    search_metadata = search_response.get("metadata", {})
                    
                else:
                    # 单一搜索
                    print(f"🔍 [RAG-DEBUG] 使用单一向量搜索")
                    if self.config["vector_store_type"] == "faiss":
                        results = self._search_faiss(question, top_k)
                    else:
                        results = self._search_qdrant(question, top_k)
                    
                    # 应用意图感知重排序
                    if self.enable_intent_reranking and self.reranker and results:
                        print(f"🔄 [RAG-DEBUG] 应用意图感知重排序（单一搜索模式）")
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
                    print(f"🔍 [SUMMARY-DEBUG] 检查摘要条件 (单一搜索):")
                    print(f"   - enable_summarization: {self.enable_summarization}")
                    print(f"   - summarizer存在: {self.summarizer is not None}")
                    print(f"   - 结果数量: {len(results)}")
                    
                    if self.enable_summarization and self.summarizer and len(results) > 0:
                        print(f"💬 [RAG-DEBUG] 使用Gemini摘要格式化答案")
                        answer = await self._format_answer_with_summary(search_response, question, original_query=original_query)
                    else:
                        print(f"💬 [RAG-DEBUG] 使用原始格式化答案")
                        if not self.enable_summarization:
                            print(f"   原因: 摘要功能未启用")
                        elif not self.summarizer:
                            print(f"   原因: 摘要器未初始化")
                        elif len(results) == 0:
                            print(f"   原因: 没有检索结果")
                        answer = self._format_answer(search_response, question)
                    
                    confidence = max([r["score"] for r in results]) if results else 0.0
                    sources = [r["chunk"].get("topic", "未知") for r in results]
                    search_metadata = search_response.get("metadata", {})
                
            else:
                # 检查是否是因为向量库不存在
                if (hasattr(self, 'vector_store_path') and self.vector_store_path is None) or not self.vector_store:
                    # 没有找到对应的向量库，返回特殊错误标识，让调用方切换到wiki模式
                    print(f"❌ [RAG-DEBUG] 向量库未找到，建议切换到wiki模式")
                    return {
                        "answer": "",  # 空答案，由调用方处理
                        "sources": [],
                        "confidence": 0.0,
                        "query_time": 0.0,
                        "results_count": 0,
                        "error": "VECTOR_STORE_NOT_FOUND",
                        "fallback_to_wiki": True  # 添加标识，提示调用方切换到wiki模式
                    }
                else:
                    # 其他情况的错误
                    print(f"❌ [RAG-DEBUG] 向量库查询失败，原因未知")
                    return {
                        "answer": "抱歉，攻略查询系统出现问题，请稍后重试。",
                        "sources": [],
                        "confidence": 0.0,
                        "query_time": 0.0,
                        "results_count": 0,
                        "error": "RAG_SYSTEM_ERROR"
                    }
            
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
            
            print(f"✅ [RAG-DEBUG] RAG查询完成，耗时: {query_time:.2f}秒")
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

    async def query_stream(self, question: str, top_k: int = 3, original_query: str = None, unified_query_result = None) -> AsyncGenerator[str, None]:
        """
        执行流式RAG查询
        
        Args:
            question: 用户问题
            top_k: 检索结果数量
            original_query: 原始查询
            unified_query_result: 预处理的统一查询结果（来自assistant_integration）
            
        Yields:
            流式答案内容
        """
        if not self.is_initialized:
            await self.initialize()
            
        # 如果初始化后仍然没有向量库，返回fallback信息
        if not self.is_initialized or not self.vector_store:
            print(f"❌ [RAG-STREAM-DEBUG] RAG系统未正确初始化，建议切换到wiki模式")
            yield "抱歉，攻略查询系统出现问题，请稍后重试。"
            return
            
        start_time = time.time()
        
        try:
            print(f"🌊 [RAG-STREAM-DEBUG] 开始流式RAG查询: '{question}'")
            if unified_query_result:
                print(f"📝 [RAG-STREAM-DEBUG] 使用预处理的统一查询结果:")
                print(f"   - 原始查询: '{unified_query_result.original_query}'")
                print(f"   - 翻译查询: '{unified_query_result.translated_query}'") 
                print(f"   - 重写查询: '{unified_query_result.rewritten_query}'")
                print(f"   - BM25优化: '{unified_query_result.bm25_optimized_query}'")
                print(f"   - 意图: {unified_query_result.intent} (置信度: {unified_query_result.confidence:.3f})")
            
            if hasattr(self, 'vector_store') and self.vector_store:
                # 执行搜索（与query方法相同的逻辑）
                if self.enable_hybrid_search and self.hybrid_retriever:
                    print(f"🔍 [RAG-STREAM-DEBUG] 使用混合搜索")
                    # 如果有预处理结果，传递给混合搜索
                    if unified_query_result:
                        search_response = self._search_hybrid_with_processed_query(unified_query_result, top_k)
                    else:
                        search_response = self._search_hybrid(question, top_k)
                    
                    results = search_response.get("results", [])
                    
                    # 应用意图感知重排序
                    if self.enable_intent_reranking and self.reranker and results:
                        print(f"🔄 [RAG-STREAM-DEBUG] 应用意图感知重排序")
                        results = self.reranker.rerank_results(
                            results, 
                            question,
                            intent_weight=self.reranking_config.get("intent_weight", 0.4),
                            semantic_weight=self.reranking_config.get("semantic_weight", 0.6)
                        )
                        search_response["results"] = results
                        # 在元数据中记录重排序信息
                        search_response.setdefault("metadata", {})["reranking_applied"] = True
                    
                    # 格式化答案（使用流式摘要）
                    print(f"🔍 [SUMMARY-STREAM-DEBUG] 检查流式摘要条件:")
                    print(f"   - enable_summarization: {self.enable_summarization}")
                    print(f"   - summarizer存在: {self.summarizer is not None}")
                    print(f"   - 结果数量: {len(results)}")
                    
                    if self.enable_summarization and self.summarizer and len(results) > 0:
                        print(f"💬 [RAG-STREAM-DEBUG] 使用Gemini流式摘要格式化答案")
                        async for chunk in self._format_answer_with_summary_stream(search_response, question, original_query=original_query):
                            yield chunk
                    else:
                        print(f"💬 [RAG-STREAM-DEBUG] 使用原始格式化答案")
                        if not self.enable_summarization:
                            print(f"   原因: 摘要功能未启用")
                        elif not self.summarizer:
                            print(f"   原因: 摘要器未初始化")
                        elif len(results) == 0:
                            print(f"   原因: 没有检索结果")
                        answer = self._format_answer(search_response, question)
                        yield answer
                        
                else:
                    # 单一搜索
                    print(f"🔍 [RAG-STREAM-DEBUG] 使用单一向量搜索")
                    if self.config["vector_store_type"] == "faiss":
                        results = self._search_faiss(question, top_k)
                    else:
                        results = self._search_qdrant(question, top_k)
                    
                    # 应用意图感知重排序
                    if self.enable_intent_reranking and self.reranker and results:
                        print(f"🔄 [RAG-STREAM-DEBUG] 应用意图感知重排序（单一搜索模式）")
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
                    
                    # 格式化答案（使用流式摘要）
                    print(f"🔍 [SUMMARY-STREAM-DEBUG] 检查流式摘要条件 (单一搜索):")
                    print(f"   - enable_summarization: {self.enable_summarization}")
                    print(f"   - summarizer存在: {self.summarizer is not None}")
                    print(f"   - 结果数量: {len(results)}")
                    
                    if self.enable_summarization and self.summarizer and len(results) > 0:
                        print(f"💬 [RAG-STREAM-DEBUG] 使用Gemini流式摘要格式化答案")
                        async for chunk in self._format_answer_with_summary_stream(search_response, question, original_query=original_query):
                            yield chunk
                    else:
                        print(f"💬 [RAG-STREAM-DEBUG] 使用原始格式化答案")
                        if not self.enable_summarization:
                            print(f"   原因: 摘要功能未启用")
                        elif not self.summarizer:
                            print(f"   原因: 摘要器未初始化")
                        elif len(results) == 0:
                            print(f"   原因: 没有检索结果")
                        answer = self._format_answer(search_response, question)
                        yield answer
            else:
                # 向量库查询失败
                print(f"❌ [RAG-STREAM-DEBUG] 向量库查询失败")
                yield "抱歉，攻略查询系统出现问题，请稍后重试。"
                
        except Exception as e:
            print(f"❌ [RAG-STREAM-DEBUG] 流式查询异常: {e}")
            logger.error(f"Streaming query error: {str(e)}")
            yield f"抱歉，查询过程中出现错误: {str(e)}"



# 全局实例
_enhanced_rag_query = None

def get_enhanced_rag_query(vector_store_path: Optional[str] = None,
                          llm_config: Optional[LLMConfig] = None,
                          enable_summarization: bool = True) -> EnhancedRagQuery:
    """获取增强RAG查询器的单例实例"""
    global _enhanced_rag_query
    if _enhanced_rag_query is None:
        _enhanced_rag_query = EnhancedRagQuery(
            vector_store_path=vector_store_path,
            llm_config=llm_config,
            enable_summarization=enable_summarization
        )
    return _enhanced_rag_query

async def query_enhanced_rag(question: str, 
                           game_name: Optional[str] = None,
                           top_k: int = 3,
                           enable_hybrid_search: bool = True,
                           hybrid_config: Optional[Dict] = None,
                           llm_config: Optional[LLMConfig] = None,
                           enable_summarization: bool = True,
                           summarization_config: Optional[Dict] = None,
                           enable_intent_reranking: bool = True,
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
    print(f"🎯 [RAG-DEBUG] 调用query_enhanced_rag - 问题: '{question}', 游戏: {game_name}")
    print(f"🔧 [RAG-DEBUG] 配置 - 混合搜索: {enable_hybrid_search}, 摘要: {enable_summarization}, 重排序: {enable_intent_reranking}")
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
                enable_summarization = summarization_settings.get("enabled", True)  # 默认启用摘要
                summarization_config = {
                    "api_key": summarization_settings.get("api_key") or os.environ.get("GEMINI_API_KEY"),
                    "model_name": summarization_settings.get("model_name", "gemini-2.5-flash-lite-preview-06-17"),
                    # 移除已废弃的max_summary_length参数
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
    
    print(f"🔧 [RAG-DEBUG] 创建EnhancedRagQuery实例")
    rag_query = EnhancedRagQuery(
        enable_hybrid_search=enable_hybrid_search,
        hybrid_config=hybrid_config,
        llm_config=llm_config,
        enable_summarization=enable_summarization,
        summarization_config=summarization_config,
        enable_intent_reranking=enable_intent_reranking,
        reranking_config=reranking_config
    )
    
    print(f"🔧 [RAG-DEBUG] 初始化RAG引擎")
    await rag_query.initialize(game_name)
    
    print(f"🔍 [RAG-DEBUG] 执行RAG查询（流式）")
    answer_parts = []
    async for chunk in rag_query.query_stream(question, top_k):
        answer_parts.append(chunk)
    
    # 构建与原 query 方法兼容的结果格式
    result = {
        "answer": "".join(answer_parts),
        "sources": [],
        "confidence": 0.0,
        "query_time": 0.0,
        "results_count": 0
    }
    print(f"✅ [RAG-DEBUG] query_enhanced_rag完成")
    return result


class SimpleRagQuery(EnhancedRagQuery):
    """简化的RAG查询器，保持向后兼容"""
    pass

def get_rag_query() -> SimpleRagQuery:
    """获取简化RAG查询器的单例实例（向后兼容）"""
    return SimpleRagQuery()

async def query_rag(question: str, game_name: Optional[str] = None) -> Dict[str, Any]:
    """执行简化RAG查询的便捷函数（向后兼容）"""
    return await query_enhanced_rag(question, game_name) 