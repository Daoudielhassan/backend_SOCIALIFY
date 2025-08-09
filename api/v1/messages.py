"""
API v1 Messages Routes - Consolidated Message Operations
All message-related endpoints in one clean, RESTful interface
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func
from typing import Dict, Any, List, Optional

from api.dependencies import get_db, get_current_user
from db.models import User, MessageMetadata
from services.emailServices import email_service
from services.analytics import analytics_service
from services.privacy import privacy_service
from utils.errors import (
    APIError, NotFoundError, ValidationError, ServerError,
    handle_api_errors
)
from utils.logger import logger
from datetime import datetime, timedelta

router = APIRouter()

# =============================================================================
# Message Listing and Search
# =============================================================================

@router.get("/")
async def list_messages(
    limit: int = Query(default=20, ge=1, le=100, description="Number of messages to return"),
    offset: int = Query(default=0, ge=0, description="Number of messages to skip"),
    source: Optional[str] = Query(default=None, description="Filter by source (gmail, whatsapp)"),
    priority: Optional[str] = Query(default=None, description="Filter by priority"),
    context: Optional[str] = Query(default=None, description="Filter by context"),
    search: Optional[str] = Query(default=None, description="Search in subject/sender domain"),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to search"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    List messages for the current user with filtering and search
    
    Args:
        limit: Number of messages to return (1-100)
        offset: Number of messages to skip for pagination
        source: Filter by message source
        priority: Filter by predicted priority
        context: Filter by predicted context
        search: Search term for subject/sender domain
        days: Number of days to search back
        
    Returns:
        Paginated list of privacy-protected message metadata
    """
    try:
        # Build query conditions
        conditions = [MessageMetadata.user_id == user.id]
        
        # Date range filter
        start_date = datetime.utcnow() - timedelta(days=days)
        conditions.append(MessageMetadata.received_at >= start_date)
        
        # Source filter
        if source:
            conditions.append(MessageMetadata.source == source)
        
        # Priority filter
        if priority:
            conditions.append(MessageMetadata.predicted_priority == priority)
        
        # Context filter
        if context:
            conditions.append(MessageMetadata.predicted_context == context)
        
        # Search filter (privacy-safe: only subject preview and sender domain)
        if search:
            search_conditions = [
                MessageMetadata.subject_preview.ilike(f"%{search}%"),
                MessageMetadata.sender_domain.ilike(f"%{search}%")
            ]
            conditions.append(or_(*search_conditions))
        
        # Execute query with pagination
        query = (
            select(MessageMetadata)
            .where(and_(*conditions))
            .order_by(desc(MessageMetadata.received_at))
            .offset(offset)
            .limit(limit)
        )
        
        result = await db.execute(query)
        messages = result.scalars().all()
        
        # Convert to privacy-safe response format
        message_list = []
        for msg in messages:
            message_list.append({
                "id": msg.id,
                "source": msg.source,
                "sender_domain": msg.sender_domain,  # Domain only for privacy
                "subject_preview": msg.subject_preview,  # Preview only
                "received_at": msg.received_at.isoformat() if msg.received_at else None,
                "predicted_priority": msg.predicted_priority,
                "predicted_context": msg.predicted_context,
                "prediction_confidence": msg.prediction_confidence,
                "processed_at": msg.processed_at.isoformat() if msg.processed_at else None,
                "privacy_protected": True
            })
        
        # Get total count for pagination
        count_query = select(MessageMetadata).where(and_(*conditions))
        count_result = await db.execute(count_query)
        total_count = len(count_result.scalars().all())
        
        return {
            "messages": message_list,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total_count,
                "has_more": offset + limit < total_count
            },
            "filters": {
                "source": source,
                "priority": priority,
                "context": context,
                "search": search,
                "days": days
            },
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error listing messages: {str(e)}")
        raise ServerError("Failed to list messages")

@router.get("/processed")
async def get_processed_messages(
    limit: int = Query(default=20, ge=1, le=100, description="Number of messages to return"),
    offset: int = Query(default=0, ge=0, description="Number of messages to skip"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get processed messages for the current user
    
    Args:
        limit: Number of messages to return (1-100)
        offset: Number of messages to skip for pagination
        db: Database session
        user: Current authenticated user
        
    Returns:
        List of processed messages with metadata
    """
    try:
        # Query processed messages (ones with predictions)
        query = select(MessageMetadata).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.predicted_priority.isnot(None)
            )
        ).order_by(desc(MessageMetadata.processed_at)).limit(limit).offset(offset)
        
        result = await db.execute(query)
        messages = result.scalars().all()
        
        # Format messages
        message_list = []
        for msg in messages:
            message_list.append({
                "id": msg.id,
                "source": msg.source,
                "sender_domain": msg.sender_domain,
                "subject_preview": msg.subject_preview,
                "predicted_priority": msg.predicted_priority,
                "predicted_context": msg.predicted_context,
                "prediction_confidence": msg.prediction_confidence,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "processed_at": msg.processed_at.isoformat() if msg.processed_at else None,
                "received_at": msg.received_at.isoformat() if msg.received_at else None,
            })
        
        # Get total count for pagination
        count_query = select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.predicted_priority.isnot(None)
            )
        )
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0
        
        return {
            "messages": message_list,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total_count,
                "has_next": offset + limit < total_count
            },
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error fetching processed messages: {str(e)}")
        raise ServerError("Failed to fetch processed messages")

@router.get("/{message_id}")
async def get_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get detailed message metadata by ID
    
    Args:
        message_id: Message ID to retrieve
        
    Returns:
        Detailed privacy-protected message metadata
    """
    try:
        # Get message with user ownership check
        query = await db.execute(
            select(MessageMetadata).where(
                and_(
                    MessageMetadata.id == message_id,
                    MessageMetadata.user_id == user.id
                )
            )
        )
        message = query.scalar_one_or_none()
        
        if not message:
            raise NotFoundError("Message not found")
        
        return {
            "id": message.id,
            "user_id": message.user_id,
            "source": message.source,
            "external_id": message.external_id,
            "sender_domain": message.sender_domain,
            "subject_preview": message.subject_preview,
            "received_at": message.received_at.isoformat() if message.received_at else None,
            "predicted_priority": message.predicted_priority,
            "predicted_context": message.predicted_context,
            "prediction_confidence": message.prediction_confidence,
            "feedback_priority": message.feedback_priority,
            "feedback_context": message.feedback_context,
            "used_in_retrain": message.used_in_retrain,
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "processed_at": message.processed_at.isoformat() if message.processed_at else None,
            "privacy_protected": True,
            "note": "Content not stored for privacy compliance",
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message {message_id}: {str(e)}")
        raise ServerError("Failed to get message")

# =============================================================================
# Message Operations
# =============================================================================

@router.post("/fetch")
async def fetch_messages(
    source: str = Query(default="all", description="Source to fetch from (gmail, whatsapp, all)"),
    max_messages: int = Query(default=50, ge=1, le=200, description="Maximum messages to fetch"),
    force_sync: bool = Query(default=False, description="Force synchronization"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Fetch new messages from external sources
    
    Args:
        source: Source to fetch from (gmail, whatsapp, all)
        max_messages: Maximum messages to fetch
        force_sync: Force synchronization
        
    Returns:
        Fetch results with privacy protection
    """
    try:
        fetched_results = []
        errors = []
        
        # Gmail fetching
        if source in ["gmail", "all"]:
            if not user.gmail_token_encrypted and not user.gmail_token:
                errors.append("Gmail not connected. Please connect your Gmail account first.")
            else:
                try:
                    gmail_result = await email_service.fetch_messages_for_user(
                        user=user,
                        db=db,
                        provider="gmail",
                        max_results=max_messages,
                        privacy_mode=True
                    )
                    
                    if "error" not in gmail_result:
                        fetched_results.append({
                            "source": "gmail",
                            "processed": gmail_result.get("processed", 0),
                            "mode": gmail_result.get("mode", "privacy"),
                            "privacy_protected": True
                        })
                    else:
                        errors.append(f"Gmail fetch error: {gmail_result['error']}")
                        
                except Exception as e:
                    errors.append(f"Gmail fetch error: {str(e)}")
        
        # WhatsApp fetching (future implementation)
        if source in ["whatsapp", "all"]:
            errors.append("WhatsApp integration not yet implemented")
        
        # Get updated message summary
        recent_query = await db.execute(
            select(MessageMetadata)
            .where(MessageMetadata.user_id == user.id)
            .order_by(desc(MessageMetadata.received_at))
            .limit(10)
        )
        recent_messages = recent_query.scalars().all()
        
        return {
            "operation": "fetch_messages",
            "source": source,
            "max_messages": max_messages,
            "force_sync": force_sync,
            "results": fetched_results,
            "errors": errors,
            "total_processed": sum(r.get("processed", 0) for r in fetched_results),
            "recent_messages_count": len(recent_messages),
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error fetching messages: {str(e)}")
        raise ServerError("Failed to fetch messages")

@router.delete("/{message_id}")
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Delete a message metadata record
    
    Args:
        message_id: Message ID to delete
        
    Returns:
        Deletion confirmation
    """
    try:
        # Get message with user ownership check
        query = await db.execute(
            select(MessageMetadata).where(
                and_(
                    MessageMetadata.id == message_id,
                    MessageMetadata.user_id == user.id
                )
            )
        )
        message = query.scalar_one_or_none()
        
        if not message:
            raise NotFoundError("Message not found")
        
        # Delete the message metadata
        await db.delete(message)
        await db.commit()
        
        logger.info(f"Deleted message metadata {message_id} for user {user.id}")
        
        return {
            "operation": "delete_message",
            "message_id": message_id,
            "status": "deleted",
            "note": "Metadata deleted - no content was stored",
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting message {message_id}: {str(e)}")
        raise ServerError("Failed to delete message")

# =============================================================================
# Message Analytics
# =============================================================================

@router.get("/analytics/summary")
async def get_message_analytics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    source: Optional[str] = Query(default=None, description="Filter by source"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get comprehensive message analytics and insights
    
    Args:
        days: Number of days to analyze
        source: Optional source filter
        
    Returns:
        Comprehensive analytics data
    """
    try:
        # Get user analytics from unified service
        analytics_data = await analytics_service.get_user_analytics(
            user_id=user.id,
            db=db,
            days=days
        )
        
        # Add source-specific filtering if requested
        filtered_analytics = analytics_data
        if source:
            # Note: This would require additional filtering logic
            # For now, we return all analytics with source indication
            filtered_analytics["source_filter"] = source
        
        return {
            "operation": "message_analytics",
            "user_id": user.id,
            "period_days": days,
            "source_filter": source,
            "analytics": filtered_analytics,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting message analytics: {str(e)}")
        raise ServerError("Failed to get analytics")

# =============================================================================
# Message Feedback and Training
# =============================================================================

@router.post("/{message_id}/feedback")
async def submit_message_feedback(
    message_id: int,
    feedback_priority: Optional[str] = Query(default=None, description="Correct priority"),
    feedback_context: Optional[str] = Query(default=None, description="Correct context"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Submit user feedback for message prediction improvement
    
    Args:
        message_id: Message ID to provide feedback for
        feedback_priority: Correct priority classification
        feedback_context: Correct context classification
        
    Returns:
        Feedback submission confirmation
    """
    try:
        # Verify message ownership
        query = await db.execute(
            select(MessageMetadata).where(
                and_(
                    MessageMetadata.id == message_id,
                    MessageMetadata.user_id == user.id
                )
            )
        )
        message = query.scalar_one_or_none()
        
        if not message:
            raise NotFoundError("Message not found")
        
        # Submit feedback using analytics service
        feedback_result = await analytics_service.record_user_feedback(
            message_id=message_id,
            feedback_priority=feedback_priority,
            feedback_context=feedback_context,
            db=db
        )
        
        return {
            "operation": "submit_feedback",
            "message_id": message_id,
            "feedback": {
                "priority": feedback_priority,
                "context": feedback_context
            },
            "result": feedback_result,
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback for message {message_id}: {str(e)}")
        raise ServerError("Failed to submit feedback")
