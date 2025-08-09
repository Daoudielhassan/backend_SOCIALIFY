"""
Test Routes - Comprehensive diagnostics and testing endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import Dict, Any, List
from api.dependencies import get_db, get_current_user
from db.models import User, MessageMetadata
from services.emailServices.email_service import email_service as email_service
from utils.logger import logger

router = APIRouter()

@router.get("/status")
async def service_status():
    """Service status endpoint"""
    return {
        "service": "Test Routes",
        "status": "operational", 
        "message": "Comprehensive diagnostic endpoints available"
    }

@router.get("/endpoints")
async def list_endpoints():
    """List all available API endpoints"""
    return {
        "authentication": [
            "POST /auth/login - User login (legacy)",
            "POST /auth/google - Google OAuth login",
            "GET /auth/google/init - Initialize OAuth flow",
            "GET /auth/google/callback - OAuth callback"
        ],
        "messages": [
            "GET /messages - Get user messages with filtering",
            "POST /messages/fetch - Fetch new messages",
            "GET /messages/{id} - Get specific message",
            "DELETE /messages/{id} - Delete message",
            "GET /messages/stats/summary - Message statistics"
        ],
        "gmail": [
            "POST /gmail/fetch/{user_id} - Manual Gmail fetch",
            "POST /gmail/fetch-all - Fetch for all users",
            "GET /gmail/status - Gmail service status"
        ],
        "analytics": [
            "GET /analytics - Analytics data with time range",
            "GET /analytics/summary - Analytics summary"
        ],
        "dashboard": [
            "GET /dashboard/stats - Dashboard statistics"
        ],
        "user": [
            "GET /user/settings - User settings",
            "PUT /user/profile - Update profile",
            "DELETE /user/account - Deactivate account"
        ],
        "health": [
            "GET /health - Unified health check",
            "GET /api/health - Unified health check (alias)"
        ],
        "test": [
            "GET /test/status - Service status",
            "GET /test/endpoints - This endpoint",
            "GET /test/database - Database diagnostics",
            "POST /test/gmail/comprehensive - Comprehensive Gmail test"
        ]
    }

@router.get("/database")
async def test_database():
    """Database connectivity and diagnostics"""
    try:
        async with get_db() as db:
            # Test basic connectivity
            result = await db.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            
            # Count users
            user_count = await db.execute(text("SELECT COUNT(*) FROM users"))
            total_users = user_count.scalar()
            
            # Count messages (if old table exists)
            try:
                msg_count = await db.execute(text("SELECT COUNT(*) FROM messages"))
                total_messages = msg_count.scalar()
            except:
                total_messages = "N/A (table not found)"
            
            # Count metadata (new table)
            try:
                meta_count = await db.execute(text("SELECT COUNT(*) FROM message_metadata"))
                total_metadata = meta_count.scalar()
            except:
                total_metadata = "N/A (table not found)"
            
            return {
                "database_status": "connected",
                "test_query": test_value == 1,
                "statistics": {
                    "total_users": total_users,
                    "total_messages": total_messages,
                    "total_metadata": total_metadata
                },
                "tables": {
                    "users": "exists",
                    "messages": "legacy (may exist)",
                    "message_metadata": "privacy-focused"
                }
            }
    except Exception as e:
        logger.error(f"Database test failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database test failed: {str(e)}")

@router.post("/gmail/comprehensive")
async def comprehensive_gmail_test(
    max_messages: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Comprehensive Gmail test - consolidates multiple Gmail test endpoints
    Tests connectivity, fetching, and diagnostics in one endpoint
    """
    
    results = {
        "user_info": {
            "email": user.email,
            "user_id": user.id,
            "has_encrypted_token": bool(user.gmail_token_encrypted),
            "has_legacy_token": False,  # No legacy tokens in current model
            "auth_method": getattr(user, 'auth_method', 'unknown')
        },
        "connectivity": {},
        "fetch_test": {},
        "diagnostics": {}
    }
    
    # 1. Connectivity Test
    try:
        if not user.gmail_token_encrypted:
            results["connectivity"] = {
                "status": "not_connected",
                "error": "No Gmail token available"
            }
        else:
            from services.emailServices.gmail_oauth import gmail_oauth_service
            
            # Use the encrypted token
            token_to_use = user.gmail_token_encrypted
            service, updated_credentials = gmail_oauth_service.get_gmail_service(token_to_use)
            
            # Test basic API access
            profile = service.users().getProfile(userId='me').execute()
            
            results["connectivity"] = {
                "status": "connected",
                "gmail_address": profile.get('emailAddress'),
                "messages_total": profile.get('messagesTotal', 0),
                "token_type": "encrypted"
            }
            
    except Exception as e:
        results["connectivity"] = {
            "status": "error",
            "error": str(e)
        }
    
    # 2. Fetch Test (only if connected)
    if results["connectivity"].get("status") == "connected":
        try:
            # Test actual message fetching
            fetch_result = await email_service.fetch_messages_for_user(
                user=user,
                db=db,
                max_results=max_messages
            )
            
            results["fetch_test"] = {
                "status": "successful" if "error" not in fetch_result else "error",
                "processed": fetch_result.get("processed", 0),
                "mode": fetch_result.get("mode", "unknown"),
                "errors": fetch_result.get("errors", [])
            }
            
        except Exception as e:
            results["fetch_test"] = {
                "status": "error",
                "error": str(e)
            }
    else:
        results["fetch_test"] = {
            "status": "skipped",
            "reason": "Gmail not connected"
        }
    
    # 3. Diagnostics
    try:
        # Check recent messages in database (if old table exists)
        try:
            recent_messages_query = await db.execute(
                select(MessageMetadata).where(
                    MessageMetadata.user_id == user.id,
                    MessageMetadata.source == 'gmail'
                ).order_by(MessageMetadata.received_at.desc()).limit(5)
            )
            recent_messages = recent_messages_query.scalars().all()
        except:
            recent_messages = []
        
        # Check metadata records
        try:
            metadata_query = await db.execute(
                select(MessageMetadata).where(
                    MessageMetadata.user_id == user.id,
                    MessageMetadata.source == 'gmail'
                ).order_by(MessageMetadata.received_at.desc()).limit(5)
            )
            recent_metadata = metadata_query.scalars().all()
        except:
            recent_metadata = []
        
        results["diagnostics"] = {
            "database_records": {
                "legacy_messages": len(recent_messages),
                "privacy_metadata": len(recent_metadata)
            },
            "latest_activity": {
                "last_message": recent_messages[0].received_at.isoformat() if recent_messages else None,
                "last_metadata": recent_metadata[0].received_at.isoformat() if recent_metadata else None
            },
            "migration_status": {
                "needs_migration": False,  # No legacy tokens in current model
                "privacy_ready": bool(user.gmail_token_encrypted)
            }
        }
        
    except Exception as e:
        results["diagnostics"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Summary
    results["summary"] = {
        "overall_status": "healthy" if (
            results["connectivity"].get("status") == "connected" and
            results["fetch_test"].get("status") == "successful"
        ) else "issues_detected",
        "recommendations": []
    }
    
    # Add recommendations  
    if not user.gmail_token_encrypted:
        results["summary"]["recommendations"].append("Connect Gmail account")
    
    if results["connectivity"].get("status") != "connected":
        results["summary"]["recommendations"].append("Reconnect Gmail account")
    
    if results["fetch_test"].get("processed", 0) == 0:
        results["summary"]["recommendations"].append("Check if Gmail has new messages")
    
    return results

@router.get("/auth-check")
async def test_authentication(user = Depends(get_current_user)):
    """Test endpoint to verify authentication is working"""
    return {
        "authenticated": True,
        "user_email": user.email,
        "user_id": user.id,
        "auth_method": getattr(user, 'auth_method', 'unknown'),
        "gmail_status": {
            "has_encrypted_token": bool(user.gmail_token_encrypted),
            "has_legacy_token": False,  # No legacy tokens in current model
            "connected": bool(user.gmail_token_encrypted)
        },
        "message": "Authentication successful"
    }

# Legacy endpoints removed - use comprehensive test instead
# @router.post("/gmail-fetch") - Deprecated: Use /gmail/comprehensive
# @router.get("/gmail-status") - Deprecated: Use /gmail/comprehensive
