"""
增强查询处理器 - 游戏战术查询优化
===================================

功能：
1. 查询重写："how to kill X" → "X weaknesses strategy"
2. 敌人名称标准化和别名处理
3. 战术意图分类和扩展
4. 多语言查询支持
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)

class QueryIntent(Enum):
    """查询意图枚举"""
    WEAKNESS = "weakness"           # 弱点查询
    STRATEGY = "strategy"           # 策略查询  
    KILL_METHOD = "kill_method"     # 击杀方法
    WEAPON_LOADOUT = "weapon_loadout"  # 武器配装
    BUILD_GUIDE = "build_guide"     # 配装指南
    GENERAL_INFO = "general_info"   # 通用信息
    UNKNOWN = "unknown"             # 未知意图

class EnhancedQueryProcessor:
    """增强查询处理器"""
    
    # 敌人名称标准化映射
    ENEMY_ALIASES = {
        # Bile Titan别名
        'bile titan': ['bile titan', 'biletitan', 'bile_titan', 'bt', '胆汁泰坦', '胆汁巨人', '酸液泰坦'],
        
        # Hulk别名
        'hulk': ['hulk', 'hulk devastator', '巨人机甲', '机甲巨人', '巨型机甲'],
        
        # Charger别名
        'charger': ['charger', 'behemoth charger', '冲锋者', '巨兽冲锋者', '重装冲锋者'],
        
        # Impaler别名
        'impaler': ['impaler', '穿刺者', '尖刺者', '触手怪'],
        
        # Brood Commander别名
        'brood commander': ['brood commander', '族群指挥官', '指挥官', '首领虫'],
        
        # Stalker别名
        'stalker': ['stalker', '潜行者', '隐身虫', '隐形者'],
        
        # Automaton敌人
        'factory strider': ['factory strider', '工厂行者', '机械行者', '巨型步行者'],
        'devastator': ['devastator', '毁灭者', '破坏者'],
        'berserker': ['berserker', '狂战士', '冲锋机器人'],
        'gunship': ['gunship', 'dropship gunship', '武装飞船', '武装直升机'],
        'tank': ['tank', 'annihilator tank', 'shredder tank', '坦克', '歼灭者坦克'],
        'dropship': ['dropship', '运输舰', '投送舰'],
    }
    
    # 查询意图模式
    INTENT_PATTERNS = {
        QueryIntent.WEAKNESS: [
            r'weak\s*point', r'weakness', r'vulnerable', r'weak\s*spot', 
            r'critical\s*point', r'弱点', r'要害', r'致命点', r'薄弱', r'脆弱'
        ],
        QueryIntent.KILL_METHOD: [
            r'how\s+to\s+kill', r'how\s+to\s+destroy', r'how\s+to\s+defeat', 
            r'kill\s+method', r'destroy\s+method', r'elimination',
            r'如何击杀', r'怎么杀', r'如何消灭', r'击杀方法', r'消灭方法'
        ],
        QueryIntent.STRATEGY: [
            r'strategy', r'tactic', r'approach', r'counter', r'fight\s+against',
            r'deal\s+with', r'handle', r'combat',
            r'策略', r'战术', r'对抗', r'应对', r'处理', r'战斗'
        ],
        QueryIntent.WEAPON_LOADOUT: [
            r'weapon', r'loadout', r'build', r'equipment', r'gear', 
            r'best\s+weapon', r'recommended\s+weapon', r'effective\s+weapon',
            r'武器', r'配装', r'装备', r'推荐武器', r'有效武器', r'最佳武器'
        ],
        QueryIntent.BUILD_GUIDE: [
            r'build\s+guide', r'loadout\s+guide', r'setup', r'configuration',
            r'配装指南', r'搭配指南', r'设置', r'配置'
        ]
    }
    
    # 战术关键词扩展
    TACTICAL_EXPANSIONS = {
        'weakness': ['weak point', 'vulnerable', 'critical', 'fatal'],
        'kill': ['destroy', 'eliminate', 'defeat', 'take down'],
        'strategy': ['tactic', 'approach', 'method', 'counter'],
        'weapon': ['loadout', 'equipment', 'gear', 'armament'],
        'effective': ['recommended', 'best', 'optimal', 'ideal'],
        
        # 中文扩展
        '弱点': ['要害', '致命点', '薄弱点', '脆弱'],
        '击杀': ['消灭', '击败', '摧毁', '击倒'],
        '策略': ['战术', '方法', '对抗', '应对'],
        '武器': ['装备', '配装', '军备', '武装'],
        '有效': ['推荐', '最佳', '理想', '优秀']
    }
    
    def __init__(self):
        """初始化查询处理器"""
        # 构建反向敌人映射（别名 -> 标准名称）
        self.enemy_reverse_map = {}
        for standard_name, aliases in self.ENEMY_ALIASES.items():
            for alias in aliases:
                self.enemy_reverse_map[alias.lower()] = standard_name
                
        # 编译正则表达式
        self.intent_regexes = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            self.intent_regexes[intent] = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    
    def normalize_enemy_names(self, query: str) -> Tuple[str, List[str]]:
        """
        标准化查询中的敌人名称
        
        Args:
            query: 原始查询
            
        Returns:
            (标准化后的查询, 识别到的敌人列表)
        """
        normalized_query = query.lower()
        detected_enemies = []
        
        # 按别名长度降序排序，优先匹配长别名
        sorted_aliases = sorted(self.enemy_reverse_map.items(), key=lambda x: len(x[0]), reverse=True)
        
        for alias, standard_name in sorted_aliases:
            if alias in normalized_query:
                # 替换为标准名称
                normalized_query = normalized_query.replace(alias, standard_name)
                if standard_name not in detected_enemies:
                    detected_enemies.append(standard_name)
        
        return normalized_query, detected_enemies
    
    def classify_intent(self, query: str) -> Tuple[QueryIntent, float]:
        """
        分类查询意图
        
        Args:
            query: 查询文本
            
        Returns:
            (意图类型, 置信度)
        """
        query_lower = query.lower()
        
        # 计算每种意图的匹配分数
        intent_scores = {}
        
        for intent, regexes in self.intent_regexes.items():
            score = 0
            for regex in regexes:
                matches = regex.findall(query_lower)
                score += len(matches)
            
            if score > 0:
                intent_scores[intent] = score
        
        if not intent_scores:
            return QueryIntent.UNKNOWN, 0.0
        
        # 找到最高分的意图
        best_intent = max(intent_scores, key=intent_scores.get)
        max_score = intent_scores[best_intent]
        
        # 计算置信度（简单的归一化）
        confidence = min(max_score / 3.0, 1.0)  # 假设3个匹配为满分
        
        return best_intent, confidence
    
    def expand_tactical_terms(self, query: str) -> str:
        """
        扩展战术术语
        
        Args:
            query: 查询文本
            
        Returns:
            扩展后的查询
        """
        expanded_terms = [query]
        query_lower = query.lower()
        
        for base_term, expansions in self.TACTICAL_EXPANSIONS.items():
            if base_term in query_lower:
                # 添加扩展术语
                for expansion in expansions:
                    if expansion not in query_lower:
                        expanded_terms.append(expansion)
        
        return " ".join(expanded_terms)
    
    def rewrite_query(self, query: str) -> Dict[str, any]:
        """
        主要查询重写函数
        
        Args:
            query: 原始查询
            
        Returns:
            重写结果字典
        """
        logger.info(f"开始处理查询: {query}")
        
        # 1. 标准化敌人名称
        normalized_query, detected_enemies = self.normalize_enemy_names(query)
        
        # 2. 分类意图
        intent, confidence = self.classify_intent(normalized_query)
        
        # 3. 根据意图重写查询
        rewritten_query = self._apply_intent_rewrite(normalized_query, intent, detected_enemies)
        
        # 4. 扩展战术术语
        expanded_query = self.expand_tactical_terms(rewritten_query)
        
        # 5. 生成搜索关键词
        search_keywords = self._generate_search_keywords(expanded_query, intent, detected_enemies)
        
        result = {
            "original": query,
            "normalized": normalized_query,
            "rewritten": expanded_query,
            "intent": intent.value,
            "confidence": confidence,
            "detected_enemies": detected_enemies,
            "search_keywords": search_keywords,
            "rewrite_applied": expanded_query != query,
            "reasoning": self._explain_rewrite(query, expanded_query, intent, detected_enemies)
        }
        
        logger.info(f"查询处理完成: {intent.value} (置信度: {confidence:.2f})")
        logger.info(f"检测到敌人: {detected_enemies}")
        logger.info(f"重写结果: {expanded_query}")
        
        return result
    
    def _apply_intent_rewrite(self, query: str, intent: QueryIntent, enemies: List[str]) -> str:
        """根据意图应用特定的重写规则"""
        
        if intent == QueryIntent.KILL_METHOD:
            # "how to kill X" → "X weaknesses strategy kill method"
            if enemies:
                base_terms = []
                for enemy in enemies:
                    base_terms.extend([enemy, f"{enemy} weakness", f"{enemy} strategy"])
                base_terms.extend(["kill method", "destroy", "eliminate"])
                return " ".join(base_terms)
            else:
                return query.replace("how to kill", "weakness strategy kill method")
                
        elif intent == QueryIntent.WEAKNESS:
            # 强化弱点查询
            if enemies:
                base_terms = []
                for enemy in enemies:
                    base_terms.extend([enemy, f"{enemy} weakness", f"{enemy} weak point"])
                base_terms.extend(["critical", "vulnerable", "fatal"])
                return " ".join(base_terms)
            else:
                return f"{query} weak point critical vulnerable"
                
        elif intent == QueryIntent.STRATEGY:
            # 强化策略查询
            if enemies:
                base_terms = []
                for enemy in enemies:
                    base_terms.extend([enemy, f"{enemy} strategy", f"{enemy} tactic"])
                base_terms.extend(["counter", "approach", "combat"])
                return " ".join(base_terms)
            else:
                return f"{query} strategy tactic counter approach"
                
        elif intent == QueryIntent.WEAPON_LOADOUT:
            # 强化武器配装查询
            if enemies:
                base_terms = []
                for enemy in enemies:
                    base_terms.extend([enemy, f"{enemy} weapon", f"{enemy} loadout"])
                base_terms.extend(["recommended", "effective", "best"])
                return " ".join(base_terms)
            else:
                return f"{query} weapon loadout recommended effective"
        
        # 默认情况
        return query
    
    def _generate_search_keywords(self, query: str, intent: QueryIntent, enemies: List[str]) -> List[str]:
        """生成搜索关键词列表"""
        keywords = []
        
        # 添加原始查询词
        keywords.extend(query.split())
        
        # 添加敌人相关关键词
        for enemy in enemies:
            keywords.extend([enemy, f"{enemy} guide", f"{enemy} tips"])
        
        # 根据意图添加特定关键词
        if intent == QueryIntent.WEAKNESS:
            keywords.extend(["weakness", "weak point", "vulnerable", "critical"])
        elif intent == QueryIntent.KILL_METHOD:
            keywords.extend(["kill", "destroy", "eliminate", "defeat"])
        elif intent == QueryIntent.STRATEGY:
            keywords.extend(["strategy", "tactic", "counter", "approach"])
        elif intent == QueryIntent.WEAPON_LOADOUT:
            keywords.extend(["weapon", "loadout", "build", "recommended"])
        
        # 去重并返回
        return list(set(keywords))
    
    def _explain_rewrite(self, original: str, rewritten: str, intent: QueryIntent, enemies: List[str]) -> str:
        """解释重写过程"""
        explanations = []
        
        if enemies:
            explanations.append(f"识别敌人: {', '.join(enemies)}")
        
        explanations.append(f"查询意图: {intent.value}")
        
        if rewritten != original:
            explanations.append("应用查询扩展以提高检索精度")
        
        return "; ".join(explanations)
    
    def get_enemy_specific_terms(self, enemy: str) -> List[str]:
        """获取敌人特定的搜索术语"""
        enemy_terms = {
            'bile titan': ['head', 'face', 'belly', 'sac', 'acid', 'spit', 'anti-tank', 'railgun'],
            'hulk': ['eye', 'socket', 'stun', 'grenade', 'leg', 'mobility', 'flamethrower'],
            'charger': ['rear', 'back', 'leg', 'armor', 'explosive', 'thermite'],
            'impaler': ['tentacle', 'spikes', 'stationary', 'stratagem'],
            'factory strider': ['eye', 'leg', 'underside', 'door', 'massive'],
            'devastator': ['head', 'stomach', 'backpack', 'shield'],
            'berserker': ['head', 'stomach', 'stagger', 'plasma'],
            'tank': ['rear', 'vent', 'turret', 'front', 'heavy'],
            'gunship': ['thruster', 'hull', 'engine', 'anti-air']
        }
        
        return enemy_terms.get(enemy, [])
    
    def create_optimized_queries(self, original_query: str) -> List[Dict[str, any]]:
        """
        创建多个优化的查询变体
        
        Args:
            original_query: 原始查询
            
        Returns:
            查询变体列表
        """
        base_result = self.rewrite_query(original_query)
        variants = [base_result]
        
        # 为每个检测到的敌人创建专门的查询
        for enemy in base_result["detected_enemies"]:
            enemy_terms = self.get_enemy_specific_terms(enemy)
            if enemy_terms:
                enemy_query = f"{enemy} {' '.join(enemy_terms[:3])}"  # 限制术语数量
                enemy_result = self.rewrite_query(enemy_query)
                enemy_result["variant_type"] = f"enemy_specific_{enemy}"
                variants.append(enemy_result)
        
        return variants


def test_query_processor():
    """测试查询处理器"""
    processor = EnhancedQueryProcessor()
    
    test_queries = [
        "how to kill bile titan",
        "bile titan weakness",
        "bt weak point",
        "hulk eye socket strategy", 
        "best weapon against charger",
        "如何击杀胆汁泰坦",
        "巨人机甲弱点",
        "factory strider loadout guide"
    ]
    
    print("=== 查询处理器测试 ===")
    
    for query in test_queries:
        print(f"\n原始查询: {query}")
        result = processor.rewrite_query(query)
        
        print(f"  意图: {result['intent']} (置信度: {result['confidence']:.2f})")
        print(f"  检测敌人: {result['detected_enemies']}")
        print(f"  重写查询: {result['rewritten']}")
        print(f"  重写原因: {result['reasoning']}")
        print(f"  搜索关键词: {result['search_keywords'][:5]}...")  # 只显示前5个


if __name__ == "__main__":
    test_query_processor() 