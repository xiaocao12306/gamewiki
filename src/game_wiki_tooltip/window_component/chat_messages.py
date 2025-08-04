from dataclasses import dataclass, field
from src.game_wiki_tooltip.core.i18n import t
from datetime import datetime
from typing import Dict, Any
from .enums import MessageType

@dataclass
class ChatMessage:
    """Single chat message"""
    type: MessageType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

# To allow class attributes to dynamically return translations, we use a metaclass
class TransitionMessagesMeta(type):
    """Metaclass for dynamically handling TransitionMessages attribute access"""

    def __getattribute__(cls, name):
        # Map old attribute names to new translation keys
        attribute_mapping = {
            'WIKI_SEARCHING': 'status_wiki_searching',
            'WIKI_FOUND': 'status_wiki_found',
            'GUIDE_SEARCHING': 'status_guide_searching',
            'GUIDE_GENERATING': 'status_guide_generating',
            'ERROR_NOT_FOUND': 'status_error_not_found',
            'ERROR_TIMEOUT': 'status_error_timeout',
            'QUERY_RECEIVED': 'status_query_received',
            'DB_SEARCHING': 'status_db_searching',
            'AI_SUMMARIZING': 'status_ai_summarizing',
            'COMPLETED': 'status_completed'
        }

        if name in attribute_mapping:
            return t(attribute_mapping[name])

        # For other attributes, use default behavior
        return super().__getattribute__(name)


class TransitionMessages(metaclass=TransitionMessagesMeta):
    """Predefined transition messages with i18n support"""

    def __new__(cls):
        # Prevent instantiation, this class should only be used for static access
        raise TypeError(f"{cls.__name__} should not be instantiated")

    # Static method versions for use when needed
    @staticmethod
    def get_wiki_searching():
        return t("status_wiki_searching")

    @staticmethod
    def get_wiki_found():
        return t("status_wiki_found")

    @staticmethod
    def get_guide_searching():
        return t("status_guide_searching")

    @staticmethod
    def get_guide_generating():
        return t("status_guide_generating")

    @staticmethod
    def get_error_not_found():
        return t("status_error_not_found")

    @staticmethod
    def get_error_timeout():
        return t("status_error_timeout")

    @staticmethod
    def get_query_received():
        return t("status_query_received")

    @staticmethod
    def get_db_searching():
        return t("status_db_searching")

    @staticmethod
    def get_ai_summarizing():
        return t("status_ai_summarizing")

    @staticmethod
    def get_completed():
        return t("status_completed")