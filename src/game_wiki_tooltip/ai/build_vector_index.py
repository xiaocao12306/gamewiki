#!/usr/bin/env python3
"""
向量索引构建工具
===============

命令行工具，用于批量处理知识库文件并构建向量索引

用法:
    python build_vector_index.py --game helldiver2
    python build_vector_index.py --game all
    python build_vector_index.py --file data/knowledge_chunk/helldiver2.json
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from src.game_wiki_tooltip.ai.batch_embedding import BatchEmbeddingProcessor, process_game_knowledge

def setup_logging(verbose: bool = False):
    """设置日志配置"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('vector_build.log', encoding='utf-8')
        ]
    )

def get_available_games(knowledge_dir: str = "data/knowledge_chunk") -> List[str]:
    """获取可用的游戏列表"""
    knowledge_path = Path(knowledge_dir)
    if not knowledge_path.exists():
        return []
    
    json_files = list(knowledge_path.glob("*.json"))
    return [f.stem for f in json_files]

def process_single_game(game_name: str, 
                       knowledge_dir: str = "data/knowledge_chunk",
                       output_dir: str = "src/game_wiki_tooltip/ai/vectorstore",
                       vector_store_type: str = "faiss",
                       batch_size: int = 64) -> bool:
    """
    处理单个游戏的知识库
    
    Args:
        game_name: 游戏名称
        knowledge_dir: 知识库目录
        output_dir: 输出目录
        vector_store_type: 向量库类型
        batch_size: 批处理大小
        
    Returns:
        是否成功
    """
    try:
        print(f"\n开始处理游戏: {game_name}")
        
        # 检查API密钥
        import os
        if not os.environ.get("JINA_API_KEY"):
            print("错误: 需要设置JINA_API_KEY环境变量")
            return False
        
        # 处理知识库
        config_path = process_game_knowledge(
            game_name=game_name,
            knowledge_dir=knowledge_dir,
            output_dir=output_dir
        )
        
        print(f"✓ 游戏 {game_name} 处理完成: {config_path}")
        return True
        
    except FileNotFoundError as e:
        print(f"✗ 游戏 {game_name} 处理失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 游戏 {game_name} 处理失败: {e}")
        return False

def process_all_games(knowledge_dir: str = "data/knowledge_chunk",
                     output_dir: str = "src/game_wiki_tooltip/ai/vectorstore",
                     vector_store_type: str = "faiss",
                     batch_size: int = 64) -> None:
    """
    处理所有游戏的知识库
    
    Args:
        knowledge_dir: 知识库目录
        output_dir: 输出目录
        vector_store_type: 向量库类型
        batch_size: 批处理大小
    """
    games = get_available_games(knowledge_dir)
    
    if not games:
        print("未找到任何游戏知识库文件")
        return
    
    print(f"找到 {len(games)} 个游戏: {', '.join(games)}")
    
    success_count = 0
    for game in games:
        if process_single_game(game, knowledge_dir, output_dir, vector_store_type, batch_size):
            success_count += 1
    
    print(f"\n处理完成: {success_count}/{len(games)} 个游戏成功")

def process_custom_file(file_path: str,
                       output_dir: str = "src/game_wiki_tooltip/ai/vectorstore",
                       collection_name: str = "custom_vectors",
                       vector_store_type: str = "faiss",
                       batch_size: int = 64) -> bool:
    """
    处理自定义文件
    
    Args:
        file_path: 文件路径
        output_dir: 输出目录
        collection_name: 集合名称
        vector_store_type: 向量库类型
        batch_size: 批处理大小
        
    Returns:
        是否成功
    """
    try:
        print(f"开始处理文件: {file_path}")
        
        # 检查API密钥
        import os
        if not os.environ.get("JINA_API_KEY"):
            print("错误: 需要设置JINA_API_KEY环境变量")
            return False
        
        # 创建处理器
        processor = BatchEmbeddingProcessor(vector_store_type=vector_store_type)
        
        # 处理文件
        config_path = processor.process_json_file(
            json_path=file_path,
            output_dir=output_dir,
            batch_size=batch_size,
            collection_name=collection_name
        )
        
        print(f"✓ 文件处理完成: {config_path}")
        return True
        
    except Exception as e:
        print(f"✗ 文件处理失败: {e}")
        return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="批量处理知识库文件并构建向量索引",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 处理特定游戏
  python build_vector_index.py --game helldiver2
  
  # 处理所有游戏
  python build_vector_index.py --game all
  
  # 处理自定义文件
  python build_vector_index.py --file data/knowledge_chunk/helldiver2.json
  
  # 使用Qdrant向量库
  python build_vector_index.py --game helldiver2 --vector-store qdrant
  
  # 设置批处理大小
  python build_vector_index.py --game helldiver2 --batch-size 32
        """
    )
    
    # 添加参数
    parser.add_argument(
        "--game", 
        type=str,
        help="游戏名称 (使用 'all' 处理所有游戏)"
    )
    
    parser.add_argument(
        "--file",
        type=str,
        help="自定义JSON文件路径"
    )
    
    parser.add_argument(
        "--knowledge-dir",
        type=str,
        default="data/knowledge_chunk",
        help="知识库目录 (默认: data/knowledge_chunk)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="src/game_wiki_tooltip/ai/vectorstore",
        help="输出目录 (默认: src/game_wiki_tooltip/ai/vectorstore)"
    )
    
    parser.add_argument(
        "--vector-store",
        type=str,
        choices=["faiss", "qdrant"],
        default="faiss",
        help="向量库类型 (默认: faiss)"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="批处理大小 (默认: 64)"
    )
    
    parser.add_argument(
        "--collection-name",
        type=str,
        default="custom_vectors",
        help="集合名称 (仅用于自定义文件)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出"
    )
    
    parser.add_argument(
        "--list-games",
        action="store_true",
        help="列出可用的游戏"
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.verbose)
    
    # 列出可用游戏
    if args.list_games:
        games = get_available_games(args.knowledge_dir)
        if games:
            print("可用的游戏:")
            for game in games:
                print(f"  - {game}")
        else:
            print("未找到任何游戏知识库文件")
        return
    
    # 检查参数
    if not args.game and not args.file:
        parser.error("需要指定 --game 或 --file 参数")
    
    if args.game and args.file:
        parser.error("不能同时指定 --game 和 --file 参数")
    
    # 处理请求
    if args.game:
        if args.game.lower() == "all":
            process_all_games(
                knowledge_dir=args.knowledge_dir,
                output_dir=args.output_dir,
                vector_store_type=args.vector_store,
                batch_size=args.batch_size
            )
        else:
            success = process_single_game(
                game_name=args.game,
                knowledge_dir=args.knowledge_dir,
                output_dir=args.output_dir,
                vector_store_type=args.vector_store,
                batch_size=args.batch_size
            )
            if not success:
                sys.exit(1)
    
    elif args.file:
        success = process_custom_file(
            file_path=args.file,
            output_dir=args.output_dir,
            collection_name=args.collection_name,
            vector_store_type=args.vector_store,
            batch_size=args.batch_size
        )
        if not success:
            sys.exit(1)

if __name__ == "__main__":
    main() 