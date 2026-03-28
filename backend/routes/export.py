import json
import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from backend.routes.chat import get_auth_data
from backend.logging_config import logger_chat

router = APIRouter(prefix="/api/export", tags=["export"])

@router.get("/notebook/{session_id}")
async def export_notebook(
    request: Request,
    session_id: str,
    auth_data: tuple = Depends(get_auth_data)
):
    sb, user_id = auth_data
    try:
        # Fetch history from Supabase
        res = sb.table("chat_history").select("role, content").eq("session_id", session_id).eq("user_id", user_id).order("created_at").execute()
        
        if not res.data:
            raise HTTPException(404, "Session not found or empty")

        nb = new_notebook()
        
        # Introduction cell
        nb.cells.append(new_markdown_cell(f"# Data Scientist Agent Export\n*Session ID*: `{session_id}`"))

        for msg in res.data:
            role = msg["role"]
            content = msg.get("content", "")
            
            # Simple markdown cell for the reasoning/question
            nb.cells.append(new_markdown_cell(f"**{role.capitalize()}**:\n{content}"))
            
            # If assistant contains code block, extract and make it a code cell
            if role == "assistant" and "```python" in content:
                parts = content.split("```python")
                for part in parts[1:]:
                    code = part.split("```")[0].strip()
                    if code:
                        nb.cells.append(new_code_cell(code))

        # We return the raw JSON Notebook format, which the frontend can download as .ipynb
        return JSONResponse(
            content=nb,
            headers={
                "Content-Disposition": f"attachment; filename=analysis_{session_id[:8]}.ipynb"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger_chat.error(f"Error exporting notebook: {e}")
        raise HTTPException(500, "Failed to export notebook")
