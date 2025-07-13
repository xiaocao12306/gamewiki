# API密钥管理机制说明

## 概述

该项目有两套API密钥管理机制，新的PyQt6 UI系统与原有系统完全兼容。

## API密钥存储位置

### 新UI系统（推荐）
- **存储位置**: `%APPDATA%/GameWikiTooltip/settings.json`
- **配置方式**: 通过设置窗口的"API配置"标签页
- **存储格式**:
```json
{
    "api": {
        "google_api_key": "your_google_api_key_here",
        "jina_api_key": "your_jina_api_key_here"
    },
    "hotkey": {
        "modifiers": ["Ctrl"],
        "key": "X"
    }
}
```

### 原有系统（仍然支持）
- **存储位置**: 环境变量或.env文件
- **配置方式**: 
  - 设置环境变量
  - 在项目根目录创建`.env`文件
- **环境变量名**:
  - `GOOGLE_API_KEY` 或 `GEMINI_API_KEY` (Google/Gemini API)
  - `JINA_API_KEY` (Jina API)
  - `OPENAI_API_KEY` (OpenAI API)
- **.env文件示例**:
```bash
# GameWiki Assistant 环境变量配置
# 在项目根目录创建 .env 文件并填入你的API密钥

# Google/Gemini API Key (必需)
# 获取地址: https://makersuite.google.com/app/apikey
GOOGLE_API_KEY=your_google_api_key_here

# Jina API Key (可选，用于高级语义搜索)
# 获取地址: https://jina.ai/
JINA_API_KEY=your_jina_api_key_here

# OpenAI API Key (可选，如果使用OpenAI模型)
# OPENAI_API_KEY=your_openai_api_key_here
```

## API密钥调用机制

### 优先级顺序
1. **settings.json中的API密钥** (通过设置窗口配置)
2. **环境变量** (包括.env文件中的变量)
3. **程序自动检测**: 如果环境变量中有API密钥，程序会自动使用，不显示设置窗口

### 代码流程

#### 1. 新UI系统的流程
```python
# 在 assistant_integration.py 中
settings = self.settings_manager.get()
api_settings = settings.get('api', {})
google_api_key = api_settings.get('google_api_key', '')

# 创建LLMConfig，明确传入API密钥
llm_config = LLMConfig(
    api_key=google_api_key,  # 这里明确传入从settings获取的密钥
    model='gemini-2.5-flash-lite-preview-06-17'
)

# 传递给AI组件
self.query_processor = GameAwareQueryProcessor(llm_config=llm_config)
```

#### 2. AI组件的获取流程
```python
# 在各种AI模块中（如 game_aware_query_processor.py）
class GameAwareQueryProcessor:
    def _initialize_gemini_client(self):
        api_key = self.llm_config.get_api_key()  # 调用LLMConfig的方法
```

#### 3. LLMConfig的get_api_key()方法
```python
def get_api_key(self) -> Optional[str]:
    """获取API密钥，优先从环境变量获取"""
    if self.api_key:  # 如果直接传入了API密钥，优先使用
        return self.api_key
    
    # 否则从环境变量获取
    if "gemini" in self.model.lower():
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    elif "gpt" in self.model.lower():
        return os.getenv("OPENAI_API_KEY")
    
    return None
```

## 兼容性设计

### 新UI系统如何兼容原有系统
1. **读取settings.json中的API密钥**
2. **创建LLMConfig时明确传入API密钥**
3. **AI组件仍然使用标准的LLMConfig.get_api_key()方法**
4. **如果settings中没有配置，仍会回退到环境变量**

### 原有系统如何继续工作
- 直接从环境变量读取，无需修改
- 所有现有的AI模块继续正常工作
- 不需要任何代码更改

## 实际使用示例

### 使用新UI系统
1. 运行程序：`python test_new_ui.py`
2. 首次运行会显示设置窗口
3. 在"API配置"标签页输入Google API Key
4. 点击"保存并应用"
5. API密钥保存到`%APPDATA%/GameWikiTooltip/settings.json`

### 使用原有系统（环境变量或.env文件）

#### 方式1：环境变量
```bash
# Windows
set GOOGLE_API_KEY=your_api_key_here
set JINA_API_KEY=your_jina_api_key_here

# Linux/Mac
export GOOGLE_API_KEY=your_api_key_here
export JINA_API_KEY=your_jina_api_key_here

# 运行程序（会自动检测环境变量，不显示设置窗口）
python test_new_ui.py
```

#### 方式2：.env文件
```bash
# 在项目根目录创建 .env 文件
echo "GOOGLE_API_KEY=your_api_key_here" > .env
echo "JINA_API_KEY=your_jina_api_key_here" >> .env

# 运行程序（会自动加载.env文件，不显示设置窗口）
python test_new_ui.py
```

### 同时使用两种方式
- 如果两种方式都配置了，**新UI系统的settings.json优先**
- 因为新系统会明确传入API密钥给LLMConfig
- 环境变量作为备用方案

## 文件位置说明

### 配置文件存储
- **Windows**: `C:\Users\{用户名}\AppData\Roaming\GameWikiTooltip\settings.json`
- **路径变量**: `APPDATA_DIR / "settings.json"`
- **代码位置**: `src/game_wiki_tooltip/qt_app.py` 中的 `SETTINGS_PATH`

### 相关代码文件
- **设置管理**: `src/game_wiki_tooltip/config.py` (SettingsManager, ApiConfig)
- **UI设置窗口**: `src/game_wiki_tooltip/qt_settings_window.py`
- **RAG集成**: `src/game_wiki_tooltip/assistant_integration.py`
- **AI组件**: `src/game_wiki_tooltip/ai/` 目录下的各个模块

## 故障排除

### 常见问题
1. **"Google API key not configured"**
   - 检查settings.json中是否有api.google_api_key
   - 检查环境变量GOOGLE_API_KEY或GEMINI_API_KEY

2. **"未找到Gemini API密钥"**
   - 确认API密钥有效性
   - 检查网络连接

3. **设置窗口无法保存**
   - 确认有写入权限到AppData目录
   - 检查settings.json文件格式

### 调试方法
```python
# 检查配置是否正确加载
from src.game_wiki_tooltip.config import SettingsManager
from src.game_wiki_tooltip.utils import APPDATA_DIR

settings_mgr = SettingsManager(APPDATA_DIR / "settings.json")
settings = settings_mgr.get()
print("API配置:", settings.get('api', {}))
```

## 总结

新的API密钥管理机制提供了：
- **自动.env文件加载**：程序启动时自动加载项目根目录的.env文件
- **智能检测**：如果环境变量中有API密钥，程序自动使用，不显示设置窗口
- **用户友好的配置界面**：支持图形界面配置API密钥
- **安全的本地存储**：API密钥保存在用户AppData目录
- **完全向后兼容**：现有的环境变量配置继续有效
- **灵活的配置方式**：支持环境变量、.env文件、图形界面三种配置方式

### 推荐使用方式
1. **开发者**：使用.env文件，方便版本控制和团队共享
2. **普通用户**：使用图形界面设置，简单直观
3. **服务器部署**：使用环境变量，符合12-factor应用原则

用户可以选择任一种方式配置API密钥，系统会自动处理优先级和回退机制。 