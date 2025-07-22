# WebView2 打包指南

## 概述

使用WebView2替代PyQt6-WebEngine后，打包流程有了重要变化。本指南详细说明如何正确打包应用程序以及如何处理Windows 10/11的兼容性问题。

## ✅ 优势对比

### 使用 PyQt6-WebEngine (旧方案)
- 打包大小：~200 MB
- 包含完整 Chromium 引擎
- 自包含，无需额外依赖

### 使用 WebView2 (新方案)  
- 打包大小：~50 MB（节省 150 MB！）
- 使用系统 Edge 引擎
- 更好的视频播放支持
- 需要 WebView2 Runtime

## 📋 准备工作

### 1. 确保WebView2组件已正确设置

```bash
# 1. 安装pythonnet依赖
pip install pythonnet

# 2. 下载WebView2 SDK文件
python src/game_wiki_tooltip/webview2_setup.py

# 3. 验证文件存在
# 确保以下文件存在于 src/game_wiki_tooltip/webview2/lib/ 目录：
# - Microsoft.Web.WebView2.Core.dll
# - Microsoft.Web.WebView2.WinForms.dll  
# - WebView2Loader.dll
```

### 2. 启用WebView2模式

在 `unified_window.py` 中确保：
```python
USE_WEBVIEW2 = True  # 设置为True使用WebView2
```

## 🛠️ 打包步骤

### 使用更新后的build_exe.py

```bash
python build_exe.py
```

新的打包流程包括以下步骤：
1. ✅ 安装依赖
2. ✅ 检查WebView2要求
3. ✅ 更新构建配置
4. ✅ 清理构建
5. ✅ 检查资源
6. ✅ 构建exe
7. ✅ 创建便携版
8. ✅ 创建WebView2安装包

### 打包后文件结构

```
GameWikiAssistant_Portable/
├── GameWikiAssistant.exe          # 主程序（约50MB）
├── webview2/
│   └── lib/                       # WebView2 SDK文件
│       ├── Microsoft.Web.WebView2.Core.dll
│       ├── Microsoft.Web.WebView2.WinForms.dll
│       └── WebView2Loader.dll
├── runtime/                       # WebView2 Runtime安装包
│   ├── MicrosoftEdgeWebView2Setup.exe
│   └── install_webview2.bat
└── README.txt                     # 使用说明
```

## 🖥️ Windows 10/11 兼容性处理

### Windows 11
- ✅ **预装WebView2 Runtime** - 无需额外操作
- ✅ 应用可直接运行

### Windows 10
- ❌ **大多数情况下未预装WebView2 Runtime**
- ⚠️ 需要用户安装 WebView2 Runtime

### 自动检测和安装方案

#### 方案1：使用提供的安装脚本
用户可以运行 `runtime/install_webview2.bat`：
- 自动检测是否已安装
- 如未安装，静默安装WebView2 Runtime
- 安装大小约100MB，一次性操作

#### 方案2：应用内检测（推荐）
在应用启动时检测并提示用户：

```python
def check_webview2_runtime():
    """检查WebView2 Runtime是否已安装"""
    try:
        import winreg
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        version = winreg.QueryValueEx(key, "pv")[0]
        winreg.CloseKey(key)
        return True, version
    except:
        return False, None

def prompt_webview2_installation():
    """提示用户安装WebView2 Runtime"""
    from PyQt6.QtWidgets import QMessageBox
    from PyQt6.QtCore import Qt
    
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Information)
    msg.setWindowTitle("需要安装WebView2 Runtime")
    msg.setText("""
应用需要Microsoft Edge WebView2 Runtime才能正常运行。

选择安装方式：
• 自动安装：运行 runtime/install_webview2.bat
• 手动下载：访问 https://go.microsoft.com/fwlink/p/?LinkId=2124703

安装完成后重新启动应用即可正常使用。
    """)
    
    msg.addButton("打开安装目录", QMessageBox.ButtonRole.ActionRole)
    msg.addButton("稍后安装", QMessageBox.ButtonRole.RejectRole)
    
    return msg.exec()
```

## 📦 分发策略

### 策略1：完整包（推荐）
- 包含WebView2 Runtime Bootstrapper
- 用户体验最佳
- 总大小：~55 MB

### 策略2：精简包  
- 仅包含应用程序
- 需要用户手动安装WebView2 Runtime
- 总大小：~50 MB

### 策略3：分层分发
```
GameWikiAssistant_Win11.zip    # 仅适用于Win11，最小包
GameWikiAssistant_Win10.zip    # 包含Runtime安装器，适用于Win10
GameWikiAssistant_Full.zip     # 完整包，适用于所有系统
```

## 🔧 故障排除

### 常见问题1：打包失败
**错误：** `ModuleNotFoundError: No module named 'pythonnet'`
**解决：** `pip install pythonnet`

### 常见问题2：WebView2 SDK文件缺失
**错误：** `缺少WebView2 SDK文件`
**解决：** `python src/game_wiki_tooltip/webview2_setup.py`

### 常见问题3：运行时找不到WebView2
**错误：** 应用启动白屏或错误
**解决：** 
1. 检查WebView2 Runtime是否安装
2. 运行 `runtime/install_webview2.bat`
3. 或手动下载安装WebView2 Runtime

### 常见问题4：Windows 7兼容性
**注意：** WebView2不支持Windows 7
**建议：** 为Windows 7用户保留PyQt6-WebEngine版本

## 📋 发布检查清单

- [ ] WebView2模式已启用 (`USE_WEBVIEW2 = True`)
- [ ] pythonnet已安装
- [ ] WebView2 SDK文件已下载
- [ ] 打包成功，exe文件约50MB
- [ ] 便携版目录包含runtime文件夹
- [ ] 在Windows 10和11上测试运行
- [ ] 准备用户说明文档

## 📚 相关资源

- [Microsoft WebView2官方文档](https://docs.microsoft.com/microsoft-edge/webview2/)
- [WebView2 Runtime下载](https://go.microsoft.com/fwlink/p/?LinkId=2124703)
- [项目WebView2设置指南](WEBVIEW2_SETUP.md)

---

**总结：** WebView2显著减少了打包体积，提升了性能，但需要处理Runtime依赖。对于Windows 10用户，建议提供便捷的安装方案，确保良好的用户体验。 