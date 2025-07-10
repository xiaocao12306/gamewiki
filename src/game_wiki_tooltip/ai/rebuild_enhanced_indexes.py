"""
重建增强索引脚本
================

功能：
1. 从现有知识库重新构建增强BM25索引
2. 保持向量索引不变
3. 测试新索引的工作情况
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

# 解决相对导入问题
if __name__ == "__main__":
    # 添加项目根目录到Python路径
    project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(project_root))

try:
    # 尝试相对导入（作为模块运行时）
    from .enhanced_bm25_indexer import EnhancedBM25Indexer
    from .enhanced_query_processor import EnhancedQueryProcessor
except ImportError:
    # 回退到绝对导入（直接运行时）
    from src.game_wiki_tooltip.ai.enhanced_bm25_indexer import EnhancedBM25Indexer
    from src.game_wiki_tooltip.ai.enhanced_query_processor import EnhancedQueryProcessor

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IndexRebuilder:
    """索引重建器"""
    
    def __init__(self, game_name: str = "helldiver2"):
        """
        初始化索引重建器
        
        Args:
            game_name: 游戏名称
        """
        self.game_name = game_name
        self.base_path = Path(__file__).parent / "vectorstore"
        self.vector_path = self.base_path / f"{game_name}_vectors"
        
    def load_existing_chunks(self) -> List[Dict[str, Any]]:
        """从现有的metadata.json加载知识块"""
        metadata_path = self.vector_path / "metadata.json"
        
        if not metadata_path.exists():
            raise FileNotFoundError(f"元数据文件不存在: {metadata_path}")
        
        logger.info(f"加载知识块: {metadata_path}")
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        logger.info(f"成功加载 {len(chunks)} 个知识块")
        return chunks
    
    def rebuild_enhanced_bm25_index(self, chunks: List[Dict[str, Any]]) -> str:
        """重建增强BM25索引"""
        logger.info("开始重建增强BM25索引...")
        
        # 创建增强BM25索引器
        enhanced_indexer = EnhancedBM25Indexer()
        
        # 构建索引
        enhanced_indexer.build_index(chunks)
        
        # 保存索引
        index_path = self.vector_path / "enhanced_bm25_index.pkl"
        enhanced_indexer.save_index(str(index_path))
        
        logger.info(f"增强BM25索引重建完成: {index_path}")
        
        # 获取统计信息
        stats = enhanced_indexer.get_stats()
        logger.info(f"索引统计: {stats}")
        
        return str(index_path)
    
    def test_enhanced_index(self, index_path: str) -> None:
        """测试增强索引"""
        logger.info("开始测试增强索引...")
        
        # 加载索引
        enhanced_indexer = EnhancedBM25Indexer()
        enhanced_indexer.load_index(index_path)
        
        # 创建查询处理器
        query_processor = EnhancedQueryProcessor()
        
        # 测试查询
        test_queries = [
            "how to kill bile titan",
            "bile titan weakness",
            "bt weak point",
            "hulk eye socket",
            "charger rear weakness",
            "如何击杀胆汁泰坦",
            "巨人机甲弱点"
        ]
        
        logger.info("=" * 60)
        logger.info("测试增强索引检索效果")
        logger.info("=" * 60)
        
        for query in test_queries:
            logger.info(f"\n🔍 测试查询: {query}")
            
            # 查询处理
            processed = query_processor.rewrite_query(query)
            logger.info(f"  📝 查询重写: {processed['original']} → {processed['rewritten']}")
            logger.info(f"  🎯 意图识别: {processed['intent']} (置信度: {processed['confidence']:.2f})")
            logger.info(f"  👾 检测敌人: {processed['detected_enemies']}")
            
            # BM25搜索
            results = enhanced_indexer.search(processed['rewritten'], top_k=3)
            
            logger.info(f"  📊 搜索结果 ({len(results)} 个):")
            for i, result in enumerate(results[:3], 1):
                chunk = result['chunk']
                topic = chunk.get('topic', 'Unknown')
                score = result['score']
                relevance = result['match_info']['relevance_reason']
                
                logger.info(f"    {i}. 分数: {score:.3f} | {topic}")
                logger.info(f"       相关性: {relevance}")
    
    def verify_integration(self) -> None:
        """验证与现有系统的集成"""
        logger.info("验证系统集成...")
        
        # 检查向量索引
        faiss_path = self.vector_path / "index.faiss"
        if faiss_path.exists():
            logger.info(f"✅ 向量索引存在: {faiss_path}")
        else:
            logger.warning(f"⚠️  向量索引不存在: {faiss_path}")
        
        # 检查配置文件
        config_path = self.base_path / f"{self.game_name}_vectors_config.json"
        if config_path.exists():
            logger.info(f"✅ 配置文件存在: {config_path}")
        else:
            logger.warning(f"⚠️  配置文件不存在: {config_path}")
        
        # 检查增强BM25索引
        enhanced_bm25_path = self.vector_path / "enhanced_bm25_index.pkl"
        if enhanced_bm25_path.exists():
            logger.info(f"✅ 增强BM25索引存在: {enhanced_bm25_path}")
        else:
            logger.error(f"❌ 增强BM25索引不存在: {enhanced_bm25_path}")
        
        logger.info("集成验证完成")
    
    def run_rebuild(self) -> str:
        """运行完整的重建流程"""
        try:
            logger.info(f"开始重建 {self.game_name} 的增强索引")
            
            # 1. 加载现有知识块
            chunks = self.load_existing_chunks()
            
            # 2. 重建增强BM25索引
            index_path = self.rebuild_enhanced_bm25_index(chunks)
            
            # 3. 测试新索引
            self.test_enhanced_index(index_path)
            
            # 4. 验证集成
            self.verify_integration()
            
            logger.info("✅ 索引重建完成！")
            logger.info(f"📍 增强BM25索引路径: {index_path}")
            
            return index_path
            
        except Exception as e:
            logger.error(f"❌ 索引重建失败: {e}")
            raise


def rebuild_for_game(game_name: str) -> str:
    """为指定游戏重建索引"""
    rebuilder = IndexRebuilder(game_name)
    return rebuilder.run_rebuild()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="重建增强BM25索引")
    parser.add_argument("--game", type=str, default="helldiver2", help="游戏名称")
    parser.add_argument("--test-only", action="store_true", help="仅测试现有索引")
    
    args = parser.parse_args()
    
    if args.test_only:
        # 仅测试现有索引
        rebuilder = IndexRebuilder(args.game)
        enhanced_bm25_path = rebuilder.vector_path / "enhanced_bm25_index.pkl"
        
        if enhanced_bm25_path.exists():
            rebuilder.test_enhanced_index(str(enhanced_bm25_path))
        else:
            logger.error(f"增强BM25索引不存在: {enhanced_bm25_path}")
    else:
        # 完整重建
        index_path = rebuild_for_game(args.game)
        print(f"\n✅ 重建完成！增强BM25索引路径: {index_path}")


if __name__ == "__main__":
    main() 