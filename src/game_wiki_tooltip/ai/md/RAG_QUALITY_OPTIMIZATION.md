# RAG 质量优化指南

## 问题描述

在对比 `rag_quality_evaluator.py` 和 `rag_query.py` 的输出时，发现 evaluator 中的 RAG 引擎返回的知识片段质量明显高于普通的 rag_query。

## 根本原因

### 1. 混合搜索权重配置差异

- **Evaluator 配置**（高质量）:
  ```python
  "vector_weight": 0.5,  # 平衡权重
  "bm25_weight": 0.5,    # 平衡权重
  ```

- **默认配置**（质量较低）:
  ```python
  "vector_weight": 0.3,  # 偏向 BM25
  "bm25_weight": 0.7,    # 偏向 BM25
  ```

权重差异导致：
- 默认配置过度依赖 BM25 关键词匹配（70%权重）
- 语义搜索权重不足（仅30%）
- 如果 BM25 索引质量不够好，会严重影响整体检索质量

### 2. 功能启用差异

Evaluator 明确启用了所有增强功能：
- `enable_summarization=True` - 启用智能摘要
- `enable_hybrid_search=True` - 启用混合搜索
- `enable_intent_reranking=True` - 启用意图感知重排序

而默认配置可能没有全部启用这些功能。

## 解决方案

### 方案1：更新全局配置文件（已实施）

更新 `src/game_wiki_tooltip/assets/settings.json`：

```json
{
    "hybrid_search": {
        "enabled": true,
        "fusion_method": "rrf",
        "vector_weight": 0.5,
        "bm25_weight": 0.5,
        "rrf_k": 60
    },
    "intent_reranking": {
        "enabled": true,
        "intent_weight": 0.4,
        "semantic_weight": 0.6
    }
}
```

### 方案2：直接使用优化配置（推荐）

在调用 RAG 查询时，明确指定优化配置：

```python
from .ai.rag_query import query_enhanced_rag
from .config import LLMConfig

# 使用与 evaluator 相同的配置
result = await query_enhanced_rag(
    question=user_query,
    game_name=game_name,
    top_k=5,  # 增加检索数量
    enable_hybrid_search=True,
    hybrid_config={
        "fusion_method": "rrf",
        "vector_weight": 0.5,  # 关键：平衡权重
        "bm25_weight": 0.5,    # 关键：平衡权重
        "rrf_k": 60
    },
    llm_config=LLMConfig(),
    enable_summarization=True,
    enable_intent_reranking=True,
    reranking_config={
        "intent_weight": 0.4,
        "semantic_weight": 0.6
    }
)
```

### 方案3：创建高质量 RAG 工厂函数

使用 `example_high_quality_rag.py` 中的函数：

```python
from .ai.example_high_quality_rag import create_high_quality_rag_engine

# 创建优化的 RAG 引擎
rag_engine = await create_high_quality_rag_engine(game_name)
result = await rag_engine.query(user_query, top_k=5)
```

## 配置参数详解

### 混合搜索权重

- **vector_weight: 0.5** - 语义搜索权重
  - 捕获查询的语义含义
  - 找到概念相关的内容
  - 处理同义词和相关概念

- **bm25_weight: 0.5** - 关键词搜索权重  
  - 精确匹配关键词
  - 处理游戏专有名词
  - 找到包含特定术语的内容

平衡的权重（0.5/0.5）结合了两种方法的优势，提供最佳的检索效果。

### 其他重要参数

- **top_k**: 建议使用 5 而非默认的 3，获取更多上下文
- **enable_intent_reranking**: 根据用户意图重新排序结果
- **enable_summarization**: 使用 LLM 生成友好的摘要回复

## 验证方法

运行测试脚本对比不同配置的效果：

```bash
python -m src.game_wiki_tooltip.ai.test_rag_quality_comparison
```

## 性能影响

优化配置可能会略微增加响应时间：
- 混合搜索：+50-100ms
- 意图重排序：+20-50ms  
- 智能摘要：+200-500ms（如启用）

但质量提升通常值得这些额外的延迟。

## 最佳实践

1. **始终使用平衡的权重配置**（0.5/0.5）
2. **启用所有增强功能**以获得最佳质量
3. **增加 top_k 到 5** 以获得更丰富的上下文
4. **定期评估和调优**配置参数
5. **监控查询性能**，在质量和速度间找到平衡

## 注意事项

- 确保 BM25 索引是最新的并且质量良好
- 向量索引和 BM25 索引应该基于相同的知识库
- 定期使用 evaluator 评估 RAG 质量
- 根据具体游戏和用户需求调整参数 