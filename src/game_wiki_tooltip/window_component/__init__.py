"""
Windows module for game wiki tooltip application.
Contains window-related classes and utilities.
"""

from .markdown_converter import convert_markdown_to_html, detect_markdown_content
from .svg_icon import load_svg_icon
from .enums import MessageType, WindowState
from .chat_messages import ChatMessage, TransitionMessages
from .chat_widgets import MessageWidget, StatusMessageWidget, StreamingMessageWidget
from .chat_view import ChatView
from .wiki_view import WikiView
from .quick_access_popup import QuickAccessPopup, ExpandableIconButton
from .window_controller import AssistantController
__all__ = [
    'convert_markdown_to_html',
    'detect_markdown_content',
    'AssistantController', 
    'WikiView',
    'load_svg_icon',
    'MessageType',
    'WindowState',
    'QuickAccessPopup',
    'ExpandableIconButton',
    'ChatMessage',
    'TransitionMessages',
    'StatusMessageWidget',
    'StreamingMessageWidget',
    'WindowsGraphicsCompatibility',
    'ChatView',
]

from src.game_wiki_tooltip.core.graphics_compatibility import WindowsGraphicsCompatibility