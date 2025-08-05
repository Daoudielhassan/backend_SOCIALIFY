"""
API v1 Package - Consolidated Route Structure
Provides clean, RESTful API organization with proper versioning
"""

from fastapi import APIRouter
from .gmail import router as gmail_router
from .messages import router as messages_router
from .prediction import router as prediction_router
from .user import router as user_router
from .analytics import router as analytics_router

# Create the main v1 router
v1_router = APIRouter(prefix="/api/v1")

# Include all v1 sub-routers
v1_router.include_router(gmail_router, prefix="/gmail", tags=["gmail-v1"])
v1_router.include_router(messages_router, prefix="/messages", tags=["messages-v1"])
v1_router.include_router(prediction_router, prefix="/prediction", tags=["prediction-v1"])
v1_router.include_router(user_router, prefix="/user", tags=["user-v1"])
v1_router.include_router(analytics_router, prefix="/analytics", tags=["analytics-v1"])

# Export individual routers for direct import
__all__ = [
    "v1_router",
    "gmail_router",
    "messages_router",
    "prediction_router", 
    "user_router",
    "analytics_router"
]

__all__ = ["v1_router"]
