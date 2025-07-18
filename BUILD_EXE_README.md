# GameWiki Assistant 打包指南

本指南将帮助你将 GameWiki Assistant 项目打包成独立的 Windows exe 文件。

## 🚀 快速开始

### 方法1：使用批处理脚本（推荐）

1. 确保在项目根目录中
2. 双击运行 `build_exe.bat`
3. 等待打包完成

### 方法2：使用Python脚本

```bash
python build_exe.py
```

### 方法3：手动执行命令

```bash
# 安装依赖
pip install -r requirements.txt

# 清理之前的构建
rmdir /s /q build dist 2>nul

# 执行打包
pyinstaller game_wiki_tooltip.spec --clean --noconfirm
```

## 📋 系统要求

- **操作系统**: Windows 10 或更高版本
- **Python**: 3.8 或更高版本
- **内存**: 建议 8GB 或更多（打包过程中会消耗大量内存）
- **磁盘空间**: 至少 5GB 可用空间

## 📦 打包后的文件

成功打包后，你将得到：

```
dist/
└── GameWikiAssistant.exe    # 主程序文件 (约200-400MB)

GameWikiAssistant_Portable/  # 便携版目录
├── GameWikiAssistant.exe
└── README.txt
```

## ⚙️ 高级配置

### 自定义打包选项

如果需要修改打包配置，编辑 `game_wiki_tooltip.spec` 文件：

```python
# 修改exe文件名
name='你的应用名称',

# 修改图标
icon='path/to/your/icon.ico',

# 添加版本信息
version_file='version_info.txt',

# 控制台窗口（调试时可设为True）
console=False,
```

### 添加额外的数据文件

在 spec 文件中的 `datas` 列表中添加：

```python
datas = [
    # 现有的数据文件...
    ('your_data_folder', 'your_data_folder'),
    ('single_file.txt', '.'),
]
```

### 排除不需要的模块

在 `excludes` 列表中添加不需要的模块以减小文件大小：

```python
excludes = [
    'tkinter',  # 如果不使用Tkinter
    'matplotlib',  # 如果不使用matplotlib
    # 其他不需要的模块...
]
```

## 🔧 常见问题解决

### 问题1：ModuleNotFoundError

**症状**: 打包的exe运行时提示找不到某个模块

**解决方案**: 在 spec 文件的 `hiddenimports` 中添加缺失的模块：

```python
hiddenimports = [
    # 现有模块...
    'missing_module_name',
]
```

### 问题2：无法找到资源文件

**症状**: 程序运行时找不到图标、配置文件等

**解决方案**: 
1. 检查 `datas` 配置是否正确
2. 确保资源文件路径在代码中使用相对路径
3. 使用 `pkg_resources` 或 `importlib.resources` 访问资源

### 问题3：exe文件过大

**解决方案**:
1. 在 `excludes` 中排除不需要的模块
2. 使用 `upx=True` 启用压缩（可能会增加启动时间）
3. 考虑使用目录模式而不是单文件模式

### 问题4：杀毒软件报警

**原因**: PyInstaller 打包的exe文件有时会被误报为病毒

**解决方案**:
1. 在杀毒软件中添加白名单
2. 使用代码签名证书对exe文件进行签名
3. 向杀毒软件厂商报告误报

### 问题5：启动缓慢

**原因**: 单文件模式需要解压到临时目录

**解决方案**:
1. 改用目录模式打包（修改spec文件中的 `onefile=False`）
2. 优化导入的模块数量
3. 使用启动画面改善用户体验

## 🛠️ 调试技巧

### 启用控制台输出

临时修改 spec 文件：

```python
console=True,  # 显示控制台窗口以查看错误信息
```

### 详细日志

运行时使用详细模式：

```bash
pyinstaller game_wiki_tooltip.spec --clean --noconfirm --log-level DEBUG
```

### 测试打包的exe

```bash
# 在dist目录中直接运行
cd dist
GameWikiAssistant.exe

# 或者从其他位置运行以测试路径问题
C:\path\to\dist\GameWikiAssistant.exe
```

## 📈 性能优化

### 减少启动时间

1. **延迟导入**: 将不必要的导入移到需要时才导入
2. **减少依赖**: 移除未使用的依赖包
3. **使用目录模式**: 避免单文件模式的解压开销

### 减少文件大小

1. **排除测试模块**: 在 `excludes` 中添加测试相关模块
2. **优化资源文件**: 压缩图片和其他资源文件
3. **移除调试信息**: 确保 `debug=False`

## 🔍 故障排除清单

在遇到问题时，请按以下顺序检查：

- [ ] Python版本是否为3.8+
- [ ] 所有依赖包是否正确安装
- [ ] 项目路径中是否包含中文或特殊字符
- [ ] 资源文件是否存在且路径正确
- [ ] 杀毒软件是否阻止了打包过程
- [ ] 磁盘空间是否充足
- [ ] 是否有足够的内存进行打包

## 📞 获取帮助

如果遇到问题，可以：

1. 查看PyInstaller官方文档
2. 在项目Issues中搜索相似问题
3. 提供完整的错误日志和系统信息

## 🎯 最佳实践

1. **定期清理**: 每次打包前清理build和dist目录
2. **版本控制**: 不要将build和dist目录提交到版本控制
3. **测试环境**: 在干净的环境中测试打包的exe
4. **文档更新**: 保持打包配置和文档的同步

---

**注意**: 第一次打包可能需要较长时间（10-30分钟），因为需要下载和处理大量的依赖包。后续打包会快一些。 