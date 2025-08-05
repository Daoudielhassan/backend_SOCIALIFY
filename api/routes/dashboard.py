from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from db.models import MessageMetadata, User
from api.dependencies import get_db, get_current_user
from datetime import datetime, timedelta
from typing import Dict, Any

router = APIRouter()

@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Get dashboard statistics for the current user"""
    
    now = datetime.utcnow()
    
    # Total messages
    total_messages_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(MessageMetadata.user_id == user.id)
    )
    total_messages = total_messages_result.scalar() or 0
    
    # Messages this week
    week_ago = now - timedelta(days=7)
    week_messages_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.created_at >= week_ago
            )
        )
    )
    week_messages = week_messages_result.scalar() or 0
    
    # Messages today
    today_start = datetime(now.year, now.month, now.day)
    today_messages_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.created_at >= today_start
            )
        )
    )
    today_messages = today_messages_result.scalar() or 0
    
    # High priority messages
    high_priority_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.predicted_priority == 'high'
            )
        )
    )
    high_priority_messages = high_priority_result.scalar() or 0
    
    # Medium priority messages
    medium_priority_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.predicted_priority == 'medium'
            )
        )
    )
    medium_priority_messages = medium_priority_result.scalar() or 0
    
    # Low priority messages
    low_priority_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.predicted_priority == 'low'
            )
        )
    )
    low_priority_messages = low_priority_result.scalar() or 0
    
    # Gmail messages
    gmail_messages_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.source == 'gmail'
            )
        )
    )
    gmail_messages = gmail_messages_result.scalar() or 0
    
    # WhatsApp messages
    whatsapp_messages_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.source == 'whatsapp'
            )
        )
    )
    whatsapp_messages = whatsapp_messages_result.scalar() or 0
    
    # Recent activity (last 5 messages)
    recent_messages_result = await db.execute(
        select(Message).where(
            MessageMetadata.user_id == user.id
        ).order_by(MessageMetadata.created_at.desc()).limit(5)
    )
    recent_messages = recent_messages_result.scalars().all()
    
    # Convert recent messages to dict
    recent_activity = [
        {
            "id": msg.id,
            "source": msg.source,
            "sender": msg.sender,
            "subject": msg.subject,
            "body": msg.body[:100] + "..." if len(msg.body) > 100 else msg.body,
            "predicted_priority": msg.predicted_priority,
            "predicted_context": msg.predicted_context,
            "created_at": msg.created_at.isoformat(),
            "received_at": msg.received_at.isoformat()
        }
        for msg in recent_messages
    ]
    
    # Calculate trends (compared to previous week)
    two_weeks_ago = now - timedelta(days=14)
    prev_week_messages_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.created_at >= two_weeks_ago,
                MessageMetadata.created_at < week_ago
            )
        )
    )
    prev_week_messages = prev_week_messages_result.scalar() or 0
    
    # Calculate percentage change
    if prev_week_messages > 0:
        week_trend = round(((week_messages - prev_week_messages) / prev_week_messages) * 100, 1)
    else:
        week_trend = 100.0 if week_messages > 0 else 0.0
    
    return {
        "totals": {
            "total_messages": total_messages,
            "messages_this_week": week_messages,
            "messages_today": today_messages,
            "week_trend_percentage": week_trend
        },
        "priority_breakdown": {
            "high": high_priority_messages,
            "medium": medium_priority_messages,
            "low": low_priority_messages,
            "unprocessed": total_messages - (high_priority_messages + medium_priority_messages + low_priority_messages)
        },
        "source_breakdown": {
            "gmail": gmail_messages,
            "whatsapp": whatsapp_messages,
            "other": total_messages - (gmail_messages + whatsapp_messages)
        },
        "recent_activity": recent_activity,
        "user_info": {
            "email": user.email,
            "full_name": user.full_name,
            "auth_method": user.auth_method,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
    }
