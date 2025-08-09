import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession
from db.db import SessionLocal
from db.models import User
from utils.encryption import token_encryption
from sqlalchemy import select

async def check_token_encryption():
    print("🔍 Token Encryption Diagnostic")
    print("="*50)
    
    # Get database session
    async with SessionLocal() as db:
        # Get user 13 (your user)
        result = await db.execute(select(User).where(User.id == 13))
        user = result.scalar_one_or_none()
        
        if not user:
            print("❌ User 13 not found")
            return
            
        print(f"👤 User: {user.email}")
        print(f"🔐 Has encrypted token: {bool(user.gmail_token_encrypted)}")
        
        if user.gmail_token_encrypted:
            encrypted_token = user.gmail_token_encrypted
            print(f"📏 Token length: {len(encrypted_token)}")
            print(f"🔤 Token type: {type(encrypted_token)}")
            print(f"🔍 Token preview (first 50 chars): {encrypted_token[:50]}...")
            
            # Check if it looks like encrypted data
            is_base64_like = all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=-_' for c in encrypted_token)
            print(f"📊 Looks like base64: {is_base64_like}")
            
            # Try to decrypt
            print("\n🔓 Attempting decryption...")
            try:
                decrypted_data = token_encryption.decrypt_token(encrypted_token)
                if decrypted_data:
                    print("✅ Decryption successful!")
                    print(f"📋 Decrypted type: {type(decrypted_data)}")
                    if isinstance(decrypted_data, dict):
                        print(f"🔑 Keys: {list(decrypted_data.keys())}")
                    else:
                        print(f"📄 Content preview: {str(decrypted_data)[:100]}...")
                else:
                    print("❌ Decryption returned None")
            except Exception as e:
                print(f"❌ Decryption failed: {str(e)}")
                
            # Check encryption utility
            print("\n🛠️ Encryption utility check...")
            print(f"🔧 Encryption key exists: {token_encryption.fernet is not None}")
            
            # Try to identify the token format
            print("\n📋 Token format analysis...")
            try:
                import base64
                import json
                
                # Try direct base64 decode
                decoded_bytes = base64.urlsafe_b64decode(encrypted_token.encode())
                print(f"📏 Decoded bytes length: {len(decoded_bytes)}")
                
                # Check if it's JSON
                try:
                    json_data = json.loads(decoded_bytes.decode())
                    print("📄 Token appears to be plain JSON (not encrypted)")
                    print(f"🔑 JSON keys: {list(json_data.keys()) if isinstance(json_data, dict) else 'Not a dict'}")
                except:
                    print("🔒 Token appears to be properly encrypted")
                    
            except Exception as e:
                print(f"⚠️ Token format analysis failed: {str(e)}")
        else:
            print("❌ No encrypted token found")

if __name__ == "__main__":
    asyncio.run(check_token_encryption())
