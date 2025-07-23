# GameWikiTooltip - 游戏Wiki悬浮窗工具

一个专为游戏玩家设计的智能Wiki悬浮窗工具，支持自动识别当前游戏并快速打开对应的Wiki页面，集成了先进的AI RAG（检索增强生成）功能，为游戏玩家提供智能问答服务。

## 🎮 功能特性

- **全局热键激活** - 使用自定义热键组合快速呼出Wiki悬浮窗
- **智能游戏识别** - 自动检测当前活跃的游戏窗口
- **悬浮窗显示** - 在游戏上方显示Wiki内容，不影响游戏体验
- **AI智能问答** - 集成Google Gemini AI和本地向量搜索的智能游戏助手
- **多游戏支持** - 内置Wiki配置和AI知识库
- **混合搜索** - 结合语义向量搜索和传统关键词搜索
- **系统托盘管理** - 后台静默运行，便捷访问

## 🎯 支持的游戏

### 🤖 AI增强游戏（完整知识库支持）
这些游戏具备先进的AI问答功能和完整的知识库：

- **地狱潜兵2 (HELLDIVERS 2)** - 合作射击游戏，包含武器、策略和敌人数据
- **艾尔登法环 (Elden Ring)** - 动作RPG，包含道具、武器、法术和Boss攻略
- **饥荒联机版 (Don't Starve Together)** - 生存多人游戏，包含合成配方和角色指南
- **文明6 (Civilization VI)** - 策略游戏，包含文明、单位和胜利指南

### 📖 Wiki访问游戏
提供基础Wiki悬浮窗支持，便于快速查阅：

- **VALORANT, 反恐精英2** - 战术射击游戏
- **怪物猎人系列** - 动作RPG游戏
- **星露谷物语** - 农场模拟游戏
- **七日杀** - 生存恐怖游戏
- 等等百款游戏

## 🤖 AI功能

### 智能问答系统
- **自然语言处理** - 支持中英文自然语言提问
- **快速向量搜索** - 毫秒级响应的FAISS数据库
- **混合搜索** - 结合语义向量搜索和BM25关键词匹配
- **全面覆盖** - 武器、道具、策略、角色和游戏机制
- **来源引用** - 每个答案都包含相关的资料来源

### AI知识库管理
- **向量库构建器** - 构建FAISS向量索引用于语义搜索
- **BM25索引构建器** - 使用bm25s创建高性能关键词搜索索引
- **多语言支持** - 智能文本处理，支持中文和英文
- **游戏特定优化** - 针对不同游戏类型的定制化处理

### 构建自定义知识库
要为新游戏添加支持或更新现有知识库：

```bash
# 为新游戏构建向量库和BM25索引
python src/game_wiki_tooltip/ai/build_vector_index.py --game 游戏名称

# 仅重建BM25索引（保留现有向量库）
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py 游戏名称

# 详细文档请查看：
# src/game_wiki_tooltip/ai/README.zh-CN.md
```



## 🚀 快速开始

### 系统要求

- Windows 10/11
- Python 3.8+
- 网络连接
- Google Cloud账户（可选，用于RAG功能）
- JINA API密钥（用于向量嵌入）
- bm25s和faiss-cpu包（用于搜索索引）

### 安装方法

1. **克隆项目**
   ```bash
   git clone https://github.com/rimulu030/gamewiki.git
   cd gamewiki
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   pip install bm25s faiss-cpu
   ```

3. **设置环境变量**
   ```bash
   # 设置JINA API密钥用于向量嵌入
   export JINA_API_KEY="your_jina_api_key_here"
   ```

5. **运行程序**
   
   **传统版本（WebView）：**
   ```bash
   python -m src.game_wiki_tooltip
   ```
   
   **Qt版本（推荐）：**
   ```bash
   python src/game_wiki_tooltip/qt_app.py
   ```
   
   **统一窗口版本：**
   ```bash
   python src/game_wiki_tooltip/unified_window.py
   ```

### 首次使用

1. 启动程序后，会弹出热键设置窗口
2. 设置您喜欢的热键组合（默认：Ctrl + X）
3. 设置完成后，程序会在系统托盘显示图标
4. 在游戏中按热键即可呼出Wiki悬浮窗

## ⚙️ 配置说明

### 热键设置

程序支持自定义热键组合：
- 修饰键：Ctrl、Alt、Shift、Win
- 功能键：F1-F12、A-Z等
- Qt版本提供更好的热键管理和配置界面

### 游戏配置

游戏配置文件位于：`src/game_wiki_tooltip/assets/games.json`

支持多语言配置：
- `games_en.json` - 英文游戏配置
- `games_zh.json` - 中文游戏配置
- `games.json` - 主配置文件

每个游戏配置包含：
```json
{
    "游戏名称": {
        "BaseUrl": "Wiki基础URL",
        "NeedsSearch": true/false
    }
}
```

### AI RAG配置

1. **设置Google AI API密钥**
   ```bash
   # 设置环境变量
   export GOOGLE_API_KEY="your-api-key"
   ```

2. **配置RAG系统**
   系统使用统一的RAG配置管理器，配置位于：
   ```
   src/game_wiki_tooltip/ai/rag_config.py
   ```

3. **构建向量索引**
   ```bash
   # 构建FAISS向量索引
   python src/game_wiki_tooltip/ai/build_vector_index.py
   
   # 构建增强BM25索引
   python src/game_wiki_tooltip/ai/enhanced_bm25_indexer.py
   
   # 重建所有增强索引
   python src/game_wiki_tooltip/ai/rebuild_enhanced_indexes.py
   ```

4. **运行质量评估**
   ```bash
   python src/game_wiki_tooltip/ai/run_quality_evaluation.py
   ```

5. **向量数据库诊断**
   ```bash
   python test_diagnose_vector.py
   ```

### 添加新游戏

1. 编辑 `games.json` 文件
2. 添加新游戏配置
3. 重启程序

示例配置：
```json
{
    "新游戏名称": {
        "BaseUrl": "https://wiki.example.com",
        "NeedsSearch": true
    }
}
```

## 🛠️ 项目结构

```
gamewiki/
├── src/game_wiki_tooltip/          # 主程序源码
│   ├── __main__.py                 # 主程序入口
│   ├── config.py                   # 配置管理
│   ├── i18n.py                     # 国际化支持
│   ├── utils.py                    # 工具函数
│   ├── assistant_integration.py    # AI助手集成
│   ├── auto_click.js               # 自动点击脚本
│   │
│   ├── app_v1/                     # 传统WebView版本
│   │   ├── app.py                  # 主应用
│   │   ├── overlay.py              # 悬浮窗管理
│   │   ├── hotkey.py               # 热键管理
│   │   ├── tray_icon.py            # 系统托盘
│   │   ├── searchbar.py            # 搜索栏组件
│   │   └── hotkey_setup.py         # 热键设置界面
│   │
│   ├── # Qt版本实现
│   ├── qt_app.py                   # Qt主应用
│   ├── qt_hotkey_manager.py        # Qt热键管理器
│   ├── qt_settings_window.py       # Qt设置窗口
│   ├── qt_tray_icon.py             # Qt系统托盘
│   ├── unified_window.py           # 统一窗口界面
│   │
│   ├── ai/                         # AI功能模块
│   │   ├── rag_config.py           # RAG配置管理
│   │   ├── rag_engine_factory.py   # RAG引擎工厂
│   │   ├── rag_query.py            # RAG查询处理
│   │   ├── hybrid_retriever.py     # 混合检索器
│   │   ├── enhanced_bm25_indexer.py # 增强BM25索引
│   │   ├── enhanced_query_processor.py # 增强查询处理器
│   │   ├── unified_query_processor.py # 统一查询处理器
│   │   ├── build_vector_index.py   # 向量索引构建
│   │   ├── batch_embedding.py      # 批量嵌入处理
│   │   ├── rebuild_enhanced_indexes.py # 重建增强索引
│   │   ├── rag_quality_evaluator.py # 质量评估器
│   │   ├── run_quality_evaluation.py # 评估运行器
│   │   ├── gemini_summarizer.py    # Gemini摘要器
│   │   ├── query_translator.py     # 查询翻译器
│   │   ├── intent_aware_reranker.py # 意图感知重排序器
│   │   │
│   │   ├── intent/                 # 意图分析模块
│   │   │   └── intent_classifier.py
│   │   │
│   │   ├── trial_proto/            # 试验性原型
│   │   │   ├── adaptive_hybrid_retriever.py
│   │   │   ├── game_aware_query_processor.py
│   │   │   ├── hybrid_search_optimizer.py
│   │   │   └── cleanchunk.py
│   │   │
│   │   ├── vectorstore/            # 向量存储
│   │   │   ├── helldiver2_vectors/
│   │   │   │   ├── index.faiss
│   │   │   │   ├── metadata.json
│   │   │   │   └── enhanced_bm25_index.pkl
│   │   │   ├── eldenring_vectors/
│   │   │   │   ├── index.faiss
│   │   │   │   └── metadata.json
│   │   │   ├── helldiver2_vectors_config.json
│   │   │   └── eldenring_vectors_config.json
│   │   │
│   │   └── evaluate_report/        # 评估报告
│   │       └── helldivers2/
│   │           └── quality_report_*.json/md
│   │
│   └── assets/                     # 资源文件
│       ├── games.json              # 主游戏配置
│       ├── games_en.json           # 英文游戏配置
│       ├── games_zh.json           # 中文游戏配置
│       ├── settings.json           # 默认设置
│       └── app.ico                 # 程序图标
│
├── data/                           # 游戏数据和资源
│   ├── knowledge_chunk/            # 知识库数据
│   │   ├── 7daystodie.json
│   │   ├── civilization6.json
│   │   ├── dst.json
│   │   ├── eldenring.json
│   │   └── helldiver2.json
│   │
│   ├── evaluator/                  # 评估器数据
│   │   ├── helldivers2_enemy_weakpoints.json
│   │   ├── inoutput/
│   │   └── quality_report_*.json/md
│   │
│   ├── sample_inoutput/            # 样本输入输出
│   │   └── helldiver2.json
│   │
│   ├── sync/                       # 同步数据
│   │   └── 根目录/
│   │
│   ├── GameFloaty.pdf              # 游戏文档
│   ├── warbond.srt                 # 战争债券数据
│   ├── warbondmd.md                # 战争债券攻略
│   └── dbprompt.docx               # 数据库提示文档
│
├── tests/                          # 测试文件
├── diagnose_vector.py              # 向量诊断工具
├── requirements.txt                # Python依赖
├── pyproject.toml                  # 项目配置
├── LICENSE                         # 许可证
├── CLAUDE.md                       # Claude AI文档
└── README.md                       # 说明文档
```

## 🔧 技术特性

### 核心技术
- **跨进程热键** - 使用Windows API实现全局热键
- **双UI架构** - WebView和Qt两种UI实现
- **智能窗口管理** - 自动保存和恢复窗口位置大小
- **异步处理** - 使用asyncio处理并发任务
- **配置热更新** - 支持运行时更新游戏配置

### AI技术栈
- **AI集成** - 集成Google Gemini AI和本地向量搜索
- **多语言支持** - 支持中文等多语言文档处理
- **FAISS向量存储** - 高效的相似度搜索引擎
- **BM25文本搜索** - 传统关键词搜索优化
- **混合检索融合** - RRF算法融合多种搜索结果
- **智能意图分析** - 自动识别查询意图类型
- **质量评估系统** - 自动评估RAG系统性能

### 高级功能
- **批量嵌入处理** - 优化大规模文档向量化
- **自适应检索** - 动态调整搜索策略
- **意图感知重排序** - 基于查询意图优化结果排序
- **查询翻译和处理** - 多语言查询处理能力
- **实时质量监控** - 持续监控系统性能

## 📝 使用说明

### 基本操作

1. **启动程序** - 选择合适的版本启动（Qt版本推荐）
2. **设置热键** - 首次运行设置热键组合
3. **游戏中使用** - 在游戏中按热键呼出Wiki
4. **AI问答** - 使用RAG功能进行智能问答
5. **关闭程序** - 右键系统托盘图标选择退出

### 高级功能

- **AI智能问答** - 使用自然语言询问支持游戏的相关问题
- **关键词搜索** - 通过悬浮窗快速进行Wiki搜索
- **窗口调整** - 可自定义悬浮窗大小和位置
- **多窗口支持** - 同时打开多个游戏参考资料

## 🐛 故障排除

### 常见问题

1. **热键不响应**
   - 检查热键是否与其他程序冲突
   - 尝试更换热键组合
   - Qt版本提供更好的热键管理

2. **游戏无法识别**
   - 确认游戏窗口标题包含在配置中
   - 手动添加游戏配置
   - 检查多语言配置文件

3. **Wiki页面无法加载**
   - 检查网络连接
   - 确认Wiki网站可访问

4. **AI功能无法使用**
   - 检查Google AI API密钥设置
   - 确认网络连接正常
   - 验证向量索引文件是否存在
   - 检查知识库数据文件完整性
   - 运行向量诊断工具

5. **搜索结果不准确**
   - 检查知识库数据是否最新
   - 调整RAG配置参数
   - 运行质量评估工具
   - 重新构建向量索引
   - 使用自适应检索优化

6. **性能问题**
   - 运行向量数据库诊断
   - 检查批量嵌入处理设置
   - 优化混合搜索参数
   - 清理和重建索引

### 日志查看

程序运行日志位于：`%APPDATA%/game_wiki_tooltip/`

### 诊断工具

- **向量诊断** - `python diagnose_vector.py`
- **质量评估** - `python src/game_wiki_tooltip/ai/run_quality_evaluation.py`
- **索引重建** - `python src/game_wiki_tooltip/ai/rebuild_enhanced_indexes.py`

## 🔧 AI模块开发

### 构建知识库
AI模块提供了构建和管理游戏知识库的全面工具：

#### 快速命令
```bash
# 构建完整知识库（向量 + BM25）
python src/game_wiki_tooltip/ai/build_vector_index.py --game 游戏名称

# 仅重建BM25索引
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py 游戏名称

# 验证现有索引
python src/game_wiki_tooltip/ai/rebuild_bm25_only.py --verify-only
```

#### 知识库格式
知识库应为 `data/knowledge_chunk/` 目录下的JSON文件，具有以下结构：
```json
[
  {
    "video_info": { "url": "...", "title": "...", "game": "..." },
    "knowledge_chunks": [
      {
        "chunk_id": "unique_id",
        "topic": "主题标题",
        "summary": "详细描述...",
        "keywords": ["关键词1", "关键词2"],
        "type": "Build_Recommendation",
        "build": { "name": "...", "focus": "..." },
        "structured_data": { "enemy_name": "...", "weak_points": [...] }
      }
    ]
  }
]
```

#### 文档
- **英文**: [AI Module README](src/game_wiki_tooltip/ai/README.md)
- **中文**: [AI模块文档](src/game_wiki_tooltip/ai/README.zh-CN.md)

### AI开发先决条件
```bash
# 安装AI依赖
pip install bm25s faiss-cpu

# 设置API密钥
export JINA_API_KEY="your_jina_api_key_here"
```

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 发起Pull Request

### 开发指南

- **代码结构** - 遵循现有的模块化架构
- **AI功能** - 试验性功能请放在 `trial_proto/` 目录
- **测试** - 确保新功能有相应的测试覆盖
- **文档** - 更新相关文档和配置说明

## 📄 许可证

本项目采用MIT许可证 - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

感谢所有为游戏Wiki社区做出贡献的开发者们！

特别感谢：
- Google Gemini AI 提供强大的AI能力
- FAISS 提供高效的向量搜索引擎
- 游戏社区贡献的Wiki内容和数据

---

**注意**：本工具支持Windows系统，推荐使用Qt版本以获得最佳体验。AI功能需要Google AI API密钥。推荐使用Python 3.8+版本以确保最佳兼容性。部分功能可能需要管理员权限运行。
