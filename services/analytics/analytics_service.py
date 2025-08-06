"""
Performance Analytics Service - Optimized Analytics Operations
Enhanced analytics with caching, batch processing, and smart aggregations
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, text

from utils.performance import (
    performance_cache, cached, batch_processor, query_optimizer,
    monitor_performance
)
from utils.logger import logger
from config.settings import settings
from db.models import User, MessageMetadata

class HighPerformanceAnalyticsService:
    """
    Enhanced analytics service with performance optimizations
    
    Features:
    - Intelligent caching for expensive aggregations
    - Batch processing for multi-user analytics
    - Pre-computed metrics and smart cache invalidation
    - Optimized database queries with proper indexing
    """
    
    def __init__(self):
        """Initialize the high-performance analytics service"""
        self.cache_ttl = {
            'user_analytics': 600,    # 10 minutes
            'system_metrics': 300,    # 5 minutes
            'trends': 900,           # 15 minutes
            'predictions': 1800,     # 30 minutes
        }
    
    @cached(ttl=600, key_prefix="user_analytics")
    @monitor_performance("get_user_analytics_cached")
    async def get_user_analytics_optimized(
        self,
        user_id: int,
        db: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get comprehensive user analytics with intelligent caching
        """
        try:
            from db.models import MessageMetadata
            
            # Use optimized query with proper index usage
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Single optimized query for all analytics
            query = text("""
                SELECT 
                    source,
                    predicted_priority,
                    predicted_context,
                    DATE(received_at) as message_date,
                    COUNT(*) as count,
                    AVG(prediction_confidence) as avg_confidence
                FROM message_metadata 
                WHERE user_id = :user_id 
                    AND received_at >= :start_date
                GROUP BY source, predicted_priority, predicted_context, DATE(received_at)
                ORDER BY message_date DESC
            """)
            
            result = await query_optimizer.execute_with_performance_monitoring(
                db, query, "user_analytics", {"user_id": user_id, "start_date": start_date}
            )
            
            rows = result.fetchall()
            
            # Process results into structured analytics
            analytics = {
                "total_messages": 0,
                "messages_by_source": defaultdict(int),
                "priority_distribution": defaultdict(int),
                "context_distribution": defaultdict(int),
                "daily_trends": defaultdict(int),
                "prediction_accuracy": {"avg_confidence": 0.0},
                "insights": []
            }
            
            total_confidence = 0
            confidence_count = 0
            
            for row in rows:
                count = row.count
                analytics["total_messages"] += count
                analytics["messages_by_source"][row.source] += count
                
                if row.predicted_priority:
                    analytics["priority_distribution"][row.predicted_priority] += count
                
                if row.predicted_context:
                    analytics["context_distribution"][row.predicted_context] += count
                
                if row.message_date:
                    analytics["daily_trends"][str(row.message_date)] += count
                
                if row.avg_confidence:
                    total_confidence += row.avg_confidence * count
                    confidence_count += count
            
            # Calculate average confidence
            if confidence_count > 0:
                analytics["prediction_accuracy"]["avg_confidence"] = total_confidence / confidence_count
            
            # Convert defaultdicts to regular dicts
            analytics = {k: dict(v) if isinstance(v, defaultdict) else v for k, v in analytics.items()}
            
            # Generate insights
            analytics["insights"] = await self._generate_insights(analytics)
            
            logger.debug(f"Generated analytics for user {user_id}: {analytics['total_messages']} messages")
            return analytics
            
        except Exception as e:
            logger.error(f"Failed to get user analytics: {e}")
            return {"error": str(e), "total_messages": 0}
    
    @cached(ttl=900, key_prefix="message_trends")
    @monitor_performance("get_message_trends_optimized")
    async def get_message_trends_optimized(
        self,
        user_id: int,
        db: AsyncSession,
        days: int = 30,
        granularity: str = "daily"
    ) -> Dict[str, Any]:
        """
        Get message trends with optimized aggregation queries
        """
        try:
            # Determine date grouping based on granularity
            date_trunc_format = {
                "hourly": "hour",
                "daily": "day", 
                "weekly": "week"
            }.get(granularity, "day")
            
            # Optimized trend query using database aggregation
            query = text(f"""
                SELECT 
                    DATE_TRUNC('{date_trunc_format}', received_at) as period,
                    source,
                    predicted_priority,
                    COUNT(*) as message_count
                FROM message_metadata 
                WHERE user_id = :user_id 
                    AND received_at >= :start_date
                GROUP BY DATE_TRUNC('{date_trunc_format}', received_at), source, predicted_priority
                ORDER BY period DESC
                LIMIT 100
            """)
            
            start_date = datetime.utcnow() - timedelta(days=days)
            result = await query_optimizer.execute_with_performance_monitoring(
                db, query, "message_trends", {"user_id": user_id, "start_date": start_date}
            )
            
            rows = result.fetchall()
            
            # Structure trend data
            trends = {
                "granularity": granularity,
                "period_days": days,
                "data": defaultdict(lambda: defaultdict(int)),
                "totals": defaultdict(int),
                "sources": defaultdict(lambda: defaultdict(int))
            }
            
            for row in rows:
                period_key = row.period.strftime("%Y-%m-%d %H:%M") if granularity == "hourly" else row.period.strftime("%Y-%m-%d")
                
                trends["data"][period_key]["total"] += row.message_count
                trends["totals"][period_key] += row.message_count
                
                if row.source:
                    trends["sources"][row.source][period_key] += row.message_count
                    trends["data"][period_key][f"{row.source}_count"] += row.message_count
                
                if row.predicted_priority:
                    trends["data"][period_key][f"{row.predicted_priority}_priority"] += row.message_count
            
            # Convert to regular dicts and sort
            trends["data"] = dict(trends["data"])
            trends["totals"] = dict(sorted(trends["totals"].items(), reverse=True))
            trends["sources"] = {k: dict(v) for k, v in trends["sources"].items()}
            
            return trends
            
        except Exception as e:
            logger.error(f"Failed to get message trends: {e}")
            return {"error": str(e), "data": {}}
    
    @monitor_performance("batch_analytics_processing")
    async def process_analytics_batch(
        self,
        user_ids: List[int],
        db: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Process analytics for multiple users in parallel
        """
        if not user_ids:
            return {"processed": 0, "errors": 0}
        
        try:
            # Create analytics tasks for parallel processing
            analytics_tasks = []
            
            for user_id in user_ids:
                async def get_user_analytics_task(uid=user_id):
                    return await self.get_user_analytics_optimized(uid, db, days)
                
                analytics_tasks.append(get_user_analytics_task)
            
            # Process in parallel with controlled concurrency
            results = await batch_processor.parallel_api_calls(
                api_calls=analytics_tasks,
                max_concurrent=5,  # Conservative limit for database operations
                timeout=30.0
            )
            
            # Count successful processing
            successful = sum(1 for r in results if r and "error" not in r)
            errors = len(results) - successful
            
            logger.info(f"Batch analytics processing: {successful}/{len(user_ids)} successful")
            
            return {
                "processed": successful,
                "errors": errors,
                "user_count": len(user_ids)
            }
            
        except Exception as e:
            logger.error(f"Batch analytics processing failed: {e}")
            return {"processed": 0, "errors": len(user_ids), "error": str(e)}
    
    @cached(ttl=300, key_prefix="system_metrics")
    async def get_system_performance_metrics(
        self,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get system-wide performance metrics with caching
        """
        try:
            # Optimized system metrics query
            query = text("""
                SELECT 
                    COUNT(*) as total_messages,
                    COUNT(DISTINCT user_id) as active_users,
                    COUNT(CASE WHEN created_at >= NOW() - INTERVAL '1 hour' THEN 1 END) as messages_last_hour,
                    COUNT(CASE WHEN created_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as messages_last_day,
                    AVG(prediction_confidence) as avg_prediction_confidence,
                    COUNT(CASE WHEN feedback_priority IS NOT NULL THEN 1 END) as feedback_count
                FROM message_metadata
                WHERE created_at >= NOW() - INTERVAL '7 days'
            """)
            
            result = await query_optimizer.execute_with_performance_monitoring(
                db, query, "system_metrics"
            )
            
            row = result.fetchone()
            
            metrics = {
                "total_messages": row.total_messages or 0,
                "active_users": row.active_users or 0,
                "messages_last_hour": row.messages_last_hour or 0,
                "messages_last_day": row.messages_last_day or 0,
                "avg_prediction_confidence": float(row.avg_prediction_confidence or 0),
                "feedback_rate": (row.feedback_count / max(row.total_messages, 1)) * 100,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return {"error": str(e)}
    
    @monitor_performance("prediction_accuracy_analysis")
    async def analyze_prediction_accuracy_batch(
        self,
        user_ids: List[int],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Analyze prediction accuracy across multiple users efficiently
        """
        try:
            if not user_ids:
                return {"accuracy": 0, "total_predictions": 0}
            
            # Batch accuracy analysis query
            query = text("""
                SELECT 
                    user_id,
                    predicted_priority,
                    feedback_priority,
                    predicted_context,
                    feedback_context,
                    prediction_confidence,
                    COUNT(*) as count
                FROM message_metadata 
                WHERE user_id = ANY(:user_ids)
                    AND feedback_priority IS NOT NULL 
                    AND predicted_priority IS NOT NULL
                GROUP BY user_id, predicted_priority, feedback_priority, 
                         predicted_context, feedback_context, prediction_confidence
            """)
            
            result = await query_optimizer.execute_with_performance_monitoring(
                db, query, "prediction_accuracy", {"user_ids": user_ids}
            )
            
            rows = result.fetchall()
            
            # Calculate accuracy metrics
            total_predictions = 0
            correct_priority = 0
            correct_context = 0
            confidence_sum = 0
            
            for row in rows:
                count = row.count
                total_predictions += count
                
                if row.predicted_priority == row.feedback_priority:
                    correct_priority += count
                
                if row.predicted_context == row.feedback_context:
                    correct_context += count
                
                if row.prediction_confidence:
                    confidence_sum += row.prediction_confidence * count
            
            # Calculate rates
            priority_accuracy = (correct_priority / max(total_predictions, 1)) * 100
            context_accuracy = (correct_context / max(total_predictions, 1)) * 100
            avg_confidence = confidence_sum / max(total_predictions, 1)
            
            return {
                "priority_accuracy": round(priority_accuracy, 2),
                "context_accuracy": round(context_accuracy, 2),
                "overall_accuracy": round((priority_accuracy + context_accuracy) / 2, 2),
                "avg_confidence": round(avg_confidence, 3),
                "total_predictions": total_predictions,
                "users_analyzed": len(user_ids)
            }
            
        except Exception as e:
            logger.error(f"Prediction accuracy analysis failed: {e}")
            return {"error": str(e), "accuracy": 0}
    
    async def _generate_insights(self, analytics: Dict[str, Any]) -> List[str]:
        """Generate insights from analytics data"""
        insights = []
        
        try:
            total = analytics.get("total_messages", 0)
            if total == 0:
                return ["No messages to analyze"]
            
            # Message volume insights
            if total > 100:
                insights.append(f"High email volume: {total} messages analyzed")
            elif total < 10:
                insights.append(f"Low email volume: {total} messages in period")
            
            # Priority distribution insights
            priorities = analytics.get("priority_distribution", {})
            if priorities:
                top_priority = max(priorities.items(), key=lambda x: x[1])
                insights.append(f"Most common priority: {top_priority[0]} ({top_priority[1]} messages)")
            
            # Source insights
            sources = analytics.get("messages_by_source", {})
            if len(sources) > 1:
                insights.append(f"Multi-source messages: {', '.join(sources.keys())}")
            
            return insights[:5]  # Limit insights
            
        except Exception as e:
            logger.error(f"Failed to generate insights: {e}")
            return ["Analysis insights unavailable"]
    
    async def invalidate_user_analytics_cache(self, user_id: int):
        """Invalidate analytics cache for a specific user"""
        patterns = [
            f"user_analytics:*:{user_id}:*",
            f"message_trends:*:{user_id}:*",
            f"func:analytics:*:{user_id}:*"
        ]
        
        invalidated_count = 0
        for pattern in patterns:
            count = await performance_cache.invalidate_pattern(pattern)
            invalidated_count += count
        
        logger.debug(f"Invalidated {invalidated_count} analytics cache entries for user {user_id}")
        return invalidated_count

# Create optimized analytics service instance
analytics_service = HighPerformanceAnalyticsService()
# Backward compatibility alias
analytics_service = analytics_service

# Export optimized service
__all__ = [
    "HighPerformanceAnalyticsService",
    "analytics_service",
    "analytics_service"
]
