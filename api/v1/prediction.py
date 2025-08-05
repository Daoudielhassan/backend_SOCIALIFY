"""
API v1 Prediction Routes - AI and ML Operations
Centralized prediction endpoints using unified analytics service
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from api.dependencies import get_db, get_current_user
from services.analytics import analytics_service
from utils.errors import (
    APIError, ValidationError, ServerError,
    handle_api_errors
)
from utils.logger import logger

router = APIRouter()

# =============================================================================
# Request/Response Models
# =============================================================================

class PredictionRequest(BaseModel):
    """Request model for single message prediction"""
    subject: str
    sender_domain: str
    source: str = "unknown"
    metadata: Optional[Dict[str, Any]] = None

class BatchPredictionRequest(BaseModel):
    """Request model for batch predictions"""
    messages: List[PredictionRequest]
    include_confidence: bool = True

# =============================================================================
# Individual Predictions
# =============================================================================

@router.post("/predict")
async def predict_message(
    request: PredictionRequest,
    user = Depends(get_current_user)
):
    """
    Predict priority and context for a single message
    
    Args:
        request: Message data to predict
        
    Returns:
        Predictions with confidence scores
    """
    try:
        # Use analytics service for prediction
        prediction_result = await analytics_service.predict_message_classification(
            subject=request.subject,
            sender_domain=request.sender_domain,
            source=request.source,
            user_id=user.id,
            metadata=request.metadata or {}
        )
        
        return {
            "operation": "predict_message",
            "input": {
                "subject_preview": request.subject[:50] + "..." if len(request.subject) > 50 else request.subject,
                "sender_domain": request.sender_domain,
                "source": request.source
            },
            "predictions": prediction_result,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error predicting message: {str(e)}")
        raise ServerError("Failed to predict message")

@router.post("/predict/batch")
async def predict_messages_batch(
    request: BatchPredictionRequest,
    user = Depends(get_current_user)
):
    """
    Predict priority and context for multiple messages
    
    Args:
        request: Batch of messages to predict
        
    Returns:
        Batch predictions with confidence scores
    """
    try:
        if len(request.messages) > 100:
            raise ValidationError("Maximum 100 messages per batch")
        
        batch_results = []
        
        for idx, message in enumerate(request.messages):
            try:
                prediction_result = await analytics_service.predict_message_classification(
                    subject=message.subject,
                    sender_domain=message.sender_domain,
                    source=message.source,
                    user_id=user.id,
                    metadata=message.metadata or {}
                )
                
                batch_results.append({
                    "index": idx,
                    "input": {
                        "subject_preview": message.subject[:50] + "..." if len(message.subject) > 50 else message.subject,
                        "sender_domain": message.sender_domain,
                        "source": message.source
                    },
                    "predictions": prediction_result,
                    "status": "success"
                })
                
            except Exception as e:
                batch_results.append({
                    "index": idx,
                    "input": {
                        "subject_preview": message.subject[:50] + "..." if len(message.subject) > 50 else message.subject,
                        "sender_domain": message.sender_domain,
                        "source": message.source
                    },
                    "predictions": None,
                    "error": str(e),
                    "status": "failed"
                })
        
        success_count = sum(1 for r in batch_results if r["status"] == "success")
        
        return {
            "operation": "predict_batch",
            "batch_size": len(request.messages),
            "successful": success_count,
            "failed": len(request.messages) - success_count,
            "include_confidence": request.include_confidence,
            "results": batch_results,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch prediction: {str(e)}")
        raise ServerError("Failed to process batch predictions")

# =============================================================================
# Model Information and Performance
# =============================================================================

@router.get("/models/info")
async def get_model_info(
    user = Depends(get_current_user)
):
    """
    Get information about current prediction models
    
    Returns:
        Model information and performance metrics
    """
    try:
        model_info = await analytics_service.get_model_info(user_id=user.id)
        
        return {
            "operation": "model_info",
            "user_id": user.id,
            "models": model_info,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting model info: {str(e)}")
        raise ServerError("Failed to get model information")

@router.get("/models/performance")
async def get_model_performance(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    user = Depends(get_current_user)
):
    """
    Get model performance metrics and accuracy
    
    Args:
        days: Number of days to analyze performance
        
    Returns:
        Performance metrics and accuracy data
    """
    try:
        performance_data = await analytics_service.get_model_performance(
            user_id=user.id,
            days=days
        )
        
        return {
            "operation": "model_performance",
            "user_id": user.id,
            "period_days": days,
            "performance": performance_data,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting model performance: {str(e)}")
        raise ServerError("Failed to get model performance")

# =============================================================================
# Model Training and Improvement
# =============================================================================

@router.post("/models/retrain")
async def trigger_model_retrain(
    force: bool = Query(default=False, description="Force retraining even if recent"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Trigger model retraining with user feedback
    
    Args:
        force: Force retraining even if recent
        
    Returns:
        Retraining status and results
    """
    try:
        retrain_result = await analytics_service.trigger_model_retrain(
            user_id=user.id,
            db=db,
            force=force
        )
        
        return {
            "operation": "model_retrain",
            "user_id": user.id,
            "force": force,
            "result": retrain_result,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error triggering model retrain: {str(e)}")
        raise ServerError("Failed to trigger model retraining")

@router.get("/feedback/summary")
async def get_feedback_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get summary of user feedback for model improvement
    
    Args:
        days: Number of days to analyze feedback
        
    Returns:
        Feedback summary and training data statistics
    """
    try:
        feedback_summary = await analytics_service.get_feedback_summary(
            user_id=user.id,
            db=db,
            days=days
        )
        
        return {
            "operation": "feedback_summary",
            "user_id": user.id,
            "period_days": days,
            "summary": feedback_summary,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting feedback summary: {str(e)}")
        raise ServerError("Failed to get feedback summary")

# =============================================================================
# Prediction History and Analytics
# =============================================================================

@router.get("/history")
async def get_prediction_history(
    limit: int = Query(default=50, ge=1, le=200, description="Number of predictions to return"),
    days: int = Query(default=7, ge=1, le=90, description="Number of days to search"),
    accuracy_only: bool = Query(default=False, description="Only show predictions with feedback"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get recent prediction history and accuracy
    
    Args:
        limit: Number of predictions to return
        days: Number of days to search
        accuracy_only: Only show predictions with user feedback
        
    Returns:
        Prediction history with accuracy metrics
    """
    try:
        prediction_history = await analytics_service.get_prediction_history(
            user_id=user.id,
            db=db,
            limit=limit,
            days=days,
            accuracy_only=accuracy_only
        )
        
        return {
            "operation": "prediction_history",
            "user_id": user.id,
            "filters": {
                "limit": limit,
                "days": days,
                "accuracy_only": accuracy_only
            },
            "history": prediction_history,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting prediction history: {str(e)}")
        raise ServerError("Failed to get prediction history")

@router.get("/insights")
async def get_prediction_insights(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get AI-driven insights about user's message patterns
    
    Args:
        days: Number of days to analyze
        
    Returns:
        Comprehensive insights and recommendations
    """
    try:
        insights = await analytics_service.generate_user_insights(
            user_id=user.id,
            db=db,
            days=days
        )
        
        return {
            "operation": "prediction_insights",
            "user_id": user.id,
            "period_days": days,
            "insights": insights,
            "privacy_protected": True,
            "api_version": "v1"
        }
        
    except Exception as e:
        logger.error(f"Error getting prediction insights: {str(e)}")
        raise ServerError("Failed to get insights")
