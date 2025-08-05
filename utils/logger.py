"""
Privacy-protected logging configuration
Filters sensitive data from logs to protect user privacy
"""

import re
from loguru import logger
import sys

class PrivacyLogFilter:
    """Filter to remove sensitive data from log messages"""
    
    SENSITIVE_PATTERNS = [
        # Email content patterns
        (r'"body":\s*"[^"]*"', '"body": "[CONTENT_FILTERED]"'),
        (r'"message":\s*"[^"]*"', '"message": "[CONTENT_FILTERED]"'),
        (r'"text":\s*"[^"]*"', '"text": "[CONTENT_FILTERED]"'),
        
        # Token patterns
        (r'"token":\s*"[^"]*"', '"token": "[TOKEN_FILTERED]"'),
        (r'"refresh_token":\s*"[^"]*"', '"refresh_token": "[TOKEN_FILTERED]"'),
        (r'"access_token":\s*"[^"]*"', '"access_token": "[TOKEN_FILTERED]"'),
        (r'"client_secret":\s*"[^"]*"', '"client_secret": "[SECRET_FILTERED]"'),
        
        # Password patterns
        (r'"password":\s*"[^"]*"', '"password": "[PASSWORD_FILTERED]"'),
        (r'"password_hash":\s*"[^"]*"', '"password_hash": "[HASH_FILTERED]"'),
        
        # Email addresses (partial filtering - keep domain)
        (r'\b[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b', r'user@\1'),
        
        # Authorization codes
        (r'"code":\s*"[^"]*"', '"code": "[CODE_FILTERED]"'),
        (r'authorization_code=[a-zA-Z0-9._-]+', 'authorization_code=[FILTERED]'),
    ]
    
    @classmethod
    def filter_sensitive_data(cls, message: str) -> str:
        """Filter sensitive data from a log message"""
        filtered_message = message
        
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            filtered_message = re.sub(pattern, replacement, filtered_message, flags=re.IGNORECASE)
        
        return filtered_message

def privacy_log_filter(record):
    """Loguru filter function that removes sensitive data"""
    if 'message' in record:
        record['message'] = PrivacyLogFilter.filter_sensitive_data(record['message'])
    return True

# Remove default logger
logger.remove()

# Add console logger with privacy filter
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    filter=privacy_log_filter,
    colorize=True
)

# Add file logger with privacy filter and rotation
logger.add(
    "logs/socialify_backend.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="1 week",
    retention="1 month",
    compression="zip",
    filter=privacy_log_filter
)

# Add error-only file logger
logger.add(
    "logs/socialify_errors.log",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="1 week",
    retention="2 months",
    compression="zip",
    filter=privacy_log_filter
)

# Log startup message
logger.info("🔒 Privacy-protected logging initialized - sensitive data will be filtered") 