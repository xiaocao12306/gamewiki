"""
Overlay manager – handles hotkey events and shows wiki content.
"""

import asyncio
import logging
import webbrowser
import webview
import ctypes
import re
import urllib.parse
from typing import Optional, Dict, Any
import pathlib
import time
import threading

from src.game_wiki_tooltip.config import GameConfig, GameConfigManager, SettingsManager
from src.game_wiki_tooltip.searchbar import ask_keyword, process_query_with_intent
from src.game_wiki_tooltip.utils import get_foreground_title

logger = logging.getLogger(__name__)

def _get_scale() -> float:
    """获取显示器缩放因子（仅 Windows）"""
    try:
        shcore = ctypes.windll.shcore
        hMonitor = ctypes.windll.user32.MonitorFromWindow(
            None,   # 传 None 拿到主显示器；要求 Win8.1+
            1       # MONITOR_DEFAULTTOPRIMARY
        )
        factor = ctypes.c_uint()
        if shcore.GetScaleFactorForMonitor(hMonitor, ctypes.byref(factor)) == 0:
            return factor.value / 100.0
    except Exception:
        pass
    return 1.0            # 失败就当 100 %

class OverlayManager:
    def __init__(self, settings_mgr: SettingsManager, game_cfg_mgr: GameConfigManager):
        self.settings_mgr = settings_mgr
        self.game_cfg_mgr = game_cfg_mgr
        self._current_window = None
        self._last_url = None

    def log(self, msg):
        """接收JavaScript日志信息"""
        logger.info(f"[JS] {msg}")

    def _create_loading_html(self):
        """创建加载动画的HTML页面"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>正在为您寻找合适的wiki...</title>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .loading-container {
                    text-align: center;
                    color: white;
                }
                .spinner {
                    width: 50px;
                    height: 50px;
                    border: 4px solid rgba(255, 255, 255, 0.3);
                    border-top: 4px solid white;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 20px;
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
                .loading-text {
                    font-size: 18px;
                    font-weight: 300;
                    margin-bottom: 10px;
                }
                .sub-text {
                    font-size: 14px;
                    opacity: 0.8;
                }
            </style>
        </head>
        <body>
            <div class="loading-container">
                <div class="spinner"></div>
                <div class="loading-text">正在搜索...</div>
                <div class="sub-text">请稍候，正在为您寻找合适的wiki</div>
                <div class="sub-text">长时间未打开时，请检查网络链接并再次尝试</div>
            </div>
        </body>
        </html>
        """

    def _open_wiki_window(self, url=None, geom=None):
        """创建wiki窗口，支持直接传入URL"""
        print("=== 开始创建wiki窗口 ===")
        w, h, x, y = (geom or (800, 600, 100, 100))
        print(f"窗口几何: w={w}, h={h}, x={x}, y={y}")
        
        if url:
            # 如果直接传入URL，直接创建指向该URL的窗口
            print(f"直接创建指向URL的窗口: {url}")
            self._current_window = webview.create_window(
                'Wiki',
                url=url,
                width=w, height=h, x=x, y=y,
                resizable=True, text_select=True,
                confirm_close=False,
                on_top=True,
                js_api=self
            )
            # 关窗时保存几何
            self._current_window.events.closing += lambda: self._save_geometry(self._current_window)
            print("=== 直接URL窗口创建完成 ===")
            return self._current_window
        else:
            # 创建临时HTML文件用于加载动画
            import tempfile
            import os
            
            temp_html = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8')
            temp_html.write(self._create_loading_html())
            temp_html.close()
            
            print(f"临时HTML文件: {temp_html.name}")
            
            self._current_window = webview.create_window(
                'Wiki',
                url=f"file://{temp_html.name}",
                width=w, height=h, x=x, y=y,
                resizable=True, text_select=True,
                confirm_close=False,
                on_top=True,
                js_api=self
            )
            
            print("wiki窗口已创建")
            
            # 关窗时保存几何并清理临时文件
            def on_closing():
                print("wiki窗口关闭")
                self._save_geometry(self._current_window)
                try:
                    os.unlink(temp_html.name)
                    print("临时HTML文件已清理")
                except:
                    pass
            
            self._current_window.events.closing += on_closing
            
            # 设置窗口加载完成事件处理器，检查是否有待处理的URL
            def on_loaded():
                try:
                    # 检查是否有待处理的URL
                    if hasattr(self, '_pending_url') and self._pending_url:
                        print(f"加载待处理的URL: {self._pending_url}")
                        url_to_load = self._pending_url
                        js_to_inject = getattr(self, '_pending_js', None)
                        
                        # 立即清理待处理的URL，避免重复加载
                        delattr(self, '_pending_url')
                        if hasattr(self, '_pending_js'):
                            delattr(self, '_pending_js')
                        
                        # 加载URL
                        self._current_window.load_url(url_to_load)
                        
                        # 如果是Bing搜索，注入JavaScript
                        if js_to_inject and 'bing.com/search' in url_to_load:
                            def on_bing_loaded():
                                try:
                                    print("开始注入Bing搜索JavaScript代码")
                                    result = self._current_window.evaluate_js(js_to_inject)
                                    print(f"JavaScript注入结果: {result}")
                                except Exception as e:
                                    print(f"JavaScript注入失败: {e}")
                            
                            self._current_window.events.loaded += on_bing_loaded
                    else:
                        print("没有待处理的URL，保持加载动画")
                            
                except Exception as e:
                    print(f"加载待处理URL失败: {e}")
            
            self._current_window.events.loaded += on_loaded
            
            print("=== wiki窗口创建完成 ===")
            return self._current_window

    def _open_new_window(self, url: str, geom=None):
        """直接创建指向 url 的 WebView，并保存到 self._current_window"""
        w, h, x, y = (geom or (800, 600, 100, 100))
        self._current_window = webview.create_window(
            'Wiki',
            url=url,
            width=w, height=h, x=x, y=y,
            resizable=True, text_select=True,
            confirm_close=False,
            on_top=True,
            js_api=self
        )
        # 关窗时保存几何
        self._current_window.events.closing += \
            lambda: self._save_geometry(self._current_window)

    def found_valid_link(self, url: str):
        """JS 找到有效链接后回调"""
        logger.info(f"JavaScript找到有效链接: {url}")

        # 在主窗口中加载目标URL
        if self._current_window:
            try:
                logger.info(f"在主窗口中加载URL: {url}")
                self._current_window.load_url(url)
                return "ok-new"
            except Exception as e:
                logger.error(f"在主窗口中加载URL失败: {e}")
                return f"error: {e}"
        else:
            logger.error("主窗口不存在")
            return "error: no main window"

    def open_url(self, url: str):
        """在当前浮窗中加载目标 URL（供 JS 调用）"""
        logger.info(f"JavaScript 请求打开 URL: {url}")
        if self._current_window:
            # 和 destroy/newWindow 相比，load_url 不会重置大小、位置
            self._current_window.load_url(url)
        return "ok"

    def _save_geometry(self, window):
        """
        保存窗口几何信息，使用物理像素除以缩放因子得到逻辑像素
        避免在窗口关闭时调用 JavaScript
        """
        if not window:
            return

        try:
            scale = _get_scale()          # 1.25 / 1.50 / 1.00
            css_w = int(window.width / scale)
            css_h = int(window.height / scale)
            css_x = int(round(window.x / scale))
            css_y = int(round(window.y / scale))

            from src.game_wiki_tooltip.config import PopupConfig
            self.settings_mgr.settings.popup = PopupConfig(
                width=css_w, height=css_h, left=css_x, top=css_y
            )
            self.settings_mgr.save()
            logging.info(f"保存几何: x={css_x}, y={css_y}, w={css_w}, h={css_h}, scale={scale}")
        except Exception as e:
            logging.error(f"保存窗口几何信息失败: {e}")

    def _show_guide_result(self, answer: str, geom=None):
        """显示攻略结果窗口"""
        w, h, x, y = (geom or (800, 600, 100, 100))
        
        # 创建HTML内容
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>游戏攻略</title>
            <style>
                body {{
                    margin: 0;
                    padding: 20px;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    line-height: 1.6;
                }}
                .container {{
                    max-width: 800px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.1);
                    padding: 30px;
                    border-radius: 15px;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                }}
                h1 {{
                    text-align: center;
                    margin-bottom: 30px;
                    color: #fff;
                    font-size: 28px;
                    font-weight: 300;
                }}
                .content {{
                    white-space: pre-wrap;
                    font-size: 16px;
                    color: #f0f0f0;
                }}
                .footer {{
                    margin-top: 30px;
                    text-align: center;
                    font-size: 14px;
                    opacity: 0.8;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎮 游戏攻略</h1>
                <div class="content">{answer}</div>
                <div class="footer">
                    基于AI智能分析的游戏攻略建议
                </div>
            </div>
        </body>
        </html>
        """
        
        # 创建临时HTML文件
        import tempfile
        import os
        
        temp_html = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8')
        temp_html.write(html_content)
        temp_html.close()
        
        # 创建窗口
        self._current_window = webview.create_window(
            '游戏攻略',
            url=f"file://{temp_html.name}",
            width=w, height=h, x=x, y=y,
            resizable=True, text_select=True,
            confirm_close=False,
            on_top=True,
            js_api=self
        )
        
        # 关窗时保存几何并清理临时文件
        def on_closing():
            self._save_geometry(self._current_window)
            try:
                os.unlink(temp_html.name)
            except:
                pass
        
        self._current_window.events.closing += on_closing

    def _try_duckduckgo_quick_link(self, keyword: str, domain: str, geom) -> bool:
        """
        尝试使用DuckDuckGo快速链接功能
        返回True如果成功打开目标wiki网页，否则返回False
        """
        try:
            print("=== DuckDuckGo快速链接开始 ===")
            # 构建DuckDuckGo快速链接URL
            # 格式: https://duckduckgo.com/?q=!ducky+关键词+site:域名
            search_query = f"!ducky {keyword} site:{domain}"
            encoded_query = urllib.parse.quote(search_query)
            duckduckgo_url = f"https://duckduckgo.com/?q={encoded_query}"
            
            logger.info(f"尝试DuckDuckGo快速链接: {duckduckgo_url}")
            print(f"DuckDuckGo URL: {duckduckgo_url}")
            
            # 保存URL，等待webview启动后再加载
            self._pending_url = duckduckgo_url
            logger.info("DuckDuckGo URL已保存，等待webview启动")
            print(f"DuckDuckGo URL已保存: {duckduckgo_url}")
            print("等待webview启动")
            
            # 如果窗口已经存在，尝试延迟加载URL（给窗口一些启动时间）
            if self._current_window:
                def delayed_load():
                    try:
                        print("延迟加载DuckDuckGo URL")
                        self._current_window.load_url(duckduckgo_url)
                        print("DuckDuckGo URL加载成功")
                    except Exception as e:
                        print(f"延迟加载DuckDuckGo URL失败: {e}")
                
                # 使用线程延迟执行，给窗口启动时间
                import threading
                import time
                threading.Timer(0.5, delayed_load).start()
            
            return True
            
        except Exception as e:
            print(f"DuckDuckGo快速链接尝试失败: {e}")
            logger.error(f"DuckDuckGo快速链接尝试失败: {e}")
            return False

    def _fallback_to_bing_search(self, keyword: str, domain: str, geom):
        """
        回退到原来的Bing搜索+JavaScript自动点击逻辑
        """
        print("=== 开始Bing搜索回退 ===")
        logger.info("回退到Bing搜索逻辑")
        
        # 构建Bing搜索URL
        import urllib.parse
        import uuid
        
        search_query = f"{keyword} site:{domain}"
        encoded_query = urllib.parse.quote(search_query)
        random_id = str(uuid.uuid4()).replace('-', '').upper()[:16]
        bing_url = f"https://www.bing.com/search?q={encoded_query}&rdr=1&rdrig={random_id}"
        
        logger.info(f"构建Bing搜索URL: {bing_url}")
        print(f"Bing搜索URL: {bing_url}")
        
        # 读取并准备JavaScript代码，动态替换目标域名
        try:
            # 读取JavaScript模板文件
            js_file_path = pathlib.Path(__file__).parent / "auto_click.js"
            with open(js_file_path, 'r', encoding='utf-8') as f:
                auto_click_js = f.read().replace('{{DOMAIN}}', domain)
                
            logger.info("成功加载JavaScript模板")
            print("成功加载JavaScript模板")
        except Exception as e:
            logger.error(f"加载JavaScript模板失败: {e}")
            print(f"加载JavaScript模板失败: {e}")
            # 使用备用JavaScript代码
            auto_click_js = """
            (function() {
                console.log('使用备用JavaScript代码');
                // 简单的备用逻辑
                setTimeout(function() {
                    const links = document.querySelectorAll('#b_results li.b_algo h2 a');
                    if (links.length > 0) {
                        console.log('备用代码点击:', links[0].href);
                        links[0].click();
                    }
                }, 1000);
            })();
            """
        
        # 保存Bing搜索URL，等待webview启动后再加载
        self._pending_url = bing_url
        self._pending_js = auto_click_js
        print(f"Bing搜索URL已保存: {bing_url}")
        logger.info("Bing搜索URL已保存，等待webview启动")
        
        # 如果窗口已经存在，尝试延迟加载URL（给窗口一些启动时间）
        if self._current_window:
            def delayed_load():
                try:
                    print("延迟加载Bing搜索URL")
                    self._current_window.load_url(bing_url)
                    print("Bing搜索URL加载成功")
                except Exception as e:
                    print(f"延迟加载Bing搜索URL失败: {e}")
            
            # 使用线程延迟执行，给窗口启动时间
            import threading
            import time
            threading.Timer(0.5, delayed_load).start()
        
        print("=== Bing搜索回退完成 ===")

    async def on_hotkey(self):
        """Handle hotkey press."""
        try:
            print("=== 热键触发开始 ===")
            # 获取当前窗口标题
            current_title = get_foreground_title()
            logger.info(f"当前窗口标题: {current_title}")
            print(f"当前窗口标题: {current_title}")

            # 查找游戏配置
            game_config = self.game_cfg_mgr.for_title(current_title)
            if not game_config:
                logger.warning(f"未找到游戏配置: {current_title}")
                print(f"未找到游戏配置: {current_title}")
                return

            logger.info(f"找到的游戏配置: {game_config}")
            print(f"找到的游戏配置: {game_config}")

            # 获取基础URL和搜索需求
            base_url = game_config.BaseUrl
            needs_search = game_config.NeedsSearch
            
            # 提取游戏名称（从窗口标题中推断，或使用游戏配置的第一个匹配的名称）
            game_name = None
            for config_name, cfg in self.game_cfg_mgr._configs.items():
                if cfg == game_config:
                    game_name = config_name
                    break
            
            # 如果没有找到配置名称，使用窗口标题
            if not game_name:
                game_name = current_title

            logger.info(f"游戏配置: game_name={game_name}, base_url={base_url}, needs_search={needs_search}")
            print(f"游戏配置: game_name={game_name}, base_url={base_url}, needs_search={needs_search}")

            
            # 如果需要搜索，显示搜索框并进行意图判断
            if needs_search:
                print("=== 开始搜索流程 ===")
                logger.info("显示搜索框并进行意图判断")
                # 先获取用户输入
                print("等待用户输入关键词...")
                keyword = await ask_keyword()
                print(f"用户输入的关键词: {keyword}")
                if not keyword:
                    print("用户取消输入")
                    return

                if keyword == "<<LAST>>":
                    print("用户选择上次搜索")
                    if self._current_window:
                        self._current_window.show()
                        return
                    if not self._last_url:
                        logger.warning("没有上次搜索记录")
                        print("没有上次搜索记录")
                        return
                    url = self._last_url
                else:
                    print("=== 开始意图判断 ===")
                    # 根据意图处理查询（传递游戏名称）
                    query_result = await process_query_with_intent(keyword, game_name)
                    print(f"意图判断结果: {query_result}")
                    if not query_result:
                        print("意图判断失败")
                        return
                    
                    intent = query_result.get("intent")
                    print(f"意图类型: {intent}")
                    
                    if intent == "guide":
                        print("=== 显示攻略结果 ===")
                        # 查攻略 - 显示RAG结果
                        logger.info("显示攻略结果")
                        rag_result = query_result.get("result", {})
                        answer = rag_result.get("answer", "抱歉，没有找到相关攻略。")
                        
                        # 获取保存的窗口设置
                        settings = self.settings_mgr.get()
                        popup_settings = settings.get('popup', {})
                        geom = (
                            popup_settings.get('width', 800),
                            popup_settings.get('height', 600),
                            popup_settings.get('left', 100),
                            popup_settings.get('top', 100)
                        )
                        
                        # 创建结果显示窗口
                        self._show_guide_result(answer, geom)
                        return
                    else:
                        print("=== 开始Wiki搜索 ===")
                        # 查wiki - 获取目标域名
                        if base_url.startswith(('http://', 'https://')):
                            from urllib.parse import urlparse
                            domain = urlparse(base_url).hostname or ''
                        else:
                            # 如果没有协议前缀，直接使用base_url作为域名
                            domain = base_url.split('/')[0]  # 移除路径部分
                        
                        # 根据意图选择搜索关键词
                        intent = query_result.get("intent", "wiki")
                        if intent == "wiki":
                            # wiki意图：使用原始查询（保持用户真实意图）
                            search_keyword = keyword
                        else:
                            # guide意图：使用重写后的查询
                            search_keyword = query_result.get("rewritten_query", keyword)
                        
                        search_optimization = query_result.get("search_optimization", "hybrid")
                        
                        logger.info(f"原始关键词: {keyword}")
                        logger.info(f"意图类型: {intent}")
                        logger.info(f"搜索关键词: {search_keyword}")
                        logger.info(f"搜索优化: {search_optimization}")
                        logger.info(f"目标域名: {domain}")
                        print(f"原始关键词: {keyword}")
                        print(f"意图类型: {intent}")
                        print(f"搜索关键词: {search_keyword}")
                        print(f"搜索优化: {search_optimization}")
                        print(f"目标域名: {domain}")
                        
                        # 获取保存的窗口设置
                        settings = self.settings_mgr.get()
                        popup_settings = settings.get('popup', {})
                        geom = (
                            popup_settings.get('width', 800),
                            popup_settings.get('height', 600),
                            popup_settings.get('left', 100),
                            popup_settings.get('top', 100)
                        )
                        print(f"窗口几何设置: {geom}")
                        
                        # 如果已有窗口，先关闭
                        if self._current_window:
                            print("关闭现有窗口")
                            self._current_window.destroy()
                            self._current_window = None
                        
                        # 1. 首先打开wiki窗口显示加载动画
                        print("=== 打开wiki窗口 ===")
                        logger.info("打开wiki窗口显示加载动画")
                        self._open_wiki_window(geom=geom)
                        print("wiki窗口已创建")
                        
                        # 2. 尝试DuckDuckGo快速链接
                        print("=== 尝试DuckDuckGo快速链接 ===")
                        logger.info("尝试DuckDuckGo快速链接...")
                        duckduckgo_success = self._try_duckduckgo_quick_link(search_keyword, domain, geom)
                        print(f"DuckDuckGo快速链接结果: {duckduckgo_success}")
                        
                        if duckduckgo_success:
                            print("=== DuckDuckGo成功 ===")
                            logger.info("DuckDuckGo快速链接成功！")
                            # 记录最后访问的URL
                            self._last_url = f"duckduckgo_success_{search_keyword}"
                        else:
                            print("=== 回退到Bing搜索 ===")
                            logger.info("DuckDuckGo快速链接失败，回退到Bing搜索")
                            # 3. 如果DuckDuckGo失败，回退到原来的Bing搜索逻辑
                            self._fallback_to_bing_search(search_keyword, domain, geom)
                            # 记录Bing搜索URL
                            import urllib.parse
                            import uuid
                            search_query = f"{search_keyword} site:{domain}"
                            encoded_query = urllib.parse.quote(search_query)
                            random_id = str(uuid.uuid4()).replace('-', '').upper()[:16]
                            self._last_url = f"https://www.bing.com/search?q={encoded_query}&rdr=1&rdrig={random_id}"
                        
                        print("=== webview窗口已准备就绪 ===")
                        # 注意：webview.start() 将在主线程中调用
            else:
                print("=== 不需要搜索，直接打开URL ===")
                url = base_url
                # 记录最后访问的URL
                self._last_url = url

                # 获取保存的窗口设置
                settings = self.settings_mgr.get()
                popup_settings = settings.get('popup', {})
                geom = (
                    popup_settings.get('width', 800),
                    popup_settings.get('height', 600),
                    popup_settings.get('left', 100),
                    popup_settings.get('top', 100)
                )

                # 如果已有窗口，先关闭
                if self._current_window:
                    self._current_window.destroy()
                    self._current_window = None

                # 不需要搜索，直接创建wiki窗口加载目标URL
                logger.info("直接创建wiki窗口加载目标URL")
                self._current_window = webview.create_window(
                    'Wiki',
                    url,
                    width=geom[0], height=geom[1], x=geom[2], y=geom[3],
                    resizable=True, text_select=True,
                    confirm_close=False,
                    on_top=True,
                    js_api=self
                )
                # 关窗时保存几何
                self._current_window.events.closing += lambda: self._save_geometry(self._current_window)

            print("=== webview窗口已准备就绪 ===")
            # 注意：webview.start() 将在主线程中调用
            print("=== 热键处理完成 ===")

        except Exception as e:
            print(f"=== 热键处理失败: {e} ===")
            logger.error(f"热键处理失败: {e}", exc_info=True) 