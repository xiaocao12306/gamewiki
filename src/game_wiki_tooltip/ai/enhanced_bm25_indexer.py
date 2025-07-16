"""
增强BM25索引器 - 针对游戏战术信息优化
=====================================

功能：
1. 敌人特定关键词权重提升
2. 战术术语权重增强  
3. 智能文本预处理
4. 多语言支持（中英文）
"""

import jieba
import json
import pickle
import re
import logging
from rank_bm25 import BM25Okapi
from typing import List, Dict, Any, Optional, Set, Tuple
from pathlib import Path
from .game_keyword_configs import GameKeywordConfig

logger = logging.getLogger(__name__)

class EnhancedBM25Indexer:
    """增强BM25索引器，支持多游戏优化的战术信息检索"""
    
    def __init__(self, game_name: str = "helldiver2", stop_words: Optional[List[str]] = None):
        """
        初始化增强BM25索引器
        
        Args:
            game_name: 游戏名称 (helldiver2, dst, eldenring, civilization6)
            stop_words: 停用词列表
        """
        self.game_name = game_name
        self.bm25 = None
        self.documents = []
        self.stop_words = self._load_stop_words(stop_words)
        
        # 根据游戏加载特定的关键词权重配置
        self._load_game_config()
    
    def _load_game_config(self) -> None:
        """加载游戏特定的关键词配置"""
        try:
            config = GameKeywordConfig.get_config(self.game_name)
            
            # 合并所有关键词权重
            self.keyword_weights = {}
            self.keyword_weights.update(config['common_keywords'])
            self.keyword_weights.update(config['enemy_keywords'])
            self.keyword_weights.update(config['tactical_keywords'])
            self.keyword_weights.update(config['item_keywords'])
            self.keyword_weights.update(config['special_keywords'])
            
            # 保存各类别关键词用于特殊处理
            self.enemy_keywords = config['enemy_keywords']
            self.tactical_keywords = config['tactical_keywords']
            self.item_keywords = config['item_keywords']
            self.special_keywords = config['special_keywords']
            
            logger.info(f"已加载 {self.game_name} 游戏配置，共 {len(self.keyword_weights)} 个关键词")
            
        except Exception as e:
            logger.error(f"加载游戏配置失败: {e}")
            # 降级到空配置
            self.keyword_weights = {}
            self.enemy_keywords = {}
            self.tactical_keywords = {}
            self.item_keywords = {}
            self.special_keywords = {}
        
    def _load_stop_words(self, stop_words: Optional[List[str]] = None) -> Set[str]:
        """加载停用词，但保留重要的战术术语"""
        default_stop_words = {
            # 中文停用词
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这',
            # 英文停用词  
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must', 'shall',
            # 通用游戏词汇（但不包括战术术语）
            'game', 'player', 'mission', 'level'
        }
        
        if stop_words:
            default_stop_words.update(stop_words)
            
        return default_stop_words
        
    def _normalize_enemy_name(self, text: str) -> str:
        """标准化敌人名称 - 基于当前游戏配置"""
        text = text.lower()
        
        # 基于游戏特定的敌人关键词进行标准化
        # 这里我们使用一个通用的方法，不再硬编码特定游戏的映射
        # 可以根据需要在游戏配置中添加别名映射
        
        # 针对Helldivers 2的特殊处理 (保留向后兼容性)
        if self.game_name == "helldiver2":
            enemy_mappings = {
                'bt': 'bile titan',
                'biletitan': 'bile titan',
                'bile_titan': 'bile titan',
                '胆汁泰坦': 'bile titan',
                '巨人机甲': 'hulk',
                'hulk devastator': 'hulk',
                '冲锋者': 'charger',
                '穿刺者': 'impaler',
                '潜行者': 'stalker',
                '族群指挥官': 'brood commander',
                '工厂行者': 'factory strider',
                '毁灭者': 'devastator',
                '狂战士': 'berserker',
                '武装直升机': 'gunship',
                '坦克': 'tank',
                '运输舰': 'dropship',
            }
            
            for original, normalized in enemy_mappings.items():
                text = text.replace(original, normalized)
            
        return text
        
    def preprocess_text(self, text: str) -> List[str]:
        """
        增强文本预处理，重点处理战术信息
        
        Args:
            text: 输入文本
            
        Returns:
            处理后的token列表，包含权重信息
        """
        if not text:
            return []
            
        # 转换为小写并标准化敌人名称
        text = self._normalize_enemy_name(text.lower())
        
        # 移除特殊字符，但保留中文、英文、数字和空格
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', text)
        
        # 中文分词
        tokens = list(jieba.cut(text))
        
        # 处理token并应用权重
        weighted_tokens = []
        for token in tokens:
            token = token.strip()
            
            # 过滤条件：非空、不是停用词、长度>1或者是数字
            if (token and 
                token not in self.stop_words and 
                (len(token) > 1 or token.isdigit())):
                
                # 检查是否是高权重关键词
                weight = self.keyword_weights.get(token, 1.0)
                
                # 根据权重重复token
                repeat_count = int(weight)
                weighted_tokens.extend([token] * repeat_count)
        
        return weighted_tokens
    
    def build_enhanced_text(self, chunk: Dict[str, Any]) -> str:
        """
        构建增强的搜索文本，优化敌人和战术信息
        
        Args:
            chunk: 知识块
            
        Returns:
            增强的搜索文本
        """
        text_parts = []
        
        # 1. Topic (最高权重 - 重复5次)
        topic = chunk.get("topic", "")
        if topic:
            text_parts.extend([topic] * 5)
            
        # 2. 关键词 (高权重 - 重复3次)
        keywords = chunk.get("keywords", [])
        if keywords:
            text_parts.extend(keywords * 3)
            
        # 3. Summary (正常权重)
        summary = chunk.get("summary", "")
        if summary:
            text_parts.append(summary)
            
        # 4. 结构化数据处理
        self._extract_structured_content(chunk, text_parts)
        
        return " ".join(text_parts)
    
    def _extract_structured_content(self, chunk: Dict[str, Any], text_parts: List[str]) -> None:
        """提取结构化内容并添加到文本部分"""
        
        # 敌人弱点信息
        if "structured_data" in chunk:
            structured = chunk["structured_data"]
            
            # 敌人名称 (重复4次)
            if "enemy_name" in structured:
                text_parts.extend([structured["enemy_name"]] * 4)
                
            # 弱点信息 (重复3次)
            if "weak_points" in structured:
                for weak_point in structured["weak_points"]:
                    if "name" in weak_point:
                        text_parts.extend([weak_point["name"]] * 3)
                    if "notes" in weak_point:
                        text_parts.append(weak_point["notes"])
                        
            # 推荐武器 (重复2次)
            if "recommended_weapons" in structured:
                for weapon in structured["recommended_weapons"]:
                    text_parts.extend([weapon] * 2)
                    
        # Build信息
        if "build" in chunk:
            build = chunk["build"]
            
            # Build名称 (重复3次)
            if "name" in build:
                text_parts.extend([build["name"]] * 3)
                
            # 战术焦点 (重复2次)
            if "focus" in build:
                text_parts.extend([build["focus"]] * 2)
                
            # 策略信息
            if "stratagems" in build:
                for stratagem in build["stratagems"]:
                    if "name" in stratagem:
                        text_parts.extend([stratagem["name"]] * 2)
                    if "rationale" in stratagem:
                        text_parts.append(stratagem["rationale"])
    
    def build_index(self, chunks: List[Dict[str, Any]]) -> None:
        """
        构建增强BM25索引
        
        Args:
            chunks: 知识块列表
        """
        logger.info(f"开始构建增强BM25索引，共 {len(chunks)} 个知识块")
        
        self.documents = chunks
        
        # 构建增强搜索文本
        search_texts = []
        for i, chunk in enumerate(chunks):
            try:
                # 构建增强文本
                enhanced_text = self.build_enhanced_text(chunk)
                
                # 预处理和权重化
                tokenized = self.preprocess_text(enhanced_text)
                search_texts.append(tokenized)
                
                # 调试信息
                if i < 3:  # 只打印前3个用于调试
                    logger.info(f"样本 {i}: {chunk.get('topic', 'Unknown')}")
                    logger.info(f"增强文本: {enhanced_text[:200]}...")
                    logger.info(f"Token样本: {tokenized[:10]}")
                    logger.info(f"Token总数: {len(tokenized)}")
                
            except Exception as e:
                logger.error(f"处理第 {i} 个知识块时出错: {e}")
                search_texts.append([])
        
        # 创建BM25索引
        try:
            self.bm25 = BM25Okapi(search_texts)
            logger.info("增强BM25索引构建完成")
        except Exception as e:
            logger.error(f"增强BM25索引构建失败: {e}")
            raise
    
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        增强BM25搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        if not self.bm25:
            logger.warning("增强BM25索引未初始化")
            return []
            
        # 预处理查询
        normalized_query = self._normalize_enemy_name(query.lower())
        tokenized_query = self.preprocess_text(normalized_query)
        
        if not tokenized_query:
            logger.warning("查询预处理后为空")
            return []
        
        print(f"🔍 [BM25-DEBUG] 增强BM25搜索 - 原始查询: {query}")
        print(f"   📝 [BM25-DEBUG] 标准化查询: {normalized_query}")
        print(f"   🔤 [BM25-DEBUG] 权重化分词: {tokenized_query}")
        logger.info(f"增强BM25搜索 - 原始查询: {query}")
        logger.info(f"标准化查询: {normalized_query}")
        logger.info(f"权重化分词: {tokenized_query}")
        
        # 获取分数
        scores = self.bm25.get_scores(tokenized_query)
        print(f"   📊 [BM25-DEBUG] 所有文档分数范围: {scores.min():.4f} - {scores.max():.4f}")
        
        # 获取top_k结果
        top_indices = scores.argsort()[-top_k:][::-1]
        print(f"   📋 [BM25-DEBUG] Top {top_k} 索引: {top_indices}")
        print(f"   📋 [BM25-DEBUG] 对应分数: {scores[top_indices]}")
        
        results = []
        for i, idx in enumerate(top_indices):
            score = scores[idx]
            if score > 0:
                chunk = self.documents[idx]
                match_info = {
                    "topic": chunk.get("topic", ""),
                    "enemy": self._extract_enemy_from_chunk(chunk),
                    "relevance_reason": self._explain_relevance(tokenized_query, chunk)
                }
                result = {
                    "chunk": chunk,
                    "score": float(score),
                    "rank": i + 1,
                    "match_info": match_info
                }
                results.append(result)
                
                # 详细的匹配调试信息
                print(f"   📋 [BM25-DEBUG] 结果 {i+1}:")
                print(f"      - 索引: {idx}")
                print(f"      - 分数: {score:.4f}")
                print(f"      - 主题: {chunk.get('topic', 'Unknown')}")
                print(f"      - 敌人: {match_info['enemy']}")
                print(f"      - 匹配理由: {match_info['relevance_reason']}")
                print(f"      - 摘要: {chunk.get('summary', '')[:100]}...")
                
                # 显示关键词权重匹配信息
                chunk_text = self.build_enhanced_text(chunk).lower()
                matched_keywords = []
                for token in set(tokenized_query):
                    if token in chunk_text:
                        weight = self.keyword_weights.get(token, 1.0)
                        if weight > 1.0:
                            matched_keywords.append(f"{token}({weight}x)")
                        else:
                            matched_keywords.append(token)
                if matched_keywords:
                    print(f"      - 匹配关键词: {', '.join(matched_keywords[:10])}")
        
        print(f"✅ [BM25-DEBUG] 增强BM25搜索完成，找到 {len(results)} 个结果")
        logger.info(f"增强BM25搜索完成，找到 {len(results)} 个结果")
        return results
    
    def _extract_enemy_from_chunk(self, chunk: Dict[str, Any]) -> str:
        """从chunk中提取敌人/目标名称 - 基于游戏类型"""
        # 检查结构化数据
        if "structured_data" in chunk and "enemy_name" in chunk["structured_data"]:
            return chunk["structured_data"]["enemy_name"]
            
        # 检查topic中的敌人关键词
        topic = chunk.get("topic", "").lower()
        for enemy in self.enemy_keywords:
            if enemy in topic:
                return enemy.title()
        
        # 对于不同游戏类型，查找不同的目标类型
        if self.game_name == "dst":
            # DST: 查找Boss、生物或角色名
            for special in self.special_keywords:
                if special in topic:
                    return special.title()
        elif self.game_name == "eldenring":
            # Elden Ring: 查找Boss名称
            for enemy in self.enemy_keywords:
                if enemy in topic:
                    return enemy.title()
        elif self.game_name == "civilization6":
            # Civilization 6: 查找文明名称
            for civ in self.special_keywords:
                if civ in topic:
                    return civ.title()
                
        return "Unknown"
    
    def _explain_relevance(self, query_tokens: List[str], chunk: Dict[str, Any]) -> str:
        """解释匹配相关性"""
        chunk_text = self.build_enhanced_text(chunk).lower()
        
        matched_terms = []
        for token in set(query_tokens):  # 去重
            if token in chunk_text:
                if token in self.keyword_weights:
                    matched_terms.append(f"{token}(权重:{self.keyword_weights[token]})")
                else:
                    matched_terms.append(token)
        
        return f"匹配: {', '.join(matched_terms[:5])}"  # 限制显示数量
    
    def save_index(self, path: str) -> None:
        """保存增强BM25索引"""
        try:
            data = {
                'bm25': self.bm25,
                'documents': self.documents,
                'stop_words': list(self.stop_words),
                'keyword_weights': self.keyword_weights
            }
            
            with open(path, 'wb') as f:
                pickle.dump(data, f)
            
            logger.info(f"增强BM25索引已保存到: {path}")
            
        except Exception as e:
            logger.error(f"保存增强BM25索引失败: {e}")
            raise
    
    def load_index(self, path: str) -> None:
        """加载增强BM25索引"""
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
            
            self.bm25 = data['bm25']
            self.documents = data['documents']
            self.stop_words = set(data.get('stop_words', []))
            self.keyword_weights = data.get('keyword_weights', {})
            
            logger.info(f"增强BM25索引已加载: {path}")
            
        except Exception as e:
            logger.error(f"加载增强BM25索引失败: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """获取增强索引统计信息"""
        if not self.bm25:
            return {"status": "未初始化"}
        
        # 分析敌人分布
        enemy_distribution = {}
        for chunk in self.documents:
            enemy = self._extract_enemy_from_chunk(chunk)
            enemy_distribution[enemy] = enemy_distribution.get(enemy, 0) + 1
        
        # 计算平均文档长度（修复corpus_size访问错误）
        try:
            # BM25Okapi的corpus是文档token列表的列表
            if hasattr(self.bm25, 'corpus') and self.bm25.corpus:
                avg_doc_length = sum(len(doc) for doc in self.bm25.corpus) / len(self.bm25.corpus)
            elif hasattr(self.bm25, 'corpus_size') and isinstance(self.bm25.corpus_size, int):
                # 如果corpus_size是整数，表示文档数量
                avg_doc_length = float(self.bm25.corpus_size)
            else:
                avg_doc_length = 0.0
        except Exception as e:
            logger.warning(f"计算平均文档长度失败: {e}")
            avg_doc_length = 0.0
        
        return {
            "status": "已初始化",
            "document_count": len(self.documents),
            "stop_words_count": len(self.stop_words),
            "keyword_weights_count": len(self.keyword_weights),
            "enemy_distribution": enemy_distribution,
            "average_document_length": avg_doc_length,
            "top_enemies": list(sorted(enemy_distribution.items(), key=lambda x: x[1], reverse=True)[:5])
        }


def test_enhanced_bm25():
    """测试增强BM25索引器 - 多游戏支持"""
    
    # Helldivers 2 测试数据
    helldivers_chunks = [
        {
            "chunk_id": "bile_titan_test",
            "topic": "Terminid: Bile Titan Weaknesses",
            "summary": "This guide details how to kill a Bile Titan. Its head is a critical weak point (1500 HP, Class 4 Armor) that can be one-shot by anti-tank launchers for an instant kill.",
            "keywords": ["Bile Titan", "Terminid", "boss weakness", "anti-tank", "headshot"],
            "structured_data": {
                "enemy_name": "Bile Titan",
                "faction": "Terminid",
                "weak_points": [
                    {
                        "name": "Head/Face",
                        "health": 1500,
                        "notes": "Instant kill if destroyed. Ideal target for anti-tank launchers."
                    }
                ],
                "recommended_weapons": ["EAT", "Recoilless Rifle", "Quasar Cannon"]
            }
        }
    ]
    
    # DST 测试数据
    dst_chunks = [
        {
            "chunk_id": "dst_winter_test",
            "topic": "Winter Survival: Managing Temperature and Deerclops",
            "summary": "Surviving winter requires thermal stone management and preparing for Deerclops boss fight around day 30.",
            "keywords": ["winter", "temperature", "deerclops", "boss", "thermal stone"],
            "data": {
                "season": "Winter",
                "boss_name": "Deerclops",
                "key_items": ["Thermal Stone", "Winter Hat", "Fire Pit"]
            }
        }
    ]
    
    # Elden Ring 测试数据
    eldenring_chunks = [
        {
            "chunk_id": "malenia_test",
            "topic": "Malenia Boss Strategy: Waterfowl Dance Counter",
            "summary": "Malenia's waterfowl dance can be dodged by running away during the first flurry, then dodging through the second and third attacks.",
            "keywords": ["Malenia", "waterfowl dance", "boss strategy", "dodge", "timing"],
            "structured_data": {
                "boss_name": "Malenia",
                "difficulty": "Very Hard",
                "key_attacks": ["Waterfowl Dance", "Scarlet Rot"]
            }
        }
    ]
    
    # 测试不同游戏的索引器
    test_cases = [
        ("helldiver2", helldivers_chunks, ["how to kill bile titan", "anti-tank weapons"]),
        ("dst", dst_chunks, ["winter survival", "deerclops strategy"]),
        ("eldenring", eldenring_chunks, ["malenia boss fight", "waterfowl dance counter"])
    ]
    
    print("=== 多游戏增强BM25索引器测试 ===\n")
    
    for game_name, chunks, queries in test_cases:
        print(f"🎮 测试游戏: {game_name.upper()}")
        print(f"📚 知识块数量: {len(chunks)}")
        
        # 创建游戏特定的索引器
        indexer = EnhancedBM25Indexer(game_name=game_name)
        
        # 构建索引
        indexer.build_index(chunks)
        
        # 显示统计信息
        stats = indexer.get_stats()
        print(f"📊 索引统计: 文档数={stats['document_count']}, 关键词数={stats['keyword_weights_count']}")
        
        # 测试查询
        for query in queries:
            print(f"\n🔍 查询: {query}")
            results = indexer.search(query, top_k=2)
            for i, result in enumerate(results, 1):
                print(f"   {i}. 分数={result['score']:.3f} | {result['chunk']['topic']}")
                print(f"      相关性: {result['match_info']['relevance_reason']}")
        
        print("\n" + "="*50 + "\n")


if __name__ == "__main__":
    test_enhanced_bm25() 