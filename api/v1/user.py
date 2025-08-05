"""
API v1 User Routes - User Management and Settings
Consolidated user operations with privacy focus
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Dict, Any, Optional
from pydantic import BaseModel, EmailStr

from api.dependencies import get_db, get_current_user
from db.models import User
from services.privacy import privacy_service
from utils.errors import (
    APIError, ValidationError, ServerError, AuthorizationError,
    handle_api_errors
)
from utils.logger import logger
from datetime import datetime

router = APIRouter()

# =============================================================================
# Request/Response Models
# =============================================================================

class UserUpdateRequest(BaseModel):
    """Request model for user profile updates"""
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None

class PrivacyPreferencesRequest(BaseModel):
    """Request model for privacy preference updates"""
    data_retention_days: Optional[int] = None
    enable_analytics: Optional[bool] = None
    enable_predictions: Optional[bool] = None
    share_aggregate_data: Optional[bool] = None
    encryption_level: Optional[str] = None

# =============================================================================
# User Profile Management
# =============================================================================

@router.get("/profile")
async def get_user_profile(
    user = Depends(get_current_user)
):
    """
    Get current user profile information
    
    Returns:
        Privacy-protected user profile data
    """
    try:
        return {
            "operation": "get_profile",
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "is_active": user.is_active,
                "gmail_connected": bool(user.gmail_token_encrypted),
                "preferences": user.preferences or {},
                "privacy_protected": True
            },
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        raise ServerError("Failed to get user profile")

@router.put("/profile")
async def update_user_profile(
    request: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Update user profile information
    
    Args:
        request: Profile update data
        
    Returns:
        Updated user profile
    """
    try:
        # Update user fields
        if request.email is not None:
            user.email = request.email
        if request.first_name is not None:
            user.first_name = request.first_name
        if request.last_name is not None:
            user.last_name = request.last_name
        if request.preferences is not None:
            # Merge with existing preferences
            current_prefs = user.preferences or {}
            current_prefs.update(request.preferences)
            user.preferences = current_prefs
        
        # Save changes
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Updated profile for user {user.id}")
        
        return {
            "operation": "update_profile",
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "preferences": user.preferences or {},
                "updated_at": datetime.utcnow().isoformat(),
                "privacy_protected": True
            },
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error updating user profile: {str(e)}")
        await db.rollback()
        raise ServerError("Failed to update user profile")

# =============================================================================
# Privacy Settings and Data Management
# =============================================================================

@router.get("/privacy")
async def get_privacy_settings(
    user = Depends(get_current_user)
):
    """
    Get user privacy settings and data handling preferences
    
    Returns:
        Current privacy settings and data summary
    """
    try:
        # Get privacy summary from privacy service
        privacy_summary = await privacy_service.get_user_privacy_summary(user_id=user.id)
        
        return {
            "operation": "get_privacy_settings",
            "user_id": user.id,
            "privacy_settings": {
                "data_retention_days": user.preferences.get("data_retention_days", 90) if user.preferences else 90,
                "enable_analytics": user.preferences.get("enable_analytics", True) if user.preferences else True,
                "enable_predictions": user.preferences.get("enable_predictions", True) if user.preferences else True,
                "share_aggregate_data": user.preferences.get("share_aggregate_data", False) if user.preferences else False,
                "encryption_level": user.preferences.get("encryption_level", "standard") if user.preferences else "standard"
            },
            "privacy_summary": privacy_summary,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting privacy settings: {str(e)}")
        raise ServerError("Failed to get privacy settings")

@router.put("/privacy")
async def update_privacy_settings(
    request: PrivacyPreferencesRequest,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Update user privacy preferences
    
    Args:
        request: Privacy preference updates
        
    Returns:
        Updated privacy settings
    """
    try:
        # Get current preferences
        current_prefs = user.preferences or {}
        
        # Update privacy preferences
        if request.data_retention_days is not None:
            if not (1 <= request.data_retention_days <= 3650):  # 1 day to 10 years
                raise ValidationError("Data retention must be between 1 and 3650 days")
            current_prefs["data_retention_days"] = request.data_retention_days
            
        if request.enable_analytics is not None:
            current_prefs["enable_analytics"] = request.enable_analytics
            
        if request.enable_predictions is not None:
            current_prefs["enable_predictions"] = request.enable_predictions
            
        if request.share_aggregate_data is not None:
            current_prefs["share_aggregate_data"] = request.share_aggregate_data
            
        if request.encryption_level is not None:
            if request.encryption_level not in ["basic", "standard", "enhanced"]:
                raise ValidationError("Invalid encryption level")
            current_prefs["encryption_level"] = request.encryption_level
        
        # Save updated preferences
        user.preferences = current_prefs
        await db.commit()
        await db.refresh(user)
        
        # Log privacy settings change
        await privacy_service.log_privacy_action(
            user_id=user.id,
            action="privacy_settings_updated",
            details={"updated_fields": list(request.dict(exclude_unset=True).keys())}
        )
        
        logger.info(f"Updated privacy settings for user {user.id}")
        
        return {
            "operation": "update_privacy_settings",
            "user_id": user.id,
            "updated_settings": current_prefs,
            "updated_at": datetime.utcnow().isoformat(),
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating privacy settings: {str(e)}")
        await db.rollback()
        raise ServerError("Failed to update privacy settings")

@router.post("/privacy/export")
async def export_user_data(
    format: str = Query(default="json", description="Export format (json, csv)"),
    include_metadata: bool = Query(default=True, description="Include message metadata"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Export user data for GDPR compliance
    
    Args:
        format: Export format (json, csv)
        include_metadata: Include message metadata
        
    Returns:
        Data export information and download link
    """
    try:
        if format not in ["json", "csv"]:
            raise ValidationError("Invalid export format. Use 'json' or 'csv'")
        
        # Use privacy service for data export
        export_result = await privacy_service.export_user_data(
            user_id=user.id,
            db=db,
            format=format,
            include_metadata=include_metadata
        )
        
        return {
            "operation": "export_user_data",
            "user_id": user.id,
            "export_format": format,
            "include_metadata": include_metadata,
            "result": export_result,
            "privacy_compliant": True,
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting user data: {str(e)}")
        raise ServerError("Failed to export user data")

@router.delete("/privacy/purge")
async def purge_user_data(
    confirm: bool = Query(default=False, description="Confirmation required"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Purge user data for GDPR right to erasure
    
    Args:
        confirm: Confirmation required for data purge
        
    Returns:
        Data purge status and summary
    """
    try:
        if not confirm:
            raise HTTPException(
                status_code=400, 
                detail="Data purge requires explicit confirmation. Set confirm=true"
            )
        
        # Use privacy service for data purge
        purge_result = await privacy_service.purge_user_data(
            user_id=user.id,
            db=db
        )
        
        return {
            "operation": "purge_user_data",
            "user_id": user.id,
            "confirmed": confirm,
            "result": purge_result,
            "privacy_compliant": True,
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error purging user data: {str(e)}")
        raise ServerError("Failed to purge user data")

# =============================================================================
# Account Connection Management
# =============================================================================

@router.get("/connections")
async def get_account_connections(
    user = Depends(get_current_user)
):
    """
    Get status of external account connections
    
    Returns:
        Account connection status summary
    """
    try:
        connections = {
            "gmail": {
                "connected": bool(user.gmail_token_encrypted),
                "encrypted": bool(user.gmail_token_encrypted),
                "status": "active" if user.gmail_token_encrypted else "disconnected"
            },
            "whatsapp": {
                "connected": False,  # Future implementation
                "status": "not_implemented"
            }
        }
        
        return {
            "operation": "get_connections",
            "user_id": user.id,
            "connections": connections,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting account connections: {str(e)}")
        raise ServerError("Failed to get account connections")

@router.delete("/connections/{provider}")
async def disconnect_account(
    provider: str,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Disconnect an external account
    
    Args:
        provider: Provider to disconnect (gmail, whatsapp)
        
    Returns:
        Disconnection status
    """
    try:
        if provider not in ["gmail", "whatsapp"]:
            raise ValidationError("Invalid provider")
        
        if provider == "gmail":
            # Clear Gmail tokens
            user.gmail_token = None
            user.gmail_token_encrypted = None
            await db.commit()
            
            logger.info(f"Disconnected Gmail for user {user.id}")
            
            return {
                "operation": "disconnect_account",
                "provider": provider,
                "user_id": user.id,
                "status": "disconnected",
                "api_version": "v1"
            }
        
        elif provider == "whatsapp":
            # Future implementation
            raise APIError(501, "WhatsApp disconnection not yet implemented", error_code="NOT_IMPLEMENTED")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting {provider}: {str(e)}")
        await db.rollback()
        raise ServerError(f"Failed to disconnect {provider}")

# =============================================================================
# User Statistics and Activity
# =============================================================================

@router.get("/stats")
async def get_user_statistics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get user activity statistics and summary
    
    Args:
        days: Number of days to analyze
        
    Returns:
        User activity statistics
    """
    try:
        # Get basic user statistics
        from sqlalchemy import func
        from db.models import MessageMetadata
        from datetime import datetime, timedelta
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Message counts
        message_query = await db.execute(
            select(func.count(MessageMetadata.id))
            .where(and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.received_at >= start_date
            ))
        )
        message_count = message_query.scalar() or 0
        
        # Source breakdown
        source_query = await db.execute(
            select(MessageMetadata.source, func.count(MessageMetadata.id))
            .where(and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.received_at >= start_date
            ))
            .group_by(MessageMetadata.source)
        )
        source_breakdown = dict(source_query.fetchall())
        
        return {
            "operation": "get_user_stats",
            "user_id": user.id,
            "period_days": days,
            "statistics": {
                "total_messages": message_count,
                "messages_by_source": source_breakdown,
                "account_age_days": (datetime.utcnow() - user.created_at).days if user.created_at else 0,
                "privacy_mode": True,
                "connections": {
                    "gmail": bool(user.gmail_token or user.gmail_token_encrypted)
                }
            },
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting user statistics: {str(e)}")
        raise ServerError("Failed to get user statistics")
