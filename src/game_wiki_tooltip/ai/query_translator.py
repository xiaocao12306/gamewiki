"""
查询翻译器 - 提高跨语言搜索效果
=====================================

将中文查询翻译为英文，以提高与英文知识库的匹配度
"""

import logging
from typing import Optional
from ..config import LLMConfig

logger = logging.getLogger(__name__)

class QueryTranslator:
    """查询翻译器"""
    
    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self.llm_config = llm_config or LLMConfig()
        self.llm_client = None
        
        # 初始化LLM客户端
        if self.llm_config.is_valid():
            self._initialize_llm_client()
        
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
                max_output_tokens=200,
                temperature=0.1,
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
    
    def detect_language(self, text: str) -> str:
        """检测文本语言"""
        # 简单的语言检测
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        total_chars = len(text)
        
        if chinese_chars / total_chars > 0.3:  # 30%以上是中文字符
            return "zh"
        else:
            return "en"
    
    def translate_query(self, query: str, target_language: str = "en") -> str:
        """
        翻译查询
        
        Args:
            query: 原始查询
            target_language: 目标语言（默认英文）
            
        Returns:
            翻译后的查询
        """
        source_lang = self.detect_language(query)
        
        # 如果已经是目标语言，直接返回
        if source_lang == target_language:
            return query
        
        # 如果没有LLM客户端，返回原查询
        if not self.llm_client:
            logger.warning("LLM客户端未初始化，无法翻译查询")
            return query
        
        try:
            # 构建翻译提示
            if source_lang == "zh" and target_language == "en":
                prompt = f"""
请将以下中文查询翻译成英文，保持原意不变，特别注意游戏术语的准确翻译：

中文查询: {query}

要求：
1. 保持原意不变
2. 游戏术语要准确翻译
3. 只返回翻译结果，不要其他解释

英文翻译:"""
            else:
                prompt = f"Please translate the following text to {target_language}: {query}"
            
            # 调用LLM翻译
            if "gemini" in self.llm_config.model.lower():
                response = self.llm_client.generate_content(prompt)
                translation = response.text.strip()
            elif "gpt" in self.llm_config.model.lower():
                response = self.llm_client.chat.completions.create(
                    model=self.llm_config.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200,
                    temperature=0.1
                )
                translation = response.choices[0].message.content.strip()
            else:
                return query
            
            logger.info(f"查询翻译: '{query}' -> '{translation}'")
            return translation
            
        except Exception as e:
            logger.error(f"查询翻译失败: {e}")
            return query

# 全局实例
_query_translator = None

def get_query_translator(llm_config: Optional[LLMConfig] = None) -> QueryTranslator:
    """获取查询翻译器的单例实例"""
    global _query_translator
    if _query_translator is None:
        _query_translator = QueryTranslator(llm_config=llm_config)
    return _query_translator

def translate_query_if_needed(query: str, llm_config: Optional[LLMConfig] = None) -> str:
    """
    如果需要的话翻译查询
    
    Args:
        query: 原始查询
        llm_config: LLM配置
        
    Returns:
        翻译后的查询（如果需要）
    """
    translator = get_query_translator(llm_config)
    return translator.translate_query(query) 