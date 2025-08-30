from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from db.models import User
from db.schemas import UserCreate, Token
from api.dependencies import get_db, get_current_user
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal
import os
import httpx
import hashlib
from dotenv import load_dotenv
from utils.logger import logger
from config.settings import settings

# Gmail OAuth imports - Import lazily to avoid circular dependencies
#         from services.email_services.gmail_oauth import gmail_oauth_service

router = APIRouter()
load_dotenv()

# Add OPTIONS handler for CORS preflight
@router.options("/{path:path}")
async def options_handler():
    return {"message": "OK"}

@router.get("/config")
async def get_auth_config():
    """Get authentication configuration for frontend"""
    return {
        "google_client_id": GOOGLE_CLIENT_ID,
        "google_enabled": bool(GOOGLE_CLIENT_ID)
    }
load_dotenv()

# Configuration using centralized settings
SECRET_KEY: str = settings.JWT_SECRET
if not SECRET_KEY:
    raise ValueError("JWT_SECRET environment variable is required")

ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_HOURS = settings.JWT_EXPIRE_HOURS
GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
PASSWORD_SALT = settings.PASSWORD_SALT

# Cookie configuration (add these to settings.py if needed frequently)
COOKIE_SECURE = False  # Set to True in production with HTTPS
COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
COOKIE_DOMAIN = None  # None for same-origin

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def set_auth_cookie(response: Response, token: str, expires_delta: Optional[timedelta] = None):
    """Set httpOnly authentication cookie"""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
        max_age = int(expires_delta.total_seconds())
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=7)
        max_age = 7 * 24 * 3600

    logger.info(f"[set_auth_cookie] Setting cookie with token starting: {token[:10]}... | max_age={max_age} | expire={expire} | secure={COOKIE_SECURE} | samesite={COOKIE_SAMESITE} | domain={COOKIE_DOMAIN}")

    try:
        response.set_cookie(
            key="access_token",
            value=token,
            max_age=max_age,
            expires=expire,  # Use datetime object directly instead of string formatting
            httponly=True,  # Prevents XSS attacks
            secure=COOKIE_SECURE,  # HTTPS only in production
            samesite=COOKIE_SAMESITE,  # CSRF protection
            domain=COOKIE_DOMAIN,  # Domain restriction
            path="/"  # Available to entire application
        )
        logger.info(f"✅ Cookie set successfully for path /")
    except Exception as e:
        logger.error(f"❌ Failed to set cookie: {str(e)}")
        raise

def clear_auth_cookie(response: Response):
    """Clear httpOnly authentication cookie"""
    response.delete_cookie(
        key="access_token",
        path="/",
        domain=COOKIE_DOMAIN,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE
    )

def hash_password(password: str) -> str:
    """Hash password using the same method as Flask backend"""
    return hashlib.pbkdf2_hmac('sha256', password.encode(), PASSWORD_SALT.encode(), 100000).hex()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password using both bcrypt and legacy hash method"""
    # Try bcrypt first
    if pwd_context.verify(plain_password, hashed_password):
        return True
    # Try legacy hash method from Flask backend
    return hash_password(plain_password) == hashed_password

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    # Debug: Print token for testing (remove in production)
    print(f"🔑 DEBUG - Generated JWT Token: {token}")
    print(f"🔑 DEBUG - Token payload: {data}")
    print(f"🔑 DEBUG - Token expires: {expire.isoformat()}")
    logger.info(f"🔑 Generated JWT token for user: {data.get('email', 'unknown')}")
    
    return token

@router.post("/login")
async def login(user_in: UserCreate, response: Response, db: AsyncSession = Depends(get_db)):
    """Login with email and password - sets httpOnly cookie"""
    query = await db.execute(
        select(User).where(User.email == user_in.email)
    )
    user = query.scalar_one_or_none()
    
    # Verify user exists and has a password
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    password_hash = getattr(user, 'password_hash', None)
    if not password_hash or not verify_password(user_in.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Update last_login
    user_id = getattr(user, 'id')
    await db.execute(
        update(User).where(User.id == user_id).values(last_login=datetime.now(timezone.utc).replace(tzinfo=None))
    )
    await db.commit()
    
    user_email = getattr(user, 'email')
    print(f"🔐 DEBUG - Creating token for user ID: {user_id}, Email: {user_email}")
    access_token = create_access_token({"sub": str(user_id), "email": user_email})
    
    # Set httpOnly cookie
    set_auth_cookie(response, access_token)
    
    print(f"🔐 DEBUG - Login successful for: {user_email}")
    return {
        "message": "Login successful",
        "user": {
            "id": user_id,
            "email": user_email,
            "name": getattr(user, 'full_name', '')
        },
        "auth_method": "cookie"
    }

@router.get("/google")
async def google_oauth_redirect(user_id: Optional[str] = None):
    """
    GET endpoint for /auth/google - redirects to OAuth initialization
    This handles cases where someone tries to access /auth/google with GET method
    """
    return await gmail_oauth_init(user_id)

@router.post("/google")
async def google_login(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Google OAuth login - sets httpOnly cookie"""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    
    credential = data.get("credential")
    if not credential:
        raise HTTPException(status_code=400, detail="Missing Google credential")
    
    # Verify Google token
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        resp = await client.get(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google token")
        id_info = resp.json()
    
    if id_info.get("aud") != GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Invalid Google client ID")
    
    email = id_info["email"]
    query = await db.execute(select(User).where(User.email == email))
    user = query.scalar_one_or_none()
    
    if not user:
        user = User(
            email=email,
            full_name=id_info.get("name"),
            google_id=id_info.get("sub"),
            auth_method="google",
            is_active=True,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            last_login=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Update last_login for existing user
        user_id = getattr(user, 'id')
        await db.execute(
            update(User).where(User.id == user_id).values(last_login=datetime.now(timezone.utc).replace(tzinfo=None))
        )
        await db.commit()
    
    user_id = getattr(user, 'id')
    user_email = getattr(user, 'email')
    print(f"🔐 DEBUG - Creating Google OAuth token for user ID: {user_id}, Email: {user_email}")
    access_token = create_access_token({"sub": str(user_id), "email": user_email})
    
    # Set httpOnly cookie
    set_auth_cookie(response, access_token)
    
    print(f"🔐 DEBUG - Google OAuth login successful for: {user_email}")
    return {
        "message": "Google login successful",
        "user": {
            "id": user_id,
            "email": user_email,
            "name": getattr(user, 'full_name', '')
        },
        "auth_method": "cookie"
    } 

@router.post("/register")
async def register(
    response: Response,
    name: str = Body(...),
    email: str = Body(...),
    password: str = Body(...),
    db: AsyncSession = Depends(get_db)
):
    # Check if user already exists
    query = await db.execute(select(User).where(User.email == email))
    user = query.scalar_one_or_none()
    if user:
        raise HTTPException(status_code=400, detail="User already exists")
    # Hash password
    password_hash = get_password_hash(password)
    # Create user
    new_user = User(
        email=email,
        full_name=name,
        password_hash=password_hash,
        auth_method="email",
        is_active=True,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        last_login=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    # Return JWT token
    user_id = getattr(new_user, 'id')
    user_email = getattr(new_user, 'email')
    access_token = create_access_token({"sub": str(user_id), "email": user_email})
    
    # Set httpOnly cookie
    set_auth_cookie(response, access_token)
    
    return {
        "message": "Registration successful",
        "user": {
            "id": user_id,
            "email": user_email,
            "name": name
        },
        "auth_method": "cookie"
    }

@router.post("/logout")
async def logout(response: Response):
    """
    Logout user by clearing the httpOnly cookie
    """
    clear_auth_cookie(response)
    return {"message": "Logout successful"}

# Gmail OAuth Routes
@router.get("/gmail/oauth")
async def gmail_oauth_init_redirect(user_id: Optional[str] = None):
    """
    Alternative endpoint for Gmail OAuth initialization (for compatibility)
    Redirects to the main Google OAuth init
    """
    return await gmail_oauth_init(user_id)

@router.get("/google/init")
async def gmail_oauth_init(user_id: Optional[str] = None):
    """
    Initialize Gmail OAuth flow
    
    Args:
        user_id: Optional user ID to associate with the OAuth flow
        
    Returns:
        Authorization URL for Gmail access
    """
    try:
        # Import OAuth service lazily to handle any import issues
        from services.emailServices.gmail_oauth import gmail_oauth_service
        auth_url = gmail_oauth_service.get_authorization_url(state=user_id)
        return {"authorization_url": auth_url}
    except ImportError as import_error:
        logger.error(f"OAuth service import failed: {import_error}")
        raise HTTPException(status_code=500, detail="OAuth service unavailable")
    except Exception as e:
        logger.error(f"Failed to initialize OAuth: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize OAuth: {str(e)}")

@router.get("/google/callback")
async def gmail_oauth_callback(
    code: str,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Gmail OAuth callback and redirect to frontend dashboard
    
    Args:
        code: Authorization code from Google
        state: State parameter (user_id)
        error: Error parameter from Google
        db: Database session
        
    Returns:
        Redirect to frontend dashboard with auth token
    """
    if error:
        logger.error(f"OAuth error received: {error}")
        # Redirect to frontend with error
        frontend_url = settings.FRONTEND_URL
        return RedirectResponse(url=f"{frontend_url}/login?error={error}")
    
    if not code:
        logger.error("Missing authorization code in callback")
        # Redirect to frontend with error
        frontend_url = settings.FRONTEND_URL
        return RedirectResponse(url=f"{frontend_url}/login?error=missing_code")
    
    logger.info(f"🔐 Processing OAuth callback with code: {code[:20]}...")
    
    try:
        # Import OAuth service lazily to handle any import issues
        from services.emailServices.gmail_oauth import gmail_oauth_service
        
        result = await gmail_oauth_service.handle_callback(code, state, db)
        logger.info("✓ OAuth callback completed successfully")
        
        # Create JWT token for the user
        access_token = create_access_token({"sub": str(result["user_id"]), "email": result["email"]})
        
        # Redirect to frontend dashboard WITHOUT user data in URL
        frontend_url = settings.FRONTEND_URL
        dashboard_url = f"{frontend_url}/dashboard"
        
        # Create redirect response and set httpOnly cookie
        response = RedirectResponse(url=dashboard_url)
        set_auth_cookie(response, access_token)
        
        logger.info(f"🚀 Redirecting to dashboard: {dashboard_url}")
        logger.info(f"🔐 JWT token set as httpOnly cookie for user: {result['email']}")
        return response
        
    except ImportError as import_error:
        logger.error(f"OAuth service import failed: {import_error}")
        frontend_url = settings.FRONTEND_URL
        return RedirectResponse(url=f"{frontend_url}/login?error=service_unavailable")
    except Exception as e:
        logger.error(f"OAuth callback processing failed: {type(e).__name__}: {str(e)}")
        frontend_url = settings.FRONTEND_URL
        error_msg = "callback_failed"
        return RedirectResponse(url=f"{frontend_url}/login?error={error_msg}")

@router.post("/gmail/disconnect")
async def disconnect_gmail(
    current_user_id: int = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Disconnect Gmail for a user
    
    Args:
        current_user_id: ID of the user to disconnect
        db: Database session
        
    Returns:
        Success message
    """
    try:
        await db.execute(
            update(User).where(User.id == current_user_id).values(gmail_token_encrypted=None)
        )
        await db.commit()
        
        return {"message": "Gmail disconnected successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to disconnect Gmail: {str(e)}")

@router.get("/gmail/status/{user_id}")
async def gmail_connection_status(user_id: int, db: AsyncSession = Depends(get_db)):
    """
    Check Gmail connection status for a user
    
    Args:
        user_id: User ID to check
        db: Database session
        
    Returns:
        Gmail connection status
    """
    try:
        query = await db.execute(select(User).where(User.id == user_id))
        user = query.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        has_gmail_token = user.gmail_token_encrypted is not None
        return {
            "user_id": user_id,
            "gmail_connected": has_gmail_token,
            "email": user.email
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check Gmail status: {str(e)}")

@router.get("/me")
async def get_current_user_info(
    current_user = Depends(get_current_user)
):
    """
    Get the current authenticated user's information
    
    Returns:
        Current user data (alias for /profile endpoint)
    """
    try:
        return {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "auth_method": current_user.auth_method,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
            "is_active": current_user.is_active,
            "gmail_connected": current_user.gmail_token_encrypted is not None,
            "user_id": current_user.id  # For backward compatibility
        }
    except Exception as e:
        logger.error(f"Failed to get current user info: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user information: {str(e)}")

@router.get("/profile")
async def get_user_profile(
    current_user = Depends(get_current_user)
):
    """
    Get the current user's profile information
    
    Returns:
        User profile data
    """
    try:
        return {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "auth_method": current_user.auth_method,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
            "is_active": current_user.is_active,
            "gmail_connected": current_user.gmail_token_encrypted is not None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")
