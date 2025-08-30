"""
Unified WhatsApp Business API Routes - Clean Version
Combines V1 compatibility with V2 multi-tenant architecture
"""

from fastapi import APIRouter, HTTPException, Query, Body, Depends, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, func

# Services
from services.whatsappServices.whatsapp_service import whatsapp_service
from services.whatsappServices.multi_tenant_whatsapp_service import multi_tenant_whatsapp_service
from services.analytics.analytics_service import analytics_service

# Utils & Dependencies
from utils.errors import WhatsAppError, ValidationError, handle_api_errors
from utils.logger import logger
from config.settings import settings
from api.dependencies import get_current_user
from db.db import get_async_session

# Database Models
from db.models import (
    User, 
    WhatsAppBusinessAccount, 
    WhatsAppPhoneNumber, 
    WhatsAppMessageV2,
    WhatsAppMessage,
    WhatsAppWebhook,
    MessageMetadata
)

router = APIRouter()

# ============================================================================
# V1 LEGACY ENDPOINTS (Backward Compatibility)
# ============================================================================

@router.post("/webhook")
async def whatsapp_webhook_v1(
    request: Request,
    db: AsyncSession = Depends(get_async_session)
):
    """V1 webhook endpoint for WhatsApp messages"""
    try:
        body = await request.json()
        logger.info(f"📱 WhatsApp webhook V1 received: {body}")
        
        # Verify webhook signature if needed
        # TODO: Add webhook verification
        
        # Process webhook with V1 service
        result = await whatsapp_service.process_webhook_message(body)
        return {"status": "success", "processed": result}
        
    except Exception as e:
        logger.error(f"❌ WhatsApp webhook V1 error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-message")
async def send_whatsapp_message_v1(
    message_data: dict = Body(...),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """V1 endpoint for sending WhatsApp messages"""
    try:
        user_id = current_user.id
        logger.info(f"📱 Sending WhatsApp message V1 for user {current_user.email}")
        
        # Validate required fields
        to = message_data.get("to")
        message = message_data.get("message")
        
        if not to or not message:
            raise HTTPException(status_code=400, detail="Missing required fields: 'to' and 'message'")
        
        # Send with V1 service
        result = await whatsapp_service.send_message(
            to=to,
            message=message,
            message_type=message_data.get("type", "text")
        )
        
        return {"status": "success", "message_id": result}
        
    except Exception as e:
        logger.error(f"❌ WhatsApp send V1 error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages")
async def get_whatsapp_messages_v1(
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """V1 endpoint for getting WhatsApp messages"""
    try:
        user_id = current_user.id
        
        # Query V1 messages
        query = (
            select(WhatsAppMessage)
            .where(WhatsAppMessage.user_id == user_id)
            .order_by(WhatsAppMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(query)
        messages = result.scalars().all()
        
        return {
            "messages": [
                {
                    "id": msg.id,
                    "message_id": msg.message_id,
                    "recipient_number": msg.recipient_number,
                    "message_type": msg.message_type,
                    "status": msg.status,
                    "created_at": msg.created_at.isoformat(),
                    "updated_at": msg.updated_at.isoformat()
                }
                for msg in messages
            ],
            "total": len(messages),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"❌ WhatsApp messages V1 error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# V2 MULTI-TENANT ENDPOINTS
# ============================================================================

@router.post("/v2/oauth/initiate")
async def initiate_whatsapp_oauth_v2(
    oauth_data: dict = Body(...),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """V2 endpoint for initiating WhatsApp Business OAuth"""
    try:
        user_id = current_user.id
        logger.info(f"📱 Initiating WhatsApp OAuth V2 for user {current_user.email}")
        
        redirect_uri = oauth_data.get("redirect_uri")
        if not redirect_uri:
            raise HTTPException(status_code=400, detail="Missing redirect_uri")
        
        # Initiate OAuth with V2 service
        result = await multi_tenant_whatsapp_service.initiate_meta_oauth(
            user_id=user_id,
            redirect_uri=redirect_uri
        )
        
        return {"status": "success", "oauth_url": result.get("oauth_url"), "state": result.get("state")}
        
    except Exception as e:
        logger.error(f"❌ WhatsApp OAuth initiation V2 error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v2/oauth/callback")
async def handle_whatsapp_oauth_callback_v2(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    V2 endpoint for handling WhatsApp Business OAuth callback (public, no auth)
    """
    try:
        logger.info(f"📱 Handling WhatsApp OAuth callback V2: code={code}, state={state}")

        # You may need to look up the user by state here!
        # user_email = get_user_email_from_state(state)
        # result = await multi_tenant_whatsapp_service.handle_meta_oauth_callback(
        #     code=code, state=state, user_email=user_email, db=db
        # )

        result = await multi_tenant_whatsapp_service.handle_meta_oauth_callback(
            code=code,
            state=state,
            db=db
        )

        return {"status": "success", "account": result}

    except Exception as e:
        logger.error(f"❌ WhatsApp connect V2 error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/v2/webhook/{phone_number_id}")
async def whatsapp_webhook_v2(
    phone_number_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_session)
):
    """V2 webhook endpoint with phone number routing"""
    try:
        body = await request.json()
        logger.info(f"📱 WhatsApp webhook V2 received for phone {phone_number_id}")
        
        # Process with V2 service
        result = await multi_tenant_whatsapp_service.route_webhook_message(
            webhook_data=body,
            db=db
        )
        
        return {"status": "success", "processed": result}
        
    except Exception as e:
        logger.error(f"❌ WhatsApp webhook V2 error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/v2/send-message")
async def send_whatsapp_message_v2(
    message_data: dict = Body(...),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """V2 endpoint for sending multi-tenant WhatsApp messages"""
    try:
        user_id = current_user.id
        logger.info(f"📱 Sending WhatsApp message V2 for user {current_user.email}")
        
        # Validate required fields
        phone_number_id = message_data.get("phone_number_id")
        to = message_data.get("to")
        message = message_data.get("message")
        
        if not phone_number_id or not to or not message:
            raise HTTPException(status_code=400, detail="Missing required fields: 'phone_number_id', 'to', and 'message'")
        
        # Send with V2 service
        result = await multi_tenant_whatsapp_service.send_message(
            user_id=user_id,
            phone_number_id=phone_number_id,
            to=to,
            message=message,
            db=db
        )
        
        return {"status": "success", "message_id": result}
        
    except Exception as e:
        logger.error(f"❌ WhatsApp send V2 error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v2/messages")
async def get_whatsapp_messages_v2(
    phone_number_id: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """V2 endpoint for getting multi-tenant WhatsApp messages"""
    try:
        user_id = current_user.id
        
        # Build query
        query = select(WhatsAppMessageV2).where(
            WhatsAppMessageV2.user_id == user_id
        )
        
        # Initialize phone_record_id
        phone_record_id = None
        
        # Add phone number filter if provided
        if phone_number_id:
            # Find phone record by phone_number_id
            phone_query = select(WhatsAppPhoneNumber.id).where(
                WhatsAppPhoneNumber.phone_number_id == phone_number_id
            )
            phone_result = await db.execute(phone_query)
            phone_record_id = phone_result.scalar_one_or_none()
            
            if phone_record_id:
                query = query.where(
                    WhatsAppMessageV2.phone_number_id == phone_record_id
                )
        
        # Add ordering, limit, offset
        query = query.order_by(WhatsAppMessageV2.created_at.desc()).limit(limit).offset(offset)
        
        # Execute query
        result = await db.execute(query)
        messages = result.scalars().all()
        
        # Build response
        message_list = []
        for msg in messages:
            message_list.append({
                "id": msg.id,
                "message_id": msg.message_id,
                "direction": msg.direction,
                "contact_phone": msg.contact_phone,
                "contact_name": msg.contact_name,
                "message_type": msg.message_type,
                "status": msg.status,
                "ai_processed": msg.ai_processed,
                "predicted_priority": msg.predicted_priority,
                "predicted_context": msg.predicted_context,
                "prediction_confidence": msg.prediction_confidence,
                "created_at": msg.created_at.isoformat(),
                "sent_at": msg.sent_at.isoformat() if msg.sent_at is not None else None,
                "delivered_at": msg.delivered_at.isoformat() if msg.delivered_at is not None else None,
                "read_at": msg.read_at.isoformat() if msg.read_at is not None else None
            })
        
        # Get total count
        count_query = select(func.count(WhatsAppMessageV2.id)).where(
            WhatsAppMessageV2.user_id == user_id
        )
        
        if phone_number_id and phone_record_id:
            count_query = count_query.where(
                WhatsAppMessageV2.phone_number_id == phone_record_id
            )
        
        count_result = await db.execute(count_query)
        total = count_result.scalar()
        
        return {
            "messages": message_list,
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"❌ WhatsApp messages V2 error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v2/accounts")
async def get_whatsapp_accounts_v2(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """V2 endpoint for getting user's WhatsApp Business Accounts"""
    try:
        user_id = current_user.id
        
        # Query user's WhatsApp accounts
        query = select(WhatsAppBusinessAccount).where(
            WhatsAppBusinessAccount.user_id == user_id
        ).order_by(WhatsAppBusinessAccount.connected_at.desc())
        
        result = await db.execute(query)
        accounts = result.scalars().all()
        
        account_list = []
        for account in accounts:
            # Get phone numbers for this account
            phone_query = select(WhatsAppPhoneNumber).where(
                WhatsAppPhoneNumber.waba_id == account.id
            )
            phone_result = await db.execute(phone_query)
            phone_numbers = phone_result.scalars().all()
            
            account_list.append({
                "id": account.id,
                "waba_id": account.waba_id,
                "business_name": account.business_name,
                "is_active": account.is_active,
                "is_verified": account.is_verified,
                "webhook_configured": account.webhook_configured,
                "connected_at": account.connected_at.isoformat(),
                "last_sync": account.last_sync.isoformat() if account.last_sync is not None else None,
                "phone_numbers": [
                    {
                        "id": phone.id,
                        "phone_number_id": phone.phone_number_id,
                        "phone_number": phone.phone_number,
                        "display_name": phone.display_name,
                        "status": phone.status,
                        "is_verified": phone.is_verified
                    }
                    for phone in phone_numbers
                ]
            })
        
        return {
            "accounts": account_list,
            "total": len(account_list)
        }
        
    except Exception as e:
        logger.error(f"❌ WhatsApp accounts V2 error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ANALYTICS & MONITORING
# ============================================================================

@router.get("/analytics")
async def get_whatsapp_analytics(
    days: int = Query(30, ge=1, le=365),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get WhatsApp analytics for the user"""
    try:
        user_id = current_user.id
        
        # Get analytics with service
        analytics = await analytics_service.get_user_analytics_optimized(
            user_id=user_id,
            days=days,
            db=db
        )
        
        return analytics
        
    except Exception as e:
        logger.error(f"❌ WhatsApp analytics error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# WEBHOOK VERIFICATION
# ============================================================================

@router.get("/webhook")
async def verify_webhook(
    request: Request
):
    """Verify WhatsApp webhook"""
    try:
        # Get query parameters
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        
        logger.info(f"🔍 WhatsApp webhook verification: mode={mode}, token={token}")
        
        # Verify the webhook
        if mode == "subscribe" and token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
            logger.info("✅ WhatsApp webhook verification successful")
            return PlainTextResponse(challenge)
        else:
            logger.error("❌ WhatsApp webhook verification failed")
            raise HTTPException(status_code=403, detail="Verification failed")
    
    except Exception as e:
        logger.error(f"❌ WhatsApp webhook verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v2/webhook/{phone_number_id}")
async def verify_webhook_v2(
    phone_number_id: str,
    request: Request
):
    """Verify WhatsApp webhook for specific phone number"""
    try:
        # Get query parameters
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        
        logger.info(f"🔍 WhatsApp webhook V2 verification for phone {phone_number_id}: mode={mode}")
        
        # Verify the webhook (you might want to use phone-specific tokens)
        if mode == "subscribe" and token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
            logger.info(f"✅ WhatsApp webhook V2 verification successful for {phone_number_id}")
            return PlainTextResponse(challenge)
        else:
            logger.error(f"❌ WhatsApp webhook V2 verification failed for {phone_number_id}")
            raise HTTPException(status_code=403, detail="Verification failed")
    
    except Exception as e:
        logger.error(f"❌ WhatsApp webhook V2 verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def whatsapp_health_check():
    """Health check endpoint for WhatsApp API"""
    return {
        "status": "healthy",
        "service": "whatsapp_unified_api",
        "version": "2.0",
        "features": ["v1_legacy", "v2_multi_tenant", "analytics", "webhooks"],
        "timestamp": datetime.utcnow().isoformat()
    }
