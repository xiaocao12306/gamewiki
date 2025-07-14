# 热键注册问题修复方案

## 问题分析

用户遇到的问题：新版本的热键冲突处理逻辑导致所有热键注册都失败，而旧版本的热键注册逻辑能正常工作。

通过对比旧版本代码（`src/game_wiki_tooltip/hotkey.py`），发现关键差异在于**错误处理策略**：

### 旧版本行为
```python
if error == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
    logger.warning("热键已被注册，将直接使用")
    self._registered = True
    return  # 直接返回成功！
```

### 新版本行为
- 将1409错误视为冲突，尝试其他热键组合
- 结果导致所有热键都失败

## 解决方案

### 1. 增加 `legacy_mode` 参数

在 `QtHotkeyManager` 中添加了 `legacy_mode` 参数：
```python
def __init__(self, settings_mgr: SettingsManager, parent=None, 
             conflict_strategy: str = HotkeyConflictStrategy.FORCE_REGISTER,
             legacy_mode: bool = True):  # 默认启用旧版兼容模式
```

### 2. 实现旧版兼容注册逻辑

添加了 `_try_register_hotkey_legacy()` 方法，完全模拟旧版本的行为：
- 当遇到1409错误时，假设热键已经可用，直接返回成功
- 保持对其他错误的正常处理

### 3. 双模式支持

在 `register()` 方法中根据 `legacy_mode` 选择注册策略：
- `legacy_mode=True`: 使用旧版兼容逻辑
- `legacy_mode=False`: 使用新版冲突处理逻辑

### 4. 默认配置

- 主应用程序 (`qt_app.py`) 默认启用 `legacy_mode=True`
- 所有测试脚本也默认使用旧版兼容模式

## 测试方法

### 1. 专用旧版测试脚本
```bash
python test_legacy_hotkey.py
```

### 2. 更新后的简化测试
```bash
python test_hotkey_simple.py
```

### 3. 运行主程序
```bash
python -m src.game_wiki_tooltip
```

## 预期结果

启用 `legacy_mode` 后：
- ✅ 遇到"热键已注册"错误时，程序假设热键可用并继续运行
- ✅ 热键功能应该能正常工作
- ✅ 保持了向后兼容性
- ✅ 程序会显示"旧版兼容模式"状态

## 新功能

### 1. 运行时控制
```python
hotkey_mgr.set_legacy_mode(True)   # 启用旧版模式
hotkey_mgr.set_legacy_mode(False)  # 启用新版模式
```

### 2. 状态查询
```python
is_legacy = hotkey_mgr.is_legacy_mode()
reg_info = hotkey_mgr.get_registration_info()
```

### 3. 详细注册信息
程序会显示详细的热键注册状态，包括模式、ID、策略等。

## 回退方案

如果需要使用新版冲突处理逻辑，只需设置：
```python
hotkey_mgr = QtHotkeyManager(
    settings_mgr, 
    legacy_mode=False  # 禁用旧版兼容模式
)
```

## 总结

这个解决方案：
1. **保持向后兼容**: 默认使用旧版行为
2. **提供新功能**: 可选择使用新版冲突处理
3. **用户友好**: 热键失败时程序仍正常运行
4. **详细日志**: 提供完整的调试信息
5. **灵活配置**: 支持运行时切换模式

用户现在应该能够成功注册热键并正常使用程序功能了。 