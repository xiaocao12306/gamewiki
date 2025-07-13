# RAG系统调试指南

## 概述

这个指南帮助你使用新添加的调试功能来比较app.py和run_quality_evaluation.py中的RAG系统差异。

## 调试功能

### 1. 向量搜索调试 (VECTOR-DEBUG)

**位置**: `rag_query.py` - `_search_faiss()` 和 `_search_qdrant()`

**输出信息**:
- 查询文本构建过程
- 向量维度和前5个值
- 索引文件路径和状态
- 检索到的原始结果
- 每个结果的详细信息（分数、主题、摘要、关键词）

**示例输出**:
```
🔍 [VECTOR-DEBUG] 开始FAISS向量检索: query='bile titan弱点', top_k=3
📄 [VECTOR-DEBUG] 构建查询文本: 'bile titan弱点 bile titan弱点 ...'
🔢 [VECTOR-DEBUG] 查询向量维度: (1, 768), 前5个值: [0.1234, -0.5678, ...]
📊 [VECTOR-DEBUG] FAISS索引信息: 总向量数=1250, 维度=768
   📋 [VECTOR-DEBUG] 结果 1:
      - 相似度分数: 0.8523
      - 主题: Terminid: Bile Titan Weaknesses
      - 敌人名称: Bile Titan
```

### 2. BM25搜索调试 (BM25-DEBUG)

**位置**: `enhanced_bm25_indexer.py` - `search()`

**输出信息**:
- 查询标准化和分词过程
- 分数分布范围
- Top-K结果索引和分数
- 匹配关键词和权重信息

**示例输出**:
```
🔍 [BM25-DEBUG] 增强BM25搜索 - 原始查询: bile titan弱点
   📝 [BM25-DEBUG] 标准化查询: bile titan弱点
   🔤 [BM25-DEBUG] 权重化分词: ['bile', 'titan', 'titan', 'titan', '弱点', '弱点', '弱点']
   📊 [BM25-DEBUG] 所有文档分数范围: 0.0000 - 15.2341
   📋 [BM25-DEBUG] 结果 1:
      - 分数: 15.2341
      - 匹配关键词: bile titan(5.0x), 弱点(4.0x)
```

### 3. 混合搜索调试 (HYBRID-DEBUG)

**位置**: `hybrid_retriever.py` - `search()`

**输出信息**:
- 向量搜索和BM25搜索的结果数量
- 融合方法和权重配置
- 融合后的Top结果比较

**示例输出**:
```
🔍 [HYBRID-DEBUG] 开始向量搜索: query='bile titan弱点', top_k=6
📊 [HYBRID-DEBUG] 向量搜索结果数量: 6
🔍 [HYBRID-DEBUG] 开始BM25搜索: query='bile titan弱点', top_k=6
📊 [HYBRID-DEBUG] BM25搜索结果数量: 6
🔄 [HYBRID-DEBUG] 开始分数融合: 方法=rrf
   - 向量权重: 0.5
   - BM25权重: 0.5
   - RRF_K: 60
```

### 4. 分数融合调试 (FUSION-DEBUG)

**位置**: `hybrid_retriever.py` - `_reciprocal_rank_fusion()`

**输出信息**:
- 每个结果的RRF分数计算
- 融合后的排序过程
- 最终分数组合

**示例输出**:
```
🔄 [FUSION-DEBUG] 开始RRF融合: 向量结果=6, BM25结果=6, k=60
   📊 [FUSION-DEBUG] 处理向量搜索结果:
      1. ID: chunk_123
         原始分数: 0.8523
         RRF分数: 0.0164
         主题: Terminid: Bile Titan Weaknesses
   📊 [FUSION-DEBUG] 融合后排序结果:
      1. ID: chunk_123
         最终RRF分数: 0.0328
         向量分数: 0.8523
         BM25分数: 15.2341
```

### 5. 意图重排序调试 (INTENT-DEBUG, RERANK-DEBUG)

**位置**: `intent_aware_reranker.py` - `identify_query_intent()` 和 `rerank_results()`

**输出信息**:
- 意图识别过程和置信度
- 重排序权重调整
- 每个结果的综合分数计算

**示例输出**:
```
🎯 [INTENT-DEBUG] 开始意图识别: query='bile titan弱点'
   📊 [INTENT-DEBUG] 各意图模式匹配结果:
      strategy: 总分=1.500
         - 关键词匹配: 1个, 得分: 0.390
         - 正则匹配: 'weakness', 得分: 0.650
   🏆 [INTENT-DEBUG] 最佳意图: strategy
      - 原始分数: 1.500
      - 置信度: 0.750

🔄 [RERANK-DEBUG] 开始意图重排序: query='bile titan弱点', 结果数量=3
⚖️ [RERANK-DEBUG] 权重调整:
   - 原始意图权重: 0.400
   - 调整后意图权重: 0.550
   - 语义权重: 0.450
```

### 6. 查询处理调试 (QUERY-DEBUG)

**位置**: `unified_query_processor.py` - `process_query()`

**输出信息**:
- 查询翻译和重写过程
- LLM调用详情
- 意图和置信度分析

**示例输出**:
```
🔄 [QUERY-DEBUG] 开始统一查询处理: 'bile titan弱点'
🤖 [QUERY-DEBUG] 调用LLM进行统一处理
   - 使用模型: gemini-2.0-flash-exp
   - 提示词长度: 2341 字符
✅ [QUERY-DEBUG] LLM处理成功:
   - 检测语言: zh
   - 翻译结果: 'bile titan weakness'
   - 重写结果: 'bile titan weak points strategy guide'
   - 意图: guide (置信度: 0.850)
   - 搜索类型: hybrid
   - 处理时间: 0.324秒
```

### 7. 摘要生成调试 (SUMMARY-DEBUG)

**位置**: `gemini_summarizer.py` - `summarize_chunks()`

**输出信息**:
- 输入知识块详情
- Gemini模型调用过程
- 摘要生成结果

**示例输出**:
```
📝 [SUMMARY-DEBUG] 开始Gemini摘要生成
   - 查询: 'bile titan弱点'
   - 知识块数量: 3
   - 模型: gemini-2.0-flash-exp
📋 [SUMMARY-DEBUG] 输入知识块详情:
   1. 主题: Terminid: Bile Titan Weaknesses
      分数: 0.8523
      类型: Enemy_Guide
      敌人: Bile Titan
🤖 [SUMMARY-DEBUG] 调用Gemini生成摘要
   - 提示词长度: 3245 字符
   - 温度设置: 0.3
✅ [SUMMARY-DEBUG] Gemini响应成功
   - 响应长度: 1203 字符
   - 使用的知识块数: 3
```

## 使用步骤

### 1. 运行带调试的查询

**方法1 - 通过app.py**:
```bash
python src/game_wiki_tooltip/app.py
# 在弹出的搜索框中输入查询，观察控制台输出
```

**方法2 - 通过质量评估器**:
```bash
python src/game_wiki_tooltip/ai/run_quality_evaluation.py --game helldiver2
# 观察详细的调试输出
```

### 2. 分析调试输出

查看控制台输出中的调试信息，重点关注：

1. **向量搜索结果**: 检查相似度分数和检索到的文档
2. **BM25搜索结果**: 检查关键词匹配和权重应用
3. **融合过程**: 检查两种搜索结果的合并方式
4. **意图识别**: 检查查询意图分类的准确性
5. **重排序效果**: 检查意图重排序对结果的影响
6. **摘要质量**: 检查最终摘要的生成过程

### 3. 比较两个系统

使用调试比较工具：

```python
from src.game_wiki_tooltip.ai.debug_comparison_tool import create_debug_comparison_tool

# 创建比较工具
comparator = create_debug_comparison_tool()

# 运行比较分析
comparator.run_comparison_analysis("bile titan弱点")
```

### 4. 常见差异分析

**可能的差异原因**:

1. **配置差异**: 
   - 检查混合搜索权重 (vector_weight vs bm25_weight)
   - 检查RRF参数 (rrf_k)
   - 检查top_k设置

2. **数据路径差异**:
   - 检查向量库路径是否一致
   - 检查BM25索引路径是否正确

3. **LLM配置差异**:
   - 检查使用的模型版本
   - 检查温度和其他参数设置

4. **处理流程差异**:
   - 检查是否启用了相同的功能 (summarization, intent_reranking等)
   - 检查查询预处理过程

### 5. 问题排查

**常见问题**:

1. **向量搜索无结果**: 检查向量库路径和索引文件
2. **BM25搜索无结果**: 检查BM25索引路径和文件
3. **融合结果异常**: 检查融合方法和权重配置
4. **意图识别错误**: 检查查询模式和正则表达式
5. **摘要生成失败**: 检查Gemini API配置和网络连接

## 调试技巧

1. **重点关注分数**: 比较向量分数、BM25分数和融合分数的差异
2. **检查步骤顺序**: 确保两个系统的处理步骤顺序一致
3. **验证配置一致性**: 确保使用相同的权重和参数
4. **比较最终结果**: 重点关注最终摘要和置信度的差异

## 输出重定向

如果调试输出太多，可以将其重定向到文件：

```bash
python src/game_wiki_tooltip/app.py > debug_app.log 2>&1
python src/game_wiki_tooltip/ai/run_quality_evaluation.py > debug_evaluation.log 2>&1
```

然后使用文本编辑器或grep命令分析日志文件。 