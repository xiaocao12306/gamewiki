"""
Gemini Flash 2.5 Lite Summarizer for RAG-retrieved knowledge chunks
"""
import os
import json
import logging
from typing import List, Dict, Optional, Any, AsyncGenerator
from google import genai
from google.genai import types
from dataclasses import dataclass
from pathlib import Path

# Import i18n for internationalization
from src.game_wiki_tooltip.core.i18n import t
from .rag_config import RAGConfig, SummarizationConfig

logger = logging.getLogger(__name__)


class GeminiSummarizer:
    """Summarizes multiple knowledge chunks using Gemini Flash 2.5 Lite"""
    
    def __init__(self, config: SummarizationConfig = None, rag_config: RAGConfig = None):
        """Initialize Gemini summarizer with configuration"""
        # Use RAGConfig if provided, otherwise use SummarizationConfig
        if rag_config:
            self.rag_config = rag_config
            self.llm_config = rag_config.llm_settings  # Store LLM config for language settings
            # Extract settings from RAGConfig
            # Use api_key from config or fallback to LLM settings
            api_key = rag_config.summarization.api_key or rag_config.llm_settings.get_api_key()
            
            # Create config from RAGConfig settings
            self.config = rag_config.summarization
            self.config.api_key = api_key
        else:
            self.config = config
            self.rag_config = None
            self.llm_config = None
        
        # API key will be used when creating the client instance
        # Model will be configured per request using the client API
        
        logger.info(f"Initialized GeminiSummarizer with model: {self.config.model_name}")
    
    async def summarize_chunks_stream(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        original_query: Optional[str] = None,
        context: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streaming summary generation, using real Gemini streaming API
        
        Args:
            chunks: Retrieved knowledge chunks
            query: Processed query
            original_query: Original query
            context: Game context
            
        Yields:
            Streaming fragments of summary content
        """
        print(f"🌊 [STREAM-DEBUG] Start streaming summary generation")
        print(f"   - Knowledge chunk count: {len(chunks)}")
        print(f"   - Query: {query}")
        if original_query and original_query != query:
            print(f"   - Original query: {original_query}")
        print(f"   - Game context: {context}")
        
        # Store game context for video source extraction
        if context:
            self.current_game_name = context
            print(f"🎮 [STREAM-DEBUG] Stored game name: {self.current_game_name}")
        else:
            print(f"⚠️ [STREAM-DEBUG] No context provided, game name not stored")
        
        if not chunks:
            yield "Sorry, no relevant game information found."
            return
            
        try:
            print(f"🚀 [STREAM-DEBUG] Calling Gemini streaming API")
            
            # Use LLM config response language if available, otherwise detect from query
            if self.llm_config and hasattr(self.llm_config, 'response_language') and self.llm_config.response_language != "auto":
                language = self.llm_config.response_language
                logger.info(f"🌐 Using LLM config response language for AI reply: {language}")
            else:
                language = self._detect_language(query) if self.config.language == "auto" else self.config.language
                logger.info(f"🌐 Using detected/fallback language for AI reply: {language}")
            
            # Build system instruction
            system_instruction = self._build_system_instruction(language)
            
            # Build prompt
            prompt = self._build_summarization_prompt(chunks, query, original_query, context)
            
            # For collecting complete response text to extract video sources
            complete_response = ""
            
            # Use new Client API for streaming calls
            try:
                # Configure the client
                client = genai.Client(api_key=self.config.api_key)
                
                # Configure Google Search tool if enabled
                tools = []
                if self.config.enable_google_search:
                    logger.debug("Enabling Google Search tool")
                    grounding_tool = types.Tool(
                        google_search=types.GoogleSearch()
                    )
                    tools = [grounding_tool]
                
                # Build config with system instruction
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools if tools else None,
                    temperature=self.config.temperature,
                    thinking_config=types.ThinkingConfig(thinking_budget=self.config.thinking_budget)
                )
                
                # Stream content generation
                response = client.models.generate_content_stream(
                    model=self.config.model_name,
                    contents=[prompt],
                    config=config
                )
            
                logger.debug("Started receiving streaming response")
                
                # Real-time streaming content output
                for chunk in response:
                    if chunk.text:
                        logger.debug(f"Received streaming chunk: {len(chunk.text)} characters")
                        complete_response += chunk.text
                        yield chunk.text
                    
                logger.debug("Streaming response completed")
                
                # After streaming output completes, add video source information
                logger.debug("Streaming output completed, starting video source extraction")
                video_sources_text = self._extract_video_sources(chunks, complete_response)
                if video_sources_text:
                    logger.debug("Found video sources, adding to streaming output")
                    # Add separator to ensure proper identification
                    separator = "\n\n---\n"
                    yield separator + video_sources_text
                else:
                    logger.debug("No video sources found")
                        
            except Exception as e:
                logger.error(f"Streaming API call failed: {e}")
                logger.debug(f"Fallback to sync method")
                
                # Check if it's an API key issue
                error_msg = str(e).lower()
                if 'api_key' in error_msg or 'authentication' in error_msg or 'unauthorized' in error_msg or 'inputs argument' in error_msg:
                    logger.debug("Detected API key related error")
                    yield "API key configuration issue, please check if Gemini API key is correctly configured.\n\n"
                    return
                else:
                    yield f"An error occurred while generating response: {str(e)}\n\n"
                    return
                    
        except Exception as e:
            logger.error(f"Overall streaming process failed: {e}")
            yield f"An error occurred during content generation: {str(e)}\n\n"
            return
    
    def _build_system_instruction(self, language: str = "auto") -> str:
        """Build system instruction for Gemini"""
        # Use LLM config response language if available
        if self.llm_config and hasattr(self.llm_config, 'response_language') and self.llm_config.response_language != "auto":
            language = self.llm_config.response_language
            logger.debug(f"Using LLM config response language: {language}")
        elif language == "auto":
            language = "en"  # Default to English if no config available
        
        if language == "zh":
            return """你是一个专业的游戏攻略助手。你的任务是基于提供的游戏知识库内容，为玩家提供准确、有用的游戏攻略信息。

回答指南：
1. **开头必须提供一句话总结**：在正式回答之前，用一句话概括答案要点（例如："💡 **总结**：推荐使用火箭筒配合重装甲来对付这个BOSS"）
2. **理解JSON结构**：每个知识块包含topic、summary、keywords、type、score等基础信息，以及structured_data详细数据
3. **双查询理解**：
   - 检索查询帮助你理解"召回思路"，判断哪些段落最相关
   - 原始查询帮助你决定回答的措辞、详细程度、写作风格，避免"语义漂移"
4. **充分利用提供的json chunks**：
   - 如果你认为某一主题的json能够有效的回答用户的问题，那么你需要充分的使用chunk中的structured_data内容，例如在装备推荐中，你**必须**列举所有的装备信息，包括主武器，副武器和其他被提及的装备
5. **智能判断回答详细程度**：
   - 仔细分析[原始查询]中的表述，理解用户期望的回答长度
   - 如果用户要求"一句话"、"简短"、"简要"等，提供简洁答案
   - 如果用户询问"为什么"、"如何"、"详细解释"等，提供完整深入的回答
   - 如果没有明确要求，根据问题复杂度提供适中长度的回答
6. **利用structured_data**：优先使用结构化数据中的具体数值、名称、配置等信息
7. **Google搜索使用指南**：
   - 必须在进行回答前主动使用Google搜索工具收集[game context]下的[原始查询]的相关信息
   - 如果用户询问的内容明显超出知识库范围（如游戏机制外的内容），使用Google搜索
   - 结合知识库和Google搜索结果提供全面答案

格式要求：
• 开头先给出一句话总结（用💡标记）
• 不要添加任何寒暄或开场白（如"我来帮你..."、"好的，让我..."）
• 如果提供的知识块足以回答问题，直接给出答案
• 如果使用了Google搜索工具，在开头说明："我使用了Google搜索为你找到了以下信息"
• 严格按照[原始查询]的要求组织答案
• 使用友好的游戏术语
• 基于实际数据，不要编造信息
• **禁止引用标记**：绝对不要在回答中添加任何引用标记、参考编号或方括号索引（如[1]、[i]、[a]等）
• **多选项格式化**：当提供多个平行选项时（如不同的装备配置、策略等），使用编号列表保持一致的层级：
  1. 第一个选项：描述
     - 子项1
     - 子项2
  2. 第二个选项：描述
     - 子项1
     - 子项2"""
        else:
            return """You are a professional game guide assistant. Your task is to provide accurate and useful game strategy information to players based on the provided game knowledge base content.

Response guidelines:
1. **Start with a one-sentence summary**: Before the detailed answer, provide a one-sentence summary of the key points (e.g., "💡 **Summary**: Recommended to use rocket launcher with heavy armor against this boss")
2. **Understand JSON structure**: Each chunk contains topic, summary, keywords, type, score and structured_data details
3. **Dual query understanding**:
   - Retrieval query helps you understand the "recall approach" to judge which segments are most relevant
   - Original query helps you decide response wording, detail level, and writing style to avoid "semantic drift"
4. **Make full use of the provided JSON chunks**:
   - If you believe that a topic’s JSON can effectively answer the user’s question, you need to fully leverage the structured_data in that chunk. For example, when giving equipment recommendations, you must list **every piece** of gear mentioned, including the primary weapon, secondary weapon, and any other referenced equipment.
5. **Intelligently determine response detail level**:
   - Carefully analyze the wording in [Original Query] to understand the user's expected response length
   - If user asks for "one sentence", "brief", "short", etc., provide concise answer
   - If user asks "why", "how", "detailed explanation", etc., provide complete in-depth response
   - If no explicit requirement, provide moderate length response based on question complexity
6. **Utilize structured_data**: Prioritize specific values, names, configurations from structured data
7. **Google Search usage guide**:
   - You must use Google Search tool in every response to gather information about the [Original Query] related to the [game context]
   - If user asks about content clearly outside knowledge base scope (like non-game-mechanic content), use Google Search
   - Combine knowledge base and Google Search results to provide comprehensive answers

Format requirements:
• Start with a one-sentence summary (marked with 💡)
• Don't add any greetings or introductions (like "I'm ready to help...", "Okay, let me...")
• If knowledge chunks are sufficient, directly provide the answer
• If Google Search tool was used, mention at the beginning: "I used Google search to find the following information"
• Strictly follow the [Original Query] requirements
• Use friendly gaming terminology
• Base on actual data, don't fabricate information
• **No citation markers**: Never add any citation markers, reference numbers, or bracketed indices (like [1], [i], [a], etc.) in your response
• **Multiple options formatting**: When providing multiple parallel options (like different loadouts, strategies, etc.), use numbered lists to maintain consistent hierarchy:
  1. First option: description
     - Sub-item 1
     - Sub-item 2
  2. Second option: description
     - Sub-item 1
     - Sub-item 2"""
    
    def _build_summarization_prompt(
        self, 
        chunks: List[Dict[str, Any]], 
        query: str,
        original_query: Optional[str] = None,
        context: Optional[str] = None
    ) -> str:
        """Build the simplified prompt for Gemini summarization (guidelines moved to system instruction)"""
        
        # Detect language from query or use config
        language = self._detect_language(query) if self.config.language == "auto" else self.config.language
        
        # Format chunks as raw JSON for the prompt
        chunks_json = self._format_chunks_as_json(chunks)
        
        # Build language-specific prompt
        if language == "zh":
            # 构建查询信息部分
            query_section = f"[检索查询]: {query}  ← 用于判断哪些材料段落最相关"
            if original_query and original_query != query:
                query_section += f"\n[原始查询]: {original_query}  ← **关键**：必须严格按照此查询的格式要求回答"
            else:
                query_section = f"[用户查询]: {query}  ← **关键**：必须严格按照此查询的格式要求回答"
            
            prompt = f"""{query_section}
{f"游戏上下文：{context}" if context else ""}

可用的游戏知识块（JSON格式）：
{chunks_json}

请基于以上知识块回答用户的问题。"""
        else:
            # 构建查询信息部分
            query_section = f"[Retrieval Query]: {query}  ← for determining which material segments are most relevant"
            if original_query and original_query != query:
                query_section += f"\n[Original Query]: {original_query}  ← **CRITICAL**: You MUST strictly follow this query's format requirements"
            else:
                query_section = f"[User Query]: {query}  ← **CRITICAL**: You MUST strictly follow this query's format requirements"
            
            prompt = f"""{query_section}
{f"Game context: {context}" if context else ""}

Available game knowledge chunks (JSON format):
{chunks_json}

Please answer the user's question based on the above knowledge chunks."""
        
        return prompt
    
    def _format_chunks_as_json(self, chunks: List[Dict[str, Any]]) -> str:
        """Format chunks as clean JSON for the prompt - now preserving all original fields"""
        formatted_chunks = []
        
        for i, chunk in enumerate(chunks, 1):
            # Create a copy to avoid modifying original
            chunk_copy = chunk.copy()
            
            # Remove chunk_id to prevent LLM from adding references like [unique_id_002]
            chunk_copy.pop('chunk_id', None)
            
            # Remove other internal fields that are not useful for LLM
            internal_fields_to_remove = ['_internal_id', '_vector_id', '_index_id', 
                                       'video_url', 'video_title']  # Also remove video fields as they're handled separately
            for field in internal_fields_to_remove:
                chunk_copy.pop(field, None)
            
            # Ensure score is included if it exists
            if 'score' in chunk and 'relevance_score' not in chunk_copy:
                chunk_copy['relevance_score'] = chunk.get('score', 0)
            
            formatted_chunks.append(chunk_copy)
        
        try:
            return json.dumps(formatted_chunks, ensure_ascii=False, indent=2)
        except Exception as e:
            # Fallback to string representation if JSON serialization fails
            logger.warning(f"Failed to serialize chunks as JSON: {e}")
            return str(formatted_chunks)

    def _convert_timestamp_to_seconds(self, timestamp: str) -> int:
        """Convert MM:SS or HH:MM:SS format to seconds"""
        if not timestamp:
            return 0
        
        try:
            parts = timestamp.split(':')
            if len(parts) == 2:  # MM:SS
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:  # HH:MM:SS
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            return 0
        except (ValueError, AttributeError):
            return 0
    
    def _extract_video_sources(self, chunks: List[Dict[str, Any]], summary_text: str) -> str:
        """Extract video source information from chunks"""
        try:
            print(f"🎥 [VIDEO-DEBUG] Starting video source extraction")
            print(f"   - Number of chunks: {len(chunks)}")
            
            # Collect video sources directly from chunks
            video_sources = []  # List of {url, title, topic, start_seconds}
            seen_entries = set()  # Track unique video+topic+timestamp combinations
            
            for chunk in chunks:
                # Check if chunk has video information in the new format
                if 'video_url' in chunk and chunk['video_url']:
                    # Extract basic info
                    url = chunk['video_url']
                    title = chunk.get('video_title', 'Video Source')
                    topic = chunk.get('topic', '')
                    
                    # Extract timestamp if available
                    start_seconds = 0
                    if 'timestamp' in chunk and isinstance(chunk['timestamp'], dict) and 'start' in chunk['timestamp']:
                        start_seconds = self._convert_timestamp_to_seconds(chunk['timestamp']['start'])
                    
                    # Create unique key to avoid duplicates
                    unique_key = f"{topic}_{url}_{start_seconds}" if start_seconds else f"{topic}_{url}"
                    
                    if unique_key not in seen_entries:
                        seen_entries.add(unique_key)
                        
                        video_source = {
                            'url': url,
                            'title': title,
                            'topic': topic,
                            'start_seconds': start_seconds
                        }
                        
                        video_sources.append(video_source)
                        print(f"✅ [VIDEO-DEBUG] Found video source: {title} - {topic}")
            
            # Check if no video sources found
            if not video_sources:
                print(f"⚠️ [VIDEO-DEBUG] No video sources found in chunks")
                # Check if chunks are in old format
                if chunks and 'video_url' not in chunks[0]:
                    print(f"❌ [VIDEO-DEBUG] Chunks are in old format without video_url/video_title")
                    logger.warning("Chunks do not contain video information. Please rebuild vector index.")
                return ""
            
            print(f"📹 [VIDEO-DEBUG] Found {len(video_sources)} unique video sources")
            
            # Build the sources text
            sources_lines = ["---", "<small>", f"📺 **{t('video_sources_label')}**"]
            
            # Sort by topic for consistent ordering
            video_sources.sort(key=lambda x: x.get('topic', ''))
            
            # Format each video source
            for source in video_sources:
                topic = source.get("topic", "Video Source")
                url = source.get("url", "")
                
                # Add timestamp parameter for YouTube videos
                if "youtube.com" in url and source.get("start_seconds", 0) > 0:
                    # Append time parameter to URL
                    time_param = f"&t={source['start_seconds']}"
                    link_url = f"{url}{time_param}"
                else:
                    link_url = url
                
                # Create markdown link with topic as text
                sources_lines.append(f"- [{topic}]({link_url})")
            
            sources_lines.append("</small>")
            
            return "\n".join(sources_lines)
            
        except Exception as e:
            logger.error(f"Error extracting video sources: {e}")
            print(f"❌ [VIDEO-DEBUG] Error extracting video sources: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
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
    model_name: Optional[str] = None,
    enable_google_search: Optional[bool] = None,
    thinking_budget: Optional[int] = None,
    rag_config: Optional[RAGConfig] = None,
    **kwargs
) -> GeminiSummarizer:
    """
    Create a Gemini summarizer instance
    
    Args:
        api_key: Gemini API key (defaults to env var GEMINI_API_KEY)
        model_name: Model to use
        enable_google_search: Enable Google search tool (default: True)
        thinking_budget: Thinking budget for dynamic thinking (default: -1)
        **kwargs: Additional config parameters
        
    Returns:
        GeminiSummarizer instance
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not provided and GEMINI_API_KEY env var not set")
    
    # If RAGConfig is provided, use it
    if rag_config:
        return GeminiSummarizer(rag_config=rag_config)
    
    # Otherwise, use individual parameters
    # Build config dict with only provided values
    config_dict = {}
    if api_key is not None:
        config_dict['api_key'] = api_key
    if model_name is not None:
        config_dict['model_name'] = model_name
    if enable_google_search is not None:
        config_dict['enable_google_search'] = enable_google_search
    if thinking_budget is not None:
        config_dict['thinking_budget'] = thinking_budget
    
    # Merge with additional kwargs
    config_dict.update(kwargs)
    
    # Create config with defaults from dataclass
    config = SummarizationConfig(**config_dict)
    
    return GeminiSummarizer(config)