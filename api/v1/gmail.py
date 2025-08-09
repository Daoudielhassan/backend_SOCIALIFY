"""
API v1 Gmail Routes - Consolidated Gmail Operations  
All Gmail-related endpoints with standardized error handling and optimized services
"""

from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, List, Optional

from api.dependencies import get_db, get_current_user
from db.models import User, MessageMetadata
from services.emailServices import email_service
from services.privacy import privacy_service
from services.analytics import analytics_service
from utils.errors import (
    APIError, NotFoundError, ValidationError, ServerError, AuthorizationError, AuthenticationError,
    handle_api_errors
)
from utils.logger import logger
from config.settings import settings
from services.scheduler import gmail_scheduler_service
from utils.logger import logger

router = APIRouter()

# =============================================================================
# Gmail Connection Management
# =============================================================================

@router.get("/status")
async def get_gmail_status(
    user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive Gmail connection status for current user
    
    Returns:
        Detailed Gmail connection and service status
    """
    try:
        # Check user's Gmail connection
        has_encrypted_token = bool(user.gmail_token_encrypted)
        is_connected = has_encrypted_token
        
        # Get recent message count
        recent_messages_query = await db.execute(
            select(MessageMetadata).where(
                MessageMetadata.user_id == user.id,
                MessageMetadata.source == 'gmail'
            ).limit(1)
        )
        has_messages = recent_messages_query.first() is not None
        
        # AI engine status (simplified - always available)
        ai_status = "active"
        
        return {
            "user_id": user.id,
            "email": privacy_service.anonymize_email(user.email),
            "connection": {
                "status": "connected" if is_connected else "disconnected",
                "token_type": "encrypted" if has_encrypted_token else "none",
                "migration_needed": False  # No legacy tokens in current model
            },
            "data": {
                "has_messages": has_messages,
                "privacy_mode": "enabled"
            },
            "services": {
                "email_service": "active",
                "ai_engine": ai_status,
                "scheduler": "active" if gmail_scheduler_service.is_running else "inactive"
            },
            "privacy_compliant": True
        }
        
    except Exception as e:
        logger.error(f"Error getting Gmail status: {str(e)}")
        raise ServerError("Failed to get Gmail status")

@router.get("/providers")
async def get_supported_providers():
    """
    Get list of supported email providers
    
    Returns:
        List of supported email providers and their capabilities
    """
    providers = email_service.get_supported_providers()
    
    provider_details = []
    for provider in providers:
        status = await email_service.get_provider_status(provider)
        provider_details.append(status)
    
    return {
        "supported_providers": providers,
        "provider_details": provider_details,
        "primary_provider": "gmail"
    }

# =============================================================================
# Gmail Message Operations
# =============================================================================

@router.post("/fetch")
async def fetch_gmail_messages(
    max_messages: int = Query(default=50, ge=1, le=200, description="Maximum messages to fetch"),
    force_sync: bool = Query(default=False, description="Force synchronization"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Fetch messages from Gmail for the current user

    Args:
        max_messages: Maximum number of messages to fetch (1-200)
        force_sync: Force synchronization even if recently synced

    Returns:
        Fetch results with privacy protection
    """
    try:
        logger.info(f"📧 Starting Gmail fetch for user {user.id}, max_messages: {max_messages}")
        
        # Check if user has encrypted token
        if not user.gmail_token_encrypted:
            logger.error(f"❌ User {user.id} has no Gmail token")
            raise AuthenticationError("Gmail account not connected. Please connect your Gmail account first.")
        
        logger.info(f"🔑 User {user.id} has encrypted Gmail token")
        
        # Fetch messages using unified email service
        result = await email_service.fetch_messages_for_user(
            user=user,
            db=db,
            provider="gmail",
            max_results=max_messages,
            privacy_mode=True
        )
        
        logger.info(f"📧 Email service returned: {type(result)}")
        
        # If underlying service returned an error, propagate as auth error
        if isinstance(result, dict) and result.get("error"):
            logger.error(f"❌ Email service error: {result.get('error')}")
            raise AuthenticationError(result.get("error"))
        
        return {
            "operation": "gmail_fetch",
            "user_id": user.id,
            "requested_max": max_messages,
            "force_sync": force_sync,
            "result": result,
            "privacy_protected": True,
            "api_version": "v1"
        }
    except Exception as e:
        logger.error(f"Error fetching Gmail messages: {str(e)}")
        raise ServerError("Failed to fetch Gmail messages")

@router.post("/fetch/all")
async def fetch_all_users_gmail(
    background_tasks: BackgroundTasks,
    admin_key: str = Query(..., description="Admin access key"),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger Gmail fetch for all users (Admin only)
    
    Args:
        admin_key: Administrative access key
        background_tasks: FastAPI background tasks
        
    Returns:
        Operation status
    """
    # Simple admin key check (in production, use proper admin authentication)
    import os
    if admin_key != os.getenv("ADMIN_KEY", "admin123"):
        raise AuthorizationError("Invalid admin key")
    
    try:
        # Run scheduler once in background
        background_tasks.add_task(gmail_scheduler_service.run_once)
        
        return {
            "operation": "fetch_all_users",
            "status": "started",
            "message": "Gmail fetch for all users started in background",
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error starting Gmail fetch for all users: {str(e)}")
        raise ServerError("Failed to start background fetch")

# =============================================================================
# Gmail Analytics and Insights
# =============================================================================

@router.get("/analytics")
async def get_gmail_analytics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get Gmail-specific analytics for the current user
    
    Args:
        days: Number of days to analyze (1-365)
        
    Returns:
        Gmail analytics data
    """
    try:
        # Get analytics filtered for Gmail only
        analytics_data = await analytics_service.get_user_analytics(
            user_id=user.id,
            db=db,
            days=days,
            metrics=[
                "message_count", "priority_distribution", 
                "sender_patterns", "time_patterns"
            ]
        )
        
        # Filter for Gmail-specific data
        gmail_analytics = {
            "source": "gmail",
            "user_id": user.id,
            "period_days": days,
            "gmail_metrics": analytics_data.get("metrics", {}),
            "privacy_protected": True,
            "api_version": "v1"
        }
        
        return gmail_analytics
        
    except Exception as e:
        logger.error(f"Error getting Gmail analytics: {str(e)}")
        raise ServerError("Failed to get Gmail analytics")

# =============================================================================
# Gmail Testing and Diagnostics
# =============================================================================

@router.post("/test/connection")
async def test_gmail_connection(
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Test Gmail connection and functionality
    
    Returns:
        Comprehensive connection test results
    """
    try:
        # Use the comprehensive test from the test service
        from api.routes.test import comprehensive_gmail_test
        
        test_result = await comprehensive_gmail_test(
            max_messages=5,
            db=db,
            user=user
        )
        
        return {
            "operation": "connection_test",
            "test_results": test_result,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error testing Gmail connection: {str(e)}")
        raise ServerError("Connection test failed")

@router.get("/test/ai-engine")
async def test_ai_engine():
    """
    Test AI engine connectivity and performance
    
    Returns:
        AI engine status and performance metrics
    """
    try:
        ai_status = await analytics_service._check_ai_engine_status()
        
        return {
            "operation": "ai_engine_test",
            "ai_engine": ai_status,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error testing AI engine: {str(e)}")
        raise ServerError("AI engine test failed")

# =============================================================================
# Gmail Privacy and Compliance
# =============================================================================

@router.get("/privacy/audit")
async def audit_gmail_privacy(
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Audit Gmail data for privacy compliance
    
    Returns:
        Privacy audit results for Gmail data
    """
    try:
        # Get overall privacy audit
        audit_result = await privacy_service.audit_database_privacy(db)
        
        # Generate privacy report
        privacy_report = privacy_service.generate_privacy_report(audit_result)
        
        return {
            "operation": "privacy_audit",
            "user_id": user.id,
            "audit_results": privacy_report,
            "gmail_specific": {
                "content_storage": "disabled",
                "metadata_only": "enabled",
                "encryption": "active"
            },
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error auditing Gmail privacy: {str(e)}")
        raise ServerError("Privacy audit failed")

@router.post("/privacy/cleanup")
async def cleanup_gmail_data(
    retention_days: int = Query(default=90, ge=30, le=365, description="Data retention days"),
    confirm: bool = Query(default=False, description="Confirm data cleanup"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Clean up old Gmail metadata according to retention policy
    
    Args:
        retention_days: Number of days to retain data (30-365)
        confirm: Confirmation flag for data cleanup
        
    Returns:
        Cleanup results
    """
    if not confirm:
        return {
            "operation": "cleanup_preview",
            "message": "Add ?confirm=true to execute cleanup",
            "retention_days": retention_days,
            "api_version": "v1"
        }
    
    try:
        cleanup_result = await privacy_service.cleanup_old_data(db, retention_days)
        
        return {
            "operation": "data_cleanup",
            "user_id": user.id,
            "cleanup_results": cleanup_result,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up Gmail data: {str(e)}")
        raise ServerError("Data cleanup failed")
