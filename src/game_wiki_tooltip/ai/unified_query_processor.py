"""
统一查询处理器 - 一次LLM调用完成多项任务
===================================================

将查询翻译、重写、意图分析合并到单次LLM调用中，提高响应速度
"""

import json
import hashlib
import time
import logging
from typing import Dict, Any, Optional, Literal
from dataclasses import dataclass

from ..config import LLMConfig

logger = logging.getLogger(__name__)

@dataclass
class UnifiedQueryResult:
    """统一查询处理结果"""
    original_query: str
    detected_language: str
    translated_query: str
    rewritten_query: str
    intent: str
    confidence: float
    search_type: str
    reasoning: str
    translation_applied: bool
    rewrite_applied: bool
    processing_time: float

class UnifiedQueryProcessor:
    """统一查询处理器 - 一次LLM调用完成翻译+重写+意图分析"""
    
    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self.llm_config = llm_config or LLMConfig()
        self.llm_client = None
        
        # 缓存机制
        self.query_cache = {}
        
        # 统计信息
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "successful_processing": 0,
            "failed_processing": 0,
            "average_processing_time": 0.0
        }
        
        # 初始化LLM客户端
        if self.llm_config.is_valid():
            self._initialize_llm_client()
        else:
            logger.warning("LLM配置无效，将使用基础处理模式")
    
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
                
            logger.info(f"统一查询处理器初始化成功，模型: {self.llm_config.model}")
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
            
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=self.llm_config.max_tokens,
                temperature=self.llm_config.temperature,
            )
            
            self.llm_client = genai.GenerativeModel(
                model_name=self.llm_config.model,
                generation_config=generation_config,
            )
            
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
            
        except Exception as e:
            logger.error(f"OpenAI客户端初始化失败: {e}")
            raise
    
    def _generate_cache_key(self, query: str) -> str:
        """生成缓存键"""
        return hashlib.md5(f"{query}_{self.llm_config.model}".encode()).hexdigest()
    
    def _get_cached_result(self, query: str) -> Optional[UnifiedQueryResult]:
        """获取缓存的结果"""
        if not self.llm_config.enable_cache:
            return None
            
        cache_key = self._generate_cache_key(query)
        if cache_key in self.query_cache:
            cached_data, timestamp = self.query_cache[cache_key]
            if time.time() - timestamp < self.llm_config.cache_ttl:
                self.stats["cache_hits"] += 1
                return cached_data
            else:
                del self.query_cache[cache_key]
        return None
    
    def _cache_result(self, query: str, result: UnifiedQueryResult):
        """缓存结果"""
        if not self.llm_config.enable_cache:
            return
            
        cache_key = self._generate_cache_key(query)
        self.query_cache[cache_key] = (result, time.time())
    
    def _create_unified_prompt(self, query: str) -> str:
        """创建统一处理的提示词"""
        prompt = f"""You are an AI assistant that processes search queries for a universal game wiki and guide system.

Your task is to analyze the user's query and perform the following tasks in ONE response:
1. **Language Detection**: Detect the language of the query
2. **Translation**: If the query is in Chinese, translate it to English
3. **Intent Classification**: Classify the intent (wiki/guide/unknown)
4. **Query Rewriting**: Optimize the query for better search results

Original Query: "{query}"

Please provide a JSON response with the following structure:
{{
    "detected_language": "zh|en|other",
    "translated_query": "English translation if needed, otherwise same as original",
    "intent": "wiki|guide|unknown",
    "confidence": 0.0-1.0,
    "rewritten_query": "optimized query for search",
    "reasoning": "explanation of your analysis and optimizations",
    "search_type": "semantic|keyword|hybrid"
}}

**Analysis Guidelines:**

**Language Detection:**
- If >30% characters are Chinese (\\u4e00-\\u9fff), mark as "zh"
- Otherwise mark as "en" or "other"

**Intent Classification:**
- **wiki**: User wants factual information, definitions, stats, or specific item/character/enemy data
  - Examples: "what is wizard", "sword stats", "什么是法师", "角色属性"
  - Keywords: "what is", "info", "stats", "damage", "是什么", "信息", "数据", "属性"

- **guide**: User wants strategies, recommendations, progression advice, or how-to instructions
  - Examples: "how to beat boss", "best build", "progression guide", "选择什么职业"
  - Keywords: "how", "best", "recommend", "next", "after", "should", "怎么", "推荐", "下一个", "选择"
  - Special attention: Queries about "what's next", "what to unlock after X", "progression order" are GUIDE queries

**Query Rewriting:**
- DO NOT add any specific game names or prefixes unless they exist in the original query
- For general terms, keep them general (e.g., "法师" -> "mage" or "wizard", not "GameName mage")
- For strategy queries, add keywords like "strategy", "guide", "tips"
- For recommendation queries, add "best", "recommended", "guide"
- Keep original game-specific terms unchanged only if they appear in the query
- Preserve the original meaning and scope of the query

**Search Type:**
- "semantic": For conceptual queries requiring understanding (recommendations, strategies)
- "keyword": For specific item/character lookups
- "hybrid": When both approaches would be beneficial

**Important Notes:**
- Queries asking for recommendations or "what's next" are ALWAYS guide intents
- Queries about progression order or unlock priorities are ALWAYS guide intents
- Only classify as "wiki" when user explicitly wants factual data/definitions
- DO NOT assume any specific game context unless explicitly mentioned in the query
- Keep translations and rewrites GENERIC and GAME-AGNOSTIC
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
                
                # 解析JSON响应
                if response_text.startswith('```json'):
                    response_text = response_text[7:-3]
                elif response_text.startswith('```'):
                    response_text = response_text[3:-3]
                
                return json.loads(response_text)
                
            except Exception as e:
                logger.warning(f"统一处理LLM调用失败 (尝试 {attempt + 1}/{self.llm_config.max_retries}): {e}")
                if attempt < self.llm_config.max_retries - 1:
                    time.sleep(self.llm_config.retry_delay * (2 ** attempt))
                
        return None
    
    def _basic_processing(self, query: str) -> UnifiedQueryResult:
        """基础处理模式（LLM不可用时的降级方案）"""
        # 简单的语言检测
        chinese_chars = sum(1 for char in query if '\u4e00' <= char <= '\u9fff')
        detected_language = "zh" if chinese_chars / len(query) > 0.3 else "en"
        
        # 基础意图分类
        intent = "guide"
        confidence = 0.6
        
        # 判断是否是询问定义的wiki查询
        wiki_patterns = ["what is", "什么是", "是什么", "info", "stats", "数据", "属性"]
        if any(pattern in query.lower() for pattern in wiki_patterns):
            intent = "wiki"
            confidence = 0.8
        # 判断是否是guide查询
        elif any(word in query.lower() for word in ["how", "如何", "怎么", "best", "recommend", "推荐", "next", "下一个", "选择", "该"]):
            intent = "guide"
            confidence = 0.8
        # 特殊处理"什么"的情况
        elif "什么" in query:
            # 如果是"该xxx什么"或"选什么"等推荐类查询
            if any(pattern in query for pattern in ["该", "选", "下一个", "推荐"]):
                intent = "guide"
                confidence = 0.7
            else:
                intent = "wiki"
                confidence = 0.6
        
        # 基础重写 - 保持通用性，不特定于任何游戏
        rewritten_query = query
        
        # 通用的推荐查询处理
        if any(word in query.lower() for word in ["推荐", "选择", "recommend", "choice", "next", "下一个"]):
            # 检测是否为推荐类查询
            if not any(word in rewritten_query.lower() for word in ["guide", "recommendation", "攻略"]):
                rewritten_query += " guide recommendation"
            intent = "guide"
            confidence = 0.8
        
        # 通用的策略查询处理
        elif any(word in query.lower() for word in ["怎么", "如何", "how to", "strategy", "攻略"]):
            if not any(word in rewritten_query.lower() for word in ["guide", "strategy", "攻略"]):
                rewritten_query += " strategy guide"
            intent = "guide"
            confidence = 0.8
        
        return UnifiedQueryResult(
            original_query=query,
            detected_language=detected_language,
            translated_query=query,  # 基础模式不翻译
            rewritten_query=rewritten_query,
            intent=intent,
            confidence=confidence,
            search_type="hybrid",
            reasoning="基础处理模式 - LLM不可用",
            translation_applied=False,
            rewrite_applied=rewritten_query != query,
            processing_time=0.001
        )
    
    def process_query(self, query: str) -> UnifiedQueryResult:
        """
        统一处理查询：翻译+重写+意图分析
        
        Args:
            query: 原始查询
            
        Returns:
            UnifiedQueryResult: 统一处理结果
        """
        start_time = time.time()
        self.stats["total_queries"] += 1
        
        # 检查缓存
        cached_result = self._get_cached_result(query)
        if cached_result:
            logger.info(f"使用缓存结果: {query}")
            return cached_result
        
        # 如果LLM不可用，使用基础处理
        if not self.llm_client:
            result = self._basic_processing(query)
            self._cache_result(query, result)
            return result
        
        try:
            # 使用LLM进行统一处理
            prompt = self._create_unified_prompt(query)
            llm_response = self._call_llm_with_retry(prompt)
            
            if llm_response:
                # 解析LLM响应
                detected_language = llm_response.get("detected_language", "en")
                translated_query = llm_response.get("translated_query", query)
                rewritten_query = llm_response.get("rewritten_query", translated_query)
                
                processing_time = time.time() - start_time
                
                result = UnifiedQueryResult(
                    original_query=query,
                    detected_language=detected_language,
                    translated_query=translated_query,
                    rewritten_query=rewritten_query,
                    intent=llm_response.get("intent", "guide"),
                    confidence=llm_response.get("confidence", 0.7),
                    search_type=llm_response.get("search_type", "hybrid"),
                    reasoning=llm_response.get("reasoning", "LLM统一处理"),
                    translation_applied=translated_query != query,
                    rewrite_applied=rewritten_query != translated_query,
                    processing_time=processing_time
                )
                
                self.stats["successful_processing"] += 1
                logger.info(f"统一处理成功: '{query}' -> 翻译: '{translated_query}' -> 重写: '{rewritten_query}'")
                
            else:
                # LLM调用失败，使用基础处理
                result = self._basic_processing(query)
                self.stats["failed_processing"] += 1
                logger.warning(f"LLM统一处理失败，使用基础处理: {query}")
                
        except Exception as e:
            logger.error(f"统一处理异常: {e}")
            result = self._basic_processing(query)
            self.stats["failed_processing"] += 1
        
        # 更新平均处理时间
        self.stats["average_processing_time"] = (
            (self.stats["average_processing_time"] * (self.stats["total_queries"] - 1) + 
             result.processing_time) / self.stats["total_queries"]
        )
        
        # 缓存结果
        self._cache_result(query, result)
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "successful_processing": 0,
            "failed_processing": 0,
            "average_processing_time": 0.0
        }

# 全局实例
_unified_processor = None

def get_unified_processor(llm_config: Optional[LLMConfig] = None) -> UnifiedQueryProcessor:
    """获取统一查询处理器的单例实例"""
    global _unified_processor
    if _unified_processor is None:
        _unified_processor = UnifiedQueryProcessor(llm_config=llm_config)
    return _unified_processor

def process_query_unified(query: str, llm_config: Optional[LLMConfig] = None) -> UnifiedQueryResult:
    """
    统一处理查询的便捷函数
    
    Args:
        query: 用户查询
        llm_config: LLM配置
        
    Returns:
        UnifiedQueryResult: 处理结果
    """
    processor = get_unified_processor(llm_config)
    return processor.process_query(query) 