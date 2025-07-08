# 批量嵌入功能使用指南

## 概述

本模块实现了基于Jina API的批量嵌入功能，可以将knowledge_chunks JSON文件批量转换为向量并存储到FAISS/Qdrant向量库中，为RAG系统提供高效的语义检索能力。

## 核心特性

- **批量处理**: 支持大批量文本的并行嵌入处理
- **多向量库支持**: 支持FAISS和Qdrant两种向量库
- **优化存储**: 使用768维向量和归一化，节省62%存储空间
- **智能文本构建**: 只将关键信息（topic、summary、keywords）送入向量模型
- **命令行工具**: 提供便捷的命令行接口

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包：
- `numpy>=1.24.0`: 数值计算
- `tqdm>=4.65.0`: 进度条显示
- `faiss-cpu>=1.7.4`: FAISS向量库
- `qdrant-client>=1.7.0`: Qdrant向量库
- `langchain-community>=0.0.10`: LangChain集成
- `requests>=2.31`: HTTP请求

## 环境配置

### 1. 设置Jina API密钥

```bash
# Windows
set JINA_API_KEY=your_api_key_here

# Linux/Mac
export JINA_API_KEY=your_api_key_here
```

### 2. 获取Jina API密钥

1. 访问 [Jina AI](https://jina.ai/)
2. 注册账号并获取API密钥
3. 将密钥设置为环境变量

## 使用方法

### 1. 命令行工具

#### 处理单个游戏
```bash
python src/game_wiki_tooltip/ai/build_vector_index.py --game helldiver2
```

#### 处理所有游戏
```bash
python src/game_wiki_tooltip/ai/build_vector_index.py --game all
```

#### 处理自定义文件
```bash
python src/game_wiki_tooltip/ai/build_vector_index.py --file data/knowledge_chunk/helldiver2.json
```

#### 使用Qdrant向量库
```bash
python src/game_wiki_tooltip/ai/build_vector_index.py --game helldiver2 --vector-store qdrant
```

#### 列出可用游戏
```bash
python src/game_wiki_tooltip/ai/build_vector_index.py --list-games
```

### 2. Python API

#### 基本用法
```python
from src.game_wiki_tooltip.ai.batch_embedding import BatchEmbeddingProcessor

# 创建处理器
processor = BatchEmbeddingProcessor()

# 处理JSON文件
config_path = processor.process_json_file(
    json_path="data/knowledge_chunk/helldiver2.json",
    output_dir="src/game_wiki_tooltip/ai/vectorstore",
    collection_name="helldiver2_vectors"
)
```

#### 便捷函数
```python
from src.game_wiki_tooltip.ai.batch_embedding import process_game_knowledge

# 处理指定游戏
config_path = process_game_knowledge("helldiver2")
```

### 3. RAG查询

#### 增强RAG查询
```python
from src.game_wiki_tooltip.ai.rag_query import query_enhanced_rag

# 执行查询
result = await query_enhanced_rag(
    question="地狱潜兵2 虫族配装推荐",
    game_name="helldiver2",
    top_k=3
)

print(result["answer"])
print(f"相关度: {result['confidence']}")
```

## 文件结构

```
src/game_wiki_tooltip/ai/
├── batch_embedding.py          # 批量嵌入处理器
├── rag_query.py               # 增强RAG查询接口
├── build_vector_index.py      # 命令行工具
├── test_batch_embedding.py    # 测试脚本
└── vectorstore/               # 向量库存储目录
    ├── helldiver2_vectors/    # Helldivers 2向量库
    ├── helldiver2_vectors_config.json
    └── ...
```

## 技术细节

### 1. 文本构建策略

只将关键信息送入向量模型：
```python
text_parts = [
    f"Topic: {chunk['topic']}",
    chunk['summary'],
    f"Keywords: {', '.join(chunk['keywords'])}"
]
```

**为什么这样做？**
- 召回需要"信号"，而不是全部细节
- 避免向量方向被稀释
- 节省token成本和向量维度
- 详细数据保存在metadata中供后续使用

### 2. 向量优化

- **维度**: 使用768维（从2048维截取），节省62%存储
- **归一化**: `normalized=True`，直接返回L2-norm为1的向量
- **距离度量**: 使用余弦相似度，避免额外归一化步骤

### 3. 批处理优化

- **默认批量大小**: 64
- **进度显示**: 使用tqdm显示处理进度
- **错误处理**: 完善的异常处理和重试机制

## 测试

运行测试脚本验证功能：

```bash
python src/game_wiki_tooltip/ai/test_batch_embedding.py
```

测试内容包括：
- 批量嵌入处理器功能
- 向量库创建
- RAG查询
- 命令行工具

## 性能优化建议

### 1. 批量大小调优
- 小数据集（<1000条）: 32-64
- 中等数据集（1000-10000条）: 64-128
- 大数据集（>10000条）: 128-256

### 2. 向量库选择
- **FAISS**: 适合本地部署，内存占用小
- **Qdrant**: 适合分布式部署，支持复杂查询

### 3. 存储优化
- 使用SSD存储向量库文件
- 定期清理临时文件
- 压缩历史向量库

## 故障排除

### 常见问题

1. **API密钥错误**
   ```
   错误: 需要提供JINA_API_KEY环境变量或参数
   ```
   解决: 检查环境变量设置

2. **依赖包缺失**
   ```
   ImportError: 需要安装faiss-cpu或qdrant-client
   ```
   解决: 运行 `pip install -r requirements.txt`

3. **文件不存在**
   ```
   FileNotFoundError: 找不到知识库文件
   ```
   解决: 检查文件路径和格式

4. **网络超时**
   ```
   requests.exceptions.Timeout
   ```
   解决: 检查网络连接，增加timeout时间

### 日志查看

查看详细日志：
```bash
python src/game_wiki_tooltip/ai/build_vector_index.py --game helldiver2 --verbose
```

日志文件位置：`vector_build.log`

## 扩展功能

### 1. 自定义文本构建
```python
def custom_build_text(chunk):
    # 自定义文本构建逻辑
    return custom_text

processor.build_text = custom_build_text
```

### 2. 自定义向量库
```python
# 支持其他向量库
processor = BatchEmbeddingProcessor(vector_store_type="custom")
```

### 3. 增量更新
```python
# 支持增量添加新知识块
processor.add_chunks(new_chunks, existing_config_path)
```

## 更新日志

- **v1.0.0**: 初始版本，支持基本批量嵌入功能
- **v1.1.0**: 添加Qdrant支持，优化存储策略
- **v1.2.0**: 增强RAG查询，添加命令行工具

## 贡献

欢迎提交Issue和Pull Request来改进这个模块！

## 许可证

本项目采用MIT许可证。 