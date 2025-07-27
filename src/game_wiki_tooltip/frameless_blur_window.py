"""
无边框PyQt6窗口，具有半透明效果和BlurWindow集成
"""





import sys
import ctypes
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QLineEdit
)
from enum import Enum
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint,
    pyqtSignal, pyqtSlot, QSize
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QLinearGradient,
    QPalette, QPixmap, QPainterPath, QRegion, QScreen, QIcon
)

# 尝试导入BlurWindow
try:
    from BlurWindow.blurWindow import GlobalBlur
    BLUR_WINDOW_AVAILABLE = True
    print("✅ BlurWindow模块加载成功")
except ImportError:
    print("警告: BlurWindow模块未找到，将使用默认透明效果")
    BLUR_WINDOW_AVAILABLE = False

# Windows版本检测
def get_windows_version():
    """获取Windows版本信息"""
    try:
        import platform
        version = platform.version()
        if "10.0" in version:
            return "Windows 10"
        elif "11.0" in version:
            return "Windows 11"
        else:
            return f"Windows {version}"
    except:
        return "Unknown"

class WindowState(Enum):
    """窗口状态枚举"""
    CHAT_ONLY = "chat_only"      # 只显示聊天框
    FULL_CONTENT = "full_content" # 显示所有内容
    WEBVIEW = "webview"          # WebView2形态

def load_svg_icon(svg_path, color="#666666", size=16):
    """加载SVG图标并设置颜色"""
    try:
        import os
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtCore import QByteArray
        
        # 检查文件是否存在
        if not os.path.exists(svg_path):
            print(f"SVG文件不存在: {svg_path}")
            return QIcon()
        
        # 读取SVG文件
        with open(svg_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()
        
        # 替换颜色
        svg_content = svg_content.replace('stroke="#000000"', f'stroke="{color}"')
        svg_content = svg_content.replace('fill="#000000"', f'fill="{color}"')
        
        # 创建图标
        icon = QIcon()
        renderer = QSvgRenderer(QByteArray(svg_content.encode()))
        
        # 创建不同尺寸的pixmap
        for s in [size, size*2]:  # 支持高DPI
            pixmap = QPixmap(s, s)
            pixmap.fill(QColor(0, 0, 0, 0))  # 透明背景
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            icon.addPixmap(pixmap)
        
        return icon
    except ImportError:
        print("PyQt6-SVG未安装，使用备用图标")
        return QIcon()
    except Exception as e:
        print(f"加载SVG图标失败: {e}")
        return QIcon()

def create_fallback_icon(text, color="#666666"):
    """创建备用文本图标"""
    icon = QIcon()
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(0, 0, 0, 0))
    
    painter = QPainter(pixmap)
    painter.setPen(QColor(color))
    painter.setFont(QFont("Segoe UI", 8))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    
    icon.addPixmap(pixmap)
    return icon



class FramelessBlurWindow(QMainWindow):
    """无边框窗口，具有半透明效果和BlurWindow集成"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        
        # 窗口属性
        self.dragging = False
        self.resizing = False
        self.resize_edge = None
        self.drag_position = QPoint()
        self.resize_start_pos = QPoint()
        self.resize_start_geometry = QRect()
        self.background_widget = None
        
        # 窗口状态管理
        self.current_state = WindowState.CHAT_ONLY
        self.has_sent_message = False
        
        # 组件引用（稍后初始化）
        self.title_bar = None
        self.content_frame = None
        self.search_bar = None
        self.webview_widget = None
        
        # 启用鼠标跟踪
        self.setMouseTracking(True)
        
        # 初始化UI
        self.init_ui()
        
        # 根据初始状态设置窗口大小和位置
        self.update_window_layout()
        
        # 应用BlurWindow半透明效果
        self.apply_blur_effect()
        
    def init_ui(self):
        """初始化用户界面"""
        # 创建中央部件
        central_widget = QWidget()
        central_widget.setMouseTracking(True)  # 启用鼠标跟踪
        self.setCentralWidget(central_widget)
        
        # 创建主容器框架（确保与BlurWindow层大小一致）
        main_container = QFrame()
        main_container.setObjectName("mainContainer")
        main_container.setMouseTracking(True)  # 启用鼠标跟踪
        
        # 保存main_container引用以便后续调整
        self.main_container = main_container
        
        # 中央部件布局（只包含主容器）
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)  # 与BlurWindow边距一致
        central_layout.addWidget(main_container)
        
        # 主容器布局
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)  # 内部无边距
        main_layout.setSpacing(0)
        
        # 标题栏
        self.title_bar = self.create_title_bar()
        main_layout.addWidget(self.title_bar)
        
        # 内容区域
        self.content_frame = self.create_content_area()
        main_layout.addWidget(self.content_frame)
        
        # 底部搜索栏区域
        self.search_bar = self.create_search_bar()
        main_layout.addWidget(self.search_bar)
        
        # WebView区域（初始隐藏）
        self.webview_widget = self.create_webview_area()
        main_layout.addWidget(self.webview_widget)
        
        # 设置样式
        self.setup_styles()
        
        # 设置初始状态的搜索栏样式（CHAT_ONLY模式）
        self.update_search_bar_style(chat_only_mode=True)
        
        # 为所有子控件启用鼠标跟踪
        self.enable_mouse_tracking_for_children()
    
    def enable_mouse_tracking_for_children(self):
        """为所有子控件递归启用鼠标跟踪"""
        def enable_tracking(widget):
            widget.setMouseTracking(True)
            for child in widget.findChildren(QWidget):
                enable_tracking(child)
        
        enable_tracking(self)
        
    def apply_blur_effect(self):
        """应用BlurWindow半透明效果"""
        if BLUR_WINDOW_AVAILABLE:
            try:
                windows_version = get_windows_version()
                print(f"检测到系统版本: {windows_version}")
                
                # 设置窗口圆角
                self.set_window_rounded_corners()
                
                # 根据Windows版本选择合适的参数
                if "Windows 11" in windows_version:
                    # Win11使用Acrylic效果
                    GlobalBlur(
                        int(self.winId()), 
                        Acrylic=True,    # Win11 Acrylic效果
                        Dark=False,      # 浅色主题
                        QWidget=self
                    )
                    print("✅ Win11 Acrylic效果已应用")
                elif "Windows 10" in windows_version:
                    # Win10使用Aero效果
                    GlobalBlur(
                        int(self.winId()), 
                        Acrylic=False,   # Win10 Aero效果
                        Dark=False,      # 浅色主题
                        QWidget=self
                    )
                    print("✅ Win10 Aero效果已应用")
                else:
                    # 其他版本尝试通用效果
                    GlobalBlur(
                        int(self.winId()), 
                        Acrylic=False,   # 通用效果
                        Dark=False,      # 浅色主题
                        QWidget=self
                    )
                    print(f"✅ 通用半透明效果已应用 ({windows_version})")
                    
            except Exception as e:
                print(f"❌ BlurWindow应用失败: {e}")
                print("将使用默认透明效果")
        else:
            print("⚠️ BlurWindow不可用，使用默认透明效果")
            
    def set_window_rounded_corners(self):
        """设置窗口圆角"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Windows API 常量
            DWM_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            
            # 获取窗口句柄
            hwnd = int(self.winId())
            
            # 调用 DwmSetWindowAttribute 设置圆角
            dwmapi = ctypes.windll.dwmapi
            corner_preference = wintypes.DWORD(DWMWCP_ROUND)
            result = dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWM_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(corner_preference),
                ctypes.sizeof(corner_preference)
            )
            
            if result == 0:
                print("✅ 窗口圆角设置成功")
            else:
                print(f"⚠️ 窗口圆角设置失败: {result}")
                
        except Exception as e:
            print(f"❌ 设置窗口圆角失败: {e}")
        
    def create_title_bar(self):
        """创建标题栏"""
        title_bar = QFrame()
        title_bar.setFixedHeight(40)
        title_bar.setObjectName("titleBar")
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # 标题
        self.title_label = QLabel("游戏智能助手")
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # 窗口控制按钮
        minimize_btn = QPushButton("─")
        minimize_btn.setObjectName("minimizeBtn")
        minimize_btn.setFixedSize(30, 25)
        minimize_btn.clicked.connect(self.showMinimized)
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(30, 25)
        close_btn.clicked.connect(self.close)
        
        layout.addWidget(minimize_btn)
        layout.addWidget(close_btn)
        
        return title_bar
        
    def create_content_area(self):
        """创建内容区域"""
        content_frame = QFrame()
        content_frame.setObjectName("contentFrame")
        content_frame.setMinimumHeight(200)
        
        layout = QVBoxLayout(content_frame)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 中文内容区域
        chinese_section = QFrame()
        chinese_section.setObjectName("chineseSection")
        
        chinese_layout = QVBoxLayout(chinese_section)
        chinese_layout.setContentsMargins(0, 0, 0, 15)
        
        chinese_title = QLabel("中文内容区域")
        chinese_title.setObjectName("chineseTitle")
        chinese_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        chinese_content = QLabel(
            "这是一个使用思源黑体（Source Han Sans SC）的中文内容区域。\n"
            "思源黑体是Adobe和Google联合开发的开源中文字体，\n"
            "具有优秀的可读性和现代感。\n"
            "适合用于界面设计和正文排版。"
        )
        chinese_content.setObjectName("chineseContent")
        chinese_content.setAlignment(Qt.AlignmentFlag.AlignLeft)
        chinese_content.setWordWrap(True)
        
        chinese_layout.addWidget(chinese_title)
        chinese_layout.addWidget(chinese_content)
        
        # 英文内容区域
        english_section = QFrame()
        english_section.setObjectName("englishSection")
        
        english_layout = QVBoxLayout(english_section)
        english_layout.setContentsMargins(0, 0, 0, 15)
        
        english_title = QLabel("English Content Section")
        english_title.setObjectName("englishTitle")
        english_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        english_content = QLabel(
            "This is an English content section using Work Sans font.\n"
            "Work Sans is a modern, clean sans-serif font designed\n"
            "for optimal readability on screens and interfaces.\n"
            "It provides excellent legibility for UI elements."
        )
        english_content.setObjectName("englishContent")
        english_content.setAlignment(Qt.AlignmentFlag.AlignLeft)
        english_content.setWordWrap(True)
        
        english_layout.addWidget(english_title)
        english_layout.addWidget(english_content)
        
        layout.addWidget(chinese_section)
        layout.addWidget(english_section)
        layout.addStretch()
        
        return content_frame
        
    def create_search_bar(self):
        """创建底部一体化搜索栏"""
        search_bar = QFrame()
        search_bar.setFixedHeight(95)  # 调整高度适配紧凑布局
        search_bar.setObjectName("searchBar")
        
        layout = QVBoxLayout(search_bar)
        layout.setContentsMargins(10, 10, 10, 10)  # 默认margin
        layout.setSpacing(0)
        
        # 保存layout引用以便后续调整
        self.search_bar_layout = layout
        
        # 一体化搜索框容器（包含两行内容）
        search_container = QFrame()
        search_container.setObjectName("searchContainer")
        search_container.setFixedHeight(80)  # 增加搜索框高度
        
        # 保存search_container引用以便后续调整
        self.search_container = search_container
        
        # 搜索框内部布局
        container_layout = QVBoxLayout(search_container)
        container_layout.setContentsMargins(12, 8, 12, 8)  # 内部padding
        container_layout.setSpacing(6)  # 两行之间的间距
        
        # 上半部分：搜索输入区域
        search_input_row = QFrame()
        search_input_row.setObjectName("searchInputRow")
        
        input_layout = QHBoxLayout(search_input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        
        # 搜索输入框
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Recommend content / 搜索游戏内容")
        self.search_input.returnPressed.connect(self.on_search_triggered)
        
        input_layout.addWidget(self.search_input)
        
        # 下半部分：快捷访问图标
        quick_access_row = QFrame()
        quick_access_row.setObjectName("quickAccessRow")
        
        access_layout = QHBoxLayout(quick_access_row)
        access_layout.setContentsMargins(0, 0, 0, 0)
        access_layout.setSpacing(8)  # 减小图标间距
        
        # 历史记录按钮
        history_btn = QPushButton()
        history_btn.setObjectName("historyBtn")
        history_btn.setFixedSize(32, 32)  # 增大按钮尺寸
        history_btn.setToolTip("历史记录")
        
        # 加载历史记录图标
        history_icon_path = "src/game_wiki_tooltip/assets/icons/refresh-ccw-clock-svgrepo-com.svg"
        history_icon = load_svg_icon(history_icon_path, color="#111111", size=20)  # 放大图标
        if history_icon.isNull():
            history_icon = create_fallback_icon("⏱", "#111111")
        history_btn.setIcon(history_icon)
        history_btn.setIconSize(QSize(20, 20))
        
        # 外部网站下拉按钮
        external_btn = QPushButton()
        external_btn.setObjectName("externalBtn")
        external_btn.setFixedSize(32, 32)  # 增大按钮尺寸
        external_btn.setToolTip("外部网站")
        external_btn.clicked.connect(self.on_external_website_clicked)
        
        # 加载外部网站图标
        external_icon_path = "src/game_wiki_tooltip/assets/icons/globe-alt-1-svgrepo-com.svg"
        external_icon = load_svg_icon(external_icon_path, color="#111111", size=20)  # 放大图标
        if external_icon.isNull():
            external_icon = create_fallback_icon("▼", "#111111")
        external_btn.setIcon(external_icon)
        external_btn.setIconSize(QSize(20, 20))
        
        # 搜索按钮（作为设置按钮的替代）
        search_btn = QPushButton()
        search_btn.setObjectName("searchBtn")
        search_btn.setFixedSize(32, 32)  # 增大按钮尺寸
        search_btn.setToolTip("搜索")
        
        # 加载搜索图标
        search_icon_path = "src/game_wiki_tooltip/assets/icons/search-alt-1-svgrepo-com.svg"
        search_icon = load_svg_icon(search_icon_path, color="#111111", size=20)  # 放大图标
        if search_icon.isNull():
            search_icon = create_fallback_icon("🔍", "#111111")
        search_btn.setIcon(search_icon)
        search_btn.setIconSize(QSize(20, 20))
        
        # 发送按钮（向上箭头）
        send_btn = QPushButton()
        send_btn.setObjectName("sendBtn")
        send_btn.setFixedSize(32, 32)  # 增大按钮尺寸
        send_btn.clicked.connect(self.on_search_triggered)
        
        # 加载发送图标
        send_icon_path = "src/game_wiki_tooltip/assets/icons/arrow-circle-up-svgrepo-com.svg"
        send_icon = load_svg_icon(send_icon_path, color="#111111", size=20)
        if send_icon.isNull():
            send_icon = create_fallback_icon("↑", "#111111")
        send_btn.setIcon(send_icon)
        send_btn.setIconSize(QSize(20, 20))
        
        access_layout.addWidget(history_btn)
        access_layout.addWidget(external_btn)
        access_layout.addWidget(search_btn)
        access_layout.addStretch()  # 中间留空
        access_layout.addWidget(send_btn)  # 发送按钮在右侧
        
        # 添加到主容器
        container_layout.addWidget(search_input_row)
        container_layout.addWidget(quick_access_row)
        
        layout.addWidget(search_container)
        
        return search_bar
    
    def create_webview_area(self):
        """创建WebView区域"""
        webview_frame = QFrame()
        webview_frame.setObjectName("webviewFrame")
        webview_frame.hide()  # 初始隐藏
        
        layout = QVBoxLayout(webview_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # WebView占位符（实际实现时需要集成WebView2）
        webview_placeholder = QLabel("WebView2 区域")
        webview_placeholder.setObjectName("webviewPlaceholder")
        webview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        webview_placeholder.setMinimumHeight(400)
        
        layout.addWidget(webview_placeholder)
        
        return webview_frame
    
    def update_window_layout(self):
        """根据当前状态更新窗口布局"""
        if self.current_state == WindowState.CHAT_ONLY:
            # 只显示聊天框，隐藏标题栏
            self.title_bar.hide()
            self.content_frame.hide()
            self.search_bar.show()
            self.webview_widget.hide()
            
            # 更新主容器样式为全圆角
            self.update_container_style(full_rounded=True)
            
            # 去除搜索栏的margin，使其完全填满窗口
            self.search_bar_layout.setContentsMargins(0, 0, 0, 0)
            
            # 设置search_bar高度与search_container一致
            container_height = self.search_container.height()
            self.search_bar.setFixedHeight(container_height)
            
            # 设置search_container圆角为10px（CHAT_ONLY模式）
            self.update_search_container_style(chat_only_mode=True)
            
            # 设置search_bar全圆角（CHAT_ONLY模式）
            self.update_search_bar_style(chat_only_mode=True)
            
            # 隐藏mainContainer的边框
            self.update_main_container_border(hide_border=True)
            
            # 调整窗口大小 - 只显示搜索框
            self.resize(380, container_height)  # 调整为搜索框高度
            self.position_chat_window()
            
        elif self.current_state == WindowState.FULL_CONTENT:
            # 显示所有内容
            self.title_bar.show()
            self.content_frame.show()
            self.search_bar.show()
            self.webview_widget.hide()
            
            # 更新标题
            self.title_label.setText("游戏智能助手 - 对话模式")
            
            # 恢复主容器样式为部分圆角
            self.update_container_style(full_rounded=False)
            
            # 恢复搜索栏的默认margin
            self.search_bar_layout.setContentsMargins(10, 10, 10, 10)
            
            # 恢复search_bar的默认高度
            self.search_bar.setFixedHeight(95)
            
            # 恢复search_container的默认样式
            self.update_search_container_style(chat_only_mode=False)
            
            # 设置search_bar只有底部圆角（FULL_CONTENT模式）
            self.update_search_bar_style(chat_only_mode=False)
            
            # 恢复mainContainer的边框
            self.update_main_container_border(hide_border=False)
            
            # 调整窗口大小 - 完整内容
            self.resize(380, 450)
            self.center_window()
            
        elif self.current_state == WindowState.WEBVIEW:
            # WebView形态
            self.title_bar.show()
            self.content_frame.hide()
            self.search_bar.hide()
            self.webview_widget.show()
            
            # 更新标题
            self.title_label.setText("游戏智能助手 - 网页浏览")
            
            # 恢复主容器样式为部分圆角
            self.update_container_style(full_rounded=False)
            
            # 恢复搜索栏的默认margin（尽管在WebView模式下是隐藏的）
            self.search_bar_layout.setContentsMargins(10, 10, 10, 10)
            
            # 恢复search_bar的默认高度
            self.search_bar.setFixedHeight(95)
            
            # 恢复search_container的默认样式
            self.update_search_container_style(chat_only_mode=False)
            
            # 设置search_bar只有底部圆角（WebView模式）
            self.update_search_bar_style(chat_only_mode=False)
            
            # 恢复mainContainer的边框
            self.update_main_container_border(hide_border=False)
            
            # 调整窗口大小和位置 - 屏幕右上角，约1/4屏幕大小
            screen = QApplication.primaryScreen()
            screen_geometry = screen.geometry()
            
            # 计算约1/4屏幕大小（稍小一点）
            width = int(screen_geometry.width() * 0.23)  # 稍小于1/4
            height = int(screen_geometry.height() * 0.23)
            
            # 设置最小尺寸
            width = max(width, 400)
            height = max(height, 300)
            
            # 定位到右上角
            x = screen_geometry.width() - width - 20  # 距离右边缘20px
            y = 20  # 距离顶部20px
            
            self.setGeometry(x, y, width, height)
    
    def switch_to_chat_only(self):
        """切换到只显示聊天框形态"""
        self.current_state = WindowState.CHAT_ONLY
        self.update_window_layout()
    
    def switch_to_full_content(self):
        """切换到显示所有内容形态"""
        self.current_state = WindowState.FULL_CONTENT
        self.has_sent_message = True
        self.update_window_layout()
    
    def switch_to_webview(self):
        """切换到WebView形态"""
        self.current_state = WindowState.WEBVIEW
        self.update_window_layout()
    
    def update_container_style(self, full_rounded=False):
        """更新主容器的圆角样式"""
        if full_rounded:
            # CHAT_ONLY模式：全圆角
            container_style = """
            #mainContainer {
                background: rgba(255, 255, 255, 115);
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 40);
            }
            """
        else:
            # 其他模式：标题栏和搜索栏有不同的圆角
            container_style = """
            #mainContainer {
                background: rgba(255, 255, 255, 115);
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 40);
            }
            """
        
        # 重新应用整个样式表（简化处理）
        self.setup_styles()
    
    def update_search_container_style(self, chat_only_mode=False):
        """更新search_container的样式"""
        # 统一设置10px圆角
        self.search_container.setStyleSheet("""
            QFrame#searchContainer {
                background: rgba(0,0,0,10);
                border: 1px solid rgba(200, 200, 200, 150);
                border-radius: 10px;
            }
        """)
    
    def update_search_bar_style(self, chat_only_mode=False):
        """更新search_bar的圆角样式"""
        if chat_only_mode:
            # CHAT_ONLY模式：全圆角
            search_bar_style = """
                QFrame#searchBar {
                    background: rgba(255, 255, 255, 115);
                    border-radius: 10px;
                    border: none;
                }
            """
        else:
            # FULL_CONTENT和WebView模式：只有底部圆角，取消上方圆角
            search_bar_style = """
                QFrame#searchBar {
                    background: rgba(255, 255, 255, 115);
                    border-bottom-left-radius: 10px;
                    border-bottom-right-radius: 10px;
                    border-top-left-radius: 0px;
                    border-top-right-radius: 0px;
                    border: none;
                }
            """
        
        self.search_bar.setStyleSheet(search_bar_style)
    
    def update_main_container_border(self, hide_border=False):
        """更新mainContainer的边框显示/隐藏"""
        if hide_border:
            # CHAT_ONLY模式：隐藏边框
            self.main_container.setStyleSheet("""
                QFrame#mainContainer {
                    background: rgba(255, 255, 255, 115);
                    border-radius: 10px;
                    border: none;
                }
            """)
        else:
            # 其他模式：显示边框
            self.main_container.setStyleSheet("""
                QFrame#mainContainer {
                    background: rgba(255, 255, 255, 115);
                    border-radius: 10px;
                    border: 1px solid rgba(255, 255, 255, 40);
                }
            """)
    
    def on_search_triggered(self):
        """搜索触发事件"""
        search_text = self.search_input.text().strip()
        if search_text:
            print(f"搜索内容: {search_text}")
            
            # 第一次发送消息时切换到完整内容形态
            if not self.has_sent_message:
                self.switch_to_full_content()
            
            # 清空输入框
            self.search_input.clear()
            
            # 这里可以添加实际的搜索逻辑
        else:
            print("请输入搜索关键词")
    
    def on_external_website_clicked(self):
        """外部网站按钮点击事件"""
        print("切换到WebView形态")
        self.switch_to_webview()
        
    def setup_styles(self):
        """设置样式表"""
        style_sheet = """
        QMainWindow {
            background: transparent;
        }
        
        QFrame {
            border: none;  /* 去除所有QFrame的默认边框 */
        }
        
        #mainContainer {
            background: rgba(255, 255, 255, 115);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 40);
        }

        #titleBar {
            background: rgba(255, 255, 255, 115);  /* 统一背景色 */
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            border: none;
            border-bottom: none;  /* 确保没有底部边框 */
            margin-bottom: 0px;   /* 去除底部边距 */
        }
    
        #titleLabel {
            color: #111111;
            font-size: 14px;
            font-weight: bold;
        }
        
        #minimizeBtn, #closeBtn {
            background: rgba(255, 255, 255, 150);
            border: none;
            border-radius: 5px;
            color: #111111;
            font-weight: bold;
        }
        
        #minimizeBtn:hover {
            background: rgba(255, 255, 255, 180);
        }
        
        #closeBtn:hover {
            background: rgba(220, 60, 60, 180);
            color: white;
        }
        
        #contentFrame {
            background: rgba(255, 255, 255, 115);  /* 统一背景色 */
            border: none;
            border-top: none;     /* 确保没有顶部边框 */
            margin-top: 0px;      /* 去除顶部边距 */
            font-family: "Segoe UI", sans-serif;
            font-size: 14px;
        }
        
        #chineseSection, #englishSection {
            background: transparent;
            border: none;
        }
        
        #chineseTitle {
            color: #111111;
            font-size: 16px;
            font-weight: bold;
            font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
            margin-bottom: 8px;
        }
        
        #chineseContent {
            color: #111111;
            font-size: 14px;
            line-height: 1.6;
            font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
        }
        
        #englishTitle {
            color: #111111;
            font-size: 16px;
            font-weight: bold;
            font-family: "Segoe UI", sans-serif;
            margin-bottom: 8px;
        }
        
        #englishContent {
            color: #111111;
            font-size: 14px;
            line-height: 1.6;
            font-family: "Segoe UI", sans-serif;
        }
        
        #searchContainer {
            background: rgba(0,0,0,10);  /* 比窗口背景更深的搜索框背景 */
            border: 1px solid rgba(200, 200, 200, 150);
            border-radius: 15px;  /* 圆角搜索框 */
        }
        
        #searchInputRow, #quickAccessRow {
            background: transparent;
            border: none;
        }
        
        #searchInput {
            background: transparent;  /* 透明背景融入容器 */
            border: none;
            color: #111111;
            font-size: 14px;
            font-family: "Segoe UI", sans-serif;
        }
        
        #searchInput:focus {
            background: transparent;
            border: none;
            outline: none;
        }
        
        #sendBtn {
            background: transparent;
            border: none;
            color: #111111;
            font-size: 12px;
            font-weight: normal;
        }
        
        #sendBtn:hover {
            background: rgba(220, 220, 220, 120);
            border-radius: 4px;
        }
        
        #historyBtn, #externalBtn, #searchBtn {
            background: transparent;
            border: none;
            color: #111111;
            font-size: 14px;
            font-weight: normal;
        }
        
        #historyBtn:hover, #externalBtn:hover, #searchBtn:hover {
            background: rgba(220, 220, 220, 120);
            border-radius: 4px;
        }
        
        #webviewFrame {
            background: rgba(255, 255, 255, 115);  /* 统一背景色 */
            border: none;
        }
        
        #webviewPlaceholder {
            color: #333333;
            font-size: 16px;
            font-family: "Segoe UI", sans-serif;
            background: rgba(245, 245, 245, 180);
            border: 2px dashed rgba(200, 200, 200, 150);
            border-radius: 10px;
            margin: 15px;
        }
        """
        self.setStyleSheet(style_sheet)
        

        
    def center_window(self):
        """将窗口居中显示"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        window_geometry = self.geometry()
        
        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2
        
        self.move(x, y)
    
    def position_chat_window(self):
        """将搜索框定位到屏幕右下角"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        window_geometry = self.geometry()
        
        # 右侧留下约1/5的空间
        x = screen_geometry.width() - window_geometry.width() - int(screen_geometry.width() * 0.2)
        # 接近底部但不紧贴，留下约50px的间距
        y = screen_geometry.height() - window_geometry.height() - 50
        
        self.move(x, y)

    def get_resize_edge(self, pos):
        """检测鼠标位置是否在窗口边缘，返回边缘类型"""
        margin = 10
        rect = self.rect()
        
        left = pos.x() <= margin
        right = pos.x() >= rect.width() - margin
        top = pos.y() <= margin
        bottom = pos.y() >= rect.height() - margin
        
        if top and left:
            return 'top-left'
        elif top and right:
            return 'top-right'
        elif bottom and left:
            return 'bottom-left'
        elif bottom and right:
            return 'bottom-right'
        elif top:
            return 'top'
        elif bottom:
            return 'bottom'
        elif left:
            return 'left'
        elif right:
            return 'right'
        else:
            return None
    
    def set_resize_cursor(self, edge):
        """根据边缘类型设置鼠标光标"""
        if edge == 'top' or edge == 'bottom':
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge == 'left' or edge == 'right':
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge == 'top-left' or edge == 'bottom-right':
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge == 'top-right' or edge == 'bottom-left':
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        

        
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            edge = self.get_resize_edge(pos)
            
            if edge:
                # 开始调整大小
                self.resizing = True
                self.resize_edge = edge
                self.resize_start_pos = event.globalPosition().toPoint()
                self.resize_start_geometry = self.geometry()
            else:
                # 开始拖动
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        pos = event.position().toPoint()
        
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self.resizing and self.resize_edge:
                # 调整窗口大小
                self.resize_window(event.globalPosition().toPoint())
            elif self.dragging:
                # 移动窗口
                self.move(event.globalPosition().toPoint() - self.drag_position)
        else:
            # 检测鼠标是否在边缘，设置光标
            edge = self.get_resize_edge(pos)
            self.set_resize_cursor(edge)
        
            event.accept()
            
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.resizing = False
            self.resize_edge = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
    
    def resize_window(self, global_pos):
        """调整窗口大小"""
        if not self.resize_edge:
            return
            
        delta = global_pos - self.resize_start_pos
        geometry = QRect(self.resize_start_geometry)
        
        # 设置最小窗口大小
        min_width = 300
        min_height = 200
        
        # 处理水平方向调整
        if 'left' in self.resize_edge:
            new_width = geometry.width() - delta.x()
            if new_width >= min_width:
                geometry.setLeft(geometry.left() + delta.x())
            else:
                # 限制在最小宽度，调整左边位置
                geometry.setLeft(geometry.right() - min_width)
        elif 'right' in self.resize_edge:
            new_width = geometry.width() + delta.x()
            if new_width >= min_width:
                geometry.setWidth(new_width)
            else:
                # 限制在最小宽度
                geometry.setWidth(min_width)
                
        # 处理垂直方向调整
        if 'top' in self.resize_edge:
            new_height = geometry.height() - delta.y()
            if new_height >= min_height:
                geometry.setTop(geometry.top() + delta.y())
            else:
                # 限制在最小高度，调整顶部位置
                geometry.setTop(geometry.bottom() - min_height)
        elif 'bottom' in self.resize_edge:
            new_height = geometry.height() + delta.y()
            if new_height >= min_height:
                geometry.setHeight(new_height)
            else:
                # 限制在最小高度
                geometry.setHeight(min_height)
        
        self.setGeometry(geometry)

    def keyPressEvent(self, event):
        """键盘按下事件"""
        # ESC键重置到聊天框形态
        if event.key() == Qt.Key.Key_Escape:
            print("ESC键：重置到聊天框形态")
            self.has_sent_message = False
            self.switch_to_chat_only()
        # F1键切换到完整内容形态
        elif event.key() == Qt.Key.Key_F1:
            print("F1键：切换到完整内容形态")
            self.switch_to_full_content()
        # F2键切换到WebView形态
        elif event.key() == Qt.Key.Key_F2:
            print("F2键：切换到WebView形态")
            self.switch_to_webview()
        else:
            super().keyPressEvent(event)
        
    def closeEvent(self, event):
        """关闭事件"""
        event.accept()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 创建窗口
    window = FramelessBlurWindow()
    window.show()
    
    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 