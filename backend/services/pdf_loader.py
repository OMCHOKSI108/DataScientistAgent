"""
PDF Loader Service - Hardened version
Extracts text from PDFs with size limits and edge case handling.
"""

from pathlib import Path
from PyPDF2 import PdfReader
from backend.services.rag import get_rag_service
from backend.logging_config import logger_upload

MAX_PDF_SIZE_MB = 50
MAX_PAGES = 500
MIN_CHUNK_SIZE = 100
MAX_CHUNK_SIZE = 1000


def load_pdf(file_path: str) -> dict:
    """
    Load and extract text from a PDF file.
    
    Args:
        file_path: Absolute path to the PDF file
        
    Returns:
        Dictionary with extraction results or error
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        
        # Check file size
        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_PDF_SIZE_MB:
            return {
                "success": False,
                "error": f"PDF exceeds max size ({file_size_mb:.1f}MB > {MAX_PDF_SIZE_MB}MB)"
            }
        
        # Read PDF
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        
        # Check page limit
        if total_pages > MAX_PAGES:
            return {
                "success": False,
                "error": f"PDF exceeds max pages ({total_pages} > {MAX_PAGES})"
            }
        
        # Extract text from all pages
        pages_text = []
        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
                if text:
                    pages_text.append(text.strip())
            except Exception as e:
                logger_upload.warning(f"Error extracting page {i}: {e}")
                continue
        
        full_text = "\n\n".join(pages_text)
        
        if not full_text.strip():
            return {
                "success": False,
                "error": "Could not extract text from PDF. It may be image-based.",
            }
        
        # Split into chunks for RAG (safe chunking)
        chunks = _split_into_chunks(
            full_text,
            chunk_size=500,
            overlap=50,
            min_size=MIN_CHUNK_SIZE
        )
        
        # Index chunks in FAISS
        metadatas = [{"source": path.name} for _ in chunks]
        try:
            get_rag_service().add_texts(chunks, metadatas)
        except Exception as e:
            logger_upload.error(f"Failed to index PDF chunks: {e}")
            # Don't fail completely - chunks are created even if indexing fails
        
        logger_upload.info(f"PDF processed: {path.name} ({total_pages} pages, {len(chunks)} chunks)")
        
        return {
            "success": True,
            "filename": path.name,
            "total_pages": total_pages,
            "text": full_text,
            "chunks": chunks,
            "error": None,
        }
        
    except Exception as exc:
        logger_upload.error(f"PDF loading error: {exc}")
        return {"success": False, "error": str(exc)[:200]}


def _split_into_chunks(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
    min_size: int = MIN_CHUNK_SIZE
) -> list:
    """
    Split text into overlapping chunks with safety guards.
    
    Args:
        text: Full document text
        chunk_size: Target characters per chunk
        overlap: Characters of overlap between chunks
        min_size: Minimum chunk size (prevents tiny fragments)
        
    Returns:
        List of text chunks
    """
    if not text:
        return []
    
    # Safety: cap parameters
    chunk_size = min(max(chunk_size, MIN_CHUNK_SIZE), MAX_CHUNK_SIZE)
    overlap = min(overlap, chunk_size // 2)
    
    chunks = []
    start = 0
    text_len = len(text)
    max_iterations = (text_len // (chunk_size - overlap)) + 10  # Prevent infinite loops
    iteration = 0
    
    while start < text_len and iteration < max_iterations:
        iteration += 1
        end = min(start + chunk_size, text_len)
        
        # Try to break at sentence boundary (only if not at end)
        if end < text_len:
            # Look backwards for a natural break point
            for sep in [". ", ".\\n", "? ", "!\\n", "\\n\\n", "\\n"]:
                # Search from chunk_size//2 onward to avoid breaking too early
                search_start = max(start + chunk_size // 2, start)
                boundary = text.rfind(sep, search_start, min(end + 100, text_len))
                
                if boundary > search_start:
                    end = boundary + len(sep)
                    break
        
        # Extract and validate chunk
        chunk = text[start:end].strip()
        
        # Only add if chunk meets minimum size
        if len(chunk) >= min_size:
            chunks.append(chunk)
        
        # Move to next position with overlap
        # Prevent infinite loop: ensure forward progress
        next_start = end - overlap
        if next_start <= start:
            next_start = start + chunk_size
        
        start = next_start
    
    if iteration >= max_iterations:
        logger_upload.warning(f"Chunk splitting hit iteration limit ({max_iterations})")
    
    return chunks
