"""
Gmail OAuth2 Service
Handles Google OAuth2 flow for Gmail access with encrypted token storage
PRIVACY-FOCUSED: Tokens are encrypted at rest
"""

import os
import json
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from fastapi import HTTPException
from utils.logger import logger
from datetime import datetime

# Import Google APIs lazily to avoid blocking
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_APIS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Google APIs not available: {e}")
    GOOGLE_APIS_AVAILABLE = False

# Import other dependencies - Use lazy imports to avoid circular dependencies
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select, update
    # Import models lazily when needed to avoid circular imports
    from utils.encryption import token_encryption
    FULL_FEATURES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Some features not available: {e}")
    FULL_FEATURES_AVAILABLE = False

from dotenv import load_dotenv
load_dotenv()

# OAuth2 configuration - Direct environment access to avoid circular imports
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

# Gmail API scopes - READ-ONLY for privacy
SCOPES = [
    'openid',  # Required for OAuth2
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/gmail.readonly'  # READ-ONLY access
]

class GmailOAuthService:
    """Service for handling Gmail OAuth2 authentication with privacy focus"""
    
    def __init__(self):
        # Validate OAuth credentials are available
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            error_msg = f"Google OAuth credentials not configured - GOOGLE_CLIENT_ID: {'SET' if GOOGLE_CLIENT_ID else 'MISSING'}, GOOGLE_CLIENT_SECRET: {'SET' if GOOGLE_CLIENT_SECRET else 'MISSING'}"
            logger.error(error_msg)
            self.client_config = None
            return
        
        logger.info(f"🔐 Initializing Gmail OAuth with Client ID: {GOOGLE_CLIENT_ID[:20]}...")
        
        self.client_config = {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        }
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Generate OAuth2 authorization URL for READ-ONLY Gmail access
        
        Args:
            state: Optional state parameter for security
            
        Returns:
            Authorization URL for Gmail READ-ONLY access
        """
        try:
            flow = Flow.from_client_config(
                self.client_config,
                scopes=SCOPES,
                redirect_uri=GOOGLE_REDIRECT_URI
            )
            
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                state=state,
                prompt='consent'  # Force consent to get refresh token
            )
            
            logger.info("🔒 Generated OAuth URL for READ-ONLY Gmail access")
            return auth_url
            
        except Exception as e:
            logger.error("Failed to generate OAuth URL")
            raise HTTPException(status_code=500, detail="Failed to generate authorization URL")
    
    async def handle_callback(self, code: str, state: Optional[str], db: AsyncSession) -> Dict[str, Any]:
        """
        Handle OAuth2 callback and save ENCRYPTED token to database
        
        Args:
            code: Authorization code from Google
            state: State parameter (should contain user_id)
            db: Database session
            
        Returns:
            User information and token status
        """
        # Import User model lazily to avoid circular imports
        from db.models import User
        
        try:
            # Create flow with the exact same configuration as authorization
            flow = Flow.from_client_config(
                self.client_config,
                scopes=SCOPES,
                redirect_uri=GOOGLE_REDIRECT_URI
            )
            
            # Exchange code for token
            try:
                flow.fetch_token(code=code)
                credentials = flow.credentials
                logger.info("🔒 OAuth callback - Token exchange successful")
            except Exception as token_error:
                logger.error("OAuth callback - Token exchange failed")
                raise HTTPException(status_code=400, detail="Invalid authorization code")
            
            # Get user info from Google
            try:
                user_info = self._get_user_info(credentials)
                logger.info("✓ Successfully retrieved user info from Google")
            except Exception as user_info_error:
                logger.error(f"Failed to get user info: {user_info_error}")
                raise HTTPException(status_code=400, detail="Failed to retrieve user information")
            
            email = user_info.get('email')
            
            if not email:
                logger.error("No email found in user info")
                raise HTTPException(status_code=400, detail="Could not retrieve email from Google")

            logger.info(f"🔐 Processing OAuth callback for email: {email}")

            # Find or create user
            try:
                query = await db.execute(select(User).where(User.email == email))
                user = query.scalar_one_or_none()
                logger.info(f"Database query result: {'Found existing user' if user else 'User not found, will create new'}")
            except Exception as db_error:
                logger.error(f"Database query failed: {db_error}")
                raise HTTPException(status_code=500, detail="Database query failed")

            # Encrypt token
            try:
                encrypted_token = token_encryption.encrypt_token(self._credentials_to_dict(credentials))
                logger.info("✓ Token encrypted successfully")
            except Exception as encryption_error:
                logger.error(f"Token encryption failed: {encryption_error}")
                raise HTTPException(status_code=500, detail="Token encryption failed")
            
            if not user:
                # Create new user with OAuth-only authentication
                try:
                    user = User(
                        email=email,
                        full_name=user_info.get('name'),
                        google_id=user_info.get('sub'),
                        auth_method='oauth',
                        is_active=True,
                        gmail_token_encrypted=encrypted_token
                    )
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                    logger.info(f"🔒 Created new OAuth user: {email}")
                except Exception as create_error:
                    logger.error(f"Failed to create new user: {create_error}")
                    await db.rollback()
                    raise HTTPException(status_code=500, detail="Failed to create user account")
            else:
                # Update existing user with encrypted token
                try:
                    await db.execute(
                        update(User).where(User.id == user.id).values(
                            gmail_token_encrypted=encrypted_token,
                            google_id=user_info.get('sub'),
                            auth_method='oauth'  # Migrate to OAuth-only
                        )
                    )
                    await db.commit()
                    logger.info(f"🔒 Updated encrypted token for user: {email}")
                except Exception as update_error:
                    logger.error(f"Failed to update user: {update_error}")
                    await db.rollback()
                    raise HTTPException(status_code=500, detail="Failed to update user account")
            
            return {
                "user_id": user.id,
                "email": email,
                "name": user_info.get('name'),
                "gmail_connected": True,
                "auth_method": "oauth"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"OAuth callback processing failed: {type(e).__name__}: {str(e)}")
            logger.error(f"Error details: {repr(e)}")
            # Add more detailed error information for debugging
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")
    
    def get_gmail_service(self, encrypted_token: str):
        """
        Create Gmail service from encrypted token
        
        Args:
            encrypted_token: Encrypted OAuth token from database
            
        Returns:
            Tuple of (gmail_service, updated_credentials)
        """
        try:
            # Decrypt token
            token_data = token_encryption.decrypt_token(encrypted_token)
            if not token_data:
                raise ValueError("Failed to decrypt token")
            
            # Create credentials from decrypted token
            credentials = self.dict_to_credentials(token_data)
            
            # Refresh if expired
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            
            # Create Gmail service
            service = build('gmail', 'v1', credentials=credentials)
            
            return service, credentials
            
        except Exception as e:
            logger.error("Failed to create Gmail service from encrypted token")
            raise ValueError("Invalid or expired token")
    
    def _get_user_info(self, credentials) -> Dict[str, Any]:
        """Get user information from Google"""
        try:
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            return user_info
        except HttpError as e:
            logger.error("Error getting user info from Google")
            raise HTTPException(status_code=400, detail="Failed to get user information")
    
    def _credentials_to_dict(self, credentials) -> Dict[str, Any]:
        """Convert credentials object to dictionary for encryption"""
        return {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
            'expiry': credentials.expiry.isoformat() if credentials.expiry else None
        }
    
    def dict_to_credentials(self, token_dict: Dict[str, Any]) -> Credentials:
        """Convert dictionary back to credentials object"""
        credentials = Credentials(
            token=token_dict.get('token'),
            refresh_token=token_dict.get('refresh_token'),
            token_uri=token_dict.get('token_uri'),
            client_id=token_dict.get('client_id'),
            client_secret=token_dict.get('client_secret'),
            scopes=token_dict.get('scopes')
        )
        
        if token_dict.get('expiry'):
            credentials.expiry = datetime.fromisoformat(token_dict['expiry'])
        
        return credentials

# Singleton instance
gmail_oauth_service = GmailOAuthService()
