"""
TXT Loader Service
Handles basic parsing of Uploaded Text Files for the Agent.
"""

from pathlib import Path
from backend.logging_config import logger_upload

MAX_TXT_SIZE_MB = 20

def load_txt(file_path: str) -> dict:
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_TXT_SIZE_MB:
            return {"success": False, "error": f"TXT exceeds max size ({file_size_mb:.1f}MB)"}

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        summary_lines = [
            f"Dataset: {path.name} (Text)",
            f"Total Lines: {len(lines)}",
            f"File Size: {file_size_mb:.2f} MB"
        ]

        return {
            "success": True,
            "filename": path.name,
            "lines": len(lines),
            "preview": "\n".join(lines[:10]),
            "summary": "\n".join(summary_lines),
            "error": None,
        }

    except Exception as exc:
        logger_upload.error(f"TXT loading error: {exc}")
        return {"success": False, "error": str(exc)[:200]}
