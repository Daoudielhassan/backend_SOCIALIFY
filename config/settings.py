"""
Configuration Management - Centralized Settings
Consolidates all environment variable handling and application configuration
"""

import os
from typing import Optional, Dict, Any
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables once at module level
load_dotenv()

class Settings:
    """
    Centralized configuration management for Socialify Backend
    
    Provides type-safe access to environment variables with defaults
    and validation. Eliminates scattered getenv() calls across the codebase.
    """
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://localhost/socialify")
    
    # JWT Configuration
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
    
    # Google OAuth Configuration  
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5173/auth/callback")
    
    # Meta OAuth Configuration for WhatsApp Business
    META_APP_ID: str = os.getenv("META_APP_ID", "")
    META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
    META_REDIRECT_URI: str = os.getenv("META_REDIRECT_URI", "https://cd81af9c9e2b.ngrok-free.app/api/whatsapp/v2/oauth/callback")
    
    # Frontend Configuration
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # External Services
    AI_ENGINE_URL: str = os.getenv("IA_ENGINE_URL", "")
    WHATSAPP_API_URL: str = os.getenv("WHATSAPP_API_URL", "")
    WHATSAPP_ACCESS_TOKEN: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
    
    # Application Configuration
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000")
    ADMIN_KEY: str = os.getenv("ADMIN_KEY", "admin123")
    
    # Privacy & Security
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    DATA_RETENTION_DAYS: int = int(os.getenv("DATA_RETENTION_DAYS", "90"))
    PASSWORD_SALT: str = os.getenv("PASSWORD_SALT", "default_salt")
    
    # Feature Flags
    ENABLE_GMAIL: bool = os.getenv("ENABLE_GMAIL", "true").lower() == "true"
    ENABLE_WHATSAPP: bool = os.getenv("ENABLE_WHATSAPP", "false").lower() == "true"
    ENABLE_AI_PREDICTIONS: bool = os.getenv("ENABLE_AI_PREDICTIONS", "true").lower() == "true"
    
    # Development & Debugging
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate_required_settings(cls) -> None:
        """
        Validate that all required configuration values are present
        Raises ValueError if any required setting is missing
        """
        required_settings = {
            "JWT_SECRET": cls.JWT_SECRET,
            "DATABASE_URL": cls.DATABASE_URL
        }
        
        missing_settings = [
            name for name, value in required_settings.items()
            if not value or value.strip() == ""
        ]
        
        if missing_settings:
            raise ValueError(
                f"❌ Missing required environment variables: {', '.join(missing_settings)}\n"
                f"Please check your .env file or environment configuration."
            )
    
    @classmethod
    def get_allowed_origins_list(cls) -> list[str]:
        """Get CORS allowed origins as a list"""
        return [origin.strip() for origin in cls.ALLOWED_ORIGINS.split(",") if origin.strip()]
    
    @classmethod
    def get_meta_oauth_config(cls) -> Dict[str, str]:
        """Get Meta OAuth configuration as a dictionary"""
        return {
            "app_id": cls.META_APP_ID,
            "app_secret": cls.META_APP_SECRET,
            "redirect_uri": cls.META_REDIRECT_URI
        }
    
    @classmethod
    def get_google_oauth_config(cls) -> Dict[str, str]:
        """Get Google OAuth configuration as a dictionary"""
        return {
            "client_id": cls.GOOGLE_CLIENT_ID,
            "client_secret": cls.GOOGLE_CLIENT_SECRET,
            "redirect_uri": cls.GOOGLE_REDIRECT_URI
        }
    
    @classmethod
    def get_feature_flags(cls) -> Dict[str, bool]:
        """Get all feature flags as a dictionary"""
        return {
            "gmail": cls.ENABLE_GMAIL,
            "whatsapp": cls.ENABLE_WHATSAPP,
            "ai_predictions": cls.ENABLE_AI_PREDICTIONS
        }
    
    @classmethod
    def get_database_config(cls) -> Dict[str, Any]:
        """Get database configuration"""
        return {
            "url": cls.DATABASE_URL,
            "echo": cls.DEBUG,
            "pool_size": 10,
            "max_overflow": 20
        }
    
    @classmethod 
    def is_development(cls) -> bool:
        """Check if running in development mode"""
        return cls.DEBUG or "localhost" in cls.DATABASE_URL
    
    @classmethod
    def get_security_config(cls) -> Dict[str, Any]:
        """Get security-related configuration"""
        return {
            "jwt_secret": cls.JWT_SECRET,
            "jwt_algorithm": cls.JWT_ALGORITHM,
            "jwt_expire_hours": cls.JWT_EXPIRE_HOURS,
            "encryption_key": cls.ENCRYPTION_KEY,
            "data_retention_days": cls.DATA_RETENTION_DAYS
        }

@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance
    
    Uses lru_cache to ensure settings are loaded only once
    and reused across the application.
    """
    settings = Settings()
    settings.validate_required_settings()
    return settings

REDIS_URL = "redis://localhost:6379/0"

# Convenience instance for direct import
settings = get_settings()

# Legacy compatibility - these can be imported directly
JWT_SECRET = settings.JWT_SECRET
DATABASE_URL = settings.DATABASE_URL
GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET

# Export commonly used configurations
__all__ = [
    "Settings",
    "get_settings", 
    "settings",
    "JWT_SECRET",
    "DATABASE_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET"
]
