"""
Minimal floating keyword prompt (semi-transparent, rounded search box).
Returns None / "<<LAST>>" / str(keyword)
"""

import asyncio
import logging
import tkinter as tk
from typing import Optional, Dict, Any

from src.game_wiki_tooltip.ai.intent.intent_classifier import classify_intent, get_intent_confidence
from src.game_wiki_tooltip.ai.rag_query import map_window_title_to_game_name
from src.game_wiki_tooltip.ai.trial_proto.game_aware_query_processor import process_game_aware_query

logger = logging.getLogger(__name__)

# ---------- helpers ----------------------------------------------------------
def _create_round_rect(cv: tk.Canvas, x1, y1, x2, y2, r=12, **kw):
    """Draw a rounded rectangle on `cv`; returns poly-id."""
    points = [
        x1+r, y1,
        x2-r, y1,
        x2,   y1,
        x2,   y1+r,
        x2,   y2-r,
        x2,   y2,
        x2-r, y2,
        x1+r, y2,
        x1,   y2,
        x1,   y2-r,
        x1,   y1+r,
        x1,   y1
    ]
    return cv.create_polygon(points, **kw, smooth=True)

# ---------- prompt window ----------------------------------------------------
class _Prompt(tk.Toplevel):
    SEARCH_ICON = "\uE721"  # Segoe MDL2 Assets 搜索图标
    _instance = None  # 类变量，用于跟踪当前实例

    def __init__(self, placeholder: str, on_done):
        # 如果已经存在实例，先销毁它
        if _Prompt._instance is not None:
            try:
                _Prompt._instance.destroy()
            except:
                pass
        _Prompt._instance = self

        super().__init__(bg="white")       # 白色→被设为全透
        self.on_done = on_done

        # 基本窗口属性 -------------------------------------------------------
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.9)
        self.attributes("-transparentcolor", "white")

        # 定位到屏幕中心 -------------------------------------------------------
        W, H = 520, 42          # 搜索栏尺寸
        BTN_H = 34
        scr_w, scr_h = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (scr_w - W) // 2, (scr_h - (H + BTN_H + 8)) // 2
        self.geometry(f"{W}x{H + BTN_H + 8}+{x}+{y}")

        # Canvas 画圆角搜索框 -------------------------------------------------
        cv = tk.Canvas(self, width=W, height=H, bg="white",
                       highlightthickness=0)
        cv.place(x=0, y=0)

        _create_round_rect(cv, 0, 0, W, H, r=16,
                           fill="#F5F5F5", outline="#DDDDDD")

        # 放大镜图标 ---------------------------------------------------------
        icon = cv.create_text(20, H//2, text=self.SEARCH_ICON,
                              font=("Segoe MDL2 Assets", 14),
                              fill="#000000")
        # 输入框 -------------------------------------------------------------
        self.entry = tk.Entry(self, bd=0, bg="#F5F5F5",
                              highlightthickness=0,
                              font=("Segoe UI", 12),
                              fg="#000000",
                              insertbackground="#000000")
        self.entry.place(x=40, y=10, width=W-60, height=H-20)
        self.entry.insert(0, placeholder)
        self.entry.select_range(0, tk.END)

        # 半透明按钮 ---------------------------------------------------------
        btn = tk.Button(self, text="打开上次搜索内容",
                        command=lambda: self._finish("<<LAST>>"),
                        font=("Segoe UI", 9),
                        relief="flat", bd=0,
                        bg="#F5F5F5", activebackground="#E0E0E0",
                        fg="#000000",
                        activeforeground="#000000")
        btn.place(x=(W-140)//2, y=H+8, width=140, height=BTN_H)

        # 事件绑定 -----------------------------------------------------------
        self.entry.bind("<Return>", lambda e: self._finish(self.entry.get()))
        self.entry.bind("<Escape>", lambda e: self._finish(None))
        self.entry.bind("<FocusOut>", self._on_focus_out)

        # 确保窗口显示并立即获得焦点
        self.deiconify()
        self.lift()
        self.focus_force()
        self.entry.focus_set()
        
        # 使用after_idle确保在窗口完全显示后设置焦点
        self.after_idle(lambda: self.entry.focus_set())
        
        logger.info("浮动搜索栏已创建")

    # -------------------------------------------------------------------------
    def _finish(self, val):
        logger.info("搜索栏关闭，返回值: %s", val)
        if _Prompt._instance == self:
            _Prompt._instance = None
        self.destroy()
        self.on_done(val)

    def _on_focus_out(self, _):
        # 点击浮窗外即取消（给系统些时间确定焦点对象）
        self.after(100, lambda: self._finish(None))

# ---------- async API --------------------------------------------------------
async def ask_keyword(placeholder: str = "") -> Optional[str]:
    """Display the floating keyword prompt and await user input."""
    loop = asyncio.get_event_loop()
    fut = loop.create_future()

    def _done(val):
        if not fut.done():
            fut.set_result(val)

    logger.info("显示搜索栏")
    prompt = _Prompt(placeholder, _done)

    # 等待结果
    return await fut

async def ask_keyword_with_intent(placeholder: str = "", game_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    显示搜索栏并进行游戏感知的意图判断
    
    Args:
        placeholder: 搜索栏占位符
        game_name: 当前游戏名称（可选）
    
    Returns:
        None: 用户取消
        Dict: 包含keyword和intent的结果
    """
    keyword = await ask_keyword(placeholder)
    if not keyword or keyword == "<<LAST>>":
        return keyword
    
    # 使用游戏感知处理器
    try:
        result = process_game_aware_query(keyword, game_name)
        logger.info(f"游戏感知处理结果: {result.intent}, 置信度: {result.confidence}, 游戏: {game_name}")
        
        return {
            "keyword": keyword,
            "intent": result.intent,
            "confidence": result.confidence,
            "translated_query": result.translated_query,
            "rewritten_query": result.rewritten_query,
            "game_name": game_name,
            "game_context": result.game_context,
            "search_optimization": result.search_optimization
        }
    except Exception as e:
        logger.error(f"游戏感知处理失败，使用基础处理: {e}")
        # 降级到基础处理
        intent = classify_intent(keyword)
        confidence = get_intent_confidence(keyword)
        
        return {
            "keyword": keyword,
            "intent": intent,
            "confidence": confidence,
            "translated_query": keyword,
            "rewritten_query": keyword,
            "game_name": game_name,
            "game_context": {},
            "search_optimization": "hybrid"
        }

async def process_query_with_intent(keyword: str, game_name: Optional[str] = None) -> Dict[str, Any]:
    """
    根据意图处理用户查询（使用游戏感知处理器）
    
    Args:
        keyword: 用户输入的关键词
        game_name: 当前游戏名称（可选）
        
    Returns:
        处理结果字典
    """
    try:
        # 使用游戏感知处理器
        result = process_game_aware_query(keyword, game_name)
        
        logger.info(f"游戏感知处理查询: '{keyword}' (游戏: {game_name})")
        logger.info(f"结果: 意图={result.intent}, 置信度={result.confidence}")
        logger.info(f"翻译: '{result.translated_query}' -> 重写: '{result.rewritten_query}'")
        
        if result.intent == "guide":
            # 查攻略 - 使用RAG查询，启用与evaluation相同的高级功能
            print(f"🎯 [SEARCHBAR-DEBUG] 使用RAG查询攻略")
            logger.info("使用RAG查询攻略")
            # 使用重写后的查询进行RAG搜索
            rag_query = result.rewritten_query if result.rewrite_applied else result.translated_query
            
            # 将游戏名称映射到向量库文件名
            mapped_game_name = map_window_title_to_game_name(game_name) if game_name else None
            print(f"🎮 [SEARCHBAR-DEBUG] 游戏名称映射: '{game_name}' -> '{mapped_game_name}'")
            logger.info(f"游戏名称映射: '{game_name}' -> '{mapped_game_name}'")
            
            # 使用与evaluation相同的高级配置
            from .ai.rag_query import query_enhanced_rag
            from .config import LLMConfig
            
            print(f"📋 [SEARCHBAR-DEBUG] 调用query_enhanced_rag，使用以下配置:")
            print(f"   - 查询: '{rag_query}'")
            print(f"   - 游戏: {mapped_game_name}")
            print(f"   - 混合搜索: 启用 (vector_weight=0.5, bm25_weight=0.5)")
            print(f"   - 摘要: 启用 (gemini-2.0-flash-exp)")
            print(f"   - 重排序: 启用 (intent_weight=0.4)")
            
            rag_result = await query_enhanced_rag(
                question=rag_query,
                game_name=mapped_game_name,
                top_k=3,
                enable_hybrid_search=True,  # 启用混合搜索
                hybrid_config={
                    "fusion_method": "rrf",
                    "vector_weight": 0.5,  # 与evaluation相同的权重
                    "bm25_weight": 0.5,    # 与evaluation相同的权重
                    "rrf_k": 60
                },
                llm_config=LLMConfig(),
                enable_summarization=True,  # 启用Gemini摘要
                summarization_config={
                    "model_name": "gemini-2.0-flash-exp",
                    "max_summary_length": 300,
                    "temperature": 0.3,
                    "include_sources": True,
                    "language": "auto"
                },
                enable_intent_reranking=True,  # 启用意图重排序
                reranking_config={
                    "intent_weight": 0.4,
                    "semantic_weight": 0.6
                }
            )
            
            print(f"📊 [SEARCHBAR-DEBUG] RAG查询结果: 置信度={rag_result.get('confidence', 0):.3f}, 结果数={rag_result.get('results_count', 0)}")
            print(f"⏱️ [SEARCHBAR-DEBUG] 查询耗时: {rag_result.get('query_time', 0):.3f}秒")
            
            return {
                "type": "guide",
                "keyword": keyword,
                "intent": result.intent,
                "confidence": result.confidence,
                "translated_query": result.translated_query,
                "rewritten_query": result.rewritten_query,
                "game_name": game_name,
                "game_context": result.game_context,
                "search_optimization": result.search_optimization,
                "processing_time": result.processing_time,
                "result": rag_result
            }
        elif result.intent == "wiki":
            # 查wiki - 返回优化后的关键词用于搜索
            logger.info("使用Wiki搜索")
            return {
                "type": "wiki",
                "keyword": keyword,
                "intent": result.intent,
                "confidence": result.confidence,
                "translated_query": result.translated_query,
                "rewritten_query": result.rewritten_query,
                "game_name": game_name,
                "game_context": result.game_context,
                "search_optimization": result.search_optimization,
                "processing_time": result.processing_time,
                "result": None  # 需要外部处理wiki搜索
            }
        else:
            # 未知意图 - 默认使用wiki搜索
            logger.info("未知意图，默认使用Wiki搜索")
            return {
                "type": "wiki",
                "keyword": keyword,
                "intent": result.intent,
                "confidence": result.confidence,
                "translated_query": result.translated_query,
                "rewritten_query": result.rewritten_query,
                "game_name": game_name,
                "game_context": result.game_context,
                "search_optimization": result.search_optimization,
                "processing_time": result.processing_time,
                "result": None
            }
            
    except Exception as e:
        print(f"⚠️ [SEARCHBAR-DEBUG] 游戏感知处理失败，降级到基础处理: {e}")
        logger.error(f"游戏感知处理失败，使用基础处理: {e}")
        # 降级到基础处理
        intent = classify_intent(keyword)
        confidence = get_intent_confidence(keyword)
        
        print(f"🔄 [SEARCHBAR-DEBUG] 基础处理查询: '{keyword}', 意图: {intent}, 置信度: {confidence}")
        logger.info(f"基础处理查询: '{keyword}', 意图: {intent}, 置信度: {confidence}")
        
        if intent == "guide":
            # 查攻略 - 使用RAG查询，同样启用高级功能
            print(f"🎯 [SEARCHBAR-DEBUG] 使用RAG查询攻略（降级模式）")
            logger.info("使用RAG查询攻略")
            # 将游戏名称映射到向量库文件名
            mapped_game_name = map_window_title_to_game_name(game_name) if game_name else None
            print(f"🎮 [SEARCHBAR-DEBUG] 游戏名称映射: '{game_name}' -> '{mapped_game_name}'")
            logger.info(f"游戏名称映射: '{game_name}' -> '{mapped_game_name}'")
            
            # 使用与evaluation相同的高级配置
            from .ai.rag_query import query_enhanced_rag
            from .config import LLMConfig
            
            print(f"📋 [SEARCHBAR-DEBUG] 调用query_enhanced_rag（降级模式），使用以下配置:")
            print(f"   - 查询: '{keyword}'")
            print(f"   - 游戏: {mapped_game_name}")
            print(f"   - 混合搜索: 启用 (vector_weight=0.5, bm25_weight=0.5)")
            print(f"   - 摘要: 启用 (gemini-2.0-flash-exp)")
            print(f"   - 重排序: 启用 (intent_weight=0.4)")
            
            rag_result = await query_enhanced_rag(
                question=keyword,
                game_name=mapped_game_name,
                top_k=3,
                enable_hybrid_search=True,  # 启用混合搜索
                hybrid_config={
                    "fusion_method": "rrf",
                    "vector_weight": 0.5,  # 与evaluation相同的权重
                    "bm25_weight": 0.5,    # 与evaluation相同的权重
                    "rrf_k": 60
                },
                llm_config=LLMConfig(),
                enable_summarization=True,  # 启用Gemini摘要
                summarization_config={
                    "model_name": "gemini-2.0-flash-exp",
                    "max_summary_length": 300,
                    "temperature": 0.3,
                    "include_sources": True,
                    "language": "auto"
                },
                enable_intent_reranking=True,  # 启用意图重排序
                reranking_config={
                    "intent_weight": 0.4,
                    "semantic_weight": 0.6
                }
            )
            
            print(f"📊 [SEARCHBAR-DEBUG] RAG查询结果（降级模式）: 置信度={rag_result.get('confidence', 0):.3f}, 结果数={rag_result.get('results_count', 0)}")
            print(f"⏱️ [SEARCHBAR-DEBUG] 查询耗时: {rag_result.get('query_time', 0):.3f}秒")
        
            return {
                "type": "guide",
                "keyword": keyword,
                "intent": intent,
                "confidence": confidence,
                "translated_query": keyword,
                "rewritten_query": keyword,
                "game_name": game_name,
                "game_context": {},
                "search_optimization": "hybrid",
                "processing_time": 0.0,
                "result": rag_result
            }
        else:
            # 默认使用wiki搜索
            return {
                "type": "wiki",
                "keyword": keyword,
                "intent": intent,
                "confidence": confidence,
                "translated_query": keyword,
                "rewritten_query": keyword,
                "game_name": game_name,
                "game_context": {},
                "search_optimization": "hybrid",
                "processing_time": 0.0,
                "result": None
            }
