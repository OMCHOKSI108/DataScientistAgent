"""
File upload routes - Hardened version
Handles CSV and PDF file uploads with strict validation.
"""

import os
import hashlib
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from backend.config import get_settings
from backend.services.csv_loader import load_csv
from backend.services.pdf_loader import load_pdf
from backend.utils.validators import (
    validate_filename,
    validate_file_size,
    ValidationError,
)
from backend.logging_config import logger_upload
from backend.middleware.rate_limiter import rate_limit_global_ip, rate_limit_upload
from supabase import create_client, ClientOptions

router = APIRouter(prefix="/api/upload", tags=["upload"])

# Allowed file extensions
ALLOWED_EXTENSIONS = {".csv", ".pdf", ".txt", ".parquet"}
MAX_FILE_SIZE_MB = 50


def get_auth_data(request: Request) -> tuple:
    """Extract user_id from authorization header."""
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    rate_limit_global_ip(request)
    
    token = authorization.split(" ", 1)[1]
    settings = get_settings()
    sb = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_KEY,
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )
    
    try:
        user_response = sb.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return sb, str(user_response.user.id)
    except HTTPException:
        raise
    except Exception as e:
        logger_upload.error(f"Auth error: {type(e).__name__}")
        raise HTTPException(status_code=401, detail="Authentication failed")


def generate_safe_filename(original_filename: str, file_hash: str) -> str:
    """
    Generate a safe filename with hash prefix to prevent collisions.
    
    Args:
        original_filename: Original uploaded filename
        file_hash: Hash of file content for collision detection
        
    Returns:
        Safe filename with hash prefix
    """
    try:
        # Validate and sanitize filename
        sanitized = validate_filename(original_filename)
    except ValidationError:
        # Fallback for invalid filenames
        ext = Path(original_filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(f"File type '{ext}' not allowed")
        sanitized = f"file{ext}"
    
    # Use first 8 chars of hash + original filename
    hash_prefix = file_hash[:8]
    return f"{hash_prefix}_{sanitized}"


@router.post("")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    auth_data: tuple = Depends(get_auth_data),
):
    """
    Upload a CSV or PDF file with strict validation.
    - Validates file extension
    - Validates file size
    - Generates collision-safe filename
    - Parses and indexes the file
    """
    user_id = auth_data[1]
    rate_limit_upload(request, user_id)
    
    # Validate filename extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger_upload.warning(
            f"User {user_id} attempted to upload file with invalid extension: {ext}"
        )
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    
    settings = get_settings()
    
    try:
        # Read file content
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)
        
        # Validate file size
        try:
            validate_file_size(len(content), max_size_mb=MAX_FILE_SIZE_MB)
        except ValidationError as ve:
            logger_upload.warning(f"User {user_id} file size exceeded: {file_size_mb:.1f}MB")
            raise HTTPException(status_code=413, detail=str(ve))
        
        # Generate safe filename with content hash
        file_hash = hashlib.md5(content).hexdigest()
        safe_filename = generate_safe_filename(file.filename, file_hash)
        
        # Ensure uploads directory exists
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        save_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
        
        # Check for existing file with same hash (prevent duplicates)
        if os.path.exists(save_path):
            logger_upload.info(f"Duplicate file detected: {safe_filename}")
            return {
                "success": True,
                "message": "File already uploaded",
                "file_path": save_path,
                "original_name": file.filename,
                "file_type": ext.replace(".", ""),
                "size_mb": round(file_size_mb, 2),
                "hash": file_hash,
            }
        
        # Write file to disk
        try:
            with open(save_path, "wb") as f:
                f.write(content)
            logger_upload.info(
                f"File saved: {safe_filename} ({file_size_mb:.2f}MB) by user {user_id}"
            )
        except Exception as e:
            logger_upload.error(f"Failed to save file: {e}")
            raise HTTPException(status_code=500, detail="Failed to save file")
        
        # Parse file based on type
        parse_result = None
        try:
            if ext == ".csv":
                parse_result = load_csv(save_path)
            elif ext == ".pdf":
                parse_result = load_pdf(save_path)
            elif ext == ".txt":
                from backend.services.txt_loader import load_txt
                parse_result = load_txt(save_path)
            elif ext == ".parquet":
                from backend.services.parquet_loader import load_parquet
                parse_result = load_parquet(save_path)
            else:
                raise ValueError(f"Unsupported file type: {ext}")
            
            if not parse_result.get("success"):
                logger_upload.warning(
                    f"Failed to parse file {safe_filename}: {parse_result.get('error')}"
                )
                # Don't fail - return what we can
        except Exception as e:
            logger_upload.error(f"Error parsing file {safe_filename}: {e}")
            parse_result = {
                "success": False,
                "error": f"Failed to parse file: {str(e)[:100]}",
            }
        
        # Prepare response
        response = {
            "file_path": save_path,
            "original_name": file.filename,
            "file_type": ext.replace(".", ""),
            "size_mb": round(file_size_mb, 2),
            "hash": file_hash,
        }
        
        # Add parse results if available
        if parse_result:
            response.update(parse_result)
        else:
            response["success"] = True
            response["message"] = "File uploaded successfully"
        
        logger_upload.info(f"Upload completed: {safe_filename} for user {user_id}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger_upload.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
    finally:
        # Close file properly
        await file.close()


@router.get("/files")
async def list_uploaded_files(request: Request, auth_data: tuple = Depends(get_auth_data)):
    """
    List all uploaded files in the uploads directory.
    Returns file metadata without exposing full system paths.
    """
    user_id = auth_data[1]
    rate_limit_upload(request, user_id)
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR)
    
    try:
        if not upload_dir.exists():
            logger_upload.info(f"Upload directory doesn't exist yet for user {user_id}")
            return {"files": []}
        
        files = []
        for f in upload_dir.iterdir():
            if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS:
                try:
                    file_size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                    files.append(
                        {
                            "filename": f.name,
                            "size_mb": file_size_mb,
                            "type": f.suffix.lower().replace(".", ""),
                            "uploaded_at": f.stat().st_mtime,
                            # Note: not returning path for security
                        }
                    )
                except Exception as e:
                    logger_upload.warning(f"Error reading file metadata: {e}")
                    continue
        
        logger_upload.info(f"Returned {len(files)} files for user {user_id}")
        return {"files": files, "total_size_mb": round(sum(f["size_mb"] for f in files), 2)}
        
    except Exception as e:
        logger_upload.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")
