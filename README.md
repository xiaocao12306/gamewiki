# GameWikiTooltip - 游戏Wiki悬浮窗工具

一个专为游戏玩家设计的智能Wiki悬浮窗工具，支持自动识别当前游戏并快速打开对应的Wiki页面，集成了AI RAG（检索增强生成）功能，为游戏玩家提供智能问答服务。

## 🎮 功能特性

- **全局热键激活** - 使用自定义热键组合快速呼出Wiki悬浮窗
- **智能游戏识别** - 自动检测当前活跃的游戏窗口
- **多游戏支持** - 内置多种热门游戏的Wiki配置
- **悬浮窗显示** - 在游戏上方显示Wiki内容，不影响游戏体验
- **系统托盘管理** - 后台运行，通过系统托盘图标管理
- **自定义配置** - 支持添加新游戏和自定义Wiki链接
- **关键词映射** - 支持游戏内关键词到Wiki页面的智能映射
- **AI RAG功能** - 集成Google Vertex AI RAG引擎，提供智能问答服务
- **本地向量搜索** - 支持本地FAISS向量数据库进行文档检索
- **地狱潜兵2数据** - 内置地狱潜兵2战争债券推荐和游戏攻略数据

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

## 🤖 AI功能

### RAG（检索增强生成）
- 基于Google Vertex AI RAG引擎
- 支持文档上传和智能问答
- 提供准确的引用和来源链接
- 支持多种文档格式（PDF等）

### 本地向量搜索
- 使用FAISS向量数据库
- 支持中文多语言嵌入模型
- 本地化文档检索，保护隐私
- 快速相似度搜索

### 地狱潜兵2智能助手
- 战争债券推荐系统
- 武器和装备分析
- 战术建议和攻略
- 基于游戏数据的智能问答

## 🚀 快速开始

### 系统要求

- Windows 10/11
- Python 3.8+
- 网络连接
- Google Cloud账户（可选，用于RAG功能）

### 安装方法

1. **克隆项目**
   ```bash
   git clone https://github.com/your-username/gamewikioverlay_ai_v1.2.git
   cd gamewikioverlay_ai_v1.2
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **运行程序**
   ```bash
   python -m game_wiki_tooltip
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

### 游戏配置

游戏配置文件位于：`%APPDATA%/game_wiki_tooltip/games.json`

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

1. **设置Google Cloud环境**
   ```bash
   gcloud auth application-default login
   ```

2. **配置环境变量**
   创建 `.env` 文件并设置：
   ```
   GOOGLE_CLOUD_PROJECT=your-project-id
   GOOGLE_CLOUD_LOCATION=your-location
   RAG_CORPUS=projects/123/locations/us-central1/ragCorpora/456
   ```

3. **上传文档到RAG引擎**
   ```bash
   python src/game_wiki_tooltip/ai/RAG/rag/shared_libraries/prepare_corpus_and_data.py
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
gamewikioverlay_ai_v1.2/
├── src/game_wiki_tooltip/          # 主程序源码
│   ├── app.py                      # 主程序入口
│   ├── config.py                   # 配置管理
│   ├── overlay.py                  # 悬浮窗管理
│   ├── hotkey.py                   # 热键管理
│   ├── tray_icon.py                # 系统托盘
│   ├── searchbar.py                # 搜索栏组件
│   ├── utils.py                    # 工具函数
│   ├── ai/                         # AI功能模块
│   │   ├── RAG/                    # RAG引擎集成
│   │   │   ├── rag/                # RAG核心功能
│   │   │   ├── deployment/         # 部署脚本
│   │   │   └── eval/               # 评估框架
│   │   ├── helljump2_faiss/        # 地狱潜兵2向量数据库
│   │   └── cleanchunk.py           # 文档清理工具
│   └── assets/                     # 资源文件
│       ├── games.json              # 游戏配置
│       ├── settings.json           # 默认设置
│       └── app.ico                 # 程序图标
├── data/                           # 游戏数据
│   ├── warbond.srt                 # 战争债券数据
│   └── warbondmd.md                # 战争债券攻略
├── requirements.txt                # Python依赖
├── pyproject.toml                  # 项目配置
└── README.md                       # 说明文档
```

## 🔧 技术特性

- **跨进程热键** - 使用Windows API实现全局热键
- **WebView渲染** - 基于pywebview显示Wiki内容
- **智能窗口管理** - 自动保存和恢复窗口位置大小
- **异步处理** - 使用asyncio处理并发任务
- **配置热更新** - 支持运行时更新游戏配置
- **AI集成** - 集成Google Vertex AI和本地向量搜索
- **多语言支持** - 支持中文等多语言文档处理

## 📝 使用说明

### 基本操作

1. **启动程序** - 双击运行或命令行启动
2. **设置热键** - 首次运行设置热键组合
3. **游戏中使用** - 在游戏中按热键呼出Wiki
4. **AI问答** - 使用RAG功能进行智能问答
5. **关闭程序** - 右键系统托盘图标选择退出

### 高级功能

- **关键词搜索** - 在悬浮窗中输入关键词快速搜索
- **窗口调整** - 可调整悬浮窗大小和位置
- **多窗口支持** - 支持同时打开多个Wiki页面
- **AI文档检索** - 上传文档并使用AI进行智能问答
- **本地向量搜索** - 使用本地数据库进行快速检索

## 🐛 故障排除

### 常见问题

1. **热键不响应**
   - 检查热键是否与其他程序冲突
   - 尝试更换热键组合

2. **游戏无法识别**
   - 确认游戏窗口标题包含在配置中
   - 手动添加游戏配置

3. **Wiki页面无法加载**
   - 检查网络连接
   - 确认Wiki网站可访问

4. **AI功能无法使用**
   - 检查Google Cloud配置
   - 确认环境变量设置正确
   - 验证RAG引擎连接

### 日志查看

程序运行日志位于：`%APPDATA%/game_wiki_tooltip/`

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

---

**注意**：本工具仅支持Windows系统，需要管理员权限运行以确保热键功能正常工作。AI功能需要Google Cloud账户和相应的API权限。
