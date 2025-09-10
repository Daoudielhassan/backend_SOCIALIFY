"""
Unified Multi-Tenant WhatsApp SaaS Database Models
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=True)
    # OAuth Authentication
    google_id = Column(String(128), nullable=True)
    gmail_token_encrypted = Column(Text, nullable=True)
    # Meta OAuth for WhatsApp Business
    meta_user_id = Column(String(128), nullable=True, index=True)
    meta_access_token_encrypted = Column(Text, nullable=True)
    meta_token_expires_at = Column(DateTime, nullable=True)
    meta_permissions = Column(JSON, nullable=True)
    # Account status
    is_active = Column(Boolean, default=True)
    subscription_tier = Column(String(50), default='free')
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow, nullable=True)
    auth_method = Column(String(50), default='oauth', nullable=False)
    # Relationships
    whatsapp_accounts = relationship("WhatsAppBusinessAccount", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("MessageMetadata", back_populates="user")
    # Optimized indexes
    __table_args__ = (
        Index('idx_tenant_email_auth_method', 'email', 'auth_method'),
        Index('idx_meta_user_id', 'meta_user_id'),
        Index('idx_tenant_active_users', 'is_active', 'subscription_tier'),
        Index('idx_tenant_created_at', 'created_at'),
    )
    def __repr__(self):
        return f'<User {self.email} ({self.subscription_tier})>'

class WhatsAppBusinessAccount(Base):
    __tablename__ = "whatsapp_business_accounts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    waba_id = Column(String(128), nullable=False, unique=True, index=True)
    business_name = Column(String(256), nullable=True)
    meta_app_id = Column(String(128), nullable=True)
    meta_user_id = Column(String(128), nullable=True)
    access_token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    last_sync = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    webhook_configured = Column(Boolean, default=False)
    # Relationships
    user = relationship("User", back_populates="whatsapp_accounts")
    phone_numbers = relationship("WhatsAppPhoneNumber", back_populates="business_account", cascade="all, delete-orphan")
    messages = relationship("WhatsAppMessageV2", back_populates="business_account", cascade="all, delete-orphan")
    # Indexes
    __table_args__ = (
        Index('idx_user_waba', 'user_id', 'waba_id'),
        Index('idx_active_accounts', 'is_active'),
    )
    def __repr__(self):
        return f'<WABA {self.waba_id}>'

class WhatsAppPhoneNumber(Base):
    __tablename__ = "whatsapp_phone_numbers"
    id = Column(Integer, primary_key=True, index=True)
    waba_id = Column(Integer, ForeignKey("whatsapp_business_accounts.id"), nullable=False)
    phone_number_id = Column(String(128), nullable=False, unique=True, index=True)
    phone_number = Column(String(32), nullable=False, index=True)
    display_name = Column(String(128), nullable=True)
    status = Column(String(50), default='pending')
    is_verified = Column(Boolean, default=False)
    # Relationships
    business_account = relationship("WhatsAppBusinessAccount", back_populates="phone_numbers")
    # Indexes
    __table_args__ = (
        Index('idx_phone_number_id', 'phone_number_id'),
        Index('idx_phone_number', 'phone_number'),
    )
    def __repr__(self):
        return f'<PhoneNumber {self.phone_number}>'

class WhatsAppMessageV2(Base):
    __tablename__ = "whatsapp_messages_v2"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    waba_id = Column(Integer, ForeignKey("whatsapp_business_accounts.id"), nullable=False)
    phone_number_id = Column(Integer, ForeignKey("whatsapp_phone_numbers.id"), nullable=False)
    message_id = Column(String(256), nullable=False, unique=True, index=True)
    direction = Column(String(20), nullable=False)
    contact_phone = Column(String(32), nullable=True)
    contact_name = Column(String(128), nullable=True)
    message_type = Column(String(50), default="text")
    template_name = Column(String(100), nullable=True)
    content_hash = Column(String(64), nullable=True)
    status = Column(String(50), default="sent")
    ai_processed = Column(Boolean, default=False)
    predicted_priority = Column(String(50), nullable=True)
    predicted_context = Column(String(100), nullable=True)
    prediction_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Relationships
    business_account = relationship("WhatsAppBusinessAccount", back_populates="messages")
    # Indexes
    __table_args__ = (
        Index('idx_tenant_messages', 'user_id', 'waba_id', 'created_at'),
        Index('idx_v2_message_id', 'message_id'),
    )
    def __repr__(self):
        return f'<WAMessageV2 {self.message_id}>'

class WhatsAppWebhook(Base):
    __tablename__ = "whatsapp_webhooks"
    id = Column(Integer, primary_key=True, index=True)
    webhook_id = Column(String(256), nullable=False, unique=True, index=True)
    event_type = Column(String(50), nullable=False)
    message_id = Column(String(256), nullable=True)
    status = Column(String(50), nullable=True)
    webhook_data = Column(JSON, nullable=True)
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime, default=datetime.utcnow)
    # Indexes
    __table_args__ = (
        Index('idx_webhook_id', 'webhook_id'),
        Index('idx_event_type', 'event_type'),
    )
    def __repr__(self):
        return f'<Webhook {self.webhook_id}>'

class MessageMetadata(Base):
    __tablename__ = "message_metadata"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    waba_id = Column(Integer, ForeignKey("whatsapp_business_accounts.id"), nullable=True)
    source = Column(String(32), nullable=False)
    external_id = Column(String(256), nullable=True, index=True)
    subject_preview = Column(String(100), nullable=True)
    sender_domain = Column(String(100), nullable=True)
    content_hash = Column(String(64), nullable=True)
    predicted_priority = Column(String(50), nullable=True)
    predicted_context = Column(String(100), nullable=True)
    prediction_confidence = Column(Float, nullable=True)
    prediction_details = Column(JSON, nullable=True)
    feedback_priority = Column(String(50), nullable=True)
    feedback_context = Column(String(100), nullable=True)
    feedback_provided_at = Column(DateTime, nullable=True)
    ai_processed = Column(Boolean, default=False)
    used_in_retrain = Column(Boolean, default=False)
    received_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    # Relationships
    user = relationship("User", back_populates="messages")
    # Indexes
    __table_args__ = (
        Index('idx_tenant_metadata', 'user_id', 'source', 'created_at'),
        Index('idx_ai_processing', 'ai_processed', 'created_at'),
        Index('idx_predictions', 'predicted_priority', 'predicted_context'),
        Index('idx_feedback', 'feedback_priority', 'feedback_context'),
        Index('idx_external_id', 'external_id'),
        Index('idx_content_hash', 'content_hash'),
    )

    # --- TenantConfiguration model for multi-tenant settings ---
class TenantConfiguration(Base):
        __tablename__ = "tenant_configurations"
        id = Column(Integer, primary_key=True, index=True)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        config_key = Column(String(100), nullable=False)
        config_value = Column(String(500), nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        # Relationships
        user = relationship("User")
        __table_args__ = (
            Index('idx_tenant_config_user_key', 'user_id', 'config_key'),
        )
        def __repr__(self):
            return f'<TenantConfiguration {self.user_id} {self.config_key}>'