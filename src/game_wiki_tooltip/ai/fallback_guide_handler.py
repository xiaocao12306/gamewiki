"""
Fallback Guide Handler - Handle guide queries for games without knowledge bases
============================================================================

When a game doesn't have a pre-built vector store but the user wants guide/strategy information,
this module uses Google Search grounding to provide answers with proper citations and warnings.
"""

import os
import logging
import asyncio
from typing import Optional, AsyncGenerator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FallbackConfig:
    """Configuration for fallback guide handler"""
    api_key: str
    model_name: str = "gemini-2.5-flash"
    temperature: float = 0.3
    language: str = "auto"  # auto, zh, en


class FallbackGuideHandler:
    """Handle guide queries for unsupported games using Google Search"""
    
    def __init__(self, config: FallbackConfig):
        """Initialize fallback guide handler"""
        self.config = config
        logger.info(f"Initialized FallbackGuideHandler with model: {config.model_name}")
    
    async def generate_guide_stream(
        self,
        query: str,
        game_context: Optional[str] = None,
        language: str = "auto",
        original_query: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate guide response with Google Search grounding
        
        Args:
            query: User query (processed/translated)
            game_context: Game name or context
            language: Response language (auto/zh/en)
            original_query: Original user query for better context
            
        Yields:
            Streaming response chunks with warnings and citations
        """
        try:
            logger.debug(f"Starting fallback guide generation")
            logger.debug(f"Query: {query}")
            logger.debug(f"Game context: {game_context}")
            logger.debug(f"Language: {language}")
            logger.debug(f"Original query: {original_query}")
            
            # Import here to avoid startup delays
            from google import genai
            from google.genai import types
            
            # Configure the client
            client = genai.Client(api_key=self.config.api_key)
            
            # Define the grounding tool
            grounding_tool = types.Tool(
                google_search=types.GoogleSearch()
            )
            
            # Build system instruction and prompt
            system_instruction = self._build_system_instruction(language)
            user_prompt = self._build_user_prompt(query, game_context, language, original_query)
            
            # Configure generation settings
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[grounding_tool],
                temperature=self.config.temperature
            )
            
            logger.debug(f"Calling Gemini with Google Search")
            logger.debug(f"System instruction length: {len(system_instruction)} chars")
            logger.debug(f"User prompt length: {len(user_prompt)} chars")
            
            # Generate complete response using standard API
            response = client.models.generate_content(
                model=self.config.model_name,
                contents=user_prompt,
                config=config
            )
            
            logger.debug(f"Received complete response from Gemini")
            
            # Get main response text
            main_text = response.text if response.text else ""
            logger.debug(f"Main response length: {len(main_text)} characters")
            
            # Yield the main content
            if main_text:
                yield main_text
            
            # Try to extract and append real citations from grounding metadata
            try:
                citations_text = self._extract_grounding_citations(response, language)
                if citations_text:
                    logger.debug("Found grounding citations, appending to output")
                    yield citations_text
                else:
                    logger.debug("No additional citations to extract")
            except Exception as e:
                logger.debug(f"Citation extraction failed: {e}")
                # Continue without additional citations
            
        except Exception as e:
            logger.error(f"Error in fallback guide generation: {e}")
            logger.debug(f"Fallback error details: {e}")
            
            # Check for specific error types
            error_str = str(e).lower()
            if "quota" in error_str or "rate limit" in error_str or "429" in error_str:
                if language == "zh" or self._is_chinese(query):
                    yield (
                        "\n\n**API 使用限制**\n\n"
                        "您已达到 Google Gemini API 的使用限制。免费账户限制：\n"
                        "• 每分钟最多 15 次请求\n"
                        "• 每天最多 1500 次请求\n\n"
                        "请稍后再试，或考虑升级到付费账户以获得更高的配额。"
                    )
                else:
                    yield (
                        "\n\n**API Rate Limit**\n\n"
                        "You've reached the Google Gemini API usage limit. Free tier limits:\n"
                        "• Maximum 15 requests per minute\n"
                        "• Maximum 1500 requests per day\n\n"
                        "Please try again later, or consider upgrading to a paid account for higher quotas."
                    )
            elif "api_key" in error_str or "authentication" in error_str:
                if language == "zh" or self._is_chinese(query):
                    yield "\n\n**API 密钥错误**\n\n请检查您的 Google Gemini API 密钥配置。"
                else:
                    yield "\n\n**API Key Error**\n\nPlease check your Google Gemini API key configuration."
            else:
                # General error message
                if language == "zh" or self._is_chinese(query):
                    yield f"\n\n抱歉，生成指导内容时出现错误：{str(e)}"
                else:
                    yield f"\n\nSorry, an error occurred while generating guide content: {str(e)}"
    
    def _build_system_instruction(self, language: str) -> str:
        """Build system instruction with user warnings"""
        if language == "zh":
            return """你是一个游戏策略指导助手。请严格按照以下格式回复：

1. 首先在回复开头添加以下警告（保持原样）：
"NOTICE: 您正在没有预建知识库的游戏中使用AI指导功能。涉及主观推荐的内容（如配装推荐等）可能存在偏差，请务必参考下方引用的权威来源进行验证。"

2. 然后回答用户的游戏问题，重点提供方法和策略：
- 使用网络搜索获取最新信息来源
- 重点说明"如何做"的方法和步骤，而不是复制具体的数值、物品列表、掉落率等详细数据
- 提供操作技巧、策略思路、注意事项等实用指导
- 如果涉及装备或配置，说明选择原则而不是具体名称和数据
- 引导用户到权威来源查看详细数据

请用中文回答，重点关注方法论和操作指导，避免直接复制wiki的具体数据内容。"""

        else:
            return """You are a gaming strategy guide assistant. Please strictly follow this format:

1. Start your response with this notice (keep as-is):
"NOTICE: You are using AI guidance in a game without a pre-built knowledge base. Content involving subjective recommendations (such as build recommendations) may be biased. Please verify against the authoritative sources cited below."

2. Then answer the user's gaming question, focusing on methods and strategies:
- Use web search to get latest information sources
- Focus on explaining "how to do" methods and steps, rather than copying specific numbers, item lists, drop rates, or detailed data
- Provide operational tips, strategic approaches, and key considerations
- For equipment or builds, explain selection principles rather than specific names and stats
- Guide users to authoritative sources for detailed data"

Answer in English, focusing on methodology and operational guidance, avoiding direct copying of specific wiki data content."""
    
    def _build_user_prompt(
        self,
        query: str,
        game_context: Optional[str],
        language: str,
        original_query: Optional[str]
    ) -> str:
        """Build user prompt for the query"""
        if language == "zh" or self._is_chinese(query):
            base_prompt = f"请帮我回答这个游戏问题：{query}"
            
            if original_query and original_query != query:
                base_prompt += f"\n\n（原始问题：{original_query}）"
            
            if game_context:
                base_prompt += f"\n\n游戏背景：{game_context}"
            
            base_prompt += "\n\n请搜索最新的游戏信息并提供详细的指导。"
            
        else:
            base_prompt = f"Please help me answer this gaming question: {query}"
            
            if original_query and original_query != query:
                base_prompt += f"\n\n(Original question: {original_query})"
            
            if game_context:
                base_prompt += f"\n\nGame context: {game_context}"
            
            base_prompt += "\n\nPlease search for the latest game information and provide detailed guidance."
        
        return base_prompt
    
    def _is_chinese(self, text: str) -> bool:
        """Check if text contains Chinese characters"""
        if not text:
            return False
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        return chinese_chars > len(text) * 0.3
    
    def _extract_grounding_citations(self, response, language: str) -> Optional[str]:
        """Extract real citations from Google Search grounding metadata"""
        try:
            # Check if we have candidates with grounding metadata
            if not (hasattr(response, 'candidates') and response.candidates):
                logger.debug("No candidates found in response")
                return None
                
            candidate = response.candidates[0]
            if not (hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata):
                logger.debug("No grounding metadata found in candidate")
                return None
                
            grounding_metadata = candidate.grounding_metadata
            logger.debug("Found grounding metadata in response")
            
            # Try to get grounding chunks (should contain URLs and titles)
            grounding_chunks = getattr(grounding_metadata, 'grounding_chunks', None)
            
            if grounding_chunks and len(grounding_chunks) > 0:
                logger.debug(f"Found {len(grounding_chunks)} grounding chunks")
                
                citations = []
                for i, chunk in enumerate(grounding_chunks):
                    try:
                        # Try to access web information
                        web_info = getattr(chunk, 'web', None)
                        if web_info:
                            uri = getattr(web_info, 'uri', None)
                            title = getattr(web_info, 'title', None)
                            
                            if uri and title:
                                # Clean up title
                                if title and '.' in title and len(title.split()) == 1:
                                    title = f"Source from {title}"
                                
                                citations.append({
                                    'uri': uri,
                                    'title': title or 'Web Source'
                                })
                                logger.debug(f"Extracted citation {i}: {title} - {uri}")
                                
                    except Exception as e:
                        logger.debug(f"Error processing grounding chunk {i}: {e}")
                        continue
                
                if citations:
                    return self._format_citations(citations, language)
                else:
                    logger.debug("No valid citations extracted from grounding chunks")
            
            # Check grounding supports as fallback
            grounding_supports = getattr(grounding_metadata, 'grounding_supports', None)
            if grounding_supports and len(grounding_supports) > 0:
                logger.debug(f"Google Search active with {len(grounding_supports)} grounding supports")
                # Citations are integrated in AI response, but no extractable URLs
                return None
            
            logger.debug("No grounding chunks or supports found")
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting grounding citations: {e}")
            return None
    
    def _format_citations(self, citations: list, language: str) -> str:
        """Format citations into user-friendly text"""
        if not citations:
            return None
            
        # Remove AI-generated citation section and replace with real ones
        if language == "zh":
            citation_header = "\n\n**Real Sources (Verified):**\n"
        else:
            citation_header = "\n\n**Real Sources (Verified):**\n"
        
        citation_lines = []
        seen_uris = set()  # Deduplicate citations
        
        for citation in citations:
            uri = citation['uri']
            title = citation['title']
            
            # Skip duplicates
            if uri in seen_uris:
                continue
            seen_uris.add(uri)
            
            # Format citation line
            citation_lines.append(f"- [{title}]({uri})")
        
        if citation_lines:
            return citation_header + "\n".join(citation_lines)
        else:
            return None


# Convenience function
def create_fallback_guide_handler(
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.5-flash",
    **kwargs
) -> FallbackGuideHandler:
    """
    Create a FallbackGuideHandler instance
    
    Args:
        api_key: Google API key
        model_name: Model to use (gemini-2.5-flash recommended)
        **kwargs: Additional config parameters
        
    Returns:
        FallbackGuideHandler instance
    """
    if not api_key:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Google API key not provided")
    
    config = FallbackConfig(
        api_key=api_key,
        model_name=model_name,
        **kwargs
    )
    
    return FallbackGuideHandler(config)