# WebView2 Setup Guide

## 概述

WebView2 是一个轻量级的替代方案，用于替代 PyQt6-WebEngine。使用 WebView2 可以：

- ✅ **减少 100+ MB 的打包体积**
- ✅ **完美支持视频播放**（YouTube、Bilibili 等）
- ✅ **更好的性能**（使用系统 Edge 引擎）
- ✅ **自动更新**（随 Windows 更新）

## 安装步骤

### 1. 安装 WebView2 Runtime

大多数 Windows 10/11 系统已经预装了 WebView2 Runtime。如果没有，请下载安装：

🔗 [下载 WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)

### 2. 安装 Python 依赖

```bash
# 安装 pythonnet（用于调用 .NET 组件）
pip install pythonnet
```

### 3. 下载 WebView2 SDK

运行设置脚本自动下载所需的 DLL 文件：

```bash
python src/game_wiki_tooltip/webview2_setup.py
```

这将下载：
- `Microsoft.Web.WebView2.Core.dll`
- `Microsoft.Web.WebView2.WinForms.dll`

## 启用 WebView2

在 `unified_window.py` 中，确保 `USE_WEBVIEW2 = True`：

```python
# Configuration option to use WebView2 instead of WebEngine
USE_WEBVIEW2 = True  # Set to True to use lightweight WebView2
```

## 验证安装

运行应用程序，您应该看到：
```
✅ WebView2创建成功 - 支持完整视频播放
```

## 故障排除

### 问题：WebView2 assemblies not found

**解决方案**：
1. 运行 `python src/game_wiki_tooltip/webview2_setup.py`
2. 确保 `src/game_wiki_tooltip/webview2/lib/` 目录存在并包含 DLL 文件

### 问题：pythonnet not installed

**解决方案**：
```bash
pip install pythonnet
```

### 问题：WebView2 Runtime not installed

**解决方案**：
1. 下载并安装 [WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)
2. 或更新到最新版本的 Microsoft Edge

## 打包说明

使用 PyInstaller 打包时，WebView2 版本会显著减小文件大小：

### 使用 PyQt6-WebEngine
- 打包大小：~200 MB
- 包含完整 Chromium 引擎

### 使用 WebView2
- 打包大小：~50 MB（节省 150 MB）
- 使用系统 Edge 引擎

## 注意事项

1. **仅支持 Windows** - WebView2 是 Windows 专有技术
2. **需要 .NET Framework** - 通常 Windows 已预装
3. **需要 Edge 或 WebView2 Runtime** - 大多数现代 Windows 系统已包含

## 回退到 WebEngine

如果需要回退到 PyQt6-WebEngine，只需：

```python
# 在 unified_window.py 中
USE_WEBVIEW2 = False  # 改为 False
```

应用会自动使用 PyQt6-WebEngine。