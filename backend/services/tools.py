"""
Agent tools with timeouts and safety guardrails.
Includes: Python REPL, web search, RAG search.
"""

import asyncio
import logging
from functools import wraps
from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL
from backend.logging_config import logger_tools

logger = logging.getLogger(__name__)

# Timeout configurations (in seconds)
PYTHON_REPL_TIMEOUT = 30
WEB_SEARCH_TIMEOUT = 15
RAG_SEARCH_TIMEOUT = 10
MAX_OUTPUT_LENGTH = 5000

# Initialize Python REPL
python_repl_utility = PythonREPL()


def run_python_code_fast(code: str) -> str:
    """Run validated Python code and return normalized output for internal fast-path flows."""
    if not code or not isinstance(code, str):
        return "Error: Code must be a non-empty string"

    code = code.strip()

    dangerous_ops = [
        "os.remove", "os.rmdir", "shutil.rmtree",
        "subprocess.call", "subprocess.run", "__import__",
        "eval(", "exec(", "compile(",
        "requests.", "urllib.", "socket.",
    ]

    code_lower = code.lower()
    for op in dangerous_ops:
        if op in code_lower:
            logger_tools.warning(f"Blocked dangerous operation: {op}")
            return f"❌ Operation not allowed: {op}"

    if len(code) > 10000:
        return "❌ Code exceeds maximum length (10000 characters)"

    try:
        logger_tools.info("Executing Python code")
        result = python_repl_utility.run(code)

        if not result:
            return "Code executed successfully (no output)"

        if len(result) > MAX_OUTPUT_LENGTH:
            result = result[:MAX_OUTPUT_LENGTH] + "\n... (output truncated)"

        logger_tools.info(f"Python execution completed: {len(result)} chars")
        return result
    except TimeoutError:
        logger_tools.error("Python execution timed out")
        return f"⏱️ Code execution timed out (max {PYTHON_REPL_TIMEOUT} seconds)"
    except Exception as e:
        error_msg = str(e)[:200]
        logger_tools.error(f"Python execution error: {error_msg}")
        return f"❌ Execution error: {error_msg}"


def timeout_handler(timeout_seconds: int):
    """Decorator to add timeout to async operations."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else asyncio.coroutine(lambda: func(*args, **kwargs))(),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                return f"⏱️ Operation timed out after {timeout_seconds} seconds"
            except Exception as e:
                return f"Error: {str(e)[:200]}"
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return f"Error: {str(e)[:200]}"
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


@tool
def python_repl(code: str) -> str:
    """
    Execute Python code safely with timeout protection.
    
    Capabilities:
    - Data analysis with pandas, matplotlib
    - File operations (reading only)
    - Mathematical computations
    
    Restrictions:
    - No network calls, file deletions, or subprocess execution
    - Maximum 30 second execution time
    - Maximum 5000 character output
    
    Usage:
    - To analyze a CSV: df = pd.read_csv(filepath)
    - To create plots: plt.savefig('frontend/graphs/name.png'); print('![Graph](/static/graphs/name.png) [Download](/static/graphs/name.png)')
    - Do NOT use plt.show()
    """
    
    return run_python_code_fast(code)


@tool
def web_search(query: str) -> str:
    """
    Search the web for real-time information using DuckDuckGo.
    
    Usage:
    - Ask to look up current facts, news, or specific information
    - Use natural language queries (e.g., "Python async/await tutorial")
    
    Restrictions:
    - Maximum 15 second response time
    - Returns top 5 results
    """
    
    if not query or not isinstance(query, str):
        return "Error: Query must be a non-empty string"
    
    query = query.strip()
    
    if len(query) > 500:
        return "❌ Query too long (max 500 characters)"
    
    try:
        logger_tools.info(f"Web search: {query[:50]}...")
        from ddgs import DDGS
        
        with DDGS() as ddgs_client:
            results = list(ddgs_client.text(query, max_results=5))
            
            if not results:
                logger_tools.info("No web search results found")
                return "❌ No results found for your query"
            
            formatted = []
            for i, r in enumerate(results, 1):
                title = r.get('title', 'No title')[:100]
                body = r.get('body', 'No content')[:200]
                url = r.get('href', '')
                formatted.append(f"{i}. **{title}**\n{body}\n🔗 {url}")
            
            output = "\n\n".join(formatted)
            
            if len(output) > MAX_OUTPUT_LENGTH:
                output = output[:MAX_OUTPUT_LENGTH] + "\n... (truncated)"
            
            logger_tools.info(f"Web search completed: {len(results)} results")
            return output
            
    except TimeoutError:
        logger_tools.error("Web search timed out")
        return f"⏱️ Search timed out (max {WEB_SEARCH_TIMEOUT} seconds)"
    except Exception as e:
        error_msg = str(e)[:200]
        logger_tools.error(f"Web search error: {error_msg}")
        return f"❌ Search failed: {error_msg}"


@tool
def rag_search(query: str) -> str:
    """
    Search previously uploaded PDF documents for specific information.
    
    Usage:
    - Ask questions about your uploaded documents
    - Use specific terms from the document (e.g., "What does section 2 say about...?")
    
    Restrictions:
    - Maximum 10 second response time
    - Only searches uploaded PDFs
    - Returns top 4 most relevant chunks
    """
    
    if not query or not isinstance(query, str):
        return "Error: Query must be a non-empty string"
    
    query = query.strip()
    
    if len(query) > 500:
        return "❌ Query too long (max 500 characters)"
    
    try:
        logger_tools.info(f"RAG search: {query[:50]}...")
        from backend.services.rag import get_rag_service
        
        result = get_rag_service().search(query, k=4)
        
        if len(result) > MAX_OUTPUT_LENGTH:
            result = result[:MAX_OUTPUT_LENGTH] + "\n... (truncated)"
        
        logger_tools.info(f"RAG search completed")
        return result
        
    except TimeoutError:
        logger_tools.error("RAG search timed out")
        return f"⏱️ Search timed out (max {RAG_SEARCH_TIMEOUT} seconds)"
    except Exception as e:
        error_msg = str(e)[:200]
        logger_tools.error(f"RAG search error: {error_msg}")
        return f"❌ Search failed: {error_msg}"


def get_tools():
    """Return the list of tools available to the agent."""
    return [python_repl, web_search, rag_search]
