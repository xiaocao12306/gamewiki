# 热键游戏检测问题修复

## 问题描述

之前的实现存在一个重要问题：在用户按下热键时，程序获取的前台窗口标题是聊天窗口的标题（"GameWiki Assistant"），而不是用户实际在玩的游戏窗口。这导致RAG系统无法正确初始化对应游戏的向量库。

### 问题根因

1. 用户在游戏中按下热键
2. 聊天窗口立即显示并成为前台窗口
3. `get_foreground_title()` 获取到的是聊天窗口标题
4. RAG系统尝试为"GameWiki Assistant"初始化向量库，失败
5. 用户无法获得正确的游戏攻略

## 解决方案

### 核心思路

**在热键触发的第一时间记录游戏窗口标题，然后在整个查询过程中使用这个记录的标题。**

### 修改内容

#### 1. 热键触发时立即记录游戏窗口 (`qt_app.py`)

```python
def _on_hotkey_triggered(self):
    # 在显示聊天窗口前，立即获取当前前台窗口（游戏窗口）
    game_window_title = get_foreground_title()
    logger.info(f"🎮 热键触发时的前台窗口: '{game_window_title}'")
    
    # 将游戏窗口标题传递给assistant controller
    self.assistant_ctrl.set_current_game_window(game_window_title)
    self.assistant_ctrl.expand_to_chat()
```

#### 2. 添加游戏窗口管理 (`unified_window.py`)

```python
class AssistantController:
    def __init__(self, settings_manager=None):
        # ...
        self.current_game_window = None  # 记录当前游戏窗口标题
    
    def set_current_game_window(self, game_window_title: str):
        """设置当前游戏窗口标题"""
        self.current_game_window = game_window_title
        logger.info(f"🎮 记录游戏窗口: '{game_window_title}'")
```

#### 3. 智能RAG引擎初始化 (`assistant_integration.py`)

```python
class IntegratedAssistantController(AssistantController):
    def set_current_game_window(self, game_window_title: str):
        """重写父类方法，设置当前游戏窗口并处理RAG引擎初始化"""
        super().set_current_game_window(game_window_title)
        
        # 检查是否需要初始化或切换RAG引擎
        vector_game_name = map_window_title_to_game_name(game_window_title)
        
        if vector_game_name:
            # 检查是否需要切换游戏
            if not hasattr(self, '_current_vector_game') or self._current_vector_game != vector_game_name:
                logger.info(f"🔄 切换RAG引擎: {current} -> {vector_game_name}")
                self._current_vector_game = vector_game_name
                self._reinitialize_rag_for_game(vector_game_name)
```

#### 4. 移除动态检测逻辑

- 移除了 `handle_query` 中的动态游戏检测
- 修改了 `process_query_async` 和 `generate_guide_async` 接受游戏上下文参数
- 修改了 `QueryWorker` 使用记录的游戏窗口标题

## 修改后的工作流程

1. **热键触发**：
   - 立即记录当前前台窗口（游戏窗口）
   - 检查是否为支持的游戏
   - 如果是支持的游戏，初始化对应的RAG引擎
   - 显示聊天窗口

2. **查询处理**：
   - 使用记录的游戏窗口标题
   - 不再动态获取前台窗口
   - 使用正确的向量库进行攻略查询

## 效果

### 修复前
```
🎮 热键触发时的前台窗口: 'Helldivers 2'
# 聊天窗口显示后...
检测到游戏切换: None -> GameWiki Assistant  ❌
未找到窗口标题 'GameWiki Assistant' 对应的向量库映射  ❌
```

### 修复后
```
🎮 热键触发时的前台窗口: 'Helldivers 2'
🎮 记录游戏窗口: 'Helldivers 2'
🎮 检测到游戏窗口，准备初始化RAG引擎: helldiver2
🔄 切换RAG引擎: None -> helldiver2  ✅
RAG引擎已重新初始化为游戏: helldiver2  ✅
```

## 受益功能

1. **正确的游戏检测** - 不再误识别聊天窗口为游戏
2. **准确的向量库加载** - 能够加载正确游戏的攻略数据
3. **完整的混合搜索** - 向量搜索 + BM25搜索正常工作
4. **智能游戏切换** - 支持在不同游戏间切换时自动重新初始化RAG引擎

现在用户可以：
- ✅ 在任何支持的游戏中按热键
- ✅ 获得该游戏的真实攻略数据  
- ✅ 享受完整的AI助手功能
- ✅ 在多个游戏间无缝切换 