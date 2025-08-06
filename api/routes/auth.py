from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from db.models import User
from db.schemas import UserCreate, Token
from api.dependencies import get_db, get_current_user
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from typing import Optional
import os
import httpx
import hashlib
from dotenv import load_dotenv
from utils.logger import logger

# Gmail OAuth imports - Import lazily to avoid circular dependencies
# from services.email.gmail_oauth import gmail_oauth_service

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

_secret_key = os.getenv("JWT_SECRET")
if not _secret_key:
    raise ValueError("JWT_SECRET environment variable is required")
SECRET_KEY: str = _secret_key
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# Augmenter la durée d'expiration par défaut à 7 jours (168 heures)
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", 168))  # 7 jours par défaut
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
PASSWORD_SALT = os.getenv("PASSWORD_SALT", "default_salt")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
    
    # Si aucune durée n'est spécifiée, utiliser la configuration par défaut
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),  # Issued at (moment de création)
        "type": "access_token"     # Type de token
    })
    
    logger.info(f"🔐 Creating JWT token that expires at: {expire.isoformat()} (in {ACCESS_TOKEN_EXPIRE_HOURS} hours)")
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_long_lived_token(data: dict, days: int = 30):
    """Create a long-lived token for extended sessions"""
    expires_delta = timedelta(days=days)
    return create_access_token(data, expires_delta)

@router.post("/login", response_model=Token)
async def login(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
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
        update(User).where(User.id == user_id).values(last_login=datetime.utcnow())
    )
    await db.commit()
    
    user_email = getattr(user, 'email')
    access_token = create_access_token({"sub": str(user_id), "email": user_email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/google")
async def google_oauth_redirect(user_id: Optional[str] = None):
    """
    GET endpoint for /auth/google - redirects to OAuth initialization
    This handles cases where someone tries to access /auth/google with GET method
    """
    return await gmail_oauth_init(user_id)

@router.post("/google", response_model=Token)
async def google_login(request: Request, db: AsyncSession = Depends(get_db)):
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
            created_at=datetime.utcnow(),
            last_login=datetime.utcnow(),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Update last_login for existing user
        user_id = getattr(user, 'id')
        await db.execute(
            update(User).where(User.id == user_id).values(last_login=datetime.utcnow())
        )
        await db.commit()
    
    user_id = getattr(user, 'id')
    user_email = getattr(user, 'email')
    access_token = create_access_token({"sub": str(user_id), "email": user_email})
    return {"access_token": access_token, "token_type": "bearer"} 

@router.post("/register", response_model=Token)
async def register(
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
        created_at=datetime.utcnow(),
        last_login=datetime.utcnow(),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    # Return JWT token
    user_id = getattr(new_user, 'id')
    user_email = getattr(new_user, 'email')
    access_token = create_access_token({"sub": str(user_id), "email": user_email})
    return {"access_token": access_token, "token_type": "bearer"}

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
        from services.email.gmail_oauth import gmail_oauth_service
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
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        return RedirectResponse(url=f"{frontend_url}/login?error={error}")
    
    if not code:
        logger.error("Missing authorization code in callback")
        # Redirect to frontend with error
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        return RedirectResponse(url=f"{frontend_url}/login?error=missing_code")
    
    logger.info(f"🔐 Processing OAuth callback with code: {code[:20]}...")
    
    try:
        # Import OAuth service lazily to handle any import issues
        from services.email.gmail_oauth import gmail_oauth_service
        
        result = await gmail_oauth_service.handle_callback(code, state, db)
        logger.info("✓ OAuth callback completed successfully")
        
        # Create JWT token for the user
        access_token = create_access_token({"sub": str(result["user_id"]), "email": result["email"]})
        
        # Redirect to frontend dashboard with token
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        dashboard_url = f"{frontend_url}/dashboard?token={access_token}&user_id={result['user_id']}&email={result['email']}"
        
        logger.info(f"🚀 Redirecting to dashboard: {frontend_url}/dashboard")
        return RedirectResponse(url=dashboard_url)
        
    except ImportError as import_error:
        logger.error(f"OAuth service import failed: {import_error}")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        return RedirectResponse(url=f"{frontend_url}/login?error=service_unavailable")
    except Exception as e:
        logger.error(f"OAuth callback processing failed: {type(e).__name__}: {str(e)}")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
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

@router.post("/refresh-token", response_model=Token)
async def refresh_access_token(
    current_user = Depends(get_current_user)
):
    """
    Renouveler le token d'accès pour l'utilisateur actuel
    
    Returns:
        Nouveau token d'accès avec une durée d'expiration étendue
    """
    try:
        # Créer un nouveau token avec la durée complète
        new_access_token = create_access_token({
            "sub": str(current_user.id), 
            "email": current_user.email
        })
        
        logger.info(f"🔄 Token refreshed for user {current_user.id}")
        
        return {
            "access_token": new_access_token, 
            "token_type": "bearer"
        }
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh token: {str(e)}")

@router.get("/token-info")
async def get_token_info(
    current_user = Depends(get_current_user)
):
    """
    Obtenir des informations sur le token actuel
    
    Returns:
        Informations sur le token (expiration, durée restante, etc.)
    """
    try:
        # Cette fonction sera appelée seulement si le token est valide
        # car elle dépend de get_current_user
        
        return {
            "user_id": current_user.id,
            "email": current_user.email,
            "token_valid": True,
            "message": "Token is valid and user is authenticated",
            "expires_in_hours": ACCESS_TOKEN_EXPIRE_HOURS,
            "auth_method": current_user.auth_method
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get token info: {str(e)}")
