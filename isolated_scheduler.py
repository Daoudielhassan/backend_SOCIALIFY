#!/usr/bin/env python3
"""
Isolated Gmail Scheduler - Standalone Version
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import models and services
from db.models import User
from utils.logger import logger

# Import email service directly to avoid circular imports
from services.emailServices.email_service import HighPerformanceEmailService

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DB_USER = os.getenv('DB_USER', 'myuser')
    DB_PASS = os.getenv('DB_PASSWORD', '')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'socialtify')
    DATABASE_URL = f'postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

class IsolatedGmailScheduler:
    """Isolated Gmail Scheduler Service"""
    
    def __init__(self):
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL not configured")
        
        self.engine = create_async_engine(DATABASE_URL, echo=False)
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )
        # Create email service instance
        self.email_service = HighPerformanceEmailService()
    
    async def run_once(self) -> dict:
        """Run Gmail polling once for all users"""
        logger.info("🔄 Starting isolated Gmail polling...")
        
        async with self.AsyncSessionLocal() as db:
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
                    try:
                        logger.info(f"Processing Gmail for user: {user.email}")
                        result = await self.email_service.fetch_messages_for_user(
                            user=user, 
                            db=db,
                            provider="gmail",
                            max_results=10,
                            privacy_mode=True
                        )
                        
                        if 'error' in result:
                            total_errors.append(f"User {user.email}: {result['error']}")
                        else:
                            processed = result.get('processed', 0)
                            total_processed += processed
                            logger.info(f"✅ Processed {processed} messages for {user.email}")
                        
                    except Exception as e:
                        error_msg = f"Error processing user {user.email}: {str(e)}"
                        logger.error(error_msg)
                        total_errors.append(error_msg)
                
                result_summary = {
                    "total_users": len(users),
                    "processed_messages": total_processed,
                    "errors": total_errors,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                logger.info(f"📊 Gmail polling completed: {total_processed} messages processed, {len(total_errors)} errors")
                return result_summary
                
            except Exception as e:
                logger.error(f"❌ Critical error in Gmail polling: {str(e)}")
                return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

async def main():
    """Main entry point"""
    print("🚀 Starting Isolated Gmail Scheduler...")
    
    try:
        scheduler = IsolatedGmailScheduler()
        result = await scheduler.run_once()
        print(f"✅ Scheduler completed successfully!")
        print(f"📊 Result: {result}")
    except Exception as e:
        print(f"❌ Scheduler failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
