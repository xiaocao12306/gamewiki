"""
BM25索引器模块
==============

功能：
1. 中文文本预处理和分词
2. 构建BM25索引
3. 执行关键词匹配搜索
4. 索引的保存和加载
"""

import jieba
import json
import pickle
import re
import logging
from rank_bm25 import BM25Okapi
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)

class BM25Indexer:
    """BM25索引器，支持中文文本处理"""
    
    def __init__(self, stop_words: Optional[List[str]] = None):
        """
        初始化BM25索引器
        
        Args:
            stop_words: 停用词列表
        """
        self.bm25 = None
        self.documents = []
        self.stop_words = self._load_stop_words(stop_words)
        
    def _load_stop_words(self, stop_words: Optional[List[str]] = None) -> Set[str]:
        """加载停用词"""
        default_stop_words = {
            # 中文停用词
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这',
            # 英文停用词
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must', 'shall',
            # 游戏常见停用词
            '游戏', '玩家', '角色', '技能', '装备', '武器', '道具', '等级', '经验', '任务', '副本', 'boss', '怪物', '攻略', '指南', '教程', '技巧', '方法', '策略', '建议', '推荐'
        }
        
        if stop_words:
            default_stop_words.update(stop_words)
            
        return default_stop_words
        
    def preprocess_text(self, text: str) -> List[str]:
        """
        中文文本预处理
        
        Args:
            text: 输入文本
            
        Returns:
            处理后的token列表
        """
        if not text:
            return []
            
        # 转换为小写
        text = text.lower()
        
        # 移除特殊字符，但保留中文、英文、数字和空格
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', text)
        
        # 中文分词
        tokens = list(jieba.cut(text))
        
        # 过滤处理
        filtered_tokens = []
        for token in tokens:
            token = token.strip()
            # 过滤条件：非空、不是停用词、长度>1或者是数字
            if (token and 
                token not in self.stop_words and 
                (len(token) > 1 or token.isdigit())):
                filtered_tokens.append(token)
        
        return filtered_tokens
    
    def build_index(self, chunks: List[Dict[str, Any]]) -> None:
        """
        构建BM25索引
        
        Args:
            chunks: 知识块列表
        """
        logger.info(f"开始构建BM25索引，共 {len(chunks)} 个知识块")
        
        self.documents = chunks
        
        # 构建搜索文本（合并topic、summary、keywords）
        search_texts = []
        for i, chunk in enumerate(chunks):
            try:
                text_parts = []
                
                # 添加topic（权重最高）
                topic = chunk.get("topic", "")
                if topic:
                    text_parts.extend([topic] * 3)  # 重复3次增加权重
                
                # 添加summary
                summary = chunk.get("summary", "")
                if summary:
                    text_parts.append(summary)
                
                # 添加keywords
                keywords = chunk.get("keywords", [])
                if keywords:
                    # keywords重复2次增加权重
                    text_parts.extend(keywords * 2)
                
                # 如果有build信息，添加配装相关内容
                if "build" in chunk:
                    build = chunk["build"]
                    if "name" in build:
                        text_parts.extend([build["name"]] * 2)
                    if "focus" in build:
                        text_parts.append(build["focus"])
                    if "stratagems" in build:
                        for stratagem in build["stratagems"]:
                            if "name" in stratagem:
                                text_parts.append(stratagem["name"])
                
                # 合并文本并分词
                search_text = " ".join(text_parts)
                tokenized = self.preprocess_text(search_text)
                search_texts.append(tokenized)
                
            except Exception as e:
                logger.error(f"处理第 {i} 个知识块时出错: {e}")
                search_texts.append([])  # 添加空列表作为占位符
        
        # 创建BM25索引
        try:
            self.bm25 = BM25Okapi(search_texts)
            logger.info("BM25索引构建完成")
        except Exception as e:
            logger.error(f"BM25索引构建失败: {e}")
            raise
    
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        BM25搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        if not self.bm25:
            logger.warning("BM25索引未初始化")
            return []
            
        # 预处理查询
        tokenized_query = self.preprocess_text(query)
        if not tokenized_query:
            logger.warning("查询预处理后为空")
            return []
        
        logger.info(f"BM25搜索查询: {query}")
        logger.info(f"分词结果: {tokenized_query}")
        
        # 获取分数
        scores = self.bm25.get_scores(tokenized_query)
        
        # 获取top_k结果
        top_indices = scores.argsort()[-top_k:][::-1]
        
        results = []
        for i, idx in enumerate(top_indices):
            score = scores[idx]
            if score > 0:  # 只返回有分数的结果
                results.append({
                    "chunk": self.documents[idx],
                    "score": float(score),
                    "rank": i + 1
                })
        
        logger.info(f"BM25搜索完成，找到 {len(results)} 个结果")
        return results
    
    def save_index(self, path: str) -> None:
        """
        保存BM25索引
        
        Args:
            path: 保存路径
        """
        try:
            data = {
                'bm25': self.bm25,
                'documents': self.documents,
                'stop_words': list(self.stop_words)
            }
            
            with open(path, 'wb') as f:
                pickle.dump(data, f)
            
            logger.info(f"BM25索引已保存到: {path}")
            
        except Exception as e:
            logger.error(f"保存BM25索引失败: {e}")
            raise
    
    def load_index(self, path: str) -> None:
        """
        加载BM25索引
        
        Args:
            path: 索引文件路径
        """
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
            
            self.bm25 = data['bm25']
            self.documents = data['documents']
            if 'stop_words' in data:
                self.stop_words = set(data['stop_words'])
            
            logger.info(f"BM25索引已加载: {path}")
            
        except Exception as e:
            logger.error(f"加载BM25索引失败: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取索引统计信息
        
        Returns:
            统计信息字典
        """
        if not self.bm25:
            return {"status": "未初始化"}
        
        return {
            "status": "已初始化",
            "document_count": len(self.documents),
            "stop_words_count": len(self.stop_words),
            "average_document_length": sum(len(doc) for doc in self.bm25.corpus_size) / len(self.bm25.corpus_size) if self.bm25.corpus_size else 0
        }


def test_bm25_indexer():
    """测试BM25索引器"""
    # 测试数据
    test_chunks = [
        {
            "chunk_id": "test_001",
            "topic": "地狱潜兵2 虫族配装推荐",
            "summary": "针对虫族敌人的最佳武器配装建议，包括火焰武器和爆炸武器的使用技巧",
            "keywords": ["虫族", "配装", "火焰", "爆炸", "武器"],
            "build": {
                "name": "虫族克星配装",
                "focus": "高效清理虫族群体",
                "stratagems": [
                    {"name": "火焰喷射器"},
                    {"name": "集束炸弹"}
                ]
            }
        },
        {
            "chunk_id": "test_002",
            "topic": "机甲族对抗策略",
            "summary": "如何有效对抗机甲族敌人，推荐使用反装甲武器和EMP设备",
            "keywords": ["机甲族", "反装甲", "EMP", "策略"],
            "build": {
                "name": "反装甲配装",
                "focus": "专门对抗重装甲敌人"
            }
        }
    ]
    
    # 创建索引器
    indexer = BM25Indexer()
    
    # 构建索引
    indexer.build_index(test_chunks)
    
    # 测试搜索
    print("=== BM25索引器测试 ===")
    print(f"索引统计: {indexer.get_stats()}")
    
    # 测试查询
    test_queries = [
        "虫族配装",
        "火焰武器",
        "机甲族对抗",
        "反装甲武器"
    ]
    
    for query in test_queries:
        print(f"\n查询: {query}")
        results = indexer.search(query, top_k=3)
        for result in results:
            print(f"  - 分数: {result['score']:.3f}, 主题: {result['chunk']['topic']}")


if __name__ == "__main__":
    test_bm25_indexer() 