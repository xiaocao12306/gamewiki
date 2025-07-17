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
    bm25_optimized_query: str  # 新增：专门为BM25优化的查询
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
4. **Query Rewriting**: Optimize the query for semantic search
5. **BM25 Optimization**: Create a specialized query for keyword-based BM25 search

Original Query: "{query}"

Please provide a JSON response with the following structure:
{{
    "detected_language": "zh|en|other",
    "translated_query": "English translation if needed, otherwise same as original",
    "intent": "wiki|guide|unknown",
    "confidence": 0.0-1.0,
    "rewritten_query": "optimized query for semantic search",
    "bm25_optimized_query": "specialized query for BM25 keyword search",
    "reasoning": "explanation of your analysis and optimizations",
    "search_type": "semantic|keyword|hybrid"
}}

**Analysis Guidelines:**

**Language Detection:**
- If >30% characters are Chinese (\\u4e00-\\u9fff), mark as "zh"
- Otherwise mark as "en" or "other"

**Intent Classification:**
- **wiki**: User wants factual information, definitions, stats, or specific item/character/enemy data
  - Single words or short phrases that look like game-specific terms should be classified as wiki
  - **Game-specific term indicators:**
    - Proper nouns (capitalized words like "Excalibur", "Gandalf", "Dragonbone")
    - Uncommon word combinations that sound like item/character names (e.g. Democratic detonation)
    - Single technical-sounding words without common modifiers
    - Foreign or fantasy-sounding terms
    - Compound words that suggest game items (e.g., "Bloodstone", "Frostbolt", "Ironhelm")
  - Examples: "wizard", "sword stats", "Excalibur", "什么是法师", "角色属性", "Bloodstone", "铁剑", "法师塔"
  - Keywords: "what is", "info", "stats", "damage", "是什么", "信息", "数据", "属性"
  - **Rule**: If the query is 1-2 words and doesn't contain guide keywords, classify as wiki

- **guide**: User wants strategies, recommendations, progression advice, or how-to instructions
  - Examples: "how to beat boss", "best build", "progression guide", "选择什么职业", "longsword build"
  - Keywords: "how", "best", "recommend", "next", "after", "should", "build", "guide", "strategy", "tips", "怎么", "推荐", "下一个", "选择", "配置", "攻略", "策略"
  - **Strategy-related terms**: "build", "setup", "loadout", "combo", "synergy", "meta", "tier", "rotation", "counter", "optimal", "efficient", "playstyle", "progression", "priority", "comparison", "vs", "choice", "unlock", "配置", "搭配", "组合", "连击", "克制", "最优", "高效", "玩法", "进阶", "优先级", "比较", "解锁", "协同"
  - **Build-related queries**: Any query containing strategy-related terms should be classified as guide
  - Special attention: Queries about "what's next", "what to unlock after X", "progression order" are GUIDE queries
  - **Rule**: Classify as guide if the query asks for advice, strategy, how-to information, OR contains build/setup-related terms

**Query Rewriting (for semantic search):**
- DO NOT add any specific game names or prefixes unless they exist in the original query
- For general terms, keep them general (e.g., "法师" -> "mage" or "wizard", not "GameName mage")
- For strategy queries, add keywords like "strategy", "guide"
- For recommendation queries, add "best", "recommendation"
- Keep original game-specific terms unchanged only if they appear in the query
- Preserve the original meaning and scope of the query

**BM25 Query Optimization (CRITICAL - for keyword search):**
This is a specialized query designed to enhance important game terms while preserving the original query intent.

**Key Principles:**
1. **Preserve original query structure**: Keep the user's original words and intent
2. **Enhance game-specific nouns**: Repeat weapon names, character names, item names, location names
3. **Boost core topic words**: Repeat important concepts like "build", "weapon", "character", "strategy"
4. **Maintain query coherence**: Don't add unrelated terms that might match wrong content
5. **Weight through repetition**: Use repetition to increase BM25 term frequency scores

**Examples:**
- "best warbond" -> "best warbond warbond warbond recommendations"
- "wizard build guide" -> "wizard wizard build build loadout guide"  
- "sword recommendations" -> "sword sword weapon recommendations guide"
- "法师推荐装备" -> "法师 法师 推荐 装备 装备 配置"

**Rules for BM25 optimization:**
- Keep ALL original query terms
- Identify game-specific proper nouns and repeat them 2-3 times
- Identify core topic words (build, weapon, character, boss, etc.) and repeat them 1-2 times
- Add closely related game terms only if they enhance the topic (e.g., "build" -> add "loadout")
- For build queries, add: "loadout", "setup", "configuration" 
- For weapon queries, add: "gear", "equipment"
- For character queries, add: "class", "hero"
- NEVER replace words - only enhance through repetition and related terms
- Maintain readability and avoid excessive repetition (max 3 times per term)

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
- BM25 optimization should focus on KEYWORDS and SPECIFIC TERMS, not generic descriptors
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
        
        # 基础BM25优化：移除通用词汇，保留核心词汇
        bm25_optimized_query = self._basic_bm25_optimization(query)
        
        return UnifiedQueryResult(
            original_query=query,
            detected_language=detected_language,
            translated_query=query,  # 基础模式不翻译
            rewritten_query=rewritten_query,
            bm25_optimized_query=bm25_optimized_query,  # 基础模式BM25优化
            intent=intent,
            confidence=confidence,
            search_type="hybrid",
            reasoning="基础处理模式 - LLM不可用",
            translation_applied=False,
            rewrite_applied=rewritten_query != query,
            processing_time=0.001
        )
    
    def _basic_bm25_optimization(self, query: str) -> str:
        """基础BM25优化（LLM不可用时的简单版本）- 使用权重增强"""
        
        words = query.lower().split()
        optimized_words = []
        
        # 游戏专有名词指标（可能的游戏术语）
        game_terms = [
            # 通用游戏术语
            'build', 'weapon', 'character', 'boss', 'enemy', 'skill', 'spell', 'item', 'gear',
            'armor', 'shield', 'sword', 'bow', 'staff', 'magic', 'fire', 'ice', 'poison',
            # Helldivers 2 相关
            'warbond', 'stratagem', 'helldiver', 'terminid', 'automaton', 'bile', 'charger',
            # 中文游戏术语
            '配装', '武器', '角色', '技能', '装备', '护甲', '法术', '魔法', '敌人', '首领'
        ]
        
        # 主题词汇（核心概念）
        topic_words = [
            'build', 'weapon', 'character', 'boss', 'strategy', 'guide', 'tip',
            '配装', '武器', '角色', '策略', '攻略', '技巧'
        ]
        
        # 通用词汇（降低权重，但不删除）
        generic_words = [
            'best', 'good', 'great', 'top', 'recommendation', 'guide', 'tutorial', 'help',
            '最好', '最佳', '推荐', '攻略', '教程', '帮助'
        ]
        
        for word in words:
            # 保留原始词汇
            optimized_words.append(word)
            
            # 如果是游戏专有名词，重复2-3次增强权重
            if word in game_terms:
                optimized_words.extend([word] * 2)  # 额外重复2次
                
            # 如果是主题词汇，重复1次增强权重
            elif word in topic_words:
                optimized_words.append(word)  # 额外重复1次
                
            # 通用词汇保持原样，不增强也不删除
        
        # 根据查询类型添加相关术语
        query_lower = query.lower()
        
        # 如果是build相关查询，添加相关术语
        if any(term in query_lower for term in ['build', 'setup', 'loadout', '配装', '搭配']):
            optimized_words.extend(['loadout', 'setup', 'configuration'])
            
        # 如果是weapon相关查询，添加相关术语  
        elif any(term in query_lower for term in ['weapon', 'sword', 'gun', '武器', '剑', '枪']):
            optimized_words.extend(['gear', 'equipment'])
            
        # 如果是character相关查询，添加相关术语
        elif any(term in query_lower for term in ['character', 'class', 'hero', '角色', '职业', '英雄']):
            optimized_words.extend(['class', 'hero'])
        
        # 清理多余空格并返回
        optimized = " ".join(optimized_words)
        return optimized if optimized.strip() else query
    
    def process_query(self, query: str) -> UnifiedQueryResult:
        """
        统一处理查询：翻译+重写+意图分析
        
        Args:
            query: 原始查询
            
        Returns:
            UnifiedQueryResult: 统一处理结果
        """
        print(f"🔄 [QUERY-DEBUG] 开始统一查询处理: '{query}'")
        
        start_time = time.time()
        self.stats["total_queries"] += 1
        
        # 检查缓存
        cached_result = self._get_cached_result(query)
        if cached_result:
            print(f"💾 [QUERY-DEBUG] 使用缓存结果")
            print(f"   - 原始查询: '{cached_result.original_query}'")
            print(f"   - 翻译结果: '{cached_result.translated_query}'")
            print(f"   - 重写结果: '{cached_result.rewritten_query}'")
            print(f"   - BM25优化: '{cached_result.bm25_optimized_query}'")
            print(f"   - 意图: {cached_result.intent} (置信度: {cached_result.confidence:.3f})")
            logger.info(f"使用缓存结果: {query}")
            return cached_result
        
        # 如果LLM不可用，使用基础处理
        if not self.llm_client:
            print(f"⚠️ [QUERY-DEBUG] LLM不可用，使用基础处理")
            result = self._basic_processing(query)
            print(f"   - 检测语言: {result.detected_language}")
            print(f"   - 意图: {result.intent} (置信度: {result.confidence:.3f})")
            print(f"   - 重写查询: '{result.rewritten_query}'")
            print(f"   - BM25优化: '{result.bm25_optimized_query}'")
            print(f"   - 重写应用: {result.rewrite_applied}")
            self._cache_result(query, result)
            return result
        
        try:
            # 使用LLM进行统一处理
            print(f"🤖 [QUERY-DEBUG] 调用LLM进行统一处理")
            prompt = self._create_unified_prompt(query)
            print(f"   - 使用模型: {self.llm_config.model}")
            print(f"   - 提示词长度: {len(prompt)} 字符")
            
            llm_response = self._call_llm_with_retry(prompt)
            
            if llm_response:
                # 解析LLM响应
                detected_language = llm_response.get("detected_language", "en")
                translated_query = llm_response.get("translated_query", query)
                rewritten_query = llm_response.get("rewritten_query", translated_query)
                
                processing_time = time.time() - start_time
                
                print(f"✅ [QUERY-DEBUG] LLM处理成功:")
                print(f"   - 检测语言: {detected_language}")
                print(f"   - 翻译结果: '{translated_query}'")
                print(f"   - 重写结果: '{rewritten_query}'")
                print(f"   - BM25优化: '{llm_response.get('bm25_optimized_query', rewritten_query)}'")
                print(f"   - 意图: {llm_response.get('intent', 'guide')} (置信度: {llm_response.get('confidence', 0.7):.3f})")
                print(f"   - 搜索类型: {llm_response.get('search_type', 'hybrid')}")
                print(f"   - 处理时间: {processing_time:.3f}秒")
                print(f"   - 推理过程: {llm_response.get('reasoning', 'LLM统一处理')}")
                
                result = UnifiedQueryResult(
                    original_query=query,
                    detected_language=detected_language,
                    translated_query=translated_query,
                    rewritten_query=rewritten_query,
                    bm25_optimized_query=llm_response.get("bm25_optimized_query", rewritten_query), # LLM处理不优化
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
                print(f"❌ [QUERY-DEBUG] LLM调用失败，使用基础处理")
                result = self._basic_processing(query)
                print(f"   - 检测语言: {result.detected_language}")
                print(f"   - 意图: {result.intent} (置信度: {result.confidence:.3f})")
                print(f"   - 重写查询: '{result.rewritten_query}'")
                print(f"   - BM25优化: '{result.bm25_optimized_query}'")
                print(f"   - 重写应用: {result.rewrite_applied}")
                self.stats["failed_processing"] += 1
                logger.warning(f"LLM统一处理失败，使用基础处理: {query}")
                
        except Exception as e:
            print(f"❌ [QUERY-DEBUG] 统一处理异常: {e}")
            logger.error(f"统一处理异常: {e}")
            result = self._basic_processing(query)
            print(f"   - 降级到基础处理")
            print(f"   - 检测语言: {result.detected_language}")
            print(f"   - 意图: {result.intent} (置信度: {result.confidence:.3f})")
            print(f"   - 重写查询: '{result.rewritten_query}'")
            print(f"   - BM25优化: '{result.bm25_optimized_query}'")
            self.stats["failed_processing"] += 1
        
        # 更新平均处理时间
        self.stats["average_processing_time"] = (
            (self.stats["average_processing_time"] * (self.stats["total_queries"] - 1) + 
             result.processing_time) / self.stats["total_queries"]
        )
        
        print(f"📊 [QUERY-DEBUG] 查询处理完成，缓存结果")
        print(f"   - 总查询数: {self.stats['total_queries']}")
        print(f"   - 缓存命中数: {self.stats['cache_hits']}")
        print(f"   - 成功处理数: {self.stats['successful_processing']}")
        print(f"   - 失败处理数: {self.stats['failed_processing']}")
        
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