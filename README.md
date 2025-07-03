# GameWikiTooltip - 游戏Wiki悬浮窗工具

一个专为游戏玩家设计的智能Wiki悬浮窗工具，支持自动识别当前游戏并快速打开对应的Wiki页面。

## 🎮 功能特性

- **全局热键激活** - 使用自定义热键组合快速呼出Wiki悬浮窗
- **智能游戏识别** - 自动检测当前活跃的游戏窗口
- **多游戏支持** - 内置多种热门游戏的Wiki配置
- **悬浮窗显示** - 在游戏上方显示Wiki内容，不影响游戏体验
- **系统托盘管理** - 后台运行，通过系统托盘图标管理
- **自定义配置** - 支持添加新游戏和自定义Wiki链接
- **关键词映射** - 支持游戏内关键词到Wiki页面的智能映射

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
- **Anno 1800** - 纪元1800
- **Brotato** - 土豆兄弟

## 🚀 快速开始

### 系统要求

- Windows 10/11
- Python 3.8+
- 网络连接

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
        "NeedsSearch": true/false,
        "KeywordMap": {
            "游戏内关键词": "对应的Wiki页面ID"
        }
    }
}
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
        "NeedsSearch": true,
        "KeywordMap": {
            "角色名": "角色页面ID",
            "物品名": "物品页面ID"
        }
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
│   ├── prompt.py                   # 用户交互
│   ├── utils.py                    # 工具函数
│   └── assets/                     # 资源文件
│       ├── games.json              # 游戏配置
│       ├── settings.json           # 默认设置
│       └── app.ico                 # 程序图标
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

## 📝 使用说明

### 基本操作

1. **启动程序** - 双击运行或命令行启动
2. **设置热键** - 首次运行设置热键组合
3. **游戏中使用** - 在游戏中按热键呼出Wiki
4. **关闭程序** - 右键系统托盘图标选择退出

### 高级功能

- **关键词搜索** - 在悬浮窗中输入关键词快速搜索
- **窗口调整** - 可调整悬浮窗大小和位置
- **多窗口支持** - 支持同时打开多个Wiki页面

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

**注意**：本工具仅支持Windows系统，需要管理员权限运行以确保热键功能正常工作。
