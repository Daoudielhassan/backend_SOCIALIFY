from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from typing import AsyncGenerator, Optional
from db.db import SessionLocal
from db.schemas import TokenData
from db.models import User
import os
from dotenv import load_dotenv

from config.settings import settings
load_dotenv()

SECRET_KEY = settings.JWT_SECRET
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Keep OAuth2PasswordBearer for backwards compatibility, but make it optional
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def get_current_user(
    request: Request,
    auth_token: Optional[str] = Depends(oauth2_scheme),
    access_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current user from either httpOnly cookie or Authorization header
    Priority: 1. HttpOnly cookie, 2. Authorization header (backwards compatibility)
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Extract token - priority to httpOnly cookie
    token = None
    if access_token:
        # Use httpOnly cookie token (preferred method)
        token = access_token
    elif auth_token:
        # Fallback to Authorization header for backwards compatibility
        token = auth_token
    else:
        # No token found in either location
        raise credentials_exception
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")  # JWT standard uses string for "sub"
        if user_id_str is None:
            raise credentials_exception
        token_data = TokenData(user_id=int(user_id_str))  # Convert to int for database lookup
    except (JWTError, ValueError):  # Handle both JWT errors and conversion errors
        raise credentials_exception
    
    # Use proper async SQLAlchemy query
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    return user 