"""
意图感知的重排序器
===================

解决语义相似度与用户意图不匹配的问题。
通过分析用户查询意图，对检索结果进行重新排序，
确保最符合用户需求的内容排在前面。

主要功能：
1. 意图类型识别（推荐、解释、攻略、比较等）
2. 基于意图的结果重排序
3. 结合语义相似度和意图匹配度的综合评分
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """查询意图类型"""
    RECOMMENDATION = "recommendation"  # 推荐类：选择、下一个、哪个好
    EXPLANATION = "explanation"        # 解释类：是什么、怎么用
    STRATEGY = "strategy"             # 攻略类：怎么打、如何通关
    COMPARISON = "comparison"         # 比较类：哪个更好、区别
    LOCATION = "location"             # 位置类：在哪里、怎么去
    BUILD = "build"                   # 配装类：配装推荐、装备搭配
    UNLOCK = "unlock"                 # 解锁类：如何解锁、解锁条件
    GENERAL = "general"               # 通用查询


@dataclass
class IntentPattern:
    """意图识别模式"""
    intent: QueryIntent
    keywords: List[str]  # 关键词列表
    patterns: List[str]  # 正则表达式模式
    weight: float = 1.0  # 意图权重


class IntentAwareReranker:
    """意图感知的重排序器"""
    
    def __init__(self):
        """初始化重排序器"""
        self.intent_patterns = self._initialize_intent_patterns()
        self.chunk_type_mapping = self._initialize_chunk_type_mapping()
        
    def _initialize_intent_patterns(self) -> List[IntentPattern]:
        """初始化意图识别模式"""
        return [
            # 推荐类意图
            IntentPattern(
                intent=QueryIntent.RECOMMENDATION,
                keywords=["推荐", "选择", "选哪个", "下一个", "下个", "应该", "最好", "最强", "recommend", "choice", "next", "should", "best", "which"],
                patterns=[
                    r"(推荐|建议).*(选择|选哪个)",
                    r"下[一个]?.*选",
                    r"(解锁|买)了.*下[一个]?",
                    r"which.*next",
                    r"what.*after",
                    r"recommend.*after"
                ],
                weight=1.5
            ),
            
            # 解释类意图
            IntentPattern(
                intent=QueryIntent.EXPLANATION,
                keywords=["是什么", "什么是", "介绍", "explain", "what is", "introduction"],
                patterns=[
                    r".*是什么",
                    r"什么是.*",
                    r"介绍一下.*",
                    r"what\s+is\s+",
                    r"explain\s+"
                ],
                weight=1.2
            ),
            
            # 攻略类意图
            IntentPattern(
                intent=QueryIntent.STRATEGY,
                keywords=["怎么打", "如何击败", "攻略", "打法", "strategy", "how to beat", "defeat"],
                patterns=[
                    r"(怎么|如何).*(打|击败|通关)",
                    r".*攻略",
                    r"how\s+to\s+(beat|defeat)",
                    r"strategy\s+for"
                ],
                weight=1.3
            ),
            
            # 比较类意图
            IntentPattern(
                intent=QueryIntent.COMPARISON,
                keywords=["哪个好", "哪个更", "对比", "比较", "区别", "which better", "compare", "difference", "vs"],
                patterns=[
                    r"哪个.*(好|强|优)",
                    r".*对比|比较",
                    r".*区别",
                    r"which.*better",
                    r".*vs\.*",
                    r"compare\s+"
                ],
                weight=1.4
            ),
            
            # 配装类意图
            IntentPattern(
                intent=QueryIntent.BUILD,
                keywords=["配装", "装备", "搭配", "build", "loadout", "equipment"],
                patterns=[
                    r".*配装",
                    r"装备.*搭配",
                    r".*build",
                    r"loadout\s+for"
                ],
                weight=1.3
            ),
            
            # 解锁类意图
            IntentPattern(
                intent=QueryIntent.UNLOCK,
                keywords=["解锁", "获得", "获取", "unlock", "obtain", "get"],
                patterns=[
                    r"(如何|怎么).*(解锁|获得)",
                    r".*解锁条件",
                    r"how\s+to\s+(unlock|get|obtain)",
                    r"unlock\s+requirements?"
                ],
                weight=1.2
            )
        ]
    
    def _initialize_chunk_type_mapping(self) -> Dict[QueryIntent, List[str]]:
        """初始化知识块类型与意图的映射关系"""
        return {
            QueryIntent.RECOMMENDATION: [
                "recommendation", "warbond recommendation", "build recommendation", 
                "weapon recommendation", "priority", "tier list", "best choice"
            ],
            QueryIntent.EXPLANATION: [
                "explanation", "introduction", "overview", "basic info", 
                "what is", "description", "guide introduction"
            ],
            QueryIntent.STRATEGY: [
                "strategy", "tactics", "boss guide", "enemy guide", 
                "how to beat", "walkthrough", "tips"
            ],
            QueryIntent.COMPARISON: [
                "comparison", "versus", "difference", "pros and cons",
                "which is better", "analysis"
            ],
            QueryIntent.BUILD: [
                "build guide", "loadout", "equipment setup", "gear recommendation",
                "build recommendation", "optimal build"
            ],
            QueryIntent.UNLOCK: [
                "unlock guide", "how to unlock", "requirements", "prerequisites",
                "unlock conditions", "acquisition"
            ]
        }
    
    def identify_query_intent(self, query: str) -> Tuple[QueryIntent, float]:
        """
        识别查询意图
        
        Args:
            query: 用户查询
            
        Returns:
            (意图类型, 置信度)
        """
        print(f"🎯 [INTENT-DEBUG] 开始意图识别: query='{query}'")
        
        query_lower = query.lower()
        intent_scores = {}
        
        print(f"   📊 [INTENT-DEBUG] 各意图模式匹配结果:")
        for pattern in self.intent_patterns:
            score = 0.0
            matches = []
            
            # 关键词匹配
            keyword_matches = sum(1 for keyword in pattern.keywords if keyword in query_lower)
            if keyword_matches > 0:
                keyword_score = keyword_matches * 0.3 * pattern.weight
                score += keyword_score
                matches.append(f"关键词匹配: {keyword_matches}个, 得分: {keyword_score:.3f}")
            
            # 正则模式匹配
            for regex_pattern in pattern.patterns:
                if re.search(regex_pattern, query_lower, re.IGNORECASE):
                    regex_score = 0.5 * pattern.weight
                    score += regex_score
                    matches.append(f"正则匹配: '{regex_pattern}', 得分: {regex_score:.3f}")
                    break
            
            if score > 0:
                intent_scores[pattern.intent] = score
                print(f"      {pattern.intent.value}: 总分={score:.3f}")
                for match in matches:
                    print(f"         - {match}")
        
        # 如果没有匹配到任何意图，返回通用意图
        if not intent_scores:
            print(f"   ⚠️ [INTENT-DEBUG] 没有匹配到任何意图，返回通用意图")
            return QueryIntent.GENERAL, 0.5
        
        # 返回得分最高的意图
        best_intent = max(intent_scores.items(), key=lambda x: x[1])
        
        # 归一化置信度到0-1之间
        confidence = min(best_intent[1] / 2.0, 1.0)
        
        print(f"   🏆 [INTENT-DEBUG] 最佳意图: {best_intent[0].value}")
        print(f"      - 原始分数: {best_intent[1]:.3f}")
        print(f"      - 置信度: {confidence:.3f}")
        
        # 显示其他候选意图
        sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_intents) > 1:
            print(f"   📋 [INTENT-DEBUG] 其他候选意图:")
            for i, (intent, score) in enumerate(sorted_intents[1:3], 2):
                print(f"      {i}. {intent.value}: {score:.3f}")
        
        logger.info(f"意图识别: {query} -> {best_intent[0].value} (置信度: {confidence:.2f})")
        return best_intent[0], confidence
    
    def _calculate_intent_relevance(self, chunk: Dict[str, Any], intent: QueryIntent) -> float:
        """
        计算知识块与查询意图的相关度
        
        Args:
            chunk: 知识块
            intent: 查询意图
            
        Returns:
            意图相关度分数 (0-1)
        """
        # 获取chunk的主题和内容
        topic = chunk.get("topic", "").lower()
        summary = chunk.get("summary", "").lower()
        keywords = [kw.lower() for kw in chunk.get("keywords", [])]
        
        # 获取与该意图相关的chunk类型
        relevant_types = self.chunk_type_mapping.get(intent, [])
        
        score = 0.0
        
        # 检查主题是否包含相关类型关键词
        for chunk_type in relevant_types:
            if chunk_type in topic:
                score += 0.5
                break
        
        # 检查关键词匹配
        for chunk_type in relevant_types:
            type_words = chunk_type.split()
            matching_words = sum(1 for word in type_words if any(word in kw for kw in keywords))
            if matching_words > 0:
                score += 0.3 * (matching_words / len(type_words))
        
        # 特殊规则：根据意图类型进行额外判断
        if intent == QueryIntent.RECOMMENDATION:
            # 推荐类意图优先考虑包含"recommendation"、"priority"、"tier"等词的内容
            recommendation_keywords = ["recommendation", "推荐", "priority", "优先", "tier", "best", "top"]
            if any(kw in topic or kw in summary for kw in recommendation_keywords):
                score += 0.4
                
        elif intent == QueryIntent.EXPLANATION:
            # 解释类意图优先考虑包含"explained"、"introduction"等词的内容
            explanation_keywords = ["explained", "解释", "introduction", "介绍", "what is", "overview"]
            if any(kw in topic or kw in summary for kw in explanation_keywords):
                score += 0.3
                
        elif intent == QueryIntent.STRATEGY:
            # 攻略类意图优先考虑包含具体战术的内容
            strategy_keywords = ["guide", "攻略", "strategy", "tactics", "tips", "weak point"]
            if any(kw in topic or kw in summary for kw in strategy_keywords):
                score += 0.3
        
        return min(score, 1.0)
    
    def rerank_results(
        self, 
        results: List[Dict[str, Any]], 
        query: str,
        intent_weight: float = 0.4,
        semantic_weight: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        基于意图重新排序搜索结果
        
        Args:
            results: 原始搜索结果
            query: 用户查询
            intent_weight: 意图匹配权重
            semantic_weight: 语义相似度权重
            
        Returns:
            重排序后的结果
        """
        print(f"🔄 [RERANK-DEBUG] 开始意图重排序: query='{query}', 结果数量={len(results)}")
        
        if not results:
            print(f"⚠️ [RERANK-DEBUG] 没有结果需要重排序")
            return results
        
        # 识别查询意图
        intent, intent_confidence = self.identify_query_intent(query)
        print(f"🎯 [RERANK-DEBUG] 识别查询意图: {intent.value}, 置信度: {intent_confidence:.3f}")
        
        # 动态调整权重：意图置信度越高，意图权重越大
        adjusted_intent_weight = intent_weight * (0.5 + intent_confidence * 0.5)
        adjusted_semantic_weight = 1.0 - adjusted_intent_weight
        
        print(f"⚖️ [RERANK-DEBUG] 权重调整:")
        print(f"   - 原始意图权重: {intent_weight:.3f}")
        print(f"   - 调整后意图权重: {adjusted_intent_weight:.3f}")
        print(f"   - 语义权重: {adjusted_semantic_weight:.3f}")
        
        # 计算每个结果的综合得分
        scored_results = []
        print(f"📊 [RERANK-DEBUG] 计算每个结果的综合得分:")
        
        for i, result in enumerate(results):
            # 获取原始的语义相似度分数
            semantic_score = result.get("score", 0.0)
            
            # 添加详细的分数来源调试
            print(f"   🔍 [RERANK-DEBUG] 结果 {i+1} 分数来源分析:")
            print(f"      主要score字段: {semantic_score:.4f}")
            if "fusion_score" in result:
                print(f"      fusion_score字段: {result['fusion_score']:.4f}")
            if "vector_score" in result:
                print(f"      vector_score字段: {result['vector_score']:.4f}")
            if "bm25_score" in result:
                print(f"      bm25_score字段: {result['bm25_score']:.4f}")
            if "original_vector_score" in result:
                print(f"      original_vector_score字段: {result['original_vector_score']:.4f}")
            if "original_bm25_score" in result:
                print(f"      original_bm25_score字段: {result['original_bm25_score']:.4f}")
            
            # 验证分数的合理性
            if semantic_score > 20.0:
                print(f"      ⚠️ [RERANK-DEBUG] 检测到异常高分数，可能来源错误")
                # 如果有fusion_score，优先使用fusion_score作为语义分数
                if "fusion_score" in result:
                    semantic_score = result["fusion_score"]
                    print(f"      🔧 [RERANK-DEBUG] 使用fusion_score作为语义分数: {semantic_score:.4f}")
                elif "vector_score" in result and result["vector_score"] > 0:
                    semantic_score = result["vector_score"]
                    print(f"      🔧 [RERANK-DEBUG] 使用vector_score作为语义分数: {semantic_score:.4f}")
            
            # 计算意图相关度分数
            chunk = result.get("chunk", result)
            intent_score = self._calculate_intent_relevance(chunk, intent)
            
            # 计算综合得分
            combined_score = (
                semantic_score * adjusted_semantic_weight +
                intent_score * adjusted_intent_weight
            )
            
            # 创建新的结果对象，保留原始信息
            reranked_result = result.copy()
            reranked_result["original_score"] = semantic_score
            reranked_result["intent_score"] = intent_score
            reranked_result["combined_score"] = combined_score
            reranked_result["detected_intent"] = intent.value
            reranked_result["intent_confidence"] = intent_confidence
            
            scored_results.append(reranked_result)
            
            # 调试信息
            print(f"   {i+1}. 主题: {chunk.get('topic', 'Unknown')}")
            print(f"      - 原始分数: {semantic_score:.4f}")
            print(f"      - 意图分数: {intent_score:.4f}")
            print(f"      - 综合分数: {combined_score:.4f}")
            print(f"      - 计算: {semantic_score:.4f} × {adjusted_semantic_weight:.3f} + {intent_score:.4f} × {adjusted_intent_weight:.3f} = {combined_score:.4f}")
        
        # 按综合得分排序
        scored_results.sort(key=lambda x: x["combined_score"], reverse=True)
        
        print(f"📈 [RERANK-DEBUG] 重排序后的结果:")
        for i, result in enumerate(scored_results):
            chunk = result.get("chunk", result)
            print(f"   {i+1}. 主题: {chunk.get('topic', 'Unknown')}")
            print(f"      - 最终分数: {result['combined_score']:.4f}")
            print(f"      - 排名变化: {result.get('rank', 'N/A')} -> {i+1}")
        
        # 更新score字段为combined_score
        for result in scored_results:
            result["score"] = result["combined_score"]
        
        print(f"✅ [RERANK-DEBUG] 重排序完成")
        logger.info(f"重排序完成 - 意图: {intent.value}, 置信度: {intent_confidence:.2f}")
        logger.info(f"权重调整 - 意图权重: {adjusted_intent_weight:.2f}, 语义权重: {adjusted_semantic_weight:.2f}")
        
        # 记录前3个结果的得分变化
        for i, result in enumerate(scored_results[:3]):
            chunk = result.get("chunk", result)
            logger.info(
                f"  #{i+1} {chunk.get('topic', 'Unknown')}: "
                f"语义={result['original_score']:.3f}, "
                f"意图={result['intent_score']:.3f}, "
                f"综合={result['combined_score']:.3f}"
            )
        
        return scored_results


# 便捷函数
def rerank_by_intent(
    results: List[Dict[str, Any]], 
    query: str,
    intent_weight: float = 0.4
) -> List[Dict[str, Any]]:
    """
    便捷函数：基于意图重排序结果
    
    Args:
        results: 搜索结果
        query: 用户查询
        intent_weight: 意图权重（0-1）
        
    Returns:
        重排序后的结果
    """
    reranker = IntentAwareReranker()
    return reranker.rerank_results(results, query, intent_weight=intent_weight)