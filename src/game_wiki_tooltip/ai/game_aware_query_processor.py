"""
游戏感知的统一查询处理器 - 结合游戏上下文的一次LLM调用
==============================================================

通过单次LLM调用完成：
1. 中文翻译成英文（如果需要）
2. 意图判断（wiki vs 攻略）
3. 结合游戏名称重写查询（针对Google搜索或RAG搜索优化）
"""

import json
import hashlib
import time
import logging
from typing import Dict, Any, Optional, Literal, List
from dataclasses import dataclass, field
from pathlib import Path

from ..config import LLMConfig

logger = logging.getLogger(__name__)

@dataclass
class GameAwareQueryResult:
    """游戏感知查询处理结果"""
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
    
    # 游戏相关信息
    game_name: Optional[str] = None
    game_context: Dict[str, Any] = field(default_factory=dict)
    search_optimization: str = "hybrid"  # "google", "rag", "hybrid"
    
    # 扩展信息
    suggested_keywords: List[str] = field(default_factory=list)
    alternative_queries: List[str] = field(default_factory=list)

class GameAwareQueryProcessor:
    """游戏感知的统一查询处理器"""
    
    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self.llm_config = llm_config or LLMConfig()
        self.llm_client = None
        
        # 缓存机制（包含游戏上下文）
        self.query_cache = {}
        
        # 游戏特定知识库
        self.game_knowledge = self._load_game_knowledge()
        
        # 统计信息
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "successful_processing": 0,
            "failed_processing": 0,
            "average_processing_time": 0.0,
            "games_processed": set()
        }
        
        # 初始化LLM客户端
        if self.llm_config.is_valid():
            self._initialize_llm_client()
        else:
            logger.warning("LLM配置无效，将使用基础处理模式")
    
    def _load_game_knowledge(self) -> Dict[str, Any]:
        """加载游戏特定知识库"""
        try:
            # 加载游戏配置
            from ..assets import package_file
            games_config_path = package_file("games.json")
            
            if games_config_path.exists():
                with open(games_config_path, 'r', encoding='utf-8') as f:
                    games_config = json.load(f)
                    
                # 构建游戏知识库
                knowledge = {}
                for game_name, config in games_config.items():
                    knowledge[game_name.lower()] = {
                        "base_url": config.get("BaseUrl", ""),
                        "needs_search": config.get("NeedsSearch", True),
                        "wiki_type": self._detect_wiki_type(config.get("BaseUrl", "")),
                        "common_terms": self._get_common_terms(game_name),
                        "search_tips": self._get_search_tips(game_name)
                    }
                
                logger.info(f"加载了 {len(knowledge)} 个游戏的知识库")
                return knowledge
            else:
                logger.warning("未找到游戏配置文件")
                return {}
                
        except Exception as e:
            logger.error(f"加载游戏知识库失败: {e}")
            return {}
    
    def _detect_wiki_type(self, base_url: str) -> str:
        """检测Wiki类型"""
        if "huijiwiki.com" in base_url:
            return "huijiwiki"
        elif "kiranico.com" in base_url:
            return "kiranico"
        elif "gamertw.com" in base_url:
            return "gamertw"
        else:
            return "generic"
    
    def _get_common_terms(self, game_name: str) -> List[str]:
        """获取游戏常见术语"""
        common_terms_mapping = {
            "VALORANT": ["瓦洛兰特", "英雄联盟", "特工", "技能", "地图", "武器", "皮肤"],
            "Counter-Strike 2": ["反恐精英", "CS2", "武器", "地图", "皮肤", "战术"],
            "Don't Starve Together": ["饥荒", "联机版", "角色", "生存", "合成", "食物", "季节"],
            "Monster Hunter": ["怪物猎人", "武器", "装备", "怪物", "素材", "任务"],
            "Stardew Valley": ["星露谷物语", "农场", "作物", "NPC", "季节", "矿物", "钓鱼"]
        }
        
        game_lower = game_name.lower()
        for key, terms in common_terms_mapping.items():
            if key.lower() in game_lower:
                return terms
        return []
    
    def _get_search_tips(self, game_name: str) -> List[str]:
        """获取搜索建议"""
        tips_mapping = {
            "VALORANT": ["使用英文关键词效果更好", "可搜索特工名称+技能", "地图名称+策略"],
            "Don't Starve Together": ["可搜索角色名称+攻略", "物品名称+合成", "生存技巧"],
            "Monster Hunter": ["可搜索怪物名称+攻略", "武器名称+配装", "素材获取方法"]
        }
        
        game_lower = game_name.lower()
        for key, tips in tips_mapping.items():
            if key.lower() in game_lower:
                return tips
        return ["使用具体的物品或角色名称", "添加'攻略'或'指南'关键词"]
    
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
                
            logger.info(f"游戏感知查询处理器初始化成功，模型: {self.llm_config.model}")
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
    
    def _generate_cache_key(self, query: str, game_name: Optional[str] = None) -> str:
        """生成缓存键（包含游戏信息）"""
        cache_content = f"{query}_{game_name}_{self.llm_config.model}"
        return hashlib.md5(cache_content.encode()).hexdigest()
    
    def _get_cached_result(self, query: str, game_name: Optional[str] = None) -> Optional[GameAwareQueryResult]:
        """获取缓存的结果"""
        if not self.llm_config.enable_cache:
            return None
            
        cache_key = self._generate_cache_key(query, game_name)
        if cache_key in self.query_cache:
            cached_data, timestamp = self.query_cache[cache_key]
            if time.time() - timestamp < self.llm_config.cache_ttl:
                self.stats["cache_hits"] += 1
                return cached_data
            else:
                del self.query_cache[cache_key]
        return None
    
    def _cache_result(self, query: str, result: GameAwareQueryResult):
        """缓存结果"""
        if not self.llm_config.enable_cache:
            return
            
        cache_key = self._generate_cache_key(query, result.game_name)
        self.query_cache[cache_key] = (result, time.time())
    
    def _create_game_aware_prompt(self, query: str, game_name: Optional[str] = None) -> str:
        """创建游戏感知的统一处理提示词"""
        
        # 获取游戏特定信息
        game_info = ""
        if game_name:
            game_knowledge = self.game_knowledge.get(game_name.lower(), {})
            if game_knowledge:
                game_info = f"""
**游戏上下文信息：**
- 游戏名称: {game_name}
- Wiki类型: {game_knowledge.get('wiki_type', 'generic')}
- 常见术语: {', '.join(game_knowledge.get('common_terms', []))}
- 搜索建议: {', '.join(game_knowledge.get('search_tips', []))}
"""
        
        prompt = f"""你是一个专业的游戏Wiki和攻略搜索助手。你需要分析用户的查询，并在一次响应中完成以下三个任务：

1. **语言检测和翻译**：如果查询是中文，翻译为英文
2. **意图判断**：判断用户是想查询wiki信息还是攻略指南
3. **查询重写**：根据游戏上下文优化查询，使其更适合搜索

**用户查询：** "{query}"

{game_info}

**请提供JSON格式的响应：**
```json
{{
    "detected_language": "zh|en|other",
    "translated_query": "英文翻译（如果需要）或原查询",
    "intent": "wiki|guide|unknown",
    "confidence": 0.0-1.0,
    "rewritten_query": "优化后的搜索查询",
    "search_type": "google|rag|hybrid",
    "reasoning": "分析和优化的详细说明",
    "search_optimization": "google|rag|hybrid",
    "suggested_keywords": ["关键词1", "关键词2"],
    "alternative_queries": ["备选查询1", "备选查询2"]
}}
```

**任务详细说明：**

**1. 语言检测和翻译**
- 如果>30%字符是中文（\\u4e00-\\u9fff），标记为"zh"
- 如果是中文，提供准确的英文翻译，特别注意游戏术语
- 保持原意不变，不要添加不存在的信息

**2. 意图判断**
- **wiki**: 用户想要查询具体信息、定义、属性、数据
  - 例子："{game_name or '游戏'}中什么是巫师"、"武器伤害"、"角色属性"
  - 关键词：what is、info、stats、damage、属性、数据、伤害
  
- **guide**: 用户想要策略、推荐、攻略、教程
  - 例子："{game_name or '游戏'}怎么打boss"、"最佳配装"、"推荐下一个解锁什么"
  - 关键词：how、best、recommend、next、怎么、推荐、攻略
  - 特别注意：询问"下一个"、"推荐"、"选择"的都是guide意图

**3. 查询重写和优化**
- **wiki意图**：保持原始查询不变，不进行重写（用户的原始输入往往最准确）
- **guide意图**：进行优化重写，添加相关关键词提高搜索效果
- **游戏术语优化**：仅对guide查询使用游戏中的标准术语
- **搜索类型选择**：
  - "google": 适合在线搜索的查询
  - "rag": 适合向量搜索的查询（重点是概念和关键词）
  - "hybrid": 两者都适合

**特殊规则：**
- **wiki意图**：rewritten_query应该与translated_query相同，不添加额外内容
- **guide意图**：可以适当添加相关关键词，如"guide"、"strategy"、"tips"等
- 对于推荐类查询，优先考虑为guide意图
- 对于"什么是"类查询，优先考虑为wiki意图
- 如果没有游戏上下文，保持查询的通用性

**示例（针对{game_name or '某游戏'}）：**
- 输入："法师职业介绍" → wiki意图，重写："mage class introduction"（保持简洁）
- 输入："怎么打最终boss" → guide意图，重写："final boss strategy guide tips"
- 输入："推荐下一个解锁什么" → guide意图，重写："next unlock recommendation progression guide"

请严格按照JSON格式回复，不要包含其他内容。"""
        
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
                logger.warning(f"游戏感知LLM调用失败 (尝试 {attempt + 1}/{self.llm_config.max_retries}): {e}")
                if attempt < self.llm_config.max_retries - 1:
                    time.sleep(self.llm_config.retry_delay * (2 ** attempt))
                
        return None
    
    def _basic_processing(self, query: str, game_name: Optional[str] = None) -> GameAwareQueryResult:
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
        
        # 基础重写 - 根据意图处理
        rewritten_query = query
        
        # 根据意图进行不同的处理
        if intent == "wiki":
            # wiki意图：保持原始查询不变，不添加额外内容
            rewritten_query = query
        elif intent == "guide":
            # guide意图：进行优化重写
            if game_name and game_name.lower() not in query.lower():
                rewritten_query = f"{game_name} {query}"
            
            if not any(word in rewritten_query.lower() for word in ["guide", "strategy", "tips", "攻略"]):
                rewritten_query += " guide"
        
        return GameAwareQueryResult(
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
            processing_time=0.001,
            game_name=game_name,
            game_context=self.game_knowledge.get(game_name.lower(), {}) if game_name else {},
            search_optimization="hybrid"
        )
    
    def process_query(self, query: str, game_name: Optional[str] = None) -> GameAwareQueryResult:
        """
        游戏感知的统一查询处理
        
        Args:
            query: 原始查询
            game_name: 游戏名称（可选）
            
        Returns:
            GameAwareQueryResult: 游戏感知处理结果
        """
        start_time = time.time()
        self.stats["total_queries"] += 1
        
        if game_name:
            self.stats["games_processed"].add(game_name.lower())
        
        # 检查缓存
        cached_result = self._get_cached_result(query, game_name)
        if cached_result:
            logger.info(f"使用缓存结果: {query} (游戏: {game_name})")
            return cached_result
        
        # 如果LLM不可用，使用基础处理
        if not self.llm_client:
            result = self._basic_processing(query, game_name)
            self._cache_result(query, result)
            return result
        
        try:
            # 使用LLM进行游戏感知处理
            prompt = self._create_game_aware_prompt(query, game_name)
            llm_response = self._call_llm_with_retry(prompt)
            
            if llm_response:
                # 解析LLM响应
                detected_language = llm_response.get("detected_language", "en")
                translated_query = llm_response.get("translated_query", query)
                rewritten_query = llm_response.get("rewritten_query", translated_query)
                
                processing_time = time.time() - start_time
                
                result = GameAwareQueryResult(
                    original_query=query,
                    detected_language=detected_language,
                    translated_query=translated_query,
                    rewritten_query=rewritten_query,
                    intent=llm_response.get("intent", "guide"),
                    confidence=llm_response.get("confidence", 0.7),
                    search_type=llm_response.get("search_type", "hybrid"),
                    reasoning=llm_response.get("reasoning", "游戏感知LLM处理"),
                    translation_applied=translated_query != query,
                    rewrite_applied=rewritten_query != translated_query,
                    processing_time=processing_time,
                    game_name=game_name,
                    game_context=self.game_knowledge.get(game_name.lower(), {}) if game_name else {},
                    search_optimization=llm_response.get("search_optimization", "hybrid"),
                    suggested_keywords=llm_response.get("suggested_keywords", []),
                    alternative_queries=llm_response.get("alternative_queries", [])
                )
                
                self.stats["successful_processing"] += 1
                logger.info(f"游戏感知处理成功: '{query}' (游戏: {game_name}) -> 翻译: '{translated_query}' -> 重写: '{rewritten_query}'")
                
            else:
                # LLM调用失败，使用基础处理
                result = self._basic_processing(query, game_name)
                self.stats["failed_processing"] += 1
                logger.warning(f"游戏感知LLM处理失败，使用基础处理: {query}")
                
        except Exception as e:
            logger.error(f"游戏感知处理异常: {e}")
            result = self._basic_processing(query, game_name)
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
        stats = self.stats.copy()
        stats["games_processed"] = list(stats["games_processed"])
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "successful_processing": 0,
            "failed_processing": 0,
            "average_processing_time": 0.0,
            "games_processed": set()
        }

# 全局实例
_game_aware_processor = None

def get_game_aware_processor(llm_config: Optional[LLMConfig] = None) -> GameAwareQueryProcessor:
    """获取游戏感知查询处理器的单例实例"""
    global _game_aware_processor
    if _game_aware_processor is None:
        _game_aware_processor = GameAwareQueryProcessor(llm_config=llm_config)
    return _game_aware_processor

def process_game_aware_query(
    query: str, 
    game_name: Optional[str] = None,
    llm_config: Optional[LLMConfig] = None
) -> GameAwareQueryResult:
    """
    游戏感知查询处理的便捷函数
    
    Args:
        query: 用户查询
        game_name: 游戏名称
        llm_config: LLM配置
        
    Returns:
        GameAwareQueryResult: 处理结果
    """
    processor = get_game_aware_processor(llm_config)
    return processor.process_query(query, game_name)
