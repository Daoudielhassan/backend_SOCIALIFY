#!/usr/bin/env python3
"""
Simple Gmail Scheduler
"""

import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import models and services directly
from db.models import User
from utils.logger import logger

# Database configuration  
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DB_USER = os.getenv('DB_USER', 'myuser')
    DB_PASS = os.getenv('DB_PASSWORD', '')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'socialtify')
    DATABASE_URL = f'postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

# Import the gmail oauth service directly
from services.email_services.gmail_oauth import gmail_oauth_service

async def simple_gmail_fetch(user, db):
    """Simple Gmail fetch for a single user"""
    try:
        if not user.gmail_token_encrypted:
            return {"error": "No Gmail token", "processed": 0}
        
        # Get Gmail service directly
        service, credentials = gmail_oauth_service.get_gmail_service(user.gmail_token_encrypted)
        
        # Fetch a small number of messages
        results = service.users().messages().list(userId='me', maxResults=5).execute()
        messages = results.get('messages', [])
        
        logger.info(f"Found {len(messages)} messages for user {user.email}")
        
        return {"processed": len(messages), "error": None}
        
    except Exception as e:
        logger.error(f"Error fetching for user {user.email}: {str(e)}")
        return {"error": str(e), "processed": 0}

async def run_simple_scheduler():
    """Simple scheduler implementation"""
    logger.info("🔄 Starting simple Gmail scheduler...")
    
    # Create database session
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        try:
            # Get all users with Gmail tokens
            query = await db.execute(
                select(User).where(User.gmail_token_encrypted.isnot(None))
            )
            users = query.scalars().all()
            
            if not users:
                logger.info("No users with Gmail tokens found")
                return {"total_users": 0, "processed": 0, "errors": []}
            
            logger.info(f"Found {len(users)} users with Gmail tokens")
            
            total_processed = 0
            total_errors = []
            
            for user in users:
                logger.info(f"Processing user: {user.email}")
                result = await simple_gmail_fetch(user, db)
                
                if result.get("error"):
                    total_errors.append(f"{user.email}: {result['error']}")
                else:
                    total_processed += result.get("processed", 0)
            
            summary = {
                "total_users": len(users),
                "processed_messages": total_processed,
                "errors": total_errors,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"📊 Simple scheduler completed: {total_processed} messages, {len(total_errors)} errors")
            return summary
            
        except Exception as e:
            logger.error(f"❌ Scheduler error: {str(e)}")
            return {"error": str(e)}

async def main():
    """Main entry point"""
    print("🚀 Starting Simple Gmail Scheduler...")
    
    try:
        result = await run_simple_scheduler()
        print("✅ Scheduler completed!")
        print(f"📊 Result: {result}")
    except Exception as e:
        print(f"❌ Failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
