"""
批量构建所有游戏知识库
====================

为所有支持的游戏构建向量索引和BM25索引，支持：
- Helldivers 2
- Don't Starve Together (DST)
- Elden Ring
- Civilization 6
"""

import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('build_indexes.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def get_supported_games() -> Dict[str, str]:
    """获取支持的游戏列表"""
    return {
        "helldiver2": "Helldivers 2",
        "dst": "Don't Starve Together", 
        "eldenring": "Elden Ring",
        "civilization6": "Civilization 6"
    }

def check_knowledge_files(knowledge_dir: str = "data/knowledge_chunk") -> List[str]:
    """检查可用的知识库文件"""
    knowledge_path = Path(knowledge_dir)
    supported_games = get_supported_games()
    available_games = []
    
    logger.info("检查知识库文件...")
    
    for game_id, game_name in supported_games.items():
        json_file = knowledge_path / f"{game_id}.json"
        if json_file.exists():
            file_size = json_file.stat().st_size / (1024 * 1024)  # MB
            logger.info(f"✅ {game_name}: {json_file} ({file_size:.2f} MB)")
            available_games.append(game_id)
        else:
            logger.warning(f"❌ {game_name}: 文件不存在 {json_file}")
    
    return available_games

def build_game_index(game_id: str, 
                    knowledge_dir: str = "data/knowledge_chunk",
                    output_dir: str = "src/game_wiki_tooltip/ai/vectorstore") -> bool:
    """为单个游戏构建索引"""
    from .batch_embedding import process_game_knowledge
    
    game_name = get_supported_games().get(game_id, game_id)
    
    try:
        logger.info(f"🎮 开始构建 {game_name} 知识库...")
        
        config_path = process_game_knowledge(
            game_name=game_id,
            knowledge_dir=knowledge_dir,
            output_dir=output_dir
        )
        
        logger.info(f"✅ {game_name} 知识库构建完成: {config_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ {game_name} 知识库构建失败: {e}")
        return False

def build_all_game_indexes(knowledge_dir: str = "data/knowledge_chunk",
                          output_dir: str = "src/game_wiki_tooltip/ai/vectorstore",
                          games: List[str] = None) -> Dict[str, bool]:
    """构建所有游戏的知识库索引"""
    
    logger.info("=== 开始批量构建游戏知识库 ===")
    
    # 检查可用的知识库文件
    available_games = check_knowledge_files(knowledge_dir)
    
    if not available_games:
        logger.error("没有找到任何可用的知识库文件")
        return {}
    
    # 如果指定了特定游戏，则只处理指定的游戏
    if games:
        available_games = [g for g in available_games if g in games]
        if not available_games:
            logger.error(f"指定的游戏 {games} 都没有对应的知识库文件")
            return {}
    
    logger.info(f"将要处理的游戏: {[get_supported_games()[g] for g in available_games]}")
    
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    results = {}
    
    # 逐个构建游戏索引
    for i, game_id in enumerate(available_games, 1):
        game_name = get_supported_games()[game_id]
        
        logger.info(f"\n📊 进度: {i}/{len(available_games)} - {game_name}")
        logger.info("-" * 50)
        
        success = build_game_index(game_id, knowledge_dir, output_dir)
        results[game_id] = success
        
        if success:
            logger.info(f"✅ {game_name} 完成")
        else:
            logger.error(f"❌ {game_name} 失败")
    
    # 总结结果
    logger.info("\n" + "=" * 60)
    logger.info("🏁 批量构建完成 - 结果总结:")
    
    successful = [g for g, success in results.items() if success]
    failed = [g for g, success in results.items() if not success]
    
    if successful:
        logger.info(f"✅ 成功构建 ({len(successful)}):")
        for game_id in successful:
            logger.info(f"   - {get_supported_games()[game_id]}")
    
    if failed:
        logger.error(f"❌ 构建失败 ({len(failed)}):")
        for game_id in failed:
            logger.error(f"   - {get_supported_games()[game_id]}")
    
    logger.info(f"📈 总体成功率: {len(successful)}/{len(results)} ({len(successful)/len(results)*100:.1f}%)")
    
    return results

def verify_indexes(output_dir: str = "src/game_wiki_tooltip/ai/vectorstore") -> None:
    """验证构建的索引文件"""
    from .enhanced_bm25_indexer import EnhancedBM25Indexer
    
    logger.info("\n🔍 验证构建的索引...")
    
    output_path = Path(output_dir)
    config_files = list(output_path.glob("*_vectors_config.json"))
    
    for config_file in config_files:
        try:
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            game_name = config.get('game_name', 'unknown')
            chunk_count = config.get('chunk_count', 0)
            hybrid_enabled = config.get('hybrid_search_enabled', False)
            
            logger.info(f"📁 {config_file.stem}:")
            logger.info(f"   游戏: {get_supported_games().get(game_name, game_name)}")
            logger.info(f"   知识块: {chunk_count}")
            logger.info(f"   混合搜索: {'✅' if hybrid_enabled else '❌'}")
            
            # 测试BM25索引加载
            if hybrid_enabled:
                try:
                    indexer = EnhancedBM25Indexer(game_name=game_name)
                    bm25_path = Path(config['bm25_index_path'])
                    if bm25_path.exists():
                        indexer.load_index(str(bm25_path))
                        stats = indexer.get_stats()
                        logger.info(f"   BM25状态: ✅ ({stats['document_count']} 文档)")
                    else:
                        logger.warning(f"   BM25文件: ❌ 不存在")
                except Exception as e:
                    logger.warning(f"   BM25加载: ❌ {e}")
                    
        except Exception as e:
            logger.error(f"验证 {config_file} 失败: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="批量构建游戏知识库索引")
    parser.add_argument("--games", nargs="+", choices=list(get_supported_games().keys()),
                       help="指定要构建的游戏 (默认: 所有可用游戏)")
    parser.add_argument("--knowledge-dir", default="data/knowledge_chunk",
                       help="知识库文件目录 (默认: data/knowledge_chunk)")
    parser.add_argument("--output-dir", default="src/game_wiki_tooltip/ai/vectorstore",
                       help="输出目录 (默认: src/game_wiki_tooltip/ai/vectorstore)")
    parser.add_argument("--verify", action="store_true",
                       help="构建后验证索引文件")
    
    args = parser.parse_args()
    
    # 构建索引
    results = build_all_game_indexes(
        knowledge_dir=args.knowledge_dir,
        output_dir=args.output_dir,
        games=args.games
    )
    
    # 验证索引
    if args.verify:
        verify_indexes(args.output_dir)
    
    # 退出码
    failed_count = sum(1 for success in results.values() if not success)
    sys.exit(failed_count) 