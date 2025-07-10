"""
Gemini Flash 2.5 Lite Summarizer for RAG-retrieved knowledge chunks
"""
import os
import logging
from typing import List, Dict, Optional, Any
import google.generativeai as genai
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SummarizationConfig:
    """Configuration for Gemini summarization"""
    api_key: str
    model_name: str = "gemini-2.5-flash-lite-preview-06-17"
    max_summary_length: int = 300
    temperature: float = 0.3
    include_sources: bool = True
    language: str = "auto"  # auto, zh, en


class GeminiSummarizer:
    """Summarizes multiple knowledge chunks using Gemini Flash 2.5 Lite"""
    
    def __init__(self, config: SummarizationConfig):
        """Initialize Gemini summarizer with configuration"""
        self.config = config
        
        # Configure Gemini API
        genai.configure(api_key=config.api_key)
        
        # Initialize model with safety settings
        self.model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": config.temperature,
                "max_output_tokens": config.max_summary_length * 2,  # Allow some buffer
            }
        )
        
        logger.info(f"Initialized GeminiSummarizer with model: {config.model_name}")
    
    def summarize_chunks(
        self, 
        chunks: List[Dict[str, Any]], 
        query: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Summarize multiple knowledge chunks into a coherent answer
        
        Args:
            chunks: List of retrieved chunks with content and metadata
            query: Original user query
            context: Optional game context
            
        Returns:
            Dictionary with summary and metadata
        """
        if not chunks:
            return {
                "summary": "No relevant information found.",
                "chunks_used": 0,
                "sources": []
            }
        
        try:
            # Build the summarization prompt
            prompt = self._build_summarization_prompt(chunks, query, context)
            
            # Generate summary
            response = self.model.generate_content(prompt)
            
            # Parse and format the response
            return self._format_summary_response(response.text, chunks)
            
        except Exception as e:
            logger.error(f"Error in summarization: {str(e)}")
            # Fallback to simple concatenation
            return self._fallback_summary(chunks, query)
    
    def _build_summarization_prompt(
        self, 
        chunks: List[Dict[str, Any]], 
        query: str,
        context: Optional[str] = None
    ) -> str:
        """Build the prompt for Gemini summarization"""
        
        # Detect language from query or use config
        language = self._detect_language(query) if self.config.language == "auto" else self.config.language
        
        # Format chunks for the prompt
        chunks_text = self._format_chunks_for_prompt(chunks)
        
        # Build language-specific prompt
        if language == "zh":
            prompt = f"""你是一个友好的游戏攻略助手。请根据检索到的游戏信息，为玩家提供一个对话式的回答。

玩家说：{query}

相关游戏信息：
{chunks_text}

回答要求：
1. **首先筛选信息**：仔细分析哪些信息块真正与玩家问题相关，忽略不相关的内容
2. **配装细节**：如果涉及装备配置、build、套装等内容，必须提供具体的装备名称、属性数值、搭配理由，不要只说配装名称
3. 用友好、对话的语气回答，就像在和朋友聊天
4. 如果是推荐类问题，明确给出推荐顺序和理由
5. 保持简洁，重点突出（{self.config.max_summary_length}字以内）
6. 可以使用表情符号让回答更生动
7. 用"推荐："、"提示："等标记重要信息

注意：只基于真正相关的信息回答，如果某个信息块与问题无关就不要使用它。

你的回答："""
        else:
            prompt = f"""You are a friendly game guide assistant. Based on the retrieved game information, provide a conversational response to the player.

Player says: {query}

Related game information:
{chunks_text}

Response requirements:
1. **Filter information first**: Carefully analyze which information chunks are truly relevant to the player's question, ignore irrelevant content
2. **Build details**: For equipment builds, loadouts, or gear configurations, provide specific item names, stat values, and synergy explanations, not just build names
3. Use a friendly, conversational tone like chatting with a friend
4. For recommendation questions, clearly state the order and reasons
5. Keep it concise and focused (within {self.config.max_summary_length} words)
6. Use emoji to make the response more engaging
7. Use markers like "Recommendation:", "Tip:" for important info

Note: Only answer based on truly relevant information. If an information chunk is unrelated to the question, don't use it.

Your response:"""
        
        return prompt
    
    def _format_chunks_for_prompt(self, chunks: List[Dict[str, Any]]) -> str:
        """Format chunks for inclusion in the prompt"""
        formatted_chunks = []
        
        for i, chunk in enumerate(chunks, 1):
            # Extract relevant information from chunk
            topic = chunk.get("topic", "Unknown Topic")
            summary = chunk.get("summary", chunk.get("content", ""))
            keywords = chunk.get("keywords", [])
            
            # Format individual chunk
            chunk_text = f"""
[知识块 {i}] {topic}
内容：{summary}
关键词：{', '.join(keywords) if keywords else 'N/A'}
相关度分数：{chunk.get('score', 0):.2f}
"""
            formatted_chunks.append(chunk_text.strip())
        
        return "\n\n".join(formatted_chunks)
    
    def _format_summary_response(
        self, 
        summary_text: str, 
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Format the summary response with metadata"""
        
        # Extract source references if present
        sources = []
        if self.config.include_sources:
            # Extract chunk indices used in summary
            for i, chunk in enumerate(chunks, 1):
                if any(keyword in summary_text for keyword in chunk.get("keywords", [])):
                    sources.append({
                        "index": i,
                        "topic": chunk.get("topic", ""),
                        "score": chunk.get("score", 0)
                    })
        
        return {
            "summary": summary_text.strip(),
            "chunks_used": len(chunks),
            "sources": sources,
            "model": self.config.model_name,
            "language": self._detect_language(summary_text)
        }
    
    def _fallback_summary(
        self, 
        chunks: List[Dict[str, Any]], 
        query: str
    ) -> Dict[str, Any]:
        """Fallback summary when Gemini fails"""
        # Simple concatenation of top chunks
        summary_parts = []
        
        for i, chunk in enumerate(chunks[:3], 1):  # Use top 3 chunks
            topic = chunk.get("topic", "")
            content = chunk.get("summary", chunk.get("content", ""))
            
            if topic:
                summary_parts.append(f"{topic}: {content}")
            else:
                summary_parts.append(content)
        
        summary = "\n\n".join(summary_parts)
        
        return {
            "summary": summary,
            "chunks_used": min(3, len(chunks)),
            "sources": [{"index": i+1, "topic": c.get("topic", "")} for i, c in enumerate(chunks[:3])],
            "model": "fallback",
            "language": self._detect_language(summary)
        }
    
    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character composition"""
        # Check for Chinese characters
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        
        if chinese_chars > len(text) * 0.3:  # If more than 30% Chinese
            return "zh"
        else:
            return "en"


# Convenience function for creating summarizer
def create_gemini_summarizer(
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.5-flash-lite-preview-06-17",
    **kwargs
) -> GeminiSummarizer:
    """
    Create a Gemini summarizer instance
    
    Args:
        api_key: Gemini API key (defaults to env var GEMINI_API_KEY)
        model_name: Model to use
        **kwargs: Additional config parameters
        
    Returns:
        GeminiSummarizer instance
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not provided and GEMINI_API_KEY env var not set")
    
    config = SummarizationConfig(
        api_key=api_key,
        model_name=model_name,
        **kwargs
    )
    
    return GeminiSummarizer(config)