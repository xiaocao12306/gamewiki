# Guidor Assistant 打包指南（MVP 商用版）

本文面向需要交付 **Guidor Assistant** MVP 的发行/运维同学，说明如何在 Windows 环境下生成可分发的 EXE 或安装程序。

---

## 1. 准备工作

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11（建议 64 位） |
| Python | 3.8 ~ 3.11（安装 64 位版本，避免 WOW64 兼容问题） |
| 其他工具 | Git、Visual C++ Build Tools、PowerShell 7+（可选）、Inno Setup（仅制作安装包时需要） |

> 建议在干净的打包机上操作，并预装 WebView2 运行时以便测试。

### 1.1 克隆项目并创建虚拟环境

```powershell
git clone https://xxx/guidor.git
cd guidor
python -m venv venv
.\venv\Scripts\activate
```

### 1.2 安装依赖

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

如需语音识别能力，可执行：

```powershell
python download_vosk_models.py
```

---

## 2. 一键打包脚本（推荐）

项目根目录提供 `build_exe.py`，支持多种产物形态。脚本默认清理旧构建、校验资源、运行 PyInstaller，并复制所需运行时组件。

```powershell
python build_exe.py [--mode onedir|onefile] [--skip-deps] [--create-installer]
```

### 2.1 onedir 模式（默认，推荐）

```powershell
python build_exe.py
```

输出目录：`GuidorAssistant_Portable_onedir/`

- `GuidorAssistant/`：可直接部署的程序目录（含 EXE、依赖文件、数据）
- `Uninstall.exe`：卸载引导程序
- `runtime/MicrosoftEdgeWebView2Setup.exe`：WebView2 运行时安装器
- `README.txt`：用户操作说明

> 适合现场部署或压缩成 zip 发布。无需额外封装即可交付。

### 2.2 onefile 模式（单文件 EXE）

```powershell
python build_exe.py --mode onefile
```

输出目录：`GuidorAssistant_Portable_onefile/GuidorAssistant.exe`

- 单文件模式启动时会解压到临时目录，退出后可清理 `%TEMP%\_MEI*`。
- 启动速度略慢，但便于邮件/网盘分发。

### 2.3 生成安装向导（Inno Setup）

```powershell
python build_exe.py --create-installer
# 或结合单文件：
python build_exe.py --mode onefile --create-installer
```

脚本会在项目根目录生成 `GuidorAssistant_onedir.iss`（或 `GuidorAssistant_onefile.iss`）。后续步骤：

1. 安装 Inno Setup（https://jrsoftware.org/isdl.php）
2. 打开生成的 `.iss` 脚本
3. `Build > Compile`（或 F9）
4. 安装程序输出位于 `installer/GuidorAssistant_Setup.exe`

> `.iss` 脚本已包含默认图标、安装路径、开始菜单快捷方式等，可按需求自定义。

### 2.4 常用参数

| 参数 | 说明 |
| --- | --- |
| `--skip-deps` | 跳过 `pip install` 步骤（适用于离线环境或已安装依赖时） |
| `--mode onedir` | 输出目录结构（默认） |
| `--mode onefile` | 输出单体 EXE |
| `--create-installer` | 附加生成 Inno Setup 脚本 |

---

## 3. 产物验证

1. **功能检查**：在打包机上直接运行 EXE，验证登录、模型调用、WebView、埋点等关键流程。
2. **环境测试**：拷贝到未安装依赖的测试机（建议 Windows 11 新装）运行；若使用 onefile，需确认临时目录权限。
3. **日志审查**：确保打包目录仅包含必要文件，避免泄露调试脚本、缓存、API Key 等敏感信息。
4. **体积优化（可选）**：如需减小体积，可启用 PyInstaller UPX、裁剪未用数据文件，但需自测兼容性。

---

## 4. 发布前检查清单

- [ ] 更新应用版本号与变更日志
- [ ] 确认打包机上的 `.env`、测试配置不会被打入产物
- [ ] 使用 onedir/onefile/安装包分别完成一次冷启动验证
- [ ] （可选）执行 `signtool` 代码签名，降低杀软误报
- [ ] 生成 SHA256 校验值，随发布包一同提供
- [ ] 在目标渠道（内部网盘/私有更新服务器）上传并记录版本信息

---

## 5. 常见问题排查

| 问题 | 处理方式 |
| --- | --- |
| `hybrid retriever module is not available` | 确认执行过 `pip install -r requirements.txt` 且 `check_ai_modules` 步骤通过 |
| 启动报缺少 WebView2 | 运行 `runtime/MicrosoftEdgeWebView2Setup.exe` 或提示用户安装 Edge WebView2 Runtime |
| 打包后杀毒软件报警 | 尽量使用 onedir 模式，必要时进行代码签名或申诉白名单 |
| 语音识别不可用 | 运行 `download_vosk_models.py` 将模型放入 `data/vosk`，重新打包 |
| 打包失败提示缺少资源 | 确认 `src/game_wiki_tooltip/assets` 内图标/配置文件仍在默认位置 |

---

## 6. 进阶定制

- 打包脚本可在 `build_exe.py` 中调整输出目录命名、嵌入版本信息、扩展入门文档等。
- 需要企业 Logo/版权信息，可在 `GuidorAssistant_onedir.iss` 内自定义安装界面。
- 若计划集成自动更新，可在安装包中嵌入更新器或添加任务计划脚本。

如需进一步自动化（CI/CD 构建、自动签名、内部发布系统联动），可基于当前脚本制作 PowerShell/Python Pipeline，欢迎与工程团队讨论需求。***
