from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from db.models import MessageMetadata, User
from api.dependencies import get_db, get_current_user
from services.analytics import analytics_service
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

router = APIRouter()

@router.get("/stats")
async def get_dashboard_stats(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Get enhanced dashboard statistics with advanced analytics"""
    
    try:
        # Get comprehensive analytics from the analytics service
        analytics = await analytics_service.get_user_analytics_optimized(
            user_id=user.id,
            db=db,
            days=days
        )
        
        # Get message trends for time-series data
        trends = await analytics_service.get_message_trends_optimized(
            user_id=user.id,
            db=db,
            days=days,
            granularity="daily"
        )
        
        # Get prediction performance metrics
        prediction_metrics = await analytics_service.get_model_performance(
            user_id=user.id,
            days=days
        )
        
        # Get recent messages with enhanced metadata
        recent_messages_result = await db.execute(
            select(MessageMetadata).where(
                MessageMetadata.user_id == user.id
            ).order_by(MessageMetadata.received_at.desc()).limit(10)
        )
        recent_messages = recent_messages_result.scalars().all()
        
        # Privacy-safe recent activity
        recent_activity = [
            {
                "id": msg.id,
                "source": msg.source,
                "sender_domain": msg.sender_domain,  # Domain only for privacy
                "subject_preview": msg.subject_preview,  # Preview only
                "predicted_priority": msg.predicted_priority,
                "predicted_context": msg.predicted_context,
                "prediction_confidence": msg.prediction_confidence,
                "received_at": msg.received_at.isoformat() if msg.received_at else None,
                "processed_at": msg.processed_at.isoformat() if msg.processed_at else None
            }
            for msg in recent_messages
        ]
        
        # Quick stats from current analytics
        total_messages = analytics.get("total_messages", 0)
        messages_by_source = analytics.get("messages_by_source", {})
        priority_distribution = analytics.get("priority_distribution", {})
        context_distribution = analytics.get("context_distribution", {})
        
        # Calculate quick metrics
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        week_ago = now - timedelta(days=7)
        
        # Messages today (from recent messages)
        messages_today = len([
            msg for msg in recent_messages 
            if msg.received_at and msg.received_at >= today_start
        ])
        
        # Messages this week (from recent messages or estimate from trends)
        messages_this_week = len([
            msg for msg in recent_messages 
            if msg.received_at and msg.received_at >= week_ago
        ])
        
        # Calculate trend from analytics data
        daily_trends = trends.get("daily_trends", {}) if trends else {}
        week_trend = 0.0
        if daily_trends:
            recent_days = list(daily_trends.values())[-7:] if len(daily_trends) >= 7 else []
            previous_days = list(daily_trends.values())[-14:-7] if len(daily_trends) >= 14 else []
            
            if recent_days and previous_days:
                recent_avg = sum(recent_days) / len(recent_days)
                previous_avg = sum(previous_days) / len(previous_days)
                if previous_avg > 0:
                    week_trend = round(((recent_avg - previous_avg) / previous_avg) * 100, 1)
        
        return {
            "overview": {
                "total_messages": total_messages,
                "messages_today": messages_today,
                "messages_this_week": messages_this_week,
                "week_trend_percentage": week_trend,
                "analysis_period_days": days
            },
            "analytics": {
                "priority_distribution": {
                    "high": priority_distribution.get("high", 0),
                    "medium": priority_distribution.get("medium", 0),
                    "low": priority_distribution.get("low", 0),
                    "unprocessed": total_messages - sum(priority_distribution.values())
                },
                "context_distribution": context_distribution,
                "source_breakdown": {
                    "gmail": messages_by_source.get("gmail", 0),
                    "whatsapp": messages_by_source.get("whatsapp", 0),
                    "other": messages_by_source.get("other", 0)
                },
                "prediction_accuracy": {
                    "avg_confidence": analytics.get("prediction_accuracy", {}).get("avg_confidence", 0.0),
                    "model_performance": prediction_metrics
                }
            },
            "trends": {
                "daily_trends": daily_trends,
                "insights": analytics.get("insights", [])
            },
            "recent_activity": recent_activity,
            "user_info": {
                "email": user.email,
                "full_name": user.full_name,
                "auth_method": user.auth_method,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "created_at": user.created_at.isoformat() if user.created_at else None
            },
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        # Fallback to basic stats if analytics service fails
        return await get_basic_dashboard_stats(db, user, days)


async def get_basic_dashboard_stats(db: AsyncSession, user, days: int):
    """Fallback function for basic dashboard stats"""
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # Total messages
    total_messages_result = await db.execute(
        select(func.count(MessageMetadata.id)).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.received_at >= start_date
            )
        )
    )
    total_messages = total_messages_result.scalar() or 0
    
    # Quick priority breakdown
    priority_result = await db.execute(
        select(
            MessageMetadata.predicted_priority,
            func.count(MessageMetadata.id)
        ).where(
            and_(
                MessageMetadata.user_id == user.id,
                MessageMetadata.received_at >= start_date
            )
        ).group_by(MessageMetadata.predicted_priority)
    )
    
    priority_breakdown = {"high": 0, "medium": 0, "low": 0}
    for priority, count in priority_result:
        if priority in priority_breakdown:
            priority_breakdown[priority] = count
    
    return {
        "overview": {
            "total_messages": total_messages,
            "messages_today": 0,
            "messages_this_week": 0,
            "week_trend_percentage": 0.0,
            "analysis_period_days": days
        },
        "analytics": {
            "priority_distribution": priority_breakdown,
            "context_distribution": {},
            "source_breakdown": {"gmail": 0, "whatsapp": 0, "other": 0},
            "prediction_accuracy": {"avg_confidence": 0.0}
        },
        "trends": {"daily_trends": {}, "insights": ["Analytics service temporarily unavailable"]},
        "recent_activity": [],
        "user_info": {
            "email": user.email,
            "full_name": user.full_name,
            "auth_method": user.auth_method,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "created_at": user.created_at.isoformat() if user.created_at else None
        },
        "privacy_protected": True,
        "api_version": "v1",
        "fallback_mode": True
    }


@router.get("/analytics/detailed")
async def get_detailed_analytics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    granularity: str = Query(default="daily", description="Granularity: hourly, daily, weekly"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Get detailed analytics with time-series data and insights"""
    
    try:
        # Get comprehensive analytics
        analytics = await analytics_service.get_user_analytics_optimized(
            user_id=user.id,
            db=db,
            days=days
        )
        
        # Get detailed trends with custom granularity
        trends = await analytics_service.get_message_trends_optimized(
            user_id=user.id,
            db=db,
            days=days,
            granularity=granularity
        )
        
        # Get model performance insights
        model_performance = await analytics_service.get_model_performance(
            user_id=user.id,
            days=days
        )
        
        # Get user insights
        insights = await analytics_service.generate_user_insights(
            user_id=user.id,
            db=db,
            days=days
        )
        
        return {
            "period": {
                "days": days,
                "granularity": granularity,
                "start_date": (datetime.utcnow() - timedelta(days=days)).isoformat(),
                "end_date": datetime.utcnow().isoformat()
            },
            "analytics": analytics,
            "trends": trends,
            "model_performance": model_performance,
            "insights": insights,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get detailed analytics: {str(e)}")


@router.get("/analytics/predictions")
async def get_prediction_analytics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Get prediction accuracy and AI model performance analytics"""
    
    try:
        # Get model performance metrics
        model_performance = await analytics_service.get_model_performance(
            user_id=user.id,
            days=days
        )
        
        # Get feedback summary
        feedback_summary = await analytics_service.get_feedback_summary(
            user_id=user.id,
            db=db,
            days=days
        )
        
        # Get prediction history
        prediction_history = await analytics_service.get_prediction_history(
            user_id=user.id,
            db=db,
            days=days,
            limit=100
        )
        
        return {
            "period_days": days,
            "model_performance": model_performance,
            "feedback_summary": feedback_summary,
            "prediction_history": prediction_history,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get prediction analytics: {str(e)}")


@router.get("/analytics/insights")
async def get_dashboard_insights(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Get AI-powered insights and recommendations for the user"""
    
    try:
        # Generate personalized insights
        insights = await analytics_service.generate_user_insights(
            user_id=user.id,
            db=db,
            days=days
        )
        
        # Get basic analytics for context
        analytics = await analytics_service.get_user_analytics_optimized(
            user_id=user.id,
            db=db,
            days=days
        )
        
        return {
            "period_days": days,
            "insights": insights,
            "summary": {
                "total_messages": analytics.get("total_messages", 0),
                "prediction_confidence": analytics.get("prediction_accuracy", {}).get("avg_confidence", 0.0),
                "top_contexts": list(analytics.get("context_distribution", {}).keys())[:3]
            },
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get insights: {str(e)}")
