# GameWikiTooltip - 游戏Wiki悬浮窗工具

一个专为游戏玩家设计的智能Wiki悬浮窗工具，支持自动识别当前游戏并快速打开对应的Wiki页面，集成了先进的AI RAG（检索增强生成）功能，为游戏玩家提供智能问答服务。

## 🎮 功能特性

- **全局热键激活** - 使用自定义热键组合快速呼出Wiki悬浮窗
- **智能游戏识别** - 自动检测当前活跃的游戏窗口
- **多游戏支持** - 内置12款热门游戏的Wiki配置
- **悬浮窗显示** - 在游戏上方显示Wiki内容，不影响游戏体验
- **系统托盘管理** - 后台运行，通过系统托盘图标管理
- **自定义配置** - 支持添加新游戏和自定义Wiki链接
- **关键词映射** - 支持游戏内关键词到Wiki页面的智能映射
- **双UI架构** - 提供传统WebView版本和现代Qt版本
- **统一窗口管理** - 集成搜索、设置和显示功能的统一界面
- **AI RAG功能** - 集成Google Gemini AI和本地向量搜索引擎
- **本地向量搜索** - 支持本地FAISS向量数据库进行文档检索
- **多游戏数据库** - 内置多款游戏的知识库和攻略数据
- **混合搜索** - 结合向量搜索和BM25算法的混合检索
- **智能重排序** - 基于意图分析的搜索结果重排序
- **质量评估** - 内置RAG系统质量评估和优化框架
- **自适应检索** - 智能调整搜索策略和参数优化

## 🎯 支持的游戏

目前支持以下游戏的Wiki快速访问：

- **VALORANT** - 英雄联盟瓦罗兰特
- **Counter-Strike 2** - 反恐精英2
- **三角洲行动** - Delta Force
- **MONSTER HUNTER: WORLD** - 怪物猎人世界
- **Monster Hunter Wilds** - 怪物猎人荒野
- **Stardew Valley** - 星露谷物语
- **Don't Starve Together** - 饥荒联机版
- **Don't Starve** - 饥荒
- **Elden Ring** - 艾尔登法环
- **HELLDIVERS 2** - 地狱潜兵2
- **7 Days to Die** - 七日杀
- **Civilization VI** - 文明6

## 📊 游戏知识库

项目内置了多个游戏的详细知识库数据：

### 📚 知识库数据文件
- **civilization6.json** - 文明6游戏数据
- **dst.json** - 饥荒联机版数据
- **eldenring.json** - 艾尔登法环数据
- **helldiver2.json** - 地狱潜兵2数据

### 🎯 特色功能
- **智能问答** - 基于游戏知识库的自然语言问答
- **快速检索** - 毫秒级搜索响应
- **多维度搜索** - 支持武器、装备、技能、攻略等多种内容
- **相关性排序** - 智能排序最相关的搜索结果

### 📈 评估和诊断
- **质量报告** - 自动生成详细的RAG质量评估报告
- **向量诊断** - 向量数据库健康检查和优化建议
- **性能监控** - 实时监控搜索性能和准确率

## 🤖 AI功能

### RAG（检索增强生成）
- 基于Google Gemini 2.0 Flash模型
- 支持多种文档格式（JSON、PDF、Markdown等）
- 提供准确的引用和来源链接
- 统一的RAG配置管理系统
- 批量嵌入处理优化

### 本地向量搜索
- 使用FAISS向量数据库
- 支持中文多语言嵌入模型
- 本地化文档检索，保护隐私
- 快速相似度搜索
- 增强的索引构建流程

### 混合搜索系统
- 结合向量搜索和BM25算法
- 自适应融合策略（RRF - Reciprocal Rank Fusion）
- 智能权重调整
- 多维度相关性评估
- 自适应混合检索优化

### 智能查询处理
- 游戏感知查询预处理
- 意图分析和分类
- 查询重写和优化
- 多语言支持
- 统一查询处理管道

### 质量评估框架
- 自动质量评估系统
- 详细的评估报告生成
- 支持多种评估指标
- 持续优化建议
- 实时质量监控

### 试验性功能
- **自适应混合检索** - 动态调整检索策略
- **游戏感知查询处理** - 针对游戏内容的专门处理
- **混合搜索优化器** - 智能优化搜索参数
- **数据清洗工具** - 自动清理和优化知识库数据

## 🚀 快速开始

### 系统要求

- Windows 10/11
- Python 3.8+
- 网络连接
- Google Cloud账户（可选，用于RAG功能）

### 安装方法

1. **克隆项目**
   ```bash
   git clone https://github.com/your-username/gamewiki.git
   cd gamewiki
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **运行程序**
   
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

- **关键词搜索** - 在悬浮窗中输入关键词快速搜索
- **窗口调整** - 可调整悬浮窗大小和位置
- **多窗口支持** - 支持同时打开多个Wiki页面
- **AI智能问答** - 基于多游戏知识库的智能问答系统
- **本地向量搜索** - 使用本地数据库进行快速检索
- **混合搜索** - 结合语义搜索和关键词搜索
- **质量评估** - 实时评估搜索结果质量
- **多游戏支持** - 针对不同游戏的专门知识库
- **统一界面** - 集成搜索、设置和管理功能

### 版本选择指南

- **Qt版本** - 推荐使用，提供更好的用户体验和稳定性
- **WebView版本** - 传统版本，适合轻量化需求
- **统一窗口版本** - 集成所有功能的单一界面

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
