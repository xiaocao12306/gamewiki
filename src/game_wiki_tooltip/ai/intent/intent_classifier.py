"""
简单的意图分类器 - 基于关键词判断用户意图
用于区分用户是想"查wiki"还是"查攻略"
"""

import re
from typing import Literal, Dict, List
import logging

logger = logging.getLogger(__name__)

class IntentClassifier:
    """简单的意图分类器，基于关键词匹配"""
    
    def __init__(self):
        # 查wiki的关键词 - 通常是具体的游戏内容、角色、物品等
        self.wiki_keywords = [
            "喜欢", "讨厌", "礼物", "生日", "结婚", "好感度", "关系",
            "艾米丽", "谢恩", "哈维", "玛鲁", "塞巴斯蒂安", "阿比盖尔",
            "种子", "作物", "动物", "工具", "武器", "装备", "建筑",
            "商店", "价格", "时间", "地点", "任务", "事件"
        ]
        
        # 查攻略的关键词 - 通常是游戏机制、策略、技巧等
        self.guide_keywords = [
            "怎么", "如何", "提升", "获得", "赚钱", "效率", "技巧",
            "攻略", "方法", "策略", "建议", "推荐", "最佳", "最快",
            "新手", "入门", "进阶", "高级", "精通", "完美"
        ]
        
        # 编译正则表达式以提高性能
        self.wiki_pattern = re.compile('|'.join(self.wiki_keywords), re.IGNORECASE)
        self.guide_pattern = re.compile('|'.join(self.guide_keywords), re.IGNORECASE)
    
    def classify(self, user_input: str) -> Literal["wiki", "guide", "unknown"]:
        """
        对用户输入进行意图分类
        
        Args:
            user_input: 用户输入的查询文本
            
        Returns:
            "wiki": 查wiki意图
            "guide": 查攻略意图  
            "unknown": 无法确定意图
        """
        if not user_input or not user_input.strip():
            return "unknown"
        
        # 转换为小写进行匹配
        input_lower = user_input.lower().strip()
        
        # 计算匹配的关键词数量
        wiki_matches = len(self.wiki_pattern.findall(input_lower))
        guide_matches = len(self.guide_pattern.findall(input_lower))
        
        logger.info(f"意图分类 - 输入: '{user_input}', Wiki匹配: {wiki_matches}, Guide匹配: {guide_matches}")
        
        # 简单的决策逻辑
        if wiki_matches > guide_matches:
            return "wiki"
        elif guide_matches > wiki_matches:
            return "guide"
        else:
            # 如果匹配数量相等或都为0，使用启发式规则
            return self._heuristic_classification(input_lower)
    
    def _heuristic_classification(self, input_lower: str) -> Literal["wiki", "guide", "unknown"]:
        """
        启发式分类规则，用于处理匹配数量相等的情况
        """
        # 包含疑问词的倾向于查攻略
        question_words = ["怎么", "如何", "为什么", "什么时候", "哪里"]
        if any(word in input_lower for word in question_words):
            return "guide"
        
        # 包含具体名称的倾向于查wiki
        specific_names = ["艾米丽", "谢恩", "哈维", "玛鲁", "塞巴斯蒂安", "阿比盖尔"]
        if any(name in input_lower for name in specific_names):
            return "wiki"
        
        # 包含"什么"的倾向于查wiki（询问具体内容）
        if "什么" in input_lower:
            return "wiki"
        
        # 默认返回unknown
        return "unknown"
    
    def get_confidence(self, user_input: str) -> Dict[str, float]:
        """
        获取分类的置信度分数
        
        Args:
            user_input: 用户输入的查询文本
            
        Returns:
            包含各意图置信度的字典
        """
        if not user_input or not user_input.strip():
            return {"wiki": 0.0, "guide": 0.0, "unknown": 1.0}
        
        input_lower = user_input.lower().strip()
        
        # 计算匹配的关键词数量
        wiki_matches = len(self.wiki_pattern.findall(input_lower))
        guide_matches = len(self.guide_pattern.findall(input_lower))
        
        # 计算总匹配数
        total_matches = wiki_matches + guide_matches
        
        if total_matches == 0:
            return {"wiki": 0.0, "guide": 0.0, "unknown": 1.0}
        
        # 计算置信度
        wiki_confidence = wiki_matches / total_matches
        guide_confidence = guide_matches / total_matches
        
        return {
            "wiki": wiki_confidence,
            "guide": guide_confidence, 
            "unknown": 0.0
        }


# 全局实例，避免重复创建
_intent_classifier = None

def get_intent_classifier() -> IntentClassifier:
    """获取意图分类器的单例实例"""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifier()
    return _intent_classifier

def classify_intent(user_input: str) -> Literal["wiki", "guide", "unknown"]:
    """
    快速意图分类的便捷函数
    
    Args:
        user_input: 用户输入的查询文本
        
    Returns:
        分类结果
    """
    classifier = get_intent_classifier()
    return classifier.classify(user_input)

def get_intent_confidence(user_input: str) -> Dict[str, float]:
    """
    获取意图分类置信度的便捷函数
    
    Args:
        user_input: 用户输入的查询文本
        
    Returns:
        置信度字典
    """
    classifier = get_intent_classifier()
    return classifier.get_confidence(user_input) 