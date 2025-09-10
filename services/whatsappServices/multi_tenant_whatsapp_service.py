"""
Multi-Tenant WhatsApp Business API Service
Handles multiple user WhatsApp Business Accounts with secure token management
"""

import asyncio
import aiohttp
import json
import hashlib
import secrets
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from cryptography.fernet import Fernet

from config.settings import settings
from utils.logger import logger
from utils.errors import WhatsAppError, ValidationError
from utils.encryption import token_encryption
from db.models import (
    WhatsAppBusinessAccount, 
    WhatsAppPhoneNumber, 
    WhatsAppMessageV2, 
    WhatsAppWebhook,
    User
)

class MultiTenantWhatsAppService:
    """
    Multi-tenant WhatsApp Business API service
    Each user can connect their own WhatsApp Business Account
    """
    
    def __init__(self):
        self.meta_oauth_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        self.meta_graph_url = "https://graph.facebook.com/v18.0"
    
    def _hash_content(self, content: str) -> str:
        """
        Generate SHA-256 hash of content for privacy and deduplication
        
        Args:
            content: Content to hash
            
        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
        
    async def initiate_meta_oauth(self, user_id: int, redirect_uri: str) -> Dict[str, Any]:
        """
        Initiate Meta OAuth flow for WhatsApp Business API
        
        Args:
            user_id: User ID requesting OAuth
            redirect_uri: Callback URL for OAuth (for compatibility, but we use settings value)
            
        Returns:
            OAuth URL and state information
        """
        try:
            # Generate secure state parameter
            state = f"{user_id}_{secrets.token_urlsafe(32)}"
            
            # Required permissions for WhatsApp Business API
            permissions = [
                "whatsapp_business_management",
                "whatsapp_business_messaging", 
                "business_management"
            ]
            
            # Use the configured redirect URI from settings for consistency
            configured_redirect_uri = settings.META_REDIRECT_URI
            
            oauth_url = (
                f"https://www.facebook.com/v18.0/dialog/oauth?"
                f"client_id={settings.META_APP_ID}&"
                f"redirect_uri={configured_redirect_uri}&"
                f"scope={','.join(permissions)}&"
                f"response_type=code&"
                f"state={state}"
            )
            
            logger.info(f"🔐 Generated Meta OAuth URL for user {user_id}")
            logger.info(f"🔐 Using configured redirect URI: {configured_redirect_uri}")
            
            return {
                "oauth_url": oauth_url,
                "state": state,
                "permissions": permissions
            }
            
        except Exception as e:
            logger.error(f"❌ Meta OAuth initiation failed: {str(e)}")
            raise WhatsAppError(f"Failed to initiate Meta OAuth: {str(e)}")
    
    async def handle_meta_oauth_callback(
        self, 
        code: str, 
        state: str, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Handle Meta OAuth callback and store credentials
        
        Args:
            code: Authorization code from Meta
            state: State parameter for security
            db: Database session
            
        Returns:
            Connection result with WABA details
        """
        try:
            # Extract user_id from state
            user_id = int(state.split('_')[0])
            
            # Exchange code for access token
            token_data = await self._exchange_code_for_token(code)
            
            # Get user info and business accounts
            user_info = await self._get_meta_user_info(token_data["access_token"])
            business_accounts = await self._get_user_business_accounts(
                user_info["id"], 
                token_data["access_token"]
            )
            
            # Store WABA credentials
            waba_connections = []
            for waba in business_accounts:
                connection = await self._store_waba_credentials(
                    user_id, waba, token_data, user_info, db
                )
                waba_connections.append(connection)
            
            await db.commit()
            
            logger.info(f"🔐 Successfully connected {len(waba_connections)} WABA(s) for user {user_id}")
            
            return {
                "success": True,
                "user_id": user_id,
                "connections": waba_connections,
                "message": f"Connected {len(waba_connections)} WhatsApp Business Account(s)"
            }
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Meta OAuth callback failed: {str(e)}")
            raise WhatsAppError(f"OAuth callback failed: {str(e)}")
    
    async def _exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "client_id": settings.META_APP_ID,
                    "client_secret": settings.META_APP_SECRET,
                    "redirect_uri": settings.META_REDIRECT_URI,
                    "code": code,
                }
                
                logger.info("🔄 Exchanging authorization code for access token")
                logger.info(f"🔄 Using redirect URI: {settings.META_REDIRECT_URI}")
                logger.info(f"🔄 Code length: {len(code)} characters")
                
                async with session.post(self.meta_oauth_url, data=payload) as response:
                    logger.info(f"🔄 Meta token exchange response status: {response.status}")
                    response_text = await response.text()
                    logger.info(f"🔄 Meta token exchange response body: {response_text}")
                    
                    if response.status == 200:
                        token_data = await response.json()
                        logger.info("✅ Token exchange successful")
                        logger.info(f"✅ Token type: {token_data.get('token_type', 'N/A')}")
                        logger.info(f"✅ Expires in: {token_data.get('expires_in', 'N/A')} seconds")
                        return token_data
                    else:
                        logger.error(f"❌ Token exchange failed with status {response.status}")
                        logger.error(f"❌ Response body: {response_text}")
                        raise WhatsAppError(f"Token exchange failed: {response_text}")
                        
        except Exception as e:
            logger.error(f"❌ Token exchange error: {str(e)}")
            raise WhatsAppError(f"Failed to exchange code for token: {str(e)}")
    
    async def _get_meta_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get Meta user information"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.meta_graph_url}/me"
                headers = {"Authorization": f"Bearer {access_token}"}
                
                logger.info("🔍 Fetching Meta user information")
                logger.info(f"🔍 Using access token: {access_token[:20]}...")
                
                async with session.get(url, headers=headers) as response:
                    logger.info(f"🔍 Meta /me response status: {response.status}")
                    response_text = await response.text()
                    logger.info(f"🔍 Meta /me response body: {response_text}")
                    
                    if response.status == 200:
                        user_data = await response.json()
                        logger.info(f"✅ Meta user info retrieved: ID {user_data.get('id')}, Name: {user_data.get('name')}")
                        return user_data
                    else:
                        logger.error(f"❌ Failed to get user info: {response_text}")
                        raise WhatsAppError(f"User info fetch failed: {response_text}")
                        
        except Exception as e:
            logger.error(f"❌ User info fetch error: {str(e)}")
            raise WhatsAppError(f"Failed to get user info: {str(e)}")
    
    async def _get_user_business_accounts(
        self, 
        user_id: str, 
        access_token: str
    ) -> List[Dict[str, Any]]:
        """Get user's WhatsApp Business Accounts"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.meta_graph_url}/{user_id}/businesses"
                headers = {"Authorization": f"Bearer {access_token}"}
                
                logger.info(f"🔍 Fetching businesses for user {user_id}")
                
                async with session.get(url, headers=headers) as response:
                    logger.info(f"🔍 Businesses response status: {response.status}")
                    response_text = await response.text()
                    logger.info(f"🔍 Businesses response body: {response_text}")
                    
                    if response.status == 200:
                        data = await response.json()
                        businesses = data.get("data", [])
                        logger.info(f"✅ Found {len(businesses)} businesses")
                        
                        # Get WhatsApp Business Accounts for each business
                        wabas = []
                        for business in businesses:
                            business_id = business["id"]
                            business_name = business.get("name", "Unknown")
                            logger.info(f"🔍 Processing business {business_id}: {business_name}")
                            
                            waba_url = f"{self.meta_graph_url}/{business_id}/owned_whatsapp_business_accounts"
                            async with session.get(waba_url, headers=headers) as waba_response:
                                logger.info(f"🔍 WABA response for business {business_id} - status: {waba_response.status}")
                                waba_response_text = await waba_response.text()
                                logger.info(f"🔍 WABA response body: {waba_response_text}")
                                
                                if waba_response.status == 200:
                                    waba_data = await waba_response.json()
                                    business_wabas = waba_data.get("data", [])
                                    logger.info(f"✅ Found {len(business_wabas)} WABAs in business {business_id}")
                                    wabas.extend(business_wabas)
                                else:
                                    logger.warning(f"⚠️ Failed to get WABAs for business {business_id}: {waba_response_text}")
                        
                        logger.info(f"📱 Total WhatsApp Business Accounts found: {len(wabas)}")
                        return wabas
                    else:
                        logger.error(f"❌ Failed to get businesses: {response_text}")
                        
                        # Try to parse the error for better messaging
                        try:
                            error_json = await response.json()
                            error_code = error_json.get("error", {}).get("code")
                            error_message = error_json.get("error", {}).get("message", "")
                            
                            if error_code == 100:  # Insufficient permissions
                                logger.error("❌ Permission error: The access token doesn't have business_management permission")
                                raise WhatsAppError("Insufficient permissions: Please ensure your Meta app has 'business_management' permission approved and granted during OAuth. You may need to re-authorize with the correct permissions.")
                            elif error_code == 190:  # Invalid access token
                                logger.error("❌ Invalid access token")
                                raise WhatsAppError("Invalid access token: The OAuth flow may have expired. Please try the authorization again.")
                            else:
                                raise WhatsAppError(f"Business accounts fetch failed: {error_message}")
                        except:
                            raise WhatsAppError(f"Business accounts fetch failed: {response_text}")
                        
        except Exception as e:
            logger.error(f"❌ Business accounts fetch error: {str(e)}")
            raise WhatsAppError(f"Failed to get business accounts: {str(e)}")
    
    async def _store_waba_credentials(
        self, 
        user_id: int, 
        waba_data: Dict[str, Any], 
        token_data: Dict[str, Any],
        user_info: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Store WABA credentials securely"""
        try:
            # Check if WABA already exists
            existing_waba = await db.execute(
                select(WhatsAppBusinessAccount).where(
                    and_(
                        WhatsAppBusinessAccount.user_id == user_id,
                        WhatsAppBusinessAccount.waba_id == waba_data["id"]
                    )
                )
            )
            waba_account = existing_waba.scalar_one_or_none()
            
            if not waba_account:
                # Create new WABA record with encrypted tokens
                encrypted_access_token = token_encryption.encrypt_token({"access_token": token_data["access_token"]})
                encrypted_refresh_token = None
                if "refresh_token" in token_data:
                    encrypted_refresh_token = token_encryption.encrypt_token({"refresh_token": token_data["refresh_token"]})
                
                waba_account = WhatsAppBusinessAccount(
                    user_id=user_id,
                    waba_id=waba_data["id"],
                    business_name=waba_data.get("name", "Unknown Business"),
                    meta_app_id=settings.META_APP_ID,
                    meta_user_id=user_info["id"],
                    access_token_encrypted=encrypted_access_token,
                    refresh_token_encrypted=encrypted_refresh_token
                )
                db.add(waba_account)
                await db.flush()  # Get ID
            
            # Update datetime fields using SQL update
            from sqlalchemy import update
            update_query = (
                update(WhatsAppBusinessAccount)
                .where(WhatsAppBusinessAccount.id == waba_account.id)
                .values(
                    token_expires_at=datetime.utcnow() + timedelta(seconds=int(token_data["expires_in"])) if "expires_in" in token_data else None,
                    last_sync=datetime.utcnow(),
                    is_active=True
                )
            )
            await db.execute(update_query)
            
            # Get the actual record ID for phone number storage
            await db.flush()
            result = await db.execute(
                select(WhatsAppBusinessAccount.id).where(
                    WhatsAppBusinessAccount.waba_id == waba_data["id"]
                )
            )
            waba_record_id = result.scalar_one()
            
            # Get and store phone numbers
            phone_numbers = await self._get_waba_phone_numbers(
                waba_data["id"], 
                token_data["access_token"],
                waba_record_id,
                db
            )
            
            return {
                "waba_id": waba_data["id"],
                "business_name": waba_data.get("name"),
                "phone_numbers": phone_numbers,
                "status": "connected"
            }
            
        except Exception as e:
            logger.error(f"❌ WABA credential storage failed: {str(e)}")
            raise WhatsAppError(f"Failed to store WABA credentials: {str(e)}")
    
    async def _get_waba_phone_numbers(
        self, 
        waba_id: str, 
        access_token: str,
        waba_record_id: int,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Get and store WABA phone numbers"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.meta_graph_url}/{waba_id}/phone_numbers"
                headers = {"Authorization": f"Bearer {access_token}"}
                
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        phone_numbers = []
                        for phone_data in data.get("data", []):
                            # Store phone number
                            phone_number = WhatsAppPhoneNumber(
                                waba_id=waba_record_id,
                                phone_number_id=phone_data["id"],
                                phone_number=phone_data["display_phone_number"],
                                display_name=phone_data.get("verified_name", ""),
                                status=phone_data.get("status", "pending"),
                                is_verified=phone_data.get("status") == "CONNECTED"
                            )
                            db.add(phone_number)
                            
                            phone_numbers.append({
                                "phone_number_id": phone_data["id"],
                                "phone_number": phone_data["display_phone_number"],
                                "status": phone_data.get("status"),
                                "verified": phone_data.get("status") == "CONNECTED"
                            })
                        
                        return phone_numbers
                    else:
                        logger.warning(f"⚠️ Could not fetch phone numbers for WABA {waba_id}")
                        return []
                        
        except Exception as e:
            logger.error(f"❌ Phone numbers fetch error: {str(e)}")
            return []
    
    async def send_message(
        self, 
        user_id: int, 
        phone_number_id: str, 
        to: str, 
        message: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Send WhatsApp message using user's own WABA
        
        Args:
            user_id: User sending the message
            phone_number_id: User's phone number ID to send from
            to: Recipient phone number
            message: Message content
            db: Database session
            
        Returns:
            Sending result
        """
        try:
            # Get user's WABA and access token
            waba_info = await self._get_user_waba_for_phone(user_id, phone_number_id, db)
            
            if not waba_info:
                raise WhatsAppError("Phone number not found or not authorized")
            
            # Decrypt access token
            encrypted_token_data = token_encryption.decrypt_token(waba_info["access_token_encrypted"])
            if not encrypted_token_data:
                raise WhatsAppError("Failed to decrypt access token")
            access_token = encrypted_token_data["access_token"]
            
            # Send message via Meta API
            result = await self._send_message_via_meta_api(
                phone_number_id, to, message, access_token
            )
            
            # Store message record
            message_record = WhatsAppMessageV2(
                user_id=user_id,
                waba_id=waba_info["waba_record_id"],
                phone_number_id=waba_info["phone_record_id"],
                message_id=result["messages"][0]["id"],
                direction="outbound",
                contact_phone=to,
                message_type="text",
                status="sent"
            )
            db.add(message_record)
            await db.commit()
            
            logger.info(f"📱 Message sent successfully for user {user_id}")
            
            return {
                "success": True,
                "message_id": result["messages"][0]["id"],
                "status": "sent"
            }
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Message send failed for user {user_id}: {str(e)}")
            raise WhatsAppError(f"Failed to send message: {str(e)}")
    
    async def _get_user_waba_for_phone(
        self, 
        user_id: int, 
        phone_number_id: str, 
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Get user's WABA info for specific phone number"""
        try:
            query = (
                select(
                    WhatsAppBusinessAccount.access_token_encrypted,
                    WhatsAppBusinessAccount.id.label("waba_record_id"),
                    WhatsAppPhoneNumber.id.label("phone_record_id")
                )
                .join(WhatsAppPhoneNumber)
                .where(
                    and_(
                        WhatsAppBusinessAccount.user_id == user_id,
                        WhatsAppPhoneNumber.phone_number_id == phone_number_id,
                        WhatsAppBusinessAccount.is_active == True
                    )
                )
            )
            
            result = await db.execute(query)
            row = result.first()
            
            if row:
                return {
                    "access_token_encrypted": row.access_token_encrypted,
                    "waba_record_id": row.waba_record_id,
                    "phone_record_id": row.phone_record_id
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ WABA lookup failed: {str(e)}")
            return None
    
    async def _send_message_via_meta_api(
        self, 
        phone_number_id: str, 
        to: str, 
        message: str, 
        access_token: str
    ) -> Dict[str, Any]:
        """Send message via Meta WhatsApp API"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.meta_graph_url}/{phone_number_id}/messages"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": message}
                }
                
                async with session.post(url, headers=headers, json=payload) as response:
                    logger.info(f"📤 Sending message to Meta API - URL: {url}")
                    logger.info(f"📤 Request payload: {payload}")
                    
                    response_text = await response.text()
                    logger.info(f"📥 Meta API response status: {response.status}")
                    logger.info(f"📥 Meta API response headers: {dict(response.headers)}")
                    logger.info(f"📥 Meta API response body: {response_text}")
                    
                    if response.status == 200:
                        response_data = await response.json()
                        logger.info(f"✅ Message sent successfully: {response_data}")
                        return response_data
                    else:
                        logger.error(f"❌ Meta API error - Status: {response.status}")
                        logger.error(f"❌ Meta API error response: {response_text}")
                        
                        try:
                            error_data = await response.json()
                            logger.error(f"❌ Meta API error details: {error_data}")
                        except:
                            logger.error(f"❌ Could not parse error response as JSON")
                        
                        raise WhatsAppError(f"Meta API error: {response_text}")
                        
        except Exception as e:
            logger.error(f"❌ Meta API send failed: {str(e)}")
            raise WhatsAppError(f"Meta API send failed: {str(e)}")
    
    async def route_webhook_message(
        self, 
        webhook_data: Dict[str, Any], 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Route incoming webhook message to correct tenant with enhanced processing
        
        Enhanced features:
        - Comprehensive webhook validation
        - Multi-tenant message routing with fallback
        - Privacy-focused message processing
        - AI processing integration
        - Detailed error handling and logging
        - Webhook event deduplication
        - Status tracking and analytics
        
        Args:
            webhook_data: Webhook payload from Meta
            db: Database session
            
        Returns:
            Processing result with detailed metrics
        """
        start_time = datetime.utcnow()
        processed_messages = []
        errors = []
        
        try:
            logger.info("🔄 Starting webhook message routing process")
            logger.info(f"📊 Webhook payload size: {len(str(webhook_data))} chars")
            
            # Validate webhook structure
            if not isinstance(webhook_data, dict):
                raise WhatsAppError("Invalid webhook payload: not a dictionary")
            
            if "entry" not in webhook_data:
                logger.warning("⚠️ Webhook payload missing 'entry' field")
                return {
                    "success": False,
                    "error": "Missing entry field",
                    "processed_count": 0,
                    "errors": ["Invalid webhook structure"]
                }
            
            entries = webhook_data.get("entry", [])
            if not entries:
                logger.info("📭 Empty webhook - no entries to process")
                return {
                    "success": True,
                    "processed_count": 0,
                    "message": "No entries to process"
                }
            
            logger.info(f"📋 Processing {len(entries)} webhook entries")
            
            # Process each entry
            for entry_idx, entry in enumerate(entries):
                try:
                    logger.info(f"🔍 Processing entry {entry_idx + 1}/{len(entries)}")
                    
                    # Extract messaging events
                    changes = entry.get("changes", [])
                    if not changes:
                        logger.info(f"📭 Entry {entry_idx + 1} has no changes")
                        continue
                    
                    for change_idx, change in enumerate(changes):
                        try:
                            # Only process messages field
                            if change.get("field") != "messages":
                                logger.info(f"⏭️ Skipping non-message change: {change.get('field')}")
                                continue
                            
                            value = change.get("value", {})
                            if not value:
                                logger.warning(f"⚠️ Empty value in change {change_idx}")
                                continue
                            
                            # Extract phone_number_id for routing
                            phone_number_id = value.get("metadata", {}).get("phone_number_id")
                            if not phone_number_id:
                                logger.warning("⚠️ No phone_number_id in webhook metadata")
                                errors.append(f"Entry {entry_idx}: Missing phone_number_id")
                                continue
                            
                            logger.info(f"📞 Routing for phone_number_id: {phone_number_id}")
                            
                            # Find tenant for this phone number
                            tenant_info = await self._find_tenant_for_phone(phone_number_id, db)
                            if not tenant_info:
                                logger.warning(f"⚠️ No tenant found for phone_number_id: {phone_number_id}")
                                errors.append(f"Entry {entry_idx}: No tenant for phone {phone_number_id}")
                                continue
                            
                            logger.info(f"👤 Found tenant: User {tenant_info['user_id']}, WABA {tenant_info['waba_id']}")
                            
                            # Process messages for this tenant
                            messages = value.get("messages", [])
                            if not messages:
                                logger.info(f"📭 No messages in entry {entry_idx}")
                                continue
                            
                            logger.info(f"💬 Processing {len(messages)} messages for tenant {tenant_info['user_id']}")
                            
                            for message_idx, message in enumerate(messages):
                                try:
                                    processed = await self._process_tenant_message(
                                        message, tenant_info, db
                                    )
                                    processed_messages.append(processed)
                                    logger.info(f"✅ Processed message {message_idx + 1}/{len(messages)} for tenant {tenant_info['user_id']}")
                                    
                                except Exception as msg_error:
                                    error_msg = f"Entry {entry_idx}, Message {message_idx}: {str(msg_error)}"
                                    logger.error(f"❌ Message processing error: {error_msg}")
                                    errors.append(error_msg)
                                    continue
                            
                        except Exception as change_error:
                            error_msg = f"Entry {entry_idx}, Change {change_idx}: {str(change_error)}"
                            logger.error(f"❌ Change processing error: {error_msg}")
                            errors.append(error_msg)
                            continue
                            
                except Exception as entry_error:
                    error_msg = f"Entry {entry_idx}: {str(entry_error)}"
                    logger.error(f"❌ Entry processing error: {error_msg}")
                    errors.append(error_msg)
                    continue
            
            # Calculate processing metrics
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            result = {
                "success": len(errors) == 0,
                "processed_count": len(processed_messages),
                "error_count": len(errors),
                "processing_time_seconds": processing_time,
                "messages_per_second": len(processed_messages) / processing_time if processing_time > 0 else 0,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if errors:
                result["errors"] = errors[:10]  # Limit error details
                logger.warning(f"⚠️ Webhook processed with {len(errors)} errors")
            
            logger.info(f"✅ Webhook routing completed: {len(processed_messages)} messages processed in {processing_time:.2f}s")
            
            # Store webhook processing record for analytics
            await self._store_webhook_record(webhook_data, result, db)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Webhook routing failed: {str(e)}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            # Ensure we return a proper error response
            return {
                "success": False,
                "error": str(e),
                "processed_count": len(processed_messages),
                "error_count": len(errors) + 1,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _find_tenant_for_phone(
        self, 
        phone_number_id: str, 
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Find tenant (user) for given phone_number_id"""
        try:
            query = (
                select(
                    WhatsAppBusinessAccount.user_id,
                    WhatsAppBusinessAccount.id.label("waba_id"),
                    WhatsAppPhoneNumber.id.label("phone_id")
                )
                .join(WhatsAppPhoneNumber)
                .where(
                    and_(
                        WhatsAppPhoneNumber.phone_number_id == phone_number_id,
                        WhatsAppBusinessAccount.is_active == True
                    )
                )
            )
            
            result = await db.execute(query)
            row = result.first()
            
            if row:
                return {
                    "user_id": row.user_id,
                    "waba_id": row.waba_id,
                    "phone_id": row.phone_id
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Tenant lookup failed: {str(e)}")
            return None
    
    async def _process_tenant_message(
        self, 
        message_data: Dict[str, Any], 
        tenant_info: Dict[str, Any], 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Process message for specific tenant with enhanced content handling
        
        Enhanced features:
        - Comprehensive message type support
        - Privacy-focused content processing
        - Content hashing for deduplication
        - Contact information extraction
        - Message status tracking
        - Error handling and recovery
        
        Args:
            message_data: Message data from webhook
            tenant_info: Tenant routing information
            db: Database session
            
        Returns:
            Processing result
        """
        try:
            message_id = message_data.get("id")
            if not message_id:
                raise WhatsAppError("Message missing ID")
            
            logger.info(f"📨 Processing message {message_id} for tenant {tenant_info['user_id']}")
            
            # Extract message details
            message_type = message_data.get("type", "text")
            timestamp = message_data.get("timestamp")
            
            # Extract contact information
            contact_phone = message_data.get("from")
            contact_profile = message_data.get("profile", {})
            contact_name = contact_profile.get("name", "")
            
            # Process message content based on type
            content_hash = None
            template_name = None
            
            if message_type == "text" and "text" in message_data:
                # Hash text content for privacy and deduplication
                message_text = message_data["text"]["body"]
                content_hash = self._hash_content(message_text)
                logger.info(f"📝 Text message content hashed: {content_hash[:8]}...")
                
            elif message_type == "template" and "template" in message_data:
                # Extract template information
                template_data = message_data["template"]
                template_name = template_data.get("name")
                logger.info(f"📋 Template message: {template_name}")
                
            elif message_type in ["image", "document", "audio", "video", "sticker"]:
                # Handle media messages
                if "media" in message_data:
                    media_id = message_data["media"]["id"]
                    content_hash = self._hash_content(media_id)  # Hash media ID for deduplication
                    logger.info(f"📎 Media message ({message_type}): {content_hash[:8]}...")
                else:
                    logger.warning(f"⚠️ Media message missing media data: {message_id}")
            
            elif message_type == "location":
                # Handle location messages
                if "location" in message_data:
                    location = message_data["location"]
                    content_hash = self._hash_content(f"{location.get('latitude')},{location.get('longitude')}")
                    logger.info(f"📍 Location message: {content_hash[:8]}...")
            
            elif message_type == "contacts":
                # Handle contact messages
                if "contacts" in message_data:
                    contacts = message_data["contacts"]
                    content_hash = self._hash_content(str(contacts))
                    logger.info(f"👤 Contact message with {len(contacts)} contacts")
            
            else:
                logger.warning(f"⚠️ Unsupported message type: {message_type}")
                content_hash = self._hash_content(str(message_data))
            
            # Check for duplicate messages
            existing_message = await db.execute(
                select(WhatsAppMessageV2).where(
                    and_(
                        WhatsAppMessageV2.message_id == message_id,
                        WhatsAppMessageV2.user_id == tenant_info["user_id"]
                    )
                )
            )
            if existing_message.scalar_one_or_none():
                logger.info(f"🔄 Duplicate message {message_id} - skipping")
                return {
                    "status": "duplicate",
                    "message_id": message_id,
                    "tenant_id": tenant_info["user_id"]
                }
            
            # Create message record
            message_record = WhatsAppMessageV2(
                user_id=tenant_info["user_id"],
                waba_id=tenant_info["waba_id"],
                phone_number_id=tenant_info["phone_id"],
                message_id=message_id,
                direction="inbound",
                contact_phone=contact_phone,
                contact_name=contact_name,
                message_type=message_type,
                template_name=template_name,
                content_hash=content_hash,
                status="received"
            )
            
            # Set timestamp if available
            if timestamp:
                try:
                    # Convert Unix timestamp to datetime
                    from datetime import datetime
                    message_timestamp = datetime.fromtimestamp(int(timestamp))
                    
                    # Update timestamp using SQLAlchemy
                    from sqlalchemy import update
                    update_stmt = (
                        update(WhatsAppMessageV2)
                        .where(WhatsAppMessageV2.id == message_record.id)
                        .values(created_at=message_timestamp)
                    )
                    await db.execute(update_stmt)
                    
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ Invalid timestamp: {timestamp}")
            
            db.add(message_record)
            await db.flush()  # Get the ID for AI processing
            
            # Process with AI (async, don't wait) - create new session
            asyncio.create_task(
                self._process_message_with_ai_async(message_record, message_data)
            )
            
            logger.info(f"✅ Stored message {message_id} for tenant {tenant_info['user_id']}")
            
            return {
                "status": "processed",
                "message_id": message_id,
                "tenant_id": tenant_info["user_id"],
                "message_type": message_type,
                "contact_phone": contact_phone
            }
            
        except Exception as e:
            logger.error(f"❌ Message processing failed for {message_data.get('id', 'unknown')}: {str(e)}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            raise WhatsAppError(f"Message processing failed: {str(e)}")
    
    async def configure_webhook(
        self, 
        user_id: int, 
        phone_number_id: str,
        webhook_url: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Configure webhook for a specific phone number
        
        Args:
            user_id: User configuring the webhook
            phone_number_id: Phone number to configure webhook for
            webhook_url: Webhook URL to receive messages
            db: Database session
            
        Returns:
            Configuration result
        """
        try:
            logger.info(f"🔧 Configuring webhook for user {user_id}, phone {phone_number_id}")
            
            # Get user's WABA and access token
            waba_info = await self._get_user_waba_for_phone(user_id, phone_number_id, db)
            if not waba_info:
                raise WhatsAppError("Phone number not found or not authorized")
            
            # Decrypt access token
            encrypted_token_data = token_encryption.decrypt_token(waba_info["access_token_encrypted"])
            if not encrypted_token_data:
                raise WhatsAppError("Failed to decrypt access token")
            access_token = encrypted_token_data["access_token"]
            
            # Configure webhook with Meta API
            result = await self._configure_meta_webhook(
                phone_number_id, webhook_url, access_token
            )
            
            # Update WABA record with webhook status
            from sqlalchemy import update
            update_stmt = (
                update(WhatsAppBusinessAccount)
                .where(WhatsAppBusinessAccount.id == waba_info["waba_record_id"])
                .values(
                    webhook_configured=True,
                    last_sync=datetime.utcnow()
                )
            )
            await db.execute(update_stmt)
            await db.commit()
            
            logger.info(f"✅ Webhook configured successfully for phone {phone_number_id}")
            
            return {
                "success": True,
                "phone_number_id": phone_number_id,
                "webhook_url": webhook_url,
                "status": "configured"
            }
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Webhook configuration failed: {str(e)}")
            raise WhatsAppError(f"Webhook configuration failed: {str(e)}")
    
    async def _configure_meta_webhook(
        self, 
        phone_number_id: str, 
        webhook_url: str,
        access_token: str
    ) -> Dict[str, Any]:
        """
        Configure webhook URL with Meta WhatsApp API
        
        Args:
            phone_number_id: Phone number ID
            webhook_url: Webhook URL
            access_token: Access token
            
        Returns:
            Configuration result
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.meta_graph_url}/{phone_number_id}"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                # Configure webhook settings
                payload = {
                    "webhooks": {
                        "url": webhook_url,
                        "status": "enabled"
                    }
                }
                
                async with session.post(url, headers=headers, json=payload) as response:
                    logger.info(f"🔧 Configuring webhook for phone {phone_number_id}")
                    
                    if response.status == 200:
                        response_data = await response.json()
                        logger.info(f"✅ Webhook configured: {response_data}")
                        return response_data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Webhook configuration failed: {error_text}")
                        raise WhatsAppError(f"Meta API webhook configuration failed: {error_text}")
                        
        except Exception as e:
            logger.error(f"❌ Meta webhook configuration error: {str(e)}")
            raise WhatsAppError(f"Meta webhook configuration error: {str(e)}")
    
    async def get_webhook_status(
        self, 
        user_id: int, 
        phone_number_id: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get webhook configuration status for a phone number
        
        Args:
            user_id: User requesting status
            phone_number_id: Phone number to check
            db: Database session
            
        Returns:
            Webhook status information
        """
        try:
            # Get WABA info
            waba_info = await self._get_user_waba_for_phone(user_id, phone_number_id, db)
            if not waba_info:
                raise WhatsAppError("Phone number not found or not authorized")
            
            # Get WABA record
            waba_query = select(WhatsAppBusinessAccount).where(
                WhatsAppBusinessAccount.id == waba_info["waba_record_id"]
            )
            waba_result = await db.execute(waba_query)
            waba_record = waba_result.scalar_one_or_none()
            
            if not waba_record:
                raise WhatsAppError("WABA record not found")
            
            return {
                "phone_number_id": phone_number_id,
                "webhook_configured": waba_record.webhook_configured,
                "last_sync": waba_record.last_sync.isoformat() if waba_record.last_sync is not None else None,
                "waba_id": waba_record.waba_id,
                "business_name": waba_record.business_name
            }
            
        except Exception as e:
            logger.error(f"❌ Webhook status check failed: {str(e)}")
            raise WhatsAppError(f"Webhook status check failed: {str(e)}")
    
    async def _store_webhook_record(
        self, 
        webhook_data: Dict[str, Any], 
        result: Dict[str, Any],
        db: AsyncSession
    ) -> None:
        """
        Store webhook processing record for analytics and debugging
        
        Args:
            webhook_data: Original webhook payload
            result: Processing result
            db: Database session
        """
        try:
            # Extract key information for analytics
            entry_count = len(webhook_data.get("entry", []))
            total_messages = sum(
                len(change.get("value", {}).get("messages", []))
                for entry in webhook_data.get("entry", [])
                for change in entry.get("changes", [])
                if change.get("field") == "messages"
            )
            
            # Create webhook record
            webhook_record = WhatsAppWebhook(
                webhook_id=webhook_data.get("id", f"webhook_{datetime.utcnow().isoformat()}"),
                event_type="messages",
                message_id=None,  # Multiple messages possible
                status=None,      # Multiple statuses possible
                webhook_data=webhook_data,  # Store full payload for debugging
                processed=True,
                processed_at=datetime.utcnow()
            )
            
            db.add(webhook_record)
            logger.info(f"📊 Stored webhook analytics record: {webhook_record.webhook_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store webhook record: {str(e)}")
            # Don't raise - this is not critical for message processing
    
    async def _process_message_with_ai(
        self, 
        message_record: WhatsAppMessageV2, 
        message_data: Dict[str, Any],
        db: AsyncSession
    ) -> None:
        """
        Process incoming message with AI for analysis and response generation
        
        Args:
            message_record: Stored message record
            message_data: Original message data from webhook
            db: Database session
        """
        try:
            # TODO: Implement AI processing
            # This is a placeholder for future AI integration
            
            # Example AI processing logic:
            # 1. Extract message content (if available)
            # 2. Analyze sentiment and intent
            # 3. Generate automated responses
            # 4. Update message record with AI insights
            
            message_text = ""
            if "text" in message_data:
                message_text = message_data["text"]["body"]
            
            # Placeholder for AI analysis
            ai_analysis = {
                "sentiment": "neutral",  # positive, negative, neutral
                "intent": "general_inquiry",  # greeting, question, complaint, etc.
                "priority": "medium",  # high, medium, low
                "auto_response": False,
                "confidence": 0.85
            }
            
            # Update message record with AI insights using SQLAlchemy update
            from sqlalchemy import update
            update_stmt = (
                update(WhatsAppMessageV2)
                .where(WhatsAppMessageV2.id == message_record.id)
                .values(
                    ai_processed=True,
                    predicted_priority=ai_analysis["priority"],
                    predicted_context=ai_analysis["intent"],
                    prediction_confidence=ai_analysis["confidence"]
                )
            )
            await db.execute(update_stmt)
            
            logger.info(f"🤖 AI processed message {message_record.message_id}: {ai_analysis}")
            
        except Exception as e:
            logger.error(f"❌ AI processing failed for message {message_record.message_id}: {str(e)}")
            # Don't raise - AI processing failure shouldn't break message storage
    
    async def _process_message_with_ai_async(
        self, 
        message_record: WhatsAppMessageV2, 
        message_data: Dict[str, Any]
    ) -> None:
        """
        Async wrapper for AI processing that creates its own database session
        
        Args:
            message_record: Stored message record
            message_data: Original message data from webhook
        """
        from db.db import get_async_session
        
        async for session in get_async_session():
            try:
                await self._process_message_with_ai(message_record, message_data, session)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"❌ AI processing session error: {str(e)}")
            finally:
                await session.close()
            break  # Only run once

# Global service instance
multi_tenant_whatsapp_service = MultiTenantWhatsAppService()
