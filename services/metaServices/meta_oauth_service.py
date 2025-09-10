"""
Meta OAuth Service for WhatsApp Business API
Handles authentication, token management, and WABA setup
"""

import httpx
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from config.settings import get_settings
from utils.logger import logger
from utils.encryption import token_encryption
from db.models import User, WhatsAppBusinessAccount, TenantConfiguration

settings = get_settings()

class MetaOAuthService:
    """
    Meta OAuth Service for WhatsApp Business API
    Handles multi-tenant authentication and WABA management
    """
    
    def __init__(self):
        self.meta_app_id = settings.META_APP_ID
        self.meta_app_secret = settings.META_APP_SECRET
        self.redirect_uri = settings.META_REDIRECT_URI
        self.base_url = "https://graph.facebook.com/v18.0"
        
        # Required permissions for WhatsApp Business
        self.required_permissions = [
            "whatsapp_business_management",
            "whatsapp_business_messaging", 
            "business_management",
            "pages_messaging",
            "pages_read_engagement"
        ]
        
        logger.info("🔐 Meta OAuth Service initialized")
        logger.info(f"🔐 App ID: {self.meta_app_id[:10]}...")
        logger.info(f"🔐 Redirect URI: {self.redirect_uri}")
        logger.info(f"🔐 Required permissions: {', '.join(self.required_permissions)}")
    
    def get_authorization_url(self, state: str) -> str:
        """
        Generate Meta OAuth authorization URL
        
        Args:
            state: CSRF protection state parameter
            
        Returns:
            Authorization URL for Meta OAuth
        """
        permissions = ",".join(self.required_permissions)
        
        auth_url = (
            f"https://www.facebook.com/v18.0/dialog/oauth?"
            f"client_id={self.meta_app_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"scope={permissions}&"
            f"state={state}&"
            f"response_type=code"
        )
        
        logger.info(f"🔐 Generated Meta OAuth URL for WhatsApp Business access - App ID: {self.meta_app_id[:10]}..., State: {state}")
        logger.info(f"🔐 OAuth URL: {auth_url}")
        return auth_url
    
    async def handle_oauth_callback(
        self, 
        code: str, 
        state: str, 
        user_email: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Handle Meta OAuth callback and setup WhatsApp Business Account
        
        Args:
            code: Authorization code from Meta
            state: CSRF state parameter
            user_email: Email of the user (tenant)
            db: Database session
            
        Returns:
            OAuth result with WABA details
        """
        logger.info(f"🔐 Starting Meta OAuth callback processing - Code: {code[:20]}..., State: {state}, User: {user_email}")
        
        try:
            # Exchange code for access token
            logger.info("🔄 Step 1: Exchanging authorization code for access token")
            token_data = await self._exchange_code_for_token(code)
            logger.info(f"✅ Token exchange successful - Access token: {token_data.get('access_token', '')[:20]}...")
            
            # Get user info from Meta
            logger.info("🔄 Step 2: Retrieving user info from Meta Graph API")
            user_info = await self._get_meta_user_info(token_data["access_token"])
            logger.info(f"✅ User info retrieved - Meta User ID: {user_info.get('id')}, Name: {user_info.get('name')}")
            
            # Get WhatsApp Business Accounts
            logger.info("🔄 Step 3: Retrieving WhatsApp Business Accounts")
            waba_data = await self._get_user_whatsapp_accounts(token_data["access_token"])
            logger.info(f"✅ WABA data retrieved - Found {len(waba_data)} WhatsApp accounts")
            
            # Store user and WABA data
            logger.info("🔄 Step 4: Storing tenant WhatsApp data in database")
            result = await self._store_tenant_whatsapp_data(
                user_email=user_email,
                token_data=token_data,
                user_info=user_info,
                waba_data=waba_data,
                db=db
            )
            
            logger.info(f"✅ Meta OAuth completed successfully for {user_email} - WABAs: {len(result['whatsapp_accounts'])}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Meta OAuth callback failed: {str(e)}")
            logger.error(f"❌ Full error details: {type(e).__name__}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=400, detail=f"OAuth callback failed: {str(e)}")
    
    async def _exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token"""
        logger.info("🔄 Starting token exchange process")
        logger.info(f"🔄 Code to exchange: {code[:20]}...")
        logger.info(f"🔄 Using App ID: {self.meta_app_id[:10]}...")
        logger.info(f"🔄 Using Redirect URI: {self.redirect_uri}")
        
        async with httpx.AsyncClient() as client:
            logger.info("🔄 Making POST request to Meta token endpoint")
            response = await client.post(
                f"{self.base_url}/oauth/access_token",
                data={
                    "client_id": self.meta_app_id,
                    "client_secret": self.meta_app_secret,
                    "redirect_uri": self.redirect_uri,
                    "code": code
                }
            )
            logger.error(f"Meta token exchange response: status={response.status_code}, body={response.text}")
            
            if response.status_code != 200:
                logger.error(f"❌ Token exchange failed with status {response.status_code}")
                logger.error(f"❌ Response body: {response.text}")
                raise Exception(f"Token exchange failed: {response.text}")
            
            token_data = response.json()
            logger.info("✅ Short-lived token exchange successful")
            logger.info(f"✅ Token type: {token_data.get('token_type')}")
            logger.info(f"✅ Expires in: {token_data.get('expires_in')} seconds")
            
            # Exchange short-lived token for long-lived token
            logger.info("🔄 Exchanging short-lived token for long-lived token")
            long_lived_response = await client.get(
                f"{self.base_url}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.meta_app_id,
                    "client_secret": self.meta_app_secret,
                    "fb_exchange_token": token_data["access_token"]
                }
            )
            logger.error(f"Meta long-lived token exchange response: status={long_lived_response.status_code}, body={long_lived_response.text}")
            
            if long_lived_response.status_code == 200:
                long_lived_data = long_lived_response.json()
                token_data.update(long_lived_data)
                logger.info("🔐 Long-lived token exchange successful")
                logger.info(f"🔐 Long-lived token expires in: {long_lived_data.get('expires_in')} seconds")
            else:
                logger.warning("⚠️ Long-lived token exchange failed, using short-lived token")
            
            logger.info("✅ Token exchange process completed")
            return token_data
    
    async def _get_meta_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from Meta Graph API"""
        logger.info("🔍 Calling Meta Graph API /me endpoint")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/me",
                params={
                    "fields": "id,name,email",
                    "access_token": access_token
                }
            )
            
            logger.info(f"🔍 Meta /me response status: {response.status_code}")
            logger.info(f"🔍 Meta /me response body: {response.text}")
            
            if response.status_code != 200:
                logger.error(f"❌ Failed to get user info from Meta: {response.text}")
                raise Exception(f"Failed to get user info: {response.text}")
            
            user_info = response.json()
            logger.info(f"✅ Meta user info retrieved: {user_info}")
            return user_info
    
    async def _get_user_whatsapp_accounts(self, access_token: str) -> List[Dict[str, Any]]:
        """Get WhatsApp Business Accounts for the user"""
        logger.info("🔍 Retrieving WhatsApp Business Accounts from Meta")
        async with httpx.AsyncClient() as client:
            # Get businesses owned by the user
            logger.info("🔍 Getting user businesses")
            businesses_response = await client.get(
                f"{self.base_url}/me/businesses",
                params={
                    "access_token": access_token
                }
            )
            
            logger.info(f"🔍 Businesses response status: {businesses_response.status_code}")
            logger.info(f"🔍 Businesses response body: {businesses_response.text}")
            
            if businesses_response.status_code != 200:
                logger.error(f"❌ Failed to get businesses: {businesses_response.text}")
                raise Exception(f"Failed to get businesses: {businesses_response.text}")
            
            businesses = businesses_response.json().get("data", [])
            logger.info(f"✅ Found {len(businesses)} businesses")
            
            whatsapp_accounts = []
            
            for business in businesses:
                business_id = business["id"]
                logger.info(f"🔍 Processing business {business_id}: {business.get('name')}")
                
                # Get WhatsApp Business Accounts for each business
                waba_response = await client.get(
                    f"{self.base_url}/{business_id}/whatsapp_business_accounts",
                    params={
                        "access_token": access_token
                    }
                )
                
                logger.info(f"🔍 WABA response for business {business_id} - status: {waba_response.status_code}")
                logger.info(f"🔍 WABA response body: {waba_response.text}")
                
                if waba_response.status_code == 200:
                    wabas = waba_response.json().get("data", [])
                    logger.info(f"✅ Found {len(wabas)} WABAs in business {business_id}")
                    
                    for waba in wabas:
                        waba_id = waba["id"]
                        logger.info(f"🔍 Processing WABA {waba_id}: {waba.get('name')}")
                        
                        # Get phone numbers for each WABA
                        phones_response = await client.get(
                            f"{self.base_url}/{waba_id}/phone_numbers",
                            params={
                                "access_token": access_token
                            }
                        )
                        
                        logger.info(f"🔍 Phone numbers response for WABA {waba_id} - status: {phones_response.status_code}")
                        logger.info(f"🔍 Phone numbers response body: {phones_response.text}")
                        
                        if phones_response.status_code == 200:
                            phones = phones_response.json().get("data", [])
                            logger.info(f"✅ Found {len(phones)} phone numbers in WABA {waba_id}")
                            
                            for phone in phones:
                                whatsapp_accounts.append({
                                    "business_id": business_id,
                                    "business_name": business.get("name"),
                                    "waba_id": waba_id,
                                    "waba_name": waba.get("name"),
                                    "phone_number_id": phone["id"],
                                    "phone_number": phone.get("display_phone_number"),
                                    "verified_name": phone.get("verified_name"),
                                    "status": phone.get("status"),
                                    "messaging_limit_tier": phone.get("messaging_limit_tier", "STANDARD")
                                })
                        else:
                            logger.warning(f"⚠️ Failed to get phone numbers for WABA {waba_id}")
                else:
                    logger.warning(f"⚠️ Failed to get WABAs for business {business_id}")
            
            logger.info(f"📱 Total WhatsApp Business phone numbers found: {len(whatsapp_accounts)}")
            return whatsapp_accounts
    
    async def _store_tenant_whatsapp_data(
        self,
        user_email: str,
        token_data: Dict[str, Any],
        user_info: Dict[str, Any],
        waba_data: List[Dict[str, Any]],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Store tenant WhatsApp data in database"""
        logger.info(f"💾 Storing WhatsApp data for user {user_email}")
        
        # Get or update user
        logger.info("🔍 Looking up user in database")
        result = await db.execute(select(User).where(User.email == user_email))
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"❌ User {user_email} not found in database")
            raise Exception(f"User {user_email} not found")
        
        logger.info(f"✅ User found: ID {user.id}, Email {user.email}")
        
        # Encrypt and store Meta access token
        logger.info("🔐 Encrypting and storing Meta access token")
        encrypted_token = token_encryption.encrypt_token({"access_token": token_data["access_token"]})
        expires_at = None
        if "expires_in" in token_data:
            expires_at = datetime.utcnow() + timedelta(seconds=int(token_data["expires_in"]))
        
        # Update user with Meta OAuth data using proper SQLAlchemy syntax
        logger.info("💾 Updating user with Meta OAuth data")
        from sqlalchemy import update
        
        # Update user record
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(
                meta_user_id=user_info["id"],
                meta_access_token_encrypted=encrypted_token,
                meta_token_expires_at=expires_at,
                meta_permissions=self.required_permissions
            )
        )
        
        # Store WhatsApp Business Accounts
        logger.info(f"💾 Storing {len(waba_data)} WhatsApp Business Accounts")
        stored_accounts = []
        for waba in waba_data:
            logger.info(f"💾 Processing WABA: {waba['waba_id']} - {waba['phone_number']}")
            
            # Check if WABA already exists
            existing_waba = await db.execute(
                select(WhatsAppBusinessAccount).where(
                    WhatsAppBusinessAccount.phone_number_id == waba["phone_number_id"]
                )
            )
            existing_waba = existing_waba.scalar_one_or_none()
            
            if existing_waba:
                logger.info(f"✅ WABA {waba['waba_id']} already exists, updating")
                # Update existing WABA using proper SQLAlchemy syntax
                await db.execute(
                    update(WhatsAppBusinessAccount)
                    .where(WhatsAppBusinessAccount.id == existing_waba.id)
                    .values(
                        user_id=user.id,
                        waba_name=waba["waba_name"],
                        phone_number=waba["phone_number"],
                        display_phone_number=waba["phone_number"],
                        status=waba["status"],
                        messaging_tier=waba["messaging_limit_tier"].lower(),
                        is_active=True,
                        updated_at=datetime.utcnow()
                    )
                )
                
                stored_accounts.append(existing_waba)
            else:
                logger.info(f"🆕 Creating new WABA {waba['waba_id']}")
                # Create new WABA
                new_waba = WhatsAppBusinessAccount(
                    user_id=user.id,
                    waba_id=waba["waba_id"],
                    waba_name=waba["waba_name"],
                    phone_number_id=waba["phone_number_id"],
                    phone_number=waba["phone_number"],
                    display_phone_number=waba["phone_number"],
                    status=waba["status"],
                    messaging_tier=waba["messaging_limit_tier"].lower(),
                    is_active=True
                )
                
                db.add(new_waba)
                stored_accounts.append(new_waba)
        
        # Create or update tenant configuration
        logger.info("💾 Updating tenant configuration")
        config_result = await db.execute(
            select(TenantConfiguration).where(TenantConfiguration.user_id == user.id)
        )
        config = config_result.scalar_one_or_none()
        
        if not config:
            logger.info("🆕 Creating new tenant configuration")
            config = TenantConfiguration(
                user_id=user.id,
                whatsapp_enabled=True,
                ai_processing_enabled=True
            )
            db.add(config)
        else:
            logger.info("✅ Updating existing tenant configuration")
            # Update existing configuration using proper SQLAlchemy syntax
            await db.execute(
                update(TenantConfiguration)
                .where(TenantConfiguration.id == config.id)
                .values(
                    whatsapp_enabled=True,
                    updated_at=datetime.utcnow()
                )
            )
        
        await db.commit()
        logger.info("✅ Database transaction committed successfully")
        
        result = {
            "success": True,
            "user_id": user.id,
            "meta_user_id": user_info["id"],
            "whatsapp_accounts": [
                {
                    "waba_id": acc.waba_id,
                    "phone_number_id": acc.phone_number_id,
                    "phone_number": acc.phone_number,
                    "status": acc.status,
                    "messaging_tier": acc.messaging_tier
                }
                for acc in stored_accounts
            ]
        }
        
        logger.info(f"✅ WhatsApp data storage completed - {len(result['whatsapp_accounts'])} accounts stored")
        return result
    
    async def refresh_token_if_needed(self, user_id: int, db: AsyncSession) -> bool:
        """
        Refresh Meta access token if it's expiring soon
        
        Args:
            user_id: User ID to refresh token for
            db: Database session
            
        Returns:
            True if token was refreshed or is still valid
        """
        logger.info(f"🔄 Checking token refresh needed for user {user_id}")
        try:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if not user or user.meta_access_token_encrypted is None:
                logger.warning(f"⚠️ No Meta token found for user {user_id}")
                return False
            
            logger.info(f"✅ Meta token found for user {user_id}")
            
            # Check if token expires within next hour
            if user.meta_token_expires_at is not None:
                time_until_expiry = user.meta_token_expires_at - datetime.utcnow()
                logger.info(f"⏰ Token expires in {time_until_expiry.total_seconds()} seconds")
                if time_until_expiry.total_seconds() < 3600:  # Less than 1 hour
                    logger.warning(f"⚠️ Meta token expiring soon for user {user_id}")
                    # TODO: Implement token refresh logic
                    # Meta long-lived tokens typically last 60 days
                    return False
            
            logger.info(f"✅ Token is still valid for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Token refresh check failed for user {user_id}: {str(e)}")
            return False
    
    async def get_tenant_access_token(self, user_id: int, db: AsyncSession) -> str:
        """
        Get decrypted access token for a tenant
        
        Args:
            user_id: User ID
            db: Database session
            
        Returns:
            Decrypted access token
        """
        logger.info(f"🔑 Retrieving access token for user {user_id}")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user or user.meta_access_token_encrypted is None:
            logger.error(f"❌ No Meta access token found for user {user_id}")
            raise Exception(f"No Meta access token found for user {user_id}")
        
        logger.info(f"✅ Encrypted token found for user {user_id}")
        
        # Check if token refresh is needed
        if not await self.refresh_token_if_needed(user_id, db):
            logger.warning(f"⚠️ Meta token may be expired for user {user_id}")
        
        # Decrypt the token (it was stored as a dict with access_token key)
        encrypted_token_value = user.meta_access_token_encrypted
        if not isinstance(encrypted_token_value, str):
            logger.error(f"❌ Invalid token format for user {user_id}: {type(encrypted_token_value)}")
            raise Exception(f"Invalid token format for user {user_id}")
            
        logger.info(f"🔐 Decrypting token for user {user_id}")
        decrypted_data = token_encryption.decrypt_token(encrypted_token_value)
        if not decrypted_data or "access_token" not in decrypted_data:
            logger.error(f"❌ Invalid encrypted token for user {user_id}: {decrypted_data}")
            raise Exception(f"Invalid encrypted token for user {user_id}")
        
        access_token = decrypted_data["access_token"]
        logger.info(f"✅ Token decrypted successfully for user {user_id} - Token: {access_token[:20]}...")
        return access_token

# Global service instance
meta_oauth_service = MetaOAuthService()
