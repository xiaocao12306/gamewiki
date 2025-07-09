"""
简单的意图分类器 - 基于关键词判断用户意图
用于区分用户是想"查wiki"还是"查攻略"
Enhanced with LLM-based query rewriting capabilities
"""

import re
import json
import hashlib
import asyncio
from typing import Literal, Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass
from functools import lru_cache
import time

from src.game_wiki_tooltip.config import LLMConfig

logger = logging.getLogger(__name__)

@dataclass
class QueryRewriteResult:
    """查询重写结果"""
    original_query: str
    rewritten_query: str
    intent: str
    confidence: float
    reasoning: str
    search_type: str  # "semantic", "keyword", "hybrid"
    
@dataclass
class IntentAnalysis:
    """意图分析结果"""
    intent: str
    confidence: float
    context: Dict
    suggested_actions: List[str]

class IntentClassifier:
    """增强的意图分类器，支持LLM查询重写"""
    
    def __init__(self, llm_config: Optional[LLMConfig] = None):
        # 原有的关键词匹配逻辑
        self.wiki_keywords = [
            # 中文关键词 - Wiki类查询（查询定义、信息、数据）
            "什么是", "是什么", "介绍", "信息", "数据", "属性", "效果",
            "价格", "伤害", "装甲", "护甲", "血量", "射程", "弹药",
            # 英文关键词 - Wiki类查询
            "what is", "info", "information", "stats", "statistics", "data",
            "damage", "armor", "health", "range", "ammo", "cost", "price",
            "item", "weapon", "equipment", "enemy", "boss", "character",
            "skill", "ability", "faction", "location", "description"
        ]
        
        self.guide_keywords = [
            # 中文关键词 - 攻略类查询（询问方法、建议、推荐）
            "怎么", "如何", "提升", "获得", "赚钱", "效率", "技巧",
            "攻略", "方法", "策略", "建议", "推荐", "最佳", "最快",
            "新手", "入门", "进阶", "高级", "精通", "完美",
            "下一个", "选择", "优先", "顺序", "先后",
            # 英文关键词 - 攻略类查询
            "how", "how to", "guide", "tutorial", "strategy", "tip", "tips",
            "beginner", "beginner guide", "walkthrough", "method", "way",
            "efficient", "efficiency", "best", "fastest", "optimize",
            "improve", "increase", "gain", "earn", "unlock", "progress",
            "advanced", "expert", "master", "perfect", "complete",
            "recommend", "recommendation", "suggestion", "advice", "help", "learn",
            # 通用游戏进度/推荐相关
            "next", "choice", "what should", "which one", "priority", "order",
            "after", "progression", "unlock order", "tier list", "build",
            "loadout", "best loadout", "meta", "viable", "worth it"
        ]
        
        # 编译正则表达式以提高性能
        self.wiki_pattern = re.compile('|'.join(self.wiki_keywords), re.IGNORECASE)
        self.guide_pattern = re.compile('|'.join(self.guide_keywords), re.IGNORECASE)
        
        # LLM相关配置
        self.llm_config = llm_config or LLMConfig()
        self.llm_client = None
        
        # 缓存机制
        self.query_cache = {}
        
        # 初始化LLM客户端
        if self.llm_config.is_valid():
            self._initialize_llm_client()
        else:
            logger.warning("LLM配置无效，将使用基础查询重写功能")
    
    def _initialize_llm_client(self):
        """初始化LLM客户端"""
        try:
            if "gemini" in self.llm_config.model.lower():
                self._initialize_gemini_client()
            elif "gpt" in self.llm_config.model.lower():
                self._initialize_openai_client()
            else:
                logger.error(f"不支持的模型类型: {self.llm_config.model}")
                return
                
            logger.info(f"LLM客户端初始化成功，模型: {self.llm_config.model}")
        except Exception as e:
            logger.error(f"LLM客户端初始化失败: {e}")
            
    def _initialize_gemini_client(self):
        """初始化Gemini客户端"""
        try:
            import google.generativeai as genai
            
            api_key = self.llm_config.get_api_key()
            if not api_key:
                raise ValueError("未找到Gemini API密钥")
                
            genai.configure(api_key=api_key)
            
            # 配置生成参数
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=self.llm_config.max_tokens,
                temperature=self.llm_config.temperature,
            )
            
            # 安全设置
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            
            self.llm_client = genai.GenerativeModel(
                model_name=self.llm_config.model,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
        except ImportError:
            logger.error("google-generativeai库未安装，请运行: pip install google-generativeai")
            raise
        except Exception as e:
            logger.error(f"Gemini客户端初始化失败: {e}")
            raise
    
    def _initialize_openai_client(self):
        """初始化OpenAI客户端"""
        try:
            import openai
            
            api_key = self.llm_config.get_api_key()
            if not api_key:
                raise ValueError("未找到OpenAI API密钥")
                
            self.llm_client = openai.OpenAI(
                api_key=api_key,
                base_url=self.llm_config.base_url if self.llm_config.base_url else None,
                timeout=self.llm_config.timeout
            )
            
        except ImportError:
            logger.error("openai库未安装，请运行: pip install openai")
            raise
        except Exception as e:
            logger.error(f"OpenAI客户端初始化失败: {e}")
            raise
    
    def _generate_cache_key(self, query: str) -> str:
        """生成缓存键"""
        return hashlib.md5(f"{query}_{self.llm_config.model}".encode()).hexdigest()
    
    def _get_cached_result(self, query: str) -> Optional[QueryRewriteResult]:
        """获取缓存的结果"""
        if not self.llm_config.enable_cache:
            return None
            
        cache_key = self._generate_cache_key(query)
        if cache_key in self.query_cache:
            cached_data, timestamp = self.query_cache[cache_key]
            if time.time() - timestamp < self.llm_config.cache_ttl:
                return cached_data
            else:
                # 清理过期缓存
                del self.query_cache[cache_key]
        return None
    
    def _cache_result(self, query: str, result: QueryRewriteResult):
        """缓存结果"""
        if not self.llm_config.enable_cache:
            return
            
        cache_key = self._generate_cache_key(query)
        self.query_cache[cache_key] = (result, time.time())
    
    def _create_rewrite_prompt(self, query: str, basic_intent: str) -> str:
        """创建查询重写的提示词"""
        prompt = f"""
You are an AI assistant that helps optimize search queries for a universal game wiki and guide system.

Your task is to analyze the user's query and rewrite it to be more effective for information retrieval.

Original Query: "{query}"
Basic Intent Classification: {basic_intent}

Please analyze the query and provide a JSON response with the following structure:
{{
    "intent": "wiki|guide|unknown",
    "confidence": 0.0-1.0,
    "rewritten_query": "optimized query for search",
    "reasoning": "explanation of your analysis",
    "search_type": "semantic|keyword|hybrid",
    "context": {{
        "game_context": "relevant game context if any",
        "user_state": "what the user seems to have/know",
        "desired_outcome": "what the user wants to achieve"
    }},
    "suggested_actions": ["action1", "action2"]
}}

Analysis Guidelines:
1. If the query mentions "next", "after", "progression", extract the current state and target the next step
2. If asking about "best", "recommend", "choice", focus on comparative information
3. If asking about specific items/mechanics, focus on detailed information
4. DO NOT assume any specific game context unless explicitly mentioned in the query
5. Optimize for semantic search by using descriptive terms
6. Keep the rewrite general and game-agnostic unless specific terms are in the original query

Examples:
- "what's my next upgrade?" -> Focus on "progression upgrade recommendation guide"
- "best weapons for boss fights" -> Focus on "effective weapons boss combat guide"
- "how to beat final boss" -> Focus on "final boss strategy guide tips"

Important: DO NOT add specific game names or terms unless they appear in the original query.

Respond only with the JSON object, no additional text.
"""
        return prompt
    
    def _call_llm_with_retry(self, prompt: str) -> Optional[Dict]:
        """带重试的LLM调用"""
        for attempt in range(self.llm_config.max_retries):
            try:
                if "gemini" in self.llm_config.model.lower():
                    response = self.llm_client.generate_content(prompt)
                    response_text = response.text.strip()
                elif "gpt" in self.llm_config.model.lower():
                    response = self.llm_client.chat.completions.create(
                        model=self.llm_config.model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=self.llm_config.max_tokens,
                        temperature=self.llm_config.temperature
                    )
                    response_text = response.choices[0].message.content.strip()
                else:
                    return None
                
                # 尝试解析JSON
                if response_text.startswith('```json'):
                    response_text = response_text[7:-3]
                elif response_text.startswith('```'):
                    response_text = response_text[3:-3]
                
                return json.loads(response_text)
                
            except Exception as e:
                logger.warning(f"LLM调用失败 (尝试 {attempt + 1}/{self.llm_config.max_retries}): {e}")
                if attempt < self.llm_config.max_retries - 1:
                    time.sleep(self.llm_config.retry_delay * (2 ** attempt))  # 指数退避
                
        return None
    
    def rewrite_query(self, user_input: str) -> QueryRewriteResult:
        """
        使用LLM重写查询以提高搜索效果
        
        Args:
            user_input: 用户原始查询
            
        Returns:
            QueryRewriteResult: 重写结果
        """
        # 检查缓存
        cached_result = self._get_cached_result(user_input)
        if cached_result:
            logger.info(f"使用缓存结果: {user_input}")
            return cached_result
        
        # 首先使用基础分类器
        basic_intent = self.classify(user_input)
        basic_confidence = self.get_confidence(user_input)
        
        # 如果LLM不可用，使用基础重写
        if not self.llm_client:
            result = self._basic_query_rewrite(user_input, basic_intent, basic_confidence)
            self._cache_result(user_input, result)
            return result
        
        # 使用LLM进行高级重写
        try:
            prompt = self._create_rewrite_prompt(user_input, basic_intent)
            llm_response = self._call_llm_with_retry(prompt)
            
            if llm_response:
                result = QueryRewriteResult(
                    original_query=user_input,
                    rewritten_query=llm_response.get("rewritten_query", user_input),
                    intent=llm_response.get("intent", basic_intent),
                    confidence=llm_response.get("confidence", basic_confidence.get(basic_intent, 0.0)),
                    reasoning=llm_response.get("reasoning", "LLM-based analysis"),
                    search_type=llm_response.get("search_type", "hybrid")
                )
                logger.info(f"LLM重写成功: '{user_input}' -> '{result.rewritten_query}'")
            else:
                # LLM调用失败，使用基础重写
                result = self._basic_query_rewrite(user_input, basic_intent, basic_confidence)
                logger.warning(f"LLM重写失败，使用基础重写: {user_input}")
                
        except Exception as e:
            logger.error(f"LLM重写异常: {e}")
            result = self._basic_query_rewrite(user_input, basic_intent, basic_confidence)
        
        # 缓存结果
        self._cache_result(user_input, result)
        return result
    
    def _basic_query_rewrite(self, user_input: str, intent: str, confidence: Dict[str, float]) -> QueryRewriteResult:
        """基础查询重写（不使用LLM的降级方案）"""
        rewritten = user_input
        search_type = "hybrid"
        reasoning = "基础关键词重写"
        
        # 通用的重写规则
        if "next" in user_input.lower() and any(word in user_input.lower() for word in ["upgrade", "unlock", "progression", "step"]):
            # 通用进度查询
            if not any(word in rewritten.lower() for word in ["recommendation", "guide", "priority"]):
                rewritten += " progression recommendation guide"
            reasoning = "检测到进度查询，专注于推荐指南"
        
        elif "best" in user_input.lower() or "recommend" in user_input.lower():
            search_type = "semantic"
            reasoning = "推荐类查询，使用语义搜索"
            if not any(word in rewritten.lower() for word in ["guide", "recommendation"]):
                rewritten += " guide recommendation"
        
        elif any(word in user_input.lower() for word in ["how to", "怎么", "如何", "strategy", "攻略"]):
            if not any(word in rewritten.lower() for word in ["guide", "strategy", "tips"]):
                rewritten += " strategy guide tips"
            reasoning = "策略类查询，添加指南上下文"
        
        return QueryRewriteResult(
            original_query=user_input,
            rewritten_query=rewritten,
            intent=intent,
            confidence=confidence.get(intent, 0.0),
            reasoning=reasoning,
            search_type=search_type
        )

    # 保持原有的方法
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
        
        logger.debug(f"意图分类 - 输入: '{user_input}', Wiki匹配: {wiki_matches}, Guide匹配: {guide_matches}")
        
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
        question_words = ["怎么", "如何", "为什么", "什么时候", "哪里", "哪个"]
        if any(word in input_lower for word in question_words):
            return "guide"
        
        # 特殊处理"什么"的情况
        if "什么" in input_lower:
            # 如果是"是什么"（询问定义），倾向于wiki
            if "是什么" in input_lower or "什么是" in input_lower:
                return "wiki"
            # 如果是"该xxx什么"、"选什么"、"下一个什么"（询问推荐），倾向于guide
            elif any(pattern in input_lower for pattern in ["该", "选", "下一个", "推荐", "买", "用", "拿"]):
                return "guide"
            # 其他"什么"查询，需要进一步判断
            else:
                # 如果包含游戏物品名称，倾向于wiki
                if any(item in input_lower for item in ["武器", "装备", "道具", "物品", "weapon", "item", "equipment", "skill", "ability"]):
                    # 但如果同时包含选择性词汇，还是倾向于guide
                    if any(choice_word in input_lower for choice_word in ["选", "推荐", "好", "最", "优先"]):
                        return "guide"
                    return "wiki"
                # 默认倾向于guide（因为大多数"什么"查询是询问建议）
                return "guide"
        
        # 包含英文疑问词的倾向于查攻略
        english_question_words = ["how", "how to", "why", "when", "where"]
        if any(word in input_lower for word in english_question_words):
            return "guide"
        
        # 特殊处理"what"的情况 - 优先检查是否为推荐/选择类查询
        if "what" in input_lower:
            # 如果是询问推荐、选择、下一步的，倾向于guide
            guide_what_patterns = [
                "what should", "what's my next", "what is my next", 
                "what to choose", "what to pick", "what to buy", 
                "what to get", "what to unlock", "what choice",
                "what's the best", "what's better", "what do you recommend"
            ]
            if any(pattern in input_lower for pattern in guide_what_patterns):
                return "guide"
            
            # 如果是"what is"（询问定义），倾向于wiki
            if "what is" in input_lower or "what are" in input_lower:
                return "wiki"
            
            # 其他"what"查询，如果不是定义类的，也倾向于guide
            return "guide"
        
        # 包含推荐、选择相关词汇的倾向于guide
        guide_words = ["best", "recommend", "choice", "should", "next", "after", "priority", 
                       "推荐", "选择", "优先", "下一个", "之后", "该"]
        if any(word in input_lower for word in guide_words):
            return "guide"
        
        # 包含定义、信息相关词汇的倾向于wiki
        wiki_words = ["info", "information", "stats", "data", "damage", "cost", 
                      "信息", "数据", "伤害", "价格", "属性"]
        if any(word in input_lower for word in wiki_words):
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

def get_intent_classifier(llm_config: Optional[LLMConfig] = None) -> IntentClassifier:
    """获取意图分类器的单例实例"""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifier(llm_config=llm_config)
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

def rewrite_query_for_search(user_input: str, llm_config: Optional[LLMConfig] = None) -> QueryRewriteResult:
    """
    重写查询以提高搜索效果的便捷函数
    
    Args:
        user_input: 用户输入的查询文本
        llm_config: LLM配置，可选
        
    Returns:
        QueryRewriteResult: 重写结果
    """
    classifier = get_intent_classifier(llm_config)
    return classifier.rewrite_query(user_input) 