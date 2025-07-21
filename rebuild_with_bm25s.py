#!/usr/bin/env python3
"""
BM25S重构脚本
==============

将现有的向量库从rank_bm25迁移到bm25s格式
同时重建所有索引以确保兼容性

用法:
    python rebuild_with_bm25s.py           # 重建所有游戏
    python rebuild_with_bm25s.py dst       # 重建单个游戏
    python rebuild_with_bm25s.py --clean   # 清理旧索引后重建
"""

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def check_environment():
    """检查环境和依赖"""
    logger = logging.getLogger(__name__)
    
    # 检查API密钥
    if not os.environ.get("JINA_API_KEY"):
        logger.error("❌ 缺少JINA_API_KEY环境变量")
        logger.info("请设置: export JINA_API_KEY=your_api_key")
        return False
    
    # 检查bm25s是否可用
    try:
        import bm25s
        logger.info(f"✅ bm25s版本: {bm25s.__version__}")
    except ImportError:
        logger.error("❌ bm25s未安装")
        logger.info("请运行: pip install bm25s>=0.2.13")
        return False
    
    # 检查数据目录
    knowledge_dir = Path("data/knowledge_chunk")
    if not knowledge_dir.exists():
        logger.error(f"❌ 知识库目录不存在: {knowledge_dir}")
        return False
    
    return True

def get_available_games() -> List[str]:
    """获取可用的游戏列表"""
    knowledge_dir = Path("data/knowledge_chunk")
    json_files = list(knowledge_dir.glob("*.json"))
    return [f.stem for f in json_files]

def backup_existing_indexes(vectorstore_dir: Path):
    """备份现有索引"""
    logger = logging.getLogger(__name__)
    
    if not vectorstore_dir.exists():
        return
    
    backup_dir = vectorstore_dir.parent / "vectorstore_backup"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    
    logger.info(f"📋 备份现有索引到: {backup_dir}")
    shutil.copytree(vectorstore_dir, backup_dir)

def clean_old_indexes(vectorstore_dir: Path):
    """清理旧的索引文件"""
    logger = logging.getLogger(__name__)
    
    if not vectorstore_dir.exists():
        return
    
    logger.info("🧹 清理旧的索引文件...")
    
    for game_dir in vectorstore_dir.glob("*_vectors"):
        if game_dir.is_dir():
            # 删除旧的BM25索引文件
            old_bm25_files = [
                game_dir / "enhanced_bm25_index.pkl",
                game_dir / "bm25_index.pkl"
            ]
            
            for old_file in old_bm25_files:
                if old_file.exists():
                    logger.info(f"  删除旧BM25索引: {old_file}")
                    old_file.unlink()
            
            # 删除旧的bm25s目录
            for bm25s_dir in game_dir.glob("*_bm25s"):
                if bm25s_dir.is_dir():
                    logger.info(f"  删除旧bm25s目录: {bm25s_dir}")
                    shutil.rmtree(bm25s_dir)

def rebuild_game_index(game_name: str) -> bool:
    """重建单个游戏的索引"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"🎮 开始重建游戏索引: {game_name}")
        
        # 使用现有的build_vector_index脚本
        from src.game_wiki_tooltip.ai.build_vector_index import process_single_game
        
        success = process_single_game(
            game_name=game_name,
            knowledge_dir="data/knowledge_chunk",
            output_dir="src/game_wiki_tooltip/ai/vectorstore",
            vector_store_type="faiss",
            batch_size=64
        )
        
        if success:
            logger.info(f"✅ {game_name} 索引重建成功")
        else:
            logger.error(f"❌ {game_name} 索引重建失败")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ {game_name} 索引重建异常: {e}")
        return False

def verify_new_indexes():
    """验证新索引的完整性"""
    logger = logging.getLogger(__name__)
    
    vectorstore_dir = Path("src/game_wiki_tooltip/ai/vectorstore")
    if not vectorstore_dir.exists():
        logger.error("❌ 向量库目录不存在")
        return False
    
    logger.info("🔍 验证新索引...")
    
    games = get_available_games()
    success_count = 0
    
    for game in games:
        game_dir = vectorstore_dir / f"{game}_vectors"
        config_file = vectorstore_dir / f"{game}_vectors_config.json"
        
        checks = {
            "游戏目录": game_dir.exists(),
            "配置文件": config_file.exists(),
            "FAISS索引": (game_dir / "index.faiss").exists(),
            "元数据": (game_dir / "metadata.json").exists(),
            "BM25索引": (game_dir / "enhanced_bm25_index.pkl").exists(),
        }
        
        # 检查bm25s目录
        bm25s_dirs = list(game_dir.glob("*_bm25s"))
        checks["BM25S目录"] = len(bm25s_dirs) > 0
        
        all_good = all(checks.values())
        status = "✅" if all_good else "❌"
        
        logger.info(f"  {status} {game}:")
        for check_name, result in checks.items():
            symbol = "✓" if result else "✗"
            logger.info(f"    {symbol} {check_name}")
        
        if all_good:
            success_count += 1
    
    logger.info(f"📊 验证完成: {success_count}/{len(games)} 个游戏索引正常")
    return success_count == len(games)

def main():
    parser = argparse.ArgumentParser(description="BM25S重构工具")
    parser.add_argument("game", nargs="?", help="游戏名称（如果不指定则重建所有）")
    parser.add_argument("--clean", action="store_true", help="清理旧索引")
    parser.add_argument("--backup", action="store_true", help="备份现有索引")
    parser.add_argument("--verify-only", action="store_true", help="仅验证索引")
    
    args = parser.parse_args()
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 BM25S重构工具启动")
    logger.info("=" * 50)
    
    # 检查环境
    if not check_environment():
        sys.exit(1)
    
    vectorstore_dir = Path("src/game_wiki_tooltip/ai/vectorstore")
    
    # 仅验证模式
    if args.verify_only:
        success = verify_new_indexes()
        sys.exit(0 if success else 1)
    
    # 备份现有索引
    if args.backup:
        backup_existing_indexes(vectorstore_dir)
    
    # 清理旧索引
    if args.clean:
        clean_old_indexes(vectorstore_dir)
    
    # 重建索引
    if args.game:
        # 重建单个游戏
        if args.game not in get_available_games():
            logger.error(f"❌ 游戏 '{args.game}' 不存在")
            logger.info(f"可用游戏: {', '.join(get_available_games())}")
            sys.exit(1)
        
        success = rebuild_game_index(args.game)
        if not success:
            sys.exit(1)
    else:
        # 重建所有游戏
        games = get_available_games()
        logger.info(f"📋 找到 {len(games)} 个游戏: {', '.join(games)}")
        
        success_count = 0
        for game in games:
            if rebuild_game_index(game):
                success_count += 1
        
        logger.info(f"📊 重建完成: {success_count}/{len(games)} 个游戏成功")
    
    # 验证新索引
    logger.info("\n" + "=" * 50)
    verify_new_indexes()
    
    logger.info("🎉 BM25S重构完成！")

if __name__ == "__main__":
    main() 