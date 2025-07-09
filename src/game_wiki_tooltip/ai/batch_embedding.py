"""
批量嵌入处理器 - 集成Jina API和向量库存储
===========================================

功能：
1. 读取knowledge_chunks JSON文件
2. 批量调用Jina API进行嵌入
3. 存储到FAISS/Qdrant向量库
4. 优化存储和检索性能
"""

import os
import json
import requests
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from tqdm import tqdm
import logging

# 尝试加载.env文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 如果没有dotenv，就跳过
from dotenv import load_dotenv
load_dotenv()

# 向量库支持
try:
    import qdrant_client
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logging.warning("qdrant-client未安装，将使用FAISS作为备选")

try:
    import faiss
    from langchain_community.vectorstores import FAISS
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logging.warning("faiss-cpu未安装，向量库功能不可用")

logger = logging.getLogger(__name__)

class BatchEmbeddingProcessor:
    """批量嵌入处理器"""
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 model: str = "jina-embeddings-v4",
                 adapter: str = "retrieval.passage",
                 output_dim: int = 768,
                 vector_store_type: str = "faiss"):
        """
        初始化批量嵌入处理器
        
        Args:
            api_key: Jina API密钥，如果为None则从环境变量获取
            model: 使用的嵌入模型
            adapter: 适配器类型
            output_dim: 输出向量维度
            vector_store_type: 向量库类型 ("faiss" 或 "qdrant")
        """
        self.api_key = api_key or os.environ.get("JINA_API_KEY")
        if not self.api_key:
            raise ValueError("需要提供JINA_API_KEY环境变量或参数")
            
        self.model = model
        self.adapter = adapter
        self.output_dim = output_dim
        self.vector_store_type = vector_store_type.lower()
        
        # 验证向量库支持
        if self.vector_store_type == "qdrant" and not QDRANT_AVAILABLE:
            logger.warning("Qdrant不可用，切换到FAISS")
            self.vector_store_type = "faiss"
            
        if not FAISS_AVAILABLE:
            raise ImportError("需要安装faiss-cpu或qdrant-client")
    
    def build_text(self, chunk: Dict[str, Any]) -> str:
        """
        构建用于嵌入的文本
        
        Args:
            chunk: knowledge_chunk字典
            
        Returns:
            格式化的文本字符串
        """
        text_parts = [
            f"Topic: {chunk.get('topic', 'Unknown')}",
            chunk.get('summary', ''),
            f"Keywords: {', '.join(chunk.get('keywords', []))}"
        ]
        
        # 可选：添加rationale信息
        if 'build' in chunk and 'focus' in chunk['build']:
            text_parts.append(f"Focus: {chunk['build']['focus']}")
            
        return "\n".join(text_parts)
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量调用Jina API进行嵌入
        
        Args:
            texts: 文本列表
            
        Returns:
            嵌入向量列表
        """
        url = "https://api.jina.ai/v1/embeddings"
        
        # 按照Jina官方示例格式构建输入
        input_data = [{"text": text} for text in texts]
        
        payload = {
            "model": self.model,
            "task": self.adapter,
            "dimensions": self.output_dim,  # 使用dimensions而不是output_dim
            "input": input_data
        }
        
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 添加调试信息
            if result.get("data") and len(result["data"]) > 0:
                first_embedding = result["data"][0].get("embedding", [])
                logger.info(f"Jina返回的第一个向量长度: {len(first_embedding)}")
                logger.info(f"期望的向量维度: {self.output_dim}")
            
            return [e["embedding"] for e in result["data"]]
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Jina API调用失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"API响应: {e.response.text}")
            raise
    
    def process_json_file(self, 
                         json_path: str, 
                         output_dir: str = "vectorstore",
                         batch_size: int = 64,
                         collection_name: str = "gamefloaty") -> str:
        """
        处理JSON文件并构建向量库
        
        Args:
            json_path: JSON文件路径
            output_dir: 输出目录
            batch_size: 批处理大小
            collection_name: 集合名称
            
        Returns:
            向量库路径
        """
        # 读取JSON文件
        logger.info(f"读取JSON文件: {json_path}")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取knowledge_chunks
        if isinstance(data, list):
            chunks = []
            for item in data:
                if isinstance(item, dict):
                    if "knowledge_chunks" in item:
                        # 直接包含knowledge_chunks的对象
                        chunks.extend(item["knowledge_chunks"])
                    elif "videos" in item:
                        # 包含videos数组的对象，跳过（这些是视频列表，不是知识块）
                        continue
            if not chunks:
                # 如果没有找到knowledge_chunks，可能是直接的chunks数组
                chunks = data
        elif isinstance(data, dict) and "knowledge_chunks" in data:
            chunks = data["knowledge_chunks"]
        else:
            raise ValueError("JSON文件格式不正确，需要包含knowledge_chunks数组")
        
        logger.info(f"找到 {len(chunks)} 个知识块")
        
        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        if self.vector_store_type == "qdrant":
            return self._build_qdrant_index(chunks, output_path, batch_size, collection_name)
        else:
            return self._build_faiss_index(chunks, output_path, batch_size, collection_name)
    
    def _build_qdrant_index(self, 
                           chunks: List[Dict], 
                           output_path: Path,
                           batch_size: int,
                           collection_name: str) -> str:
        """构建Qdrant索引"""
        # 初始化Qdrant客户端
        client = qdrant_client.QdrantClient(":memory:")  # 内存模式，生产环境可改为文件路径
        client.recreate_collection(
            collection_name, 
            vector_size=self.output_dim, 
            distance="Cosine"
        )
        
        # 批量处理
        for i in tqdm(range(0, len(chunks), batch_size), desc="构建Qdrant索引"):
            batch = chunks[i:i + batch_size]
            texts = [self.build_text(c) for c in batch]
            vectors = self.embed_batch(texts)
            
            # 上传到Qdrant
            client.upload_collection(
                collection_name=collection_name,
                vectors=vectors,
                payload=batch,  # 原始JSON作为payload
                ids=[c.get("chunk_id", f"chunk_{i+j}") for j, c in enumerate(batch)]
            )
        
        # 保存配置
        config = {
            "vector_store_type": "qdrant",
            "collection_name": collection_name,
            "model": self.model,
            "output_dim": self.output_dim,
            "chunk_count": len(chunks)
        }
        
        config_path = output_path / f"{collection_name}_config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Qdrant索引构建完成，配置保存到: {config_path}")
        return str(config_path)
    
    def _build_faiss_index(self, 
                          chunks: List[Dict], 
                          output_path: Path,
                          batch_size: int,
                          collection_name: str) -> str:
        """构建FAISS索引和BM25索引"""
        all_vectors = []
        all_metadatas = []
        
        # 批量处理
        for i in tqdm(range(0, len(chunks), batch_size), desc="构建FAISS索引"):
            batch = chunks[i:i + batch_size]
            texts = [self.build_text(c) for c in batch]
            vectors = self.embed_batch(texts)
            
            all_vectors.extend(vectors)
            all_metadatas.extend(batch)
        
        # 转换为numpy数组
        vectors_array = np.array(all_vectors, dtype=np.float32)
        
        # 添加调试信息
        logger.info(f"vectors_array.shape={vectors_array.shape}, self.output_dim={self.output_dim}")
        
        # 检查向量维度
        if vectors_array.shape[1] != self.output_dim:
            logger.error(f"向量维度不匹配: 实际={vectors_array.shape[1]}, 期望={self.output_dim}")
            raise ValueError(f"向量维度不匹配: 实际={vectors_array.shape[1]}, 期望={self.output_dim}")
        
        # 创建FAISS索引
        index_path = output_path / collection_name
        index_path.mkdir(exist_ok=True)
        
        # 创建并保存FAISS索引
        index = faiss.IndexFlatIP(vectors_array.shape[1])  # 使用实际维度
        index.add(vectors_array)
        faiss.write_index(index, str(index_path / "index.faiss"))
        
        # 保存元数据
        metadata_path = index_path / "metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(all_metadatas, f, ensure_ascii=False, indent=2)
        
        # 构建BM25索引
        logger.info("开始构建BM25索引...")
        try:
            from .bm25_indexer import BM25Indexer
            
            bm25_indexer = BM25Indexer()
            bm25_indexer.build_index(chunks)
            
            # 保存BM25索引
            bm25_path = index_path / "bm25_index.pkl"
            bm25_indexer.save_index(str(bm25_path))
            
            logger.info(f"BM25索引构建完成，保存到: {bm25_path}")
            
        except Exception as e:
            logger.error(f"构建BM25索引失败: {e}")
            bm25_path = None
        
        # 保存配置
        config = {
            "vector_store_type": "faiss",
            "collection_name": collection_name,
            "model": self.model,
            "output_dim": self.output_dim,
            "chunk_count": len(chunks),
            "index_path": str(index_path),
            "bm25_index_path": str(bm25_path) if bm25_path else None,
            "hybrid_search_enabled": bm25_path is not None
        }
        
        config_path = output_path / f"{collection_name}_config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"FAISS索引构建完成，保存到: {index_path}")
        return str(config_path)
    
    def load_vector_store(self, config_path: str):
        """
        加载向量库
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            向量库实例
        """
        # 保存配置文件路径供其他方法使用
        self._config_file_path = config_path
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if config["vector_store_type"] == "qdrant":
            return self._load_qdrant_store(config)
        else:
            return self._load_faiss_store(config)
    
    def _load_qdrant_store(self, config: Dict) -> Any:
        """加载Qdrant存储"""
        if not QDRANT_AVAILABLE:
            raise ImportError("qdrant-client未安装")
        
        client = qdrant_client.QdrantClient(":memory:")
        return client
    
    def _load_faiss_store(self, config: Dict) -> Any:
        """加载FAISS存储"""
        if not FAISS_AVAILABLE:
            raise ImportError("faiss-cpu未安装")
        
        # 获取配置文件所在的目录
        if hasattr(self, '_config_file_path') and self._config_file_path:
            config_dir = Path(self._config_file_path).parent
            index_path = config_dir / Path(config["index_path"]).name
        else:
            # 如果没有配置文件路径，尝试构建绝对路径
            index_path_str = config["index_path"]
            if not Path(index_path_str).is_absolute():
                # 使用当前文件的位置来构建绝对路径
                current_dir = Path(__file__).parent
                index_path = current_dir / "vectorstore" / Path(index_path_str).name
            else:
                index_path = Path(index_path_str)
        
        metadata_path = index_path / "metadata.json"
        
        logger.info(f"尝试加载FAISS存储，索引路径: {index_path}")
        logger.info(f"元数据路径: {metadata_path}")
        
        if not metadata_path.exists():
            logger.error(f"元数据文件不存在: {metadata_path}")
            raise FileNotFoundError(f"元数据文件不存在: {metadata_path}")
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        return {
            "index_path": str(index_path),
            "metadata": metadata,
            "config": config
        }


def process_game_knowledge(game_name: str, 
                          knowledge_dir: str = "data/knowledge_chunk",
                          output_dir: str = "src/game_wiki_tooltip/ai/vectorstore") -> str:
    """
    处理指定游戏的知识库
    
    Args:
        game_name: 游戏名称 (如 "helldiver2")
        knowledge_dir: 知识库目录
        output_dir: 输出目录
        
    Returns:
        向量库配置路径
    """
    json_path = Path(knowledge_dir) / f"{game_name}.json"
    
    if not json_path.exists():
        raise FileNotFoundError(f"找不到知识库文件: {json_path}")
    
    processor = BatchEmbeddingProcessor()
    return processor.process_json_file(
        str(json_path),
        output_dir=output_dir,
        collection_name=f"{game_name}_vectors"
    )


if __name__ == "__main__":
    # 示例用法
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # 处理Helldivers 2知识库
    try:
        config_path = process_game_knowledge("helldiver2")
        print(f"向量库构建完成: {config_path}")
    except Exception as e:
        print(f"处理失败: {e}") 