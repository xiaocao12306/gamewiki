# GameWikiTooltip - 游戏Wiki悬浮窗工具

一个专为游戏玩家设计的智能Wiki悬浮窗工具，支持自动识别当前游戏并快速打开对应的Wiki页面，为部分游戏集成了AI RAG（检索增强生成）功能，为游戏玩家提供智能问答服务。

## 功能特性

- **全局热键激活** - 使用自定义热键组合快速呼出对话框
- **智能游戏识别** - 自动检测当前活跃的游戏窗口
- **悬浮窗显示** - 在游戏上方显示Wiki内容
- **AI智能问答** - 集成Google Gemini AI和本地向量搜索的智能游戏助手
- **多游戏支持** - 内置Wiki配置和AI知识库

## 支持的游戏

###  AI增强游戏（完整知识库支持）
这些游戏具备先进的AI问答功能和完整的知识库：

- **地狱潜兵2 (HELLDIVERS 2)**
- **艾尔登法环 (Elden Ring)**
- **饥荒联机版 (Don't Starve Together)**
- **文明6 (Civilization VI)** 

###  Wiki访问游戏
提供基础Wiki悬浮窗支持，便于快速查阅：

- **怪物猎人系列** 
- **星露谷物语** 
- **无人深空** 
- 等等百款游戏

##  AI功能

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

##  快速开始

### 系统要求

- Windows 10/11
- Python 3.8+
- 网络连接
- Google Cloud账户（可选，用于RAG功能）

### 安装方法

1. **克隆项目**
   ```bash
   git clone https://github.com/rimulu030/gamewiki.git
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

5. **运行程序**

   ```bash
   python -m src.game_wiki_tooltip
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
- 功能键：A-Z

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

3. **构建构建自定义知识库/向量索引**

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

   ```bash
   # 构建FAISS向量索引
   python src/game_wiki_tooltip/ai/build_vector_index.py --game 游戏名称
   ```

### 添加新游戏wiki

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
├── src/
│   └── game_wiki_tooltip/       # 主应用程序模块
│       ├── ai/                  # AI和RAG相关功能
│       │   ├── vectorstore/     # FAISS向量索引存储
│       │   ├── build_vector_index.py  # 向量索引构建器
│       │   ├── hybrid_retriever.py   # 混合检索系统
│       │   ├── intent_aware_reranker.py # 意图感知重排序器
│       │   ├── unified_query_processor.py # 统一查询处理器
│       │   └── rag_query.py          # RAG查询接口
│       ├── assets/              # 静态资源文件
│       │   ├── games.json       # 游戏配置
│       │   ├── games_en.json    # 英文游戏配置
│       │   ├── games_zh.json    # 中文游戏配置
│       │   ├── html/            # 游戏任务流程HTML
│       │   └── icons/           # 图标资源
│       ├── window_component/    # 窗口组件
│       │   ├── unified_window.py     # 统一窗口系统
│       │   ├── wiki_view.py          # Wiki视图组件
│       │   └── window_controller.py  # 窗口控制器
│       ├── qt_app.py            # Qt应用主入口
│       ├── qt_hotkey_manager.py # 全局热键管理
│       ├── qt_settings_window.py # 设置窗口
│       ├── qt_tray_icon.py      # 系统托盘图标
│       ├── assistant_integration.py  # AI助手集成
│       ├── config.py            # 配置管理
│       ├── history_manager.py   # 历史记录管理
│       ├── i18n.py             # 国际化支持
│       └── webview_widget.py    # WebView组件
├── data/
│   ├── knowledge_chunk/         # 游戏知识库JSON文件
│   │   ├── helldiver2.json     # 地狱潜兵2知识库
│   │   ├── eldenring.json      # 艾尔登法环知识库
│   │   ├── dst.json            # 饥荒联机版知识库
│   │   └── civilization6.json  # 文明6知识库
│   └── LLM_prompt/             # LLM提示词模板
├── requirements.txt             # Python依赖
└── README.zh-CN.md             # 中文说明文档
```

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


#### 文档
- **英文**: [AI Module README](src/game_wiki_tooltip/ai/README.md)
- **中文**: [AI模块文档](src/game_wiki_tooltip/ai/README.zh-CN.md)

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 发起Pull Request

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
