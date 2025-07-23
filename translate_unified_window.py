#!/usr/bin/env python3
"""
Script to translate Chinese print statements in unified_window.py to English
"""

import re

# Chinese to English translations for print statements
translations = {
    "Markdown转换失败": "Markdown conversion failed",
    "链接被点击": "Link clicked",
    "消息类型": "Message type",
    "是否为流式消息": "Is streaming message",
    "content_label格式": "content_label format",
    "使用标题": "Using title",
    "找到ChatView实例，调用显示Wiki页面": "Found ChatView instance, calling show Wiki page",
    "未找到ChatView实例": "ChatView instance not found",
    "新StreamingMessageWidget初始化完成，timer状态": "New StreamingMessageWidget initialization completed, timer status",
    "激活": "Active",
    "未激活": "Inactive",
    "初始化时已连接linkActivated信号": "linkActivated signal already connected during initialization",
    "初始化连接linkActivated信号失败": "Failed to connect linkActivated signal during initialization",
    "流式消息视图宽度异常": "Streaming message view width abnormal",
    "固定bubble宽度": "Fixed bubble width",
    "固定content宽度": "Fixed content width",
    "恢复bubble灵活宽度，最大": "Restored bubble flexible width, max",
    "恢复content灵活宽度，最大": "Restored content flexible width, max",
    "流式消息已停止，拒绝新内容块": "Streaming message stopped, rejecting new content chunk",
    "全文已更新，新长度": "Full text updated, new length",
    "初始检测到markdown格式，长度": "Initially detected markdown format, length",
    "Timer状态": "Timer status",
    "前50字符": "First 50 characters",
    "启动打字机定时器": "Started typewriter timer",
    "打字机定时器已在运行": "Typewriter timer already running",
    "调整打字速度": "Adjusted typing speed",
    "剩余": "Remaining",
    "字符": "characters",
    "流式消息已停止，显示位置": "Streaming message stopped, display position",
    "打字机效果检测到停止状态，立即终止": "Typewriter effect detected stop state, immediately terminating",
    "早期检测到markdown格式": "Early detected markdown format",
    "全文长度": "Full text length",
    "检测到视频源内容，触发渲染": "Detected video source content, triggering render",
    "检测到格式内容，触发渲染，当前长度": "Detected format content, triggering render, current length",
    "重新检测到格式内容，触发渲染": "Re-detected format content, triggering render",
    "重置为纯文本格式": "Reset to plain text format",
    "强制检测到格式内容，触发渲染，位置": "Force detected format content, triggering render, position",
    "强制渲染已检测的markdown内容，位置": "Force render detected markdown content, position",
    "切换到RichText格式，内容长度": "Switched to RichText format, content length",
    "已连接linkActivated信号": "linkActivated signal connected",
    "当前内容包含链接": "Current content contains links",
    "内容标签配置 - OpenExternalLinks": "Content label config - OpenExternalLinks",
    "内容标签格式": "Content label format",
    "切换到PlainText格式，内容长度": "Switched to PlainText format, content length",
    "强制显示前5个字符": "Force display first 5 characters",
    "流式消息完成，长度": "Streaming message completed, length",
    "包含视频源": "Contains video sources",
    "最终检测到markdown格式，强制更新渲染": "Finally detected markdown format, force update render",
    "最终格式检测": "Final format detection",
    "缓存状态": "Cache status",
    "最终渲染时连接linkActivated信号": "Connect linkActivated signal during final render",
    "最终渲染 - 内容包含链接": "Final render - content contains links",
    "最终渲染 - OpenExternalLinks": "Final render - OpenExternalLinks",
    "最终渲染 - 文本格式": "Final render - text format",
    "最终渲染完成，使用RichText格式": "Final render completed, using RichText format",
    "最终渲染完成，使用PlainText格式": "Final render completed, using PlainText format",
    "流式输出完成，快速显示剩余内容": "Streaming output completed, quickly display remaining content",
    "当前显示": "Currently displaying",
    "剩余": "Remaining",
    "字符，切换到极速显示模式": "characters, switching to ultra-fast display mode",
    "字符不多，保持当前速度": "characters not many, maintaining current speed",
    "检测到ChatView宽度异常，开始修复": "Detected ChatView width abnormal, starting fix",
    "父容器宽度": "Parent container width",
    "ChatView宽度": "ChatView width",
    "viewport宽度": "viewport width",
    "完整父容器链": "Complete parent container chain",
    "宽度": "width",
    "几何": "geometry",
    "已修复ChatView宽度为": "Fixed ChatView width to",
    "检测到viewport宽度异常，强制刷新layout": "Detected viewport width abnormal, force refresh layout",
    "当前尺寸策略": "Current size policy",
    "最小尺寸": "Minimum size",
    "最大尺寸": "Maximum size",
    "开始创建流式消息组件": "Started creating streaming message component",
    "流式消息组件创建成功": "Streaming message component created successfully",
    "流式消息组件类型": "Streaming message component type",
    "创建流式消息组件失败": "Failed to create streaming message component",
    "滚动请求被拒绝": "Scroll request rejected",
    "收到滚动请求，启动防抖定时器": "Received scroll request, starting debounce timer",
    "_perform_auto_scroll 被调用，pending": "_perform_auto_scroll called, pending",
    "内容高度变化": "Content height changed",
    "等待稳定": "Waiting for stability",
    "滚动检查": "Scroll check",
    "执行自动滚动，高度": "Executing auto scroll, height",
    "滚动被禁用或用户手动滚动": "Scroll disabled or user manually scrolled",
    "用户滚动到底部附近，重新启用自动滚动": "User scrolled near bottom, re-enabling auto scroll",
    "用户手动滚动离开底部，禁用自动滚动": "User manually scrolled away from bottom, disabling auto scroll",
    "用户在底部附近，保持自动滚动": "User near bottom, maintaining auto scroll",
    "滚轮操作离开底部，禁用自动滚动": "Wheel operation left bottom, disabling auto scroll",
    "双击聊天区域，重新启用自动滚动": "Double-clicked chat area, re-enabling auto scroll",
    "重置自动滚动状态": "Reset auto scroll state",
    "禁用自动滚动": "Disable auto scroll",
    "按下End键，重新启用自动滚动": "Pressed End key, re-enabling auto scroll",
    "按下Home键，滚动到顶部并禁用自动滚动": "Pressed Home key, scroll to top and disable auto scroll",
    "视图宽度异常": "View width abnormal",
    "ChatView布局更新": "ChatView layout updated",
    "更新消息显示时出错": "Error updating message display",
    "_ensureContentComplete 出错": "_ensureContentComplete error",
    "更新气泡高度时出错": "Error updating bubble height",
    "尝试创建WebView2": "Attempting to create WebView2",
    "WebView2创建成功 - 支持完整视频播放": "WebView2 created successfully - supports full video playback",
    "WebView2创建失败": "WebView2 creation failed",
    "WebView不可用，使用文本视图": "WebView not available, using text view",
    "页面加载完成处理失败": "Page load completion handling failed",
    "重定向检查失败": "Redirect check failed",
    "WikiView找到真实wiki页面": "WikiView found real wiki page",
    "处理页面标题失败": "Failed to process page title",
    "开始延迟WebView创建": "Starting delayed WebView creation",
    "WebView延迟创建成功": "WebView delayed creation successful"
}

def translate_file():
    """Translate the unified_window.py file"""
    file_path = "src/game_wiki_tooltip/unified_window.py"
    
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Apply translations
    for chinese, english in translations.items():
        content = content.replace(chinese, english)
    
    # Write back to file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Translation completed!")

if __name__ == "__main__":
    translate_file() 