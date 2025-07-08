#!/usr/bin/env python3
"""
批量嵌入功能使用示例
==================

演示如何使用批量嵌入功能处理游戏知识库
"""

import os
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from src.game_wiki_tooltip.ai.batch_embedding import BatchEmbeddingProcessor, process_game_knowledge
from src.game_wiki_tooltip.ai.rag_query import query_enhanced_rag

async def main():
    """主函数 - 演示完整的使用流程"""
    
    print("=== 批量嵌入功能使用示例 ===\n")
    
    # 检查API密钥
    if not os.environ.get("JINA_API_KEY"):
        print("❌ 请先设置JINA_API_KEY环境变量")
        print("Windows: set JINA_API_KEY=your_api_key_here")
        print("Linux/Mac: export JINA_API_KEY=your_api_key_here")
        return
    
    print("✓ Jina API密钥已设置")
    
    # 1. 处理Helldivers 2知识库
    print("\n1. 处理Helldivers 2知识库...")
    try:
        config_path = process_game_knowledge("helldiver2")
        print(f"✓ 向量库构建完成: {config_path}")
    except Exception as e:
        print(f"❌ 向量库构建失败: {e}")
        return
    
    # 2. 测试RAG查询
    print("\n2. 测试RAG查询...")
    
    test_questions = [
        "地狱潜兵2 虫族配装推荐",
        "Terminid 最佳武器选择",
        "火焰配装如何搭配",
        "虫族地图攻略"
    ]
    
    for question in test_questions:
        print(f"\n查询: {question}")
        try:
            result = await query_enhanced_rag(
                question=question,
                game_name="helldiver2",
                top_k=2
            )
            
            print(f"答案: {result['answer'][:150]}...")
            print(f"相关度: {result['confidence']:.3f}")
            print(f"查询时间: {result['query_time']:.3f}s")
            
        except Exception as e:
            print(f"❌ 查询失败: {e}")
    
    # 3. 演示批量处理其他游戏
    print("\n3. 检查其他可用游戏...")
    
    knowledge_dir = Path("data/knowledge_chunk")
    if knowledge_dir.exists():
        json_files = list(knowledge_dir.glob("*.json"))
        games = [f.stem for f in json_files]
        
        print(f"发现 {len(games)} 个游戏知识库:")
        for game in games:
            print(f"  - {game}")
        
        if len(games) > 1:
            print(f"\n可以运行以下命令处理所有游戏:")
            print(f"python src/game_wiki_tooltip/ai/build_vector_index.py --game all")
    
    print("\n=== 示例完成 ===")
    print("\n更多用法请参考 README_batch_embedding.md")

if __name__ == "__main__":
    asyncio.run(main()) 