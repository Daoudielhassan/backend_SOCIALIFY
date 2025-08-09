#!/usr/bin/env python3
"""
Test script to run the Gmail scheduler
"""

import sys
import os
import asyncio

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now import the scheduler
from services.scheduler import gmail_scheduler_service

async def main():
    print("🚀 Testing Gmail Scheduler...")
    try:
        result = await gmail_scheduler_service.run_once()
        print(f"✅ Scheduler completed successfully!")
        print(f"📊 Result: {result}")
    except Exception as e:
        print(f"❌ Scheduler failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
