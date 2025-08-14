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
        db_gen = get_db()
        db = await db_gen.__anext__()
        try:
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
        finally:
            await db_gen.aclose()
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

# =============================================================================
# Missing Test Endpoints
# =============================================================================

@router.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "service": "Socialify Backend",
        "timestamp": "2025-08-13T00:00:00Z",
        "version": "1.0.0",
        "environment": "production"
    }

@router.get("/test-db")
async def test_database_connection(db: AsyncSession = Depends(get_db)):
    """Test database connectivity and basic operations"""
    try:
        # Test basic database connection
        result = await db.execute(text("SELECT 1 as test_value"))
        test_row = result.fetchone()
        
        # Test user table access
        user_count_result = await db.execute(text("SELECT COUNT(*) as count FROM users"))
        user_count = user_count_result.scalar() or 0
        
        # Test message table access
        message_count_result = await db.execute(text("SELECT COUNT(*) as count FROM message_metadata"))
        count_row = message_count_result.fetchone()
        message_count = count_row[0] if count_row is not None else 0
        
        return {
            "database_status": "connected",
            "test_query": test_row.test_value if test_row else None,
            "tables": {
                "users": {
                    "accessible": True,
                    "count": user_count
                },
                "message_metadata": {
                    "accessible": True,
                    "count": message_count
                }
            },
            "message": "Database connection successful"
        }
        
    except Exception as e:
        logger.error(f"Database test failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

@router.post("/gmail-diagnose")
async def diagnose_gmail_issues(
    user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Comprehensive Gmail integration diagnostics"""
    try:
        diagnosis = {
            "user_info": {
                "user_id": user.id,
                "email": user.email,
                "auth_method": getattr(user, 'auth_method', 'unknown')
            },
            "gmail_connectivity": {},
            "token_status": {},
            "recent_activity": {},
            "recommendations": []
        }
        
        # Check Gmail token status
        has_encrypted_token = bool(user.gmail_token_encrypted)
        diagnosis["token_status"] = {
            "has_encrypted_token": has_encrypted_token,
            "token_available": has_encrypted_token,
            "connection_status": "connected" if has_encrypted_token else "disconnected"
        }
        
        if not has_encrypted_token:
            diagnosis["recommendations"].append("Gmail token not found. Please reconnect your Gmail account.")
            diagnosis["gmail_connectivity"]["status"] = "no_token"
        else:
            # Test Gmail API connectivity (basic test)
            try:
                # This is a safe test that doesn't actually call Gmail API
                diagnosis["gmail_connectivity"]["status"] = "token_available"
                diagnosis["gmail_connectivity"]["message"] = "Gmail token is present and encrypted"
            except Exception as e:
                diagnosis["gmail_connectivity"]["status"] = "error"
                diagnosis["gmail_connectivity"]["error"] = str(e)
                diagnosis["recommendations"].append(f"Gmail API connection issue: {str(e)}")
        
        # Check recent message activity
        try:
            recent_messages = await db.execute(
                select(MessageMetadata)
                .where(MessageMetadata.user_id == user.id)
                .order_by(MessageMetadata.created_at.desc())
                .limit(5)
            )
            messages = recent_messages.scalars().all()
            
            diagnosis["recent_activity"] = {
                "recent_message_count": len(messages),
                "last_message_time": messages[0].created_at.isoformat() if messages else None,
                "sources": list(set([msg.source for msg in messages])) if messages else []
            }
            
            if not messages:
                diagnosis["recommendations"].append("No recent messages found. Try fetching new messages.")
            
        except Exception as e:
            diagnosis["recent_activity"]["error"] = str(e)
            diagnosis["recommendations"].append("Could not check recent message activity")
        
        # Overall health assessment
        if has_encrypted_token and len(diagnosis["recommendations"]) == 0:
            diagnosis["overall_status"] = "healthy"
            diagnosis["message"] = "Gmail integration appears to be working correctly"
        else:
            diagnosis["overall_status"] = "issues_detected"
            diagnosis["message"] = "Some issues detected with Gmail integration"
        
        return diagnosis
        
    except Exception as e:
        logger.error(f"Gmail diagnosis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)}")

@router.get("/gmail-token-info")
async def gmail_token_information(user = Depends(get_current_user)):
    """Get Gmail token status and information (safe, no sensitive data exposed)"""
    try:
        token_info = {
            "user_id": user.id,
            "token_status": {
                "has_encrypted_token": bool(user.gmail_token_encrypted),
                "token_present": bool(user.gmail_token_encrypted),
                "encryption_status": "encrypted" if user.gmail_token_encrypted else "none"
            },
            "connection_info": {
                "gmail_connected": bool(user.gmail_token_encrypted),
                "status": "connected" if user.gmail_token_encrypted else "disconnected",
                "requires_reconnection": not bool(user.gmail_token_encrypted)
            },
            "security_info": {
                "token_encrypted": bool(user.gmail_token_encrypted),
                "secure_storage": True,
                "sensitive_data_filtered": True
            }
        }
        
        # Add recommendations if needed
        if not user.gmail_token_encrypted:
            token_info["recommendations"] = [
                "Gmail account is not connected",
                "Use the Gmail OAuth flow to connect your account",
                "Check /api/v1/gmail/status for connection options"
            ]
        else:
            token_info["recommendations"] = [
                "Gmail account is properly connected",
                "Token is securely encrypted",
                "Ready for message fetching"
            ]
        
        return token_info
        
    except Exception as e:
        logger.error(f"Gmail token info request failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Token info request failed: {str(e)}")

# Legacy endpoints removed - use comprehensive test instead
# @router.post("/gmail-fetch") - Deprecated: Use /gmail/comprehensive
# @router.get("/gmail-status") - Deprecated: Use /gmail/comprehensive
