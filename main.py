import defusedxml
defusedxml.defuse_stdlib()

from defusedxml.xmlrpc import monkey_patch
monkey_patch()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Use centralized configuration
from config.settings import settings
from db.db import engine, Base
from utils.logger import logger
import uvicorn
from sqlalchemy import text

# Import optimized services from reorganized structure
from services.email import email_service
from services.analytics import analytics_service
from services.privacy import privacy_service

# Privacy-focused Socialify Backend - Optimized v2.1
# Following privacy-first principles with optimized architecture:
# 1. OAuth2-only authentication (no password storage)
# 2. Encrypted token storage
# 3. In-memory message processing only
# 4. Sensitive data filtering in logs
# 5. Organized service layer with performance optimizations

app = FastAPI(
    title="Socialify AI Backend - API v1", 
    version="2.1.0-v1-api",
    description="Privacy-first messaging assistant with unified services and RESTful API v1 structure"
)

# CORS configuration using centralized settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Import routers after app creation to avoid circular imports
from api.routes import auth, test

# Include legacy routers (will be deprecated)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(test.router, prefix="/test", tags=["test"])

# Include new v1 API routers (PRIMARY - Use these)
from api.v1 import gmail, messages, prediction, user, analytics
app.include_router(gmail.router, prefix="/api/v1/gmail", tags=["v1-gmail"])
app.include_router(messages.router, prefix="/api/v1/messages", tags=["v1-messages"])
app.include_router(prediction.router, prefix="/api/v1/prediction", tags=["v1-prediction"])
app.include_router(user.router, prefix="/api/v1/user", tags=["v1-user"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["v1-analytics"])

# Essential legacy routes (kept for unique functionality)
from api.routes import feedback, dashboard
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])

# Legacy redirects for backward compatibility
from fastapi.responses import RedirectResponse

@app.get("/analytics")
async def legacy_analytics_redirect():
    """Redirect legacy /analytics to v1 analytics dashboard"""
    return RedirectResponse(url="/api/v1/analytics/dashboard", status_code=301)

@app.get("/analytics/user/{user_id}")
async def legacy_analytics_user_redirect(user_id: int, days: int = 30, includeTrends: bool = True):
    """Redirect legacy /analytics/user/{user_id} to v1 analytics user endpoint"""
    return RedirectResponse(url=f"/api/v1/analytics/user/{user_id}?days={days}&includeTrends={includeTrends}", status_code=301)

@app.get("/messages/processed")
async def legacy_messages_processed_redirect():
    """Redirect legacy /messages/processed to v1 messages processed"""
    return RedirectResponse(url="/api/v1/messages/processed", status_code=301)

@app.get("/api/health")
@app.get("/health")  # Consolidated endpoint
async def unified_health_check():
    """Unified health check endpoint - replaces duplicate endpoints"""
    from datetime import datetime
    
    # Basic health info
    health_info = {
        "status": "healthy",
        "service": "Socialify AI Backend",
        "version": "2.1.0-v1-api",
        "timestamp": datetime.utcnow().isoformat(),
        "api_version": "v1",
        "privacy_mode": "enabled",
        "auth_method": "oauth_only",
        "encryption": "enabled",
        "database": "postgresql",
        "features": {
            "unified_services": True,
            "restful_api_v1": True,
            "gmail_integration": True,
            "ai_predictions": True,
            "privacy_protection": True,
            "legacy_compatibility": True
        }
    }
    
    # Database health check
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        health_info["database_status"] = "connected"
    except Exception:
        health_info["database_status"] = "error"
        health_info["status"] = "degraded"
    
    return health_info

@app.on_event("startup")
async def on_startup():
    """Startup event with privacy-focused initialization"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created successfully")
        
        # Test database connection
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ PostgreSQL connection successful")
        
        logger.info("🔒 Privacy-focused Socialify Backend started")
        logger.info("🔒 OAuth2-only authentication enabled")
        logger.info("🔒 Token encryption enabled") 
        logger.info("🔒 Sensitive data filtering active")
        logger.info(f"🔒 Configuration loaded: {settings.get_feature_flags()}")
        
    except Exception as e:
        logger.error(f"❌ Database error: {type(e).__name__}")
        raise

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True) 
