"""
API v1 Analytics Routes - Dashboard and Insights
Comprehensive analytics endpoints using unified analytics service
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from api.dependencies import get_db, get_current_user
from services.analytics import analytics_service
from utils.errors import (
    APIError, ValidationError, ServerError,
    handle_api_errors
)
from utils.logger import logger

router = APIRouter()

# =============================================================================
# Dashboard Analytics
# =============================================================================

@router.get("/dashboard")
async def get_dashboard_analytics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get comprehensive dashboard analytics
    
    Args:
        days: Number of days to analyze
        
    Returns:
        Complete dashboard data with privacy protection
    """
    try:
        # Get comprehensive user analytics
        dashboard_data = await analytics_service.get_user_analytics(
            user_id=user.id,
            db=db,
            days=days
        )
        
        # Add dashboard-specific formatting
        dashboard_formatted = {
            "overview": {
                "total_messages": dashboard_data.get("total_messages", 0),
                "messages_by_source": dashboard_data.get("messages_by_source", {}),
                "priority_distribution": dashboard_data.get("priority_distribution", {}),
                "context_distribution": dashboard_data.get("context_distribution", {}),
                "period_days": days,
                "last_updated": datetime.utcnow().isoformat()
            },
            "trends": dashboard_data.get("trends", {}),
            "predictions": {
                "accuracy": dashboard_data.get("prediction_accuracy", {}),
                "confidence": dashboard_data.get("prediction_confidence", {}),
                "feedback_count": dashboard_data.get("feedback_count", 0)
            },
            "insights": dashboard_data.get("insights", []),
            "privacy_protected": True
        }
        
        return {
            "operation": "dashboard_analytics",
            "user_id": user.id,
            "period_days": days,
            "dashboard": dashboard_formatted,
            "generated_at": datetime.utcnow().isoformat(),
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard analytics: {str(e)}")
        raise ServerError("Failed to get dashboard analytics")

@router.get("/overview")
async def get_analytics_overview(
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get quick analytics overview for header/summary display
    
    Returns:
        High-level analytics summary
    """
    try:
        # Get quick overview data
        overview_data = await analytics_service.get_analytics_overview(
            user_id=user.id,
            db=db
        )
        
        return {
            "operation": "analytics_overview",
            "user_id": user.id,
            "overview": overview_data,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting analytics overview: {str(e)}")
        raise ServerError("Failed to get analytics overview")

# =============================================================================
# Message Analytics
# =============================================================================

@router.get("/messages/trends")
async def get_message_trends(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    granularity: str = Query(default="daily", description="Trend granularity (hourly, daily, weekly)"),
    source: Optional[str] = Query(default=None, description="Filter by source"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get message volume trends over time
    
    Args:
        days: Number of days to analyze
        granularity: Trend granularity (hourly, daily, weekly)
        source: Optional source filter
        
    Returns:
        Message trends data for visualization
    """
    try:
        if granularity not in ["hourly", "daily", "weekly"]:
            raise ValidationError("Invalid granularity. Use 'hourly', 'daily', or 'weekly'")
        
        trends_data = await analytics_service.get_message_trends(
            user_id=user.id,
            db=db,
            days=days,
            granularity=granularity,
            source=source
        )
        
        return {
            "operation": "message_trends",
            "user_id": user.id,
            "filters": {
                "days": days,
                "granularity": granularity,
                "source": source
            },
            "trends": trends_data,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message trends: {str(e)}")
        raise ServerError("Failed to get message trends")

@router.get("/messages/distribution")
async def get_message_distribution(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    dimension: str = Query(default="priority", description="Distribution dimension (priority, context, source, hour)"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get message distribution across different dimensions
    
    Args:
        days: Number of days to analyze
        dimension: Distribution dimension to analyze
        
    Returns:
        Message distribution data for charts
    """
    try:
        if dimension not in ["priority", "context", "source", "hour", "day_of_week"]:
            raise HTTPException(
                status_code=400, 
                detail="Invalid dimension. Use 'priority', 'context', 'source', 'hour', or 'day_of_week'"
            )
        
        distribution_data = await analytics_service.get_message_distribution(
            user_id=user.id,
            db=db,
            days=days,
            dimension=dimension
        )
        
        return {
            "operation": "message_distribution",
            "user_id": user.id,
            "filters": {
                "days": days,
                "dimension": dimension
            },
            "distribution": distribution_data,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message distribution: {str(e)}")
        raise ServerError("Failed to get message distribution")

# =============================================================================
# Prediction Analytics
# =============================================================================

@router.get("/predictions/accuracy")
async def get_prediction_accuracy(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    prediction_type: str = Query(default="all", description="Prediction type (priority, context, all)"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get prediction accuracy metrics and trends
    
    Args:
        days: Number of days to analyze
        prediction_type: Type of prediction to analyze
        
    Returns:
        Prediction accuracy data and trends
    """
    try:
        if prediction_type not in ["priority", "context", "all"]:
            raise ValidationError("Invalid prediction type. Use 'priority', 'context', or 'all'")
        
        accuracy_data = await analytics_service.get_prediction_accuracy(
            user_id=user.id,
            db=db,
            days=days,
            prediction_type=prediction_type
        )
        
        return {
            "operation": "prediction_accuracy",
            "user_id": user.id,
            "filters": {
                "days": days,
                "prediction_type": prediction_type
            },
            "accuracy": accuracy_data,
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting prediction accuracy: {str(e)}")
        raise ServerError("Failed to get prediction accuracy")

@router.get("/predictions/confidence")
async def get_prediction_confidence(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get prediction confidence distribution and trends
    
    Args:
        days: Number of days to analyze
        
    Returns:
        Prediction confidence analysis
    """
    try:
        confidence_data = await analytics_service.get_prediction_confidence(
            user_id=user.id,
            db=db,
            days=days
        )
        
        return {
            "operation": "prediction_confidence",
            "user_id": user.id,
            "period_days": days,
            "confidence": confidence_data,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting prediction confidence: {str(e)}")
        raise ServerError("Failed to get prediction confidence")

# =============================================================================
# Advanced Analytics
# =============================================================================

@router.get("/insights/advanced")
async def get_advanced_insights(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    insight_type: str = Query(default="all", description="Insight type (patterns, anomalies, recommendations, all)"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get advanced AI-driven insights and recommendations
    
    Args:
        days: Number of days to analyze
        insight_type: Type of insights to generate
        
    Returns:
        Advanced insights and recommendations
    """
    try:
        if insight_type not in ["patterns", "anomalies", "recommendations", "all"]:
            raise HTTPException(
                status_code=400, 
                detail="Invalid insight type. Use 'patterns', 'anomalies', 'recommendations', or 'all'"
            )
        
        insights_data = await analytics_service.generate_user_insights(
            user_id=user.id,
            db=db,
            days=days,
            insight_type=insight_type
        )
        
        return {
            "operation": "advanced_insights",
            "user_id": user.id,
            "filters": {
                "days": days,
                "insight_type": insight_type
            },
            "insights": insights_data,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting advanced insights: {str(e)}")
        raise ServerError("Failed to get advanced insights")

@router.get("/reports/summary")
async def get_analytics_report(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to analyze"),
    report_type: str = Query(default="weekly", description="Report type (daily, weekly, monthly)"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Generate comprehensive analytics report
    
    Args:
        days: Number of days to analyze
        report_type: Type of report to generate
        
    Returns:
        Comprehensive analytics report
    """
    try:
        if report_type not in ["daily", "weekly", "monthly"]:
            raise ValidationError("Invalid report type. Use 'daily', 'weekly', or 'monthly'")
        
        report_data = await analytics_service.generate_analytics_report(
            user_id=user.id,
            db=db,
            days=days,
            report_type=report_type
        )
        
        return {
            "operation": "analytics_report",
            "user_id": user.id,
            "report_config": {
                "days": days,
                "type": report_type,
                "generated_at": datetime.utcnow().isoformat()
            },
            "report": report_data,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating analytics report: {str(e)}")
        raise ServerError("Failed to generate analytics report")

# =============================================================================
# Performance Analytics
# =============================================================================

@router.get("/performance/system")
async def get_system_performance(
    user = Depends(get_current_user)
):
    """
    Get system performance metrics for the user
    
    Returns:
        System performance data and health metrics
    """
    try:
        performance_data = await analytics_service.get_system_performance(user_id=user.id)
        
        return {
            "operation": "system_performance",
            "user_id": user.id,
            "performance": performance_data,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting system performance: {str(e)}")
        raise ServerError("Failed to get system performance")

@router.get("/performance/usage")
async def get_usage_metrics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get user usage metrics and patterns
    
    Args:
        days: Number of days to analyze
        
    Returns:
        Usage metrics and activity patterns
    """
    try:
        usage_data = await analytics_service.get_usage_metrics(
            user_id=user.id,
            db=db,
            days=days
        )
        
        return {
            "operation": "usage_metrics",
            "user_id": user.id,
            "period_days": days,
            "usage": usage_data,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting usage metrics: {str(e)}")
        raise ServerError("Failed to get usage metrics")
