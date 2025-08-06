from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from typing import AsyncGenerator
from db.db import SessionLocal
from db.schemas import TokenData
from db.models import User
import os
from dotenv import load_dotenv

from config.settings import settings
load_dotenv()

SECRET_KEY = settings.JWT_SECRET
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_db() -> AsyncGenerator:
    async with SessionLocal() as session:
        yield session

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")  # JWT standard uses string for "sub"
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=int(user_id))  # Convert to int for database lookup
    except (JWTError, ValueError):  # Handle both JWT errors and conversion errors
        raise credentials_exception
    
    # Use proper async SQLAlchemy query
    result = await db.execute(select(User).where(User.id == int(token_data.user_id)))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    return user 