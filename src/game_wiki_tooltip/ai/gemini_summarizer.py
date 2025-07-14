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
        print(f"📝 [SUMMARY-DEBUG] 开始Gemini摘要生成")
        print(f"   - 查询: '{query}'")
        print(f"   - 知识块数量: {len(chunks)}")
        print(f"   - 上下文: {context or 'None'}")
        print(f"   - 模型: {self.config.model_name}")
        
        if not chunks:
            print(f"⚠️ [SUMMARY-DEBUG] 没有知识块可用于摘要")
            return {
                "summary": "No relevant information found.",
                "chunks_used": 0,
                "sources": []
            }
        
        # 显示知识块信息
        print(f"📋 [SUMMARY-DEBUG] 输入知识块详情:")
        for i, chunk in enumerate(chunks, 1):
            print(f"   {i}. 主题: {chunk.get('topic', 'Unknown')}")
            print(f"      分数: {chunk.get('score', 0):.4f}")
            print(f"      类型: {chunk.get('type', 'General')}")
            print(f"      关键词: {chunk.get('keywords', [])}")
            print(f"      摘要: {chunk.get('summary', '')[:100]}...")
            
            # 如果有结构化数据，显示关键信息
            if "structured_data" in chunk:
                structured = chunk["structured_data"]
                if "enemy_name" in structured:
                    print(f"      敌人: {structured['enemy_name']}")
                if "loadout_recap" in structured:
                    print(f"      配装数: {len(structured['loadout_recap'])} 项")
                if "stratagems" in structured:
                    print(f"      策略数: {len(structured['stratagems'])} 项")
        
        try:
            # 检测语言
            language = self._detect_language(query) if self.config.language == "auto" else self.config.language
            print(f"🌐 [SUMMARY-DEBUG] 检测到语言: {language}")
            
            # Build the summarization prompt
            print(f"📝 [SUMMARY-DEBUG] 构建摘要提示词")
            prompt = self._build_summarization_prompt(chunks, query, context)
            print(f"   - 提示词长度: {len(prompt)} 字符")
            print(f"   - 温度设置: {self.config.temperature}")
            print(f"   - 最大输出tokens: {self.config.max_summary_length * 2}")
            
            # Generate summary
            print(f"🤖 [SUMMARY-DEBUG] 调用Gemini生成摘要")
            response = self.model.generate_content(prompt)
            
            print(f"✅ [SUMMARY-DEBUG] Gemini响应成功")
            print(f"   - 响应长度: {len(response.text)} 字符")
            print(f"   - 响应预览: {response.text[:200]}...")
            
            # Parse and format the response
            formatted_response = self._format_summary_response(response.text, chunks)
            
            print(f"📊 [SUMMARY-DEBUG] 摘要生成完成")
            print(f"   - 使用的知识块数: {formatted_response['chunks_used']}")
            print(f"   - 来源数: {len(formatted_response['sources'])}")
            print(f"   - 最终摘要长度: {len(formatted_response['summary'])} 字符")
            
            return formatted_response
            
        except Exception as e:
            print(f"❌ [SUMMARY-DEBUG] 摘要生成失败: {e}")
            logger.error(f"Error in summarization: {str(e)}")
            
            # Fallback to simple concatenation
            print(f"🔄 [SUMMARY-DEBUG] 使用降级摘要策略")
            fallback_result = self._fallback_summary(chunks, query)
            
            print(f"📊 [SUMMARY-DEBUG] 降级摘要完成")
            print(f"   - 使用的知识块数: {fallback_result['chunks_used']}")
            print(f"   - 降级摘要长度: {len(fallback_result['summary'])} 字符")
            
            return fallback_result
    
    def _build_summarization_prompt(
        self, 
        chunks: List[Dict[str, Any]], 
        query: str,
        context: Optional[str] = None
    ) -> str:
        """Build the prompt for Gemini summarization"""
        
        # Detect language from query or use config
        language = self._detect_language(query) if self.config.language == "auto" else self.config.language
        
        # Format chunks for the prompt with structured data
        chunks_text = self._format_chunks_with_structured_data(chunks)
        
        # Build language-specific prompt
        if language == "zh":
            prompt = f"""你是一个专业的游戏攻略助手。请根据检索到的游戏信息，为玩家提供一个结构化的回答。

玩家问题：{query}

可用的游戏信息：
{chunks_text}

回答要求：
1. **首先给出一句话总结**：用一句简洁的话概括最佳解决方案或推荐
2. **然后提供详细原因讲解**：基于structured_data中的具体信息进行深入解释

格式要求：
• 一句话总结：直接给出最核心的建议
• 详细讲解：包含具体的装备名称、数值、搭配理由等
• 如果是配装推荐，必须列出完整的装备配置和选择理由
• 如果是敌人攻略，必须包含弱点位置、血量、推荐武器等
• 保持友好的对话语气，可以使用适当的表情符号

注意：
- 只基于提供的信息回答，不要编造内容
- 优先使用structured_data中的详细信息
- 如果信息不相关，请明确说明

你的回答："""
        else:
            prompt = f"""You are a professional game guide assistant. Based on the retrieved game information, provide a structured response to the player.

Player question: {query}

Available game information:
{chunks_text}

Response requirements:
1. **Start with a one-sentence summary**: Give a concise recommendation or solution
2. **Then provide detailed explanation**: Use specific information from structured_data for in-depth analysis

Format requirements:
• One-sentence summary: Direct core recommendation
• Detailed explanation: Include specific equipment names, stats, synergy reasons
• For build recommendations, must list complete loadout configuration and selection rationale
• For enemy guides, must include weak point locations, HP values, recommended weapons
• Maintain friendly conversational tone with appropriate emojis

Note:
- Only answer based on provided information, don't fabricate content
- Prioritize detailed information from structured_data
- If information is irrelevant, clearly state so

Your response:"""
        
        return prompt
    
    def _format_chunks_with_structured_data(self, chunks: List[Dict[str, Any]]) -> str:
        """Format chunks including structured_data for inclusion in the prompt"""
        formatted_chunks = []
        
        for i, chunk in enumerate(chunks, 1):
            # Extract basic information
            topic = chunk.get("topic", "Unknown Topic")
            summary = chunk.get("summary", "")
            keywords = chunk.get("keywords", [])
            chunk_type = chunk.get("type", "General")
            
            # Extract structured_data if available
            structured_data = chunk.get("structured_data", {})
            
            # Format basic chunk info
            chunk_text = f"""
[知识块 {i}] {topic} (类型: {chunk_type})
概述：{summary}
关键词：{', '.join(keywords) if keywords else 'N/A'}
相关度分数：{chunk.get('score', 0):.2f}
"""
            
            # Add structured data details if available
            if structured_data:
                structured_text = self._format_structured_data(structured_data, chunk_type)
                if structured_text:
                    chunk_text += f"\n详细结构化信息：\n{structured_text}"
            
            formatted_chunks.append(chunk_text.strip())
        
        return "\n\n".join(formatted_chunks)
    
    def _format_structured_data(self, structured_data: Dict[str, Any], chunk_type: str) -> str:
        """Format structured_data based on chunk type"""
        if not structured_data:
            return ""
        
        formatted_parts = []
        
        # Handle different types of structured data
        if chunk_type == "Build_Recommendation":
            # Format build information
            if "loadout_recap" in structured_data:
                loadout = structured_data["loadout_recap"]
                formatted_parts.append("完整配装：")
                for key, value in loadout.items():
                    formatted_parts.append(f"  • {key}: {value}")
            
            if "stratagems" in structured_data:
                formatted_parts.append("\n战略支援详情：")
                for stratagem in structured_data["stratagems"]:
                    name = stratagem.get("name", "Unknown")
                    category = stratagem.get("category", "Unknown")
                    rationale = stratagem.get("rationale", "No reason provided")
                    formatted_parts.append(f"  • {name} ({category}): {rationale}")
            
            if "primary_weapon" in structured_data:
                weapon = structured_data["primary_weapon"]
                if isinstance(weapon, dict):
                    name = weapon.get("name", "Unknown")
                    rationale = weapon.get("rationale", "No reason provided")
                    formatted_parts.append(f"\n主武器: {name}")
                    formatted_parts.append(f"  选择理由: {rationale}")
                else:
                    formatted_parts.append(f"\n主武器: {weapon}")
            
            if "secondary_weapons" in structured_data:
                formatted_parts.append("\n副武器选择：")
                for weapon in structured_data["secondary_weapons"]:
                    name = weapon.get("name", "Unknown")
                    rationale = weapon.get("rationale", "No reason provided")
                    formatted_parts.append(f"  • {name}: {rationale}")
            
            if "grenade" in structured_data:
                grenade = structured_data["grenade"]
                if isinstance(grenade, dict):
                    name = grenade.get("name", "Unknown")
                    rationale = grenade.get("rationale", "No reason provided")
                    formatted_parts.append(f"\n手雷: {name}")
                    formatted_parts.append(f"  选择理由: {rationale}")
                else:
                    formatted_parts.append(f"\n手雷: {grenade}")
            
            if "armor" in structured_data:
                armor = structured_data["armor"]
                if isinstance(armor, dict):
                    armor_class = armor.get("class", "Unknown")
                    perk = armor.get("perk", "Unknown")
                    rationale = armor.get("rationale", "No reason provided")
                    formatted_parts.append(f"\n护甲: {armor_class}级护甲 ({perk})")
                    formatted_parts.append(f"  选择理由: {rationale}")
                else:
                    formatted_parts.append(f"\n护甲: {armor}")
        
        elif chunk_type == "Enemy_Weakpoint_Guide":
            # Format enemy weakpoint information
            if "enemy_name" in structured_data:
                enemy_name = structured_data["enemy_name"]
                faction = structured_data.get("faction", "Unknown")
                main_health = structured_data.get("main_health", "Unknown")
                formatted_parts.append(f"敌人: {enemy_name} ({faction})")
                formatted_parts.append(f"主要血量: {main_health}")
            
            if "weak_points" in structured_data:
                formatted_parts.append("\n弱点详情：")
                for wp in structured_data["weak_points"]:
                    name = wp.get("name", "Unknown")
                    health = wp.get("health", "Unknown")
                    armor_class = wp.get("armor_class", "Unknown")
                    note = wp.get("note", "")
                    formatted_parts.append(f"  • {name}: {health}血量, {armor_class}级护甲")
                    if note:
                        formatted_parts.append(f"    说明: {note}")
            
            if "recommended_weapons" in structured_data:
                weapons = structured_data["recommended_weapons"]
                formatted_parts.append(f"\n推荐武器: {', '.join(weapons)}")
            
            if "general_strategy" in structured_data:
                strategy = structured_data["general_strategy"]
                formatted_parts.append(f"\n总体策略: {strategy}")
        
        elif chunk_type == "Gameplay_Strategy":
            # Format gameplay strategy information
            if "combos" in structured_data:
                formatted_parts.append("战术组合：")
                for combo in structured_data["combos"]:
                    name = combo.get("name", "Unknown")
                    description = combo.get("description", "No description")
                    formatted_parts.append(f"  • {name}: {description}")
            
            if "enemy_strategies" in structured_data:
                formatted_parts.append("\n敌人应对策略：")
                for strategy in structured_data["enemy_strategies"]:
                    enemy = strategy.get("enemy", "Unknown")
                    tactic = strategy.get("strategy", "No strategy provided")
                    formatted_parts.append(f"  • {enemy}: {tactic}")
        
        # Handle any other structured data generically
        for key, value in structured_data.items():
            if key not in ["loadout_recap", "stratagems", "primary_weapon", "secondary_weapons", 
                          "grenade", "armor", "enemy_name", "faction", "main_health", 
                          "weak_points", "recommended_weapons", "general_strategy", 
                          "combos", "enemy_strategies"]:
                if isinstance(value, (str, int, float)):
                    formatted_parts.append(f"{key}: {value}")
                elif isinstance(value, list):
                    formatted_parts.append(f"{key}: {', '.join(map(str, value))}")
                elif isinstance(value, dict):
                    formatted_parts.append(f"{key}: {str(value)}")
        
        return "\n".join(formatted_parts)
    
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
        # Simple concatenation of top chunks with structured data
        summary_parts = []
        
        for i, chunk in enumerate(chunks[:2], 1):  # Use top 2 chunks
            topic = chunk.get("topic", "")
            content = chunk.get("summary", chunk.get("content", ""))
            
            # Add basic info
            if topic:
                summary_parts.append(f"💡 {topic}")
            
            summary_parts.append(content)
            
            # Add key structured data if available
            structured_data = chunk.get("structured_data", {})
            if structured_data:
                # Extract key recommendations
                if "loadout_recap" in structured_data:
                    loadout = structured_data["loadout_recap"]
                    key_items = []
                    for key, value in list(loadout.items())[:3]:  # Top 3 items
                        key_items.append(f"{key}: {value}")
                    if key_items:
                        summary_parts.append(f"🔧 推荐配置: {'; '.join(key_items)}")
                
                elif "weak_points" in structured_data:
                    weak_points = structured_data["weak_points"]
                    if weak_points:
                        main_weakness = weak_points[0]
                        name = main_weakness.get("name", "Unknown")
                        health = main_weakness.get("health", "Unknown")
                        summary_parts.append(f"🎯 主要弱点: {name} ({health}血量)")
            
            summary_parts.append("")  # Add spacing between chunks
        
        summary = "\n".join(summary_parts).strip()
        
        return {
            "summary": summary,
            "chunks_used": min(2, len(chunks)),
            "sources": [{"index": i+1, "topic": c.get("topic", "")} for i, c in enumerate(chunks[:2])],
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