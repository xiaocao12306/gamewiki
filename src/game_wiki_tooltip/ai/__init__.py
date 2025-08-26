"""
GameWiki Assistant AI Module Package
===================================

This package contains all AI-related functionality for the GameWiki Assistant,
including vector search, BM25 search, hybrid retrieval, and LLM integration.
"""

# Ensure all key modules are properly recognized during packaging
__all__ = [
    'hybrid_retriever',
    'enhanced_bm25_indexer', 
    'batch_embedding',
    'rag_query',
    'unified_query_processor',
    'gemini_embedding',
    'gemini_summarizer',
    'intent_aware_reranker',
    # Note: 'intent' module is deprecated, functionality moved to unified_query_processor
]

# Version information
__version__ = "1.0.0"
