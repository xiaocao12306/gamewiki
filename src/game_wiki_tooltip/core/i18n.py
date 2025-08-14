"""
Internationalization (i18n) support for GameWiki Assistant.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from src.game_wiki_tooltip.core.utils import APPDATA_DIR

logger = logging.getLogger(__name__)

# 支持的语言
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'zh': '中文'
}

# 默认语言
DEFAULT_LANGUAGE = 'en'


class TranslationManager:
    """翻译管理器，负责加载和管理多语言翻译"""
    
    def __init__(self, language: str = DEFAULT_LANGUAGE):
        self.current_language = language
        self.translations: Dict[str, Dict[str, str]] = {}
        self.fallback_translations: Dict[str, str] = {}
        
        # 创建翻译文件目录
        self.translations_dir = APPDATA_DIR / "translations"
        self.translations_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载翻译文件
        self._load_translations()
    
    def _load_translations(self):
        """加载翻译文件，支持开发阶段的自动更新"""
        try:
            # 获取代码中定义的最新翻译
            latest_defaults = self._create_default_translations()
            
            # 加载默认语言（英语）
            default_file = self._get_translation_file(DEFAULT_LANGUAGE)
            
            if default_file.exists():
                # 读取现有文件
                with open(default_file, 'r', encoding='utf-8') as f:
                    existing_translations = json.load(f)
                
                # 检查是否需要更新
                updated = False
                
                # 添加新键和更新现有键的值
                for key, value in latest_defaults.items():
                    if key not in existing_translations:
                        existing_translations[key] = value
                        logger.info(f"Added new translation key: {key}")
                        updated = True
                    elif existing_translations[key] != value:
                        # 检测到现有键的值发生变化，更新它
                        existing_translations[key] = value
                        logger.info(f"Updated translation value for key: {key}")
                        updated = True
                
                # 移除已删除的键
                keys_to_remove = []
                for key in existing_translations:
                    if key not in latest_defaults:
                        keys_to_remove.append(key)
                        logger.info(f"Removed obsolete translation key: {key}")
                        updated = True
                
                for key in keys_to_remove:
                    del existing_translations[key]
                
                # 如果有更新，保存文件
                if updated:
                    self._save_translation_file(DEFAULT_LANGUAGE, existing_translations)
                    logger.info(f"Updated translation file: {default_file}")
                
                self.fallback_translations = existing_translations
            else:
                # 首次运行，创建新文件
                self.fallback_translations = latest_defaults
                self._save_translation_file(DEFAULT_LANGUAGE, self.fallback_translations)
                logger.info(f"Created new translation file: {default_file}")
            
            # 处理当前语言（如中文）
            if self.current_language != DEFAULT_LANGUAGE:
                current_file = self._get_translation_file(self.current_language)
                latest_current = self._create_language_translations(self.current_language)
                
                if current_file.exists():
                    # 同样的更新逻辑
                    with open(current_file, 'r', encoding='utf-8') as f:
                        existing_current = json.load(f)
                    
                    updated = False
                    for key, value in latest_current.items():
                        if key not in existing_current:
                            existing_current[key] = value
                            logger.info(f"Added new translation key to {self.current_language}: {key}")
                            updated = True
                        elif existing_current[key] != value:
                            # 检测到现有键的值发生变化，更新它
                            existing_current[key] = value
                            logger.info(f"Updated translation value for key in {self.current_language}: {key}")
                            updated = True
                    
                    # 移除过时的键
                    keys_to_remove = [k for k in existing_current if k not in latest_current]
                    for key in keys_to_remove:
                        del existing_current[key]
                        logger.info(f"Removed obsolete translation key from {self.current_language}: {key}")
                        updated = True
                    
                    if updated:
                        self._save_translation_file(self.current_language, existing_current)
                        logger.info(f"Updated translation file: {current_file}")
                    
                    self.translations[self.current_language] = existing_current
                else:
                    self.translations[self.current_language] = latest_current
                    self._save_translation_file(self.current_language, latest_current)
                    logger.info(f"Created new translation file: {current_file}")
                    
        except Exception as e:
            logger.error(f"Failed to load translations: {e}")
            # 降级到内存中的翻译
            self.fallback_translations = self._create_default_translations()
            if self.current_language != DEFAULT_LANGUAGE:
                self.translations[self.current_language] = self._create_language_translations(self.current_language)
    
    def _get_translation_file(self, language: str) -> Path:
        """获取翻译文件路径"""
        return self.translations_dir / f"{language}.json"
    
    def _save_translation_file(self, language: str, translations: Dict[str, str]):
        """保存翻译文件"""
        try:
            file_path = self._get_translation_file(language)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(translations, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save translation file for {language}: {e}")
    
    def _create_default_translations(self) -> Dict[str, str]:
        """创建默认的英语翻译"""
        return {
            # Settings window
            "settings_title": "GameWiki Assistant Settings",
            "hotkey_tab": "Hotkey Settings",
            "api_tab": "API Configuration",
            "language_tab": "Language Settings",
            "wiki_tab": "Wiki",
            "apply_button": "Save & Apply",
            "cancel_button": "Cancel",
            
            # Hotkey settings
            "hotkey_title": "Global Hotkey Settings",
            "modifiers_label": "Modifiers:",
            "main_key_label": "Main Key:",
            "hotkey_tips": "Tips:\n"
                         "• Press the hotkey in-game to invoke the AI assistant\n"
                         "• Some games may not support certain hotkey combinations\n"
                         "• Recommended: Ctrl + Letter key combinations",
            
            # API settings
            "api_title": "API Key Configuration",
            "google_api_label": "Google (Gemini) API Key:",
                "google_api_placeholder": "Enter your Gemini API key",
    "google_api_help": "Get Gemini API Key",
            "jina_api_label": "Jina API Key (Optional):",
            "jina_api_placeholder": "Enter your Jina API key",
            "jina_api_help": "Get Jina API Key",
            "api_tips": "Notes:\n"
                       "• Gemini API Key is required for AI conversations and content generation\n"
                       "• API keys are securely stored in local configuration files",
            
            # Language settings
            "language_title": "Language Settings",
            "language_label": "Interface Language:",
            "language_tips": "Notes:\n"
                           "• Changing language will affect the entire application interface\n"
                           "• Wiki sources will be adjusted according to the selected language\n"
                           "• Requires restart to fully apply language changes",
            
            # Audio settings
            "audio_title": "Audio Settings",
            "audio_input_device_label": "Audio Input Device:",
            "refresh_devices_button": "Refresh Devices",
            "refreshing_devices": "Refreshing...",
            "refresh_cooldown": "Too fast! Wait...",
            "refresh_complete": "Refreshed!",
            
            # Wiki settings
            "wiki_title": "Wiki URL Configuration",
            "wiki_description": "When searching for wiki content, we restrict the search to these wiki sites to prevent interference from other content.",
            "wiki_search_label": "Search:",
            "wiki_search_placeholder": "e.g., civ",
            "wiki_edit_button": "Edit",
            "wiki_reset_button": "Reset to Default",
            "wiki_tips": "Tip: Edit the base URL for each game to use your preferred wiki source.",
            "wiki_tips_with_warning": "Tip: Edit the base URL for each game to use your preferred wiki source.<br><br><b>Important: The game name must exactly match the game window title for wiki search to work!</b>",
            "wiki_select_game": "Please select a game to edit",
            "wiki_select_game_remove": "Please select a game to remove",
            "wiki_edit_title": "Edit Wiki URL",
            "wiki_edit_prompt": "Enter the new wiki URL for {game}:",
            "wiki_add_title": "Add Wiki Entry",
            "wiki_add_game_prompt": "Enter the exact game window title:",
            "wiki_add_url_prompt": "Enter the wiki URL for {game}:",
            "wiki_game_exists": "This game already exists in the list",
            "wiki_remove_confirm_title": "Confirm Remove",
            "wiki_remove_confirm_message": "Are you sure you want to remove the wiki entry for {game}?",
            "wiki_reset_confirm_title": "Confirm Reset",
            "wiki_reset_confirm_message": "Are you sure you want to reset all wiki URLs to their default values?",
            "wiki_reset_success": "Wiki URLs have been reset to default values",
            "wiki_reset_failed": "Failed to reset wiki URLs",
            "wiki_save_failed": "Failed to save wiki URL changes",
            
            # Tray icon
            "tray_settings": "Settings",
            "tray_exit": "Exit",
            "tray_tooltip": "GameWiki Assistant",
            "tray_show_overlay": "Show Overlay",
            "tray_hide_overlay": "Hide Overlay",
            
            # Right-click menu options
            "menu_hide_overlay": "Hide Overlay",
            "menu_minimize_to_mini": "Minimize to Mini Window",
            "menu_hide_to_tray": "Hide to Tray",
            
            # Notifications
            "hotkey_registered": "Started, press {hotkey} to invoke assistant",
            "hotkey_failed": "Started, but hotkey registration failed. Please configure hotkey in settings or run as administrator.",
            "settings_applied": "Settings Applied",
            "hotkey_updated": "Hotkey updated to {hotkey}",
            
            # Validation messages
            "validation_modifier_required": "Please select at least one modifier key",
            "validation_api_key_required": "Please enter Gemini API Key, or set GEMINI_API_KEY environment variable",
            "validation_settings_saved": "Settings saved and applied successfully",
            "validation_setup_incomplete": "Setup incomplete",
            "validation_api_key_needed": "Gemini API Key is required to use this program.\n\n"
                                       "Please configure API key in settings window, or set GEMINI_API_KEY environment variable.",
            
            # Welcome message
            "welcome_title": "🎮 Welcome to GameWiki Assistant!",
            "welcome_features": "💡 **Features:**",
            "welcome_wiki_search": "• **Wiki Search** - Quick access to website Wiki",
            "welcome_ai_guide": "• **AI Guide BETA** - Haven't support context memory; ONLY support Helldivers2/Elden Ring/Don't Starve Together/Civilization VI so far; AI could make mistakes, check the attached video link for validity.)",
            "welcome_examples": "🎯 **Recommended Query Examples for AI Guide:**",
            "welcome_helldivers": "• Helldivers 2: `best warbond to buy first` / `low level loadout`",
            "welcome_eldenring": "• Elden Ring: `boss strategies` / `equipment recommendations`",
            "welcome_dst": "• Don't Starve Together: `What to do on day 1` / `character recommendation`",
            "welcome_usage": "📝 **Usage Tips:**",
            "welcome_usage_desc": "Simply type your question, and the system will automatically determine whether to use Wiki search or AI guide functionality.",
            
            # Common
            "ok": "OK",
            "yes": "Yes",
            "no": "No",
            "warning": "Warning",
            "error": "Error",
            "info": "Information",
            "success": "Success",
            
            # Video sources
            "video_sources_label": "Sources:",
            
            # RAG System Status Messages
            "rag_initializing": "🚀 Game guide system is initializing, please wait...",
            "rag_init_complete": "✅ RAG engine initialization complete",
            "rag_init_failed": "❌ RAG engine initialization failed",
            "rag_error_occurred": "Guide query system error",
            "rag_vector_store_error": "Vector store unavailable",
            "rag_bm25_error": "BM25 search function unavailable",
            
            # BM25 Index Error Messages
            
            # Status Messages (for chat transitions)
            "status_query_received": "🔍 Analyzing your question...",
            "status_db_searching": "📚 Searching knowledge base...",
            "status_ai_summarizing": "📝 Generating intelligent summary...",
            "status_completed": "✨ Response generation completed",
            "status_wiki_searching": "Searching Wiki page...",
            "status_wiki_found": "Found Wiki page:",
            "status_guide_searching": "Searching for information...",
            "status_guide_generating": "Generating guide content...",
            "status_error_not_found": "Sorry, no relevant information found",
            "status_error_timeout": "Request timeout, please try again later",
            
            # Search mode menu
            "search_mode_auto": "Auto search",
            "search_mode_wiki": "Wiki search",
            "search_mode_ai": "AI search",
            "search_mode_url": "Go to URL",
            
            # Game Task Flow Buttons and Content
            "dst_task_button": "📋 DST Task Flow",
            "helldiver2_task_button": "📋 Helldivers 2 Guide",
            "eldenring_task_button": "📋 Elden Ring Guide",
            "dst_task_flow_title": "DST Task Flow",
            "dst_survival_guide_title": "Don't Starve Together - Survival Guide",
            "dst_technical_error": "Unable to display the complete task flow page due to technical issues.",
            "dst_recommended_resources": "Recommended resources:",
            "dst_official_wiki": "Official Don't Starve Wiki",
            "civ6_task_button": "📋 Civ VI Guide",
            "dst_basic_survival": "Basic Survival: Collect twigs and flint to craft tools",
            "dst_food_gathering": "Food Gathering: Pick berries and carrots", 
            "dst_base_building": "Base Building: Choose a good location for your campfire",
            "dst_winter_preparation": "Winter Preparation: Stock up on food and fuel",
            "bm25_load_failed": "Failed to load enhanced BM25 index: {error}",
            "bm25_index_missing": "BM25 index directory not found and cannot rebuild: {path}",
            "bm25_package_unavailable": "BM25 index loading failed: bm25s package unavailable - {error}",
            "bm25_save_failed": "Failed to save simplified BM25 index: {error}",
            "bm25_stats_failed": "Failed to get BM25 statistics: bm25s package unavailable",
            "bm25_search_failed": "BM25 search failed: bm25s package not available",
            "bm25_build_failed": "BM25 index build failed: bm25s package not available",
            "bm25_build_error": "Enhanced BM25 index build failed: {error}",
            "bm25_search_not_initialized": "BM25 search failed: index not initialized, please call build_index() method first",
            "bm25_save_not_available": "BM25 index save failed: bm25s package unavailable",
            "bm25_search_execution_failed": "BM25 search execution failed: {error}",
            "enhanced_bm25_load_failed": "Enhanced BM25 index loading failed: {error}",
            "bm25_index_build_failed": "BM25 index build failed: {error}",
            "enhanced_bm25_index_build_failed": "Enhanced BM25 index build failed: {error}",
            
            # Game detection messages
            "game_not_detected": "No game detected. Please trigger the hotkey while in a game, or add the game to settings if it's not in the default list.",
            "game_not_supported": "The current window '{window}' is not a supported game. Please switch to a supported game or add it in settings."
        }
    
    def _create_language_translations(self, language: str) -> Dict[str, str]:
        """为特定语言创建翻译"""
        if language == 'zh':
            return {
                # Settings window
                "settings_title": "GameWiki Assistant 设置",
                "hotkey_tab": "热键设置",
                "api_tab": "API配置",
                "language_tab": "语言设置",
                "wiki_tab": "Wiki",
                "apply_button": "保存并应用",
                "cancel_button": "取消",
                
                # Hotkey settings
                "hotkey_title": "全局热键设置",
                "modifiers_label": "修饰键：",
                "main_key_label": "主键：",
                "hotkey_tips": "提示：\n"
                             "• 在游戏中按下热键即可呼出AI助手\n"
                             "• 部分游戏可能不支持某些热键组合，请选择合适的组合\n"
                             "• 建议使用 Ctrl + 字母键 的组合",
                
                # API settings
                "api_title": "API 密钥配置",
                "google_api_label": "Google (Gemini) API Key:",
                    "google_api_placeholder": "输入您的 Gemini API 密钥",
    "google_api_help": "获取 Gemini API Key",
                "jina_api_label": "Jina API Key (可选):",
                "jina_api_placeholder": "输入您的 Jina API 密钥",
                "jina_api_help": "获取 Jina API Key",
                "api_tips": "说明：\n"
                           "• Gemini API Key 用于AI对话和内容生成\n"
                           "• API密钥将安全保存在本地配置文件中",
                
                # Language settings
                "language_title": "语言设置",
                "language_label": "界面语言：",
                "language_tips": "说明：\n"
                               "• 更改语言将影响整个应用程序界面\n"
                               "• Wiki源将根据所选语言进行调整\n"
                               "• 需要重启程序以完全应用语言更改",
                
                # Audio settings
                "audio_title": "音频设置",
                "audio_input_device_label": "音频输入设备：",
                "refresh_devices_button": "刷新设备",
                "refreshing_devices": "正在刷新...",
                "refresh_cooldown": "太快了！请稍等...",
                "refresh_complete": "刷新完成！",
                
                # Wiki settings
                "wiki_title": "Wiki网址配置",
                "wiki_description": "在搜索wiki内容时，我们会将搜索的网站限制在这个wiki站点中，防止其他内容的影响。",
                "wiki_search_label": "搜索：",
                "wiki_search_placeholder": "例如：civ",
                "wiki_edit_button": "编辑",
                "wiki_reset_button": "重置为默认",
                "wiki_tips": "提示：编辑每个游戏的基础网址以使用您偏好的wiki源。",
                "wiki_tips_with_warning": "提示：编辑每个游戏的基础网址以使用您偏好的wiki源。<br><br><b>重要提示：游戏名称必须与游戏窗口标题完全一致，wiki搜索才能正常工作！</b>",
                "wiki_select_game": "请选择要编辑的游戏",
                "wiki_select_game_remove": "请选择要删除的游戏",
                "wiki_edit_title": "编辑Wiki网址",
                "wiki_edit_prompt": "输入{game}的新wiki网址：",
                "wiki_add_title": "添加Wiki条目",
                "wiki_add_game_prompt": "输入准确的游戏窗口标题：",
                "wiki_add_url_prompt": "输入{game}的wiki网址：",
                "wiki_game_exists": "该游戏已存在于列表中",
                "wiki_remove_confirm_title": "确认删除",
                "wiki_remove_confirm_message": "您确定要删除{game}的wiki条目吗？",
                "wiki_reset_confirm_title": "确认重置",
                "wiki_reset_confirm_message": "您确定要将所有wiki网址重置为默认值吗？",
                "wiki_reset_success": "Wiki网址已重置为默认值",
                "wiki_reset_failed": "重置wiki网址失败",
                "wiki_save_failed": "保存wiki网址更改失败",
                
                # Tray icon
                "tray_settings": "设置",
                "tray_exit": "退出",
                "tray_tooltip": "GameWiki Assistant",
                "tray_show_overlay": "显示悬浮窗",
                "tray_hide_overlay": "隐藏悬浮窗",
                
                # 右键菜单选项
                "menu_hide_overlay": "隐藏悬浮窗",
                "menu_minimize_to_mini": "最小化到迷你窗口",
                "menu_hide_to_tray": "隐藏到托盘",
                
                # Notifications
                "hotkey_registered": "已启动，按 {hotkey} 呼出助手",
                "hotkey_failed": "已启动，但热键注册失败。请在设置中配置热键或以管理员身份运行。",
                "settings_applied": "设置已应用",
                "hotkey_updated": "热键已更新为 {hotkey}",
                
                # Validation messages
                "validation_modifier_required": "请至少选择一个修饰键",
                "validation_api_key_required": "请输入 Gemini API Key，或在环境变量中设置 GEMINI_API_KEY",
                "validation_settings_saved": "设置已保存并应用",
                "validation_setup_incomplete": "设置未完成",
                "validation_api_key_needed": "需要配置Gemini API密钥才能使用本程序。\n\n"
                                           "请在设置窗口中配置API密钥，或设置环境变量 GEMINI_API_KEY。",

                # Welcome message
                "welcome_title": "🎮 欢迎使用GameWiki智能助手！",
                "welcome_features": "💡 **功能介绍：**",
                "welcome_wiki_search": "• **Wiki搜索** - 快速查找游戏wiki资料",
                "welcome_ai_guide": "• **AI攻略BETA** - 智能游戏攻略问答（需要配置API密钥；目前仅支持饥荒/文明6/艾尔登法环/地狱潜兵2）",
                "welcome_examples": "🎯 **推荐查询示例：**",
                "welcome_helldivers": "• 地狱潜兵2：`虫族配装推荐` / `火焰武器搭配`",
                "welcome_eldenring": "• 艾尔登法环：`Boss攻略` / `装备推荐`",
                "welcome_stardew": "• 星露谷物语：`农场布局` / `好感度攻略`",
                "welcome_dst": "• 饥荒联机版：`生存技巧` / `角色选择`",
                "welcome_usage": "📝 **使用提示：**",
                "welcome_usage_desc": "直接输入您的问题，系统会自动判断使用Wiki搜索还是AI攻略功能。",
                
                # Common
                "ok": "确定",
                "yes": "是",
                "no": "否",
                "warning": "警告",
                "error": "错误",
                "info": "信息",
                "success": "成功",
                
                # Status Messages (for chat transitions)
                "status_query_received": "🔍 正在分析您的问题...",
                "status_db_searching": "📚 检索相关知识库...",
                "status_ai_summarizing": "📝 智能总结生成中...",
                "status_completed": "✨ 回答生成完成",
                "status_wiki_searching": "正在搜索Wiki页面...",
                "status_wiki_found": "找到Wiki页面：",
                "status_guide_searching": "正在搜索相关信息...",
                "status_guide_generating": "正在生成攻略内容...",
                "status_error_not_found": "抱歉，未找到相关信息",
                "status_error_timeout": "请求超时，请稍后重试",
                
                # Search mode menu
                "search_mode_auto": "自动搜索",
                "search_mode_wiki": "Wiki 搜索",
                "search_mode_ai": "AI 搜索",
                "search_mode_url": "访问网址",
                
                # Game Task Flow Buttons and Content
                "dst_task_button": "📋 DST任务流程",
                "helldiver2_task_button": "📋 地狱潜兵2攻略",
                "eldenring_task_button": "📋 艾尔登法环攻略",
                "dst_task_flow_title": "DST 任务流程",
                "dst_survival_guide_title": "饥荒联机版 - 生存指南",
                "dst_technical_error": "由于技术问题，无法显示完整的任务流程页面。",
                "dst_recommended_resources": "建议访问以下资源：",
                "dst_official_wiki": "饥荒官方Wiki",
                "civ6_task_button": "📋 文明6攻略",
                "dst_basic_survival": "基础生存：收集树枝、燧石制作工具",
                "dst_food_gathering": "食物获取：采集浆果、胡萝卜",
                "dst_base_building": "建造基地：选择好位置建立营火",
                "dst_winter_preparation": "过冬准备：储备食物和燃料",
                
                # Video sources
                "video_sources_label": "信息来源：",
                
                # RAG System Status Messages
                "rag_initializing": "🚀 游戏攻略系统正在初始化中，请稍候...",
                "rag_init_complete": "✅ RAG引擎初始化完成",
                "rag_init_failed": "❌ RAG引擎初始化失败",
                "rag_error_occurred": "攻略查询系统出现错误",
                "rag_vector_store_error": "向量库不可用",
                "rag_bm25_error": "BM25搜索功能不可用",
                
                # BM25 索引错误信息
                "bm25_load_failed": "加载增强BM25索引失败: {error}",
                "bm25_index_missing": "无法找到BM25索引目录且无法重建: {path}",
                "bm25_package_unavailable": "BM25索引加载失败: bm25s包不可用 - {error}",
                "bm25_save_failed": "保存简化BM25索引失败: {error}",
                "bm25_stats_failed": "获取BM25统计信息失败: bm25s包不可用",
                "bm25_search_failed": "BM25搜索失败: bm25s包不可用",
                "bm25_build_failed": "BM25索引构建失败: bm25s包不可用",
                "bm25_build_error": "增强BM25索引构建失败: {error}",
                "bm25_search_not_initialized": "BM25搜索失败: 索引未初始化，请先调用build_index()方法",
                "bm25_save_not_available": "BM25索引保存失败: bm25s包不可用",
                "bm25_search_execution_failed": "BM25搜索执行失败: {error}",
                "enhanced_bm25_load_failed": "增强BM25索引加载失败: {error}",
                "bm25_index_build_failed": "构建BM25索引失败: {error}",
                "enhanced_bm25_index_build_failed": "构建增强BM25索引失败: {error}",
                
                # 游戏检测消息
                "game_not_detected": "未检测到游戏。请在游戏中触发热键，或如果游戏不在默认列表中，请在设置中添加。",
                "game_not_supported": "当前窗口 '{window}' 不是支持的游戏。请切换到支持的游戏或在设置中添加。"
            }
        else:
            # 对于其他语言，返回英语翻译作为基础
            return self.fallback_translations.copy()
    
    def t(self, key: str, **kwargs) -> str:
        """翻译函数，根据key获取翻译文本"""
        # 首先尝试从当前语言获取翻译
        current_translations = self.translations.get(self.current_language, {})
        text = current_translations.get(key)
        
        # 如果当前语言没有翻译，使用fallback
        if text is None:
            text = self.fallback_translations.get(key, key)
        
        # 支持字符串格式化
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing format parameter for key '{key}': {e}")
        
        return text
    
    def set_language(self, language: str):
        """设置当前语言"""
        if language not in SUPPORTED_LANGUAGES:
            logger.warning(f"Unsupported language: {language}")
            return
        
        self.current_language = language
        self._load_translations()
    
    def get_current_language(self) -> str:
        """获取当前语言"""
        return self.current_language
    
    def get_supported_languages(self) -> Dict[str, str]:
        """获取支持的语言列表"""
        return SUPPORTED_LANGUAGES.copy()


# 全局翻译管理器实例
_translation_manager: Optional[TranslationManager] = None


def init_translations(language: str = DEFAULT_LANGUAGE):
    """初始化翻译系统"""
    global _translation_manager
    _translation_manager = TranslationManager(language)


def get_translation_manager() -> TranslationManager:
    """获取翻译管理器实例"""
    global _translation_manager
    if _translation_manager is None:
        init_translations()
    return _translation_manager


def t(key: str, **kwargs) -> str:
    """翻译函数的全局快捷方式"""
    return get_translation_manager().t(key, **kwargs)


def set_language(language: str):
    """设置当前语言的全局快捷方式"""
    get_translation_manager().set_language(language)


def get_current_language() -> str:
    """获取当前语言的全局快捷方式"""
    return get_translation_manager().get_current_language()


def get_supported_languages() -> Dict[str, str]:
    """获取支持的语言列表的全局快捷方式"""
    return get_translation_manager().get_supported_languages() 