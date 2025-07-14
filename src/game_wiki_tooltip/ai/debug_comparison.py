#!/usr/bin/env python
"""
RAG流程调试对比脚本
====================

用于对比evaluator流程和主流程（searchbar）的RAG调用差异
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.game_wiki_tooltip.ai.rag_quality_evaluator import RAGQualityEvaluator
from src.game_wiki_tooltip.searchbar import process_query_with_intent

async def test_evaluator_flow(query: str, game: str = "helldiver2"):
    """测试评估器流程"""
    print(f"\n{'='*60}")
    print(f"🧪 测试评估器流程")
    print(f"{'='*60}")
    
    evaluator = RAGQualityEvaluator(game=game)
    await evaluator.initialize()
    
    result = await evaluator.run_rag_query(query)
    return result

async def test_searchbar_flow(query: str, game: str = "Helldivers 2"):
    """测试主流程（searchbar）"""
    print(f"\n{'='*60}")
    print(f"🔍 测试主流程（searchbar）")
    print(f"{'='*60}")
    
    result = await process_query_with_intent(query, game)
    return result

async def main():
    """主测试函数"""
    print(f"🎯 RAG流程调试对比测试")
    print(f"{'='*80}")
    
    # 测试查询
    test_query = "绝地战士配装推荐"
    
    print(f"📝 测试查询: '{test_query}'")
    print(f"🎮 游戏: Helldivers 2")
    
    try:
        # 测试评估器流程
        evaluator_result = await test_evaluator_flow(test_query, "helldiver2")
        
        # 测试主流程
        searchbar_result = await test_searchbar_flow(test_query, "Helldivers 2")
        
        # 对比结果
        print(f"\n{'='*60}")
        print(f"📊 结果对比")
        print(f"{'='*60}")
        
        print(f"\n🧪 评估器流程结果:")
        print(f"   - 置信度: {evaluator_result.get('confidence', 0):.3f}")
        print(f"   - 结果数: {evaluator_result.get('results_count', 0)}")
        print(f"   - 耗时: {evaluator_result.get('processing_time', 0):.3f}秒")
        print(f"   - 答案长度: {len(evaluator_result.get('answer', ''))}")
        
        print(f"\n🔍 主流程结果:")
        if searchbar_result and 'result' in searchbar_result:
            main_result = searchbar_result['result']
            print(f"   - 置信度: {main_result.get('confidence', 0):.3f}")
            print(f"   - 结果数: {main_result.get('results_count', 0)}")
            print(f"   - 耗时: {main_result.get('query_time', 0):.3f}秒")
            print(f"   - 答案长度: {len(main_result.get('answer', ''))}")
        else:
            print(f"   - 主流程未返回RAG结果（可能是意图分类问题）")
            print(f"   - 返回类型: {searchbar_result.get('type', 'unknown')}")
        
        # 显示答案内容的前200个字符进行对比
        print(f"\n📝 答案内容对比:")
        print(f"\n🧪 评估器答案预览:")
        evaluator_answer = evaluator_result.get('answer', '')[:200]
        print(f"   {evaluator_answer}...")
        
        print(f"\n🔍 主流程答案预览:")
        if searchbar_result and 'result' in searchbar_result:
            main_answer = searchbar_result['result'].get('answer', '')[:200]
            print(f"   {main_answer}...")
        else:
            print(f"   无RAG答案")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 