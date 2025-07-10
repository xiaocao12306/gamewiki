"""
高质量 RAG 查询示例
====================

展示如何使用与 evaluator 相同的配置来获得高质量的知识片段返回
"""

import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

# 导入必要的模块
from .rag_query import EnhancedRagQuery
from ..config import LLMConfig


async def create_high_quality_rag_engine(game_name: str, llm_config: Optional[LLMConfig] = None) -> EnhancedRagQuery:
    """
    创建高质量的 RAG 引擎，使用与 evaluator 相同的配置
    
    Args:
        game_name: 游戏名称
        llm_config: LLM 配置
        
    Returns:
        配置优化的 RAG 引擎实例
    """
    # 使用与 evaluator 相同的配置
    rag_engine = EnhancedRagQuery(
        enable_summarization=True,      # 启用摘要功能
        enable_hybrid_search=True,      # 启用混合搜索
        enable_intent_reranking=True,   # 启用意图重排序
        llm_config=llm_config or LLMConfig(),
        hybrid_config={
            "fusion_method": "rrf",
            "vector_weight": 0.5,       # 平衡权重（而非默认的 0.3）
            "bm25_weight": 0.5,         # 平衡权重（而非默认的 0.7）
            "rrf_k": 60
        },
        reranking_config={
            "intent_weight": 0.4,
            "semantic_weight": 0.6
        }
    )
    
    # 初始化
    await rag_engine.initialize(game_name=game_name)
    return rag_engine


async def query_high_quality_rag(
    question: str,
    game_name: str,
    top_k: int = 5,  # 增加检索数量以获得更多上下文
    llm_config: Optional[LLMConfig] = None
) -> Dict[str, Any]:
    """
    执行高质量的 RAG 查询
    
    Args:
        question: 用户问题
        game_name: 游戏名称
        top_k: 检索结果数量（建议使用 5 而非默认的 3）
        llm_config: LLM 配置
        
    Returns:
        查询结果
    """
    # 创建优化配置的 RAG 引擎
    rag_engine = await create_high_quality_rag_engine(game_name, llm_config)
    
    # 执行查询
    result = await rag_engine.query(question, top_k=top_k)
    
    return result


def get_optimized_rag_config() -> Dict[str, Any]:
    """
    获取优化的 RAG 配置参数
    
    Returns:
        包含所有优化配置的字典
    """
    return {
        "enable_summarization": True,
        "enable_hybrid_search": True,
        "enable_intent_reranking": True,
        "hybrid_config": {
            "fusion_method": "rrf",
            "vector_weight": 0.5,  # 关键：平衡的权重配置
            "bm25_weight": 0.5,    # 关键：平衡的权重配置
            "rrf_k": 60
        },
        "reranking_config": {
            "intent_weight": 0.4,
            "semantic_weight": 0.6
        },
        "summarization_config": {
            "enabled": True,
            "model_name": "gemini-2.5-flash-lite-preview-06-17",
            "max_summary_length": 300,
            "temperature": 0.3,
            "include_sources": True,
            "language": "auto"
        }
    }


# 示例用法
async def main():
    """示例：使用高质量配置进行查询"""
    
    # 创建 LLM 配置
    llm_config = LLMConfig()
    
    # 测试查询
    test_queries = [
        "地狱潜兵2中最好的主武器是什么？",
        "如何对付虫族？",
        "推荐一些适合新手的战纽配置"
    ]
    
    game_name = "helldiver2"
    
    print("使用高质量 RAG 配置进行查询...\n")
    
    for query in test_queries:
        print(f"问题: {query}")
        result = await query_high_quality_rag(
            question=query,
            game_name=game_name,
            top_k=5,  # 增加检索数量
            llm_config=llm_config
        )
        
        print(f"回答: {result['answer'][:200]}...")
        print(f"置信度: {result['confidence']:.3f}")
        print(f"检索到的文档数: {result['results_count']}")
        print("-" * 50 + "\n")


if __name__ == "__main__":
    asyncio.run(main()) 