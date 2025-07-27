# BlurWindow 半透明窗口说明

## 概述

本项目集成了 BlurWindow 库，实现了真正的系统级半透明效果，支持 Windows 10 和 Windows 11。

## BlurWindow 库特性

BlurWindow 库封装了 Windows 的 DWM API：
- `SetWindowCompositionAttribute` (Windows 10)
- `DwmSetWindowAttribute` (Windows 11)
- 自动判断系统版本并应用相应的半透明效果

## 支持的效果

### Windows 11
- **Acrylic 效果**: 真正的 Win11 毛玻璃效果
- 参数: `Acrylic=True`

### Windows 10  
- **Aero 效果**: 经典的 Win10 半透明效果
- 参数: `Acrylic=False`

### 其他版本
- 通用半透明效果
- 自动降级处理

## 安装方法

### 方法1: 使用安装脚本
```bash
python install_blurwindow.py
```

### 方法2: 手动安装
```bash
pip install BlurWindow
```

### 方法3: 从源码安装
```bash
git clone https://github.com/ifwe/BlurWindow.git
cd BlurWindow
pip install -e .
```

## 使用方法

### 运行窗口
```bash
python test_frameless_blur_window.py
```

### 功能说明
1. **自动检测**: 程序会自动检测 Windows 版本
2. **效果应用**: 根据系统版本应用相应的半透明效果
3. **系统信息**: 点击"系统信息"按钮查看详细信息
4. **重新应用**: 点击"重新应用效果"按钮重新应用半透明效果

## 系统要求

- Windows 10 或更高版本
- Python 3.7+
- PyQt6
- BlurWindow 库

## 故障排除

### 问题1: BlurWindow 导入失败
```
解决方案: pip install BlurWindow
```

### 问题2: DWM 不可用
```
可能原因: 
- 系统版本过低
- DWM 服务被禁用
- 显卡驱动问题
```

### 问题3: 效果不明显
```
解决方案:
- 确保窗口背景有内容
- 检查系统主题设置
- 尝试重新应用效果
```

## 技术细节

### API 调用
```python
from BlurWindow.blurWindow import GlobalBlur

# Windows 11
GlobalBlur(hwnd, Acrylic=True, Dark=False, QWidget=widget)

# Windows 10  
GlobalBlur(hwnd, Acrylic=False, Dark=False, QWidget=widget)
```

### 系统检测
```python
def get_windows_version():
    import platform
    version = platform.version()
    if "11.0" in version:
        return "Windows 11"
    elif "10.0" in version:
        return "Windows 10"
    return "Unknown"
```

## 注意事项

1. **性能**: BlurWindow 效果会消耗一定的 GPU 资源
2. **兼容性**: 某些老旧显卡可能不支持 DWM 效果
3. **主题**: 效果会根据系统主题自动调整
4. **权限**: 某些效果可能需要管理员权限

## 更新日志

- v1.0: 基础 BlurWindow 集成
- v1.1: 添加 Windows 10 适配
- v1.2: 改进系统检测和错误处理 