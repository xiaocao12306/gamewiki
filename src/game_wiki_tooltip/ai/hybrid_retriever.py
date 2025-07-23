"""
Hybrid Search Retriever Module
=============================

Features:
1. Integrates vector search and BM25 search
2. Implements multiple score fusion algorithms
3. Provides a unified search interface
4. Supports unified query processing (translation + rewrite + intent analysis)
5. Performance optimization: complete multiple tasks in one LLM call
"""

import numpy as np
import logging
from typing import List, Dict, Any, Optional, Tuple
from sklearn.preprocessing import MinMaxScaler
from pathlib import Path
from .enhanced_bm25_indexer import EnhancedBM25Indexer, BM25UnavailableError
from .unified_query_processor import process_query_unified, UnifiedQueryResult
from ..config import LLMConfig
from src.game_wiki_tooltip.i18n import t

logger = logging.getLogger(__name__)


class VectorRetrieverAdapter:
    """Vector retriever adapter for wrapping existing vector search functionality"""
    
    def __init__(self, rag_query_instance):
        """
        Initialize the adapter
        
        Args:
            rag_query_instance: EnhancedRagQuery instance
        """
        self.rag_query = rag_query_instance
    
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Perform vector search
        
        Args:
            query: Query text
            top_k: Number of results to return
            
        Returns:
            List of search results
        """
        if self.rag_query.config and self.rag_query.config["vector_store_type"] == "faiss":
            return self.rag_query._search_faiss(query, top_k)
        else:
            return self.rag_query._search_qdrant(query, top_k)


class HybridSearchRetriever:
    """Hybrid Search Retriever"""
    
    def __init__(self, 
                 vector_retriever: VectorRetrieverAdapter,
                 bm25_index_path: str,
                 fusion_method: str = "rrf",
                 vector_weight: float = 0.6,
                 bm25_weight: float = 0.4,
                 rrf_k: int = 60,
                 llm_config: Optional[LLMConfig] = None,
                 enable_unified_processing: bool = True,
                 enable_query_rewrite: bool = True):
        """
        Initialize the hybrid search retriever
        
        Args:
            vector_retriever: Vector retriever adapter
            bm25_index_path: BM25 index path
            fusion_method: Fusion method ("rrf", "weighted", "normalized")
            vector_weight: Vector search weight
            bm25_weight: BM25 search weight
            rrf_k: k parameter for RRF algorithm
            llm_config: LLM config
            enable_unified_processing: Whether to enable unified query processing (recommended)
            enable_query_rewrite: Whether to enable query rewrite (only effective when unified processing is disabled)
        """
        self.vector_retriever = vector_retriever
        self.fusion_method = fusion_method
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.rrf_k = rrf_k
        self.llm_config = llm_config or LLMConfig()
        
        # Performance optimization: unified vs separate processing
        self.enable_unified_processing = enable_unified_processing
        self.enable_query_rewrite = enable_query_rewrite if not enable_unified_processing else False
        
        # Initialize enhanced BM25 indexer
        self.bm25_indexer = None
        bm25_path = Path(bm25_index_path)
        
        if not bm25_path.exists():
            error_msg = f"BM25 index file does not exist: {bm25_index_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        try:
            self.bm25_indexer = EnhancedBM25Indexer()
            self.bm25_indexer.load_index(str(bm25_path))
            logger.info(f"Enhanced BM25 index loaded successfully: {bm25_index_path}")
        except BM25UnavailableError as e:
            # Re-raise BM25 specific error, keep error message intact
            logger.error(f"Hybrid search initialization failed: {e}")
            raise e
        except Exception as e:
            error_msg = t("enhanced_bm25_load_failed", error=str(e))
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # Statistics
        self.unified_processing_stats = {
            "total_queries": 0,
            "unified_successful": 0,
            "unified_failed": 0,
            "cache_hits": 0,
            "average_processing_time": 0.0
        }
        
        # Fallback statistics (only used when unified processing is disabled)
        self.query_rewrite_stats = {
            "total_queries": 0,
            "rewritten_queries": 0,
            "cache_hits": 0
        }
        
        self.query_translation_stats = {
            "total_queries": 0,
            "translated_queries": 0
        }
    
    def search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Perform hybrid search
        
        Args:
            query: Query text
            top_k: Number of results to return (kept for compatibility, but internally fixed to 5)
            
        Returns:
            Search result dict, including result list and metadata
        """
        logger.info(f"Starting hybrid search: {query}")
        
        # Fixed search parameters: vector and BM25 each return 10, final fusion returns 5
        vector_search_count = 10
        bm25_search_count = 10
        final_result_count = 5
        
        # Update statistics
        if self.enable_unified_processing:
            self.unified_processing_stats["total_queries"] += 1
        else:
            self.query_rewrite_stats["total_queries"] += 1
            self.query_translation_stats["total_queries"] += 1
        
        # Query processing
        if self.enable_unified_processing:
            # Use unified processor (recommended)
            try:
                unified_result = process_query_unified(query, self.llm_config)
                
                # Extract processing results
                final_query = unified_result.rewritten_query
                translation_applied = unified_result.translation_applied
                rewrite_applied = unified_result.rewrite_applied
                
                # Update statistics
                self.unified_processing_stats["unified_successful"] += 1
                if hasattr(unified_result, 'processing_time'):
                    avg_time = self.unified_processing_stats["average_processing_time"]
                    total_queries = self.unified_processing_stats["total_queries"]
                    self.unified_processing_stats["average_processing_time"] = (
                        (avg_time * (total_queries - 1) + unified_result.processing_time) / total_queries
                    )
                
                # Build query metadata
                query_metadata = {
                    "original_query": query,
                    "processed_query": final_query,
                    "bm25_optimized_query": unified_result.bm25_optimized_query,  # Add BM25 optimized query
                    "translation_applied": translation_applied,
                    "rewrite_applied": rewrite_applied,
                    "intent": unified_result.intent,
                    "confidence": unified_result.confidence,
                    "detected_language": unified_result.detected_language,
                    "processing_method": "unified",
                    "reasoning": unified_result.reasoning
                }
                
                logger.info(f"Unified processing succeeded: '{query}' -> '{final_query}' (translation: {translation_applied}, rewrite: {rewrite_applied})")
                
            except Exception as e:
                logger.error(f"Unified processing failed: {e}")
                self.unified_processing_stats["unified_failed"] += 1
                
                # Fallback to original query
                final_query = query
                translation_applied = False
                rewrite_applied = False
                query_metadata = {
                    "original_query": query,
                    "processed_query": final_query,
                    "bm25_optimized_query": final_query,  # Use original query on fallback
                    "translation_applied": False,
                    "rewrite_applied": False,
                    "processing_method": "fallback",
                    "error": str(e)
                }
        else:
            # Original separate processing (kept for compatibility)
            final_query = query
            translation_applied = False
            rewrite_applied = False
            
            # Query translation feature has been replaced by unified query processor, removed here
            
            # Query rewrite (if enabled)
            if self.enable_query_rewrite:
                try:
                    from .intent.intent_classifier import rewrite_query_for_search
                    rewrite_result = rewrite_query_for_search(final_query, self.llm_config)
                    
                    if rewrite_result.rewritten_query != final_query:
                        final_query = rewrite_result.rewritten_query
                        rewrite_applied = True
                        self.query_rewrite_stats["rewritten_queries"] += 1
                        logger.info(f"Query rewritten: '{query}' -> '{final_query}'")
                        
                except Exception as e:
                    logger.warning(f"Query rewrite failed: {e}")
            
            query_metadata = {
                "original_query": query,
                "processed_query": final_query,
                "bm25_optimized_query": final_query,  # Use processed query in separate processing
                "translation_applied": translation_applied,
                "rewrite_applied": rewrite_applied,
                "processing_method": "separate"
            }
        
        # Perform hybrid search
        try:
            # Vector search - always return 10 results
            print(f"🔍 [HYBRID-DEBUG] Starting vector search: query='{final_query}', top_k={vector_search_count}")
            vector_results = self.vector_retriever.search(final_query, vector_search_count)
            print(f"📊 [HYBRID-DEBUG] Number of vector search results: {len(vector_results)}")
            
            if vector_results:
                print(f"   📋 [HYBRID-DEBUG] Top 3 vector search results:")
                for i, result in enumerate(vector_results[:3]):
                    chunk = result.get("chunk", {})
                    print(f"      {i+1}. Topic: {chunk.get('topic', 'Unknown')}")
                    print(f"         Score: {result.get('score', 0):.4f}")
                    print(f"         Summary: {chunk.get('summary', '')[:80]}...")
            
            # BM25 search - always return 10 results, use LLM-optimized query
            bm25_results = []
            if self.bm25_indexer:
                # Use LLM-optimized BM25 query
                bm25_query = query_metadata.get("bm25_optimized_query", final_query)
                print(f"🔍 [HYBRID-DEBUG] Starting BM25 search:")
                print(f"   - Original query: '{query}'")
                print(f"   - Semantic query: '{final_query}'")
                print(f"   - BM25 optimized: '{bm25_query}'")
                print(f"   - Number of results: {bm25_search_count}")
                
                bm25_results = self.bm25_indexer.search(bm25_query, bm25_search_count)
                print(f"📊 [HYBRID-DEBUG] Number of BM25 search results: {len(bm25_results)}")
                
                if bm25_results:
                    print(f"   📋 [HYBRID-DEBUG] Top 3 BM25 search results:")
                    for i, result in enumerate(bm25_results[:3]):
                        chunk = result.get("chunk", {})
                        print(f"      {i+1}. Topic: {chunk.get('topic', 'Unknown')}")
                        print(f"         Score: {result.get('score', 0):.4f}")
                        print(f"         Summary: {chunk.get('summary', '')[:80]}...")
                        if "match_info" in result:
                            print(f"         Match info: {result['match_info'].get('relevance_reason', 'N/A')}")
            else:
                print(f"⚠️ [HYBRID-DEBUG] BM25 indexer not initialized, skipping BM25 search")
            
            # Score fusion - always return 5 results
            print(f"🔄 [HYBRID-DEBUG] Starting score fusion: method={self.fusion_method}")
            print(f"   - Vector weight: {self.vector_weight}")
            print(f"   - BM25 weight: {self.bm25_weight}")
            print(f"   - RRF_K: {self.rrf_k}")
            print(f"   - Final number of results: {final_result_count}")
            
            final_results = self._fuse_results(vector_results, bm25_results, final_result_count)
            
            print(f"✅ [HYBRID-DEBUG] Score fusion complete, final number of results: {len(final_results)}")
            if final_results:
                print(f"   📋 [HYBRID-DEBUG] Top 5 fused results:")
                for i, result in enumerate(final_results):
                    chunk = result.get("chunk", {})
                    print(f"      {i+1}. Topic: {chunk.get('topic', 'Unknown')}")
                    print(f"         Fusion score: {result.get('fusion_score', 0):.4f}")
                    print(f"         Vector score: {result.get('vector_score', 0):.4f}")
                    print(f"         BM25 score: {result.get('bm25_score', 0):.4f}")
            
            # Build return result
            return {
                "results": final_results,
                "query": query_metadata,
                "metadata": {
                    "fusion_method": self.fusion_method,
                    "vector_results_count": len(vector_results),
                    "bm25_results_count": len(bm25_results),
                    "final_results_count": len(final_results),
                    "vector_search_count": vector_search_count,
                    "bm25_search_count": bm25_search_count,
                    "target_final_count": final_result_count,
                    "processing_stats": self._get_processing_stats()
                }
            }
            
        except Exception as e:
            print(f"❌ [HYBRID-DEBUG] Hybrid search execution failed: {e}")
            logger.error(f"Hybrid search execution failed: {e}")
            return {
                "results": [],
                "query": query_metadata,
                "metadata": {
                    "error": str(e),
                    "vector_search_count": vector_search_count,
                    "bm25_search_count": bm25_search_count,
                    "target_final_count": final_result_count,
                    "processing_stats": self._get_processing_stats()
                }
            }
    
    def _fuse_results(self, vector_results: List[Dict], bm25_results: List[Dict], top_k: int) -> List[Dict]:
        """
        Fuse the results of vector search and BM25 search
        
        Args:
            vector_results: Vector search results
            bm25_results: BM25 search results
            top_k: Number of results to return
            
        Returns:
            Fused search results
        """
        if self.fusion_method == "rrf":
            return self._reciprocal_rank_fusion(vector_results, bm25_results, top_k)
        elif self.fusion_method == "weighted":
            return self._weighted_fusion(vector_results, bm25_results, top_k)
        elif self.fusion_method == "normalized":
            return self._normalized_fusion(vector_results, bm25_results, top_k)
        else:
            logger.warning(f"Unknown fusion method: {self.fusion_method}, using RRF")
            return self._reciprocal_rank_fusion(vector_results, bm25_results, top_k)
    
    def _reciprocal_rank_fusion(self, vector_results: List[Dict], bm25_results: List[Dict], top_k: int) -> List[Dict]:
        """
        Fuse results using Reciprocal Rank Fusion (RRF) algorithm
        """
        print(f"🔄 [FUSION-DEBUG] Starting RRF fusion: vector results={len(vector_results)}, BM25 results={len(bm25_results)}, k={self.rrf_k}")
        
        # Create mapping from document ID to score
        doc_scores = {}
        
        # Process vector search results
        print(f"   📊 [FUSION-DEBUG] Processing vector search results:")
        for rank, result in enumerate(vector_results, 1):
            chunk = result.get("chunk", {})
            doc_id = chunk.get("chunk_id", f"vector_{rank}")
            rrf_score = 1.0 / (self.rrf_k + rank)
            
            print(f"      {rank}. ID: {doc_id}")
            print(f"         Original score: {result.get('score', 0):.4f}")
            print(f"         RRF score: {rrf_score:.4f}")
            print(f"         Topic: {chunk.get('topic', 'Unknown')}")
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "result": result,
                    "vector_score": result.get("score", 0),
                    "bm25_score": 0,
                    "rrf_score": 0
                }
            doc_scores[doc_id]["rrf_score"] += rrf_score
        
        # Process BM25 search results
        print(f"   📊 [FUSION-DEBUG] Processing BM25 search results:")
        for rank, result in enumerate(bm25_results, 1):
            chunk = result.get("chunk", {})
            doc_id = chunk.get("chunk_id", f"bm25_{rank}")
            rrf_score = 1.0 / (self.rrf_k + rank)
            
            print(f"      {rank}. ID: {doc_id}")
            print(f"         Original score: {result.get('score', 0):.4f}")
            print(f"         RRF score: {rrf_score:.4f}")
            print(f"         Topic: {chunk.get('topic', 'Unknown')}")
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "result": result,
                    "vector_score": 0,
                    "bm25_score": result.get("score", 0),
                    "rrf_score": 0
                }
            else:
                doc_scores[doc_id]["bm25_score"] = result.get("score", 0)
            
            doc_scores[doc_id]["rrf_score"] += rrf_score
        
        # Sort by RRF score and return top_k results
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1]["rrf_score"], reverse=True)
        
        print(f"   📊 [FUSION-DEBUG] Sorted fusion results:")
        for i, (doc_id, scores) in enumerate(sorted_docs[:min(5, len(sorted_docs))]):
            print(f"      {i+1}. ID: {doc_id}")
            print(f"         Final RRF score: {scores['rrf_score']:.4f}")
            print(f"         Vector score: {scores['vector_score']:.4f}")
            print(f"         BM25 score: {scores['bm25_score']:.4f}")
            print(f"         Topic: {scores['result'].get('chunk', {}).get('topic', 'Unknown')}")
        
        final_results = []
        for doc_id, scores in sorted_docs[:top_k]:
            # Deep copy result object to avoid reference issues
            result = scores["result"].copy()
            
            # Ensure correct score fields are set
            result["score"] = scores["rrf_score"]  # Main score is RRF score
            result["fusion_score"] = scores["rrf_score"]
            result["vector_score"] = scores["vector_score"] 
            result["bm25_score"] = scores["bm25_score"]
            result["fusion_method"] = "rrf"
            result["original_vector_score"] = scores["vector_score"]  # Keep original vector score
            result["original_bm25_score"] = scores["bm25_score"]     # Keep original BM25 score
            
            # Add debug validation
            print(f"   🔧 [FUSION-DEBUG] Final result {len(final_results)+1}:")
            print(f"      Topic: {result.get('chunk', {}).get('topic', 'Unknown')}")
            print(f"      Set score field: {result['score']:.4f}")
            print(f"      RRF score: {result['fusion_score']:.4f}")
            
            final_results.append(result)
        
        print(f"✅ [FUSION-DEBUG] RRF fusion complete, returning {len(final_results)} results")
        return final_results
    
    def _weighted_fusion(self, vector_results: List[Dict], bm25_results: List[Dict], top_k: int) -> List[Dict]:
        """
        Fuse results using weighted average
        """
        # Normalize scores
        vector_scores = [r.get("score", 0) for r in vector_results]
        bm25_scores = [r.get("score", 0) for r in bm25_results]
        
        if vector_scores:
            vector_scaler = MinMaxScaler()
            vector_scores_norm = vector_scaler.fit_transform([[s] for s in vector_scores]).flatten()
        else:
            vector_scores_norm = []
        
        if bm25_scores:
            bm25_scaler = MinMaxScaler()
            bm25_scores_norm = bm25_scaler.fit_transform([[s] for s in bm25_scores]).flatten()
        else:
            bm25_scores_norm = []
        
        # Create document score mapping
        doc_scores = {}
        
        # Process vector results
        for i, result in enumerate(vector_results):
            doc_id = result.get("chunk_id", f"vector_{i}")
            normalized_score = vector_scores_norm[i] if i < len(vector_scores_norm) else 0
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "result": result,
                    "vector_score": normalized_score,
                    "bm25_score": 0
                }
            else:
                doc_scores[doc_id]["vector_score"] = normalized_score
        
        # Process BM25 results
        for i, result in enumerate(bm25_results):
            doc_id = result.get("chunk_id", f"bm25_{i}")
            normalized_score = bm25_scores_norm[i] if i < len(bm25_scores_norm) else 0
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    "result": result,
                    "vector_score": 0,
                    "bm25_score": normalized_score
                }
            else:
                doc_scores[doc_id]["bm25_score"] = normalized_score
        
        # Calculate weighted score
        for doc_id, scores in doc_scores.items():
            weighted_score = (
                scores["vector_score"] * self.vector_weight +
                scores["bm25_score"] * self.bm25_weight
            )
            scores["fusion_score"] = weighted_score
        
        # Sort and return results
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1]["fusion_score"], reverse=True)
        
        final_results = []
        for doc_id, scores in sorted_docs[:top_k]:
            result = scores["result"].copy()
            result["fusion_score"] = scores["fusion_score"]
            result["vector_score"] = scores["vector_score"]
            result["bm25_score"] = scores["bm25_score"]
            result["fusion_method"] = "weighted"
            final_results.append(result)
        
        return final_results
    
    def _normalized_fusion(self, vector_results: List[Dict], bm25_results: List[Dict], top_k: int) -> List[Dict]:
        """
        Fuse results using normalization
        """
        # Normalization logic is similar to weighted fusion, but with equal weights
        temp_vector_weight = self.vector_weight
        temp_bm25_weight = self.bm25_weight
        
        # Temporarily set equal weights
        self.vector_weight = 0.5
        self.bm25_weight = 0.5
        
        result = self._weighted_fusion(vector_results, bm25_results, top_k)
        
        # Restore original weights
        self.vector_weight = temp_vector_weight
        self.bm25_weight = temp_bm25_weight
        
        # Update fusion method tag
        for r in result:
            r["fusion_method"] = "normalized"
        
        return result
    
    def _get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        if self.enable_unified_processing:
            return {
                "method": "unified_processing",
                "stats": self.unified_processing_stats.copy()
            }
        else:
            return {
                "method": "separate_processing",
                "translation_stats": self.query_translation_stats.copy(),
                "rewrite_stats": self.query_rewrite_stats.copy()
            }
    
    def get_search_stats(self) -> Dict[str, Any]:
        """Get search statistics"""
        vector_stats = {}
        bm25_stats = {}
        
        # Get BM25 statistics
        if hasattr(self.bm25_indexer, 'get_stats'):
            bm25_stats = self.bm25_indexer.get_stats()
        
        base_stats = {
            "vector_stats": vector_stats,
            "bm25_stats": bm25_stats,
            "unified_processing_enabled": self.enable_unified_processing,
            "query_rewrite_enabled": self.enable_query_rewrite
        }
        
        if self.enable_unified_processing:
            base_stats["unified_processing_stats"] = self.unified_processing_stats.copy()
        else:
            base_stats["query_rewrite_stats"] = self.query_rewrite_stats.copy()
            base_stats["query_translation_stats"] = self.query_translation_stats.copy()
        
        return base_stats
    
    def reset_stats(self):
        """Reset all statistics"""
        self.unified_processing_stats = {
            "total_queries": 0,
            "unified_successful": 0,
            "unified_failed": 0,
            "cache_hits": 0,
            "average_processing_time": 0.0
        }
        
        self.query_rewrite_stats = {
            "total_queries": 0,
            "rewritten_queries": 0,
            "cache_hits": 0
        }
        
        self.query_translation_stats = {
            "total_queries": 0,
            "translated_queries": 0
        }


def test_hybrid_retriever():
    """Test hybrid retriever"""
    # Requires actual vector retriever instance
    print("Hybrid retriever test requires full RAG system support")
    print("Please test in the complete system")


if __name__ == "__main__":
    test_hybrid_retriever() 