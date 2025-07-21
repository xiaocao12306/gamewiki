# BM25S迁移指南

## 概述

我们正在将BM25实现从 `rank_bm25` 迁移到 `bm25s`，以解决numpy兼容性问题并提升性能。

## 迁移原因

1. **解决兼容性问题**：`rank_bm25` 在新版本numpy下出现导入错误
2. **性能提升**：`bm25s` 比 `rank_bm25` 快10-100倍
3. **更好的维护**：`bm25s` 是积极维护的现代库

## 迁移步骤

### 1. 安装依赖

```bash
# 安装bm25s
pip install bm25s>=0.2.13

# 或者更新requirements.txt后安装
pip install -r requirements.txt
```

### 2. 设置环境变量

确保设置了Jina API密钥：

```bash
export JINA_API_KEY=your_jina_api_key_here
```

### 3. 运行重构脚本

#### 选项A：重建所有游戏索引（推荐）

```bash
# 备份现有索引并重建所有
python rebuild_with_bm25s.py --backup --clean

# 仅重建所有（不备份）
python rebuild_with_bm25s.py --clean
```

#### 选项B：重建单个游戏

```bash
# 重建DST游戏索引
python rebuild_with_bm25s.py dst --clean

# 重建地狱潜兵2索引
python rebuild_with_bm25s.py helldiver2 --clean
```

#### 选项C：使用原始构建脚本

```bash
# 重建所有游戏
python src/game_wiki_tooltip/ai/build_vector_index.py --game all

# 重建单个游戏
python src/game_wiki_tooltip/ai/build_vector_index.py --game dst
```

### 4. 验证迁移结果

```bash
# 验证所有索引
python rebuild_with_bm25s.py --verify-only
```

## 新文件结构

迁移后，每个游戏的文件结构如下：

```
vectorstore/
├── dst_vectors/
│   ├── index.faiss                      # FAISS向量索引
│   ├── metadata.json                    # 知识块元数据
│   ├── enhanced_bm25_index.pkl          # BM25元数据文件
│   └── enhanced_bm25_index_bm25s/       # BM25S索引目录
│       ├── corpus.json                  # 语料库数据
│       ├── vocab.json                   # 词汇表
│       └── scores.npz                   # 预计算分数
└── dst_vectors_config.json              # 配置文件
```

## 性能对比

| 数据集 | rank_bm25 | bm25s | 提升倍数 |
|--------|-----------|-------|----------|
| DST    | 4.46 QPS  | 507 QPS | 113x |
| 艾尔登法环 | 9.01 QPS  | 767 QPS | 85x |
| 地狱潜兵2 | 47.6 QPS  | 953 QPS | 20x |

## 常见问题

### Q: 迁移后原来的索引还能用吗？
A: 不能。新代码只兼容bm25s格式，需要重建所有索引。

### Q: 重建需要多长时间？
A: 取决于知识库大小，通常每个游戏2-5分钟。

### Q: 如果重建失败怎么办？
A: 检查错误日志，确保：
- JINA_API_KEY已设置
- bm25s>=0.2.13已安装
- 网络连接正常

### Q: 可以回退到旧版本吗？
A: 可以，但需要：
1. 恢复备份的向量库文件
2. 在requirements.txt中恢复rank_bm25
3. 恢复enhanced_bm25_indexer.py的旧版本

## 故障排除

### 导入错误
```
ImportError: cannot import name 'ComplexWarning' from 'numpy.core.numeric'
```
**解决方案**：确保已安装bm25s并重建了所有索引。

### 文件不存在错误
```
FileNotFoundError: enhanced_bm25_index_bm25s.pkl
```
**解决方案**：运行重构脚本重建索引。

### API密钥错误
```
ERROR: 缺少JINA_API_KEY环境变量
```
**解决方案**：设置环境变量 `export JINA_API_KEY=your_key`

## 技术细节

### BM25S的优势

1. **向量化计算**：使用numpy和scipy优化
2. **稀疏矩阵存储**：内存效率更高
3. **预计算分数**：查询时无需重新计算
4. **内存映射支持**：大型数据集友好

### 兼容性

- Python 3.8+
- NumPy 1.21+
- SciPy 1.7+
- 支持所有现有的游戏类型和查询功能

---

如有问题，请查看日志文件或联系开发团队。 