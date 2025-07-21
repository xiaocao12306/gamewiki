# 混合搜索和向量库问题修复总结

## 问题概述

根据日志分析，发现了两个主要问题：

1. **向量库路径问题**：配置文件中使用了硬编码的绝对路径 `C:\Users\chuwe\...`，这是另一台开发电脑的用户名，导致在当前用户 `62718` 的电脑上路径不匹配。

2. **BM25搜索初始化失败**：`rank_bm25` 包导入时出现 `ComplexWarning` 相关的 numpy 兼容性错误，之前的代码选择了静默降级，这会让用户感觉程序性能不好。

## 修复方案

### 1. 路径问题修复

**修改的文件：**
- `src/game_wiki_tooltip/ai/batch_embedding.py`
- `src/game_wiki_tooltip/ai/vectorstore/*.json`

**修复内容：**
- 将配置文件中的硬编码绝对路径改为相对路径
- 更新路径解析逻辑，确保在运行时动态构建正确的绝对路径
- 修复了所有向量库配置文件：
  - `dst_vectors_config.json`
  - `eldenring_vectors_config.json`
  - `civilization6_vectors_config.json`
  - `helldiver2_vectors_config.json`

**修复前：**
```json
{
  "index_path": "C:\\Users\\chuwe\\PycharmProjects\\gamewiki\\src\\game_wiki_tooltip\\ai\\vectorstore\\dst_vectors",
  "bm25_index_path": "C:\\Users\\chuwe\\PycharmProjects\\gamewiki\\src\\game_wiki_tooltip\\ai\\vectorstore\\dst_vectors\\enhanced_bm25_index.pkl"
}
```

**修复后：**
```json
{
  "index_path": "dst_vectors",
  "bm25_index_path": "dst_vectors/enhanced_bm25_index.pkl"
}
```

### 2. 错误处理改进

**修改的文件：**
- `src/game_wiki_tooltip/ai/enhanced_bm25_indexer.py`
- `src/game_wiki_tooltip/ai/hybrid_retriever.py`
- `src/game_wiki_tooltip/ai/rag_query.py`
- `src/game_wiki_tooltip/ai/batch_embedding.py`

**修复内容：**

#### 2.1 创建专用错误类
```python
class BM25UnavailableError(Exception):
    """BM25功能不可用错误"""
    pass

class VectorStoreUnavailableError(Exception):
    """向量库不可用错误"""
    pass
```

#### 2.2 BM25索引器改进
- 移除静默降级逻辑
- 在 `rank_bm25` 导入失败时直接抛出 `BM25UnavailableError`
- 提供详细的错误信息和解决方案建议
- 所有相关方法（`build_index`, `search`, `save_index`, `load_index`）都会在BM25不可用时抛出明确错误

#### 2.3 向量库系统改进
- 在批量嵌入模块不可用时抛出 `VectorStoreUnavailableError`
- 在向量库文件不存在时提供详细错误信息，包括可用的游戏列表
- 在混合检索器初始化失败时抛出明确错误

#### 2.4 混合检索器改进
- 在BM25索引文件不存在时直接抛出 `FileNotFoundError`
- 在BM25索引加载失败时重新抛出相应错误
- 移除所有静默降级逻辑

## 错误信息示例

### BM25不可用错误
```
BM25搜索功能初始化失败: rank_bm25包导入错误 - cannot import name 'ComplexWarning' from 'numpy.core.numeric'
这通常是由于numpy版本兼容性问题导致的。请尝试以下解决方案：
1. 升级rank_bm25: pip install rank_bm25 --upgrade
2. 检查numpy版本兼容性: pip install 'numpy>=1.21.0,<2.0'
3. 重新安装相关包: pip uninstall rank_bm25 numpy && pip install numpy rank_bm25
```

### 向量库不存在错误
```
向量库不存在: 未找到游戏 'unknown_game' 的向量库配置文件
搜索路径: C:\Users\62718\PycharmProjects\gamewiki\src\game_wiki_tooltip\ai\vectorstore
查找模式: unknown_game_vectors_config.json
可用的游戏向量库: dst, eldenring, civilization6, helldiver2
```

## 受益效果

1. **明确的错误反馈**：用户现在能够得到具体的错误信息，知道哪个功能出现了问题以及如何解决
2. **跨平台兼容**：路径问题得到解决，代码可以在不同用户的电脑上正常运行
3. **更好的用户体验**：不再有静默降级，用户不会感觉程序性能突然变差
4. **便于调试**：详细的错误信息帮助开发者和用户快速定位问题

## 测试建议

运行 `python test_fixes.py` 来验证修复效果，该脚本会测试：
1. BM25索引器初始化
2. 向量库路径解析
3. RAG系统初始化

## 注意事项

- 如果遇到 `rank_bm25` 导入问题，按照错误信息中的建议执行相应的 pip 命令
- 确保所有向量库文件存在于正确的位置
- 如果需要重新构建向量库，新生成的配置文件将自动使用相对路径 