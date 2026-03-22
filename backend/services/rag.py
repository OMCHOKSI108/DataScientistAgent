"""
RAG Service - Thread-safe FAISS vector store management.
Handles PDF chunking, embeddings, and semantic search.
"""

import os
import threading
import logging
from typing import List, Dict, Optional
from backend.config import get_settings

logger = logging.getLogger(__name__)

FAISS_INDEX_PATH = "backend/faiss_index"

# Thread safety
_rag_lock = threading.RLock()  # Re-entrant lock for nested calls
_rag_service_instance = None


class FAISSRetriever:
    """Thread-safe FAISS vector store wrapper."""
    
    def __init__(self):
        self.settings = get_settings()
        self._lock = threading.RLock()
        self.vectorstore = None
        self.embeddings = None
        self._initialized = False
        self._init_embeddings()
        self._load_index()
    
    def _init_embeddings(self):
        """Initialize embeddings model using HuggingFace (free, no API key needed)."""
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            self.embeddings = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
            self._initialized = True
            logger.info("HuggingFace embeddings initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}")
            self._initialized = False
    
    def _load_index(self):
        """Load existing FAISS index from disk."""
        if not os.path.exists(FAISS_INDEX_PATH):
            return
        
        with self._lock:
            try:
                from langchain_community.vectorstores import FAISS
                
                self.vectorstore = FAISS.load_local(
                    FAISS_INDEX_PATH,
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                logger.info("FAISS index loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load FAISS index: {e}")
                self.vectorstore = None
    
    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict]] = None
    ) -> bool:
        """
        Add text chunks to the FAISS index.
        Thread-safe operation with file locking.
        
        Args:
            texts: List of text chunks
            metadatas: Optional metadata for each chunk
            
        Returns:
            True if successful, False otherwise
        """
        if not texts:
            return False
        
        if not self._initialized or not self.embeddings:
            logger.error("Embeddings not initialized")
            return False
        
        with self._lock:
            try:
                from langchain_community.vectorstores import FAISS
                
                if self.vectorstore is None:
                    # Create new index
                    self.vectorstore = FAISS.from_texts(
                        texts,
                        self.embeddings,
                        metadatas=metadatas,
                    )
                    logger.info(f"Created new FAISS index with {len(texts)} chunks")
                else:
                    # Add to existing index
                    self.vectorstore.add_texts(texts, metadatas=metadatas)
                    logger.info(f"Added {len(texts)} chunks to FAISS index")
                
                # Save to disk atomically
                os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
                self.vectorstore.save_local(FAISS_INDEX_PATH)
                logger.info("FAISS index saved to disk")
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to add texts to FAISS: {e}")
                return False
    
    def search(
        self,
        query: str,
        k: int = 4
    ) -> str:
        """
        Search the FAISS index for relevant chunks.
        Thread-safe read operation.
        
        Args:
            query: Search query
            k: Number of results to return
            
        Returns:
            Formatted search results as string
        """
        if not self.vectorstore:
            return "No documents have been uploaded or indexed yet."
        
        if not query or not isinstance(query, str):
            return "Invalid query"
        
        with self._lock:
            try:
                results = self.vectorstore.similarity_search(
                    query,
                    k=min(k, 10),  # Cap at 10
                )
                
                if not results:
                    logger.info(f"No search results for query: {query[:50]}")
                    return "No relevant information found in the documents."
                
                formatted_results = []
                for i, doc in enumerate(results):
                    source = doc.metadata.get("source", "Unknown Document")
                    content = doc.page_content[:500]  # Limit content length
                    # Sanitize content to prevent XSS
                    content_safe = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    formatted_results.append(
                        f"--- Document Snippet {i + 1} (Source: {source}) ---\n{content_safe}"
                    )
                
                output = "\n\n".join(formatted_results)
                logger.info(f"Search returned {len(results)} results")
                return output
                
            except Exception as e:
                logger.error(f"FAISS search error: {e}")
                return f"Error searching documents (details logged)"


def get_rag_service() -> FAISSRetriever:
    """
    Get or initialize the global RAG service instance.
    Thread-safe singleton pattern.
    
    Returns:
        FAISSRetriever instance
    """
    global _rag_service_instance
    
    if _rag_service_instance is None:
        with _rag_lock:
            # Double-check locking pattern
            if _rag_service_instance is None:
                logger.info("Initializing RAG service...")
                _rag_service_instance = FAISSRetriever()
    
    return _rag_service_instance
