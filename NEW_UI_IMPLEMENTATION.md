# 新UI系统实现说明

## 概述

已成功将整个项目从混合GUI框架（tkinter + PyQt6）迁移到纯PyQt6实现，解决了事件循环冲突问题。

## 新增文件

1. **src/game_wiki_tooltip/qt_app.py**
   - 主应用程序入口
   - 管理整个应用生命周期
   - 处理首次运行和设置流程

2. **src/game_wiki_tooltip/qt_tray_icon.py**
   - 基于QSystemTrayIcon的托盘图标实现
   - 支持右键菜单和系统通知

3. **src/game_wiki_tooltip/qt_settings_window.py**
   - 设置窗口，包含两个标签页：
     - 热键配置
     - API密钥配置（Google和Jina）

4. **src/game_wiki_tooltip/qt_hotkey_manager.py**
   - 全局热键管理器
   - 与PyQt6事件系统集成

5. **test_new_ui.py**
   - 测试脚本，可直接运行新UI

## 修改的文件

1. **src/game_wiki_tooltip/config.py**
   - 新增ApiConfig数据类
   - 更新AppSettings和SettingsManager以支持API配置

2. **src/game_wiki_tooltip/__main__.py**
   - 更改为导入qt_app而非app

3. **已有的三个UI文件保持不变**
   - unified_window.py
   - assistant_integration.py  
   - app_with_new_ui.py（作为参考）

## 程序流程

1. **启动流程**：
   ```
   用户运行程序 -> 检查是否首次运行（无API密钥）
   ├─ 是 -> 显示设置窗口（热键+API配置）
   │        └─ 用户保存设置 -> 初始化所有组件
   └─ 否 -> 直接初始化所有组件
   ```

2. **组件初始化**：
   - 创建IntegratedAssistantController（集成RAG）
   - 显示系统托盘图标
   - 注册全局热键
   - 启动Windows消息监听线程
   - 显示圆形悬浮窗

3. **用户交互**：
   - 点击悬浮窗或按热键 -> 展开聊天窗口
   - 输入查询 -> RAG处理 -> 返回结果
   - Wiki查询 -> 在窗口内显示Wiki页面
   - 攻略查询 -> 流式输出结果

4. **设置管理**：
   - 托盘图标右键菜单 -> 设置
   - 可修改热键和API密钥
   - 应用后立即生效

## 运行方式

```bash
# 方式1：通过模块运行
python -m src.game_wiki_tooltip

# 方式2：直接运行测试脚本
python test_new_ui.py
```

## 依赖要求

需要安装PyQt6相关包和python-dotenv：
```bash
pip install PyQt6 PyQt6-WebEngine python-dotenv

# 或者安装所有依赖
pip install -r requirements.txt
```

## 特性

1. **统一的事件循环**：完全基于PyQt6，无事件循环冲突
2. **完整的设置UI**：包含热键和API密钥配置
3. **首次运行引导**：自动显示设置窗口
4. **系统通知**：使用系统原生通知
5. **优雅退出**：正确清理所有资源

## 注意事项

1. 需要Google API密钥才能使用AI功能
2. Jina API密钥为可选，用于高级语义搜索
3. Windows专用，使用了Windows特定的热键API
4. 建议使用Ctrl+字母键作为热键组合 