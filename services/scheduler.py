"""
Scheduler Service
Periodically fetches Gmail messages for all users with valid tokens
"""

import asyncio
import os
from datetime import datetime
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from db.models import User
from services.emailServices.email_service import email_service
from utils.logger import logger
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DB_USER = os.getenv('DB_USER', 'myuser')
    DB_PASS = os.getenv('DB_PASSWORD', '')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'socialtify')
    DATABASE_URL = f'postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

class GmailSchedulerService:
    """Service for scheduling periodic Gmail fetching"""
    
    def __init__(self):
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL not configured")
        
        self.engine = create_async_engine(DATABASE_URL, echo=False)
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.is_running = False
    
    async def poll_gmail_for_all_users(self) -> dict:
        """
        Poll Gmail for all users with valid tokens
        
        Returns:
            Dictionary with polling results
        """
        logger.info("🔄 Starting Gmail polling for all users...")
        
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
                    user_email = user.email  # Get email early to avoid lazy loading in error handlers
                    try:
                        logger.info(f"Processing Gmail for user: {user_email}")
                        result = await email_service.fetch_messages_for_user(user, db)
                        
                        if 'error' in result:
                            total_errors.append(f"User {user_email}: {result['error']}")
                        else:
                            total_processed += result.get('processed', 0)
                            logger.info(f"✅ Processed {result.get('processed', 0)} messages for {user_email}")
                        
                    except Exception as e:
                        error_msg = f"Error processing user {user_email}: {str(e)}"
                        logger.error(error_msg)
                        total_errors.append(error_msg)
                
                result_summary = {
                    "total_users": len(users),
                    "processed_messages": total_processed,
                    "errors": total_errors,
                    "timestamp": datetime.now().astimezone().isoformat()
                }
                
                logger.info(f"📊 Gmail polling completed: {total_processed} messages processed, {len(total_errors)} errors")
                return result_summary
                
            except Exception as e:
                logger.error(f"❌ Critical error in Gmail polling: {str(e)}")
                return {"error": str(e), "timestamp": datetime.now().astimezone().isoformat()}
    
    async def scheduler_loop(self, interval_minutes: int = 10):
        """
        Main scheduler loop
        
        Args:
            interval_minutes: Interval between polling cycles
        """
        logger.info(f"🚀 Starting Gmail scheduler with {interval_minutes} minute intervals")
        self.is_running = True
        
        while self.is_running:
            try:
                await self.poll_gmail_for_all_users()
                logger.info(f"⏰ Next Gmail poll in {interval_minutes} minutes")
                await asyncio.sleep(interval_minutes * 60)
                
            except KeyboardInterrupt:
                logger.info("🛑 Scheduler stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Scheduler error: {str(e)}")
                # Wait a bit before retrying to avoid tight error loops
                await asyncio.sleep(60)
        
        self.is_running = False
        logger.info("📴 Gmail scheduler stopped")
    
    def stop(self):
        """Stop the scheduler"""
        self.is_running = False
    
    async def run_once(self):
        """Run polling once (for testing or manual triggers)"""
        return await self.poll_gmail_for_all_users()

# Singleton instance
gmail_scheduler_service = GmailSchedulerService()

# CLI entry point
async def main():
    """Main entry point for running scheduler standalone"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Gmail Scheduler Service')
    parser.add_argument('--interval', type=int, default=10, help='Polling interval in minutes')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    
    args = parser.parse_args()
    
    if args.once:
        logger.info("Running Gmail polling once...")
        result = await gmail_scheduler_service.run_once()
        logger.info(f"Result: {result}")
    else:
        await gmail_scheduler_service.scheduler_loop(args.interval)

if __name__ == "__main__":
    asyncio.run(main())
