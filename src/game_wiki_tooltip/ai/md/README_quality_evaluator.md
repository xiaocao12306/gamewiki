# RAG输出质量评估工具

## 概述

这个工具用于评估游戏攻略RAG（Retrieval-Augmented Generation）系统的输出质量。它通过对比系统生成的答案与预期答案，使用大语言模型（LLM）进行多维度的质量评分和问题分析。

## 功能特点

- 🎯 **多维度评估**: 从准确性、完整性、相关性、实用性和清晰度5个维度评估答案质量
- 🤖 **智能分析**: 使用Gemini-2.0模型进行智能评估，考虑主观推荐的合理性
- 📊 **详细报告**: 生成包含问题诊断和改进建议的综合报告
- 🔄 **完整流程测试**: 测试完整的RAG流程（查询处理→混合搜索→内容生成）
- 📈 **性能指标**: 记录处理时间、检索置信度等关键指标

## 安装要求

确保已安装所有必要的依赖：

```bash
pip install -r requirements.txt
```

需要配置的环境变量或API密钥：
- `GOOGLE_API_KEY` 或在配置文件中设置Gemini API密钥
- `JINA_API_KEY`（如果使用Jina嵌入）

## 使用方法

### 1. 命令行运行

最简单的方式是使用提供的运行脚本：

```bash
# 评估默认游戏（Helldivers 2）
python src/game_wiki_tooltip/ai/run_quality_evaluation.py

# 评估其他游戏
python src/game_wiki_tooltip/ai/run_quality_evaluation.py --game eldenring

# 指定输出目录
python src/game_wiki_tooltip/ai/run_quality_evaluation.py --output ./evaluation_reports/

# 启用详细日志
python src/game_wiki_tooltip/ai/run_quality_evaluation.py --verbose
```

### 2. 作为模块使用

```python
import asyncio
from rag_quality_evaluator import RAGQualityEvaluator

async def evaluate_game(game_name):
    # 创建评估器
    evaluator = RAGQualityEvaluator(game=game_name)
    
    # 运行评估
    report = await evaluator.evaluate_all()
    
    # 保存报告
    evaluator.save_report(report)
    
    # 获取评估结果
    print(f"平均得分: {report.average_score:.2f}/10")
    
# 运行评估
asyncio.run(evaluate_game("helldiver2"))
```

### 3. 直接运行评估器

```bash
cd src/game_wiki_tooltip/ai
python rag_quality_evaluator.py
```

## 测试数据格式

测试数据应放在 `data/sample_inoutput/{game}.json`，格式如下：

```json
[
  {
    "query": "玩家的问题",
    "answer": "期望得到的答案"
  },
  ...
]
```

## 输出报告

评估完成后会生成两种格式的报告：

### 1. JSON报告 (`quality_report_{game}_{timestamp}.json`)

包含完整的评估数据：
- 每个测试用例的详细评分
- 各维度的平均分
- 常见问题列表
- 改进建议
- RAG系统元数据

### 2. Markdown报告 (`quality_report_{game}_{timestamp}.md`)

人类可读的报告摘要：
- 总体评分和统计
- 主要问题总结
- 关键改进建议
- 每个测试用例的简要结果

## 评估维度说明

1. **准确性 (Accuracy)**: 答案的事实正确性，与期望答案的一致性
2. **完整性 (Completeness)**: 是否涵盖了期望答案中的所有要点
3. **相关性 (Relevance)**: 答案是否直接回答了用户的问题
4. **实用性 (Practicality)**: 答案对游戏玩家的实际帮助程度
5. **清晰度 (Clarity)**: 答案的表达是否清晰易懂

## 结果解读

### 评分标准
- 8-10分：优秀 - 答案质量很高，可以直接使用
- 6-8分：良好 - 答案基本正确，但有改进空间
- 4-6分：一般 - 答案有明显问题，需要改进
- 0-4分：差 - 答案质量很低，需要重大改进

### 常见问题类型

1. **知识库问题**
   - 内容不足：缺少相关攻略内容
   - 信息过时：攻略信息需要更新
   - 覆盖不全：某些主题缺少深度内容

2. **检索问题**
   - 相关性低：检索到的内容与问题关联度不高
   - 排序不当：最相关的内容没有排在前面
   - 召回不足：没有找到存在的相关内容

3. **生成问题**
   - 摘要不当：重要信息被遗漏
   - 结构混乱：答案组织不够清晰
   - 语言问题：表达不够自然流畅

## 改进建议实施

基于评估报告的建议，可以从以下方面改进RAG系统：

1. **扩充知识库**
   ```bash
   # 添加更多游戏攻略内容到 data/knowledge_chunk/{game}.json
   # 然后重建向量索引
   python build_vector_index.py --game {game}
   ```

2. **优化检索策略**
   - 调整混合搜索的权重参数
   - 改进查询重写策略
   - 优化意图识别逻辑

3. **改进答案生成**
   - 调整摘要生成的提示词
   - 优化答案组织结构
   - 增加上下文信息

## 故障排除

### 常见错误

1. **"测试数据文件不存在"**
   - 确保 `data/sample_inoutput/{game}.json` 文件存在
   - 检查文件名拼写是否正确

2. **"API密钥未找到"**
   - 设置环境变量 `GOOGLE_API_KEY`
   - 或在配置文件中添加API密钥

3. **"向量库未找到"**
   - 先运行 `build_vector_index.py` 构建向量库
   - 确保游戏名称匹配

### 调试模式

使用 `--verbose` 参数启用详细日志：
```bash
python run_quality_evaluation.py --verbose
```

## 扩展使用

### 添加新游戏评估

1. 创建测试数据文件 `data/sample_inoutput/{new_game}.json`
2. 确保已构建该游戏的向量库
3. 运行评估：`python run_quality_evaluation.py --game {new_game}`

### 自定义评估维度

修改 `RAGQualityEvaluator.EVALUATION_DIMENSIONS` 添加新的评估维度。

### 批量评估

```python
games = ["helldiver2", "eldenring", "dst"]
for game in games:
    await evaluate_game(game)
```

## 注意事项

- 评估过程会消耗API调用配额（每个测试用例需要2-3次LLM调用）
- 建议先用少量测试用例验证配置是否正确
- 评估结果受LLM主观判断影响，建议多次评估取平均值
- 对于推荐类问题，评估器会考虑答案的合理性而非完全匹配