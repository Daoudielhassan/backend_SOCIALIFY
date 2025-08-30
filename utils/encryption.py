"""
Encryption utilities for secure token storage
Provides AES encryption for sensitive data like OAuth tokens
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv
import json
from typing import Dict, Any, Optional
from utils.logger import logger
from config.settings import settings

load_dotenv()

class TokenEncryption:
    """Handles encryption and decryption of OAuth tokens"""
    
    def __init__(self):
        # Use encryption key from environment or generate one
        self.encryption_key = self._get_or_create_key()
        self.fernet = Fernet(self.encryption_key)
    
    def _get_or_create_key(self) -> bytes:
        """Get encryption key from environment or derive from secret"""
        # Use JWT secret as base for encryption key derivation
        jwt_secret = settings.JWT_SECRET
        if not jwt_secret:
            raise ValueError("JWT_SECRET must be set for token encryption")
        
        # Derive a consistent encryption key from JWT secret
        salt = b'socialify_token_salt_v1'  # Fixed salt for consistency
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(jwt_secret.encode()))
        return key
    
    def encrypt_token(self, token_data: Dict[str, Any]) -> str:
        """
        Encrypt OAuth token data
        
        Args:
            token_data: Dictionary containing token information
            
        Returns:
            Encrypted token as base64 string
        """
        try:
            # Convert to JSON string
            json_str = json.dumps(token_data, sort_keys=True)
            
            # Encrypt the JSON string
            encrypted = self.fernet.encrypt(json_str.encode())
            
            # Return as base64 string for database storage
            return base64.urlsafe_b64encode(encrypted).decode()
            
        except Exception as e:
            logger.error("Failed to encrypt token data")
            raise ValueError("Token encryption failed")
    
    def decrypt_token(self, encrypted_token: str) -> Optional[Dict[str, Any]]:
        """
        Decrypt OAuth token data
        
        Args:
            encrypted_token: Base64 encoded encrypted token
            
        Returns:
            Decrypted token data or None if decryption fails
        """
        try:
            # Decode from base64
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_token.encode())
            
            # Decrypt
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            
            # Parse JSON
            token_data = json.loads(decrypted_bytes.decode())
            
            return token_data
            
        except Exception as e:
            logger.error("Failed to decrypt token data")
            return None
    
    def is_encrypted_token(self, token_data: Any) -> bool:
        """Check if token data is encrypted (string) or plain (dict)"""
        return isinstance(token_data, str)

# Global instance
token_encryption = TokenEncryption()
