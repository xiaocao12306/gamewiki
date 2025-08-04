from enum import Enum

class WindowState(Enum):
    """Window state enumeration"""
    CHAT_ONLY = "chat_only"      # Only show input box
    FULL_CONTENT = "full_content" # Show all content
    WEBVIEW = "webview"          # WebView2 form

class MessageType(Enum):
    """Chat message types"""
    USER_QUERY = "user_query"
    AI_RESPONSE = "ai_response"
    AI_STREAMING = "ai_streaming"
    WIKI_LINK = "wiki_link"
    TRANSITION = "transition"