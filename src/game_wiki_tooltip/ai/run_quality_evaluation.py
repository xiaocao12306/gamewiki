#!/usr/bin/env python
"""
RAG质量评估运行脚本
=====================

快速运行RAG输出质量评估的便捷脚本
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# 处理相对导入
try:
    from .rag_quality_evaluator import RAGQualityEvaluator
except ImportError:
    # 如果直接运行脚本，添加当前目录到路径
    sys.path.insert(0, str(Path(__file__).parent))
    from rag_quality_evaluator import RAGQualityEvaluator


def setup_logging(verbose: bool = False):
    """设置日志配置"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="评估RAG系统的输出质量",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 评估Helldivers 2的RAG质量（默认）
  python run_quality_evaluation.py
  
  # 评估其他游戏
  python run_quality_evaluation.py --game eldenring
  
  # 指定输出目录
  python run_quality_evaluation.py --output ./reports/
  
  # 启用详细日志
  python run_quality_evaluation.py --verbose
        """
    )
    
    parser.add_argument(
        "--game",
        type=str,
        default="helldiver2",
        help="要评估的游戏（默认: helldiver2）"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出报告的目录路径（默认: 当前目录）"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="启用详细日志输出"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.verbose)
    
    # 运行评估
    asyncio.run(run_evaluation(args.game, args.output))


async def run_evaluation(game: str, output_dir: str = None):
    """运行质量评估"""
    print(f"\n{'='*60}")
    print(f"RAG质量评估器 - {game}")
    print(f"{'='*60}\n")
    
    # 创建评估器
    evaluator = RAGQualityEvaluator(game=game)
    
    try:
        # 初始化
        print("正在初始化RAG引擎和评估器...")
        await evaluator.initialize()
        
        # 运行评估
        print(f"\n开始评估 {game} 的RAG输出质量...")
        print("这可能需要几分钟时间，请耐心等待...\n")
        
        report = await evaluator.evaluate_all()
        
        # 确定输出路径
        if output_dir:
            output_path = Path(output_dir) / f"quality_report_{game}.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_path = None
            
        # 保存报告
        evaluator.save_report(report, output_path)
        
        # 打印结果摘要
        print(f"\n{'='*60}")
        print("评估完成！")
        print(f"{'='*60}")
        print(f"\n📊 总体评分: {report.average_score:.2f}/10")
        print(f"📝 测试用例数: {report.total_cases}")
        
        print(f"\n📈 各维度得分:")
        for dim, score in report.scores_by_dimension.items():
            bar = "█" * int(score) + "░" * (10 - int(score))
            print(f"  {dim:<15} [{bar}] {score:.2f}")
        
        print(f"\n⚠️  主要问题:")
        for i, issue in enumerate(report.common_issues[:3], 1):
            print(f"  {i}. {issue}")
        
        print(f"\n💡 改进建议:")
        for i, suggestion in enumerate(report.improvement_suggestions[:3], 1):
            print(f"  {i}. {suggestion}")
            
        print(f"\n✅ 报告已保存")
        print(f"   - JSON报告: quality_report_{game}_*.json")
        print(f"   - Markdown报告: quality_report_{game}_*.md")
        
    except FileNotFoundError as e:
        print(f"\n❌ 错误: {e}")
        print(f"请确保存在测试数据文件: data/sample_inoutput/{game}.json")
        
    except Exception as e:
        print(f"\n❌ 评估过程出错: {e}")
        logging.error(f"详细错误信息: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()