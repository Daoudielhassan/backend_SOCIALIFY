"""
Email Services Module
Handles all email-related operations including Gmail integration, OAuth, and optimized processing
"""

from .email_service import HighPerformanceEmailService, email_service
from .gmail_oauth import GmailOAuthService

__all__ = [
    "HighPerformanceEmailService",
    "email_service", 
    "GmailOAuthService"
]
