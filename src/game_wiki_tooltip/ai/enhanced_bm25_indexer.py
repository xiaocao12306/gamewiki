"""
简化BM25索引器 - 专注于高效检索
=================================

功能：
1. 智能文本预处理
2. 多语言支持（中英文）
3. 简化的BM25检索
4. 由LLM负责查询优化
"""

import jieba
import json
import pickle
import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from pathlib import Path

# 导入翻译函数
from src.game_wiki_tooltip.i18n import t

# 尝试导入bm25s，更现代、更快的BM25实现
try:
    import bm25s
    BM25_AVAILABLE = True
    BM25_IMPORT_ERROR = None
except ImportError as e:
    BM25_AVAILABLE = False
    bm25s = None
    BM25_IMPORT_ERROR = str(e)

logger = logging.getLogger(__name__)

class BM25UnavailableError(Exception):
    """BM25功能不可用错误"""
    pass

class EnhancedBM25Indexer:
    """简化BM25索引器，专注于高效检索，查询优化由LLM负责"""
    
    def __init__(self, game_name: str = "helldiver2", stop_words: Optional[List[str]] = None):
        """
        初始化简化BM25索引器
        
        Args:
            game_name: 游戏名称 (用于敌人名称标准化)
            stop_words: 停用词列表
            
        Raises:
            BM25UnavailableError: 当bm25s包不可用时
        """
        self.game_name = game_name
        self.bm25 = None
        self.documents = []
        
        if not BM25_AVAILABLE:
            error_msg = t("bm25_package_unavailable", error=BM25_IMPORT_ERROR)
            error_msg += "\n请尝试以下解决方案："
            error_msg += "\n1. 安装bm25s: pip install bm25s"
            error_msg += "\n2. 如果仍有问题，尝试重新安装: pip uninstall bm25s && pip install bm25s"
            error_msg += "\n3. 确保numpy和scipy已正确安装: pip install numpy scipy"
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)
            
        self.stop_words = self._load_stop_words(stop_words)
        logger.info(f"BM25索引器初始化成功 - 游戏: {game_name}")

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
        简化的文本预处理，专注于高效分词
        移除复杂的权重逻辑，由LLM负责查询优化
        
        Args:
            text: 输入文本
            
        Returns:
            处理后的token列表
        """
        if not text:
            return []
            
        # 转换为小写并标准化敌人名称
        text = self._normalize_enemy_name(text.lower())
        
        # 移除特殊字符，但保留中文、英文、数字和空格
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', text)
        
        # 检测是否包含中文
        has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', text))
        
        # 分词处理
        if has_chinese:
            # 包含中文，使用jieba分词
            tokens = list(jieba.cut(text))
        else:
            # 纯英文，使用空格分词（更准确）
            tokens = text.split()
        
        # 简单的英文词干提取
        def simple_stem(word):
            """简单的词干提取，处理常见的英文变形"""
            if len(word) <= 2:
                return word
                
            # 处理复数形式
            if word.endswith('s') and len(word) > 3:
                # 特殊复数形式
                if word.endswith('ies') and len(word) > 4:
                    return word[:-3] + 'y'  # strategies -> strategy
                elif word.endswith('es') and len(word) > 4:
                    return word[:-2]  # boxes -> box
                else:
                    return word[:-1]  # recommendations -> recommendation
                    
            # 处理其他常见后缀
            if word.endswith('ing') and len(word) > 5:
                return word[:-3]  # running -> run
            if word.endswith('ed') and len(word) > 4:
                return word[:-2]  # played -> play
            if word.endswith('ly') and len(word) > 4:
                return word[:-2]  # quickly -> quick
                
            return word
        
        # 处理token - 简化版本
        processed_tokens = []
        for token in tokens:
            token = token.strip()
            
            # 过滤条件：非空、不是停用词、长度>1或者是数字
            if (token and 
                token not in self.stop_words and 
                (len(token) > 1 or token.isdigit())):
                
                # 对英文单词应用词干提取
                if not re.search(r'[\u4e00-\u9fa5]', token):  # 非中文
                    stemmed = simple_stem(token)
                    processed_tokens.append(stemmed)
                    
                    # 如果词干与原词不同，也添加原词
                    if stemmed != token:
                        processed_tokens.append(token)
                else:
                    # 中文词汇直接处理
                    processed_tokens.append(token)
        
        return processed_tokens
    
    def build_enhanced_text(self, chunk: Dict[str, Any]) -> str:
        """
        构建搜索文本，专注于内容提取
        移除权重逻辑，由LLM负责查询优化
        
        Args:
            chunk: 知识块
            
        Returns:
            搜索文本
        """
        text_parts = []
        
        # 1. Topic（重要内容）
        topic = chunk.get("topic", "")
        if topic:
            text_parts.append(topic)
            
        # 2. 关键词
        keywords = chunk.get("keywords", [])
        if keywords:
            text_parts.extend(keywords)
            
        # 3. Summary
        summary = chunk.get("summary", "")
        if summary:
            text_parts.append(summary)
            
        # 4. 结构化数据处理
        self._extract_structured_content(chunk, text_parts)
        
        return " ".join(text_parts)
    
    def _extract_structured_content(self, chunk: Dict[str, Any], text_parts: List[str]) -> None:
        """提取结构化内容，专注于内容而非权重"""
        
        # 敌人弱点信息
        if "structured_data" in chunk:
            structured = chunk["structured_data"]
            
            # 敌人名称
            if "enemy_name" in structured:
                text_parts.append(structured["enemy_name"])
                
            # 弱点信息
            if "weak_points" in structured:
                for weak_point in structured["weak_points"]:
                    if "name" in weak_point:
                        text_parts.append(weak_point["name"])
                    if "notes" in weak_point:
                        text_parts.append(weak_point["notes"])
                        
            # 推荐武器
            if "recommended_weapons" in structured:
                for weapon in structured["recommended_weapons"]:
                    text_parts.append(weapon)
                    
        # Build信息
        if "build" in chunk:
            build = chunk["build"]
            
            # Build名称
            if "name" in build:
                text_parts.append(build["name"])
                
            # 战术焦点
            if "focus" in build:
                text_parts.append(build["focus"])
                
            # 策略信息
            if "stratagems" in build:
                for stratagem in build["stratagems"]:
                    if "name" in stratagem:
                        text_parts.append(stratagem["name"])
                    if "rationale" in stratagem:
                        text_parts.append(stratagem["rationale"])
    
    def build_index(self, chunks: List[Dict[str, Any]]) -> None:
        """
        构建增强BM25索引
        
        Args:
            chunks: 知识块列表
            
        Raises:
            BM25UnavailableError: 当BM25功能不可用时
        """
        if not BM25_AVAILABLE:
            raise BM25UnavailableError(t("bm25_build_failed"))
            
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
            self.bm25 = bm25s.BM25()
            self.bm25.index(search_texts)
            # 保存原始文档以便后续使用
            self.corpus_tokens = search_texts
            logger.info("增强BM25索引构建完成")
        except Exception as e:
            error_msg = t("bm25_build_error", error=str(e))
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        增强BM25搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            搜索结果列表
            
        Raises:
            BM25UnavailableError: 当BM25功能不可用时
        """
        if not BM25_AVAILABLE:
            raise BM25UnavailableError(t("bm25_search_failed"))
            
        if not self.bm25:
            raise BM25UnavailableError(t("bm25_search_not_initialized"))
            
        # 预处理查询 - 使用与索引构建相同的逻辑
        normalized_query = self._normalize_enemy_name(query.lower())
        tokenized_query = self.preprocess_text(normalized_query)
        
        if not tokenized_query:
            logger.warning("查询预处理后为空")
            return []
        
        print(f"🔍 [BM25-DEBUG] 简化BM25搜索 - 原始查询: {query}")
        print(f"   📝 [BM25-DEBUG] 标准化查询: {normalized_query}")
        print(f"   🔤 [BM25-DEBUG] 分词结果: {tokenized_query}")
        logger.info(f"简化BM25搜索 - 原始查询: {query}")
        logger.info(f"标准化查询: {normalized_query}")
        logger.info(f"分词结果: {tokenized_query}")
        
        try:
            # 使用bm25s的retrieve方法
            results_ids, scores = self.bm25.retrieve(tokenized_query, k=top_k)
            # results_ids shape: (1, top_k), scores shape: (1, top_k)
            top_indices = results_ids[0]  # 获取第一个查询的结果
            top_scores = scores[0]  # 获取第一个查询的分数
            
            print(f"   📊 [BM25-DEBUG] Top {len(top_scores)} 结果分数: {top_scores}")
            print(f"   📋 [BM25-DEBUG] Top {top_k} 索引: {top_indices}")
            print(f"   📋 [BM25-DEBUG] 对应分数: {top_scores}")
            
            results = []
            for i, idx in enumerate(top_indices):
                score = top_scores[i]  # 使用已排序的分数
                if score > 0:
                    chunk = self.documents[idx]
                    match_info = {
                        "topic": chunk.get("topic", ""),
                        "enemy": self._extract_enemy_from_chunk(chunk),
                        "relevance_reason": self._explain_relevance(tokenized_query, chunk, original_query=query)
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
                    
                    # 显示关键词匹配信息
                    chunk_text = self.build_enhanced_text(chunk).lower()
                    matched_keywords = []
                    for token in set(tokenized_query):
                        if token in chunk_text:
                            matched_keywords.append(token)
                    if matched_keywords:
                        print(f"      - 匹配关键词: {', '.join(matched_keywords[:10])}")
            
            print(f"✅ [BM25-DEBUG] 增强BM25搜索完成，找到 {len(results)} 个结果")
            logger.info(f"增强BM25搜索完成，找到 {len(results)} 个结果")
            return results
            
        except Exception as e:
            error_msg = t("bm25_search_execution_failed", error=str(e))
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)
    
    def _extract_enemy_from_chunk(self, chunk: Dict[str, Any]) -> str:
        """从chunk中提取敌人/目标名称"""
        # 检查结构化数据
        if "structured_data" in chunk and "enemy_name" in chunk["structured_data"]:
            return chunk["structured_data"]["enemy_name"]
            
        # 简单提取：从topic中查找可能的敌人名称
        topic = chunk.get("topic", "")
        
        # 基本的敌人/目标识别关键词
        target_indicators = ["enemy", "boss", "敌人", "首领", "怪物", "对手"]
        if any(indicator in topic.lower() for indicator in target_indicators):
            # 提取topic中的主要词汇作为目标名称
            words = topic.split()
            if len(words) >= 2:
                # 取前两个词作为目标名称
                return " ".join(words[:2])
        
        # 如果没有明确的敌人标识，返回通用标识
        return "Target"
    
    def _explain_relevance(self, query_tokens: List[str], chunk: Dict[str, Any], original_query: str = None) -> str:
        """解释匹配相关性，专注于词汇匹配而非权重"""
        chunk_text = self.build_enhanced_text(chunk).lower()
        
        matched_terms = []
        original_terms = []
        
        # 如果有原始查询，分析原始查询词的匹配情况
        if original_query:
            original_tokens = original_query.lower().split()
            for token in original_tokens:
                # 检查原始词和词干形式的匹配
                if token in chunk_text:
                    original_terms.append(token)
                else:
                    # 检查词干匹配
                    # 简单词干提取逻辑（与preprocess_text中的一致）
                    if token.endswith('s') and len(token) > 3:
                        stemmed = token[:-1]
                        if stemmed in chunk_text:
                            original_terms.append(f"{token}->{stemmed}")
        
        # 分析处理后的token匹配
        for token in set(query_tokens):  # 去重
            if token in chunk_text:
                matched_terms.append(token)
        
        # 构建匹配说明
        if original_terms and matched_terms:
            return f"匹配: {', '.join(original_terms[:3])} | 处理后: {', '.join(matched_terms[:3])}"
        elif matched_terms:
            return f"匹配: {', '.join(matched_terms[:5])}"
        elif original_terms:
            return f"匹配: {', '.join(original_terms[:5])}"
        else:
            return "无明显匹配"
    
    def save_index(self, path: str) -> None:
        """
        保存简化BM25索引
        
        Raises:
            BM25UnavailableError: 当BM25功能不可用时
        """
        if not BM25_AVAILABLE:
            raise BM25UnavailableError(t("bm25_save_not_available"))
            
        try:
            # 使用bm25s的保存方法
            path_obj = Path(path)
            bm25_dir = path_obj.parent / f"{path_obj.stem}_bm25s"
            
            # 保存BM25索引
            self.bm25.save(str(bm25_dir))
            
            # 保存附加数据（文档和停用词）
            additional_data = {
                'documents': self.documents,
                'stop_words': list(self.stop_words),
                'corpus_tokens': getattr(self, 'corpus_tokens', [])
            }
            
            with open(path, 'wb') as f:
                pickle.dump(additional_data, f)
            
            logger.info(f"简化BM25索引已保存到: {path} (BM25数据: {bm25_dir})")
            
        except Exception as e:
            error_msg = t("bm25_save_failed", error=str(e))
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)
    
    def load_index(self, path: str) -> None:
        """
        加载简化BM25索引
        
        Raises:
            BM25UnavailableError: 当BM25功能不可用时
        """
        if not BM25_AVAILABLE:
            error_msg = t("bm25_package_unavailable", error=BM25_IMPORT_ERROR)
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)
            
        try:
            # 加载附加数据
            with open(path, 'rb') as f:
                data = pickle.load(f)
                
            self.documents = data['documents']
            self.stop_words = set(data.get('stop_words', []))
            self.corpus_tokens = data.get('corpus_tokens', [])
            
            # 加载BM25索引
            path_obj = Path(path)
            bm25_dir = path_obj.parent / f"{path_obj.stem}_bm25s"
            
            if bm25_dir.exists():
                self.bm25 = bm25s.BM25.load(str(bm25_dir))
            else:
                # 如果bm25s目录不存在，尝试重建索引
                logger.warning(f"BM25索引目录不存在: {bm25_dir}，尝试重建索引")
                if self.corpus_tokens:
                    self.bm25 = bm25s.BM25()
                    self.bm25.index(self.corpus_tokens)
                else:
                    raise FileNotFoundError(t("bm25_index_missing", path=str(bm25_dir)))
            
            logger.info(f"简化BM25索引已加载: {path}")
            
        except Exception as e:
            error_msg = t("bm25_load_failed", error=str(e))
            logger.error(error_msg)
            raise BM25UnavailableError(error_msg)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取增强索引统计信息
        
        Raises:
            BM25UnavailableError: 当BM25功能不可用时
        """
        if not BM25_AVAILABLE:
            raise BM25UnavailableError(t("bm25_stats_failed"))
            
        if not self.bm25:
            return {"status": "未初始化", "error": "BM25索引未构建"}
        
        # 分析敌人分布
        enemy_distribution = {}
        for chunk in self.documents:
            enemy = self._extract_enemy_from_chunk(chunk)
            enemy_distribution[enemy] = enemy_distribution.get(enemy, 0) + 1
        
        # 计算平均文档长度（修复corpus_size访问错误）
        try:
            # bm25s的corpus是文档token列表的列表
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
        print(f"📊 索引统计: 文档数={stats['document_count']}, 停用词数={stats['stop_words_count']}")
        
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