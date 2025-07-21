# BM25索引重构指南（仅BM25部分）

## 🎯 目标

只重构BM25部分，保留现有的FAISS向量库，快速解决numpy兼容性问题。

## ⚡ 优势

- **🚀 速度快**：无需重建耗时的向量库
- **💾 节省资源**：保留现有工作成果
- **🎯 针对性强**：只解决兼容性问题
- **⚡ 性能提升**：BM25搜索速度提升10-100倍

## 📋 前提条件

✅ 您已经有现有的向量库文件：
```
src/game_wiki_tooltip/ai/vectorstore/
├── dst_vectors/
│   ├── index.faiss      ✓ 保留
│   ├── metadata.json    ✓ 保留
│   └── enhanced_bm25_index.pkl  ❌ 需要重建
├── dst_vectors_config.json  ✓ 更新
└── ... 其他游戏
```

## 🚀 执行步骤

### 1. 安装bm25s库

```bash
pip install bm25s>=0.2.13
```

### 2. 执行重构（三种方式）

#### 方式A：重建所有游戏的BM25索引（推荐）
```bash
python rebuild_bm25_only.py --clean
```

#### 方式B：重建单个游戏
```bash
# 重建DST的BM25索引
python rebuild_bm25_only.py dst --clean

# 重建地狱潜兵2的BM25索引
python rebuild_bm25_only.py helldiver2 --clean
```

#### 方式C：不清理旧文件直接重建
```bash
python rebuild_bm25_only.py
```

### 3. 验证重构结果

```bash
python rebuild_bm25_only.py --verify-only
```

## 📊 预期输出

成功的重构会显示：
```
🚀 BM25索引重构工具启动
==================================================
📋 说明：此工具仅重构BM25索引，保留现有FAISS向量库
✅ bm25s版本: 0.2.13
📋 找到 4 个现有游戏: dst, eldenring, civilization6, helldiver2

==================== dst ====================
📖 加载知识块数据: .../dst_vectors/metadata.json
✅ 成功加载 111 个知识块
🔨 构建新的BM25索引...
💾 保存新索引到: .../dst_vectors/enhanced_bm25_index.pkl
📝 更新配置文件: .../dst_vectors_config.json
🧪 测试新索引...
✅ 索引测试成功
✅ 游戏 'dst' 的BM25索引重建成功!

... (其他游戏类似)

📊 重建完成: 4/4 个游戏成功
🔍 验证BM25索引...
  ✅ dst:
    ✓ BM25索引文件
    ✓ 配置文件  
    ✓ BM25S目录
    ✓ 混合搜索启用
🎉 BM25索引重构完成！
```

## 🔍 文件变化

### 每个游戏目录的变化：

**重构前：**
```
dst_vectors/
├── index.faiss              # 保持不变
├── metadata.json            # 保持不变
└── enhanced_bm25_index.pkl  # 旧格式 (rank_bm25)
```

**重构后：**
```
dst_vectors/
├── index.faiss                      # 保持不变 ✓
├── metadata.json                    # 保持不变 ✓
├── enhanced_bm25_index.pkl          # 新格式元数据 🆕
└── enhanced_bm25_index_bm25s/       # bm25s索引目录 🆕
    ├── corpus.json
    ├── vocab.json
    └── scores.npz
```

## ⏱️ 时间估算

| 游戏 | 知识块数量 | 预计时间 |
|------|------------|----------|
| DST | 111 | 30-60秒 |
| 艾尔登法环 | 214 | 1-2分钟 |
| 地狱潜兵2 | 83 | 20-40秒 |
| 文明6 | 28 | 10-20秒 |
| **总计** | **436** | **2-4分钟** |

## 🆚 对比：完整重建 vs BM25重构

| 项目 | 完整重建 | BM25重构 |
|------|----------|----------|
| ⏱️ 时间 | 20-40分钟 | 2-4分钟 |
| 🌐 网络需求 | 需要Jina API | 不需要 |
| 💾 保留数据 | 全部重建 | 保留向量库 |
| 🎯 解决问题 | 全面 | 针对性 |

## 🔧 故障排除

### 错误：bm25s未安装
```
❌ bm25s未安装
请运行: pip install bm25s>=0.2.13
```
**解决**：`pip install bm25s>=0.2.13`

### 错误：未找到向量库
```
❌ 未找到任何现有的向量库
请先使用 build_vector_index.py 构建向量库
```
**解决**：确保已有向量库，或先运行完整构建

### 错误：元数据文件不存在
```
FileNotFoundError: 元数据文件不存在: .../metadata.json
```
**解决**：说明向量库不完整，需要先重建向量库

## ✅ 验证成功标志

重构成功后，您应该看到：

1. ✅ 所有游戏显示"索引测试成功"
2. ✅ 验证显示所有检查项都是"✓"
3. ✅ 程序启动时不再报numpy错误
4. ✅ 混合搜索功能正常工作

---

**💡 提示**：重构完成后，您可以立即启动程序测试，无需额外配置！ 