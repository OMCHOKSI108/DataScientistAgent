"""
Input validators for the API.
Provides reusable validation functions to sanitize and validate user input across routes.
"""

import re
from pathlib import Path
from typing import Optional

# Configuration
MAX_MESSAGE_LENGTH = 5000
MAX_TITLE_LENGTH = 100
MAX_EMAIL_LENGTH = 254
MAX_PASSWORD_LENGTH = 128
MIN_PASSWORD_LENGTH = 8
MAX_FILE_SIZE_MB = 50
ALLOWED_FILE_EXTENSIONS = {".csv", ".pdf"}

# File name pattern - only alphanumeric, dash, underscore, dot
SAFE_FILENAME_PATTERN = re.compile(r"^[\w\-. ]+$")


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_message(message: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """
    Validate and normalize a chat message.
    
    Args:
        message: Raw user message
        max_length: Maximum allowed message length
        
    Returns:
        Normalized message
        
    Raises:
        ValidationError: If message is invalid
    """
    if not isinstance(message, str):
        raise ValidationError("Message must be a string")
    
    normalized = message.strip()
    
    if not normalized:
        raise ValidationError("Message cannot be empty")
    
    if len(normalized) > max_length:
        raise ValidationError(f"Message exceeds maximum length of {max_length} characters")
    
    # Prevent common injection patterns
    if any(pattern in normalized.lower() for pattern in ["<script", "onclick=", "onerror="]):
        raise ValidationError("Message contains invalid characters")
    
    return normalized


def validate_email(email: str) -> str:
    """
    Validate email address.
    
    Args:
        email: Email string
        
    Returns:
        Normalized email (lowercase)
        
    Raises:
        ValidationError: If email is invalid
    """
    if not isinstance(email, str):
        raise ValidationError("Email must be a string")
    
    normalized = email.strip().lower()
    
    if len(normalized) > MAX_EMAIL_LENGTH:
        raise ValidationError("Email exceeds maximum length")
    
    # Basic email validation
    email_pattern = re.compile(
        r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
    )
    
    if not email_pattern.match(normalized):
        raise ValidationError("Invalid email format")
    
    return normalized


def validate_password(password: str) -> str:
    """
    Validate password strength.
    
    Args:
        password: Password string
        
    Returns:
        Password (unchanged)
        
    Raises:
        ValidationError: If password is weak
    """
    if not isinstance(password, str):
        raise ValidationError("Password must be a string")
    
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(f"Password exceeds maximum length of {MAX_PASSWORD_LENGTH}")
    
    return password


def validate_title(title: str, max_length: int = MAX_TITLE_LENGTH) -> str:
    """
    Validate and normalize a chat title.
    
    Args:
        title: Session title
        max_length: Maximum allowed length
        
    Returns:
        Normalized title
        
    Raises:
        ValidationError: If title is invalid
    """
    if not isinstance(title, str):
        raise ValidationError("Title must be a string")
    
    normalized = title.strip()
    
    if not normalized:
        raise ValidationError("Title cannot be empty")
    
    if len(normalized) > max_length:
        normalized = normalized[:max_length].strip()
    
    return normalized


def validate_filename(filename: str) -> str:
    """
    Validate and sanitize uploaded filename.
    
    Args:
        filename: Original filename from upload
        
    Returns:
        Sanitized filename
        
    Raises:
        ValidationError: If filename is invalid
    """
    if not isinstance(filename, str):
        raise ValidationError("Filename must be a string")
    
    filename = filename.strip()
    
    if not filename:
        raise ValidationError("Filename cannot be empty")
    
    # Check extension
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise ValidationError(f"File type '{ext}' not allowed. Allowed types: {', '.join(ALLOWED_FILE_EXTENSIONS)}")
    
    # Get base name without extension
    base_name = Path(filename).stem
    
    # Validate filename characters
    if not SAFE_FILENAME_PATTERN.match(base_name):
        raise ValidationError("Filename contains invalid characters. Only alphanumeric, dash, underscore, space, and dot are allowed")
    
    # Limit filename length (leave room for UUID prefix)
    if len(base_name) > 100:
        base_name = base_name[:100]
    
    # Reconstruct sanitized filename
    sanitized = f"{base_name}{ext}"
    
    return sanitized


def validate_file_size(file_size_bytes: int, max_size_mb: int = MAX_FILE_SIZE_MB) -> None:
    """
    Validate uploaded file size.
    
    Args:
        file_size_bytes: Size of file in bytes
        max_size_mb: Maximum allowed size in MB
        
    Raises:
        ValidationError: If file is too large or invalid
    """
    if file_size_bytes is None or not isinstance(file_size_bytes, int):
        raise ValidationError("File size must be a valid integer")
    
    if file_size_bytes <= 0:
        raise ValidationError("File size must be greater than 0 bytes")
    
    max_bytes = max_size_mb * 1024 * 1024
    
    if file_size_bytes > max_bytes:
        raise ValidationError(
            f"File size ({file_size_bytes / 1024 / 1024:.1f} MB) exceeds maximum of {max_size_mb} MB"
        )


def validate_session_id(session_id: str) -> str:
    """
    Validate session ID format (UUID).
    
    Args:
        session_id: Session ID string
        
    Returns:
        Session ID if valid
        
    Raises:
        ValidationError: If not a valid UUID
    """
    if not isinstance(session_id, str):
        raise ValidationError("Session ID must be a string")
    
    session_id = session_id.strip()
    
    # Basic UUID validation (handles UUID4 format)
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$",
        re.IGNORECASE
    )
    
    if not uuid_pattern.match(session_id):
        raise ValidationError("Invalid session ID format")
    
    return session_id


def validate_query(query: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """
    Validate search/RAG query.
    
    Args:
        query: Search query string
        max_length: Maximum allowed length
        
    Returns:
        Normalized query
        
    Raises:
        ValidationError: If query is invalid
    """
    if not isinstance(query, str):
        raise ValidationError("Query must be a string")
    
    normalized = query.strip()
    
    if not normalized:
        raise ValidationError("Query cannot be empty")
    
    if len(normalized) > max_length:
        raise ValidationError(f"Query exceeds maximum length of {max_length} characters")
    
    return normalized


def validate_python_code(code: str, max_length: int = 10000) -> str:
    """
    Basic validation of Python code before execution.
    
    Args:
        code: Python code string
        max_length: Maximum allowed code length
        
    Returns:
        Code if valid
        
    Raises:
        ValidationError: If code is invalid or dangerous
    """
    if not isinstance(code, str):
        raise ValidationError("Code must be a string")
    
    normalized = code.strip()
    
    if not normalized:
        raise ValidationError("Code cannot be empty")
    
    if len(normalized) > max_length:
        raise ValidationError(f"Code exceeds maximum length of {max_length} characters")
    
    # Block dangerous patterns
    dangerous_patterns = [
        "os.remove",
        "os.rmdir",
        "shutil.rmtree",
        "subprocess.call",
        "subprocess.run",
        "__import__",
        "eval(",
        "exec(",
        "compile(",
    ]
    
    code_lower = normalized.lower()
    for pattern in dangerous_patterns:
        if pattern in code_lower:
            raise ValidationError(f"Code contains dangerous operation: {pattern}")
    
    return normalized
