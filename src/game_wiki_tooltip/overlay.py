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
        self._wiki_window = None  # 新增：wiki窗口
        self._search_window = None  # 新增：搜索窗口
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

    def _open_wiki_window(self, geom=None):
        """创建wiki窗口显示加载动画"""
        w, h, x, y = (geom or (800, 600, 100, 100))
        
        # 创建临时HTML文件用于加载动画
        import tempfile
        import os
        
        temp_html = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8')
        temp_html.write(self._create_loading_html())
        temp_html.close()
        
        self._wiki_window = webview.create_window(
            'Wiki',
            url=f"file://{temp_html.name}",
            width=w, height=h, x=x, y=y,
            resizable=True, text_select=True,
            confirm_close=False,
            js_api=self
        )
        
        # 关窗时保存几何并清理临时文件
        def on_closing():
            self._save_geometry(self._wiki_window)
            try:
                os.unlink(temp_html.name)
            except:
                pass
        
        self._wiki_window.events.closing += on_closing
        return self._wiki_window

    def _open_new_window(self, url: str, geom=None):
        """直接创建指向 url 的 WebView，并保存到 self._current_window"""
        w, h, x, y = (geom or (800, 600, 100, 100))
        self._current_window = webview.create_window(
            'Wiki',
            url=url,
            width=w, height=h, x=x, y=y,
            resizable=True, text_select=True,
            confirm_close=False,
            js_api=self
        )
        # 关窗时保存几何
        self._current_window.events.closing += \
            lambda: self._save_geometry(self._current_window)

    def found_valid_link(self, url: str):
        """JS 找到有效链接后回调"""
        logger.info(f"JavaScript找到有效链接: {url}")

        # 关闭隐藏的搜索窗口
        if self._search_window:
            try:
                self._search_window.destroy()
                logger.info("已关闭隐藏的搜索窗口")
            except Exception as e:
                logger.warning(f"关闭搜索窗口失败: {e}")
            finally:
                self._search_window = None

        # 在wiki窗口中加载目标URL
        if self._wiki_window:
            try:
                logger.info(f"在wiki窗口中加载URL: {url}")
                self._wiki_window.load_url(url)
                # 将wiki窗口设为主窗口
                self._current_window = self._wiki_window
                self._wiki_window = None
                return "ok-new"
            except Exception as e:
                logger.error(f"在wiki窗口中加载URL失败: {e}")
                return f"error: {e}"
        else:
            logger.error("wiki窗口不存在")
            return "error: no wiki window"

    def open_url(self, url: str):
        """在当前浮窗中加载目标 URL（供 JS 调用）"""
        logger.info(f"JavaScript 请求打开 URL: {url}")
        if self._current_window:
            # 和 destroy/newWindow 相比，load_url 不会重置大小、位置
            self._current_window.load_url(url)
        elif self._wiki_window:
            # 如果在wiki窗口中，也在wiki窗口中加载
            self._wiki_window.load_url(url)
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

    async def on_hotkey(self):
        """Handle hotkey press."""
        try:
            # 获取当前窗口标题
            current_title = get_foreground_title()
            logger.info(f"当前窗口标题: {current_title}")

            # 查找游戏配置
            game_config = self.game_cfg_mgr.for_title(current_title)
            if not game_config:
                logger.warning(f"未找到游戏配置: {current_title}")
                return

            logger.info(f"找到的游戏配置: {game_config}")

            # 获取基础URL和搜索需求
            base_url = game_config.BaseUrl
            needs_search = game_config.NeedsSearch

            logger.info(f"游戏配置: base_url={base_url}, needs_search={needs_search}")

            
            # 如果需要搜索，显示搜索框并进行意图判断
            if needs_search:
                logger.info("显示搜索框并进行意图判断")
                # 先获取用户输入
                keyword = await ask_keyword()
                if not keyword:
                    return

                if keyword == "<<LAST>>":
                    if self._current_window:
                        self._current_window.show()
                        return
                    if not self._last_url:
                        logger.warning("没有上次搜索记录")
                        return
                    url = self._last_url
                else:
                    # 根据意图处理查询
                    query_result = await process_query_with_intent(keyword)
                    if not query_result:
                        return
                    
                    intent = query_result.get("intent")
                    
                    if intent == "guide":
                        # 查攻略 - 显示RAG结果
                        logger.info("显示攻略结果")
                        rag_result = query_result.get("result", {})
                        answer = rag_result.get("answer", "抱歉，没有找到相关攻略。")
                        
                        # 创建结果显示窗口
                        self._show_guide_result(answer, geom)
                        return
                    else:
                        # 查wiki - 构建Bing搜索URL
                        import urllib.parse
                        import uuid
                        
                        # 获取目标域名
                        if base_url.startswith(('http://', 'https://')):
                            from urllib.parse import urlparse
                            domain = urlparse(base_url).hostname or ''
                        else:
                            # 如果没有协议前缀，直接使用base_url作为域名
                            domain = base_url.split('/')[0]  # 移除路径部分
                        
                        # 构建搜索查询：关键词 site:域名
                        search_query = f"{keyword} site:{domain}"
                        encoded_query = urllib.parse.quote(search_query)
                        
                        # 生成随机ID
                        random_id = str(uuid.uuid4()).replace('-', '').upper()[:16]
                        
                        # 构建完整的Bing搜索URL
                        url = f"https://www.bing.com/search?q={encoded_query}&rdr=1&rdrig={random_id}"
                        
                        logger.info(f"构建Bing搜索URL: {url}")
                        logger.info(f"搜索关键词: {keyword}")
                        logger.info(f"目标域名: {domain}")
            else:
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


            # 如果需要搜索，使用双窗口模式
            if needs_search:
                # 1. 首先打开wiki窗口显示加载动画
                logger.info("打开wiki窗口显示加载动画")
                self._open_wiki_window(geom)

                # 读取并准备JavaScript代码，动态替换目标域名
                try:
                    # 获取目标域名
                    from urllib.parse import urlparse
                    
                    # 处理没有协议前缀的域名
                    if base_url.startswith(('http://', 'https://')):
                        domain = urlparse(base_url).hostname or ''
                    else:
                        # 如果没有协议前缀，直接使用base_url作为域名
                        domain = base_url.split('/')[0]  # 移除路径部分
                    
                    logger.info(f"目标域名: {domain}")
                    
                    # 读取JavaScript模板文件
                    js_file_path = pathlib.Path(__file__).parent / "auto_click.js"
                    with open(js_file_path, 'r', encoding='utf-8') as f:
                        auto_click_js = f.read().replace('{{DOMAIN}}', domain)
                        
                    logger.info("成功加载JavaScript模板")
                except Exception as e:
                    logger.error(f"加载JavaScript模板失败: {e}")
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
                
                # 3. 创建隐藏的搜索窗口
                logger.info("创建搜索窗口")
                self._search_window = webview.create_window(
                    'Search',
                    url,
                    width=800, height=600, x=100, y=100,  
                    resizable=False, text_select=True,
                    confirm_close=False,
                    js_api=self
                )
                
                # 添加页面加载完成事件，注入自动点击脚本
                def on_loaded():
                    try:
                        # 获取当前页面URL
                        current_url = self._search_window.get_current_url()
                        logger.info(f"搜索页面加载完成，当前URL: {current_url}")
                        
                        # 检查是否已经注入过脚本，并且URL没有改变
                        if hasattr(self._search_window, '_script_injected') and hasattr(self._search_window, '_last_url'):
                            if self._search_window._last_url == current_url:
                                logger.info("脚本已注入且URL未改变，跳过")
                                return
                            else:
                                logger.info(f"URL已改变，重置注入标记。旧URL: {self._search_window._last_url}, 新URL: {current_url}")
                        
                        # 标记已注入并记录当前URL
                        self._search_window._script_injected = True
                        self._search_window._last_url = current_url
                        
                        # 只有当URL属于Bing搜索页时才注入脚本，避免无意义注入
                        if 'bing.com/search' in current_url:
                            logger.info("开始注入JavaScript代码...")
                            logger.info(f"JavaScript代码长度: {len(auto_click_js)} 字符")
                            
                            # 注入JavaScript代码
                            result = self._search_window.evaluate_js(auto_click_js)
                            logger.info(f"JavaScript注入结果: {result}")
                            logger.info("已注入自动点击脚本")
                            
                            # 验证脚本是否成功执行
                            try:
                                # 检查是否有js_api
                                api_check = self._search_window.evaluate_js("window.pywebview && window.pywebview.api ? 'API可用' : 'API不可用'")
                                logger.info(f"JS API检查: {api_check}")
                                
                                # 测试简单的JavaScript执行
                                test_result = self._search_window.evaluate_js("'JavaScript执行正常'")
                                logger.info(f"JavaScript测试: {test_result}")
                                
                                # 检查页面标题
                                title = self._search_window.evaluate_js("document.title")
                                logger.info(f"页面标题: {title}")
                                
                                # 检查是否有搜索结果
                                results_count = self._search_window.evaluate_js("document.querySelectorAll('#b_results li.b_algo').length")
                                logger.info(f"搜索结果数量: {results_count}")
                                
                            except Exception as e:
                                logger.warning(f"JavaScript验证失败: {e}")
                        else:
                            logger.info("当前页面不是Bing搜索页，跳过脚本注入")
                        
                    except Exception as e:
                        logger.error(f"注入JavaScript失败: {e}")
                        logger.error(f"错误详情: {e.__class__.__name__}: {str(e)}")
                
                # 监听页面加载完成事件
                self._search_window.events.loaded += on_loaded
            else:
                # 不需要搜索，直接创建wiki窗口加载目标URL
                logger.info("直接创建wiki窗口加载目标URL")
                self._current_window = webview.create_window(
                    'Wiki',
                    url,
                    width=geom[0], height=geom[1], x=geom[2], y=geom[3],
                    resizable=True, text_select=True,
                    confirm_close=False,
                    js_api=self
                )
                # 关窗时保存几何
                self._current_window.events.closing += lambda: self._save_geometry(self._current_window)

            # 启动窗口
            webview.start()

        except Exception as e:
            logger.error(f"热键处理失败: {e}", exc_info=True) 