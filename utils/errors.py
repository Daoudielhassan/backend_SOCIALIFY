"""
Standardized Error Handling - Consistent API Error Responses
Provides uniform error handling patterns across all API endpoints
"""

from typing import Optional, Dict, Any, Union
from fastapi import HTTPException, status
from utils.logger import logger
import traceback

class APIError(HTTPException):
    """
    Standardized API Error with consistent response format
    
    Provides structured error responses with optional details,
    error codes, and automatic logging.
    """
    
    def __init__(
        self,
        status_code: int,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        log_error: bool = True
    ):
        """
        Initialize standardized API error
        
        Args:
            status_code: HTTP status code
            message: Human-readable error message
            details: Additional error details (optional)
            error_code: Machine-readable error code (optional)
            log_error: Whether to log the error (default: True)
        """
        
        # Create structured error detail
        error_detail = {
            "error": True,
            "message": message,
            "status_code": status_code
        }
        
        if error_code:
            error_detail["error_code"] = error_code
            
        if details:
            error_detail["details"] = details
            
        # Add timestamp and API version
        from datetime import datetime
        error_detail["timestamp"] = datetime.utcnow().isoformat()
        error_detail["api_version"] = "v1"
        
        # Log error if requested
        if log_error:
            self._log_error(status_code, message, details, error_code)
            
        super().__init__(status_code=status_code, detail=error_detail)
    
    def _log_error(
        self,
        status_code: int,
        message: str,
        details: Optional[Dict[str, Any]],
        error_code: Optional[str]
    ):
        """Log error with appropriate level based on status code"""
        
        log_data = {
            "status_code": status_code,
            "message": message,
            "error_code": error_code,
            "details": details
        }
        
        if status_code >= 500:
            logger.error(f"Server Error: {message}", extra=log_data)
        elif status_code >= 400:
            logger.warning(f"Client Error: {message}", extra=log_data)
        else:
            logger.info(f"Error Response: {message}", extra=log_data)

# Predefined Error Classes for Common Scenarios

class ValidationError(APIError):
    """Validation error (400)"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=message,
            details=details,
            error_code="VALIDATION_ERROR"
        )

class AuthenticationError(APIError):
    """Authentication error (401)"""
    def __init__(self, message: str = "Authentication required", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message,
            details=details,
            error_code="AUTHENTICATION_ERROR"
        )

class AuthorizationError(APIError):
    """Authorization error (403)"""
    def __init__(self, message: str = "Access forbidden", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            message=message,
            details=details,
            error_code="AUTHORIZATION_ERROR"
        )

class NotFoundError(APIError):
    """Resource not found error (404)"""
    def __init__(self, resource: str = "Resource", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"{resource} not found",
            details=details,
            error_code="NOT_FOUND_ERROR"
        )

class ConflictError(APIError):
    """Resource conflict error (409)"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            message=message,
            details=details,
            error_code="CONFLICT_ERROR"
        )

class RateLimitError(APIError):
    """Rate limit exceeded error (429)"""
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        details = {"retry_after": retry_after} if retry_after else None
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            message=message,
            details=details,
            error_code="RATE_LIMIT_ERROR"
        )

class ServerError(APIError):
    """Internal server error (500)"""
    def __init__(self, message: str = "Internal server error", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=message,
            details=details,
            error_code="SERVER_ERROR"
        )

class ServiceUnavailableError(APIError):
    """Service unavailable error (503)"""
    def __init__(self, service: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            message=f"{service} service unavailable",
            details=details,
            error_code="SERVICE_UNAVAILABLE_ERROR"
        )

# Error Handler Decorators

def handle_api_errors(func):
    """
    Decorator to automatically handle common exceptions and convert them to APIErrors
    
    Usage:
        @handle_api_errors
        async def my_endpoint():
            # Your endpoint logic
    """
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except APIError:
            # Re-raise API errors as-is
            raise
        except ValueError as e:
            raise ValidationError(str(e))
        except PermissionError as e:
            raise AuthorizationError(str(e))
        except FileNotFoundError as e:
            raise NotFoundError("File", {"file_error": str(e)})
        except ConnectionError as e:
            raise ServiceUnavailableError("External service", {"connection_error": str(e)})
        except Exception as e:
            # Log the full traceback for unexpected errors
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            logger.error(traceback.format_exc())
            raise ServerError(
                "An unexpected error occurred",
                {"function": func.__name__, "error_type": type(e).__name__}
            )
    
    return wrapper

# Utility Functions

def create_error_response(
    status_code: int,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standardized error response dictionary
    
    Useful for manual error response creation without raising exceptions
    """
    from datetime import datetime
    
    response = {
        "error": True,
        "message": message,
        "status_code": status_code,
        "timestamp": datetime.utcnow().isoformat(),
        "api_version": "v1"
    }
    
    if error_code:
        response["error_code"] = error_code
        
    if details:
        response["details"] = details
        
    return response

def log_error_context(
    error: Exception,
    context: Dict[str, Any],
    user_id: Optional[int] = None
):
    """
    Log error with additional context information
    
    Args:
        error: The exception that occurred
        context: Additional context (request data, function name, etc.)
        user_id: Optional user ID for tracking
    """
    
    log_data = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context
    }
    
    if user_id:
        log_data["user_id"] = user_id
    
    logger.error("Error with context", extra=log_data)

# Export all error classes and utilities
__all__ = [
    "APIError",
    "ValidationError", 
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ServerError",
    "ServiceUnavailableError",
    "handle_api_errors",
    "create_error_response",
    "log_error_context"
]
